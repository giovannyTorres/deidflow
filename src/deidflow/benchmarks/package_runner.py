"""BMX-02 package admission through the descriptive EMAIL evaluation seam."""

from __future__ import annotations

import math
import platform
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deidflow import DeidEngine, __version__
from deidflow.core import Finding
from deidflow.detectors import CORE_RULES_VERSION

from ._package_io import MAX_RECORDS, is_sha256
from .datasets import Example, GoldSpan
from .email import _source_digest, _write_report
from .evaluation_package import load_evaluation_package
from .metrics import evaluate


@dataclass(frozen=True)
class DetectionCandidate:
    """A trusted local callback and caller-declared identity, not a plugin loader."""

    candidate_id: str
    source_sha256: str
    detect: Callable[[str], Sequence[Finding]]


class UnsupportedEvaluationError(ValueError):
    """A valid package may require a track/profile this increment cannot score."""

    status = "UNSUPPORTED"

    def __init__(self) -> None:
        super().__init__("Unsupported EMAIL evaluation configuration")


def _candidate_adapter(
    candidate: str | DetectionCandidate, source: str
) -> tuple[Callable[[str], Sequence[Finding]], dict[str, Any]]:
    if isinstance(candidate, str) and candidate == "rules.mx":
        engine = DeidEngine(language="es", country="MX", offline=True, performance="balanced")
        return engine.scan_text, {
            "id": candidate,
            "deidflow_version": __version__,
            "rules_version": CORE_RULES_VERSION,
            "source_sha256": source,
            "nlp": None,
            "offline": True,
            "performance": "balanced",
            "identity_provenance": "builtin",
        }
    if (
        not isinstance(candidate, DetectionCandidate)
        or not isinstance(candidate.candidate_id, str)
        or re.fullmatch(r"candidate-[0-9a-f]{1,32}", candidate.candidate_id) is None
        or not is_sha256(candidate.source_sha256)
        or not callable(candidate.detect)
    ):
        raise UnsupportedEvaluationError
    return candidate.detect, {
        "id": candidate.candidate_id,
        "source_sha256": candidate.source_sha256,
        "deidflow_version": None,
        "rules_version": None,
        "nlp": "unspecified",
        "offline": None,
        "performance": None,
        "identity_provenance": "caller_declared",
    }


def _probability(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1


def _findings(response: Any, text: str) -> list[Finding]:
    if not isinstance(response, (list, tuple)) or len(response) > MAX_RECORDS:
        raise ValueError
    result = []
    for finding in response:
        label, start, end, score = finding.entity_type, finding.start, finding.end, finding.score
        confidence = getattr(finding, "confidence", None)
        if (
            not isinstance(label, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", label) is None
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or not _probability(score)
            or (confidence is not None and not _probability(confidence))
        ):
            raise ValueError
        # Copy validated primitives; a mutable or custom response has no authority.
        result.append(
            Finding(
                str(label),
                start,
                end,
                float(score),
                "benchmark-candidate",
                confidence=float(confidence) if confidence is not None else None,
            )
        )
    return result


def run_package_benchmark(
    package: str | Path,
    *,
    manifest_sha256: str,
    candidate: str | DetectionCandidate,
    profile: str,
    output: str | Path,
) -> dict[str, Any]:
    """Admit a full package and evaluate EMAIL with an explicit local profile."""
    started = datetime.now(UTC).isoformat()
    before = time.perf_counter()
    if profile != "email-descriptive-v1":
        raise UnsupportedEvaluationError
    loaded = load_evaluation_package(package, manifest_sha256=manifest_sha256)
    records = loaded.records
    selected_cases = {
        row["case_id"] for row in records["documents"] if row["panel"] == "known_regression"
    }
    selected_units = {
        unit["unit_id"] for unit in records["units"] if unit["case_id"] in selected_cases
    }
    if (
        not selected_cases
        or profile not in loaded.manifest["profiles"]
        or set(loaded.manifest["scope"]["entity_types"]) != {"EMAIL"}
        or set(loaded.manifest["scope"]["formats"]) != {"text"}
        or any(
            row["format"] != "text" or set(row["capabilities_required"]) - {"text_detection"}
            for row in records["documents"]
            if row["case_id"] in selected_cases
        )
        or any(
            mention["certainty"] != "confirmed"
            for mention in records["mentions"]
            if mention["unit_id"] in selected_units
        )
        or any(
            "EMAIL" not in entry["exhaustive_entity_types"]
            for entry in loaded.manifest["annotation_coverage"]
            if entry["unit_id"] in selected_units
        )
    ):
        raise UnsupportedEvaluationError
    examples = [
        Example(
            unit["unit_id"],
            unit["text"],
            tuple(
                GoldSpan(mention["entity_type"], mention["start"], mention["end"])
                for mention in records["mentions"]
                if mention["unit_id"] == unit["unit_id"]
            ),
            "known_regression",
            "package-fixture",
        )
        for unit in sorted(records["units"], key=lambda item: item["unit_id"])
        if unit["unit_id"] in selected_units
    ]
    source_sha256 = _source_digest()
    detect, descriptor = _candidate_adapter(candidate, source_sha256)
    unit_cases = {unit["unit_id"]: unit["case_id"] for unit in records["units"]}
    predictions = []
    failed_cases: set[str] = set()
    failed_units = 0
    for example in examples:
        try:
            findings = _findings(detect(example.text), example.text)
            predictions.append([finding for finding in findings if finding.entity_type == "EMAIL"])
        except Exception:
            failed_units += 1
            failed_cases.add(unit_cases[example.id])
    metrics = None
    if not failed_units:
        measured = evaluate(examples, predictions)
        tp, fp, fn = measured.true_positives, measured.false_positives, measured.false_negatives
        metrics = {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "support": tp + fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        }
    report = {
        "schema_version": "df-eval-mx.package-report.v1",
        "result": {
            "candidate": descriptor,
            "evaluator": {
                "version": "df-eval-mx.package-report.v1",
                "source_sha256": source_sha256,
            },
            "dataset": {
                "id": "sha256:" + manifest_sha256,
                "version": loaded.manifest["dataset_version"],
                "panel": "known_regression",
            },
            "profile": {"id": profile, "ratified": False},
            "scope": {
                "track": "detection",
                "entity_types": ["EMAIL"],
                "source_format": "text",
                "language": "es",
                "country": "MX",
                "matching": "exact",
            },
            "admission": {
                "status": "valid",
                **{
                    name: len(records[name])
                    for name in ("sources", "documents", "units", "mentions", "expectations")
                },
            },
            "attempt_status": "candidate_error" if failed_units else "completed",
            "execution": {
                "required_documents": len(selected_cases),
                "completed_documents": len(selected_cases) - len(failed_cases),
                "failed_documents": len(failed_cases),
                "required_units": len(examples),
                "completed_units": len(examples) - failed_units,
                "failed_units": failed_units,
                "required_mentions": sum(len(example.spans) for example in examples),
            },
            "diagnostics": [{"code": "CANDIDATE_ERROR", "count": failed_units}]
            if failed_units
            else [],
            "quality": "DESCRIPTIVE_ONLY",
            "metrics": {"EMAIL": metrics},
            "limitations": [
                "EMAIL_ONLY_KNOWN_REGRESSION",
                "ANNOTATION_REVIEW_NOT_AUTHENTICATED",
                "SOURCE_DECLARATIONS_NOT_AUTHENTICATED",
                "TRANSFORMATION_NOT_EVALUATED",
                "DATASET_INDEPENDENCE_NOT_EVALUATED",
                "PROCESS_NETWORK_ISOLATION_NOT_EVALUATED",
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
