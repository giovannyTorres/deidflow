"""Offline, staged adaptation of the Spanish span perceptron.

Training/validation select weights and calibration. A separately supplied test
and context regression set only measure the frozen artifacts. Passing the gate
never installs or activates a model. Fingerprints detect exact/normalised text
and explicit source-group reuse; they cannot detect undeclared related sources.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any

from deidflow.benchmarks.datasets import Example, GoldSpan
from deidflow.benchmarks.release_gate import release_gate_metrics
from deidflow.engine import DeidEngine
from deidflow.nlp.tagger import BUILTIN_MODELS, MAX_MODEL_BYTES, SpanTagger, tokenize
from deidflow.policies import Policy
from deidflow.private.security import protect
from deidflow.training.tagger import train_span_tagger

_LABEL = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_FORMAT = "deidflow.span-adaptation.v1"
_MAX_LINE = 8 * 1024**2


@dataclass(frozen=True)
class AdaptationConfig:
    epochs: int = 12
    patience: int = 3
    seed: int = 1729
    min_feature_docs: int = 2
    prune_below: float = 0.0

    def __post_init__(self) -> None:
        for name in ("epochs", "patience", "min_feature_docs"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if (
            type(self.prune_below) not in {int, float}
            or not math.isfinite(self.prune_below)
            or self.prune_below < 0
        ):
            raise ValueError("prune_below must be finite and nonnegative")


@dataclass(frozen=True)
class PromotionCriteria:
    """Frozen before fitting; rates are fractions, never percentages.

    Every candidate label is evaluated on the target holdout by default. A
    subset may be declared, but new labels cannot be excluded. All baseline
    labels also need independent context regression evidence.
    """

    target_types: tuple[str, ...] = ()
    minimum_documents: int = 100
    minimum_type_support: int = 20
    minimum_negative_documents: int = 20
    minimum_approved_documents: int = 5
    minimum_exact_recall: float = 0.95
    minimum_exact_precision: float = 0.90
    maximum_recall_drop: float = 0.0
    maximum_precision_drop: float = 0.0
    minimum_output_character_recall: float = 0.99
    maximum_approved_leak_rate: float = 0.0
    maximum_overredaction_rate: float = 0.02
    maximum_overredaction_increase: float = 0.0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name == "target_types":
                if not isinstance(value, (tuple, list)) or any(
                    not isinstance(kind, str) or not _LABEL.fullmatch(kind) for kind in value
                ):
                    raise ValueError("Invalid promotion target types")
                if len(value) != len(set(value)):
                    raise ValueError("Repeated promotion target type")
            elif name in {
                "minimum_documents",
                "minimum_type_support",
                "minimum_negative_documents",
                "minimum_approved_documents",
            }:
                if type(value) is not int or value < 1:
                    raise ValueError(f"{name} must be a positive integer")
            elif type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite fraction")


def _json(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _parse(payload: bytes) -> Any:
    def reject_constant(value: str) -> Any:
        raise ValueError("Non-finite JSON number")

    return json.loads(payload, object_pairs_hook=_unique_pairs, parse_constant=reject_constant)


def _read_bounded(path: Path, limit: int = MAX_MODEL_BYTES) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Artifact exceeds size limit")
    return payload


def load_adaptation_model(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load validated JSON/gzip or ``builtin:es-clinical``; never pickle."""
    if isinstance(source, Mapping):
        payload = _json(dict(source))
        if len(payload) > MAX_MODEL_BYTES:
            raise ValueError("Model exceeds size limit")
        model = _parse(payload)
    else:
        name = str(source)
        expected = None
        if name.startswith("builtin:"):
            key = name.removeprefix("builtin:")
            if key not in BUILTIN_MODELS:
                raise ValueError("Unknown builtin span model")
            filename, expected = BUILTIN_MODELS[key]
            payload = resources.files("deidflow.models").joinpath(filename).read_bytes()
        else:
            payload = _read_bounded(Path(source))
        if expected is not None and _sha(payload) != expected:
            raise ValueError("Builtin model digest mismatch")
        if payload.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                payload = stream.read(MAX_MODEL_BYTES + 1)
        if len(payload) > MAX_MODEL_BYTES:
            raise ValueError("Model exceeds size limit")
        model = _parse(payload)
    if not isinstance(model, dict):
        raise ValueError("Span model must be a JSON object")
    SpanTagger(model)
    return dict(model)


def load_adaptation_jsonl(path: str | Path, *, split: str) -> list[Example]:
    """Require id/text/group_id/spans; never silently assign source groups.

    Span objects contain ``start``, ``end`` and ``label`` (or ``entity_type``).
    A declared record split must equal the caller's expected split. Group IDs
    must identify the real source/patient/template family across all files.
    """
    examples = []
    with Path(path).open("rb") as stream:
        while line := stream.readline(_MAX_LINE + 1):
            if len(line) > _MAX_LINE:
                raise ValueError("Annotation line exceeds size limit")
            if not line.strip():
                continue
            record = _parse(line)
            if not isinstance(record, dict) or not isinstance(record.get("spans"), list):
                raise ValueError("Annotations require an object with spans")
            if record.get("split", split) != split:
                raise ValueError("Annotation split does not match its declared role")
            group = record.get("group_id", record.get("template_id"))
            if (
                "group_id" in record
                and "template_id" in record
                and record["group_id"] != record["template_id"]
            ):
                raise ValueError("Conflicting annotation source groups")
            spans = []
            for span in record["spans"]:
                if not isinstance(span, dict):
                    raise ValueError("Malformed span annotation")
                kind = span.get("label", span.get("entity_type"))
                if (
                    "label" in span
                    and "entity_type" in span
                    and span["label"] != span["entity_type"]
                ):
                    raise ValueError("Conflicting annotation labels")
                start, end = span.get("start"), span.get("end")
                if not isinstance(kind, str) or type(start) is not int or type(end) is not int:
                    raise ValueError("Invalid span label or offsets")
                spans.append(GoldSpan(kind, start, end))
            identifier, text = record.get("id"), record.get("text")
            if not all(isinstance(value, str) for value in (identifier, text, group)):
                raise ValueError("Nonempty document id, text and source group_id are required")
            assert isinstance(identifier, str) and isinstance(text, str) and isinstance(group, str)
            examples.append(Example(identifier, text, tuple(spans), split, group))
    _partition(examples, split)
    return examples


def _partition(examples: Sequence[Example], role: str) -> dict[str, Any]:
    if not examples:
        raise ValueError(f"The {role} partition is empty")
    identities: list[str] = []
    groups: list[str] = []
    contents: list[str] = []
    annotations: list[str] = []
    counts: Counter[str] = Counter()
    negative = 0
    for example in examples:
        if example.split != role:
            raise ValueError(f"Only {role} examples are accepted in this partition")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (example.id, example.text, example.template_id)
        ):
            raise ValueError("Nonempty document id, text and source group_id are required")
        tokens = tokenize(example.text)
        starts, ends = {start for start, _ in tokens}, {end for _, end in tokens}
        previous = -1
        for span in example.spans:
            if (
                not isinstance(span.entity_type, str)
                or not _LABEL.fullmatch(span.entity_type)
                or type(span.start) is not int
                or type(span.end) is not int
                or not 0 <= span.start < span.end <= len(example.text)
            ):
                raise ValueError("Invalid span label or offsets")
        for span in sorted(example.spans, key=lambda span: (span.start, span.end)):
            if span.start < previous:
                raise ValueError("Overlapping or duplicated span annotations")
            if span.start not in starts or span.end not in ends:
                raise ValueError("Span boundaries must align with complete tagger tokens")
            previous = span.end
            counts[span.entity_type] += 1
        normal = " ".join(unicodedata.normalize("NFKC", example.text).casefold().split())
        identities.append(_sha(example.id.strip().encode("utf-8")))
        groups.append(_sha(example.template_id.strip().encode("utf-8")))
        contents.append(_sha(normal.encode("utf-8")))
        annotations.append(_sha(_json(asdict(example))))
        negative += not example.spans
    if len(set(identities)) != len(identities):
        raise ValueError(f"Duplicate document ID in {role}")
    if len(set(contents)) != len(contents):
        raise ValueError(f"Duplicate normalized content in {role}")
    return {
        "role": role,
        "documents": len(examples),
        "negative_documents": negative,
        "spans_by_type": dict(sorted(counts.items())),
        "id_sha256": sorted(identities),
        "group_sha256": sorted(set(groups)),
        "content_sha256": sorted(contents),
        "annotations_sha256": sorted(annotations),
        "ordered_corpus_sha256": _sha(_json(annotations)),
    }


def _disjoint(partitions: Sequence[Mapping[str, Any]]) -> None:
    for field in ("id_sha256", "group_sha256", "content_sha256"):
        seen: set[str] = set()
        for partition in partitions:
            values = set(partition[field])
            if seen & values:
                raise ValueError(f"Partition leakage detected in {field}")
            seen.update(values)


def _new_directory(path: str | Path, payloads: Mapping[str, bytes]) -> Path:
    """Never overwrite an existing run (including a partially written run)."""
    destination = Path(path)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    protect(destination, directory=True)
    for name, payload in payloads.items():
        with (destination / name).open("xb") as stream:
            protect(destination / name, directory=False)
            stream.write(payload)
    return destination


def stage_span_adaptation(
    baseline: str | Path | Mapping[str, Any],
    train: Sequence[Example],
    validation: Sequence[Example],
    output_dir: str | Path,
    *,
    replay: Sequence[Example] = (),
    config: AdaptationConfig | None = None,
    criteria: PromotionCriteria | None = None,
) -> dict[str, Any]:
    """Fit a staged candidate from baseline averaged weights plus train/replay.

    Replay is explicitly labeled ``train`` and cannot overlap validation. No
    test or regression argument is accepted. The immutable directory contains
    both models, an aggregate training report and a SHA-256-bound manifest.
    """
    if Path(output_dir).exists():
        raise FileExistsError("Staging destination already exists")
    config = config or AdaptationConfig()
    criteria = criteria or PromotionCriteria()
    fitting = [*train, *replay]
    train_partition = _partition(fitting, "train")
    validation_partition = _partition(validation, "validation")
    _disjoint([train_partition, validation_partition])
    initial = load_adaptation_model(baseline)
    baseline_types = sorted({tag[2:] for tag in initial["labels"] if tag != "O"})
    training_types = set(train_partition["spans_by_type"])
    kinds = sorted(set(baseline_types) | training_types)
    if not training_types:
        raise ValueError("Adaptation needs annotated entity spans in training")
    if set(validation_partition["spans_by_type"]) - set(kinds):
        raise ValueError("Validation contains labels absent from baseline and training")
    targets = tuple(sorted(criteria.target_types or kinds))
    if set(targets) - set(kinds) or (set(kinds) - set(baseline_types)) - set(targets):
        raise ValueError("Promotion targets must cover new labels and exist in the candidate")
    criteria = replace(criteria, target_types=targets)
    initial_bytes = _json(initial)
    candidate, training = train_span_tagger(
        fitting,
        validation,
        initial_model=initial,
        **asdict(config),
        metadata={"baseline_sha256": _sha(initial_bytes), "stage": "candidate_not_activated"},
    )
    # Wall-clock time is deliberately omitted from reproducible evidence.
    training.pop("seconds", None)
    candidate_bytes, training_bytes = _json(candidate), _json(training)
    manifest = {
        "format": _FORMAT,
        "state": "STAGED",
        "activated": False,
        "method": "warm-start from averaged perceptron weights; fresh averaging state",
        "replay_documents": len(replay),
        "baseline_types": baseline_types,
        "candidate_types": kinds,
        "configuration": asdict(config),
        "criteria": asdict(criteria),
        "partitions": {"train": train_partition, "validation": validation_partition},
        "artifacts": {
            "baseline.json": _sha(initial_bytes),
            "candidate.json": _sha(candidate_bytes),
            "training.json": _sha(training_bytes),
        },
        "evaluation_protocol": "frozen independent test and context regression; no fitting",
        "fingerprint_normalization": "NFKC, casefold, whitespace collapse; SHA-256",
    }
    manifest_bytes = _json(manifest)
    _new_directory(
        output_dir,
        {
            "baseline.json": initial_bytes,
            "candidate.json": candidate_bytes,
            "training.json": training_bytes,
            "manifest.json": manifest_bytes,
            "manifest.sha256": (_sha(manifest_bytes) + "\n").encode("ascii"),
        },
    )
    return manifest


def _read_stage(path: Path, expected_manifest_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _read_bounded(path / "manifest.json", 32 * 1024**2)
    if _sha(raw) != expected_manifest_sha256:
        raise ValueError("Staged manifest digest mismatch")
    manifest = _parse(raw)
    if manifest.get("format") != _FORMAT or manifest.get("state") != "STAGED":
        raise ValueError("Unsupported staged adaptation manifest")
    models = {}
    for name in ("baseline.json", "candidate.json", "training.json"):
        payload = _read_bounded(path / name)
        if _sha(payload) != manifest["artifacts"][name]:
            raise ValueError("Staged artifact digest mismatch")
        if name != "training.json":
            models[name.removesuffix(".json")] = load_adaptation_model(_parse(payload))
    return manifest, models


def _measure(model: Mapping[str, Any], examples: Sequence[Example]) -> dict[str, Any]:
    tagger = SpanTagger(model, accelerate=False)
    support: Counter[str] = Counter()
    predictions: Counter[str] = Counter()
    matched: Counter[str] = Counter()
    for example in examples:
        gold = {(span.entity_type, span.start, span.end) for span in example.spans}
        predicted = {
            (span.entity_type, span.start, span.end) for span in tagger.predict(example.text)
        }
        support.update(kind for kind, _, _ in gold)
        predictions.update(kind for kind, _, _ in predicted)
        matched.update(kind for kind, _, _ in gold & predicted)
    exact = {}
    for kind in sorted(support.keys() | predictions.keys()):
        exact[kind] = {
            "support": support[kind],
            "predicted": predictions[kind],
            "matched": matched[kind],
            "recall": matched[kind] / support[kind] if support[kind] else None,
            "precision": matched[kind] / predictions[kind] if predictions[kind] else None,
        }
    output = release_gate_metrics(DeidEngine(nlp=tagger), examples, Policy.strict())
    output.pop("p50_seconds", None)
    return {"exact_by_type": exact, "output": output}


def _gate(
    measurements: Mapping[str, Any],
    partitions: Mapping[str, Any],
    criteria: PromotionCriteria,
    baseline_types: Sequence[str],
) -> list[str]:
    reasons = []
    for role in ("test", "regression"):
        partition = partitions[role]
        if partition["documents"] < criteria.minimum_documents:
            reasons.append(f"{role}: insufficient documents")
        if partition["negative_documents"] < criteria.minimum_negative_documents:
            reasons.append(f"{role}: insufficient negative context documents")
        baseline = measurements[role]["baseline"]
        candidate = measurements[role]["candidate"]
        types = criteria.target_types if role == "test" else baseline_types
        for kind in types:
            old = baseline["exact_by_type"].get(kind, {})
            new = candidate["exact_by_type"].get(kind, {})
            if new.get("support", 0) < criteria.minimum_type_support:
                reasons.append(f"{role}/{kind}: insufficient gold support")
            recall, precision = new.get("recall"), new.get("precision")
            if recall is None or recall < criteria.minimum_exact_recall:
                reasons.append(f"{role}/{kind}: exact recall below minimum")
            if recall is None or recall + criteria.maximum_recall_drop < (old.get("recall") or 0):
                reasons.append(f"{role}/{kind}: exact recall regression")
            if precision is None or precision < criteria.minimum_exact_precision:
                reasons.append(f"{role}/{kind}: exact precision below minimum")
            if precision is None or precision + criteria.maximum_precision_drop < (
                old.get("precision") or 0
            ):
                reasons.append(f"{role}/{kind}: exact precision regression")
        before, after = baseline["output"], candidate["output"]
        approved = after["status_counts"].get("APPROVED", 0)
        if approved < criteria.minimum_approved_documents:
            reasons.append(f"{role}: insufficient approved output evidence")
        leak = after["approved_leak_rate"]
        if leak is None or leak > criteria.maximum_approved_leak_rate:
            reasons.append(f"{role}: approved output leakage above maximum or unmeasured")
        if (
            leak is not None
            and before["approved_leak_rate"] is not None
            and leak > before["approved_leak_rate"]
        ):
            reasons.append(f"{role}: approved output leakage regression")
        recall = after["output_sensitive_character_recall"]
        old_recall = before["output_sensitive_character_recall"]
        if recall is None or recall < criteria.minimum_output_character_recall:
            reasons.append(f"{role}: output character recall below minimum or unmeasured")
        if (
            recall is not None
            and old_recall is not None
            and recall + criteria.maximum_recall_drop < old_recall
        ):
            reasons.append(f"{role}: output character recall regression")
        over = after["over_redaction_rate"]
        old_over = before["over_redaction_rate"]
        if over is None or over > criteria.maximum_overredaction_rate:
            reasons.append(f"{role}: context overredaction above maximum or unmeasured")
        if (
            over is not None
            and old_over is not None
            and over > old_over + criteria.maximum_overredaction_increase
        ):
            reasons.append(f"{role}: context overredaction regression")
    return reasons


def evaluate_adaptation(
    staged_dir: str | Path,
    test: Sequence[Example],
    regression: Sequence[Example],
    output_dir: str | Path,
    *,
    expected_manifest_sha256: str,
    evidence_kind: str = "unknown",
    baseline_exposure_verified: bool = False,
) -> dict[str, Any]:
    """Evaluate once; no training, selection, activation or builtin replacement.

    Supply the manifest digest recorded at staging time, not a fresh untrusted
    digest from the same directory. ``baseline_exposure_verified`` attests that
    the evaluator checked the baseline's original training/selection sources
    against both holdouts, which cannot be inferred from weights. Independent
    annotation provenance is an attestation, not something software can prove.
    """
    if evidence_kind not in {"unknown", "fictional_demo", "independently_annotated"}:
        raise ValueError("Unknown evaluation evidence kind")
    if type(baseline_exposure_verified) is not bool:
        raise ValueError("baseline_exposure_verified must be boolean")
    if Path(output_dir).exists():
        raise FileExistsError("Evaluation destination already exists")
    manifest, models = _read_stage(Path(staged_dir), expected_manifest_sha256)
    partitions = {
        "test": _partition(test, "test"),
        "regression": _partition(regression, "regression"),
    }
    _disjoint([*manifest["partitions"].values(), *partitions.values()])
    known = set(manifest["candidate_types"])
    if any(set(partition["spans_by_type"]) - known for partition in partitions.values()):
        raise ValueError("Evaluation contains labels absent from the candidate")
    measurements = {
        role: {name: _measure(model, examples) for name, model in models.items()}
        for role, examples in (("test", test), ("regression", regression))
    }
    criteria = PromotionCriteria(**manifest["criteria"])
    reasons = _gate(measurements, partitions, criteria, manifest["baseline_types"])
    if evidence_kind != "independently_annotated":
        reasons.append(
            "Independent annotated evidence is required; synthetic/unknown data is insufficient"
        )
    if not baseline_exposure_verified:
        reasons.append("Baseline training/selection exposure to holdouts has not been verified")
    report = {
        "format": _FORMAT,
        "stage_manifest_sha256": expected_manifest_sha256,
        "artifacts": manifest["artifacts"],
        "criteria": manifest["criteria"],
        "partitions": partitions,
        "measurements": measurements,
        "evidence_kind": evidence_kind,
        "baseline_exposure_verified": baseline_exposure_verified,
        "inference": {"policy": "strict", "review_margin": None, "redact_margin": None},
        "decision": "ELIGIBLE_FOR_MANUAL_REVIEW" if not reasons else "BLOCKED",
        "reasons": reasons,
        "activated": False,
        "limitations": [
            "Measured performance applies only to the annotated corpus and this inference policy.",
            "Exact/group fingerprints cannot detect undeclared near-duplicates or hidden baseline exposure.",
            "Hashes prove integrity, not origin, annotation quality, consent or anonymization.",
            "After inspecting test results, use a new independent test for further development.",
        ],
    }
    payload = _json(report)
    _new_directory(
        output_dir,
        {"evaluation.json": payload, "evaluation.sha256": (_sha(payload) + "\n").encode("ascii")},
    )
    return report


__all__ = [
    "AdaptationConfig",
    "PromotionCriteria",
    "evaluate_adaptation",
    "load_adaptation_jsonl",
    "load_adaptation_model",
    "stage_span_adaptation",
]
