from __future__ import annotations

from dataclasses import dataclass

import pytest

from deidflow.benchmarks import (
    Example,
    GoldSpan,
    evaluate,
    read_corpus,
    synthetic_corpus,
    write_corpus,
)


@dataclass
class Prediction:
    entity_type: str
    start: int
    end: int
    confidence: float | None = None


def test_corpus_is_seeded_and_split_disjoint(tmp_path):
    train = synthetic_corpus("train", count=10)
    test = synthetic_corpus("test", count=10)
    assert train == synthetic_corpus("train", count=10)
    assert not {e.template_id for e in train} & {e.template_id for e in test}
    train_values = {e.text[s.start : s.end] for e in train for s in e.spans}
    test_values = {e.text[s.start : s.end] for e in test for s in e.spans}
    assert not train_values & test_values
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    assert write_corpus(first, test) == write_corpus(second, test)
    assert read_corpus(first) == test
    for example in test:
        for span in example.spans:
            assert example.text[span.start : span.end]


def test_exact_overlap_false_redaction_and_deduplication():
    examples = [Example("x", "abCDEfgh", (GoldSpan("PERSON", 2, 5),), "test", "t")]
    predictions = [[Prediction("PERSON", 1, 5), Prediction("PERSON", 1, 5)]]
    exact = evaluate(examples, predictions)
    assert exact.true_positives == 0
    assert exact.false_positives == 1
    assert exact.false_negatives == 1
    assert exact.document_leakage_rate == 1
    assert exact.false_redaction_rate == pytest.approx(1 / 5)
    assert exact.entity_level_recall == 1
    assert evaluate(examples, predictions, exact=False).f1 == 1
    assert exact.expected_calibration_error is None


def test_ece_requires_real_calibrated_predictions():
    examples = [Example("x", "Ana", (GoldSpan("PERSON", 0, 3),), "test", "t")]
    result = evaluate(examples, [[Prediction("PERSON", 0, 3, 0.75)]])
    assert result.expected_calibration_error == 0.25
    assert result.calibration_count == 1


def test_metric_rejects_omitted_documents_and_invalid_spans():
    examples = [Example("x", "a", (), "test", "t")]
    with pytest.raises(ValueError):
        evaluate(examples, [])
    with pytest.raises(ValueError):
        evaluate(examples, [[Prediction("PERSON", 0, 2)]])


def test_overlap_matching_finds_maximum_instead_of_greedy_assignment():
    example = Example(
        "x", "abcdefgh", (GoldSpan("PERSON", 2, 4), GoldSpan("PERSON", 5, 7)), "test", "t"
    )
    # Broad candidate appears first. It must be reassigned to the second gold
    # span so the narrow candidate can match the first one.
    result = evaluate(
        [example], [[Prediction("PERSON", 0, 7), Prediction("PERSON", 2, 4)]], exact=False
    )
    assert result.true_positives == 2
    assert result.recall == 1


def test_offline_guard_rejects_even_swallowed_connect_attempt():
    import socket

    from deidflow.benchmarks.runner import offline_network

    with pytest.raises(RuntimeError, match="attempted network"):
        with offline_network():
            try:
                socket.create_connection(("127.0.0.1", 9))
            except RuntimeError:
                pass
