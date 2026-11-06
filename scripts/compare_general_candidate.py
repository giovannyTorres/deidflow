"""Compare a local general model with the builtin under frozen rules and corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import deidflow

sys.path.insert(0, str(Path(deidflow.__file__).resolve().parents[2] / "scripts"))
from benchmark_context import _checkpoint, _revision, _source_state
from benchmark_domain_regression import _case

from deidflow.benchmarks.context_quality import (
    evaluate_context_sessions,
    load_context_cases,
    measure_context_case,
    summarize_context_counts,
)
from deidflow.benchmarks.release_gate import DIRECT_IDENTIFIERS
from deidflow.benchmarks.runner import offline_network
from deidflow.benchmarks.synthetic_es import generate
from deidflow.domains import get_domain_pack
from deidflow.nlp.tagger import BUILTIN_MODELS, SpanTagger
from deidflow.session import DeidSession


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-model", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path")
    runtime = Path(deidflow.__file__).resolve().parents[2]
    cases, corpus_sha = load_context_cases(runtime / "benchmarks/context-cases-es.jsonl")
    examples = list(generate(600, split="test", seed=1729))
    corpus_digest = hashlib.sha256()
    for example in examples:
        value = json.dumps(asdict(example), sort_keys=True, ensure_ascii=False).encode()
        corpus_digest.update(len(value).to_bytes(8, "big") + value)
    report = {
        "schema_version": 1,
        "evidence_type": "observed_synthetic_regression_model_comparison",
        "git_revision": _revision(),
        "source_state": _source_state(),
        "candidate_revision": args.candidate_revision,
        "baseline_model_sha256": BUILTIN_MODELS["es-general"][1],
        "candidate_model_sha256": args.candidate_sha256,
        "context_corpus_sha256": corpus_sha,
        "synthetic_annotated_records_sha256": corpus_digest.hexdigest(),
        "synthetic_text_sha256": hashlib.sha256(
            "".join(hashlib.sha256(e.text.encode()).hexdigest() for e in examples).encode()
        ).hexdigest(),
        "profile": {"name": "balanced", "review_margin": None, "redact_margin": None},
        "design": "Same frozen runtime, original 600 test documents, domain rules and policies. Only es-general changes for general/legal; clinical and financial remain pinned.",
        "limitations": [
            "Observed regression corpus; no training, threshold selection, or claim of untouched independent model/rule evaluation.",
            "Candidate training provenance requires separate inspection.",
            "No automatically approved domain outputs expected; leaks include review and blocked documents.",
        ],
        "pipelines": {},
    }
    packs = {domain: get_domain_pack(domain) for domain in {case.domain for case in cases}}
    with offline_network() as guard:
        candidate = SpanTagger.load(args.candidate_model, sha256=args.candidate_sha256)
        for name in ["reference_builtin", "candidate_adapter"]:
            engines = {
                domain: (
                    pack.engine(
                        model="custom", adapter=candidate, adapter_digest=args.candidate_sha256
                    )
                    if name == "candidate_adapter" and domain in {"general", "legal"}
                    else pack.engine()
                )
                for domain, pack in packs.items()
            }
            context = evaluate_context_sessions(
                cases,
                lambda domain, selected=engines: DeidSession(
                    selected[domain], policy=packs[domain].policy()
                ),
                checkpoint=_checkpoint,
            )
            totals = Counter()
            direct_totals = Counter()
            statuses = Counter()
            issues = Counter()
            for example in examples:
                case = _case(example)
                with DeidSession(engines["general"], policy=packs["general"].policy()) as session:
                    result = session.deidentify(case.text, domain="general")
                totals.update(measure_context_case(case, result).counts)
                direct = replace(
                    case,
                    spans=tuple(s for s in case.spans if s.entity_type in DIRECT_IDENTIFIERS),
                    preserve=(),
                )
                direct_totals.update(measure_context_case(direct, result).counts)
                statuses[str(result.status)] += 1
                issues.update(result.issues)
            report["pipelines"][name] = {
                "context40": context,
                "synthetic600": {
                    "all_annotated_categories": summarize_context_counts(totals),
                    "direct_identifiers": {
                        k: v
                        for k, v in summarize_context_counts(direct_totals).items()
                        if k
                        in {
                            "documents",
                            "sensitive_characters",
                            "sensitive_spans",
                            "removed_sensitive_characters",
                            "unremoved_sensitive_characters",
                            "fully_replaced_sensitive_spans",
                            "literal_sensitive_value_survivors",
                            "documents_with_unremoved_sensitive_data",
                            "sensitive_character_removal_rate",
                            "full_sensitive_span_removal_rate",
                        }
                    },
                    "status_counts": dict(statuses),
                    "issue_counts": dict(issues),
                },
            }
        report["network_guard"] = {"attempts": guard["attempts"]}
    report["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    for name, p in report["pipelines"].items():
        print(
            name,
            "context40",
            p["context40"]["aggregate"]["joint_success_documents"],
            "stable",
            p["context40"]["aggregate"]["consistent_identity_pairs"],
            "direct",
            p["synthetic600"]["direct_identifiers"],
            "context",
            p["synthetic600"]["all_annotated_categories"]["nonsensitive_character_retention_rate"],
        )


if __name__ == "__main__":
    main()
