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


def _git_fixture(tmp_path):
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    origin = tmp_path / "origin"
    (origin / "corpus/train/brat").mkdir(parents=True)
    (origin / "corpus/dev/brat").mkdir(parents=True)
    (origin / "corpus/test/brat").mkdir(parents=True)
    for split in ("train", "dev", "test"):
        (origin / f"corpus/{split}/brat/a.txt").write_bytes(b"Nombre: Ana Ruiz\r\n")
        # Bytes, not text mode: Windows would translate newlines and change digests.
        (origin / f"corpus/{split}/brat/a.ann").write_bytes(
            b"T1\tNOMBRE_SUJETO_ASISTENCIA 8 16\tAna Ruiz\n"
        )
    (origin / "README.md").write_bytes(b"synthetic fixture\n")
    (origin / "unrelated.py").write_bytes(b"print('not extracted')\n")

    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.autocrlf=false", *args],
            cwd=origin,
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.test",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.test",
                "PATH": __import__("os").environ["PATH"],
                "HOME": str(tmp_path),
            },
        ).stdout.decode()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "fixture")
    git("config", "uploadpack.allowAnySHA1InWant", "true")
    return origin, git("rev-parse", "HEAD").strip()


def test_git_acquisition_pins_commit_and_digest_manifest(tmp_path, monkeypatch):
    import hashlib

    from deidflow.benchmarks.public_corpus import acquire_git

    origin, commit = _git_fixture(tmp_path)
    digests = {}
    for split in ("train", "dev", "test"):
        digests[f"meddocan/{split}/a.txt"] = hashlib.sha256(b"Nombre: Ana Ruiz\r\n").hexdigest()
        digests[f"meddocan/{split}/a.ann"] = hashlib.sha256(
            b"T1\tNOMBRE_SUJETO_ASISTENCIA 8 16\tAna Ruiz\n"
        ).hexdigest()
    digests["meddocan/README.md"] = hashlib.sha256(b"synthetic fixture\n").hexdigest()
    pinned = hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()
    monkeypatch.setitem(SOURCES["meddocan"], "repository", origin.as_uri())
    monkeypatch.setitem(SOURCES["meddocan"], "commit", commit)
    monkeypatch.setitem(SOURCES["meddocan"], "file_digest_manifest_sha256", pinned)
    destination = tmp_path / "verified"
    manifest = acquire_git("meddocan", destination)
    assert manifest["extracted_files"] == 7
    # CRLF bytes are read from git objects, not a converted working tree.
    assert (destination / "meddocan/train/a.txt").read_bytes().endswith(b"\r\n")
    assert not (destination / "meddocan/unrelated.py").exists()
    assert (
        verify_acquired_corpus(destination / "meddocan", "meddocan")["verified_corpus_files"] == 6
    )
    assert load_meddocan(destination / "meddocan", "train").examples[0].spans[0].end == 16
    (destination / "meddocan/test/extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        verify_acquired_corpus(destination / "meddocan", "meddocan")
    monkeypatch.setitem(SOURCES["meddocan"], "file_digest_manifest_sha256", "0" * 64)
    with pytest.raises(ValueError, match="digest"):
        acquire_git("meddocan", tmp_path / "other")
    assert not (tmp_path / "other/meddocan").exists()


@pytest.mark.parametrize("variable", ["SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"])
def test_acquisition_honors_explicit_ca_bundle(tmp_path, monkeypatch, variable):
    from deidflow.benchmarks import public_corpus

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    bundle = tmp_path / "bundle.pem"
    bundle.write_text("configured certificate")
    monkeypatch.setenv(variable, str(bundle))
    sentinel = object()
    calls = []

    def context(*, cafile):
        calls.append(cafile)
        return sentinel

    monkeypatch.setattr(public_corpus.ssl, "create_default_context", context)
    assert public_corpus._tls_context() is sentinel
    assert calls == [str(bundle)]


def test_acquisition_missing_explicit_ca_fails_closed(tmp_path, monkeypatch):
    from deidflow.benchmarks.public_corpus import _tls_context

    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    with pytest.raises(FileNotFoundError):
        _tls_context()


def test_meddocan_roles_validate_gold_and_preserve_document_order(tmp_path):
    from deidflow.benchmarks.public_corpus import load_meddocan_roles

    root = tmp_path / "test"
    root.mkdir()
    for name, label, text in [
        ("b", "NOMBRE_SUJETO_ASISTENCIA", "Luis"),
        ("a", "NOMBRE_PERSONAL_SANITARIO", "Ana"),
    ]:
        (root / (name + ".txt")).write_text(text)
        (root / (name + ".ann")).write_text(f"T1\t{label} 0 {len(text)}\t{text}\n")
    assert load_meddocan_roles(tmp_path) == [[(0, 3, "clinician")], [(0, 4, "patient")]]
    (root / "a.ann").write_text("T1\tNOMBRE_PERSONAL_SANITARIO 0 8\tAna\n")
    with pytest.raises(ValueError, match="annotation"):
        load_meddocan_roles(tmp_path)
