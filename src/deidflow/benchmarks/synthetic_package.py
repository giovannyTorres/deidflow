"""Deterministic fictional packages; no production detector supplies the reference."""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ._package_io import (
    MAX_MANIFEST_BYTES,
    MAX_PACKAGE_BYTES,
    MAX_RECORDS,
    MAX_RESOURCE_BYTES,
    MAX_RESOURCES,
    is_sha256,
    strict_json,
)
from .evaluation_package import EvaluationPackage, InvalidPackageError, load_evaluation_package

GENERATOR_VERSION = "mx-identifiers-1.0.0"
_DATE = "2026-11-06T00:00:00Z"
_PROFILES = (
    "detection-descriptive-v1",
    "validation-descriptive-v1",
    "transformation-descriptive-v1",
    "pipeline-descriptive-v1",
)


def canonical_json(value: Any) -> bytes:
    """Stable UTF-8 representation used by generated package resources."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _bounded_json(value: Any, limit: int, *, jsonl: bool = False) -> bytes:
    """Stop encoding at the remaining resource/package budget, including newlines."""
    encoder = json.JSONEncoder(
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    payload = bytearray()
    for row in value if jsonl else (value,):
        for chunk in encoder.iterencode(row):
            if len(chunk) > limit - len(payload):
                raise ValueError
            encoded = chunk.encode("utf-8")
            if len(encoded) > limit - len(payload):
                raise ValueError
            payload.extend(encoded)
        if jsonl:
            if len(payload) >= limit:
                raise ValueError
            payload.extend(b"\n")
    return bytes(payload)


def write_package_records(
    destination: str | Path, records: dict[str, Any], manifest: dict[str, Any]
) -> EvaluationPackage:
    """Serialize records, rebuild resource/profile hashes and memberships, then admit.

    Lists are JSONL, dictionaries JSON, bytes binary. The caller owns annotation,
    unit/source digests, lineage and exposure; these are checked, never repaired.
    Existing output is never replaced. Invalid admission leaves no output package.
    """
    try:
        return _write_records(destination, records, manifest)
    except InvalidPackageError:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError("Invalid synthetic package output") from None


def _write_records(
    destination: str | Path, records: dict[str, Any], manifest: dict[str, Any]
) -> EvaluationPackage:
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise ValueError("Synthetic package destination already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not 1 <= len(records) <= MAX_RESOURCES:
        raise ValueError
    value = deepcopy(manifest)
    resources = {}
    total = 0
    with TemporaryDirectory(prefix=".deidflow-package-", dir=target.parent) as temporary:
        staging = Path(temporary)
        for role, record in sorted(records.items()):
            if not isinstance(role, str) or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", role) is None:
                raise ValueError("Invalid synthetic package resource")
            if isinstance(record, bytes):
                kind, payload, count, extension = "binary", record, 0, ".bin"
            elif isinstance(record, list):
                if len(record) > MAX_RECORDS:
                    raise ValueError
                kind, count, extension = "jsonl", len(record), ".jsonl"
                payload = _bounded_json(
                    record, min(MAX_RESOURCE_BYTES, MAX_PACKAGE_BYTES - total), jsonl=True
                )
            elif isinstance(record, dict):
                kind, count, extension = "json", 1, ".json"
                payload = _bounded_json(record, min(MAX_RESOURCE_BYTES, MAX_PACKAGE_BYTES - total))
            else:
                raise ValueError("Invalid synthetic package resource")
            total += len(payload)
            if len(payload) > MAX_RESOURCE_BYTES or total > MAX_PACKAGE_BYTES:
                raise ValueError("Invalid synthetic package resource")
            name = role + extension
            (staging / name).write_bytes(payload)
            resources[role] = {
                "path": name,
                "kind": kind,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "records": count,
            }
        value["resources"] = resources
        for profile in value["profiles"].values():
            profile["sha256"] = resources[profile["resource"]]["sha256"]
        for field, names in (
            ("partition", ("train", "validation", "calibration", "blind_test")),
            ("panel", ("known_regression", "external_transfer")),
        ):
            value["partitions" if field == "partition" else "panels"] = {
                name: {
                    "case_ids": sorted(
                        row["case_id"] for row in records["documents"] if row[field] == name
                    ),
                    "group_ids": sorted(
                        {row["group_id"] for row in records["documents"] if row[field] == name}
                    ),
                }
                for name in names
            }
        payload = _bounded_json(value, min(MAX_MANIFEST_BYTES, MAX_PACKAGE_BYTES - total))
        digest = hashlib.sha256(payload).hexdigest()
        (staging / "manifest.json").write_bytes(payload)
        admitted = load_evaluation_package(staging, manifest_sha256=digest)
        # mkdir, rather than an overwriting rename, reserves an unused destination.
        target.mkdir()
        try:
            for member in staging.iterdir():
                shutil.copyfile(member, target / member.name)
        except OSError:
            shutil.rmtree(target)
            raise
    return admitted


def read_operational_decision(path: str | Path, *, sha256: str) -> tuple[bytes, dict[str, str]]:
    """Read a caller-pinned local governing receipt; never ratify an execution profile."""
    try:
        with Path(path).open("rb") as stream:
            payload = stream.read(MAX_RESOURCE_BYTES + 1)
        if (
            not is_sha256(sha256)
            or len(payload) > MAX_RESOURCE_BYTES
            or hashlib.sha256(payload).hexdigest() != sha256
        ):
            raise ValueError
        receipt = strict_json(payload)
        if (
            receipt["schema_version"] != "df-eval-mx.operational-decision.v1"
            or receipt["decision_id"] != "BMX-09-operational-v1"
            or receipt["version"] != "1.0.0"
            or receipt["status"] != "ratified"
            or receipt["quality_profile_ratified"] is not False
            or receipt["D2"]
            != {
                "ambiguous": "review_required",
                "attributed_personal_plausible_even_invalid": "remove",
                "documented_nonpersonal_distractor": "preserve",
                "validity_is_sensitivity": False,
            }
            or receipt["D3"]["precedence"] != ["review_required", "remove", "preserve"]
        ):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("Invalid operational decision receipt") from None
    return payload, {"id": receipt["decision_id"], "sha256": sha256, "status": "ratified"}


def _manifest(entity_types: list[str], seed: int) -> dict[str, Any]:
    return {
        "schema_version": "df-eval-mx.package.v1",
        "dataset_version": "1.0.0",
        "taxonomy_version": "df-eval-mx.taxonomy.v1",
        "annotation_version": "df-eval-mx.annotation.v1",
        "dataset_id": "d-10",
        "created_at": _DATE,
        "resources": {},
        "partitions": {},
        "panels": {},
        "scope": {
            "language": "es",
            "country": "MX",
            "entity_types": entity_types,
            "formats": ["text"],
            "required_strata": ["valid"],
            "optional_strata": [],
        },
        "profiles": {
            profile: {"resource": f"profile-{index:x}", "sha256": "0" * 64}
            for index, profile in enumerate(_PROFILES, 1)
        },
        "generation": {
            "generator_version": GENERATOR_VERSION,
            "random_algorithm": "python-random-v1",
            "seeds": {"templates": seed},
            "resources": ["generator-a", "evidence-1", "evidence-9"],
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


# References are declared literals, checked offline using independent tools and
# worksheets. Generation never imports validators, Faker, stdnum or a detector.
_VALID = ("valid", "valid", "valid")
_BAD_CHECK = ("valid", "valid", "invalid")
_BAD_STRUCTURE = ("valid", "invalid", "valid")
_TRUNCATED = ("invalid", "invalid", "unknown")
_PHONE_FORMAT = ("valid", "unknown", "not_applicable")
_PHONE_SHORT = ("invalid", "unknown", "not_applicable")
_EMAIL_FORMAT = ("valid", "valid", "not_applicable")
_EMAIL_BAD = ("invalid", "invalid", "not_applicable")
# family, entity, literal, stratum, required action, independent attribute states
_IDENTIFIER_CASES = (
    ("rfc_physical", "RFC", "ZZZX010101AA1", "valid", "remove", _VALID),
    ("rfc_physical", "RFC", "ZZZX-010101-AA1", "formatted", "remove", _VALID),
    ("rfc_physical", "RFC", "ZZZX010101AA2", "invalid_checksum", "remove", _BAD_CHECK),
    ("rfc_physical", "RFC", "ZZZX011301AA4", "invalid_structure", "remove", _BAD_STRUCTURE),
    ("rfc_physical", "RFC", "ZZZX010101AA2", "ambiguous", "review_required", _BAD_CHECK),
    ("rfc_physical", "RFC", "ZZZX010101AA2", "nonpersonal_distractor", "preserve", _BAD_CHECK),
    ("rfc_legal_shape", "RFC", "ZZZ010101AA1", "valid", "remove", _VALID),
    ("rfc_legal_shape", "RFC", "ZZZ-010101-AA1", "formatted", "remove", _VALID),
    ("rfc_legal_shape", "RFC", "ZZZ010101AA2", "invalid_checksum", "remove", _BAD_CHECK),
    ("rfc_legal_shape", "RFC", "ZZZ010101AA2", "nonpersonal_distractor", "preserve", _BAD_CHECK),
    ("rfc_generic", "RFC", "XAXX010101000", "nonpersonal_distractor", "preserve", _BAD_CHECK),
    ("rfc_generic", "RFC", "XEXX010101000", "nonpersonal_distractor", "preserve", _VALID),
    ("curp", "CURP", "ZAXX010101HDFZZZ06", "valid", "remove", _VALID),
    ("curp", "CURP", "ZAXX010101HDFZZZ07", "invalid_checksum", "remove", _BAD_CHECK),
    ("curp", "CURP", "ZAXX010231HDFZZZ05", "invalid_structure", "remove", _BAD_STRUCTURE),
    ("curp", "CURP", "ZAXX010101HDFZZZ0", "invalid_pattern", "remove", _TRUNCATED),
    ("curp", "CURP", "ZAXX010101HDFZZZ07", "nonpersonal_distractor", "preserve", _BAD_CHECK),
    ("clabe", "CLABE", "002999000000000012", "valid", "remove", _VALID),
    ("clabe", "CLABE", "002 999 00000000001 2", "formatted", "remove", _VALID),
    ("clabe", "CLABE", "002999000000000013", "invalid_checksum", "remove", _BAD_CHECK),
    ("clabe", "CLABE", "00299900000000001", "invalid_pattern", "remove", _TRUNCATED),
    ("clabe", "CLABE", "002999000000000013", "nonpersonal_distractor", "preserve", _BAD_CHECK),
    ("pan", "PAYMENT_CARD", "9999000011112228", "valid", "remove", _VALID),
    ("pan", "PAYMENT_CARD", "9999 0000 1111 2228", "formatted", "remove", _VALID),
    ("pan", "PAYMENT_CARD", "9999000011112229", "invalid_checksum", "remove", _BAD_CHECK),
    ("pan", "PAYMENT_CARD", "9999000011118", "valid", "remove", _VALID),
    ("pan", "PAYMENT_CARD", "9999000011112229", "nonpersonal_distractor", "preserve", _BAD_CHECK),
    ("phone_mx", "PHONE", "+52 55 0000 0001", "valid", "remove", _PHONE_FORMAT),
    ("phone_mx", "PHONE", "55 0000 0001", "formatted", "remove", _PHONE_FORMAT),
    ("phone_mx", "PHONE", "+52 55 0000 001", "invalid_pattern", "remove", _PHONE_SHORT),
    ("phone_mx", "PHONE", "55 0000 0001", "nonpersonal_distractor", "preserve", _PHONE_FORMAT),
    ("email", "EMAIL", "persona.a@example.invalid", "valid", "remove", _EMAIL_FORMAT),
    ("email", "EMAIL", "persona+mx@example.invalid", "formatted", "remove", _EMAIL_FORMAT),
    ("email", "EMAIL", "persona..a@example.invalid", "invalid_pattern", "remove", _EMAIL_BAD),
    ("email", "EMAIL", "persona.a@@example.invalid", "invalid_pattern", "remove", _EMAIL_BAD),
    (
        "email",
        "EMAIL",
        "persona.a@example.invalid",
        "nonpersonal_distractor",
        "preserve",
        _EMAIL_FORMAT,
    ),
)


def _identifier_evidence() -> dict[str, Any]:
    return {
        "version": "mx-identifier-references-1.0.0",
        "tools": {
            "python-stdnum": "2.2",
            "email.headerregistry.Address": "Python standard library",
        },
        "method": "Offline separate attribute checks; full validator acceptance is not a checksum oracle",
        "rfc": {
            "tool": "stdnum.mx.rfc.compact/calc_check_digit; validate with checksum disabled for date",
            "expected_digits": {
                "ZZZX010101AA": "1",
                "ZZZX011301AA": "4",
                "ZZZ010101AA": "1",
                "XAXX01010100": "4",
                "XEXX01010100": "0",
            },
            "generics": "Invoice exceptions are nonpersonal constants; XAXX ordinary checksum invalid, XEXX valid. Strict stdnum rejects both serial components, not both checksums.",
        },
        "curp": {
            "tool": "stdnum.mx.curp",
            "expected_digits": {"ZAXX010101HDFZZZ0": "6", "ZAXX010231HDFZZZ0": "5"},
            "impossible_date": "February 31",
            "truncation_checksum": "unknown",
        },
        "clabe": {
            "method": "Independent reduced-product worksheet",
            "prefix": "00299900000000001",
            "weights": [3, 7, 1],
            "reduced_terms": [0, 0, 2, 7, 3, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7],
            "sum": 28,
            "expected_digit": "2",
            "structure_scope": "18 ASCII digits, nondegenerate; no bank/plaza/account registry assertion",
        },
        "pan": {
            "tool": "stdnum.luhn",
            "expected_digits": {"999900001111222": "8", "999900001111": "8"},
            "structure_scope": "13-19 ASCII digits, nondegenerate; no network/BIN/account registry assertion",
        },
        "phone": {
            "method": "Independent bounded format worksheet",
            "pattern_scope": "Optional +52, ten national ASCII digits, spaces or hyphens as separators",
            "structure": "unknown",
            "checksum": "not_applicable",
            "no_numbering_database": True,
        },
        "email": {
            "method": "Address(addr_spec=value) plus ASCII dot-atom and DNS-label worksheet",
            "syntax_scope": "One @, nonempty dot-atom local components, at least two nonempty ASCII DNS labels without boundary hyphens; reserved example.invalid domain",
            "checksum": "not_applicable",
            "delivery": "unknown",
        },
        "limitations": [
            "Known exposed synthetic regression, not blind evaluation",
            "Independent tools have narrower and different semantics; no issuance or ownership check",
            "Fictional construction does not prove a numeric identifier or phone is unassigned",
            "PHONE/EMAIL built-in validation remains unknown; syntax references do not add a production validator",
        ],
        "vectors": [
            {
                "family": family,
                "entity_type": entity,
                "fictional_value": value,
                "stratum": stratum,
                "action": action,
                "validity": dict(zip(("pattern", "structure", "checksum"), states, strict=True)),
            }
            for family, entity, value, stratum, action, states in _IDENTIFIER_CASES
        ],
    }


def generate_identifier_package(
    destination: str | Path, *, seed: int, decision: str | Path, decision_sha256: str
) -> dict[str, Any]:
    """Generate 36 exposed fictional cases; the seed selects templates only.

    Literal references and group assignments precede rendering. Fixed formatted
    examples are authored fixtures, not generated perturbations or blind data.
    """
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Invalid synthetic corpus seed")
    receipt, decision_metadata = read_operational_decision(decision, sha256=decision_sha256)
    families = {
        family: index
        for index, family in enumerate(dict.fromkeys(row[0] for row in _IDENTIFIER_CASES), 1)
    }
    entities = sorted({row[1] for row in _IDENTIFIER_CASES})
    rng = random.Random(seed)
    records: dict[str, Any] = {
        role: []
        for role in (
            "sources",
            "documents",
            "units",
            "mentions",
            "expectations",
            "validation_vectors",
        )
    }
    records.update(
        {
            "generator-a": canonical_json(
                {
                    "version": GENERATOR_VERSION,
                    "license": "Apache-2.0",
                    "attribution": "DeidFlow: original fictional literals and Spanish templates",
                    "inputs": "No real personal source; generic invoice constants explicitly nonpersonal",
                    "seed_algorithm": "python-random-v1: Random(integer seed), random() stream, floor(2*u) template selection",
                    "group_assignment": "Family ids assigned in declaration order before rendering; all memberships known_regression",
                    "reference_table_sha256": hashlib.sha256(
                        canonical_json(_identifier_evidence()["vectors"])
                    ).hexdigest(),
                    "decision_ref": "evidence-9",
                }
            ),
            "evidence-1": canonical_json(_identifier_evidence()),
            "evidence-9": receipt,
        }
    )
    for index, profile in enumerate(_PROFILES, 1):
        records[f"profile-{index:x}"] = {
            "profile_id": profile,
            "ratified": False,
            "clinical_policy": "not_evaluated",
            "quasi_identifier_policy": "not_evaluated",
            "precedence": ["review_required", "remove", "preserve"],
        }
    manifest = _manifest(entities, seed)
    manifest["scope"]["required_strata"] = sorted({row[3] for row in _IDENTIFIER_CASES})
    manifest["scope"]["optional_strata"] = list(families)
    labels = {"PAYMENT_CARD": "tarjeta", "PHONE": "teléfono", "EMAIL": "correo"}
    for index, (family, entity, value, stratum, action, states) in enumerate(_IDENTIFIER_CASES, 1):
        suffix, group = f"{index:x}", f"{families[family]:x}"
        label = labels.get(entity, entity)
        templates = {
            "remove": (
                f"Expediente ficticio; {label}: ",
                f"Registro sintético del titular; {label}: ",
            ),
            "preserve": (
                f"Ejercicio no personal: constante literal {label}: ",
                f"Prueba de software sin titular, constante {label}: ",
            ),
            "review_required": (
                f"Campo sin atribución confirmada, {label}: ",
                f"Origen personal indeterminado, {label}: ",
            ),
        }[action]
        prefix = templates[int(rng.random() * len(templates))]
        start, end = len(prefix), len(prefix) + len(value)
        text = prefix + value + "; fin del caso sintético."
        validity = dict(zip(("pattern", "structure", "checksum"), states, strict=True))
        unit_id, case_id, mention_id = "u-" + suffix, "c-" + suffix, "m-" + suffix
        # Contextually nonpersonal constants have no detection-gold mention.
        sensitive = action != "preserve"
        digest = hashlib.sha256(text.encode()).hexdigest()
        records["units"].append(
            {
                "unit_id": unit_id,
                "case_id": case_id,
                "text": text,
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
                "domain": "general",
                "origin_reference": "generator-a",
                "terms_reference": "generator-a",
                "license": "Apache-2.0",
                "attribution": "DeidFlow: corpus ficticio original",
                "permissions": dict.fromkeys(
                    ("evaluation", "annotation", "derivation", "training", "redistribution"), True
                ),
                "permission_review": {
                    "status": "synthetic_fixture",
                    "evidence_ref": "generator-a",
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
                "case_id": case_id,
                "source_id": "s-" + suffix,
                "root_document_id": case_id,
                "group_id": "g-" + group,
                "template_family_id": "t-" + group,
                "parent_case_id": None,
                "variant_id": None,
                "partition": None,
                "panel": "known_regression",
                "format": "text",
                "strata": [stratum, family],
                "capabilities_required": ["text_detection"],
                "artifact_ref": None,
                "artifact_sha256": None,
                "unit_ids": [unit_id],
                "perturbation_recipe": None,
                "annotation_state": "adjudicated",
            }
        )
        if sensitive:
            records["mentions"].append(
                {
                    "mention_id": mention_id,
                    "unit_id": unit_id,
                    "entity_type": entity,
                    "start": start,
                    "end": end,
                    "region_ref": None,
                    "certainty": "ambiguous" if action == "review_required" else "confirmed",
                    "validity": validity,
                    "sensitivity_reference": "BMX-09-D2-"
                    + (
                        "ambiguous"
                        if action == "review_required"
                        else "attributed-fictional-identifier"
                    ),
                    "entity_id": None,
                    "identity_evidence": None,
                    "annotation_provenance": {
                        "method": "synthetic_fixture",
                        "manual_version": "1.0.0",
                        "reviews": [],
                    },
                }
            )
        records["validation_vectors"].append(
            {
                "vector_id": "v-" + suffix,
                "unit_id": unit_id,
                "entity_type": entity,
                "start": start,
                "end": end,
                "mention_id": mention_id if sensitive else None,
                "sensitivity": "sensitive" if sensitive else "nonpersonal_distractor",
                "validity": validity,
                "provenance": {
                    "method": "independent_worksheet"
                    if entity in {"CLABE", "PHONE", "EMAIL"}
                    else "independent_reference",
                    "version": "mx-identifier-references-1.0.0",
                    "evidence_ref": "evidence-1",
                },
            }
        )
        for profile in _PROFILES:
            records["expectations"].append(
                {
                    "expectation_id": f"e-{len(records['expectations']) + 1:x}",
                    "profile_id": profile,
                    "case_id": case_id,
                    "mention_id": mention_id if sensitive else None,
                    "unit_id": None if sensitive else unit_id,
                    "start": None if sensitive else start,
                    "end": None if sensitive else end,
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
        manifest["annotation_coverage"].append(
            {
                "unit_id": unit_id,
                "exhaustive_entity_types": entities,
                "inspected_ranges": [{"start": 0, "end": len(text)}],
                "limitations": [
                    "Synthetic fixture reference only; no claim of deployment coverage"
                ],
            }
        )
    package = write_package_records(destination, records, manifest)
    support = Counter(row[1] for row in _IDENTIFIER_CASES)
    strata = {
        entity: dict(
            sorted(
                Counter(
                    stratum
                    for row in _IDENTIFIER_CASES
                    if row[1] == entity
                    for stratum in (row[3], row[0])
                ).items()
            )
        )
        for entity in entities
    }
    return {
        "manifest_sha256": package.manifest_sha256,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "documents": len(records["documents"]),
        "groups": len(families),
        "mentions": len(records["mentions"]),
        "vectors": len(records["validation_vectors"]),
        "support_by_entity": dict(sorted(support.items())),
        "support_by_entity_stratum": strata,
        "support_by_family": dict(sorted(Counter(row[0] for row in _IDENTIFIER_CASES).items())),
        "support_by_action": dict(sorted(Counter(row[4] for row in _IDENTIFIER_CASES).items())),
        "decision": decision_metadata,
        "executable_profile_ratified": False,
        "quality_ratified": False,
        "quality": "DESCRIPTIVE_ONLY",
        "panel": "known_regression",
        "limitations": [
            "KNOWN_SYNTHETIC_REGRESSION",
            "NO_BLIND_TEST",
            "NO_ISSUANCE_OR_OWNERSHIP_CHECK",
            "PHONE_EMAIL_BUILTIN_VALIDATION_UNKNOWN",
        ],
    }
