"""CI guard for gross rules-performance/critical-recall regressions.

Budgets intentionally tolerate noisy shared runners. They are safety rails, not
cross-machine speed targets or proof of a benchmark improvement.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from deidflow import DeidEngine
from deidflow.benchmarks import evaluate, synthetic_corpus
from deidflow.benchmarks.runner import machine_metadata
from deidflow.detectors import RuleDetector


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", default="benchmarks/results/micro.json")
    parser.add_argument("--records", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.records < 10 or args.repeats < 3:
        parser.error("Use at least ten records and three repeats")
    corpus = synthetic_corpus("test", count=50)
    texts = [corpus[index % len(corpus)].text for index in range(args.records)]
    engine = DeidEngine()
    reference = RuleDetector()
    engine.scan_text(texts[0])
    reference.detect(texts[0])
    engine_times = []
    reference_times = []
    for repeat in range(args.repeats):
        # Alternate order to reduce systematic warm-cache/order bias.
        cases: list[tuple[str, Any]] = [
            ("engine", engine.scan_text),
            ("reference", reference.detect),
        ]
        if repeat % 2:
            cases.reverse()
        for name, detect in cases:
            started = time.perf_counter()
            for text in texts:
                detect(text)
            (engine_times if name == "engine" else reference_times).append(
                time.perf_counter() - started
            )
    engine_median = statistics.median(engine_times)
    reference_median = statistics.median(reference_times)
    metrics = evaluate(corpus, [engine.scan_text(example.text) for example in corpus])
    critical_recall = {
        label: metrics.recall_by_type.get(label, 0.0)
        for label in ("EMAIL", "CURP", "RFC", "CLABE", "API_KEY")
    }
    per_record = engine_median / args.records
    relative = engine_median / reference_median
    budgets = {
        "max_seconds_per_record": 0.005,
        "max_engine_to_same_run_rules_ratio": 5.0,
        "minimum_critical_exact_recall": 1.0,
    }
    passed = (
        per_record <= budgets["max_seconds_per_record"]
        and relative <= budgets["max_engine_to_same_run_rules_ratio"]
        and all(
            value >= budgets["minimum_critical_exact_recall"] for value in critical_recall.values()
        )
    )
    report = {
        "machine": machine_metadata(),
        "records": args.records,
        "repeats": args.repeats,
        "engine_seconds": engine_times,
        "same_run_reference_seconds": reference_times,
        "median_seconds_per_record": per_record,
        "engine_to_same_run_reference_ratio": relative,
        "critical_exact_recall": critical_recall,
        "budgets": budgets,
        "passed": passed,
        "scope": "Gross CI regression guard; identical contextual rules, engine wrapper versus direct detector, alternating timing order; no fine-grained cross-machine or statistical speedup claim",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": passed,
                "median_seconds_per_record": per_record,
                "relative_ratio": relative,
                "critical_exact_recall": critical_recall,
            },
            indent=2,
        )
    )
    if args.check and not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
