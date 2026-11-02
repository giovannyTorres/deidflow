"""Generate actual scanned PDFs and record OCR coverage or explicit unavailability.

No OCR accuracy or throughput value is produced unless a local executable and
requested traineddata are available. Synthetic fixtures stay outside the repo.
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import shutil
import sys
import time
from pathlib import Path

from deidflow import DeidEngine
from deidflow.ocr import OCRError, TesseractOCR
from deidflow.readers import DocumentError, read_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    repository = Path(__file__).resolve().parents[1]
    parser.add_argument("--work", type=Path, default=repository.parents[1] / "work" / "ocr-probe")
    parser.add_argument(
        "--output", type=Path, default=repository / "benchmarks" / "results" / "ocr-probe.json"
    )
    parser.add_argument("--tesseract", type=str)
    parser.add_argument("--language", default="spa+eng")
    args = parser.parse_args()
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    args.work.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default(size=32)
    for index in range(3):
        path = args.work / f"synthetic-scan-{index}.pdf"
        with Image.new("RGB", (1200, 400), "white") as raster:
            draw = ImageDraw.Draw(raster)
            draw.text((40, 60), f"Paciente SINTETICO {index}", fill="black", font=font)
            draw.text((40, 130), f"Correo: synthetic{index}@example.test", fill="black", font=font)
            buffer = io.BytesIO()
            raster.save(buffer, format="PNG")
            buffer.seek(0)
            canvas = Canvas(str(path), pagesize=(600, 200), invariant=1)
            canvas.drawImage(ImageReader(buffer), 0, 0, width=600, height=200)
            canvas.showPage()
            canvas.save()
        paths.append(path)
    executable = args.tesseract or shutil.which("tesseract")
    ocr = TesseractOCR(language=args.language, executable=executable) if executable else None
    engine = DeidEngine(ocr=ocr)
    records: list[dict[str, object]] = []
    extraction_start = time.perf_counter()
    ocr_failure = None
    for path in paths:
        try:
            graph = read_document(path, ocr=ocr)
            refused = False
            try:
                engine.scan(path)
            except DocumentError:
                refused = True
            records.append(
                {
                    "case": path.name,
                    "complete": graph.complete,
                    "issues": graph.issues,
                    "scan_refused": refused,
                    "ocr_fragments": sum(f.kind == "ocr" for f in graph.fragments),
                }
            )
        except OCRError:
            ocr_failure = "LOCAL_OCR_EXECUTION_FAILED"
            records.append(
                {
                    "case": path.name,
                    "complete": False,
                    "issues": [ocr_failure],
                    "scan_refused": True,
                    "ocr_fragments": 0,
                }
            )
    elapsed = time.perf_counter() - extraction_start
    available = executable is not None and ocr_failure is None
    output = {
        "schema_version": 1,
        "purpose": "actual_scanned_pdf_coverage_probe",
        "synthetic": True,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "documents": len(paths),
        "pages": len(paths),
        "requested_language": args.language,
        "ocr_status": "EXECUTED" if available else "NOT_RUN" if executable is None else "FAILED",
        "reason": None
        if available
        else "LOCAL_TESSERACT_NOT_INSTALLED"
        if executable is None
        else ocr_failure,
        "coverage_probe_wall_seconds": elapsed,
        "ocr_pages_per_second": None,
        "ocr_error_rate": None,
        "detection_recall": None,
        "note": "Coverage/routing probe only. Wall time includes extraction and refusal checks; it is not an OCR benchmark. No unavailable metric is imputed.",
        "cases": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "ocr_status": output["ocr_status"],
                "documents": len(paths),
                "scan_refusals": sum(bool(r["scan_refused"]) for r in records),
            }
        )
    )


if __name__ == "__main__":
    main()
