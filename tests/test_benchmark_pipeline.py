from __future__ import annotations

import pytest
from benchmark_case_fixtures import fixture_records, profile_package

from deidflow.engine import ReleaseStatus, Result


def run_pipeline(tmp_path, callback="rules.mx", *, capability=None, preserve_negation=False):
    from deidflow.benchmarks.pipeline_runner import PipelineCandidate, run_pipeline_benchmark

    records = fixture_records()
    if capability:
        records["documents"][0]["capabilities_required"].append(capability)
    for expectation in records["expectations"]:
        expectation["acceptable_release_states"] = ["APPROVED", "REVIEW_REQUIRED", "BLOCKED"]
    if preserve_negation:
        records["expectations"].append(
            dict(
                records["expectations"][0],
                expectation_id="e-3",
                mention_id=None,
                unit_id="u-2",
                case_id="c-2",
                start=0,
                end=2,
                action="preserve",
                allowed_operators=["keep"],
                verification="exact_preservation",
            )
        )
    _, digest = profile_package(tmp_path / "package", records, "pipeline-descriptive-v1", ["EMAIL"])
    return run_pipeline_benchmark(
        tmp_path / "package",
        manifest_sha256=digest,
        candidate=callback
        if isinstance(callback, str)
        else PipelineCandidate("candidate-a", "0" * 64, callback),
        profile="pipeline-descriptive-v1",
        output=tmp_path / "report",
    )["result"]


def test_pipeline_uses_existing_real_engine_and_independent_reference(tmp_path):
    result = run_pipeline(tmp_path)
    assert result["execution"]["required_documents"] == 2
    assert result["execution"]["completed_documents"] == 2
    assert result["detection"]["metrics"]["EMAIL"]["true_positives"] == 1
    assert result["verdicts"]["quality"] == "DESCRIPTIVE_ONLY"
    assert result["scope"]["track"] == "pipeline"


def test_blocking_everything_does_not_claim_zero_risk_or_joint_success(tmp_path):
    result = run_pipeline(tmp_path, lambda text, policy: Result(ReleaseStatus.BLOCKED))
    assert result["metrics"]["joint_success_documents"] == 0
    assert result["release"]["states"]["BLOCKED"] == 2
    assert result["release"]["no_output_documents"] == 2
    assert result["release"]["approved"]["emitted"] == 0
    assert result["release"]["approved"]["risk_lower"] is None
    assert result["release"]["emitted"]["risk_upper"] is None
    assert result["metrics"]["required_removals"] == 2


@pytest.mark.parametrize("status", list(ReleaseStatus))
def test_all_observable_outputs_are_checked_regardless_of_status(tmp_path, status):
    result = run_pipeline(tmp_path, lambda text, policy: Result(status, output_text=text))
    assert result["release"]["states"][status.value] == 2
    assert result["release"]["emitted"]["emitted"] == 2
    assert result["release"]["emitted"]["leaked"] == 1
    assert result["metrics"]["leaked_mentions"] == 2
    if status == ReleaseStatus.APPROVED:
        assert result["release"]["approved"]["leaked"] == 1
        assert result["release"]["approved"]["risk_lower"] == 0.5


def test_incomplete_maps_produce_empirical_risk_bounds(tmp_path):
    def invalid_maps(text, policy):
        return Result(ReleaseStatus.APPROVED, output_text="[REDACTED]")

    result = run_pipeline(tmp_path, invalid_maps)
    assert result["release"]["emitted"] == {
        "emitted": 2,
        "leaked": 0,
        "unverified_without_confirmed_leak": 2,
        "completely_inspected": 0,
        "risk_lower": 0,
        "risk_upper": 1,
        "undefined_reason": None,
    }
    assert result["verdicts"]["technical_conformity"] == "INCOMPLETE"
    assert result["verdicts"]["quality"] == "DESCRIPTIVE_ONLY"


def test_copied_identifier_with_invalid_maps_is_still_confirmed_residual(tmp_path):
    def duplicate(text, policy):
        return Result(ReleaseStatus.APPROVED, output_text=text + text)

    result = run_pipeline(tmp_path, duplicate)
    assert result["release"]["approved"]["leaked"] == 1
    assert result["metrics"]["removed_mentions"] == 0
    assert result["metrics"]["required_removals"] == 2
    assert result["verdicts"]["technical_conformity"] == "FAIL"


def test_error_keeps_support_and_sanitizes_public_report(tmp_path):
    def fail(text, policy):
        raise RuntimeError("FICTIONAL_CANARY_FILENAME_TOKEN")

    result = run_pipeline(tmp_path, fail)
    assert result["execution"]["required_documents"] == 2
    assert result["execution"]["failed_documents"] == 2
    assert result["metrics"]["required_removals"] == 2
    assert result["metrics"]["joint_success_documents"] == 0
    assert result["detection"]["metrics"]["EMAIL"] is None
    assert result["verdicts"]["execution"] == "INCOMPLETE"
    assert "FICTIONAL_CANARY" not in (tmp_path / "report" / "report.json").read_text()


def test_malformed_response_is_counted_without_dropping_case(tmp_path):
    result = run_pipeline(tmp_path, lambda text, policy: {"status": "APPROVED"})
    assert result["release"]["states"]["ERROR"] == 2
    assert result["execution"]["failed_documents"] == 2
    assert result["metrics"]["joint_success_documents"] == 0


def test_changed_suffix_does_not_reduce_required_support(tmp_path):
    def alter(text, policy):
        return Result(
            ReleaseStatus.APPROVED, output_text=text.replace("example.test", "example.tesX")
        )

    result = run_pipeline(tmp_path, alter)
    assert result["metrics"]["required_removals"] == 2
    assert result["metrics"]["removed_mentions"] == 0
    assert result["metrics"]["joint_success_documents"] == 1
    assert result["release"]["emitted"]["unverified_without_confirmed_leak"] == 1


def test_malformed_maps_do_not_hide_observable_output(tmp_path):
    def malformed(text, policy):
        return Result(ReleaseStatus.APPROVED, output_text=text, mappings=None)

    result = run_pipeline(tmp_path, malformed)
    assert result["release"]["emitted"]["emitted"] == 2
    assert result["release"]["approved"]["leaked"] == 1
    assert result["metrics"]["leaked_mentions"] == 2


@pytest.mark.parametrize("field", ["output_path", "safe_jsonl", "audit_path"])
def test_secondary_text_artifact_with_residual_is_not_ignored(tmp_path, field):
    from deidflow import DeidEngine

    engine = DeidEngine(language="es", country="MX", offline=True)

    def additional_artifact(text, policy):
        result = engine.deidentify_text(text, policy=policy)
        artifact = tmp_path / "FICTIONAL_FILENAME.txt"
        artifact.write_text(text)
        setattr(result, field, artifact)
        return result

    result = run_pipeline(tmp_path, additional_artifact)
    assert result["release"]["approved"]["leaked"] == 1
    assert result["metrics"]["leaked_mentions"] == 2
    assert result["metrics"]["removed_mentions"] == 0
    assert result["metrics"]["joint_success_documents"] == 1
    assert result["verdicts"]["technical_conformity"] == "FAIL"
    assert "FICTIONAL_FILENAME" not in (tmp_path / "report" / "report.json").read_text()


def test_missing_required_capability_cannot_pass_conformity(tmp_path):
    result = run_pipeline(tmp_path, capability="unimplemented_text_capability")
    assert result["verdicts"]["technical_conformity"] == "INCOMPLETE"
    assert result["verdicts"]["execution"] == "INCOMPLETE"
    assert result["execution"]["pending_documents"] == 1
    assert result["diagnostics"] == [{"code": "REQUIRED_CAPABILITY_NOT_EVALUATED", "count": 1}]


def test_secondary_output_losing_negation_reduces_context_and_retention(tmp_path):
    from deidflow import DeidEngine
    from deidflow.transformations import SourceMap

    engine = DeidEngine(language="es", country="MX", offline=True)

    def lose_negation(text, policy):
        result = engine.deidentify_text(text, policy=policy)
        if text.startswith("No"):
            result.mappings = [SourceMap(0, 2, 0, 2, ("REGION",), "keep")]
            artifact = tmp_path / "secondary.txt"
            artifact.write_text("Si" + text[2:])
            result.output_path = artifact
        return result

    result = run_pipeline(tmp_path, lose_negation, preserve_negation=True)
    assert result["metrics"]["required_context_spans"] == 1
    assert result["metrics"]["preserved_context_spans"] == 0
    assert result["metrics"]["retention"] < 1
    assert result["metrics"]["overtransformed_chars"] == 2
    assert result["verdicts"]["technical_conformity"] == "FAIL"


def _coverage_variant(tmp_path, mutate):
    from benchmark_case_fixtures import save_manifest
    from test_benchmark_package import write_fixture

    from deidflow.benchmarks.pipeline_runner import run_pipeline_benchmark

    records = fixture_records()
    for item in records["expectations"]:
        item["acceptable_release_states"] = ["APPROVED", "REVIEW_REQUIRED", "BLOCKED"]
    records["profile-1"]["profile_id"] = "pipeline-descriptive-v1"
    for item in records["expectations"]:
        item["profile_id"] = "pipeline-descriptive-v1"
    root = tmp_path / "package"
    manifest, _ = write_fixture(root, records)
    manifest["profiles"] = {"pipeline-descriptive-v1": manifest["profiles"]["email-descriptive-v1"]}
    manifest["scope"]["entity_types"] = ["EMAIL"]
    for coverage in manifest["annotation_coverage"]:
        coverage["exhaustive_entity_types"] = ["EMAIL"]
    mutate(manifest)
    digest = save_manifest(root, manifest)
    return run_pipeline_benchmark(
        root,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="pipeline-descriptive-v1",
        output=tmp_path / "report",
    )["result"]


def test_nonexhaustive_reference_never_certifies_complete_inspection(tmp_path):
    def nonexhaustive(manifest):
        for coverage in manifest["annotation_coverage"]:
            coverage["exhaustive_entity_types"] = []

    result = _coverage_variant(tmp_path, nonexhaustive)
    assert result["detection"]["reference_conformity"] == "INCOMPLETE"
    assert result["verdicts"]["technical_conformity"] != "PASS"
    assert result["release"]["emitted"]["completely_inspected"] == 0
    emitted = result["release"]["emitted"]
    assert (
        emitted["emitted"] == 0
        or emitted["risk_upper"] > emitted["risk_lower"]
        or (emitted["unverified_without_confirmed_leak"] > 0)
    )


def test_pending_human_review_keeps_approved_risk_uncertain(tmp_path):
    import hashlib
    from pathlib import Path

    from deidflow.benchmarks.pipeline_runner import run_pipeline_benchmark

    root = Path(__file__).resolve().parents[1] / "examples/benchmark-mx-contextual/ambiguous"
    digest = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    result = run_pipeline_benchmark(
        root,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="pipeline-descriptive-v1",
        output=tmp_path / "report",
    )["result"]
    approved = result["release"]["approved"]
    assert result["release"]["emitted"]["completely_inspected"] == 0
    assert approved["emitted"] == 0 or approved["risk_upper"] > approved["risk_lower"]
    assert result["verdicts"]["technical_conformity"] != "PASS"
