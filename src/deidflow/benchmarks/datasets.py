"""Seeded, entirely fictional evaluation records, with exact Python text spans.

Templates and value namespaces are disjoint across train/validation/test.  These
small synthetic corpora are regression instruments, not population estimates.
"""

from __future__ import annotations

import hashlib
import json
import random
import string
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoldSpan:
    entity_type: str
    start: int
    end: int


@dataclass(frozen=True)
class Example:
    id: str
    text: str
    spans: tuple[GoldSpan, ...]
    split: str
    template_id: str
    source_format: str = "text"
    challenge: str = "standard"


_TEMPLATES: dict[str, tuple[str, ...]] = {
    "train": (
        "Correo: {EMAIL}. Teléfono: {PHONE}.",
        "Paciente: {PERSON}\nCURP: {CURP}\nDiagnóstico: {DIAGNOSIS}",
        "El RFC es {RFC}; la CLABE bancaria es {CLABE}.",
        "Cliente: {CUSTOMER_ID}. Dirección: {ADDRESS}",
        "La credencial de servicio es api_key={API_KEY}.",
    ),
    "validation": (
        "Para responder utilice {EMAIL}; contacto telefónico {PHONE}.",
        "Expediente\nNombre: {PERSON}\nCURP {CURP}\nPadece {MEDICAL_CONDITION}.",
        "Transferir a CLABE {CLABE}. Registro fiscal: {RFC}.",
        "Número de cliente: {CUSTOMER_ID}\nDomicilio: {ADDRESS}",
        "Variable de entorno: api_key={API_KEY}",
    ),
    "test": (
        "No publique este mensaje: {EMAIL}\nTel: {PHONE}.",
        "Nombre del paciente: {PERSON}.\nSu CURP es {CURP}.\nDiagnóstico: {DIAGNOSIS}.",
        "Datos para facturación\nRFC: {RFC}\nCuenta de destino CLABE {CLABE}",
        "ID de cliente: {CUSTOMER_ID}; enviar a\nDirección: {ADDRESS}",
        "Se encontró la siguiente asignación: api_key={API_KEY}",
    ),
}

_NEGATIVES: dict[str, tuple[str, ...]] = {
    "train": (
        "La diabetes es una enfermedad estudiada en este artículo general.",
        "El correo electrónico es un medio de comunicación.",
        "El presupuesto total fue de 2500 pesos.",
    ),
    "validation": (
        "Este manual describe la hipertensión sin describir a una persona.",
        "La tabla contiene 18 columnas y 900 filas.",
        "Un RFC debe comprobarse antes de procesarse.",
    ),
    "test": (
        "La diabetes puede tratarse: este es material educativo general.",
        "En 2024 se procesaron 250000 registros de ejemplo.",
        "Una CLABE tiene dieciocho dígitos; esto no es un número de cuenta.",
        "Factura de prueba por $12,345.67, sin datos de una persona.",
    ),
}


def clabe_check_digit(prefix: str) -> str:
    if len(prefix) != 17 or not prefix.isascii() or not prefix.isdigit():
        raise ValueError("CLABE prefix must contain seventeen ASCII digits")
    total = sum((int(c) * (3, 7, 1)[i % 3]) % 10 for i, c in enumerate(prefix))
    return str((-total) % 10)


def _values(split: str, index: int, rng: random.Random) -> dict[str, str]:
    # Reserved example domains and explicit fictional data only.  Identifiers
    # satisfy selected structural checks; they do not establish registry status.
    namespace = {"train": "a", "validation": "b", "test": "c"}[split]
    suffix = f"{index:06d}"
    prefix = "002180" + str({"train": 1, "validation": 2, "test": 3}[split]) + suffix + "1234"
    name_prefix = {"train": "Amalia", "validation": "Beatriz", "test": "Cecilia"}[split]
    # This artificial family name makes cross-split identity overlap impossible.
    letters = "".join(string.ascii_lowercase[(index // 26**power) % 26] for power in range(4))
    name = f"{name_prefix} Prueba{namespace}{letters}"
    curp_prefix = {"train": "PAOA", "validation": "PEOB", "test": "PIOC"}[split]
    curp = curp_prefix + "900101MDFRRN" + "0"
    alphabet = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
    total = sum(alphabet.index(c) * (18 - i) for i, c in enumerate(curp))
    curp += str((-total) % 10)
    token = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(32))
    from deidflow.validators import rfc_check_digit

    rfc_prefix = {"train": "PAOA900101AA", "validation": "PEOB900101BB", "test": "PIOC900101CC"}[
        split
    ]
    return {
        "EMAIL": f"persona.{namespace}.{suffix}@example.org",
        "PHONE": f"55 {index % 10000:04d} {int(namespace, 36) * 100 + index % 100:04d}",
        "PERSON": name,
        "CURP": curp,
        "RFC": rfc_prefix + rfc_check_digit(rfc_prefix),
        "CLABE": prefix + clabe_check_digit(prefix),
        "CUSTOMER_ID": f"{namespace.upper()}-{suffix}",
        "ADDRESS": f"Calle Ejemplo {int(namespace, 36) * 1000 + index},\nColonia Sintética, CDMX",
        "API_KEY": token,
        "MEDICAL_CONDITION": {"train": "diabetes", "validation": "hipertensión", "test": "asma"}[
            split
        ],
        "DIAGNOSIS": {"train": "diabetes", "validation": "hipertensión", "test": "asma"}[split],
    }


def _render(template: str, values: dict[str, str]) -> tuple[str, tuple[GoldSpan, ...]]:
    import re

    pieces: list[str] = []
    spans: list[GoldSpan] = []
    length = 0
    previous = 0
    for match in re.finditer(r"\{([A-Z_]+)\}", template):
        literal = template[previous : match.start()]
        pieces.append(literal)
        length += len(literal)
        label = match.group(1)
        value = values[label]
        pieces.append(value)
        spans.append(GoldSpan(label, length, length + len(value)))
        length += len(value)
        previous = match.end()
    pieces.append(template[previous:])
    return "".join(pieces), tuple(spans)


def synthetic_corpus(split: str = "test", *, count: int = 150, seed: int = 1729) -> list[Example]:
    if split not in _TEMPLATES:
        raise ValueError("split must be train, validation, or test")
    if count < 1:
        raise ValueError("count must be positive")
    rng = random.Random(f"deidflow:{seed}:{split}")
    examples: list[Example] = []
    for index in range(count):
        template_index = index % len(_TEMPLATES[split])
        template = _TEMPLATES[split][template_index]
        text, spans = _render(template, _values(split, index, rng))
        examples.append(
            Example(f"{split}-{index:06d}", text, spans, split, f"{split}-t{template_index}")
        )
    for index, text in enumerate(_NEGATIVES[split]):
        examples.append(
            Example(
                f"{split}-negative-{index}",
                text,
                (),
                split,
                f"{split}-n{index}",
                challenge="negative",
            )
        )
    if split == "test":
        challenges = (
            ("split", "CLABE: {CLABE}"),
            ("mixed-language", "Please contact {EMAIL}; este es el único contacto."),
            ("multiline", "Domicilio: {ADDRESS}"),
            ("unlabelled-person", "Ayer habló {PERSON} con el equipo y pidió confidencialidad."),
            ("ocr-degradation", "CURP: {CURP}"),
        )
        for index, (challenge, template) in enumerate(challenges):
            values = _values(split, count + index, rng)
            if challenge == "split":
                number = values["CLABE"]
                values["CLABE"] = number[:6] + "\n" + number[6:12] + " " + number[12:]
            elif challenge == "ocr-degradation":
                values["CURP"] = values["CURP"][:5] + "O" + values["CURP"][6:]
            text, spans = _render(template, values)
            examples.append(
                Example(
                    f"test-challenge-{index}",
                    text,
                    spans,
                    split,
                    f"challenge-{index}",
                    challenge=challenge,
                )
            )
    return examples


def write_corpus(path: str | Path, examples: Iterable[Example]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("wb") as stream:
        for example in examples:
            line = (json.dumps(asdict(example), ensure_ascii=False, sort_keys=True) + "\n").encode(
                "utf-8"
            )
            stream.write(line)
            digest.update(line)
    return digest.hexdigest()


def read_corpus(path: str | Path) -> list[Example]:
    result = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            data = json.loads(line)
            spans = tuple(GoldSpan(**s) for s in data.pop("spans"))
            example = Example(spans=spans, **data)
            if any(s.start < 0 or s.end <= s.start or s.end > len(example.text) for s in spans):
                raise ValueError("invalid benchmark annotation")
            result.append(example)
    return result
