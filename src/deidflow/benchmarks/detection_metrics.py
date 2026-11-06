"""Exact, per-entity counts without conflating unsupported denominators."""

from __future__ import annotations

from typing import Any

from deidflow.core import Finding

from .datasets import Example
from .span_coverage import coverage_counts


def metric_cell(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "support": tp + fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "undefined_reason": {
            "precision": None if tp + fp else "NO_PREDICTIONS",
            "recall": None if tp + fn else "NO_GOLD",
            "f1": None if 2 * tp + fp + fn else "NO_GOLD_OR_PREDICTIONS",
        },
    }


def score_detection(
    examples: list[Example],
    predictions: list[list[Finding]] | None,
    entity_types: list[str],
    coverage: dict[str, set[str]],
    ambiguous: set[tuple[str, str, int, int]],
) -> dict[str, Any]:
    cells = {}
    partial = {}
    ambiguous_pairs = {(unit, label) for unit, label, _start, _end in ambiguous}
    exclusions: dict[str, Any] = {
        "ambiguous_mentions": len(ambiguous),
        "ambiguous_unit_entity_pairs": len(ambiguous_pairs),
        "nonexhaustive_unit_entity_pairs": sum(
            label not in coverage[example.id] for example in examples for label in entity_types
        ),
        "out_of_scope_predictions": sum(
            len(
                {
                    (f.entity_type, f.start, f.end)
                    for f in items
                    if f.entity_type not in entity_types
                }
            )
            for items in predictions
        )
        if predictions is not None
        else None,
    }
    reference_fields = {
        "exclusions": exclusions,
        "reference_conformity": "INCOMPLETE"
        if ambiguous or exclusions["nonexhaustive_unit_entity_pairs"]
        else "COMPLETE_FOR_DECLARED_SCOPE",
        "ambiguity_policy": "exclude_unit_entity_if_ambiguous.v1",
    }
    if predictions is None:
        return {
            **reference_fields,
            "metrics": {label: None for label in entity_types},
            "aggregates": None,
            "partial_diagnostics": None,
            "metric_unavailable_reason": "CANDIDATE_ERROR",
            "coverage_diagnostics": None,
        }
    diagnostic = {}
    for label in sorted(entity_types):
        tp = fp = fn = 0
        partial_tp = partial_fn = partial_predictions = 0
        covered: dict[str, int] = {}
        for example, findings in zip(examples, predictions, strict=True):
            gold = {
                (span.start, span.end)
                for span in example.spans
                if span.entity_type == label
                and (example.id, label, span.start, span.end) not in ambiguous
            }
            predicted = {(span.start, span.end) for span in findings if span.entity_type == label}
            for key, value in coverage_counts(gold, predicted).items():
                covered[key] = covered.get(key, 0) + value
            if label not in coverage[example.id] or (example.id, label) in ambiguous_pairs:
                partial_tp += len(gold & predicted)
                partial_fn += len(gold - predicted)
                partial_predictions += len(predicted)
                continue
            tp += len(gold & predicted)
            fp += len(predicted - gold)
            fn += len(gold - predicted)
        cells[label] = metric_cell(tp, fp, fn)
        diagnostic[label] = covered
        partial[label] = {
            "known_true_positives": partial_tp,
            "known_false_negatives": partial_fn,
            "known_support": partial_tp + partial_fn,
            "unscored_predictions": partial_predictions,
            "false_positives": None,
            "undefined_reason": "REFERENCE_NOT_EXHAUSTIVE_OR_AMBIGUOUS",
        }
    micro = metric_cell(
        *(
            sum(cell[key] for cell in cells.values())
            for key in ("true_positives", "false_positives", "false_negatives")
        )
    )
    macro: dict[str, Any] = {"defined_entities": {}, "undefined_reason": {}}
    for key in ("precision", "recall", "f1"):
        values = [cell[key] for cell in cells.values() if cell[key] is not None]
        macro[key] = sum(values) / len(values) if values else None
        macro["defined_entities"][key] = len(values)
        macro["undefined_reason"][key] = None if values else "NO_DEFINED_ENTITIES"
    return {
        "metrics": cells,
        "aggregates": {"micro": micro, "macro": macro},
        **reference_fields,
        "partial_diagnostics": partial,
        "coverage_diagnostics": diagnostic,
    }
