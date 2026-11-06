"""Local orchestration, bounded batches and fail-closed artifact verification."""

from __future__ import annotations

import contextvars
import csv
import hashlib
import itertools
import json
import os
import secrets
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from deidflow.core import DocumentGraph, Finding
from deidflow.detectors import RuleDetector, fuse
from deidflow.placeholders import PLACEHOLDER, PlaceholderAllocator, canonical_placeholder
from deidflow.policies import Policy
from deidflow.structured import dataframe_columns, profile_column, profile_table, scan_cell
from deidflow.transformations import (
    SAFE_REPLACEMENT_ACTIONS,
    IncompleteTransformationError,
    SourceMap,
    replacement_only,
    transform_text,
)
from deidflow.verification import residual_proper_nouns

# Set while an e-mail is rewritten, so its attachments share one pseudonym scope and
# one indexed-placeholder allocator with the message (distinct people never share
# an index, and the same person keeps it across body and attachments).
_SHARED_DOCUMENT: contextvars.ContextVar[tuple[str, PlaceholderAllocator, str] | None] = (
    contextvars.ContextVar("deidflow_shared_document", default=None)
)


class ReleaseStatus(StrEnum):
    APPROVED = "APPROVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class Result:
    status: ReleaseStatus
    output_path: Path | None = None
    output_text: str | None = field(default=None, repr=False)
    dataframe: Any = field(default=None, repr=False)
    findings: list[Finding] = field(default_factory=list, repr=False)
    mappings: list[SourceMap] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    records: int = 0
    audit: dict[str, Any] = field(default_factory=dict)
    safe_jsonl: Path | None = field(default=None, repr=False)
    audit_path: Path | None = field(default=None, repr=False)

    @property
    def release_approved(self) -> bool:
        return self.status == ReleaseStatus.APPROVED

    @property
    def safe_pdf(self) -> Path | None:
        return (
            self.output_path
            if self.output_path and self.output_path.suffix.lower() == ".pdf"
            else None
        )

    def audit_dict(self) -> dict[str, Any]:
        """No filenames, source values, headers or locations are included in audit logs."""
        return {
            "status": str(self.status),
            "records": self.records,
            "issues": self.issues,
            **self.audit,
        }


def _rules_batch_worker(
    texts: list[str], countries: frozenset[str] | None = None
) -> list[list[Finding]]:
    detector = RuleDetector(countries=countries)
    return [detector.detect(text) for text in texts]


def _countries(country: str | Iterable[str]) -> frozenset[str] | None:
    """``"ALL"`` (every supported country) or ISO codes such as ``"MX"`` or ``"ES,AR"``."""
    codes = [country] if isinstance(country, str) else list(country)
    names = {part.strip().upper() for code in codes for part in str(code).split(",")}
    names.discard("")
    if not names:
        raise ValueError("At least one country code is required")
    if "ALL" in names:
        return None
    return frozenset(names)


def _source_review_issues(findings: Iterable[Finding], policy: Policy) -> list[str]:
    """Retain source uncertainty without keeping sensitive spans across batches."""
    uncertain = boundary = False
    for finding in findings:
        uncertain |= finding.score < policy.review_below
        boundary |= "window_boundary" in finding.context
        if uncertain and boundary:
            break
    issues = []
    if uncertain:
        issues.append("UNCERTAIN_SOURCE_FINDINGS")
    if boundary:
        issues.append("UNRESOLVED_MODEL_WINDOW_BOUNDARY")
    return issues


def _json_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in items}) != len(items):
        raise ValueError("Duplicate JSON keys are unsupported")
    return dict(items)


def _reject_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON numbers are unsupported")


def _batches(values: Iterable[Any], size: int) -> Iterator[list[Any]]:
    iterator = iter(values)
    while batch := list(itertools.islice(iterator, size)):
        yield batch


class DeidEngine:
    def __init__(
        self,
        *,
        language: str = "es",
        country: str | Iterable[str] = "ALL",
        performance: str = "balanced",
        offline: bool = True,
        nlp: Any = None,
        recognizers: Iterable[Any] = (),
        key: bytes | None = None,
        tenant_id: str | None = None,
        dataset_id: str | None = None,
        max_bytes: int = 64 * 1024 * 1024,
        memory_budget_mb: int = 256,
        ocr: Any = None,
        custom_transforms: dict[str, Callable[[str], str]] | None = None,
        schema_fast_path: bool = True,
        pdf_dpi: int = 216,
        pdf_max_pages: int = 1000,
        pdf_workers: int = 1,
        pdf_profile: bool = False,
    ) -> None:
        if language != "es":
            raise ValueError("Only Spanish-language detection is implemented")
        self.countries = _countries(country)
        if offline is not True:
            raise ValueError("DeidFlow supports only local offline inference")
        if performance not in {"fast", "balanced", "assurance"}:
            raise ValueError("Unknown performance profile")
        if max_bytes < 1 or memory_budget_mb < 8:
            raise ValueError("Invalid resource budget")
        if (
            type(pdf_dpi) is not int
            or not 72 <= pdf_dpi <= 600
            or type(pdf_max_pages) is not int
            or not 1 <= pdf_max_pages <= 1000
        ):
            raise ValueError("Invalid PDF rasterization limits")
        if key is not None and (not isinstance(key, bytes) or len(key) < 32):
            raise ValueError("Secret key must contain at least 32 bytes")
        self.detector = RuleDetector(recognizers=recognizers, countries=self.countries)
        self.nlp, self.ocr, self.performance = nlp, ocr, performance
        self.key, self.tenant_id, self.dataset_id = key, tenant_id, dataset_id
        self.max_bytes, self.memory_budget_mb = max_bytes, memory_budget_mb
        self.schema_fast_path = schema_fast_path
        self.pdf_dpi, self.pdf_max_pages = pdf_dpi, pdf_max_pages
        if (
            type(pdf_workers) is not int
            or not 1 <= pdf_workers <= 8
            or type(pdf_profile) is not bool
        ):
            raise ValueError("Invalid PDF concurrency or profiling configuration")
        self.pdf_workers, self.pdf_profile = pdf_workers, pdf_profile
        self.custom_transforms = custom_transforms or {}
        self.session_id = secrets.token_hex(16)
        self._nlp_lock = threading.Lock()

    def scan_text(self, text: str) -> list[Finding]:
        return self.scan_texts([text])[0]

    def scan_ocr_text(self, text: str) -> list[Finding]:
        """Add uncertain field candidates while retaining the original OCR text."""
        from deidflow.detectors.ocr import ocr_field_candidates

        findings = self.scan_text(text)
        from deidflow.performance import ACTIVE_PROFILER

        profiler = ACTIVE_PROFILER.get()
        with profiler.stage("context") if profiler else nullcontext():
            return fuse(findings + ocr_field_candidates(text, findings))

    def scan_texts(self, texts: list[str]) -> list[list[Finding]]:
        if any(not isinstance(t, str) for t in texts):
            raise TypeError("Text input must be Unicode strings")
        if any(len(t.encode("utf-8", errors="surrogatepass")) > self.max_bytes for t in texts):
            raise ValueError("Text exceeds configured size limit")
        if sum(len(t) for t in texts) * 4 > self.memory_budget_mb * 1024**2 // 2:
            raise ValueError("Text batch exceeds configured memory budget")
        from deidflow.performance import ACTIVE_PROFILER

        profiler = ACTIVE_PROFILER.get()
        try:
            with profiler.stage("rules") if profiler else nullcontext():
                results = [self.detector.detect(t) for t in texts]
        except Exception:
            raise RuntimeError("Local rule recognizer failed; output is not verified") from None
        if self.nlp is not None and texts:
            try:
                with self._nlp_lock, profiler.stage("nlp") if profiler else nullcontext():
                    predicted = self.nlp.detect_batch(texts)
            except Exception:
                raise RuntimeError("Local NLP adapter failed; output is not verified") from None
            if len(predicted) != len(texts):
                raise ValueError("NLP adapter returned an invalid batch length")
            for i, items in enumerate(predicted):
                if any(not 0 <= f.start < f.end <= len(texts[i]) for f in items):
                    raise ValueError("NLP adapter returned invalid offsets")
                results[i] = fuse(results[i] + items)
        return results

    def _rescan_texts(
        self, texts: list[str], placeholders: PlaceholderAllocator | None = None
    ) -> list[list[Finding]]:
        """Ignore known replacements, plus indexed tokens issued for this document."""
        issued = placeholders.issued() if placeholders is not None else {}
        result = []
        for text, items in zip(texts, self.scan_texts(texts), strict=True):
            ranges = [
                match.span()
                for match in PLACEHOLDER.finditer(text)
                if canonical_placeholder(
                    match.group("label") or match.group("bare_label"),
                    match.group("index") or match.group("bare_index"),
                )
                in issued
            ]
            result.append(
                [
                    finding
                    for finding in items
                    if not replacement_only(text, finding.start, finding.end)
                    and not (
                        ranges and replacement_only(text, finding.start, finding.end, ranges=ranges)
                    )
                ]
            )
        return result

    def read(self, source: str | Path) -> DocumentGraph:
        from deidflow.readers import read_document

        return read_document(
            source, max_bytes=self.max_bytes, ocr=self.ocr, performance=self.performance
        )

    def scan(self, source: str | Path) -> list[Finding]:
        if Path(source).suffix.lower() in {".csv", ".tsv"}:
            return list(self.scan_csv(source))
        graph = self.read(source)
        if not graph.complete:
            # Returning findings alone would hide unscanned regions from an API consumer.
            from deidflow.readers import DocumentError

            raise DocumentError("Incomplete document coverage; inspect engine.read().issues")
        findings: list[Finding] = []
        for batch in _batches(graph.fragments, 32):
            for fragment, items in zip(
                batch, self.scan_texts([f.text for f in batch]), strict=True
            ):
                if fragment.kind == "ocr":
                    from deidflow.detectors.ocr import ocr_field_candidates

                    items = fuse(items + ocr_field_candidates(fragment.text, items))
                findings.extend(replace(f, location=fragment.location) for f in items)
        return findings

    def scan_many(
        self,
        sources: Iterable[str | Path],
        *,
        input_kind: str = "path",
        workers: int = 1,
        batch_size: int = 32,
        ordered: bool = True,
    ) -> Iterator[list[Finding]]:
        if not 1 <= workers <= 32 or batch_size < 1 or input_kind not in {"path", "text"}:
            raise ValueError("Invalid batch configuration")
        if not ordered:
            raise ValueError("Only deterministic output order is currently supported")
        if workers > 1 and (
            input_kind != "text" or self.nlp is not None or self.detector.recognizers
        ):
            raise ValueError(
                "Multiprocessing supports built-in text rules only; use one worker for adapters"
            )
        if workers == 1:
            for batch in _batches(sources, batch_size):
                if input_kind == "text":
                    yield from self.scan_texts([str(x) for x in batch])
                else:
                    yield from (self.scan(x) for x in batch)
            return
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for batch in _batches(sources, min(batch_size, workers * 256)):
                texts = [str(x) for x in batch]
                if (
                    sum(len(t.encode("utf-8", errors="surrogatepass")) for t in texts)
                    > self.memory_budget_mb * 1024**2 // 2
                ):
                    raise ValueError("Parallel batch exceeds memory budget")
                if any(
                    len(t.encode("utf-8", errors="surrogatepass")) > self.max_bytes for t in texts
                ):
                    raise ValueError("Text exceeds configured size limit")
                task_size = min(64, max(1, len(texts) // workers))
                tasks = list(_batches(texts, task_size))
                for results in pool.map(
                    _rules_batch_worker, tasks, [self.countries] * len(tasks), chunksize=1
                ):
                    yield from results

    def _document(self, policy: Policy) -> tuple[str, PlaceholderAllocator, str]:
        """(scope, allocator, document id) for one output file, shared inside an e-mail."""
        shared = _SHARED_DOCUMENT.get()
        if shared is not None:
            return shared
        document_id = secrets.token_hex(16)
        return self._scope(policy, document_id), PlaceholderAllocator(), document_id

    def _scope(self, policy: Policy, document_id: str) -> str:
        if policy.token_scope == "tenant":
            if not self.tenant_id:
                raise ValueError("Tenant token scope requires tenant_id")
            return json.dumps(["tenant", self.tenant_id], ensure_ascii=True)
        if policy.token_scope == "dataset":
            if not self.dataset_id:
                raise ValueError("Dataset token scope requires dataset_id")
            return json.dumps(["dataset", self.tenant_id, self.dataset_id], ensure_ascii=True)
        if policy.token_scope == "session":
            return json.dumps(["session", self.tenant_id, self.session_id], ensure_ascii=True)
        return json.dumps(["document", self.tenant_id, document_id], ensure_ascii=True)

    def _gate(
        self,
        *,
        policy: Policy,
        residual: list[Finding],
        original: list[Finding] | None = None,
        complete: bool = True,
        issues: list[str] | None = None,
        domain: str | None = None,
        independent_check_checked: bool = False,
    ) -> Result:
        problems = list(issues or [])
        if policy.independent_check != "none" and not independent_check_checked:
            problems.append("INDEPENDENT_CHECK_REQUIRES_REVIEW")
        if not complete:
            problems.append("INCOMPLETE_COVERAGE")
        remaining = [
            f
            for f in residual
            if policy.rule(f.entity_type, domain).action != "keep"
            and f.entity_type not in policy.allow_residual_types
        ]
        if remaining:
            problems.append("RESIDUAL_FINDINGS")
        blocked = bool(remaining) or not complete
        if policy.require_ner and self.nlp is None:
            problems.append("SEMANTIC_MODEL_REQUIRED")
        problems.extend(_source_review_issues(original or [], policy))
        if any("window_boundary" in f.context for f in residual):
            problems.append("UNRESOLVED_MODEL_WINDOW_BOUNDARY")
        status = (
            ReleaseStatus.BLOCKED
            if blocked
            else ReleaseStatus.REVIEW_REQUIRED
            if problems
            else ReleaseStatus.APPROVED
        )
        return Result(
            status,
            findings=residual,
            issues=list(dict.fromkeys(problems)),
            audit={
                "verification": "reread_and_rescan",
                "model": "rules+adapter" if self.nlp else "rules_only",
                "policy": policy.name,
                "policy_sha256": policy.fingerprint(),
                "domain": domain,
                "anonymity_proven": False,
            },
        )

    def deidentify_text(
        self,
        text: str,
        *,
        policy: Policy | None = None,
        document_id: str | None = None,
        domain: str | None = None,
        placeholders: PlaceholderAllocator | None = None,
    ) -> Result:
        policy = policy or Policy.strict()
        findings = self.scan_text(text)
        scope = self._scope(policy, document_id or secrets.token_hex(16))
        try:
            transformed, mappings = transform_text(
                text,
                findings,
                policy,
                key=self.key,
                scope=scope,
                domain=domain,
                custom=self.custom_transforms,
                placeholders=placeholders,
            )
        except IncompleteTransformationError:
            return Result(ReleaseStatus.BLOCKED, issues=["INCOMPLETE_TRANSFORMATION"])
        rescanned = self.scan_text(transformed)
        applied = [
            (m.output_start, m.output_end)
            for m in mappings
            if m.action in SAFE_REPLACEMENT_ACTIONS and m.output_end > m.output_start
        ]
        residual = [
            f
            for f in rescanned
            if not replacement_only(transformed, f.start, f.end, ranges=applied)
        ]
        checks = []
        if policy.independent_check == "proper_nouns" and residual_proper_nouns(
            transformed, applied
        ):
            checks.append("POSSIBLE_RESIDUAL_PROPER_NOUN")
        result = self._gate(
            policy=policy,
            residual=residual,
            original=findings,
            domain=domain,
            issues=checks,
            independent_check_checked=True,
        )
        result.audit["replacement_only_rescan_findings"] = len(rescanned) - len(residual)
        result.output_text, result.mappings, result.records = transformed, mappings, 1
        result.audit["transformations"] = len(mappings)
        result.audit["sha256"] = hashlib.sha256(
            transformed.encode("utf-8", errors="surrogatepass")
        ).hexdigest()
        return result

    def verify(
        self,
        source: str | Path,
        *,
        policy: Policy | None = None,
        expected_sha256: str | None = None,
        domain: str | None = None,
        _placeholders: PlaceholderAllocator | None = None,
    ) -> Result:
        path = Path(source)
        policy = policy or (
            Policy.strict_pdf() if path.suffix.lower() == ".pdf" else Policy.strict()
        )
        if expected_sha256:
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != expected_sha256:
                return Result(ReleaseStatus.BLOCKED, issues=["OUTPUT_DIGEST_MISMATCH"])
        if path.suffix.lower() == ".pdf":
            from deidflow.redactors.pdf import verify_pdf

            return verify_pdf(path, engine=self, policy=policy, dpi=self.pdf_dpi, domain=domain)
        if path.suffix.lower() in {".csv", ".tsv", ".jsonl", ".json"}:
            return self._verify_stream(path, policy, domain)
        graph = self.read(source)
        findings: list[Finding] = []
        for batch in _batches(graph.fragments, 32):
            findings.extend(
                f
                for items in self._rescan_texts([x.text for x in batch], _placeholders)
                for f in items
            )
        result = self._gate(
            policy=policy,
            residual=findings,
            complete=graph.complete,
            issues=graph.issues,
            domain=domain,
        )
        result.output_path = path
        return result

    def _verify_stream(
        self,
        path: Path,
        policy: Policy,
        domain: str | None,
        *,
        transformed: bool = False,
        placeholders: PlaceholderAllocator | None = None,
    ) -> Result:
        findings: list[Finding] = []
        issues: list[str] = []
        records = 0

        def scalars(value: Any, header: str = "") -> Iterator[str]:
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from scalars(item, key)
            elif isinstance(value, list):
                for item in value:
                    yield from scalars(item, header)
            elif value is not None and not isinstance(value, bool):
                profile = profile_column(header, [], self.detector)
                if (
                    not transformed
                    and profile.entity_type
                    and policy.rule(profile.entity_type, domain).action != "keep"
                ):
                    if not issues:
                        issues.append("SCHEMA_TRANSFORMATION_RECEIPT_REQUIRED")
                yield str(value)

        def consume(values: Iterable[str]) -> None:
            for cells in _batches(values, 128):
                for items in self._rescan_texts(cells, placeholders):
                    for f in items:
                        if (
                            len(findings) < 100
                            and policy.rule(f.entity_type, domain).action != "keep"
                            and f.entity_type not in policy.allow_residual_types
                        ):
                            findings.append(f)

        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                if path.suffix.lower() == ".json":
                    if path.stat().st_size > self.max_bytes:
                        return Result(ReleaseStatus.BLOCKED, issues=["RECORD_SIZE_EXCEEDED"])
                    consume(
                        scalars(
                            json.load(
                                handle,
                                object_pairs_hook=_json_pairs,
                                parse_constant=_reject_constant,
                            )
                        )
                    )
                    records = 1
                elif path.suffix.lower() == ".jsonl":
                    while line := handle.readline(self.max_bytes + 1):
                        if len(line.encode("utf-8")) > self.max_bytes:
                            return Result(ReleaseStatus.BLOCKED, issues=["RECORD_SIZE_EXCEEDED"])
                        consume(
                            scalars(
                                json.loads(
                                    line,
                                    object_pairs_hook=_json_pairs,
                                    parse_constant=_reject_constant,
                                )
                            )
                        )
                        records += 1
                else:
                    reader = csv.reader(
                        handle, delimiter="\t" if path.suffix.lower() == ".tsv" else ","
                    )
                    headers = next(reader, [])
                    consume(headers)
                    profiles = [profile_column(h, [], self.detector) for h in headers]
                    for row in reader:
                        if len(row) != len(headers):
                            return Result(ReleaseStatus.BLOCKED, issues=["SCHEMA_MISMATCH"])
                        consume(row)
                        if not transformed and any(
                            v
                            and p.entity_type
                            and policy.rule(p.entity_type, domain).action != "keep"
                            for v, p in zip(row, profiles, strict=True)
                        ):
                            if not issues:
                                issues.append("SCHEMA_TRANSFORMATION_RECEIPT_REQUIRED")
                        records += 1
        except (UnicodeError, csv.Error, json.JSONDecodeError, RecursionError):
            return Result(ReleaseStatus.BLOCKED, issues=["MALFORMED_INPUT"])
        result = self._gate(policy=policy, residual=findings, domain=domain, issues=issues)
        result.records, result.output_path = records, path
        return result

    def _rows(
        self,
        headers: list[str],
        rows: list[list[Any]],
        policy: Policy,
        scope: str,
        domain: str | None = None,
        placeholders: PlaceholderAllocator | None = None,
    ) -> tuple[list[list[Any]], list[str], int]:
        placeholders = placeholders if placeholders is not None else PlaceholderAllocator()
        if len(set(headers)) != len(headers):
            raise ValueError("Duplicate column names are unsupported")
        if any(len(row) != len(headers) for row in rows):
            raise ValueError("Inconsistent table row width")
        if sum(len(str(v)) for row in rows for v in row) * 4 > self.memory_budget_mb * 1024**2 // 2:
            raise ValueError("Table batch exceeds memory budget")
        profiles = profile_table(headers, rows, self.detector)
        issues = (
            ["UNKNOWN_IDENTIFIER_CANDIDATE"] if any(p.unknown_identifier for p in profiles) else []
        )
        out = [list(row) for row in rows]
        # Every nonempty value in recognized columns is transformed in full. Statistical
        # inference is batched once across the remaining fields, never once per cell.
        pending: list[tuple[int, int, str]] = []
        count = 0
        for j, profile in enumerate(profiles):
            rule = policy.rule(profile.entity_type or "", domain)
            whole = (
                self.schema_fast_path
                and profile.entity_type is not None
                and rule.action
                in {"redact", "suppress", "placeholder", "indexed", "pseudonym", "generalize"}
            )
            for i, row in enumerate(rows):
                value = row[j]
                if value is None or value == "":
                    continue
                text = str(value)
                if whole:
                    finding = Finding(
                        profile.entity_type or "CONFIDENTIAL",
                        0,
                        len(text),
                        profile.score,
                        "schema.column",
                        protected=True,
                    )
                    transformed, mappings = transform_text(
                        text,
                        [finding],
                        policy,
                        key=self.key,
                        scope=scope,
                        domain=domain,
                        custom=self.custom_transforms,
                        placeholders=placeholders,
                    )
                    out[i][j] = None if rule.action == "suppress" else transformed
                    issues.extend(_source_review_issues([finding], policy))
                    count += len(mappings)
                else:
                    pending.append((i, j, text))
        for batch in _batches(pending, 128):
            for (i, j, text), findings in zip(
                batch, self.scan_texts([x[2] for x in batch]), strict=True
            ):
                if profiles[j].entity_type:
                    findings = fuse(
                        findings
                        + scan_cell(
                            rows[i][j], profiles[j], self.detector, row=i, column=headers[j]
                        )
                    )
                transformed, mappings = transform_text(
                    text,
                    findings,
                    policy,
                    key=self.key,
                    scope=scope,
                    domain=domain,
                    custom=self.custom_transforms,
                    placeholders=placeholders,
                )
                if mappings:
                    out[i][j] = transformed
                issues.extend(_source_review_issues(findings, policy))
                count += len(mappings)
        return out, list(dict.fromkeys(issues)), count

    def profile(self, source: Any, *, sample_size: int = 128) -> list[Any]:
        if sample_size < 1:
            raise ValueError("Sample size must be positive")
        if isinstance(source, (str, Path)):
            with Path(source).open(encoding="utf-8", newline="") as handle:
                reader = csv.reader(
                    handle, delimiter="\t" if Path(source).suffix.lower() == ".tsv" else ","
                )
                headers = next(reader, [])
                rows = list(itertools.islice(reader, sample_size))
            if any(len(r) != len(headers) for r in rows):
                raise ValueError("Inconsistent table row width")
            return profile_table(headers, rows, self.detector)
        headers, columns, _ = dataframe_columns(source.head(sample_size))
        return profile_table(
            headers,
            [list(r) for r in zip(*(columns[h][:sample_size] for h in headers), strict=True)],
            self.detector,
        )

    def scan_dataframe(self, frame: Any) -> list[Finding]:
        headers, columns, _ = dataframe_columns(frame)
        profiles = self.profile(frame)
        results = []
        pending = []
        for j, h in enumerate(headers):
            for i, value in enumerate(columns[h]):
                if value is not None and value != "":
                    results.extend(scan_cell(value, profiles[j], self.detector, row=i, column=h))
                    if not profiles[j].entity_type:
                        pending.append((i, h, str(value)))
        if self.nlp is not None:
            for batch in _batches(pending, 128):
                from deidflow.core import SourceLocation

                for (i, h, _), findings in zip(
                    batch, self.scan_texts([x[2] for x in batch]), strict=True
                ):
                    results.extend(
                        replace(f, location=SourceLocation(row=i, column=h)) for f in findings
                    )
        from deidflow.core import SourceLocation

        for column in headers:
            results.extend(
                replace(f, location=SourceLocation(part="dataframe.schema", column=column))
                for f in self.scan_text(column)
            )
        if type(frame).__module__.split(".")[0] == "pandas":
            for i, value in enumerate(frame.index):
                results.extend(
                    replace(f, location=SourceLocation(part="dataframe.index", row=i))
                    for f in self.scan_text(str(value))
                )
        return results

    def scan_csv(self, source: str | Path, *, batch_size: int = 1024) -> Iterator[Finding]:
        """Streaming locations; use this instead of collecting a million-row finding list."""
        if batch_size < 1:
            raise ValueError("Batch size must be positive")
        path = Path(source)
        offset = 0
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t" if path.suffix.lower() == ".tsv" else ",")
            headers = next(reader, [])
            if len(set(headers)) != len(headers):
                raise ValueError("Duplicate column names are unsupported")
            for batch in _batches(reader, batch_size):
                if any(len(r) != len(headers) for r in batch):
                    raise ValueError("Inconsistent table row width")
                if sum(len(v) for r in batch for v in r) * 4 > self.memory_budget_mb * 1024**2 // 2:
                    raise ValueError("Table batch exceeds memory budget")
                profiles = profile_table(headers, batch, self.detector)
                pending = []
                for i, row in enumerate(batch):
                    for j, value in enumerate(row):
                        yield from scan_cell(
                            value, profiles[j], self.detector, row=offset + i, column=headers[j]
                        )
                        if self.nlp is not None and not profiles[j].entity_type and value:
                            pending.append((offset + i, j, value))
                if pending:
                    from deidflow.core import SourceLocation

                    for cells in _batches(pending, 128):
                        for (i, j, _), found in zip(
                            cells, self.scan_texts([v for _, _, v in cells]), strict=True
                        ):
                            yield from (
                                replace(f, location=SourceLocation(row=i, column=headers[j]))
                                for f in found
                                if f.detector != "rules.es_MX"
                            )
                offset += len(batch)

    def deidentify_dataframe(
        self,
        frame: Any,
        *,
        policy: Policy | None = None,
        domain: str | None = None,
        batch_size: int = 1024,
    ) -> Result:
        policy = policy or Policy.strict()
        headers, columns, module = dataframe_columns(frame)
        if batch_size < 1:
            raise ValueError("Batch size must be positive")
        rows = zip(*(columns[h] for h in headers), strict=True)
        transformed, issues, count = [], [], 0
        scope, allocator, _ = self._document(policy)
        for header in headers:
            allocator.reserve_source(header)
        if module == "pandas":
            for value in itertools.chain(frame.index, frame.index.names):
                if value is not None:
                    allocator.reserve_source(str(value))
        for batch in _batches(rows, batch_size):
            output, problems, n = self._rows(
                headers, [list(r) for r in batch], policy, scope, domain, allocator
            )
            transformed.extend(output)
            issues.extend(problems)
            count += n
        if module == "pandas":
            import pandas as pd

            output_frame = pd.DataFrame(transformed, columns=headers, index=frame.index)
            for column in headers:
                try:
                    casted = output_frame[column].astype(frame[column].dtype)
                    before = (
                        output_frame[column]
                        .astype(object)
                        .where(output_frame[column].notna(), None)
                        .tolist()
                    )
                    after = casted.astype(object).where(casted.notna(), None).tolist()
                    if before == after:
                        output_frame[column] = casted
                except (ValueError, TypeError):
                    pass  # A changed dtype is recorded, never an unchecked cast.
        else:
            import polars as pl

            output_frame = pl.DataFrame(transformed, schema=headers, orient="row", strict=False)
        residual: list[Finding] = []
        for cells in _batches((str(v) for row in transformed for v in row if v is not None), 128):
            residual.extend(f for items in self._rescan_texts(cells, allocator) for f in items)
        # Headers and pandas indices may themselves disclose identities.
        metadata = list(headers)
        if module == "pandas":
            metadata.extend(str(v) for v in frame.index)
            metadata.extend(str(v) for v in frame.index.names if v is not None)
        if any(self.scan_text(x) for x in metadata):
            issues.append("SENSITIVE_SCHEMA_OR_INDEX")
        result = self._gate(policy=policy, residual=residual, issues=issues, domain=domain)
        result.dataframe, result.records = output_frame, len(transformed)
        result.audit["transformations"] = count
        result.audit["schema_changed"] = str(frame.dtypes) != str(output_frame.dtypes)
        return result

    def _csv(
        self, source: Path, output: Path, policy: Policy, batch_size: int, domain: str | None
    ) -> Result:
        delimiter = "\t" if source.suffix.lower() == ".tsv" else ","
        scope, allocator, _ = self._document(policy)
        records, count, issues = 0, 0, []
        with (
            source.open(encoding="utf-8-sig", newline="") as inp,
            output.open("w", encoding="utf-8", newline="") as out,
        ):
            reader, writer = (
                csv.reader(inp, delimiter=delimiter),
                csv.writer(out, delimiter=delimiter),
            )
            headers = next(reader, [])
            for header in headers:
                allocator.reserve_source(header)
            if len(set(headers)) != len(headers):
                raise ValueError("Duplicate column names are unsupported")
            if any(self.scan_text(h) for h in headers):
                issues.append("SENSITIVE_SCHEMA_OR_INDEX")
            writer.writerow(headers)
            for batch in _batches(reader, batch_size):
                rows, problems, n = self._rows(headers, batch, policy, scope, domain, allocator)
                writer.writerows(rows)
                records += len(rows)
                count += n
                issues.extend(problems)
        # Reopen the actual serialized output, validate schema/count and rescan every cell.
        residual: list[Finding] = []
        reread = 0
        with output.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            if next(reader, []) != headers:
                return Result(ReleaseStatus.BLOCKED, issues=["SCHEMA_MISMATCH"])
            for batch in _batches(reader, batch_size):
                if any(len(r) != len(headers) for r in batch):
                    return Result(ReleaseStatus.BLOCKED, issues=["SCHEMA_MISMATCH"])
                reread += len(batch)
                for cells in _batches((v for row in batch for v in row if v), 128):
                    found = [f for items in self._rescan_texts(cells, allocator) for f in items]
                    disallowed = [
                        f
                        for f in found
                        if policy.rule(f.entity_type, domain).action != "keep"
                        and f.entity_type not in policy.allow_residual_types
                    ]
                    residual.extend(disallowed[: max(0, 100 - len(residual))])
        if records != reread:
            return Result(ReleaseStatus.BLOCKED, issues=["ROW_COUNT_MISMATCH"])
        result = self._gate(policy=policy, residual=residual, issues=issues, domain=domain)
        result.records = records
        result.audit["transformations"] = count
        return result

    def deidentify(
        self,
        source: str | Path,
        *,
        policy: Policy | None = None,
        output: str | Path,
        batch_size: int = 1024,
        domain: str | None = None,
        outputs: list[str] | tuple[str, ...] | None = None,
        require_table_structure: bool = False,
        office_media: str = "remove",
    ) -> Result:
        """Write a de-identified copy of ``source`` and verify it by reading it back.

        DOCX output keeps the layout; tracked changes are accepted, personal
        properties, the thumbnail, external links and data-bearing field codes
        are removed. ``office_media="remove"`` (default) also drops images,
        charts and embedded objects, which cannot be checked without OCR;
        ``"keep"`` copies them and the result is blocked as incomplete.
        """
        source, target = Path(source), Path(output)
        if office_media not in {"remove", "keep"}:
            raise ValueError("office_media must be 'remove' or 'keep'")
        if type(require_table_structure) is not bool:
            raise ValueError("Table structure requirement must be boolean")
        if require_table_structure and (
            not isinstance(outputs, (list, tuple))
            or any(not isinstance(value, str) for value in outputs)
            or set(outputs) != {"pdf", "jsonl"}
        ):
            raise ValueError("Table structure verification requires a PDF+JSONL bundle")
        policy = policy or (
            Policy.strict_pdf() if source.suffix.lower() == ".pdf" else Policy.strict()
        )
        if batch_size < 1 or source.resolve() == target.resolve():
            raise ValueError("Use a distinct output path and positive batch size")
        if outputs is not None:
            if (
                not isinstance(outputs, (list, tuple))
                or any(not isinstance(v, str) for v in outputs)
                or len(set(outputs)) != len(outputs)
            ):
                raise ValueError("Invalid output format selection")
            if set(outputs) == {"pdf", "jsonl"} and source.suffix.lower() == ".pdf":
                from deidflow.rag import export_pdf_bundle

                return export_pdf_bundle(
                    source,
                    target,
                    engine=self,
                    policy=policy,
                    domain=domain,
                    require_table_structure=require_table_structure,
                )
            if outputs != ["pdf"] and outputs != ("pdf",):
                return Result(
                    ReleaseStatus.UNSUPPORTED, issues=["OUTPUT_FORMAT_COMBINATION_UNSUPPORTED"]
                )
            if source.suffix.lower() != ".pdf":
                return Result(
                    ReleaseStatus.UNSUPPORTED, issues=["OUTPUT_FORMAT_COMBINATION_UNSUPPORTED"]
                )
        if source.suffix.lower() == ".pdf" and target.suffix.lower() == ".pdf":
            from deidflow.redactors.pdf import redact_pdf

            return redact_pdf(
                source,
                target,
                engine=self,
                policy=policy,
                dpi=self.pdf_dpi,
                max_pages=self.pdf_max_pages,
                max_bytes=self.max_bytes,
                memory_budget_mb=self.memory_budget_mb,
                domain=domain,
            )
        suffix = source.suffix.lower()
        if (
            suffix
            not in {
                ".txt",
                ".text",
                ".md",
                ".log",
                ".csv",
                ".tsv",
                ".json",
                ".jsonl",
                ".docx",
                ".xlsx",
                ".odt",
                ".ods",
                ".html",
                ".htm",
                ".eml",
            }
            or target.suffix.lower() != suffix
        ):
            return Result(
                ReleaseStatus.UNSUPPORTED, issues=["AUTOMATIC_FORMAT_TRANSFORMATION_UNSUPPORTED"]
            )
        if target.exists():
            raise FileExistsError("Output already exists; choose a new path")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".deidflow-", suffix=suffix, dir=target.parent)
        os.close(fd)
        candidate = Path(temporary)
        try:
            if suffix in {".csv", ".tsv"}:
                result = self._csv(source, candidate, policy, batch_size, domain)
            elif suffix in {".docx", ".xlsx", ".odt", ".ods"}:
                result = self._office(source, candidate, policy, domain, office_media == "remove")
            elif suffix in {".html", ".htm"}:
                result = self._html(source, candidate, policy, domain)
            elif suffix == ".eml":
                result = self._eml(source, candidate, policy, domain, office_media)
            elif suffix in {".txt", ".text", ".md", ".log"}:
                if source.stat().st_size > self.max_bytes:
                    raise ValueError("Text exceeds configured size limit")
                _, allocator, document_id = self._document(policy)
                result = self.deidentify_text(
                    source.read_bytes().decode("utf-8"),
                    policy=policy,
                    domain=domain,
                    document_id=document_id,
                    placeholders=allocator,
                )
                if result.status == ReleaseStatus.BLOCKED:
                    return result
                candidate.write_bytes((result.output_text or "").encode("utf-8"))
                verified = self.verify(
                    candidate,
                    policy=policy,
                    expected_sha256=result.audit["sha256"],
                    domain=domain,
                    _placeholders=allocator,
                )
                if verified.status == ReleaseStatus.BLOCKED:
                    result = verified
            else:
                result = self._json_file(source, candidate, policy, domain)
            if result.status == ReleaseStatus.BLOCKED:
                return result  # Candidate is removed, never exposed under final filename.
            # Atomic creation without overwriting an output created concurrently.
            os.link(candidate, target)
            result.output_path = target
            with target.open("rb") as handle:
                result.audit["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
            return result
        except IncompleteTransformationError:
            return Result(ReleaseStatus.BLOCKED, issues=["INCOMPLETE_TRANSFORMATION"])
        except (UnicodeError, csv.Error, json.JSONDecodeError):
            return Result(ReleaseStatus.BLOCKED, issues=["MALFORMED_INPUT"])
        finally:
            candidate.unlink(missing_ok=True)

    def _office(
        self, source: Path, output: Path, policy: Policy, domain: str | None, remove_media: bool
    ) -> Result:
        from deidflow.office import CellGrid, rewrite_docx, rewrite_xlsx
        from deidflow.opendocument import rewrite_odf
        from deidflow.readers import DocumentError

        if source.stat().st_size > self.max_bytes:
            raise ValueError("Document exceeds configured size limit")
        scope, allocator, _ = self._document(policy)
        originals: list[Finding] = []
        office_issues: list[str] = []

        def rewrite(text: str) -> tuple[str, list[tuple[int, int, str]]]:
            findings = self.scan_text(text)
            originals.extend(findings)
            transformed, mappings = transform_text(
                text,
                findings,
                policy,
                key=self.key,
                scope=scope,
                domain=domain,
                custom=self.custom_transforms,
                placeholders=allocator,
            )
            return transformed, [
                (m.source_start, m.source_end, transformed[m.output_start : m.output_end])
                for m in mappings
            ]

        def transform_cells(sheets: list[tuple[str, CellGrid]]) -> list[CellGrid]:
            return [
                self._sheet_cells(grid, policy, scope, domain, originals, office_issues, allocator)
                for _, grid in sheets
            ]

        try:
            if source.suffix.lower() in {".odt", ".ods"}:
                report = rewrite_odf(
                    source,
                    output,
                    rewrite,
                    transform_cells,
                    max_bytes=self.max_bytes,
                    remove_media=remove_media,
                )
            elif source.suffix.lower() == ".xlsx":
                report = rewrite_xlsx(
                    source,
                    output,
                    transform_cells,
                    rewrite,
                    max_bytes=self.max_bytes,
                    remove_media=remove_media,
                )
            else:
                report = rewrite_docx(
                    source, output, rewrite, max_bytes=self.max_bytes, remove_media=remove_media
                )
            graph = self.read(output)
        except DocumentError:
            return Result(ReleaseStatus.BLOCKED, issues=["MALFORMED_INPUT"])
        residual: list[Finding] = []
        for batch in _batches(graph.fragments, 32):
            residual.extend(
                f for items in self._rescan_texts([x.text for x in batch], allocator) for f in items
            )
        result = self._gate(
            policy=policy,
            residual=residual,
            original=originals,
            complete=graph.complete,
            issues=graph.issues + office_issues,
            domain=domain,
        )
        result.records = 1
        result.audit["transformations"] = report.transformations
        result.audit["office_removed"] = dict(sorted(report.removed.items()))
        return result

    def _html(self, source: Path, output: Path, policy: Policy, domain: str | None) -> Result:
        from deidflow.markup import rewrite_html
        from deidflow.readers import DocumentError

        if source.stat().st_size > self.max_bytes:
            raise ValueError("Document exceeds configured size limit")
        scope, allocator, _ = self._document(policy)
        originals: list[Finding] = []

        def rewrite(text: str) -> tuple[str, list[tuple[int, int, str]]]:
            findings = self.scan_text(text)
            originals.extend(findings)
            transformed, mappings = transform_text(
                text,
                findings,
                policy,
                key=self.key,
                scope=scope,
                domain=domain,
                custom=self.custom_transforms,
                placeholders=allocator,
            )
            return transformed, [
                (m.source_start, m.source_end, transformed[m.output_start : m.output_end])
                for m in mappings
            ]

        output_text, report = rewrite_html(source.read_bytes().decode("utf-8"), rewrite)
        output.write_bytes(output_text.encode("utf-8"))
        try:
            graph = self.read(output)
        except DocumentError:
            return Result(ReleaseStatus.BLOCKED, issues=["MALFORMED_INPUT"])
        residual: list[Finding] = []
        for batch in _batches(graph.fragments, 32):
            residual.extend(
                f for items in self._rescan_texts([x.text for x in batch], allocator) for f in items
            )
        result = self._gate(
            policy=policy,
            residual=residual,
            original=originals,
            complete=graph.complete,
            issues=graph.issues,
            domain=domain,
        )
        result.records = 1
        result.audit["transformations"] = report.transformations
        result.audit["markup_removed"] = dict(sorted(report.removed.items()))
        return result

    def _eml(
        self, source: Path, output: Path, policy: Policy, domain: str | None, office_media: str
    ) -> Result:
        from deidflow.mail import rewrite_message
        from deidflow.markup import rewrite_html
        from deidflow.readers import DocumentError

        if source.stat().st_size > self.max_bytes:
            raise ValueError("Message exceeds configured size limit")
        scope, allocator, document_id = self._document(policy)
        originals: list[Finding] = []

        def rewrite(text: str) -> tuple[str, list[tuple[int, int, str]]]:
            findings = self.scan_text(text)
            originals.extend(findings)
            transformed, mappings = transform_text(
                text,
                findings,
                policy,
                key=self.key,
                scope=scope,
                domain=domain,
                custom=self.custom_transforms,
                placeholders=allocator,
            )
            return transformed, [
                (m.source_start, m.source_end, transformed[m.output_start : m.output_end])
                for m in mappings
            ]

        def whole(value: str, entity_type: str) -> str:
            # Header semantics: a display name is a person, an address an e-mail.
            finding = Finding(entity_type, 0, len(value), 1.0, "email.header", protected=True)
            transformed, _ = transform_text(
                value,
                [finding],
                policy,
                key=self.key,
                scope=scope,
                domain=domain,
                custom=self.custom_transforms,
                placeholders=allocator,
            )
            return transformed

        def attachment(path: Path, target: Path) -> tuple[str, list[str]]:
            result = self.deidentify(
                path, policy=policy, output=target, domain=domain, office_media=office_media
            )
            return str(result.status), list(result.issues)

        shared = _SHARED_DOCUMENT.set((scope, allocator, document_id))
        try:
            data, report = rewrite_message(
                source.read_bytes(),
                rewrite=rewrite,
                whole=whole,
                attachment=attachment,
                rewrite_html=lambda text: rewrite_html(text, rewrite)[0],
                key=self.key or secrets.token_bytes(32),
                remove_media=office_media == "remove",
            )
            output.write_bytes(data)
            graph = self.read(output)
        except (DocumentError, ValueError, LookupError):
            return Result(ReleaseStatus.BLOCKED, issues=["MALFORMED_INPUT"])
        finally:
            _SHARED_DOCUMENT.reset(shared)
        residual: list[Finding] = []
        for batch in _batches(graph.fragments, 32):
            residual.extend(
                f for items in self._rescan_texts([x.text for x in batch], allocator) for f in items
            )
        result = self._gate(
            policy=policy,
            residual=residual,
            original=originals,
            complete=graph.complete,
            issues=graph.issues + report.issues,
            domain=domain,
        )
        result.records = 1
        result.audit["transformations"] = report.transformations
        result.audit["email_removed"] = dict(sorted(report.removed.items()))
        return result

    def _sheet_cells(
        self,
        grid: dict[tuple[int, int], str],
        policy: Policy,
        scope: str,
        domain: str | None,
        originals: list[Finding],
        issues: list[str],
        placeholders: PlaceholderAllocator | None = None,
    ) -> dict[tuple[int, int], str]:
        """New text of every changed cell of one worksheet.

        The first nonempty row is the header. Columns the profiler recognizes
        (``Nombre``, ``RFC``, ``Teléfono``...) are transformed whole, as for CSV;
        other cells are scanned with their column header as a ``Header: value``
        prefix, so labelled-value rules and the tagger see the field name.
        """
        if not grid:
            return {}
        placeholders = placeholders if placeholders is not None else PlaceholderAllocator()
        for value in grid.values():
            placeholders.reserve_source(value)
        rows = sorted({r for r, _ in grid})
        columns = sorted({c for _, c in grid})
        header_row = rows[0]
        labels = {c: grid.get((header_row, c), "").strip() for c in columns}
        headers: list[str] = []
        seen: dict[str, int] = {}
        for c in columns:
            name = labels[c] or f"columna_{c}"
            seen[name] = seen.get(name, 0) + 1
            headers.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
        body = rows[1:]
        if len(body) * len(columns) > self.memory_budget_mb * 1024**2 // 64:
            from deidflow.readers import DocumentError

            raise DocumentError("XLSX table expansion exceeds configured memory budget")
        table = [[grid.get((r, c), "") for c in columns] for r in body]
        profiles = profile_table(headers, table, self.detector)
        if any(profile.unknown_identifier for profile in profiles):
            issues.append("UNKNOWN_IDENTIFIER_CANDIDATE")
        changed: dict[tuple[int, int], str] = {}
        pending: list[tuple[int, int, str, str]] = [
            (header_row, c, "", grid[(header_row, c)]) for c in columns if (header_row, c) in grid
        ]
        whole_actions = {"redact", "suppress", "placeholder", "pseudonym", "generalize", "indexed"}
        for j, (c, profile) in enumerate(zip(columns, profiles, strict=True)):
            rule = policy.rule(profile.entity_type or "", domain)
            whole = (
                self.schema_fast_path
                and profile.entity_type is not None
                and rule.action in whole_actions
            )
            for i, r in enumerate(body):
                value = table[i][j]
                if not value:
                    continue
                if whole:
                    finding = Finding(
                        profile.entity_type or "CONFIDENTIAL",
                        0,
                        len(value),
                        profile.score,
                        "schema.column",
                        protected=True,
                    )
                    originals.append(finding)
                    transformed, _ = transform_text(
                        value,
                        [finding],
                        policy,
                        key=self.key,
                        scope=scope,
                        domain=domain,
                        custom=self.custom_transforms,
                        placeholders=placeholders,
                    )
                    changed[(r, c)] = "" if rule.action == "suppress" else transformed
                else:
                    prefix = f"{labels[c]}: " if labels[c] else ""
                    pending.append((r, c, prefix, value))
        for batch in _batches(pending, 128):
            texts = [prefix + value for _, _, prefix, value in batch]
            for (r, c, prefix, value), findings in zip(batch, self.scan_texts(texts), strict=True):
                shift = len(prefix)
                local = [
                    replace(f, start=max(f.start, shift) - shift, end=f.end - shift)
                    for f in findings
                    if f.end > shift
                ]
                originals.extend(local)
                transformed, mappings = transform_text(
                    value,
                    local,
                    policy,
                    key=self.key,
                    scope=scope,
                    domain=domain,
                    custom=self.custom_transforms,
                    placeholders=placeholders,
                )
                if mappings:
                    changed[(r, c)] = transformed
        return changed

    def _json_file(self, source: Path, output: Path, policy: Policy, domain: str | None) -> Result:
        issues, count, records = [], 0, 0
        scope, allocator, _ = self._document(policy)

        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            if len({k for k, _ in items}) != len(items):
                raise ValueError("Duplicate JSON keys are unsupported")
            return dict(items)

        def walk(value: Any, header: str = "") -> Any:
            nonlocal count
            if isinstance(value, dict):
                out = {}
                for key, item in value.items():
                    key_findings = self.scan_text(key)
                    new_key, key_mappings = transform_text(
                        key,
                        key_findings,
                        policy,
                        key=self.key,
                        scope=scope,
                        domain=domain,
                        custom=self.custom_transforms,
                        placeholders=allocator,
                    )
                    if new_key in out:
                        raise ValueError("Transformed JSON keys would collide")
                    issues.extend(_source_review_issues(key_findings, policy))
                    count += len(key_mappings)
                    out[new_key] = walk(item, key)
                return out
            if isinstance(value, list):
                return [walk(x, header) for x in value]
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                rows, problems, n = self._rows(
                    [header], [[value]], policy, scope, domain, allocator
                )
                issues.extend(problems)
                count += n
                return rows[0][0]
            return value

        with (
            source.open(encoding="utf-8") as inp,
            output.open("w", encoding="utf-8", newline="") as out,
        ):
            if source.suffix.lower() == ".jsonl":
                while line := inp.readline(self.max_bytes + 1):
                    if len(line.encode("utf-8")) > self.max_bytes:
                        raise ValueError("JSONL record exceeds size limit")
                    out.write(
                        json.dumps(
                            walk(json.loads(line, object_pairs_hook=pairs)),
                            ensure_ascii=False,
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    records += 1
            else:
                if source.stat().st_size > self.max_bytes:
                    raise ValueError("JSON exceeds configured size limit")
                json.dump(
                    walk(json.load(inp, object_pairs_hook=pairs)),
                    out,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                records = 1
        result = self._verify_stream(
            output, policy, domain, transformed=True, placeholders=allocator
        )
        if issues and result.status == ReleaseStatus.APPROVED:
            result.status = ReleaseStatus.REVIEW_REQUIRED
        result.issues = list(dict.fromkeys(result.issues + issues))
        result.records, result.audit["transformations"] = records, count
        return result

    def deidentify_many(
        self,
        sources: Iterable[str | Path],
        *,
        output_dir: str | Path,
        policy: Policy | None = None,
        batch_size: int = 1024,
    ) -> Iterator[Result]:
        directory = Path(output_dir)
        for source in sources:
            yield self.deidentify(
                source, output=directory / Path(source).name, policy=policy, batch_size=batch_size
            )

    def benchmark(self, texts: Iterable[str], *, repeats: int = 3) -> dict[str, Any]:
        if repeats < 1:
            raise ValueError("Repeats must be positive")
        values = list(texts)
        times = []
        for _ in range(repeats):
            start = time.perf_counter()
            list(self.scan_many(values, input_kind="text"))
            times.append(time.perf_counter() - start)
        return {
            "documents": len(values),
            "seconds": times,
            "records_per_second": [len(values) / max(t, 1e-9) for t in times],
        }
