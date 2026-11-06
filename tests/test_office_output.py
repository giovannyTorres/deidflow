from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy
from deidflow.readers import benign_field, read_document

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = (
    f'xmlns:w="{W}" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'mc:Ignorable="w14"'
)
CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="jpeg" ContentType="image/jpeg"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail" Target="docProps/thumbnail.jpeg"/>
</Relationships>"""
DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="mailto:maria.lopez@example.com" TargetMode="External"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>"""
DRAWING = (
    '<w:r><w:drawing><wp:inline><wp:docPr id="1" name="Foto" descr="Foto de María López"/>'
    '<a:graphic><a:graphicData><pic:pic><pic:blipFill><a:blip r:embed="rId4"/></pic:blipFill>'
    "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
)
DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {NS}><w:body>
<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Paciente: </w:t></w:r><w:r><w:t>María </w:t></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>López</w:t></w:r><w:r><w:t xml:space="preserve"> García, DNI 1234</w:t></w:r><w:r><w:t>5678Z.</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Correo</w:t></w:r></w:p></w:tc><w:tc><w:p><w:hyperlink r:id="rId3"><w:r><w:t>maria.lopez@example.com</w:t></w:r></w:hyperlink></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>Teléfono</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>+34 612 345 678</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:p><w:del w:id="1" w:author="Dr. Ramón Ortega" w:date="2024-03-01T10:00:00Z"><w:r><w:delText>Antes vivía en Calle Mayor 5.</w:delText></w:r></w:del><w:ins w:id="2" w:author="Dr. Ramón Ortega" w:date="2024-03-01T10:00:00Z"><w:r><w:t>Tratamiento revisado.</w:t></w:r></w:ins><w:commentRangeStart w:id="0"/><w:r><w:t>Control en 3 meses.</w:t></w:r><w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>
<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> MERGEFIELD </w:instrText></w:r><w:r><w:instrText xml:space="preserve">Nombre_Paciente </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>Juan Pérez</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>
<w:p>{DRAWING}</w:p>
<w:sectPr><w:footerReference w:type="default" r:id="rId1"/></w:sectPr>
</w:body></w:document>"""
FOOTER = f"""<w:ftr {NS}><w:p><w:r><w:t xml:space="preserve">Página </w:t></w:r><w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>"""
COMMENTS = f"""<w:comments {NS}><w:comment w:id="0" w:author="Dr. Ramón Ortega" w:initials="RO" w:date="2024-03-01T10:00:00Z"><w:p><w:r><w:t>Avisar a la paciente.</w:t></w:r></w:p></w:comment></w:comments>"""
CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Informe de alta</dc:title><dc:creator>Ramón Ortega</dc:creator><cp:lastModifiedBy>Ramón Ortega</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">2024-03-01T10:00:00Z</dcterms:created></cp:coreProperties>"""
APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Microsoft Office Word</Application><Company>Clínica San Rafael</Company></Properties>"""
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def make_docx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("[Content_Types].xml", CONTENT_TYPES)
        out.writestr("_rels/.rels", PACKAGE_RELS)
        out.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        out.writestr("word/document.xml", DOCUMENT)
        out.writestr("word/footer1.xml", FOOTER)
        out.writestr("word/comments.xml", COMMENTS)
        out.writestr("word/media/image1.png", PNG)
        out.writestr("docProps/core.xml", CORE)
        out.writestr("docProps/app.xml", APP)
        out.writestr("docProps/thumbnail.jpeg", b"\xff\xd8\xff\xe0 first page render")
    return path


def _package_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", "replace") for name in archive.namelist()
        )


def test_docx_output_transforms_text_across_runs_and_removes_hidden_content(tmp_path):
    source = make_docx(tmp_path / "informe.docx")
    engine = DeidEngine(country="ES")
    result = engine.deidentify(
        source, output=tmp_path / "out.docx", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    package = _package_text(result.output_path)
    for secret in (
        "López",
        "12345678Z",
        "5678Z",
        "maria.lopez@example.com",
        "612 345 678",
        "Calle Mayor",
        "Ramón",
        "Ortega",
        "2024-03-01",
        "Clínica San Rafael",
        "first page render",
        "Nombre_Paciente",
        "Foto de María",
    ):
        assert secret not in package, secret
    with zipfile.ZipFile(result.output_path) as archive:
        names = set(archive.namelist())
        document = archive.read("word/document.xml").decode()
        footer = archive.read("word/footer1.xml").decode()
    assert "word/media/image1.png" not in names and "docProps/thumbnail.jpeg" not in names
    # Formatting and namespace declarations survive; the run split stays in place.
    assert "<w:b/>" in document and "<w:i/>" in document
    assert 'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"' in document
    assert 'mc:Ignorable="w14"' in document
    assert "Tratamiento revisado." in document and "Control en 3 meses." in document
    assert "<w:t>Correo</w:t>" in document
    # A layout field (PAGE) is kept, the data-bearing MERGEFIELD code is not.
    assert 'w:instr=" PAGE "' in footer
    assert "MERGEFIELD" not in document
    graph = read_document(result.output_path)
    assert graph.complete, graph.issues
    removed = result.audit["office_removed"]
    assert removed["media"] >= 1 and removed["thumbnail"] == 1 and removed["external_links"] >= 1
    assert result.audit["transformations"] >= 4


def test_docx_media_can_be_kept_but_then_blocks(tmp_path):
    source = make_docx(tmp_path / "informe.docx")
    result = DeidEngine(country="ES").deidentify(
        source,
        output=tmp_path / "out.docx",
        policy=Policy.strict(require_ner=False),
        office_media="keep",
    )
    assert result.status == "BLOCKED"
    assert "office_images_require_separate_ocr" in result.issues
    assert not (tmp_path / "out.docx").exists()
    with pytest.raises(ValueError):
        DeidEngine().deidentify(source, output=tmp_path / "x.docx", office_media="ocr")


def test_reader_flags_only_data_bearing_fields_and_thumbnails(tmp_path):
    assert benign_field(" PAGE \\* MERGEFORMAT ") and benign_field("TOC \\o 1-3 \\h")
    assert not benign_field(' HYPERLINK "mailto:x@example.com" ')
    assert not benign_field(" MERGEFIELD Nombre ") and not benign_field("")
    graph = read_document(make_docx(tmp_path / "informe.docx"))
    assert "word_fields_require_review" in graph.issues
    assert "office_thumbnail_requires_review" in graph.issues
    assert any(f.kind == "field_instruction" and "MERGEFIELD" in f.text for f in graph.fragments)


def test_docx_rejects_malformed_package_without_output(tmp_path):
    source = tmp_path / "bad.docx"
    with zipfile.ZipFile(source, "w") as out:
        out.writestr("word/document.xml", "<w:document")
    result = DeidEngine().deidentify(source, output=tmp_path / "out.docx")
    assert result.status == "BLOCKED" and not (tmp_path / "out.docx").exists()


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_docx_output_opens_in_libreoffice(tmp_path):
    source = make_docx(tmp_path / "informe.docx")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.docx", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None
    converted = subprocess.run(
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation=file://{tmp_path}/lo",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(tmp_path / "txt"),
            str(result.output_path),
        ],
        capture_output=True,
        timeout=120,
    )
    text = (tmp_path / "txt" / "out.txt").read_text("utf-8-sig")
    assert converted.returncode == 0
    assert "Paciente:" in text and "Tratamiento revisado." in text and "López" not in text
