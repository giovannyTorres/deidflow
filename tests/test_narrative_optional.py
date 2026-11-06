"""Optional audit-branch recognizers do not change default detector behavior."""

from deidflow import DeidEngine
from deidflow.detectors.narrative import NarrativeRecognizer


def test_optional_titles_and_roles_do_not_change_default_rules():
    text = "La señora Verónica fue vista por el doctor Jiménez y su hija Ana."
    baseline = DeidEngine().scan_text(text)
    assert not any("role:clinician" in item.context for item in baseline)
    found = {
        (item.entity_type, text[item.start : item.end]): item
        for item in DeidEngine(recognizers=[NarrativeRecognizer()]).scan_text(text)
    }
    assert "gender:f" in found[("PERSON", "Verónica")].context
    assert "role:clinician" in found[("PERSON", "Jiménez")].context
    assert "role:family" in found[("PERSON", "Ana")].context
    assert DeidEngine().scan_text(text) == baseline


def test_optional_narrative_no_runtime_download_and_valid_offsets():
    text = "Fue al Hospital Ángeles de Guadalajara. Vive en Calle Luna 5, Col. Roma."
    findings = NarrativeRecognizer().detect(text)
    assert findings
    assert all(0 <= item.start < item.end <= len(text) for item in findings)
    assert any(item.entity_type == "MEDICAL_FACILITY" for item in findings)
    assert any(item.entity_type in {"ADDRESS", "LOCATION"} for item in findings)
