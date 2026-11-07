from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import pytest

DECISION = Path(__file__).parents[1] / "docs/benchmark-mx/operational-decision-v1.json"
PROFILES = {
    "detection-descriptive-v1",
    "validation-descriptive-v1",
    "transformation-descriptive-v1",
    "pipeline-descriptive-v1",
}
CLINICAL = {
    "DIAGNOSIS",
    "MEDICAL_CONDITION",
    "MEDICATION",
    "TREATMENT",
    "CLINICAL_OBSERVATION",
}


def generate(root: Path, mode: str = "contextual"):
    from deidflow.benchmarks.contextual_package import generate_contextual_package

    return generate_contextual_package(
        root,
        mode=mode,
        decision=DECISION,
        decision_sha256=hashlib.sha256(DECISION.read_bytes()).hexdigest(),
    )


def generated_package(root: Path, mode: str = "contextual"):
    from deidflow.benchmarks.evaluation_package import load_evaluation_package

    summary = generate(root, mode)
    return load_evaluation_package(root, manifest_sha256=summary["manifest_sha256"]), summary


def case_with_stratum(package, stratum: str):
    return next(row for row in package.records["documents"] if stratum in row["strata"])


def case_mentions(package, case):
    units = set(case["unit_ids"])
    return [row for row in package.records["mentions"] if row["unit_id"] in units]


def case_text(package, case):
    return "\n".join(
        row["text"] for row in package.records["units"] if row["unit_id"] in case["unit_ids"]
    )


def gold_transform(root: Path, digest: str, output: Path, candidate="transform.text"):
    from deidflow.benchmarks.transformation_runner import run_transformation_benchmark

    return run_transformation_benchmark(
        root,
        manifest_sha256=digest,
        candidate=candidate,
        profile="transformation-descriptive-v1",
        output=output,
    )["result"]


@pytest.mark.parametrize("mode,documents", [("contextual", 10), ("strict", 10), ("ambiguous", 2)])
def test_fixed_public_generator_is_reproducible_and_explicit_about_evidence(
    tmp_path, mode, documents
):
    left, right = tmp_path / "left", tmp_path / "right"
    package, summary = generated_package(left, mode)
    assert generate(right, mode) == summary
    assert {path.name: path.read_bytes() for path in left.iterdir()} == {
        path.name: path.read_bytes() for path in right.iterdir()
    }
    assert summary["documents"] == len(package.records["documents"]) == documents
    assert set(package.manifest["profiles"]) == PROFILES
    assert package.manifest["generation"]["random_algorithm"] == "none"
    assert package.manifest["generation"]["seeds"] == {}
    assert all(not item["case_ids"] for item in package.manifest["partitions"].values())
    assert all(row["panel"] == "known_regression" for row in package.records["documents"])
    assert all(
        row["ratified"] is False
        for key, row in package.records.items()
        if key.startswith("profile-")
    )
    assert package.records["evidence-9"] == DECISION.read_bytes()
    assert summary["decision"]["status"] == "ratified"
    assert summary["executable_profile_ratified"] is False
    assert summary["quality_ratified"] is False
    assert summary["quality"] == "DESCRIPTIVE_ONLY"
    serialized = json.dumps(summary, ensure_ascii=False)
    for row in package.records["sources"]:
        assert row["origin_kind"] == "synthetic"
        assert row["personal_data_status"] == "fictional"
        assert row["exposure"]["training"] == row["exposure"]["tuning"] == "unknown"
        assert row["exposure"]["candidate_exposure"] == "known"
    units = {row["unit_id"]: row["text"] for row in package.records["units"]}
    for row in package.records["mentions"]:
        assert row["annotation_provenance"]["method"] == "synthetic_fixture"
        if row["entity_type"] == "PERSON":
            assert units[row["unit_id"]][row["start"] : row["end"]] not in serialized


def test_contextual_and_strict_share_detection_reference_with_opposite_clinical_expectations(
    tmp_path,
):
    contextual, _ = generated_package(tmp_path / "contextual")
    strict, _ = generated_package(tmp_path / "strict", "strict")
    assert contextual.records["mentions"] == strict.records["mentions"]
    assert contextual.records["units"] == strict.records["units"]
    assert contextual.records["documents"] == strict.records["documents"]
    mentions = {row["mention_id"]: row for row in contextual.records["mentions"]}
    assert CLINICAL <= {row["entity_type"] for row in mentions.values()}
    actions = []
    for package, clinical_action, policy in (
        (contextual, "preserve", "preserve_context"),
        (strict, "remove", "strict"),
    ):
        assert all(
            row["clinical_policy"] == policy
            for key, row in package.records.items()
            if key.startswith("profile-")
        )
        indexed = {}
        for row in package.records["expectations"]:
            if row["mention_id"] is None:
                continue
            mention = mentions[row["mention_id"]]
            expected = clinical_action if mention["entity_type"] in CLINICAL else "remove"
            assert row["action"] == expected
            indexed[(row["profile_id"], row["mention_id"])] = row["action"]
        actions.append(indexed)
    assert set(actions[0]) == set(actions[1])
    assert any(actions[0][key] != actions[1][key] for key in actions[0])


def test_guide_reference_and_actual_review_records_are_hash_bound_to_authored_spans(tmp_path):
    from datetime import datetime

    package, summary = generated_package(tmp_path / "corpus")
    guide, reference = package.records["evidence-1"], package.records["evidence-3"]
    ledger = json.loads(package.records["evidence-2"])
    snapshot = json.loads(reference)
    assert hashlib.sha256(guide).hexdigest() == summary["guide_sha256"]
    assert hashlib.sha256(reference).hexdigest() == summary["reference_sha256"]
    assert snapshot["guide_sha256"] == ledger["guide_sha256"] == summary["guide_sha256"]
    assert ledger["reference_sha256"] == summary["reference_sha256"]
    assert ledger["status"] == summary["reference_status"]
    authored = {row["mention_id"]: row for row in snapshot["annotations"]}
    units = {row["unit_id"]: row["text"] for row in package.records["units"]}
    for mention in package.records["mentions"]:
        row = authored[mention["mention_id"]]
        assert units[row["unit_id"]][row["start"] : row["end"]] == row["surface"]
        assert row["start"] == mention["start"]
        assert row["end"] == mention["end"]
    if ledger["status"] == "draft":
        assert ledger["reviews"] == []
        assert all(row["annotation_state"] == "draft" for row in package.records["documents"])
        assert all(
            not row["annotation_provenance"]["reviews"] for row in package.records["mentions"]
        )
    else:
        reviews = {row["review_id"]: row for row in ledger["reviews"]}
        assert len(reviews) >= 2
        assert len({row["actor_id"] for row in reviews.values()}) == len(reviews)
        all_cases = {row["case_id"] for row in snapshot["cases"]}
        for review in reviews.values():
            assert review["actor_type"] == "agent"
            assert review["candidate_predictions_seen"] is False
            assert review["reference_sha256"] == summary["reference_sha256"]
            assert review["guide_sha256"] == summary["guide_sha256"]
            assert set(review["case_ids"]) == all_cases
            assert datetime.fromisoformat(review["reviewed_at"]).utcoffset().total_seconds() == 0
        for mention in package.records["mentions"]:
            assert set(mention["annotation_provenance"]["reviews"]) == set(reviews)


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate_actor",
        "rejected_outcome",
        "missing_case_decision",
        "wrong_case_decision",
        "naive_timestamp",
        "stale_guide",
        "stale_reference",
    ],
)
def test_public_generator_rejects_invalid_review_evidence_before_writing(
    tmp_path, monkeypatch, damage
):
    from deidflow.benchmarks import contextual_package

    # These are deliberately synthetic test actors in a substituted resource
    # directory. They never become the shipped actual-agent review evidence.
    package, summary = generated_package(tmp_path / "authored")
    resource_dir = tmp_path / "test-resources"
    resource_dir.mkdir()
    (resource_dir / "_contextual_guide.md").write_bytes(package.records["evidence-1"])
    ledger = json.loads(package.records["evidence-2"])
    snapshot = json.loads(package.records["evidence-3"])
    all_cases = [row["case_id"] for row in snapshot["cases"]]
    decisions = {
        row["case_id"]: "unresolved_challenge" if row["ambiguous"] else "accepted"
        for row in snapshot["cases"]
    }
    ledger["status"] = "agent_reviewed"
    ledger["reviews"] = [
        {
            "review_id": f"r-{index:x}",
            "actor_type": "agent",
            "actor_id": f"synthetic-test-fixture-actor-{index}",
            "reviewed_at": "2026-11-06T18:00:00Z",
            "candidate_predictions_seen": False,
            "guide_sha256": summary["guide_sha256"],
            "reference_sha256": summary["reference_sha256"],
            "outcome": "accepted_with_unresolved_challenges",
            "case_ids": all_cases,
            "case_decisions": decisions.copy(),
        }
        for index in (1, 2)
    ]
    row = ledger["reviews"][1]
    if damage == "duplicate_actor":
        row["actor_id"] = ledger["reviews"][0]["actor_id"]
    elif damage == "rejected_outcome":
        row["outcome"] = "rejected"
    elif damage == "missing_case_decision":
        row["case_decisions"].pop(all_cases[0])
    elif damage == "wrong_case_decision":
        row["case_decisions"][all_cases[-1]] = "accepted"
    elif damage == "naive_timestamp":
        row["reviewed_at"] = "2026-11-06T18:00:00"
    elif damage == "stale_guide":
        row["guide_sha256"] = "0" * 64
    elif damage == "stale_reference":
        row["reference_sha256"] = "0" * 64
    (resource_dir / "_contextual_reviews.json").write_text(json.dumps(ledger), encoding="utf-8")
    monkeypatch.setattr(contextual_package, "files", lambda package_name: resource_dir)
    with pytest.raises(ValueError, match="Invalid contextual reference evidence"):
        generate(tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_public_gold_transform_protects_identifiers_and_obeys_each_clinical_mode(tmp_path):
    results = []
    for mode in ("contextual", "strict"):
        root = tmp_path / mode
        _, summary = generated_package(root, mode)
        result = gold_transform(root, summary["manifest_sha256"], tmp_path / (mode + "-report"))
        assert result["attempt_status"] == "completed"
        assert result["verification_status"] == "COMPLETED"
        assert result["metrics"]["required_documents"] == 10
        assert result["metrics"]["joint_success_documents"] == 10
        assert result["metrics"]["leaked_mentions"] == 0
        assert result["metrics"]["unverifiable_mentions"] == 0
        assert result["metrics"]["retention"] == 1
        assert result["quality"] == "DESCRIPTIVE_ONLY"
        results.append(result["metrics"])
    assert results[0]["required_context_spans"] > results[1]["required_context_spans"]
    assert results[0]["required_removals"] < results[1]["required_removals"]


def test_erasing_negations_doses_and_relationships_cannot_satisfy_contextual_profile(tmp_path):
    from deidflow.benchmarks.transformation_runner import (
        TransformationCandidate,
        TransformationOutput,
    )
    from deidflow.transformations import SourceMap

    root = tmp_path / "corpus"
    package, summary = generated_package(root)
    all_text = "\n".join(row["text"] for row in package.records["units"])
    assert "niega" in all_text.casefold()
    assert "500 mg" in all_text
    assert "madre" in all_text.casefold()

    def erase(text, gold, policy):
        return TransformationOutput("", (SourceMap(0, len(text), 0, 0, ("PERSON",), "suppress"),))

    result = gold_transform(
        root,
        summary["manifest_sha256"],
        tmp_path / "erased-report",
        TransformationCandidate("candidate-11", "0" * 64, erase),
    )
    assert result["metrics"]["required_context_spans"] > 0
    assert result["metrics"]["preserved_context_spans"] == 0
    assert result["metrics"]["retention"] == 0
    assert result["metrics"]["overtransformed_chars"] > 0
    assert result["metrics"]["joint_success_documents"] == 0


def test_punctuation_pair_preserves_exact_text_offsets_and_family_membership(tmp_path):
    package, _ = generated_package(tmp_path / "corpus")
    dotted = case_with_stratum(package, "narrative_dotted")
    undotted = case_with_stratum(package, "narrative_undotted")
    dotted_text, undotted_text = case_text(package, dotted), case_text(package, undotted)
    assert "." in dotted_text
    assert "." not in undotted_text
    assert dotted["template_family_id"] == undotted["template_family_id"]
    assert dotted["group_id"] == undotted["group_id"]
    assert "Á" in dotted_text or "í" in dotted_text
    values = []
    for case, text in ((dotted, dotted_text), (undotted, undotted_text)):
        values.append(
            [
                (row["entity_type"], text[row["start"] : row["end"]])
                for row in case_mentions(package, case)
            ]
        )
    assert values[0] == values[1]


def test_confirmed_nested_and_crossed_mentions_survive_admission_without_flattening(tmp_path):
    package, _ = generated_package(tmp_path / "corpus")
    nested = case_mentions(package, case_with_stratum(package, "nested_clinical"))
    crossed = case_mentions(package, case_with_stratum(package, "crossed_mentions"))
    assert any(
        first["start"] <= second["start"] < second["end"] <= first["end"]
        and (first["start"], first["end"]) != (second["start"], second["end"])
        for first in nested
        for second in nested
    )
    assert any(
        first["start"] < second["start"] < first["end"] < second["end"]
        for first in crossed
        for second in crossed
    )
    assert all(row["certainty"] == "confirmed" for row in nested + crossed)


def test_homonyms_are_distinct_and_unresolved_aliases_are_not_linked_by_name(tmp_path):
    package, _ = generated_package(tmp_path / "corpus")
    homonyms = case_with_stratum(package, "distinct_homonyms")
    units = {row["unit_id"]: row["text"] for row in package.records["units"]}
    identities = defaultdict(set)
    for row in case_mentions(package, homonyms):
        if row["entity_type"] == "PERSON":
            identities[units[row["unit_id"]][row["start"] : row["end"]]].add(row["entity_id"])
    assert any(None not in items and len(items) > 1 for items in identities.values())
    assert "distintas" in case_text(package, homonyms).casefold()
    alias = case_mentions(package, case_with_stratum(package, "alias_unresolved"))
    persons = [row for row in alias if row["entity_type"] == "PERSON"]
    assert len(persons) >= 2
    assert all(row["certainty"] == "confirmed" for row in persons)
    assert all(row["entity_id"] is None and row["identity_evidence"] is None for row in persons)


def test_only_explicit_continuity_links_cross_document_identities(tmp_path):
    package, _ = generated_package(tmp_path / "corpus")
    first = case_with_stratum(package, "continuity_origin")
    followup = case_with_stratum(package, "continuity_followup")
    assert first["group_id"] == followup["group_id"]
    persons = [
        row
        for row in case_mentions(package, first) + case_mentions(package, followup)
        if row["entity_type"] == "PERSON"
    ]
    assert len({row["entity_id"] for row in persons}) == 1
    assert persons[0]["entity_id"] is not None
    mention_ids = {row["mention_id"] for row in persons}
    assert any(
        row["identity_evidence"]["method"] == "explicit_reference"
        and set(row["identity_evidence"]["mention_ids"]) & (mention_ids - {row["mention_id"]})
        for row in persons
    )


def test_unresolved_challenge_is_separate_and_never_gets_gold_transformation_success(tmp_path):
    package, summary = generated_package(tmp_path / "ambiguous", "ambiguous")
    confirmed, _ = generated_package(tmp_path / "contextual")
    assert all(row["certainty"] == "confirmed" for row in confirmed.records["mentions"])
    assert all(row["certainty"] == "ambiguous" for row in package.records["mentions"])
    assert all(row["annotation_state"] == "unresolvable" for row in package.records["documents"])
    assert all(row["entity_id"] is None for row in package.records["mentions"])
    assert {row["action"] for row in package.records["expectations"]} == {"review_required"}
    assert {row["case_id"] for row in package.records["documents"]}.isdisjoint(
        row["case_id"] for row in confirmed.records["documents"]
    )
    result = gold_transform(
        tmp_path / "ambiguous", summary["manifest_sha256"], tmp_path / "challenge-report"
    )
    assert result["verification_status"] == "REVIEW_REQUIRED"
    assert result["metrics"]["required_documents"] == 2
    assert result["metrics"]["review_required_spans"] > 0
    assert result["metrics"]["joint_success_documents"] == 0


@pytest.mark.parametrize("mode", ["unknown", "contextual-v1", "", None, True, []])
def test_invalid_mode_is_rejected_without_creating_output(tmp_path, mode):
    with pytest.raises(ValueError):
        generate(tmp_path / "rejected", mode)
    assert not (tmp_path / "rejected").exists()


def test_receipt_pin_and_clinical_decisions_are_checked_before_output(tmp_path):
    from deidflow.benchmarks.contextual_package import generate_contextual_package

    with pytest.raises(ValueError, match="Invalid operational decision receipt"):
        generate_contextual_package(
            tmp_path / "wrong-pin", mode="contextual", decision=DECISION, decision_sha256="0" * 64
        )
    assert not (tmp_path / "wrong-pin").exists()
    altered = json.loads(DECISION.read_bytes())
    altered["D3"]["contextual-v1"]["clinical_facts_negation_dose_quantity_relations"] = "remove"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError):
        generate_contextual_package(
            tmp_path / "wrong-policy",
            mode="contextual",
            decision=changed,
            decision_sha256=hashlib.sha256(changed.read_bytes()).hexdigest(),
        )
    assert not (tmp_path / "wrong-policy").exists()


def test_existing_package_is_never_overwritten(tmp_path):
    root = tmp_path / "corpus"
    generate(root)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    with pytest.raises(ValueError):
        generate(root, "strict")
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


@pytest.mark.parametrize(
    "stratum,relation",
    [("narrative_undotted", "template_family_id"), ("continuity_followup", "explicit_identity")],
)
def test_cross_partition_family_or_identity_blocks_independence_even_with_new_group(
    tmp_path, stratum, relation
):
    from deidflow.benchmarks.independence import SimilarityProfile, audit_independence
    from deidflow.benchmarks.synthetic_package import write_package_records

    package, _ = generated_package(tmp_path / "original")
    records = deepcopy(package.records)
    document = next(row for row in records["documents"] if stratum in row["strata"])
    # A relabeled group and erased derivation must not defeat the remaining
    # family/explicit-identity evidence in the independent relationship audit.
    document.update(
        panel=None,
        partition="validation",
        group_id="g-ffff",
        root_document_id=document["case_id"],
        parent_case_id=None,
        variant_id=None,
        perturbation_recipe=None,
    )
    crossed = write_package_records(tmp_path / "crossed", records, package.manifest)
    result = audit_independence(
        tmp_path / "crossed",
        manifest_sha256=crossed.manifest_sha256,
        similarity=SimilarityProfile(),
    )["result"]
    assert result["independence_accredited"] is False
    assert result["relations"][relation] > 0
    assert result["cross_partition_components"] > 0
    assert "CROSS_PARTITION_COMPONENT" in {row["code"] for row in result["diagnostics"]}
