"""Independent source-bound admission of the two Unicode development recipes.

This verifier deliberately does not import the generator or its edit helpers.
Transport hashes and structurally consistent maps alone cannot prove a recipe.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from itertools import accumulate
from typing import Any

from ._package_io import strict_json
from .evaluation_package import EvaluationPackage


def _same(actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ValueError


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _id(namespace: str, prefix: str, parent: str) -> str:
    return prefix + "-" + _sha(f"{namespace}:{prefix}:{parent}:0".encode())[:32]


def _reference_edit(source: EvaluationPackage, unit: dict[str, Any], recipe: str, seed: int):
    text, key = unit["text"], unit["unit_id"]
    events = [0] * (len(text) + 1)
    endpoints: set[int] = set()
    for role in ("mentions", "validation_vectors", "expectations"):
        for row in source.records.get(role, []):
            if row["unit_id"] != key:
                continue
            endpoints.update((row["start"], row["end"]))
            if role == "mentions" and row["entity_type"] in {
                "PERSON",
                "ADDRESS",
                "EMAIL",
                "PHONE",
                "RFC",
                "CURP",
                "CLABE",
                "PAYMENT_CARD",
            }:
                events[row["start"]] += 1
                events[row["end"]] -= 1
    for row in source.manifest["annotation_coverage"]:
        if row["unit_id"] == key:
            for region in row["inspected_ranges"]:
                endpoints.update((region["start"], region["end"]))
    active = list(accumulate(events))
    parts, boundaries, changed = [], [0], 0
    for position, character in enumerate(text):
        result = character
        if active[position] and recipe == "fullwidth.v1" and 33 <= ord(character) <= 126:
            result = chr(ord(character) + 65248)
        boundary = position + 1
        if (
            recipe == "format_chars.v1"
            and boundary < len(text)
            and active[position]
            and active[boundary]
            and boundary not in endpoints
            and character.isalnum()
            and text[boundary].isalnum()
        ):
            result += chr((0xAD, 0x200B, 0x200D, 0x2060, 0xFEFF)[(seed + boundary) % 5])
        changed += result != character
        parts.append(result)
        boundaries.append(boundaries[-1] + len(result))
    return (
        "".join(parts),
        boundaries,
        {
            "selection": "direct_identifier_mentions.v1",
            "algorithm": "seed_plus_boundary_mod5.v1"
            if recipe == "format_chars.v1"
            else "ascii_graphics_to_fullwidth.v1",
            "changed_codepoints": changed,
        },
    )


def verify_unicode_derivation(
    source: EvaluationPackage, derived: EvaluationPackage, recipe: str, seed: int, version: str
) -> None:
    """Reject coherent repinning of text, maps, gold, lineage or recipe claims."""
    if (
        len(source.records["units"]) > 512
        or sum(len(u["text"]) for u in source.records["units"]) > 50_000
    ):
        raise ValueError
    namespace = f"{source.manifest_sha256}:{recipe}:{seed}"
    original, child = source.records, derived.records
    evidence_id = _id(namespace, "evidence", recipe)
    _same(set(child), set(original) | {evidence_id})
    identifiers = {
        role: {row[field]: _id(namespace, prefix, row[field]) for row in original.get(role, [])}
        for role, field, prefix in (
            ("documents", "case_id", "c"),
            ("units", "unit_id", "u"),
            ("mentions", "mention_id", "m"),
            ("expectations", "expectation_id", "e"),
            ("validation_vectors", "vector_id", "v"),
        )
    }
    edits = {
        unit["unit_id"]: _reference_edit(source, unit, recipe, seed) for unit in original["units"]
    }
    old_units = {unit["unit_id"]: unit for unit in original["units"]}

    def projected(row):
        text, offsets, _ = edits[row["unit_id"]]
        start, end = offsets[row["start"]], offsets[row["end"]]
        changed = old_units[row["unit_id"]]["text"][row["start"] : row["end"]] != text[start:end]
        return start, end, changed

    expected: dict[str, list[dict[str, Any]]] = {}
    expected["units"] = []
    for row in original["units"]:
        copied = deepcopy(row)
        text = edits[row["unit_id"]][0]
        copied.update(
            unit_id=identifiers["units"][row["unit_id"]],
            case_id=identifiers["documents"][row["case_id"]],
            text=text,
            text_sha256=_sha(text.encode()),
        )
        expected["units"].append(copied)
    expected["documents"], expected["sources"] = [], []
    for row in original["documents"]:
        copied = deepcopy(row)
        strata = ["perturbation:" + recipe] + [
            "perturbation:" + recipe + ":" + s for s in row["strata"]
        ]
        source_id = _id(namespace, "s", row["case_id"])
        copied.update(
            case_id=identifiers["documents"][row["case_id"]],
            source_id=source_id,
            parent_case_id=row["case_id"],
            annotation_state="draft",
            variant_id=_id(namespace, "v", row["case_id"]),
            unit_ids=[identifiers["units"][key] for key in row["unit_ids"]],
            strata=list(dict.fromkeys(row["strata"] + strata)),
            perturbation_recipe={
                "version": "1.0.0",
                "operation": recipe,
                "seed": seed,
                "parameters": {identifiers["units"][key]: edits[key][2] for key in row["unit_ids"]},
            },
        )
        expected["documents"].append(copied)
        units = sorted(
            (u for u in expected["units"] if u["case_id"] == copied["case_id"]),
            key=lambda u: u["unit_id"],
        )
        framed = hashlib.sha256()
        for unit in units:
            for value in (unit["unit_id"].encode(), unit["text"].encode()):
                framed.update(len(value).to_bytes(8, "big") + value)
        origin = deepcopy(
            next(s for s in original["sources"] if s["source_id"] == row["source_id"])
        )
        origin.update(
            source_id=source_id,
            content_sha256=units[0]["text_sha256"] if len(units) == 1 else framed.hexdigest(),
        )
        expected["sources"].append(origin)
    for role, field in (
        ("mentions", "mention_id"),
        ("validation_vectors", "vector_id"),
        ("expectations", "expectation_id"),
    ):
        if role not in original:
            continue
        expected[role] = []
        for row in original[role]:
            copied = deepcopy(row)
            copied[field] = identifiers[role][row[field]]
            if role != "expectations" or row["mention_id"] is None:
                start, end, changed = projected(row)
                copied.update(unit_id=identifiers["units"][row["unit_id"]], start=start, end=end)
                if role != "expectations":
                    copied["validity"] = {
                        key: "unknown" if changed and value != "not_applicable" else value
                        for key, value in row["validity"].items()
                    }
            if role == "mentions":
                copied["annotation_provenance"].update(method="synthetic_fixture", reviews=[])
                if copied["identity_evidence"] is not None:
                    copied["identity_evidence"]["mention_ids"] = [
                        identifiers["mentions"][key]
                        for key in row["identity_evidence"]["mention_ids"]
                    ]
            else:
                copied["mention_id"] = (
                    identifiers["mentions"][row["mention_id"]] if row["mention_id"] else None
                )
                if role == "expectations":
                    copied["case_id"] = identifiers["documents"][row["case_id"]]
                else:
                    copied["provenance"] = {
                        "method": "synthetic_derivation",
                        "version": version,
                        "evidence_ref": evidence_id,
                    }
            expected[role].append(copied)
    for role, additions in expected.items():
        _same(child[role], original[role] + additions)
    generation = deepcopy(source.manifest["generation"])
    generation["generator_version"] = version
    generation["perturbation_rules"].append(evidence_id)
    _same(derived.manifest["generation"], generation)
    _same(
        derived.manifest["freeze"],
        {
            "status": "unfrozen",
            "frozen_at": None,
            "resource_sha256": {},
            "exposure": "known_regression",
            "custody": None,
        },
    )
    for field in (
        "schema_version",
        "dataset_version",
        "taxonomy_version",
        "annotation_version",
        "dataset_id",
        "created_at",
        "profiles",
    ):
        _same(derived.manifest[field], source.manifest[field])
    _same(
        strict_json(child[evidence_id]),
        {
            "schema_version": "df-eval-mx.synthetic-derivation.v1",
            "version": version,
            "source_manifest_sha256": source.manifest_sha256,
            "recipe": recipe,
            "seed": seed,
            "codepoint_boundaries": {
                key: [[[a, b] for a, b in zip(offsets[:-1], offsets[1:], strict=True)]]
                for key, (_, offsets, _) in edits.items()
            },
            "vector_derivations": [
                {
                    "vector_id": identifiers["validation_vectors"][v["vector_id"]],
                    "parent_vector_id": v["vector_id"],
                }
                for v in original.get("validation_vectors", [])
            ],
        },
    )
    coverage = deepcopy(source.manifest["annotation_coverage"])
    for row in source.manifest["annotation_coverage"]:
        copied = deepcopy(row)
        copied["unit_id"] = identifiers["units"][row["unit_id"]]
        offsets = edits[row["unit_id"]][1]
        ranges: list[dict[str, int]] = []
        for region in sorted(row["inspected_ranges"], key=lambda r: (r["start"], r["end"])):
            start, end = offsets[region["start"]], offsets[region["end"]]
            if ranges and start <= ranges[-1]["end"]:
                ranges[-1]["end"] = max(ranges[-1]["end"], end)
            else:
                ranges.append({"start": start, "end": end})
        copied["inspected_ranges"] = ranges
        copied["limitations"] = list(
            dict.fromkeys(row["limitations"] + ["SYNTHETIC_DERIVATION_NOT_REVIEWED"])
        )
        coverage.append(copied)
    _same(derived.manifest["annotation_coverage"], coverage)
