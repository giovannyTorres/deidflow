"""Invoke only from an independently launched, external private terminal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .gmail import PrivateConfig, connect
from .reports import validate_report
from .runner import benchmark, quiet_private_runtime
from .security import (
    PrivateArgumentParser,
    PrivateError,
    private_path,
    require_external_terminal,
    write_private,
)


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(prog="deidflow benchmark private-gmail")
    parser.add_argument("--config", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--inventory", action="store_true")
    choice.add_argument("--run", action="store_true")
    choice.add_argument("--authorize", action="store_true")
    choice.add_argument("--review-personal", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--external-terminal-ack", action="store_true")
    parser.add_argument("--consent-display-metadata", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--ocr-executable", type=Path)
    parser.add_argument("--tessdata-dir", type=Path)
    parser.add_argument("--model", type=Path)
    try:
        args = parser.parse_args(argv)
        require_external_terminal(args.external_terminal_ack)
        if args.run and not args.local_only:
            raise PrivateError("EXTERNAL_TERMINAL_REQUIRED")
        if args.review_personal and args.consent_display_metadata is not True:
            raise PrivateError("ANNOTATION_CONSENT_REQUIRED")
        config = PrivateConfig.load(args.config)
        with quiet_private_runtime():
            transport = connect(config, authorize=args.authorize, external_terminal_ack=True)
        if args.authorize:
            print(json.dumps({"status": "PERSONAL_READ_ONLY_AUTHORIZED"}))
            return 0
        if args.review_personal:
            from .review import serve_personal_review

            serve_personal_review(config, transport)
            return 0
        from deidflow import DeidEngine

        nlp, ocr = None, None
        if args.model:
            from deidflow.nlp import SpacyNER

            nlp = SpacyNER(args.model)
        if args.ocr_executable:
            from deidflow.ocr import TesseractOCR

            ocr = TesseractOCR(
                executable=str(args.ocr_executable),
                tessdata_dir=args.tessdata_dir,
                language="spa+eng",
            )
        result = benchmark(
            config,
            transport,
            DeidEngine(ocr=ocr, nlp=nlp),
            run=args.run,
            external_terminal_ack=True,
        )
        validate_report(result)
        if args.report:
            write_private(private_path(args.report), (json.dumps(result, indent=2) + "\n").encode())
        print(json.dumps(result))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"status": "PRIVATE_OPERATION_STOPPED"}))
        return 130
    except Exception as error:
        code = error.code if isinstance(error, PrivateError) else "PRIVATE_OPERATION_FAILED"
        print(json.dumps({"status": "BLOCKED", "code": code}), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
