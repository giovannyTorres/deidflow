"""Street addresses written the Spanish and Latin American way, without a field label.

Four families, all bounded and linear:

- Colombian (and Venezuelan) grid nomenclature: ``Calle 45 # 12-30``,
  ``Cra. 7 No. 71-21``, ``Cl. 84 Bis T # 8T-94 Sur``. Distinctive on its own.
- An address introduced by residence words: ``domicilio en``, ``vivo en``,
  ``reside en``, ``ubicada en`` followed by a capitalized name and a number
  (``Los Alerces 33``, ``Skolgatan 8``, ``416 Paseo de Martí``).
- A street type, a capitalized name and a number: ``C/ Pintor Baeza, 11``,
  ``Avda. Patricio Lynch 63``, ``Jr. Huallaga 123``, ``Calzada de Tlalpan 1500``.
- Mexican tails that extend any of them: ``Col. Roma Norte``, ``C.P. 06700``.

Floors, doors and units (``Piso 2``, ``8ºB``, ``Bajo A``, ``Dpto. 302``, ``Int. 4``)
are included. A city name or a street without a number is not an address here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from deidflow.normalization import DetectionView

_CAP = r"[A-ZÁÉÍÓÚÜÑ]"
_WORD = r"[\wÁÉÍÓÚÜÑáéíóúüñ'’.-]*"
# Lowercase connectors only: a capitalized word ("San", "Santa") is a name word, so
# every token has exactly one reading and the bounded repetitions cannot backtrack
# combinatorially.
_LINK = r"(?:(?:de(?:l)?|la|las|los|el|y|e)\s+)"
_NAME = rf"(?:{_LINK}{{0,3}}{_CAP}{_WORD}(?:\s+{_LINK}{{0,3}}{_CAP}{_WORD}){{0,5}})"
_TYPE = (
    r"(?i:calle|c/|cl\.|cll\.|avenida|avda\.|av\.|paseo|pº|plaza|pza\.|ronda|rambla|camino"
    r"|carretera|ctra\.|traves[íi]a|glorieta|jir[óo]n|jr\.|pasaje|psje\.|calzada|calz\."
    r"|bulevar|boulevard|blvd\.|privada|priv\.|prolongaci[óo]n|prol\.|callej[óo]n|cerrada"
    r"|andador|urbanizaci[óo]n|urb\.|v[íi]a|vial|ca[ñn]ada|diagonal|transversal|carrera"
    r"|cra\.|autopista|circunvalaci[óo]n|alameda|malec[óo]n|costanera|ruta)"
)
_NUMBER = (
    r"(?:(?i:n[úu]m(?:ero)?\.?|no\.|n[º°]\.?|nro\.?|\#)\s*)?"
    r"\d{1,5}[A-Za-z]?(?:\s*[-–]\s*\d{1,5}[A-Za-z]?)?"
    r"|(?i:s/n)"
)
_UNIT = (
    r"(?:,?\s*(?i:piso|planta|puerta|pta\.|depto\.?|dpto\.?|departamento|apto\.?|apartamento"
    r"|apt\.?|int\.?|interior|local|of\.|oficina|casa|torre|bloque|blq\.|escalera|esc\."
    r"|portal|edificio|edif\.|manzana|mz\.?|lote|lt\.)\s*[\wºª°-]{1,8}(?![\wºª°-])"
    r"|,?\s*\d{1,2}\s*[ºª°]\s*[A-Z]?(?![\w])"
    r"|,\s*\d{1,2}[A-Z](?![\w])"
    r"|,?\s*(?i:bajo|[áa]tico|entresuelo|principal)(?:\s+[A-Z])?(?![\w]))"
)
_POSTAL_LABEL = r"(?i:c\.\s?p\.|cp|c[óo]digo\s+postal)"
_COLONY_WORD = rf"(?!{_POSTAL_LABEL}\s*:?\s*\d{{5}}){_CAP}{_WORD}"
_TAIL = (
    rf"(?:,?\s*(?i:col\.|colonia)\s+{_COLONY_WORD}(?:\s+{_LINK}{{0,3}}{_COLONY_WORD}){{0,4}})?"
    rf"(?:,?\s*{_POSTAL_LABEL}\s*:?\s*\d{{5}}(?!\d))?"
)
_COLOMBIAN = re.compile(
    r"(?<![\w])(?i:calle|cl\.?|cll\.?|carrera|cra\.?|kra\.?|kr\.?|avenida(?:\s+(?:calle|carrera))?"
    r"|av\.?|ak\.?|ac\.?|diagonal|dg\.?|transversal|tv\.?|tr\.?)\s*"
    r"\d{1,3}\s?[A-Z]{0,2}(?:\s?(?i:bis))?(?:\s?[A-Z])?(?:\s+(?i:sur|este|norte|oeste))?\s*"
    r"(?:\#|(?i:no\.?|n[º°]\.?|nro\.?|n[úu]mero))\s*"
    r"\d{1,3}\s?[A-Z]{0,2}(?:\s?(?i:bis))?\s*[-–]\s*\d{1,3}"
    r"(?:\s+(?i:sur|este|norte|oeste))?(?![\w])" + rf"(?:{_UNIT}){{0,3}}"
)
_CONTEXT = (
    r"(?i:domicilio(?:\s+(?:social|fiscal|particular|actual|habitual))?|domiciliad[oa]s?"
    r"|vive|vivo|vivimos|viven|reside|resido|residen|residente|ubicad[oa]s?|situad[oa]s?"
    r"|localizad[oa]s?|con\s+domicilio)"
    r"\s+(?i:en)\s+(?:(?i:la|el)\s+)?"
)
_TYPED = rf"{_TYPE}\s*{_NAME},?\s+(?:{_NUMBER})(?![\w])(?:{_UNIT}){{0,4}}{_TAIL}(?![\w])"
_UNTYPED = rf"{_NAME},?\s+(?:{_NUMBER})(?![\w])(?:{_UNIT}){{0,4}}{_TAIL}(?![\w])"
_NUMBER_FIRST = rf"\d{{1,5}}\s+(?:{_TYPE}\s+)?{_NAME}(?:{_UNIT}){{0,4}}{_TAIL}(?![\w])"
_INTRODUCED = re.compile(rf"(?<![\w]){_CONTEXT}(?P<value>{_TYPED}|{_UNTYPED}|{_NUMBER_FIRST})")
# Validate following measurement language after the greedy match in Python.
# A trailing negative lookahead here let regex backtracking truncate a unit or
# colony word ("302" -> "30", "Norte" -> "Nort") to evade that validation.
_STREET = re.compile(rf"(?<![\w])(?P<value>{_TYPED})")
_MEASUREMENT_AFTER = re.compile(
    r"\s+(?i:veces?|puntos?|d[ií]as?|a[nñ]os?|meses?|semanas?|horas?|minutos?|segundos?|"
    r"cm|mm|metros?|cent[ií]metros?|mil[ií]metros?|mg|miligramos?|kg|kilogramos?|"
    r"comprimidos?|dosis)(?!\w)"
)
_COLONIA = re.compile(
    rf"(?<![\w])(?P<value>(?i:col\.|colonia)\s+{_COLONY_WORD}(?:\s+{_LINK}{{0,3}}{_COLONY_WORD}){{0,4}}"
    r",?\s*(?i:c\.\s?p\.|cp)\s*:?\s*\d{5})(?!\d)"
)


@dataclass(frozen=True)
class AddressCandidate:
    start: int
    end: int
    score: float
    context: tuple[str, ...]


def address_lexical_view(source: str, view: DetectionView) -> str:
    """Interpret source ordinal token classes at normalized view coordinates.

    NFKC merges ordinal indicators with ordinary a/o, although these have
    different roles in house numbers, floors and street abbreviations. Validate
    that distinction using source provenance, rather than accepting ordinary
    prose such as '3 o más' as a floor. This does not change any view offsets.
    """
    if "ª" not in source and "º" not in source:
        return view.text
    characters = list(view.text)
    for index, character in enumerate(characters):
        if character in "ao":
            start, end = view.bounds(index, index + 1)
            original = source[start:end]
            if "ª" in original and character == "a":
                characters[index] = "ª"
            elif "º" in original and character == "o":
                characters[index] = "º"
    return "".join(characters)


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while end > start and text[end - 1] in " \t,.;:":
        end -= 1
    return start, end


def address_candidates(text: str) -> Iterator[AddressCandidate]:
    for match in _COLOMBIAN.finditer(text):
        yield AddressCandidate(*_trim(text, *match.span()), 0.9, ("address:grid",))
    for match in _INTRODUCED.finditer(text):
        if _MEASUREMENT_AFTER.match(text, match.end("value")):
            continue
        yield AddressCandidate(*_trim(text, *match.span("value")), 0.85, ("address:introduced",))
    for match in _STREET.finditer(text):
        if _MEASUREMENT_AFTER.match(text, match.end("value")):
            continue
        start, end = _trim(text, *match.span("value"))
        detailed = end - start > 0 and bool(
            re.search(r"[,ºª°]|\b(?i:piso|c\.\s?p|col)", text[start:end])
        )
        yield AddressCandidate(start, end, 0.85 if detailed else 0.8, ("address:street",))
    for match in _COLONIA.finditer(text):
        yield AddressCandidate(*_trim(text, *match.span("value")), 0.8, ("address:colonia",))


__all__ = ["AddressCandidate", "address_candidates"]
