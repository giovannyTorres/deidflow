from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from deidflow.benchmarks.evaluation_package import InvalidPackageError, load_evaluation_package
from deidflow.benchmarks.perturbation_package import generate_perturbation_suite
from deidflow.benchmarks.synthetic_package import canonical_json, write_package_records

EXAMPLES = Path(__file__).parents[1] / "examples"


def generated_vector_package(tmp_path):
    source = EXAMPLES / "benchmark-mx-identifiers"
    digest = hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest()
    suite = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=tmp_path / "suite",
        seed=1,
        recipes=("nfd.v1",),
    )
    entry = suite["packages"][0]
    return load_evaluation_package(
        tmp_path / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
    )


def test_derivation_evidence_rejects_a_malformed_unused_vector_link(tmp_path):
    package = generated_vector_package(tmp_path)
    child = next(
        row
        for row in package.records["validation_vectors"]
        if row["provenance"]["method"] == "synthetic_derivation"
    )
    evidence_ref = child["provenance"]["evidence_ref"]
    evidence = json.loads(package.records[evidence_ref])
    evidence["vector_derivations"].append(
        {"vector_id": "private-canary", "parent_vector_id": "v-1"}
    )
    package.records[evidence_ref] = canonical_json(evidence)

    destination = tmp_path / "rejected"
    with pytest.raises(InvalidPackageError) as error:
        write_package_records(destination, package.records, package.manifest)

    assert str(error.value) == "Invalid evaluation package"
    assert not destination.exists()


@pytest.mark.parametrize("seed", [True, 1.0])
def test_derivation_evidence_requires_an_integer_seed(tmp_path, seed):
    package = generated_vector_package(tmp_path)
    child = next(
        row
        for row in package.records["validation_vectors"]
        if row["provenance"]["method"] == "synthetic_derivation"
    )
    evidence_ref = child["provenance"]["evidence_ref"]
    evidence = json.loads(package.records[evidence_ref])
    evidence["seed"] = seed
    package.records[evidence_ref] = canonical_json(evidence)

    destination = tmp_path / "rejected"
    with pytest.raises(InvalidPackageError):
        write_package_records(destination, package.records, package.manifest)

    assert not destination.exists()


@pytest.mark.parametrize(
    "corruption",
    ["original_method", "reused_original_evidence", "wrong_parent", "partition", "malformed_id"],
)
def test_derivation_cannot_forge_original_evidence_or_parent_relationships(tmp_path, corruption):
    package = generated_vector_package(tmp_path)
    vectors = package.records["validation_vectors"]
    original = vectors[0]
    child = next(row for row in vectors if row["provenance"]["method"] == "synthetic_derivation")
    evidence_ref = child["provenance"]["evidence_ref"]
    evidence = json.loads(package.records[evidence_ref])
    link = next(
        row for row in evidence["vector_derivations"] if row["vector_id"] == child["vector_id"]
    )
    if corruption == "original_method":
        original["provenance"] = dict(child["provenance"])
    elif corruption == "reused_original_evidence":
        original_ref = original["provenance"]["evidence_ref"]
        package.records[original_ref] = package.records[evidence_ref]
        for vector in vectors:
            if vector["provenance"]["evidence_ref"] == evidence_ref:
                vector["provenance"]["evidence_ref"] = original_ref
    elif corruption == "wrong_parent":
        link["parent_vector_id"] = vectors[1]["vector_id"]
        package.records[evidence_ref] = canonical_json(evidence)
    elif corruption == "malformed_id":
        link["parent_vector_id"] = {"private-canary": []}
        package.records[evidence_ref] = canonical_json(evidence)
    else:
        unit = next(row for row in package.records["units"] if row["unit_id"] == child["unit_id"])
        document = next(
            row for row in package.records["documents"] if row["case_id"] == unit["case_id"]
        )
        document.update(partition="validation", panel=None)

    destination = tmp_path / "rejected"
    with pytest.raises(InvalidPackageError) as error:
        write_package_records(destination, package.records, package.manifest)

    assert str(error.value) == "Invalid evaluation package"
    assert not destination.exists()


def test_malformed_deep_derivation_evidence_has_a_sanitized_admission_error(tmp_path):
    package = generated_vector_package(tmp_path)
    child = next(
        row
        for row in package.records["validation_vectors"]
        if row["provenance"]["method"] == "synthetic_derivation"
    )
    package.records[child["provenance"]["evidence_ref"]] = b"[" * 2000 + b"]" * 2000

    destination = tmp_path / "rejected"
    with pytest.raises(InvalidPackageError) as error:
        write_package_records(destination, package.records, package.manifest)

    assert str(error.value) == "Invalid evaluation package"
    assert not destination.exists()


@pytest.mark.parametrize("corruption", ["missing", "out_of_bounds", "wrong_projection"])
def test_derivation_vector_must_follow_its_declared_codepoint_map(tmp_path, corruption):
    package = generated_vector_package(tmp_path)
    child = next(
        row
        for row in package.records["validation_vectors"]
        if row["provenance"]["method"] == "synthetic_derivation"
    )
    evidence_ref = child["provenance"]["evidence_ref"]
    evidence = json.loads(package.records[evidence_ref])
    parent_id = next(
        row["parent_vector_id"]
        for row in evidence["vector_derivations"]
        if row["vector_id"] == child["vector_id"]
    )
    parent = next(
        row for row in package.records["validation_vectors"] if row["vector_id"] == parent_id
    )
    mapping = evidence["codepoint_boundaries"][parent["unit_id"]][0]
    if corruption == "missing":
        evidence["codepoint_boundaries"] = {}
    elif corruption == "out_of_bounds":
        mapping[0] = [0, 1000000]
    else:
        for offset in range(parent["start"], parent["end"]):
            start = offset - parent["start"]
            mapping[offset] = [start, start + 1]
    package.records[evidence_ref] = canonical_json(evidence)

    destination = tmp_path / "rejected"
    with pytest.raises(InvalidPackageError):
        write_package_records(destination, package.records, package.manifest)

    assert not destination.exists()


@pytest.mark.parametrize("claim", ["identity", "review"])
def test_derived_validation_mention_cannot_invent_identity_or_review_evidence(tmp_path, claim):
    package = generated_vector_package(tmp_path)
    child = next(
        row
        for row in package.records["validation_vectors"]
        if row["provenance"]["method"] == "synthetic_derivation"
        and row["sensitivity"] == "sensitive"
    )
    mention = next(
        row for row in package.records["mentions"] if row["mention_id"] == child["mention_id"]
    )
    if claim == "identity":
        mention.update(
            entity_id="i-abcdef",
            identity_evidence={
                "method": "synthetic_identity",
                "mention_ids": [mention["mention_id"]],
            },
        )
    else:
        mention["annotation_provenance"].update(method="human_review", reviews=["r-abcdef"])

    destination = tmp_path / "rejected"
    with pytest.raises(InvalidPackageError):
        write_package_records(destination, package.records, package.manifest)

    assert not destination.exists()
