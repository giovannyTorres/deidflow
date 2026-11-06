"""Independent source-offset measurements for Spanish context regression cases.

This is an evaluation instrument, not a release gate or an anonymization claim.
The shipped cases are fictional and must never be used for fitting or selecting
models while being described as held-out evidence. Reports contain aggregate
counts only: no input/output text, entity values, offsets or session keys.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

from deidflow.core import EntityType
from deidflow.engine import Result
from deidflow.placeholders import LABELS_ES, ROLE_LABELS_ES
from deidflow.transformations import SourceMap

_ID = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")
_TOKEN = re.compile(r"\[(?P<label>[A-Z][A-Z0-9_]{0,39})_[1-9][0-9]{0,5}\]\Z")
_DOMAINS = frozenset({"clinical", "financial", "legal", "general"})
_RELATIONS = frozenset(
    {
        "familiar_de",
        "atiende_a",
        "pertenece_a",
        "representa_a",
        "parte_de",
        "titular_de",
        "contraparte_de",
        "relacionado_con",
    }
)
_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class SensitiveSpan:
    start: int
    end: int
    entity_type: str
    entity_id: str


@dataclass(frozen=True)
class ContextSpan:
    start: int
    end: int
    category: str


@dataclass(frozen=True)
class ExpectedRelation:
    source: str
    relation: str
    target: str


@dataclass(frozen=True)
class ContextCase:
    id: str
    domain: str
    session_id: str
    text: str = field(repr=False)
    spans: tuple[SensitiveSpan, ...]
    preserve: tuple[ContextSpan, ...]
    relations: tuple[ExpectedRelation, ...] = ()


@dataclass
class CaseMeasurement:
    """Counts plus opaque fixture identities for cross-document evaluation."""

    counts: Counter[str]
    mentions: list[tuple[str, str | None]] = field(repr=False)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    if len(items) != len({key for key, _ in items}):
        raise ValueError("Duplicate context corpus field")
    return dict(items)


def _id(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def validate_case(case: ContextCase) -> None:
    if (
        not _id(case.id)
        or not _id(case.session_id)
        or case.domain not in _DOMAINS
        or not isinstance(case.text, str)
        or not case.text
        or len(case.text) > 100_000
        or len(case.spans) + len(case.preserve) > 1000
    ):
        raise ValueError("Invalid context corpus record")
    annotations: tuple[SensitiveSpan | ContextSpan, ...] = (*case.spans, *case.preserve)
    for span in annotations:
        if (
            type(span.start) is not int
            or type(span.end) is not int
            or not 0 <= span.start < span.end <= len(case.text)
        ):
            raise ValueError("Invalid context corpus character offsets")
    previous = 0
    for span in sorted(case.spans, key=lambda s: s.start):
        if (
            span.start < previous
            or span.entity_type not in EntityType.__members__
            or not _id(span.entity_id)
        ):
            raise ValueError("Invalid or overlapping sensitive annotations")
        previous = span.end
    for context in case.preserve:
        if not _id(context.category) or any(
            context.start < span.end and span.start < context.end for span in case.spans
        ):
            raise ValueError("Context annotations overlap sensitive annotations")
    for relation in case.relations:
        if (
            not _id(relation.source)
            or not _id(relation.target)
            or relation.source == relation.target
            or relation.relation not in _RELATIONS
        ):
            raise ValueError("Invalid expected relation")


def load_context_cases(path: str | Path) -> tuple[list[ContextCase], str]:
    """Read bounded test-only JSONL; return cases and the exact corpus digest."""
    with Path(path).open("rb") as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("Context corpus exceeds size limit")
    cases = []
    try:
        for line in raw.decode("utf-8").splitlines():
            data = json.loads(line, object_pairs_hook=_pairs)
            if not isinstance(data, dict) or set(data) != {
                "id",
                "domain",
                "session_id",
                "text",
                "spans",
                "preserve",
                "relations",
            }:
                raise ValueError("Invalid context corpus schema")
            case = ContextCase(
                id=data["id"],
                domain=data["domain"],
                session_id=data["session_id"],
                text=data["text"],
                spans=tuple(SensitiveSpan(**span) for span in data["spans"]),
                preserve=tuple(ContextSpan(**span) for span in data["preserve"]),
                relations=tuple(ExpectedRelation(**edge) for edge in data["relations"]),
            )
            validate_case(case)
            cases.append(case)
    except (UnicodeError, TypeError, KeyError, json.JSONDecodeError):
        raise ValueError("Invalid context corpus") from None
    if not cases or len(cases) > 10_000 or len({case.id for case in cases}) != len(cases):
        raise ValueError("Context corpus requires bounded unique cases")
    groups: dict[str, list[ContextCase]] = defaultdict(list)
    for case in cases:
        groups[case.session_id].append(case)
    for group in groups.values():
        entities = {span.entity_id for case in group for span in case.spans}
        if len({case.domain for case in group}) != 1 or any(
            edge.source not in entities or edge.target not in entities
            for case in group
            for edge in case.relations
        ):
            raise ValueError("Context session has incompatible domain or relation endpoints")
        identity: dict[str, tuple[str, str]] = {}
        for case in group:
            for span in case.spans:
                value = (span.entity_type, case.text[span.start : span.end])
                if span.entity_id in identity and identity[span.entity_id] != value:
                    raise ValueError("Exact-value identity fixture contains conflicting values")
                identity[span.entity_id] = value
    return cases, hashlib.sha256(raw).hexdigest()


def _whole_replacement(mapping: SourceMap, original: str, replacement: str) -> bool:
    """Do not trust an action name to certify the bytes actually emitted."""
    if original in replacement:
        return False
    if mapping.action == "indexed":
        matched = _TOKEN.fullmatch(replacement)
        return matched is not None and matched["label"] in {
            *LABELS_ES.values(),
            *ROLE_LABELS_ES.values(),
        }
    if mapping.action == "placeholder":
        return replacement in {
            f"[{kind}]" for kind in mapping.entity_types if kind in EntityType.__members__
        }
    if mapping.action == "pseudonym":
        return any(
            re.fullmatch(rf"\[DF_{re.escape(kind)}_[A-Z2-7]{{32}}\]", replacement)
            for kind in mapping.entity_types
            if kind in EntityType.__members__
        )
    if mapping.action == "redact":
        return replacement == "█" * len(original)
    if mapping.action == "suppress":
        return replacement == ""
    return False


def measure_context_case(case: ContextCase, result: Result) -> CaseMeasurement:
    """Measure actual output and validate every claimed unchanged source segment.

    Full replacements count as removed source characters. A mask counts only
    its changed prefix; custom/generalizing/date/bucket transforms get no removal
    credit because a source map alone cannot prove their privacy semantics.
    Literal value survival is also checked in the complete output independently.
    """
    validate_case(case)
    counts: Counter[str] = Counter(documents=1)
    sensitive = set(i for s in case.spans for i in range(s.start, s.end))
    counts["sensitive_characters"] = len(sensitive)
    counts["sensitive_spans"] = len(case.spans)
    counts["nonsensitive_characters"] = len(case.text) - len(sensitive)
    counts["required_context_spans"] = len(case.preserve)
    counts["required_context_characters"] = len(
        {i for s in case.preserve for i in range(s.start, s.end)}
    )
    output = result.output_text
    counts["output_documents"] = int(output is not None)
    counts["approved_documents"] = int(result.release_approved)
    valid = output is not None
    source_cursor = output_cursor = 0
    untouched: set[int] = set()
    removed: set[int] = set()
    exact: dict[tuple[int, int], str] = {}
    exact_types: dict[tuple[int, int], tuple[str, ...]] = {}
    if output is not None:
        for mapping in result.mappings:
            if not (
                0 <= source_cursor <= mapping.source_start < mapping.source_end <= len(case.text)
                and 0 <= output_cursor <= mapping.output_start <= mapping.output_end <= len(output)
                and case.text[source_cursor : mapping.source_start]
                == output[output_cursor : mapping.output_start]
            ):
                valid = False
                break
            untouched.update(range(source_cursor, mapping.source_start))
            original = case.text[mapping.source_start : mapping.source_end]
            replacement = output[mapping.output_start : mapping.output_end]
            if _whole_replacement(mapping, original, replacement):
                removed.update(range(mapping.source_start, mapping.source_end))
                if mapping.action == "indexed" and _TOKEN.fullmatch(replacement):
                    exact[(mapping.source_start, mapping.source_end)] = replacement
                    exact_types[(mapping.source_start, mapping.source_end)] = mapping.entity_types
            elif mapping.action == "mask" and replacement == (
                "*" * len(original)
                if len(original) <= 4
                else "*" * (len(original) - 4) + original[-4:]
            ):
                for offset, (before, after) in enumerate(zip(original, replacement, strict=True)):
                    target = untouched if before == after else removed
                    target.add(mapping.source_start + offset)
            elif original == replacement:
                untouched.update(range(mapping.source_start, mapping.source_end))
            else:
                counts["unmeasured_transformations"] += 1
            source_cursor, output_cursor = mapping.source_end, mapping.output_end
        if valid and case.text[source_cursor:] != output[output_cursor:]:
            valid = False
        if valid:
            untouched.update(range(source_cursor, len(case.text)))
    if not valid:
        untouched.clear()
        removed.clear()
        exact.clear()
        exact_types.clear()
    counts["valid_source_map_documents"] = int(valid)
    counts["removed_sensitive_characters"] = len(sensitive & removed)
    counts["unremoved_sensitive_characters"] = len(sensitive - removed)
    counts["retained_nonsensitive_characters"] = len(untouched - sensitive)
    counts["fully_replaced_sensitive_spans"] = sum(
        set(range(span.start, span.end)) <= removed for span in case.spans
    )
    counts["exact_indexed_sensitive_spans"] = sum(
        (span.start, span.end) in exact for span in case.spans
    )
    counts["typed_exact_indexed_sensitive_spans"] = sum(
        span.entity_type in exact_types.get((span.start, span.end), ()) for span in case.spans
    )
    counts["literal_sensitive_value_survivors"] = (
        sum(case.text[span.start : span.end] in output for span in case.spans)
        if output is not None
        else 0
    )
    counts["retained_required_context_spans"] = sum(
        set(range(span.start, span.end)) <= untouched for span in case.preserve
    )
    required = {i for s in case.preserve for i in range(s.start, s.end)}
    counts["retained_required_context_characters"] = len(required & untouched)
    leaked = bool(
        counts["unremoved_sensitive_characters"] or counts["literal_sensitive_value_survivors"]
    )
    counts["documents_with_unremoved_sensitive_data"] = int(leaked)
    counts["approved_documents_with_unremoved_sensitive_data"] = int(
        result.release_approved and leaked
    )
    counts["joint_success_documents"] = int(
        valid
        and not leaked
        and counts["retained_required_context_spans"] == counts["required_context_spans"]
    )
    return CaseMeasurement(
        counts,
        [(span.entity_id, exact.get((span.start, span.end))) for span in case.spans],
    )


_RATIOS = {
    "sensitive_character_removal_rate": ("removed_sensitive_characters", "sensitive_characters"),
    "full_sensitive_span_removal_rate": ("fully_replaced_sensitive_spans", "sensitive_spans"),
    "exact_indexed_span_rate": ("exact_indexed_sensitive_spans", "sensitive_spans"),
    "typed_exact_indexed_span_rate": ("typed_exact_indexed_sensitive_spans", "sensitive_spans"),
    "nonsensitive_character_retention_rate": (
        "retained_nonsensitive_characters",
        "nonsensitive_characters",
    ),
    "required_context_retention_rate": (
        "retained_required_context_spans",
        "required_context_spans",
    ),
    "same_entity_consistency_rate": ("consistent_identity_pairs", "identity_pairs"),
    "declared_relation_fidelity": ("retained_relations", "expected_relations"),
    "declared_relation_precision": ("retained_relations", "actual_relations"),
    "joint_success_rate": ("joint_success_documents", "documents"),
    "approved_sensitive_data_leak_rate": (
        "approved_documents_with_unremoved_sensitive_data",
        "approved_documents",
    ),
}


def summarize_context_counts(counts: Mapping[str, int]) -> dict[str, Any]:
    summary: dict[str, Any] = dict(sorted(counts.items()))
    for name, (numerator, denominator) in _RATIOS.items():
        summary[name] = (
            counts.get(numerator, 0) / counts[denominator] if counts.get(denominator) else None
        )
    supporting = counts.get("sessions_supporting_relations", 0)
    summary["relation_support"] = (
        "unsupported"
        if not supporting
        else "supported"
        if supporting == counts.get("sessions")
        else "partial"
    )
    if not supporting:
        summary["declared_relation_fidelity"] = None
    return summary


def _relations(
    session: Any, expected: set[ExpectedRelation], tokens: dict[str, set[str]], counts: Counter[str]
) -> None:
    counts["expected_relations"] += len(expected)
    supported = callable(getattr(session, "graph", None)) and callable(
        getattr(session, "relate", None)
    )
    counts["sessions_supporting_relations"] += int(supported)
    if not supported:
        return
    graph = session.graph()
    requested: dict[tuple[str, str, str], set[str]] = {}
    for edge in sorted(expected, key=lambda e: (e.source, e.relation, e.target)):
        if len(tokens.get(edge.source, set())) != 1 or len(tokens.get(edge.target, set())) != 1:
            continue
        source, target = next(iter(tokens[edge.source])), next(iter(tokens[edge.target]))
        evidence = [
            occ["id"] for occ in graph["occurrences"] if occ["entity_id"] in {source, target}
        ]
        requested[(source, edge.relation, target)] = set(evidence)
        try:
            session.relate(source, edge.relation, target, evidence_ids=evidence, provenance="human")
        except (ValueError, TypeError):
            counts["relation_errors"] += 1
            continue
        counts["attempted_relations"] += 1
    actual = session.graph()["relations"]
    retained: set[tuple[str, str, str]] = set()
    counts["actual_relations"] += len(actual)
    for item in actual:
        identity = (item["source"], item["relation"], item["target"])
        if (
            identity in requested
            and identity not in retained
            and item["provenance"] == "human"
            and set(item["evidence_ids"]) == requested[identity]
        ):
            retained.add(identity)
        else:
            counts["unexpected_relations"] += 1
    counts["retained_relations"] += len(retained)


def evaluate_context_sessions(
    cases: Sequence[ContextCase],
    session_factory: Callable[[str], Any],
    *,
    checkpoint: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one fresh session per fixture group with identical corpus order.

    Relations are explicitly supplied by the fixture, never automatically
    inferred: fidelity measures storage of declared edges, not extraction skill.
    Identity credit requires exact-boundary indexed replacements in both docs.
    """
    grouped: dict[str, list[ContextCase]] = defaultdict(list)
    if not cases or len({case.id for case in cases}) != len(cases):
        raise ValueError("Evaluation requires nonempty unique cases")
    for case in cases:
        validate_case(case)
        grouped[case.session_id].append(case)
    domain_counts: dict[str, Counter[str]] = defaultdict(Counter)
    statuses: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    for group in grouped.values():
        if len({case.domain for case in group}) != 1:
            raise ValueError("A fixture session cannot mix domain packs")
        counts = domain_counts[group[0].domain]
        counts["sessions"] += 1
        session = session_factory(group[0].domain)
        mentions: dict[str, list[tuple[int, str | None]]] = defaultdict(list)
        tokens: dict[str, set[str]] = defaultdict(set)
        try:
            for index, case in enumerate(group):
                try:
                    result = session.deidentify(case.text, domain=case.domain)
                    statuses[str(result.status)] += 1
                except (ValueError, TypeError, RuntimeError) as error:
                    errors[type(error).__name__] += 1
                    from deidflow.engine import ReleaseStatus

                    result = Result(ReleaseStatus.BLOCKED)
                    statuses["PROCESSING_ERROR"] += 1
                measurement = measure_context_case(case, result)
                counts.update(measurement.counts)
                for entity, token in measurement.mentions:
                    mentions[entity].append((index, token))
                    if token is not None:
                        tokens[entity].add(token)
                if checkpoint is not None and index + 1 < len(group):
                    session = checkpoint(session)
                    counts["checkpoint_roundtrips"] += 1
            for values in mentions.values():
                for first, second in combinations(values, 2):
                    if first[0] != second[0]:
                        counts["identity_pairs"] += 1
                        counts["consistent_identity_pairs"] += int(
                            first[1] is not None and first[1] == second[1]
                        )
            for first_tokens, second_tokens in combinations(tokens.values(), 2):
                counts["distinct_entity_collisions"] += int(bool(first_tokens & second_tokens))
            _relations(session, {edge for case in group for edge in case.relations}, tokens, counts)
        finally:
            session.close()
    total: Counter[str] = Counter()
    for counts in domain_counts.values():
        total.update(counts)
    return {
        "aggregate": summarize_context_counts(total),
        "domains": {
            name: summarize_context_counts(counts) for name, counts in sorted(domain_counts.items())
        },
        "status_counts": dict(sorted(statuses.items())),
        "processing_errors": dict(sorted(errors.items())),
        "checkpoint_between_documents": checkpoint is not None,
        "evidence": "Fictional fixed regression cases; not population accuracy or production readiness.",
        "relation_definition": "Storage fidelity for explicitly declared human edges, not automatic extraction.",
        "identity_definition": "Exact values within one session; cross-document pairs require indexed replacement with exact gold boundaries.",
    }


__all__ = [
    "ContextCase",
    "ContextSpan",
    "ExpectedRelation",
    "SensitiveSpan",
    "evaluate_context_sessions",
    "load_context_cases",
    "measure_context_case",
    "summarize_context_counts",
]
