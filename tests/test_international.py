from __future__ import annotations

import random
import string
import time

import pytest

from deidflow import DeidEngine
from deidflow.detectors import RuleDetector
from deidflow.validators import international as v

KNOWN_VALID = [
    (v.validate_es_dni, "12345678Z"),
    (v.validate_es_nie, "X1234567L"),
    (v.validate_es_cif, "B12345674"),
    (v.validate_es_nss, "28 12345678 40"),
    (v.validate_es_ccc, "2100 0418 45 0200051332"),
    (v.validate_ar_cuit, "20-12345678-6"),
    (v.validate_ar_cbu, "2850590940090418135201"),
    (v.validate_cl_rut, "12.345.678-5"),
    (v.validate_pe_ruc, "20100070970"),
    (v.validate_ec_ci, "1710034065"),
    (v.validate_ec_ruc, "1790011674001"),
    (v.validate_uy_ci, "1.234.567-2"),
    (v.validate_sv_dui, "00016297-5"),
]


@pytest.mark.parametrize(("validator", "value"), KNOWN_VALID)
def test_known_valid_identifiers(validator, value):
    assert validator(value).status == "checksum"
    # Changing the last character breaks the check digit.
    last = value[-1]
    replacement = "0" if last != "0" else "1"
    assert validator(value[:-1] + replacement).status != "checksum"


def test_repeated_digit_placeholders_are_not_valid():
    for validator, value in (
        (v.validate_cl_rut, "11.111.111-1"),
        (v.validate_es_ccc, "0" * 20),
        (v.validate_ar_cbu, "0" * 22),
    ):
        assert validator(value).status == "invalid"


def test_structure_only_validators():
    assert v.validate_us_ssn("123-45-6789").structural
    assert not v.validate_us_ssn("666-45-6789").structural
    assert not v.validate_us_ssn("123-00-6789").structural
    assert v.validate_cu_ni("85030512345").structural  # born 1985-03-05
    assert not v.validate_cu_ni("85133112345").structural  # month 13
    assert v.validate_mx_clave_elector("GMVLMR80070501M100").structural
    assert v.validate_ip("2001:db8::1").structural and not v.validate_ip("10:30:00").pattern
    assert not v.validate_ip("999.1.1.1").pattern


def _random_digits(rng, n):
    return "".join(rng.choice(string.digits) for _ in range(n))


STDNUM_CASES = [
    ("es", "dni", v.validate_es_dni, lambda r: _random_digits(r, 8), "TRWAGMYFPDXBNJZSQVHLCKE"),
    (
        "es",
        "nie",
        v.validate_es_nie,
        lambda r: r.choice("XYZ") + _random_digits(r, 7),
        "TRWAGMYFPDXBNJZSQVHLCKE",
    ),
    (
        "es",
        "cif",
        v.validate_es_cif,
        lambda r: r.choice("ABCDEFGHJNPQRSUVW") + _random_digits(r, 7),
        "0123456789ABCDEFGHIJ",
    ),
    (
        "ar",
        "cuit",
        v.validate_ar_cuit,
        lambda r: r.choice(["20", "23", "27", "30", "33"]) + _random_digits(r, 8),
        string.digits,
    ),
    (
        "cl",
        "rut",
        v.validate_cl_rut,
        lambda r: _random_digits(r, r.choice([7, 8])),
        string.digits + "K",
    ),
    ("co", "nit", v.validate_co_nit, lambda r: _random_digits(r, 9), string.digits),
    (
        "pe",
        "ruc",
        v.validate_pe_ruc,
        lambda r: r.choice(["10", "20"]) + _random_digits(r, 8),
        string.digits,
    ),
    (
        "ec",
        "ci",
        v.validate_ec_ci,
        lambda r: f"{r.randint(1, 24):02d}{r.randint(0, 5)}" + _random_digits(r, 6),
        string.digits,
    ),
    (
        "ve",
        "rif",
        v.validate_ve_rif,
        lambda r: r.choice("VEJPG") + _random_digits(r, 8),
        string.digits,
    ),
    (
        "py",
        "ruc",
        v.validate_py_ruc,
        lambda r: _random_digits(r, r.choice([6, 7, 8])),
        string.digits,
    ),
    ("do", "cedula", v.validate_do_cedula, lambda r: _random_digits(r, 10), string.digits),
    ("do", "rnc", v.validate_do_rnc, lambda r: _random_digits(r, 8), string.digits),
    (
        "gt",
        "nit",
        v.validate_gt_nit,
        lambda r: _random_digits(r, r.choice([6, 7, 8])),
        string.digits + "K",
    ),
]


@pytest.mark.parametrize(("cc", "name", "validator", "body", "checks"), STDNUM_CASES)
def test_validators_agree_with_python_stdnum(cc, name, validator, body, checks):
    stdnum = pytest.importorskip("stdnum")
    module = stdnum.get_cc_module(cc, name)
    rng = random.Random(hash((cc, name)) & 0xFFFF)
    valid = 0
    for _ in range(150):
        prefix = body(rng)
        for check in checks:
            value = prefix + check
            ours = validator(value).status == "checksum"
            assert ours == module.is_valid(value), value
            valid += ours
    assert valid >= 150  # every random body has at least one valid check character


def test_ecuador_ruc_agrees_with_python_stdnum():
    stdnum = pytest.importorskip("stdnum")
    module = stdnum.get_cc_module("ec", "ruc")
    rng = random.Random(3)
    for _ in range(4000):
        value = f"{rng.randint(1, 24):02d}{rng.choice('01234569')}" + _random_digits(rng, 10)
        assert (v.validate_ec_ruc(value).status == "checksum") == module.is_valid(value), value


def _found(text, **engine):
    return {(f.entity_type, text[f.start : f.end]) for f in DeidEngine(**engine).scan_text(text)}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "DNI 12345678Z y NIE X1234567L.",
            {("NATIONAL_ID", "12345678Z"), ("NATIONAL_ID", "X1234567L")},
        ),
        ("Empresa con CIF B12345674.", {("TAX_ID", "B12345674")}),
        ("Seguridad Social: 28 12345678 40.", {("INSURANCE_ID", "28 12345678 40")}),
        ("Cuenta 2100 0418 45 0200051332.", {("BANK_ACCOUNT", "2100 0418 45 0200051332")}),
        (
            "CUIT 20-12345678-6 y CBU 2850590940090418135201.",
            {("TAX_ID", "20-12345678-6"), ("BANK_ACCOUNT", "2850590940090418135201")},
        ),
        ("Su DNI es 30.123.456.", {("NATIONAL_ID", "30.123.456")}),
        ("RUT 12.345.678-5.", {("NATIONAL_ID", "12.345.678-5")}),
        ("Cédula de ciudadanía 1.020.304.050.", {("NATIONAL_ID", "1.020.304.050")}),
        ("RUC 20100070970.", {("TAX_ID", "20100070970")}),
        ("Cédula 1710034065.", {("NATIONAL_ID", "1710034065")}),
        ("C.I. V-12.345.678.", {("NATIONAL_ID", "V-12.345.678")}),
        ("DUI 00016297-5.", {("NATIONAL_ID", "00016297-5")}),
        ("SSN 123-45-6789.", {("NATIONAL_ID", "123-45-6789")}),
        ("Clave de elector GMVLMR80070501M100.", {("NATIONAL_ID", "GMVLMR80070501M100")}),
        ("Tel. +34 612 345 678.", {("PHONE", "+34 612 345 678")}),
        ("Llámenos al 612 34 56 78.", {("PHONE", "612 34 56 78")}),
        (
            "Acceso desde 192.168.1.20 y 2001:db8::8a2e:370:7334.",
            {("IP_ADDRESS", "192.168.1.20"), ("IP_ADDRESS", "2001:db8::8a2e:370:7334")},
        ),
        ("Firmado el 3 de marzo de 1985.", {("DATE", "3 de marzo de 1985")}),
    ],
)
def test_international_detection(text, expected):
    assert expected <= _found(text)


@pytest.mark.parametrize(
    "text",
    [
        "El total fue de 1.234.567 pesos y 45.678 dólares.",
        "La reunión empieza a las 10:30:00 en la sala 2.",
        "Versión 2.1.0 del manual; capítulo 12, página 345.",
        "Se aplicaron 12345678 operaciones en el año.",
        "Proporción 3:2 y razón 1/2.",
    ],
)
def test_ordinary_numbers_are_not_identifiers(text):
    kinds = {kind for kind, _ in _found(text)}
    assert not kinds & {"NATIONAL_ID", "TAX_ID", "BANK_ACCOUNT", "PHONE", "IP_ADDRESS"}


def test_country_selection():
    text = "RUT 12.345.678-5 y DNI 12345678Z."
    assert ("NATIONAL_ID", "12.345.678-5") not in _found(text, country="ES")
    assert ("NATIONAL_ID", "12345678Z") in _found(text, country="ES")
    assert ("NATIONAL_ID", "12.345.678-5") in _found(text, country="CL,AR")
    assert ("NATIONAL_ID", "12.345.678-5") in _found(text, country=["ALL"])
    with pytest.raises(ValueError):
        DeidEngine(country="XX")
    with pytest.raises(ValueError):
        RuleDetector(countries=[])


def test_identifier_digits_are_not_also_cards_or_phones():
    text = "Cuenta 2100 0418 45 0200051332."
    kinds = {kind for kind, _ in _found(text)}
    assert "PAYMENT_CARD" not in kinds and "CLABE" not in kinds and "PHONE" not in kinds


def test_international_patterns_are_linear_on_adversarial_input():
    detector = RuleDetector()
    for chunk in ("1.", "12-", "+5", "V-1", "1 2 ", "a:", "de marzo "):
        text = chunk * 20000
        start = time.perf_counter()
        detector.detect(text)
        assert time.perf_counter() - start < 5, chunk
