"""Context-preserving de-identification sessions for LLM prompts and responses.

```python
from deidflow import DeidEngine, Policy
from deidflow.llm import DeidSession

session = DeidSession(DeidEngine(), policy=Policy.llm(require_ner=False))
safe = session.deidentify("La señora Verónica Herrera fue diagnosticada por el doctor Jiménez.")
safe.output_text  # 'La señora [PERSONA_1] fue diagnosticada por el doctor [MEDICO_1].'
answer = call_your_llm(safe.output_text)          # only placeholders leave the process
session.reidentify(answer).text                    # originals restored locally
```

Release semantics are unchanged: always check ``result.release_approved`` (or the
status) before sending text to a model. Re-identification restores only
placeholders this session issued; unknown or invented placeholders stay as text
and are reported.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
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
    text: str
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
        self.reversible = reversible
        if not reversible and vault is not None:
            raise ValueError("An irreversible session cannot use a vault")
        self.vault: Vault | None = (vault or MemoryVault()) if reversible else None
        self.allocator = allocator or PlaceholderAllocator()
        self.session_id = secrets.token_hex(16)

    def __enter__(self) -> DeidSession:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def deidentify(self, text: str, *, domain: str | None = None) -> Result:
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
                # Keep the most complete surface form ("Verónica Herrera" over "Herrera").
                if current is None or len(value) > len(current):
                    self.vault.put(placeholder, value)
        return result

    def reidentify(self, text: str, *, strict: bool = False) -> ReidentifyResult:
        if self.vault is None:
            raise ValueError("This session is irreversible; no vault was kept")
        issued = self.allocator.issued()
        restored = 0
        unknown: list[str] = []

        def replace(match: Any) -> str:
            nonlocal restored
            label = match.group("label") or match.group("bare_label")
            index = match.group("index") or match.group("bare_index")
            placeholder = canonical_placeholder(label, index)
            value = self.vault.get(placeholder) if placeholder in issued else None  # type: ignore[union-attr]
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


__all__ = ["SYSTEM_PROMPT_ES", "DeidSession", "ReidentifyResult"]
