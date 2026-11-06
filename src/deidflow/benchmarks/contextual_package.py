"""Fixed fictional contextual references, independent of candidate predictions."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any

from ._package_io import strict_json
from .synthetic_package import (
    canonical_json,
    read_operational_decision,
    write_package_records,
)

GENERATOR_VERSION = "mx-contextual-1.0.0"
_DATE = "2026-11-06T00:00:00Z"
_PROFILES = (
    "detection-descriptive-v1",
    "validation-descriptive-v1",
    "transformation-descriptive-v1",
    "pipeline-descriptive-v1",
)
_CLINICAL = {"DIAGNOSIS", "MEDICAL_CONDITION", "MEDICATION", "TREATMENT", "CLINICAL_OBSERVATION"}


@dataclass(frozen=True)
class _Span:
    label: str
    surface: str
    occurrence: int = 0
    identity: str | None = None
    identity_method: str = "synthetic_identity"


@dataclass(frozen=True)
class _Case:
    number: int
    family: int
    stratum: str
    text: str
    spans: tuple[_Span, ...]
    ambiguous: bool = False


_NARRATIVE = (
    "Caso ficticio. José Ángel del Río niega diabetes. Recibe paracetamol 500 mg por vía oral "
    "cada 8 horas. Su madre refiere dolor leve; el paciente no presenta dolor."
)
_NARRATIVE_SPANS = (
    _Span("PERSON", "José Ángel del Río", identity="i-2"),
    _Span("DIAGNOSIS", "diabetes"),
    _Span("CLINICAL_OBSERVATION", "niega diabetes"),
    _Span("MEDICATION", "paracetamol"),
    _Span("TREATMENT", "paracetamol 500 mg por vía oral cada 8 horas"),
    _Span("MEDICAL_CONDITION", "dolor leve"),
    _Span("CLINICAL_OBSERVATION", "Su madre refiere dolor leve"),
    _Span("MEDICAL_CONDITION", "dolor", 1),
    _Span("CLINICAL_OBSERVATION", "el paciente no presenta dolor"),
)

_CASES = (
    _Case(
        1,
        1,
        "form",
        "Caso ficticio.\r\nPaciente: María de la Luz Castañeda Robles\r\n"
        "Domicilio: Av. Lluvia de Papel núm. 28, int. B, Col. Nube Azul, Villa Nopal "
        "(localidad ficticia)\r\nDiagnóstico: diabetes mellitus tipo 2\r\n"
        "Tratamiento: metformina 500 mg por vía oral cada 12 horas\r\nObservación: sin fiebre",
        (
            _Span("PERSON", "María de la Luz Castañeda Robles", identity="i-1"),
            _Span("ADDRESS", "Av. Lluvia de Papel núm. 28, int. B, Col. Nube Azul, Villa Nopal"),
            _Span("DIAGNOSIS", "diabetes mellitus tipo 2"),
            _Span("TREATMENT", "metformina 500 mg por vía oral cada 12 horas"),
            _Span("MEDICATION", "metformina"),
            _Span("CLINICAL_OBSERVATION", "sin fiebre"),
            _Span("MEDICAL_CONDITION", "fiebre"),
        ),
    ),
    _Case(2, 2, "narrative_dotted", _NARRATIVE, _NARRATIVE_SPANS),
    _Case(3, 2, "narrative_undotted", _NARRATIVE.replace(".", ""), _NARRATIVE_SPANS),
    _Case(
        4,
        3,
        "common_words",
        "Caso ficticio. La paciente Esperanza Sierra expresa esperanza de mejorar. "
        "Domicilio: Calle Esperanza 7, Col. Sierra Azul, Villa Papel (localidad ficticia).",
        (
            _Span("PERSON", "Esperanza Sierra", identity="i-4"),
            _Span("ADDRESS", "Calle Esperanza 7, Col. Sierra Azul, Villa Papel"),
        ),
    ),
    _Case(
        5,
        4,
        "distinct_homonyms",
        "Caso ficticio. La recién nacida Rosa del Valle es la paciente. La médica tratante "
        "también se llama Rosa del Valle. Son dos personas distintas. "
        "La paciente no presenta fiebre.",
        (
            _Span("PERSON", "Rosa del Valle", identity="i-51"),
            _Span("PERSON", "Rosa del Valle", 1, "i-52"),
            _Span("CLINICAL_OBSERVATION", "La paciente no presenta fiebre"),
            _Span("MEDICAL_CONDITION", "fiebre"),
        ),
    ),
    _Case(
        6,
        5,
        "continuity_origin",
        "Primera nota ficticia. La paciente Elena Itzel Castañeda recibe amoxicilina "
        "250 mg cada 8 horas.",
        (
            _Span(
                "PERSON",
                "Elena Itzel Castañeda",
                identity="i-6",
                identity_method="explicit_reference",
            ),
            _Span("MEDICATION", "amoxicilina"),
            _Span("TREATMENT", "amoxicilina 250 mg cada 8 horas"),
        ),
    ),
    _Case(
        7,
        5,
        "continuity_followup",
        "Continuación de «Primera nota ficticia». Elena Itzel Castañeda es la misma paciente "
        "de esa nota. Continúa el tratamiento indicado.",
        (
            _Span(
                "PERSON",
                "Elena Itzel Castañeda",
                identity="i-6",
                identity_method="explicit_reference",
            ),
            _Span("TREATMENT", "Continúa el tratamiento indicado"),
        ),
    ),
    _Case(
        8,
        6,
        "alias_unresolved",
        "Caso ficticio. En la primera hoja figura José de la Paz. Otra nota menciona a Pepe "
        "como paciente. No se indica si Pepe es José de la Paz o una persona distinta.",
        (
            _Span("PERSON", "José de la Paz"),
            _Span("PERSON", "José de la Paz", 1),
            _Span("PERSON", "Pepe"),
            _Span("PERSON", "Pepe", 1),
        ),
    ),
    _Case(
        9,
        7,
        "nested_clinical",
        "Caso ficticio. Tratamiento: fisioterapia respiratoria con ejercicios suaves. "
        "Observación: niega dolor torácico.",
        (
            _Span("TREATMENT", "fisioterapia respiratoria con ejercicios suaves"),
            _Span("CLINICAL_OBSERVATION", "niega dolor torácico"),
            _Span("MEDICAL_CONDITION", "dolor torácico"),
        ),
    ),
    _Case(
        10,
        8,
        "crossed_mentions",
        "Plantilla ficticia de superposición. La cadena «Ana María Sol» codifica a dos "
        "personas distintas: «Ana María» y «María Sol». El segmento «María» es compartido.",
        (
            _Span("PERSON", "Ana María", identity="i-a1"),
            _Span("PERSON", "María Sol", identity="i-a2"),
            _Span("PERSON", "Ana María", 1, "i-a1"),
            _Span("PERSON", "María Sol", 1, "i-a2"),
        ),
    ),
    _Case(
        11,
        9,
        "uncertain_referent",
        "Caso ficticio. La nota contiene «Sol». No permite saber si identifica a una persona, "
        "una calle o una firma comercial.",
        (_Span("PERSON", "Sol"),),
        True,
    ),
    _Case(
        12,
        10,
        "uncertain_boundaries",
        "Ficha ficticia incompleta: «Ana María Sol». Se perdieron los separadores entre los "
        "nombres de paciente y acompañante.",
        (_Span("PERSON", "Ana María"), _Span("PERSON", "María Sol")),
        True,
    ),
)


def _annotations() -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for case in _CASES:
        for span in case.spans:
            start = -1
            for _ in range(span.occurrence + 1):
                start = case.text.index(span.surface, start + 1)
            annotations.append(
                {
                    "mention_id": f"m-{len(annotations) + 1:x}",
                    "case_id": f"c-{case.number:x}",
                    "unit_id": f"u-{case.number:x}",
                    "entity_type": span.label,
                    "start": start,
                    "end": start + len(span.surface),
                    "surface": span.surface,
                    "left_boundary": case.text[max(0, start - 24) : start],
                    "right_boundary": case.text[
                        start + len(span.surface) : start + len(span.surface) + 24
                    ],
                    "certainty": "ambiguous" if case.ambiguous else "confirmed",
                    "entity_id": span.identity,
                    "identity_method": span.identity_method if span.identity else None,
                }
            )
    return annotations


def _lineage(case: _Case) -> dict[str, Any]:
    if case.number == 3:
        return {
            "root_document_id": "c-2",
            "parent_case_id": "c-2",
            "variant_id": "v-3",
            "perturbation_recipe": {
                "version": "1.0.0",
                "operation": "remove_sentence_periods",
                "seed": 0,
                "parameters": {"removed_literal": "."},
            },
        }
    return {
        "root_document_id": f"c-{case.number:x}",
        "parent_case_id": None,
        "variant_id": None,
        "perturbation_recipe": None,
    }


def _snapshot(guide: bytes) -> bytes:
    return canonical_json(
        {
            "schema_version": "df-eval-mx.contextual-reference.v1",
            "generator_version": GENERATOR_VERSION,
            "guide_sha256": hashlib.sha256(guide).hexdigest(),
            "cases": [
                {
                    "case_id": f"c-{case.number:x}",
                    "group_id": f"g-{case.family:x}",
                    "template_family_id": f"t-{case.family:x}",
                    "stratum": case.stratum,
                    "text": case.text,
                    "ambiguous": case.ambiguous,
                    **_lineage(case),
                }
                for case in _CASES
            ],
            "annotations": [
                row
                | {
                    "actions_by_mode": {
                        mode: "review_required"
                        if row["certainty"] == "ambiguous"
                        else (
                            "preserve"
                            if mode == "contextual" and row["entity_type"] in _CLINICAL
                            else "remove"
                        )
                        for mode in ("contextual", "strict", "ambiguous")
                        if (mode == "ambiguous") == (row["certainty"] == "ambiguous")
                    }
                }
                for row in _annotations()
            ],
            "expectation_rule": {
                "contextual": "Identifiers remove; clinical mentions preserve, including complete assertions/regimens",
                "strict": "Identifiers and complete clinical assertions/regimens remove",
                "ambiguous": "Unresolved referents/boundaries require review; never infer identity",
            },
        }
    )


def _reference() -> tuple[bytes, bytes, dict[str, Any], bytes]:
    """Hash-bind the real guide/review record to the exact authored reference."""
    resources = files("deidflow.benchmarks")
    guide = resources.joinpath("_contextual_guide.md").read_bytes()
    snapshot = _snapshot(guide)
    ledger_bytes = resources.joinpath("_contextual_reviews.json").read_bytes()
    try:
        ledger = strict_json(ledger_bytes)
        _check_review_evidence(ledger, guide, snapshot)
    except (ValueError, KeyError, TypeError):
        raise ValueError("Invalid contextual reference evidence") from None
    return guide, snapshot, ledger, ledger_bytes


def _check_review_evidence(ledger: dict[str, Any], guide: bytes, snapshot: bytes) -> None:
    if (
        ledger["schema_version"] != "df-eval-mx.agent-reference-review.v1"
        or ledger["guide_sha256"] != hashlib.sha256(guide).hexdigest()
        or ledger["reference_sha256"] != hashlib.sha256(snapshot).hexdigest()
        or ledger["status"] not in {"draft", "agent_reviewed"}
    ):
        raise ValueError
    reviews = ledger["reviews"]
    if not isinstance(reviews, list):
        raise ValueError
    if ledger["status"] == "draft":
        if reviews:
            raise ValueError
        return
    expected_decisions = {
        f"c-{case.number:x}": "unresolved_challenge" if case.ambiguous else "accepted"
        for case in _CASES
    }
    if (
        len(reviews) < 2
        or len({row["review_id"] for row in reviews}) != len(reviews)
        or len({row["actor_id"] for row in reviews}) != len(reviews)
    ):
        raise ValueError
    for row in reviews:
        if (
            re.fullmatch(r"r-[0-9a-f]{1,32}", row["review_id"]) is None
            or row["actor_type"] != "agent"
            or not isinstance(row["actor_id"], str)
            or not row["actor_id"]
            or row["reference_sha256"] != ledger["reference_sha256"]
            or row["guide_sha256"] != ledger["guide_sha256"]
            or row["candidate_predictions_seen"] is not False
            or row["outcome"] != "accepted_with_unresolved_challenges"
            or len(row["case_ids"]) != len(expected_decisions)
            or set(row["case_ids"]) != set(expected_decisions)
            or row["case_decisions"] != expected_decisions
            or datetime.fromisoformat(row["reviewed_at"]).utcoffset() != timedelta(0)
        ):
            raise ValueError


def _decision(path: str | Path, sha256: str) -> tuple[bytes, dict[str, str]]:
    receipt, metadata = read_operational_decision(path, sha256=sha256)
    try:
        d3 = strict_json(receipt)["D3"]
        if (
            d3["contextual-v1"]
            != {
                "clinical_facts_negation_dose_quantity_relations": "preserve",
                "identifiers": "remove",
            }
            or d3["strict-v1"]
            != {
                "clinical_facts_negation_dose_quantity_relations": "remove",
                "identifiers": "remove",
            }
            or d3["allowed_operators"]
            != {
                "remove": ["placeholder", "redact", "suppress"],
                "preserve": ["keep"],
                "review_required": [],
            }
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ValueError("Invalid operational decision receipt") from None
    return receipt, metadata


def generate_contextual_package(
    destination: str | Path, *, mode: str, decision: str | Path, decision_sha256: str
) -> dict[str, Any]:
    """Write one fixed contextual/strict/challenge package; never overwrite output.

    The caller supplies the local governing receipt and its trusted pin. Installed
    package resources contain the authored guide and actual reference-review log.
    No repository documentation, candidate, remote service or RNG is consulted.
    """
    if not isinstance(mode, str) or mode not in {"contextual", "strict", "ambiguous"}:
        raise ValueError("Invalid contextual corpus mode")
    receipt, decision_metadata = _decision(decision, decision_sha256)
    guide, snapshot, ledger, ledger_bytes = _reference()
    cases = [case for case in _CASES if case.ambiguous == (mode == "ambiguous")]
    case_ids = {f"c-{case.number:x}" for case in cases}
    annotations = [row for row in _annotations() if row["case_id"] in case_ids]
    entities = sorted({row["entity_type"] for row in annotations})
    reviewed = ledger["status"] == "agent_reviewed"
    review_ids = [row["review_id"] for row in ledger["reviews"]] if reviewed else []
    records: dict[str, Any] = {
        "sources": [],
        "documents": [],
        "units": [],
        "mentions": [],
        "expectations": [],
        "generator-b": canonical_json(
            {
                "version": GENERATOR_VERSION,
                "source": "original fixed fictional literals",
                "license": "Apache-2.0",
                "mode": mode,
                "reference_resource": "evidence-3",
            }
        ),
        "evidence-1": guide,
        "evidence-2": ledger_bytes,
        "evidence-3": snapshot,
        "evidence-9": receipt,
    }
    manifest: dict[str, Any] = {
        "schema_version": "df-eval-mx.package.v1",
        "dataset_version": "1.0.0",
        "taxonomy_version": "df-eval-mx.taxonomy.v1",
        "annotation_version": "df-eval-mx.annotation.v1",
        "dataset_id": {"contextual": "d-11", "strict": "d-12", "ambiguous": "d-13"}[mode],
        "created_at": _DATE,
        "resources": {},
        "partitions": {},
        "panels": {},
        "scope": {
            "language": "es",
            "country": "MX",
            "entity_types": entities,
            "formats": ["text"],
            "required_strata": sorted({case.stratum for case in cases}),
            "optional_strata": [],
        },
        "profiles": {
            profile: {"resource": f"profile-{index:x}", "sha256": "0" * 64}
            for index, profile in enumerate(_PROFILES, 1)
        },
        "generation": {
            "generator_version": GENERATOR_VERSION,
            "random_algorithm": "none",
            "seeds": {},
            "resources": ["generator-b", "evidence-1", "evidence-2", "evidence-3", "evidence-9"],
            "perturbation_rules": [],
        },
        "freeze": {
            "status": "unfrozen",
            "frozen_at": None,
            "resource_sha256": {},
            "exposure": "known_regression",
            "custody": None,
        },
        "annotation_coverage": [],
    }
    for index, profile in enumerate(_PROFILES, 1):
        records[f"profile-{index:x}"] = {
            "profile_id": profile,
            "ratified": False,
            "clinical_policy": {
                "contextual": "preserve_context",
                "strict": "strict",
                "ambiguous": "not_evaluated",
            }[mode],
            "quasi_identifier_policy": "review_required",
            "precedence": ["review_required", "remove", "preserve"],
        }
    for case in cases:
        suffix = f"{case.number:x}"
        digest = hashlib.sha256(case.text.encode("utf-8")).hexdigest()
        records["units"].append(
            {
                "unit_id": "u-" + suffix,
                "case_id": "c-" + suffix,
                "text": case.text,
                "text_sha256": digest,
                "content_role": "body",
                "locator": {"kind": "text", "index": 0},
            }
        )
        records["sources"].append(
            {
                "source_id": "s-" + suffix,
                "revision": "1.0.0",
                "content_sha256": digest,
                "origin_kind": "synthetic",
                "language": "es",
                "country": "MX",
                "domain": "clinical",
                "origin_reference": "generator-b",
                "terms_reference": "generator-b",
                "license": "Apache-2.0",
                "attribution": "DeidFlow: corpus ficticio original",
                "permissions": dict.fromkeys(
                    ("evaluation", "annotation", "derivation", "training", "redistribution"), True
                ),
                "permission_review": {
                    "status": "synthetic_fixture",
                    "evidence_ref": "generator-b",
                    "reviewed_at": _DATE,
                },
                "personal_data_status": "fictional",
                "exposure": {
                    "training": "unknown",
                    "tuning": "unknown",
                    "prior_evaluation": True,
                    "candidate_exposure": "known",
                },
            }
        )
        records["documents"].append(
            {
                "case_id": "c-" + suffix,
                "source_id": "s-" + suffix,
                **_lineage(case),
                "group_id": f"g-{case.family:x}",
                "template_family_id": f"t-{case.family:x}",
                "partition": None,
                "panel": "known_regression",
                "format": "text",
                "strata": [case.stratum],
                "capabilities_required": ["text_detection"],
                "artifact_ref": None,
                "artifact_sha256": None,
                "unit_ids": ["u-" + suffix],
                "annotation_state": "unresolvable"
                if case.ambiguous
                else "adjudicated"
                if reviewed
                else "draft",
            }
        )
        manifest["annotation_coverage"].append(
            {
                "unit_id": "u-" + suffix,
                "exhaustive_entity_types": [] if case.ambiguous else entities,
                "inspected_ranges": [{"start": 0, "end": len(case.text)}],
                "limitations": ["Synthetic authored scope; no deployment or blind-test claim"]
                + (["Unresolved reference; challenge only"] if case.ambiguous else []),
            }
        )
    for row in annotations:
        identity = row["entity_id"]
        records["mentions"].append(
            {
                key: row[key]
                for key in (
                    "mention_id",
                    "unit_id",
                    "entity_type",
                    "start",
                    "end",
                    "certainty",
                    "entity_id",
                )
            }
            | {
                "region_ref": None,
                "validity": dict.fromkeys(("pattern", "structure", "checksum"), "not_applicable"),
                "sensitivity_reference": "Authored fictional reference; clinical sensitivity remains policy-dependent",
                "identity_evidence": {
                    "method": row["identity_method"],
                    "mention_ids": [
                        other["mention_id"]
                        for other in annotations
                        if other["entity_id"] == identity
                    ],
                }
                if identity
                else None,
                "annotation_provenance": {
                    "method": "synthetic_fixture",
                    "manual_version": "1.0.0",
                    "reviews": review_ids,
                },
            }
        )
        action = (
            "review_required"
            if row["certainty"] == "ambiguous"
            else (
                "preserve" if mode == "contextual" and row["entity_type"] in _CLINICAL else "remove"
            )
        )
        for profile in _PROFILES:
            records["expectations"].append(
                {
                    "expectation_id": f"e-{len(records['expectations']) + 1:x}",
                    "profile_id": profile,
                    "case_id": row["case_id"],
                    "mention_id": row["mention_id"],
                    "unit_id": None,
                    "start": None,
                    "end": None,
                    "action": action,
                    "allowed_operators": {
                        "remove": ["placeholder", "redact", "suppress"],
                        "preserve": ["keep"],
                        "review_required": [],
                    }[action],
                    "verification": {
                        "remove": "complete_removal",
                        "preserve": "exact_preservation",
                        "review_required": "human_review",
                    }[action],
                    "coverage_required": "complete",
                    "acceptable_release_states": ["REVIEW_REQUIRED"]
                    if action == "review_required"
                    else ["APPROVED"],
                }
            )
    package = write_package_records(destination, records, manifest)
    return {
        "manifest_sha256": package.manifest_sha256,
        "generator_version": GENERATOR_VERSION,
        "mode": mode,
        "documents": len(cases),
        "groups": len({case.family for case in cases}),
        "mentions": len(annotations),
        "support_by_entity": dict(
            sorted(Counter(row["entity_type"] for row in annotations).items())
        ),
        "support_by_stratum": dict(sorted(Counter(case.stratum for case in cases).items())),
        "ambiguous_mentions": sum(row["certainty"] == "ambiguous" for row in annotations),
        "reference_status": ledger["status"],
        "reference_sha256": hashlib.sha256(snapshot).hexdigest(),
        "guide_sha256": hashlib.sha256(guide).hexdigest(),
        "review_count": len(review_ids),
        "decision": decision_metadata,
        "executable_profile_ratified": False,
        "quality_ratified": False,
        "quality": "DESCRIPTIVE_ONLY",
        "panel": "known_regression",
        "limitations": [
            "KNOWN_SYNTHETIC_REGRESSION",
            "NO_BLIND_TEST",
            "AGENT_REFERENCE_NOT_HUMAN_REVIEW",
            "IDENTITY_METRICS_NOT_IMPLEMENTED",
        ]
        + (["UNRESOLVED_CHALLENGE_EXCLUDED_FROM_PRIMARY"] if mode == "ambiguous" else []),
    }
