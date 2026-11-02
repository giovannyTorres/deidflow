"""CLI emits finding locations and safe audit counters, never detected plaintext."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from deidflow import DeidEngine, Policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deidflow")
    parser.add_argument("command", choices=["scan", "deidentify", "verify", "profile"])
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument(
        "--model", type=Path, help="Explicit local Spanish spaCy pipeline directory"
    )
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument(
        "--ocr-executable", type=Path, help="Explicit local Tesseract executable (no downloads)"
    )
    parser.add_argument(
        "--tessdata-dir", type=Path, help="Directory containing local spa/eng traineddata"
    )
    parser.add_argument("--ocr-language", default="spa+eng")
    parser.add_argument("--ocr-psm", type=int, default=6)
    parser.add_argument("--ocr-timeout", type=float, default=60)
    parser.add_argument("--pdf-dpi", type=int, default=216)
    parser.add_argument("--pdf-max-pages", type=int, default=1000)
    args = parser.parse_args(argv)
    try:
        nlp = None
        if args.model:
            from deidflow.nlp import SpacyNER

            nlp = SpacyNER(args.model)
        ocr = None
        if args.ocr_executable:
            from deidflow.ocr import TesseractOCR

            ocr = TesseractOCR(
                executable=str(args.ocr_executable),
                tessdata_dir=str(args.tessdata_dir) if args.tessdata_dir else None,
                language=args.ocr_language,
                psm=args.ocr_psm,
                timeout=args.ocr_timeout,
            )
        elif args.tessdata_dir:
            parser.error("--tessdata-dir requires --ocr-executable")
        engine = DeidEngine(
            nlp=nlp, ocr=ocr, pdf_dpi=args.pdf_dpi, pdf_max_pages=args.pdf_max_pages
        )
        policy = (
            Policy.from_yaml(args.policy)
            if args.policy
            else (Policy.strict_pdf() if args.source.suffix.lower() == ".pdf" else Policy.strict())
        )
        if args.command == "scan":
            found = (
                engine.scan_csv(args.source, batch_size=args.batch_size)
                if args.source.suffix.lower() in {".csv", ".tsv"}
                else iter(engine.scan(args.source))
            )
            counts: Counter[str] = Counter()
            for finding in found:
                counts[finding.entity_type] += 1
            print(
                json.dumps(
                    {
                        "finding_count": sum(counts.values()),
                        "by_type": dict(counts),
                        "release_assessed": False,
                    }
                )
            )
            return 0
        if args.command == "profile":
            profiles = engine.profile(args.source)
            print(
                json.dumps(
                    {
                        "columns": len(profiles),
                        "classified": sum(p.entity_type is not None for p in profiles),
                        "unknown_candidates": sum(p.unknown_identifier for p in profiles),
                    }
                )
            )
            return 0
        if args.command == "deidentify":
            if not args.output:
                parser.error("deidentify requires --output")
            result = engine.deidentify(
                args.source, output=args.output, policy=policy, batch_size=args.batch_size
            )
        else:
            result = engine.verify(args.source, policy=policy)
        print(json.dumps(result.audit_dict()))
        return 0 if result.release_approved else 2
    except Exception:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error": "Processing failed; inspect input, dependencies and configuration locally",
                }
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
