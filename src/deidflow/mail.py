"""De-identify RFC 5322 e-mail messages (``.eml``): headers, bodies and attachments.

Headers are kept on an allowlist. Address headers keep their structure with each
display name transformed as a person and each address as an e-mail; subjects are
scanned as text; message identifiers become keyed pseudonyms so replies still
thread. Trace and vendor headers (``Received``, ``X-*``, ``DKIM-Signature``,
``Authentication-Results``...), which hold IP addresses, host names and mailbox
details, and the ``Date`` header are removed. Text and HTML bodies are rewritten
in place; attachments are renamed and de-identified with the engine's own file
path, or removed when their format is unsupported or their result is blocked.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import email
import email.policy
import hashlib
import hmac
import mimetypes
import quopri
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from email.feedparser import BytesFeedParser
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path
from typing import Any, cast

from deidflow.core import Fragment

# rewrite(text) -> (output, [(source_start, source_end, replacement), ...])
Rewrite = Callable[[str], tuple[str, list[tuple[int, int, str]]]]
# whole(value, entity_type) -> transformed value (the whole value is the entity)
Whole = Callable[[str, str], str]
# attachment(source, output) -> (status, issues); output exists when it was written
Attachment = Callable[[Path, Path], tuple[str, list[str]]]

ADDRESS_HEADERS = frozenset(
    {"from", "to", "cc", "bcc", "reply-to", "sender", "return-path", "delivered-to",
     "resent-from", "resent-to", "resent-cc", "resent-bcc", "resent-sender",
     "disposition-notification-to"}
)  # fmt: skip
TEXT_HEADERS = frozenset({"subject", "comments", "keywords", "thread-topic", "content-description"})
# Content-ID values often embed the sender's host name; they become pseudonyms too.
ID_HEADERS = frozenset(
    {"message-id", "in-reply-to", "references", "resent-message-id", "content-id"}
)
STRUCTURE_HEADERS = frozenset(
    {"mime-version", "content-type", "content-transfer-encoding", "content-disposition",
     "content-language"}
)  # fmt: skip
KEPT_HEADERS = ADDRESS_HEADERS | TEXT_HEADERS | ID_HEADERS | STRUCTURE_HEADERS
ATTACHMENT_SUFFIXES = frozenset(
    {".txt", ".text", ".md", ".log", ".csv", ".tsv", ".json", ".jsonl", ".html", ".htm",
     ".docx", ".xlsx", ".odt", ".ods", ".pdf"}
)  # fmt: skip
MAX_DEPTH = 8
MAX_PARTS = 512
MAX_BYTES = 64 * 1024 * 1024
MAX_HEADER_BYTES = 65_536
MAX_HEADERS = 8192
_ID = re.compile(r"<[^<>\s]*>")
_BOUNDARY_PARAMETER = re.compile(r';\s*boundary\s*=\s*"([^"\r\n]*)"', re.IGNORECASE)
# Applied to a stripped item. Each part is a single reading (the name excludes "<",
# quotes and commas; spaces before "<" belong to the name and are stripped later), so
# a failed match is linear even on very long headers.
_ADDRESS = re.compile(
    r'(?:(?P<name>"(?:[^"\\]|\\.)*"[ \t]*|[^<>,"]*)<(?P<angle>[^<>]*)>|(?P<bare>[^,<>"\s]+))'
)


@dataclass
class MailReport:
    transformations: int = 0
    removed: dict[str, int] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    # Ephemeral provenance from this rewrite only. Never included in Result.audit,
    # serialized as a public receipt or inferred from the spelling of source text.
    _generated_ids: set[str] = field(default_factory=set, repr=False)
    _generated_boundaries: set[str] = field(default_factory=set, repr=False)

    def count(self, what: str, n: int = 1) -> None:
        if n:
            self.removed[what] = self.removed.get(what, 0) + n

    def issue(self, name: str) -> None:
        if name not in self.issues:
            self.issues.append(name)

    def _generated_spans(self, fragment: Fragment) -> list[tuple[int, int]]:
        """Exact minted spans in their structural header location, never body text."""
        if fragment.kind != "email_header" or fragment.location.part != "header":
            return []
        name = fragment.metadata.get("name")
        if name in ID_HEADERS:
            return [
                (match.start(), match.end())
                for match in _ID.finditer(fragment.text)
                if match.group() in self._generated_ids
            ]
        if name == "content-type":
            return [
                (match.start(1), match.end(1))
                for match in _BOUNDARY_PARAMETER.finditer(fragment.text)
                if match.group(1) in self._generated_boundaries
            ]
        return []


@dataclass
class _OutputBudget:
    remaining: int

    def consume(self, size: int) -> None:
        if size > self.remaining:
            raise ValueError("E-mail output size limit exceeded")
        self.remaining -= size


class _BoundedParser(BytesFeedParser):
    """Stop the stdlib parser before it recursively enters excess MIME parts."""

    _msgstack: list[EmailMessage]  # stdlib parser state, not exposed by typeshed

    def __init__(self, max_parts: int, max_depth: int) -> None:
        super().__init__(policy=email.policy.default)
        self._part_limit, self._depth_limit, self._parts_seen = max_parts, max_depth, 0

    def _new_message(self) -> None:
        self._parts_seen += 1
        if self._parts_seen > self._part_limit or len(self._msgstack) > self._depth_limit:
            raise ValueError("E-mail structure limit exceeded")
        super()._new_message()  # type: ignore[misc]  # stdlib recursion hook


def parse(
    data: bytes,
    *,
    max_bytes: int = MAX_BYTES,
    max_parts: int = MAX_PARTS,
    max_depth: int = MAX_DEPTH,
    max_decoded_bytes: int | None = None,
) -> EmailMessage:
    if max_bytes < 1 or max_parts < 1 or max_depth < 0 or len(data) > max_bytes:
        raise ValueError("E-mail size limit exceeded")
    parser = _BoundedParser(max_parts, max_depth)
    try:
        parser.feed(data)
        message = parser.close()
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Malformed e-mail message") from exc
    if not isinstance(message, EmailMessage):
        raise ValueError("Unsupported e-mail message")
    decoded_limit = max_bytes if max_decoded_bytes is None else max_decoded_bytes
    if decoded_limit < 1:
        raise ValueError("E-mail decoded size limit exceeded")
    _validate_payloads(message, max_bytes=decoded_limit)
    return message


def header_text(raw: Any) -> str:
    """A header value with RFC 2047 encoded words decoded, as a reader sees it."""
    value = re.sub(r"\r?\n[ \t]+", " ", str(raw))
    try:
        value.encode("utf-8", errors="strict")
        if "\r" in value or "\n" in value:
            raise ValueError("Malformed e-mail header")
        words = re.compile(r"=\?([^?\s]+)\?([bBqQ])\?([^?]*)\?=")
        if "=?" in words.sub("", value):
            raise ValueError("Malformed encoded e-mail header")
        for word in words.finditer(value):
            charset, encoding, encoded = word.groups()
            codecs.lookup(charset)
            if encoding.lower() == "b":
                base64.b64decode(encoded.encode("ascii"), validate=True).decode(charset)
            else:
                if re.search(r"=(?![0-9a-fA-F]{2})", encoded):
                    raise ValueError("Malformed encoded e-mail header")
                quopri.decodestring(encoded.replace("_", " ").encode("ascii")).decode(charset)
        for chunk, charset in decode_header(value):
            if isinstance(chunk, bytes):
                chunk.decode(charset or "ascii", errors="strict")
        return str(make_header(decode_header(value)))
    except (ValueError, LookupError, UnicodeError, binascii.Error):
        raise ValueError("Malformed encoded e-mail header") from None


def split_addresses(value: str) -> list[tuple[str, str]]:
    """(display name, address) pairs of an address list, tolerant of placeholders."""
    pairs = []
    for item in _split_list(value):
        item = item.strip()
        match = _ADDRESS.fullmatch(item)
        if match is None:
            pairs.append(("", item.strip()))
        elif match.group("bare") is not None:
            pairs.append(("", match.group("bare")))
        else:
            name = match.group("name").strip()
            if name.startswith('"') and name.endswith('"') and len(name) >= 2:
                name = re.sub(r"\\(.)", r"\1", name[1:-1])
            pairs.append((name, match.group("angle").strip()))
    return pairs


def _split_list(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quoted, depth = False, 0
    previous = ""
    for character in value:
        if character == '"' and previous != "\\":
            quoted = not quoted
        elif not quoted and character == "<":
            depth += 1
        elif not quoted and character == ">":
            depth = max(0, depth - 1)
        if character == "," and not quoted and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(character)
        previous = character
    items.append("".join(current))
    return [item for item in items if item.strip()]


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def rewrite_message(
    data: bytes,
    *,
    rewrite: Rewrite,
    whole: Whole,
    attachment: Attachment,
    rewrite_html: Callable[[str], str],
    key: bytes,
    remove_media: bool = True,
    max_bytes: int = MAX_BYTES,
    max_parts: int = MAX_PARTS,
    max_depth: int = MAX_DEPTH,
    max_decoded_bytes: int | None = None,
) -> tuple[bytes, MailReport]:
    report = MailReport()
    message = parse(
        data,
        max_bytes=max_bytes,
        max_parts=max_parts,
        max_depth=max_depth,
        max_decoded_bytes=max_decoded_bytes,
    )
    if not _rewrite_part(
        message,
        report,
        rewrite,
        whole,
        attachment,
        rewrite_html,
        key,
        remove_media,
        0,
        _OutputBudget(max_bytes),
    ):
        raise ValueError("Unsupported e-mail root content")
    output = message.as_bytes(policy=email.policy.default)
    if len(output) > max_bytes:
        raise ValueError("E-mail output size limit exceeded")
    # The serializer chooses new boundaries after _rewrite_headers has removed
    # every source boundary. Record the actual values it minted, not a pattern.
    report._generated_boundaries.update(
        boundary for part in message.walk() if (boundary := part.get_boundary()) is not None
    )
    return output, report


_ENCODINGS = frozenset({"7bit", "8bit", "binary", "base64", "quoted-printable"})
_MULTIPART_TYPES = frozenset({"multipart/mixed", "multipart/alternative", "multipart/related"})
_MEDIA_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        "video/mp4",
        "video/webm",
    }
)
_ATTACHMENT_TYPES = {
    ".txt": "text/plain",
    ".text": "text/plain",
    ".md": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".html": "text/html",
    ".htm": "text/html",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf": "application/pdf",
}


def _decoded_bytes(part: EmailMessage) -> bytes:
    """Strict decoding: never silently ignore malformed trailing payload bytes."""
    encoding = str(part.get("content-transfer-encoding", "7bit")).strip().lower()
    if encoding not in _ENCODINGS:
        raise ValueError("Unsupported e-mail transfer encoding")
    payload = part.get_payload()
    if not isinstance(payload, str):
        raise ValueError("Invalid e-mail leaf payload")
    if encoding in {"base64", "quoted-printable"}:
        try:
            encoded = payload.encode("ascii")
            if encoding == "base64":
                return base64.b64decode(re.sub(rb"[ \t\r\n]", b"", encoded), validate=True)
            if re.search(rb"=(?![0-9a-fA-F]{2}|\r?\n)", encoded):
                raise ValueError("Invalid quoted-printable payload")
            return quopri.decodestring(encoded)
        except (UnicodeError, binascii.Error):
            raise ValueError("Malformed encoded e-mail payload") from None
    raw = part.get_payload(decode=True)
    if not isinstance(raw, bytes) or (encoding == "7bit" and any(b > 127 for b in raw)):
        raise ValueError("Malformed e-mail payload")
    return raw


def _text_content(part: EmailMessage) -> str:
    try:
        return _decoded_bytes(part).decode(part.get_content_charset() or "ascii", errors="strict")
    except (UnicodeError, LookupError):
        raise ValueError("Unsupported e-mail text encoding") from None


def _validate_payloads(message: EmailMessage, *, max_bytes: int) -> None:
    decoded_total = 0
    header_count = 0
    pending = [message]
    while pending:
        part = pending.pop()
        for name, value in part.raw_items():
            header_count += 1
            if header_count > MAX_HEADERS or len(name) > 128 or len(value) > MAX_HEADER_BYTES:
                raise ValueError("E-mail header limit exceeded")
        if part.defects:
            raise ValueError("Malformed MIME message")
        payload = part.get_payload()
        content_type = part.get_content_type()
        if isinstance(payload, list):
            if content_type == "message/rfc822":
                encoding = str(part.get("content-transfer-encoding", "7bit")).strip().lower()
                if len(payload) != 1 or encoding not in {"7bit", "8bit", "binary"}:
                    raise ValueError("Unsupported encapsulated message")
            elif not content_type.startswith("multipart/"):
                raise ValueError("Unsupported structured MIME payload")
            if not payload or any(not isinstance(child, EmailMessage) for child in payload):
                raise ValueError("Invalid multipart message")
            pending.extend(cast(list[EmailMessage], payload))
        else:
            if content_type.startswith("multipart/") or content_type == "message/rfc822":
                raise ValueError("Malformed multipart message")
            decoded_total += len(_decoded_bytes(part))
            if decoded_total > max_bytes:
                raise ValueError("E-mail decoded size limit exceeded")
            if content_type in {"text/plain", "text/html"} and (
                part.get_content_disposition() != "attachment"
            ):
                _text_content(part)


@dataclass(frozen=True)
class _Structure:
    """MIME structure read before any header is rewritten."""

    content_type: str
    charset: str | None
    related_type: str | None
    disposition: str | None
    filename: str | None

    @classmethod
    def of(cls, part: EmailMessage) -> _Structure:
        charset = part.get_content_charset()
        try:
            if charset is not None:
                codecs.lookup(charset)
        except LookupError:
            charset = None
        content_type = part.get_content_type()
        if content_type.startswith("multipart/") and content_type not in _MULTIPART_TYPES:
            content_type = "multipart/mixed"
        return cls(
            content_type,
            charset if charset and re.fullmatch(r"[\w.:-]{1,40}", charset) else None,
            None,
            part.get_content_disposition(),
            part.get_filename(),
        )

    def header(self, name: str, value: str) -> str | None:
        """Rebuild a structural header from validated values only (no comments)."""
        if name == "mime-version":
            return "1.0"
        if name == "content-type":
            parameters = ""
            if self.content_type.startswith("text/") and self.charset:
                parameters = f'; charset="{self.charset}"'
            elif self.related_type:
                parameters = f'; type="{self.related_type}"'
            # No boundary: the generator writes a fresh random one.
            return self.content_type + parameters
        if name == "content-transfer-encoding":
            token = value.strip().lower()
            return token if token in _ENCODINGS else None
        if name == "content-disposition":
            return self.disposition if self.disposition in {"inline", "attachment"} else None
        if name == "content-language":
            # Language tags are free-form caller input, not trusted metadata.
            return None
        return None


def _rewrite_headers(
    part: EmailMessage,
    report: MailReport,
    rewrite: Rewrite,
    whole: Whole,
    key: bytes,
    structure: _Structure,
    budget: _OutputBudget,
) -> None:
    spelled: dict[str, str] = {}
    raw_values: dict[str, list[str]] = {}
    for original, raw in part.raw_items():
        spelled.setdefault(original.lower(), original)
        raw_values.setdefault(original.lower(), []).append(raw)
    for name, original in spelled.items():
        values = raw_values[name]
        del part[name]
        if name not in KEPT_HEADERS:
            report.count("trace_and_vendor_headers" if name != "date" else "date", len(values))
            continue
        for value in values:
            value = header_text(value)
            if name in ADDRESS_HEADERS:
                rendered = []
                for display, address in split_addresses(value):
                    pieces = []
                    if display.strip():
                        pieces.append(_quote(whole(display, "PERSON")))
                        report.transformations += 1
                    if address:
                        pieces.append("<" + whole(address, "EMAIL") + ">")
                        report.transformations += 1
                    rendered.append(" ".join(pieces))
                value = ", ".join(rendered)
            elif name in TEXT_HEADERS:
                new, mappings = rewrite(value)
                report.transformations += len(mappings)
                value = new
            elif name in ID_HEADERS:
                identifiers = _ID.findall(value)
                generated = [_pseudonymous_id(item, key) for item in identifiers or [value]]
                report._generated_ids.update(generated)
                value = " ".join(generated)
            elif name in STRUCTURE_HEADERS:
                rebuilt = structure.header(name, value)
                if rebuilt is None:
                    report.count("structure_parameters")
                    continue
                if rebuilt != value:
                    report.count("structure_parameters")
                value = rebuilt
            budget.consume(len(value.encode("utf-8")) + len(original) + 4)
            part[original] = value


def _pseudonymous_id(value: str, key: bytes) -> str:
    digest = hmac.new(key, value.strip().encode("utf-8", "surrogatepass"), hashlib.sha256)
    return "<df" + digest.hexdigest()[:24] + "@deidflow>"


def _filename_suffix(part: EmailMessage, filename: str | None) -> str:
    name = filename or ""
    suffix = Path(name).suffix.lower()
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(part.get_content_type()) or ""
    return guessed.lower()


def _rewrite_part(
    part: EmailMessage,
    report: MailReport,
    rewrite: Rewrite,
    whole: Whole,
    attachment: Attachment,
    rewrite_html: Callable[[str], str],
    key: bytes,
    remove_media: bool,
    depth: int,
    budget: _OutputBudget,
) -> bool:
    """Rewrite ``part`` in place; False when the part must be removed."""
    if depth > MAX_DEPTH:
        raise ValueError("E-mail nesting limit exceeded")
    structure = _Structure.of(part)
    if part.get_content_type().startswith("multipart/") and (
        part.get_content_type() not in _MULTIPART_TYPES
    ):
        report.issue("EMAIL_MULTIPART_NORMALIZED")
    _rewrite_headers(part, report, rewrite, whole, key, structure, budget)
    content_type = structure.content_type
    if part.is_multipart():
        # Text before the first and after the last boundary is never displayed.
        for field_name in ("preamble", "epilogue"):
            if getattr(part, field_name):
                setattr(part, field_name, None)
                report.count("preamble_and_epilogue")
        payload = part.get_payload()
        assert isinstance(payload, list)
        kept = [
            child
            for child in payload
            if isinstance(child, EmailMessage)
            and _rewrite_part(
                child,
                report,
                rewrite,
                whole,
                attachment,
                rewrite_html,
                key,
                remove_media,
                depth + 1,
                budget,
            )  # fmt: skip
        ]
        payload[:] = kept
        return bool(kept)
    if content_type == "message/rfc822":
        inner = part.get_payload()
        if isinstance(inner, list) and inner and isinstance(inner[0], EmailMessage):
            _rewrite_part(
                inner[0], report, rewrite, whole, attachment, rewrite_html, key, remove_media,
                depth + 1,
                budget,
            )  # fmt: skip
        raise ValueError("Malformed encapsulated message")
    disposition = part.get_content_disposition()
    if content_type in {"text/plain", "text/html"} and disposition != "attachment":
        text = _text_content(part)
        if content_type == "text/plain":
            new, mappings = rewrite(text)
            report.transformations += len(mappings)
        else:
            new = rewrite_html(text)
        budget.consume(len(new.encode("utf-8")))
        # Always reset the content headers: a body part may carry a file name.
        part.set_content(new, subtype=content_type.split("/", 1)[1], charset="utf-8")
        return True
    if content_type.startswith(("image/", "audio/", "video/")):
        if remove_media or content_type not in _MEDIA_TYPES:
            report.count("media")
            if not remove_media:
                report.issue("EMAIL_ATTACHMENT_REMOVED")
            return False
        report.issue("email_media_requires_review")
        budget.consume(len(_decoded_bytes(part)))
        return True
    suffix = _filename_suffix(part, structure.filename)
    if suffix not in ATTACHMENT_SUFFIXES:
        report.count("unsupported_attachments")
        report.issue("EMAIL_ATTACHMENT_REMOVED")
        return False
    raw = attachment_bytes(part)
    with tempfile.TemporaryDirectory(prefix="deidflow-mail-") as folder:
        source = Path(folder) / ("adjunto" + suffix)
        output = Path(folder) / ("adjunto.safe" + suffix)
        source.write_bytes(raw)
        status, issues = attachment(source, output)
        if not output.exists() or status not in {"APPROVED", "REVIEW_REQUIRED"}:
            report.count("blocked_attachments")
            report.issue("EMAIL_ATTACHMENT_REMOVED")
            return False
        budget.consume(output.stat().st_size)
        safe = output.read_bytes()
    if status != "APPROVED":
        report.issue("EMAIL_ATTACHMENT_REVIEW_REQUIRED")
    index = report.removed.get("attachments_renamed", 0) + 1
    report.count("attachments_renamed")
    maintype, subtype = _ATTACHMENT_TYPES[suffix].split("/", 1)
    filename = f"adjunto-{index}{suffix}"
    params = {"charset": "utf-8"} if maintype == "text" else None
    part.set_content(safe, maintype=maintype, subtype=subtype, filename=filename, params=params)
    return True


def attachment_bytes(part: EmailMessage) -> bytes:
    """The attachment's bytes as sent (transfer encoding removed, no charset guess)."""
    return _decoded_bytes(part)


__all__ = [
    "KEPT_HEADERS",
    "MailReport",
    "attachment_bytes",
    "header_text",
    "parse",
    "rewrite_message",
    "split_addresses",
]
