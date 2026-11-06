"""Leakage-oriented MEDDOCAN evaluation with optional CI thresholds (audit F0).

Reports only aggregate numbers: no corpus text, filenames or entity values. The
corpus must be verified against the pinned archive or per-file digest manifest
(see ``acquire_public_corpus.py --git``). Thresholds turn the run into a
ratchet: the process exits with status 1 when a leakage metric regresses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from deidflow import DeidEngine
from deidflow.benchmarks.public_corpus import (
    MEDDOCAN_LABELS,
    MEDDOCAN_ROLES,
    load_meddocan_roles,
    load_public,
    verify_acquired_corpus,
)
from deidflow.benchmarks.public_quality import map_predictions, quality_metrics, role_metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", choices=["dev", "test"], default="test")
    parser.add_argument("--spacy-model", type=Path, help="local spaCy model directory")
    parser.add_argument(
        "--meddocan-labels",
        action="store_true",
        help="the local model predicts original MEDDOCAN labels; map them to DeidFlow types",
    )
    parser.add_argument("--model-only", action="store_true")
    parser.add_argument("--ci-repeats", type=int, default=200)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-direct-coverage", type=float)
    parser.add_argument("--min-fully-covered", type=float)
    parser.add_argument("--max-direct-leak-documents", type=int)
    args = parser.parse_args()
    if args.model_only and not args.spacy_model:
        parser.error("--model-only requires --spacy-model")
    if args.meddocan_labels and not args.spacy_model:
        parser.error("--meddocan-labels requires --spacy-model")
    if args.ci_repeats < 1:
        parser.error("--ci-repeats must be positive")
    for threshold in (args.min_direct_coverage, args.min_fully_covered):
        if threshold is not None and not 0 <= threshold <= 1:
            parser.error("coverage thresholds must be between zero and one")
    if args.max_direct_leak_documents is not None and args.max_direct_leak_documents < 0:
        parser.error("--max-direct-leak-documents must be nonnegative")
    integrity = verify_acquired_corpus(args.corpus, "meddocan")
    corpus = load_public(args.corpus, "meddocan", args.split)
    detect = DeidEngine().scan_text
    name = "deidflow_rules"
    if args.spacy_model:
        from deidflow.nlp import SpacyNER

        ner = SpacyNER(
            args.spacy_model,
            labels=dict(MEDDOCAN_LABELS) if args.meddocan_labels else None,
            roles=dict(MEDDOCAN_ROLES) if args.meddocan_labels else None,
        )
        detect = ner.detect if args.model_only else DeidEngine(nlp=ner).scan_text
        name = ("model_only_" if args.model_only else "rules_plus_") + args.spacy_model.name
    detect(corpus.examples[0].text)
    started = time.perf_counter()
    raw = [detect(e.text) for e in corpus.examples]
    seconds = time.perf_counter() - started
    predictions = [map_predictions("meddocan", p) for p in raw]
    metrics = quality_metrics(corpus, predictions, ci_repeats=args.ci_repeats)
    breakdown = metrics["leakage_breakdown"]
    result = {
        "pipeline": name,
        "split": args.split,
        "integrity": integrity,
        "seconds_single_pass": seconds,
        "exact": {k: metrics["exact"][k] for k in ("precision", "recall", "f1")},
        "overlap": {k: metrics["overlap"][k] for k in ("precision", "recall", "f1")},
        "exact_f1_ci95": metrics["confidence_intervals"].get("intervals", {}).get("f1"),
        "false_redaction_rate": metrics["exact"]["false_redaction_rate"],
        "coverage_leakage": metrics["coverage_leakage"],
        "leakage_breakdown": breakdown,
        "person_roles": role_metrics(load_meddocan_roles(args.corpus, args.split), raw),
    }
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    failures = []
    if args.min_direct_coverage is not None and (
        breakdown["direct_fully_covered_mention_rate"] is None
        or breakdown["direct_fully_covered_mention_rate"] < args.min_direct_coverage
    ):
        failures.append("direct identifier coverage regressed")
    if args.min_fully_covered is not None and (
        breakdown["fully_covered_mention_rate"] is None
        or breakdown["fully_covered_mention_rate"] < args.min_fully_covered
    ):
        failures.append("fully covered mention rate regressed")
    if (
        args.max_direct_leak_documents is not None
        and breakdown["documents_with_direct_identifier_leak"] > args.max_direct_leak_documents
    ):
        failures.append("documents with direct-identifier leaks increased")
    if failures:
        print("; ".join(failures), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
