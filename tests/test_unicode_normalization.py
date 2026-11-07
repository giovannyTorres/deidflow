"""Trace normalization through its public detection view."""

from deidflow.normalization import detection_view


def test_combining_composition_preserves_complete_original_character_span():
    view = detection_view("x a\u0301 z")
    assert view.text == "x á z"
    assert view.bounds(2, 3) == (2, 4)


def test_reordered_marks_share_a_complete_original_cluster():
    view = detection_view("a\u0301\u0327")
    assert view.text == "á\u0327"
    assert view.bounds(0, 1) == view.bounds(1, 2) == (0, 3)


def test_zero_combining_class_compositions_are_not_split():
    hangul = detection_view("\u1100\u1161\u11a8")
    assert hangul.text == "각"
    assert hangul.bounds(0, 1) == (0, 3)
    bengali = detection_view("\u09c7\u09be")
    assert bengali.text == "\u09cb"
    assert bengali.bounds(0, 1) == (0, 2)


def test_compatibility_expansion_keeps_the_original_scalar_whole():
    view = detection_view("x ﬃ y")
    assert view.text == "x ffi y"
    assert [view.bounds(i, i + 1) for i in (2, 3, 4)] == [(2, 3)] * 3
    assert view.bounds(2, 5) == (2, 3)


def test_invisible_edges_and_interior_are_included_in_original_span():
    view = detection_view("L \u200bana\u200d@example.test\ufeff R")
    assert view.text == "L ana@example.test R"
    assert view.bounds(2, 18) == (2, 21)


def test_fullwidth_source_is_not_emitted_as_normalized_text():
    view = detection_view("Ｘ ａｎａ＠ｅｘａｍｐｌｅ．ｔｅｓｔ Ｙ")
    assert view.text == "X ana@example.test Y"
    assert view.bounds(2, 18) == (2, 18)


def test_projection_preserves_finding_provenance():
    from deidflow.core import Finding

    original = Finding("TOKEN", 2, 3, 0.8, "local", context=("evidence",), protected=True)
    mapped = detection_view("x a\u0301 z").project(original)
    assert (mapped.start, mapped.end) == (2, 4)
    assert mapped.score == original.score
    assert mapped.context == ("evidence",)
    assert mapped.detector == "local" and mapped.protected


def test_large_ascii_identity_does_not_require_tracing_allocations():
    text = "ordinary text " * 20_000
    assert detection_view(text, max_characters=1).text == text


def test_decomposed_tracing_budget_fails_closed_without_exposing_input():
    import pytest

    with pytest.raises(ValueError, match="^Text exceeds normalization tracing budget$"):
        detection_view("\ufdfa" * 10, max_characters=10)


def test_invalid_detection_offsets_fail_closed():
    import pytest

    view = detection_view("x a\u0301 z")
    for start, end in ((0, 0), (-1, 1), (0, 100), (True, 2)):
        with pytest.raises(ValueError, match="Invalid normalized detection offsets"):
            view.bounds(start, end)


def test_residual_controls_are_a_review_signal_without_inventing_entities():
    from deidflow.normalization import has_internal_format_controls

    for control in ("\u00ad", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"):
        assert has_internal_format_controls("ab" + control + "cd")
        assert has_internal_format_controls("a\u0301" + control + "b")
        assert not has_internal_format_controls(control + "abc")
        assert not has_internal_format_controls("abc" + control + " def")
    assert not has_internal_format_controls("\u200b" * 200_000)


def test_trace_matches_whole_string_unicode_reference_for_development_samples():
    import random
    import unicodedata

    alphabet = "aá1@ ﬃ\u0327\u0301\u0344\u1100\u1161\u11a8\u09c7\u09be\u00ad\u200b\ufeffＡ１\ufdfa"
    randomizer = random.Random(1729)
    for _ in range(600):
        source = "".join(randomizer.choices(alphabet, k=randomizer.randrange(1, 20)))
        view = detection_view(source)
        reference = unicodedata.normalize(
            "NFKC",
            "".join(character for character in source if unicodedata.category(character) != "Cf"),
        )
        assert view.text == reference
        intervals = [view.bounds(i, i + 1) for i in range(len(view.text))]
        assert all(0 <= start < end <= len(source) for start, end in intervals)
        assert all(
            a[0] <= b[0] and a[1] <= b[1] for a, b in zip(intervals, intervals[1:], strict=False)
        )


def test_already_normalized_non_ascii_preserves_the_original_input_budget():
    source = "á" * 2_000
    assert detection_view(source, max_characters=1).text == source


def test_tracing_budget_metadata_distinguishes_identity_from_mapped_views():
    assert detection_view("ordinary ASCII").traced_characters == 0
    assert detection_view("á").traced_characters == 0
    assert detection_view("ﬃ").traced_characters == 3
    assert detection_view("a\u0301").traced_characters == 1
