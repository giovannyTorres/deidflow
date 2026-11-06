from __future__ import annotations

import pytest

from deidflow import DeidEngine, Policy
from deidflow.markup import parse, rewrite_html
from deidflow.readers import read_document

PAGE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Expediente de Mar&iacute;a L&oacute;pez</title>
<meta name="author" content="Correo: autor.real@example.com">
<script>var paciente = "maria.lopez@example.com";</script>
<style>td { padding: 2px }</style>
</head>
<body>
<!-- revisado por Ramón Ortega, DNI 11111112L -->
<h1>Informe</h1>
<table>
<tr><td>Nombre:</td><td><b>María</b> L&oacute;pez García</td></tr>
<tr><td>DNI</td><td>12345678Z</td></tr>
<tr><td>Correo</td><td><a href="mailto:maria.lopez@example.com">maria.lopez@example.com</a></td></tr>
</table>
<p>Tel&eacute;fono de contacto: +34 612 345 678.</p>
<img src="data:image/png;base64,iVBORw0KGgo=" alt="Foto, DNI 87654321X">
<form><input type="text" name="cuenta" value="ES91 2100 0418 4502 0005 1332"></form>
</body></html>
"""


def test_parse_offsets_and_text_stream():
    markup = parse(PAGE)
    text = markup.text()
    assert "Nombre: María López García" in " ".join(text.split())
    for segment in markup.segments:
        if not isinstance(segment, str) and segment.exact:
            assert PAGE[segment.start : segment.end] == segment.text
    assert any(name == "href" for _, _, name, _ in markup.attributes)
    assert markup.comments and markup.scripts


def test_html_output_keeps_markup_and_removes_values(tmp_path):
    source = tmp_path / "expediente.html"
    source.write_text(PAGE, "utf-8")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.html", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    output = result.output_path.read_text("utf-8")
    for secret in (
        "12345678Z",
        "maria.lopez@example.com",
        "612 345 678",
        "Ramón",  # comment
        "11111112L",
        "87654321X",  # alt text
        "iVBORw0KGgo",  # embedded image
        "2100 0418",  # form value
        "autor.real@example.com",  # meta content
        "López García",
    ):
        assert secret not in output, secret
    assert "<script" not in output and "<!--" not in output
    assert "<style>td { padding: 2px }</style>" in output
    assert "<td>Nombre:</td>" in output and "<h1>Informe</h1>" in output
    assert 'href="mailto:[EMAIL]"' in output
    assert read_document(result.output_path).complete
    removed = result.audit["markup_removed"]
    assert removed == {"comment": 1, "embedded_data": 1, "script": 1}


def test_character_references_are_replaced_whole():
    calls = []

    def rewrite(text):
        calls.append(text)
        start = text.index("José")
        return text, [(start, start + len("José Núñez"), "[PERSON]")]

    output, report = rewrite_html("<p>Firma: Jos&eacute; N&#250;&#xF1;ez.</p>", rewrite)
    assert calls == ["\nFirma: José Núñez.\n"]
    assert output == "<p>Firma: [PERSON].</p>" and report.transformations == 1


def test_reader_flags_scripts_and_embedded_images(tmp_path):
    path = tmp_path / "page.htm"
    path.write_text(PAGE, "utf-8")
    graph = read_document(path)
    assert not graph.complete
    assert {"html_scripts_require_review", "html_embedded_data_requires_review"} <= set(
        graph.issues
    )
    kinds = {f.kind for f in graph.fragments}
    assert {"html_text", "attribute", "comment", "script"} <= kinds


@pytest.mark.parametrize(
    "fragment",
    [
        '<img src="https://example.com/fotos/ana.ruiz@example.com.png">',
        '<img srcset="data:image/svg+xml;base64,PHN2Zz5hbmFAZXhhbXBsZS5jb208L3N2Zz4= 2x">',
        '<style>p::before { content: "ana.ruiz@example.com"; }</style><p>Informe</p>',
        "<p style=\"background: url('https://example.com/u/ana.ruiz@example.com')\">x</p>",
        '<object data="data:application/pdf;base64,JVBERi0xLjQ="></object>',
    ],
)
def test_urls_data_urls_and_css_values_are_covered(tmp_path, fragment):
    source = tmp_path / "page.html"
    source.write_text(f"<html><body>{fragment}</body></html>", "utf-8")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.html", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    output = result.output_path.read_text("utf-8")
    assert "ana.ruiz@example.com" not in output
    assert "base64" not in output
    assert read_document(result.output_path).complete


@pytest.mark.parametrize("suffix", [".md", ".log", ".text"])
def test_plain_text_formats_are_rewritten(tmp_path, suffix):
    source = tmp_path / f"nota{suffix}"
    source.write_text("# Nota\n\n- DNI: 12345678Z\n- Correo: ana@example.com\n", "utf-8")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / f"out{suffix}", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    text = result.output_path.read_text("utf-8")
    assert "12345678Z" not in text and "ana@example.com" not in text and "# Nota" in text


def test_markup_patterns_are_linear_on_adversarial_input():
    import time

    for source in (
        "<style>" + "url(" * 50000 + "</style>",
        '<p title="' + "data:" * 50000 + '">x</p>',
        "<style>" + "url(a" * 40000 + "</style>",
        '<img srcset="' + "data:image/png;base64" * 10000 + '">',
    ):
        start = time.perf_counter()
        parse(source)
        assert time.perf_counter() - start < 2, source[:20]
