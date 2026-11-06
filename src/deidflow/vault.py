"""Local stores for reversible pseudonyms, never for prompts or public logs.

The optional encrypted store protects individual values in memory and persists an
AEAD-authenticated envelope containing its version, session, expiry and entries.
Version 1 files had unauthenticated metadata and are deliberately rejected.
Python cannot guarantee erasure of all plaintext or key copies in process memory.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

_FORMAT = "deidflow.vault.v2"
_VERSION = 2
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_ENTRIES = 100000
_SESSION = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")


def _finite_number(value: Any) -> float:
    try:
        number = float(value) if type(value) in {int, float} else math.nan
    except (ValueError, OverflowError):
        number = math.nan
    if not math.isfinite(number):
        raise ValueError("Vault timestamps must be finite numbers")
    return number


def _unique_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in items}) != len(items):
        raise ValueError("Duplicate vault fields")
    return dict(items)


def _invalid_constant(value: str) -> Any:
    raise ValueError("Nonfinite vault metadata")


class Vault(Protocol):
    def put(self, placeholder: str, value: str) -> None: ...

    def get(self, placeholder: str) -> str | None: ...

    def placeholders(self) -> list[str]: ...

    def clear(self) -> None: ...


class MemoryVault:
    """In-process values with optional absolute expiry and an opaque session ID."""

    def __init__(
        self,
        *,
        ttl_seconds: float | None = None,
        clock: Callable[[], float] = time.time,
        session_id: str | None = None,
    ) -> None:
        if ttl_seconds is not None:
            ttl_seconds = _finite_number(ttl_seconds)
            if ttl_seconds <= 0:
                raise ValueError("Vault TTL must be positive")
        self._clock = clock
        now = _finite_number(clock())
        self._expires = None if ttl_seconds is None else _finite_number(now + ttl_seconds)
        self.session_id = secrets.token_hex(16) if session_id is None else session_id
        if not isinstance(self.session_id, str) or not _SESSION.fullmatch(self.session_id):
            raise ValueError("Vault session ID must be an opaque identifier")
        self._values: dict[str, Any] = {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(entries={len(self._values)})"

    def _alive(self) -> bool:
        now = _finite_number(self._clock())
        if self._expires is not None and now >= self._expires:
            self.clear()
            return False
        return True

    def _encode(self, placeholder: str, value: str) -> Any:
        return value

    def _decode(self, placeholder: str, stored: Any) -> str:
        return str(stored)

    def put(self, placeholder: str, value: str) -> None:
        if not isinstance(placeholder, str) or not placeholder or len(placeholder) > 128:
            raise ValueError("Vault placeholders must be bounded nonempty strings")
        if not isinstance(value, str) or not value:
            raise ValueError("Vault values must be nonempty strings")
        if not self._alive():
            raise ValueError("Vault expired")
        if placeholder not in self._values and len(self._values) >= _MAX_ENTRIES:
            raise ValueError("Vault entry limit exceeded")
        self._values[placeholder] = self._encode(placeholder, value)

    def get(self, placeholder: str) -> str | None:
        if not self._alive() or placeholder not in self._values:
            return None
        return self._decode(placeholder, self._values[placeholder])

    def placeholders(self) -> list[str]:
        return list(self._values) if self._alive() else []

    def clear(self) -> None:
        self._values.clear()

    def __len__(self) -> int:
        return len(self.placeholders())


class EncryptedVault(MemoryVault):
    """AES-256-GCM values and fully authenticated version-2 file metadata.

    Saving preserves an existing destination by using exclusive creation. Loading
    authenticates the whole envelope and every entry before returning a store.
    This persists a vault, not the allocator state needed to resume a session.
    """

    def __init__(
        self,
        key: bytes,
        *,
        ttl_seconds: float | None = None,
        clock: Callable[[], float] = time.time,
        session_id: str | None = None,
    ) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("EncryptedVault requires a 32-byte key")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise ImportError("Install deidflow[vault] for encrypted vaults") from None
        super().__init__(ttl_seconds=ttl_seconds, clock=clock, session_id=session_id)
        self._aead = AESGCM(key)

    def _entry_aad(self, placeholder: str) -> bytes:
        return json.dumps([_FORMAT, self.session_id, placeholder], separators=(",", ":")).encode()

    def _encode(self, placeholder: str, value: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + self._aead.encrypt(
            nonce, value.encode("utf-8"), self._entry_aad(placeholder)
        )

    def _decode(self, placeholder: str, stored: Any) -> str:
        try:
            return str(
                self._aead.decrypt(stored[:12], stored[12:], self._entry_aad(placeholder)).decode()
            )
        except Exception:
            raise ValueError("Vault entry failed authentication") from None

    def save(self, path: str | Path) -> None:
        """Write authenticated ciphertext to a new file with restrictive mode."""
        if not self._alive():
            raise ValueError("Vault expired")
        payload = json.dumps(
            {
                "format": _FORMAT,
                "version": _VERSION,
                "session_id": self.session_id,
                "expires": self._expires,
                "entries": {
                    p: base64.b64encode(v).decode("ascii") for p, v in sorted(self._values.items())
                },
            },
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
        nonce = secrets.token_bytes(12)
        encrypted = nonce + self._aead.encrypt(nonce, payload, _FORMAT.encode())
        envelope = json.dumps(
            {"format": _FORMAT, "ciphertext": base64.b64encode(encrypted).decode("ascii")},
            separators=(",", ":"),
        )
        if len(envelope) > _MAX_FILE_BYTES:
            raise ValueError("Vault file exceeds size limit")
        target = Path(path)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                from deidflow.private.security import protect

                protect(target, directory=False)
                handle.write(envelope)
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    @classmethod
    def load(
        cls, path: str | Path, key: bytes, *, clock: Callable[[], float] = time.time
    ) -> EncryptedVault:
        # Validate key/dependency before handling untrusted file contents.
        vault = cls(key, clock=clock)
        try:
            with Path(path).open("rb") as handle:
                raw = handle.read(_MAX_FILE_BYTES + 1)
            if len(raw) > _MAX_FILE_BYTES:
                raise ValueError("Vault file exceeds size limit")
            envelope = json.loads(
                raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
            )
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"format", "ciphertext"}
                or envelope["format"] != _FORMAT
            ):
                raise ValueError("Unsupported vault format")
            encrypted = base64.b64decode(envelope["ciphertext"], validate=True)
            plaintext = vault._aead.decrypt(encrypted[:12], encrypted[12:], _FORMAT.encode())
            payload = json.loads(
                plaintext, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
            )
            if (
                not isinstance(payload, dict)
                or set(payload) != {"format", "version", "session_id", "expires", "entries"}
                or payload["format"] != _FORMAT
                or type(payload["version"]) is not int
                or payload["version"] != _VERSION
                or not isinstance(payload["session_id"], str)
                or not _SESSION.fullmatch(payload["session_id"])
                or not isinstance(payload["entries"], dict)
                or len(payload["entries"]) > _MAX_ENTRIES
            ):
                raise ValueError("Invalid vault metadata")
            expires = payload["expires"]
            vault._expires = None if expires is None else _finite_number(expires)
            vault.session_id = payload["session_id"]
            if not vault._alive():
                raise ValueError("Vault expired")
            entries: dict[str, bytes] = {}
            for placeholder, ciphertext in payload["entries"].items():
                if not isinstance(placeholder, str) or not placeholder or len(placeholder) > 128:
                    raise ValueError("Invalid vault entry")
                stored = base64.b64decode(ciphertext, validate=True)
                if not vault._decode(placeholder, stored):
                    raise ValueError("Empty vault entry")
                entries[placeholder] = stored
            vault._values = entries
        except Exception:
            vault.clear()
            raise ValueError("Unreadable, expired or unauthenticated vault file") from None
        return vault


__all__ = ["EncryptedVault", "MemoryVault", "Vault"]
