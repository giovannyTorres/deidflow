"""LLM acceptance suite (audit F0.3): Spanish narrative in, context-preserving
placeholders out. Every value is fictional. ``must_hide`` strings may never reach
the model; ``expected`` pins the exact context-preserving output where it matters.
Known gaps are strict xfails so a fix must update this file deliberately.
"""

from __future__ import annotations

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus
from deidflow.llm import DeidSession

CASES = [
    (
        "La señora Verónica Herrera fue diagnosticada por el doctor Jiménez antes de la cita "
        "del señor González.",
        ["Verónica", "Herrera", "Jiménez", "González"],
        "La señora [PERSONA_1] fue diagnosticada por el doctor [MEDICO_1] antes de la cita "
        "del señor [PERSONA_2].",
    ),
    (
        "La doctora Ana Ruiz atendió a la Lic. Paola Méndez en el Hospital General de México.",
        ["Ana Ruiz", "Paola", "Méndez", "Hospital General de México"],
        "La doctora [MEDICO_1] atendió a la Lic. [PERSONA_1] en el [CENTRO_MEDICO_1].",
    ),
    (
        "El Ing. Roberto Salinas, NSS 12345678901, trabaja en Pemex en Villahermosa, Tabasco.",
        ["Roberto", "Salinas", "12345678901", "Pemex", "Villahermosa", "Tabasco"],
        None,
    ),
    (
        "Mi número es 5512345678 y mi WhatsApp 33 1234 5678.",
        ["5512345678", "33 1234 5678"],
        None,
    ),
    (
        "Vive en Av. Insurgentes Sur 1602, Col. Crédito Constructor, Benito Juárez, 03940 CDMX.",
        ["Insurgentes", "1602", "Crédito Constructor", "Benito Juárez", "03940", "CDMX"],
        "Vive en [DIRECCION_1].",
    ),
    (
        "Nació el 3 de marzo de 1985 en Monterrey; tiene 39 años.",
        ["3 de marzo de 1985", "Monterrey", "39"],
        "Nació el [FECHA_NACIMIENTO_1] en [LUGAR_1]; tiene [30,40) años.",
    ),
    (
        "Clave de elector GMVLMR80070501M100, INE folio 1234567890123.",
        ["GMVLMR80070501M100", "1234567890123"],
        None,
    ),
    (
        "Paciente femenina de 52 años con VIH, tratada en el IMSS de Guadalajara.",
        ["52", "IMSS", "Guadalajara"],
        "Paciente femenina de [50,60) años con VIH, tratada en el [ORGANIZACION_1] de [LUGAR_1].",
    ),
    (
        "Verónica tiene VIH y toma metformina; su médico es el Dr. Ramírez del Hospital "
        "Ángeles en Guadalajara.",
        ["Verónica", "Ramírez", "Ángeles", "Guadalajara"],
        "[PERSONA_1] tiene VIH y toma metformina; su médico es el Dr. [MEDICO_1] del "
        "[CENTRO_MEDICO_1] en [LUGAR_1].",
    ),
    (
        "Juan Pérez Gómez llamó ayer. El señor Pérez dijo que su hija Ana lo acompañará.",
        ["Juan", "Pérez", "Gómez", "Ana"],
        "[PERSONA_1] llamó ayer. El señor [PERSONA_1] dijo que su hija [FAMILIAR_1] lo acompañará.",
    ),
    (
        "El paciente Luis Ortega fue valorado por la enfermera Rocío Lara.",
        ["Luis", "Ortega", "Rocío", "Lara"],
        "El paciente [PACIENTE_1] fue valorado por la enfermera [MEDICO_1].",
    ),
    (
        "La señora González y el señor González llegaron juntos.",
        ["González"],
        "La señora [PERSONA_1] y el señor [PERSONA_2] llegaron juntos.",
    ),
    (
        "Correo: ana.ruiz@example.org, CURP GOLM800101MDFRRR09, RFC GODE561231GR8.",
        ["ana.ruiz@example.org", "GOLM800101MDFRRR09", "GODE561231GR8"],
        None,
    ),
    (
        "Trabaja en Comercializadora del Norte S.A. de C.V. en Monterrey.",
        ["Comercializadora del Norte", "Monterrey"],
        None,
    ),
    (
        "Domicilio en C/ Mayor 5, 28013 Madrid; cédula profesional 1234567.",
        ["Mayor 5", "28013", "Madrid", "1234567"],
        None,
    ),
]


@pytest.fixture
def session() -> DeidSession:
    return DeidSession(DeidEngine(), policy=Policy.llm(require_ner=False))


@pytest.mark.parametrize(("text", "must_hide", "expected"), CASES)
def test_llm_acceptance_hides_identity_and_keeps_context(session, text, must_hide, expected):
    result = session.deidentify(text)
    assert result.status != ReleaseStatus.BLOCKED
    assert result.output_text is not None
    for value in must_hide:
        assert value not in result.output_text
    if expected is not None:
        assert result.output_text == expected


def test_session_keeps_placeholders_across_turns_and_restores_answers(session):
    first = session.deidentify("La señora Verónica Herrera fue atendida por el doctor Jiménez.")
    second = session.deidentify("Mañana Verónica Herrera vuelve con el doctor Jiménez.")
    assert first.output_text == "La señora [PERSONA_1] fue atendida por el doctor [MEDICO_1]."
    assert second.output_text == "Mañana [PERSONA_1] vuelve con el doctor [MEDICO_1]."
    answer = "El [Medico 1] debe llamar a PERSONA_1; [PERSONA_7] no existe."
    restored = session.reidentify(answer)
    assert restored.text == "El Jiménez debe llamar a Verónica Herrera; [PERSONA_7] no existe."
    assert restored.restored == 2 and restored.unknown == ("[PERSONA_7]",)
    with pytest.raises(ValueError):
        session.reidentify(answer, strict=True)


def test_missed_names_cannot_be_approved(session):
    # Neither name is in any gazetteer nor introduced by a title: the detector misses
    # them, and the independent orthographic check must stop an APPROVED release.
    result = session.deidentify("Hoy trabajé con Zoila Quintanar en Zyxcorp.")
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "POSSIBLE_RESIDUAL_PROPER_NOUN" in result.issues


@pytest.mark.xfail(strict=True, reason="Bare surname without title or given name needs NER")
def test_known_gap_bare_surname(session):
    result = session.deidentify("ayer Quintanar firmó el contrato.")
    assert "Quintanar" not in (result.output_text or "")
