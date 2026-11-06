"""Local, reversible pseudonymization for reviewed LLM prompts and responses.

This module never calls a model or sends text. Check ``release_approved`` and
complete the required privacy review before using output externally. Restoring
an issued token does not prove an LLM used that token truthfully; inspect the
response in the trusted environment and keep restored data local.

Identity is exact-value only, with no automatic alias/coreference resolution.
Persisted vaults are separate from the in-memory allocator: resuming one requires
its matching allocator explicitly, otherwise a populated vault is rejected.
"""

from __future__ import annotations

import secrets
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from deidflow.engine import DeidEngine, ReleaseStatus, Result
from deidflow.placeholders import PLACEHOLDER, PlaceholderAllocator, canonical_placeholder
from deidflow.policies import Policy
from deidflow.vault import MemoryVault, Vault

SYSTEM_PROMPT_ES = (
    "Los textos entre corchetes como [PERSONA_1], [MEDICO_1] o [LUGAR_2] son marcadores "
    "que sustituyen datos personales. Consérvalos exactamente como aparecen, no intentes "
    "adivinar su contenido y usa el mismo marcador cada vez que te refieras a esa entidad."
)


@dataclass(frozen=True)
class ReidentifyResult:
    text: str = field(repr=False)
    restored: int
    unknown: tuple[str, ...]


class DeidSession:
    """Shared placeholders across turns, plus an optional vault for re-identification."""

    def __init__(
        self,
        engine: DeidEngine,
        *,
        policy: Policy | None = None,
        vault: Vault | None = None,
        reversible: bool = True,
        allocator: PlaceholderAllocator | None = None,
    ) -> None:
        self.engine = engine
        self.policy = policy or Policy.llm()
        if type(reversible) is not bool:
            raise ValueError("reversible must be a boolean")
        self.reversible = reversible
        if not reversible and vault is not None:
            raise ValueError("An irreversible session cannot use a vault")
        self.vault: Vault | None = (
            (vault if vault is not None else MemoryVault()) if reversible else None
        )
        self.allocator = allocator if allocator is not None else PlaceholderAllocator()
        self.session_id = getattr(self.vault, "session_id", secrets.token_hex(16))
        if self.vault is not None:
            stored = {token: self.vault.get(token) for token in self.vault.placeholders()}
            self.allocator.bind_vault(self.session_id, stored)
        self._closed = False

    def __enter__(self) -> DeidSession:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def deidentify(self, text: str, *, domain: str | None = None) -> Result:
        if self._closed:
            raise ValueError("Session closed")
        self.allocator.reserve_source(text)
        result = self.engine.deidentify_text(
            text,
            policy=self.policy,
            document_id=self.session_id,
            domain=domain,
            placeholders=self.allocator,
        )
        if self.vault is not None and result.output_text is not None:
            if result.status in {ReleaseStatus.BLOCKED, ReleaseStatus.UNSUPPORTED}:
                return result
            for mapping in result.mappings:
                if mapping.action != "indexed":
                    continue
                placeholder = result.output_text[mapping.output_start : mapping.output_end]
                value = text[mapping.source_start : mapping.source_end]
                current = self.vault.get(placeholder)
                if current is not None and unicodedata.normalize("NFC", current) != (
                    unicodedata.normalize("NFC", value)
                ):
                    raise ValueError("Vault conflicts with issued placeholder")
                if current is None:
                    self.vault.put(placeholder, value)
        return result

    def reidentify(self, text: str, *, strict: bool = True) -> ReidentifyResult:
        if type(strict) is not bool:
            raise ValueError("strict must be a boolean")
        if self._closed:
            raise ValueError("Session closed")
        if self.vault is None:
            raise ValueError("This session is irreversible; no vault was kept")
        vault = self.vault
        issued = self.allocator.issued()
        restored = 0
        unknown: list[str] = []

        def replace(match: Any) -> str:
            nonlocal restored
            label = match.group("label") or match.group("bare_label")
            index = match.group("index") or match.group("bare_index")
            placeholder = canonical_placeholder(label, index)
            value = vault.get(placeholder) if placeholder in issued else None
            if value is None:
                unknown.append(placeholder)
                return str(match.group(0))
            restored += 1
            return value

        output = PLACEHOLDER.sub(replace, text)
        if strict and unknown:
            raise ValueError("Response contains placeholders not issued by this session")
        return ReidentifyResult(output, restored, tuple(dict.fromkeys(unknown)))

    def placeholders(self) -> dict[str, tuple[str, str | None]]:
        """Issued placeholder -> (entity type, role); never includes source values."""
        return self.allocator.issued()

    def close(self) -> None:
        if self.vault is not None:
            self.vault.clear()
        self.allocator.reset()
        self._closed = True


__all__ = ["SYSTEM_PROMPT_ES", "DeidSession", "ReidentifyResult"]
