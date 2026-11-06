"""Bounded human review of source text; receipts contain no source values.

The application, configured model digest and human reviewer are trusted. JSON
files and receipt status fields are not authorization. HMAC receipts authenticate
holders of a caller-managed key, not a person's identity or detection accuracy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import asdict, dataclass, replace
from typing import Any

from deidflow.core import EntityType, Finding
from deidflow.detectors import CORE_RULES_VERSION
from deidflow.engine import DeidEngine, ReleaseStatus, Result
from deidflow.placeholders import PlaceholderAllocator
from deidflow.policies import Policy
from deidflow.transformations import (
    SAFE_REPLACEMENT_ACTIONS,
    SourceMap,
    replacement_only,
    transform_text,
)
from deidflow.verification import residual_proper_nouns

MAX_REVIEW_BYTES = 8 * 1024 * 1024
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_SPANS = 10_000
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_REVIEWER = re.compile(r"reviewer-[0-9a-f]{16,64}\Z")
_KINDS = frozenset(str(kind) for kind in EntityType)
_REASONS = frozenset(
    {
        "confirmed",
        "false_positive",
        "public_context",
        "not_personal",
        "missed_identifier",
        "span_correction",
    }
)


class ReviewError(ValueError):
    """Errors intentionally exclude input text, paths and caller-provided values."""


def _fail() -> None:
    raise ReviewError("INVALID_REVIEW_RECORD")


def _canonical(value: Any) -> bytes:
    # Bound caller-supplied dicts before serialization; a byte limit checked
    # after json.dumps alone would not bound deeply nested/oversized objects.
    pending = [(value, 0)]
    nodes = characters = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 200_000 or depth > 16:
            _fail()
        if isinstance(item, dict):
            if len(item) > 100:
                _fail()
            pending.extend((part, depth + 1) for pair in item.items() for part in pair)
        elif isinstance(item, (list, tuple)):
            if len(item) > MAX_SPANS * 2:
                _fail()
            pending.extend((part, depth + 1) for part in item)
        elif isinstance(item, str):
            characters += len(item)
            if characters > MAX_RECORD_BYTES:
                _fail()
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError):
        raise ReviewError("INVALID_REVIEW_RECORD") from None
    if len(encoded) > MAX_RECORD_BYTES:
        _fail()
    return encoded


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hex(value: Any) -> bool:
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _strict_json(value: str) -> dict[str, Any]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_RECORD_BYTES:
        _fail()

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in items}) != len(items):
            _fail()
        return dict(items)

    try:
        result = json.loads(value, object_pairs_hook=pairs, parse_constant=lambda _: _fail())
    except (ValueError, RecursionError):
        raise ReviewError("INVALID_REVIEW_RECORD") from None
    if not isinstance(result, dict):
        _fail()
    return result


@dataclass(frozen=True)
class ReviewSpan:
    span_id: str
    start: int
    end: int
    entity_type: str
    score: float
    evidence_digest: str

    def __post_init__(self) -> None:
        if (
            not _hex(self.span_id)
            or not _hex(self.evidence_digest)
            or type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= MAX_REVIEW_BYTES
            or self.entity_type not in _KINDS
            or type(self.score) not in {int, float}
            or not 0 <= self.score <= 1
        ):
            _fail()


@dataclass(frozen=True)
class ReviewPlan:
    source_digest: str
    source_length: int
    policy_digest: str
    model_digest: str
    domain_digest: str
    spans: tuple[ReviewSpan, ...]
    plan_digest: str
    schema: int = 2
    rules_version: str = CORE_RULES_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.schema) is not int
            or self.schema != 2
            or not isinstance(self.rules_version, str)
            or re.fullmatch(r"rules-[0-9]+(?:\.[0-9]+){1,2}", self.rules_version) is None
            or type(self.source_length) is not int
            or not 0 <= self.source_length <= MAX_REVIEW_BYTES
            or not isinstance(self.spans, tuple)
            or len(self.spans) > MAX_SPANS
            or not all(isinstance(span, ReviewSpan) for span in self.spans)
            or len({span.span_id for span in self.spans}) != len(self.spans)
            or any(span.end > self.source_length for span in self.spans)
            or not all(
                _hex(value)
                for value in (
                    self.source_digest,
                    self.policy_digest,
                    self.model_digest,
                    self.domain_digest,
                    self.plan_digest,
                )
            )
        ):
            _fail()
        if not hmac.compare_digest(self.plan_digest, _digest(self._payload())):
            _fail()

    def _payload(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key != "plan_digest"}

    def to_json(self) -> str:
        return _canonical(asdict(self)).decode()

    @classmethod
    def from_json(cls, value: str) -> ReviewPlan:
        data = _strict_json(value)
        try:
            if set(data) != set(cls.__dataclass_fields__) or not isinstance(data["spans"], list):
                _fail()
            if len(data["spans"]) > MAX_SPANS:
                _fail()
            data["spans"] = tuple(ReviewSpan(**span) for span in data["spans"])
            return cls(**data)
        except (TypeError, KeyError, AttributeError):
            raise ReviewError("INVALID_REVIEW_RECORD") from None


@dataclass(frozen=True)
class ReviewDecision:
    action: str
    reason: str
    span_id: str | None = None
    start: int | None = None
    end: int | None = None
    entity_type: str | None = None

    def __post_init__(self) -> None:
        if self.action not in {"confirm", "reject", "add"} or self.reason not in _REASONS:
            _fail()
        if self.action == "add":
            if (
                self.span_id is not None
                or type(self.start) is not int
                or type(self.end) is not int
                or not 0 <= self.start < self.end <= MAX_REVIEW_BYTES
                or self.entity_type not in _KINDS
                or self.reason not in {"missed_identifier", "span_correction"}
            ):
                _fail()
        elif (
            not _hex(self.span_id)
            or any(v is not None for v in (self.start, self.end, self.entity_type))
            or (self.action == "confirm" and self.reason != "confirmed")
            or (
                self.action == "reject"
                and self.reason
                not in {"false_positive", "public_context", "not_personal", "span_correction"}
            )
        ):
            _fail()

    @classmethod
    def confirm(cls, span_id: str) -> ReviewDecision:
        return cls("confirm", "confirmed", span_id)

    @classmethod
    def reject(cls, span_id: str, *, reason: str = "false_positive") -> ReviewDecision:
        return cls("reject", reason, span_id)

    @classmethod
    def add(
        cls, start: int, end: int, entity_type: str, *, reason: str = "missed_identifier"
    ) -> ReviewDecision:
        return cls("add", reason, start=start, end=end, entity_type=entity_type)


def _source(source: str, maximum: int) -> None:
    if not isinstance(source, str):
        raise ReviewError("INVALID_REVIEW_SOURCE")
    try:
        if len(source.encode("utf-8")) > min(MAX_REVIEW_BYTES, maximum):
            raise ReviewError("REVIEW_SOURCE_LIMIT")
    except UnicodeError:
        raise ReviewError("INVALID_REVIEW_SOURCE") from None


def _plan(
    engine: DeidEngine, source: str, policy: Policy, model_digest: str, domain: str | None
) -> tuple[ReviewPlan, list[Finding]]:
    _source(source, engine.max_bytes)
    if not isinstance(policy, Policy) or not _hex(model_digest):
        _fail()
    configured_digest = getattr(engine, "model_digest", None)
    if configured_digest is not None and configured_digest != model_digest:
        raise ReviewError("REVIEW_MODEL_DIGEST_MISMATCH")
    if domain is not None and (not isinstance(domain, str) or len(domain) > 128):
        _fail()
    findings = sorted(
        engine.scan_text(source), key=lambda f: (f.start, f.end, f.entity_type, f.detector, f.score)
    )
    if len(findings) > MAX_SPANS:
        raise ReviewError("REVIEW_SPAN_LIMIT")
    spans = []
    for index, finding in enumerate(findings):
        evidence = _digest(asdict(finding))
        span_id = _digest([index, finding.start, finding.end, finding.entity_type, evidence])
        spans.append(
            ReviewSpan(
                span_id, finding.start, finding.end, finding.entity_type, finding.score, evidence
            )
        )
    payload: dict[str, Any] = dict(
        source_digest=_hash_text(source),
        source_length=len(source),
        policy_digest=policy.fingerprint(),
        model_digest=model_digest,
        domain_digest=_digest(domain),
        spans=tuple(spans),
        schema=2,
        rules_version=CORE_RULES_VERSION,
    )
    digest_payload = {**payload, "spans": [asdict(span) for span in spans]}
    return ReviewPlan(**payload, plan_digest=_digest(digest_payload)), findings


def create_review_plan(
    engine: DeidEngine, source: str, *, policy: Policy, model_digest: str, domain: str | None = None
) -> ReviewPlan:
    """Detect source spans. model_digest must identify the trusted model/rules manifest.

    The manifest digest is supplied by the application; this function does not
    attest installed model bytes. Plans have offsets, never copied source values.
    """
    return _plan(engine, source, policy, model_digest, domain)[0]


def _project(span: ReviewSpan, mappings: list[SourceMap]) -> tuple[int, int] | None:
    delta = 0
    for mapping in mappings:
        if mapping.source_start < span.end and mapping.source_end > span.start:
            return None
        if mapping.source_end <= span.start:
            delta += (
                mapping.output_end
                - mapping.output_start
                - mapping.source_end
                + mapping.source_start
            )
    return span.start + delta, span.end + delta


@dataclass(frozen=True)
class ReviewedText:
    result: Result
    receipt: dict[str, Any]


def _key(key: bytes | None) -> None:
    if key is not None and (not isinstance(key, bytes) or len(key) < 32):
        raise ReviewError("INVALID_REVIEW_SIGNING_KEY")


def apply_review(
    engine: DeidEngine,
    source: str,
    plan: ReviewPlan,
    decisions: list[ReviewDecision] | tuple[ReviewDecision, ...],
    *,
    policy: Policy,
    model_digest: str,
    reviewer_id: str,
    approve: bool = False,
    source_complete: bool = False,
    signing_key: bytes | None = None,
    domain: str | None = None,
    placeholders: PlaceholderAllocator | None = None,
) -> ReviewedText:
    """Rebuild text from verified source offsets, then rescan and apply release gates.

    approve and source_complete are explicit human attestations, never inferred
    from the plan or a JSON status. Every detected span requires one decision.
    """
    return _apply_review(
        engine,
        source,
        plan,
        decisions,
        policy=policy,
        model_digest=model_digest,
        reviewer_id=reviewer_id,
        approve=approve,
        source_complete=source_complete,
        signing_key=signing_key,
        domain=domain,
        placeholders=placeholders,
    )


def _apply_review(
    engine: DeidEngine,
    source: str,
    plan: ReviewPlan,
    decisions: list[ReviewDecision] | tuple[ReviewDecision, ...],
    *,
    policy: Policy,
    model_digest: str,
    reviewer_id: str,
    approve: bool = False,
    source_complete: bool = False,
    signing_key: bytes | None = None,
    domain: str | None = None,
    placeholders: PlaceholderAllocator | None = None,
    scope: str | None = None,
) -> ReviewedText:
    """Apply the same cell gates with an optional enclosing document's scope."""
    _key(signing_key)
    if (
        not isinstance(plan, ReviewPlan)
        or type(approve) is not bool
        or type(source_complete) is not bool
        or not isinstance(reviewer_id, str)
        or _REVIEWER.fullmatch(reviewer_id) is None
        or not isinstance(decisions, (list, tuple))
        or len(decisions) > MAX_SPANS * 2
        or not all(isinstance(d, ReviewDecision) for d in decisions)
    ):
        _fail()
    fresh, findings = _plan(engine, source, policy, model_digest, domain)
    if fresh != plan:
        raise ReviewError("STALE_REVIEW_PLAN")
    disposition: dict[str, ReviewDecision] = {}
    additions = []
    for decision in decisions:
        if decision.action == "add":
            assert decision.start is not None and decision.end is not None
            assert decision.entity_type is not None
            if decision.end > len(source):
                _fail()
            additions.append(
                Finding(
                    decision.entity_type,
                    decision.start,
                    decision.end,
                    1.0,
                    "human.review",
                    protected=True,
                )
            )
        else:
            assert decision.span_id is not None
            if decision.span_id in disposition:
                _fail()
            disposition[decision.span_id] = decision
    if set(disposition) != {span.span_id for span in plan.spans}:
        raise ReviewError("REVIEW_DECISIONS_INCOMPLETE")
    selected, rejected = [], []
    for span, finding in zip(plan.spans, findings, strict=True):
        if disposition[span.span_id].action == "reject":
            rejected.append(span)
        else:
            # Confirmation resolves this source-span uncertainty, while keeping
            # domain role/gender semantics available to the shared allocator.
            # Context is never serialized into the public review receipt.
            context = tuple(
                c
                for c in finding.context
                if c
                not in {
                    "window_boundary",
                    "domain_boundary_refinement",
                    "domain_context_refinement",
                    "person_coordination_split",
                }
            )
            selected.append(replace(finding, score=1.0, context=context, protected=True))
    selected.extend(additions)
    allocator = placeholders if placeholders is not None else PlaceholderAllocator()
    transformed, mappings = transform_text(
        source,
        selected,
        policy,
        key=engine.key,
        scope=engine._scope(policy, plan.plan_digest) if scope is None else scope,
        domain=domain,
        custom=engine.custom_transforms,
        placeholders=allocator,
    )
    _source(transformed, MAX_REVIEW_BYTES)
    applied = [
        (m.output_start, m.output_end)
        for m in mappings
        if m.action in SAFE_REPLACEMENT_ACTIONS - {"generalize"} and m.output_end > m.output_start
    ]
    rejected_output = [
        (span.entity_type, projected)
        for span in rejected
        if (projected := _project(span, mappings)) is not None
    ]
    residual = []
    for finding in engine.scan_text(transformed):
        if replacement_only(transformed, finding.start, finding.end, ranges=applied):
            continue
        if (finding.entity_type, (finding.start, finding.end)) in rejected_output:
            continue
        residual.append(finding)
    checks = []
    if not approve:
        checks.append("HUMAN_APPROVAL_REQUIRED")
    if not source_complete:
        checks.append("HUMAN_SOURCE_REVIEW_REQUIRED")
    if policy.independent_check == "proper_nouns" and residual_proper_nouns(
        transformed, applied + [position for _, position in rejected_output]
    ):
        checks.append("POSSIBLE_RESIDUAL_PROPER_NOUN")
    result = engine._gate(
        policy=policy,
        residual=residual,
        original=selected,
        domain=domain,
        issues=checks,
        independent_check_checked=True,
        human_reviewed=approve and source_complete,
    )
    result.output_text, result.mappings, result.records = transformed, mappings, 1
    result.audit.update(
        verification="human_review_and_rescan",
        review_plan=plan.plan_digest,
        transformations=len(mappings),
        sha256=_hash_text(transformed),
    )
    payload = dict(
        schema=1,
        plan_digest=plan.plan_digest,
        source_digest=plan.source_digest,
        output_digest=_hash_text(transformed),
        policy_digest=plan.policy_digest,
        model_digest=plan.model_digest,
        domain_digest=plan.domain_digest,
        reviewer_id=reviewer_id,
        approve=approve,
        source_complete=source_complete,
        status=str(result.status),
        issues=list(result.issues),
        decisions=[asdict(d) for d in decisions],
        created_at=int(time.time()),
    )
    encoded = _canonical(payload)
    receipt = {
        "payload": payload,
        "digest": hashlib.sha256(encoded).hexdigest(),
        "signature": (
            hmac.new(signing_key, encoded, hashlib.sha256).hexdigest()
            if signing_key is not None
            else None
        ),
    }
    return ReviewedText(result, receipt)


def verify_review_receipt(
    receipt: dict[str, Any] | str,
    *,
    source: str,
    output: str,
    policy: Policy,
    model_digest: str,
    signing_key: bytes | None = None,
    domain: str | None = None,
    require_signed: bool = True,
    require_approved: bool = True,
) -> bool:
    """Verify bindings/integrity; default requires a signed approved review.

    With require_signed=False, an unsigned digest detects accidental changes
    only: anyone can recompute it. Never use that mode as an authorization check.
    """
    try:
        _key(signing_key)
        _source(source, MAX_REVIEW_BYTES)
        _source(output, MAX_REVIEW_BYTES)
        if type(require_signed) is not bool or type(require_approved) is not bool:
            return False
        record = (
            _strict_json(receipt)
            if isinstance(receipt, str)
            else _strict_json(_canonical(receipt).decode())
        )
        if set(record) != {"payload", "digest", "signature"}:
            return False
        payload = record["payload"]
        fields = {
            "schema",
            "plan_digest",
            "source_digest",
            "output_digest",
            "policy_digest",
            "model_digest",
            "domain_digest",
            "reviewer_id",
            "approve",
            "source_complete",
            "status",
            "issues",
            "decisions",
            "created_at",
        }
        if not isinstance(payload, dict) or set(payload) != fields:
            return False
        if (
            type(payload["schema"]) is not int
            or payload["schema"] != 1
            or not all(_hex(payload[name]) for name in fields if name.endswith("digest"))
            or type(payload["approve"]) is not bool
            or type(payload["source_complete"]) is not bool
            or not isinstance(payload["reviewer_id"], str)
            or _REVIEWER.fullmatch(payload["reviewer_id"]) is None
            or type(payload["created_at"]) is not int
            or payload["created_at"] < 0
            or payload["status"] not in {str(s) for s in ReleaseStatus}
            or not isinstance(payload["issues"], list)
            or len(payload["issues"]) > 100
            or not all(
                isinstance(i, str) and re.fullmatch(r"[A-Z_]{1,80}", i) for i in payload["issues"]
            )
            or not isinstance(payload["decisions"], list)
            or len(payload["decisions"]) > MAX_SPANS * 2
        ):
            return False
        for decision in payload["decisions"]:
            ReviewDecision(**decision)
        expected = dict(
            source_digest=_hash_text(source),
            output_digest=_hash_text(output),
            policy_digest=policy.fingerprint(),
            model_digest=model_digest,
            domain_digest=_digest(domain),
        )
        if any(payload[name] != value for name, value in expected.items()):
            return False
        if require_approved and (
            payload["status"] != "APPROVED"
            or not payload["approve"]
            or not payload["source_complete"]
            or payload["issues"]
        ):
            return False
        encoded = _canonical(payload)
        if not _hex(record["digest"]) or not hmac.compare_digest(
            record["digest"], hashlib.sha256(encoded).hexdigest()
        ):
            return False
        if record["signature"] is None:
            return not require_signed
        return (
            signing_key is not None
            and _hex(record["signature"])
            and hmac.compare_digest(
                record["signature"], hmac.new(signing_key, encoded, hashlib.sha256).hexdigest()
            )
        )
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        return False


__all__ = [
    "ReviewError",
    "ReviewSpan",
    "ReviewPlan",
    "ReviewDecision",
    "ReviewedText",
    "create_review_plan",
    "apply_review",
    "verify_review_receipt",
]
