"""Receipt-bound structured export from actual physically sanitized PDF pixels.

Private staging holds candidates until PDF and independent JSONL gates both pass.
This module never serializes native/source text or detected source values.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from deidflow.core import Finding
from deidflow.engine import ReleaseStatus, Result
from deidflow.policies import Policy

_DOCUMENT_ID = re.compile(r"[a-f0-9]{32}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_CHUNK_ID = re.compile(r"p[0-9]{6}-l[0-9]{6}\Z")
_PAGE_KEYS = {
    "schema_version",
    "document_id",
    "kind",
    "page",
    "width_points",
    "height_points",
    "raster_width",
    "raster_height",
    "text",
    "lines",
    "tables",
    "structure_status",
}
_LINE_KEYS = {"chunk_id", "previous_id", "next_id", "line_index", "start", "end", "bbox", "tokens"}
_SAFE_ISSUES = frozenset(
    {
        "LOW_SOURCE_OCR_CONFIDENCE",
        "LOW_OUTPUT_OCR_CONFIDENCE",
        "UNCERTAIN_SOURCE_FINDINGS",
        "UNRESOLVED_MODEL_WINDOW_BOUNDARY",
        "SOURCE_FINDING_BELOW_POLICY_THRESHOLD",
        "SEMANTIC_MODEL_REQUIRED",
        "RESIDUAL_FINDINGS",
        "INCOMPLETE_COVERAGE",
        "PDF_REDACTION_OR_VERIFICATION_FAILED",
        "PDF_PROCESSING_FAILED",
        "PDF_SOURCE_FEATURE_UNSUPPORTED",
        "PDF_POLICY_ACTION_UNSUPPORTED",
        "LOCAL_OCR_REQUIRED",
        "SOURCE_CHANGED_DURING_PROCESSING",
        "RAG_TABLE_STRUCTURE_UNAVAILABLE",
        "RAG_TRANSFORMATION_RECEIPT_REQUIRED",
        "UPSTREAM_REVIEW_REQUIRED",
    }
)


class RAGExportError(RuntimeError):
    """Sanitized structured-export failure."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({k for k, _ in items}) != len(items):
        raise RAGExportError("Duplicate structured output keys")
    return dict(items)


def _reject_constant(value: str) -> None:
    raise RAGExportError("Nonfinite structured output value")


def _number(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(value)


def _hash_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _secure_stage(parent: Path) -> Path:
    stage = Path(tempfile.mkdtemp(prefix=".deidflow-rag-", dir=parent))
    try:
        if os.name == "nt":
            flags = 0x08000000  # Win32 CREATE_NO_WINDOW; available to cross-platform type checks.
            info = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"],
                capture_output=True,
                check=True,
                creationflags=flags,
                timeout=15,
            ).stdout.decode("utf-8")
            sid = re.search(r"S-1-[0-9]+(?:-[0-9]+)+", info)
            if sid is None:
                raise RAGExportError("Cannot establish private staging permissions")
            subprocess.run(
                ["icacls", str(stage), "/inheritance:r", "/grant:r", f"*{sid.group()}:(OI)(CI)F"],
                capture_output=True,
                check=True,
                creationflags=flags,
                timeout=15,
            )
        else:
            stage.chmod(0o700)
        return stage
    except Exception:
        # The directory was just allocated by this function and is still empty.
        try:
            stage.rmdir()
        except OSError:
            pass
        raise RAGExportError("Cannot establish private staging permissions") from None


def _publish(stage: Path, target: Path) -> None:
    """Exclusive atomic directory publication; never replace an existing directory."""
    if os.name == "nt":
        os.rename(stage, target)  # Windows refuses an existing target.
    elif sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        rename = getattr(library, "renameat2", None)
        if rename is None:
            raise RAGExportError("Exclusive atomic directory publication is unavailable")
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(stage), -100, os.fsencode(target), 1) != 0:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError("Output bundle already exists")
            raise RAGExportError("Atomic directory publication failed")
    elif sys.platform == "darwin":
        # renamex_np(RENAME_EXCL) fails with EEXIST instead of replacing a target.
        library = ctypes.CDLL(None, use_errno=True)
        rename = getattr(library, "renamex_np", None)
        if rename is None:
            raise RAGExportError("Exclusive atomic directory publication is unavailable")
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(os.fsencode(stage), os.fsencode(target), 0x00000004) != 0:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError("Output bundle already exists")
            raise RAGExportError("Atomic directory publication failed")
    else:
        raise RAGExportError(
            "Exclusive atomic directory publication is unsupported on this platform"
        )


def _cleanup_stage(stage: Path, parent: Path, identity: tuple[int, int]) -> None:
    if not stage.exists():
        return
    current = stage.lstat()
    if (
        stage.is_symlink()
        or stage.parent.resolve() != parent.resolve()
        or not stage.name.startswith(".deidflow-rag-")
        or (current.st_dev, current.st_ino) != identity
    ):
        raise RAGExportError("Private staging ownership changed; cleanup refused")
    try:
        shutil.rmtree(stage)
    except OSError:
        raise RAGExportError("Private staging cleanup failed") from None


def _page_record(page: dict[str, Any], document_id: str) -> dict[str, Any]:
    text = page["text"]
    if not isinstance(text, str) or len(text) > 250_000:
        raise RAGExportError("Invalid verified output text")
    lines: list[dict[str, Any]] = []
    cursor = 0
    for value in text.splitlines(keepends=True):
        end = cursor + len(value.rstrip("\r\n"))
        token_spans = [
            (start, finish, box)
            for start, finish, box in page["spans"]
            if start < end and finish > cursor
        ]
        matched = [box for _, _, box in token_spans]
        if end > cursor and matched:
            index = len(lines)
            lines.append(
                {
                    "chunk_id": f"p{page['page']:06d}-l{index:06d}",
                    "previous_id": None,
                    "next_id": None,
                    "line_index": index,
                    "start": cursor,
                    "end": end,
                    "bbox": [
                        min(b[0] for b in matched),
                        min(b[1] for b in matched),
                        max(b[2] for b in matched),
                        max(b[3] for b in matched),
                    ],
                    "tokens": [
                        {"start": start, "end": finish, "bbox": list(box)}
                        for start, finish, box in token_spans
                    ],
                }
            )
        cursor += len(value)
    for index, line in enumerate(lines):
        line["previous_id"] = lines[index - 1]["chunk_id"] if index else None
        line["next_id"] = lines[index + 1]["chunk_id"] if index + 1 < len(lines) else None
    return {
        "schema_version": 1,
        "document_id": document_id,
        "kind": "page",
        "page": page["page"],
        "width_points": page["page_width"],
        "height_points": page["page_height"],
        "raster_width": page["raster_width"],
        "raster_height": page["raster_height"],
        "text": text,
        "lines": lines,
        "tables": [],
        "structure_status": "lines_only",
    }


def _validate_page(record: Any, *, page_number: int, document_id: str | None) -> str:
    if not isinstance(record, dict) or set(record) != _PAGE_KEYS:
        raise RAGExportError("Unexpected structured output schema")
    identity = record["document_id"]
    if (
        not isinstance(identity, str)
        or not _DOCUMENT_ID.fullmatch(identity)
        or (document_id is not None and identity != document_id)
    ):
        raise RAGExportError("Inconsistent structured document identity")
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["kind"] != "page"
        or type(record["page"]) is not int
        or record["page"] != page_number
        or record["structure_status"] != "lines_only"
        or record["tables"] != []
    ):
        raise RAGExportError("Invalid structured page metadata")
    for key in ("width_points", "height_points"):
        if not _number(record[key]) or not 0 < record[key] <= 100000:
            raise RAGExportError("Invalid structured page dimensions")
    for key in ("raster_width", "raster_height"):
        if type(record[key]) is not int or not 0 < record[key] <= 40000:
            raise RAGExportError("Invalid structured raster dimensions")
    if record["raster_width"] * record["raster_height"] > 40_000_000:
        raise RAGExportError("Structured raster pixel budget exceeded")
    text, lines = record["text"], record["lines"]
    if (
        not isinstance(text, str)
        or len(text) > 250_000
        or not isinstance(lines, list)
        or len(lines) > 20000
    ):
        raise RAGExportError("Structured text budget exceeded")
    previous_end = 0
    for i, line in enumerate(lines):
        if (
            not isinstance(line, dict)
            or set(line) != _LINE_KEYS
            or type(line["line_index"]) is not int
            or line["line_index"] != i
        ):
            raise RAGExportError("Invalid structured line schema")
        expected = f"p{page_number:06d}-l{i:06d}"
        if (
            line["chunk_id"] != expected
            or line["previous_id"] != (f"p{page_number:06d}-l{i - 1:06d}" if i else None)
            or line["next_id"]
            != (f"p{page_number:06d}-l{i + 1:06d}" if i + 1 < len(lines) else None)
        ):
            raise RAGExportError("Invalid structured chunk relationships")
        start, end, box = line["start"], line["end"], line["bbox"]
        if (
            type(start) is not int
            or type(end) is not int
            or not previous_end <= start < end <= len(text)
            or not isinstance(box, list)
            or len(box) != 4
            or not all(_number(v) for v in box)
            or not 0 <= box[0] < box[2] <= record["raster_width"]
            or not 0 <= box[1] < box[3] <= record["raster_height"]
        ):
            raise RAGExportError("Invalid structured line location")
        if text[previous_end:start].strip():
            raise RAGExportError("Structured text lacks verified line coverage")
        previous_end = end
        tokens = line["tokens"]
        if not isinstance(tokens, list) or not tokens or len(tokens) > 20000:
            raise RAGExportError("Invalid structured token schema")
        previous_token_end = start
        for token in tokens:
            if not isinstance(token, dict) or set(token) != {"start", "end", "bbox"}:
                raise RAGExportError("Unexpected structured token fields")
            a, b, rectangle = token["start"], token["end"], token["bbox"]
            if (
                type(a) is not int
                or type(b) is not int
                or not previous_token_end <= a < b <= end
                or not isinstance(rectangle, list)
                or len(rectangle) != 4
                or not all(_number(v) for v in rectangle)
                or not 0 <= rectangle[0] < rectangle[2] <= record["raster_width"]
                or not 0 <= rectangle[1] < rectangle[3] <= record["raster_height"]
                or not box[0] <= rectangle[0] < rectangle[2] <= box[2]
                or not box[1] <= rectangle[1] < rectangle[3] <= box[3]
            ):
                raise RAGExportError("Invalid structured token location")
            if text[previous_token_end:a].strip():
                raise RAGExportError("Structured text lacks verified token coverage")
            previous_token_end = b
        if text[previous_token_end:end].strip():
            raise RAGExportError("Structured line has unattested text")
    if text[previous_end:].strip():
        raise RAGExportError("Structured page has unattested text")
    return identity


def _verify_rag_jsonl(
    source: str | Path,
    *,
    engine: Any,
    policy: Policy | None = None,
    domain: str | None = None,
    expected_record_hashes: list[str] | None = None,
    expected_document_id: str | None = None,
    require_table_structure: bool = False,
) -> Result:
    """Reopen, validate and rescan. Without internal receipts approval is unavailable."""
    policy = policy or Policy.strict_pdf()
    path = Path(source)
    issues: list[str] = []
    residual: list[Finding] = []
    pages = 0
    identity = expected_document_id
    if expected_record_hashes is None:
        issues.append("RAG_TRANSFORMATION_RECEIPT_REQUIRED")
    if require_table_structure:
        issues.append("RAG_TABLE_STRUCTURE_UNAVAILABLE")
    try:
        total = 0
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while line := handle.readline(min(engine.max_bytes, 1024**2) + 1):
                total += len(line)
                digest.update(line)
                if len(line) > min(engine.max_bytes, 1024**2) or total > engine.max_bytes:
                    raise RAGExportError("Structured output byte limit exceeded")
                record = json.loads(
                    line.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant
                )
                pages += 1
                if pages > getattr(engine, "pdf_max_pages", 1000):
                    raise RAGExportError("Structured output page budget exceeded")
                identity = _validate_page(record, page_number=pages, document_id=identity)
                if expected_record_hashes is not None and (
                    pages > len(expected_record_hashes)
                    or hashlib.sha256(_canonical(record)).hexdigest()
                    != expected_record_hashes[pages - 1]
                ):
                    raise RAGExportError("Structured output differs from verified PDF content")
                found = engine.scan_ocr_text(record["text"])
                disallowed = [
                    f
                    for f in found
                    if policy.rule(f.entity_type, domain).action != "keep"
                    and f.entity_type not in policy.allow_residual_types
                ]
                residual.extend(disallowed[: max(0, 100 - len(residual))])
        if not pages or (
            expected_record_hashes is not None and pages != len(expected_record_hashes)
        ):
            raise RAGExportError("Structured output page coverage mismatch")
        result = engine._gate(policy=policy, residual=residual, issues=issues, domain=domain)
        result.records = pages
        result.audit["jsonl_sha256"] = digest.hexdigest()
        return result
    except Exception:
        return Result(ReleaseStatus.BLOCKED, issues=["RAG_STRUCTURED_VERIFICATION_FAILED"])


def verify_rag_jsonl(
    source: str | Path,
    *,
    engine: Any,
    policy: Policy | None = None,
    domain: str | None = None,
    require_table_structure: bool = False,
) -> Result:
    """Standalone inspection is never approval without internal PDF receipts."""
    return _verify_rag_jsonl(
        source,
        engine=engine,
        policy=policy,
        domain=domain,
        require_table_structure=require_table_structure,
    )


def _safe_codes(codes: list[str]) -> list[str]:
    return sorted({code if code in _SAFE_ISSUES else "UPSTREAM_REVIEW_REQUIRED" for code in codes})


def _write_audit(
    path: Path,
    *,
    document_id: str,
    status: ReleaseStatus,
    policy: Policy,
    pages: int,
    pdf_sha256: str,
    jsonl_sha256: str,
    issues: list[str],
) -> None:
    if not _DOCUMENT_ID.fullmatch(document_id) or not all(
        _HASH.fullmatch(v) for v in (policy.fingerprint(), pdf_sha256, jsonl_sha256)
    ):
        raise RAGExportError("Invalid export audit provenance")
    record = {
        "schema_version": 1,
        "document_id": document_id,
        "status": str(status),
        "policy_sha256": policy.fingerprint(),
        "pages": pages,
        "artifacts": {"pdf_sha256": pdf_sha256, "jsonl_sha256": jsonl_sha256},
        "verification": {
            "pdf_encoded_pixels": True,
            "pdf_rerendered_ocr": True,
            "jsonl_reread_and_rescanned": True,
            "shared_verified_pixel_decisions": True,
        },
        "structure": "page_and_line_relationships",
        "tables": "not_reconstructed",
        "issues": _safe_codes(issues),
        "anonymity_proven": False,
    }
    path.write_bytes(_canonical(record) + b"\n")
    # Independent serialization round trip; no user/source strings are audit fields.
    checked = json.loads(
        path.read_bytes(), object_pairs_hook=_pairs, parse_constant=_reject_constant
    )
    if checked != record:
        raise RAGExportError("Export audit verification failed")


def export_pdf_bundle(
    source: str | Path,
    output_dir: str | Path,
    *,
    engine: Any,
    policy: Policy | None = None,
    domain: str | None = None,
    require_table_structure: bool = False,
) -> Result:
    """Publish a single new directory containing jointly gated PDF, JSONL and audit.

    ``output_dir`` is explicit; no private source filename becomes a public ID.
    PDF operators retain their existing semantics and strict defaults.
    """
    from deidflow.redactors.pdf import redact_pdf

    policy = policy or Policy.strict_pdf()
    if type(require_table_structure) is not bool:
        raise ValueError("require_table_structure must be boolean")
    target = Path(output_dir)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Output bundle already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    parent = target.parent.resolve()
    target = parent / target.name
    stage: Path | None = None
    identity: tuple[int, int] | None = None
    try:
        stage = _secure_stage(parent)
        stat = stage.stat()
        identity = (stat.st_dev, stat.st_ino)
        document_id = secrets.token_hex(16)
        pdf_path, jsonl_path, audit_path = (
            stage / "document.safe.pdf",
            stage / "document.safe.jsonl",
            stage / "document.audit.json",
        )
        expected: list[str] = []
        with jsonl_path.open("xb") as handle:

            def capture(page: dict[str, Any]) -> None:
                record = _page_record(page, document_id)
                _validate_page(record, page_number=len(expected) + 1, document_id=document_id)
                encoded = _canonical(record)
                if len(encoded) > min(engine.max_bytes, 1024**2):
                    raise RAGExportError("Structured page exceeds output byte budget")
                handle.write(encoded + b"\n")
                expected.append(hashlib.sha256(encoded).hexdigest())

            pdf_result = redact_pdf(
                source,
                pdf_path,
                engine=engine,
                policy=policy,
                dpi=engine.pdf_dpi,
                max_pages=engine.pdf_max_pages,
                max_bytes=engine.max_bytes,
                memory_budget_mb=engine.memory_budget_mb,
                domain=domain,
                _on_verified_page=capture,
            )
        if pdf_result.status in {ReleaseStatus.BLOCKED, ReleaseStatus.UNSUPPORTED}:
            return Result(
                pdf_result.status, issues=_safe_codes(pdf_result.issues), records=pdf_result.records
            )
        if (
            pdf_result.audit.get("encoded_pixels_verified") is not True
            or pdf_result.audit.get("output_rerendered_and_ocr_verified") is not True
            or len(expected) != pdf_result.records
        ):
            raise RAGExportError("PDF did not provide complete structured export receipts")
        jsonl_result = _verify_rag_jsonl(
            jsonl_path,
            engine=engine,
            policy=policy,
            domain=domain,
            expected_record_hashes=expected,
            expected_document_id=document_id,
            require_table_structure=require_table_structure,
        )
        if jsonl_result.status == ReleaseStatus.BLOCKED:
            return Result(
                ReleaseStatus.BLOCKED, issues=jsonl_result.issues, records=jsonl_result.records
            )
        issues = _safe_codes(pdf_result.issues + jsonl_result.issues)
        status = (
            ReleaseStatus.REVIEW_REQUIRED
            if issues
            or pdf_result.status != ReleaseStatus.APPROVED
            or jsonl_result.status != ReleaseStatus.APPROVED
            else ReleaseStatus.APPROVED
        )
        pdf_digest, jsonl_digest = _hash_file(pdf_path), _hash_file(jsonl_path)
        if pdf_digest != pdf_result.audit.get("sha256") or jsonl_digest != jsonl_result.audit.get(
            "jsonl_sha256"
        ):
            raise RAGExportError("Output artifacts changed after verification")
        _write_audit(
            audit_path,
            document_id=document_id,
            status=status,
            policy=policy,
            pages=pdf_result.records,
            pdf_sha256=pdf_digest,
            jsonl_sha256=jsonl_digest,
            issues=issues,
        )
        _publish(stage, target)
        result = Result(
            status,
            output_path=target / pdf_path.name,
            issues=issues,
            records=pdf_result.records,
            audit={
                "format": "pdf+jsonl",
                "pages": pdf_result.records,
                "document_id": document_id,
                "joint_artifact_verification": True,
                "anonymity_proven": False,
            },
            safe_jsonl=target / jsonl_path.name,
            audit_path=target / audit_path.name,
        )
        return result
    except Exception:
        return Result(ReleaseStatus.BLOCKED, issues=["RAG_EXPORT_FAILED"])
    finally:
        if stage is not None and identity is not None:
            _cleanup_stage(stage, parent, identity)


__all__ = ["RAGExportError", "export_pdf_bundle", "verify_rag_jsonl"]
