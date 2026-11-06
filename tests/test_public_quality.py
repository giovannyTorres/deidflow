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


def test_leakage_breakdown_requires_complete_character_coverage():
    from deidflow.benchmarks.public_quality import leakage_breakdown

    example = Example(
        "d",
        "Ana Ruiz vive en Lugo",
        (GoldSpan("PERSON", 0, 8), GoldSpan("LOCATION", 17, 21)),
        "test",
        "independent",
    )
    corpus = PublicCorpus("meddocan", "es", "semi_synthetic_clinical", (example,), {})
    # Partial person coverage is a leak even though the span overlaps.
    partial = leakage_breakdown(corpus, [[Finding("PERSON", 0, 3, 0.9, "t")]])
    assert partial["documents_with_direct_identifier_leak"] == 1
    assert partial["by_type"]["PERSON"]["fully_covered_rate"] == 0.0
    # Any category counts for coverage; typed precision still reports the mismatch.
    full = leakage_breakdown(
        corpus, [[Finding("LOCATION", 0, 8, 0.9, "t"), Finding("LOCATION", 17, 21, 0.9, "t")]]
    )
    assert full["documents_with_direct_identifier_leak"] == 0
    assert full["fully_covered_mention_rate"] == 1.0
    assert full["by_type"]["LOCATION"]["typed_overlap_precision"] == 0.5


def test_role_metrics_use_role_context_only():
    from deidflow.benchmarks.public_quality import role_metrics

    gold = [[(0, 3, "patient"), (10, 14, "clinician"), (20, 24, "family")]]
    predicted = [
        [
            Finding("PERSON", 0, 3, 0.9, "t", context=("role:patient",)),
            Finding("PERSON", 10, 14, 0.9, "t", context=("role:patient",)),
            Finding("PERSON", 20, 24, 0.9, "t"),
        ]
    ]
    result = role_metrics(gold, predicted)
    assert result["patient"]["role_accuracy_when_assigned"] == 1.0
    assert result["clinician"]["role_accuracy_when_assigned"] == 0.0
    assert result["family"]["role_assigned_rate"] == 0.0
    with pytest.raises(ValueError):
        role_metrics(gold, [])


def test_leakage_breakdown_uses_shared_financial_identifier_taxonomy():
    from deidflow.benchmarks.public_quality import leakage_breakdown
    from deidflow.benchmarks.release_gate import DIRECT_IDENTIFIERS

    example = Example("one", "12345", (GoldSpan("BANK_ACCOUNT", 0, 5),), "test", "one")
    corpus = PublicCorpus("gretel_finance", "es", "synthetic", (example,), {})
    result = leakage_breakdown(corpus, [[]])
    assert result["documents_with_direct_identifier_leak"] == 1
    assert result["direct_fully_covered_mention_rate"] == 0.0
    assert result["direct_identifier_types"] == sorted(DIRECT_IDENTIFIERS)
    with pytest.raises(ValueError, match="align"):
        leakage_breakdown(corpus, [])
    with pytest.raises(ValueError, match="offsets"):
        leakage_breakdown(corpus, [[Finding("BANK_ACCOUNT", 0, 6, 0.9, "t")]])
