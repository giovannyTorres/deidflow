"""Leakage-oriented per-type breakdown on MEDDOCAN (audit 2026-11).

Reports only aggregate numbers: no corpus text, filenames or entity values.
The corpus directory uses the acquisition layout ``<root>/{train,dev,test}/*.txt|.ann``.
When the codeload archive is unavailable, ``--manifest`` verifies the per-file
digest manifest hash recorded by ``acquire()`` instead of the archive bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from deidflow import DeidEngine
from deidflow.benchmarks.public_corpus import MEDDOCAN_LABELS, load_public
from deidflow.benchmarks.public_quality import map_predictions, quality_metrics

DIRECT = {
    "PERSON",
    "ADDRESS",
    "PATIENT_ID",
    "EMAIL",
    "REGIONAL_ID",
    "INSURANCE_ID",
    "PHONE",
    "EMPLOYEE_ID",
}


def file_manifest_hash(root: Path) -> str:
    """Recompute ``file_digest_manifest_sha256`` exactly as ``acquire()`` records it."""
    digests = {}
    base = root.parent
    for path in sorted(root.rglob("*")):
        if path.is_file() and (
            path.suffix in {".txt", ".ann"}
            or path.name in {"README.md", "LICENSE", "LICENSE.txt", "guidelines.md"}
        ):
            digests[path.relative_to(base).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()


def breakdown(corpus: Any, predictions: list[list[Any]]) -> dict[str, Any]:
    gold_n: Counter[str] = Counter()
    full: Counter[str] = Counter()
    chars: Counter[str] = Counter()
    chars_hit: Counter[str] = Counter()
    pred_n: Counter[str] = Counter()
    pred_typed: Counter[str] = Counter()
    docs_direct_leak = 0
    for example, predicted in zip(corpus.examples, predictions, strict=True):
        covered = bytearray(len(example.text))
        for finding in predicted:
            covered[finding.start : finding.end] = b"\x01" * (finding.end - finding.start)
        leak = False
        for gold in example.spans:
            gold_n[gold.entity_type] += 1
            chars[gold.entity_type] += gold.end - gold.start
            chars_hit[gold.entity_type] += sum(covered[gold.start : gold.end])
            complete = all(covered[gold.start : gold.end])
            full[gold.entity_type] += int(complete)
            leak |= gold.entity_type in DIRECT and not complete
        docs_direct_leak += int(leak)
        for kind, start, end in {(f.entity_type, f.start, f.end) for f in predicted}:
            pred_n[kind] += 1
            pred_typed[kind] += int(
                any(
                    g.entity_type == kind and g.start < end and g.end > start for g in example.spans
                )
            )
    direct_total = sum(gold_n[k] for k in DIRECT)
    return {
        "fully_covered_mention_rate": sum(full.values()) / sum(gold_n.values()),
        "direct_fully_covered_mention_rate": sum(full[k] for k in DIRECT) / direct_total
        if direct_total
        else None,
        "documents_with_direct_identifier_leak": docs_direct_leak,
        "documents": len(corpus.examples),
        "by_type": {
            kind: {
                "gold_mentions": gold_n[kind],
                "fully_covered_rate": full[kind] / gold_n[kind] if gold_n[kind] else None,
                "character_coverage": chars_hit[kind] / chars[kind] if chars[kind] else None,
                "predictions": pred_n[kind],
                "typed_overlap_precision": pred_typed[kind] / pred_n[kind]
                if pred_n[kind]
                else None,
            }
            for kind in sorted(set(gold_n) | set(pred_n), key=lambda k: -gold_n[k])
        },
        "definition": "fully covered = every gold character covered by any prediction, any category; detection coverage only, not transformed-output verification",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", choices=["dev", "test"], default="test")
    parser.add_argument("--manifest", type=Path, help="public-sources JSON with digest hash")
    parser.add_argument("--spacy-model", type=Path, help="local spaCy model directory")
    parser.add_argument(
        "--meddocan-labels",
        action="store_true",
        help="the local model predicts original MEDDOCAN labels; map them to DeidFlow types",
    )
    parser.add_argument("--model-only", action="store_true")
    parser.add_argument("--ci-repeats", type=int, default=200)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    integrity = None
    if args.manifest:
        expected = json.loads(args.manifest.read_text(encoding="utf-8"))
        actual = file_manifest_hash(args.corpus)
        if actual != expected["file_digest_manifest_sha256"]:
            raise SystemExit("Corpus differs from the pinned per-file digest manifest")
        integrity = {"file_digest_manifest_sha256": actual, "verified": True}
    corpus = load_public(args.corpus, "meddocan", args.split)
    detect = DeidEngine().scan_text
    name = "deidflow_rules"
    if args.spacy_model:
        from deidflow.nlp import SpacyNER

        ner = SpacyNER(
            args.spacy_model, labels=dict(MEDDOCAN_LABELS) if args.meddocan_labels else None
        )
        detect = ner.detect if args.model_only else DeidEngine(nlp=ner).scan_text
        name = ("model_only_" if args.model_only else "rules_plus_") + args.spacy_model.name
    detect(corpus.examples[0].text)
    started = time.perf_counter()
    predictions = [map_predictions("meddocan", detect(e.text)) for e in corpus.examples]
    seconds = time.perf_counter() - started
    metrics = quality_metrics(corpus, predictions, ci_repeats=args.ci_repeats)
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
        "leakage_breakdown": breakdown(corpus, predictions),
    }
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
