"""Fit rules-only score mapping on validation templates; measure ECE on test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from deidflow.benchmarks import evaluate, synthetic_corpus
from deidflow.detectors import RuleDetector
from deidflow.training import fit_score_calibrator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/calibration")
    parser.add_argument("--count", type=int, default=150)
    args = parser.parse_args()
    validation = synthetic_corpus("validation", count=args.count)
    test = synthetic_corpus("test", count=args.count)
    detector = RuleDetector()
    calibration_findings = []
    correct = []
    for example in validation:
        gold = {(span.entity_type, span.start, span.end) for span in example.spans}
        for finding in detector.detect(example.text):
            calibration_findings.append(finding)
            correct.append((finding.entity_type, finding.start, finding.end) in gold)
    calibrator = fit_score_calibrator(calibration_findings, correct)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    calibrator.save(output / "rules-calibration.json")
    test_predictions = [detector.detect(example.text) for example in test]
    calibrated = [
        [calibrator.apply(finding) for finding in findings] for findings in test_predictions
    ]
    report = {
        "fit_split": "validation",
        "evaluation_split": "test",
        "seed": 1729,
        "fit_candidates": len(correct),
        "fit_positive_candidates": sum(correct),
        "unmodified": evaluate(test, test_predictions).to_dict(),
        "calibrated": evaluate(test, calibrated).to_dict(),
        "limitations": [
            "Synthetic challenge-only score mapping; not a production probability guarantee",
            "Only rules.es_MX/model provenance calibrated",
            "Calibration annotates scores without discarding any candidate",
            "Uncalibrated raw scores have no reported ECE",
        ],
    }
    (output / "evaluation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "fit_candidates": len(correct),
                "test_calibrated_ece": report["calibrated"]["expected_calibration_error"],
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
