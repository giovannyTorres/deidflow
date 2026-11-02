"""Paired CSV fast-path and text multiprocessing experiments with gold checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from functools import partial
from pathlib import Path
from typing import Any

from benchmark_workloads import benchmark_csv

from deidflow import DeidEngine
from deidflow.benchmarks import synthetic_corpus
from deidflow.benchmarks.runner import machine_metadata, measure


def run_text(records: int, workers: int, batch_size: int) -> dict[str, Any]:
    corpus = synthetic_corpus("test", count=100)
    texts = (corpus[index % len(corpus)].text for index in range(records))
    engine = DeidEngine()
    digest = hashlib.sha256()
    count = findings_count = 0
    for findings in engine.scan_many(
        texts, input_kind="text", workers=workers, batch_size=batch_size
    ):
        count += 1
        findings_count += len(findings)
        digest.update(
            (
                json.dumps(
                    [(finding.entity_type, finding.start, finding.end) for finding in findings],
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        )
    return {"records": count, "findings": findings_count, "prediction_sha256": digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/experiments.json")
    parser.add_argument("--work", default="../../work/deidflow-experiments")
    parser.add_argument("--csv-rows", type=int, default=10000)
    parser.add_argument("--text-records", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--batch-sizes", nargs="+", type=int, default=[128, 1024])
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--skip-csv", action="store_true")
    args = parser.parse_args()
    if min([args.csv_rows, args.text_records, args.repeats] + args.batch_sizes + args.workers) < 1:
        parser.error("Experiment sizes must be positive")
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    csv_runs = []
    if not args.skip_csv:
        for batch in args.batch_sizes:
            for enabled in (False, True):
                csv_runs.append(
                    benchmark_csv(
                        work,
                        rows=args.csv_rows,
                        batch_size=batch,
                        repeats=args.repeats,
                        schema_fast_path=enabled,
                    )
                )
                print(
                    json.dumps(
                        {
                            "workload": "csv",
                            "batch_size": batch,
                            "schema_fast_path": enabled,
                            "status": csv_runs[-1]["status"],
                        }
                    ),
                    flush=True,
                )
    text_runs = []
    for workers in args.workers:
        for batch in args.batch_sizes:
            repetitions = []
            for _ in range(args.repeats):
                measurement, output = measure(
                    partial(run_text, args.text_records, workers, batch), units=args.text_records
                )
                repetitions.append({**measurement, **output})
            text_runs.append({"workers": workers, "batch_size": batch, "runs": repetitions})
    reference_digest = text_runs[0]["runs"][0]["prediction_sha256"]
    consistent = all(
        run["prediction_sha256"] == reference_digest and run["records"] == args.text_records
        for experiment in text_runs
        for run in experiment["runs"]
    )
    report = {
        "machine": machine_metadata(),
        "repeats": args.repeats,
        "csv_fast_path": csv_runs,
        "text_worker_scaling": text_runs,
        "parallel_outputs_identical": consistent,
        "scope": "CSV paired conditions classify and handle every same sensitive column, then re-read and independently verify all gold cells. schema_fast_path=False additionally scans all input cells; true replaces known sensitive fields wholesale. Text timers include multiprocessing startup and hashing of findings; process-tree RSS includes spawned interpreters. Results are machine-specific, not universal speedups.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"results": str(output), "parallel_outputs_identical": consistent}))
    if not consistent or not all(run["status"] == "measured" for run in csv_runs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
