"""Local pattern/structure/checksum agreement against independent references."""

from __future__ import annotations

import platform
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deidflow import __version__
from deidflow.detectors import CORE_RULES_VERSION
from deidflow.validators import validate_card, validate_clabe, validate_curp, validate_rfc

from ._package_io import is_sha256
from .email import _source_digest, _write_report
from .evaluation_package import load_evaluation_package

_VALIDATORS = {
    "RFC": validate_rfc,
    "CURP": validate_curp,
    "CLABE": validate_clabe,
    "PAYMENT_CARD": validate_card,
}
_ATTRIBUTES = ("pattern", "structure", "checksum")


@dataclass(frozen=True)
class ValidationCandidate:
    candidate_id: str
    source_sha256: str
    validate: Callable[[str, str], Mapping[str, str]]


class UnsupportedValidationError(ValueError):
    status = "UNSUPPORTED"

    def __init__(self) -> None:
        super().__init__("Unsupported validation benchmark configuration")


def _builtin(entity_type: str, value: str) -> dict[str, str]:
    if entity_type in {"PHONE", "EMAIL"}:
        return {"pattern": "unknown", "structure": "unknown", "checksum": "not_applicable"}
    result = _VALIDATORS[entity_type](value)
    return {
        key: "unknown" if state is None else "valid" if state else "invalid"
        for key, state in zip(
            _ATTRIBUTES, (result.pattern, result.structural, result.checksum), strict=True
        )
    }


def _attribute_cell(references: list[str], observed: list[str]) -> dict[str, Any]:
    pairs = list(zip(references, observed, strict=True))
    applicable = [
        (expected, actual) for expected, actual in pairs if expected in {"valid", "invalid"}
    ]
    matched = sum(expected == actual for expected, actual in applicable)
    return {
        "evaluated": len(applicable),
        "matched": matched,
        "mismatched": len(applicable) - matched,
        "not_applicable": references.count("not_applicable"),
        "unknown_reference": references.count("unknown"),
        "unknown_prediction": sum(actual == "unknown" for _expected, actual in applicable),
        "not_applicable_disagreements": sum(
            expected == "not_applicable" and actual != expected for expected, actual in pairs
        ),
        "accuracy": matched / len(applicable) if applicable else None,
        "undefined_reason": None if applicable else "NO_KNOWN_APPLICABLE_REFERENCE",
    }


def run_validation_benchmark(
    package: str | Path,
    *,
    manifest_sha256: str,
    candidate: str | ValidationCandidate,
    profile: str,
    output: str | Path,
) -> dict[str, Any]:
    started, before = datetime.now(UTC).isoformat(), time.perf_counter()
    if profile != "validation-descriptive-v1":
        raise UnsupportedValidationError
    loaded = load_evaluation_package(package, manifest_sha256=manifest_sha256)
    if profile not in loaded.manifest["profiles"] or "validation_vectors" not in loaded.records:
        raise UnsupportedValidationError
    documents = {row["case_id"]: row for row in loaded.records["documents"]}
    units = {row["unit_id"]: row for row in loaded.records["units"]}
    vectors = sorted(
        (
            row
            for row in loaded.records["validation_vectors"]
            if documents[units[row["unit_id"]]["case_id"]]["panel"] == "known_regression"
        ),
        key=lambda row: row["vector_id"],
    )
    if not vectors or any(
        row["entity_type"] not in {*_VALIDATORS, "PHONE", "EMAIL"} for row in vectors
    ):
        raise UnsupportedValidationError
    source = _source_digest()
    validate: Callable[[str, str], Mapping[str, str]]
    descriptor: dict[str, Any]
    if isinstance(candidate, str) and candidate == "rules.mx":
        validate = _builtin
        descriptor = {
            "id": "rules.mx",
            "source_sha256": source,
            "rules_version": CORE_RULES_VERSION,
            "deidflow_version": __version__,
            "identity_provenance": "builtin",
        }
    elif (
        isinstance(candidate, ValidationCandidate)
        and isinstance(candidate.candidate_id, str)
        and re.fullmatch(r"candidate-[0-9a-f]{1,32}", candidate.candidate_id)
        and is_sha256(candidate.source_sha256)
        and callable(candidate.validate)
    ):
        validate = candidate.validate
        descriptor = {
            "id": candidate.candidate_id,
            "source_sha256": candidate.source_sha256,
            "rules_version": None,
            "deidflow_version": None,
            "identity_provenance": "caller_declared",
        }
    else:
        raise UnsupportedValidationError
    observed = []
    failures = 0
    for row in vectors:
        try:
            raw = validate(
                row["entity_type"], units[row["unit_id"]]["text"][row["start"] : row["end"]]
            )
            if (
                not isinstance(raw, Mapping)
                or set(raw) != set(_ATTRIBUTES)
                or any(
                    value not in {"valid", "invalid", "unknown", "not_applicable"}
                    for value in raw.values()
                )
            ):
                raise ValueError
            observed.append(dict(raw))
        except Exception:
            failures += 1
    entity_types = sorted(
        set(loaded.manifest["scope"]["entity_types"]) & {*_VALIDATORS, "PHONE", "EMAIL"}
    )
    metrics = {}
    for entity in entity_types:
        if failures:
            metrics[entity] = dict.fromkeys(_ATTRIBUTES)
            continue
        selected = [
            (row, actual)
            for row, actual in zip(vectors, observed, strict=True)
            if row["entity_type"] == entity
        ]
        metrics[entity] = {
            attribute: _attribute_cell(
                [row["validity"][attribute] for row, _actual in selected],
                [actual[attribute] for _row, actual in selected],
            )
            for attribute in _ATTRIBUTES
        }
    report: dict[str, Any] = {
        "schema_version": "df-eval-mx.validation-report.v1",
        "result": {
            "candidate": descriptor,
            "evaluator": {"source_sha256": source, "version": "df-eval-mx.validation-report.v1"},
            "dataset": {
                "id": "sha256:" + manifest_sha256,
                "version": loaded.manifest["dataset_version"],
                "panel": "known_regression",
            },
            "profile": {"id": profile, "ratified": False},
            "scope": {
                "track": "validation",
                "entity_types": entity_types,
                "attributes": list(_ATTRIBUTES),
            },
            "execution": {
                "required_vectors": len(vectors),
                "completed_vectors": len(vectors) - failures,
                "failed_vectors": failures,
            },
            "attempt_status": "candidate_error" if failures else "completed",
            "diagnostics": [{"code": "CANDIDATE_ERROR", "count": failures}] if failures else [],
            "metrics": metrics,
            "reference_sensitivity": {
                key: sum(row["sensitivity"] == key for row in vectors)
                for key in ("sensitive", "nonpersonal_distractor")
            },
            "reference_evidence_sha256": sorted(
                {
                    loaded.manifest["resources"][row["provenance"]["evidence_ref"]]["sha256"]
                    for row in vectors
                }
            ),
            "quality": "DESCRIPTIVE_ONLY",
            "limitations": [
                "KNOWN_REGRESSION_ONLY",
                "NO_ISSUANCE_OR_OWNERSHIP_CHECK",
                "DETECTION_AND_TRANSFORMATION_NOT_EVALUATED",
                "REFERENCE_DECLARATIONS_NOT_AUTHENTICATED",
            ],
        },
        "operational": {
            "started_at": started,
            "elapsed_seconds": time.perf_counter() - before,
            "python_version": platform.python_version(),
        },
    }
    _write_report(Path(output), report)
    return report
