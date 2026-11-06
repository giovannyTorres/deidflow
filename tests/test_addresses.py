from __future__ import annotations

import time

import pytest

from deidflow import DeidEngine
from deidflow.detectors import RuleDetector


def _addresses(text):
    return [
        text[f.start : f.end] for f in DeidEngine().scan_text(text) if f.entity_type == "ADDRESS"
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("vivo en la Calle 45 # 12-30 de Medellín.", "Calle 45 # 12-30"),
        ("Domicilio en Cra. 7 No. 71-21, Apto 502, Bogotá.", "Cra. 7 No. 71-21, Apto 502"),
        ("Entrega en Cl. 84 Bis T # 8T-94 Sur.", "Cl. 84 Bis T # 8T-94 Sur"),
        ("Para tener su domicilio en Los Alerces 33.", "Los Alerces 33"),
        ("con domicilio en Skolgatan 8, y el Participante", "Skolgatan 8"),
        ("reside en 416 Paseo de Martí.", "416 Paseo de Martí"),
        ("Remitir a C/ Pintor Baeza, 11, 03010 Alicante.", "C/ Pintor Baeza, 11"),
        ("Av. Kansas City 92, 8ºB 41007 SEVILLA", "Av. Kansas City 92, 8ºB"),
        (
            "Oficina: Av. Insurgentes Sur 1602, Col. Crédito Constructor, C.P. 03940, CDMX.",
            "Av. Insurgentes Sur 1602, Col. Crédito Constructor, C.P. 03940",
        ),
        ("Jr. Huallaga 123, Lima", "Jr. Huallaga 123"),
        (
            "Urbanización de Jesusa Cisneros 7 Piso 9 · Maracaibo",
            "Urbanización de Jesusa Cisneros 7 Piso 9",
        ),
    ],
)
def test_unlabelled_spanish_and_latin_american_addresses(text, expected):
    assert expected in _addresses(text)


@pytest.mark.parametrize(
    "text",
    [
        "visitamos la Plaza Mayor 3 veces",
        "vivo en Madrid desde 2010",
        "La calle estaba vacía a las 3 de la tarde.",
        "Capítulo 12, página 345.",
        "Ruta 66 es famosa.",
        "Tomar 2 comprimidos cada 8 horas.",
    ],
)
def test_ordinary_text_is_not_an_address(text):
    assert _addresses(text) == []


def test_overlapping_address_candidates_become_one_finding():
    found = _addresses("Oficina: Av. Insurgentes Sur 1602, Col. Roma Norte, C.P. 06700.")
    assert found == ["Av. Insurgentes Sur 1602, Col. Roma Norte, C.P. 06700"]


def test_address_patterns_are_linear_on_adversarial_input():
    detector = RuleDetector()
    for chunk in ("Calle ", "Calle Aa ", "domicilio en Aa ", "Av. 1 # 1-", "Col. Aa ", "1 Aa "):
        text = chunk * 20000
        start = time.perf_counter()
        detector.detect(text)
        assert time.perf_counter() - start < 5, chunk
