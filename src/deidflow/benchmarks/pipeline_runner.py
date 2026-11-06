"""Run the existing textual engine, inspecting outputs independently of it."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deidflow import DeidEngine
from deidflow.core import Finding
from deidflow.engine import ReleaseStatus, Result
from deidflow.policies import Policy

from ._package_io import is_sha256
from .datasets import Example, GoldSpan
from .detection_metrics import score_detection
from .email import _source_digest, _write_report
from .evaluation_package import load_evaluation_package
from .package_runner import _findings
from .transformation_metrics import TransformationOutput, inspect_text_output, resolve_requirements
from .transformation_runner import transformation_policy


@dataclass(frozen=True)
class PipelineCandidate:
    candidate_id: str
    source_sha256: str
    run: Callable[[str, Policy], Result]
    detect: Callable[[str], Sequence[Finding]] | None = None


class UnsupportedPipelineError(ValueError):
    status = "UNSUPPORTED"

    def __init__(self) -> None:
        super().__init__("Unsupported pipeline benchmark configuration")


def _risk(documents: list[dict[str, Any]]) -> dict[str, Any]:
    emitted = [row for row in documents if row["emitted"]]
    count = len(emitted)
    leaked = sum(row["leaked"] for row in emitted)
    uncertain = sum(not row["complete"] and not row["leaked"] for row in emitted)
    return {
        "emitted": count,
        "leaked": leaked,
        "unverified_without_confirmed_leak": uncertain,
        "completely_inspected": sum(row["complete"] for row in emitted),
        "risk_lower": leaked / count if count else None,
        "risk_upper": (leaked + uncertain) / count if count else None,
        "undefined_reason": None if count else "NO_EMITTED_DOCUMENTS",
    }


def _document_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    priority = ["ERROR", "UNSUPPORTED", "BLOCKED", "REVIEW_REQUIRED", "APPROVED"]
    return {
        "state": min((row["state"] for row in events), key=priority.index),
        "emitted": any(row["output_observable"] for row in events),
        "complete": all(
            row["output_observable"] and row["verification_complete"] for row in events
        ),
        "leaked": any(row["leaked_mentions"] for row in events),
        "joint": all(row["joint_success"] for row in events),
        "failed": any(row["error"] for row in events),
    }


def run_pipeline_benchmark(
    package: str | Path,
    *,
    manifest_sha256: str,
    candidate: str | PipelineCandidate,
    profile: str,
    output: str | Path,
) -> dict[str, Any]:
    loaded = load_evaluation_package(package, manifest_sha256=manifest_sha256)
    if (
        profile != "pipeline-descriptive-v1"
        or profile not in loaded.manifest["profiles"]
        or loaded.manifest["scope"]["formats"] != ["text"]
    ):
        raise UnsupportedPipelineError
    source = _source_digest()
    run: Callable[[str, Policy], Result]
    detect: Callable[[str], Sequence[Finding]] | None = None
    if candidate == "rules.mx":
        engine = DeidEngine(language="es", country="MX", offline=True, performance="balanced")

        def run(text: str, policy: Policy) -> Result:
            return engine.deidentify_text(text, policy=policy)

        identity, candidate_sha, provenance = "rules.mx", source, "builtin"
        detect = engine.scan_text
    elif (
        isinstance(candidate, PipelineCandidate)
        and isinstance(candidate.candidate_id, str)
        and re.fullmatch(r"candidate-[0-9a-f]{1,32}", candidate.candidate_id)
        and is_sha256(candidate.source_sha256)
        and callable(candidate.run)
    ):
        run, identity, candidate_sha, provenance = (
            candidate.run,
            candidate.candidate_id,
            candidate.source_sha256,
            "caller_declared",
        )
        detect = candidate.detect
    else:
        raise UnsupportedPipelineError
    records = loaded.records
    cases: dict[str, list[dict[str, Any]]] = {
        row["case_id"]: [] for row in records["documents"] if row["panel"] == "known_regression"
    }
    if not cases:
        raise UnsupportedPipelineError
    mentions = {row["mention_id"]: row for row in records["mentions"]}
    precedence = records[loaded.manifest["profiles"][profile]["resource"]]["precedence"]
    examples, predictions = [], []
    totals: dict[str, int] = {}
    failed_units = 0
    detection_failed = False
    for unit in sorted(records["units"], key=lambda row: row["unit_id"]):
        if unit["case_id"] not in cases:
            continue
        unit_mentions = [row for row in records["mentions"] if row["unit_id"] == unit["unit_id"]]
        examples.append(
            Example(
                unit["unit_id"],
                unit["text"],
                tuple(
                    GoldSpan(row["entity_type"], row["start"], row["end"]) for row in unit_mentions
                ),
                "known_regression",
                "package-fixture",
            )
        )
        rows = [
            row
            for row in records["expectations"]
            if row["profile_id"] == profile
            and (mentions[row["mention_id"]]["unit_id"] if row["mention_id"] else row["unit_id"])
            == unit["unit_id"]
        ]
        requirements, overridden = resolve_requirements(rows, mentions, precedence)
        observed = None
        error, state = False, "ERROR"
        try:
            _gold, policy = transformation_policy(requirements)
            result = run(unit["text"], policy)
            if not isinstance(result, Result) or not isinstance(result.status, ReleaseStatus):
                raise ValueError
            if result.output_text is not None and not isinstance(result.output_text, str):
                raise ValueError
            state = result.status.value
            observed = TransformationOutput(result.output_text, tuple(result.mappings), state)
        except Exception:
            error = True
            failed_units += 1
        if detect is not None:
            try:
                predictions.append(_findings(detect(unit["text"]), unit["text"]))
            except Exception:
                detection_failed = True
        inspected = inspect_text_output(unit["text"], requirements, observed)
        cases[unit["case_id"]].append({**inspected, "state": state, "error": error})
        for key, value in inspected.items():
            if type(value) is int:
                totals[key] = totals.get(key, 0) + value
        totals["overridden_chars"] = totals.get("overridden_chars", 0) + overridden
    documents = [_document_summary(events) for events in cases.values()]
    failed_documents = sum(row["failed"] for row in documents)
    states = {
        state: sum(row["state"] == state for row in documents)
        for state in (*[item.value for item in ReleaseStatus], "ERROR")
    }
    emitted, approved = (
        _risk(documents),
        _risk([row for row in documents if row["state"] == "APPROVED"]),
    )
    detection = score_detection(
        examples,
        predictions if detect is not None and not detection_failed else None,
        sorted(loaded.manifest["scope"]["entity_types"]),
        {
            row["unit_id"]: set(row["exhaustive_entity_types"])
            for row in loaded.manifest["annotation_coverage"]
        },
        {
            (row["unit_id"], row["entity_type"], row["start"], row["end"])
            for row in records["mentions"]
            if row["certainty"] == "ambiguous"
        },
    )
    known_failure = any(
        totals[key] > 0
        for key in ("leaked_mentions", "overtransformed_chars", "release_state_failures")
    )
    complete = (
        all(row["complete"] for row in documents)
        and not failed_units
        and detect is not None
        and not detection_failed
        and not totals["review_required_spans"]
    )
    report = {
        "schema_version": "df-eval-mx.pipeline-report.v1",
        "result": {
            "candidate": {
                "id": identity,
                "source_sha256": candidate_sha,
                "identity_provenance": provenance,
            },
            "evaluator": {"source_sha256": source},
            "dataset": {
                "id": "sha256:" + manifest_sha256,
                "version": loaded.manifest["dataset_version"],
                "panel": "known_regression",
            },
            "profile": {"id": profile, "ratified": False},
            "scope": {"track": "pipeline", "source_format": "text"},
            "execution": {
                "required_documents": len(cases),
                "completed_documents": len(cases) - failed_documents,
                "failed_documents": failed_documents,
                "required_units": len(examples),
                "failed_units": failed_units,
            },
            "attempt_status": "candidate_error" if failed_units else "completed",
            "metrics": {
                **totals,
                "required_documents": len(cases),
                "joint_success_documents": sum(row["joint"] for row in documents),
                "retention": totals["retained_chars"] / totals["retention_required_chars"]
                if totals["retention_required_chars"]
                else None,
            },
            "release": {
                "states": states,
                "no_output_documents": sum(not row["emitted"] for row in documents),
                "emitted": emitted,
                "approved": approved,
                "state_aggregation": "worst_fragment_state.v1",
            },
            "detection": detection,
            "detection_observation": "ORIGINAL_INPUT_SCAN"
            if detect is not None and not detection_failed
            else "ORIGINAL_DETECTIONS_UNAVAILABLE",
            "verdicts": {
                "execution": "INCOMPLETE" if failed_units else "COMPLETED",
                "technical_conformity": "FAIL"
                if known_failure
                else "PASS"
                if complete
                else "INCOMPLETE",
                "quality": "DESCRIPTIVE_ONLY",
            },
            "limitations": [
                "KNOWN_REGRESSION_ONLY",
                "TEXT_ONLY",
                "PROPOSED_PROFILE",
                "NO_PROCESS_ISOLATION",
                "EMPIRICAL_BOUNDS_NOT_POPULATION_CONFIDENCE_INTERVALS",
            ],
        },
    }
    _write_report(Path(output), report)
    return report
