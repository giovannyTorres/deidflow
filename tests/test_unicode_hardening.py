"""Invisible characters beyond Cf, look-alike letters and word-level tracing."""

from __future__ import annotations

import random
import time
import unicodedata

import pytest

from deidflow import DeidEngine, Policy
from deidflow.normalization import (
    NormalizationLimitError,
    detection_view,
    has_internal_format_controls,
    is_ignorable,
    ordinal_feature_text,
)

STRICT = Policy.strict(require_ner=False)

# Default_Ignorable_Code_Point characters that are not format controls (Cf).
NON_CF_INVISIBLES = [
    "͏",  # combining grapheme joiner (Mn)
    "️",  # variation selector-16 (Mn)
    "︀",  # variation selector-1 (Mn)
    "ㅤ",  # Hangul filler (Lo)
    "ﾠ",  # half-width Hangul filler (Lo)
    "ᅟ",  # Hangul choseong filler (Lo)
    "᠋",  # Mongolian free variation selector (Mn)
    "឴",  # Khmer vowel inherent AQ (Mn)
    "\U000e0101",  # variation selector-18 (Mn)
]


@pytest.mark.parametrize("invisible", NON_CF_INVISIBLES)
def test_every_default_ignorable_is_removed_from_identifiers(invisible):
    assert is_ignorable(invisible)
    engine = DeidEngine(country="ES")
    for text, token in (
        (f"DNI 1234{invisible}5678Z", "[NATIONAL_ID]"),
        (f"Correo ana{invisible}.lopez@example.com", "[EMAIL]"),
        (f"Tel. 612{invisible}345{invisible}678", "[PHONE]"),
    ):
        result = engine.deidentify_text(text, policy=STRICT)
        assert result.status == "APPROVED", (text, result.issues)
        assert token in (result.output_text or "")
        assert invisible not in (result.output_text or "")


@pytest.mark.parametrize("invisible", NON_CF_INVISIBLES)
def test_default_ignorable_inside_a_word_is_a_review_signal(invisible):
    assert has_internal_format_controls(f"pala{invisible}bra")
    assert not has_internal_format_controls(f"palabra{invisible} final")


@pytest.mark.parametrize(
    ("source", "token"),
    [
        ("DNI 12345678Ζ", "[NATIONAL_ID]"),  # Greek capital Zeta
        ("DNI 1234567Η8Z", None),  # Greek Eta inside digits: not a DNI, unchanged
        ("Correo аna.lopez@example.com", "[EMAIL]"),  # Cyrillic a
        ("Correo ana.lоpez@example.com", "[EMAIL]"),  # Cyrillic o
        ("RFC GOMA800101НВ1", None),
    ],
)
def test_latin_look_alikes_in_mixed_words_are_folded_for_detection(source, token):
    result = DeidEngine(country="ES").deidentify_text(source, policy=STRICT)
    output = result.output_text or ""
    if token is not None:
        assert token in output and result.status == "APPROVED"
    assert all(ch in source or ch in output for ch in output)


def test_pure_greek_and_cyrillic_words_are_left_alone():
    for text in ("Interferón β y α-tocoferol", "Москва и Αθήνα"):
        view = detection_view(text)
        for word in ("β", "Москва", "Αθήνα"):
            if word in text:
                assert word in view.text
    # A mixed word is only folded in the view, never in the emitted text.
    result = DeidEngine(country="ES").deidentify_text(
        "Tratamiento con 5α-reductasa.", policy=STRICT
    )
    assert result.output_text == "Tratamiento con 5α-reductasa."


def test_only_changed_words_are_traced_and_one_to_one_words_allocate_nothing():
    text = ("Paciente en planta 3º con 12 mg diarios. " * 20_000) + "ＡＢＣ 1​2"
    view = detection_view(text)
    assert "3o con 12 mg" in view.text  # NFKC applied word by word
    assert view.traced_characters == 2  # only the word with the removed control
    assert view.bounds(len(view.text) - 2, len(view.text)) == (len(text) - 3, len(text))


def test_large_document_with_common_spanish_symbols_is_processed(tmp_path):
    source = tmp_path / "grande.txt"
    source.write_text(("Paciente en planta 3º, revisión del día 5. " * 30_000) + "DNI 12345678Z\n")
    start = time.perf_counter()
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "salida.txt", policy=STRICT
    )
    assert result.status == "APPROVED", result.issues
    assert "12345678Z" not in (tmp_path / "salida.txt").read_text()
    assert time.perf_counter() - start < 60


def test_tracing_budget_counts_only_length_changing_words():
    one_to_one = ("ｘ" * 5 + " ") * 10_000
    assert detection_view(one_to_one, max_characters=1).traced_characters == 0
    with pytest.raises(NormalizationLimitError):
        detection_view(("a​b " * 1_000), max_characters=100)


def test_ordinal_features_are_restored_in_changed_words_only():
    source = "Calle Ficción 12, 5º derecha, nº 3"
    view = detection_view(source)
    assert view.text == "Calle Ficción 12, 5o derecha, no 3"
    assert ordinal_feature_text(source, view) == source


def _reference(text: str) -> str:
    kept = "".join(c for c in text if not is_ignorable(c))
    return unicodedata.normalize("NFKC", kept)


def test_word_level_view_matches_whole_string_reference():
    alphabet = "aá1@ ﬃ̧́각­​͏️ㅤＡ１ \nº"
    randomizer = random.Random(2026)
    for _ in range(800):
        source = "".join(randomizer.choices(alphabet, k=randomizer.randrange(1, 30)))
        view = detection_view(source)
        assert view.text == _reference(source), repr(source)
        intervals = [view.bounds(i, i + 1) for i in range(len(view.text))]
        assert all(0 <= a < b <= len(source) for a, b in intervals)
        assert all(
            x[0] <= y[0] and x[1] <= y[1] for x, y in zip(intervals, intervals[1:], strict=False)
        )


def test_long_words_without_whitespace_stay_linear():
    for text in ("á" * 400_000, "x" * 200_000 + "​" + "y" * 200_000, "Ａ" * 300_000):
        start = time.perf_counter()
        detection_view(text)
        assert time.perf_counter() - start < 5
