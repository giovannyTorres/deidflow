from __future__ import annotations

import json

import pytest

from deidflow.benchmarks.span_corpus import (
    GRETEL_LABELS,
    load_gretel_finance,
    load_span_jsonl,
    register_local_files,
    verify_registered_files,
)


def _write(path, records):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", "utf-8")
    return path


def test_span_jsonl_round_trip_and_label_mapping(tmp_path):
    path = _write(
        tmp_path / "spans.jsonl",
        [
            {
                "id": "a",
                "text": "Cliente: Ana Ruiz",
                "spans": [{"start": 9, "end": 17, "label": "name"}],
            },
            {"id": "b", "text": "Sin datos personales."},
        ],
    )
    corpus = load_span_jsonl(path, split="validation", labels={"name": "PERSON"})
    assert [e.id for e in corpus.examples] == ["a", "b"]
    span = corpus.examples[0].spans[0]
    assert (span.entity_type, corpus.examples[0].text[span.start : span.end]) == (
        "PERSON",
        "Ana Ruiz",
    )
    assert corpus.metadata["gold_span_count"] == 1 and corpus.examples[0].split == "validation"


@pytest.mark.parametrize(
    "record",
    [
        {"id": "a", "text": "abc", "spans": [{"start": 0, "end": 9, "label": "X"}]},
        {"id": "a", "text": "abc", "spans": [{"start": 2, "end": 1, "label": "X"}]},
        {"id": "a", "text": "a c", "spans": [{"start": 1, "end": 2, "label": "X"}]},
        {"id": "a", "text": "abc", "spans": [{"start": 0, "end": 1, "label": ""}]},
        {"id": "a", "text": "abc", "spans": [{"start": 0, "end": 1, "label": "unmapped"}]},
        {"id": "", "text": "abc"},
        {"id": "a", "text": 5},
    ],
)
def test_span_jsonl_rejects_malformed_gold(tmp_path, record):
    path = _write(tmp_path / "bad.jsonl", [record])
    with pytest.raises(ValueError):
        load_span_jsonl(path, labels={"X": "PERSON"})


def test_span_jsonl_rejects_duplicate_ids_and_keys(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        load_span_jsonl(_write(tmp_path / "d.jsonl", [{"id": "a", "text": "x"}] * 2))
    (tmp_path / "k.jsonl").write_text('{"id": "a", "id": "b", "text": "x"}\n', "utf-8")
    with pytest.raises(ValueError):
        load_span_jsonl(tmp_path / "k.jsonl")


def _gretel(text, spans, language="Spanish"):
    return {
        "document_type": "Bank Statement",
        "language": language,
        "generated_text": text,
        "pii_spans": json.dumps(spans),
    }


def test_gretel_finance_selects_language_and_maps_labels(tmp_path):
    text = "Titular: Ana Ruiz, IBAN ES9121000418450200051332."
    path = _write(
        tmp_path / "train.jsonl",
        [
            _gretel(
                text,
                [
                    {"start": 9, "end": 17, "label": "name"},
                    {"start": 24, "end": 48, "label": "iban"},
                ],
            ),
            _gretel("Holder: Ann Roe.", [{"start": 8, "end": 15, "label": "name"}], "English"),
        ],
    )
    corpus = load_gretel_finance([path], language="Spanish", split="test")
    assert len(corpus.examples) == 1 and corpus.provenance_kind == "synthetic_financial"
    kinds = {(s.entity_type, text[s.start : s.end]) for s in corpus.examples[0].spans}
    assert kinds == {("PERSON", "Ana Ruiz"), ("BANK_ACCOUNT", "ES9121000418450200051332")}
    assert corpus.metadata["documents_by_language"] == {"English": 1, "Spanish": 1}


def test_gretel_finance_fails_closed_on_schema_changes(tmp_path):
    unknown = _write(
        tmp_path / "u.jsonl", [_gretel("abc", [{"start": 0, "end": 3, "label": "new_type"}])]
    )
    with pytest.raises(ValueError, match="unknown span label"):
        load_gretel_finance([unknown])
    missing = _write(tmp_path / "m.jsonl", [{"language": "Spanish", "text": "abc"}])
    with pytest.raises(ValueError, match="missing expected field"):
        load_gretel_finance([missing])
    assert set(GRETEL_LABELS.values()) >= {"PERSON", "BANK_ACCOUNT", "PAYMENT_CARD", "NATIONAL_ID"}


def test_registered_files_are_pinned_outside_repository(tmp_path):
    source = _write(tmp_path / "train.jsonl", [_gretel("abc", [])])
    manifest = register_local_files(
        "gretel_finance", [source], tmp_path / "verified", {"license": "Apache-2.0"}
    )
    assert manifest["license"] == "Apache-2.0" and "train.jsonl" in manifest["files"]
    root = tmp_path / "verified/gretel_finance"
    assert verify_registered_files(root, "gretel_finance")["verified_corpus_files"] == 1
    (root / "train.jsonl").write_text("changed", "utf-8")
    with pytest.raises(ValueError, match="differ"):
        verify_registered_files(root, "gretel_finance")


def test_gretel_files_select_published_split(tmp_path):
    from deidflow.benchmarks.span_corpus import gretel_files

    for name in ("Spanish_train-00000-of-00001.jsonl", "Spanish_test-00000-of-00001.jsonl"):
        _write(tmp_path / name, [_gretel("abc", [])])
    (tmp_path / "README.md").write_text("card", "utf-8")
    assert [p.name for p in gretel_files(tmp_path, "test")] == ["Spanish_test-00000-of-00001.jsonl"]
    assert [p.name for p in gretel_files(tmp_path, "train")] == [
        "Spanish_train-00000-of-00001.jsonl"
    ]
    with pytest.raises(ValueError, match="train and test"):
        gretel_files(tmp_path, "dev")


def test_hash_split_is_deterministic_and_keeps_duplicates_together():
    from deidflow.benchmarks.datasets import Example
    from deidflow.benchmarks.span_corpus import hash_split

    examples = [Example(str(i), f"documento {i % 50}", (), "train", "t") for i in range(400)]
    train, validation = hash_split(examples, validation_fraction=0.2)
    again = hash_split(examples, validation_fraction=0.2)
    assert [e.id for e in validation] == [e.id for e in again[1]]
    assert {e.text for e in train}.isdisjoint({e.text for e in validation})
    assert all(e.split == "validation" for e in validation) and 0 < len(validation) < 400
    with pytest.raises(ValueError):
        hash_split(examples, validation_fraction=1.0)
