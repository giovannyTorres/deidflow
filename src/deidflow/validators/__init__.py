"""Offline structural checks; none establish issuance, identity or account ownership."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

CURP_ALPHABET = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
RFC_ALPHABET = "0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ Ñ"
STATES = frozenset(
    "AS BC BS CC CL CM CS CH DF DG GT GR HG JC MC MN MS NT NL OC PL QT QR SP SL SR TC TS TL VZ YN ZS NE".split()
)
_CURP = re.compile(
    r"[A-Z][AEIOUX][A-Z]{2}\d{6}[HMX][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d", re.ASCII
)
_RFC = re.compile(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{2}[0-9A]", re.ASCII)


def normalize_identifier(value: str) -> str:
    """Remove permitted formatting, never confusable OCR substitutions."""
    return re.sub(r"[\s-]", "", value).upper()


@dataclass(frozen=True, slots=True)
class ValidationResult:
    pattern: bool
    structural: bool
    checksum: bool | None = None
    confirmed: bool = False

    @property
    def status(self) -> str:
        if not self.pattern or not self.structural or self.checksum is False:
            return "invalid"
        if self.checksum is True:
            return "checksum"
        return "structural"

    def __bool__(self) -> bool:
        return self.pattern and self.structural and self.checksum is not False


def _valid_date(value: str, century: int | None = None) -> bool:
    try:
        yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])
        date((century or 2000) + yy, mm, dd)
    except (ValueError, OverflowError):
        return False
    return True


def clabe_check_digit(prefix: str) -> str:
    if len(prefix) != 17 or not prefix.isascii() or not prefix.isdigit():
        raise ValueError("CLABE prefix must contain 17 ASCII digits")
    return str((-sum(int(ch) * (3, 7, 1)[i % 3] for i, ch in enumerate(prefix))) % 10)


def validate_clabe(value: str) -> ValidationResult:
    value = normalize_identifier(value)
    pattern = len(value) == 18 and value.isascii() and value.isdigit()
    structural = pattern and len(set(value)) > 1
    return ValidationResult(
        pattern, structural, clabe_check_digit(value[:17]) == value[-1] if pattern else None
    )


def curp_check_digit(prefix: str) -> str:
    if len(prefix) != 17 or any(ch not in CURP_ALPHABET for ch in prefix):
        raise ValueError("CURP prefix must contain 17 compatible characters")
    return str((-sum(CURP_ALPHABET.index(ch) * (18 - i) for i, ch in enumerate(prefix))) % 10)


def validate_curp(value: str) -> ValidationResult:
    value = normalize_identifier(value)
    pattern = _CURP.fullmatch(value) is not None
    if not pattern:
        return ValidationResult(False, False)
    century = 1900 if value[16].isdigit() else 2000
    structural = value[11:13] in STATES and _valid_date(value[4:10], century)
    return ValidationResult(True, structural, curp_check_digit(value[:17]) == value[-1])


def rfc_check_digit(prefix: str) -> str:
    if len(prefix) not in (11, 12) or any(ch not in RFC_ALPHABET for ch in prefix):
        raise ValueError("RFC prefix must contain 11 or 12 compatible characters")
    padded = prefix if len(prefix) == 12 else " " + prefix
    remainder = 11 - sum(RFC_ALPHABET.index(ch) * (13 - i) for i, ch in enumerate(padded)) % 11
    return "0" if remainder == 11 else "A" if remainder == 10 else str(remainder)


def validate_rfc(value: str) -> ValidationResult:
    value = normalize_identifier(value)
    pattern = _RFC.fullmatch(value) is not None
    if not pattern:
        return ValidationResult(False, False)
    structural = _valid_date(value[-9:-3])
    # SAT's generic national/foreign invoice RFCs are published special values.
    checksum = (
        value in {"XAXX010101000", "XEXX010101000"} or rfc_check_digit(value[:-1]) == value[-1]
    )
    return ValidationResult(True, structural, checksum)


def validate_card(value: str) -> ValidationResult:
    value = normalize_identifier(value)
    pattern = 13 <= len(value) <= 19 and value.isascii() and value.isdigit()
    if not pattern:
        return ValidationResult(False, False)
    digits = [int(ch) for ch in value]
    checksum = (
        sum(
            (d * 2 - 9 if d >= 5 else d * 2) if i % 2 == len(digits) % 2 else d
            for i, d in enumerate(digits)
        )
        % 10
        == 0
    )
    return ValidationResult(True, len(set(value)) > 1, checksum)


validate_payment_card = validate_card

__all__ = [
    "ValidationResult",
    "normalize_identifier",
    "validate_curp",
    "validate_rfc",
    "validate_clabe",
    "validate_card",
    "validate_payment_card",
    "curp_check_digit",
    "rfc_check_digit",
    "clabe_check_digit",
]
