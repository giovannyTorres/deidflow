"""Real local OCR on synthetic difficult layouts; no private source files."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus
from deidflow.ocr import TesseractOCR


def _engine():
    executable = os.getenv("DEIDFLOW_TEST_TESSERACT")
    if not executable or not Path(executable).is_file():
        pytest.skip("Explicit local OCR assets required")
    return DeidEngine(
        ocr=TesseractOCR(
            executable=executable, tessdata_dir=os.getenv("DEIDFLOW_TEST_TESSDATA_DIR"), psm=6
        ),
        memory_budget_mb=512,
    )


def test_rotated_native_text_is_explicitly_unsupported(tmp_path):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas").Canvas(str(tmp_path / "rotated.pdf"))
    canvas.translate(100, 100)
    canvas.rotate(90)
    canvas.drawString(0, 0, "Correo: rotated@example.test")
    canvas.save()
    # No OCR call is needed: native geometry itself is unsupported.
    result = DeidEngine(ocr=TesseractOCR()).deidentify(
        tmp_path / "rotated.pdf",
        output=tmp_path / "safe.pdf",
        policy=Policy.strict_pdf(require_ner=False),
    )
    assert result.status == ReleaseStatus.UNSUPPORTED
    assert not (tmp_path / "safe.pdf").exists()


def test_spanning_merged_table_has_no_invented_relationships_or_green_release(tmp_path):
    engine = _engine()
    source = tmp_path / "table.pdf"
    canvas = pytest.importorskip("reportlab.pdfgen.canvas").Canvas(str(source), pagesize=(500, 400))
    for page in range(2):
        canvas.setFont("Helvetica", 12)
        canvas.rect(20, 320, 460, 35)
        canvas.drawString(30, 332, "Tabla continuada: clientes ficticios")
        canvas.rect(20, 220, 460, 100)
        canvas.line(340, 220, 340, 320)
        canvas.line(20, 270, 480, 270)
        canvas.drawString(30, 290, f"Correo: tabla{page}@example.test")
        canvas.drawString(355, 290, "Importe: 42")
        canvas.drawString(30, 240, "Domicilio: Calle Luna 14")
        canvas.drawString(355, 240, "MXN")
        canvas.showPage()
    canvas.save()
    result = engine.deidentify(
        source,
        output=tmp_path / "bundle",
        outputs=["pdf", "jsonl"],
        policy=Policy.strict_pdf(require_ner=False),
        require_table_structure=True,
    )
    assert not result.release_approved
    assert result.status in {ReleaseStatus.REVIEW_REQUIRED, ReleaseStatus.BLOCKED}
    if result.safe_jsonl:
        records = [json.loads(line) for line in result.safe_jsonl.read_text().splitlines()]
        assert all(
            row["tables"] == [] and row["structure_status"] == "lines_only" for row in records
        )
        assert "@example.test" not in result.safe_jsonl.read_text()


def test_partial_text_layer_blank_page_and_hidden_text_use_actual_rasters(tmp_path):
    engine = _engine()
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    font_path = next(
        (
            p
            for p in (
                Path("C:/Windows/Fonts/arial.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            )
            if p.is_file()
        ),
        None,
    )
    if not font_path:
        pytest.skip("Local fixture font required")
    source = tmp_path / "partial.pdf"
    canvas = Canvas(str(source), pagesize=(500, 400))
    canvas.setFont("Helvetica", 12)
    canvas.drawString(20, 360, "Informe de prueba local")
    with Image.new("RGB", (900, 160), "white") as image:
        ImageDraw.Draw(image).text(
            (20, 25),
            "Correo: raster@example.test",
            fill="black",
            font=ImageFont.truetype(str(font_path), 36),
        )
        canvas.drawImage(ImageReader(image), 20, 220, width=450, height=80)
    invisible = canvas.beginText(20, 180)
    invisible.setTextRenderMode(3)
    invisible.textLine("Correo: hidden@example.test")
    canvas.drawText(invisible)
    canvas.showPage()
    canvas.showPage()  # Exactly white page must not become a failed OCR success.
    canvas.save()
    result = engine.deidentify(
        source,
        output=tmp_path / "safe.pdf",
        policy=Policy.strict_pdf(require_ner=False),
    )
    assert result.status in {ReleaseStatus.APPROVED, ReleaseStatus.REVIEW_REQUIRED}, result.issues
    assert result.records == 2
    from pypdf import PdfReader

    assert all(not page.extract_text() for page in PdfReader(result.output_path).pages)
    assert result.audit["page_receipts"][1]["all_unmasked_pixels_white"]
    assert result.audit["source_findings_by_type"]["EMAIL"] >= 2
