from __future__ import annotations

import hashlib

import pytest
from benchmark_case_fixtures import fixture_records, profile_package

from deidflow.transformations import SourceMap


def transformation_package(root, *, action="preserve", precedence=()):
    records = fixture_records()
    text = "Persona: Nombre Ficticio. Niega diabetes; dosis: 5 mg. [PERSON]"
    unit = records["units"][0]
    unit.update(text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
    records["sources"][0]["content_sha256"] = unit["text_sha256"]
    start, end = text.index("Nombre"), text.index(". Niega")
    records["mentions"] = [dict(records["mentions"][0], entity_type="PERSON", start=start, end=end)]
    reference = dict(records["expectations"][0], acceptable_release_states=["APPROVED"])
    context = dict(
        reference,
        expectation_id="e-2",
        mention_id=None,
        unit_id="u-1",
        start=text.index("Niega"),
        end=text.index(" [PERSON]"),
        action=action,
        allowed_operators=["keep" if action == "preserve" else "placeholder"],
        verification="exact_preservation" if action == "preserve" else "complete_removal",
    )
    records["expectations"] = [reference, context]
    records["profile-1"]["precedence"] = list(precedence)
    return records


def run_case(tmp_path, *, records=None, callback=None):
    from deidflow.benchmarks.transformation_runner import (
        TransformationCandidate,
        run_transformation_benchmark,
    )

    records = transformation_package(tmp_path) if records is None else records
    _, digest = profile_package(
        tmp_path / "package", records, "transformation-descriptive-v1", ["PERSON"]
    )
    candidate = (
        "transform.text"
        if callback is None
        else TransformationCandidate("candidate-a", "0" * 64, callback)
    )
    return run_transformation_benchmark(
        tmp_path / "package",
        manifest_sha256=digest,
        candidate=candidate,
        profile="transformation-descriptive-v1",
        output=tmp_path / "report",
    )["result"]


def test_gold_transformation_removes_name_and_preserves_clinical_context(tmp_path):
    result = run_case(tmp_path)
    assert result["metrics"]["required_removals"] == 1
    assert result["metrics"]["removed_mentions"] == 1
    assert result["metrics"]["leaked_mentions"] == 0
    assert result["metrics"]["required_context_spans"] == 1
    assert result["metrics"]["preserved_context_spans"] == 1
    assert result["metrics"]["retention"] == 1
    assert result["metrics"]["joint_success_documents"] == 2
    assert result["quality"] == "DESCRIPTIVE_ONLY"
    assert "Nombre Ficticio" not in (tmp_path / "report" / "report.json").read_text()


@pytest.mark.parametrize("attack", ["copy", "partial_mask", "forged_map"])
def test_maps_and_operator_names_cannot_certify_sensitive_content(tmp_path, attack):
    from deidflow.benchmarks.transformation_runner import TransformationOutput

    def transform(text, gold, policy):
        if not gold:
            return TransformationOutput(text, ())
        finding = gold[0]
        start, end = finding.start, finding.end
        original = text[start:end]
        replacement = {
            "copy": original,
            "partial_mask": "*" * (len(original) - 4) + original[-4:],
            "forged_map": "[PERSON]",
        }[attack]
        output = text[:start] + replacement + text[end:]
        output_start = start + (1 if attack == "forged_map" else 0)
        return TransformationOutput(
            output,
            (
                SourceMap(
                    start, end, output_start, start + len(replacement), ("PERSON",), "placeholder"
                ),
            ),
        )

    result = run_case(tmp_path, callback=transform)
    assert result["metrics"]["removed_mentions"] == 0
    assert result["metrics"]["joint_success_documents"] == 1
    if attack in {"copy", "partial_mask"}:
        assert result["metrics"]["leaked_mentions"] == 1
    else:
        assert result["metrics"]["unverifiable_mentions"] == 1


def test_losing_negation_and_dose_reduces_retention_and_joint_success(tmp_path):
    from deidflow.benchmarks.transformation_runner import TransformationOutput

    def erase_all(text, gold, policy):
        return TransformationOutput("", (SourceMap(0, len(text), 0, 0, ("PERSON",), "suppress"),))

    result = run_case(tmp_path, callback=erase_all)
    assert result["metrics"]["preserved_context_spans"] == 0
    assert result["metrics"]["overtransformed_chars"] > 0
    assert result["metrics"]["retention"] == 0
    assert result["metrics"]["joint_success_documents"] == 0


def test_explicit_strict_profile_can_remove_the_same_clinical_content(tmp_path):
    result = run_case(tmp_path, records=transformation_package(tmp_path, action="remove"))
    assert result["metrics"]["required_removals"] == 2
    assert result["metrics"]["removed_mentions"] == 2
    assert result["metrics"]["joint_success_documents"] == 2


@pytest.mark.parametrize(
    "action,verification,operator",
    [
        ("generalize", "unverifiable", "generalize"),
        ("review_required", "human_review", "keep"),
    ],
)
def test_missing_verifier_or_human_decision_cannot_satisfy_profile(
    tmp_path, action, verification, operator
):
    records = transformation_package(tmp_path)
    records["expectations"][0].update(
        action=action, verification=verification, allowed_operators=[operator]
    )
    result = run_case(tmp_path, records=records)
    assert result["metrics"]["joint_success_documents"] == 1
    assert result["verification_status"] == (
        "UNVERIFIABLE" if action == "generalize" else "REVIEW_REQUIRED"
    )


def test_conflicting_expectations_need_precedence_and_keep_overlapping_gold(tmp_path):
    records = transformation_package(tmp_path)
    target = records["mentions"][0]
    records["expectations"][1].update(start=target["start"], end=target["end"])
    with pytest.raises(ValueError, match="Invalid evaluation package"):
        run_case(tmp_path, records=records)


def test_declared_precedence_resolves_only_overlapping_pieces(tmp_path):
    records = transformation_package(tmp_path, precedence=("remove", "preserve"))
    records["expectations"][1]["start"] = records["mentions"][0]["start"]
    result = run_case(tmp_path, records=records)
    assert result["metrics"]["removed_mentions"] == 1
    assert result["metrics"]["preserved_context_spans"] == 1
    assert result["metrics"]["overridden_chars"] > 0


def test_candidate_error_retains_required_transformation_support(tmp_path):
    def fail(*args):
        raise RuntimeError("FICTIONAL_PRIVATE_CANARY")

    result = run_case(tmp_path, callback=fail)
    assert result["attempt_status"] == "candidate_error"
    assert result["execution"]["required_documents"] == 2
    assert result["metrics"]["required_removals"] == 1
    assert result["metrics"]["removed_mentions"] == 0
    assert result["metrics"]["joint_success_documents"] == 0
    assert "FICTIONAL_PRIVATE_CANARY" not in (tmp_path / "report" / "report.json").read_text()


def test_copy_to_another_mapped_region_does_not_accredit_complete_removal(tmp_path):
    from deidflow.benchmarks.transformation_runner import TransformationOutput

    def duplicate(text, gold, policy):
        if not gold:
            return TransformationOutput(text, ())
        item = gold[0]
        name = text[item.start : item.end]
        replacement = "[PERSON]"
        emitted = text[: item.start] + replacement + text[item.end :] + name
        return TransformationOutput(
            emitted,
            (
                SourceMap(
                    item.start,
                    item.end,
                    item.start,
                    item.start + len(replacement),
                    ("PERSON",),
                    "placeholder",
                ),
            ),
        )

    result = run_case(tmp_path, callback=duplicate)
    assert result["metrics"]["removed_mentions"] == 0
    assert result["metrics"]["leaked_mentions"] == 1


def test_verified_placeholder_is_not_leakage_from_accidental_equal_characters(tmp_path):
    records = transformation_package(tmp_path)
    unit = records["units"][0]
    unit["text"] = unit["text"].replace("Nombre Ficticio", "PIERRE X")
    unit["text_sha256"] = hashlib.sha256(unit["text"].encode()).hexdigest()
    records["sources"][0]["content_sha256"] = unit["text_sha256"]
    records["mentions"][0]["end"] = unit["text"].index(". Niega")
    records["expectations"][1].update(
        start=unit["text"].index("Niega"), end=unit["text"].index(" [PERSON]")
    )
    result = run_case(tmp_path, records=records)
    assert result["metrics"]["removed_mentions"] == 1
    assert result["metrics"]["leaked_mentions"] == 0


def test_compatible_operator_intersection_is_used_for_repeated_entity(tmp_path):
    records = transformation_package(tmp_path)
    records["mentions"].append(dict(records["mentions"][0], mention_id="m-2", start=0, end=7))
    records["expectations"][0]["allowed_operators"] = ["placeholder", "redact"]
    records["expectations"].append(
        dict(
            records["expectations"][0],
            expectation_id="e-3",
            mention_id="m-2",
            allowed_operators=["redact"],
        )
    )
    result = run_case(tmp_path, records=records)
    assert result["attempt_status"] == "completed"
    assert result["metrics"]["removed_mentions"] == 2
