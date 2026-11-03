"""Official read-only Gmail REST access, invoked only by an external private runner."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field, fields
from datetime import date
from email.utils import getaddresses
from pathlib import Path
from typing import Any, Protocol

from .security import (
    PrivateError,
    private_path,
    protect,
    require_external_terminal,
    secure_directory,
    write_private,
)

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_MAP = {
    ".pdf": ("pdf", {"application/pdf"}),
    ".docx": ("docx", {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ".xlsx": ("xlsx", {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    ".csv": ("csv", {"text/csv", "application/csv"}),
    ".tsv": ("tsv", {"text/tab-separated-values"}),
    ".txt": ("txt", {"text/plain"}),
    ".json": ("json", {"application/json"}),
    ".jsonl": ("jsonl", {"application/x-ndjson", "application/jsonl", "text/plain"}),
    ".parquet": ("parquet", {"application/vnd.apache.parquet", "application/parquet"}),
    ".png": ("png", {"image/png"}),
    ".jpg": ("jpeg", {"image/jpeg"}),
    ".jpeg": ("jpeg", {"image/jpeg"}),
    ".tif": ("tiff", {"image/tiff"}),
    ".tiff": ("tiff", {"image/tiff"}),
}
DEFAULT_DOMAINS = ("bbva.com", "bbva.mx", "bbva.com.mx", "grupobbva.com", "bbva.es")
DEFAULT_TERMS = (
    "bbva",
    "corporativo",
    "corporate",
    "confidencial",
    "confidential",
    "reporte interno",
    "internal report",
    "nómina",
    "nomina",
    "empleado",
    "employee",
    "vpn",
    "intranet",
)


def strict_json(data: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        return json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except Exception:
        raise PrivateError("PRIVATE_CONFIG_INVALID") from None


@dataclass(frozen=True)
class PrivateConfig:
    account: str = field(repr=False)
    private_root: str = field(repr=False)
    token_file: str = field(repr=False)
    personal_senders: tuple[str, ...] = field(repr=False)
    client_secret_file: str | None = field(default=None, repr=False)
    excluded_domains: tuple[str, ...] = DEFAULT_DOMAINS
    excluded_senders: tuple[str, ...] = field(default=(), repr=False)
    excluded_subject_terms: tuple[str, ...] = DEFAULT_TERMS
    allowed_extensions: tuple[str, ...] = tuple(_MAP)
    after: str | None = None
    before: str | None = None
    max_messages: int = 1000
    max_attachments: int = 100
    max_attachments_per_message: int = 20
    max_attachment_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    seconds_per_attachment: float | None = None
    approval_file: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.account, str)
            or not _EMAIL.fullmatch(self.account)
            or self.account.rsplit("@", 1)[1].lower() not in {"gmail.com", "googlemail.com"}
        ):
            raise PrivateError("PERSONAL_ACCOUNT_REQUIRED")
        if (
            not isinstance(self.personal_senders, tuple)
            or not self.personal_senders
            or not all(isinstance(v, str) and _EMAIL.fullmatch(v) for v in self.personal_senders)
        ):
            raise PrivateError("PRIVATE_CONFIG_INVALID")
        for key in (
            "excluded_domains",
            "excluded_senders",
            "excluded_subject_terms",
            "allowed_extensions",
        ):
            values = getattr(self, key)
            if not isinstance(values, tuple) or not all(isinstance(v, str) and v for v in values):
                raise PrivateError("PRIVATE_CONFIG_INVALID")
        if not set(self.allowed_extensions) <= set(_MAP) or not self.allowed_extensions:
            raise PrivateError("PRIVATE_CONFIG_INVALID")
        limits = {
            "max_messages": (1, 10000),
            "max_attachments": (1, 10000),
            "max_attachments_per_message": (1, 100),
            "max_attachment_bytes": (1, 64 * 1024 * 1024),
            "max_total_bytes": (1, 4 * 1024**3),
        }
        if any(
            type(getattr(self, k)) is not int or not lo <= getattr(self, k) <= hi
            for k, (lo, hi) in limits.items()
        ):
            raise PrivateError("PRIVATE_CONFIG_INVALID")
        try:
            if self.after is not None:
                date.fromisoformat(self.after)
            if self.before is not None:
                date.fromisoformat(self.before)
            if self.after and self.before and self.after >= self.before:
                raise ValueError
            if self.seconds_per_attachment is not None:
                import math

                if (
                    type(self.seconds_per_attachment) not in {int, float}
                    or not math.isfinite(self.seconds_per_attachment)
                    or not 0 < self.seconds_per_attachment < 86400
                ):
                    raise ValueError
            for value in (
                self.private_root,
                self.token_file,
                self.client_secret_file,
                self.approval_file,
            ):
                if value is not None:
                    if not isinstance(value, str):
                        raise ValueError
                    private_path(value)
        except (TypeError, ValueError):
            raise PrivateError("PRIVATE_CONFIG_INVALID") from None

    @classmethod
    def load(cls, path: str | Path) -> PrivateConfig:
        try:
            source = private_path(path)
            if source.stat().st_size > 64 * 1024:
                raise ValueError
            protect(source, directory=False)
            data = strict_json(source.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
                raise ValueError
            for key in (
                "personal_senders",
                "excluded_domains",
                "excluded_senders",
                "excluded_subject_terms",
                "allowed_extensions",
            ):
                if key in data:
                    if not isinstance(data[key], list):
                        raise ValueError
                    data[key] = tuple(data[key])
            return cls(**data)
        except PrivateError:
            raise
        except Exception:
            raise PrivateError("PRIVATE_CONFIG_INVALID") from None


class GmailTransport(Protocol):
    def get(
        self, path: str, *, params: dict[str, Any] | None = None, max_bytes: int = 1_000_000
    ) -> dict[str, Any]: ...


class GoogleReadOnlyTransport:
    """Only GET requests to fixed Gmail resource paths; response bodies are bounded."""

    def __init__(self, credentials: Any) -> None:
        try:
            if set(credentials.scopes or ()) != {SCOPE}:
                raise PrivateError("READ_ONLY_SCOPE_REQUIRED")
            if credentials.granted_scopes is not None and set(credentials.granted_scopes) != {
                SCOPE
            }:
                raise PrivateError("READ_ONLY_SCOPE_REQUIRED")
            from google.auth.transport.requests import AuthorizedSession

            self.session = AuthorizedSession(credentials)
        except PrivateError:
            raise
        except Exception:
            raise PrivateError("PRIVATE_AUTH_REQUIRED") from None

    def get(
        self, path: str, *, params: dict[str, Any] | None = None, max_bytes: int = 1_000_000
    ) -> dict[str, Any]:
        if not re.fullmatch(
            r"profile|messages|messages/[A-Za-z0-9_-]+(?:/attachments/[A-Za-z0-9_-]+)?", path
        ):
            raise PrivateError("PRIVATE_API_FAILED")
        try:
            with self.session.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/" + path,
                params=params,
                timeout=60,
                stream=True,
                allow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise ValueError
                chunks, size = [], 0
                for block in response.iter_content(64 * 1024):
                    size += len(block)
                    if size > max_bytes:
                        raise ValueError
                    chunks.append(block)
            data = strict_json(b"".join(chunks).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except Exception:
            raise PrivateError("PRIVATE_API_FAILED") from None


def _validate_account(transport: GmailTransport, expected: str) -> None:
    try:
        value = transport.get("profile", params={"fields": "emailAddress"})
        actual = value.get("emailAddress")
        if (
            not isinstance(actual, str)
            or actual.lower() != expected.lower()
            or actual.rsplit("@", 1)[-1].lower() not in {"gmail.com", "googlemail.com"}
        ):
            raise ValueError
    except Exception:
        raise PrivateError("PERSONAL_ACCOUNT_REQUIRED") from None


def connect(
    config: PrivateConfig, *, authorize: bool = False, external_terminal_ack: bool = False
) -> GoogleReadOnlyTransport:
    """Use intended OAuth credential files only, never browser/session secrets."""
    require_external_terminal(external_terminal_ack)
    try:
        from google.oauth2.credentials import Credentials

        token = private_path(config.token_file)
        if authorize:
            if config.client_secret_file is None or token.exists():
                raise PrivateError("PRIVATE_AUTH_REQUIRED")
            secret = private_path(config.client_secret_file)
            if secret.stat().st_size > 64 * 1024:
                raise ValueError
            protect(secret, directory=False)
            info = strict_json(secret.read_text(encoding="utf-8"))
            installed = info.get("installed", {})
            if (
                installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth"
                or installed.get("token_uri") != "https://oauth2.googleapis.com/token"
            ):
                raise ValueError
            from google_auth_oauthlib.flow import InstalledAppFlow

            flow = InstalledAppFlow.from_client_config(
                info, scopes=[SCOPE], autogenerate_code_verifier=True
            )
            credentials = flow.run_local_server(
                host="127.0.0.1",
                port=0,
                open_browser=True,
                authorization_prompt_message="",
                success_message="Local authorization complete. Close this tab.",
                login_hint=config.account,
                prompt="select_account",
                include_granted_scopes="false",
                timeout_seconds=180,
            )
        else:
            if not token.is_file() or token.stat().st_size > 64 * 1024:
                raise PrivateError("PRIVATE_AUTH_REQUIRED")
            protect(token, directory=False)
            info = strict_json(token.read_text(encoding="utf-8"))
            if (
                set(info.get("scopes", ())) != {SCOPE}
                or info.get("token_uri") != "https://oauth2.googleapis.com/token"
            ):
                raise PrivateError("READ_ONLY_SCOPE_REQUIRED")
            credentials = Credentials.from_authorized_user_info(info, scopes=[SCOPE])
        transport = GoogleReadOnlyTransport(credentials)
        _validate_account(transport, config.account)
        # Refreshes stay within the intended OAuth mechanism. Do not persist a
        # newly authenticated credential until the personal-account gate passes.
        if authorize:
            secure_directory(token.parent)
            write_private(token, credentials.to_json().encode())
        return transport
    except PrivateError:
        raise
    except Exception:
        raise PrivateError("PRIVATE_AUTH_FAILED") from None


@dataclass(frozen=True)
class Attachment:
    message_id: str = field(repr=False)
    attachment_id: str = field(repr=False)
    extension: str
    format: str
    size: int


def _domain_blocked(address: str, config: PrivateConfig) -> bool:
    domain = address.rsplit("@", 1)[-1].lower()
    # Employer exclusions cannot be removed by an empty user configuration.
    return (
        any(
            domain == d or domain.endswith("." + d)
            for d in (*DEFAULT_DOMAINS, *config.excluded_domains)
        )
        or "bbva" in domain
    )


def personal_message(metadata: dict[str, Any], config: PrivateConfig) -> bool:
    try:
        headers = metadata["payload"]["headers"]
        if not isinstance(headers, list) or len(headers) > 100:
            return False
        values: dict[str, list[str]] = {}
        for header in headers:
            if (
                not isinstance(header, dict)
                or not isinstance(header.get("name"), str)
                or not isinstance(header.get("value"), str)
            ):
                return False
            values.setdefault(header["name"].lower(), []).append(header["value"])
        senders = [a.lower() for _, a in getaddresses(values.get("from", []))]
        recipients = [
            a.lower() for _, a in getaddresses(values.get("to", []) + values.get("cc", []))
        ]
        if len(senders) != 1 or senders[0] not in {s.lower() for s in config.personal_senders}:
            return False
        if senders[0] in {s.lower() for s in config.excluded_senders} or any(
            _domain_blocked(a, config) for a in senders + recipients
        ):
            return False
        subject = " ".join(values.get("subject", [])).casefold()
        if not subject or any(
            term.casefold() in subject for term in (*DEFAULT_TERMS, *config.excluded_subject_terms)
        ):
            return False
        return True
    except Exception:
        return False


def metadata_fields(depth: int = 8) -> str:
    # Keep a harmless sentinel for deeper nesting so traversal fails closed
    # instead of silently ignoring an attachment below the supported depth.
    leaf = "mimeType,filename,body(size,attachmentId),parts(mimeType)"
    for _ in range(depth):
        leaf = "mimeType,filename,body(size,attachmentId),parts(" + leaf + ")"
    return "id,payload(" + leaf + ")"


def iter_parts(payload: dict[str, Any], *, depth: int = 0) -> Iterator[dict[str, Any]]:
    if depth > 8 or not isinstance(payload, dict):
        raise PrivateError("PRIVATE_RESPONSE_INVALID")
    body = payload.get("body", {})
    if not isinstance(body, dict) or "data" in body:
        raise PrivateError("PRIVATE_RESPONSE_INVALID")
    if payload.get("filename"):
        yield payload
    parts = payload.get("parts", [])
    if not isinstance(parts, list) or len(parts) > 128:
        raise PrivateError("PRIVATE_RESPONSE_INVALID")
    for child in parts:
        yield from iter_parts(child, depth=depth + 1)


def candidate(
    part: dict[str, Any], message_id: str, config: PrivateConfig
) -> tuple[Attachment | None, str]:
    try:
        filename, mime, body = part.get("filename"), part.get("mimeType"), part.get("body", {})
        if not isinstance(filename, str) or not isinstance(mime, str) or not isinstance(body, dict):
            raise ValueError
        extension = Path(filename.replace("\\", "/")).suffix.lower()
        if extension not in _MAP or extension not in config.allowed_extensions:
            return None, "unsupported_attachments"
        format_name, mimes = _MAP[extension]
        if mime.lower() not in mimes:
            return None, "unsupported_attachments"
        size, identifier = body.get("size"), body.get("attachmentId")
        if (
            type(size) is not int
            or size < 1
            or not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", identifier)
        ):
            return None, "filter_exclusions"
        if size > config.max_attachment_bytes:
            return None, "oversize_attachments"
        return Attachment(
            message_id, identifier, extension, format_name, size
        ), "eligible_attachments"
    except Exception:
        return None, "filter_exclusions"


def attachment_bytes(transport: GmailTransport, item: Attachment, config: PrivateConfig) -> bytes:
    try:
        body = transport.get(
            f"messages/{item.message_id}/attachments/{item.attachment_id}",
            params={"fields": "size,data"},
            max_bytes=config.max_attachment_bytes * 2 + 4096,
        )
        if (
            set(body) != {"size", "data"}
            or type(body["size"]) is not int
            or not isinstance(body["data"], str)
        ):
            raise ValueError
        encoded = body["data"]
        if len(encoded) > config.max_attachment_bytes * 4 // 3 + 8:
            raise ValueError
        data = base64.b64decode(
            encoded + "=" * ((-len(encoded)) % 4), altchars=b"-_", validate=True
        )
        if (
            len(data) != body["size"]
            or len(data) != item.size
            or len(data) > config.max_attachment_bytes
        ):
            raise ValueError
        return data
    except Exception:
        raise PrivateError("PRIVATE_RESPONSE_INVALID") from None
