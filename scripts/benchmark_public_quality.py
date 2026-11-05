"""Evaluate independently annotated PUBLIC corpora; never reads Gmail/private data."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from deidflow import DeidEngine
from deidflow.benchmarks.public_corpus import (
    SOURCES,
    PublicCorpus,
    load_public,
    verify_acquired_corpus,
)
from deidflow.benchmarks.public_quality import (
    evaluate_detector,
    map_predictions,
    quality_metrics,
    snapshot_predictions,
    taxonomy_description,
)
from deidflow.benchmarks.runner import (
    _presidio_baseline,
    _spacy_baseline,
    machine_metadata,
    offline_network,
)
from deidflow.benchmarks.span_corpus import (
    GRETEL_FINANCE,
    gretel_files,
    load_gretel_finance,
    verify_registered_files,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["meddocan", "tab", "gretel_finance"])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--baseline", type=Path, help="Frozen v0.2.0 source tree; omit to skip that comparison"
    )
    parser.add_argument("--split", choices=["dev", "test"], default="test")
    parser.add_argument("--language", default="Spanish", help="gretel_finance language")
    parser.add_argument(
        "--tagger",
        action="append",
        default=[],
        metavar="NAME=MODEL",
        help="Span tagger to evaluate (model path or builtin:<name>); repeat for several. "
        "With several, their combination is also evaluated.",
    )
    parser.add_argument("--spacy-model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--ci-repeats", type=int, default=500)
    parser.add_argument("--rules-only", action="store_true")
    parser.add_argument(
        "--source-group-holdout",
        action="store_true",
        help="MEDDOCAN test articles absent from official train/dev; metadata-only selection",
    )
    args = parser.parse_args()
    if args.source == "gretel_finance":
        integrity = verify_registered_files(args.corpus, args.source)
        if args.split != "test":
            parser.error("gretel_finance publishes train and test only; evaluate --split test")
        corpus = load_gretel_finance(
            gretel_files(args.corpus, "test"), language=args.language, split="test"
        )
        source_description = GRETEL_FINANCE
    else:
        integrity = verify_acquired_corpus(args.corpus, args.source)
        corpus = load_public(args.corpus, args.source, args.split)
        source_description = SOURCES[args.source]
    keep_indices = None
    if args.source_group_holdout:
        if args.source != "meddocan" or args.split != "test":
            parser.error("Source-group holdout is defined for MEDDOCAN test only")
        seen = {
            e.id.rsplit("-", 1)[0]
            for split in ("train", "dev")
            for e in load_public(args.corpus, args.source, split).examples
        }
        keep_indices = {
            i for i, e in enumerate(corpus.examples) if e.id.rsplit("-", 1)[0] not in seen
        }
        selected = tuple(e for i, e in enumerate(corpus.examples) if i in keep_indices)
        corpus = PublicCorpus(
            corpus.source,
            corpus.language,
            corpus.provenance_kind,
            selected,
            {
                "official_split": "test",
                "selection": "Source article IDs absent from train/dev; selection does not use predictions or gold errors",
                "official_documents": len(corpus.examples),
                "retained_documents": len(selected),
                "gold_span_count": sum(len(e.spans) for e in selected),
                "gold_verified_against_text": True,
            },
        )
    result = {
        "schema_version": 1,
        "machine": machine_metadata(),
        "source": source_description,
        "integrity": integrity,
        "corpus": corpus.metadata,
        "split": args.split,
        "documents": len(corpus.examples),
        "scope": "Independent public human annotations; semi-synthetic clinical and real public judicial corpora remain separate",
        "taxonomy": taxonomy_description(args.source),
        "corpus_sha256": hashlib.sha256(
            "".join(hashlib.sha256(e.text.encode()).hexdigest() for e in corpus.examples).encode()
        ).hexdigest(),
        "pipelines": [],
    }
    if args.baseline is not None:
        frozen, meta = snapshot_predictions(args.baseline, args.corpus, args.source, args.split)
        if keep_indices is not None:
            frozen = [p for i, p in enumerate(frozen) if i in keep_indices]
        baseline_latency = [
            latency
            for i, latency in enumerate(meta["latency_seconds"])
            if keep_indices is None or i in keep_indices
        ]
        predictions = [map_predictions(args.source, p) for p in frozen]
        result["pipelines"].append(
            {
                "name": "deidflow_v0.2.0_rules",
                "status": "measured",
                "snapshot_commit": meta["commit"],
                "source_sha256": meta["source_sha256"],
                "p50_seconds": statistics.median(baseline_latency),
                "metrics": quality_metrics(corpus, predictions, ci_repeats=args.ci_repeats),
            }
        )
    with offline_network() as guard:
        current, _ = evaluate_detector(
            "deidflow_candidate_rules",
            DeidEngine().scan_text,
            corpus,
            repeats=args.repeats,
            ci_repeats=args.ci_repeats,
        )
        result["pipelines"].append(current)
        if args.tagger:
            from deidflow.nlp import CombinedNER
            from deidflow.nlp.tagger import BUILTIN_MODELS, SpanTagger

            taggers = []
            result["tagger_models"] = {}
            for item in args.tagger:
                name, _, model = item.rpartition("=")
                name = name or "tagger"
                if model.startswith("builtin:"):
                    tagger = SpanTagger.builtin(model[8:])
                    digest = BUILTIN_MODELS[model[8:]][1]
                else:
                    tagger = SpanTagger.load(model)
                    digest = hashlib.sha256(Path(model).read_bytes()).hexdigest()
                result["tagger_models"][name] = {
                    "sha256": digest,
                    "version": tagger.model_version,
                    "accelerated": tagger.accelerated,
                    "training_data": tagger.metadata.get("training_data"),
                }
                taggers.append((name, tagger))
            runs = []
            for name, tagger in taggers:
                runs.append(("deidflow_" + name, tagger.detect))
                runs.append(("deidflow_rules_plus_" + name, DeidEngine(nlp=tagger).scan_text))
            if len(taggers) > 1:
                combined = CombinedNER(*(tagger for _, tagger in taggers))
                label = "+".join(name for name, _ in taggers)
                runs.append(("deidflow_" + label, combined.detect))
                runs.append(("deidflow_rules_plus_" + label, DeidEngine(nlp=combined).scan_text))
            for name, detector in runs:
                measured, _ = evaluate_detector(
                    name, detector, corpus, repeats=args.repeats, ci_repeats=args.ci_repeats
                )
                result["pipelines"].append(measured)
        if (
            args.source == "meddocan"
            and args.spacy_model
            and not args.rules_only
            and args.baseline is not None
        ):
            from deidflow.nlp import SpacyNER

            prior, prior_meta = snapshot_predictions(
                args.baseline, args.corpus, args.source, args.split, nlp_path=args.spacy_model
            )
            if keep_indices is not None:
                prior = [p for i, p in enumerate(prior) if i in keep_indices]
            prior_latency = [
                latency
                for i, latency in enumerate(prior_meta["latency_seconds"])
                if keep_indices is None or i in keep_indices
            ]
            prior_mapped = [map_predictions(args.source, p) for p in prior]
            result["pipelines"].append(
                {
                    "name": "deidflow_v0.2.0_rules_plus_spacy",
                    "status": "measured",
                    "snapshot_commit": prior_meta["commit"],
                    "source_sha256": prior_meta["source_sha256"],
                    "p50_seconds": statistics.median(prior_latency),
                    "metrics": quality_metrics(corpus, prior_mapped, ci_repeats=args.ci_repeats),
                }
            )

            for name, factory in (
                ("spacy_spanish", _spacy_baseline),
                ("presidio_spanish", _presidio_baseline),
            ):
                detector = factory(args.spacy_model)
                measured, _ = evaluate_detector(
                    name, detector, corpus, repeats=args.repeats, ci_repeats=args.ci_repeats
                )
                result["pipelines"].append(measured)
            engine = DeidEngine(nlp=SpacyNER(args.spacy_model))
            measured, _ = evaluate_detector(
                "deidflow_candidate_rules_plus_spacy",
                engine.scan_text,
                corpus,
                repeats=args.repeats,
                ci_repeats=args.ci_repeats,
            )
            result["pipelines"].append(measured)
        elif args.source == "tab":
            result["pipelines"].append(
                {
                    "name": "spacy_presidio_english",
                    "status": "not_measured",
                    "reason": "No reviewed local English model provisioned; applying a Spanish NER model to English is not a comparable baseline",
                }
            )
        result["network_guard"] = {"attempts": guard["attempts"], "dns_and_connect": "denied"}
    result["limitations"] = [
        "MEDDOCAN is not real private patient data and is predominantly Spain Spanish, not a Mexican enterprise holdout",
        "TAB uses the first reviewed annotator, DIRECT/QUASI mask decisions and a different English judicial task",
        "No corpus text, source filenames or entity values are in this report",
        "Text corpora do not measure OCR/layout/table accuracy or real output-transformation leakage",
        "Confidence intervals resample documents and do not account for source/provider template correlations",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "source": args.source,
                "split": args.split,
                "documents": len(corpus.examples),
                "results": [
                    {
                        "name": p["name"],
                        "status": p["status"],
                        "precision": p.get("metrics", {}).get("exact", {}).get("precision"),
                        "recall": p.get("metrics", {}).get("exact", {}).get("recall"),
                        "f1": p.get("metrics", {}).get("exact", {}).get("f1"),
                    }
                    for p in result["pipelines"]
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
