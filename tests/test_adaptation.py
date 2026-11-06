"""Adaptation cannot promote memorization, missing evidence or unsafe output."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import random
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from deidflow.benchmarks.datasets import Example, GoldSpan
from deidflow.nlp.tagger import FEATURE_SET, FORMAT, FORMAT_VERSION, SpanTagger, feature_key
from deidflow.training import adaptation
from deidflow.training.adaptation import (
    AdaptationConfig,
    PromotionCriteria,
    evaluate_adaptation,
    load_adaptation_jsonl,
    load_adaptation_model,
    stage_span_adaptation,
)
from deidflow.training.tagger import train_span_tagger

pytest.importorskip("numpy")


def _baseline() -> dict:
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "feature_set": FEATURE_SET,
        "labels": ["O", "B-PERSON", "I-PERSON"],
        "start": [0, 0, 0],
        "transitions": [[0, 0, 0] for _ in range(3)],
        "weights": {feature_key("only-in-parent-model"): [[1, 2], [1, 3]]},
        "calibration": None,
        "metadata": {"version": "baseline-fixture-1", "training_data": "fictional fixture"},
    }


def _examples(role: str, count: int = 12, *, domain: bool = True) -> list[Example]:
    rng = random.Random({"train": 1, "validation": 2, "test": 3, "regression": 4}[role])
    result = []
    for index in range(count):
        name = "".join(rng.choice("bcdfglmnrstv") + rng.choice("aeiou") for _ in range(4)).title()
        code = f"HC{100 + rng.randrange(899)}{index:04d}"
        if index % 4 == 0:
            text = f"La movilidad se mantiene estable en la nota ficticia {name.lower()}."
            spans = []
        else:
            text = f"Persona: {name}."
            spans = [GoldSpan("PERSON", text.index(name), text.index(name) + len(name))]
            if domain:
                text += f" Expediente: {code}."
                spans.append(GoldSpan("PATIENT_ID", text.index(code), text.index(code) + len(code)))
            text += f" El seguimiento clínico de {role} continúa."
        result.append(Example(f"{role}-{index}", text, tuple(spans), role, f"group-{role}"))
    return result


def _criteria(**changes) -> PromotionCriteria:
    return PromotionCriteria(
        minimum_documents=8,
        minimum_type_support=5,
        minimum_negative_documents=2,
        minimum_approved_documents=2,
        **changes,
    )


def _stage(path: Path, *, criteria: PromotionCriteria | None = None) -> dict:
    return stage_span_adaptation(
        _baseline(),
        _examples("train", 24),
        _examples("validation"),
        path,
        config=AdaptationConfig(epochs=5, patience=2, seed=17, min_feature_docs=1),
        criteria=criteria or _criteria(),
    )


@pytest.fixture
def staged(tmp_path):
    path = tmp_path / "staged"
    _stage(path)
    return path


def _evaluate(staged: Path, output: Path, **options) -> dict:
    return evaluate_adaptation(
        staged,
        _examples("test"),
        _examples("regression", domain=False),
        output,
        expected_manifest_sha256=(staged / "manifest.sha256").read_text().strip(),
        **options,
    )


def test_warm_start_preserves_labels_weights_and_distinct_model_version(staged):
    candidate = load_adaptation_model(staged / "candidate.json")
    assert candidate["labels"][:3] == _baseline()["labels"]
    assert {"B-PATIENT_ID", "I-PATIENT_ID"} <= set(candidate["labels"])
    assert candidate["weights"][feature_key("only-in-parent-model")] == [[1, 5.0]]
    assert SpanTagger(candidate).model_version.startswith("es-adapt-")
    assert SpanTagger(candidate).model_version != SpanTagger(_baseline()).model_version
    assert candidate["metadata"]["parent_version"] == "baseline-fixture-1"
    assert "training_data" not in candidate["metadata"]
    assert candidate["metadata"]["parent_metadata"]["training_data"] == "fictional fixture"
    assert SpanTagger(candidate).predict(_examples("test")[1].text)


def test_deterministic_staging_and_evaluation_without_raw_text_or_paths(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    _stage(left)
    _stage(right)
    for path in left.iterdir():
        assert path.read_bytes() == (right / path.name).read_bytes()
    one = _evaluate(left, tmp_path / "eval1")
    two = _evaluate(right, tmp_path / "eval2")
    assert one == two
    assert (tmp_path / "eval1/evaluation.json").read_bytes() == (
        tmp_path / "eval2/evaluation.json"
    ).read_bytes()
    for path in [*left.iterdir(), *list((tmp_path / "eval1").iterdir())]:
        text = path.read_text()
        assert str(tmp_path) not in text
        assert "seconds" not in text
        assert _examples("train")[1].text not in text
        assert '"group-train"' not in text


@pytest.mark.parametrize("field", ["id", "template_id", "text"])
def test_stage_rejects_cross_partition_identity_group_or_normalized_content(tmp_path, field):
    train, validation = _examples("train"), _examples("validation")
    value = getattr(train[0], field)
    if field == "text":
        value = "  " + value.upper().replace(" ", "\n\t") + "  "
    validation[0] = replace(validation[0], **{field: value})
    with pytest.raises(ValueError, match="Partition leakage"):
        stage_span_adaptation(_baseline(), train, validation, tmp_path / "no-artifacts")
    assert not (tmp_path / "no-artifacts").exists()


def test_unicode_normalization_rejects_content_reuse(tmp_path):
    first = Example("a", "evolución normal", (), "train", "source-a")
    second = Example("b", "evolucio\u0301n normal", (), "validation", "source-b")
    with pytest.raises(ValueError, match="content_sha256"):
        stage_span_adaptation(_baseline(), [first], [second], tmp_path / "bad")


@pytest.mark.parametrize("role", ["test", "regression", "validation"])
def test_training_never_accepts_wrong_roles_including_replay(tmp_path, role):
    replay = [replace(_examples("train")[1], split=role)]
    with pytest.raises(ValueError, match="Only train"):
        stage_span_adaptation(
            _baseline(),
            _examples("train"),
            _examples("validation"),
            tmp_path / "bad",
            replay=replay,
        )


@pytest.mark.parametrize(
    "change,match",
    [
        ({"id": ""}, "Nonempty"),
        ({"template_id": " "}, "Nonempty"),
        ({"spans": (GoldSpan("PERSON", 1, 4),)}, "complete tagger tokens"),
        ({"spans": (GoldSpan("PERSON", True, 4),)}, "Invalid span"),
        ({"spans": (GoldSpan("PERSON", -1, 4),)}, "Invalid span"),
        ({"spans": (GoldSpan("bad-kind", 0, 2),)}, "Invalid span"),
        ({"spans": (GoldSpan("PERSON", 0, 7), GoldSpan("PERSON", 0, 7))}, "Overlapping"),
    ],
)
def test_invalid_annotations_fail_before_fit(tmp_path, change, match):
    train = _examples("train")
    train[1] = replace(train[1], **change)
    with pytest.raises(ValueError, match=match):
        stage_span_adaptation(_baseline(), train, _examples("validation"), tmp_path / "bad")


def test_loader_requires_group_and_enforces_role_and_unique_json_keys(tmp_path):
    path = tmp_path / "annotations.jsonl"
    record = {
        "id": "a",
        "text": "Persona: Tufalora.",
        "group_id": "family-a",
        "spans": [{"start": 9, "end": 17, "label": "PERSON"}],
        "split": "train",
    }
    # Correct offsets are checked against the actual tokenizer, not just the string bounds.
    record["spans"][0].update(start=9, end=17)
    path.write_text(json.dumps(record))
    assert load_adaptation_jsonl(path, split="train")[0].template_id == "family-a"
    with pytest.raises(ValueError, match="split"):
        load_adaptation_jsonl(path, split="validation")
    del record["group_id"]
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="group_id"):
        load_adaptation_jsonl(path, split="train")
    path.write_text('{"id":"a","id":"b","text":"x","spans":[]}')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_adaptation_jsonl(path, split="train")


@pytest.mark.parametrize("field", ["id", "template_id", "text"])
def test_holdout_contamination_is_rejected_without_running_metrics(
    staged, tmp_path, monkeypatch, field
):
    holdout = _examples("test")
    holdout[0] = replace(holdout[0], **{field: getattr(_examples("train")[0], field)})
    monkeypatch.setattr(
        adaptation, "_measure", lambda *a: pytest.fail("contaminated holdout measured")
    )
    with pytest.raises(ValueError, match="Partition leakage"):
        evaluate_adaptation(
            staged,
            holdout,
            _examples("regression", domain=False),
            tmp_path / "bad",
            expected_manifest_sha256=(staged / "manifest.sha256").read_text().strip(),
        )


def test_holdouts_cannot_share_groups_with_each_other(staged, tmp_path):
    regression = [replace(example, template_id="group-test") for example in _examples("regression")]
    with pytest.raises(ValueError, match="group_sha256"):
        evaluate_adaptation(
            staged,
            _examples("test"),
            regression,
            tmp_path / "bad",
            expected_manifest_sha256=(staged / "manifest.sha256").read_text().strip(),
        )


@pytest.mark.parametrize(
    "artifact", ["manifest.json", "baseline.json", "candidate.json", "training.json"]
)
def test_modified_artifact_cannot_be_evaluated(staged, tmp_path, artifact):
    path = staged / artifact
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest mismatch"):
        _evaluate(staged, tmp_path / "bad")


def test_existing_runs_are_never_overwritten(staged, tmp_path):
    with pytest.raises(FileExistsError):
        _stage(staged)
    _evaluate(staged, tmp_path / "evaluation")
    with pytest.raises(FileExistsError):
        _evaluate(staged, tmp_path / "evaluation")


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode test; Windows uses protected DACL")
def test_artifacts_are_private_before_publication(staged, tmp_path):
    _evaluate(staged, tmp_path / "evaluation")
    for directory in (staged, tmp_path / "evaluation"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir())


def test_evaluation_never_fits_and_unknown_synthetic_evidence_never_promotes(
    staged, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        adaptation, "train_span_tagger", lambda *a, **k: pytest.fail("test used for fitting")
    )
    for evidence in ("unknown", "fictional_demo"):
        result = _evaluate(staged, tmp_path / evidence, evidence_kind=evidence)
        assert result["decision"] == "BLOCKED"
        assert not result["activated"]
        assert any("Independent annotated evidence" in reason for reason in result["reasons"])
        assert any("Baseline training/selection" in reason for reason in result["reasons"])


def test_measured_candidate_can_only_become_eligible_for_manual_review(staged, tmp_path):
    result = _evaluate(
        staged,
        tmp_path / "evaluation",
        evidence_kind="independently_annotated",
        baseline_exposure_verified=True,
    )
    assert result["decision"] == "ELIGIBLE_FOR_MANUAL_REVIEW", result["reasons"]
    assert result["activated"] is False
    assert result["measurements"]["test"]["candidate"]["exact_by_type"]["PATIENT_ID"]["recall"] == 1


def test_missing_critical_support_and_negative_context_block(staged, tmp_path):
    positive = [example for example in _examples("test", domain=False) if example.spans]
    result = evaluate_adaptation(
        staged,
        positive,
        _examples("regression", domain=False),
        tmp_path / "evaluation",
        expected_manifest_sha256=(staged / "manifest.sha256").read_text().strip(),
        evidence_kind="independently_annotated",
        baseline_exposure_verified=True,
    )
    assert result["decision"] == "BLOCKED"
    assert "test/PATIENT_ID: insufficient gold support" in result["reasons"]
    assert "test: insufficient negative context documents" in result["reasons"]


@pytest.mark.parametrize(
    "metric,value,reason",
    [
        ("over_redaction_rate", 0.4, "context overredaction"),
        ("approved_leak_rate", 0.2, "approved output leakage"),
        ("approved_leak_rate", None, "approved output leakage"),
        ("output_sensitive_character_recall", 0.8, "output character recall"),
    ],
)
def test_good_exact_recall_cannot_hide_output_leakage_or_context_destruction(
    staged, tmp_path, monkeypatch, metric, value, reason
):
    real = adaptation._measure

    def measured(model, examples):
        result = real(model, examples)
        if model["metadata"]["version"].startswith("es-adapt-"):
            result["output"][metric] = value
        return result

    monkeypatch.setattr(adaptation, "_measure", measured)
    result = _evaluate(
        staged,
        tmp_path / "bad",
        evidence_kind="independently_annotated",
        baseline_exposure_verified=True,
    )
    assert result["decision"] == "BLOCKED"
    assert any(reason in failure for failure in result["reasons"])


def test_no_approved_documents_is_not_vacuous_success(staged, tmp_path, monkeypatch):
    real = adaptation._measure

    def measured(model, examples):
        result = real(model, examples)
        result["output"]["status_counts"] = {"REVIEW_REQUIRED": len(examples)}
        result["output"]["approved_leak_rate"] = None
        return result

    monkeypatch.setattr(adaptation, "_measure", measured)
    result = _evaluate(
        staged,
        tmp_path / "bad",
        evidence_kind="independently_annotated",
        baseline_exposure_verified=True,
    )
    assert any("insufficient approved output evidence" in failure for failure in result["reasons"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"epochs": True},
        {"seed": 1.0},
        {"min_feature_docs": 0},
        {"prune_below": float("nan")},
        {"prune_below": float("inf")},
    ],
)
def test_invalid_fit_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        AdaptationConfig(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_documents": 0},
        {"minimum_exact_recall": float("nan")},
        {"target_types": ("PERSON", "PERSON")},
        {"target_types": ("bad",)},
    ],
)
def test_invalid_promotion_criteria_is_rejected(kwargs):
    with pytest.raises(ValueError):
        PromotionCriteria(**kwargs)


def test_new_labels_cannot_be_excluded_from_gate(tmp_path):
    with pytest.raises(ValueError, match="cover new labels"):
        _stage(tmp_path / "bad", criteria=_criteria(target_types=("PERSON",)))


def test_gzip_and_json_roundtrip_and_bounded_artifacts(tmp_path, monkeypatch):
    path = tmp_path / "model.json.gz"
    path.write_bytes(gzip.compress(json.dumps(_baseline()).encode()))
    assert load_adaptation_model(path) == _baseline()
    monkeypatch.setattr(adaptation, "MAX_MODEL_BYTES", 8)
    with pytest.raises(ValueError, match="size limit"):
        load_adaptation_model(path)
    with pytest.raises(ValueError, match="size limit"):
        load_adaptation_model(_baseline())


def test_warm_start_is_not_a_cold_retrain():
    model = _baseline()
    original = copy.deepcopy(model)
    candidate, _ = train_span_tagger(
        _examples("train"),
        _examples("validation"),
        initial_model=model,
        epochs=2,
        min_feature_docs=1,
    )
    cold, _ = train_span_tagger(
        _examples("train"), _examples("validation"), epochs=2, min_feature_docs=1
    )
    assert candidate["weights"][feature_key("only-in-parent-model")] == [[1, 5.0]]
    assert feature_key("only-in-parent-model") not in cold["weights"]
    assert model == original


def test_warm_start_ignores_values_on_forbidden_bio_edges():
    baseline = _baseline()
    altered = copy.deepcopy(baseline)
    altered["start"][2] = 1e8
    altered["transitions"][0][2] = 1e8
    normal, _ = train_span_tagger(
        _examples("train"),
        _examples("validation"),
        initial_model=baseline,
        epochs=2,
        min_feature_docs=1,
    )
    masked, _ = train_span_tagger(
        _examples("train"),
        _examples("validation"),
        initial_model=altered,
        epochs=2,
        min_feature_docs=1,
    )
    assert normal["weights"] == masked["weights"]
    assert normal["start"] == masked["start"]
    assert normal["transitions"] == masked["transitions"]


def test_fictional_cli_demo_is_reproducible_and_keeps_builtin_untouched(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "adapt_span_tagger.py"
    models = Path(__file__).parents[1] / "src/deidflow/models"
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in models.glob("*.gz")
    }
    for name in ("first", "second"):
        result = subprocess.run(
            [sys.executable, str(script), "demo", "--output", str(tmp_path / name)],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(result.stdout)
        assert report["decision"] == "BLOCKED"
        assert len(report["reasons"]) == 1
        assert (
            report["measurements"]["test"]["baseline"]["exact_by_type"]["PATIENT_ID"]["recall"] == 0
        )
        assert (
            report["measurements"]["test"]["candidate"]["exact_by_type"]["PATIENT_ID"]["recall"]
            == 1
        )
    for relative in ("staged/manifest.json", "staged/candidate.json", "evaluation/evaluation.json"):
        assert (tmp_path / "first" / relative).read_bytes() == (
            tmp_path / "second" / relative
        ).read_bytes()
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in models.glob("*.gz")
    }
