"""Dependency-free linear-chain span tagger for local, offline inference.

The model is an averaged structured perceptron over BIO tags with first-order
transitions (Collins, 2002). Inference is pure Python, so it needs no optional
dependency, GPU or model download.

Model files are JSON or gzip-compressed JSON, never pickle, so loading a model
cannot execute code. Feature strings are stored only as keyed 64-bit BLAKE2b
digests, and training drops features seen in fewer than ``min_feature_docs``
documents. That keeps rare training tokens (for example a name that occurs in a
single record) out of the file in plain text, but common hashed features can
still be confirmed by a dictionary attack: treat model files trained on private
data as sensitive. A SHA-256 check proves integrity, not who published a file.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from operator import add
from pathlib import Path
from typing import Any

from deidflow.core import Finding
from deidflow.transformations import replacement_only

FORMAT = "deidflow.span-tagger"
FORMAT_VERSION = 1
FEATURE_SET = "es-1"
MAX_MODEL_BYTES = 256 * 1024**2
_NEG = float("-inf")
_TOKEN = re.compile(r"\w+|[^\w\s]")
_PERSON = b"deidflow.es-1"
_MEDIUM_RISK = frozenset(
    {"LOCATION", "ORGANIZATION", "MEDICAL_FACILITY", "OCCUPATION", "DEMOGRAPHIC"}
)

# name -> (resource file, SHA-256). Resources ship inside the wheel. See NOTICE
# for training-data attribution and docs/TAGGER.md for the model card.
BUILTIN_MODELS: dict[str, tuple[str, str]] = {
    "es-clinical": (
        "es-clinical-meddocan-1.json.gz",
        "dc824100552ddb5bae036d128da9cfe4e31aba68b7cb74c2ab1252ddc0952da9",
    ),
    "es-finance": (
        "es-finance-gretel-1.json.gz",
        "f7a28b8fef3ccc1090d171b693f744098b4032008a48b56530c5aabdf371679c",
    ),
}


def builtin_profiles() -> dict[str, dict[str, dict[str, Any]]]:
    """Packaged operating profiles: ``{model: {profile: {margins and measurements}}}``."""
    text = resources.files("deidflow.models").joinpath("profiles.json").read_text("utf-8")
    profiles = json.loads(text)
    if not isinstance(profiles, dict):
        raise ValueError("Packaged tagger profiles are malformed")
    return profiles


def tokenize(text: str) -> list[tuple[int, int]]:
    """Word and single-punctuation tokens as half-open character offsets."""
    return [match.span() for match in _TOKEN.finditer(text)]


def _shape(word: str) -> str:
    out = []
    for character in word[:16]:
        if character.isdigit():
            out.append("d")
        elif character.isupper():
            out.append("X")
        elif character.isalpha():
            out.append("x")
        else:
            out.append(character)
    return "".join(out)


def _short_shape(shape: str) -> str:
    out: list[str] = []
    for character in shape:
        if not out or out[-1] != character:
            out.append(character)
    return "".join(out)


def _length(word: str) -> str:
    size = len(word)
    if size <= 3:
        return str(size)
    return "4-5" if size <= 5 else "6-8" if size <= 8 else "9+"


def token_features(text: str, tokens: Sequence[tuple[int, int]]) -> list[list[str]]:
    """Feature strings per token for feature set ``es-1``.

    Context covers two tokens on each side plus the field label of the current
    line (the one and two tokens before the most recent colon), which captures the
    ``Nombre: ...`` and ``Edad: 70 Sexo: H`` layouts of forms and clinical headers.
    """
    words = [text[start:end] for start, end in tokens]
    lowers = [word.casefold()[:32] for word in words]
    shapes = [_shape(word) for word in words]
    shorts = [_short_shape(shape) for shape in shapes]
    count = len(tokens)
    newline = [
        index == 0 or "\n" in text[tokens[index - 1][1] : tokens[index][0]]
        for index in range(count)
    ]

    def word(index: int) -> str:
        return lowers[index] if 0 <= index < count else ("<s>" if index < 0 else "</s>")

    def short(index: int) -> str:
        return shorts[index] if 0 <= index < count else ("<s>" if index < 0 else "</s>")

    result: list[list[str]] = []
    label = last_label = ""
    since = 0
    position = 0
    for index in range(count):
        if newline[index]:
            label, last_label, since, position = "", "", 0, 0
        current = lowers[index]
        original = words[index]
        features = [
            "b",
            "w=" + current,
            "sh=" + shorts[index],
            "fs=" + shapes[index][:10],
            "p3=" + current[:3],
            "x2=" + current[-2:],
            "x3=" + current[-3:],
            "x4=" + current[-4:],
            "len=" + _length(original),
            "w-1=" + word(index - 1),
            "w+1=" + word(index + 1),
            "w-2=" + word(index - 2),
            "w+2=" + word(index + 2),
            "w-2|w-1=" + word(index - 2) + "|" + word(index - 1),
            "w+1|w+2=" + word(index + 1) + "|" + word(index + 2),
            "sh-1=" + short(index - 1),
            "sh+1=" + short(index + 1),
            "sh-1|sh|sh+1=" + short(index - 1) + "|" + shorts[index] + "|" + short(index + 1),
            "lp=" + str(min(position, 6)),
        ]
        if newline[index]:
            features.append("bol")
        if index + 1 == count or newline[index + 1]:
            features.append("eol")
        if original[:1].isupper():
            features.append("T")
        if original.isupper() and len(original) > 1:
            features.append("U")
        if original.isdigit():
            features.append("D" + str(min(len(original), 12)))
        elif any(character.isdigit() for character in original):
            features.append("HD")
        if label:
            since_bucket = str(min(since, 4))
            features.extend(("lab=" + label, "lab|sc=" + label + "|" + since_bucket))
            features.append("lab|w=" + label + "|" + current)
            features.append("lab1|sc=" + last_label + "|" + since_bucket)
        else:
            features.append("nolab")
        result.append(features)
        if original == ":":
            label = " ".join(lowers[max(0, index - 2) : index]) if index else ""
            last_label = lowers[index - 1] if index else ""
            since = 0
        elif label:
            since += 1
        position += 1
    return result


@lru_cache(maxsize=1 << 18)
def feature_key(feature: str) -> str:
    """Keyed 64-bit digest; model files never contain plaintext feature strings."""
    return hashlib.blake2b(
        feature.encode("utf-8", "surrogatepass"), digest_size=8, person=_PERSON
    ).hexdigest()


def _bio_parts(labels: Sequence[str]) -> list[tuple[str, str]]:
    parts = []
    for label in labels:
        if label == "O":
            parts.append(("O", ""))
        elif label[:2] in {"B-", "I-"} and len(label) > 2:
            parts.append((label[0], label[2:]))
        else:
            raise ValueError("Tagger labels must be O, B-<TYPE> or I-<TYPE>")
    return parts


def allowed_transition(previous: str, current: str) -> bool:
    """BIO constraint: ``I-X`` may only follow ``B-X`` or ``I-X``."""
    if not current.startswith("I-"):
        return True
    return previous in {"B-" + current[2:], "I-" + current[2:]}


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _finite(value: Any) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("Tagger model contains a non-finite weight")
    return float(value)


@dataclass(frozen=True, slots=True)
class TaggedSpan:
    """A model span with its max-marginal margin (best path minus best alternative)."""

    entity_type: str
    start: int
    end: int
    margin: float
    near_miss: bool = False


class SpanTagger:
    """Local statistical span detector usable as ``DeidEngine(nlp=...)``.

    Scores are Platt-calibrated estimates of exact span correctness when the
    model carries a calibration fitted on held-out data, and then also populate
    ``Finding.confidence``. Without calibration every span scores 0.75 and
    ``confidence`` stays ``None``.

    Two optional margins act on tokens the model tagged ``O`` by only a small
    margin (best path score minus the best path that labels the token as an
    entity), trading utility for recall:

    - ``review_margin``: such tokens become near-miss candidates scored 0.5,
      below the default review gate, so the document needs human review.
    - ``redact_margin``: such tokens (outside ``review_margin``) become
      candidates scored 0.75, at the default gate, so they are transformed
      without forcing review. This over-redacts on purpose.

    ``profile`` selects packaged, validation-tuned margins for built-in models
    (see :meth:`builtin`); explicit margins override it.
    """

    def __init__(
        self,
        model: Mapping[str, Any],
        *,
        labels: Mapping[str, str] | None = None,
        review_margin: float | None = None,
        redact_margin: float | None = None,
        max_segment_tokens: int = 4000,
        accelerate: bool | None = None,
    ) -> None:
        if accelerate not in {None, True, False}:
            raise ValueError("accelerate must be None, True or False")
        for name, value in (("review_margin", review_margin), ("redact_margin", redact_margin)):
            if value is not None and (type(value) not in {int, float} or not 0 < value < 1e6):
                raise ValueError(f"{name} must be a positive number")
        if type(max_segment_tokens) is not int or max_segment_tokens < 64:
            raise ValueError("max_segment_tokens must be an integer of at least 64")
        if model.get("format") != FORMAT or model.get("format_version") != FORMAT_VERSION:
            raise ValueError("Unsupported span tagger model format")
        if model.get("feature_set") != FEATURE_SET:
            raise ValueError("Unsupported span tagger feature set")
        tags = model.get("labels")
        if not isinstance(tags, list) or not tags or tags[0] != "O" or len(set(tags)) != len(tags):
            raise ValueError("Tagger labels must start with O and be unique")
        self.tags: tuple[str, ...] = tuple(str(tag) for tag in tags)
        self._parts = _bio_parts(self.tags)
        size = len(self.tags)
        start = model.get("start")
        transitions = model.get("transitions")
        if (
            not isinstance(start, list)
            or len(start) != size
            or not isinstance(transitions, list)
            or len(transitions) != size
            or any(not isinstance(row, list) or len(row) != size for row in transitions)
        ):
            raise ValueError("Tagger transition dimensions do not match its labels")
        self._start = [
            _finite(value) if not tag.startswith("I-") else _NEG
            for tag, value in zip(self.tags, start, strict=True)
        ]
        # Column-major transitions for the forward pass, row-major for backward.
        matrix = [
            [
                _finite(transitions[p][c])
                if allowed_transition(self.tags[p], self.tags[c])
                else _NEG
                for c in range(size)
            ]
            for p in range(size)
        ]
        self._rows = matrix
        self._columns = [[matrix[p][c] for p in range(size)] for c in range(size)]
        self._inside_previous: dict[int, tuple[int, int]] = {}
        for index, (prefix, kind) in enumerate(self._parts):
            if prefix == "I":
                self._inside_previous[index] = (
                    self.tags.index("B-" + kind),
                    index,
                )
        weights = model.get("weights")
        if not isinstance(weights, dict):
            raise ValueError("Tagger weights must be an object")
        compiled: dict[str, tuple[tuple[int, float], ...]] = {}
        for key, entries in weights.items():
            if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{16}", key):
                raise ValueError("Tagger weight keys must be feature digests")
            if not isinstance(entries, list):
                raise ValueError("Tagger weight entries must be lists")
            pairs = []
            for entry in entries:
                if (
                    not isinstance(entry, list)
                    or len(entry) != 2
                    or type(entry[0]) is not int
                    or not 0 <= entry[0] < size
                ):
                    raise ValueError("Tagger weight entry is malformed")
                pairs.append((entry[0], _finite(entry[1])))
            compiled[key] = tuple(pairs)
        self._weights = compiled
        calibration = model.get("calibration")
        self._calibration: tuple[float, float] | None = None
        if calibration is not None:
            if (
                not isinstance(calibration, dict)
                or calibration.get("method") != "platt"
                or calibration.get("feature") != "log1p_margin"
            ):
                raise ValueError("Unsupported tagger calibration")
            self._calibration = (_finite(calibration["a"]), _finite(calibration["b"]))
        self.metadata: dict[str, Any] = dict(model.get("metadata") or {})
        self.model_version = str(self.metadata.get("version", "unversioned"))
        kinds = {kind for _, kind in self._parts if kind}
        self.labels = dict(labels) if labels is not None else {kind: kind for kind in kinds}
        if labels is not None and not labels:
            raise ValueError("Tagger label mapping must not be empty")
        self.review_margin = review_margin
        self.redact_margin = redact_margin
        self.max_segment_tokens = max_segment_tokens
        self._cache: dict[str, Any] = {}
        self._numpy: Any = None
        if accelerate is not False:
            try:
                import numpy
            except ImportError:
                if accelerate:
                    raise ImportError("accelerate=True requires NumPy") from None
            else:
                self._prepare_numpy(numpy)
        self.accelerated = self._numpy is not None

    # -- loading -----------------------------------------------------------------

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        sha256: str | None = None,
        **options: Any,
    ) -> SpanTagger:
        """Load a JSON or ``.json.gz`` model file; optionally verify its SHA-256."""
        payload = Path(path).read_bytes()
        return cls.from_bytes(payload, sha256=sha256, **options)

    @classmethod
    def from_bytes(cls, payload: bytes, *, sha256: str | None = None, **options: Any) -> SpanTagger:
        if len(payload) > MAX_MODEL_BYTES:
            raise ValueError("Tagger model exceeds size limit")
        if sha256 is not None and hashlib.sha256(payload).hexdigest() != sha256.lower():
            raise ValueError("Tagger model SHA-256 mismatch")
        if payload[:2] == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                payload = stream.read(MAX_MODEL_BYTES + 1)
            if len(payload) > MAX_MODEL_BYTES:
                raise ValueError("Decompressed tagger model exceeds size limit")
        try:
            model = json.loads(payload.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Tagger model is not valid JSON") from None
        if not isinstance(model, dict):
            raise ValueError("Tagger model must be a JSON object")
        return cls(model, **options)

    @classmethod
    def builtin(cls, name: str, *, profile: str | None = None, **options: Any) -> SpanTagger:
        """Load a model shipped inside the package, verifying its pinned digest.

        ``profile`` applies packaged operating margins tuned on validation data
        (``models/profiles.json``); explicitly passed margins take precedence.
        """
        if name not in BUILTIN_MODELS:
            raise ValueError(
                "Unknown built-in tagger; available: " + ", ".join(sorted(BUILTIN_MODELS))
            )
        if profile is not None:
            settings = builtin_profiles().get(name, {}).get(profile)
            if settings is None:
                raise ValueError(f"Unknown profile {profile!r} for built-in tagger {name!r}")
            for key in ("review_margin", "redact_margin"):
                if options.get(key) is None and settings.get(key) is not None:
                    options[key] = settings[key]
        resource, digest = BUILTIN_MODELS[name]
        payload = resources.files("deidflow.models").joinpath(resource).read_bytes()
        return cls.from_bytes(payload, sha256=digest, **options)

    # -- inference ---------------------------------------------------------------

    def _prepare_numpy(self, np: Any) -> None:
        size = len(self.tags)
        index = {key: row for row, key in enumerate(self._weights, 1)}
        # Row 0 stays zero: every token also points at it, so no segment is empty.
        dense = np.zeros((len(index) + 1, size))
        for key, row in index.items():
            for label, weight in self._weights[key]:
                dense[row, label] = weight
        transitions = np.array(self._rows, dtype=float)
        self._numpy = np
        self._dense = dense
        self._index = index
        self._np_transitions = transitions
        self._np_start = np.array(self._start, dtype=float)
        self._np_columns = np.arange(size)

    def _lookup(self, feature: str) -> Any:
        cache = self._cache
        value = cache.get(feature)
        if value is None:
            if len(cache) >= 1 << 19:
                cache.clear()
            key = feature_key(feature)
            value = (
                self._index.get(key, 0) if self._numpy is not None else self._weights.get(key, ())
            )
            cache[feature] = value
        return value

    def _emissions(self, features: list[list[str]]) -> list[list[float]]:
        size = len(self.tags)
        out = []
        lookup = self._lookup
        for token_features in features:
            row = [0.0] * size
            for feature in token_features:
                for label, weight in lookup(feature):
                    row[label] += weight
            out.append(row)
        return out

    def _decode_numpy(
        self, features: list[list[str]]
    ) -> tuple[list[int], list[list[float]], float]:
        np = self._numpy
        lookup = self._lookup
        ids: list[int] = []
        offsets: list[int] = []
        for token_features in features:
            offsets.append(len(ids))
            ids.append(0)
            ids.extend(row for row in map(lookup, token_features) if row)
        emissions = np.add.reduceat(self._dense[ids], offsets, axis=0)
        count, size = emissions.shape
        transitions = self._np_transitions
        columns = self._np_columns
        alpha = np.empty((count, size))
        back = np.zeros((count, size), dtype=np.intp)
        alpha[0] = self._np_start + emissions[0]
        for t in range(1, count):
            candidates = alpha[t - 1][:, None] + transitions
            pointers = candidates.argmax(0)
            back[t] = pointers
            alpha[t] = candidates[pointers, columns] + emissions[t]
        beta = np.zeros((count, size))
        for t in range(count - 2, -1, -1):
            beta[t] = (transitions + (emissions[t + 1] + beta[t + 1])).max(1)
        last = int(alpha[-1].argmax())
        best = float(alpha[-1, last])
        path = [last]
        back_rows = back.tolist()
        for t in range(count - 1, 0, -1):
            path.append(back_rows[t][path[-1]])
        path.reverse()
        return path, (alpha + beta).tolist(), best

    def _decode(self, emissions: list[list[float]]) -> tuple[list[int], list[list[float]], float]:
        """Viterbi path, max-marginals and best path score under BIO constraints."""
        size = len(self.tags)
        count = len(emissions)
        alpha = [list(map(add, self._start, emissions[0]))]
        back: list[list[int]] = [[0] * size]
        columns, inside = self._columns, self._inside_previous
        for t in range(1, count):
            previous = alpha[-1]
            emission = emissions[t]
            row = [0.0] * size
            pointers = [0] * size
            for current in range(size):
                pair = inside.get(current)
                if pair is not None:
                    begin, same = pair
                    column = columns[current]
                    first = previous[begin] + column[begin]
                    second = previous[same] + column[same]
                    if second > first:
                        row[current], pointers[current] = second + emission[current], same
                    else:
                        row[current], pointers[current] = first + emission[current], begin
                else:
                    candidates = list(map(add, previous, columns[current]))
                    best = max(candidates)
                    row[current] = best + emission[current]
                    pointers[current] = candidates.index(best)
            alpha.append(row)
            back.append(pointers)
        last = alpha[-1]
        best_score = max(last)
        path = [last.index(best_score)]
        for t in range(count - 1, 0, -1):
            path.append(back[t][path[-1]])
        path.reverse()
        beta = [[0.0] * size for _ in range(count)]
        rows = self._rows
        for t in range(count - 2, -1, -1):
            following = list(map(add, emissions[t + 1], beta[t + 1]))
            beta[t] = [max(map(add, rows[current], following)) for current in range(size)]
        marginals = [list(map(add, alpha[t], beta[t])) for t in range(count)]
        return path, marginals, best_score

    def _segments(self, text: str, tokens: list[tuple[int, int]]) -> list[tuple[int, int]]:
        limit = self.max_segment_tokens
        segments = []
        begin = 0
        for index in range(1, len(tokens)):
            length = index - begin
            boundary = "\n" in text[tokens[index - 1][1] : tokens[index][0]]
            if (boundary and length >= limit) or length >= 2 * limit:
                segments.append((begin, index))
                begin = index
        if tokens:
            segments.append((begin, len(tokens)))
        return segments

    def _score(self, margin: float) -> tuple[float, float | None]:
        if self._calibration is None:
            return 0.75, None
        a, b = self._calibration
        probability = min(0.999, max(0.001, _sigmoid(a * math.log1p(margin) + b)))
        return probability, probability

    def _candidate_margin(self) -> float | None:
        margins = [m for m in (self.review_margin, self.redact_margin) if m is not None]
        return max(margins) if margins else None

    def predict(self, text: str, *, candidate_margin: float | None = None) -> list[TaggedSpan]:
        """Raw model spans with max-marginal margins, before label mapping.

        Near-miss candidates are collected up to ``candidate_margin`` (default:
        the larger of the configured margins). Spans whose letters and digits
        all belong to DeidFlow replacement tokens are dropped.
        """
        threshold = self._candidate_margin() if candidate_margin is None else candidate_margin
        tokens = tokenize(text)
        if not tokens:
            return []
        features = token_features(text, tokens)
        spans: list[TaggedSpan] = []
        for begin, end in self._segments(text, tokens):
            if self._numpy is not None:
                path, marginals, best = self._decode_numpy(features[begin:end])
            else:
                path, marginals, best = self._decode(self._emissions(features[begin:end]))
            spans.extend(self._path_spans(tokens, begin, path, marginals, best))
            if threshold is not None:
                spans.extend(
                    self._near_misses(tokens, begin, path, marginals, best, float(threshold))
                )
        spans = [s for s in spans if not replacement_only(text, s.start, s.end)]
        return sorted(spans, key=lambda s: (s.start, s.end, s.entity_type))

    def detect(self, text: str) -> list[Finding]:
        return self.to_findings(self.predict(text))

    def to_findings(self, spans: Iterable[TaggedSpan]) -> list[Finding]:
        """Map spans to findings under the current label mapping and margins."""
        findings = []
        review = self.review_margin or 0.0
        redact = self.redact_margin or 0.0
        for span in spans:
            kind = self.labels.get(span.entity_type)
            if kind is None:
                continue
            risk = "medium" if kind in _MEDIUM_RISK else "high"
            if span.near_miss:
                context: tuple[str, ...]
                if span.margin < review:
                    score, context = 0.5, ("near_miss",)
                elif span.margin < redact:
                    score, context = 0.75, ("near_miss", "redact_only")
                else:
                    continue
                findings.append(
                    Finding(
                        kind,
                        span.start,
                        span.end,
                        score,
                        "tagger.local",
                        validation="statistical_candidate",
                        context=context,
                        model_version=self.model_version,
                        risk=risk,
                    )
                )
                continue
            score, confidence = self._score(span.margin)
            findings.append(
                Finding(
                    kind,
                    span.start,
                    span.end,
                    score,
                    "tagger.local",
                    validation="statistical",
                    model_version=self.model_version,
                    confidence=confidence,
                    risk=risk,
                )
            )
        return findings

    def _path_spans(
        self,
        tokens: list[tuple[int, int]],
        offset: int,
        path: list[int],
        marginals: list[list[float]],
        best: float,
    ) -> list[TaggedSpan]:
        out: list[TaggedSpan] = []
        parts = self._parts
        index = 0
        while index < len(path):
            prefix, kind = parts[path[index]]
            if prefix == "O":
                index += 1
                continue
            stop = index + 1
            while stop < len(path) and parts[path[stop]] == ("I", kind):
                stop += 1
            margin = min(
                best - max(v for label, v in enumerate(marginals[t]) if label != path[t])
                for t in range(index, stop)
            )
            out.append(
                TaggedSpan(
                    kind,
                    tokens[offset + index][0],
                    tokens[offset + stop - 1][1],
                    max(0.0, margin),
                )
            )
            index = stop
        return out

    def _near_misses(
        self,
        tokens: list[tuple[int, int]],
        offset: int,
        path: list[int],
        marginals: list[list[float]],
        best: float,
        threshold: float,
    ) -> list[TaggedSpan]:
        flagged: list[tuple[int, str, float]] = []
        for t, label in enumerate(path):
            if label != 0:
                continue
            row = marginals[t]
            alternative = max(range(1, len(row)), key=row.__getitem__)
            gap = best - row[alternative]
            if gap < threshold:
                flagged.append((t, self._parts[alternative][1], gap))
        out: list[TaggedSpan] = []
        index = 0
        while index < len(flagged):
            t, kind, gap = flagged[index]
            stop = index + 1
            while (
                stop < len(flagged)
                and flagged[stop][0] == flagged[stop - 1][0] + 1
                and flagged[stop][1] == kind
            ):
                gap = min(gap, flagged[stop][2])
                stop += 1
            out.append(
                TaggedSpan(
                    kind,
                    tokens[offset + t][0],
                    tokens[offset + flagged[stop - 1][0]][1],
                    gap,
                    near_miss=True,
                )
            )
            index = stop
        return out

    def detect_batch(self, texts: list[str]) -> list[list[Finding]]:
        try:
            return [self.detect(text) for text in texts]
        except Exception:
            # Never chain an exception that might carry document text.
            raise RuntimeError(
                "Local tagger inference failed; processing must be blocked"
            ) from None

    def entity_types(self) -> list[str]:
        return sorted(set(self.labels.values()))


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON constants are not allowed in tagger models")


def bio_tags(
    tokens: Sequence[tuple[int, int]], spans: Iterable[tuple[str, int, int]]
) -> tuple[list[str], int]:
    """Gold BIO tags; returns the tags and the number of spans that could not be aligned.

    A span aligns when it starts at a token start and ends at a token end and
    does not overlap an earlier-aligned span. Unaligned spans are counted, never
    silently stretched.
    """
    tags = ["O"] * len(tokens)
    starts = {start: index for index, (start, _) in enumerate(tokens)}
    ends = {end: index for index, (_, end) in enumerate(tokens)}
    skipped = 0
    for kind, start, end in sorted(spans, key=lambda s: (s[1], -(s[2] - s[1]))):
        first, last = starts.get(start), ends.get(end)
        if (
            first is None
            or last is None
            or last < first
            or any(tag != "O" for tag in tags[first : last + 1])
        ):
            skipped += 1
            continue
        tags[first] = "B-" + kind
        for index in range(first + 1, last + 1):
            tags[index] = "I-" + kind
    return tags, skipped


__all__ = [
    "BUILTIN_MODELS",
    "FEATURE_SET",
    "builtin_profiles",
    "FORMAT",
    "FORMAT_VERSION",
    "SpanTagger",
    "TaggedSpan",
    "allowed_transition",
    "bio_tags",
    "feature_key",
    "token_features",
    "tokenize",
]
