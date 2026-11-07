from __future__ import annotations

import csv
import email.policy
import html
import json
import zipfile
from email.message import EmailMessage
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy
from deidflow.readers import read_document


@pytest.mark.parametrize("operation", ["text", "verify"])
def test_unrecognized_word_with_internal_format_control_requires_review(tmp_path, operation):
    source = "infor\u200bme"
    engine = DeidEngine()
    policy = Policy.strict(require_ner=False)
    assert engine.scan_text(source) == []
    if operation == "text":
        result = engine.deidentify_text(source, policy=policy)
        assert result.output_text == source
    else:
        path = tmp_path / "input.txt"
        path.write_text(source, encoding="utf-8")
        result = engine.verify(path, policy=policy)
    assert result.status == "REVIEW_REQUIRED"
    assert "UNICODE_FORMAT_CONTROLS_REQUIRE_REVIEW" in result.issues


FORMATS = ("txt", "csv", "tsv", "json", "jsonl", "docx", "xlsx", "html", "eml")
CONTROLS = ("\u00ad", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff")
CONTEXT = "No se modifica la dosis. Control en tres meses."
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
T = "http://schemas.openxmlformats.org/package/2006/content-types"


def _office_document(path: Path, sensitive: str) -> None:
    if path.suffix == ".docx":
        # The identifier crosses real Word run boundaries, including a control
        # in the first run; rewriting must cover the complete logical value.
        left, separator, right = sensitive.partition(".")
        body = (
            f'<w:document xmlns:w="{W}"><w:body><w:p>'
            f"<w:r><w:t>Correo: {html.escape(left)}</w:t></w:r>"
            f"<w:r><w:t>{separator}{html.escape(right)}</w:t></w:r></w:p>"
            f"<w:p><w:r><w:t>{CONTEXT}</w:t></w:r></w:p></w:body></w:document>"
        )
        parts = {
            "word/document.xml": body,
            "word/comments.xml": (
                f'<w:comments xmlns:w="{W}"><w:comment w:id="0"><w:p><w:r>'
                f"<w:t>{html.escape(sensitive)}</w:t></w:r></w:p></w:comment></w:comments>"
            ),
        }
        primary = "word/document.xml"
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    else:
        parts = {
            "xl/workbook.xml": (
                f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets>'
                '<sheet name="Datos" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": (
                f'<Relationships xmlns="{P}"><Relationship Id="rId1" '
                f'Type="{R}/worksheet" Target="worksheets/sheet1.xml"/>'
                f'<Relationship Id="rId2" Type="{R}/sharedStrings" Target="sharedStrings.xml"/>'
                "</Relationships>"
            ),
            "xl/worksheets/sheet1.xml": (
                f'<worksheet xmlns="{S}"><sheetData>'
                '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
                '<row r="2"><c r="A2" t="s"><v>1</v></c></row>'
                "</sheetData></worksheet>"
            ),
            "xl/sharedStrings.xml": (
                f'<sst xmlns="{S}" count="2" uniqueCount="3"><si><t>texto</t></si>'
                f"<si><t>Correo: {html.escape(sensitive)}; {CONTEXT}</t></si>"
                # Deleted-cell copy is recoverable even if no grid cell uses it.
                f"<si><t>{html.escape(sensitive)}</t></si></sst>"
            ),
        }
        primary = "xl/workbook.xml"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    parts["[Content_Types].xml"] = (
        f'<Types xmlns="{T}"><Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{primary}" ContentType="{mime}"/></Types>'
    )
    parts["_rels/.rels"] = (
        f'<Relationships xmlns="{P}"><Relationship Id="rId1" '
        f'Type="{R}/officeDocument" Target="{primary}"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def _write_document(path: Path, sensitive: str) -> None:
    text = f"Correo: {sensitive}; {CONTEXT}"
    suffix = path.suffix
    if suffix in {".docx", ".xlsx"}:
        _office_document(path, sensitive)
    elif suffix in {".csv", ".tsv"}:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t" if suffix == ".tsv" else ",")
            writer.writerows([["texto"], [text]])
    elif suffix in {".json", ".jsonl"}:
        path.write_text(json.dumps({"texto": text}, ensure_ascii=False) + "\n", encoding="utf-8")
    elif suffix == ".html":
        path.write_text(
            f"<p>Correo: {html.escape(sensitive)}</p><p>{CONTEXT}</p>"
            f'<span title="{html.escape(sensitive)}">Informe.</span>',
            encoding="utf-8",
        )
    elif suffix == ".eml":
        message = EmailMessage()
        message["From"] = "remitente@example.invalid"
        message["To"] = "destino@example.invalid"
        message["Subject"] = "Informe."
        message.set_content(text)
        path.write_bytes(message.as_bytes(policy=email.policy.default))
    else:
        path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("suffix", FORMATS)
@pytest.mark.parametrize("form", [*CONTROLS, "fullwidth"])
def test_real_writers_remove_normalized_identifiers_and_preserve_context(tmp_path, suffix, form):
    sensitive = (
        "ａｎａ.lopez@example.test" if form == "fullwidth" else f"ana{form}.lopez@example.test"
    )
    source = tmp_path / ("source." + suffix)
    target = tmp_path / ("output." + suffix)
    _write_document(source, sensitive)
    source_graph = read_document(source)
    assert sensitive in "\n".join(fragment.text for fragment in source_graph.fragments)
    result = DeidEngine(country="ES").deidentify(
        source, output=target, policy=Policy.strict(require_ner=False)
    )
    assert result.output_path == target, result.issues
    assert result.status in {"APPROVED", "REVIEW_REQUIRED"}, result.issues
    recovered = "\n".join(fragment.text for fragment in read_document(target).fragments)
    assert "[EMAIL]" in recovered
    assert "lopez@example.test" not in recovered
    assert "ａｎａ" not in recovered
    assert all(control not in recovered for control in CONTROLS)
    assert CONTEXT in recovered
    if suffix in {"docx", "xlsx"}:
        with zipfile.ZipFile(target) as archive:
            recoverable_xml = "\n".join(
                archive.read(name).decode("utf-8") for name in archive.namelist()
            )
        assert "lopez@example.test" not in recoverable_xml
        assert all(control not in recoverable_xml for control in CONTROLS)


@pytest.mark.parametrize("entity", ["&#8203;", "&shy;"])
def test_html_encoded_format_controls_across_nodes_and_attributes_are_removed(tmp_path, entity):
    source = tmp_path / "source.html"
    source.write_text(
        f"<p>Correo: ana<b>{entity}</b>.lopez@example.test</p>"
        f'<span title="Correo: ana{entity}.lopez@example.test">{CONTEXT}</span>',
        encoding="utf-8",
    )
    target = tmp_path / "output.html"
    result = DeidEngine().deidentify(source, output=target, policy=Policy.strict(require_ner=False))
    assert result.output_path == target, result.issues
    raw = target.read_text(encoding="utf-8")
    assert "lopez@example.test" not in raw
    assert entity not in raw
    assert CONTEXT in raw
    assert "[EMAIL]" in raw


@pytest.mark.parametrize("suffix", FORMATS)
def test_residual_control_in_unknown_word_never_approves_a_real_writer(tmp_path, suffix):
    source = tmp_path / ("source." + suffix)
    target = tmp_path / ("output." + suffix)
    _write_document(source, "infor\u200bme")
    result = DeidEngine().deidentify(source, output=target, policy=Policy.strict(require_ner=False))
    assert result.output_path == target, result.issues
    assert result.status == "REVIEW_REQUIRED"
    assert "UNICODE_FORMAT_CONTROLS_REQUIRE_REVIEW" in result.issues
    recovered = "\n".join(fragment.text for fragment in read_document(target).fragments)
    assert "infor\u200bme" in recovered
    assert CONTEXT in recovered


@pytest.mark.parametrize("suffix", ["txt", "csv", "docx", "xlsx", "jsonl"])
def test_eml_attachments_use_the_same_original_offset_detection(tmp_path, suffix):
    attachment = tmp_path / ("material." + suffix)
    _write_document(attachment, "ana\u200d.lopez@example.test")
    message = EmailMessage()
    message["From"] = "remitente@example.invalid"
    message["To"] = "destino@example.invalid"
    message["Subject"] = "Informe."
    message.set_content(CONTEXT)
    message.add_attachment(
        attachment.read_bytes(),
        maintype="application",
        subtype="octet-stream",
        filename=attachment.name,
    )
    source = tmp_path / "source.eml"
    source.write_bytes(message.as_bytes(policy=email.policy.default))
    target = tmp_path / "output.eml"
    result = DeidEngine().deidentify(source, output=target, policy=Policy.strict(require_ner=False))
    if suffix == "xlsx":
        # Existing MIME completeness rules retain the mandatory XLSX review as
        # incomplete attachment coverage. Unicode detection cannot approve it.
        assert result.status == "BLOCKED"
        assert result.output_path is None
        assert not target.exists()
        assert "INCOMPLETE_COVERAGE" in result.issues
        return
    assert result.output_path == target, result.issues
    recovered = "\n".join(fragment.text for fragment in read_document(target).fragments)
    assert "lopez@example.test" not in recovered
    assert "\u200d" not in recovered
    assert "[EMAIL]" in recovered
    assert CONTEXT in recovered
