"""Route each document to the span tagger trained for its domain.

A multinomial Naive Bayes document classifier over hashed word features picks
the configured clinical or financial route. The packaged configuration uses the
clinical tagger for clinical text and the general tagger for financial or weak
domain evidence. Custom mixed routes can fuse several explicitly selected taggers.
Inference is pure Python; model files are JSON (never pickle) and, like tagger
models, store only keyed feature digests.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from importlib import resources
from typing import Any

from deidflow.core import Finding
from deidflow.detectors import fuse
from deidflow.nlp.tagger import MAX_MODEL_BYTES, SpanTagger, feature_key, tokenize
from deidflow.normalization import DetectionView, ordinal_feature_text

ROUTER_FORMAT = "deidflow.domain-router"
ROUTER_FORMAT_VERSION = 1
BUILTIN_ROUTER = (
    "es-domain-router-1.json.gz",
    "316d2ee699ddee08879d0835df894715ae14b1ae176f1794b45b283d82ff6324",
)
# Chosen on validation (MEDDOCAN dev, Gretel train holdout): the smallest margin
# with at most 1% of each domain's documents routed to the wrong single tagger.
DEFAULT_MIN_EVIDENCE = 0.5


def _features(text: str, limit: int = 20000) -> Counter[str]:
    words = [text[s:e].casefold() for s, e in tokenize(text[:limit])]
    return Counter(feature_key("w=" + w[:32]) for w in words if any(c.isalpha() for c in w))


def train_router(
    documents: Mapping[str, Sequence[str]], *, min_docs: int = 5, max_features: int = 20000
) -> dict[str, Any]:
    """Fit per-domain log-probabilities with Laplace smoothing and uniform priors."""
    if len(documents) < 2 or any(not texts for texts in documents.values()):
        raise ValueError("Router training needs at least two nonempty domains")
    document_frequency: Counter[str] = Counter()
    counts: dict[str, Counter[str]] = {}
    for domain, texts in documents.items():
        counts[domain] = Counter()
        for text in texts:
            features = _features(text)
            counts[domain].update(features)
            document_frequency.update(features.keys())
    vocabulary = [
        key
        for key, n in sorted(document_frequency.items(), key=lambda item: (-item[1], item[0]))
        if n >= min_docs
    ][:max_features]
    weights: dict[str, list[float]] = {}
    domains = sorted(documents)
    totals = {d: sum(counts[d][k] for k in vocabulary) + len(vocabulary) for d in domains}
    for key in sorted(vocabulary):
        weights[key] = [round(math.log((counts[d][key] + 1) / totals[d]), 5) for d in domains]
    unknown = [round(math.log(1 / totals[d]), 5) for d in domains]
    return {
        "format": ROUTER_FORMAT,
        "format_version": ROUTER_FORMAT_VERSION,
        "domains": domains,
        "weights": weights,
        "unknown": unknown,
        "metadata": {
            "algorithm": "multinomial Naive Bayes, uniform priors, Laplace smoothing",
            "feature_hashing": "keyed BLAKE2b-64 word features, as in tagger models",
            "min_docs": min_docs,
            "documents": {d: len(documents[d]) for d in domains},
        },
    }


class DomainRouter:
    """``nlp`` adapter that runs the tagger of each document's predicted domain.

    ``taggers`` maps router domains to taggers. A document whose mean per-token
    log-likelihood ratio between the two best domains is below ``min_evidence``
    is ``"mixed"`` and runs the ``mixed`` taggers (by default every tagger).
    """

    def __init__(
        self,
        model: Mapping[str, Any],
        taggers: Mapping[str, Any],
        *,
        min_evidence: float = DEFAULT_MIN_EVIDENCE,
        mixed: Sequence[Any] | None = None,
    ) -> None:
        if (
            model.get("format") != ROUTER_FORMAT
            or model.get("format_version") != ROUTER_FORMAT_VERSION
        ):
            raise ValueError("Unsupported domain router format")
        domains = model.get("domains")
        if not isinstance(domains, list) or len(domains) < 2:
            raise ValueError("Domain router needs at least two domains")
        if set(taggers) != set(domains):
            raise ValueError("Router taggers must cover exactly the router's domains")
        weights = model.get("weights")
        unknown = model.get("unknown")
        if not isinstance(weights, dict) or not isinstance(unknown, list):
            raise ValueError("Domain router weights are malformed")
        size = len(domains)
        for key, row in weights.items():
            if (
                not isinstance(key, str)
                or len(key) != 16
                or not isinstance(row, list)
                or len(row) != size
                or not all(type(v) in {int, float} and math.isfinite(v) for v in row)
            ):
                raise ValueError("Domain router weight entry is malformed")
        if len(unknown) != size or not all(
            type(v) in {int, float} and math.isfinite(v) for v in unknown
        ):
            raise ValueError("Domain router weights are malformed")
        if type(min_evidence) not in {int, float} or min_evidence < 0:
            raise ValueError("min_evidence must be a nonnegative number")
        self.domains: tuple[str, ...] = tuple(domains)
        self._weights: dict[str, list[float]] = {
            k: [float(v) for v in r] for k, r in weights.items()
        }
        self._unknown = [float(v) for v in unknown]
        self.taggers = dict(taggers)
        fallback = list(self.taggers.values()) if mixed is None else list(mixed)
        if not fallback:
            raise ValueError("Mixed-domain documents need at least one tagger")
        unique: dict[int, Any] = {}
        for tagger in fallback:
            unique.setdefault(id(tagger), tagger)
        self.mixed: tuple[Any, ...] = tuple(unique.values())
        self.min_evidence = float(min_evidence)
        self.metadata = dict(model.get("metadata") or {})

    @classmethod
    def from_bytes(cls, payload: bytes, taggers: Mapping[str, Any], **options: Any) -> DomainRouter:
        if len(payload) > MAX_MODEL_BYTES:
            raise ValueError("Domain router model exceeds size limit")
        if payload[:2] == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                payload = stream.read(MAX_MODEL_BYTES + 1)
        try:
            model = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Domain router model is not valid JSON") from None
        if not isinstance(model, dict):
            raise ValueError("Domain router model must be a JSON object")
        return cls(model, taggers, **options)

    @classmethod
    def builtin(cls, *, profile: str | None = None, **options: Any) -> DomainRouter:
        """Packaged router: clinical documents to ``es-clinical``, all others to ``es-general``.

        ``es-general`` (trained on clinical, financial and multi-country synthetic
        documents) replaced ``es-finance`` on the financial route and for
        mixed-evidence documents because it scored higher on the financial and
        synthetic validation splits (``docs/TAGGER.md``).
        """
        resource, digest = BUILTIN_ROUTER
        payload = resources.files("deidflow.models").joinpath(resource).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("Packaged domain router SHA-256 mismatch")
        general = SpanTagger.builtin("es-general", profile=profile)
        taggers = {
            "clinical": SpanTagger.builtin("es-clinical", profile=profile),
            "financial": general,
        }
        options.setdefault("mixed", [general])
        return cls.from_bytes(payload, taggers, **options)

    def scores(self, text: str) -> dict[str, float]:
        """Mean per-token log-likelihood of the text under each domain."""
        features = _features(text)
        total = sum(features.values())
        sums = [0.0] * len(self.domains)
        for key, count in features.items():
            row = self._weights.get(key, self._unknown)
            for index, value in enumerate(row):
                sums[index] += count * value
        return {d: (s / total if total else 0.0) for d, s in zip(self.domains, sums, strict=True)}

    def route(self, text: str) -> str:
        """The predicted domain, or ``"mixed"`` when the evidence is weak."""
        scores = self.scores(text)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not text.strip() or ranked[0][1] - ranked[1][1] < self.min_evidence:
            return "mixed"
        return ranked[0][0]

    def detect(self, text: str) -> list[Finding]:
        domain = self.route(text)
        selected = self.mixed if domain == "mixed" else (self.taggers[domain],)
        findings: list[Finding] = []
        for tagger in selected:
            findings.extend(tagger.detect(text))
        return fuse(findings)

    def detect_batch(self, texts: list[str]) -> list[list[Finding]]:
        try:
            return [self.detect(text) for text in texts]
        except Exception:
            raise RuntimeError(
                "Local tagger inference failed; processing must be blocked"
            ) from None

    def detect_views(self, sources: list[str], views: list[DetectionView]) -> list[list[Finding]]:
        if len(sources) != len(views):
            raise ValueError("Normalized inference source/view batch length differs")
        result = []
        try:
            for source, view in zip(sources, views, strict=True):
                domain = self.route(ordinal_feature_text(source, view))
                selected = self.mixed if domain == "mixed" else (self.taggers[domain],)
                findings: list[Finding] = []
                for tagger in selected:
                    detect_views = getattr(tagger, "detect_views", None)
                    if callable(detect_views):
                        predicted = detect_views([source], [view])
                        if len(predicted) != 1:
                            raise ValueError("NLP adapter returned an invalid batch length")
                        findings.extend(predicted[0])
                    else:
                        findings.extend(tagger.detect(view.text))
                result.append(fuse(findings))
        except Exception:
            raise RuntimeError(
                "Local tagger inference failed; processing must be blocked"
            ) from None
        return result


def route_counts(router: DomainRouter, texts: Iterable[str]) -> dict[str, int]:
    return dict(Counter(router.route(text) for text in texts))


__all__ = ["DEFAULT_MIN_EVIDENCE", "DomainRouter", "route_counts", "train_router"]
