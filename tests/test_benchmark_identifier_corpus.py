from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

DECISION = Path(__file__).parents[1] / "docs/benchmark-mx/operational-decision-v1.json"


def generate(root: Path, seed: int = 104729):
    from deidflow.benchmarks.synthetic_package import generate_identifier_package

    return generate_identifier_package(
        root,
        seed=seed,
        decision=DECISION,
        decision_sha256=hashlib.sha256(DECISION.read_bytes()).hexdigest(),
    )


def test_seeded_public_generator_produces_reproducible_admissible_known_regression(tmp_path):
    from deidflow.benchmarks.evaluation_package import load_evaluation_package

    first, second = tmp_path / "first", tmp_path / "second"
    summary = generate(first)
    assert generate(second) == summary
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    package = load_evaluation_package(first, manifest_sha256=summary["manifest_sha256"])
    assert package.manifest["panels"]["known_regression"]["case_ids"]
    assert all(not membership["case_ids"] for membership in package.manifest["partitions"].values())
    assert summary["decision"]["status"] == "ratified"
    assert summary["executable_profile_ratified"] is False
    assert summary["quality_ratified"] is False


def test_generated_identifier_cases_reach_real_detection_and_validation_with_honest_limits(
    tmp_path,
):
    from deidflow.benchmarks.evaluation_package import load_evaluation_package
    from deidflow.benchmarks.package_runner import run_package_benchmark
    from deidflow.benchmarks.validation_runner import run_validation_benchmark

    root = tmp_path / "corpus"
    summary = generate(root)
    labels = {"RFC", "CURP", "CLABE", "PAYMENT_CARD", "PHONE", "EMAIL"}
    assert set(summary["support_by_entity"]) == labels
    assert 30 <= summary["documents"] <= 40
    assert set(summary["support_by_action"]) == {"remove", "preserve", "review_required"}
    package = load_evaluation_package(root, manifest_sha256=summary["manifest_sha256"])
    assert package.records["evidence-9"] == DECISION.read_bytes()
    detection = run_package_benchmark(
        root,
        manifest_sha256=summary["manifest_sha256"],
        candidate="rules.mx",
        profile="detection-descriptive-v1",
        output=tmp_path / "detection",
    )["result"]
    validation = run_validation_benchmark(
        root,
        manifest_sha256=summary["manifest_sha256"],
        candidate="rules.mx",
        profile="validation-descriptive-v1",
        output=tmp_path / "validation",
    )["result"]
    assert detection["attempt_status"] == validation["attempt_status"] == "completed"
    assert detection["quality"] == validation["quality"] == "DESCRIPTIVE_ONLY"
    assert validation["execution"]["completed_vectors"] == summary["documents"]
    assert validation["metrics"]["RFC"]["checksum"]["mismatched"] == 1  # XAXX exception.
    assert validation["metrics"]["PHONE"]["pattern"]["unknown_prediction"] > 0
    assert validation["metrics"]["EMAIL"]["pattern"]["unknown_prediction"] > 0


def test_writer_preserves_existing_packages_and_rejects_invalid_admission_without_output(tmp_path):
    from copy import deepcopy

    from deidflow.benchmarks.evaluation_package import InvalidPackageError, load_evaluation_package
    from deidflow.benchmarks.synthetic_package import write_package_records

    original = tmp_path / "original"
    summary = generate(original)
    package = load_evaluation_package(original, manifest_sha256=summary["manifest_sha256"])
    before = {p.name: p.read_bytes() for p in original.iterdir()}
    with pytest.raises(ValueError):
        write_package_records(original, package.records, package.manifest)
    assert {p.name: p.read_bytes() for p in original.iterdir()} == before
    records = deepcopy(package.records)
    records["units"][0]["text"] = "private-canary@example.invalid"
    rejected = tmp_path / "rejected"
    with pytest.raises(InvalidPackageError, match="^Invalid evaluation package$"):
        write_package_records(rejected, records, package.manifest)
    assert not rejected.exists()
    blocker = tmp_path / "private-canary@example.invalid"
    blocker.write_text("existing file")
    with pytest.raises(ValueError) as error:
        write_package_records(blocker / "package", package.records, package.manifest)
    assert "canary" not in str(error.value)
    assert blocker.read_text() == "existing file"


def test_same_invalid_literal_follows_context_and_receipt_pinning_is_required(tmp_path):
    from deidflow.benchmarks.evaluation_package import load_evaluation_package
    from deidflow.benchmarks.synthetic_package import generate_identifier_package

    root = tmp_path / "corpus"
    summary = generate(root)
    package = load_evaluation_package(root, manifest_sha256=summary["manifest_sha256"])
    units = {row["unit_id"]: row for row in package.records["units"]}
    vectors = [
        row
        for row in package.records["validation_vectors"]
        if units[row["unit_id"]]["text"][row["start"] : row["end"]] == "ZZZX010101AA2"
    ]
    cases = {units[row["unit_id"]]["case_id"] for row in vectors}
    assert {
        row["action"] for row in package.records["expectations"] if row["case_id"] in cases
    } == {"remove", "preserve", "review_required"}
    assert sorted(row["sensitivity"] for row in vectors) == [
        "nonpersonal_distractor",
        "sensitive",
        "sensitive",
    ]
    assert all(row["validity"]["checksum"] == "invalid" for row in vectors)
    with pytest.raises(ValueError, match="^Invalid operational decision receipt$"):
        generate_identifier_package(
            tmp_path / "wrong-pin", seed=104729, decision=DECISION, decision_sha256="0" * 64
        )
    assert not (tmp_path / "wrong-pin").exists()


def test_seed_changes_templates_without_moving_groups_or_reference_labels(tmp_path):
    from deidflow.benchmarks.evaluation_package import load_evaluation_package
    from deidflow.benchmarks.independence import SimilarityProfile, audit_independence
    from deidflow.benchmarks.synthetic_package import write_package_records

    first, second = tmp_path / "first", tmp_path / "second"
    left, right = generate(first), generate(second, seed=104730)
    assert left["manifest_sha256"] != right["manifest_sha256"]
    packages = [
        load_evaluation_package(path, manifest_sha256=summary["manifest_sha256"])
        for path, summary in ((first, left), (second, right))
    ]
    assert [
        {key: value for key, value in row.items() if key not in {"start", "end"}}
        for row in packages[0].records["validation_vectors"]
    ] == [
        {key: value for key, value in row.items() if key not in {"start", "end"}}
        for row in packages[1].records["validation_vectors"]
    ]
    assert packages[0].records["documents"] == packages[1].records["documents"]
    cloned = write_package_records(tmp_path / "clone", packages[0].records, packages[0].manifest)
    assert cloned.manifest_sha256 == left["manifest_sha256"]
    independence = audit_independence(
        first, manifest_sha256=left["manifest_sha256"], similarity=SimilarityProfile()
    )["result"]
    assert independence["cross_partition_components"] == 0
    assert independence["split_declared_groups"] == 0
    assert independence["independence_accredited"] is False  # Exposed; no blind test.
