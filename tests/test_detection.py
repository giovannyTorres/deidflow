from __future__ import annotations

import os
import re
import socket
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from deidflow.core import DocumentGraph, Finding, Fragment, SourceLocation
from deidflow.detectors import RegexRecognizer, RuleDetector, fuse, non_overlapping
from deidflow.detectors.resolution import resolve_exact_mentions
from deidflow.nlp import SpacyNER
from deidflow.validators import (
    clabe_check_digit,
    curp_check_digit,
    rfc_check_digit,
    validate_card,
    validate_clabe,
    validate_curp,
    validate_rfc,
)


@pytest.mark.parametrize(
    "value,validator",
    [
        ("GODE561231GR8", validate_rfc),
        ("EKU9003173C9", validate_rfc),
        ("XAXX010101000", validate_rfc),
        ("RACW050729MMCSHNA2", validate_curp),
        ("002115016003269411", validate_clabe),
        ("4111 1111 1111 1111", validate_card),
    ],
)
def test_independent_known_checksum_examples(value, validator):
    result = validator(value)
    assert result and result.checksum is True and result.confirmed is False


@pytest.mark.parametrize(
    "value,validator",
    [
        ("GODE561231GR9", validate_rfc),
        ("GODE560231GR8", validate_rfc),
        ("RACW050729MMCSHNA3", validate_curp),
        ("RACW050230MMCSHNA2", validate_curp),
        ("002115016003269412", validate_clabe),
        ("4111111111111112", validate_card),
        ("０１２１１５０１６００３２６９４１１", validate_clabe),
        ("000000000000000000", validate_clabe),
    ],
)
def test_invalid_identifiers_are_not_confirmed(value, validator):
    result = validator(value)
    assert not result and not result.confirmed


@given(st.lists(st.integers(0, 9), min_size=17, max_size=17).filter(lambda x: len(set(x)) > 1))
def test_clabe_checksum_roundtrip_and_mutations(digits):
    prefix = "".join(map(str, digits))
    value = prefix + clabe_check_digit(prefix)
    assert validate_clabe(value)
    assert not validate_clabe(value[:-1] + str((int(value[-1]) + 1) % 10))


@given(st.text(max_size=400))
def test_unicode_spans_are_nonempty_and_within_original(text):
    for finding in RuleDetector().detect(text):
        assert 0 <= finding.start < finding.end <= len(text)


def test_mixed_span_offsets_and_multiline_addresses():
    text = "😀 Nombre: María López Pérez; correo: ana@example.org\nDomicilio: Calle Luna 14\nColonia Centro\nCP 06000\nTeléfono: +52 55 1234 5678"
    values = {(f.entity_type, text[f.start : f.end]) for f in RuleDetector().detect(text)}
    assert ("PERSON", "María López Pérez") in values
    assert ("EMAIL", "ana@example.org") in values
    assert ("PHONE", "+52 55 1234 5678") in values
    assert any(kind == "ADDRESS" and "Colonia Centro\nCP 06000" in value for kind, value in values)


def test_identifiers_across_line_boundaries_and_invalid_still_flagged():
    text = "CURP: RACW0507\n29MMCSHNA2; RFC: GODE56\n1231GR8; incorrecto: GODE561231GR9"
    found = RuleDetector().detect(text)
    assert [(f.entity_type, f.validation) for f in found] == [
        ("CURP", "checksum"),
        ("RFC", "checksum"),
        ("RFC", "invalid"),
    ]
    assert all(f.protected for f in found)


def test_ocr_substitution_is_uncertain_labelled_candidate_not_silent_correction():
    for text, kind in (
        ("CURP: G0DE561231HDFRRN00", "CURP"),
        ("RFC: GODE56O231GR8", "RFC"),
        ("CLABE: 0021150160032694I1", "CLABE"),
    ):
        findings = RuleDetector().detect(text)
        assert len(findings) == 1 and findings[0].entity_type == kind
        assert findings[0].validation == "invalid"
        assert findings[0].confidence is None


@pytest.mark.parametrize("name", ["ana lópez", "ANA LÓPEZ", "María de la Luz Pérez"])
def test_explicit_name_fields_accept_case_and_particles(name):
    text = f"Nombre: {name}; expediente: ABC-123"
    names = [f for f in RuleDetector().detect(text) if f.entity_type == "PERSON"]
    assert any(text[f.start : f.end] == name for f in names)


def test_health_context_avoids_generic_medical_terms():
    assert not RuleDetector().detect("La diabetes y la hipertensión son temas de este manual.")
    text = "Paciente: Ana Luna; diagnóstico: diabetes; tratamiento con metformina."
    types = {f.entity_type for f in RuleDetector().detect(text)}
    assert {"PERSON", "DIAGNOSIS", "MEDICATION"} <= types


def test_secrets_and_pem_entire_payload():
    text = "api_key=abc123xyz; password='s3cr3t';\n-----BEGIN PRIVATE KEY-----\naabbccdd\n-----END PRIVATE KEY-----"
    found = RuleDetector().detect(text)
    assert {f.entity_type for f in found} == {"API_KEY", "CREDENTIAL"}
    assert any("aabbccdd" in text[f.start : f.end] for f in found if f.entity_type == "CREDENTIAL")


def test_contextual_id_labels_and_custom_multiple_labels():
    custom = RegexRecognizer("PROJECT_SECRET", re.compile(r"PRJ-[0-9]{5}"), score=0.9)
    text = "Empleado: EMP-123; cliente id: CUST-22; pasaporte: G12345678; PRJ-43210"
    findings = RuleDetector(recognizers=[custom]).detect(text)
    assert {f.entity_type for f in findings} == {
        "EMPLOYEE_ID",
        "CUSTOMER_ID",
        "PASSPORT",
        "PROJECT_SECRET",
    }
    a = Finding("EMAIL", 0, 5, 0.6, "first", labels=("DIRECT_ID",))
    b = replace(a, score=0.9, detector="second", protected=True)
    merged = fuse([a, b])
    assert len(merged) == 1 and merged[0].score == 0.9 and merged[0].detector == "first|second"
    assert merged[0].labels == ("DIRECT_ID",)


def test_english_explicit_identifier_labels_keep_correct_category():
    text = "employee id: EMP-12345; patient id: PAT-45678; bank account: 12345678"
    found = RuleDetector().detect(text)
    assert {f.entity_type for f in found} == {"EMPLOYEE_ID", "PATIENT_ID", "BANK_ACCOUNT"}


def test_union_overlaps_preserves_entire_covered_area():
    a = Finding("PERSON", 0, 12, 0.9, "a")
    b = Finding("EMAIL", 8, 20, 0.8, "b", protected=True)
    c = Finding("RFC", 20, 33, 0.9, "a")
    united = non_overlapping([b, a, c])
    assert [(f.start, f.end) for f in united] == [(0, 20), (20, 33)]
    assert united[0].entity_type == "EMAIL"


def test_repr_and_validation_exceptions_do_not_include_sensitive_text():
    secret = "private-customer-value"
    fragment = Fragment("one", secret, SourceLocation(fragment_id="one"))
    graph = DocumentGraph("one", "text", [fragment])
    assert secret not in repr(fragment) and secret not in repr(graph)
    with pytest.raises(ValueError) as raised:
        curp_check_digit(secret)
    assert secret not in str(raised.value)


def test_rules_execute_with_network_forbidden(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network use forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    assert RuleDetector().detect("correo: ana@example.org")


def test_local_model_required_and_no_silent_fallback(tmp_path):
    adapter = SpacyNER(tmp_path / "missing")
    with pytest.raises(ValueError, match="local spaCy model"):
        adapter.detect("Ana López")


def test_spacy_window_reconstruction_and_batch(tmp_path):
    spacy = pytest.importorskip("spacy")
    nlp = spacy.blank("es")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns([{"label": "PER", "pattern": "Ana López"}])
    model = tmp_path / "model"
    nlp.to_disk(model)
    adapter = SpacyNER(model, window_chars=128, overlap_chars=40, batch_size=2)
    text = "Texto " * 19 + "Ana López" + ". Texto" * 30
    results = adapter.detect_batch([text, "Ana López", ""])
    assert len(results) == 3 and results[2] == []
    assert len(results[0]) == 1
    found = results[0][0]
    assert text[found.start : found.end] == "Ana López"


def test_real_installed_spanish_model_with_network_denied(monkeypatch):
    """Optional installed-asset integration test; CI never downloads GPL model weights."""
    model = os.environ.get("DEIDFLOW_TEST_SPACY_MODEL")
    if not model:
        pytest.skip("Set DEIDFLOW_TEST_SPACY_MODEL to a separately licensed local model")
    pytest.importorskip("spacy")

    def forbidden(*args, **kwargs):
        raise AssertionError("Network operation attempted during offline inference")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    adapter = SpacyNER(model)
    text = "María López trabaja en Ciudad de México."
    found = adapter.detect_batch([text, "Juan Pérez presentó su solicitud."])
    assert len(found) == 2
    assert any(
        f.entity_type == "PERSON" and text[f.start : f.end] == "María López" for f in found[0]
    )


def test_span_ruler_overlaps_are_loaded_and_empty_label_map_rejected(tmp_path):
    spacy = pytest.importorskip("spacy")
    nlp = spacy.blank("es")
    ruler = nlp.add_pipe("span_ruler")
    ruler.add_patterns(
        [{"label": "PER", "pattern": "Ana López"}, {"label": "PER", "pattern": "López"}]
    )
    model = tmp_path / "span-model"
    nlp.to_disk(model)
    found = SpacyNER(model).detect("Ana López")
    assert {(f.start, f.end) for f in found} == {(0, 9), (4, 9)}
    with pytest.raises(ValueError, match="mapping"):
        SpacyNER(model, labels={})


def test_checksum_helpers_reject_values_without_plaintext_echo():
    for func in (clabe_check_digit, curp_check_digit, rfc_check_digit):
        with pytest.raises(ValueError):
            func("sensitive")


def test_exact_resolution_scopes_and_no_weak_name_merging():
    text = "Ana López; Ana López; Ana; Ana"
    spans = [(0, 9), (11, 20), (22, 25), (27, 30)]
    findings = [Finding("PERSON", a, b, 0.9, "test") for a, b in spans]
    a = resolve_exact_mentions(text, findings, key=b"x" * 32, scope="tenant-a")
    b = resolve_exact_mentions(text, findings, key=b"x" * 32, scope="tenant-b")
    assert [g.mention_indices for g in a] == [(0, 1), (2,), (3,)]
    assert set(g.group_id for g in a).isdisjoint(g.group_id for g in b)
    assert "Ana" not in repr(a)


def test_iban_checksum_and_grouping():
    from deidflow import DeidEngine
    from deidflow.validators import validate_iban

    assert validate_iban("ES91 2100 0418 4502 0005 1332").status == "checksum"
    assert validate_iban("GB82WEST12345698765432").status == "checksum"
    assert validate_iban("ES9121000418450200051333").status == "invalid"
    assert validate_iban("ES912100").status == "invalid"
    engine = DeidEngine()
    text = "Transferir a ES91 2100 0418 4502 0005 1332 hoy."
    found = [(f.entity_type, text[f.start : f.end], f.validation) for f in engine.scan_text(text)]
    # The grouped digits are not also reported as a card or phone number.
    assert found == [("BANK_ACCOUNT", "ES91 2100 0418 4502 0005 1332", "checksum")]
    assert not engine.scan_text("Referencia interna AB12CDEF3456GH sin cuenta.")
    labelled = engine.scan_text("IBAN: ES0000000000000000000000")
    assert [(f.validation, f.score < 0.75) for f in labelled] == [("invalid", True)]


def test_span_model_roles_become_role_context(tmp_path):
    spacy = pytest.importorskip("spacy")
    nlp = spacy.blank("es")
    ruler = nlp.add_pipe("span_ruler")
    ruler.add_patterns([{"label": "NOMBRE_PERSONAL_SANITARIO", "pattern": "Ana López"}])
    model = tmp_path / "role-model"
    nlp.to_disk(model)
    adapter = SpacyNER(
        model,
        labels={"NOMBRE_PERSONAL_SANITARIO": "PERSON"},
        roles={"NOMBRE_PERSONAL_SANITARIO": "clinician"},
    )
    (found,) = adapter.detect("Ana López")
    assert found.entity_type == "PERSON" and "role:clinician" in found.context


@pytest.mark.parametrize("roles", [{"MISSING": "patient"}, {"PERSON": ""}, {"PERSON": 1}])
def test_span_model_rejects_invalid_role_mapping(tmp_path, roles):
    with pytest.raises(ValueError, match="roles"):
        SpacyNER(tmp_path, roles=roles)
