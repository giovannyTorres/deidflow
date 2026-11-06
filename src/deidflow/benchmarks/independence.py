"""Versioned relationship/content/exposure audit without publishing reference."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from .email import _source_digest
from .evaluation_package import load_evaluation_package


@dataclass(frozen=True)
class SimilarityProfile:
    threshold: float = 0.85
    maximum_comparisons: int = 100_000

    def __post_init__(self) -> None:
        if (
            type(self.threshold) not in {float, int}
            or not math.isfinite(self.threshold)
            or not 0.5 <= self.threshold <= 1
            or type(self.maximum_comparisons) is not int
            or not 0 <= self.maximum_comparisons <= 1_000_000
        ):
            raise ValueError("Invalid similarity profile")


class _Components:
    def __init__(self, cases: list[str]) -> None:
        self.parents = dict(zip(cases, cases, strict=True))

    def root(self, case: str) -> str:
        ancestor = case
        while self.parents[ancestor] != ancestor:
            ancestor = self.parents[ancestor]
        while case != ancestor:
            parent = self.parents[case]
            self.parents[case] = ancestor
            case = parent
        return ancestor

    def link(self, left: str, right: str) -> None:
        first, second = sorted((self.root(left), self.root(right)))
        self.parents[second] = first


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text)
    return (
        {tuple(words[index : index + 3]) for index in range(max(1, len(words) - 2))}
        if words
        else set()
    )


def audit_independence(
    package: str | Path,
    *,
    manifest_sha256: str,
    similarity: SimilarityProfile | None,
) -> dict[str, Any]:
    """Audit declared package independence; custody/history remain separate."""
    if similarity is not None and not isinstance(similarity, SimilarityProfile):
        raise ValueError("Invalid similarity profile")
    loaded = load_evaluation_package(package, manifest_sha256=manifest_sha256)
    records = loaded.records
    documents = {row["case_id"]: row for row in records["documents"]}
    sources = {row["source_id"]: row for row in records["sources"]}
    units = {row["unit_id"]: row for row in records["units"]}
    components = _Components(sorted(documents))
    relations: Counter[str] = Counter()
    diagnostics: Counter[str] = Counter()
    partition = {case: row["partition"] or row["panel"] for case, row in documents.items()}

    def connect(
        buckets: dict[Any, list[str]], relation: str, duplicate_code: str | None = None
    ) -> None:
        for members in buckets.values():
            members = sorted(set(members))
            if len(members) < 2:
                continue
            relations[relation] += len(members) * (len(members) - 1) // 2
            for member in members[1:]:
                components.link(members[0], member)
            if duplicate_code and len({partition[case] for case in members}) > 1:
                diagnostics[duplicate_code] += 1

    for field in ("source_id", "root_document_id", "group_id", "template_family_id"):
        buckets: dict[Any, list[str]] = defaultdict(list)
        for case, document in documents.items():
            buckets[document[field]].append(case)
        connect(buckets, field)
    hashes: dict[Any, list[str]] = defaultdict(list)
    for case, document in documents.items():
        hashes[sources[document["source_id"]]["content_sha256"]].append(case)
    connect(hashes, "original_source_hash")
    identities: dict[Any, list[str]] = defaultdict(list)
    for mention in records["mentions"]:
        if mention["entity_id"] is not None and mention["identity_evidence"] is not None:
            identities[mention["entity_id"]].append(units[mention["unit_id"]]["case_id"])
    connect(identities, "explicit_identity")
    texts = {
        case: "\n".join(
            units[key]["text"]
            for key in sorted(
                document["unit_ids"], key=lambda key: (units[key]["locator"]["index"], key)
            )
        )
        for case, document in documents.items()
    }
    originals: dict[Any, list[str]] = defaultdict(list)
    normalized: dict[Any, list[str]] = defaultdict(list)
    normalized_texts = {case: _normalized(text) for case, text in texts.items()}
    for case, text in texts.items():
        originals[text].append(case)
        normalized[normalized_texts[case]].append(case)
    connect(originals, "exact_text", "EXACT_TEXT_DUPLICATE")
    connect(normalized, "normalized_text", "NORMALIZED_TEXT_DUPLICATE")
    groups: dict[str, list[str]] = defaultdict(list)
    for case in sorted(documents):
        groups[components.root(case)].append(case)
    crossing = sum(len({partition[case] for case in members}) > 1 for members in groups.values())
    split_groups = sum(
        len({documents[case]["group_id"] for case in members}) > 1 for members in groups.values()
    )
    if crossing:
        diagnostics["CROSS_PARTITION_COMPONENT"] = crossing
    if split_groups:
        diagnostics["CLOSURE_GROUP_SPLIT"] = split_groups
    near = compared = 0
    descriptor = None
    if similarity is None:
        diagnostics["SIMILARITY_PROFILE_REQUIRED"] = 1
    else:
        configuration = {
            "algorithm": "nfkc-casefold-ws.word-trigram-jaccard.v1",
            **asdict(similarity),
        }
        descriptor = {
            **configuration,
            "sha256": hashlib.sha256(
                json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        shingles = {case: _shingles(text) for case, text in normalized_texts.items()}
        for left, right in combinations(sorted(documents), 2):
            if partition[left] == partition[right] or components.root(left) == components.root(
                right
            ):
                continue
            if compared >= similarity.maximum_comparisons:
                diagnostics["SIMILARITY_BUDGET_EXCEEDED"] = 1
                break
            compared += 1
            union = shingles[left] | shingles[right]
            if union and len(shingles[left] & shingles[right]) / len(union) >= similarity.threshold:
                near += 1
        if near:
            diagnostics["UNRESOLVED_NEAR_MATCH"] = near
    blind = [row for row in documents.values() if row["partition"] == "blind_test"]
    incompatible = 0
    for document in blind:
        exposure = sources[document["source_id"]]["exposure"]
        if exposure["candidate_exposure"] != "unexposed" or any(
            exposure[key] is not False for key in ("training", "tuning", "prior_evaluation")
        ):
            incompatible += 1
    if incompatible:
        diagnostics["BLIND_EXPOSURE_NOT_ACCREDITED"] = incompatible
    if not blind:
        diagnostics["NO_BLIND_TEST"] = 1
    elif (
        loaded.manifest["freeze"]["status"] != "frozen"
        or loaded.manifest["freeze"]["exposure"] != "unexposed"
    ):
        diagnostics["BLIND_TEST_NOT_FROZEN"] = len(blind)
    names = (
        "train",
        "validation",
        "calibration",
        "blind_test",
        "known_regression",
        "external_transfer",
    )
    return {
        "schema_version": "df-eval-mx.independence-report.v1",
        "result": {
            "dataset_sha256": manifest_sha256,
            "dataset_version": loaded.manifest["dataset_version"],
            "evaluator_source_sha256": _source_digest(),
            "independence_accredited": not bool(diagnostics),
            "accreditation_scope": "DECLARED_PACKAGE_RELATIONSHIPS_AND_EXPOSURE",
            "required_documents": len(documents),
            "partition_counts": {
                name: sum(value == name for value in partition.values()) for name in names
            },
            "components": len(groups),
            "cross_partition_components": crossing,
            "split_declared_groups": split_groups,
            "relations": {
                name: relations[name]
                for name in (
                    "source_id",
                    "root_document_id",
                    "group_id",
                    "template_family_id",
                    "original_source_hash",
                    "explicit_identity",
                    "exact_text",
                    "normalized_text",
                )
            },
            "near_cross_partition_pairs": near,
            "similarity_comparisons": compared,
            "similarity_profile": descriptor,
            "blind_incompatible_exposure_documents": incompatible,
            "unknown_exposure_sources": sum(
                any(value == "unknown" for value in row["exposure"].values())
                for row in sources.values()
            ),
            "diagnostics": [
                {"code": code, "count": count} for code, count in sorted(diagnostics.items())
            ],
            "quality": "DESCRIPTIVE_ONLY",
            "limitations": [
                "EXPOSURE_DECLARATIONS_NOT_AUTHENTICATED",
                "CUSTODY_NOT_ACCREDITED_BY_THIS_AUDIT",
                "REFERENCE_ACCESS_IS_NOT_PROOF_OF_NONEXPOSURE",
                "NO_QUALITY_OR_GENERALIZATION_APPROVAL",
            ],
        },
    }
