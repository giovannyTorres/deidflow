"""Fictional hidden-channel regressions, not a universal HTML anonymity claim."""

from __future__ import annotations

import _markupbase
from html.parser import HTMLParser

import pytest

from deidflow import DeidEngine, Policy
from deidflow.nlp.tagger import SpanTagger
from deidflow.readers import read_document


@pytest.fixture
def engine():
    return DeidEngine(nlp=SpanTagger.builtin("es-clinical"))


@pytest.mark.parametrize(
    "source",
    [
        '<p foo="private@example.com">Informe.</p>',
        "<p onclick=\"send('private@example.com')\">Informe.</p>",
        '<p data-private@example.com="ok">Informe.</p>',
        '<p id="private@example.com" class="private@example.com">Informe.</p>',
        "<p private@example.com>Informe.</p>",
        "<style>/* private@example.com */ p{color:black}</style><p>Informe.</p>",
        "<style>:root{--private:private@example.com}</style><p>Informe.</p>",
        r'<style>p:after{content:"private\40 example.com"}</style><p>Informe.</p>',
        r'<p style="background: url(private\40 example.com)">Informe.</p>',
        "<style>.private@example.com {color:black}</style><p>Informe.</p>",
        '<p style="font-family:private@example.com">Informe.</p>',
        '<!DOCTYPE html SYSTEM "private@example.com"><p>Informe.</p>',
        "<?metadata private@example.com?><p>Informe.</p>",
        "<p>Informe.</p private@example.com>",
        '<iframe srcdoc="private@example.com"></iframe><p>Informe.</p>',
        '<img src="data:image/svg+xml;base64,cHJpdmF0ZUBleGFtcGxlLmNvbQ==">',
        '<a href="mailto:private%40example.com">Informe.</a>',
        '<a href="mailto:private%2540example.com">Informe.</a>',
        '<a href="da&#10;ta:text/plain,private@example.com">Informe.</a>',
        '<a href="java&#9;script:private@example.com">Informe.</a>',
    ],
)
def test_hidden_html_channels_removed_before_review_candidate(engine, tmp_path, source):
    original, output = tmp_path / "input.html", tmp_path / "output.html"
    original.write_text(source, encoding="utf-8")
    result = engine.deidentify(original, output=output, policy=Policy.strict())
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert "HTML_REVIEW_REQUIRED" in result.issues
    text = output.read_text(encoding="utf-8")
    assert "private" not in text
    assert "base64" not in text
    graph = read_document(output)
    assert graph.complete
    assert engine.verify(output, policy=Policy.strict()).status == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    "source",
    [
        "<private@example.com>Informe.</private@example.com>",
        "<svg><metadata>private@example.com</metadata></svg>",
        "<script>private@example.com",
        "<style>/* private@example.com */",
        "<script/>private@example.com",
        '<p "private@example.com">Informe.</p>',
        "<!-- private@example.com",
        "<!-->Dosis: 5 mg cada 8 horas.<!-- private@example.com -->",
        "<!--->Dosis: 5 mg cada 8 horas.<!-- private@example.com -->",
        "<!-- private@example.com -- >Dosis: 5 mg cada 8 horas.",
    ],
)
def test_unsupported_html_syntax_blocks_without_artifact(engine, tmp_path, source):
    original, output = tmp_path / "input.html", tmp_path / "output.html"
    original.write_text(source, encoding="utf-8")
    result = engine.deidentify(original, output=output, policy=Policy.strict())
    assert result.status == "BLOCKED"
    assert not output.exists()
    assert "private" not in str(result.issues)


def test_static_layout_and_visible_context_preserved(engine, tmp_path):
    source = """<html lang="es"><head><style>td { padding: 2px; color: black }</style></head>
<body><table><tr><td colspan="2" style="font-family:Times New Roman; text-align:center">
Informe de seguimiento, sin cambios.</td></tr></table></body></html>"""
    original, output = tmp_path / "input.html", tmp_path / "output.html"
    original.write_text(source, encoding="utf-8")
    result = engine.deidentify(original, output=output, policy=Policy.strict())
    assert result.status == "REVIEW_REQUIRED"
    assert output.read_text(encoding="utf-8") == source


def test_standalone_reader_does_not_certify_uninspected_css(tmp_path):
    source = tmp_path / "input.html"
    source.write_text("<style>/* private@example.com */ p { color:black }</style>")
    graph = read_document(source)
    assert not graph.complete
    assert "html_unsupported_channels_require_review" in graph.issues


@pytest.mark.parametrize("closing", ["-->", "--!>"])
def test_comment_boundary_preserves_following_clinical_context(engine, tmp_path, closing):
    original, output = tmp_path / "input.html", tmp_path / "output.html"
    original.write_text(
        f"<p><!-- private@example.com {closing}Dosis: 5 mg cada 8 horas.</p>", encoding="utf-8"
    )
    result = engine.deidentify(original, output=output, policy=Policy.strict())
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert output.read_text(encoding="utf-8") == "<p>Dosis: 5 mg cada 8 horas.</p>"


@pytest.mark.parametrize("legacy_parser", [False, True])
def test_comment_boundaries_do_not_depend_on_stdlib_patch_release(monkeypatch, legacy_parser):
    from deidflow.markup import rewrite_html

    if legacy_parser:
        # This is the inherited parser used by older 3.11/3.12 patch releases
        # shipped on Windows/macOS CI; it recognizes --> but not --!>.
        monkeypatch.setattr(HTMLParser, "parse_comment", _markupbase.ParserBase.parse_comment)
    source = (
        "<p>Antes<!-- sin identificador detectable --!>Dosis: 5 mg cada 8 horas.\n"
        "<!-- otra nota privada -->Niega fiebre.</p>"
    )
    scanned = []

    def inspect_text(text):
        scanned.append(text)
        return text, []

    output, report = rewrite_html(source, inspect_text)
    assert output == "<p>AntesDosis: 5 mg cada 8 horas.\nNiega fiebre.</p>"
    assert report.removed == {"comment": 2}
    assert "Dosis: 5 mg cada 8 horas." in "".join(scanned)
    assert "detectable" not in "".join(scanned) and "privada" not in "".join(scanned)


def test_long_non_css_payload_is_removed_without_suffix_search():
    from deidflow.markup import rewrite_html

    source = "<style>" + "x" * 65_536 + "</style><p>Informe.</p>"
    output, _ = rewrite_html(source, lambda text: (text, []))
    assert output == "<style></style><p>Informe.</p>"
