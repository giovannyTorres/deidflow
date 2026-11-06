from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy


def test_unchanged_url_keeps_percent_escapes_byte_for_byte(tmp_path: Path):
    source = '<a href="https://example.test/foo%20bar?q=a%26b">Informe.</a>'
    path = tmp_path / "source.html"
    path.write_text(source, encoding="utf-8")
    result = DeidEngine(country="ES").deidentify(
        path,
        output=tmp_path / "output.html",
        policy=Policy.strict(require_ner=False),
    )
    assert result.output_path is not None, result.issues
    assert result.output_path.read_text(encoding="utf-8") == source


def test_unchanged_unquoted_attribute_keeps_its_entity(tmp_path: Path):
    source = "<a title=Informe&#32;clínico>Texto.</a>"
    path = tmp_path / "source.html"
    path.write_text(source, encoding="utf-8")
    result = DeidEngine(country="ES").deidentify(
        path,
        output=tmp_path / "output.html",
        policy=Policy.strict(require_ner=False),
    )
    assert result.output_path is not None, result.issues
    assert result.output_path.read_text(encoding="utf-8") == source


def test_rewritten_unquoted_attribute_quotes_the_complete_value(tmp_path: Path):
    source = "<a title=Contacto:&#32;uno@example.test>Texto.</a>"
    path = tmp_path / "source.html"
    path.write_text(source, encoding="utf-8")
    result = DeidEngine(country="ES").deidentify(
        path,
        output=tmp_path / "output.html",
        policy=Policy.strict(require_ner=False),
    )
    assert result.output_path is not None, result.issues
    assert (
        result.output_path.read_text(encoding="utf-8") == '<a title="Contacto: [EMAIL]">Texto.</a>'
    )


def test_url_replacement_preserves_encoded_context_outside_the_sensitive_span(tmp_path: Path):
    source = '<a href="https://example.test/foo%20bar?q=a%26b&amp;Contacto:%75no%40example.test">Texto.</a>'
    path = tmp_path / "source.html"
    path.write_text(source, encoding="utf-8")
    result = DeidEngine(country="ES").deidentify(
        path,
        output=tmp_path / "output.html",
        policy=Policy.strict(require_ner=False),
    )
    assert result.output_path is not None, result.issues
    assert result.output_path.read_text(encoding="utf-8") == (
        '<a href="https://example.test/foo%20bar?q=a%26b&amp;Contacto:[EMAIL]">Texto.</a>'
    )


def test_identity_attribute_mapping_does_not_reserialize_its_encoding():
    from deidflow.markup import rewrite_html

    source = "<a title=Informe&#32;clínico>Texto.</a>"

    def identity_with_mapping(value):
        return value, [(0, len(value), value)]

    output, _ = rewrite_html(source, identity_with_mapping)
    assert output == source


def _rewrite(source: str, tmp_path: Path):
    path = tmp_path / "source.html"
    path.write_text(source, encoding="utf-8")
    result = DeidEngine(country="ES").deidentify(
        path,
        output=tmp_path / "output.html",
        policy=Policy.strict(require_ner=False),
    )
    assert result.output_path is not None, result.issues
    return result.output_path.read_text(encoding="utf-8")


def test_unchanged_attribute_entity_spellings_and_quotes_are_preserved(tmp_path: Path):
    source = '<a title="Informe&#x20;clínico" aria-label=Informe&#32;final summary=Texto&amp;texto>Texto.</a>'
    assert _rewrite(source, tmp_path) == source


def test_encoded_email_in_url_is_still_removed(tmp_path: Path):
    source = '<a href="mailto:%75no%40example.test">Texto.</a>'
    assert _rewrite(source, tmp_path) == '<a href="mailto:[EMAIL]">Texto.</a>'


def test_nested_percent_encoded_email_is_still_removed(tmp_path: Path):
    source = '<a href="mailto:%2575no%2540example.test">Texto.</a>'
    assert _rewrite(source, tmp_path) == '<a href="mailto:[EMAIL]">Texto.</a>'


def test_html_encoded_percent_signs_are_projected_as_whole_references(tmp_path: Path):
    source = '<a href="mailto:&#x25;75no&#37;40example.test">Texto.</a>'
    assert _rewrite(source, tmp_path) == '<a href="mailto:[EMAIL]">Texto.</a>'


def test_encoded_utf8_context_outside_email_remains_exact(tmp_path: Path):
    source = '<a href="https://example.test/%C3%B1%3A%75no%40example.test">Texto.</a>'
    assert _rewrite(source, tmp_path) == (
        '<a href="https://example.test/%C3%B1%3A[EMAIL]">Texto.</a>'
    )


def test_url_with_encoded_control_inside_email_remains_protected(tmp_path: Path):
    source = '<a href="mailto:u%09no%40example.test">Texto.</a>'
    assert _rewrite(source, tmp_path) == '<a href="mailto:[EMAIL]">Texto.</a>'


def test_rewritten_unquoted_url_gets_complete_quoted_value(tmp_path: Path):
    source = "<a href=mailto:%75no%40example.test>Texto.</a>"
    assert _rewrite(source, tmp_path) == '<a href="mailto:[EMAIL]">Texto.</a>'


def test_single_quoted_attribute_keeps_its_quote_style_when_rewritten(tmp_path: Path):
    source = "<a title='Contacto: uno@example.test'>Texto.</a>"
    assert _rewrite(source, tmp_path) == "<a title='Contacto: [EMAIL]'>Texto.</a>"


@pytest.mark.parametrize(
    "value",
    (
        "javascript:alert(1)",
        "java%73cript:alert(1)",
        "java&#x09;script:alert(1)",
        "%256a%2561vascript:alert(1)",
        "%252525256aavascript:alert(1)",
        "data:text/plain,example",
        "file:///etc/passwd",
    ),
)
def test_unsafe_schemes_still_get_removed(tmp_path: Path, value: str):
    source = f'<a href="{value}">Texto.</a>'
    assert _rewrite(source, tmp_path) == "<a >Texto.</a>"


def test_explicit_url_rewrite_without_mappings_keeps_callback_output():
    from deidflow.markup import rewrite_html

    def move_url(value):
        if value.startswith("https:"):
            return "https://example.test/new", []
        return value, []

    output, _ = rewrite_html('<a href="https://example.test/old">Texto.</a>', move_url)
    assert output == '<a href="https://example.test/new">Texto.</a>'


def test_long_encoded_url_stays_linear_and_preserves_untouched_source(tmp_path: Path):
    import time

    prefix = "https://example.test/" + "%20" * 70_000 + "Contacto:"
    source = f'<a href="{prefix}%75no%40example.test">Texto.</a>'
    start = time.perf_counter()
    output = _rewrite(source, tmp_path)
    elapsed = time.perf_counter() - start
    assert output == f'<a href="{prefix}[EMAIL]">Texto.</a>'
    assert elapsed < 3, elapsed


def test_oversized_changed_url_fails_closed_before_building_offset_map(tmp_path: Path):
    prefix = "https://example.test/" + "%20" * 350_000 + "Contacto:"
    source = f'<a href="{prefix}%75no%40example.test">Texto.</a>'
    path = tmp_path / "source.html"
    path.write_text(source, encoding="utf-8")
    result = DeidEngine(country="ES").deidentify(
        path,
        output=tmp_path / "output.html",
        policy=Policy.strict(require_ner=False),
    )
    assert result.status == "BLOCKED"
    assert result.output_path is None
    assert not (tmp_path / "output.html").exists()


@pytest.mark.parametrize(
    "prefix",
    ("&copyContact:", "&ampContacto:", "&notinContacto:", "&#58Contacto:", "&unknownContacto:"),
)
def test_semicolonless_reference_keeps_its_literal_suffix(tmp_path: Path, prefix: str):
    source = f'<a href="https://example.test/p?x={prefix}uno@example.test">Texto.</a>'
    assert _rewrite(source, tmp_path) == (
        f'<a href="https://example.test/p?x={prefix}[EMAIL]">Texto.</a>'
    )


def test_unquoted_url_with_query_string_is_supported(tmp_path: Path):
    source = tmp_path / "consulta.html"
    source.write_text(
        "<p><a href=https://example.test/p?x=1&amp;y=2>Ver</a> "
        "<a href=https://example.test/p?dni=12345678Z&amp;x=1>Ficha</a></p>\n"
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "salida.html", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    output = result.output_path.read_text()
    assert "<a href=https://example.test/p?x=1&amp;y=2>Ver</a>" in output  # unchanged
    assert "12345678Z" not in output
    assert '<a href="https://example.test/p?dni=[NATIONAL_ID]&amp;x=1">Ficha</a>' in output
