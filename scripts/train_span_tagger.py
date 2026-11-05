"""Train the local span tagger on a public gold corpus or local span JSONL.

Weights are fitted on the training split; the validation split selects the epoch
and fits calibration. The test split is never read here.

    python scripts/train_span_tagger.py meddocan --corpus ../work/public-corpora/verified/meddocan \
        --output src/deidflow/models/es-clinical-meddocan-1.json.gz \
        --report benchmarks/results/tagger/training-report.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

from deidflow.benchmarks.public_corpus import SOURCES, load_public, verify_acquired_corpus
from deidflow.benchmarks.span_corpus import (
    GRETEL_FINANCE,
    gretel_files,
    hash_split,
    load_gretel_finance,
    load_span_jsonl,
    verify_registered_files,
)
from deidflow.training.tagger import train_span_tagger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", choices=["meddocan", "gretel_finance", "jsonl"])
    parser.add_argument(
        "--corpus", type=Path, help="Verified MEDDOCAN or registered Gretel finance directory"
    )
    parser.add_argument("--language", default="Spanish", help="gretel_finance language")
    parser.add_argument("--validation-fraction", type=float, default=0.1)
    parser.add_argument("--train-jsonl", type=Path)
    parser.add_argument("--validation-jsonl", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--version", default="es-clinical-meddocan-1")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--min-feature-docs", type=int, default=2)
    parser.add_argument("--prune-below", type=float, default=0.0)
    args = parser.parse_args()

    if args.source == "meddocan":
        if args.corpus is None:
            parser.error("--corpus is required for meddocan")
        integrity = verify_acquired_corpus(args.corpus, "meddocan")
        train = load_public(args.corpus, "meddocan", "train").examples
        validation = load_public(args.corpus, "meddocan", "dev").examples
        specification = SOURCES["meddocan"]
        provenance = {
            "source": "meddocan",
            "repository": specification["repository"],
            "commit": specification["commit"],
            "license": specification["license"],
            "license_url": specification["license_url"],
            "attribution": specification["attribution"],
            "file_digest_manifest_sha256": integrity["file_digest_manifest_sha256"]
            if "file_digest_manifest_sha256" in integrity
            else specification["file_digest_manifest_sha256"],
            "splits": {"weights": "train", "epoch_selection_and_calibration": "dev"},
            "changes": "Gold labels mapped to DeidFlow categories; no source text edits",
            "provenance_kind": specification["provenance_kind"],
        }
    elif args.source == "gretel_finance":
        if args.corpus is None:
            parser.error("--corpus is required for gretel_finance")
        integrity = verify_registered_files(args.corpus, "gretel_finance")
        files = gretel_files(args.corpus, "train")
        published = load_gretel_finance(files, language=args.language, split="train")
        train, validation = hash_split(
            published.examples, validation_fraction=args.validation_fraction
        )
        manifest = json.loads(
            (args.corpus.parent / "gretel_finance-provenance.json").read_text("utf-8")
        )
        provenance = {
            "source": "gretel_finance",
            "repository": GRETEL_FINANCE["repository"],
            "revision": manifest.get("revision"),
            "license": GRETEL_FINANCE["license"],
            "attribution": GRETEL_FINANCE["attribution"],
            "language": args.language,
            "files": {path.name: manifest["files"][path.name] for path in files},
            "file_digest_manifest_sha256": integrity["file_digest_manifest_sha256"],
            "splits": {
                "weights": f"published train minus a {args.validation_fraction:.0%} text-hash holdout",
                "epoch_selection_and_calibration": "text-hash holdout of the published train split",
                "test": "published test split, never read during training",
            },
            "changes": "PII labels mapped to DeidFlow categories; no source text edits",
            "provenance_kind": GRETEL_FINANCE["provenance_kind"],
        }
    else:
        if args.train_jsonl is None or args.validation_jsonl is None:
            parser.error("--train-jsonl and --validation-jsonl are required for jsonl")
        train = load_span_jsonl(args.train_jsonl, split="train").examples
        validation = load_span_jsonl(args.validation_jsonl, split="validation").examples
        provenance = {
            "source": "local span JSONL",
            "train_sha256": hashlib.sha256(args.train_jsonl.read_bytes()).hexdigest(),
            "validation_sha256": hashlib.sha256(args.validation_jsonl.read_bytes()).hexdigest(),
            "splits": {"weights": "train", "epoch_selection_and_calibration": "validation"},
        }
    model, report = train_span_tagger(
        train,
        validation,
        epochs=args.epochs,
        patience=args.patience,
        seed=args.seed,
        min_feature_docs=args.min_feature_docs,
        prune_below=args.prune_below,
        metadata={
            "version": args.version,
            "language": "es",
            # Only the financial model records a domain, so the packaged clinical
            # model (trained before this field existed) rebuilds byte for byte.
            **({"domain": "financial"} if args.source == "gretel_finance" else {}),
            "training_data": provenance,
        },
        log=lambda line: print(line, file=sys.stderr, flush=True),
    )
    payload = json.dumps(model, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    if args.output.suffix == ".gz":
        payload = gzip.compress(payload, compresslevel=9, mtime=0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    report["model_file_bytes"] = len(payload)
    report["model_sha256"] = hashlib.sha256(payload).hexdigest()
    report["training_data"] = provenance
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "selected_epoch",
                    "selected_validation_exact_f1",
                    "stored_features",
                    "model_file_bytes",
                    "model_sha256",
                    "seconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
