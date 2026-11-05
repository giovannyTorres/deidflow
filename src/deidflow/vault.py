"""Placeholder -> original-value stores for reversible LLM workflows.

A vault turns anonymization into **pseudonymization**: whoever holds the vault (and
its key) can re-identify. Keep vaults on the trusted side of the boundary, never in
prompts, logs or the LLM provider. ``MemoryVault`` keeps values in process memory
only. ``EncryptedVault`` additionally encrypts every value with AES-256-GCM
(``pip install deidflow[vault]``) and can be persisted to a user-only file.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

_FORMAT = "deidflow.vault.v1"


class Vault(Protocol):
    def put(self, placeholder: str, value: str) -> None: ...

    def get(self, placeholder: str) -> str | None: ...

    def placeholders(self) -> list[str]: ...

    def clear(self) -> None: ...


class MemoryVault:
    """In-process mapping with optional time-to-live. Values are never serialized."""

    def __init__(self, *, ttl_seconds: float | None = None, clock: Callable[[], float] = time.time):
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("Vault TTL must be positive")
        self._clock = clock
        self._expires = None if ttl_seconds is None else clock() + ttl_seconds
        self._values: dict[str, Any] = {}

    def __repr__(self) -> str:  # Never echo values.
        return f"{type(self).__name__}(entries={len(self._values)})"

    def _alive(self) -> bool:
        if self._expires is not None and self._clock() >= self._expires:
            self.clear()
            return False
        return True

    def _encode(self, placeholder: str, value: str) -> Any:
        return value

    def _decode(self, placeholder: str, stored: Any) -> str:
        return str(stored)

    def put(self, placeholder: str, value: str) -> None:
        if not isinstance(placeholder, str) or not isinstance(value, str) or not value:
            raise ValueError("Vault entries require a placeholder and a nonempty value")
        if self._alive():
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
    """AES-256-GCM per value; the placeholder is bound as associated data."""

    def __init__(
        self,
        key: bytes,
        *,
        ttl_seconds: float | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("EncryptedVault requires a 32-byte key")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise ImportError("Install deidflow[vault] for encrypted vaults") from None
        super().__init__(ttl_seconds=ttl_seconds, clock=clock)
        self._aead = AESGCM(key)

    def _encode(self, placeholder: str, value: str) -> Any:
        nonce = secrets.token_bytes(12)
        return nonce + self._aead.encrypt(nonce, value.encode("utf-8"), placeholder.encode())

    def _decode(self, placeholder: str, stored: Any) -> str:
        try:
            return self._aead.decrypt(stored[:12], stored[12:], placeholder.encode()).decode()
        except Exception:
            raise ValueError("Vault entry failed authentication") from None

    def save(self, path: str | Path) -> None:
        """Write ciphertexts only, to a new file readable by the current user."""
        if not self._alive():
            raise ValueError("Vault expired")
        payload = {
            "format": _FORMAT,
            "expires": self._expires,
            "entries": {
                p: base64.b64encode(v).decode("ascii") for p, v in sorted(self._values.items())
            },
        }
        target = Path(path)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    @classmethod
    def load(
        cls, path: str | Path, key: bytes, *, clock: Callable[[], float] = time.time
    ) -> EncryptedVault:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if payload.get("format") != _FORMAT:
                raise ValueError
            entries = {
                str(p): base64.b64decode(v, validate=True)
                for p, v in dict(payload["entries"]).items()
            }
            expires = payload.get("expires")
        except (OSError, ValueError, TypeError, KeyError):
            raise ValueError("Unreadable vault file") from None
        vault = cls(key, clock=clock)
        vault._expires = None if expires is None else float(expires)
        vault._values = entries
        for placeholder in entries:  # Authenticate everything before use.
            vault._decode(placeholder, entries[placeholder])
        return vault


__all__ = ["EncryptedVault", "MemoryVault", "Vault"]
