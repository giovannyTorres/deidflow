"""Measure end-to-end release decisions and actual output leakage on a gold corpus.

For each document this runs ``DeidEngine.deidentify_text`` and records the release
status. A gold character leaks when no applied transformation covers it, so the
report can answer the operational question: of the documents a pipeline would
approve without review, how many still contain sensitive characters?

Only aggregate counts are written; no text, identifiers or offsets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from deidflow import DeidEngine, Policy
from deidflow.benchmarks.public_corpus import load_public, verify_acquired_corpus
from deidflow.benchmarks.release_gate import release_gate_metrics
from deidflow.benchmarks.runner import machine_metadata, offline_network
from deidflow.benchmarks.span_corpus import (
    gretel_files,
    load_gretel_finance,
    verify_registered_files,
)
from deidflow.nlp import CombinedNER
from deidflow.nlp.tagger import SpanTagger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=["meddocan", "gretel_finance"], default="meddocan")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument(
        "--tagger",
        action="append",
        default=[],
        help="Model path or builtin:<name>; repeat to combine (default builtin:es-clinical)",
    )
    parser.add_argument("--review-margin", type=float)
    parser.add_argument("--redact-margin", type=float)
    parser.add_argument("--profile", help="Packaged operating profile for built-in taggers")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.source == "meddocan":
        integrity = verify_acquired_corpus(args.corpus, "meddocan")
        examples = load_public(args.corpus, "meddocan", args.split).examples
    else:
        if args.split != "test":
            parser.error("gretel_finance publishes train and test only; use --split test")
        integrity = verify_registered_files(args.corpus, "gretel_finance")
        examples = load_gretel_finance(gretel_files(args.corpus, "test"), split="test").examples
    taggers = []
    for item in args.tagger or ["builtin:es-clinical"]:
        if item == "builtin:auto":
            from deidflow.nlp.router import DomainRouter

            taggers.append(DomainRouter.builtin(profile=args.profile))
            continue
        if item.startswith("builtin:"):
            taggers.append(
                SpanTagger.builtin(
                    item[8:],
                    profile=args.profile,
                    review_margin=args.review_margin,
                    redact_margin=args.redact_margin,
                )
            )
        else:
            taggers.append(
                SpanTagger.load(
                    item, review_margin=args.review_margin, redact_margin=args.redact_margin
                )
            )
    nlp = taggers[0] if len(taggers) == 1 else CombinedNER(*taggers)
    report: dict[str, Any] = {
        "schema_version": 1,
        "machine": machine_metadata(),
        "corpus": args.source,
        "split": args.split,
        "integrity": integrity,
        "tagger": {
            "versions": [getattr(t, "model_version", "domain-router") for t in taggers],
            "profile": args.profile,
            "review_margins": [getattr(t, "review_margin", None) for t in taggers],
            "redact_margins": [getattr(t, "redact_margin", None) for t in taggers],
        },
        "policy": "Policy.strict() defaults: placeholder for every category, review_below=0.75",
        "pipelines": {},
    }
    with offline_network() as guard:
        for name, engine, policy in (
            ("rules_only_explicit", DeidEngine(), Policy.strict(require_ner=False)),
            ("rules_plus_tagger", DeidEngine(nlp=nlp), Policy.strict()),
        ):
            report["pipelines"][name] = release_gate_metrics(engine, examples, policy)
        report["network_guard"] = {"attempts": guard["attempts"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                name: {
                    key: value[key]
                    for key in (
                        "status_counts",
                        "approved_leak_rate",
                        "output_sensitive_character_recall",
                    )
                }
                for name, value in report["pipelines"].items()
            }
        )
    )


if __name__ == "__main__":
    main()
