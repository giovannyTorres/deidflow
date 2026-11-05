"""Choose tagger review/redact margins for an approved-leak target on VALIDATION data.

For every margin pair the full pipeline runs (rules + tagger, transformation,
verification rescan, release gate). The selected pair is the one that approves
the most documents while its approved leak rate stays at or below the target;
ties prefer less over-redaction. Test splits are never read here: evaluate the
chosen pair once with ``scripts/benchmark_release_gate.py``.

    python scripts/tune_operating_points.py meddocan --corpus ../work/public-corpora/verified/meddocan \\
        --tagger es-clinical --target 0.02 --output benchmarks/results/tagger/operating-points-es-clinical.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from deidflow import DeidEngine, Policy
from deidflow.benchmarks.public_corpus import load_public, verify_acquired_corpus
from deidflow.benchmarks.release_gate import CachedTagger, release_gate_metrics
from deidflow.benchmarks.runner import machine_metadata, offline_network
from deidflow.benchmarks.span_corpus import (
    gretel_files,
    hash_split,
    load_gretel_finance,
    verify_registered_files,
)
from deidflow.nlp.tagger import BUILTIN_MODELS, SpanTagger

GRID = (5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", choices=["meddocan", "gretel_finance"])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--tagger", choices=sorted(BUILTIN_MODELS), required=True)
    parser.add_argument("--target", type=float, default=0.02)
    parser.add_argument(
        "--metric",
        choices=["approved_leak_rate", "approved_direct_identifier_leak_rate"],
        default="approved_leak_rate",
        help="Leak rate the target applies to (both are always reported)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.target < 1:
        parser.error("--target must be between zero and one")
    if args.source == "meddocan":
        integrity = verify_acquired_corpus(args.corpus, "meddocan")
        examples = load_public(args.corpus, "meddocan", "dev").examples
        split = "official dev"
    else:
        integrity = verify_registered_files(args.corpus, "gretel_finance")
        published = load_gretel_finance(gretel_files(args.corpus, "train"), split="train")
        _, examples = hash_split(published.examples)
        split = "10% text-hash holdout of the published train file (the tagger's validation set)"
    tagger = SpanTagger.builtin(args.tagger)
    adapter = CachedTagger(tagger, (e.text for e in examples), candidate_margin=max(GRID))
    engine = DeidEngine(nlp=adapter)
    pairs: list[tuple[float | None, float | None]] = [(None, None)]
    pairs += [(None, redact) for redact in GRID]
    pairs += [(review, None) for review in GRID]
    pairs += [(review, redact) for review in GRID for redact in GRID if redact > review]
    grid: list[dict[str, Any]] = []
    with offline_network() as guard:
        for review, redact in pairs:
            tagger.review_margin, tagger.redact_margin = review, redact
            metrics = release_gate_metrics(engine, examples, Policy.strict())
            row = {"review_margin": review, "redact_margin": redact, **metrics}
            grid.append(row)
            print(
                f"review={review} redact={redact} "
                f"approved={metrics['status_counts'].get('APPROVED', 0)} "
                f"leak={metrics['approved_leak_rate']} "
                f"direct={metrics['approved_direct_identifier_leak_rate']} "
                f"over={metrics['over_redaction_rate']:.4f}",
                file=sys.stderr,
                flush=True,
            )
    eligible = [
        row for row in grid if row[args.metric] is not None and row[args.metric] <= args.target
    ]
    selected = (
        max(
            eligible,
            key=lambda r: (r["status_counts"].get("APPROVED", 0), -r["over_redaction_rate"]),
        )
        if eligible
        else None
    )
    report = {
        "schema_version": 1,
        "machine": machine_metadata(),
        "source": args.source,
        "split": split,
        "integrity": integrity,
        "tagger": args.tagger,
        "target": {"metric": args.metric, "value": args.target},
        "rule": "Most APPROVED documents with the target metric <= target; ties prefer less "
        "over-redaction. Validation data only.",
        "selected": None
        if selected is None
        else {k: selected[k] for k in ("review_margin", "redact_margin")},
        "selected_metrics": selected,
        "grid": grid,
        "network_guard": {"attempts": guard["attempts"]},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    best = min(
        (r for r in grid if r[args.metric] is not None),
        key=lambda r: (r[args.metric], -r["status_counts"].get("APPROVED", 0)),
        default=None,
    )
    report["lowest_leak_configuration"] = best
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected": report["selected"], "eligible_configurations": len(eligible)}))


if __name__ == "__main__":
    main()
