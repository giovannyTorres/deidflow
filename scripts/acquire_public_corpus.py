"""Explicit pinned public-data acquisition, never private Gmail access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from deidflow.benchmarks.public_corpus import acquire, acquire_from_checkout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["meddocan", "tab"])
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--from-checkout",
        type=Path,
        help="git checkout at the pinned commit; verified with the per-file digest manifest",
    )
    args = parser.parse_args()
    result = (
        acquire_from_checkout(args.source, args.from_checkout, args.destination)
        if args.from_checkout
        else acquire(args.source, args.destination)
    )
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "source",
                    "license",
                    "language",
                    "gold",
                    "provenance_kind",
                    "extracted_files",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
