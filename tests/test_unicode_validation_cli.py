"""Public validation CLI guards; fake bytes are never admitted as a corpus."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def invoke_gretel(corpus: Path, output: Path):
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validate_unicode_detection.py"),
            "--source-root",
            str(ROOT),
            "--label",
            "candidate",
            "--source",
            "gretel",
            "--corpus",
            str(corpus),
            "--output",
            str(output),
        ],
        cwd=output.parent,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_gretel_validation_rejects_published_test_before_parsing(tmp_path):
    corpus = tmp_path / "Spanish_test-00000-of-00001.parquet"
    corpus.write_bytes(b"fictional invalid parquet; never a real corpus")
    output = tmp_path / "report.json"
    result = invoke_gretel(corpus, output)
    assert result.returncode != 0
    assert "Gretel validation accepts only the pinned Spanish train file" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("present", "diagnostic"),
    [
        (False, "Pinned Gretel Spanish train is unavailable"),
        (True, "Gretel Spanish train SHA-256 differs from the registered pin"),
    ],
)
def test_gretel_validation_requires_available_verified_train_bytes(tmp_path, present, diagnostic):
    corpus = tmp_path / "Spanish_train-00000-of-00001.parquet"
    if present:
        corpus.write_bytes(b"fictional invalid bytes that must never reach a parser")
    output = tmp_path / "report.json"
    result = invoke_gretel(corpus, output)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert "Traceback" not in result.stderr
    assert "fictional invalid bytes" not in result.stderr
    assert not output.exists()


def test_validation_evidence_is_not_overwritten_even_when_corpus_is_missing(tmp_path):
    output = tmp_path / "report.json"
    output.write_text("previous immutable evidence")
    result = invoke_gretel(tmp_path / "missing", output)
    assert result.returncode != 0
    assert "Refusing to overwrite validation evidence" in result.stderr
    assert output.read_text() == "previous immutable evidence"


@pytest.mark.parametrize("symlink", [False, True])
def test_gretel_raw_corpus_cannot_be_loaded_from_another_git_checkout(tmp_path, symlink):
    repository = tmp_path / "other-checkout"
    repository.mkdir()
    (repository / ".git").mkdir()
    corpus = repository / "Spanish_train-00000-of-00001.parquet"
    corpus.write_bytes(b"fictional invalid bytes")
    if symlink:
        alias = tmp_path / corpus.name
        alias.symlink_to(corpus)
        corpus = alias
    output = tmp_path / "report.json"
    result = invoke_gretel(corpus, output)
    assert result.returncode != 0
    assert "Raw Gretel validation assets must remain outside Git checkouts" in result.stderr
    assert not output.exists()
