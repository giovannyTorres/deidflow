"""CLI emits finding locations and safe audit counters, never detected plaintext."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from deidflow import DeidEngine, Policy, __version__


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:2] == ["benchmark", "private-gmail"]:
        from deidflow.private.cli import main as private_main

        return private_main(arguments[2:])
    if arguments[:1] == ["annotate"]:
        from deidflow.private.annotation import main as annotation_main

        return annotation_main(arguments[1:])
    parser = argparse.ArgumentParser(
        prog="deidflow",
        epilog=(
            "Private workflows (external terminal only): "
            "deidflow benchmark private-gmail --help; deidflow annotate --help. "
            "See docs/PRIVATE_GMAIL_BENCHMARK.md before using private data."
        ),
    )
    parser.add_argument("--version", action="version", version=f"deidflow {__version__}")
    parser.add_argument("command", choices=["scan", "deidentify", "verify", "profile"])
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument(
        "--model", type=Path, help="Explicit local Spanish spaCy pipeline directory"
    )
    parser.add_argument(
        "--tagger",
        help="Local span tagger: a model file path, builtin:<name> for a packaged model, "
        "or builtin:auto to route each document to the clinical or financial model",
    )
    parser.add_argument("--tagger-sha256", help="Required SHA-256 of a --tagger model file")
    parser.add_argument(
        "--tagger-profile",
        help="Packaged operating profile for built-in taggers (see docs/TAGGER.md)",
    )
    parser.add_argument(
        "--redact-margin",
        type=float,
        help="Also redact near-miss tagger candidates without forcing review (over-redacts)",
    )
    parser.add_argument(
        "--review-margin",
        type=float,
        help="Also flag near-miss tagger candidates for review (trades review load for recall)",
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
    parser.add_argument(
        "--pdf-workers", type=int, default=1, help="Bounded concurrent local OCR processes, 1-8"
    )
    parser.add_argument(
        "--profile-stages",
        action="store_true",
        help="Record numeric-only PDF stage timing and sampled memory",
    )
    parser.add_argument(
        "--outputs",
        nargs="+",
        choices=["pdf", "jsonl"],
        help="PDF+JSONL creates a new output bundle directory",
    )
    parser.add_argument(
        "--require-table-structure",
        action="store_true",
        help="Require review if table relationships cannot be reconstructed",
    )
    args = parser.parse_args(arguments)
    if args.tagger_sha256 and not args.tagger:
        parser.error("--tagger-sha256 requires --tagger")
    if (
        args.review_margin is not None or args.redact_margin is not None or args.tagger_profile
    ) and not args.tagger:
        parser.error("--review-margin, --redact-margin and --tagger-profile require --tagger")
    try:
        adapters: list[object] = []
        if args.model:
            from deidflow.nlp import SpacyNER

            adapters.append(SpacyNER(args.model))
        if args.tagger:
            from deidflow.nlp.tagger import SpanTagger

            margins = {"review_margin": args.review_margin, "redact_margin": args.redact_margin}
            if args.tagger.startswith("builtin:"):
                if args.tagger_sha256:
                    parser.error("Built-in taggers are verified against their pinned digest")
                if args.tagger == "builtin:auto":
                    from deidflow.nlp.router import DomainRouter

                    if any(value is not None for value in margins.values()):
                        parser.error("builtin:auto takes --tagger-profile, not explicit margins")
                    adapters.append(DomainRouter.builtin(profile=args.tagger_profile))
                else:
                    adapters.append(
                        SpanTagger.builtin(args.tagger[8:], profile=args.tagger_profile, **margins)
                    )
            else:
                if args.tagger_profile:
                    parser.error("--tagger-profile applies to built-in taggers only")
                adapters.append(SpanTagger.load(args.tagger, sha256=args.tagger_sha256, **margins))
        nlp = None
        if len(adapters) == 1:
            nlp = adapters[0]
        elif adapters:
            from deidflow.nlp import CombinedNER

            nlp = CombinedNER(*adapters)
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
            nlp=nlp,
            ocr=ocr,
            pdf_dpi=args.pdf_dpi,
            pdf_max_pages=args.pdf_max_pages,
            pdf_workers=args.pdf_workers,
            pdf_profile=args.profile_stages,
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
                args.source,
                output=args.output,
                policy=policy,
                batch_size=args.batch_size,
                outputs=args.outputs,
                require_table_structure=args.require_table_structure,
            )
        else:
            result = engine.verify(args.source, policy=policy)
        print(json.dumps(result.audit_dict()))
        return 0 if result.release_approved else 2
    except Exception as error:
        # The exception class is safe to report; its message may contain document text.
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error": "Processing failed; inspect input, dependencies and configuration locally",
                    "error_type": type(error).__name__,
                }
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
