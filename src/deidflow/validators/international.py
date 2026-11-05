"""Offline check-digit and structure validators for Spanish-speaking countries.

Every function takes a candidate string (separators allowed), normalizes it and
returns a :class:`ValidationResult`. A passing checksum shows the value is
well formed, not that it was issued or who it belongs to. Algorithms follow the
issuing authorities' published rules; the test suite cross-checks them against
python-stdnum on random inputs.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date

from . import ValidationResult

_SEPARATORS = re.compile(r"[\s.\-/]")
_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def _clean(value: str) -> str:
    return _SEPARATORS.sub("", value).upper()


def _digits(value: str) -> bool:
    return value.isascii() and value.isdigit()


def _result(
    pattern: bool, structural: bool = True, checksum: bool | None = None, *, value: str = ""
) -> ValidationResult:
    """``value`` (the compact digits) marks one repeated digit as structurally invalid."""
    if not pattern:
        return ValidationResult(False, False)
    degenerate = len(value) > 1 and len(set(value)) == 1
    return ValidationResult(True, structural and not degenerate, checksum)


# -- Spain ---------------------------------------------------------------------


def validate_es_dni(value: str) -> ValidationResult:
    """DNI: eight digits and a mod-23 control letter."""
    v = _clean(value)
    if not (len(v) == 9 and _digits(v[:8]) and v[8].isalpha()):
        return _result(False)
    return _result(True, True, _DNI_LETTERS[int(v[:8]) % 23] == v[8])


def validate_es_nie(value: str) -> ValidationResult:
    """NIE: X/Y/Z, seven digits and the DNI control letter."""
    v = _clean(value)
    if not (len(v) == 9 and v[0] in "XYZ" and _digits(v[1:8]) and v[8].isalpha()):
        return _result(False)
    number = str("XYZ".index(v[0])) + v[1:8]
    return _result(True, True, _DNI_LETTERS[int(number) % 23] == v[8])


def validate_es_cif(value: str) -> ValidationResult:
    """CIF (legal entities): letter, seven digits and a digit or letter control."""
    v = _clean(value)
    if not (
        len(v) == 9
        and v[0] in "ABCDEFGHJNPQRSUVW"
        and _digits(v[1:8])
        and v[8] in "0123456789ABCDEFGHIJ"
    ):
        return _result(False)
    digits = [int(c) for c in v[1:8]]
    total = sum(digits[1::2]) + sum(sum(divmod(2 * d, 10)) for d in digits[0::2])
    control = (10 - total % 10) % 10
    # Sources disagree on which entity types use a letter or a digit, so (like
    # python-stdnum) both forms of the same control value are accepted.
    return _result(True, True, v[8] in {str(control), "JABCDEFGHI"[control]})


def validate_es_nss(value: str) -> ValidationResult:
    """Social Security number: province, eight digits and a mod-97 control."""
    v = _clean(value)
    if not (len(v) == 12 and _digits(v)):
        return _result(False)
    province, number, control = int(v[:2]), int(v[2:10]), int(v[10:])
    base = province * 10**7 + number if number < 10**7 else int(v[:10])
    return _result(True, True, base % 97 == control, value=v)


def _ccc_digit(digits: str) -> int:
    weights = (1, 2, 4, 8, 5, 10, 9, 7, 3, 6)
    check = 11 - sum(w * int(d) for w, d in zip(weights, digits, strict=True)) % 11
    return 0 if check == 11 else 1 if check == 10 else check


def validate_es_ccc(value: str) -> ValidationResult:
    """Código Cuenta Cliente: entity, office, two control digits, account."""
    v = _clean(value)
    if not (len(v) == 20 and _digits(v)):
        return _result(False)
    first = _ccc_digit("00" + v[:8])
    second = _ccc_digit(v[10:])
    return _result(True, True, v[8:10] == f"{first}{second}", value=v)


# -- Argentina -------------------------------------------------------------------


def validate_ar_cuit(value: str) -> ValidationResult:
    """CUIT/CUIL: type prefix, document number and a mod-11 check digit."""
    v = _clean(value)
    if not (len(v) == 11 and _digits(v)):
        return _result(False)
    structural = v[:2] in {"20", "23", "24", "25", "26", "27", "30", "33", "34"}
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    remainder = sum(w * int(d) for w, d in zip(weights, v[:10], strict=True)) % 11
    expected = "012345678990"[11 - remainder]
    return _result(True, structural, v[10] == expected, value=v)


def _cbu_digit(digits: str) -> str:
    weights = (3, 1, 7, 9)
    total = sum(int(d) * weights[i % 4] for i, d in enumerate(reversed(digits)))
    return str((10 - total) % 10)


def validate_ar_cbu(value: str) -> ValidationResult:
    """CBU: 22 digits in two blocks, each with its own check digit."""
    v = _clean(value)
    if not (len(v) == 22 and _digits(v)):
        return _result(False)
    return _result(True, True, _cbu_digit(v[:7]) == v[7] and _cbu_digit(v[8:21]) == v[21], value=v)


# -- Andean countries --------------------------------------------------------------


def validate_cl_rut(value: str) -> ValidationResult:
    """Chile RUT/RUN: number and a mod-11 check character (0-9 or K)."""
    v = _clean(value)
    if not (8 <= len(v) <= 9 and _digits(v[:-1]) and (v[-1].isdigit() or v[-1] == "K")):
        return _result(False)
    total = sum(int(d) * (2 + i % 6) for i, d in enumerate(reversed(v[:-1])))
    check = 11 - total % 11
    expected = "0" if check == 11 else "K" if check == 10 else str(check)
    return _result(True, int(v[:-1]) > 0, v[-1] == expected, value=v[:-1])


def validate_co_nit(value: str) -> ValidationResult:
    """Colombia NIT: up to 15 digits and a prime-weighted mod-11 check digit."""
    v = _clean(value)
    if not (8 <= len(v) <= 16 and _digits(v)):
        return _result(False)
    weights = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
    remainder = sum(w * int(d) for w, d in zip(weights, reversed(v[:-1]), strict=False)) % 11
    return _result(True, True, v[-1] == "01987654321"[remainder], value=v)


def validate_pe_ruc(value: str) -> ValidationResult:
    """Peru RUC: 11 digits with a type prefix and mod-11 check digit."""
    v = _clean(value)
    if not (len(v) == 11 and _digits(v)):
        return _result(False)
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(w * int(d) for w, d in zip(weights, v[:10], strict=True))
    structural = v[:2] in {"10", "15", "16", "17", "20"}
    return _result(True, structural, v[10] == str((11 - total % 11) % 10), value=v)


def _ec_ci_digit(digits: str) -> str:
    total = 0
    for index, digit in enumerate(digits):
        product = (2 - index % 2) * int(digit)
        total += product - 9 if product > 9 else product
    return str(-total % 10)


def validate_ec_ci(value: str) -> ValidationResult:
    """Ecuador cédula: province, person type and a mod-10 check digit."""
    v = _clean(value)
    if not (len(v) == 10 and _digits(v)):
        return _result(False)
    structural = (1 <= int(v[:2]) <= 24 or v[:2] == "30") and int(v[2]) < 6
    return _result(True, structural, _ec_ci_digit(v[:9]) == v[9], value=v)


def validate_ec_ruc(value: str) -> ValidationResult:
    """Ecuador RUC: natural person (cédula + establishment), public or juridical."""
    v = _clean(value)
    if not (len(v) == 13 and _digits(v)):
        return _result(False)
    province_ok = 1 <= int(v[:2]) <= 24 or v[:2] in {"30", "50"}

    def weighted(digits: str, weights: tuple[int, ...]) -> int:
        return sum(w * int(d) for w, d in zip(weights, digits, strict=True)) % 11

    natural = v[10:] != "000" and _ec_ci_digit(v[:9]) == v[9]
    public = v[9:] != "0000" and weighted(v[:9], (3, 2, 7, 6, 5, 4, 3, 2, 1)) == 0
    juridical = v[10:] != "000" and weighted(v[:10], (4, 3, 2, 7, 6, 5, 4, 3, 2, 1)) == 0
    kind = int(v[2])
    if kind < 6:
        valid = natural
    elif kind == 6:
        valid = public or natural
    elif kind == 9:
        valid = public or juridical
    else:
        return _result(True, False, None)
    return _result(True, province_ok, valid)


# -- Venezuela, Uruguay, Paraguay -------------------------------------------------


def validate_ve_rif(value: str) -> ValidationResult:
    """Venezuela RIF: entity type letter, eight digits and a mod-11 check digit."""
    v = _clean(value)
    types = {"V": 4, "E": 8, "J": 12, "P": 16, "G": 20}
    if not (len(v) == 10 and v[0] in types and _digits(v[1:])):
        return _result(False)
    weights = (3, 2, 7, 6, 5, 4, 3, 2)
    total = types[v[0]] + sum(w * int(d) for w, d in zip(weights, v[1:9], strict=True))
    return _result(True, True, v[9] == "00987654321"[total % 11])


def validate_uy_ci(value: str) -> ValidationResult:
    """Uruguay cédula de identidad: up to seven digits and a check digit."""
    v = _clean(value)
    if not (6 <= len(v) <= 8 and _digits(v)):
        return _result(False)
    body = v[:-1].rjust(7, "0")
    weights = (2, 9, 8, 7, 6, 3, 4)
    total = sum(w * int(d) for w, d in zip(weights, body, strict=True))
    return _result(True, True, v[-1] == str(-total % 10), value=v)


def validate_py_ruc(value: str) -> ValidationResult:
    """Paraguay RUC: base number and a mod-11 check digit."""
    v = _clean(value)
    if not (5 <= len(v) <= 9 and _digits(v)):
        return _result(False)
    total = sum((i + 2) * int(d) for i, d in enumerate(reversed(v[:-1])))
    return _result(True, True, v[-1] == str((-total % 11) % 10), value=v)


# -- Central America and the Caribbean ---------------------------------------------


def validate_do_cedula(value: str) -> ValidationResult:
    """Dominican Republic cédula: 11 digits with a Luhn check digit."""
    v = _clean(value)
    if not (len(v) == 11 and _digits(v)):
        return _result(False)
    total = 0
    for index, digit in enumerate(reversed(v)):
        number = int(digit) * (2 if index % 2 else 1)
        total += number - 9 if number > 9 else number
    return _result(True, True, total % 10 == 0, value=v)


def validate_do_rnc(value: str) -> ValidationResult:
    """Dominican Republic RNC (companies): nine digits, weighted check digit."""
    v = _clean(value)
    if not (len(v) == 9 and _digits(v)):
        return _result(False)
    weights = (7, 9, 8, 6, 5, 4, 3, 2)
    remainder = sum(w * int(d) for w, d in zip(weights, v[:8], strict=True)) % 11
    return _result(True, True, v[8] == str((10 - remainder) % 9 + 1), value=v)


def validate_gt_nit(value: str) -> ValidationResult:
    """Guatemala NIT: number and a mod-11 check character (0-9 or K)."""
    v = _clean(value)
    if not (2 <= len(v) <= 12 and _digits(v[:-1]) and (v[-1].isdigit() or v[-1] == "K")):
        return _result(False)
    check = -sum(i * int(d) for i, d in enumerate(reversed(v[:-1]), 2)) % 11
    return _result(True, True, v[-1] == ("K" if check == 10 else str(check)))


def validate_sv_dui(value: str) -> ValidationResult:
    """El Salvador DUI: eight digits and a weighted check digit."""
    v = _clean(value)
    if not (len(v) == 9 and _digits(v)):
        return _result(False)
    total = sum(w * int(d) for w, d in zip(range(9, 1, -1), v[:8], strict=True))
    return _result(True, True, v[8] == str(-total % 10), value=v)


def validate_us_ssn(value: str) -> ValidationResult:
    """US Social Security number: area, group and serial exclusions (no checksum)."""
    v = _clean(value)
    if not (len(v) == 9 and _digits(v)):
        return _result(False)
    area, group, serial = v[:3], v[3:5], v[5:]
    structural = (
        area not in {"000", "666"} and area[0] != "9" and group != "00" and serial != "0000"
    )
    return _result(True, structural, None)


def _valid_yymmdd(digits: str, century: int) -> bool:
    try:
        date(century + int(digits[:2]), int(digits[2:4]), int(digits[4:6]))
    except ValueError:
        return False
    return True


def validate_cu_ni(value: str) -> ValidationResult:
    """Cuba carné de identidad: 11 digits starting with the birth date (YYMMDD)."""
    v = _clean(value)
    if not (len(v) == 11 and _digits(v)):
        return _result(False)
    century = {"9": 1800, "0": 1900, "1": 1900, "2": 1900, "3": 1900, "4": 1900, "5": 1900}
    century.update(dict.fromkeys("678", 2000))
    return _result(True, _valid_yymmdd(v[:6], century[v[6]]), None)


def validate_mx_nss(value: str) -> ValidationResult:
    """Mexico IMSS social security number: 11 digits with a Luhn-style check digit."""
    v = _clean(value)
    if not (len(v) == 11 and _digits(v)):
        return _result(False)
    total = 0
    for index, digit in enumerate(v[:10]):
        number = int(digit) * (2 if index % 2 else 1)
        total += number - 9 if number > 9 else number
    return _result(True, True, v[10] == str(-total % 10), value=v)


def validate_mx_clave_elector(value: str) -> ValidationResult:
    """Mexico INE clave de elector: 6 letters, birth date, state, sex and 3 digits."""
    v = _clean(value)
    if not re.fullmatch(r"[A-Z]{6}\d{8}[HMX]\d{3}", v, re.ASCII):
        return _result(False)
    plausible = _valid_yymmdd(v[6:12], 1900) or _valid_yymmdd(v[6:12], 2000)
    return _result(True, plausible and 1 <= int(v[12:14]) <= 33, None)


# -- Network identifiers -------------------------------------------------------------


def validate_ip(value: str) -> ValidationResult:
    """IPv4 or IPv6 address, validated by the standard library parser."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return _result(False)
    return _result(True, not address.is_unspecified, None)


__all__ = [
    "validate_ar_cbu",
    "validate_ar_cuit",
    "validate_cl_rut",
    "validate_co_nit",
    "validate_cu_ni",
    "validate_do_cedula",
    "validate_do_rnc",
    "validate_ec_ci",
    "validate_ec_ruc",
    "validate_es_ccc",
    "validate_es_cif",
    "validate_es_dni",
    "validate_es_nie",
    "validate_es_nss",
    "validate_gt_nit",
    "validate_ip",
    "validate_mx_clave_elector",
    "validate_mx_nss",
    "validate_pe_ruc",
    "validate_py_ruc",
    "validate_sv_dui",
    "validate_us_ssn",
    "validate_uy_ci",
    "validate_ve_rif",
]
