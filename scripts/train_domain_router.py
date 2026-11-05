"""Build the packaged clinical/financial domain router from TRAINING splits only.

Validation (MEDDOCAN dev, the Gretel train holdout) reports routing accuracy and
the evidence margins; test splits are not read.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import statistics
from pathlib import Path

from deidflow.benchmarks.public_corpus import load_public, verify_acquired_corpus
from deidflow.benchmarks.span_corpus import (
    gretel_files,
    hash_split,
    load_gretel_finance,
    verify_registered_files,
)
from deidflow.nlp.router import DomainRouter, train_router


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--meddocan", type=Path, required=True)
    parser.add_argument("--gretel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    verify_acquired_corpus(args.meddocan, "meddocan")
    verify_registered_files(args.gretel, "gretel_finance")
    clinical_train = [e.text for e in load_public(args.meddocan, "meddocan", "train").examples]
    clinical_validation = [e.text for e in load_public(args.meddocan, "meddocan", "dev").examples]
    published = load_gretel_finance(gretel_files(args.gretel, "train"), split="train").examples
    financial_train_examples, financial_validation_examples = hash_split(published)
    financial_train = [e.text for e in financial_train_examples]
    financial_validation = [e.text for e in financial_validation_examples]
    model = train_router({"clinical": clinical_train, "financial": financial_train})
    model["metadata"]["training_data"] = {
        "clinical": "MEDDOCAN official train split (CC-BY-4.0)",
        "financial": "Gretel synthetic_pii_finance_multilingual Spanish train file minus its "
        "10% text-hash holdout (Apache-2.0)",
    }
    payload = gzip.compress(
        json.dumps(model, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(),
        compresslevel=9,
        mtime=0,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    router = DomainRouter(model, {"clinical": None, "financial": None}, min_evidence=0.0)
    validation = {}
    for domain, texts in (("clinical", clinical_validation), ("financial", financial_validation)):
        margins = []
        correct = 0
        for text in texts:
            scores = router.scores(text)
            other = next(d for d in scores if d != domain)
            margins.append(scores[domain] - scores[other])
            correct += int(router.route(text) == domain)
        validation[domain] = {
            "documents": len(texts),
            "accuracy_without_mixed_fallback": correct / len(texts),
            "evidence_margin_min": min(margins),
            "evidence_margin_p01": statistics.quantiles(margins, n=100)[0],
            "evidence_margin_median": statistics.median(margins),
        }
    report = {
        "model_sha256": hashlib.sha256(payload).hexdigest(),
        "model_bytes": len(payload),
        "features": len(model["weights"]),
        "training_documents": model["metadata"]["documents"],
        "validation": validation,
        "test_split_used": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
