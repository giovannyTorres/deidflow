from __future__ import annotations

import json

import pytest

from deidflow.training import (
    ColumnPrediction,
    ColumnSample,
    LocalColumnModel,
    import_span_annotations,
    promotion_gate,
    select_active_learning,
    train_column_model,
    weak_annotations,
)


def test_local_training_holdout_integrity_and_activation(tmp_path):
    pytest.importorskip("sklearn")
    samples = (
        [
            ColumnSample("correo", (f"a{i}@example.org",), "EMAIL", "train", "t1", "e1")
            for i in range(8)
        ]
        + [
            ColumnSample("cantidad", (str(i * 10),), "NON_SENSITIVE", "train", "t2", "e2")
            for i in range(8)
        ]
        + [
            ColumnSample("email", ("heldout@example.net",), "EMAIL", "validation", "v1", "v-e1"),
            ColumnSample("importe", ("920",), "NON_SENSITIVE", "validation", "v2", "v-e2"),
        ]
    )
    manifest = train_column_model(samples, tmp_path / "model", version="1.0")
    assert manifest["activation"] == "STAGED"
    model = LocalColumnModel(tmp_path / "model")
    assert model.predict("correo", ["novel@example.com"]).label == "EMAIL"
    assert model.predict("correo", ["novel@example.com"]).calibrated is False
    model_file = tmp_path / "model" / "model.joblib"
    model_file.write_bytes(model_file.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        LocalColumnModel(tmp_path / "model")


def test_training_rejects_cross_split_leakage_before_loading_deps(tmp_path):
    samples = [
        ColumnSample("x", ("sensitive",), "A", "train", "same"),
        ColumnSample("y", ("secret",), "B", "validation", "same"),
    ]
    with pytest.raises(ValueError, match="leakage"):
        train_column_model(samples, tmp_path / "model", version="v1")
    assert not (tmp_path / "model").exists()


def test_recall_regression_missing_categories_and_nan_block():
    baseline = {"recall_by_type": {"CURP": 1.0}}
    assert (
        promotion_gate({"recall_by_type": {"CURP": 0.9}}, baseline, critical_categories=["CURP"])[
            "status"
        ]
        == "BLOCKED"
    )
    assert (
        promotion_gate({"recall_by_type": {}}, baseline, critical_categories=["CURP"])["status"]
        == "BLOCKED"
    )
    assert (
        promotion_gate(
            {"recall_by_type": {"CURP": float("nan")}}, baseline, critical_categories=["CURP"]
        )["status"]
        == "BLOCKED"
    )
    assert promotion_gate(baseline, baseline, critical_categories=["CURP"])["eligible"]
    assert (
        promotion_gate({"recall_by_type": {"CURP": True}}, baseline, critical_categories=["CURP"])[
            "status"
        ]
        == "BLOCKED"
    )


def test_local_model_rejects_nondict_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text("[]", encoding="utf-8")
    (tmp_path / "model.joblib").write_bytes(b"not deserialized")
    with pytest.raises(ValueError, match="manifest"):
        LocalColumnModel(tmp_path)


def test_entropy_selection_is_stable_and_uncalibrated():
    predictions = [
        ColumnPrediction("a", 0.99, {"a": 0.99, "b": 0.01}),
        ColumnPrediction("a", 0.5, {"a": 0.5, "b": 0.5}),
    ]
    assert select_active_learning(predictions, count=1) == [1]
    with pytest.raises(ValueError):
        select_active_learning([ColumnPrediction("a", 0.5, {"a": 0.9, "b": 0.9})], count=1)


def test_span_annotation_validation_does_not_expose_plaintext(tmp_path):
    path = tmp_path / "annotations.jsonl"
    path.write_text(
        json.dumps({"text": "secreto", "spans": [{"start": 0, "end": 90, "label": "A"}]}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as error:
        import_span_annotations(path)
    assert "secreto" not in str(error.value)
    path.write_text(
        json.dumps({"text": "Ana", "spans": [{"start": 0, "end": 3, "label": "PERSON"}]}) + "\n",
        encoding="utf-8",
    )
    assert import_span_annotations(path, labels={"PERSON"})[0]["spans"][0]["end"] == 3


def test_weak_annotations_mark_source():
    from deidflow.detectors import RuleDetector

    records = list(weak_annotations(["correo: demo@example.org"], RuleDetector()))
    assert records[0]["provenance"] == "weak-supervision-unreviewed"
    assert records[0]["spans"]


def test_schema_provenance_changes_only_for_rule_derived_profiles():
    from deidflow.detectors import CORE_RULES_VERSION, RuleDetector
    from deidflow.structured import profile_column, scan_cell
    from deidflow.training import ScoreCalibrator

    detector = RuleDetector()
    exact = profile_column("nombre", ["Ana"], detector)
    assert exact.model_version == "rules-0.2"
    unchanged = scan_cell("Ana", exact, detector, row=0, column="nombre")[0]
    assert ScoreCalibrator(unchanged.detector, "rules-0.2", 1.0, 0.0, 10).apply(unchanged)
    values = ["Calle Norte 10", "Calle Sur 11", "Calle Este 12"]
    inferred = profile_column("ubicacion", values, detector)
    assert inferred.evidence == ("value_pattern_rate",)
    assert inferred.model_version == f"schema-{CORE_RULES_VERSION}"
    changed = scan_cell(values[0], inferred, detector, row=0, column="ubicacion")[0]
    with pytest.raises(ValueError, match="provenance"):
        ScoreCalibrator(changed.detector, "rules-0.2", 1.0, 0.0, 10).apply(changed)


def test_calibration_never_discards_and_rejects_mixed_scores(tmp_path):
    pytest.importorskip("sklearn")
    from deidflow.core import Finding
    from deidflow.training import ScoreCalibrator, fit_score_calibrator

    findings = [
        Finding("EMAIL", 0, 4, 0.1 + index * 0.08, "rules", protected=True) for index in range(10)
    ]
    calibration = fit_score_calibrator(findings, [index > 4 for index in range(10)])
    predicted = calibration.apply(findings[0])
    assert predicted.protected is True
    assert predicted.start == findings[0].start
    assert predicted.confidence is not None
    path = tmp_path / "calibration.json"
    calibration.save(path)
    assert ScoreCalibrator.load(path) == calibration
    with pytest.raises(ValueError, match="provenance"):
        calibration.apply(Finding("EMAIL", 0, 4, 0.2, "other"))
    with pytest.raises(ValueError, match="incompatible"):
        fit_score_calibrator(
            findings[:-1] + [Finding("EMAIL", 0, 4, 0.2, "other")],
            [index > 4 for index in range(10)],
        )
