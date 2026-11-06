from __future__ import annotations

import pytest
from test_benchmark_package import fixture_records, save_manifest, write_fixture

from deidflow.core import Finding


def detection_package(root, *, labels=None, records=None):
    records = fixture_records() if records is None else records
    records["profile-1"]["profile_id"] = "detection-descriptive-v1"
    for expectation in records["expectations"]:
        expectation["profile_id"] = "detection-descriptive-v1"
    manifest, _ = write_fixture(root, records)
    manifest["profiles"] = {
        "detection-descriptive-v1": manifest["profiles"]["email-descriptive-v1"]
    }
    if labels is not None:
        manifest["scope"]["entity_types"] = labels
        for coverage in manifest["annotation_coverage"]:
            coverage["exhaustive_entity_types"] = labels
    return manifest, save_manifest(root, manifest)


def test_multientity_report_keeps_empty_categories_and_exact_one_to_one_counts(tmp_path):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark

    package = tmp_path / "package"
    labels = [
        "RFC",
        "CURP",
        "CLABE",
        "PAYMENT_CARD",
        "PHONE",
        "EMAIL",
        "PERSON",
        "ADDRESS",
        "DIAGNOSIS",
        "MEDICAL_CONDITION",
        "MEDICATION",
        "TREATMENT",
        "CLINICAL_OBSERVATION",
    ]
    _, digest = detection_package(package, labels=labels)

    def detect(text):
        return (
            [
                Finding("EMAIL", 8, 24, 0.9, "fixture"),
                Finding("EMAIL", 8, 24, 0.9, "fixture"),
                Finding("EMAIL", 8, 23, 0.9, "fixture"),
            ]
            if text.startswith("Correo:")
            else []
        )

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate=DetectionCandidate("candidate-f", "0" * 64, detect),
        profile="detection-descriptive-v1",
        output=tmp_path / "result",
    )

    result = report["result"]
    assert set(result["metrics"]) == set(labels)
    assert result["metrics"]["EMAIL"]["true_positives"] == 1
    assert result["metrics"]["EMAIL"]["false_positives"] == 1
    assert result["metrics"]["EMAIL"]["false_negatives"] == 1
    assert result["metrics"]["EMAIL"]["precision"] == 0.5
    assert result["metrics"]["EMAIL"]["recall"] == 0.5
    assert result["metrics"]["EMAIL"]["f1"] == 0.5
    assert result["metrics"]["RFC"]["support"] == 0
    assert result["metrics"]["RFC"]["f1"] is None
    assert result["metrics"]["RFC"]["undefined_reason"]["f1"] == "NO_GOLD_OR_PREDICTIONS"
    assert result["aggregates"]["micro"]["f1"] == 0.5
    assert result["aggregates"]["macro"]["f1"] == 0.5
    assert result["aggregates"]["macro"]["defined_entities"]["f1"] == 1
    assert result["quality"] == "DESCRIPTIVE_ONLY"


@pytest.mark.parametrize("uncertainty", ["partial", "ambiguous"])
def test_uncertain_reference_is_reported_without_inventing_primary_false_positives(
    tmp_path, uncertainty
):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark

    records = fixture_records()
    if uncertainty == "ambiguous":
        records["mentions"][1]["certainty"] = "ambiguous"
    package = tmp_path / "package"
    manifest, _ = detection_package(package, records=records)
    if uncertainty == "partial":
        manifest["annotation_coverage"][0]["exhaustive_entity_types"] = []
    digest = save_manifest(package, manifest)

    def detect(text):
        return (
            [Finding("EMAIL", 8, 24, 0.9, "fixture"), Finding("LOCATION", 0, 6, 0.9, "fixture")]
            if text.startswith("Correo:")
            else []
        )

    result = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate=DetectionCandidate("candidate-f", "0" * 64, detect),
        profile="detection-descriptive-v1",
        output=tmp_path / "result",
    )["result"]

    assert result["metrics"]["EMAIL"]["support"] == 0
    assert result["metrics"]["EMAIL"]["false_positives"] == 0
    assert result["metrics"]["EMAIL"]["f1"] is None
    assert result["partial_diagnostics"]["EMAIL"]["known_true_positives"] == 1
    assert result["partial_diagnostics"]["EMAIL"]["known_false_negatives"] == (
        1 if uncertainty == "partial" else 0
    )
    assert result["partial_diagnostics"]["EMAIL"]["false_positives"] is None
    assert result["exclusions"]["out_of_scope_predictions"] == 1
    assert result["exclusions"]["ambiguous_mentions"] == (1 if uncertainty == "ambiguous" else 0)
    assert result["reference_conformity"] == "INCOMPLETE"
    assert result["aggregates"]["macro"]["f1"] is None
    assert result["aggregates"]["macro"]["undefined_reason"]["f1"] == "NO_DEFINED_ENTITIES"


def test_wrong_entity_type_is_an_error_not_a_gold_guided_alias(tmp_path):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark

    package = tmp_path / "package"
    _, digest = detection_package(package, labels=["EMAIL", "PERSON"])

    def detect(text):
        return [Finding("PERSON", 8, 24, 0.9, "fixture")] if text.startswith("Correo:") else []

    result = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate=DetectionCandidate("candidate-f", "0" * 64, detect),
        profile="detection-descriptive-v1",
        output=tmp_path / "result",
    )["result"]
    assert result["metrics"]["EMAIL"]["true_positives"] == 0
    assert result["metrics"]["EMAIL"]["false_negatives"] == 2
    assert result["metrics"]["PERSON"]["false_positives"] == 1


def test_failed_candidate_keeps_required_support_per_entity(tmp_path):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark

    package = tmp_path / "package"
    _, digest = detection_package(package, labels=["EMAIL", "PERSON"])

    def detect(_text):
        return [Finding("EMAIL", 1, 999, 0.9, "fixture")]

    result = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate=DetectionCandidate("candidate-f", "0" * 64, detect),
        profile="detection-descriptive-v1",
        output=tmp_path / "result",
    )["result"]
    assert result["attempt_status"] == "candidate_error"
    assert result["metrics"] == {"EMAIL": None, "PERSON": None}
    assert result["aggregates"] is None
    assert result["execution"]["required_support_by_entity"] == {"EMAIL": 2, "PERSON": 0}


def test_real_detector_keeps_original_unicode_and_crlf_offsets(tmp_path):
    import hashlib

    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    text = "😀 Café\r\nCorreo: a.b@example.test."
    records["units"][0].update(text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
    records["sources"][0]["content_sha256"] = records["units"][0]["text_sha256"]
    records["mentions"][0].update(start=16, end=32)
    records["mentions"][1].update(start=18, end=32)
    package = tmp_path / "package"
    _, digest = detection_package(package, records=records)
    result = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="detection-descriptive-v1",
        output=tmp_path / "result",
    )["result"]
    assert result["metrics"]["EMAIL"]["true_positives"] == 1
    assert result["metrics"]["EMAIL"]["false_negatives"] == 1
