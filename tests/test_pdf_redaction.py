from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from deidflow import DeidEngine, Finding, Policy, ReleaseStatus, Rule
from deidflow.ocr import OCRError, OCRResult, OCRToken, TesseractOCR
from deidflow.redactors.pdf import (
    PDFRedactionError,
    _box,
    _native_text,
    _ocr_masks,
    _ocr_text,
    _RasterWriter,
    _verification_image,
    _verify_encoded,
    redact_pdf,
    verify_pdf,
)


def _native(path: Path, *, pages: int = 1) -> None:
    canvas = pytest.importorskip("reportlab.pdfgen.canvas").Canvas(str(path), pagesize=(300, 200))
    for _ in range(pages):
        canvas.setFont("Helvetica", 12)
        canvas.drawString(20, 170, "Informe de prueba")
        canvas.drawString(20, 130, "Correo: demo@example.test")
        canvas.drawString(20, 90, "Importe: 42 pesos")
        canvas.showPage()
    canvas.save()


class _FixedOCR:
    """Deterministic adapter tests mechanics only, never benchmark accuracy."""

    min_confidence = 50

    def recognize(self, image):
        token = OCRToken("Informe", (10, 10, 70, 25), 99, (1, 1, 1))
        return OCRResult((token,), image.width, image.height, "test-adapter")


def _engine(ocr=None):
    return DeidEngine(ocr=ocr or _FixedOCR())


def _policy():
    return Policy(default=Rule("redact"), require_ner=False)


def test_token_mapping_masks_complete_intersecting_token():
    result = OCRResult(
        (OCRToken("x@example.test", (10, 20, 100, 40), 99, (1, 1, 1)),), 200, 100, "test"
    )
    text, spans, _ = _ocr_text(result, (200, 100))
    boxes = _ocr_masks(
        text, spans, [Finding("EMAIL", 2, 8, 0.9, "test")], _policy(), None, 200, 100, 3
    )
    assert boxes == [(7, 17, 103, 43)]


def test_token_metadata_and_geometry_fail_closed():
    with pytest.raises(PDFRedactionError):
        _ocr_text(
            OCRResult((OCRToken("text", (0, 0, 10, 10), float("nan")),), 20, 20, "test"), (20, 20)
        )
    with pytest.raises(PDFRedactionError):
        _box((100, 10, 101, 20), 20, 20, 2)


def test_native_char_indices_do_not_assume_extracted_text_offsets():
    class Page:
        def count_chars(self):
            return 3

    class Raw:
        def FPDFText_GetUnicode(self, page, index):
            return [ord("A"), 0, 0x1F600][index]

    text, indices = _native_text(Page(), Raw())
    assert text == "A😀" and indices == [0, 2]


def test_minimal_streaming_pdf_actual_raster_integrity(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    PdfReader = pytest.importorskip("pypdf").PdfReader
    path = tmp_path / "clean.pdf"
    with Image.new("RGB", (30, 20), "black") as image, path.open("wb") as handle:
        writer = _RasterWriter(handle, 10000)
        writer.page(image, (30, 20))
        writer.finish()
        receipt = {
            "raster_width": 30,
            "raster_height": 20,
            "raster_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
            "page_width": 30,
            "page_height": 20,
            "masks": [(0, 0, 30, 20)],
        }
    _verify_encoded(path, [receipt], PdfReader)
    receipt["raster_sha256"] = "0" * 64
    with pytest.raises(PDFRedactionError, match="raster"):
        _verify_encoded(path, [receipt], PdfReader)


def test_encoded_verification_releases_each_decoded_page(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    PdfReader = pytest.importorskip("pypdf").PdfReader
    path = tmp_path / "many.pdf"
    receipts = []
    with Image.new("RGB", (20, 20), "black") as image, path.open("wb") as handle:
        writer = _RasterWriter(handle, 100000)
        for _ in range(20):
            writer.page(image, (20, 20))
            receipts.append(
                {
                    "raster_width": 20,
                    "raster_height": 20,
                    "raster_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                    "page_width": 20,
                    "page_height": 20,
                    "masks": [(0, 0, 20, 20)],
                }
            )
        writer.finish()
    readers = []

    def tracked(*args, **kwargs):
        reader = PdfReader(*args, **kwargs)
        readers.append(reader)
        return reader

    _verify_encoded(path, receipts, tracked)
    assert all(
        page["/Resources"]["/XObject"]["/Im0"].get_object().decoded_self is None
        for page in readers[0].pages
    )


def test_native_removal_has_no_original_objects_text_or_metadata(tmp_path):
    PdfReader = pytest.importorskip("pypdf").PdfReader
    PdfWriter = pytest.importorskip("pypdf").PdfWriter
    source = tmp_path / "original.pdf"
    _native(source)
    writer = PdfWriter(clone_from=source)
    writer.add_metadata({"/Author": "private@example.test", "/Title": "Confidential"})
    writer.add_attachment("private.txt", b"attachment@example.test")
    source2 = tmp_path / "attached.pdf"
    writer.write(source2)
    output = tmp_path / "safe.pdf"
    result = redact_pdf(source2, output, engine=_engine(), policy=_policy(), dpi=144)
    assert result.release_approved and result.records == 1
    reader = PdfReader(output)
    assert reader.metadata is None and not reader.pages[0].extract_text()
    assert "/Names" not in reader.trailer["/Root"]
    assert (
        result.audit["encoded_pixels_verified"] and result.audit["original_objects_copied"] is False
    )
    assert result.audit["masks"] > 0
    assert "demo@example.test" not in repr(result.audit)
    assert source2.exists()


def test_low_ocr_confidence_forces_review(tmp_path):
    class Low(_FixedOCR):
        def recognize(self, image):
            return OCRResult(
                (OCRToken("Informe", (10, 10, 70, 25), 20, (1, 1, 1)),),
                image.width,
                image.height,
                "test",
            )

    source = tmp_path / "in.pdf"
    _native(source)
    result = redact_pdf(
        source, tmp_path / "safe.pdf", engine=_engine(Low()), policy=_policy(), dpi=144
    )
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "LOW_SOURCE_OCR_CONFIDENCE" in result.issues


def test_invisible_native_text_is_not_carried_into_output(tmp_path):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas").Canvas
    PdfReader = pytest.importorskip("pypdf").PdfReader
    source = tmp_path / "hidden.pdf"
    c = canvas(str(source), pagesize=(300, 200))
    c.drawString(20, 170, "Informe visible")
    hidden = c.beginText(20, 130)
    hidden.setTextRenderMode(3)
    hidden.textOut("hidden@example.test")
    c.drawText(hidden)
    c.save()
    output = tmp_path / "safe.pdf"
    result = redact_pdf(source, output, engine=_engine(), policy=_policy(), dpi=144)
    assert result.release_approved
    assert result.audit["source_findings_by_type"]["EMAIL"] == 1
    assert not PdfReader(output).pages[0].extract_text()


def test_annotation_payload_is_removed(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    source = tmp_path / "source.pdf"
    _native(source)
    writer = pypdf.PdfWriter(clone_from=source)
    from pypdf.annotations import Text

    writer.add_annotation(
        0, Text(rect=(220, 20, 250, 50), text="annotation@example.test", open=False)
    )
    annotated = tmp_path / "annotated.pdf"
    writer.write(annotated)
    output = tmp_path / "safe.pdf"
    result = redact_pdf(annotated, output, engine=_engine(), policy=_policy(), dpi=144)
    assert result.release_approved
    assert "/Annots" not in pypdf.PdfReader(output).pages[0]


def test_default_requires_semantic_adapter(tmp_path):
    source = tmp_path / "in.pdf"
    _native(source)
    result = redact_pdf(source, tmp_path / "safe.pdf", engine=_engine(), dpi=144)
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues


@pytest.mark.parametrize(
    "action", ["placeholder", "pseudonym", "date_shift", "custom", "generalize", "mask", "bucket"]
)
def test_unsupported_operator_never_silently_substituted(tmp_path, action):
    rule = Rule(action, custom="test" if action == "custom" else None)
    output = tmp_path / "safe.pdf"
    result = redact_pdf(tmp_path / "in.pdf", output, engine=_engine(), policy=Policy(default=rule))
    assert result.status == ReleaseStatus.UNSUPPORTED and not output.exists()


def test_missing_or_failed_ocr_never_releases(tmp_path):
    source = tmp_path / "in.pdf"
    _native(source)
    assert (
        redact_pdf(source, tmp_path / "one.pdf", engine=DeidEngine()).status
        == ReleaseStatus.BLOCKED
    )

    class Fail:
        def recognize(self, image):
            raise OCRError("source text must not escape")

    result = redact_pdf(source, tmp_path / "two.pdf", engine=_engine(Fail()), policy=_policy())
    assert result.status == ReleaseStatus.BLOCKED and not (tmp_path / "two.pdf").exists()
    assert "source text" not in str(result.issues)
    assert not list(tmp_path.glob(".deidflow-*"))


def test_output_residual_blocks_and_removes_candidate(tmp_path):
    class Leak(_FixedOCR):
        calls = 0

        def recognize(self, image):
            self.calls += 1
            value = "Informe" if self.calls == 1 else "leak@example.test"
            return OCRResult(
                (OCRToken(value, (10, 10, 100, 25), 99, (1, 1, 1)),),
                image.width,
                image.height,
                "test",
            )

    source = tmp_path / "in.pdf"
    _native(source)
    result = redact_pdf(
        source, tmp_path / "safe.pdf", engine=_engine(Leak()), policy=_policy(), dpi=144
    )
    assert result.status == ReleaseStatus.BLOCKED
    assert not (tmp_path / "safe.pdf").exists()


def test_no_overwrite_inplace_invalid_limits(tmp_path):
    source = tmp_path / "in.pdf"
    _native(source)
    with pytest.raises(ValueError):
        redact_pdf(source, source, engine=_engine())
    output = tmp_path / "exists.pdf"
    output.write_bytes(b"previous")
    with pytest.raises(FileExistsError):
        redact_pdf(source, output, engine=_engine())
    assert output.read_bytes() == b"previous"
    with pytest.raises(ValueError):
        redact_pdf(source, tmp_path / "invalid.pdf", engine=_engine(), dpi=1)


def test_geometry_encryption_and_forms_are_unsupported(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    source = tmp_path / "in.pdf"
    _native(source)
    for kind in ("rotation", "crop", "encrypted", "form"):
        writer = pypdf.PdfWriter(clone_from=source)
        if kind == "rotation":
            writer.pages[0].rotate(90)
        elif kind == "crop":
            writer.pages[0].cropbox.upper_right = (250, 180)
        elif kind == "encrypted":
            writer.encrypt("private")
        else:
            from pypdf.generic import DictionaryObject, NameObject

            writer.root_object[NameObject("/AcroForm")] = DictionaryObject()
        path = tmp_path / (kind + ".pdf")
        writer.write(path)
        result = redact_pdf(
            path, tmp_path / (kind + "-safe.pdf"), engine=_engine(), policy=_policy()
        )
        assert result.status == ReleaseStatus.UNSUPPORTED


def test_page_memory_and_byte_limits_fail_closed(tmp_path):
    source = tmp_path / "in.pdf"
    _native(source, pages=2)
    assert (
        redact_pdf(
            source, tmp_path / "pages.pdf", engine=_engine(), policy=_policy(), max_pages=1
        ).status
        == ReleaseStatus.BLOCKED
    )
    assert (
        redact_pdf(
            source, tmp_path / "bytes.pdf", engine=_engine(), policy=_policy(), max_bytes=10
        ).status
        == ReleaseStatus.BLOCKED
    )
    assert (
        redact_pdf(
            source,
            tmp_path / "memory.pdf",
            engine=_engine(),
            policy=_policy(),
            dpi=600,
            memory_budget_mb=16,
        ).status
        == ReleaseStatus.BLOCKED
    )


def test_standalone_verification_never_assumes_receipt(tmp_path):
    source = tmp_path / "in.pdf"
    _native(source)
    result = verify_pdf(source, engine=_engine(), policy=_policy(), dpi=144)
    # FixedOCR intentionally knows no email; source has not been transformed.
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "PDF_TRANSFORMATION_RECEIPT_REQUIRED" in result.issues


def test_source_mutation_before_release_blocks(tmp_path):
    source = tmp_path / "in.pdf"
    _native(source)

    class Mutate(_FixedOCR):
        calls = 0

        def recognize(self, image):
            self.calls += 1
            if self.calls == 2:
                source.write_bytes(source.read_bytes() + b"\n% changed\n")
            return super().recognize(image)

    result = redact_pdf(
        source, tmp_path / "safe.pdf", engine=_engine(Mutate()), policy=_policy(), dpi=144
    )
    assert result.status == ReleaseStatus.BLOCKED
    assert "SOURCE_CHANGED_DURING_PROCESSING" in result.issues
    assert not (tmp_path / "safe.pdf").exists()


def test_ocr_exclusion_requires_actual_constant_pixels():
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    with Image.new("RGB", (20, 20), "black") as image:
        with _verification_image(image, [(0, 0, 20, 20)], ImageDraw) as verified:
            assert verified.getpixel((1, 1)) == (255, 255, 255)
        # An original white glyph retained in a supposed black region must fail.
        image.putpixel((5, 5), (255, 255, 255))
        with pytest.raises(PDFRedactionError, match="actual solid"):
            _verification_image(image, [(0, 0, 20, 20)], ImageDraw)


def test_real_spanish_ocr_pdf_roundtrip_offline(tmp_path, monkeypatch):
    executable = os.environ.get("DEIDFLOW_TEST_TESSERACT")
    if not executable:
        pytest.skip("Explicit local Tesseract executable not configured")
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("Network access attempted")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    source = tmp_path / "real.pdf"
    _native(source)
    ocr = TesseractOCR(
        executable=executable, tessdata_dir=os.environ.get("DEIDFLOW_TEST_TESSDATA_DIR"), psm=6
    )
    result = redact_pdf(
        source, tmp_path / "safe.pdf", engine=DeidEngine(ocr=ocr), policy=_policy(), dpi=216
    )
    assert result.status in {ReleaseStatus.APPROVED, ReleaseStatus.REVIEW_REQUIRED}
    assert (
        result.audit["encoded_pixels_verified"]
        and result.audit["output_rerendered_and_ocr_verified"]
    )
    assert result.audit["masks"] > 0 and result.audit["pages"] == 1
