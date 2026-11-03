from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

import deidflow.detectors as detector_module
import deidflow.detectors.clinical as clinical_module
from deidflow import DeidEngine, Policy, Rule
from deidflow.detectors import RuleDetector
from deidflow.detectors.clinical import contextual_spanish


@pytest.mark.parametrize(
    "text,kind,value",
    [
        ("Nombre: Ana\nApellidos: Ruiz Sol", "PERSON", "Ana"),
        ("Apellidos: Ruiz Sol\n", "PERSON", "Ruiz Sol"),
        ("Médico: Ana Ruiz NºCol: 28 28 12345", "PERSON", "Ana Ruiz"),
        ("Remitido por: Dra. Ana Sol\n", "PERSON", "Ana Sol"),
        ("NHC: 1234567", "PATIENT_ID", "1234567"),
        ("CIPA: nhc-1234567", "PATIENT_ID", "1234567"),
        ("NASS: 28 12345678 00", "INSURANCE_ID", "28 12345678 00"),
        ("NºCol: 28 28 12345", "REGIONAL_ID", "28 28 12345"),
        ("DNI: 12345678Z", "NATIONAL_ID", "12345678Z"),
        ("Teléfono +34 612 34 56 78", "PHONE", "+34 612 34 56 78"),
        ("Fecha: 7/2/2024", "DATE", "7/2/2024"),
        ("Cita: 7 de febrero de 2024", "DATE", "7 de febrero de 2024"),
        ("Nacimiento: 7 de febrero de 2024", "DATE_OF_BIRTH", "7 de febrero de 2024"),
        ("Mujer de 64 años", "AGE", "64"),
        ("Sexo: M", "DEMOGRAPHIC", "M"),
    ],
)
def test_contextual_spanish_regressions_use_synthetic_values(text, kind, value):
    assert any(
        f.entity_type == kind and text[f.start : f.end] == value for f in contextual_spanish(text)
    )


def test_dni_checksum_is_evidence_not_registry_confirmation():
    valid = next(f for f in contextual_spanish("DNI: 12345678Z") if f.entity_type == "NATIONAL_ID")
    invalid = next(
        f for f in contextual_spanish("DNI: 12345678A") if f.entity_type == "NATIONAL_ID"
    )
    assert valid.validation == "checksum" and invalid.validation == "invalid" and invalid.protected


@pytest.mark.parametrize(
    "text",
    [
        "Médico:\nNombre:\nApellidos:",
        "La medicina estudia enfermedades.",
        "31 de febrero de 2024",
        "DNI sin información.",
    ],
)
def test_hard_negatives_and_invalid_dates_not_new_sensitive_facts(text):
    assert not contextual_spanish(text)


def test_numeric_age_boundary_retains_bucketing_compatibility():
    result = DeidEngine().deidentify_text(
        "Mujer de 64 años",
        policy=Policy(
            default=Rule("keep"),
            entities={"AGE": Rule("bucket", width=10)},
            require_ner=False,
            allow_residual_types=("AGE",),
        ),
    )
    assert "[60,70)" in result.output_text


def test_new_rules_never_discard_existing_highrisk_findings():
    text = "Correo: a@example.test RFC: GODE561231GR8 CLABE: 002180000000000009"
    prior = RuleDetector(contextual=False).detect(text)
    current = RuleDetector().detect(text)
    keys = {(f.entity_type, f.start, f.end) for f in current}
    assert all((f.entity_type, f.start, f.end) in keys for f in prior if f.protected)


@given(
    prefix=st.text(alphabet=" abcdefÁÉÑ.,:\n0123456789", max_size=80),
    tail=st.text(alphabet=" abcdefÁÉÑ.,:\n0123456789", max_size=80),
    identity=st.sampled_from(
        [
            "RFC: GODE561231GR8",
            "CURP: GODE561231HDFRRN09",
            "CLABE: 002180000000000009",
            "Tarjeta: 4111111111111111",
            "Correo: a@example.test",
            "NHC: 1234567",
            "Nombre: Ana Sol",
        ]
    ),
)
def test_contextual_additions_preserve_all_prior_protected_candidates(prefix, tail, identity):
    text = prefix + "\n" + identity + "\n" + tail
    with patch.object(detector_module, "contextual_spanish", return_value=[]):
        prior = RuleDetector().detect(text)
    current = RuleDetector().detect(text)
    protected = {(f.entity_type, f.start, f.end, f.location) for f in current if f.protected}
    assert all(
        (f.entity_type, f.start, f.end, f.location) in protected for f in prior if f.protected
    )


@given(text=st.text(max_size=180))
def test_trigger_prefilter_is_equivalent_to_scanning_arbitrary_text(text):
    expected = contextual_spanish(text)
    with patch.object(clinical_module, "_TRIGGER", __import__("re").compile("")):
        full_scan = contextual_spanish(text)
    assert expected == full_scan


@pytest.mark.parametrize(
    "text",
    [
        "Nombre: Ana Sol",
        "NHC: 1234567",
        "Sexo: M",
        "+34 612 34 56 78",
        "7 de febrero de 2024",
        "7/2/2024",
        "Mujer de 64 años",
        "DNI 12345678Z",
    ],
)
def test_trigger_prefilter_covers_each_recognizer_family(text):
    expected = contextual_spanish(text)
    with patch.object(clinical_module, "_TRIGGER", __import__("re").compile("")):
        assert expected == contextual_spanish(text)
    assert expected
