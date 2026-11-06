import time

import pytest

from deidflow import DeidEngine, Policy
from deidflow.core import Finding


def test_invisible_inside_dni_is_removed_with_original_offsets():
    source = "Informe. DNI 1234\u200b5678Z; tratamiento sin cambios."
    engine = DeidEngine(country="ES")
    result = engine.deidentify_text(source, policy=Policy.strict(require_ner=False))
    assert result.output_text == "Informe. DNI [NATIONAL_ID]; tratamiento sin cambios."
    assert [(m.source_start, m.source_end) for m in result.mappings] == [(13, 23)]


@pytest.mark.parametrize("control", ["\u00ad", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"])
@pytest.mark.parametrize(
    ("left", "right", "token"),
    [
        ("DNI 1234", "5678Z", "[NATIONAL_ID]"),
        ("Tel. 612", "345678", "[PHONE]"),
        ("Correo ana", ".lopez@example.com", "[EMAIL]"),
        ("CURP GOMA800101HDFRRN0", "9", "[CURP]"),
    ],
)
def test_format_controls_inside_identifiers_are_completely_removed(control, left, right, token):
    result = DeidEngine(country="ES").deidentify_text(
        left + control + right, policy=Policy.strict(require_ner=False)
    )
    assert token in result.output_text
    assert control not in result.output_text
    assert result.audit["transformations"] >= 1


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Correo ａｎａ.lopez@example.com", "Correo [EMAIL]"),
        ("DNI １２３４５６７８Ｚ", "DNI [NATIONAL_ID]"),
        ("Correo ana＠example.com", "Correo [EMAIL]"),
    ],
)
def test_compatibility_forms_are_detected_without_normalizing_unrelated_output(source, expected):
    suffix = "; información útil: ﬁnal ①."
    result = DeidEngine(country="ES").deidentify_text(
        source + suffix, policy=Policy.strict(require_ner=False)
    )
    assert result.output_text == expected + suffix


def test_nlp_adapter_receives_normalized_text_and_returns_original_offsets():
    class ExactNameAdapter:
        def detect_batch(self, texts):
            return [
                [Finding("PERSON", 0, 3, 1.0, "local.name.adapter")] if text == "Zoë" else []
                for text in texts
            ]

    source = "Ｚｏe\u0308\u200b"
    engine = DeidEngine(nlp=ExactNameAdapter())
    findings = engine.scan_texts([source])[0]
    assert [(f.entity_type, f.start, f.end) for f in findings] == [("PERSON", 0, 5)]
    result = engine.deidentify_text(source, policy=Policy.strict(require_ner=False))
    assert result.output_text == "[PERSON]"


def test_two_hundred_thousand_invisibles_inside_identifier_have_bounded_runtime():
    source = "DNI 1234" + "\u200b" * 200_000 + "5678Z"
    started = time.perf_counter()
    result = DeidEngine(country="ES").deidentify_text(
        source, policy=Policy.strict(require_ner=False)
    )
    assert result.output_text == "DNI [NATIONAL_ID]"
    assert time.perf_counter() - started < 3


def test_normalized_floor_ordinal_keeps_the_existing_address_coverage():
    source = "Mi dirección es Calle Ficción 12, 3ª planta."
    addresses = [f for f in DeidEngine().scan_text(source) if f.entity_type == "ADDRESS"]
    assert [source[f.start : f.end] for f in addresses] == ["Calle Ficción 12, 3ª"]


def test_a_floor_without_a_house_number_does_not_become_a_new_address():
    source = "Calle Ficción, 3ª planta."
    assert not [f for f in DeidEngine().scan_text(source) if f.entity_type == "ADDRESS"]


@pytest.mark.parametrize("tail", [", 3 o más pisos", ", 3 a 5 visitas"])
def test_ordinary_ascii_prose_is_not_reinterpreted_as_a_floor(tail):
    source = "Calle Ficción 12" + tail
    addresses = [f for f in DeidEngine().scan_text(source) if f.entity_type == "ADDRESS"]
    assert [source[f.start : f.end] for f in addresses] == ["Calle Ficción 12"]


def test_ordinal_in_street_type_keeps_its_original_lexical_meaning():
    source = "Pº Ficción 12"
    addresses = [f for f in DeidEngine().scan_text(source) if f.entity_type == "ADDRESS"]
    assert [source[f.start : f.end] for f in addresses] == [source]
