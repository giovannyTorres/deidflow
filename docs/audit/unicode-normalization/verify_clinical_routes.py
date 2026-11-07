"""Validation-only check of the clinical pack and the packaged automatic router."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import deidflow
from deidflow import DeidEngine
from deidflow.benchmarks.public_corpus import load_public, verify_acquired_corpus
from deidflow.benchmarks.public_quality import map_predictions, quality_metrics
from deidflow.benchmarks.runner import offline_network
from deidflow.domains import get_domain_pack
from deidflow.nlp.router import BUILTIN_ROUTER, DomainRouter
from deidflow.nlp.tagger import BUILTIN_MODELS

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--source-root", type=Path, required=True)
p.add_argument("--helper", type=Path, required=True)
p.add_argument("--corpus", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
if a.output.exists():
    raise SystemExit("Refusing to overwrite validation evidence")
if not Path(deidflow.__file__).resolve().is_relative_to(a.source_root.resolve() / "src"):
    raise SystemExit("Wrong runtime source path")
spec = importlib.util.spec_from_file_location("unicode_validation_helper", a.helper)
assert spec is not None and spec.loader is not None
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
source_digest = helper.digest_sources(a.source_root)
integrity = verify_acquired_corpus(a.corpus, "meddocan")
corpus = load_public(a.corpus, "meddocan", "dev")
assert len(corpus.examples) == 250 and all(e.split == "dev" for e in corpus.examples)
pack = get_domain_pack("clinical")
report = {
    "schema_version": "deidflow.unicode-additional-validation.v1",
    "source_revision": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=a.source_root, text=True
    ).strip(),
    "source_sha256": source_digest,
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "helper_sha256": hashlib.sha256(a.helper.read_bytes()).hexdigest(),
    "evidence_type": "public_semi_synthetic_validation",
    "source": "SPACCC MEDDOCAN",
    "official_split": "dev",
    "partition": "validation",
    "documents": 250,
    "integrity": integrity,
    "corpus_texts_sha256": helper.digest_records(e.text for e in corpus.examples),
    "configuration": {
        "clinical_pack": pack.to_dict(),
        "model_pins": BUILTIN_MODELS,
        "router_pin": BUILTIN_ROUTER,
        "profile": "balanced",
    },
    "scoring_passes_per_configuration": 1,
    "warmup_calls": 0,
    "test_scoring_passes": 0,
    "results": {},
}
with offline_network() as guard:
    for name, engine in (
        ("clinical_domain_pack_balanced", pack.engine(profile="balanced")),
        ("builtin_auto_balanced", DeidEngine(nlp=DomainRouter.builtin(profile="balanced"))),
    ):
        rows = [engine.scan_text(e.text) for e in corpus.examples]
        predictions = [map_predictions(corpus.source, row) for row in rows]
        measured = quality_metrics(corpus, predictions, ci_repeats=500)
        report["results"][name] = {
            "prediction_offsets_sha256": helper.digest_records(
                [(str(f.entity_type), f.start, f.end) for f in row] for row in predictions
            ),
            "nlp_scores_sha256": helper.digest_records(
                [
                    (str(f.entity_type), f.start, f.end, f.score, f.confidence, f.context)
                    for f in row
                    if "tagger.local" in f.detector
                ]
                for row in rows
            ),
            "uncertain_nlp_offsets_sha256_at_075": helper.digest_records(
                [
                    (str(f.entity_type), f.start, f.end)
                    for f in row
                    if "tagger.local" in f.detector and f.score < 0.75
                ]
                for row in rows
            ),
            "uncertain_nlp_findings_at_075": sum(
                f.score < 0.75 for row in rows for f in row if "tagger.local" in f.detector
            ),
            "exact": measured["exact"],
            "coverage_leakage": measured["coverage_leakage"],
        }
    report["python_network_attempts"] = guard["attempts"]
assert source_digest == helper.digest_sources(a.source_root)
a.output.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
print("Clinical/auto MEDDOCAN dev validation completed without test scoring")
