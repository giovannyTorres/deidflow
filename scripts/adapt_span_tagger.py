#!/usr/bin/env python3
"""Stage, independently evaluate or demonstrate offline span-model adaptation."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from deidflow.benchmarks.datasets import Example, GoldSpan
from deidflow.training.adaptation import (
    AdaptationConfig,
    PromotionCriteria,
    evaluate_adaptation,
    load_adaptation_jsonl,
    stage_span_adaptation,
)
from deidflow.training.tagger import train_span_tagger


def _fictional(role: str, count: int, *, domain: bool, seed: int) -> list[Example]:
    """Made-up subjects and separate template families, never real patient data."""
    rng = random.Random(seed)
    patterns = {
        "old_train": "Persona: {name}. La movilidad se mantiene estable.",
        "old_validation": "Persona: {name}. El seguimiento continúa sin novedades.",
        "train": "Paciente: {name}. Expediente: {code}. El tratamiento es fisioterapia.",
        "validation": "Paciente: {name}. Expediente: {code}. La rehabilitación continúa.",
        "test": "Paciente: {name}. Expediente: {code}. La movilidad ha mejorado.",
        "regression": "Persona: {name}. La exploración presenta evolución favorable.",
    }
    result = []
    for index in range(count):
        words = [
            "".join(rng.choice("bcdfglmnrstv") + rng.choice("aeiou") for _ in range(3))
            for _ in range(2)
        ]
        name = " ".join(word.title() for word in words)
        code = f"HC{seed:03d}{index:04d}"
        spans = []
        if index % 4 == 0:
            text = f"Se mantiene la actividad cotidiana sin limitaciones; nota ficticia {words[0]}."
        else:
            text = patterns[role].format(name=name, code=code)
            start = text.index(name)
            spans.append(GoldSpan("PERSON", start, start + len(name)))
            if domain:
                start = text.index(code)
                spans.append(GoldSpan("PATIENT_ID", start, start + len(code)))
        split = (
            "train" if role == "old_train" else "validation" if role == "old_validation" else role
        )
        # Each role has a distinct template family; all examples within it stay together.
        result.append(
            Example(
                f"fiction-{role}-{index}", text, tuple(spans), split, f"fiction-template-{role}"
            )
        )
    return result


def run_demo(output: Path) -> dict[str, Any]:
    """Reproducible mechanics demonstration; synthetic evidence never promotes."""
    output.mkdir(parents=True, exist_ok=False)
    old_train = _fictional("old_train", 48, domain=False, seed=11)
    old_validation = _fictional("old_validation", 24, domain=False, seed=12)
    baseline, _ = train_span_tagger(old_train, old_validation, epochs=8, patience=3, seed=53)
    splits = {
        "train": _fictional("train", 64, domain=True, seed=21),
        "validation": _fictional("validation", 32, domain=True, seed=22),
        "test": _fictional("test", 40, domain=True, seed=23),
        "regression": _fictional("regression", 40, domain=False, seed=24),
        "replay": old_train,
    }
    for role, examples in splits.items():
        with (output / f"{role}.jsonl").open("w", encoding="utf-8") as stream:
            for example in examples:
                stream.write(
                    json.dumps(
                        {
                            "id": example.id,
                            "text": example.text,
                            "split": example.split,
                            "group_id": example.template_id,
                            "spans": [asdict(span) for span in example.spans],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
    stage_span_adaptation(
        baseline,
        splits["train"],
        splits["validation"],
        output / "staged",
        replay=old_train,
        config=AdaptationConfig(epochs=8, patience=3, seed=53),
        criteria=PromotionCriteria(
            minimum_documents=30, minimum_type_support=20, minimum_negative_documents=10
        ),
    )
    digest = (output / "staged" / "manifest.sha256").read_text("ascii").strip()
    return evaluate_adaptation(
        output / "staged",
        splits["test"],
        splits["regression"],
        output / "evaluation",
        expected_manifest_sha256=digest,
        evidence_kind="fictional_demo",
        baseline_exposure_verified=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="Warm-start a frozen, inactive candidate")
    stage.add_argument("--baseline", required=True, help="JSON/gzip path or builtin:es-clinical")
    stage.add_argument("--train", type=Path, required=True)
    stage.add_argument("--validation", type=Path, required=True)
    stage.add_argument("--replay", type=Path)
    stage.add_argument(
        "--criteria", type=Path, help="JSON PromotionCriteria object; frozen before fit"
    )
    stage.add_argument("--output", type=Path, required=True)
    for flag, default in (("epochs", 12), ("patience", 3), ("seed", 1729), ("min-feature-docs", 2)):
        stage.add_argument("--" + flag, type=int, default=default)
    evaluate = commands.add_parser("evaluate", help="Measure frozen models; never fit or activate")
    evaluate.add_argument("--staged", type=Path, required=True)
    evaluate.add_argument(
        "--manifest-sha256", required=True, help="Digest recorded at staging time"
    )
    evaluate.add_argument("--test", type=Path, required=True)
    evaluate.add_argument("--regression", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument(
        "--evidence-kind",
        choices=("unknown", "fictional_demo", "independently_annotated"),
        default="unknown",
    )
    evaluate.add_argument(
        "--baseline-exposure-verified",
        action="store_true",
        help="Attest baseline training/selection sources do not contain either holdout",
    )
    demo = commands.add_parser("demo", help="Safe fictional reproducibility demonstration")
    demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "stage":
            criteria = (
                PromotionCriteria(**json.loads(args.criteria.read_text("utf-8")))
                if args.criteria
                else PromotionCriteria()
            )
            manifest = stage_span_adaptation(
                args.baseline,
                load_adaptation_jsonl(args.train, split="train"),
                load_adaptation_jsonl(args.validation, split="validation"),
                args.output,
                replay=load_adaptation_jsonl(args.replay, split="train") if args.replay else (),
                config=AdaptationConfig(
                    epochs=args.epochs,
                    patience=args.patience,
                    seed=args.seed,
                    min_feature_docs=args.min_feature_docs,
                ),
                criteria=criteria,
            )
            print(
                json.dumps(
                    {
                        "state": manifest["state"],
                        "activated": False,
                        "manifest_sha256": (args.output / "manifest.sha256")
                        .read_text("ascii")
                        .strip(),
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "demo":
            report = run_demo(args.output)
        else:
            report = evaluate_adaptation(
                args.staged,
                load_adaptation_jsonl(args.test, split="test"),
                load_adaptation_jsonl(args.regression, split="regression"),
                args.output,
                expected_manifest_sha256=args.manifest_sha256,
                evidence_kind=args.evidence_kind,
                baseline_exposure_verified=args.baseline_exposure_verified,
            )
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        parser.exit(2, f"Adaptation failed: {error}\n")
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "activated": False,
                "reasons": report["reasons"],
                "measurements": report["measurements"],
            },
            indent=2,
        )
    )
    # The fictional demo is successful when it runs; a blocked real gate is nonzero.
    return 0 if args.command == "demo" or report["decision"] == "ELIGIBLE_FOR_MANUAL_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
