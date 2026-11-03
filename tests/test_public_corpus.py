from __future__ import annotations

import json
from pathlib import Path

import pytest

from deidflow.benchmarks.public_corpus import (
    SOURCES,
    _outside_repository,
    acquire,
    load_meddocan,
    load_tab,
    verify_acquired_corpus,
)


def test_source_registry_pins_license_and_hashes():
    for source in SOURCES.values():
        assert len(source["commit"]) == 40 and len(source["archive_sha256"]) == 64
        assert source["archive_url"].startswith("https://codeload.github.com/")
        assert source["license"] in {"CC-BY-4.0", "MIT"} and source["gold"]


def test_acquisition_cannot_store_raw_data_in_repo():
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="outside"):
        _outside_repository(root / "private")
    with pytest.raises(ValueError):
        acquire("unknown-source", root / "unknown")


def test_brat_exact_unicode_offsets_and_mapping(tmp_path):
    split = tmp_path / "dev"
    split.mkdir()
    (split / "example.txt").write_bytes("Nombre: María Luna\n".encode())
    (split / "example.ann").write_text(
        "T1\tNOMBRE_SUJETO_ASISTENCIA 8 18\tMaría Luna\n", encoding="utf-8"
    )
    corpus = load_meddocan(tmp_path, "dev")
    assert corpus.examples[0].spans[0].entity_type == "PERSON"
    assert corpus.examples[0].text[8:18] == "María Luna"
    assert corpus.provenance_kind == "semi_synthetic_clinical"


@pytest.mark.parametrize(
    "annotation", ["T1\tUNSUPPORTED 0 4\ttest", "T1\tFECHAS 0 4\twrong", "T1\tFECHAS 0 2;3 4\ttest"]
)
def test_invalid_public_gold_is_not_silently_accepted(tmp_path, annotation):
    split = tmp_path / "test"
    split.mkdir()
    (split / "example.txt").write_text("test", encoding="utf-8")
    (split / "example.ann").write_text(annotation, encoding="utf-8")
    with pytest.raises(ValueError):
        load_meddocan(tmp_path)


def _mention(start, end, text, identifier="DIRECT"):
    return {
        "entity_type": "PERSON",
        "start_offset": start,
        "end_offset": end,
        "span_text": text,
        "identifier_type": identifier,
    }


def test_tab_uses_reviewed_annotator_and_masks_only_direct_quasi(tmp_path):
    record = {
        "doc_id": "synthetic-1",
        "text": "Ana y Luis",
        "quality_checked": ["b"],
        "annotations": {
            "a": {"entity_mentions": [_mention(6, 10, "Luis")]},
            "b": {"entity_mentions": [_mention(0, 3, "Ana"), _mention(6, 10, "Luis", "NO_MASK")]},
        },
    }
    (tmp_path / "echr_test.json").write_text(json.dumps([record]), encoding="utf-8")
    corpus = load_tab(tmp_path)
    assert len(corpus.examples[0].spans) == 1 and corpus.examples[0].spans[0].start == 0
    assert corpus.metadata["ignored_no_mask_mentions"] == 1
    assert corpus.language == "en"


def test_tab_requires_reviewed_gold(tmp_path):
    (tmp_path / "echr_test.json").write_text(
        json.dumps([{"doc_id": "x", "text": "Ana", "quality_checked": [], "annotations": {}}])
    )
    with pytest.raises(ValueError, match="reviewed"):
        load_tab(tmp_path)


def test_benchmark_integrity_refuses_modified_or_extra_corpus(tmp_path, monkeypatch):
    import hashlib
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("repo/data/echr_train.json", "[]")
        bundle.writestr("repo/data/echr_dev.json", "[]")
        bundle.writestr("repo/data/echr_test.json", "[]")
    payload = buffer.getvalue()
    (tmp_path / "tab.zip").write_bytes(payload)
    root = tmp_path / "tab"
    root.mkdir()
    for split in ("train", "dev", "test"):
        (root / f"echr_{split}.json").write_text("[]")
    monkeypatch.setitem(SOURCES["tab"], "archive_sha256", hashlib.sha256(payload).hexdigest())
    assert verify_acquired_corpus(root, "tab")["verified_corpus_files"] == 3
    (root / "echr_extra.json").write_text("[]")
    with pytest.raises(ValueError, match="Unexpected"):
        verify_acquired_corpus(root, "tab")
    (root / "echr_extra.json").unlink()
    (root / "echr_test.json").write_text("changed")
    with pytest.raises(ValueError, match="differs"):
        verify_acquired_corpus(root, "tab")
