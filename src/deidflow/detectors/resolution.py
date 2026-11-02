"""Conservative mention grouping, distinct from identity verification."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Iterable
from dataclasses import dataclass

from deidflow.core import Finding
from deidflow.validators import normalize_identifier

_IDENTIFIERS = {
    "RFC",
    "CURP",
    "CLABE",
    "PAYMENT_CARD",
    "PHONE",
    "BANK_ACCOUNT",
    "NATIONAL_ID",
    "EMPLOYEE_ID",
    "CUSTOMER_ID",
    "PATIENT_ID",
    "PASSPORT",
    "DOCUMENT_ID",
    "INTERNAL_ID",
}


@dataclass(frozen=True, slots=True)
class MentionGroup:
    """A scoped key and matching mention indices, without retained plaintext."""

    group_id: str
    entity_type: str
    mention_indices: tuple[int, ...]


def resolve_exact_mentions(
    text: str,
    findings: Iterable[Finding],
    *,
    key: bytes,
    scope: str,
    aliases: dict[str, str] | None = None,
) -> list[MentionGroup]:
    """Group exact normalized mentions, accepting only explicitly supplied aliases.

    Text and finding offsets must belong to one fragment. Full-name equality is
    mention consistency, not proof that two people with the same name are equal.
    No fuzzy person-name merging occurs; short names remain separate.
    """
    if len(key) < 32 or not scope:
        raise ValueError("Mention resolution requires a 32-byte key and explicit scope")
    groups: dict[tuple[str, str], list[int]] = {}
    for index, finding in enumerate(findings):
        if finding.end > len(text):
            raise ValueError("Finding extends beyond its source fragment")
        value = text[finding.start : finding.end]
        value = (
            normalize_identifier(value)
            if finding.entity_type in _IDENTIFIERS
            else re.sub(r"\s+", " ", value).strip().casefold()
        )
        if aliases is not None:
            value = aliases.get(value, value)
        if finding.entity_type == "PERSON" and len(value.split()) < 2:
            value = f"{value}\x00mention:{index}"
        fields = [scope, finding.entity_type, value]
        framed = b"deidflow.resolution.v1\x00"
        for item in fields:
            encoded = item.encode("utf-8", errors="surrogatepass")
            framed += len(encoded).to_bytes(8, "big") + encoded
        digest = hmac.new(key, framed, hashlib.sha256).hexdigest()
        groups.setdefault((finding.entity_type, digest), []).append(index)
    return [
        MentionGroup(digest, kind, tuple(indices)) for (kind, digest), indices in groups.items()
    ]


__all__ = ["MentionGroup", "resolve_exact_mentions"]
