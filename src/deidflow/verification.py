"""Detector-independent output checks for the release gate.

Re-scanning a transformed text with the same detector cannot find what that
detector missed. These checks use a different signal (orthography) so that a
missed name in otherwise "clean" output yields REVIEW_REQUIRED rather than
APPROVED. They report counts only, never the matched words.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_CAPITALIZED = re.compile(
    r"(?<![\w\[])[A-ZÁÉÍÓÚÜÑÀÈÌÒÙÇÏ][a-záéíóúüñàèìòùçï]+(?:[-'’][A-Za-záéíóúüñàèìòùçï]+)?"
)
_SENTENCE_OPENERS = ".!?:;\n\r\t•·*-—–|>#/"
_FIELD_LABEL = re.compile(r"[ \t]*:")
_ALLOWED = frozenset(
    """
    dr dra sr sra srta lic ing mtro mtra prof profa arq enf lcdo lcda don dona doña
    usted ustedes ud uds vd vds dios
    lunes martes miercoles jueves viernes sabado domingo
    enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre
    noviembre diciembre
    """.split()
)


def _fold(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", word.casefold())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def residual_proper_nouns(
    text: str,
    protected: Iterable[tuple[int, int]] = (),
    *,
    allowed: Iterable[str] = (),
) -> int:
    """Count mid-sentence capitalized words outside generated placeholders.

    Spanish capitalizes proper nouns, not ordinary words, so such a word after
    transformation is a possible residual name, place or organization.
    """
    ranges: list[tuple[int, int]] = []
    for start, end in sorted(protected):
        if start >= end:
            continue
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(end, ranges[-1][1]))
        else:
            ranges.append((start, end))
    extra = {_fold(w) for w in allowed}
    count = range_index = 0
    for match in _CAPITALIZED.finditer(text):
        while range_index < len(ranges) and ranges[range_index][1] <= match.start():
            range_index += 1
        if range_index < len(ranges) and ranges[range_index][0] <= match.start():
            continue
        # Inspect only the preceding separator, never copy the entire prefix for
        # each candidate in a long document.
        before = match.start() - 1
        while before >= 0 and text[before] in " \t\"'«“‘(¿¡":
            before -= 1
        if before < 0 or text[before] in _SENTENCE_OPENERS or text[before].isdigit():
            continue
        if _FIELD_LABEL.match(text, match.end()):  # "Provincia:" is a form label
            continue
        word = _fold(match.group())
        if word in _ALLOWED or word in extra:
            continue
        count += 1
    return count


__all__ = ["residual_proper_nouns"]
