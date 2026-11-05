"""Public gold evaluation with fixed taxonomies and document bootstrap intervals."""

from __future__ import annotations

import hashlib
import json
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from deidflow.core import Finding

from .datasets import Example
from .metrics import evaluate
from .public_corpus import MEDDOCAN_LABELS, TAB_LABELS, PublicCorpus
from .runner import measure

_CLINICAL_NOT_ANNOTATED = {
    "DIAGNOSIS",
    "MEDICAL_CONDITION",
    "TREATMENT",
    "MEDICATION",
    "CLINICAL_OBSERVATION",
    "MEDICAL_HISTORY",
    "MEDICAL_ATTRIBUTE",
}
_CODE_TYPES = {
    "RFC",
    "CURP",
    "CLABE",
    "BANK_ACCOUNT",
    "PAYMENT_CARD",
    "NATIONAL_ID",
    "EMPLOYEE_ID",
    "CUSTOMER_ID",
    "PATIENT_ID",
    "PASSPORT",
    "DOCUMENT_ID",
    "REGIONAL_ID",
    "INTERNAL_ID",
    "CONTRACT_ID",
    "PHONE",
    "EMAIL",
    "INSURANCE_ID",
}


def map_predictions(source: str, findings: Sequence[Finding]) -> list[Finding]:
    result = []
    for finding in findings:
        kind = finding.entity_type
        if kind in _CLINICAL_NOT_ANNOTATED:
            continue
        if source == "meddocan":
            kind = {
                "DATE_OF_BIRTH": "DATE",
                "NATIONAL_ID": "PATIENT_ID",
                "PASSPORT": "PATIENT_ID",
            }.get(kind, kind)
        elif source == "tab":
            if kind in _CODE_TYPES:
                kind = "CODE"
            elif kind in {"AGE", "OCCUPATION", "DEMOGRAPHIC"}:
                kind = "DEMOGRAPHIC"
            elif kind == "DATE_OF_BIRTH":
                kind = "DATE"
        else:
            raise ValueError("Unknown public evaluation source")
        result.append(replace(finding, entity_type=kind))
    return result


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    point = (len(ordered) - 1) * fraction
    lower = int(point)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (
        point - lower
    )


def bootstrap_intervals(
    examples: Sequence[Example],
    predictions: Sequence[Sequence[Finding]],
    *,
    repeats: int = 500,
    seed: int = 1729,
) -> dict[str, Any]:
    if repeats < 1 or len(examples) != len(predictions):
        raise ValueError("Invalid confidence-interval input")
    if len(examples) < 20:
        return {
            "status": "insufficient_documents",
            "documents": len(examples),
            "minimum_documents": 20,
        }
    rows = []
    for example, predicted in zip(examples, predictions, strict=True):
        metric = evaluate([example], [predicted])
        rows.append(
            (
                metric.true_positives,
                metric.false_positives,
                metric.false_negatives,
                int(metric.false_negatives > 0),
                int(bool(example.spans)),
            )
        )
    rng = random.Random(seed)
    values: dict[str, list[float]] = {
        "precision": [],
        "recall": [],
        "f1": [],
        "document_leakage_rate": [],
    }
    for _ in range(repeats):
        selected = rng.choices(rows, k=len(rows))
        tp, fp, fn, leak, positive = [sum(row[k] for row in selected) for k in range(5)]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        values["precision"].append(precision)
        values["recall"].append(recall)
        values["f1"].append(
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        values["document_leakage_rate"].append(leak / positive if positive else 0.0)
    return {
        "status": "measured",
        "unit": "document bootstrap",
        "seed": seed,
        "repeats": repeats,
        "confidence": 0.95,
        "intervals": {
            key: [_percentile(vals, 0.025), _percentile(vals, 0.975)]
            for key, vals in values.items()
        },
    }


def _subset(
    examples: Sequence[Example], predictions: Sequence[Sequence[Finding]], kinds: set[str]
) -> tuple[list[Example], list[list[Finding]]]:
    return (
        [replace(e, spans=tuple(s for s in e.spans if s.entity_type in kinds)) for e in examples],
        [[f for f in p if f.entity_type in kinds] for p in predictions],
    )


def quality_metrics(
    corpus: PublicCorpus, predictions: Sequence[Sequence[Finding]], *, ci_repeats: int = 500
) -> dict[str, Any]:
    examples = corpus.examples
    exact = evaluate(examples, predictions)
    overlap = evaluate(examples, predictions, exact=False)
    person_examples, person_predictions = _subset(examples, predictions, {"PERSON"})
    comparable = (
        {"PERSON", "LOCATION", "EMAIL", "PHONE", "DATE"}
        if corpus.source == "meddocan"
        else {"PERSON", "LOCATION", "DATE"}
    )
    comparable_examples, comparable_predictions = _subset(examples, predictions, comparable)
    frequencies = Counter(e.text[s.start : s.end].casefold() for e in examples for s in e.spans)
    frequency_strata = {}
    for name, check in (
        ("once", lambda n: n == 1),
        ("two_to_five", lambda n: 2 <= n <= 5),
        ("more_than_five", lambda n: n > 5),
    ):
        total = hit = 0
        for example, predicted in zip(examples, predictions, strict=True):
            keys = {(f.entity_type, f.start, f.end) for f in predicted}
            for gold in example.spans:
                if check(frequencies[example.text[gold.start : gold.end].casefold()]):
                    total += 1
                    hit += int((gold.entity_type, gold.start, gold.end) in keys)
        frequency_strata[name] = {
            "gold_mentions": total,
            "exact_recall": hit / total if total else None,
        }
    sensitive_chars = covered_sensitive_chars = character_leaked_docs = positive_docs = 0
    value_coverage: dict[tuple[str, str], list[bool]] = {}
    for example, predicted in zip(examples, predictions, strict=True):
        covered = bytearray(len(example.text))
        for finding in predicted:
            covered[finding.start : finding.end] = b"\x01" * (finding.end - finding.start)
        sensitive = bytearray(len(example.text))
        for gold in example.spans:
            sensitive[gold.start : gold.end] = b"\x01" * (gold.end - gold.start)
            key = (gold.entity_type, example.text[gold.start : gold.end].casefold())
            value_coverage.setdefault(key, []).append(all(covered[gold.start : gold.end]))
        total = sum(sensitive)
        hit = sum(bool(s) and bool(c) for s, c in zip(sensitive, covered, strict=True))
        sensitive_chars += total
        covered_sensitive_chars += hit
        positive_docs += int(total > 0)
        character_leaked_docs += int(hit < total)
    review_documents = sum(
        any(f.score < 0.75 or f.validation == "invalid" for f in predicted)
        for predicted in predictions
    )
    return {
        "exact": exact.to_dict(),
        "overlap": overlap.to_dict(),
        "confidence_intervals": bootstrap_intervals(examples, predictions, repeats=ci_repeats),
        "person_only_exact": evaluate(person_examples, person_predictions).to_dict(),
        "common_scope_exact": evaluate(comparable_examples, comparable_predictions).to_dict(),
        "common_scope_types": sorted(comparable),
        "frequency_strata": frequency_strata,
        "coverage_leakage": {
            "sensitive_character_recall": covered_sensitive_chars / sensitive_chars
            if sensitive_chars
            else None,
            "documents_with_uncovered_gold_characters": character_leaked_docs,
            "character_coverage_document_leakage_rate": character_leaked_docs / positive_docs
            if positive_docs
            else None,
            "entity_value_groups": len(value_coverage),
            "entity_value_complete_coverage_rate": sum(
                all(hits) for hits in value_coverage.values()
            )
            / len(value_coverage)
            if value_coverage
            else None,
            "definition": "Union of predicted spans, irrespective of predicted category; detection coverage only, not final transformed-output leakage. Entity values group by category and casefolded text, not verified personal identities.",
        },
        "leakage_breakdown": leakage_breakdown(corpus, predictions),
        "uncertain_candidate_document_rate": review_documents / len(examples),
        "review_rate_definition": "candidate uncertainty proxy only; no transformation or semantic-model release gating evaluated",
        "strata": {
            "source": corpus.source,
            "language": corpus.language,
            "source_format": "text",
            "scanned": False,
            "domain": corpus.provenance_kind,
            "structure": "unstructured",
        },
        "ocr_cer": None,
        "ocr_wer": None,
        "table_reconstruction_quality": None,
        "unavailable_metrics_reason": "Text gold corpus does not include original page images or table geometry; rule scores are not calibrated",
    }


DIRECT_IDENTIFIERS = frozenset(
    {
        "PERSON",
        "ADDRESS",
        "PATIENT_ID",
        "EMAIL",
        "REGIONAL_ID",
        "INSURANCE_ID",
        "PHONE",
        "EMPLOYEE_ID",
    }
)


def leakage_breakdown(
    corpus: PublicCorpus, predictions: Sequence[Sequence[Finding]]
) -> dict[str, Any]:
    """Leak-oriented view (audit F0.1): a gold mention is protected only if every one
    of its characters is covered by some prediction, whatever the predicted category."""
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
            leak |= gold.entity_type in DIRECT_IDENTIFIERS and not complete
        docs_direct_leak += int(leak)
        for kind, start, end in {(f.entity_type, f.start, f.end) for f in predicted}:
            pred_n[kind] += 1
            pred_typed[kind] += int(
                any(
                    g.entity_type == kind and g.start < end and g.end > start for g in example.spans
                )
            )
    direct_total = sum(gold_n[k] for k in DIRECT_IDENTIFIERS)
    return {
        "fully_covered_mention_rate": sum(full.values()) / sum(gold_n.values()) if gold_n else None,
        "direct_fully_covered_mention_rate": sum(full[k] for k in DIRECT_IDENTIFIERS) / direct_total
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
            for kind in sorted(set(gold_n) | set(pred_n), key=lambda k: (-gold_n[k], k))
        },
        "definition": "fully covered = every gold character covered by any prediction, any category; detection coverage only, not transformed-output verification",
    }


def role_metrics(
    roles: Sequence[Sequence[tuple[int, int, str]]], raw: Sequence[Sequence[Finding]]
) -> dict[str, Any]:
    """Person-role evidence (``role:<name>`` context) against role gold (audit F0.2)."""
    if len(roles) != len(raw):
        raise ValueError("Role gold and predictions must align")
    gold: Counter[str] = Counter()
    with_role: Counter[str] = Counter()
    correct: Counter[str] = Counter()
    for spans, findings in zip(roles, raw, strict=True):
        people = [f for f in findings if f.entity_type == "PERSON"]
        for start, end, role in spans:
            gold[role] += 1
            predicted = {
                c[5:]
                for f in people
                if f.start < end and f.end > start
                for c in f.context
                if c.startswith("role:")
            }
            if len(predicted) == 1:
                with_role[role] += 1
                correct[role] += int(predicted == {role})
    return {
        role: {
            "gold_mentions": gold[role],
            "role_assigned_rate": with_role[role] / gold[role] if gold[role] else None,
            "role_accuracy_when_assigned": correct[role] / with_role[role]
            if with_role[role]
            else None,
        }
        for role in sorted(gold)
    }


def evaluate_detector(
    name: str,
    detect: Callable[[str], Sequence[Finding]],
    corpus: PublicCorpus,
    *,
    repeats: int = 1,
    ci_repeats: int = 500,
) -> tuple[dict[str, Any], list[list[Finding]]]:
    if repeats < 1:
        raise ValueError("Benchmark repeats must be positive")
    detect(corpus.examples[0].text)
    latency = []
    raw: list[list[Finding]] = []
    runs = []
    for _ in range(repeats):

        def work() -> list[list[Finding]]:
            results = []
            for example in corpus.examples:
                start = time.perf_counter()
                results.append(list(detect(example.text)))
                latency.append(time.perf_counter() - start)
            return results

        measurement, raw = measure(
            work,
            units=len(corpus.examples),
            size_bytes=sum(len(e.text.encode()) for e in corpus.examples),
        )
        runs.append(measurement)
    predictions = [map_predictions(corpus.source, p) for p in raw]
    output = {
        "name": name,
        "status": "measured",
        "documents": len(corpus.examples),
        "repeats": repeats,
        "runs": runs,
        "p50_seconds": statistics.median(latency),
        "p95_seconds": _percentile(latency, 0.95),
        "metrics": quality_metrics(corpus, predictions, ci_repeats=ci_repeats),
        "prediction_sha256": hashlib.sha256(
            json.dumps([[(f.entity_type, f.start, f.end) for f in p] for p in predictions]).encode()
        ).hexdigest(),
    }
    return output, raw


def snapshot_predictions(
    snapshot: str | Path,
    corpus_root: str | Path,
    source: str,
    split: str,
    *,
    python: str | None = None,
    nlp_path: str | Path | None = None,
) -> tuple[list[list[Finding]], dict[str, Any]]:
    """Execute a frozen source tree without passing its document text to stdout."""
    import os
    import tempfile

    snapshot = Path(snapshot).resolve()
    if not (snapshot / "src/deidflow/__init__.py").is_file():
        raise ValueError("Frozen baseline source is unavailable")
    provenance_path = snapshot / "baseline-provenance.json"
    if not provenance_path.is_file():
        raise ValueError("Frozen baseline provenance is unavailable")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("commit") != "0b79d3d" or provenance.get("version") != "0.2.0":
        raise ValueError("Unexpected frozen baseline provenance")
    source_sha256 = hashlib.sha256(
        json.dumps(
            {
                str(p.relative_to(snapshot)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((snapshot / "src").rglob("*.py"))
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    with tempfile.TemporaryDirectory(prefix="deidflow-public-predictions-") as temporary:
        output = Path(temporary) / "predictions.json"
        # Loader module stays current, but baseline package owns all imports.
        driver = r"""
import json,sys,time,socket
from pathlib import Path
def deny(*a,**k):raise RuntimeError("Frozen inference network disabled")
socket.getaddrinfo=deny;socket.create_connection=deny;socket.socket.connect=deny;socket.socket.connect_ex=deny
from deidflow import DeidEngine
from deidflow.nlp import SpacyNER
data=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
engine=DeidEngine(nlp=SpacyNER(sys.argv[3]) if len(sys.argv)>3 else None);predictions=[];latency=[]
for text in data:
    start=time.perf_counter();f=engine.scan_text(text);latency.append(time.perf_counter()-start)
    predictions.append([[x.entity_type,x.start,x.end,x.score,x.detector,x.validation,x.model_version] for x in f])
Path(sys.argv[2]).write_text(json.dumps({"predictions":predictions,"latency_seconds":latency}),encoding="utf-8")
"""
        from .public_corpus import load_public

        corpus = load_public(corpus_root, source, split)
        data = Path(temporary) / "public-input.json"
        data.write_text(json.dumps([e.text for e in corpus.examples]), encoding="utf-8")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(snapshot / "src")
        completed = subprocess.run(
            [
                python or sys.executable,
                "-c",
                driver,
                str(data),
                str(output),
                *([str(Path(nlp_path).resolve())] if nlp_path else []),
            ],
            cwd=snapshot,
            env=environment,
            capture_output=True,
            timeout=300,
        )
        if completed.returncode:
            raise RuntimeError("Frozen public baseline process failed")
        result = json.loads(output.read_text(encoding="utf-8"))
    predictions = [
        [
            Finding(kind, start, end, score, detector, validation=validation, model_version=version)
            for kind, start, end, score, detector, validation, version in doc
        ]
        for doc in result["predictions"]
    ]
    return predictions, {
        "latency_seconds": result["latency_seconds"],
        "source_snapshot": "frozen-v0.2.0",
        "commit": provenance["commit"],
        "source_sha256": source_sha256,
    }


def taxonomy_description(source: str) -> dict[str, Any]:
    return {
        "gold_label_mapping": MEDDOCAN_LABELS if source == "meddocan" else TAB_LABELS,
        "prediction_aliases": {
            "meddocan": {
                "DATE_OF_BIRTH": "DATE",
                "NATIONAL_ID": "PATIENT_ID",
                "PASSPORT": "PATIENT_ID",
            },
            "tab": "regional/document/contact identifiers -> CODE; AGE/OCCUPATION -> DEMOGRAPHIC",
        },
        "excluded_prediction_categories": sorted(_CLINICAL_NOT_ANNOTATED),
        "exclusion_reason": "These clinical attributes are outside the PHI/masking gold annotation task, so unlabeled medical spans cannot be asserted false positives",
    }
