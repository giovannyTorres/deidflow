"""Deterministic textual stress cases with explicit reference maps and lineage."""

from __future__ import annotations

import hashlib
import random
import shutil
import unicodedata
from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ._package_io import (
    MAX_PACKAGE_BYTES,
    MAX_RECORDS,
    MAX_RESOURCE_BYTES,
    is_sha256,
    read_member,
    strict_json,
)
from .evaluation_package import EvaluationPackage, load_evaluation_package
from .package_runner import DetectionCandidate, run_package_benchmark
from .synthetic_package import bounded_canonical_json, write_package_records

DEFAULT_RECIPES = (
    "uppercase.v1",
    "nfd.v1",
    "crlf.v1",
    "separators.v1",
    "ocr_simulated.v1",
    "columns.v1",
    "near_cut.v1",
    "long_low_density.v1",
    "high_density.v1",
)
VERSION = "mx-perturbations-1.0.0"
MAX_SOURCE_CODEPOINTS = 50_000
MAX_SOURCE_UNITS = 512
MAX_REPORT_PAIRS = 512


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identifier(prefix: str, namespace: str, original: str, copy: int = 0) -> str:
    return prefix + "-" + _sha(f"{namespace}:{prefix}:{original}:{copy}".encode())[:32]


def _parts(text: str, recipe: str, *, left: str = "", right: str = "") -> tuple[str, list[int]]:
    if recipe == "uppercase.v1":
        parts = [character.upper() for character in text]
        result = text.upper()
    elif recipe == "nfd.v1":
        parts = [unicodedata.normalize("NFD", character) for character in text]
        result = unicodedata.normalize("NFD", text)
    elif recipe == "crlf.v1":
        parts = [
            "\r\n"
            if (character == "\n" and (text[i - 1] if i else left) != "\r")
            or (character == "\r" and (text[i + 1] if i + 1 < len(text) else right) != "\n")
            else character
            for i, character in enumerate(text)
        ]
        result = "".join(parts)
    elif recipe == "separators.v1":
        parts = ["\t | " if character == " " else character for character in text]
        result = "".join(parts)
    elif recipe == "ocr_simulated.v1":
        confusions = {"O": "0", "o": "0", "I": "1", "l": "1", "S": "5"}
        parts = [confusions.get(character, character) for character in text]
        result = "".join(parts)
    else:
        parts, result = list(text), text
    offsets = [0]
    for part in parts:
        offsets.append(offsets[-1] + len(part))
    return result, offsets


def _validity(validity: dict[str, str], changed: bool) -> dict[str, str]:
    return {
        key: "unknown" if changed and value != "not_applicable" else value
        for key, value in validity.items()
    }


def _merged(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def _edit(text: str, recipe: str, targets: list[tuple[int, int]], first: int, seed: int):
    """Map every input codepoint to output intervals, including duplicated copies."""
    identity = [(i, i + 1) for i in range(len(text))]
    authored: list[tuple[int, int]] = []
    parameters: dict[str, Any] = {}
    if recipe == "columns.v1":
        cuts = [
            i
            for i in range(1, len(text))
            if text[i - 1].isspace() and not any(start < i < end for start, end in targets)
        ]
        if not cuts:
            return text, [identity], authored, {"cut": None}
        cut = min(cuts, key=lambda i: (abs(i - len(text) // 2), i))
        text_out = text[cut:] + text[:cut]
        positions = [len(text) - cut + i if i < cut else i - cut for i in range(len(text))]
        return text_out, [[(i, i + 1) for i in positions]], authored, {"cut": cut}
    if recipe in {"near_cut.v1", "long_low_density.v1"}:
        if recipe == "near_cut.v1":
            boundary = next(
                (n for n in (64, 256, 1024, 4096, 16384, 65536, 262144) if n > first), None
            )
            if boundary is None:
                raise ValueError("Unsupported perturbation cut position")
            wanted = boundary + random.Random(seed).choice((-1, 0, 1))
            prefix, suffix = wanted - first, 0
            parameters = {"boundary": boundary, "target_start": wanted}
        else:
            prefix = suffix = 8192
            parameters = {"prefix_codepoints": prefix, "suffix_codepoints": suffix}
        # Authored, explicitly nonpersonal padding. It carries no hidden oracle.
        neutral = " texto neutro "
        left = (neutral * (prefix // len(neutral) + 1))[:prefix]
        right = (neutral * (suffix // len(neutral) + 1))[:suffix]
        authored = [(0, prefix)] if prefix else []
        if suffix:
            authored.append((prefix + len(text), prefix + len(text) + suffix))
        return (
            left + text + right,
            [[(a + prefix, b + prefix) for a, b in identity]],
            authored,
            parameters,
        )
    if recipe == "high_density.v1":
        output = text
        copied: list[tuple[int, int] | None] = [None] * len(text)
        for start, end in _merged(targets):
            authored.append((len(output), len(output) + 3))
            output += " | "
            offset = len(output)
            for i in range(start, end):
                copied[i] = (offset + i - start, offset + i - start + 1)
            output += text[start:end]
        return output, [identity, copied], authored, {"copies": 2, "selection": "target_union"}
    output, offsets = _parts(text, recipe)
    return output, [[(offsets[i], offsets[i + 1]) for i in range(len(text))]], authored, parameters


def _project(mapping, start: int, end: int) -> tuple[int, int]:
    pieces = mapping[start:end]
    if not pieces or any(piece is None for piece in pieces):
        raise ValueError("Unrepresentable perturbation reference boundary")
    if any(left[1] != right[0] for left, right in zip(pieces[:-1], pieces[1:], strict=True)):
        raise ValueError("Unrepresentable perturbation reference boundary")
    return pieces[0][0], pieces[-1][1]


def _density(units, mentions) -> dict[str, int | float]:
    characters = sum(len(u["text"]) for u in units)
    covered = sum(
        sum(
            end - start
            for start, end in _merged(
                [(m["start"], m["end"]) for m in mentions if m["unit_id"] == u["unit_id"]]
            )
        )
        for u in units
    )
    return {
        "units": len(units),
        "codepoints": characters,
        "mentions": len(mentions),
        "mentions_per_1000_codepoints": 1000 * len(mentions) / characters if characters else 0,
        "annotated_codepoint_fraction": covered / characters if characters else 0,
    }


def _derive(package: EvaluationPackage, recipe: str, seed: int) -> tuple[Any, Any, Any]:
    originals = package.records
    records, manifest = deepcopy(originals), deepcopy(package.manifest)
    namespace = f"{package.manifest_sha256}:{recipe}:{seed}"
    copies = 2 if recipe == "high_density.v1" else 1
    case_ids = {
        r["case_id"]: _identifier("c", namespace, r["case_id"]) for r in originals["documents"]
    }
    unit_ids = {r["unit_id"]: _identifier("u", namespace, r["unit_id"]) for r in originals["units"]}
    mention_ids = {
        (r["mention_id"], copy): _identifier("m", namespace, r["mention_id"], copy)
        for copy in range(copies)
        for r in originals["mentions"]
    }
    old_units = {r["unit_id"]: r["text"] for r in originals["units"]}
    maps, new_units, edit_parameters, authored = {}, {}, {}, {}
    for original in originals["units"]:
        key = original["unit_id"]
        targets = [
            (r["start"], r["end"])
            for role in ("mentions", "validation_vectors")
            for r in originals.get(role, [])
            if r["unit_id"] == key
        ]
        targets += [
            (r["start"], r["end"]) for r in originals["expectations"] if r["unit_id"] == key
        ]
        first = min((r["start"] for r in originals["mentions"] if r["unit_id"] == key), default=0)
        text, mappings, padding, parameters = _edit(original["text"], recipe, targets, first, seed)
        maps[key], new_units[key], edit_parameters[key], authored[key] = (
            mappings,
            text,
            parameters,
            padding,
        )
        row = deepcopy(original)
        row.update(
            unit_id=unit_ids[key],
            case_id=case_ids[row["case_id"]],
            text=text,
            text_sha256=_sha(text.encode()),
        )
        records["units"].append(row)

    def project(original, copy):
        key = original["unit_id"]
        start, end = _project(maps[key][copy], original["start"], original["end"])
        before = old_units[key][original["start"] : original["end"]]
        after = new_units[key][start:end]
        if (
            after
            != _parts(
                before,
                recipe,
                left=old_units[key][max(0, original["start"] - 1) : original["start"]],
                right=old_units[key][original["end"] : original["end"] + 1],
            )[0]
        ):
            raise ValueError("Unrepresentable perturbation reference boundary")
        return start, end, before != after

    strata = {"perturbation:" + recipe}
    for original in originals["documents"]:
        row = deepcopy(original)
        source_id = _identifier("s", namespace, row["case_id"])
        child_strata = ["perturbation:" + recipe] + [
            "perturbation:" + recipe + ":" + s for s in row["strata"]
        ]
        strata.update(child_strata)
        row.update(
            case_id=case_ids[row["case_id"]],
            source_id=source_id,
            parent_case_id=original["case_id"],
            annotation_state="draft",
            variant_id=_identifier("v", namespace, original["case_id"]),
            unit_ids=[unit_ids[key] for key in original["unit_ids"]],
            strata=list(dict.fromkeys(original["strata"] + child_strata)),
            perturbation_recipe={
                "version": "1.0.0",
                "operation": recipe,
                "seed": seed,
                "parameters": {unit_ids[k]: edit_parameters[k] for k in original["unit_ids"]},
            },
        )
        records["documents"].append(row)
        source = deepcopy(
            next(s for s in originals["sources"] if s["source_id"] == original["source_id"])
        )
        units = sorted(
            (u for u in records["units"] if u["case_id"] == row["case_id"]),
            key=lambda u: u["unit_id"],
        )
        framed = hashlib.sha256()
        for unit in units:
            name, text = unit["unit_id"].encode(), unit["text"].encode()
            framed.update(len(name).to_bytes(8, "big") + name)
            framed.update(len(text).to_bytes(8, "big") + text)
        source.update(
            source_id=source_id,
            content_sha256=units[0]["text_sha256"] if len(units) == 1 else framed.hexdigest(),
        )
        records["sources"].append(source)
    for copy in range(copies):
        for original in originals["mentions"]:
            row = deepcopy(original)
            start, end, changed = project(original, copy)
            row.update(
                mention_id=mention_ids[row["mention_id"], copy],
                unit_id=unit_ids[row["unit_id"]],
                start=start,
                end=end,
                validity=_validity(row["validity"], changed),
            )
            row["annotation_provenance"].update(method="synthetic_fixture", reviews=[])
            if row["identity_evidence"] is not None:
                row["identity_evidence"]["mention_ids"] = [
                    mention_ids[key, copy] for key in row["identity_evidence"]["mention_ids"]
                ]
            records["mentions"].append(row)
        for original in originals["expectations"]:
            row = deepcopy(original)
            row.update(
                expectation_id=_identifier("e", namespace, row["expectation_id"], copy),
                case_id=case_ids[row["case_id"]],
            )
            if row["mention_id"] is not None:
                row["mention_id"] = mention_ids[row["mention_id"], copy]
            else:
                start, end, _ = project(original, copy)
                row.update(unit_id=unit_ids[row["unit_id"]], start=start, end=end)
            records["expectations"].append(row)
    evidence_role = _identifier("evidence", namespace, recipe)
    vector_derivations = []
    for copy in range(copies):
        for original in originals.get("validation_vectors", []):
            row = deepcopy(original)
            start, end, changed = project(original, copy)
            row.update(
                vector_id=_identifier("v", namespace, row["vector_id"], copy),
                unit_id=unit_ids[row["unit_id"]],
                start=start,
                end=end,
                validity=_validity(row["validity"], changed),
                mention_id=mention_ids[row["mention_id"], copy] if row["mention_id"] else None,
                provenance={
                    "method": "synthetic_derivation",
                    "version": VERSION,
                    "evidence_ref": evidence_role,
                },
            )
            vector_derivations.append(
                {"vector_id": row["vector_id"], "parent_vector_id": original["vector_id"]}
            )
            records["validation_vectors"].append(row)
    for original in package.manifest["annotation_coverage"]:
        row = deepcopy(original)
        row["unit_id"] = unit_ids[original["unit_id"]]
        ranges = list(authored[original["unit_id"]])
        for mapping in maps[original["unit_id"]]:
            for region in original["inspected_ranges"]:
                if recipe == "nfd.v1" and region["start"] < region["end"]:
                    start, end = _project(mapping, region["start"], region["end"])
                    before = old_units[original["unit_id"]][region["start"] : region["end"]]
                    if new_units[original["unit_id"]][start:end] != unicodedata.normalize(
                        "NFD", before
                    ):
                        raise ValueError("Unrepresentable perturbation reference boundary")
                ranges.extend(
                    piece for piece in mapping[region["start"] : region["end"]] if piece is not None
                )
        row["inspected_ranges"] = [{"start": start, "end": end} for start, end in _merged(ranges)]
        if not new_units[original["unit_id"]]:
            row["inspected_ranges"] = [{"start": 0, "end": 0}]
        row["limitations"] = list(
            dict.fromkeys(row["limitations"] + ["SYNTHETIC_DERIVATION_NOT_REVIEWED"])
        )
        manifest["annotation_coverage"].append(row)
    declared = set(manifest["scope"]["required_strata"] + manifest["scope"]["optional_strata"])
    manifest["scope"]["optional_strata"].extend(sorted(strata - declared))
    records[evidence_role] = bounded_canonical_json(
        {
            "schema_version": "df-eval-mx.synthetic-derivation.v1",
            "version": VERSION,
            "source_manifest_sha256": package.manifest_sha256,
            "recipe": recipe,
            "seed": seed,
            "codepoint_boundaries": maps,
            "vector_derivations": vector_derivations,
        },
        MAX_RESOURCE_BYTES,
    )
    manifest["generation"]["perturbation_rules"].append(evidence_role)
    manifest["generation"]["generator_version"] = VERSION
    if recipe == "near_cut.v1":
        manifest["generation"]["random_algorithm"] = "python-random-v1"
        manifest["generation"]["seeds"]["perturbation"] = seed
    manifest["freeze"] = {
        "status": "unfrozen",
        "frozen_at": None,
        "resource_sha256": {},
        "exposure": "known_regression",
        "custody": None,
    }
    return (
        records,
        manifest,
        {
            "changed_units": sum(old_units[key] != text for key, text in new_units.items()),
            "clean_density": _density(originals["units"], originals["mentions"]),
            "perturbed_density": _density(
                records["units"][len(originals["units"]) :],
                records["mentions"][len(originals["mentions"]) :],
            ),
            "strata": sorted({s for row in originals["documents"] for s in row["strata"]}),
        },
    )


def generate_perturbation_suite(
    source: str | Path,
    *,
    manifest_sha256: str,
    destination: str | Path,
    seed: int,
    recipes: tuple[str, ...] = DEFAULT_RECIPES,
) -> dict[str, Any]:
    """Retain exact originals in one admitted package per declared text recipe."""
    package = load_evaluation_package(source, manifest_sha256=manifest_sha256)
    if (
        type(seed) is not int
        or not 0 <= seed < 2**64
        or not isinstance(recipes, tuple)
        or not recipes
        or any(type(recipe) is not str for recipe in recipes)
        or len(set(recipes)) != len(recipes)
        or any(recipe not in DEFAULT_RECIPES for recipe in recipes)
        or sum(len(row["text"]) for row in package.records["units"]) > MAX_SOURCE_CODEPOINTS
        or len(package.records["units"]) > MAX_SOURCE_UNITS
        or any(
            len(package.records.get(role, [])) * (3 if "high_density.v1" in recipes else 2)
            > MAX_RECORDS
            for role in ("mentions", "expectations", "validation_vectors")
        )
        or set(package.manifest["scope"]["formats"]) != {"text"}
        or any(
            stratum.startswith("perturbation:")
            for row in package.records["documents"]
            for stratum in row["strata"]
        )
        or any(
            row["panel"] != "known_regression" or row["format"] != "text"
            for row in package.records["documents"]
        )
    ):
        raise ValueError("Unsupported textual perturbation configuration")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise ValueError("Perturbation destination already exists")
    if Path(source).is_dir() and target.resolve().is_relative_to(Path(source).resolve()):
        raise ValueError("Perturbation destination overlaps source")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".deidflow-perturbation-", dir=target.parent) as temp:
            staging = Path(temp)
            entries = []
            unique = {r["case_id"]: r for r in package.records["documents"]}
            for recipe in recipes:
                records, manifest, statistics = _derive(package, recipe, seed)
                relative = recipe.replace(".", "-")
                admitted = write_package_records(staging / relative, records, manifest)
                unique.update({row["case_id"]: row for row in records["documents"]})
                entries.append(
                    {
                        "recipe": recipe,
                        "path": relative,
                        "manifest_sha256": admitted.manifest_sha256,
                        **statistics,
                    }
                )
            counts = Counter(row["root_document_id"] for row in unique.values())
            index = {
                "schema_version": "df-eval-mx.perturbation-suite.v1",
                "generator_version": VERSION,
                "source_manifest_sha256": manifest_sha256,
                "seed": seed,
                "packages": entries,
                "unique_cases": len(unique),
                "serialized_cases": sum(len(package.records["documents"]) * 2 for _ in recipes),
                "case_weights": [
                    {
                        "case_id": key,
                        "root_document_id": row["root_document_id"],
                        "weight": 1 / counts[row["root_document_id"]],
                    }
                    for key, row in sorted(unique.items())
                ],
                "quality": "DESCRIPTIVE_ONLY",
            }
            payload = bounded_canonical_json(index, MAX_RESOURCE_BYTES)
            (staging / "suite.json").write_bytes(payload)
            # Exclusive reservation protects existing destinations. The index is
            # published last; cleanup is confined to the directory we created.
            target.mkdir()
            try:
                for entry in entries:
                    (staging / entry["path"]).rename(target / entry["path"])
                (staging / "suite.json").rename(target / "suite.json")
            except OSError:
                shutil.rmtree(target)
                raise
        return {**index, "index_sha256": _sha(payload)}
    except (OSError, TypeError, KeyError, OverflowError):
        raise ValueError("Invalid perturbation suite output") from None


def _admit_suite(source: EvaluationPackage, suite: Path, digest: str):
    if any(
        s.startswith("perturbation:") for row in source.records["documents"] for s in row["strata"]
    ):
        raise ValueError
    payload = read_member(suite.resolve(), "suite.json", MAX_RESOURCE_BYTES)
    if not is_sha256(digest) or _sha(payload) != digest:
        raise ValueError
    index = strict_json(payload)
    fields = {
        "schema_version",
        "generator_version",
        "source_manifest_sha256",
        "seed",
        "packages",
        "unique_cases",
        "serialized_cases",
        "case_weights",
        "quality",
    }
    if (
        not isinstance(index, dict)
        or set(index) != fields
        or index["schema_version"] != "df-eval-mx.perturbation-suite.v1"
        or index["generator_version"] != VERSION
        or index["source_manifest_sha256"] != source.manifest_sha256
        or type(index["seed"]) is not int
        or not 0 <= index["seed"] < 2**64
        or index["quality"] != "DESCRIPTIVE_ONLY"
        or not isinstance(index["packages"], list)
        or not 1 <= len(index["packages"]) <= len(DEFAULT_RECIPES)
    ):
        raise ValueError
    original_cases = {r["case_id"]: r for r in source.records["documents"]}
    unique = dict(original_cases)
    serialized = 0
    seen = set()
    strata = sorted({s for r in original_cases.values() for s in r["strata"]})
    for entry in index["packages"]:
        if (
            not isinstance(entry, dict)
            or set(entry)
            != {
                "recipe",
                "path",
                "manifest_sha256",
                "changed_units",
                "clean_density",
                "perturbed_density",
                "strata",
            }
            or type(entry["recipe"]) is not str
            or entry["recipe"] not in DEFAULT_RECIPES
            or entry["recipe"] in seen
            or entry["path"] != entry["recipe"].replace(".", "-")
            or entry["strata"] != strata
        ):
            raise ValueError
        seen.add(entry["recipe"])
        loaded = load_evaluation_package(
            suite / entry["path"], manifest_sha256=entry["manifest_sha256"]
        )
        for role, value in source.records.items():
            derived = loaded.records[role]
            if isinstance(value, list):
                if derived[: len(value)] != value:
                    raise ValueError
            elif derived != value:
                raise ValueError
        children = loaded.records["documents"][len(original_cases) :]
        if len(children) != len(original_cases) or {r["parent_case_id"] for r in children} != set(
            original_cases
        ):
            raise ValueError
        for child in children:
            parent = original_cases[child["parent_case_id"]]
            expected_strata = list(
                dict.fromkeys(
                    parent["strata"]
                    + ["perturbation:" + entry["recipe"]]
                    + [
                        "perturbation:" + entry["recipe"] + ":" + stratum
                        for stratum in parent["strata"]
                    ]
                )
            )
            if (
                any(
                    child[key] != parent[key]
                    for key in (
                        "root_document_id",
                        "group_id",
                        "template_family_id",
                        "partition",
                        "panel",
                    )
                )
                or child["perturbation_recipe"]["operation"] != entry["recipe"]
                or child["perturbation_recipe"]["seed"] != index["seed"]
                or child["strata"] != expected_strata
            ):
                raise ValueError
        new_units = loaded.records["units"][len(source.records["units"]) :]
        new_mentions = loaded.records["mentions"][len(source.records["mentions"]) :]
        if (
            entry["clean_density"] != _density(source.records["units"], source.records["mentions"])
            or entry["perturbed_density"] != _density(new_units, new_mentions)
            or type(entry["changed_units"]) is not int
            or entry["changed_units"]
            != sum(
                a["text"] != b["text"]
                for a, b in zip(source.records["units"], new_units, strict=True)
            )
        ):
            raise ValueError
        unique.update({r["case_id"]: r for r in children})
        serialized += len(loaded.records["documents"])
    if sum(1 + len(entry["strata"]) for entry in index["packages"]) > MAX_REPORT_PAIRS:
        raise ValueError
    counts = Counter(r["root_document_id"] for r in unique.values())
    weights = [
        {
            "case_id": key,
            "root_document_id": row["root_document_id"],
            "weight": 1 / counts[row["root_document_id"]],
        }
        for key, row in sorted(unique.items())
    ]
    if (
        index["unique_cases"] != len(unique)
        or index["serialized_cases"] != serialized
        or index["case_weights"] != weights
    ):
        raise ValueError
    return index


def run_perturbation_suite(
    source: str | Path,
    *,
    manifest_sha256: str,
    suite: str | Path,
    index_sha256: str,
    candidate: str | DetectionCandidate,
    profile: str,
    output: str | Path,
) -> dict[str, Any]:
    """Admit every package before executing real, separate detection reports.

    Each recipe has an all-cases pair and a pair per original stratum. These
    strata can overlap. Root weights are accounting metadata, never pooled F1.
    """
    try:
        original = load_evaluation_package(source, manifest_sha256=manifest_sha256)
        index = _admit_suite(original, Path(suite), index_sha256)
        target = Path(output)
        if (
            target.exists()
            or target.is_symlink()
            or target.resolve().is_relative_to(Path(suite).resolve())
            or (Path(source).is_dir() and target.resolve().is_relative_to(Path(source).resolve()))
        ):
            raise ValueError
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(
            prefix=".deidflow-perturbation-reports-", dir=target.parent
        ) as temp:
            staging = Path(temp)
            results: list[dict[str, Any]] = []
            report = {
                "schema_version": "df-eval-mx.perturbation-report.v1",
                "suite_index_sha256": index_sha256,
                "source_manifest_sha256": manifest_sha256,
                "serialized_cases": index["serialized_cases"],
                "unique_cases": index["unique_cases"],
                "case_weights": index["case_weights"],
                "results": results,
                "quality": "DESCRIPTIVE_ONLY",
                "limitations": [
                    "KNOWN_REGRESSION_ONLY",
                    "SIMULATED_TEXT_NOT_OCR",
                    "DERIVED_REFERENCE_NOT_REVIEWED",
                    "STRATA_CAN_OVERLAP",
                    "NO_POOLED_METRICS_OR_BOOTSTRAP",
                    "ROOT_WEIGHTS_ARE_ACCOUNTING_ONLY",
                ],
            }
            encoded_bytes = len(bounded_canonical_json(report, MAX_PACKAGE_BYTES))
            for entry in index["packages"]:
                for number, stratum in enumerate([None, *entry["strata"]]):
                    base = entry["path"] + "/" + ("all" if stratum is None else f"stratum-{number}")
                    clean = run_package_benchmark(
                        source,
                        manifest_sha256=manifest_sha256,
                        candidate=candidate,
                        profile=profile,
                        output=staging / base / "clean",
                        strata=None if stratum is None else (stratum,),
                    )
                    perturbed_stratum = "perturbation:" + entry["recipe"]
                    if stratum is not None:
                        perturbed_stratum += ":" + stratum
                    perturbed = run_package_benchmark(
                        Path(suite) / entry["path"],
                        manifest_sha256=entry["manifest_sha256"],
                        candidate=candidate,
                        profile=profile,
                        output=staging / base / "perturbed",
                        strata=(perturbed_stratum,),
                    )
                    pair = {
                        "recipe": entry["recipe"],
                        "stratum": stratum,
                        "clean_report": base + "/clean/report.json",
                        "perturbed_report": base + "/perturbed/report.json",
                        "clean": clean["result"],
                        "perturbed": perturbed["result"],
                    }
                    comma = int(bool(results))
                    encoded_pair = bounded_canonical_json(
                        pair, MAX_PACKAGE_BYTES - encoded_bytes - comma
                    )
                    encoded_bytes += len(encoded_pair) + comma
                    results.append(pair)
            report_payload = bounded_canonical_json(report, MAX_PACKAGE_BYTES)
            (staging / "report.json").write_bytes(report_payload)
            target.mkdir()
            try:
                for entry in index["packages"]:
                    (staging / entry["path"]).rename(target / entry["path"])
                (staging / "report.json").rename(target / "report.json")
            except OSError:
                shutil.rmtree(target)
                raise
        return report
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("Invalid perturbation suite evaluation") from None
