"""Explicit matching rules for detection evaluation; no score conflation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from .datasets import Example, GoldSpan


@dataclass(frozen=True)
class DetectionMetrics:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    document_leakage_rate: float
    false_redaction_rate: float
    entity_level_recall: float
    recall_by_type: dict[str, float]
    recall_by_format: dict[str, float]
    expected_calibration_error: float | None
    calibration_count: int
    matching: str
    documents: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _key(span: Any) -> tuple[str, int, int]:
    label = span.entity_type
    if hasattr(label, "value"):
        label = label.value
    return str(label), int(span.start), int(span.end)


def _matches(prediction: Any, gold: GoldSpan, *, exact: bool) -> bool:
    p_type, p_start, p_end = _key(prediction)
    if p_type != gold.entity_type:
        return False
    if exact:
        return (p_start, p_end) == (gold.start, gold.end)
    return p_start < gold.end and p_end > gold.start


def _assignment(
    findings: Sequence[Any], gold: Sequence[GoldSpan], *, exact: bool
) -> dict[int, int]:
    """Deterministic maximum one-to-one matching, including overlapping entities."""
    edges = [
        [i for i, span in enumerate(gold) if _matches(finding, span, exact=exact)]
        for finding in findings
    ]
    gold_to_prediction: dict[int, int] = {}

    def augment(prediction: int, seen: set[int]) -> bool:
        for target in edges[prediction]:
            if target in seen:
                continue
            seen.add(target)
            previous = gold_to_prediction.get(target)
            if previous is None or augment(previous, seen):
                gold_to_prediction[target] = prediction
                return True
        return False

    for prediction in range(len(findings)):
        augment(prediction, set())
    return {prediction: target for target, prediction in gold_to_prediction.items()}


def evaluate(
    examples: Sequence[Example],
    predictions: Iterable[Sequence[Any]],
    *,
    exact: bool = True,
    calibration_bins: int = 10,
) -> DetectionMetrics:
    if calibration_bins < 1:
        raise ValueError("calibration_bins must be positive")
    predicted = list(predictions)
    if len(predicted) != len(examples):
        raise ValueError("prediction count must equal example count")
    tp = fp = fn = leaked = annotated_docs = non_sensitive_chars = falsely_covered_chars = 0
    by_type_total: Counter[str] = Counter()
    by_type_hit: Counter[str] = Counter()
    by_format_total: Counter[str] = Counter()
    by_format_hit: Counter[str] = Counter()
    calibration: list[tuple[float, int]] = []
    overlap_hits = total_gold = 0
    for example, findings in zip(examples, predicted, strict=True):
        # Identical candidates from several detectors count once.  Distinct
        # overlapping spans are retained and evaluated as actual predictions.
        unique = {_key(f): f for f in findings}
        findings = [unique[key] for key in sorted(unique)]
        assignment = _assignment(findings, example.spans, exact=exact)
        overlap_assignment = _assignment(findings, example.spans, exact=False)
        matched = set(assignment.values())
        for prediction_index, finding in enumerate(findings):
            hit = prediction_index in assignment
            if hit:
                index = assignment[prediction_index]
                by_type_hit[example.spans[index].entity_type] += 1
                by_format_hit[example.source_format] += 1
                tp += 1
            else:
                fp += 1
            confidence = getattr(finding, "confidence", None)
            if confidence is not None:
                if not 0 <= confidence <= 1:
                    raise ValueError("calibrated confidence must be in [0, 1]")
                calibration.append((float(confidence), int(hit)))
        overlap_hits += len(overlap_assignment)
        total_gold += len(example.spans)
        fn += len(example.spans) - len(matched)
        if example.spans:
            annotated_docs += 1
            leaked += int(len(matched) < len(example.spans))
        for gold in example.spans:
            by_type_total[gold.entity_type] += 1
            by_format_total[example.source_format] += 1
        # Union per character prevents overlaps inflating the denominator.
        sensitive = bytearray(len(example.text))
        covered = bytearray(len(example.text))
        for gold in example.spans:
            sensitive[gold.start : gold.end] = b"\x01" * (gold.end - gold.start)
        for finding in findings:
            _, start, end = _key(finding)
            if start < 0 or end <= start or end > len(example.text):
                raise ValueError("prediction span outside source text")
            covered[start:end] = b"\x01" * (end - start)
        non_sensitive_chars += sum(c == 0 for c in sensitive)
        falsely_covered_chars += sum(
            bool(p) and not g for p, g in zip(covered, sensitive, strict=True)
        )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    ece = None
    if calibration:
        ece = 0.0
        for index in range(calibration_bins):
            bucket = [
                (c, h)
                for c, h in calibration
                if min(int(c * calibration_bins), calibration_bins - 1) == index
            ]
            if bucket:
                confidence = sum(c for c, _ in bucket) / len(bucket)
                accuracy = sum(h for _, h in bucket) / len(bucket)
                ece += len(bucket) / len(calibration) * abs(confidence - accuracy)
    return DetectionMetrics(
        precision,
        recall,
        2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        tp,
        fp,
        fn,
        leaked / annotated_docs if annotated_docs else 0.0,
        falsely_covered_chars / non_sensitive_chars if non_sensitive_chars else 0.0,
        overlap_hits / total_gold if total_gold else 0.0,
        {key: by_type_hit[key] / count for key, count in sorted(by_type_total.items())},
        {key: by_format_hit[key] / count for key, count in sorted(by_format_total.items())},
        ece,
        len(calibration),
        "exact" if exact else "overlap",
        len(examples),
    )
