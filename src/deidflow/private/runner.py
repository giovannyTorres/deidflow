"""Bounded private operation; no record-level output and no accuracy claims."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from .gmail import (
    Attachment,
    GmailTransport,
    PrivateConfig,
    _validate_account,
    attachment_bytes,
    candidate,
    iter_parts,
    metadata_fields,
    personal_message,
    strict_json,
)
from .reports import OperationalMetrics
from .security import (
    PrivateError,
    private_path,
    protect,
    require_external_terminal,
    secure_directory,
    temporary_workspace,
    write_private,
)


@contextmanager
def quiet_private_runtime() -> Iterator[None]:
    old = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(old)


def discovery(
    config: PrivateConfig, transport: GmailTransport, metrics: OperationalMetrics
) -> Iterator[tuple[Attachment, dict[str, str]]]:
    """Only metadata trees are requested, and uncertain work provenance is excluded."""
    _validate_account(transport, config.account)
    query = "has:attachment -in:spam -in:trash"
    if config.after:
        query += " after:" + config.after.replace("-", "/")
    if config.before:
        query += " before:" + config.before.replace("-", "/")
    seen_messages: set[str] = set()
    seen_attachments: set[tuple[str, str]] = set()
    page_token = None
    seen_tokens: set[str] = set()
    while True:
        parameters: dict[str, Any] = {
            "q": query,
            "maxResults": min(100, config.max_messages - len(seen_messages)),
            "includeSpamTrash": "false",
            "fields": "messages(id),nextPageToken",
        }
        if page_token is not None:
            parameters["pageToken"] = page_token
        listing = transport.get("messages", params=parameters)
        messages = listing.get("messages", [])
        if not isinstance(messages, list) or len(messages) > 500:
            raise PrivateError("PRIVATE_RESPONSE_INVALID")
        for message in messages:
            identifier = message.get("id") if isinstance(message, dict) else None
            import re

            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
                raise PrivateError("PRIVATE_RESPONSE_INVALID")
            if identifier in seen_messages:
                continue
            if len(seen_messages) >= config.max_messages:
                metrics.truncated = True
                return
            seen_messages.add(identifier)
            metrics.counts["messages_examined"] += 1
            metadata = transport.get(
                "messages/" + identifier,
                params={
                    "format": "metadata",
                    "metadataHeaders": ["From", "To", "Cc", "Subject"],
                    "fields": "id,payload(headers)",
                },
            )
            if not personal_message(metadata, config):
                metrics.counts["work_or_uncertain_exclusions"] += 1
                continue
            response = transport.get(
                "messages/" + identifier, params={"format": "full", "fields": metadata_fields()}
            )
            parts = list(iter_parts(response.get("payload", {})))
            if len(parts) > config.max_attachments_per_message:
                metrics.counts["filter_exclusions"] += len(parts)
                continue
            headers = {h["name"].lower(): h["value"] for h in metadata["payload"]["headers"]}
            for part in parts:
                if metrics.counts["candidate_attachments"] >= config.max_attachments:
                    metrics.truncated = True
                    return
                metrics.counts["candidate_attachments"] += 1
                item, reason = candidate(part, identifier, config)
                if item is None:
                    metrics.counts[reason] += 1
                    continue
                key = (item.message_id, item.attachment_id)
                if key in seen_attachments:
                    metrics.counts["metadata_duplicate_candidates"] += 1
                    continue
                seen_attachments.add(key)
                metrics.counts["eligible_attachments"] += 1
                metrics.formats[item.format] += 1
                metrics.total_bytes += item.size
                metrics.size_bins[
                    "lt_1_mib"
                    if item.size < 1024**2
                    else "1_to_10_mib"
                    if item.size < 10 * 1024**2
                    else "10_to_64_mib"
                ] += 1
                # This identifying metadata is used only in the local consent UI.
                # It never enters an aggregate report or log.
                yield (
                    item,
                    {
                        "filename": str(part["filename"]),
                        "sender": headers.get("from", ""),
                        "subject": headers.get("subject", ""),
                    },
                )
        next_token = listing.get("nextPageToken")
        if next_token is None:
            return
        if (
            not isinstance(next_token, str)
            or not next_token
            or len(next_token) > 4096
            or next_token in seen_tokens
        ):
            raise PrivateError("PRIVATE_RESPONSE_INVALID")
        if len(seen_messages) >= config.max_messages or len(seen_tokens) >= config.max_messages:
            metrics.truncated = True
            return
        seen_tokens.add(next_token)
        page_token = next_token


class PersonalApprovals:
    """HMAC references, never filenames or document text, persist personal attestations."""

    def __init__(self, config: PrivateConfig) -> None:
        root = secure_directory(config.private_root)
        key_path = root / ".approval-key"
        if not key_path.exists():
            write_private(key_path, secrets.token_bytes(32))
        protect(key_path, directory=False)
        self.key = key_path.read_bytes()
        if len(self.key) != 32:
            raise PrivateError("PRIVATE_CONFIG_INVALID")
        self.account = config.account.lower()
        self.path = (
            private_path(config.approval_file)
            if config.approval_file
            else root / "personal-approvals.json"
        )
        self.decisions: dict[str, str] = {}
        self.review_path = root / "review-queue.json"
        self.review: dict[str, list[str]] = {}
        if self.path.exists():
            protect(self.path, directory=False)
            if self.path.stat().st_size > 4 * 1024**2:
                raise PrivateError("PRIVATE_CONFIG_INVALID")
            data = strict_json(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or set(data) != {"schema_version", "decisions"}
                or data["schema_version"] != 1
                or not isinstance(data["decisions"], dict)
            ):
                raise PrivateError("PRIVATE_CONFIG_INVALID")
            import re

            if any(
                not isinstance(k, str)
                or not re.fullmatch(r"[0-9a-f]{64}", k)
                or v not in {"PERSONAL", "EXCLUDE"}
                for k, v in data["decisions"].items()
            ):
                raise PrivateError("PRIVATE_CONFIG_INVALID")
            self.decisions = data["decisions"]
        if self.review_path.exists():
            data = strict_json(self.review_path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or set(data) != {"schema_version", "items"}
                or data["schema_version"] != 1
                or not isinstance(data["items"], dict)
            ):
                raise PrivateError("PRIVATE_CONFIG_INVALID")
            allowed = {
                "UNREADABLE",
                "OCR_UNCERTAIN",
                "REVIEW_REQUIRED",
                "VERIFICATION_FAILED",
                "UNSUPPORTED",
            }
            import re

            if any(
                not isinstance(k, str)
                or not re.fullmatch(r"[0-9a-f]{64}", k)
                or not isinstance(v, list)
                or not all(isinstance(c, str) and c in allowed for c in v)
                for k, v in data["items"].items()
            ):
                raise PrivateError("PRIVATE_CONFIG_INVALID")
            self.review = data["items"]

    def reference(self, item: Attachment) -> str:
        message = json.dumps(
            [self.account, item.message_id, item.attachment_id, item.extension, item.size],
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        return hmac.new(self.key, message, hashlib.sha256).hexdigest()

    def approved(self, item: Attachment) -> bool:
        return self.decisions.get(self.reference(item)) == "PERSONAL"

    def decide(self, item: Attachment, decision: str, *, attest_personal: bool = False) -> None:
        if (
            not isinstance(decision, str)
            or decision not in {"PERSONAL", "EXCLUDE"}
            or (decision == "PERSONAL" and attest_personal is not True)
        ):
            raise PrivateError("ANNOTATION_CONSENT_REQUIRED")
        self.decisions[self.reference(item)] = decision
        write_private(
            self.path,
            (
                json.dumps({"schema_version": 1, "decisions": self.decisions}, sort_keys=True)
                + "\n"
            ).encode(),
            overwrite=self.path.exists(),
        )

    def needs_review(self, item: Attachment, reason: str) -> None:
        if reason not in {
            "UNREADABLE",
            "OCR_UNCERTAIN",
            "REVIEW_REQUIRED",
            "VERIFICATION_FAILED",
            "UNSUPPORTED",
        }:
            raise PrivateError("PRIVATE_CONFIG_INVALID")
        codes = self.review.setdefault(self.reference(item), [])
        if reason not in codes:
            codes.append(reason)
        write_private(
            self.review_path,
            (
                json.dumps({"schema_version": 1, "items": self.review}, sort_keys=True) + "\n"
            ).encode(),
            overwrite=self.review_path.exists(),
        )


def _format_matches(data: bytes, extension: str) -> bool:
    if extension == ".pdf":
        return data.startswith(b"%PDF-")
    if extension in {".docx", ".xlsx"}:
        return data.startswith(b"PK\x03\x04")
    if extension == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension in {".tif", ".tiff"}:
        return data.startswith((b"II*\x00", b"MM\x00*"))
    if extension == ".parquet":
        return data.startswith(b"PAR1") and data.endswith(b"PAR1")
    try:
        data.decode("utf-8-sig")
        return b"\x00" not in data
    except UnicodeError:
        return False


def _category(kind: str) -> str:
    if kind in {
        "DIAGNOSIS",
        "MEDICAL_CONDITION",
        "TREATMENT",
        "MEDICATION",
        "MEDICAL_HISTORY",
        "MEDICAL_ATTRIBUTE",
        "CLINICAL_OBSERVATION",
    }:
        return "health"
    if kind in {"API_KEY", "CREDENTIAL", "AUTH_TOKEN"}:
        return "credentials"
    if kind in {"AGE", "LOCATION", "DATE", "OCCUPATION", "DEMOGRAPHIC"}:
        return "quasi_identifier"
    if kind in {
        "PERSON",
        "ADDRESS",
        "EMAIL",
        "PHONE",
        "RFC",
        "CURP",
        "CLABE",
        "BANK_ACCOUNT",
        "PAYMENT_CARD",
        "PATIENT_ID",
        "CUSTOMER_ID",
        "EMPLOYEE_ID",
        "DATE_OF_BIRTH",
        "PASSPORT",
        "NATIONAL_ID",
        "DOCUMENT_ID",
        "REGIONAL_ID",
    }:
        return "personal"
    return "other"


@contextmanager
def _memory(metrics: OperationalMetrics) -> Iterator[None]:
    done = threading.Event()
    try:
        import psutil

        process = psutil.Process()

        def sample() -> None:
            while not done.is_set():
                try:
                    total = process.memory_info().rss
                    for child in process.children(recursive=True):
                        try:
                            total += child.memory_info().rss
                        except psutil.Error:
                            pass
                    metrics.peak_rss = max(metrics.peak_rss, total)
                except psutil.Error:
                    pass
                done.wait(0.05)

        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
    except ImportError:
        monitor = None
    try:
        yield
    finally:
        done.set()
        if monitor:
            monitor.join(timeout=1)


def benchmark(
    config: PrivateConfig,
    transport: GmailTransport,
    engine: Any,
    *,
    run: bool = False,
    external_terminal_ack: bool = False,
    synthetic_test: bool = False,
) -> dict[str, Any]:
    if synthetic_test:
        if getattr(transport, "synthetic_only", False) is not True:
            raise PrivateError("EXTERNAL_TERMINAL_REQUIRED")
    else:
        require_external_terminal(external_terminal_ack)
    metrics = OperationalMetrics()
    started = time.perf_counter()
    from deidflow import Policy

    hashes: set[bytes] = set()
    downloaded_bytes = 0
    with quiet_private_runtime(), _memory(metrics):
        approvals = PersonalApprovals(config)
        with temporary_workspace(Path(config.private_root)) as workspace:
            for item, _ in discovery(config, transport, metrics):
                if not approvals.approved(item):
                    metrics.counts["unapproved_attachments"] += 1
                    continue
                metrics.counts["personally_approved_attachments"] += 1
                if not run:
                    continue
                if downloaded_bytes + item.size > config.max_total_bytes:
                    metrics.truncated = True
                    break
                before = time.perf_counter()
                source = workspace / (secrets.token_hex(16) + item.extension)
                output = workspace / (secrets.token_hex(16) + item.extension)
                metrics.counts["processed_documents"] += 1
                unique_attempt = True
                try:
                    downloaded_bytes += item.size
                    data = attachment_bytes(transport, item, config)
                    digest = hashlib.sha256(data).digest()
                    if digest in hashes:
                        metrics.counts["content_duplicates"] += 1
                        metrics.counts["processed_documents"] -= 1
                        unique_attempt = False
                        continue
                    hashes.add(digest)
                    metrics.unique_content_documents = len(hashes)
                    metrics.processed_bytes += len(data)
                    if not _format_matches(data, item.extension):
                        raise PrivateError("PRIVATE_RESPONSE_INVALID")
                    write_private(source, data)
                    del data
                    graph = engine.read(source)
                    if not graph.complete:
                        metrics.counts["incomplete_documents"] += 1
                        metrics.counts["review_required_documents"] += 1
                        approvals.needs_review(item, "REVIEW_REQUIRED")
                    if any("ocr" in issue for issue in graph.issues):
                        metrics.counts["ocr_uncertain_documents"] += 1
                        approvals.needs_review(item, "OCR_UNCERTAIN")
                    pages = {
                        f.location.page for f in graph.fragments if f.location.page is not None
                    }
                    metrics.counts["approximate_pages_observed"] += len(pages)
                    categories: set[str] = set()
                    for fragment in graph.fragments:
                        found = (
                            engine.scan_ocr_text(fragment.text)
                            if fragment.kind == "ocr"
                            else engine.scan_text(fragment.text)
                        )
                        categories.update(_category(f.entity_type) for f in found)
                    for family in categories:
                        metrics.categories[family] += 1
                    policy = Policy.strict_pdf() if item.extension == ".pdf" else Policy.strict()
                    transformed = engine.deidentify(source, output=output, policy=policy)
                    state = str(transformed.status)
                    if state == "UNSUPPORTED":
                        metrics.counts["unsupported_attachments"] += 1
                        approvals.needs_review(item, "UNSUPPORTED")
                    elif state == "BLOCKED":
                        metrics.counts["verification_failed_documents"] += 1
                        approvals.needs_review(item, "VERIFICATION_FAILED")
                    elif state == "REVIEW_REQUIRED" and graph.complete:
                        metrics.counts["review_required_documents"] += 1
                        approvals.needs_review(item, "REVIEW_REQUIRED")
                    elif state == "APPROVED":
                        metrics.counts["approved_documents"] += 1
                except Exception:
                    metrics.counts["processing_failures"] += 1
                    metrics.counts["unreadable_or_encrypted_documents"] += 1
                    approvals.needs_review(item, "UNREADABLE")
                finally:
                    if unique_attempt:
                        metrics.latencies.append(time.perf_counter() - before)
                    source.unlink(missing_ok=True)
                    output.unlink(missing_ok=True)
    metrics.elapsed_seconds = time.perf_counter() - started
    return metrics.emit(
        mode="RUN" if run else "INVENTORY", seconds_per_attachment=config.seconds_per_attachment
    )
