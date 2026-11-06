"""Local contextual Spanish recognizers motivated by public development errors.

No patient names, source excerpts, training vocabulary or corpus-specific IDs are
stored here. These additions retain every original high-risk rule candidate.
"""

from __future__ import annotations

import re
from datetime import date

from deidflow.core import Finding

_FLAGS = re.IGNORECASE | re.UNICODE
_NUMBER_LABEL = re.compile(r"(?<!\w)[Nn][º°](?!\w)")
# Necessary condition for every recognizer below: fields contain ':', phones '+',
# dates a digit plus date delimiter/'de', ages 'años', or a DNI/NIF/NIE label.
# This changes only whether a provably empty set is scanned, never candidate rules.
_TRIGGER = re.compile(
    r"[:+]|[0-9][ \t]+de[ \t]|[0-9][/.-][0-9]|[0-9][ \t]+a[ñn]os\b|\b(?:DNI|NIF|NIE)\b",
    _FLAGS,
)
_LETTER = r"[A-ZÁÉÍÓÚÜÑ]"
_WORD = _LETTER + r"[A-ZÁÉÍÓÚÜÑ'’-]{0,63}"
_STOP = r"(?=[ \t]*(?:N[º°o.]?[ \t]*Col(?:egiad[oa])?[ \t]*:|Nombre[ \t]*:|Apellidos[ \t]*:|[\r\n,;]|$))"
_PERSON = re.compile(
    r"\b(?:nombre(?:[ \t]+completo)?|apellidos|m[eé]dico|responsable[ \t]+cl[ií]nico|remitido[ \t]+por)[ \t]*:[ \t]*(?:(?:Dr|Dra)\.[ \t]*)?(?P<value>"
    + _WORD
    + r"(?:[ \t]+"
    + _WORD
    + r"){0,7})"
    + _STOP,
    _FLAGS,
)
_CLINICAL_ID = re.compile(
    r"(?P<label>\bNHC|\bNASS|\bNSS|\bCIPA|\bepisodio|N[º°o.]?[ \t]*Col(?:egiad[oa])?)[ \t]*:[ \t]*(?:nhc-)?(?P<value>[0-9](?:[0-9 \t]{2,26})[0-9])(?![0-9])",
    _FLAGS,
)
_DNI = re.compile(
    r"\b(?:DNI|NIF|NIE)[ \t]*[:=]?[ \t]*(?P<value>(?:[0-9][ \t.-]*){8}[A-Z]|[XYZ][ \t.-]*(?:[0-9][ \t.-]*){7}[A-Z])(?!\w)",
    _FLAGS,
)
_INTERNATIONAL_PHONE = re.compile(
    r"(?<!\w)\+(?:[0-9][ \t().-]*(?:\r?\n[ \t]*)?){7,14}[0-9](?!\w|[ \t.-]*[0-9])"
)
_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS)
_WRITTEN_DATE = re.compile(
    r"(?<!\w)(?P<day>[0-3]?[0-9])[ \t]+de[ \t]+(?P<month>"
    + _MONTH_PATTERN
    + r")[ \t]+de[ \t]+(?P<year>(?:19|20)[0-9]{2})(?!\w)",
    _FLAGS,
)
_SHORT_DATE = re.compile(
    r"(?<![\w/.-])(?P<day>[0-3]?[0-9])(?P<sep>[/.-])(?P<month>[01]?[0-9])(?P=sep)(?P<year>(?:19|20)[0-9]{2}|[0-9]{2})(?![\w/.-])"
)
_DOB = re.compile(r"(?:nacimiento|naci[oó]|\bDOB)[ \t]*[:=]?[ \t]*$", _FLAGS)
_AGE = re.compile(
    r"\b(?:paciente|var[oó]n|mujer|hombre|niñ[oa])[^\n.;:]{0,35}?[ \t]+(?P<value>[0-9]{1,3})[ \t]+a[ñn]os\b",
    _FLAGS,
)
_SEX_FIELD = re.compile(
    r"\bsexo[ \t]*:[ \t]*(?P<value>H|M|F|masculino|femenino|hombre|mujer|var[oó]n)(?!\w)", _FLAGS
)
_SEX_AGE = re.compile(
    r"\b(?P<value>var[oó]n|mujer|hombre)[ \t]+(?:de[ \t]+)?[0-9]{1,3}[ \t]+a[ñn]os\b", _FLAGS
)


def person_field_boundary(lexical_text: str, start: int, end: int) -> int:
    """A source number-label token is not another surname; literal No remains valid."""
    marker = _NUMBER_LABEL.search(lexical_text, start, end)
    if marker is None:
        return end
    boundary = marker.start()
    while boundary > start and lexical_text[boundary - 1] in " \t":
        boundary -= 1
    return boundary


def contextual_spanish(text: str, *, lexical_text: str | None = None) -> list[Finding]:
    if not _TRIGGER.search(text):
        return []
    findings = []

    def add(
        kind: str,
        start: int,
        end: int,
        score: float,
        *,
        validation: str = "contextual",
        risk: str = "high",
        protected: bool = True,
        context: tuple[str, ...] = (),
    ) -> None:
        findings.append(
            Finding(
                kind,
                start,
                end,
                score,
                "rules.es_clinical",
                validation=validation,
                context=context,
                model_version="clinical-context-0.3",
                risk=risk,
                protected=protected,
            )
        )

    for match in _PERSON.finditer(text):
        start, end = match.span("value")
        end = person_field_boundary(lexical_text if lexical_text is not None else text, start, end)
        if end <= start:
            continue
        # Another label is never a person's name, including blank redacted forms.
        if (
            text[end : end + 1] == ":"
            or re.fullmatch(r"(?i:Nombre|Apellidos|Médico|Paciente|Domicilio)", text[start:end])
            and re.match(r"[ \t]*:", text[end:])
        ):
            continue
        add("PERSON", start, end, 0.9, context=("explicit_person_field",))
    for match in _CLINICAL_ID.finditer(text):
        label = match.group("label").casefold()
        kind = (
            "REGIONAL_ID"
            if "col" in label
            else "INSURANCE_ID"
            if label in {"nass", "nss"}
            else "PATIENT_ID"
        )
        start, end = match.span("value")
        while text[end - 1].isspace():
            end -= 1
        add(kind, start, end, 0.88, context=("explicit_clinical_identifier",))
    for match in _DNI.finditer(text):
        compact = re.sub(r"[ \t.-]", "", match.group("value")).upper()
        digits = compact[:-1].translate(str.maketrans("XYZ", "012"))
        checksum = "TRWAGMYFPDXBNJZSQVHLCKE"[int(digits) % 23] == compact[-1]
        add(
            "NATIONAL_ID",
            *match.span("value"),
            0.98 if checksum else 0.55,
            validation="checksum" if checksum else "invalid",
            context=("explicit_spanish_identifier",),
        )
    for match in _INTERNATIONAL_PHONE.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if 8 <= len(digits) <= 15:
            add(
                "PHONE",
                *match.span(),
                0.92,
                validation="structural",
                context=("international_prefix",),
            )
    for pattern, written in ((_WRITTEN_DATE, True), (_SHORT_DATE, False)):
        for match in pattern.finditer(text):
            year = int(match.group("year"))
            year += 2000 if year < 30 else 1900 if year < 100 else 0
            month = (
                _MONTHS[match.group("month").casefold()] if written else int(match.group("month"))
            )
            try:
                date(year, month, int(match.group("day")))
            except ValueError:
                continue
            dob = bool(_DOB.search(text[max(0, match.start() - 50) : match.start()]))
            add(
                "DATE_OF_BIRTH" if dob else "DATE",
                *match.span(),
                0.85 if dob else 0.7,
                risk="high" if dob else "medium",
                protected=dob,
                validation="structural",
                context=("calendar_date",),
            )
    for match in _AGE.finditer(text):
        if int(match.group("value")) <= 125:
            add(
                "AGE",
                *match.span("value"),
                0.8,
                risk="medium",
                protected=False,
                context=("subject_age",),
            )
    for pattern in (_SEX_FIELD, _SEX_AGE):
        for match in pattern.finditer(text):
            add(
                "DEMOGRAPHIC",
                *match.span("value"),
                0.8,
                risk="medium",
                protected=False,
                context=("subject_demographic",),
            )
    return findings
