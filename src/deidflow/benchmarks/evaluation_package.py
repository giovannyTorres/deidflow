"""Admission of local, versioned benchmark packages."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import groupby
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from deidflow.core import EntityType

from ._package_io import (
    MAX_MANIFEST_BYTES,
    MAX_PACKAGE_BYTES,
    MAX_RECORDS,
    MAX_RESOURCE_BYTES,
    MAX_RESOURCES,
    PackageReader,
    is_sha256,
    strict_json,
)


class InvalidPackageError(ValueError):
    """Invalid data never produces a favorable evaluation or an input echo."""

    status = "INVALID_RUN"

    def __init__(self) -> None:
        super().__init__("Invalid evaluation package")


@dataclass(frozen=True)
class EvaluationPackage:
    manifest_sha256: str
    manifest: dict[str, Any]
    records: dict[str, Any]


@dataclass(frozen=True)
class _Indexes:
    sources: dict[str, dict[str, Any]]
    documents: dict[str, dict[str, Any]]
    units: dict[str, dict[str, Any]]
    mentions: dict[str, dict[str, Any]]
    profiles: dict[str, dict[str, Any]]
    expectations: dict[str, dict[str, Any]]


def _object(value: Any, fields: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ValueError
    return value


def _identifier(value: Any, prefix: str) -> bool:
    return isinstance(value, str) and re.fullmatch(prefix + r"-[0-9a-f]{1,32}", value) is not None


def _version(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", value) is not None
    )


def _utc(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 40:
        return False
    parsed = datetime.fromisoformat(value)
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _strings(value: Any, allowed: set[str] | None = None) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and 0 < len(item) <= 128 for item in value)
        and len(set(value)) == len(value)
        and (allowed is None or set(value) <= allowed)
    )


def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 4096


def _indexed(value: Any, key: str, prefix: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError
    result: dict[str, dict[str, Any]] = {}
    for row in value:
        if not isinstance(row, dict) or not _identifier(row.get(key), prefix) or row[key] in result:
            raise ValueError
        result[row[key]] = row
    return result


def _source_contracts(value: Any) -> dict[str, dict[str, Any]]:
    sources = _indexed(value, "source_id", "s")
    if not sources:
        raise ValueError
    for source in sources.values():
        _object(
            source,
            "source_id revision content_sha256 origin_kind language country domain origin_reference terms_reference license attribution permissions permission_review personal_data_status exposure",
        )
        if (
            not _version(source["revision"])
            or not is_sha256(source["content_sha256"])
            or source["origin_kind"]
            not in {"synthetic", "licensed_public_nonpersonal", "external_transfer"}
            or not _text(source["language"])
            or not isinstance(source["country"], str)
            or re.fullmatch(r"[A-Z]{2}", source["country"]) is None
            or not _text(source["domain"])
            or not _text(source["license"])
            or source["license"].strip().lower() in {"unknown", "uncertain"}
            or not _text(source["attribution"])
            or any(
                source[name] is not None and not _text(source[name])
                for name in ("origin_reference", "terms_reference")
            )
        ):
            raise ValueError
        permissions = _object(
            source["permissions"], "evaluation annotation derivation training redistribution"
        )
        review = _object(source["permission_review"], "status evidence_ref")
        exposure = _object(
            source["exposure"], "training tuning prior_evaluation candidate_exposure"
        )
        if (
            any(type(item) is not bool for item in permissions.values())
            or permissions["evaluation"] is not True
            or review["status"] not in {"synthetic_fixture", "approved"}
            or any(
                type(exposure[key]) is not bool and exposure[key] != "unknown"
                for key in ("training", "tuning", "prior_evaluation")
            )
            or exposure["candidate_exposure"] not in {"known", "unknown", "unexposed"}
            or (
                source["origin_kind"] == "synthetic"
                and source["personal_data_status"] != "fictional"
            )
            or (
                source["origin_kind"] != "synthetic"
                and (
                    source["personal_data_status"] != "verified_nonpersonal"
                    or review["status"] != "approved"
                    or not _text(review["evidence_ref"])
                    or not _text(source["terms_reference"])
                )
            )
        ):
            raise ValueError
    return sources


def _document_contracts(value: Any, scope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    documents = _indexed(value, "case_id", "c")
    if not documents:
        raise ValueError
    for document in documents.values():
        _object(
            document,
            "case_id source_id root_document_id group_id template_family_id parent_case_id variant_id partition panel format strata capabilities_required artifact_ref artifact_sha256 unit_ids perturbation_recipe annotation_state",
        )
        if (
            any(
                not _identifier(document[key], prefix)
                for key, prefix in (
                    ("source_id", "s"),
                    ("root_document_id", "c"),
                    ("group_id", "g"),
                    ("template_family_id", "t"),
                )
            )
            or (
                document["parent_case_id"] is not None
                and not _identifier(document["parent_case_id"], "c")
            )
            or (document["variant_id"] is not None and not _identifier(document["variant_id"], "v"))
            or document["partition"]
            not in {None, "train", "validation", "calibration", "blind_test"}
            or document["panel"] not in {None, "known_regression", "external_transfer"}
            or (document["partition"] is None) == (document["panel"] is None)
            or document["format"] not in scope["formats"]
            or not _strings(
                document["strata"], set(scope["required_strata"] + scope["optional_strata"])
            )
            or not _strings(document["capabilities_required"])
            or not _strings(document["unit_ids"])
            or not document["unit_ids"]
            or any(not _identifier(item, "u") for item in document["unit_ids"])
            or document["annotation_state"] not in {"adjudicated", "draft", "unresolvable"}
        ):
            raise ValueError
        if document["format"] == "text":
            if document["artifact_ref"] is not None or document["artifact_sha256"] is not None:
                raise ValueError
        elif not _text(document["artifact_ref"]) or not is_sha256(document["artifact_sha256"]):
            raise ValueError
        recipe = document["perturbation_recipe"]
        if document["parent_case_id"] is None:
            if document["variant_id"] is not None or recipe is not None:
                raise ValueError
        else:
            recipe = _object(recipe, "version operation seed parameters")
            if (
                document["variant_id"] is None
                or not _version(recipe["version"])
                or not _text(recipe["operation"])
                or type(recipe["seed"]) is not int
                or not 0 <= recipe["seed"] < 2**64
                or not isinstance(recipe["parameters"], dict)
            ):
                raise ValueError
    return documents


def _unit_contracts(value: Any) -> dict[str, dict[str, Any]]:
    units = _indexed(value, "unit_id", "u")
    if not units:
        raise ValueError
    for unit in units.values():
        _object(unit, "unit_id case_id text text_sha256 content_role locator")
        locator = _object(unit["locator"], "kind index")
        if (
            not _identifier(unit["case_id"], "c")
            or not isinstance(unit["text"], str)
            or not is_sha256(unit["text_sha256"])
            or hashlib.sha256(unit["text"].encode("utf-8")).hexdigest() != unit["text_sha256"]
            or unit["content_role"] not in {"body", "header", "footer", "subject", "reference_text"}
            or locator["kind"] != "text"
            or type(locator["index"]) is not int
            or locator["index"] < 0
        ):
            raise ValueError
    return units


def _interval(start: Any, end: Any, text: str) -> bool:
    return type(start) is int and type(end) is int and 0 <= start < end <= len(text)


def _mention_contracts(
    value: Any, units: dict[str, dict[str, Any]], scope: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    mentions = _indexed(value, "mention_id", "m")
    for mention in mentions.values():
        _object(
            mention,
            "mention_id unit_id entity_type start end region_ref certainty validity sensitivity_reference entity_id identity_evidence annotation_provenance",
        )
        text = units[mention["unit_id"]]["text"]
        validity = _object(mention["validity"], "pattern structure checksum")
        provenance = _object(mention["annotation_provenance"], "method manual_version reviews")
        if (
            not _interval(mention["start"], mention["end"], text)
            or mention["region_ref"] is not None
            or mention["entity_type"] not in scope["entity_types"]
            or mention["certainty"] not in {"confirmed", "ambiguous"}
            or any(
                item not in {"valid", "invalid", "not_applicable", "unknown"}
                for item in validity.values()
            )
            or not _text(mention["sensitivity_reference"])
            or provenance["method"] not in {"synthetic_fixture", "human_review"}
            or not _version(provenance["manual_version"])
            or not _strings(provenance["reviews"])
            or any(not _identifier(item, "r") for item in provenance["reviews"])
            or (provenance["method"] == "human_review" and not provenance["reviews"])
        ):
            raise ValueError
        if mention["entity_id"] is None:
            if mention["identity_evidence"] is not None:
                raise ValueError
        else:
            evidence = _object(mention["identity_evidence"], "method mention_ids")
            if (
                not _identifier(mention["entity_id"], "i")
                or evidence["method"] not in {"synthetic_identity", "explicit_reference"}
                or not _strings(evidence["mention_ids"])
                or any(not _identifier(item, "m") for item in evidence["mention_ids"])
            ):
                raise ValueError
    return mentions


def _profile_contracts(
    manifest: dict[str, Any], records: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    profiles = manifest["profiles"]
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError
    result = {}
    for identifier, reference in profiles.items():
        _object(reference, "resource sha256")
        if (
            re.fullmatch(r"[a-z][a-z0-9-]{0,63}", identifier) is None
            or not is_sha256(reference["sha256"])
            or reference["resource"] not in records
            or reference["sha256"] != manifest["resources"][reference["resource"]]["sha256"]
            or manifest["resources"][reference["resource"]]["kind"] != "json"
        ):
            raise ValueError
        profile = _object(
            records[reference["resource"]],
            "profile_id ratified clinical_policy quasi_identifier_policy precedence",
        )
        if (
            profile["profile_id"] != identifier
            or profile["ratified"] is not False
            or profile["clinical_policy"] not in {"not_evaluated", "preserve_context", "strict"}
            or profile["quasi_identifier_policy"]
            not in {"not_evaluated", "protect", "review_required"}
            or not _strings(
                profile["precedence"], {"remove", "preserve", "generalize", "review_required"}
            )
        ):
            raise ValueError
        result[identifier] = profile
    return result


def _expectation_contracts(
    value: Any,
    profiles: dict[str, dict[str, Any]],
    mentions: dict[str, dict[str, Any]],
    units: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    expectations = _indexed(value, "expectation_id", "e")
    for expectation in expectations.values():
        _object(
            expectation,
            "expectation_id profile_id case_id mention_id unit_id start end action allowed_operators verification coverage_required acceptable_release_states",
        )
        if (
            expectation["profile_id"] not in profiles
            or not _identifier(expectation["case_id"], "c")
            or expectation["action"] not in {"remove", "preserve", "generalize", "review_required"}
            or not _strings(
                expectation["allowed_operators"],
                {
                    "redact",
                    "suppress",
                    "placeholder",
                    "indexed",
                    "pseudonym",
                    "mask",
                    "generalize",
                    "date_shift",
                    "keep",
                },
            )
            or expectation["verification"]
            not in {"complete_removal", "exact_preservation", "human_review", "unverifiable"}
            or expectation["coverage_required"] != "complete"
            or not _strings(
                expectation["acceptable_release_states"],
                {"APPROVED", "REVIEW_REQUIRED", "BLOCKED", "UNSUPPORTED"},
            )
            or not expectation["acceptable_release_states"]
        ):
            raise ValueError
        if expectation["mention_id"] is not None:
            if expectation["mention_id"] not in mentions or any(
                expectation[key] is not None for key in ("unit_id", "start", "end")
            ):
                raise ValueError
        elif expectation["unit_id"] not in units or not _interval(
            expectation["start"], expectation["end"], units[expectation["unit_id"]]["text"]
        ):
            raise ValueError
    return expectations


def _metadata_contracts(manifest: dict[str, Any], indexed: _Indexes) -> None:
    resources = manifest["resources"]
    generation = _object(
        manifest["generation"],
        "generator_version random_algorithm seeds resources perturbation_rules",
    )
    if (
        not _text(generation["generator_version"])
        or generation["random_algorithm"] not in {"none", "python-random-v1"}
        or not isinstance(generation["seeds"], dict)
        or any(
            not _text(key) or type(value) is not int or not 0 <= value < 2**64
            for key, value in generation["seeds"].items()
        )
        or (generation["random_algorithm"] == "none" and generation["seeds"])
        or not _strings(generation["resources"], set(resources))
        or not _strings(generation["perturbation_rules"], set(resources))
    ):
        raise ValueError
    freeze = _object(manifest["freeze"], "status frozen_at resource_sha256 exposure custody")
    if freeze["status"] not in {"frozen", "unfrozen"} or freeze["exposure"] not in {
        "known_regression",
        "unknown",
        "unexposed",
    }:
        raise ValueError
    if freeze["status"] == "unfrozen":
        if (
            freeze["frozen_at"] is not None
            or freeze["resource_sha256"] != {}
            or freeze["custody"] is not None
        ):
            raise ValueError
    elif (
        not _utc(freeze["frozen_at"])
        or datetime.fromisoformat(freeze["frozen_at"])
        < datetime.fromisoformat(manifest["created_at"])
        or not _text(freeze["custody"])
        or freeze["resource_sha256"]
        != {key: resource["sha256"] for key, resource in resources.items()}
    ):
        raise ValueError
    for source in indexed.sources.values():
        for reference in (source["terms_reference"], source["permission_review"]["evidence_ref"]):
            if reference is not None and reference not in resources:
                raise ValueError
    for document in indexed.documents.values():
        if document["artifact_ref"] is not None:
            resource = resources[document["artifact_ref"]]
            if (
                resource["kind"] != "binary"
                or document["artifact_sha256"] != resource["sha256"]
                or not document["artifact_ref"].startswith("artifact-")
            ):
                raise ValueError


def _document_relations(indexed: _Indexes) -> None:
    unit_sets: dict[str, set[str]] = defaultdict(set)
    locators = set()
    for identifier, unit in indexed.units.items():
        if unit["case_id"] not in indexed.documents:
            raise ValueError
        unit_sets[unit["case_id"]].add(identifier)
        key = (unit["case_id"], unit["locator"]["kind"], unit["locator"]["index"])
        if key in locators:
            raise ValueError
        locators.add(key)
    source_units: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for identifier, document in indexed.documents.items():
        source = indexed.sources[document["source_id"]]
        root = indexed.documents[document["root_document_id"]]
        if (
            set(document["unit_ids"]) != unit_sets[identifier]
            or root["parent_case_id"] is not None
            or root["root_document_id"] != root["case_id"]
        ):
            raise ValueError
        if document["parent_case_id"] is None:
            if document["root_document_id"] != identifier:
                raise ValueError
        else:
            parent = indexed.documents[document["parent_case_id"]]
            if (
                any(
                    document[key] != parent[key]
                    for key in ("root_document_id", "group_id", "template_family_id")
                )
                or source["permissions"]["derivation"] is not True
                or indexed.sources[parent["source_id"]]["permissions"]["derivation"] is not True
            ):
                raise ValueError
        source_units[document["source_id"]].extend(
            indexed.units[key] for key in document["unit_ids"]
        )
    completed: set[str] = set()
    for identifier in indexed.documents:
        trail: set[str] = set()
        current: str | None = identifier
        while current is not None and current not in completed:
            if current in trail:
                raise ValueError
            trail.add(current)
            current = indexed.documents[current]["parent_case_id"]
        completed.update(trail)
    for identifier, source in indexed.sources.items():
        units = sorted(source_units[identifier], key=lambda row: row["unit_id"])
        if not units:
            raise ValueError
        if len(units) == 1:
            expected = units[0]["text_sha256"]
        else:
            digest = hashlib.sha256()
            for unit in units:
                name, text = unit["unit_id"].encode(), unit["text"].encode("utf-8")
                digest.update(len(name).to_bytes(8, "big") + name)
                digest.update(len(text).to_bytes(8, "big") + text)
            expected = digest.hexdigest()
        if source["content_sha256"] != expected:
            raise ValueError


def _membership(manifest: dict[str, Any], documents: dict[str, dict[str, Any]]) -> None:
    partitions = _object(manifest["partitions"], "train validation calibration blind_test")
    panels = _object(manifest["panels"], "known_regression external_transfer")
    seen_cases: set[str] = set()
    seen_groups: set[str] = set()
    for field, collections in (("partition", partitions), ("panel", panels)):
        for name, membership in collections.items():
            membership = _object(membership, "case_ids group_ids")
            cases, groups = membership["case_ids"], membership["group_ids"]
            if (
                not _strings(cases, set(documents))
                or not _strings(groups)
                or any(not _identifier(item, "g") for item in groups)
                or seen_cases & set(cases)
                or seen_groups & set(groups)
                or {documents[item]["group_id"] for item in cases} != set(groups)
                or any(documents[item][field] != name for item in cases)
            ):
                raise ValueError
            seen_cases.update(cases)
            seen_groups.update(groups)
    if seen_cases != set(documents):
        raise ValueError


def _annotation_relations(manifest: dict[str, Any], indexed: _Indexes) -> None:
    seen_spans = set()
    for mention in indexed.mentions.values():
        key = (mention["unit_id"], mention["entity_type"], mention["start"], mention["end"])
        if key in seen_spans:
            raise ValueError
        seen_spans.add(key)
        if mention["identity_evidence"] is not None:
            for target in mention["identity_evidence"]["mention_ids"]:
                if indexed.mentions[target]["entity_id"] != mention["entity_id"]:
                    raise ValueError
    coverage = manifest["annotation_coverage"]
    if not isinstance(coverage, list):
        raise ValueError
    seen_units = set()
    for entry in coverage:
        _object(entry, "unit_id exhaustive_entity_types inspected_ranges limitations")
        unit = indexed.units[entry["unit_id"]]
        if (
            entry["unit_id"] in seen_units
            or not _strings(
                entry["exhaustive_entity_types"], set(manifest["scope"]["entity_types"])
            )
            or not _strings(entry["limitations"])
            or not isinstance(entry["inspected_ranges"], list)
        ):
            raise ValueError
        seen_units.add(entry["unit_id"])
        ranges = []
        for region in entry["inspected_ranges"]:
            _object(region, "start end")
            if not _interval(region["start"], region["end"], unit["text"]) and not (
                unit["text"] == ""
                and type(region["start"]) is int
                and type(region["end"]) is int
                and region["start"] == region["end"] == 0
            ):
                raise ValueError
            ranges.append((region["start"], region["end"]))
        position = 0
        has_gap = False
        for start, end in sorted(ranges):
            has_gap = has_gap or start > position
            position = max(position, end)
        if entry["exhaustive_entity_types"] and (has_gap or position != len(unit["text"])):
            raise ValueError
    if seen_units != set(indexed.units):
        raise ValueError


def _expectation_relations(indexed: _Indexes) -> None:
    intervals: dict[tuple[str, str], list[tuple[int, int, dict[str, Any]]]] = defaultdict(list)
    verification = {
        "remove": "complete_removal",
        "preserve": "exact_preservation",
        "generalize": "unverifiable",
        "review_required": "human_review",
    }
    for expectation in indexed.expectations.values():
        if expectation["mention_id"] is not None:
            target = indexed.mentions[expectation["mention_id"]]
            unit_id, start, end = target["unit_id"], target["start"], target["end"]
        else:
            unit_id, start, end = expectation["unit_id"], expectation["start"], expectation["end"]
        if (
            indexed.units[unit_id]["case_id"] != expectation["case_id"]
            or expectation["case_id"] not in indexed.documents
            or expectation["verification"] != verification[expectation["action"]]
            or (expectation["action"] != "review_required" and not expectation["allowed_operators"])
        ):
            raise ValueError
        bucket = intervals[(expectation["profile_id"], unit_id)]
        bucket.extend(((start, 1, expectation), (end, -1, expectation)))
    # Sweep half-open spans. Counts avoid quadratic comparisons for nested gold.
    for (profile_id, _unit_id), events in intervals.items():
        actions: Counter[str] = Counter()
        operators: dict[str, Counter[str]] = defaultdict(Counter)
        states: dict[str, Counter[str]] = defaultdict(Counter)
        precedence = indexed.profiles[profile_id]["precedence"]
        for _position, changes in groupby(
            sorted(events, key=lambda item: item[0]), key=lambda item: item[0]
        ):
            for _offset, delta, expectation in changes:
                action = expectation["action"]
                actions[action] += delta
                for operator in expectation["allowed_operators"]:
                    operators[action][operator] += delta
                for state in expectation["acceptable_release_states"]:
                    states[action][state] += delta
            active = [action for action, count in actions.items() if count]
            if not active:
                continue
            if len(active) > 1:
                if not set(active) <= set(precedence):
                    raise ValueError
                action = min(active, key=precedence.index)
            else:
                action = active[0]
            if (
                action != "review_required"
                and not any(count == actions[action] for count in operators[action].values())
            ) or not any(count == actions[action] for count in states[action].values()):
                raise ValueError


def _manifest_contract(value: Any) -> dict[str, Any]:
    manifest = _object(
        value,
        "schema_version dataset_version taxonomy_version annotation_version dataset_id created_at resources partitions panels scope profiles generation freeze annotation_coverage",
    )
    if (
        manifest["schema_version"] != "df-eval-mx.package.v1"
        or manifest["taxonomy_version"] != "df-eval-mx.taxonomy.v1"
        or manifest["annotation_version"] != "df-eval-mx.annotation.v1"
        or not _version(manifest["dataset_version"])
        or not _identifier(manifest["dataset_id"], "d")
        or not _utc(manifest["created_at"])
    ):
        raise ValueError
    scope = _object(
        manifest["scope"], "language country entity_types formats required_strata optional_strata"
    )
    if (
        scope["language"] != "es"
        or scope["country"] != "MX"
        or not _strings(scope["entity_types"], {item.value for item in EntityType})
        or not scope["entity_types"]
        or not _strings(
            scope["formats"],
            {"text", "json", "jsonl", "csv", "tsv", "docx", "xlsx", "html", "eml", "pdf", "image"},
        )
        or not scope["formats"]
        or not _strings(scope["required_strata"])
        or not _strings(scope["optional_strata"])
        or set(scope["required_strata"]) & set(scope["optional_strata"])
    ):
        raise ValueError
    return manifest


def load_evaluation_package(path: str | Path, *, manifest_sha256: str) -> EvaluationPackage:
    """Load the declared local resources before invoking any candidate."""
    reader = None
    try:
        reader = PackageReader(path)
        payload = reader.read("manifest.json", MAX_MANIFEST_BYTES)
        if not is_sha256(manifest_sha256) or hashlib.sha256(payload).hexdigest() != manifest_sha256:
            raise ValueError
        manifest = _manifest_contract(strict_json(payload))
        resources = manifest["resources"]
        if not isinstance(resources, dict) or not 1 <= len(resources) <= MAX_RESOURCES:
            raise ValueError
        required_roles = {"sources", "documents", "units", "mentions", "expectations"}
        if not required_roles <= set(resources) or not isinstance(manifest["profiles"], dict):
            raise ValueError
        profile_roles = set()
        for reference in manifest["profiles"].values():
            _object(reference, "resource sha256")
            if not isinstance(reference["resource"], str):
                raise ValueError
            profile_roles.add(reference["resource"])
        records = {}
        paths = set()
        total = len(payload)
        for role, resource in resources.items():
            if (
                not isinstance(resource, dict)
                or set(resource) != {"path", "kind", "sha256", "bytes", "records"}
                or not is_sha256(resource["sha256"])
                or type(resource["bytes"]) is not int
                or not 0 <= resource["bytes"] <= MAX_RESOURCE_BYTES
                or type(resource["records"]) is not int
                or not 0 <= resource["records"] <= MAX_RECORDS
            ):
                raise ValueError
            if role in required_roles:
                if resource["kind"] != "jsonl":
                    raise ValueError
            elif role in profile_roles:
                if (
                    re.fullmatch(r"profile-[0-9a-f]{1,32}", role) is None
                    or resource["kind"] != "json"
                ):
                    raise ValueError
            elif (
                resource["kind"] != "binary"
                or re.fullmatch(r"(?:artifact|evidence|generator|rule)-[0-9a-f]{1,32}", role)
                is None
            ):
                raise ValueError
            if not isinstance(resource["path"], str) or resource["path"] in paths:
                raise ValueError
            paths.add(resource["path"])
            content = reader.read(resource["path"], MAX_RESOURCE_BYTES)
            total += len(content)
            if (
                len(content) != resource["bytes"]
                or hashlib.sha256(content).hexdigest() != resource["sha256"]
                or total > MAX_PACKAGE_BYTES
            ):
                raise ValueError
            value: Any
            if resource["kind"] == "jsonl":
                lines = content.split(b"\n")
                if lines[-1] == b"":
                    lines.pop()
                value = [strict_json(line) for line in lines]
                count = len(value)
            elif resource["kind"] == "json":
                value, count = strict_json(content), 1
            elif resource["kind"] == "binary":
                value, count = content, 0
            else:
                raise ValueError
            if count != resource["records"]:
                raise ValueError
            records[role] = value
        sources = _source_contracts(records["sources"])
        documents = _document_contracts(records["documents"], manifest["scope"])
        units = _unit_contracts(records["units"])
        mentions = _mention_contracts(records["mentions"], units, manifest["scope"])
        profiles = _profile_contracts(manifest, records)
        expectations = _expectation_contracts(records["expectations"], profiles, mentions, units)
        indexed = _Indexes(sources, documents, units, mentions, profiles, expectations)
        _metadata_contracts(manifest, indexed)
        _document_relations(indexed)
        _membership(manifest, documents)
        _annotation_relations(manifest, indexed)
        _expectation_relations(indexed)
        return EvaluationPackage(manifest_sha256, manifest, records)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, BadZipFile, EOFError):
        raise InvalidPackageError from None
    finally:
        if reader is not None:
            reader.close()
