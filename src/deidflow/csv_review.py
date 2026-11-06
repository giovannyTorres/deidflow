"""Bounded, signed human review of CSV text, including every header and empty cell.

Detection is the public text-review API applied to Unicode cells. This workflow
does not infer column identities or clinical subjects from neighboring cells.
Reviewers must add omissions and explicitly attest complete source review.
Plans and receipts contain coordinates, offsets and hashes, never source values.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from deidflow.engine import DeidEngine, ReleaseStatus, Result
from deidflow.placeholders import PlaceholderAllocator
from deidflow.policies import Policy
from deidflow.review import (
    ReviewDecision,
    ReviewError,
    ReviewPlan,
    _apply_review,
    create_review_plan,
    verify_review_receipt,
)

MAX_CSV_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ROWS = 1000
MAX_COLUMNS = 64
MAX_CELLS = 10_000
MAX_FIELD_CHARACTERS = 131_072
MAX_FINDINGS = 10_000
MAX_DECISIONS = 20_000
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_REVIEWER = re.compile(r"reviewer-[0-9a-f]{16,64}\Z")
_ISSUE = re.compile(r"[A-Z_]{1,80}\Z")


class CSVReviewError(ValueError):
    """Fixed error codes without source contents, paths or third-party errors."""


def _fail(code: str = "CSV_INVALID_REVIEW_RECORD") -> NoReturn:
    raise CSVReviewError(code)


def _hex(value: Any) -> bool:
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _canonical(value: Any) -> bytes:
    pending = [(value, 0)]
    nodes = characters = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 1_000_000 or depth > 24:
            _fail("CSV_JSON_LIMIT")
        if isinstance(item, dict):
            if len(item) > 100 or not all(isinstance(key, str) for key in item):
                _fail()
            pending.extend((part, depth + 1) for pair in item.items() for part in pair)
        elif isinstance(item, (list, tuple)):
            if len(item) > MAX_DECISIONS:
                _fail("CSV_JSON_LIMIT")
            pending.extend((part, depth + 1) for part in item)
        elif isinstance(item, str):
            characters += len(item)
            if characters > MAX_JSON_BYTES:
                _fail("CSV_JSON_LIMIT")
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise CSVReviewError("CSV_INVALID_REVIEW_RECORD") from None
    if len(encoded) > MAX_JSON_BYTES:
        _fail("CSV_JSON_LIMIT")
    return encoded


def _strict_json(value: str) -> dict[str, Any]:
    if not isinstance(value, str):
        _fail()
    try:
        if len(value.encode("utf-8")) > MAX_JSON_BYTES:
            _fail("CSV_JSON_LIMIT")

        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            if len({key for key, _ in items}) != len(items):
                _fail()
            return dict(items)

        result = json.loads(value, object_pairs_hook=pairs, parse_constant=lambda _: _fail())
        if not isinstance(result, dict):
            _fail()
        _canonical(result)
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise CSVReviewError("CSV_INVALID_REVIEW_RECORD") from None


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _runtime_digest() -> str:
    # Bind the installed implementation used to construct and refresh plans.
    # Receipt verification remains historical: it checks this signed binding,
    # rather than requiring the verifier to run the same installed version.
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _strict_quotes(text: str) -> None:
    """Reject stray quotes that csv.reader(strict=True) accepts in bare fields."""
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char in ",\r\n":
                state = "start"
            else:
                _fail("CSV_MALFORMED_INPUT")
        elif char in ",\r\n":
            state = "start"
        elif char == '"':
            if state != "start":
                _fail("CSV_MALFORMED_INPUT")
            state = "quoted"
        else:
            state = "bare"
    if state == "quoted":
        _fail("CSV_MALFORMED_INPUT")


def _valid_headers(headers: list[str]) -> bool:
    return all(value.strip() for value in headers) and len(set(headers)) == len(headers)


def _parse(source: bytes, *, check_headers: bool = True) -> list[list[str]]:
    if not isinstance(source, bytes):
        _fail("CSV_INVALID_SOURCE")
    if len(source) > MAX_CSV_BYTES:
        _fail("CSV_SOURCE_LIMIT")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeError:
        raise CSVReviewError("CSV_INVALID_ENCODING") from None
    if "\x00" in text:
        _fail("CSV_MALFORMED_INPUT")
    _strict_quotes(text)
    result: list[list[str]] = []
    width = 0
    # Keep csv.field_size_limit untouched. A lower interpreter setting can reject
    # earlier; a larger one cannot extend this workflow's explicit field bound.
    try:
        reader = csv.reader(
            io.StringIO(text, newline=""), delimiter=",", quotechar='"', strict=True
        )
        for row in reader:
            if any(len(value) > MAX_FIELD_CHARACTERS for value in row):
                _fail("CSV_FIELD_LIMIT")
            if not result:
                width = len(row)
                if not 1 <= width <= MAX_COLUMNS:
                    _fail("CSV_COLUMN_LIMIT")
                if check_headers and not _valid_headers(row):
                    _fail("CSV_INVALID_HEADER")
            if len(row) != width:
                _fail("CSV_INCONSISTENT_WIDTH")
            if len(result) > MAX_ROWS or (len(result) + 1) * width > MAX_CELLS:
                _fail("CSV_SHAPE_LIMIT")
            result.append(row)
    except csv.Error:
        raise CSVReviewError("CSV_MALFORMED_INPUT") from None
    if not result:
        _fail("CSV_EMPTY_INPUT")
    return result


def _serialize(rows: list[list[str]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.writer(handle, delimiter=",", quotechar='"', lineterminator="\r\n")
    size = 0
    for row in rows:
        # Check before writing a possibly large collection of expanded cells.
        size += sum(len(value.encode("utf-8")) + value.count('"') + 3 for value in row) + 2
        if size > MAX_CSV_BYTES * 2:
            _fail("CSV_OUTPUT_LIMIT")
        writer.writerow(row)
    output = handle.getvalue().encode("utf-8")
    if len(output) > MAX_CSV_BYTES:
        _fail("CSV_OUTPUT_LIMIT")
    return output


@dataclass(frozen=True)
class CSVCellPlan:
    row: int
    column: int
    review: ReviewPlan

    def __post_init__(self) -> None:
        if (
            type(self.row) is not int
            or not 0 <= self.row <= MAX_ROWS
            or type(self.column) is not int
            or not 0 <= self.column < MAX_COLUMNS
            or not isinstance(self.review, ReviewPlan)
        ):
            _fail()


@dataclass(frozen=True)
class CSVReviewPlan:
    source_digest: str
    policy_digest: str
    model_digest: str
    domain_digest: str
    row_count: int
    column_count: int
    cells: tuple[CSVCellPlan, ...]
    rules_version: str
    runtime_digest: str
    plan_digest: str
    schema: int = 1

    def __post_init__(self) -> None:
        if (
            type(self.schema) is not int
            or self.schema != 1
            or type(self.row_count) is not int
            or not 0 <= self.row_count <= MAX_ROWS
            or type(self.column_count) is not int
            or not 1 <= self.column_count <= MAX_COLUMNS
            or not isinstance(self.cells, tuple)
            or len(self.cells) != (self.row_count + 1) * self.column_count
            or len(self.cells) > MAX_CELLS
            or not isinstance(self.rules_version, str)
            or re.fullmatch(r"rules-[0-9]+(?:\.[0-9]+){1,2}", self.rules_version) is None
            or not all(
                _hex(value)
                for value in (
                    self.source_digest,
                    self.policy_digest,
                    self.model_digest,
                    self.domain_digest,
                    self.runtime_digest,
                    self.plan_digest,
                )
            )
        ):
            _fail()
        spans = 0
        for index, cell in enumerate(self.cells):
            if not isinstance(cell, CSVCellPlan):
                _fail()
            if (cell.row, cell.column) != divmod(index, self.column_count):
                _fail()
            review = cell.review
            if (
                review.policy_digest != self.policy_digest
                or review.model_digest != self.model_digest
                or review.domain_digest != self.domain_digest
                or review.rules_version != self.rules_version
            ):
                _fail()
            spans += len(review.spans)
            if spans > MAX_FINDINGS:
                _fail("CSV_FINDING_LIMIT")
        if not hmac.compare_digest(self.plan_digest, _digest(self._payload())):
            _fail()

    def _payload(self) -> dict[str, Any]:
        return {name: value for name, value in asdict(self).items() if name != "plan_digest"}

    def to_json(self) -> str:
        return _canonical(asdict(self)).decode("ascii")

    @classmethod
    def from_json(cls, value: str) -> CSVReviewPlan:
        data = _strict_json(value)
        try:
            if set(data) != set(cls.__dataclass_fields__) or not isinstance(data["cells"], list):
                _fail()
            if len(data["cells"]) > MAX_CELLS:
                _fail("CSV_SHAPE_LIMIT")
            cells = []
            for cell in data["cells"]:
                if not isinstance(cell, dict) or set(cell) != {"row", "column", "review"}:
                    _fail()
                cells.append(
                    CSVCellPlan(
                        cell["row"],
                        cell["column"],
                        ReviewPlan.from_json(_canonical(cell["review"]).decode("ascii")),
                    )
                )
            data["cells"] = tuple(cells)
            return cls(**data)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CSVReviewError("CSV_INVALID_REVIEW_PLAN") from None


@dataclass(frozen=True)
class CSVReviewDecision:
    row: int
    column: int
    decision: ReviewDecision

    def __post_init__(self) -> None:
        if (
            type(self.row) is not int
            or not 0 <= self.row <= MAX_ROWS
            or type(self.column) is not int
            or not 0 <= self.column < MAX_COLUMNS
            or not isinstance(self.decision, ReviewDecision)
        ):
            _fail()


@dataclass(frozen=True)
class ReviewedCSV:
    result: Result
    output_bytes: bytes = field(repr=False)
    receipt: dict[str, Any]


def create_csv_review_plan(
    engine: DeidEngine,
    source: bytes,
    *,
    policy: Policy,
    model_digest: str,
    domain: str | None = None,
) -> CSVReviewPlan:
    """Plan every cell, using text detection without column/schema inference."""
    try:
        rows = _parse(source)
        cells = []
        findings = 0
        for row_index, row in enumerate(rows):
            for column_index, text in enumerate(row):
                review = create_review_plan(
                    engine, text, policy=policy, model_digest=model_digest, domain=domain
                )
                findings += len(review.spans)
                if findings > MAX_FINDINGS:
                    _fail("CSV_FINDING_LIMIT")
                cells.append(CSVCellPlan(row_index, column_index, review))
        first = cells[0].review
        payload: dict[str, Any] = dict(
            schema=1,
            source_digest=_bytes_digest(source),
            policy_digest=first.policy_digest,
            model_digest=first.model_digest,
            domain_digest=first.domain_digest,
            row_count=len(rows) - 1,
            column_count=len(rows[0]),
            cells=tuple(cells),
            rules_version=first.rules_version,
            runtime_digest=_runtime_digest(),
        )
        encoded = {**payload, "cells": [asdict(cell) for cell in cells]}
        return CSVReviewPlan(**payload, plan_digest=_digest(encoded))
    except CSVReviewError:
        raise
    except Exception:
        raise CSVReviewError("CSV_PLAN_FAILED") from None


def _decisions(
    plan: CSVReviewPlan,
    decisions: list[CSVReviewDecision],
) -> list[list[ReviewDecision]]:
    if not isinstance(decisions, list) or len(decisions) > MAX_DECISIONS:
        _fail("CSV_DECISION_LIMIT")
    grouped: list[list[ReviewDecision]] = [[] for _ in plan.cells]
    for item in decisions:
        if not isinstance(item, CSVReviewDecision):
            _fail()
        if item.row > plan.row_count or item.column >= plan.column_count:
            _fail("CSV_INVALID_DECISION")
        # Revalidate nested records even when callers pass dataclass instances.
        decision = ReviewDecision(**asdict(item.decision))
        grouped[item.row * plan.column_count + item.column].append(decision)
    for cell, chosen in zip(plan.cells, grouped, strict=True):
        ids = [d.span_id for d in chosen if d.action != "add"]
        if len(ids) != len(set(ids)) or set(ids) != {s.span_id for s in cell.review.spans}:
            _fail("CSV_DECISIONS_INCOMPLETE")
        if any(d.end is not None and d.end > cell.review.source_length for d in chosen):
            _fail("CSV_INVALID_DECISION")
    return grouped


def _aggregate(
    cells: list[dict[str, Any]],
    output_rows: list[list[str]],
) -> tuple[ReleaseStatus, list[str]]:
    issues = list(dict.fromkeys(issue for cell in cells for issue in cell["payload"]["issues"]))
    statuses = {cell["payload"]["status"] for cell in cells}
    invalid_header = not _valid_headers(output_rows[0])
    if invalid_header:
        issues.append("CSV_HEADER_INVALID")
    if invalid_header or statuses & {"BLOCKED", "UNSUPPORTED"}:
        return ReleaseStatus.BLOCKED, list(dict.fromkeys(issues))
    if "REVIEW_REQUIRED" in statuses or issues:
        return ReleaseStatus.REVIEW_REQUIRED, issues
    return ReleaseStatus.APPROVED, []


def _sign(payload: dict[str, Any], key: bytes) -> dict[str, Any]:
    encoded = _canonical(payload)
    return dict(
        payload=payload,
        digest=hashlib.sha256(encoded).hexdigest(),
        signature=hmac.new(key, encoded, hashlib.sha256).hexdigest(),
    )


def apply_csv_review(
    engine: DeidEngine,
    source: bytes,
    plan: CSVReviewPlan,
    decisions: list[CSVReviewDecision],
    *,
    policy: Policy,
    model_digest: str,
    reviewer_id: str,
    signing_key: bytes,
    approve: bool = False,
    source_complete: bool = False,
    domain: str | None = None,
) -> ReviewedCSV:
    """Recheck a complete plan, apply decisions, serialize and verify every cell.

    The shared allocator is memory-only. Both explicit human attestations and a
    signing key are required for approval; independent cell gates still apply.
    """
    try:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            _fail("CSV_INVALID_SIGNING_KEY")
        if (
            not isinstance(plan, CSVReviewPlan)
            or not isinstance(reviewer_id, str)
            or _REVIEWER.fullmatch(reviewer_id) is None
            or type(approve) is not bool
            or type(source_complete) is not bool
        ):
            _fail()
        plan = CSVReviewPlan.from_json(plan.to_json())
        fresh = create_csv_review_plan(
            engine, source, policy=policy, model_digest=model_digest, domain=domain
        )
        if fresh != plan:
            _fail("STALE_CSV_REVIEW_PLAN")
        chosen = _decisions(plan, decisions)
        source_rows = _parse(source)
        scope = engine._scope(policy, plan.plan_digest)
        allocator = PlaceholderAllocator(compatible_context=True)
        for row in source_rows:
            for source_text in row:
                allocator.reserve_source(source_text)
        output_rows = [["" for _ in row] for row in source_rows]
        cell_receipts = []
        transformations = 0
        output_size = 0
        for cell, cell_decisions in zip(plan.cells, chosen, strict=True):
            reviewed = _apply_review(
                engine,
                source_rows[cell.row][cell.column],
                cell.review,
                cell_decisions,
                policy=policy,
                model_digest=model_digest,
                reviewer_id=reviewer_id,
                signing_key=signing_key,
                approve=approve,
                source_complete=source_complete,
                domain=domain,
                placeholders=allocator,
                scope=scope,
            )
            text = reviewed.result.output_text
            if not isinstance(text, str):
                _fail("CSV_CELL_OUTPUT_MISSING")
            output_size += len(text.encode("utf-8"))
            if output_size > MAX_CSV_BYTES:
                _fail("CSV_OUTPUT_LIMIT")
            output_rows[cell.row][cell.column] = text
            transformations += len(reviewed.result.mappings)
            cell_receipts.append(reviewed.receipt)
        output = _serialize(output_rows)
        reread = _parse(output, check_headers=False)
        if reread != output_rows:
            _fail("CSV_SERIALIZATION_MISMATCH")
        for cell, receipt in zip(plan.cells, cell_receipts, strict=True):
            if not verify_review_receipt(
                receipt,
                source=source_rows[cell.row][cell.column],
                output=reread[cell.row][cell.column],
                policy=policy,
                model_digest=model_digest,
                signing_key=signing_key,
                domain=domain,
                require_approved=False,
            ):
                _fail("CSV_CELL_VERIFICATION_FAILED")
        status, issues = _aggregate(cell_receipts, reread)
        result = Result(
            status,
            issues=issues,
            records=plan.row_count,
            audit=dict(
                verification="signed_csv_human_review_and_serialized_cell_reread",
                sha256=_bytes_digest(output),
                review_plan=plan.plan_digest,
                transformations=transformations,
                rows=plan.row_count,
                columns=plan.column_count,
            ),
        )
        payload = dict(
            schema=1,
            source_digest=plan.source_digest,
            output_digest=_bytes_digest(output),
            plan_digest=plan.plan_digest,
            plan=json.loads(plan.to_json()),
            policy_digest=plan.policy_digest,
            model_digest=plan.model_digest,
            domain_digest=plan.domain_digest,
            rules_version=plan.rules_version,
            runtime_digest=plan.runtime_digest,
            row_count=plan.row_count,
            column_count=plan.column_count,
            reviewer_id=reviewer_id,
            approve=approve,
            source_complete=source_complete,
            status=str(status),
            issues=issues,
            decisions=[asdict(d) for d in decisions],
            cells=cell_receipts,
            created_at=int(time.time()),
        )
        receipt = _sign(payload, signing_key)
        # Bind the envelope too, including its signature/digest overhead.
        _canonical(receipt)
        return ReviewedCSV(result, output, receipt)
    except CSVReviewError:
        raise
    except ReviewError:
        raise CSVReviewError("CSV_CELL_REVIEW_FAILED") from None
    except Exception:
        raise CSVReviewError("CSV_REVIEW_FAILED") from None


def verify_csv_review_receipt(
    receipt: dict[str, Any] | str,
    *,
    source: bytes,
    output: bytes,
    policy: Policy,
    model_digest: str,
    signing_key: bytes,
    domain: str | None = None,
    require_approved: bool = True,
) -> bool:
    """Authenticate exact CSV bytes, plan, coordinate decisions and all cell receipts.

    Preview or blocked receipts are inspectable with require_approved=False; that
    flag never changes their signed status or authorizes publication.
    """
    try:
        if (
            not isinstance(signing_key, bytes)
            or len(signing_key) < 32
            or type(require_approved) is not bool
            or not isinstance(policy, Policy)
            or not _hex(model_digest)
        ):
            return False
        record = _strict_json(receipt if isinstance(receipt, str) else _canonical(receipt).decode())
        if set(record) != {"payload", "digest", "signature"}:
            return False
        payload = record["payload"]
        fields = {
            "schema",
            "source_digest",
            "output_digest",
            "plan_digest",
            "plan",
            "policy_digest",
            "model_digest",
            "domain_digest",
            "rules_version",
            "runtime_digest",
            "row_count",
            "column_count",
            "reviewer_id",
            "approve",
            "source_complete",
            "status",
            "issues",
            "decisions",
            "cells",
            "created_at",
        }
        if not isinstance(payload, dict) or set(payload) != fields:
            return False
        if (
            type(payload["schema"]) is not int
            or payload["schema"] != 1
            or type(payload["approve"]) is not bool
            or type(payload["source_complete"]) is not bool
            or not isinstance(payload["reviewer_id"], str)
            or _REVIEWER.fullmatch(payload["reviewer_id"]) is None
            or type(payload["created_at"]) is not int
            or payload["created_at"] < 0
            or type(payload["row_count"]) is not int
            or not 0 <= payload["row_count"] <= MAX_ROWS
            or type(payload["column_count"]) is not int
            or not 1 <= payload["column_count"] <= MAX_COLUMNS
            or payload["status"] not in {str(status) for status in ReleaseStatus}
            or not isinstance(payload["issues"], list)
            or len(payload["issues"]) > 100
            or not all(
                isinstance(issue, str) and _ISSUE.fullmatch(issue) for issue in payload["issues"]
            )
            or not isinstance(payload["cells"], list)
            or len(payload["cells"]) > MAX_CELLS
            or not isinstance(payload["decisions"], list)
            or len(payload["decisions"]) > MAX_DECISIONS
        ):
            return False
        encoded = _canonical(payload)
        if (
            not _hex(record["digest"])
            or not _hex(record["signature"])
            or not hmac.compare_digest(record["digest"], hashlib.sha256(encoded).hexdigest())
            or not hmac.compare_digest(
                record["signature"], hmac.new(signing_key, encoded, hashlib.sha256).hexdigest()
            )
        ):
            return False
        plan = CSVReviewPlan.from_json(_canonical(payload["plan"]).decode())
        expected = dict(
            source_digest=_bytes_digest(source),
            output_digest=_bytes_digest(output),
            policy_digest=policy.fingerprint(),
            model_digest=model_digest,
            domain_digest=_digest(domain),
            rules_version=plan.rules_version,
            runtime_digest=plan.runtime_digest,
            plan_digest=plan.plan_digest,
            row_count=plan.row_count,
            column_count=plan.column_count,
        )
        if any(payload[name] != value for name, value in expected.items()):
            return False
        if (
            plan.source_digest != expected["source_digest"]
            or plan.policy_digest != expected["policy_digest"]
            or plan.model_digest != model_digest
            or plan.domain_digest != expected["domain_digest"]
        ):
            return False
        decisions = []
        for item in payload["decisions"]:
            if not isinstance(item, dict) or set(item) != {"row", "column", "decision"}:
                return False
            decisions.append(
                CSVReviewDecision(item["row"], item["column"], ReviewDecision(**item["decision"]))
            )
        chosen = _decisions(plan, decisions)
        source_rows, output_rows = _parse(source), _parse(output, check_headers=False)
        shape = (plan.row_count + 1, plan.column_count)
        if (
            (len(source_rows), len(source_rows[0])) != shape
            or (len(output_rows), len(output_rows[0])) != shape
            or len(payload["cells"]) != len(plan.cells)
        ):
            return False
        for cell, cell_decisions, cell_receipt in zip(
            plan.cells, chosen, payload["cells"], strict=True
        ):
            original, transformed = (
                source_rows[cell.row][cell.column],
                output_rows[cell.row][cell.column],
            )
            if not verify_review_receipt(
                cell_receipt,
                source=original,
                output=transformed,
                policy=policy,
                model_digest=model_digest,
                signing_key=signing_key,
                domain=domain,
                require_approved=False,
            ):
                return False
            cell_payload = cell_receipt["payload"]
            if (
                cell_payload["plan_digest"] != cell.review.plan_digest
                or cell.review.source_digest != hashlib.sha256(original.encode()).hexdigest()
                or cell.review.source_length != len(original)
                or cell_payload["decisions"] != [asdict(d) for d in cell_decisions]
                or any(
                    cell_payload[name] != payload[name]
                    for name in (
                        "reviewer_id",
                        "approve",
                        "source_complete",
                    )
                )
            ):
                return False
        status, issues = _aggregate(payload["cells"], output_rows)
        if payload["status"] != str(status) or payload["issues"] != issues:
            return False
        return not require_approved or (
            status == ReleaseStatus.APPROVED
            and payload["approve"]
            and payload["source_complete"]
            and not issues
        )
    except Exception:
        return False


__all__ = [
    "CSVReviewError",
    "CSVCellPlan",
    "CSVReviewPlan",
    "CSVReviewDecision",
    "ReviewedCSV",
    "create_csv_review_plan",
    "apply_csv_review",
    "verify_csv_review_receipt",
]
