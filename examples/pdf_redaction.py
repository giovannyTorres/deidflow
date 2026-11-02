"""Local native/scanned PDF reconstruction; never installs or uploads assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from deidflow import DeidEngine, Policy
from deidflow.ocr import TesseractOCR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--runtime", type=Path, default=Path(__file__).resolve().parents[3] / "work/tesseract-5.5.4"
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Explicitly accept the narrower rules-only release gate",
    )
    parser.add_argument("--dpi", type=int, default=216)
    args = parser.parse_args()
    ocr = TesseractOCR(
        executable=str(args.runtime / "bin/tesseract.exe"),
        tessdata_dir=args.runtime / "share/tessdata",
        language="spa+eng",
        psm=6,
        timeout=60,
    )
    result = DeidEngine(ocr=ocr, pdf_dpi=args.dpi).deidentify(
        args.source, output=args.output, policy=Policy.strict_pdf(require_ner=not args.rules_only)
    )
    # Safe counters only; recognized text and private locations stay out of logs.
    summary = {
        "status": str(result.status),
        "issues": result.issues,
        "pages": result.records,
        "physical_masks": result.audit.get("masks"),
        "pixels_verified": result.audit.get("encoded_pixels_verified"),
        "release_approved": result.release_approved,
    }
    print(json.dumps(summary))
    return 0 if result.release_approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
