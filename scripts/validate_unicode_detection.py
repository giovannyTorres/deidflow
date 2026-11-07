"""Frozen local validation comparison; never selects or reads a test partition.

Run the identical artifact against baseline and candidate via explicit PYTHONPATH.
Only aggregate metrics and hashes are written. No corpus text or predictions are
exported. This validation helper is separate from the library runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import platform
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import deidflow
from deidflow import DeidEngine
from deidflow.benchmarks.public_corpus import PublicCorpus, load_public, verify_acquired_corpus
from deidflow.benchmarks.public_quality import map_predictions, quality_metrics
from deidflow.benchmarks.runner import offline_network
from deidflow.benchmarks.span_corpus import hash_split, load_gretel_finance
from deidflow.benchmarks.synthetic_es import generate
from deidflow.domains import get_domain_pack
from deidflow.nlp.tagger import BUILTIN_MODELS, builtin_profiles

GRETEL_TRAIN_FILENAME = "Spanish_train-00000-of-00001.parquet"
GRETEL_TRAIN_SHA256 = "39954d0931f3d3771af1200f0255016bbe29905dcd0fec539864d3b01ea63b7b"
GRETEL_REVISION = "7b844d16738527a04264f50214cb426a4cea0897"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest_records(records):
    state = hashlib.sha256()
    for record in records:
        raw = canonical(record)
        state.update(len(raw).to_bytes(8, "big"))
        state.update(raw)
    return state.hexdigest()


def digest_sources(root):
    state = hashlib.sha256()
    for path in sorted((root / "src/deidflow").rglob("*.py")):
        name = path.relative_to(root).as_posix().encode()
        raw = path.read_bytes()
        state.update(len(name).to_bytes(8, "big"))
        state.update(name)
        state.update(len(raw).to_bytes(8, "big"))
        state.update(raw)
    return state.hexdigest()


def gretel_validation(corpus_path):
    if corpus_path is None:
        raise SystemExit("Pinned Gretel Spanish train is unavailable")
    path = corpus_path / GRETEL_TRAIN_FILENAME if corpus_path.is_dir() else corpus_path
    if not path.is_file():
        raise SystemExit("Pinned Gretel Spanish train is unavailable")
    path = path.resolve()
    if path.name != GRETEL_TRAIN_FILENAME:
        raise SystemExit("Gretel validation accepts only the pinned Spanish train file")
    if any((parent / ".git").exists() for parent in path.parents):
        raise SystemExit("Raw Gretel validation assets must remain outside Git checkouts")

    def file_digest():
        try:
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError:
            raise SystemExit("Pinned Gretel Spanish train cannot be accessed") from None

    if file_digest() != GRETEL_TRAIN_SHA256:
        raise SystemExit("Gretel Spanish train SHA-256 differs from the registered pin")
    try:
        published = load_gretel_finance([path], language="Spanish", split="train")
        training, validation = hash_split(
            published.examples, validation_fraction=0.1, salt="deidflow"
        )
    except Exception:
        raise SystemExit("Pinned Gretel train validation could not be loaded locally") from None
    if file_digest() != GRETEL_TRAIN_SHA256:
        raise SystemExit("Pinned Gretel Spanish train changed during loading")
    examples = tuple(validation)
    assert all(example.split == "validation" for example in examples)
    metadata = {
        "partition": "validation",
        "official_split": "train",
        "evidence_type": "public_synthetic_financial_validation",
        "provenance_kind": "synthetic_financial",
        "source": "Gretel.ai synthetic_pii_finance_multilingual",
        "license": "Apache-2.0",
        "source_revision": GRETEL_REVISION,
        "train_file_sha256": GRETEL_TRAIN_SHA256,
        "published_train_documents_loaded": len(published.examples),
        "internal_training_documents_not_scored": len(training),
        "documents": len(examples),
        "gold_mentions": sum(len(e.spans) for e in examples),
        "gold_support_by_entity": dict(
            sorted(Counter(s.entity_type for e in examples for s in e.spans).items())
        ),
        "hash_split": {
            "validation_fraction": 0.1,
            "salt": "deidflow",
            "duplicate_texts_share_partition": True,
            "identity_or_template_independence_accredited": False,
        },
        "template_ids_retained_from_published_train": True,
        "official_test_files_opened": 0,
        "annotated_records_sha256": digest_records(asdict(e) for e in examples),
        "texts_sha256": digest_records(e.text for e in examples),
    }
    corpus = PublicCorpus("gretel_finance", "Spanish", "synthetic_financial", examples, metadata)
    return corpus, examples, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--label", choices=("baseline", "candidate"), required=True)
    parser.add_argument(
        "--source", choices=("synthetic", "meddocan", "gretel"), default="synthetic"
    )
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--expected-revision")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    runtime = Path(deidflow.__file__).resolve()
    if not runtime.is_relative_to(root / "src"):
        raise SystemExit(
            "Wrong deidflow runtime: set explicit PYTHONPATH to the selected source/src"
        )
    if args.output.exists():
        raise SystemExit("Refusing to overwrite validation evidence")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if args.expected_revision and args.expected_revision != revision:
        raise SystemExit("Source revision differs from expected pin")
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root, text=True
        )
    )
    if args.label == "baseline" and dirty:
        raise SystemExit("Baseline must be a clean checkout")
    before_digest = digest_sources(root)
    if args.source == "synthetic":
        if args.corpus is not None:
            raise SystemExit("Synthetic validation does not accept external corpus input")
        examples = tuple(generate(600, split="validation", seed=1729))
        assert len(examples) == 600 and all(e.split == "validation" for e in examples)
        generator_path = Path(inspect.getsourcefile(generate))
        metadata = {
            "partition": "validation",
            "evidence_type": "synthetic_validation",
            "provenance_kind": "generated_fictional",
            "generator": "deidflow.benchmarks.synthetic_es.generate",
            "generator_sha256": hashlib.sha256(generator_path.read_bytes()).hexdigest(),
            "faker_version": importlib.metadata.version("faker"),
            "seed": 1729,
            "documents": len(examples),
            "gold_mentions": sum(len(e.spans) for e in examples),
            "gold_support_by_entity": dict(
                sorted(Counter(s.entity_type for e in examples for s in e.spans).items())
            ),
            "template_families": dict(
                sorted(Counter(e.template_id.split(":")[0] for e in examples).items())
            ),
            "annotated_records_sha256": digest_records(asdict(e) for e in examples),
            "texts_sha256": digest_records(e.text for e in examples),
        }
        corpus = PublicCorpus("synthetic_es", "es", "synthetic", examples, metadata)
    elif args.source == "meddocan":
        if args.corpus is None:
            raise SystemExit("MEDDOCAN dev requires an explicitly supplied registered corpus path")
        integrity = verify_acquired_corpus(args.corpus, "meddocan")
        # This is the only public partition parsed or used for detection.
        corpus = load_public(args.corpus, "meddocan", "dev")
        examples = corpus.examples
        assert len(examples) == 250 and all(e.split == "dev" for e in examples)
        metadata = {
            "partition": "validation",
            "official_split": "dev",
            "evidence_type": "public_semi_synthetic_validation",
            "provenance_kind": "semi_synthetic_clinical",
            "source": "SPACCC MEDDOCAN",
            "license": "CC-BY-4.0",
            "source_commit": "783a6df385c975b328c99bcffb54196a9ba4078a",
            "integrity": integrity,
            "integrity_hashing_reads_published_archive_bytes_without_parsing_other_partitions": True,
            "documents": len(examples),
            "gold_mentions": sum(len(e.spans) for e in examples),
            "gold_support_by_entity": dict(
                sorted(Counter(s.entity_type for e in examples for s in e.spans).items())
            ),
            "annotated_records_sha256": digest_records(asdict(e) for e in examples),
            "texts_sha256": digest_records(e.text for e in examples),
            "loader_metadata": corpus.metadata,
        }
    else:
        corpus, examples, metadata = gretel_validation(args.corpus)
    pack = get_domain_pack("general")
    rules_config = {
        "factory": "deidflow.DeidEngine",
        "arguments": {"country": "ALL", "performance": "balanced"},
        "nlp": None,
        "additional_recognizers": [],
        "measurement": "scan_text detection only; no policy transformation",
    }
    general_config = {
        "factory": "get_domain_pack('general').engine",
        "arguments": {"profile": "balanced"},
        "pack": pack.to_dict(),
        "pack_fingerprint": pack.fingerprint(),
        "model_pin": BUILTIN_MODELS[pack.model_name],
        "operating_settings": builtin_profiles()[pack.model_name]["balanced"],
        "policy_fingerprint_not_applied_to_detection": pack.policy().fingerprint(),
        "measurement": "scan_text detection only; same frozen default domain recognizers",
        "default_recognizer_types": [
            type(recognizer).__name__ for recognizer in pack.recognizers()
        ],
    }
    report = {
        "schema_version": "deidflow.unicode-validation.v1",
        "label": args.label,
        "evidence_type": {
            "synthetic": "validation_synthetic_fiction",
            "meddocan": "validation_public_semi_synthetic",
            "gretel": "validation_public_synthetic_financial",
        }[args.source],
        "source": args.source,
        "partition": "validation",
        "source_revision": revision,
        "source_dirty": dirty,
        "python_source_sha256": before_digest,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_version": platform.python_version(),
        "corpus": metadata,
        "detection_passes_per_configuration": 1,
        "warmup_calls": 0,
        "test_partitions_loaded_for_scoring": 0,
        "published_train_files_loaded_for_validation_split": int(args.source == "gretel"),
        "internal_training_examples_scored": 0,
        "threshold_or_weight_adjustments": 0,
        "pipelines": {},
        "limitations": [
            "Validation, whether synthetic or public, is not an untouched test or deployment-quality approval",
            "Detection span coverage is not transformed artifact leakage",
            "Identical fixed defaults compare implementation changes; no model or NarrativeRecognizer adoption decision",
            "Public MEDDOCAN-dev and Gretel train-holdout evidence requires separately available pinned local assets",
            "No text, per-document filenames, entity values or prediction coordinates are exported",
        ],
    }
    with offline_network() as guard:
        for name, configuration, factory in (
            ("rules_only", rules_config, lambda: DeidEngine(country="ALL", performance="balanced")),
            (
                "general_domain_pack_balanced",
                general_config,
                lambda: pack.engine(profile="balanced"),
            ),
        ):
            engine = factory()
            started = time.perf_counter()
            predictions = [
                map_predictions(corpus.source, engine.scan_text(example.text))
                for example in examples
            ]
            inference_seconds = time.perf_counter() - started
            measured = quality_metrics(corpus, predictions, ci_repeats=500)
            exact = measured["exact"]
            coverage = measured["coverage_leakage"]
            report["pipelines"][name] = {
                "configuration": configuration,
                "configuration_sha256": hashlib.sha256(canonical(configuration)).hexdigest(),
                "engine_model_digest": engine.model_digest,
                "detection_calls": len(examples),
                "inference_seconds": inference_seconds,
                "prediction_offsets_sha256": digest_records(
                    [(str(f.entity_type), f.start, f.end) for f in row] for row in predictions
                ),
                "acceptance_metrics": {
                    "exact_false_positives": exact["false_positives"],
                    "exact_false_negatives": exact["false_negatives"],
                    "exact_precision": exact["precision"],
                    "exact_recall": exact["recall"],
                    "exact_f1": exact["f1"],
                    "false_redaction_rate": exact["false_redaction_rate"],
                    "sensitive_character_recall": coverage["sensitive_character_recall"],
                    "documents_with_uncovered_gold_characters": coverage[
                        "documents_with_uncovered_gold_characters"
                    ],
                },
                "metrics": measured,
            }
        report["python_network_attempts"] = guard["attempts"]
    if before_digest != digest_sources(root):
        raise SystemExit("Source changed during validation run")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "label": args.label,
                "source_revision": revision,
                "corpus_sha256": metadata["annotated_records_sha256"],
                "python_network_attempts": report["python_network_attempts"],
                "results": {
                    name: value["acceptance_metrics"] for name, value in report["pipelines"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
