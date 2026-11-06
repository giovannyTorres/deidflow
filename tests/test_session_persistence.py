"""Synthetic persistence, authentication and transaction acceptance cases."""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from deidflow import DeidEngine, Finding, Policy, ReleaseStatus, Rule
from deidflow.placeholders import PlaceholderAllocator
from deidflow.session import DeidSession
from deidflow.vault import MemoryVault

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY = b"k" * 32
MODEL = "a" * 64
FORMAT = "deidflow.session.v1"


def policy():
    return Policy(default=Rule("indexed"), require_ner=False)


def session(**kwargs):
    return DeidSession(DeidEngine(), policy=policy(), **kwargs)


def state(path):
    envelope = json.loads(path.read_text())
    encrypted = base64.b64decode(envelope["ciphertext"])
    return json.loads(AESGCM(KEY).decrypt(encrypted[:12], encrypted[12:], FORMAT.encode()))


def write_state(path, payload):
    nonce = b"n" * 12  # Deterministic fixture only, never used for production writes.
    encrypted = nonce + AESGCM(KEY).encrypt(nonce, json.dumps(payload).encode(), FORMAT.encode())
    path.write_text(
        json.dumps({"format": FORMAT, "ciphertext": base64.b64encode(encrypted).decode()})
    )


def test_resume_in_a_fresh_process_preserves_identity_graph_and_counters(tmp_path):
    current = session(model_digest=MODEL)
    first = current.deidentify("ana@example.test y beto@example.test")
    assert first.output_text == "[CORREO_1] y [CORREO_2]"
    saved_graph = current.graph()
    path = tmp_path / "session.enc"
    current.save(path, key=KEY)
    raw = path.read_bytes()
    assert b"ana@example.test" not in raw and b"CORREO" not in raw and b"allocator" not in raw
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    current.close()
    script = """
import json, sys
from deidflow import DeidEngine
from deidflow.session import DeidSession
s = DeidSession.load(sys.argv[1], key=b'k'*32,
                     engine=DeidEngine(), model_digest='a'*64)
previous = s.graph()
r = s.deidentify('beto@example.test y carmen@example.test')
print(json.dumps({'previous': previous, 'output': r.output_text,
                  'restored': s.reidentify(r.output_text).text}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    result = json.loads(completed.stdout)
    assert result["previous"] == saved_graph
    assert result["output"] == "[CORREO_2] y [CORREO_3]"
    assert result["restored"] == "beto@example.test y carmen@example.test"


class Roles:
    def detect_batch(self, texts):
        return [
            [
                Finding(
                    "PERSON",
                    *match.span(),
                    0.99,
                    "synthetic.roles",
                    context=("role:patient", "gender:f"),
                )
                for match in re.finditer(r"Ana Lo\u0301pez|Ana López|Ana Gómez", text)
            ]
            for text in texts
        ]


def test_resume_preserves_role_gender_unicode_and_reserved_tokens(tmp_path):
    current = DeidSession(DeidEngine(nlp=Roles()), policy=policy())
    current.deidentify("[PACIENTE_1] y Ana López")
    path = tmp_path / "session.enc"
    current.save(path, key=KEY)
    resumed = DeidSession.load(path, key=KEY, engine=DeidEngine(nlp=Roles()))
    assert (
        resumed.deidentify("Ana Lo\u0301pez y Ana Gómez").output_text
        == "[PACIENTE_2] y [PACIENTE_3]"
    )
    assert resumed.graph()["entities"][0] == {
        "id": "[PACIENTE_2]",
        "type": "PERSON",
        "role": "patient",
        "gender": "f",
    }
    with pytest.raises(ValueError, match="previously issued"):
        resumed.deidentify("[Paciente 2]")
    with pytest.raises(ValueError, match="not issued"):
        resumed.reidentify("[PACIENTE_1]")


def test_authentication_policy_and_model_binding(tmp_path):
    current = session(model_digest=MODEL)
    current.deidentify("ana@example.test")
    path = tmp_path / "session.enc"
    current.save(path, key=KEY)
    for options in (
        {"key": b"x" * 32, "model_digest": MODEL},
        {"key": KEY},
        {"key": KEY, "model_digest": "b" * 64},
        {"key": KEY, "model_digest": MODEL, "policy": replace(policy(), review_below=0.9)},
    ):
        with pytest.raises(ValueError, match="unauthenticated"):
            DeidSession.load(path, engine=DeidEngine(), **options)
    with pytest.raises(FileExistsError):
        current.save(path, key=KEY)
    raw = json.loads(path.read_text())
    encrypted = bytearray(base64.b64decode(raw["ciphertext"]))
    encrypted[-1] ^= 1
    raw["ciphertext"] = base64.b64encode(encrypted).decode()
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="unauthenticated"):
        DeidSession.load(path, key=KEY, engine=DeidEngine(), model_digest=MODEL)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_value",
        "wrong_value",
        "extra_value",
        "allocator_key",
        "counter",
        "duplicate_identity",
        "reserved_collision",
        "binding",
        "policy",
        "unknown_field",
        "version",
        "expiry",
        "document",
        "occurrence",
        "output_offsets",
        "duplicate_occurrence",
        "extra_identity_field",
    ],
)
def test_authenticated_but_invalid_snapshot_is_rejected(tmp_path, mutation):
    current = session()
    current.deidentify("ana@example.test")
    path = tmp_path / "session.enc"
    current.save(path, key=KEY)
    payload = state(path)
    if mutation == "missing_value":
        payload["values"].clear()
    elif mutation == "wrong_value":
        payload["values"]["[CORREO_1]"] = "other@example.test"
    elif mutation == "extra_value":
        payload["values"]["[CORREO_2]"] = "other@example.test"
    elif mutation == "allocator_key":
        payload["allocator"]["key"] = "b" * 64
    elif mutation == "counter":
        payload["allocator"]["counters"]["CORREO"] = 0
    elif mutation == "duplicate_identity":
        payload["allocator"]["identities"] *= 2
    elif mutation == "reserved_collision":
        payload["allocator"]["reserved"] = ["[CORREO_1]"]
    elif mutation == "binding":
        payload["allocator"]["vault_session_id"] = "x" * 32
    elif mutation == "policy":
        payload["policy"]["default"]["action"] = "keep"
    elif mutation == "unknown_field":
        payload["arbitrary"] = 1
    elif mutation == "version":
        payload["version"] = True
    elif mutation == "expiry":
        payload["expires_at"] = float("nan")
    elif mutation == "document":
        payload["documents"][0]["status"] = "BLOCKED"
    elif mutation == "occurrence":
        payload["occurrences"][0]["entity_id"] = "[CORREO_9]"
    elif mutation == "output_offsets":
        payload["occurrences"][0]["output_end"] += 1
    elif mutation == "duplicate_occurrence":
        payload["occurrences"] *= 2
    elif mutation == "extra_identity_field":
        payload["allocator"]["identities"][0]["original"] = "ana@example.test"
    write_state(path, payload)
    with pytest.raises(ValueError, match="unauthenticated"):
        DeidSession.load(path, key=KEY, engine=DeidEngine())


def test_cleared_or_changed_vault_cannot_be_saved_or_resumed(tmp_path):
    vault = MemoryVault()
    current = session(vault=vault)
    current.deidentify("ana@example.test")
    vault.clear()
    with pytest.raises(ValueError, match="incomplete"):
        current.save(tmp_path / "broken.enc", key=KEY)
    with pytest.raises(ValueError, match="incomplete"):
        session(vault=vault, allocator=current.allocator)
    assert not (tmp_path / "broken.enc").exists()


def test_expiry_is_authenticated_terminal_and_can_only_be_shortened(tmp_path):
    now = [100.0]
    current = session(clock=lambda: now[0])
    current.deidentify("ana@example.test")
    path = tmp_path / "first.enc"
    current.save(path, key=KEY, ttl_seconds=10)
    now[0] = 101
    second = tmp_path / "second.enc"
    current.save(second, key=KEY, ttl_seconds=1000)
    assert state(second)["expires_at"] == 110
    resumed = DeidSession.load(second, key=KEY, engine=DeidEngine(), clock=lambda: now[0])
    now[0] = 110
    assert resumed.placeholders() == {}
    assert resumed.allocator._exact == {} and resumed._occurrences == []
    for operation in (
        lambda: resumed.deidentify("ana@example.test"),
        resumed.graph,
        lambda: resumed.save(tmp_path / "expired.enc", key=KEY),
    ):
        with pytest.raises(ValueError, match="closed"):
            operation()
    with pytest.raises(ValueError):
        DeidSession.load(second, key=KEY, engine=DeidEngine(), clock=lambda: now[0])


@pytest.mark.parametrize("ttl", [0, -1, True, "10", float("nan"), float("inf")])
def test_invalid_snapshot_ttl_does_not_write(tmp_path, ttl):
    path = tmp_path / "bad.enc"
    with pytest.raises(ValueError):
        session().save(path, key=KEY, ttl_seconds=ttl)
    assert not path.exists()


def test_irreversible_session_resumes_without_original_values(tmp_path):
    current = session(reversible=False)
    current.deidentify("ana@example.test")
    path = tmp_path / "session.enc"
    current.save(path, key=KEY)
    assert state(path)["values"] == {}
    resumed = DeidSession.load(path, key=KEY, engine=DeidEngine())
    assert resumed.graph() == current.graph()
    assert resumed.deidentify("ana@example.test").output_text == "[CORREO_1]"
    with pytest.raises(ValueError, match="irreversible"):
        resumed.reidentify("[CORREO_1]")


def test_engine_and_policy_cannot_change_during_session():
    engine = DeidEngine()
    engine.model_digest = MODEL
    current = DeidSession(engine, policy=policy())
    current.deidentify("ana@example.test")
    engine.model_digest = "b" * 64
    with pytest.raises(ValueError, match="model"):
        current.deidentify("beto@example.test")
    engine.model_digest = MODEL
    current.policy = replace(current.policy, review_below=0.9)
    with pytest.raises(ValueError, match="policy"):
        current.graph()


def test_expiry_during_processing_does_not_restore_closed_allocator(monkeypatch):
    now = [100.0]
    current = session(vault=MemoryVault(ttl_seconds=10, clock=lambda: now[0]))
    current.deidentify("ana@example.test")
    original = current.engine.deidentify_text

    def expire(*args, **kwargs):
        result = original(*args, **kwargs)
        now[0] = 110
        return result

    monkeypatch.setattr(current.engine, "deidentify_text", expire)
    with pytest.raises(ValueError, match="expired"):
        current.deidentify("beto@example.test")
    assert current._closed and current.placeholders() == {}
    assert current.allocator._exact == {} and current._documents == []
    assert current._occurrences == [] and len(current.vault) == 0


def test_failed_or_blocked_processing_rolls_back_allocated_tokens(monkeypatch):
    current = session()
    current.deidentify("ana@example.test")
    before = current.graph()
    allocator_before = current.allocator._dump_state()
    original = current.engine.deidentify_text

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(current.engine, "deidentify_text", fail)
    with pytest.raises(RuntimeError):
        current.deidentify("beto@example.test")
    assert current.graph() == before
    assert current.allocator._dump_state() == allocator_before

    def block(*args, **kwargs):
        result = original(*args, **kwargs)
        result.status = ReleaseStatus.BLOCKED
        return result

    monkeypatch.setattr(current.engine, "deidentify_text", block)
    assert current.deidentify("beto@example.test").status == ReleaseStatus.BLOCKED
    assert current.graph() == before and current.allocator._dump_state() == allocator_before


def test_file_protection_failure_removes_snapshot(tmp_path, monkeypatch):
    from deidflow.private import security

    def deny(*args, **kwargs):
        raise security.PrivateError("PRIVATE_PERMISSIONS_FAILED")

    monkeypatch.setattr(security, "protect", deny)
    path = tmp_path / "session.enc"
    with pytest.raises(security.PrivateError):
        session().save(path, key=KEY)
    assert not path.exists()


def test_unknown_envelope_fields_and_oversize_are_rejected(tmp_path, monkeypatch):
    import deidflow.session as module

    path = tmp_path / "session.enc"
    session().save(path, key=KEY)
    envelope = json.loads(path.read_text())
    envelope["expires_at"] = None
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError):
        DeidSession.load(path, key=KEY, engine=DeidEngine())
    monkeypatch.setattr(module, "_MAX_BYTES", 32)
    with pytest.raises(ValueError):
        DeidSession.load(path, key=KEY, engine=DeidEngine())
    with pytest.raises(ValueError, match="size"):
        session().save(tmp_path / "oversize.enc", key=KEY)


def test_snapshot_keys_must_be_raw_32_bytes(tmp_path):
    for key in (None, "k" * 32, b"k" * 31, bytearray(b"k" * 32)):
        with pytest.raises(ValueError, match="32-byte"):
            session().save(tmp_path / "bad.enc", key=key)


def test_allocator_state_rejects_boundaries_and_unknown_fields():
    allocator = PlaceholderAllocator()
    allocator.placeholder("Ana", "PERSON")
    restored = PlaceholderAllocator._from_state(allocator._dump_state())
    assert restored.placeholder("Ana", "PERSON") == "[PERSONA_1]"
    assert restored.placeholder("Beto", "PERSON") == "[PERSONA_2]"
    for key, value in (("identities", [None]), ("use_roles", 1), ("key", "x" * 64)):
        invalid = allocator._dump_state()
        invalid[key] = value
        with pytest.raises(ValueError):
            PlaceholderAllocator._from_state(invalid)


@pytest.mark.parametrize("mutation", ["provenance", "kind", "evidence", "endpoint", "duplicate"])
def test_authenticated_invalid_relationship_is_rejected(tmp_path, mutation):
    current = session()
    current.deidentify("ana@example.test y beto@example.test")
    evidence = [item["id"] for item in current.graph()["occurrences"]]
    current.relate("[CORREO_1]", "relacionado_con", "[CORREO_2]", evidence_ids=evidence)
    path = tmp_path / "relations.enc"
    current.save(path, key=KEY)
    payload = state(path)
    relation = payload["relations"][0]
    if mutation == "provenance":
        relation["provenance"] = "automatic"
    elif mutation == "kind":
        relation["relation"] = "same_person"
    elif mutation == "evidence":
        relation["evidence_ids"] = evidence[:1]
    elif mutation == "endpoint":
        relation["target"] = "[CORREO_99]"
    else:
        payload["relations"] *= 2
    write_state(path, payload)
    with pytest.raises(ValueError, match="unauthenticated"):
        DeidSession.load(path, key=KEY, engine=DeidEngine())


def test_engine_explicit_digest_cannot_override_attached_binding():
    engine = DeidEngine()
    engine.model_digest = MODEL
    with pytest.raises(ValueError, match="conflicts"):
        DeidSession(engine, model_digest="b" * 64)


def test_invalid_receipt_rolls_back_without_storing_wrong_identity(monkeypatch):
    current = session()
    original = current.engine.deidentify_text

    def wrong(*args, **kwargs):
        result = original(*args, **kwargs)
        result.mappings[0] = replace(result.mappings[0], source_start=0, source_end=3)
        return result

    monkeypatch.setattr(current.engine, "deidentify_text", wrong)
    with pytest.raises(ValueError, match="identity"):
        current.deidentify("otro ana@example.test")
    assert current.graph()["documents"] == [] and current.placeholders() == {}
    assert len(current.vault) == 0


class ChangingContext:
    def __init__(self, *context):
        self.context = context

    def detect_batch(self, texts):
        return [
            [
                Finding("PERSON", *match.span(), 0.99, "synthetic.context", context=self.context)
                for match in re.finditer("Ana López", text)
            ]
            for text in texts
        ]


def test_context_constraints_and_alias_keys_survive_encrypted_resumption(tmp_path):
    adapter = ChangingContext()
    current = DeidSession(DeidEngine(nlp=adapter), policy=policy())
    first = current.deidentify("Ana López")
    adapter.context = ("role:patient",)
    assert current.deidentify("Ana López").output_text == first.output_text == "[PERSONA_1]"
    adapter.context = ("gender:f",)
    current.deidentify("Ana López")
    path = tmp_path / "context.enc"
    current.save(path, key=KEY)
    payload = state(path)
    assert payload["allocator"]["version"] == 2
    assert payload["allocator"]["compatible_context"] is True
    assert payload["allocator"]["contexts"] == {"[PERSONA_1]": {"role": "patient", "gender": "f"}}
    adapter2 = ChangingContext("role:patient", "gender:f")
    resumed = DeidSession.load(path, key=KEY, engine=DeidEngine(nlp=adapter2))
    assert resumed.graph() == current.graph()
    assert resumed.deidentify("Ana López").output_text == "[PERSONA_1]"
    assert resumed.graph()["entities"] == [
        {"id": "[PERSONA_1]", "type": "PERSON", "role": "patient", "gender": "f"}
    ]
    assert resumed.reidentify("[PERSONA_1]").text == "Ana López"
    adapter2.context = ("role:clinician", "gender:f")
    assert resumed.deidentify("Ana López").output_text == "[MEDICO_1]"
    before = resumed.graph()
    adapter2.context = ()
    with pytest.raises(ValueError, match="Ambiguous"):
        resumed.deidentify("Ana López")
    assert resumed.graph() == before
    resumed.save(tmp_path / "context2.enc", key=KEY)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "role", "gender", "strict", "alias_hash", "alias_type", "alias_role"],
)
def test_authenticated_context_constraint_tampering_is_rejected(tmp_path, mutation):
    adapter = ChangingContext()
    current = DeidSession(DeidEngine(nlp=adapter), policy=policy())
    current.deidentify("Ana López")
    adapter.context = ("role:patient", "gender:f")
    current.deidentify("Ana López")
    path = tmp_path / "context.enc"
    current.save(path, key=KEY)
    payload = state(path)
    allocator = payload["allocator"]
    if mutation == "missing":
        allocator["contexts"].clear()
    elif mutation == "extra":
        allocator["contexts"]["[PERSONA_2]"] = {"role": None, "gender": None}
    elif mutation in {"role", "gender"}:
        allocator["contexts"]["[PERSONA_1]"][mutation] = None
    elif mutation == "strict":
        allocator["compatible_context"] = False
    elif mutation == "alias_hash":
        allocator["identities"][1]["hash"] = "b" * 64
    elif mutation == "alias_type":
        allocator["identities"][1]["type"] = "ORGANIZATION"
    else:
        allocator["identities"][1]["role"] = "clinician"
    write_state(path, payload)
    with pytest.raises(ValueError, match="unauthenticated"):
        DeidSession.load(path, key=KEY, engine=DeidEngine(nlp=ChangingContext()))


def test_old_allocator_snapshot_loads_in_strict_mode_without_silent_policy_change(tmp_path):
    current = DeidSession(
        DeidEngine(nlp=ChangingContext()), policy=policy(), allocator=PlaceholderAllocator()
    )
    current.deidentify("Ana López")
    path = tmp_path / "legacy.enc"
    current.save(path, key=KEY)
    payload = state(path)
    payload["allocator"]["version"] = 1
    del payload["allocator"]["compatible_context"]
    del payload["allocator"]["contexts"]
    write_state(path, payload)
    restored = DeidSession.load(
        path, key=KEY, engine=DeidEngine(nlp=ChangingContext("role:patient"))
    )
    assert restored.allocator.compatible_context is False
    assert restored.deidentify("Ana López").output_text == "[PACIENTE_1]"
    assert restored.reidentify("[PERSONA_1]").text == "Ana López"


def test_failed_processing_rolls_back_known_context_updates(monkeypatch):
    adapter = ChangingContext()
    current = DeidSession(DeidEngine(nlp=adapter), policy=policy())
    current.deidentify("Ana López")
    before = current.graph()
    allocator_before = current.allocator._dump_state()
    adapter.context = ("role:patient", "gender:f")
    original = current.engine.deidentify_text

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(current.engine, "deidentify_text", fail)
    with pytest.raises(RuntimeError):
        current.deidentify("Ana López")
    assert current.graph() == before and current.allocator._dump_state() == allocator_before
