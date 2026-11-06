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

import codecs
import email
import email.policy
import hashlib
import hmac
import mimetypes
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path
from typing import Any

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
     ".docx", ".xlsx", ".pdf"}
)  # fmt: skip
MAX_DEPTH = 8
_ID = re.compile(r"<[^<>\s]*>")
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

    def count(self, what: str, n: int = 1) -> None:
        if n:
            self.removed[what] = self.removed.get(what, 0) + n

    def issue(self, name: str) -> None:
        if name not in self.issues:
            self.issues.append(name)


def parse(data: bytes) -> EmailMessage:
    message = email.message_from_bytes(data, policy=email.policy.default)
    if not isinstance(message, EmailMessage):
        raise ValueError("Unsupported e-mail message")
    return message


def header_text(raw: Any) -> str:
    """A header value with RFC 2047 encoded words decoded, as a reader sees it."""
    value = str(raw)
    try:
        return str(make_header(decode_header(value)))
    except (ValueError, LookupError, UnicodeError):
        return value


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
) -> tuple[bytes, MailReport]:
    report = MailReport()
    message = parse(data)
    _rewrite_part(message, report, rewrite, whole, attachment, rewrite_html, key, remove_media, 0)
    return message.as_bytes(policy=email.policy.default), report


_ENCODINGS = frozenset({"7bit", "8bit", "binary", "base64", "quoted-printable"})
_MIME_TYPE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}")
_LANGUAGES = re.compile(
    r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*(?:\s*,\s*[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*)*"
)


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
        related = part.get_param("type") if part.get_content_type() == "multipart/related" else None
        return cls(
            part.get_content_type(),
            charset if charset and re.fullmatch(r"[\w.:-]{1,40}", charset) else None,
            related if isinstance(related, str) and _MIME_TYPE.fullmatch(related.lower()) else None,
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
            text = value.strip()
            return text if _LANGUAGES.fullmatch(text) else None
        return None


def _rewrite_headers(
    part: EmailMessage,
    report: MailReport,
    rewrite: Rewrite,
    whole: Whole,
    key: bytes,
    structure: _Structure,
) -> None:
    spelled: dict[str, str] = {}
    for original in part.keys():
        spelled.setdefault(original.lower(), original)
    for name, original in spelled.items():
        values = [header_text(v) for v in part.get_all(name, [])]
        del part[name]
        if name not in KEPT_HEADERS:
            report.count("trace_and_vendor_headers" if name != "date" else "date", len(values))
            continue
        for value in values:
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
                value = _ID.sub(lambda m: _pseudonymous_id(m.group(), key), value)
                if "<" not in value:
                    value = _pseudonymous_id(value, key)
            elif name in STRUCTURE_HEADERS:
                rebuilt = structure.header(name, value)
                if rebuilt is None:
                    report.count("structure_parameters")
                    continue
                if rebuilt != value:
                    report.count("structure_parameters")
                value = rebuilt
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
) -> bool:
    """Rewrite ``part`` in place; False when the part must be removed."""
    if depth > MAX_DEPTH:
        raise ValueError("E-mail nesting limit exceeded")
    structure = _Structure.of(part)
    _rewrite_headers(part, report, rewrite, whole, key, structure)
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
            )  # fmt: skip
        ]
        payload[:] = kept
        return True
    if content_type == "message/rfc822":
        inner = part.get_payload()
        if isinstance(inner, list) and inner and isinstance(inner[0], EmailMessage):
            _rewrite_part(
                inner[0], report, rewrite, whole, attachment, rewrite_html, key, remove_media,
                depth + 1,
            )  # fmt: skip
        return True
    disposition = part.get_content_disposition()
    if content_type in {"text/plain", "text/html"} and disposition != "attachment":
        text = part.get_content()
        if content_type == "text/plain":
            new, mappings = rewrite(text)
            report.transformations += len(mappings)
        else:
            new = rewrite_html(text)
        # Always reset the content headers: a body part may carry a file name.
        part.set_content(new, subtype=content_type.split("/", 1)[1], charset="utf-8")
        return True
    if content_type.startswith(("image/", "audio/", "video/")):
        if remove_media:
            report.count("media")
            return False
        report.issue("email_media_requires_review")
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
        if not output.exists() or status == "BLOCKED":
            report.count("blocked_attachments")
            report.issue("EMAIL_ATTACHMENT_REMOVED")
            return False
        safe = output.read_bytes()
    if status != "APPROVED":
        report.issue("EMAIL_ATTACHMENT_REVIEW_REQUIRED")
    index = report.removed.get("attachments_renamed", 0) + 1
    report.count("attachments_renamed")
    maintype, subtype = content_type.split("/", 1)
    filename = f"adjunto-{index}{suffix}"
    params = {"charset": "utf-8"} if maintype == "text" else None
    part.set_content(safe, maintype=maintype, subtype=subtype, filename=filename, params=params)
    return True


def attachment_bytes(part: EmailMessage) -> bytes:
    """The attachment's bytes as sent (transfer encoding removed, no charset guess)."""
    payload = part.get_payload(decode=True)
    return payload if isinstance(payload, bytes) else b""


__all__ = [
    "KEPT_HEADERS",
    "MailReport",
    "attachment_bytes",
    "header_text",
    "parse",
    "rewrite_message",
    "split_addresses",
]
