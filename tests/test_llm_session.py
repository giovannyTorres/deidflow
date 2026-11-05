from __future__ import annotations

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus, Rule
from deidflow.core import Finding
from deidflow.llm import DeidSession
from deidflow.placeholders import PlaceholderAllocator, canonical_placeholder
from deidflow.transformations import transform_text
from deidflow.vault import EncryptedVault, MemoryVault
from deidflow.verification import residual_proper_nouns


def person(start: int, end: int, *context: str) -> Finding:
    return Finding("PERSON", start, end, 0.9, "test", context=context)


def test_allocator_merges_only_unambiguous_compatible_mentions():
    allocator = PlaceholderAllocator()
    patient = [person(0, 5, "role:patient")]
    assert allocator.placeholder("Ana López Ruiz", "PERSON", patient) == "[PACIENTE_1]"
    assert allocator.placeholder("López", "PERSON") == "[PACIENTE_1]"
    assert allocator.placeholder("Ana López", "PERSON") == "[PACIENTE_1]"
    # Conflicting explicit roles never merge.
    doctor = allocator.placeholder("López", "PERSON", [person(0, 5, "role:clinician")])
    assert doctor == "[MEDICO_1]"
    assert allocator.placeholder("Pedro Ruiz", "PERSON", [person(0, 5, "gender:m")]) == (
        "[PERSONA_1]"
    )
    # "Ruiz" now matches two people: ambiguity allocates a new placeholder.
    assert allocator.placeholder("Ruiz", "PERSON") == "[PERSONA_2]"
    # Conflicting grammatical gender never merges either ("el señor Ruiz" / "la señora Ruiz").
    other = PlaceholderAllocator()
    assert other.placeholder("Ruiz", "PERSON", [person(0, 4, "gender:m")]) == "[PERSONA_1]"
    assert other.placeholder("Ruiz", "PERSON", [person(0, 4, "gender:f")]) == "[PERSONA_2]"
    assert "López" not in repr(allocator)


def test_allocator_normalizes_identifiers_and_text():
    allocator = PlaceholderAllocator()
    assert allocator.placeholder("55 1234 5678", "PHONE") == "[TELEFONO_1]"
    assert allocator.placeholder("5512345678", "PHONE") == "[TELEFONO_1]"
    assert allocator.placeholder("Guadalajara", "LOCATION") == "[LUGAR_1]"
    assert allocator.placeholder("GUADALAJARA", "LOCATION") == "[LUGAR_1]"
    assert allocator.placeholder("Zapopan", "LOCATION") == "[LUGAR_2]"
    assert allocator.issued()["[LUGAR_2]"] == ("LOCATION", None)
    with pytest.raises(ValueError):
        PlaceholderAllocator(labels={"PERSON": "bad label"})


def test_indexed_transform_without_session_numbers_per_call():
    text = "Ana y Ana"
    findings = [person(0, 3), person(6, 9)]
    output, mappings = transform_text(text, findings, Policy(default=Rule("indexed")))
    assert output == "[PERSONA_1] y [PERSONA_1]"
    assert {m.action for m in mappings} == {"indexed"}


def test_llm_policy_shape_and_validation():
    policy = Policy.llm()
    assert policy.rule("PERSON").action == "indexed"
    assert policy.rule("DIAGNOSIS").action == "keep"
    assert policy.rule("AGE").action == "bucket"
    assert Policy.llm(keep_clinical=False).rule("DIAGNOSIS").action == "indexed"
    assert policy.independent_check == "proper_nouns"
    assert Policy.from_dict({"independent_check": "proper_nouns"}).independent_check == (
        "proper_nouns"
    )
    with pytest.raises(ValueError):
        Policy(independent_check="maybe")
    # Default policy still requires an evaluated semantic model.
    result = DeidEngine().deidentify_text("Hola Ana", policy=policy)
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues


def test_bucket_keeps_unit_and_spanish_date_shift_keeps_format():
    policy = Policy(entities={"AGE": Rule("bucket", width=10)})
    assert transform_text("58 años", [Finding("AGE", 0, 7, 1, "t")], policy)[0] == "[50,60) años"
    shift = Policy(default=Rule("date_shift", shift_days=3))
    for value, expected in (
        ("2024-01-30", "2024-02-02"),
        ("30/01/2024", "02/02/2024"),
        ("30-01-24", "02-02-24"),
        ("30 de enero de 2024", "2 de febrero de 2024"),
        ("30 de Enero de 2024", "2 de Febrero de 2024"),
    ):
        finding = Finding("DATE", 0, len(value), 1, "t")
        assert transform_text(value, [finding], shift)[0] == expected
    with pytest.raises(ValueError, match="ISO or Spanish"):
        transform_text("ayer", [Finding("DATE", 0, 4, 1, "t")], shift)


def test_memory_vault_ttl_and_repr():
    now = [100.0]
    vault = MemoryVault(ttl_seconds=10, clock=lambda: now[0])
    vault.put("[PERSONA_1]", "Ana")
    assert vault.get("[PERSONA_1]") == "Ana" and "Ana" not in repr(vault)
    now[0] = 111.0
    assert vault.get("[PERSONA_1]") is None and len(vault) == 0
    with pytest.raises(ValueError):
        MemoryVault(ttl_seconds=0)


def test_encrypted_vault_round_trip_and_tamper_detection(tmp_path):
    pytest.importorskip("cryptography")
    key = b"k" * 32
    vault = EncryptedVault(key)
    vault.put("[PERSONA_1]", "Verónica Herrera")
    assert b"Ver" not in vault._values["[PERSONA_1]"]
    path = tmp_path / "vault.json"
    vault.save(path)
    assert "Verónica" not in path.read_text(encoding="utf-8")
    assert EncryptedVault.load(path, key).get("[PERSONA_1]") == "Verónica Herrera"
    with pytest.raises(ValueError):
        EncryptedVault.load(path, b"x" * 32)
    with pytest.raises(FileExistsError):
        vault.save(path)
    with pytest.raises(ValueError):
        EncryptedVault(b"short")


def test_session_vault_keeps_longest_surface_and_close_clears():
    session = DeidSession(DeidEngine(), policy=Policy.llm(require_ner=False))
    session.deidentify("El señor Pérez llegó. Después llegó Juan Pérez Gómez.")
    assert session.reidentify("[PERSONA_1]").text == "Juan Pérez Gómez"
    session.close()
    assert session.reidentify("[PERSONA_1]").unknown == ("[PERSONA_1]",)


def test_irreversible_session_keeps_no_values():
    session = DeidSession(DeidEngine(), policy=Policy.llm(require_ner=False), reversible=False)
    assert session.deidentify("La señora Ana Ruiz").output_text == "La señora [PERSONA_1]"
    with pytest.raises(ValueError):
        session.reidentify("[PERSONA_1]")
    with pytest.raises(ValueError):
        DeidSession(DeidEngine(), reversible=False, vault=MemoryVault())


def test_placeholder_contents_are_not_residual_findings():
    session = DeidSession(DeidEngine(), policy=Policy.llm(require_ner=False))
    result = session.deidentify("La señora Ana Ruiz vive en Guadalajara.")
    assert result.status == ReleaseStatus.APPROVED
    assert result.findings == []


def test_proper_noun_verifier_counts_only_mid_sentence_words():
    assert residual_proper_nouns("Hola. Ella vive aquí.") == 0
    assert residual_proper_nouns("Ella vive con Quintanar.") == 1
    assert residual_proper_nouns("Nombre: [PERSONA_1]", [(8, 19)]) == 0
    assert residual_proper_nouns("Lo vio el Dr. Ruiz el lunes.", allowed=["Ruiz"]) == 0
    assert canonical_placeholder("Médico", "01") == "[MEDICO_1]"


def test_indexed_placeholders_in_tables_share_one_document_scope(tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("correo,nota\na@example.org,x\na@example.org,y\n", encoding="utf-8")
    output = tmp_path / "out.csv"
    policy = Policy(default=Rule("indexed"), require_ner=False)
    DeidEngine().deidentify(source, policy=policy, output=output)
    rows = output.read_text(encoding="utf-8").splitlines()
    assert rows[1].startswith("[CORREO_1]") and rows[2].startswith("[CORREO_1]")
