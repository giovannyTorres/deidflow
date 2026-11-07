"""Spanish narrative recognizers: people introduced by titles/relations, places,
health facilities, institutions, Mexican identifiers and address tails.

This optional recognizer is not enabled by RuleDetector defaults.
Its scores are heuristic, not calibrated model probabilities.

These rules target free text sent to LLMs ("la señora Verónica fue atendida por el
doctor Jiménez"). Role and grammatical-gender evidence is recorded in
``Finding.context`` as ``role:<name>`` / ``gender:<f|m>`` so that indexed
placeholders can preserve who-is-who without exposing identity. Scores remain
uncalibrated evidence ranks.
"""

from __future__ import annotations

import re
import unicodedata

from deidflow.core import Finding
from deidflow.normalization import DetectionView, ordinal_feature_text

from .gazetteer import AMBIGUOUS_GIVEN, GIVEN_NAMES, INSTITUTIONS, LOCATIONS, variants

_UPPER = "A-ZÁÉÍÓÚÜÑÀÈÌÒÙÇÏ"
_LOWER = "a-záéíóúüñàèìòùçï"
# Capitalized words that start institutional or generic phrases, never a name token.
_NOT_NAME = (
    r"(?!(?:Hospital|Cl[ií]nica|Centro|Instituto|Sanatorio|Universidad|Unidad|Servicio|"
    r"Departamento|General|Nacional|Federal|Estatal|Municipal|Oficial|Mexicana|Mexicano|"
    r"Juzgado|Tribunal|Secretar[ií]a|Colonia|Calle|Avenida|Urgencias|Consulta|Doctor|"
    r"Doctora|Señor|Señora|Paciente|Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|"
    r"Domingo)\b)"
)
_NAME_TOKEN = _NOT_NAME + rf"[{_UPPER}][{_LOWER}]+(?:[-'’][{_UPPER}{_LOWER}][{_LOWER}]+)?"
_CONNECTOR = r"(?:de[ \t]+la|de[ \t]+las|de[ \t]+los|del|de|y|e|van|von|da|di)"
_GIVEN_WORDS = "|".join(re.escape(n) for n in variants(GIVEN_NAMES))
# A conjunction followed by another known given name and surname starts another
# person. Keep surname conjunctions such as "Ortega y Gasset" intact.
_NOT_COORDINATED_PERSON = rf"(?![ \t]+(?:y|e)[ \t]+(?:{_GIVEN_WORDS})[ \t]+{_NAME_TOKEN})"
# A capitalized place word; a trailing period ends the phrase (sentence boundary).
_PLACE_WORD = rf"[{_UPPER}](?:[\w'’-]|\.(?=\w))*\.?"
_NAME_SEQ = (
    rf"{_NAME_TOKEN}(?:{_NOT_COORDINATED_PERSON}[ \t]+(?:{_CONNECTOR}[ \t]+)?{_NAME_TOKEN}){{0,4}}"
)


def _fold(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value.casefold()) if unicodedata.category(c) != "Mn"
    ).rstrip(".")


_KNOWN_GIVEN = frozenset(_fold(name) for name in GIVEN_NAMES)


def coordinated_person_spans(text: str, start: int, end: int) -> tuple[tuple[int, int], ...]:
    """Split only full coordinated names with known given names and surnames.

    This separates mentions, not identities. Unknown/ambiguous conjunctions keep
    their full original coverage, including compound surnames and initials.
    """
    separators = list(re.finditer(r"[ \t]+(?:y|e)[ \t]+", text[start:end]))
    if not separators or len(separators) > 3:
        return ((start, end),)
    spans = []
    left = start
    for separator in separators:
        spans.append((left, start + separator.start()))
        left = start + separator.end()
    spans.append((left, end))
    for left, right in spans:
        value = text[left:right]
        words = value.split()
        if (
            len(words) < 2
            or _fold(words[0]) not in _KNOWN_GIVEN
            or not re.fullmatch(_NAME_SEQ, value)
        ):
            return ((start, end),)
    return tuple(spans)


# title -> (role, grammatical gender). Role vocabulary: patient, clinician, family.
_TITLES: dict[str, tuple[str | None, str | None]] = {
    "señor": (None, "m"),
    "senor": (None, "m"),
    "señora": (None, "f"),
    "senora": (None, "f"),
    "señorita": (None, "f"),
    "senorita": (None, "f"),
    "sr": (None, "m"),
    "sra": (None, "f"),
    "srta": (None, "f"),
    "don": (None, "m"),
    "doña": (None, "f"),
    "dona": (None, "f"),
    "licenciado": (None, "m"),
    "licenciada": (None, "f"),
    "lic": (None, None),
    "lcdo": (None, "m"),
    "lcda": (None, "f"),
    "ingeniero": (None, "m"),
    "ingeniera": (None, "f"),
    "ing": (None, None),
    "maestro": (None, "m"),
    "maestra": (None, "f"),
    "mtro": (None, "m"),
    "mtra": (None, "f"),
    "profesor": (None, "m"),
    "profesora": (None, "f"),
    "prof": (None, None),
    "profa": (None, "f"),
    "arquitecto": (None, "m"),
    "arquitecta": (None, "f"),
    "arq": (None, None),
    "abogado": (None, "m"),
    "abogada": (None, "f"),
    "contador": (None, "m"),
    "contadora": (None, "f"),
    "doctor": ("clinician", "m"),
    "doctora": ("clinician", "f"),
    "dr": ("clinician", "m"),
    "dra": ("clinician", "f"),
    "médico": ("clinician", "m"),
    "medico": ("clinician", "m"),
    "médica": ("clinician", "f"),
    "medica": ("clinician", "f"),
    "enfermero": ("clinician", "m"),
    "enfermera": ("clinician", "f"),
    "enf": ("clinician", None),
    "psicólogo": ("clinician", "m"),
    "psicologo": ("clinician", "m"),
    "psicóloga": ("clinician", "f"),
    "psicologa": ("clinician", "f"),
    "psiquiatra": ("clinician", None),
    "cirujano": ("clinician", "m"),
    "cirujana": ("clinician", "f"),
    "odontólogo": ("clinician", "m"),
    "odontóloga": ("clinician", "f"),
    "dentista": ("clinician", None),
    "pediatra": ("clinician", None),
    "ginecólogo": ("clinician", "m"),
    "ginecóloga": ("clinician", "f"),
    "cardiólogo": ("clinician", "m"),
    "cardióloga": ("clinician", "f"),
    "nutriólogo": ("clinician", "m"),
    "nutrióloga": ("clinician", "f"),
    "paciente": ("patient", None),
    "derechohabiente": ("patient", None),
}
_RELATIONS: dict[str, str | None] = {
    "hijo": "m",
    "hija": "f",
    "esposo": "m",
    "esposa": "f",
    "marido": "m",
    "mujer": "f",
    "madre": "f",
    "padre": "m",
    "mamá": "f",
    "mama": "f",
    "papá": "m",
    "papa": "m",
    "hermano": "m",
    "hermana": "f",
    "abuelo": "m",
    "abuela": "f",
    "tío": "m",
    "tio": "m",
    "tía": "f",
    "tia": "f",
    "primo": "m",
    "prima": "f",
    "sobrino": "m",
    "sobrina": "f",
    "nieto": "m",
    "nieta": "f",
    "cónyuge": None,
    "conyuge": None,
    "pareja": None,
    "novio": "m",
    "novia": "f",
    "suegro": "m",
    "suegra": "f",
    "tutor": "m",
    "tutora": "f",
}
_ABBREVIATED = {"sr", "sra", "srta", "lic", "lcdo", "lcda", "ing", "mtro", "mtra", "prof", "profa"}
_ABBREVIATED |= {"arq", "dr", "dra", "enf"}
_TITLE_LOOKUP = {_fold(k): v for k, v in _TITLES.items()}
_RELATION_LOOKUP = {_fold(k): v for k, v in _RELATIONS.items()}


def _title_pattern() -> str:
    words = variants([t for t in _TITLES if t not in _ABBREVIATED])
    abbreviations = sorted(_ABBREVIATED, key=len, reverse=True)
    return (
        r"(?P<title>\b(?i:"
        + "|".join(re.escape(w) for w in words)
        + r")\b|\b(?i:"
        + "|".join(re.escape(a) for a in abbreviations)
        + r")\.)"
    )


_TITLED = re.compile(_title_pattern() + rf"[ \t]*(?:\r?\n[ \t]*)?(?P<value>{_NAME_SEQ})")
_RELATION = re.compile(
    r"\b(?i:su|sus|mi|mis|tu|la|el)[ \t]+(?P<relation>(?i:"
    + "|".join(re.escape(r) for r in variants(list(_RELATIONS)))
    + rf"))\b[ \t]*,?[ \t]+(?P<value>{_NAME_SEQ})"
)
_INTRODUCED = re.compile(
    r"\b(?i:me[ \t]+llamo|mi[ \t]+nombre[ \t]+es|su[ \t]+nombre[ \t]+es|de[ \t]+nombre|"
    r"llamad[oa]|se[ \t]+llama(?:ba)?|conocid[oa][ \t]+como|a[ \t]+nombre[ \t]+de)"
    rf"[ \t]+(?P<value>{_NAME_SEQ})"
)
_GIVEN = re.compile(
    r"(?<![\w])(?P<value>(?:"
    + _GIVEN_WORDS
    + rf")(?:{_NOT_COORDINATED_PERSON}[ \t]+(?:{_CONNECTOR}[ \t]+)?{_NAME_TOKEN}){{0,4}})(?![\w])"
)
_AMBIGUOUS_GIVEN = re.compile(
    r"(?<![\w])(?P<value>(?:"
    + "|".join(re.escape(n) for n in variants(AMBIGUOUS_GIVEN))
    + rf")(?:{_NOT_COORDINATED_PERSON}[ \t]+(?:{_CONNECTOR}[ \t]+)?{_NAME_TOKEN}){{1,4}})(?![\w])"
)
_LOCATION = re.compile(
    r"(?<![\w])(?:" + "|".join(re.escape(n) for n in variants(LOCATIONS)) + r")(?![\w])"
)
_INSTITUTION = re.compile(
    r"(?<![\w])(?:" + "|".join(re.escape(n) for n in variants(INSTITUTIONS)) + r")(?![\w-])"
)
_PROPER_TAIL = (
    rf"(?:[ \t]+(?:(?:{_CONNECTOR}|la|el|las|los)[ \t]+)?"
    rf"(?:[{_UPPER}][\w.'’-]*|N[º°o]\.?[ \t]*[0-9]{{1,4}}|[0-9]{{1,4}})){{1,7}}"
)
_FACILITY = re.compile(
    r"\b(?P<value>(?i:hospital(?:es)?(?:[ \t]+universitario)?|cl[íi]nica|sanatorio|"
    r"policl[íi]nica|centro[ \t]+(?:de[ \t]+salud|m[ée]dico|hospitalario|de[ \t]+especialidades|"
    r"de[ \t]+atenci[óo]n[ \t]+primaria)|unidad[ \t]+de[ \t]+medicina[ \t]+familiar|UMF|"
    r"ambulatorio|consultorio|complejo[ \t]+hospitalario)" + _PROPER_TAIL + ")"
)
_ORGANIZATION = re.compile(
    r"\b(?P<value>(?:Universidad|Instituto|Fundaci[óo]n|Asociaci[óo]n|Banco|Grupo|Colegio|"
    r"Escuela|Aseguradora|Seguros|Despacho|Bufete|Empresa|Compañ[íi]a)" + _PROPER_TAIL + ")"
)
_COMPANY = re.compile(
    rf"(?<![\w])(?P<value>[{_UPPER}][\w&.'’-]*(?:[ \t]+(?:{_CONNECTOR}[ \t]+)?[{_UPPER}][\w&.'’-]*){{0,4}}"
    r",?[ \t]+(?:S\.?[ \t]?A\.?[ \t]?P\.?[ \t]?I\.?|S\.?[ \t]?A\.?|S\.?[ \t]?C\.?|S\.?[ \t]?L\.?|"
    r"S\.?[ \t]?de[ \t]?R\.?[ \t]?L\.?)(?:[ \t]+de[ \t]+C\.?[ \t]?V\.?)?)(?![\w])"
)
_SETTLEMENT = re.compile(
    r"\b(?P<kind>(?i:colonia|col\.|fraccionamiento|fracc\.|barrio|alcald[íi]a|municipio|"
    r"delegaci[óo]n|localidad|poblado|ejido|comunidad))[ \t]*(?:(?:de|del)[ \t]+)?"
    rf"(?P<value>{_PLACE_WORD}(?:(?<!\.)[ \t]+(?:(?:{_CONNECTOR}|la|el)[ \t]+)?"
    rf"(?:{_PLACE_WORD}|[0-9]{{1,3}})){{0,4}})"
)
_POSTAL = re.compile(
    r"\b(?i:C\.?[ \t]?P\.?|c[óo]digo[ \t]+postal)[ \t]*:?[ \t]*(?P<value>[0-9]{4,5})(?![0-9])"
)
_PLACE_FIELD = re.compile(
    r"\b(?i:localidad|provincia|municipio|ciudad|poblaci[óo]n|pa[íi]s|estado|residencia|"
    r"lugar[ \t]+de[ \t]+(?:nacimiento|residencia|origen)|nacionalidad|procedencia)"
    r"(?:[ \t]*/[ \t]*(?i:provincia|estado|pa[íi]s|municipio))?[ \t]*:[ \t]*"
    rf"(?P<value>{_PLACE_WORD}(?:(?<!\.)[ \t]*[-/]?[ \t]*(?:(?:{_CONNECTOR}|la|el|los)[ \t]+)?"
    rf"{_PLACE_WORD}){{0,4}})"
)
_STREET = re.compile(
    r"\b(?P<value>(?i:calle|c/\.?|avenida|avda\.?|av\.?|calzada|calz\.|bulevar|boulevard|blvd\.?|"
    r"privada|priv\.|prolongaci[óo]n|prol\.|andador|callej[óo]n|paseo|p[ºo]\.?|perif[ée]rico|"
    r"carretera|ctra\.|camino|circuito|cerrada|retorno|plaza|pza\.|ronda|traves[íi]a|glorieta|"
    r"carrer|r[úu]a|gran[ \t]+v[íi]a|urbanizaci[óo]n|urb\.)"
    r"[ \t]*(?:(?:de|del|de[ \t]+la|de[ \t]+los|la|el|los)[ \t]+)?"
    rf"[{_UPPER}0-9][\w.'’-]*(?:[ \t]+(?:(?:{_CONNECTOR}|la|el|los)[ \t]+)?[{_UPPER}0-9][\w.'’-]*){{0,5}}"
    r"(?:,?[ \t]+(?i:n[úu]m(?:ero)?\.?|n\.?[ºo°]\.?|no\.?|#)?[ \t]*"
    r"(?:[0-9]{1,5}(?:[ \t]?[A-Z](?![\w])|[ \t]*-[ \t]*[0-9A-Z]{1,4})?|(?i:s[ \t]*/[ \t]*n))"
    r"(?:[ \t]*[,-]?[ \t]*(?:[0-9]{1,2}[ \t]*\.?[ \t]*[ºª°][ \t]*[A-Za-z]{0,5}\.?|"
    r"(?i:bajo(?:[ \t]+(?:izq|izda|der|dcha)\.?)?|(?:int(?:erior)?|depto|departamento|piso|local|"
    r"planta|puerta|suite)\.?[ \t]*[0-9A-Z]{1,5})|P[0-9][ \t]*[0-9]?[A-Z]?)){0,3}))"
    r"(?![\w])"
)
ADDRESS_TAIL = re.compile(
    r"(?:(?:[ \t]*,[ \t]*|[ \t]+(?=[0-9]{5}(?![0-9])))(?:(?i:col(?:onia)?\.?|fracc(?:ionamiento)?\.?|alcald[íi]a|municipio|"
    r"delegaci[óo]n|C\.?[ \t]?P\.?)[ \t]*)?"
    rf"(?:{_PLACE_WORD}(?:(?<!\.)[ \t]+(?:(?:{_CONNECTOR}|la|el)[ \t]+)?{_PLACE_WORD}){{0,4}}"
    rf"|[0-9]{{5}}(?:[ \t]+{_PLACE_WORD}(?:(?<!\.)[ \t]+{_PLACE_WORD}){{0,2}})?)){{1,5}}"
)
_NSS = re.compile(
    r"\b(?i:NSS|IMSS|n[úu]mero[ \t]+de[ \t]+seguridad[ \t]+social|seguro[ \t]+social)\b"
    r"[^\n0-9]{0,24}?(?P<value>[0-9](?:[ \t-]?[0-9]){10})(?![0-9])"
)
_ELECTOR_KEY = re.compile(r"(?<![\w])[A-Z]{6}[0-9]{8}[HM][0-9]{3}(?![\w])")
_INE_NUMBER = re.compile(
    r"\b(?i:INE|IFE|credencial[ \t]+(?:para[ \t]+votar|de[ \t]+elector))\b[^\n]{0,30}?"
    r"\b(?i:folio|CIC|OCR|n[úu]mero|no\.?)[ \t]*[:#]?[ \t]*(?P<value>[0-9]{9,13})(?![0-9])"
)
_PROFESSIONAL_LICENSE = re.compile(
    r"\b(?i:c[ée]dula(?:[ \t]+profesional)?)[ \t]*(?i:n[úu]m(?:ero)?\.?|no\.?)?[ \t]*[:#]?[ \t]*"
    r"(?P<value>[0-9]{7,8})(?![0-9])"
)
_PASSPORT = re.compile(
    r"\b(?i:pasaporte)[ \t]*(?i:n[úu]m(?:ero)?\.?|no\.?)?[ \t]*[:#]?[ \t]*"
    r"(?P<value>(?=[A-Z0-9]*[0-9])[A-Z][A-Z0-9]{5,11})(?![\w])"
)

_AGE = re.compile(
    r"\b(?i:tiene|ten[íi]a|cumpli[óo]|cumple|cumplir[áa]|edad[ \t]+de)[ \t]+(?P<value>[0-9]{1,3})"
    r"[ \t]+(?i:a[ñn]os)\b|\b(?P<value2>[0-9]{1,3})[ \t]+(?i:a[ñn]os[ \t]+de[ \t]+edad)\b"
)


def luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def narrative_spanish(text: str) -> list[Finding]:
    findings: list[Finding] = []

    def add(
        kind: str,
        start: int,
        end: int,
        score: float,
        *,
        context: tuple[str, ...] = (),
        risk: str = "high",
        protected: bool = True,
        validation: str = "contextual",
    ) -> None:
        while end > start and text[end - 1] in " \t.,;":
            end -= 1
        if end > start:
            spans = (
                coordinated_person_spans(text, start, end) if kind == "PERSON" else ((start, end),)
            )
            # A regex stopped before another full given-name sequence. Mark the
            # boundary decision even when no broad span needed splitting.
            coordinated = len(spans) > 1 or (
                kind == "PERSON"
                and bool(
                    re.match(
                        rf"[ \t]+(?:y|e)[ \t]+(?:{_GIVEN_WORDS})[ \t]+{_NAME_TOKEN}", text[end:]
                    )
                )
            )
            if coordinated:
                context = (*context, "person_coordination_split")
        else:
            spans = ()
        for start, end in spans:
            findings.append(
                Finding(
                    kind,
                    start,
                    end,
                    score,
                    "rules.es_narrative",
                    validation=validation,
                    context=context,
                    model_version="narrative-0.5",
                    risk=risk,
                    protected=protected,
                )
            )

    for match in _TITLED.finditer(text):
        role, gender = _TITLE_LOOKUP.get(_fold(match.group("title")), (None, None))
        context = ["person_title"]
        if role:
            context.append(f"role:{role}")
        if gender:
            context.append(f"gender:{gender}")
        add("PERSON", *match.span("value"), 0.88, context=tuple(context))
    for match in _RELATION.finditer(text):
        gender = _RELATION_LOOKUP.get(_fold(match.group("relation")))
        relation = ("person_relation", "role:family") + ((f"gender:{gender}",) if gender else ())
        add("PERSON", *match.span("value"), 0.85, context=relation)
    for match in _INTRODUCED.finditer(text):
        add("PERSON", *match.span("value"), 0.88, context=("person_introduced",))
    for pattern, score in ((_GIVEN, 0.75), (_AMBIGUOUS_GIVEN, 0.8)):
        for match in pattern.finditer(text):
            start, end = match.span("value")
            multi = bool(re.search(r"[ \t]", text[start:end]))
            add(
                "PERSON",
                start,
                end,
                0.85 if multi else score,
                context=("given_name_gazetteer",),
            )
    for match in _LOCATION.finditer(text):
        add("LOCATION", *match.span(), 0.8, context=("location_gazetteer",), risk="medium")
    for match in _INSTITUTION.finditer(text):
        add(
            "ORGANIZATION",
            *match.span(),
            0.85,
            context=("institution_gazetteer",),
            risk="medium",
            protected=False,
        )
    for match in _FACILITY.finditer(text):
        add(
            "MEDICAL_FACILITY",
            *match.span("value"),
            0.85,
            context=("facility_structure",),
            risk="medium",
            protected=False,
        )
    for pattern in (_ORGANIZATION, _COMPANY):
        for match in pattern.finditer(text):
            add(
                "ORGANIZATION",
                *match.span("value"),
                0.8,
                context=("organization_structure",),
                risk="medium",
                protected=False,
            )
    for match in _SETTLEMENT.finditer(text):
        kind = match.group("kind").casefold()
        address = kind.startswith(("col", "fracc", "barrio"))
        add(
            "ADDRESS" if address else "LOCATION",
            *match.span("value"),
            0.85,
            context=("settlement_label",),
            risk="high" if address else "medium",
        )
    for match in _PLACE_FIELD.finditer(text):
        add("LOCATION", *match.span("value"), 0.85, context=("place_field",), risk="medium")
    for match in _POSTAL.finditer(text):
        add("ADDRESS", *match.span("value"), 0.85, context=("postal_code",))
    for match in _STREET.finditer(text):
        start, end = match.span("value")
        tail = ADDRESS_TAIL.match(text, end)
        add(
            "ADDRESS",
            start,
            tail.end() if tail else end,
            0.85,
            context=("street_structure",),
        )
    for match in _AGE.finditer(text):
        group = "value" if match.group("value") else "value2"
        if int(match.group(group)) <= 125:
            add(
                "AGE",
                *match.span(group),
                0.8,
                context=("subject_age",),
                risk="medium",
                protected=False,
            )
    for match in _NSS.finditer(text):
        digits = re.sub(r"\D", "", match.group("value"))
        valid = luhn_valid(digits)
        add(
            "INSURANCE_ID",
            *match.span("value"),
            0.95 if valid else 0.7,
            context=("social_security_label",),
            validation="checksum" if valid else "invalid",
        )
    for match in _ELECTOR_KEY.finditer(text):
        add("NATIONAL_ID", *match.span(), 0.9, context=("elector_key_structure",))
    for match in _INE_NUMBER.finditer(text):
        add("NATIONAL_ID", *match.span("value"), 0.85, context=("ine_label",))
    for match in _PROFESSIONAL_LICENSE.finditer(text):
        add("REGIONAL_ID", *match.span("value"), 0.85, context=("professional_license_label",))
    for match in _PASSPORT.finditer(text):
        add("PASSPORT", *match.span("value"), 0.85, context=("passport_label",))
    return findings


class NarrativeRecognizer:
    """Opt-in narrative rules for ``DeidEngine(recognizers=[NarrativeRecognizer()])``.

    Does not change packaged tagger profiles or claim calibrated release quality.
    Evaluate on a representative holdout before using it for release decisions.
    """

    def detect_view(self, source: str, view: DetectionView) -> list[Finding]:
        """Interpret source ordinal classes without changing normalized offsets."""
        return self.detect(ordinal_feature_text(source, view))

    def detect(self, text: str) -> list[Finding]:
        return narrative_spanish(text)


__all__ = ["ADDRESS_TAIL", "NarrativeRecognizer", "luhn_valid", "narrative_spanish"]
