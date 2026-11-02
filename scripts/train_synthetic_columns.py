"""Executable local training demonstration on explicitly synthetic columns."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from deidflow.benchmarks.datasets import clabe_check_digit
from deidflow.training import (
    ColumnSample,
    LocalColumnModel,
    classification_metrics,
    promotion_gate,
    train_column_model,
)


def examples() -> list[ColumnSample]:
    samples = []
    for split_index, split in enumerate(("train", "validation", "test"), start=1):
        rng = random.Random(1729 + split_index)
        for index in range(24 if split == "train" else 12):
            code = split_index * 10000 + index * 100
            columns = {
                "EMAIL": tuple(f"persona.{split}.{code + i}@example.org" for i in range(8)),
                "CLABE": tuple(
                    (lambda prefix: prefix + clabe_check_digit(prefix))(f"002180{code + i:011d}")
                    for i in range(8)
                ),
                "CUSTOMER_ID": tuple(
                    f"CLI-{split_index}{rng.randrange(100000, 999999)}" for _ in range(8)
                ),
                "NON_SENSITIVE": tuple(str(rng.randrange(5, 95)) for _ in range(8)),
            }
            for label, values in columns.items():
                # Opaque headers force value-based generalization.  Template and
                # entity groups are partition-specific and checked by training.
                samples.append(
                    ColumnSample(
                        f"campo_{split}_{index}",
                        values,
                        label,
                        split,
                        f"{split}-{label}",
                        f"{split}-{index}-{label}",
                    )
                )
    return samples


def baseline(sample: ColumnSample) -> str:
    import re

    if all("@" in value for value in sample.values):
        return "EMAIL"
    if all(len(value) == 18 and value.isdigit() for value in sample.values):
        return "CLABE"
    if all(re.fullmatch(r"CLI-\d+", value) for value in sample.values):
        return "CUSTOMER_ID"
    return "NON_SENSITIVE"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/training-model")
    args = parser.parse_args()
    samples = examples()
    manifest = train_column_model(samples, args.output, version="synthetic-0.1", seed=1729)
    model = LocalColumnModel(args.output)
    test = [sample for sample in samples if sample.split == "test"]
    test_metrics = model.evaluate(test)
    baseline_metrics = classification_metrics(
        [sample.label for sample in test], [baseline(sample) for sample in test]
    )
    gate = promotion_gate(
        test_metrics, baseline_metrics, critical_categories=["EMAIL", "CLABE", "CUSTOMER_ID"]
    )
    report = {
        "training": manifest,
        "test": test_metrics,
        "baseline_test": baseline_metrics,
        "promotion_gate": gate,
        "scope": "Synthetic four-label columns only; no pretrained assets, no production calibration or auto activation",
    }
    Path(args.output, "evaluation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
