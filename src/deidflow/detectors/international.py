"""Identifier, phone and network recognizers for Spanish-speaking countries.

Each specification pairs a bounded regular expression with a validator and an
acceptance rule:

- ``checksum``: reported when the check digit is valid; with an explicit field
  label an invalid value is still reported as an uncertain candidate.
- ``structural``: the format is distinctive enough on its own (fixed separators,
  embedded dates, letter prefixes); reported when the structure validates.
- ``context``: the digits alone are ambiguous (for example an 8-digit DNI), so
  a field label must precede the value.

Patterns are linear (fixed or small bounded repetitions) and use ASCII digits.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass

from deidflow.validators import ValidationResult
from deidflow.validators import international as v

_I = re.IGNORECASE
_NUM = r"(?:n(?:[úu]m(?:ero)?|[º°o])\.?\s*)?"


def _label(words: str) -> re.Pattern[str]:
    # "DNI: ", "DNI nº ", "cédula de ciudadanía ", "su DNI es ", "RUC número "
    connector = r"(?:(?:es|era|ser[áa]|n[úu]mero|nro\.?)\s+)?"
    return re.compile(
        r"(?:" + words + r")\s*" + _NUM + r"(?:de\s+\w+\s*)?" + connector + r"[:=#]?\s*$", _I
    )


LABELS = {
    "dni": _label(
        r"\bD\.?\s?N\.?\s?I\.?|\bdocumento(?:\s+nacional)?(?:\s+de\s+identidad)?|\bn[úu]mero\s+de\s+documento|\bdoc\.?"
    ),
    "cedula": _label(
        r"\bc[ée]dula(?:\s+de\s+(?:identidad|ciudadan[íi]a))?(?:\s+de\s+\w+)?|\bC\.\s?[CI]\.?|\bCC|\bCI|\bidentidad|\bIdent\."
    ),
    "nie": _label(r"\bN\.?\s?I\.?\s?E\.?"),
    "nss": _label(r"\bseguridad\s+social|\bN\.?\s?A?\.?\s?S\.?\s?S\.?|\bafiliaci[óo]n|\bIMSS"),
    "ruc": _label(r"\bR\.?\s?U\.?\s?C\.?"),
    "nit": _label(r"\bN\.?\s?I\.?\s?T\.?"),
    "rnc": _label(r"\bR\.?\s?N\.?\s?C\.?"),
    "dui": _label(r"\bD\.?\s?U\.?\s?I\.?"),
    "dpi": _label(r"\bD\.?\s?P\.?\s?I\.?|\bC\.?\s?U\.?\s?I\.?"),
    "carne": _label(r"\bcarn[ée]t?(?:\s+de\s+identidad)?|\bCI"),
    "iban": _label(r"\bIBAN"),
    "rif": _label(r"\bR\.?\s?I\.?\s?F\.?"),
}


@dataclass(frozen=True)
class IdentifierSpec:
    name: str
    countries: frozenset[str]
    entity_type: str
    pattern: re.Pattern[str]
    validator: Callable[[str], ValidationResult] | None
    accept: str  # "checksum" | "structural" | "context"
    labels: tuple[str, ...] = ()
    score: float = 0.99


def _spec(
    name: str,
    countries: str,
    entity_type: str,
    pattern: str,
    validator: Callable[[str], ValidationResult] | None,
    accept: str,
    labels: tuple[str, ...] = (),
    score: float = 0.99,
    flags: int = 0,
) -> IdentifierSpec:
    return IdentifierSpec(
        name,
        frozenset(countries.split()),
        entity_type,
        re.compile(pattern, flags),
        validator,
        accept,
        labels,
        score,
    )


_D8 = r"\d{1,2}\.?\d{3}\.?\d{3}"  # 7-8 digits with optional thousands dots

SPECS: tuple[IdentifierSpec, ...] = (
    # Spain
    _spec(
        "ES-DNI",
        "ES",
        "NATIONAL_ID",
        r"(?<![\w.])" + _D8 + r"[ -]?[A-Za-z](?!\w)",
        v.validate_es_dni,
        "checksum",
        ("dni",),
    ),
    _spec(
        "ES-NIE",
        "ES",
        "NATIONAL_ID",
        r"(?<!\w)[XYZxyz][ -]?\d{7}[ -]?[A-Za-z](?!\w)",
        v.validate_es_nie,
        "checksum",
        ("nie", "dni"),
    ),
    _spec(
        "ES-CIF",
        "ES",
        "TAX_ID",
        r"(?<!\w)[ABCDEFGHJNPQRSUVW][ -]?\d{7}[ -]?[0-9A-J](?!\w)",
        v.validate_es_cif,
        "checksum",
        ("nit",),
    ),
    _spec(
        "ES-NSS",
        "ES",
        "INSURANCE_ID",
        r"(?<![\d/])\d{2}[ /-]?\d{8}[ /-]?\d{2}(?![\d/])",
        v.validate_es_nss,
        "context",
        ("nss",),
    ),
    _spec(
        "ES-CCC",
        "ES",
        "BANK_ACCOUNT",
        r"(?<!\w)\d{4}[ -]?\d{4}[ -]?\d{2}[ -]?\d{10}(?!\w)",
        v.validate_es_ccc,
        "checksum",
    ),
    # Argentina
    _spec(
        "AR-CUIT",
        "AR",
        "TAX_ID",
        r"(?<![\d.])(?:20|23|24|25|26|27|30|33|34)-?\d{2}\.?\d{3}\.?\d{3}-?\d(?![\d.])",
        v.validate_ar_cuit,
        "checksum",
    ),
    _spec(
        "AR-CBU",
        "AR",
        "BANK_ACCOUNT",
        r"(?<!\w)\d{8}[ -]?\d{14}(?!\w)",
        v.validate_ar_cbu,
        "checksum",
    ),
    # Chile, Uruguay (dotted body with a hyphenated check character)
    _spec(
        "CL-RUT",
        "CL",
        "NATIONAL_ID",
        r"(?<![\w.])\d{1,2}\.?\d{3}\.?\d{3}-[\dkK](?!\w)",
        v.validate_cl_rut,
        "checksum",
        ("cedula", "dni"),
    ),
    _spec(
        "UY-CI",
        "UY",
        "NATIONAL_ID",
        r"(?<![\w.])\d\.?\d{3}\.?\d{3}-\d(?!\w)",
        v.validate_uy_ci,
        "checksum",
        ("cedula",),
    ),
    # Colombia
    _spec(
        "CO-NIT",
        "CO",
        "TAX_ID",
        r"(?<![\w.])\d{3}\.?\d{3}\.?\d{3}-\d(?!\w)",
        v.validate_co_nit,
        "checksum",
        ("nit",),
    ),
    # Peru
    _spec(
        "PE-RUC",
        "PE",
        "TAX_ID",
        r"(?<!\w)(?:10|15|16|17|20)\d{9}(?!\w)",
        v.validate_pe_ruc,
        "checksum",
        ("ruc",),
    ),
    # Ecuador
    _spec(
        "EC-CI",
        "EC",
        "NATIONAL_ID",
        r"(?<!\w)\d{9}-?\d(?!\w)",
        v.validate_ec_ci,
        "context",
        ("cedula",),
    ),
    _spec("EC-RUC", "EC", "TAX_ID", r"(?<!\w)\d{13}(?!\w)", v.validate_ec_ruc, "context", ("ruc",)),
    # Venezuela
    _spec(
        "VE-CI",
        "VE",
        "NATIONAL_ID",
        r"(?<!\w)[VE]-?" + _D8 + r"(?![\d-]|[.,]\d)",
        None,
        "structural",
        score=0.9,
    ),
    _spec(
        "VE-RIF",
        "VE",
        "TAX_ID",
        r"(?<!\w)[VEJPG]-?\d{8}-?\d(?!\w)",
        v.validate_ve_rif,
        "checksum",
        ("rif", "nit"),
        flags=_I,
    ),
    # Paraguay, Bolivia, Cuba, Honduras, Panama, Costa Rica (label-dependent)
    _spec(
        "PY-RUC",
        "PY",
        "TAX_ID",
        r"(?<![\w.])\d{5,8}-\d(?!\w)",
        v.validate_py_ruc,
        "context",
        ("ruc",),
    ),
    _spec(
        "CU-NI",
        "CU",
        "NATIONAL_ID",
        r"(?<!\w)\d{11}(?!\w)",
        v.validate_cu_ni,
        "context",
        ("carne", "cedula"),
    ),
    _spec(
        "HN-DNI",
        "HN",
        "NATIONAL_ID",
        r"(?<!\w)\d{4}-\d{4}-\d{5}(?!\w)",
        None,
        "structural",
        score=0.85,
    ),
    _spec(
        "NI-CEDULA",
        "NI",
        "NATIONAL_ID",
        r"(?<!\w)\d{3}-\d{6}-\d{4}[A-Z](?!\w)",
        None,
        "structural",
        score=0.9,
    ),
    _spec(
        "PA-CEDULA",
        "PA",
        "NATIONAL_ID",
        r"(?<![\w-])(?:PE|E|N|[1-9]|1[0-3])(?:AV|PI)?-\d{1,4}-\d{1,6}(?![\w-])",
        None,
        "context",
        ("cedula",),
    ),
    _spec(
        "CR-CEDULA",
        "CR",
        "NATIONAL_ID",
        r"(?<![\d-])[1-9]-\d{4}-\d{4}(?![\d-])",
        None,
        "structural",
        score=0.85,
    ),
    # Dominican Republic
    _spec(
        "DO-CEDULA",
        "DO",
        "NATIONAL_ID",
        r"(?<!\w)\d{3}-\d{7}-\d(?!\w)",
        v.validate_do_cedula,
        "checksum",
        ("cedula",),
    ),
    _spec(
        "DO-RNC",
        "DO",
        "TAX_ID",
        r"(?<![\d-])\d-?\d{2}-?\d{5}-?\d(?![\d-])",
        v.validate_do_rnc,
        "context",
        ("rnc",),
    ),
    # Guatemala, El Salvador
    _spec(
        "GT-NIT",
        "GT",
        "TAX_ID",
        r"(?<![\w.])\d{4,9}-?[\dkK](?!\w)",
        v.validate_gt_nit,
        "context",
        ("nit",),
    ),
    _spec(
        "GT-DPI",
        "GT",
        "NATIONAL_ID",
        r"(?<!\w)\d{4}[ -]?\d{5}[ -]?\d{4}(?!\w)",
        None,
        "context",
        ("dpi", "dni"),
    ),
    _spec(
        "SV-DUI",
        "SV",
        "NATIONAL_ID",
        r"(?<![\d-])\d{8}-\d(?![\d-])",
        v.validate_sv_dui,
        "context",
        ("dui",),
    ),
    # Mexico (in addition to CURP/RFC/CLABE in the core rules)
    _spec(
        "MX-NSS",
        "MX",
        "INSURANCE_ID",
        r"(?<!\w)\d{2}[ -]?\d{2}[ -]?\d{2}[ -]?\d{4}[ -]?\d(?!\w)",
        v.validate_mx_nss,
        "context",
        ("nss",),
    ),
    _spec(
        "MX-CLAVE-ELECTOR",
        "MX",
        "NATIONAL_ID",
        r"(?<!\w)[A-Z]{6}\d{8}[HMX]\d{3}(?!\w)",
        v.validate_mx_clave_elector,
        "structural",
        score=0.95,
    ),
    # United States / Puerto Rico
    _spec(
        "US-SSN",
        "US PR",
        "NATIONAL_ID",
        r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])",
        v.validate_us_ssn,
        "structural",
        score=0.9,
    ),
    # Generic labelled document numbers (Argentina, Peru, Bolivia, Paraguay, Colombia, ...)
    _spec(
        "LATAM-DNI",
        "AR PE BO PY CO CL UY GT HN",
        "NATIONAL_ID",
        r"(?<![\w.])" + _D8 + r"(?!\w|[.,]\d|-\w)",
        None,
        "context",
        ("dni", "cedula"),
        score=0.9,
    ),
    _spec(
        "LATAM-CEDULA",
        "CO EC BO PY VE CR CU HN NI PA",
        "NATIONAL_ID",
        r"(?<![\w.])\d{1,3}(?:\.?\d{3}){1,3}(?!\w|[.,]\d|-\w)",
        None,
        "context",
        ("cedula",),
        score=0.9,
    ),
)

_PHONE_CODES = (
    # Spain, Equatorial Guinea, Latin America (50x, 5x, 59x) and NANP (+1: US, PR, DO)
    r"(?:240|34|5[0-8]|59[1-8]|1)"
)
_INTL_PHONE = re.compile(
    r"(?<![\w+])\+"
    + _PHONE_CODES
    + r"[ .-]?(?:\(?\d{1,4}\)?[ .-]?)?\d{2,4}(?:[ .-]?\d{2,4}){1,3}(?!\d|-\d)"
)
_ES_PHONE = re.compile(
    r"(?<![\d+.,])(?:[6789]\d{2}(?: \d{2}){3}|[6789]\d{2}[ .]\d{3}[ .]\d{3}|9\d[ .]\d{3}[ .]\d{2}[ .]\d{2})(?!\d|[.,]\d|-\d)"
)
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IPV6 = re.compile(r"(?<![\w:])(?=[0-9A-Fa-f:]*:[0-9A-Fa-f]*:)[0-9A-Fa-f:]{3,39}(?![\w:])")

_MONTHS = (
    r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|sep?tiembre|octubre|noviembre|diciembre)"
)
_TEXT_DATE = re.compile(
    r"\b\d{1,2}\s+de\s+" + _MONTHS + r"(?:\s+(?:de|del)\s+\d{4})?\b"
    r"|\b" + _MONTHS + r"\s+(?:de|del)\s+\d{4}\b"
    r"|\b" + _MONTHS + r"\s+\d{1,2},?\s+(?:de\s+)?\d{4}\b",
    _I,
)
# The same separator twice: "15/3/2021", "1-4-89"; not scores such as "2-3/10".
_SHORT_DATE = re.compile(r"(?<![\d/.-])\d{1,2}([/-])\d{1,2}\1(?:\d{4}|\d{2})(?![\d/-])")


def _has_label(text: str, start: int, names: tuple[str, ...]) -> bool:
    window = text[max(0, start - 48) : start]
    return any(LABELS[name].search(window) for name in names)


@dataclass(frozen=True)
class Candidate:
    entity_type: str
    start: int
    end: int
    score: float
    validation: str
    context: tuple[str, ...]
    labels: tuple[str, ...]


def identifier_candidates(
    text: str, countries: Collection[str] | None = None
) -> Iterator[Candidate]:
    """Yield identifier candidates for ``countries`` (``None`` means all)."""
    for spec in SPECS:
        if countries is not None and not (spec.countries & set(countries)):
            continue
        for match in spec.pattern.finditer(text):
            value = match.group()
            labelled = bool(spec.labels) and _has_label(text, match.start(), spec.labels)
            result = spec.validator(value) if spec.validator else None
            status = result.status if result is not None else "pattern"
            valid = result is None or bool(result)
            checksum_ok = result is not None and result.checksum is True
            if spec.accept == "checksum":
                if checksum_ok and result is not None and result.structural:
                    score = spec.score
                elif labelled:
                    score = 0.55
                else:
                    continue
            elif spec.accept == "structural":
                if not valid:
                    if not labelled:
                        continue
                    score = 0.55
                else:
                    score = spec.score
            else:  # context
                if not labelled:
                    continue
                score = spec.score if valid else 0.55
            context = ("explicit_identifier_label",) if labelled else ()
            yield Candidate(
                spec.entity_type,
                match.start(),
                match.end(),
                score,
                status,
                context + (("checksum_valid",) if checksum_ok else ()),
                ("id:" + spec.name,),
            )


def phone_candidates(text: str) -> Iterator[Candidate]:
    for pattern, score, name in ((_INTL_PHONE, 0.92, "intl"), (_ES_PHONE, 0.8, "es")):
        for match in pattern.finditer(text):
            digits = sum(c.isdigit() for c in match.group())
            if 8 <= digits <= 15:
                yield Candidate("PHONE", *match.span(), score, "structural", (), ("phone:" + name,))


def network_candidates(text: str) -> Iterator[Candidate]:
    for pattern in (_IPV4, _IPV6):
        for match in pattern.finditer(text):
            if v.validate_ip(match.group()):
                yield Candidate("IP_ADDRESS", *match.span(), 0.95, "structural", (), ("ip",))


def date_candidates(text: str) -> Iterator[tuple[int, int]]:
    """Textual Spanish dates and short numeric dates with valid day/month."""
    yield from (m.span() for m in _TEXT_DATE.finditer(text))
    for match in _SHORT_DATE.finditer(text):
        day, month = (int(part) for part in re.split(r"[/-]", match.group())[:2])
        if 1 <= day <= 31 and 1 <= month <= 12:
            yield match.span()


SUPPORTED_COUNTRIES = frozenset(
    "AR BO CL CO CR CU DO EC ES GT HN MX NI PA PE PR PY SV US UY VE".split()
)

__all__ = [
    "LABELS",
    "SPECS",
    "SUPPORTED_COUNTRIES",
    "Candidate",
    "IdentifierSpec",
    "date_candidates",
    "identifier_candidates",
    "network_candidates",
    "phone_candidates",
]
