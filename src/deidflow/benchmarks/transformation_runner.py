"""Gold-driven textual transformation evaluation, independent of detection."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deidflow.core import Finding
from deidflow.policies import Policy, Rule
from deidflow.transformations import transform_text

from ._package_io import is_sha256
from .email import _source_digest, _write_report
from .evaluation_package import load_evaluation_package
from .transformation_metrics import (
    TextRequirement,
    TransformationOutput,
    inspect_text_output,
    resolve_requirements,
)


@dataclass(frozen=True)
class TransformationCandidate:
    candidate_id: str
    source_sha256: str
    transform: Callable[[str, tuple[Finding, ...], Policy], TransformationOutput]


class UnsupportedTransformationError(ValueError):
    status = "UNSUPPORTED"

    def __init__(self) -> None:
        super().__init__("Unsupported transformation benchmark configuration")


def transformation_policy(
    requirements: list[TextRequirement],
) -> tuple[tuple[Finding, ...], Policy]:
    findings: list[Finding] = []
    rules: dict[str, Rule] = {}
    for requirement in requirements:
        if requirement.action in {"preserve", "review_required"} or not requirement.ranges:
            continue
        operator = requirement.operators[0]
        label = requirement.entity_type
        rule = Rule(operator)
        if label in rules and rules[label] != rule:
            raise UnsupportedTransformationError
        rules[label] = rule
        findings.extend(
            Finding(label, a, b, 1.0, "benchmark-gold", protected=True)
            for a, b in requirement.ranges
        )
    return tuple(findings), Policy(
        name="benchmark-explicit", default=Rule("keep"), entities=rules, require_ner=False
    )


def _builtin(text: str, gold: tuple[Finding, ...], policy: Policy) -> TransformationOutput:
    emitted, mappings = transform_text(text, list(gold), policy)
    return TransformationOutput(emitted, tuple(mappings))


def run_transformation_benchmark(
    package: str | Path,
    *,
    manifest_sha256: str,
    candidate: str | TransformationCandidate,
    profile: str,
    output: str | Path,
) -> dict[str, Any]:
    loaded = load_evaluation_package(package, manifest_sha256=manifest_sha256)
    if (
        profile != "transformation-descriptive-v1"
        or profile not in loaded.manifest["profiles"]
        or loaded.manifest["scope"]["formats"] != ["text"]
    ):
        raise UnsupportedTransformationError
    source = _source_digest()
    transform: Callable[[str, tuple[Finding, ...], Policy], TransformationOutput]
    if candidate == "transform.text":
        transform, identity, provenance = _builtin, "transform.text", "builtin"
        candidate_sha = source
    elif (
        isinstance(candidate, TransformationCandidate)
        and isinstance(candidate.candidate_id, str)
        and re.fullmatch(r"candidate-[0-9a-f]{1,32}", candidate.candidate_id)
        and is_sha256(candidate.source_sha256)
        and callable(candidate.transform)
    ):
        transform, identity, candidate_sha, provenance = (
            candidate.transform,
            candidate.candidate_id,
            candidate.source_sha256,
            "caller_declared",
        )
    else:
        raise UnsupportedTransformationError
    records = loaded.records
    cases = {row["case_id"] for row in records["documents"] if row["panel"] == "known_regression"}
    if not cases:
        raise UnsupportedTransformationError
    mentions = {row["mention_id"]: row for row in records["mentions"]}
    totals: dict[str, int] = {}
    successful = set(cases)
    failures, units, overridden = 0, 0, 0
    complete = True
    for unit in records["units"]:
        if unit["case_id"] not in cases:
            continue
        units += 1
        rows = [
            row
            for row in records["expectations"]
            if row["profile_id"] == profile
            and (mentions[row["mention_id"]]["unit_id"] if row["mention_id"] else row["unit_id"])
            == unit["unit_id"]
        ]
        requirements, superseded = resolve_requirements(
            rows, mentions, records[loaded.manifest["profiles"][profile]["resource"]]["precedence"]
        )
        overridden += superseded
        try:
            gold, policy = transformation_policy(requirements)
            observed = transform(unit["text"], gold, policy)
            if not isinstance(observed, TransformationOutput):
                raise ValueError
        except Exception:
            observed = None
            failures += 1
        inspected = inspect_text_output(unit["text"], requirements, observed)
        complete = complete and inspected["verification_complete"]
        if not inspected["joint_success"]:
            successful.discard(unit["case_id"])
        for key, value in inspected.items():
            if type(value) is int:
                totals[key] = totals.get(key, 0) + value
    totals.update(
        joint_success_documents=len(successful),
        required_documents=len(cases),
        overridden_chars=overridden,
    )
    metrics: dict[str, Any] = dict(totals)
    metrics["retention"] = (
        totals["retained_chars"] / totals["retention_required_chars"]
        if totals["retention_required_chars"]
        else None
    )
    status = (
        "UNVERIFIABLE"
        if not complete
        else "REVIEW_REQUIRED"
        if totals["review_required_spans"]
        else "COMPLETED"
    )
    report = {
        "schema_version": "df-eval-mx.transformation-report.v1",
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
            "scope": {"track": "transformation", "source_format": "text"},
            "execution": {
                "required_documents": len(cases),
                "required_units": units,
                "failed_units": failures,
            },
            "attempt_status": "candidate_error" if failures else "completed",
            "verification_status": status,
            "metrics": metrics,
            "quality": "DESCRIPTIVE_ONLY",
            "limitations": [
                "KNOWN_REGRESSION_ONLY",
                "TEXT_ONLY",
                "PROPOSED_PROFILE",
                "NO_PROCESS_ISOLATION",
                "GENERALIZATION_AND_KEYED_OPERATORS_REQUIRE_VERIFIERS",
            ],
        },
    }
    _write_report(Path(output), report)
    return report


__all__ = ["TransformationCandidate", "TransformationOutput", "run_transformation_benchmark"]
