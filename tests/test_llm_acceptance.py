"""Synthetic LLM preprocessing workflows; no remote service or quality claim.

Narrative detection is explicitly enabled where used. Exact-value pseudonyms do
not resolve aliases, and any release remains subject to the library's gates.
"""

from __future__ import annotations

import re

import pytest

from deidflow import DeidEngine, Finding, Policy, ReleaseStatus
from deidflow.detectors.narrative import NarrativeRecognizer
from deidflow.llm import DeidSession


@pytest.fixture
def narrative_session():
    return DeidSession(
        DeidEngine(recognizers=[NarrativeRecognizer()]),
        policy=Policy.llm(require_ner=False),
    )


@pytest.mark.parametrize(
    ("text", "must_hide"),
    [
        (
            "La señora Verónica Herrera fue diagnosticada por el doctor Jiménez antes de la cita "
            "del señor González.",
            ["Verónica", "Herrera", "Jiménez", "González"],
        ),
        (
            "La doctora Ana Ruiz atendió a la Lic. Paola Méndez en el Hospital General de México.",
            ["Ana Ruiz", "Paola", "Méndez", "Hospital General de México"],
        ),
        (
            "Correo: ana.ruiz@example.org, CURP GOLM800101MDFRRR09, RFC GODE561231GR8.",
            ["ana.ruiz@example.org", "GOLM800101MDFRRR09", "GODE561231GR8"],
        ),
        (
            "El paciente Luis Ortega fue valorado por la enfermera Rocío Lara.",
            ["Luis", "Ortega", "Rocío", "Lara"],
        ),
    ],
)
def test_explicit_narrative_pipeline_removes_known_synthetic_values(
    narrative_session, text, must_hide
):
    result = narrative_session.deidentify(text)
    assert result.output_text is not None
    for value in must_hide:
        assert value not in result.output_text
    # This fixture measures transformation behavior, not real-world NER accuracy.
    assert result.audit["anonymity_proven"] is False


class ExactAdapter:
    def detect_batch(self, texts):
        return [
            [
                Finding("PERSON", *m.span(), 0.99, "synthetic.names")
                for m in re.finditer("Verónica Herrera|Jiménez", text)
            ]
            for text in texts
        ]


def test_sessions_keep_exact_tokens_across_turns_and_restore_only_known_response_tokens():
    current = DeidSession(DeidEngine(nlp=ExactAdapter()), policy=Policy.llm())
    first = current.deidentify("Verónica Herrera habló con Jiménez.")
    second = current.deidentify("Mañana Verónica Herrera vuelve.")
    assert first.output_text == "[PERSONA_1] habló con [PERSONA_2]."
    assert second.output_text == "Mañana [PERSONA_1] vuelve."
    restored = current.reidentify("Debe llamar a [Persona 1] y PERSONA_2.")
    assert restored.text == "Debe llamar a Verónica Herrera y Jiménez."
    assert restored.restored == 2
    with pytest.raises(ValueError, match="not issued"):
        current.reidentify("Debe llamar a [PERSONA_7].")


def test_undetected_mid_sentence_names_require_review(narrative_session):
    result = narrative_session.deidentify("Hoy trabajé con Zoila Quintanar en Zyxcorp.")
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "POSSIBLE_RESIDUAL_PROPER_NOUN" in result.issues


def test_narrative_rules_are_optional_and_do_not_satisfy_semantic_requirement():
    current = DeidSession(DeidEngine(recognizers=[NarrativeRecognizer()]))
    result = current.deidentify("La señora Verónica Herrera habló con el doctor Jiménez.")
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues


def test_structured_llm_policy_does_not_silently_bypass_independent_review(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("correo,nota\na@example.org,x\na@example.org,y\n")
    output = tmp_path / "candidate.csv"
    result = DeidEngine().deidentify(
        source, policy=Policy.llm(require_ner=False), output=output, batch_size=1
    )
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "INDEPENDENT_CHECK_REQUIRES_REVIEW" in result.issues
    rows = output.read_text().splitlines()
    assert rows[1].startswith("[CORREO_1]") and rows[2].startswith("[CORREO_1]")


def test_blocked_source_output_is_not_added_to_reversible_vault():
    class ResidualAdapter:
        def detect_batch(self, texts):
            return [
                [Finding("PERSON", 0, 3, 0.99, "source")]
                if text == "Ana remains"
                else [Finding("PERSON", text.index("remains"), len(text), 0.99, "residual")]
                if "remains" in text
                else []
                for text in texts
            ]

    current = DeidSession(DeidEngine(nlp=ResidualAdapter()), policy=Policy.llm())
    result = current.deidentify("Ana remains")
    assert result.status == ReleaseStatus.BLOCKED
    assert len(current.vault) == 0
    with pytest.raises(ValueError, match="not issued"):
        current.reidentify("[PERSONA_1]")
