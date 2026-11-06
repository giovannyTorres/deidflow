"""Regression tests for verified replacement ranges and private CLI I/O."""

import json
import os
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus, Rule
from deidflow.product_cli import _bundle, _key, _read, _write, main


@pytest.mark.parametrize(
    "replacement", ["Contacto: ana@example.com", "[GENERALIZED] ana@example.com"]
)
def test_arbitrary_generalization_cannot_exempt_retained_source_pii(replacement):
    engine = DeidEngine()
    result = engine.deidentify_text(
        "ana@example.com",
        policy=Policy(default=Rule("generalize", replacement=replacement), require_ner=False),
    )
    assert result.status == ReleaseStatus.BLOCKED
    assert "RESIDUAL_FINDINGS" in result.issues


def test_neutral_context_preset_keeps_legacy_fingerprint():
    legacy = Policy(
        name="llm",
        default=Rule("indexed"),
        entities={"DEMOGRAPHIC": Rule("keep"), "AGE": Rule("bucket", width=10)},
        token_scope="session",
        independent_check="proper_nouns",
    )
    assert Policy.llm(keep_clinical=False).fingerprint() == legacy.fingerprint()
    assert Policy.context().name == "context"
    assert Policy.context().rule("MEDICATION").action == "keep"


def test_keygen_is_private_exclusive_and_does_not_print_key(tmp_path, capsys):
    path = tmp_path / "key"
    assert main(["keygen", str(path)]) == 0
    assert len(_key(path)) == 32
    assert json.loads(capsys.readouterr().out) == {"status": "KEY_CREATED"}
    before = path.read_bytes()
    assert main(["keygen", str(path)]) == 3
    assert path.read_bytes() == before
    assert str(path) not in capsys.readouterr().err


def test_key_replacement_during_open_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "key"
    _write(path, b"a" * 32)
    replacement = tmp_path / "replacement"
    _write(replacement, b"b" * 32)
    original_open = os.open

    def substitute(name, flags, *args, **kwargs):
        if Path(name) == path:
            os.replace(replacement, path)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", substitute)
    with pytest.raises(ValueError, match="changed"):
        _key(path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission and FIFO semantics")
def test_read_rejects_fifo_without_blocking_and_key_rejects_public_permissions(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular"):
        _read(fifo, 10)
    key = tmp_path / "key"
    key.write_bytes(b"x" * 32)
    key.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        _key(key)


def test_bundle_is_all_or_nothing_and_preserves_existing_output(tmp_path):
    target = tmp_path / "output"
    with pytest.raises(RuntimeError):
        with _bundle(target) as stage:
            _write(stage / "candidate.txt", b"fictional candidate")
            raise RuntimeError("injected failure")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
    with _bundle(target) as stage:
        _write(stage / "candidate.txt", b"first")
    with pytest.raises(FileExistsError):
        with _bundle(target) as stage:
            _write(stage / "candidate.txt", b"second")
    assert (target / "candidate.txt").read_bytes() == b"first"
    assert list(tmp_path.iterdir()) == [target]
