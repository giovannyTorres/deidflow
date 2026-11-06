from __future__ import annotations

import random
import time

import pytest

from deidflow import DeidEngine
from deidflow.detectors import RuleDetector, _select_addresses
from deidflow.detectors.addresses import AddressCandidate


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
    for text in (
        "Calle " + "San " * 2000 + "!",
        "domicilio en " + "de la " * 2000 + "X",
        "Calle " + "Santa de la " * 1000 + "!",
    ):
        start = time.perf_counter()
        detector.detect(text)
        assert time.perf_counter() - start < 2, text[:30]


def test_many_separate_addresses_scale_linearly():
    detector = RuleDetector()
    timings = []
    for count in (2000, 8000):
        start = time.perf_counter()
        found = detector.detect("Calle Mayor 12.\n" * count)
        timings.append(time.perf_counter() - start)
        assert sum(f.entity_type == "ADDRESS" for f in found) == count
    assert timings[1] < timings[0] * 8  # 4x the input, far from 16x


def test_candidate_extending_a_labelled_address_is_kept():
    found = _addresses("Dirección: Calle Mayor\n12, Madrid")
    assert "Calle Mayor\n12" in found


@pytest.mark.parametrize(
    "suffix,expected",
    [
        ("Col. Roma Norte cerca del hospital.", "Calle Azul 2 Col. Roma Norte"),
        ("Dpto. 302 presenta dolor.", "Calle Azul 2 Dpto. 302"),
        ("Piso 3 con vista.", "Calle Azul 2 Piso 3"),
        (
            "Col. Roma Norte C.P. 06700 cerca del hospital.",
            "Calle Azul 2 Col. Roma Norte C.P. 06700",
        ),
    ],
)
def test_prose_after_full_units_and_colonies_does_not_truncate_tokens(suffix, expected):
    assert _addresses("Calle Azul 2 " + suffix) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "Paciente ubicada en Glasgow 15 puntos.",
        "La lesión se encuentra ubicada en Región Temporal 3 cm.",
        "Reside en Casa Hogar 10 años.",
    ],
)
def test_introduced_measurements_and_durations_are_not_house_numbers(text):
    assert _addresses(text) == []
    assert _addresses("Domicilio en Casa Hogar 10.") == ["Casa Hogar 10"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Vive en 416 Paseo de Martí Diagnóstico: diabetes.", "416 Paseo de Martí"),
        ("Calle Azul 2 Col. Roma Norte Diagnóstico: diabetes.", "Calle Azul 2 Col. Roma Norte"),
    ],
)
def test_unlabelled_address_extensions_stop_at_next_explicit_field(text, expected):
    assert _addresses(text) == [expected]


def test_address_overlap_index_matches_direct_interval_selection():
    rng = random.Random(1729)
    for _ in range(30):
        candidates = [
            AddressCandidate(start, start + rng.randrange(1, 90), rng.choice((0.8, 0.9)), ())
            for start in (rng.randrange(500) for _ in range(100))
        ]
        labelled = [(40, 90), (80, 130), (300, 325)]
        expected = []
        for candidate in sorted(candidates, key=lambda a: (-(a.end - a.start), -a.score, a.start)):
            if any(start <= candidate.start and candidate.end <= end for start, end in labelled):
                continue
            if any(
                candidate.start < other.end and other.start < candidate.end for other in expected
            ):
                continue
            expected.append(candidate)
        assert _select_addresses(candidates, labelled) == expected


def test_address_overlap_index_scales_with_adversarial_length_order():
    timings = []
    for count in (6000, 24000):
        candidates = [
            AddressCandidate(i * 100, i * 100 + (i % 97) + 1, 0.8, ()) for i in range(count)
        ]
        start = time.perf_counter()
        assert len(_select_addresses(candidates, [])) == count
        timings.append(time.perf_counter() - start)
    assert timings[1] < timings[0] * 9
