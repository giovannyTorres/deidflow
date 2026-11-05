"""Non-reversible keyed tokens, deterministic overlap handling and offset maps.

No mapping of plaintext to tokens is persisted. A token is still linkable data.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from deidflow.core import Finding
from deidflow.policies import Policy, Rule

if TYPE_CHECKING:
    from deidflow.placeholders import PlaceholderAllocator

_MONTHS = (
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre"
).split()
_MONTH_NUMBER = {name: i + 1 for i, name in enumerate(_MONTHS)} | {"setiembre": 9}
_WRITTEN = re.compile(
    r"(?P<day>[0-3]?[0-9])(?P<s1>[ \t]+de[ \t]+)(?P<month>[A-Za-zÁÉÍÓÚáéíóú]+)"
    r"(?P<s2>[ \t]+de(?:l)?[ \t]+)(?P<year>[0-9]{4})\Z"
)
_NUMERIC = re.compile(
    r"(?P<day>[0-3]?[0-9])(?P<sep>[/.-])(?P<month>[01]?[0-9])(?P=sep)(?P<year>[0-9]{4}|[0-9]{2})\Z"
)
_NUMBER = re.compile(r"(?P<number>-?[0-9]+(?:[.,][0-9]+)?)(?P<rest>\D*)\Z")


def _shift_date(value: str, days: int) -> str:
    """Shift ISO, dd/mm/yyyy (/ . -) and Spanish written dates, keeping their format."""
    stripped = value.strip()
    try:
        return (date.fromisoformat(stripped) + timedelta(days=days)).isoformat()
    except ValueError:
        pass
    if match := _NUMERIC.match(stripped):
        year = int(match.group("year"))
        short = len(match.group("year")) == 2
        if short:
            year += 2000 if year < 30 else 1900
        shifted = date(year, int(match.group("month")), int(match.group("day"))) + timedelta(
            days=days
        )
        sep = match.group("sep")
        year_text = f"{shifted.year % 100:02d}" if short else str(shifted.year)
        return f"{shifted.day:02d}{sep}{shifted.month:02d}{sep}{year_text}"
    if match := _WRITTEN.match(stripped):
        month_name = match.group("month")
        month = _MONTH_NUMBER[month_name.casefold()]
        shifted = date(int(match.group("year")), month, int(match.group("day"))) + timedelta(
            days=days
        )
        name = _MONTHS[shifted.month - 1]
        if month_name[:1].isupper():
            name = name.capitalize()
        return f"{shifted.day}{match.group('s1')}{name}{match.group('s2')}{shifted.year}"
    raise ValueError


class IncompleteTransformationError(ValueError):
    """A non-keep operator returned the original sensitive span unchanged."""


@dataclass(frozen=True)
class SourceMap:
    source_start: int
    source_end: int
    output_start: int
    output_end: int
    entity_types: tuple[str, ...]
    action: str


def token(value: str, entity_type: str, *, key: bytes, scope: str) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("Pseudonymization requires at least 32 bytes of secret key")
    # Length framing avoids concatenation ambiguity. Case is intentionally retained.
    parts = [scope, entity_type, unicodedata.normalize("NFC", value)]
    try:
        encoded = [p.encode("utf-8") for p in parts]
    except UnicodeError:
        raise ValueError("Pseudonymization requires valid Unicode") from None
    message = b"deidflow-v1\0" + b"".join(len(p).to_bytes(8, "big") + p for p in encoded)
    digest = hmac.new(key, message, hashlib.sha256).digest()[:20]
    return f"[DF_{entity_type}_{base64.b32encode(digest).decode().rstrip('=')}]"


def _apply(
    value: str,
    kind: str,
    rule: Rule,
    *,
    key: bytes | None,
    scope: str,
    custom: dict[str, Callable[[str], str]],
) -> str:
    if rule.action == "redact":
        return "█" * len(value)
    if rule.action == "suppress":
        return ""
    if rule.action == "placeholder":
        return f"[{kind}]"
    if rule.action == "pseudonym":
        if key is None:
            raise ValueError("Pseudonymization requires an explicit secret key")
        return token(value, kind, key=key, scope=scope)
    if rule.action == "mask":
        if len(value) <= 4:
            return "*" * len(value)
        return "*" * max(0, len(value) - 4) + value[-4:]
    if rule.action == "generalize":
        return rule.replacement
    if rule.action == "bucket":
        try:
            # A unit after the number ("58 años") is kept; the number is bucketed.
            parsed = _NUMBER.match(value.strip())
            if parsed is None:
                raise ValueError
            number = float(parsed.group("number").replace(",", "."))
            if not math.isfinite(number):
                raise ValueError
            lower = math.floor(number / rule.width) * rule.width
            return f"[{lower},{lower + rule.width})" + parsed.group("rest")
        except ValueError:
            raise ValueError("Numeric bucketing requires a finite number") from None
    if rule.action == "date_shift":
        try:
            return _shift_date(value, rule.shift_days)
        except (ValueError, OverflowError, KeyError):
            raise ValueError("Date shifting requires a valid ISO or Spanish date") from None
    if rule.action == "custom":
        if rule.custom not in custom:
            raise ValueError("Custom transformation is not registered")
        try:
            result = custom[rule.custom](value)
            if not isinstance(result, str):
                raise TypeError
            return result
        except Exception:
            raise ValueError("Custom transformation failed") from None
    return value


def transform_text(
    text: str,
    findings: list[Finding],
    policy: Policy,
    *,
    key: bytes | None = None,
    scope: str = "",
    domain: str | None = None,
    custom: dict[str, Callable[[str], str]] | None = None,
    placeholders: PlaceholderAllocator | None = None,
) -> tuple[str, list[SourceMap]]:
    selected = []
    for finding in findings:
        if not 0 <= finding.start < finding.end <= len(text):
            raise ValueError("Finding is outside source bounds")
        rule = policy.rule(finding.entity_type, domain)
        # Protected deterministic candidates cannot be removed by a score threshold.
        if rule.action != "keep" and (finding.score >= rule.threshold or finding.protected):
            selected.append((finding, rule))
    selected.sort(key=lambda item: (item[0].start, -item[0].end, item[0].entity_type))
    groups: list[list[tuple[Finding, Rule]]] = []
    for item in selected:
        if groups and item[0].start < max(f.end for f, _ in groups[-1]):
            groups[-1].append(item)
        else:
            groups.append([item])
    parts, mappings, cursor, out_cursor = [], [], 0, 0
    priority = {
        "redact": 0,
        "suppress": 1,
        "placeholder": 2,
        "indexed": 2,
        "pseudonym": 3,
        "custom": 4,
        "generalize": 5,
        "date_shift": 6,
        "bucket": 7,
        "mask": 8,
    }
    for group in groups:
        start, end = min(f.start for f, _ in group), max(f.end for f, _ in group)
        chosen, rule = min(
            group,
            key=lambda item: (
                priority[item[1].action],
                -(item[0].end - item[0].start),
                -item[0].score,
                item[0].entity_type,
            ),
        )
        untouched = text[cursor:start]
        parts.append(untouched)
        out_cursor += len(untouched)
        if rule.action == "indexed":
            if placeholders is None:
                from deidflow.placeholders import PlaceholderAllocator

                placeholders = PlaceholderAllocator()
            replacement = placeholders.placeholder(
                text[start:end], chosen.entity_type, [f for f, _ in group]
            )
        else:
            replacement = _apply(
                text[start:end], chosen.entity_type, rule, key=key, scope=scope, custom=custom or {}
            )
        if replacement == text[start:end]:
            raise IncompleteTransformationError("Transformation left a sensitive span unchanged")
        parts.append(replacement)
        mappings.append(
            SourceMap(
                start,
                end,
                out_cursor,
                out_cursor + len(replacement),
                tuple(sorted({f.entity_type for f, _ in group})),
                rule.action,
            )
        )
        out_cursor += len(replacement)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), mappings
