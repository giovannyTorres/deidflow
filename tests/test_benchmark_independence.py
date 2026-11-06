from __future__ import annotations

import hashlib

import pytest
from benchmark_case_fixtures import fixture_records, profile_package, save_manifest


def partition_package(
    root, texts=None, *, shared_template=False, historical=True, linked_identity=False
):
    records = fixture_records()
    records["mentions"], records["expectations"] = [], []
    if texts is not None:
        for index, (unit, text) in enumerate(zip(records["units"], texts, strict=True)):
            unit.update(text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
            records["sources"][index]["content_sha256"] = unit["text_sha256"]
    for index, document in enumerate(records["documents"]):
        document.update(panel=None, partition="train" if index == 0 else "blind_test")
        if shared_template:
            document["template_family_id"] = "t-a"
        if not historical:
            records["sources"][index]["exposure"] = {
                "training": False,
                "tuning": False,
                "prior_evaluation": False,
                "candidate_exposure": "unexposed",
            }
    if linked_identity:
        for index, unit in enumerate(records["units"], 1):
            start = unit["text"].index("Ana")
            records["mentions"].append(
                dict(
                    fixture_records()["mentions"][0],
                    mention_id=f"m-{index}",
                    unit_id=unit["unit_id"],
                    entity_type="PERSON",
                    start=start,
                    end=start + 3,
                    entity_id="i-a",
                    identity_evidence={
                        "method": "synthetic_identity",
                        "mention_ids": ["m-1", "m-2"],
                    },
                )
            )
    manifest, _ = profile_package(
        root, records, "detection-descriptive-v1", ["PERSON"] if linked_identity else ["EMAIL"]
    )
    manifest["panels"]["known_regression"] = {"case_ids": [], "group_ids": []}
    for index, partition in enumerate(("train", "blind_test"), 1):
        manifest["partitions"][partition] = {
            "case_ids": [f"c-{index}"],
            "group_ids": [f"g-{index}"],
        }
    return records, manifest, save_manifest(root, manifest)


def audit(root, digest, profile="default"):
    from deidflow.benchmarks.independence import SimilarityProfile, audit_independence

    return audit_independence(
        root,
        manifest_sha256=digest,
        similarity=SimilarityProfile() if profile == "default" else profile,
    )["result"]


@pytest.mark.parametrize(
    "texts,code",
    [
        (("Documento ficticio igual.", "Documento ficticio igual."), "EXACT_TEXT_DUPLICATE"),
        (("ＦＩＣＴＩＣＩＯ   A", "ficticio\t a"), "NORMALIZED_TEXT_DUPLICATE"),
    ],
)
def test_original_and_normalized_duplicates_cannot_cross_partitions(tmp_path, texts, code):
    _, _, digest = partition_package(tmp_path, texts)
    result = audit(tmp_path, digest)
    assert result["independence_accredited"] is False
    assert code in {row["code"] for row in result["diagnostics"]}
    assert result["components"] == 1
    assert result["cross_partition_components"] == 1


def test_shared_template_links_components_without_using_provider_or_language(tmp_path):
    _, _, digest = partition_package(tmp_path, shared_template=True)
    result = audit(tmp_path, digest)
    assert result["components"] == 1
    assert result["cross_partition_components"] == 1


def test_missing_similarity_profile_does_not_accredit_independence(tmp_path):
    _, _, digest = partition_package(tmp_path)
    result = audit(tmp_path, digest, profile=None)
    assert result["independence_accredited"] is False
    assert "SIMILARITY_PROFILE_REQUIRED" in {row["code"] for row in result["diagnostics"]}


def test_near_match_is_unresolved_and_keeps_declared_profile(tmp_path):
    from deidflow.benchmarks.independence import SimilarityProfile

    _, _, digest = partition_package(
        tmp_path,
        (
            "uno dos tres cuatro cinco seis siete ocho nueve diez",
            "uno dos tres cuatro cinco seis siete ocho nueve once",
        ),
    )
    result = audit(tmp_path, digest, SimilarityProfile(threshold=0.5))
    assert result["near_cross_partition_pairs"] == 1
    assert result["independence_accredited"] is False
    assert result["similarity_profile"]["sha256"]


def test_exposure_unknown_and_historical_never_become_blind_evidence(tmp_path):
    _, _, digest = partition_package(tmp_path)
    result = audit(tmp_path, digest)
    assert result["blind_incompatible_exposure_documents"] == 1
    assert result["independence_accredited"] is False
    assert result["partition_counts"]["train"] == 1
    assert result["partition_counts"]["blind_test"] == 1


def test_homonyms_without_identity_evidence_do_not_join_documents(tmp_path):
    _, _, digest = partition_package(
        tmp_path,
        (
            "Persona ficticia Ana compra un libro azul.",
            "Persona ficticia Ana cultiva flores rojas.",
        ),
    )
    result = audit(tmp_path, digest)
    assert result["components"] == 2
    assert result["relations"]["explicit_identity"] == 0


def test_similarity_budget_exhaustion_is_not_a_negative_result(tmp_path):
    from deidflow.benchmarks.independence import SimilarityProfile

    _, _, digest = partition_package(tmp_path)
    result = audit(tmp_path, digest, SimilarityProfile(maximum_comparisons=0))
    assert result["independence_accredited"] is False
    assert "SIMILARITY_BUDGET_EXCEEDED" in {row["code"] for row in result["diagnostics"]}


def test_exposed_regression_package_is_not_renamed_blind(tmp_path):
    records = fixture_records()
    _, digest = profile_package(tmp_path, records, "detection-descriptive-v1", ["EMAIL"])
    result = audit(tmp_path, digest)
    assert result["partition_counts"]["known_regression"] == 2
    assert result["partition_counts"]["blind_test"] == 0
    assert result["independence_accredited"] is False
    assert "NO_BLIND_TEST" in {row["code"] for row in result["diagnostics"]}
    assert "a.b@example.test" not in str(result)


def test_derivative_cannot_cross_partition_even_with_different_seed_and_hash(tmp_path):
    records, _, _ = partition_package(tmp_path)
    child = records["documents"][1]
    child.update(
        parent_case_id="c-1",
        root_document_id="c-1",
        variant_id="v-a",
        perturbation_recipe={
            "version": "1.0.0",
            "operation": "simulated_ocr",
            "seed": 42,
            "parameters": {},
        },
    )
    # Reuse the ordinary writer with the altered relationship, then restore membership.
    manifest, _ = profile_package(tmp_path / "case", records, "detection-descriptive-v1", ["EMAIL"])
    manifest["panels"]["known_regression"] = {"case_ids": [], "group_ids": []}
    manifest["partitions"]["train"] = {"case_ids": ["c-1"], "group_ids": ["g-1"]}
    manifest["partitions"]["blind_test"] = {"case_ids": ["c-2"], "group_ids": ["g-2"]}
    digest = save_manifest(tmp_path / "case", manifest)
    with pytest.raises(ValueError, match="Invalid evaluation package"):
        audit(tmp_path / "case", digest)


def test_explicit_synthetic_identity_joins_documents(tmp_path):
    _, _, digest = partition_package(
        tmp_path,
        ("Ana compra libros ficticios.", "Ana cultiva flores ficticias."),
        linked_identity=True,
    )
    result = audit(tmp_path, digest)
    assert result["relations"]["explicit_identity"] == 1
    assert result["components"] == 1
    assert result["cross_partition_components"] == 1


def test_frozen_unexposed_declaration_fixture_passes_only_declaration_checks(tmp_path):
    # Tests the declaration contract; this inspected fixture is not actual blind evidence.
    _, manifest, _ = partition_package(tmp_path, historical=False)
    manifest["freeze"] = {
        "status": "frozen",
        "frozen_at": manifest["created_at"],
        "resource_sha256": {role: row["sha256"] for role, row in manifest["resources"].items()},
        "exposure": "unexposed",
        "custody": "fictional-contract-fixture-only",
    }
    result = audit(tmp_path, save_manifest(tmp_path, manifest))
    assert result["independence_accredited"] is True
    assert result["accreditation_scope"] == "DECLARED_PACKAGE_RELATIONSHIPS_AND_EXPOSURE"
    assert "CUSTODY_NOT_ACCREDITED_BY_THIS_AUDIT" in result["limitations"]
    assert result["quality"] == "DESCRIPTIVE_ONLY"
