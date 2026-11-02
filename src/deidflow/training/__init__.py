"""Private, local discriminative column-model training and release safeguards.

Dependencies are lazy.  Model files use joblib and must come from a trusted
source: SHA-256 integrity checking is not publisher authentication.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ColumnSample:
    header: str = field(repr=False)
    values: tuple[str, ...] = field(repr=False)
    label: str
    split: str = "train"
    template_id: str = ""
    entity_group: str = ""


@dataclass(frozen=True)
class ColumnPrediction:
    label: str
    score: float
    probabilities: dict[str, float]
    calibrated: bool = False


def _features(sample: ColumnSample) -> str:
    # Bounded features avoid accidentally materializing an entire table.  The
    # caller controls sample choice; every record still needs downstream scans.
    header = sample.header[:256]
    values = sample.values[:64]
    return "header " + header + "\n" + "\n".join(value[:256] for value in values)


def _require_training() -> tuple[Any, Any, Any]:
    try:
        import joblib
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
    except ImportError:
        raise RuntimeError("Local training requires the training extra") from None
    return joblib, Pipeline, (TfidfVectorizer, LogisticRegression)


def _validate_partitions(samples: Sequence[ColumnSample]) -> None:
    templates: dict[str, str] = {}
    entities: dict[str, str] = {}
    for sample in samples:
        if sample.split not in {"train", "validation", "test"}:
            raise ValueError("Unknown dataset split")
        if not sample.label or not sample.values:
            raise ValueError("Column samples require a label and values")
        for identifier, seen in ((sample.template_id, templates), (sample.entity_group, entities)):
            if identifier and identifier in seen and seen[identifier] != sample.split:
                raise ValueError("Cross-split template or entity leakage detected")
            if identifier:
                seen[identifier] = sample.split


def train_column_model(
    samples: Sequence[ColumnSample],
    output: str | Path,
    *,
    version: str,
    seed: int = 1729,
    max_features: int = 30000,
) -> dict[str, Any]:
    """Fit a CPU character-ngram/logistic model; never activates it.

    Validation is used for reported metrics only, not model selection.  Test
    samples are excluded from both fitting and the validation report.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", version):
        raise ValueError("Version must be a safe short identifier")
    if max_features < 100:
        raise ValueError("max_features must be at least one hundred")
    _validate_partitions(samples)
    train = [sample for sample in samples if sample.split == "train"]
    validation = [sample for sample in samples if sample.split == "validation"]
    if len({sample.label for sample in train}) < 2:
        raise ValueError("Training needs at least two labels")
    if not validation:
        raise ValueError("A held-out validation split is required")
    if set(sample.label for sample in validation) - set(sample.label for sample in train):
        raise ValueError("Validation contains a label absent from training")
    joblib, Pipeline, (TfidfVectorizer, LogisticRegression) = _require_training()
    model = Pipeline(
        [
            (
                "features",
                TfidfVectorizer(
                    analyzer="char",
                    ngram_range=(2, 5),
                    max_features=max_features,
                    sublinear_tf=True,
                ),
            ),
            (
                "classifier",
                LogisticRegression(max_iter=400, class_weight="balanced", random_state=seed),
            ),
        ]
    )
    model.fit([_features(sample) for sample in train], [sample.label for sample in train])
    validation_predictions = model.predict([_features(sample) for sample in validation])
    metrics = classification_metrics(
        [sample.label for sample in validation], list(validation_predictions)
    )
    target = Path(output)
    target.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, target / "model.joblib", compress=3)
    manifest = {
        "schema_version": 1,
        "kind": "column-char-logistic",
        "version": version,
        "sha256": hashlib.sha256((target / "model.joblib").read_bytes()).hexdigest(),
        "labels": sorted({sample.label for sample in train}),
        "seed": seed,
        "training_samples": len(train),
        "validation_samples": len(validation),
        "validation": metrics,
        "calibrated": False,
        "activation": "STAGED",
        "software": {name: importlib.metadata.version(name) for name in ("scikit-learn", "joblib")},
        "limitations": [
            "Character n-gram model is a column prior, not a definitive PII classifier",
            "Model may retain customer-specific feature strings; keep private",
            "Validation is synthetic unless caller supplies a representative private holdout",
        ],
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def classification_metrics(gold: Sequence[str], predictions: Sequence[str]) -> dict[str, Any]:
    if len(gold) != len(predictions) or not gold:
        raise ValueError("Evaluation needs equally sized nonempty labels")
    labels = sorted(set(gold) | set(predictions))
    recall = {}
    precision = {}
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, predictions, strict=True))
        positives = sum(g == label for g in gold)
        predicted = sum(p == label for p in predictions)
        recall[label] = tp / positives if positives else None
        precision[label] = tp / predicted if predicted else None
    return {
        "accuracy": sum(g == p for g, p in zip(gold, predictions, strict=True)) / len(gold),
        "recall_by_type": recall,
        "precision_by_type": precision,
        "samples": len(gold),
    }


class LocalColumnModel:
    """Explicitly loaded trusted local model; no remote or fallback path."""

    def __init__(self, path: str | Path):
        target = Path(path)
        try:
            self.manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            payload = (target / "model.joblib").read_bytes()
        except (OSError, ValueError):
            raise ValueError("Local model assets are missing or malformed") from None
        if not isinstance(self.manifest, dict) or (
            self.manifest.get("schema_version") != 1
            or self.manifest.get("kind") != "column-char-logistic"
        ):
            raise ValueError("Unsupported local model manifest")
        if hashlib.sha256(payload).hexdigest() != self.manifest.get("sha256"):
            raise ValueError("Local model integrity check failed")
        joblib, _, _ = _require_training()
        # Deserialization remains intentionally explicit and trusted-local only.
        self._model = joblib.load(io.BytesIO(payload))

    def predict(self, header: str, values: Iterable[str]) -> ColumnPrediction:
        from itertools import islice

        sample = ColumnSample(header, tuple(islice(values, 64)), "UNKNOWN")
        probabilities = self._model.predict_proba([_features(sample)])[0]
        labels = self._model.classes_
        best = int(probabilities.argmax())
        return ColumnPrediction(
            str(labels[best]),
            float(probabilities[best]),
            {str(label): float(score) for label, score in zip(labels, probabilities, strict=True)},
        )

    def evaluate(self, samples: Sequence[ColumnSample]) -> dict[str, Any]:
        return classification_metrics(
            [s.label for s in samples], [self.predict(s.header, s.values).label for s in samples]
        )


def promotion_gate(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    critical_categories: Sequence[str],
    max_recall_drop: float = 0.0,
    minimum_recall: float = 0.95,
) -> dict[str, Any]:
    """Pure decision: missing categories block; no automatic activation occurs."""
    if not 0 <= max_recall_drop <= 1 or not 0 <= minimum_recall <= 1 or not critical_categories:
        raise ValueError("Invalid promotion criteria")
    candidate_recall = candidate.get("recall_by_type", {})
    baseline_recall = baseline.get("recall_by_type", {})
    reasons = []
    for category in critical_categories:
        new, old = candidate_recall.get(category), baseline_recall.get(category)
        if new is None or old is None:
            reasons.append(f"missing_holdout_category:{category}")
        elif (
            type(new) not in (int, float)
            or type(old) not in (int, float)
            or not math.isfinite(new)
            or not math.isfinite(old)
            or not 0 <= new <= 1
            or not 0 <= old <= 1
        ):
            reasons.append(f"invalid_holdout_metric:{category}")
        elif new < minimum_recall:
            reasons.append(f"below_minimum_recall:{category}")
        elif new + max_recall_drop + 1e-12 < old:
            reasons.append(f"critical_recall_regression:{category}")
    return {
        "eligible": not reasons,
        "status": "ELIGIBLE_FOR_MANUAL_ACTIVATION" if not reasons else "BLOCKED",
        "reasons": reasons,
    }


def select_active_learning(predictions: Sequence[ColumnPrediction], *, count: int) -> list[int]:
    """Return largest predictive entropy first; scores are not calibrated risk."""
    if count < 0:
        raise ValueError("count must be nonnegative")
    entropy = []
    for index, prediction in enumerate(predictions):
        values = list(prediction.probabilities.values())
        if (
            not values
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values)
            or abs(sum(values) - 1) > 1e-6
        ):
            raise ValueError("Invalid class probabilities")
        entropy.append((-sum(v * math.log(v) for v in values if v), index))
    return [index for _, index in sorted(entropy, key=lambda x: (-x[0], x[1]))[:count]]


def import_span_annotations(
    path: str | Path, *, labels: set[str] | None = None, max_line_bytes: int = 1_000_000
) -> list[dict[str, Any]]:
    """Import UTF-8 JSONL {text, spans:[{start,end,label}]} without token guessing."""
    result = []
    with Path(path).open("rb") as stream:
        while line := stream.readline(max_line_bytes + 1):
            if len(line) > max_line_bytes:
                raise ValueError("Annotation record exceeds configured limit")
            try:
                record = json.loads(line)
                if (
                    set(record) != {"text", "spans"}
                    or not isinstance(record["text"], str)
                    or not isinstance(record["spans"], list)
                ):
                    raise ValueError
                for span in record["spans"]:
                    if (
                        set(span) != {"start", "end", "label"}
                        or not isinstance(span["label"], str)
                        or not span["label"]
                    ):
                        raise ValueError
                    if (
                        type(span["start"]) is not int
                        or type(span["end"]) is not int
                        or not 0 <= span["start"] < span["end"] <= len(record["text"])
                    ):
                        raise ValueError
                    if labels is not None and span["label"] not in labels:
                        raise ValueError
            except (ValueError, TypeError, KeyError, UnicodeDecodeError):
                raise ValueError("Malformed span annotation record") from None
            result.append(record)
    return result


def weak_annotations(texts: Iterable[str], detector: Any) -> Iterable[dict[str, Any]]:
    """Yield local silver annotations; provenance marks them as unreviewed."""
    for text in texts:
        yield {
            "text": text,
            "spans": [
                {"start": f.start, "end": f.end, "label": str(f.entity_type)}
                for f in detector.detect(text)
            ],
            "provenance": "weak-supervision-unreviewed",
        }


@dataclass(frozen=True)
class ScoreCalibrator:
    """A logistic mapping valid only for the fitted detector/model provenance.

    Calibration annotates candidates; it never changes thresholds or removes a
    high-risk rule.  Distribution shift can invalidate the mapping.
    """

    detector: str
    model_version: str
    coefficient: float
    intercept: float
    samples: int

    def apply(self, finding: Any) -> Any:
        from dataclasses import replace

        if finding.detector != self.detector or finding.model_version != self.model_version:
            raise ValueError("Calibration provenance does not match candidate")
        logit = self.coefficient * finding.score + self.intercept
        confidence = (
            1 / (1 + math.exp(-logit)) if logit >= 0 else math.exp(logit) / (1 + math.exp(logit))
        )
        return replace(finding, confidence=confidence)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> ScoreCalibrator:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            model = cls(**data)
            if (
                not model.detector
                or not model.model_version
                or model.samples < 10
                or not math.isfinite(model.coefficient)
                or not math.isfinite(model.intercept)
            ):
                raise ValueError
        except (OSError, ValueError, TypeError):
            raise ValueError("Invalid local calibration asset") from None
        return model


def fit_score_calibrator(findings: Sequence[Any], correctness: Sequence[bool]) -> ScoreCalibrator:
    """Fit on validation-only candidate labels; assess ECE on a separate holdout."""
    if len(findings) != len(correctness) or len(findings) < 10 or len(set(correctness)) != 2:
        raise ValueError("Calibration needs ten or more validation candidates and both outcomes")
    provenance = {(finding.detector, finding.model_version) for finding in findings}
    if len(provenance) != 1:
        raise ValueError("Cannot pool incompatible detector/model scores")
    _, _, (_, LogisticRegression) = _require_training()
    model = LogisticRegression(random_state=1729)
    model.fit([[finding.score] for finding in findings], [int(correct) for correct in correctness])
    detector, version = next(iter(provenance))
    return ScoreCalibrator(
        detector, version, float(model.coef_[0][0]), float(model.intercept_[0]), len(findings)
    )


__all__ = [
    "ColumnSample",
    "ColumnPrediction",
    "LocalColumnModel",
    "train_column_model",
    "classification_metrics",
    "promotion_gate",
    "select_active_learning",
    "import_span_annotations",
    "weak_annotations",
    "ScoreCalibrator",
    "fit_score_calibrator",
]
