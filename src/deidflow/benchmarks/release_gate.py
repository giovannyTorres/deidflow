"""End-to-end release decisions and real output leakage on gold-annotated text.

A gold character leaks when no applied transformation covers its source offset.
The central operational number is the *approved leak rate*: of the documents a
configuration would release without review, the share that still contain at
least one sensitive character. Only aggregate counts are produced.
"""

from __future__ import annotations

import math
import statistics
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from deidflow.benchmarks.datasets import Example
from deidflow.core import Finding
from deidflow.engine import DeidEngine
from deidflow.policies import Policy

# Categories that identify a person or account on their own (TAB's DIRECT
# identifiers). Dates, ages, places, organizations, occupations and similar
# categories are quasi-identifiers: risky in combination, reported separately.
DIRECT_IDENTIFIERS = frozenset(
    {
        "PERSON", "EMAIL", "PHONE", "ADDRESS", "DATE_OF_BIRTH", "RFC", "CURP", "CLABE",
        "BANK_ACCOUNT", "PAYMENT_CARD", "NATIONAL_ID", "PASSPORT", "PATIENT_ID",
        "INSURANCE_ID", "REGIONAL_ID", "EMPLOYEE_ID", "CUSTOMER_ID", "CREDENTIAL",
        "API_KEY", "AUTH_TOKEN", "IP_ADDRESS", "TAX_ID",
    }
)  # fmt: skip


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> list[float] | None:
    """Wilson score interval for a binomial proportion; ``None`` without trials."""
    if trials <= 0:
        return None
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def release_gate_metrics(
    engine: DeidEngine, examples: Sequence[Example], policy: Policy
) -> dict[str, Any]:
    statuses: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    leaked_documents: Counter[str] = Counter()
    direct_leaked_documents: Counter[str] = Counter()
    leaked_characters: Counter[str] = Counter()
    sensitive_characters = nonsensitive_characters = over_redacted = 0
    latency = []
    for example in examples:
        start = time.perf_counter()
        result = engine.deidentify_text(example.text, policy=policy)
        latency.append(time.perf_counter() - start)
        status = str(result.status)
        statuses[status] += 1
        issues.update(result.issues)
        covered = bytearray(len(example.text))
        for mapping in result.mappings:
            covered[mapping.source_start : mapping.source_end] = b"\x01" * (
                mapping.source_end - mapping.source_start
            )
        sensitive = bytearray(len(example.text))
        for span in example.spans:
            sensitive[span.start : span.end] = b"\x01" * (span.end - span.start)
        missed = sum(bool(s) and not c for s, c in zip(sensitive, covered, strict=True))
        direct_missed = any(
            not covered[i]
            for span in example.spans
            if span.entity_type in DIRECT_IDENTIFIERS
            for i in range(span.start, span.end)
            if not example.text[i].isspace()
        )
        extra = sum(
            bool(c) and not s and not character.isspace()
            for s, c, character in zip(sensitive, covered, example.text, strict=True)
        )
        sensitive_characters += sum(sensitive)
        nonsensitive_characters += sum(
            not s and not character.isspace()
            for s, character in zip(sensitive, example.text, strict=True)
        )
        over_redacted += extra
        leaked_characters[status] += missed
        leaked_documents[status] += int(missed > 0)
        direct_leaked_documents[status] += int(direct_missed)
    documents = len(examples)
    approved = statuses.get("APPROVED", 0)
    approved_leaks = leaked_documents.get("APPROVED", 0)
    approved_direct = direct_leaked_documents.get("APPROVED", 0)
    return {
        "documents": documents,
        "status_counts": dict(statuses),
        "issue_counts": dict(issues),
        "approved_rate": approved / documents if documents else None,
        "review_or_blocked_rate": 1 - approved / documents if documents else None,
        "approved_documents_with_leaked_gold_characters": approved_leaks,
        "approved_leak_rate": approved_leaks / approved if approved else None,
        "approved_leak_rate_wilson95": wilson_interval(approved_leaks, approved),
        "approved_documents_with_leaked_direct_identifier": approved_direct,
        "approved_direct_identifier_leak_rate": approved_direct / approved if approved else None,
        "approved_direct_identifier_leak_rate_wilson95": wilson_interval(approved_direct, approved),
        "documents_with_leaked_gold_characters_by_status": dict(leaked_documents),
        "leaked_gold_characters_by_status": dict(leaked_characters),
        "output_sensitive_character_recall": 1
        - sum(leaked_characters.values()) / sensitive_characters
        if sensitive_characters
        else None,
        "over_redaction_rate": over_redacted / nonsensitive_characters
        if nonsensitive_characters
        else None,
        "p50_seconds": statistics.median(latency) if latency else None,
        "definition": "A gold character leaks when no applied transformation covers its source "
        "offset. Over-redaction is the share of non-whitespace, non-gold characters that a "
        "transformation covered. Direct identifiers: "
        + ", ".join(sorted(DIRECT_IDENTIFIERS))
        + "; every other category counts as a quasi-identifier.",
    }


class CachedTagger:
    """Adapter that reuses one Viterbi decoding per source text across margin settings.

    The cache holds the decoding (tokens, paths, max-marginals), not spans, so
    near-miss candidates are re-derived under the tagger's *current*
    ``review_margin``/``redact_margin`` by the same code as live inference.
    Texts that were not pre-computed (such as transformed output) are decoded
    live. Evaluation helper only; not part of the release pipeline.
    """

    def __init__(self, tagger: Any, texts: Iterable[str]) -> None:
        self.tagger = tagger
        self.cache = {text: tagger.decode(text) for text in texts}

    def detect(self, text: str) -> list[Finding]:
        decoded = self.cache.get(text)
        if decoded is None:
            return list(self.tagger.detect(text))
        return list(self.tagger.to_findings(self.tagger.spans(text, decoded)))

    def detect_batch(self, texts: list[str]) -> list[list[Finding]]:
        return [self.detect(text) for text in texts]


__all__ = ["DIRECT_IDENTIFIERS", "CachedTagger", "release_gate_metrics", "wilson_interval"]
