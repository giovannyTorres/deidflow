from __future__ import annotations

import pytest

from deidflow.benchmarks.datasets import Example, GoldSpan
from deidflow.benchmarks.public_corpus import PublicCorpus
from deidflow.benchmarks.public_quality import bootstrap_intervals, map_predictions, quality_metrics
from deidflow.core import Finding


def test_bootstrap_resamples_documents_and_is_seeded():
    examples = [
        Example(str(i), "Ana", (GoldSpan("PERSON", 0, 3),), "test", "independent")
        for i in range(20)
    ]
    predicted = [[Finding("PERSON", 0, 3, 0.9, "test")] for _ in examples]
    a = bootstrap_intervals(examples, predicted, repeats=30)
    assert a == bootstrap_intervals(examples, predicted, repeats=30)
    assert a["intervals"]["recall"] == [1.0, 1.0]
    assert bootstrap_intervals(examples[:2], predicted[:2])["status"] == "insufficient_documents"


def test_taxonomy_aliases_do_not_discard_identifier_predictions():
    found = [Finding("NATIONAL_ID", 0, 3, 0.9, "test"), Finding("DATE_OF_BIRTH", 4, 8, 0.9, "test")]
    assert [f.entity_type for f in map_predictions("meddocan", found)] == ["PATIENT_ID", "DATE"]
    assert [f.entity_type for f in map_predictions("tab", found)] == ["CODE", "DATE"]
    with pytest.raises(ValueError):
        map_predictions("unknown", found)


def test_annotated_scope_and_no_fake_ocr_or_calibration():
    corpus = PublicCorpus(
        "meddocan",
        "es",
        "semi_synthetic_clinical",
        (Example("one", "Ana", (GoldSpan("PERSON", 0, 3),), "test", "one"),),
        {},
    )
    result = quality_metrics(corpus, [[Finding("PERSON", 0, 3, 0.8, "test")]], ci_repeats=5)
    assert result["exact"]["recall"] == 1.0
    assert result["exact"]["expected_calibration_error"] is None
    assert result["ocr_cer"] is None and result["table_reconstruction_quality"] is None
    assert result["confidence_intervals"]["status"] == "insufficient_documents"


def test_character_coverage_is_distinct_from_exact_boundary_matching():
    corpus = PublicCorpus(
        "meddocan",
        "es",
        "semi_synthetic_clinical",
        (Example("one", "Ana Sol", (GoldSpan("PERSON", 0, 7),), "test", "one"),),
        {},
    )
    result = quality_metrics(
        corpus,
        [[Finding("PERSON", 0, 3, 0.8, "test"), Finding("PERSON", 3, 7, 0.8, "test")]],
        ci_repeats=5,
    )
    assert result["exact"]["document_leakage_rate"] == 1
    assert result["coverage_leakage"]["character_coverage_document_leakage_rate"] == 0
    assert result["coverage_leakage"]["sensitive_character_recall"] == 1
    assert result["coverage_leakage"]["entity_value_complete_coverage_rate"] == 1
