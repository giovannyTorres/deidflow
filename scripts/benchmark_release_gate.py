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
import statistics
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from deidflow import DeidEngine, Policy
from deidflow.benchmarks.datasets import Example
from deidflow.benchmarks.public_corpus import load_public, verify_acquired_corpus
from deidflow.benchmarks.runner import machine_metadata, offline_network
from deidflow.nlp.tagger import SpanTagger


def evaluate(engine: DeidEngine, examples: Sequence[Example], policy: Policy) -> dict[str, Any]:
    statuses: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    leaked_documents: Counter[str] = Counter()
    leaked_characters: Counter[str] = Counter()
    sensitive_characters = 0
    latency = []
    for example in examples:
        start = time.perf_counter()
        result = engine.deidentify_text(example.text, policy=policy)
        latency.append(time.perf_counter() - start)
        status = str(result.status)
        statuses[status] += 1
        issues.update(result.issues)
        covered = bytearray(len(example.text))
        for mapping in result.mappings:
            covered[mapping.source_start : mapping.source_end] = b"\x01" * (
                mapping.source_end - mapping.source_start
            )
        sensitive = bytearray(len(example.text))
        for span in example.spans:
            sensitive[span.start : span.end] = b"\x01" * (span.end - span.start)
        total = sum(sensitive)
        missed = sum(bool(s) and not c for s, c in zip(sensitive, covered, strict=True))
        sensitive_characters += total
        leaked_characters[status] += missed
        leaked_documents[status] += int(missed > 0)
    documents = len(examples)
    approved = statuses.get("APPROVED", 0)
    return {
        "documents": documents,
        "status_counts": dict(statuses),
        "issue_counts": dict(issues),
        "approved_rate": approved / documents,
        "review_or_blocked_rate": 1 - approved / documents,
        "approved_documents_with_leaked_gold_characters": leaked_documents.get("APPROVED", 0),
        "approved_leak_rate": leaked_documents.get("APPROVED", 0) / approved if approved else None,
        "documents_with_leaked_gold_characters_by_status": dict(leaked_documents),
        "leaked_gold_characters_by_status": dict(leaked_characters),
        "output_sensitive_character_recall": 1
        - sum(leaked_characters.values()) / sensitive_characters,
        "p50_seconds": statistics.median(latency),
        "definition": "A gold character leaks when no applied transformation covers its source offset",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--tagger", default="builtin:es-clinical")
    parser.add_argument("--review-margin", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    integrity = verify_acquired_corpus(args.corpus, "meddocan")
    examples = load_public(args.corpus, "meddocan", args.split).examples
    if args.tagger.startswith("builtin:"):
        tagger = SpanTagger.builtin(args.tagger[8:], review_margin=args.review_margin)
    else:
        tagger = SpanTagger.load(args.tagger, review_margin=args.review_margin)
    report: dict[str, Any] = {
        "schema_version": 1,
        "machine": machine_metadata(),
        "corpus": "meddocan",
        "split": args.split,
        "integrity": integrity,
        "tagger": {"version": tagger.model_version, "review_margin": args.review_margin},
        "policy": "Policy.strict() defaults: placeholder for every category, review_below=0.75",
        "pipelines": {},
    }
    with offline_network() as guard:
        for name, engine, policy in (
            ("rules_only_explicit", DeidEngine(), Policy.strict(require_ner=False)),
            ("rules_plus_tagger", DeidEngine(nlp=tagger), Policy.strict()),
        ):
            report["pipelines"][name] = evaluate(engine, examples, policy)
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
