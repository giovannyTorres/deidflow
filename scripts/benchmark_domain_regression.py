"""Compare domain refinements with identical model/policy on 600 synthetic documents.

The generator's test template families were withheld from model fitting. This
repeat comparison is a regression measurement, not fresh independent public gold
or a license to tune models on the test partition. No raw text is exported.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import inspect
import json
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from benchmark_context import _revision, _source_state

from deidflow import DeidEngine, __version__
from deidflow.benchmarks.context_quality import (
    ContextCase,
    ContextSpan,
    SensitiveSpan,
    measure_context_case,
    summarize_context_counts,
)
from deidflow.benchmarks.release_gate import DIRECT_IDENTIFIERS
from deidflow.benchmarks.runner import offline_network
from deidflow.benchmarks.synthetic_es import generate
from deidflow.detectors.domain_roles import DomainRoleRecognizer
from deidflow.detectors.narrative import NarrativeRecognizer
from deidflow.domains import get_domain_pack
from deidflow.nlp.tagger import BUILTIN_MODELS, SpanTagger
from deidflow.session import DeidSession


def _case(example: Any) -> ContextCase:
    spans = tuple(
        SensitiveSpan(span.start, span.end, span.entity_type, f"entity-{i}")
        for i, span in enumerate(example.spans)
    )
    # All gold-sensitive categories, including quasi-identifiers, stay outside
    # the utility denominator. Dates intentionally changed are not false positives.
    preserve = []
    cursor = 0
    for span in sorted(spans, key=lambda s: s.start):
        if cursor < span.start:
            preserve.append(ContextSpan(cursor, span.start, "unannotated_context"))
        cursor = max(cursor, span.end)
    if cursor < len(example.text):
        preserve.append(ContextSpan(cursor, len(example.text), "unannotated_context"))
    return ContextCase(example.id, "general", example.id, example.text, spans, tuple(preserve))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=600)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--split", choices=["validation", "test"], default="test")
    parser.add_argument(
        "--ablate-narrative",
        action="store_true",
        help="Compare explicit role-only and role+narrative rules on validation",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path, help="Optional aggregate CSV (empty value means null)")
    args = parser.parse_args()
    if not 1 <= args.documents <= 10000 or args.output.exists():
        parser.error("Use 1–10000 documents and a new output path")
    if args.csv and (args.csv.exists() or args.csv.resolve() == args.output.resolve()):
        parser.error("CSV requires a separate new output path")
    if args.ablate_narrative and args.split != "validation":
        parser.error("Ablation choices must be evaluated on validation, not selected on test")
    examples = list(generate(args.documents, split=args.split, seed=args.seed))
    texts_digest = hashlib.sha256(
        "".join(hashlib.sha256(e.text.encode()).hexdigest() for e in examples).encode()
    ).hexdigest()
    annotations_digest = hashlib.sha256()
    for example in examples:
        raw = json.dumps(asdict(example), sort_keys=True, ensure_ascii=False).encode()
        annotations_digest.update(len(raw).to_bytes(8, "big") + raw)
    generator_path = inspect.getsourcefile(generate)
    assert generator_path is not None
    pack = get_domain_pack("general")
    policy = pack.policy()
    report: dict[str, Any] = {
        "schema_version": 1,
        "evidence_type": "synthetic_template_regression",
        "package_version": __version__,
        "git_revision": _revision(),
        "source_state": _source_state(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "corpus": {
            "generator": "deidflow.benchmarks.synthetic_es.generate",
            "generator_sha256": hashlib.sha256(Path(generator_path).read_bytes()).hexdigest(),
            "faker_version": importlib.metadata.version("faker"),
            "documents": len(examples),
            "split": args.split,
            "seed": args.seed,
            "text_sha256": texts_digest,
            "annotated_records_sha256": annotations_digest.hexdigest(),
            "template_families": dict(
                sorted(Counter(e.template_id.split(":")[0] for e in examples).items())
            ),
            "entity_types": dict(
                sorted(Counter(s.entity_type for e in examples for s in e.spans).items())
            ),
        },
        "comparison_design": "Same es-general balanced model, same general-pack policy, fresh isolated session per document; compare core engine with domain role/boundary refinements.",
        "model_sha256": BUILTIN_MODELS["es-general"][1],
        "profile": "balanced",
        "ablate_narrative": args.ablate_narrative,
        "policy_fingerprint": policy.fingerprint(),
        "policy_actions": {
            kind: policy.rule(kind).action
            for kind in sorted({s.entity_type for e in examples for s in e.spans})
        },
        "pipelines": {},
        "limitations": [
            "Generated fictional examples are not representative annotated real-world documents.",
            "Test families were held out for the existing model; this repeat measurement is not untouched new evidence.",
            "Observed test errors informed grammar corrections in this release; this set is diagnostic/regression evidence for the new rules, not an independent rule holdout.",
            "No training, calibration, margin search or candidate selection is performed here.",
            "Full removal intentionally gives no credit to age bucketing/date shifts or custom transforms; direct identifiers are reported separately.",
            "Utility uses only source characters outside all annotated sensitive spans, not semantic adequacy or legal anonymity.",
            "Cross-document identity, persisted relations, Office, HTML, PDF and OCR are not measured in this independent-document suite.",
        ],
    }
    with offline_network() as guard:
        engines = {
            "base_general_model": DeidEngine(
                nlp=SpanTagger.builtin("es-general", profile="balanced")
            ),
            "general_domain_pack": pack.engine(profile="balanced"),
        }
        if args.ablate_narrative:
            for name, recognizers in (
                (
                    "explicit_role_and_narrative",
                    (DomainRoleRecognizer("general"), NarrativeRecognizer()),
                ),
                ("explicit_role_only", (DomainRoleRecognizer("general"),)),
            ):
                template = pack.engine(profile="balanced")
                engine = DeidEngine(
                    nlp=template.nlp, recognizers=recognizers, performance="balanced"
                )
                engine.model_digest = hashlib.sha256(
                    (name + template.model_digest).encode()
                ).hexdigest()
                engines[name] = engine
            # Explicit variants make the choice independent of future default changes.
            del engines["general_domain_pack"]
        for name, engine in engines.items():
            totals: Counter[str] = Counter()
            direct_totals: Counter[str] = Counter()
            statuses: Counter[str] = Counter()
            issues: Counter[str] = Counter()
            family_counts: dict[str, Counter[str]] = defaultdict(Counter)
            for example in examples:
                case = _case(example)
                with DeidSession(engine, policy=policy) as session:
                    result = session.deidentify(example.text, domain="general")
                statuses[str(result.status)] += 1
                issues.update(result.issues)
                measured = measure_context_case(case, result).counts
                totals.update(measured)
                family_counts[example.template_id.split(":")[0]].update(measured)
                direct = replace(
                    case,
                    spans=tuple(s for s in case.spans if s.entity_type in DIRECT_IDENTIFIERS),
                    preserve=(),
                )
                direct_totals.update(measure_context_case(direct, result).counts)
            direct_summary = summarize_context_counts(direct_totals)
            direct_metrics = {
                key: direct_summary[key]
                for key in (
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
                )
            }
            report["pipelines"][name] = {
                "all_annotated_categories": summarize_context_counts(totals),
                "direct_identifiers": direct_metrics,
                "status_counts": dict(sorted(statuses.items())),
                "issue_counts": dict(sorted(issues.items())),
                "template_families": {
                    name: summarize_context_counts(counts)
                    for name, counts in sorted(family_counts.items())
                },
            }
        report["network_guard"] = {"attempts": guard["attempts"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("pipeline", "scope", "metric", "value"))
            for name, pipeline in report["pipelines"].items():
                for scope in (
                    "all_annotated_categories",
                    "direct_identifiers",
                    "status_counts",
                    "issue_counts",
                ):
                    for metric, value in sorted(pipeline[scope].items()):
                        writer.writerow((name, scope, metric, value))
    print(
        json.dumps(
            {
                name: {
                    "direct_sensitive_character_removal_rate": pipeline["direct_identifiers"][
                        "sensitive_character_removal_rate"
                    ],
                    "full_direct_span_removal_rate": pipeline["direct_identifiers"][
                        "full_sensitive_span_removal_rate"
                    ],
                    "all_sensitive_character_removal_rate": pipeline["all_annotated_categories"][
                        "sensitive_character_removal_rate"
                    ],
                    "nonsensitive_character_retention_rate": pipeline["all_annotated_categories"][
                        "nonsensitive_character_retention_rate"
                    ],
                    "status_counts": pipeline["status_counts"],
                }
                for name, pipeline in report["pipelines"].items()
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
