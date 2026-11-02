from __future__ import annotations

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus
from deidflow.cli import main
from deidflow.detectors.ocr import ocr_field_candidates


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Correo: anaQexample.org", "EMAIL"),
        ("CLABE: OO218O OOOOOO12345678", "CLABE"),
        ("Teléfono: 55 S678 I234", "PHONE"),
    ],
)
def test_damaged_ocr_field_is_review_candidate(text, kind):
    engine = DeidEngine()
    candidates = engine.scan_ocr_text(text)
    uncertain = [
        f for f in candidates if f.entity_type == kind and f.detector == "ocr.label_context"
    ]
    assert uncertain and all(f.protected and f.confidence is None for f in uncertain)
    assert text[uncertain[0].start : uncertain[0].end] == text.split(": ", 1)[1]
    assert (
        engine._gate(
            policy=Policy.strict_pdf(require_ner=False), residual=[], original=candidates
        ).status
        == ReleaseStatus.REVIEW_REQUIRED
    )


def test_valid_email_is_not_downgraded_by_ocr_context():
    found = DeidEngine().scan_ocr_text("Correo: ana@example.org.")
    assert not any(f.detector == "ocr.label_context" for f in found)


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Nombre: maría del sol", "PERSON"),
        ("Domicilio: av revolución l23", "ADDRESS"),
        ("RFC: BAXO 9OO1O1 123", "RFC"),
    ],
)
def test_already_covered_field_retains_detector_provenance(text, kind):
    found = DeidEngine().scan_ocr_text(text)
    assert any(f.entity_type == kind for f in found)
    assert not any(f.detector == "ocr.label_context" for f in found)


def test_blank_or_unlabelled_ocr_is_not_falsely_accepted_as_id():
    assert not ocr_field_candidates("Correo: \nImporte: 42", [])
    assert not ocr_field_candidates("El correo electrónico es una tecnología.", [])


def test_pdf_policy_has_physical_removal_semantics():
    policy = Policy.strict_pdf()
    assert policy.default.action == "redact" and policy.require_ner is True
    assert Policy.strict().default.action == "placeholder"


@pytest.mark.parametrize(
    "options",
    [
        {"pdf_dpi": 71},
        {"pdf_dpi": 601},
        {"pdf_dpi": True},
        {"pdf_max_pages": 0},
        {"pdf_max_pages": 1001},
    ],
)
def test_pdf_limits_rejected(options):
    with pytest.raises(ValueError):
        DeidEngine(**options)


def test_pdf_cli_missing_ocr_is_blocked(tmp_path, capsys):
    path = tmp_path / "input.pdf"
    path.write_bytes(b"not a real PDF")
    assert main(["deidentify", str(path), "--output", str(tmp_path / "out.pdf")]) == 2
    assert "LOCAL_OCR_REQUIRED" in capsys.readouterr().out
    assert not (tmp_path / "out.pdf").exists()


def test_pdf_unsupported_policy_never_silently_substituted(tmp_path):
    result = DeidEngine().deidentify(
        tmp_path / "in.pdf", output=tmp_path / "out.pdf", policy=Policy.strict()
    )
    assert result.status == ReleaseStatus.UNSUPPORTED
    assert result.issues == ["PDF_POLICY_ACTION_UNSUPPORTED"]


@pytest.mark.parametrize(
    "text",
    [
        "Cliente:\nDomicilio:\nDiagnóstico:\nImporte: 42 pesos",
        "Paciente:\nFecha de nacimiento:",
        "Cliente:    \n   Domicilio: \n Diagnóstico:",
    ],
)
def test_empty_fields_do_not_consume_the_next_field_label(text):
    assert not DeidEngine().scan_ocr_text(text)


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Cliente:\nCLI-98765", "CUSTOMER_ID"),
        ("Domicilio:\nAvenida Prueba 123\nColonia Centro", "ADDRESS"),
        ("Paciente:\nMaría Del Sol", "PERSON"),
    ],
)
def test_legitimate_values_on_following_line_remain_detected(text, kind):
    assert any(f.entity_type == kind for f in DeidEngine().scan_text(text))


def test_updated_rules_refuse_old_calibration_provenance():
    from deidflow.training import ScoreCalibrator

    finding = DeidEngine().scan_text("a@example.test")[0]
    assert finding.model_version == "rules-0.2"
    with pytest.raises(ValueError, match="provenance"):
        ScoreCalibrator("rules.es_MX", "rules-0.1", 1.0, 0.0, 100).apply(finding)
