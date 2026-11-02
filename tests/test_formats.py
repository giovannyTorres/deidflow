from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from deidflow.ocr import OCRError, OCRResult, OCRToken, TesseractOCR
from deidflow.readers import DocumentError, UnsupportedFormat, iter_parquet_batches, read_document
from deidflow.redactors import redact_image, verify_pixels


def archive(path: Path, parts: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        for name, content in parts.items():
            stream.writestr(name, content)
    return path


def test_text_exact_unicode_and_no_plaintext_repr(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes("Señora 🌻\r\nprivate@example.test".encode())
    graph = read_document(path)
    assert graph.fragments[0].text == "Señora 🌻\r\nprivate@example.test"
    assert "private@example.test" not in repr(graph)
    assert graph.complete


def test_json_keys_values_and_numeric_fields_are_scanned(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text(
        '{"key@example.test":{"account":1234567890},"items":["value@example.test"]}',
        encoding="utf-8",
    )
    graph = read_document(path)
    values = {f.text for f in graph.fragments}
    assert {"key@example.test", "value@example.test", "1234567890"} <= values
    assert all("key@example.test" not in repr(f.location) for f in graph.fragments)


@pytest.mark.parametrize("text", ['{"x":"lost@example.test","x":"second"}', '{"x":NaN}'])
def test_json_ambiguous_input_rejected(tmp_path: Path, text: str) -> None:
    path = tmp_path / "data.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DocumentError):
        read_document(path)


def test_jsonl_and_tsv_locations(tmp_path: Path) -> None:
    path = tmp_path / "data.jsonl"
    path.write_text('{"e":"one@example.test"}\n\n{"e":"two@example.test"}\n', encoding="utf-8")
    graph = read_document(path)
    assert any(f.location.json_path == "$/line:2/value:0" for f in graph.fragments)
    path = tmp_path / "data.tsv"
    path.write_bytes(b'email\tnote\n"one@example.test"\t"first\nsecond"\n')
    graph = read_document(path)
    assert graph.fragments[-1].text == "first\nsecond"
    assert graph.fragments[-1].location.row == 1


@pytest.mark.parametrize("suffix", [".bin", ".doc", ".xls", ".pptx"])
def test_unsupported_formats(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / ("file" + suffix)
    path.write_bytes(b"not interpreted")
    with pytest.raises(UnsupportedFormat):
        read_document(path)


def test_malformed_and_excessive_inputs_do_not_leak(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes(b"secret@example.test\xff")
    with pytest.raises(DocumentError) as error:
        read_document(path)
    assert "secret" not in str(error.value)
    with pytest.raises(DocumentError):
        read_document(path, max_bytes=2)
    path = tmp_path / "broken.docx"
    path.write_bytes(b"secret@example.test")
    with pytest.raises(DocumentError) as error:
        read_document(path)
    assert "secret" not in str(error.value)


def test_docx_headers_comments_revisions_metadata_and_tables(tmp_path: Path) -> None:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    path = archive(
        tmp_path / "input.docx",
        {
            "word/document.xml": f'<w:document {ns}><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>table@example.test</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p><w:del w:author="Editor"><w:r><w:delText>deleted@example.test</w:delText></w:r></w:del><w:ins><w:r><w:t>new@example.test</w:t></w:r></w:ins></w:p></w:body></w:document>',
            "word/header1.xml": f"<w:hdr {ns}><w:p><w:r><w:t>header@example.test</w:t></w:r></w:p></w:hdr>",
            "word/footer1.xml": f"<w:ftr {ns}><w:p><w:r><w:t>footer@example.test</w:t></w:r></w:p></w:ftr>",
            "word/comments.xml": f'<w:comments {ns}><w:comment w:author="Author"><w:p><w:r><w:t>comment@example.test</w:t></w:r></w:p></w:comment></w:comments>',
            "docProps/core.xml": "<properties><author>meta@example.test</author></properties>",
        },
    )
    graph = read_document(path)
    text = "\n".join(f.text for f in graph.fragments)
    assert all(
        word in text
        for word in ["table@", "deleted@", "new@", "header@", "footer@", "comment@", "meta@"]
    )
    assert graph.complete
    assert any(f.location.part == "word/header1.xml" for f in graph.fragments)


def test_docx_embedded_and_images_block_completeness(tmp_path: Path) -> None:
    path = archive(
        tmp_path / "input.docx",
        {
            "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>',
            "word/embeddings/other.bin": "secret",
            "word/media/image1.png": "opaque",
        },
    )
    graph = read_document(path)
    assert not graph.complete
    assert "embedded_or_active_content_not_extracted" in graph.issues
    assert "office_images_require_separate_ocr" in graph.issues


def test_archive_bomb_and_entities_rejected(tmp_path: Path) -> None:
    path = archive(tmp_path / "input.docx", {"word/document.xml": "A" * (2 * 1024 * 1024)})
    with pytest.raises(DocumentError, match="compression ratio"):
        read_document(path)
    path = archive(
        tmp_path / "entities.docx",
        {"word/document.xml": '<!DOCTYPE r [<!ENTITY x "private">]><r>&x;</r>'},
    )
    with pytest.raises(DocumentError, match="entity"):
        read_document(path)


def test_duplicate_archive_members_and_ragged_csv_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.docx"
    with zipfile.ZipFile(path, "w") as stream:
        stream.writestr("word/document.xml", "<first/>")
        with pytest.warns(UserWarning):
            stream.writestr("word/document.xml", "<second/>")
    with pytest.raises(DocumentError, match="Duplicate archive"):
        read_document(path)
    path = tmp_path / "ragged.csv"
    path.write_bytes(b"first,second\none,other,extra\n")
    with pytest.raises(DocumentError, match="row width"):
        read_document(path)


def test_xlsx_orphan_shared_strings_are_scanned(tmp_path: Path) -> None:
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    parts = {
        "xl/workbook.xml": f"<workbook {ns}/>",
        "xl/sharedStrings.xml": f"<sst {ns}><si><t>ordinary</t></si><si><t>deleted@example.test</t></si></sst>",
        "xl/worksheets/sheet1.xml": f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>',
    }
    path = archive(tmp_path / "orphan.xlsx", parts)
    graph = read_document(path)
    assert any(
        f.text == "deleted@example.test" and f.kind == "shared_string" for f in graph.fragments
    )
    parts["xl/worksheets/sheet1.xml"] = parts["xl/worksheets/sheet1.xml"].replace(
        "<v>0</v>", "<v>-1</v>"
    )
    path = archive(tmp_path / "negative-reference.xlsx", parts)
    with pytest.raises(DocumentError, match="shared string reference"):
        read_document(path)


def test_xlsx_hidden_comments_formulas_headers_and_metadata(tmp_path: Path) -> None:
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    path = archive(
        tmp_path / "input.xlsx",
        {
            "xl/workbook.xml": f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Hidden" state="veryHidden" sheetId="1" r:id="rId1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/></Relationships>',
            "xl/sharedStrings.xml": f"<sst {ns}><si><t>hidden@example.test</t></si></sst>",
            "xl/worksheets/sheet1.xml": f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="str"><f>"formula@example.test"</f><v>cached@example.test</v></c></row></sheetData><headerFooter><oddHeader>header@example.test</oddHeader></headerFooter></worksheet>',
            "xl/comments/comment1.xml": f'<comments {ns}><authors><author>author@example.test</author></authors><commentList><comment ref="A1" authorId="0"><text><t>comment@example.test</t></text></comment></commentList></comments>',
            "docProps/core.xml": "<properties><author>meta@example.test</author></properties>",
        },
    )
    graph = read_document(path)
    text = "\n".join(f.text for f in graph.fragments)
    assert all(
        word in text
        for word in ["hidden@", "formula@", "cached@", "header@", "comment@", "author@", "meta@"]
    )
    assert any(f.metadata.get("sheet_state") == "veryHidden" for f in graph.fragments)
    assert not graph.complete
    assert "spreadsheet_formulas_require_review" in graph.issues


class LocalTestOCR:
    """Deterministic adapter fixture; not used for accuracy/performance claims."""

    def __init__(self, confidence: float = 95) -> None:
        self.confidence = confidence

    def recognize(self, image: object) -> OCRResult:
        return OCRResult(
            (
                OCRToken("one@example.test", (1, 2, 80, 20), self.confidence),
                OCRToken("next", (1, 30, 40, 50), 95, (0, 0, 1)),
            ),
            image.width,
            image.height,
            "test-fixture",
        )


def test_ocr_preserves_offsets_confidence_coordinates(tmp_path: Path) -> None:
    image = pytest.importorskip("PIL.Image")
    path = tmp_path / "input.png"
    image.new("RGB", (100, 100), "white").save(path)
    graph = read_document(path, ocr=LocalTestOCR())
    fragment = graph.fragments[0]
    assert fragment.text == "one@example.test\nnext"
    assert fragment.metadata["tokens"][0] == {
        "start": 0,
        "end": 16,
        "bbox": (1, 2, 80, 20),
        "confidence": 95,
    }
    assert fragment.location.page == 1
    assert graph.complete
    low = read_document(path, ocr=LocalTestOCR(20))
    assert not low.complete
    assert "low_ocr_confidence" in low.issues
    missing = read_document(path)
    assert not missing.complete
    assert "ocr_required_but_not_configured" in missing.issues


def test_ocr_adapter_empty_or_invalid_result_never_approves_coverage(tmp_path: Path) -> None:
    image = pytest.importorskip("PIL.Image")
    path = tmp_path / "input.png"
    image.new("RGB", (100, 100), "white").save(path)

    class Adapter:
        def __init__(self, result: OCRResult) -> None:
            self.result = result

        def recognize(self, raster: object) -> OCRResult:
            return self.result

    for invalid in [
        OCRResult((), 100, 100, "empty"),
        OCRResult((OCRToken("word", (0, 0, 110, 20), 99),), 100, 100, "bad-box"),
        OCRResult((OCRToken("word", (0, 0, 90, 20), float("nan")),), 100, 100, "bad-score"),
        OCRResult((OCRToken("word", (0, 0, 90, 20), 99),), 200, 100, "bad-size"),
    ]:
        with pytest.raises(OCRError):
            read_document(path, ocr=Adapter(invalid))


def test_pixel_redaction_reopens_png_and_removes_metadata(tmp_path: Path) -> None:
    image = pytest.importorskip("PIL.Image")
    png = pytest.importorskip("PIL.PngImagePlugin")
    path = tmp_path / "input.png"
    metadata = png.PngInfo()
    metadata.add_text("private", "meta@example.test")
    image.new("RGBA", (100, 60), (255, 0, 0, 0)).save(path, pnginfo=metadata)
    output = tmp_path / "safe.png"
    result = redact_image(path, output, [(10, 10, 60, 40)])
    assert result.pixels_verified and result.metadata_removed
    assert result.status == "REVIEW_REQUIRED"
    assert verify_pixels(output, result.masks)
    assert not verify_pixels(output, [])
    assert not verify_pixels(output, [(100, 60, 150, 90)])
    with image.open(output) as reopened:
        assert reopened.getpixel((15, 15)) == (0, 0, 0)
        assert reopened.getpixel((0, 0)) == (255, 255, 255)
        assert not reopened.info
    with pytest.raises(DocumentError):
        redact_image(path, path, [(10, 10, 60, 40)])
    with pytest.raises(DocumentError):
        redact_image(path, tmp_path / "unsafe.jpg", [(10, 10, 60, 40)])
    with pytest.raises(DocumentError):
        redact_image(path, output, [])


def test_image_multiple_frames_not_silently_dropped(tmp_path: Path) -> None:
    image = pytest.importorskip("PIL.Image")
    path = tmp_path / "frames.tiff"
    first = image.new("RGB", (100, 100), "white")
    second = image.new("RGB", (100, 100), "black")
    first.save(path, save_all=True, append_images=[second])
    graph = read_document(path, ocr=LocalTestOCR())
    assert [f.location.page for f in graph.fragments] == [1, 2]
    with pytest.raises(DocumentError, match="multi-frame"):
        redact_image(path, tmp_path / "out.png", [(0, 0, 10, 10)])


def test_pdf_native_text_and_missing_ocr_gate(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    path = tmp_path / "native.pdf"
    writer = canvas.Canvas(str(path))
    writer.drawString(72, 700, "Contact: native@example.test, a long enough text page.")
    writer.showPage()
    writer.save()
    graph = read_document(path)
    assert graph.complete
    assert any("native@example.test" in f.text for f in graph.fragments)
    assert graph.metadata["page_count"] == 1
    path = tmp_path / "blank.pdf"
    writer = canvas.Canvas(str(path))
    writer.showPage()
    writer.save()
    graph = read_document(path)
    assert not graph.complete
    assert "pdf_regions_require_ocr" in graph.issues


def test_pdf_ocr_renders_only_required_pages(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    path = tmp_path / "mixed.pdf"
    writer = canvas.Canvas(str(path))
    writer.drawString(72, 700, "This page contains enough native text to avoid OCR.")
    writer.showPage()
    writer.showPage()
    writer.save()
    graph = read_document(path, ocr=LocalTestOCR())
    assert graph.complete
    assert len([f for f in graph.fragments if f.kind == "ocr"]) == 1
    assert [f.location.page for f in graph.fragments if f.kind == "ocr"] == [2]


def test_tesseract_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        TesseractOCR(timeout=0)
    with pytest.raises(ValueError):
        TesseractOCR(min_confidence=101)


def test_tesseract_missing_binary_fails_explicitly(tmp_path: Path) -> None:
    image = pytest.importorskip("PIL.Image")
    pytest.importorskip("pytesseract")
    with pytest.raises(OCRError, match="Local OCR"):
        TesseractOCR(executable=str(tmp_path / "missing.exe")).recognize(
            image.new("RGB", (100, 100))
        )


def test_parquet_all_rows_and_bounded_batches(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "input.parquet"
    table = pa.table(
        {"email": [f"person{i}@example.test" for i in range(25)], "amount": list(range(25))}
    )
    pq.write_table(table, path, row_group_size=10)
    graph = read_document(path)
    assert graph.complete
    assert graph.metadata["row_count"] == 25
    assert len([f for f in graph.fragments if f.kind == "cell"]) == 50
    assert any(f.text == "person24@example.test" and f.location.row == 24 for f in graph.fragments)
    batches = list(iter_parquet_batches(path, batch_size=7))
    assert sum(b.num_rows for b in batches) == 25
    assert max(b.num_rows for b in batches) <= 7


def test_parquet_nested_schema_metadata_and_empty_headers(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "nested.parquet"
    table = pa.table({"patient": [{"email": "nested@example.test"}]}).replace_schema_metadata(
        {b"author": b"meta@example.test"}
    )
    pq.write_table(table, path)
    graph = read_document(path)
    assert not graph.complete
    assert "nested_parquet_fields_require_review" in graph.issues
    assert any(f.text == "meta@example.test" for f in graph.fragments)
    path = tmp_path / "empty.parquet"
    pq.write_table(pa.table({"header@example.test": pa.array([], type=pa.string())}), path)
    graph = read_document(path)
    assert any(f.text == "header@example.test" for f in graph.fragments)
    assert graph.metadata["row_count"] == 0
