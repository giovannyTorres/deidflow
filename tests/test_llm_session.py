"""Session/storage controls on synthetic values, not detector-quality claims."""

from __future__ import annotations

import base64
import json
import os
import re
import stat

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus, Rule
from deidflow.core import Finding
from deidflow.llm import DeidSession
from deidflow.placeholders import PlaceholderAllocator, canonical_placeholder
from deidflow.transformations import transform_text
from deidflow.vault import EncryptedVault, MemoryVault
from deidflow.verification import residual_proper_nouns


class ExactNames:
    def detect_batch(self, texts):
        return [
            [
                Finding("PERSON", *m.span(), 0.95, "synthetic.names")
                for m in re.finditer(r"Ana López|Ana Gómez|Quintanar", text)
            ]
            for text in texts
        ]


def session(**kwargs):
    return DeidSession(DeidEngine(nlp=ExactNames()), policy=Policy.llm(), **kwargs)


def person(*context):
    return [Finding("PERSON", 0, 3, 0.95, "synthetic.roles", context=context)]


def test_allocator_uses_exact_values_not_weak_coreference():
    allocator = PlaceholderAllocator()
    assert allocator.placeholder("Ana López", "PERSON") == "[PERSONA_1]"
    assert allocator.placeholder("López", "PERSON") == "[PERSONA_2]"
    assert allocator.placeholder("Ana", "PERSON") == "[PERSONA_3]"
    assert allocator.placeholder("Ana Gómez", "PERSON") == "[PERSONA_4]"
    assert allocator.placeholder("Ana López", "PERSON") == "[PERSONA_1]"
    assert allocator.placeholder("Ana Lo\u0301pez", "PERSON") == "[PERSONA_1]"
    assert allocator.placeholder("Ana Lopez", "PERSON") == "[PERSONA_5]"
    assert "López" not in repr(allocator)


def test_allocator_preserves_explicit_roles_genders_types_and_case():
    allocator = PlaceholderAllocator()
    assert allocator.placeholder("Ana", "PERSON", person("role:patient")) == "[PACIENTE_1]"
    assert allocator.placeholder("Ana", "PERSON", person("role:clinician")) == "[MEDICO_1]"
    assert allocator.placeholder("Ana", "PERSON", person("gender:f")) == "[PERSONA_1]"
    assert allocator.placeholder("Ana", "PERSON", person("gender:m")) == "[PERSONA_2]"
    assert allocator.placeholder("ANA", "PERSON", person("gender:f")) == "[PERSONA_3]"
    assert allocator.placeholder("Ana", "LOCATION") == "[LUGAR_1]"
    assert allocator.issued()["[MEDICO_1]"] == ("PERSON", "clinician")
    for bad_label in ("bad label", "PERSONA_"):
        with pytest.raises(ValueError):
            PlaceholderAllocator(labels={"PERSON": bad_label})


@pytest.mark.parametrize("token", ["[PERSONA_1]", "[persona 01]", "PERSONA_1"])
def test_source_tokens_are_reserved_never_allocated(token):
    allocator = PlaceholderAllocator()
    allocator.reserve_source(token)
    allocator.reserve_source(token)
    assert allocator.placeholder("Ana", "PERSON") == "[PERSONA_2]"
    with pytest.raises(ValueError, match="previously issued"):
        allocator.reserve_source("[Persona 2]")


def test_custom_short_and_numeric_labels_round_trip():
    for label in ("A", "P2", "PERSONA_ALT"):
        custom = session(allocator=PlaceholderAllocator(labels={"PERSON": label}))
        result = custom.deidentify("Ana López")
        assert result.output_text == f"[{label}_1]"
        assert custom.reidentify(result.output_text).text == "Ana López"


def test_indexed_transformation_reserves_literals_without_a_session():
    text = "[PERSONA_1] y Ana"
    output, mappings = transform_text(
        text,
        [Finding("PERSON", 14, 17, 0.95, "synthetic")],
        Policy(default=Rule("indexed")),
    )
    assert output == "[PERSONA_1] y [PERSONA_2]"
    assert {m.action for m in mappings} == {"indexed"}


def test_session_reuses_only_exact_values_and_does_not_echo_in_repr():
    current = session()
    first = current.deidentify("Ana López y Ana Gómez")
    second = current.deidentify("Ana Gómez")
    assert first.output_text == "[PERSONA_1] y [PERSONA_2]"
    assert second.output_text == "[PERSONA_2]"
    restored = current.reidentify("[Persona 1] y PERSONA_2; [PERSONA_7]", strict=False)
    assert restored.text == "Ana López y Ana Gómez; [PERSONA_7]"
    assert restored.restored == 2 and restored.unknown == ("[PERSONA_7]",)
    assert "Ana" not in repr(restored)
    with pytest.raises(ValueError, match="not issued"):
        current.reidentify("[PERSONA_7]")


def test_literal_source_placeholder_cannot_restore_an_unrelated_person():
    current = session()
    result = current.deidentify("[PERSONA_1] y Ana López")
    assert result.output_text == "[PERSONA_1] y [PERSONA_2]"
    restored = current.reidentify(result.output_text, strict=False)
    assert restored.text == "[PERSONA_1] y Ana López"
    assert restored.unknown == ("[PERSONA_1]",)
    with pytest.raises(ValueError, match="previously issued"):
        current.deidentify("Texto original [PERSONA_2]")


def test_supplied_empty_ttl_vault_is_preserved_and_expiry_applies():
    now = [100.0]
    vault = MemoryVault(ttl_seconds=10, clock=lambda: now[0])
    current = session(vault=vault)
    assert current.vault is vault
    current.deidentify("Ana López")
    assert len(vault) == 1
    now[0] = 110.0
    assert current.reidentify("[PERSONA_1]", strict=False).unknown == ("[PERSONA_1]",)
    with pytest.raises(ValueError, match="expired"):
        vault.put("[PERSONA_2]", "Synthetic")


def test_supplied_empty_encrypted_vault_is_preserved():
    pytest.importorskip("cryptography")
    vault = EncryptedVault(b"k" * 32)
    current = session(vault=vault)
    assert current.vault is vault
    current.deidentify("Ana López")
    assert isinstance(vault._values["[PERSONA_1]"], bytes)
    assert b"Ana" not in vault._values["[PERSONA_1]"]
    assert current.reidentify("[PERSONA_1]").text == "Ana López"


@pytest.mark.parametrize("ttl", [0, -1, float("nan"), float("inf"), True, "10", 10**1000])
def test_invalid_ttl_is_rejected(ttl):
    with pytest.raises(ValueError):
        MemoryVault(ttl_seconds=ttl)


def test_clock_must_remain_finite():
    now = [1.0]
    vault = MemoryVault(ttl_seconds=10, clock=lambda: now[0])
    vault.put("[PERSONA_1]", "Synthetic")
    now[0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        vault.get("[PERSONA_1]")


def test_encrypted_round_trip_authenticates_session_expiry_and_entries(tmp_path):
    pytest.importorskip("cryptography")
    key = b"k" * 32
    vault = EncryptedVault(key, ttl_seconds=10, clock=lambda: 100)
    vault.put("[PERSONA_1]", "Synthetic Name")
    path = tmp_path / "vault.json"
    vault.save(path)
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    content = path.read_text()
    assert "Synthetic" not in content and "expires" not in content and "session_id" not in content
    loaded = EncryptedVault.load(path, key, clock=lambda: 105)
    assert loaded.session_id == vault.session_id
    assert loaded.get("[PERSONA_1]") == "Synthetic Name"
    with pytest.raises(ValueError):
        EncryptedVault.load(path, b"x" * 32, clock=lambda: 105)
    with pytest.raises(ValueError):
        EncryptedVault.load(path, key, clock=lambda: 110)
    with pytest.raises(FileExistsError):
        vault.save(path)
    payload = json.loads(content)
    ciphertext = bytearray(base64.b64decode(payload["ciphertext"]))
    ciphertext[-1] ^= 1
    payload["ciphertext"] = base64.b64encode(ciphertext).decode()
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        EncryptedVault.load(path, key, clock=lambda: 105)


@pytest.mark.parametrize("mutation", ["expires", "session_id", "version", "entries"])
def test_unauthenticated_metadata_injection_is_rejected(tmp_path, mutation):
    pytest.importorskip("cryptography")
    vault = EncryptedVault(b"k" * 32, ttl_seconds=10, clock=lambda: 0)
    vault.put("[PERSONA_1]", "Synthetic")
    path = tmp_path / "vault.json"
    vault.save(path)
    payload = json.loads(path.read_text())
    payload[mutation] = None
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        EncryptedVault.load(path, b"k" * 32, clock=lambda: 100)


def test_legacy_vaults_and_invalid_payload_metadata_are_rejected(tmp_path):
    pytest.importorskip("cryptography")
    key = b"k" * 32
    path = tmp_path / "vault.json"
    path.write_text(json.dumps({"format": "deidflow.vault.v1", "expires": None, "entries": {}}))
    with pytest.raises(ValueError):
        EncryptedVault.load(path, key)
    # Authenticated but malformed metadata still must fail schema validation.
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    for bad_expiry in (float("nan"), float("inf"), "later", True):
        payload = {
            "format": "deidflow.vault.v2",
            "version": 2,
            "session_id": "a" * 32,
            "expires": bad_expiry,
            "entries": {},
        }
        nonce = b"n" * 12
        encrypted = nonce + AESGCM(key).encrypt(
            nonce, json.dumps(payload).encode(), b"deidflow.vault.v2"
        )
        path.write_text(
            json.dumps(
                {"format": "deidflow.vault.v2", "ciphertext": base64.b64encode(encrypted).decode()}
            )
        )
        with pytest.raises(ValueError):
            EncryptedVault.load(path, key)


def test_file_permission_failure_leaves_no_vault(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    from deidflow.private import security

    def deny(*args, **kwargs):
        raise security.PrivateError("PRIVATE_PERMISSIONS_FAILED")

    monkeypatch.setattr(security, "protect", deny)
    path = tmp_path / "vault.json"
    with pytest.raises(security.PrivateError):
        EncryptedVault(b"k" * 32).save(path)
    assert not path.exists()


def test_loaded_populated_vault_requires_matching_allocator(tmp_path):
    pytest.importorskip("cryptography")
    vault = EncryptedVault(b"k" * 32)
    current = session(vault=vault)
    current.deidentify("Ana López")
    path = tmp_path / "vault.json"
    vault.save(path)
    loaded = EncryptedVault.load(path, b"k" * 32)
    with pytest.raises(ValueError, match="matching"):
        session(vault=loaded)
    resumed = session(vault=loaded, allocator=current.allocator)
    assert resumed.reidentify("[PERSONA_1]").text == "Ana López"


def test_session_close_and_irreversible_mode():
    current = session()
    current.deidentify("Ana López")
    current.close()
    assert current.placeholders() == {} and len(current.vault) == 0
    with pytest.raises(ValueError, match="closed"):
        current.reidentify("[PERSONA_1]")
    with pytest.raises(ValueError, match="closed"):
        current.deidentify("Ana López")
    irreversible = session(reversible=False)
    assert irreversible.deidentify("Ana López").output_text == "[PERSONA_1]"
    with pytest.raises(ValueError, match="irreversible"):
        irreversible.reidentify("[PERSONA_1]")
    with pytest.raises(ValueError):
        session(reversible=False, vault=MemoryVault())


def test_default_policy_still_requires_semantic_adapter_and_check_is_only_heuristic():
    result = DeidEngine().deidentify_text("Sin datos", policy=Policy.llm())
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues
    assert residual_proper_nouns("Hola. Ella vive aquí.") == 0
    assert residual_proper_nouns("Ella vive con Quintanar.") == 1
    assert residual_proper_nouns("Nombre: [PERSONA_1]", [(8, 19)]) == 0
    assert canonical_placeholder("Médico", "01") == "[MEDICO_1]"


def test_proper_noun_review_handles_long_text_and_overlapping_protected_ranges():
    text = "vive con Quintanar y Zyxcorp. " * 5000
    assert residual_proper_nouns(text) == 10000
    first = text.index("Quintanar")
    second = text.index("Zyxcorp")
    assert residual_proper_nouns(text, [(first, second), (first + 2, second + 7)]) == 9998


@pytest.mark.parametrize("same_value", [False, True])
def test_populated_vault_rejects_different_allocator_with_identical_token_names(same_value):
    original = session()
    original.deidentify("Ana López")
    other = session()
    other.deidentify("Ana López" if same_value else "Ana Gómez")
    assert original.placeholders().keys() == other.placeholders().keys()
    with pytest.raises(ValueError, match="matching"):
        session(vault=original.vault, allocator=other.allocator)
    assert original.reidentify("[PERSONA_1]").text == "Ana López"


def test_matching_allocator_rejects_changed_vault_identity():
    original = session()
    original.deidentify("Ana López")
    original.vault.put("[PERSONA_1]", "Ana Gómez")
    with pytest.raises(ValueError, match="match"):
        session(vault=original.vault, allocator=original.allocator)


def test_new_allocator_cannot_resume_manually_populated_vault():
    vault = MemoryVault()
    vault.put("[PERSONA_1]", "Ana López")
    allocator = PlaceholderAllocator()
    assert allocator.placeholder("Ana López", "PERSON") == "[PERSONA_1]"
    with pytest.raises(ValueError, match="matching"):
        session(vault=vault, allocator=allocator)
