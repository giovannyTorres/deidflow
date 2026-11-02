"""Run from repository root after `pip install -e .[benchmarks]`."""

from __future__ import annotations

import argparse
import json

from deidflow.benchmarks.runner import run_detection_benchmarks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/local")
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument(
        "--spacy-model", help="Existing local Spanish spaCy directory; no downloads"
    )
    args = parser.parse_args()
    result = run_detection_benchmarks(
        args.output,
        count=args.count,
        repeats=args.repeats,
        seed=args.seed,
        spacy_model=args.spacy_model,
    )
    print(
        json.dumps(
            {
                "results": args.output,
                "baselines": [
                    {
                        "name": b["name"],
                        "status": b["status"],
                        "f1": b.get("exact", {}).get("f1"),
                        "recall": b.get("exact", {}).get("recall"),
                        "records_per_second": b.get("median_records_per_second"),
                    }
                    for b in result["baselines"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
