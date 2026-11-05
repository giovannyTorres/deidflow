"""Compiled Spanish/Mexican recognizers and deterministic candidate fusion."""

from __future__ import annotations

import bisect
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Protocol

from deidflow.core import Finding
from deidflow.validators import (
    ValidationResult,
    validate_card,
    validate_clabe,
    validate_curp,
    validate_rfc,
)

from .clinical import contextual_spanish
from .narrative import ADDRESS_TAIL, narrative_spanish


class Detector(Protocol):
    def detect(self, text: str) -> list[Finding]: ...


@dataclass(frozen=True)
class RegexRecognizer:
    """Trusted application-defined regex; patterns must be bounded and audited for ReDoS."""

    entity_type: str
    pattern: re.Pattern[str]
    score: float = 0.85
    group: int | str = 0
    validator: Callable[[str], ValidationResult] | None = None
    name: str = "custom.regex"
    risk: str = "high"

    def detect(self, text: str) -> list[Finding]:
        out = []
        for match in self.pattern.finditer(text):
            start, end = match.span(self.group)
            if end <= start:
                continue
            result = self.validator(match.group(self.group)) if self.validator else None
            out.append(
                Finding(
                    self.entity_type,
                    start,
                    end,
                    self.score if result is None or result else min(self.score, 0.55),
                    self.name,
                    validation=result.status if result is not None else "pattern",
                    risk=self.risk,
                    protected=self.risk == "high",
                )
            )
        return out


_FLAGS = re.IGNORECASE | re.UNICODE
_BREAK = r"(?:[ \t]*\r?\n[ \t]*)?"


def _split_pattern(pattern: str) -> str:
    """Allow a line-wrap between identifier character classes without normalizing offsets."""
    parts = re.findall(r"\[[^]]+\]|\\d|[A-Z0-9]", pattern)
    return _BREAK.join(parts)


# Literal fixed lengths make these identifiers linear in input size.
_CURP_BODY = (
    "[A-Z][AEIOUX][A-Z][A-Z]"
    + "[0-9]" * 6
    + "[HMX][A-Z][A-Z]"
    + "[B-DF-HJ-NP-TV-Z]" * 3
    + "[A-Z0-9][0-9]"
)
_RFC_SEP = r"[ \t]*(?:\r?\n[ \t]*)?"
_RFC_BODY = (
    r"(?:"
    + _RFC_SEP.join(["[A-ZÑ&]"] * 4 + ["[0-9]"] * 6 + ["[A-Z0-9]"] * 2 + ["[0-9A]"])
    + r"|"
    + _RFC_SEP.join(["[A-ZÑ&]"] * 3 + ["[0-9]"] * 6 + ["[A-Z0-9]"] * 2 + ["[0-9A]"])
    + r")"
)
_EMAIL = re.compile(
    r"(?<![\w.!#$%&'*+/=?^`{|}~-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,62}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,62}[A-Z0-9])?)+(?![\w-])",
    _FLAGS,
)
_CURP_RE = re.compile(r"(?<!\w)" + _split_pattern(_CURP_BODY) + r"(?!\w)", _FLAGS)
_RFC_RE = re.compile(r"(?<!\w)" + _RFC_BODY + r"(?!\w)", _FLAGS)
_LABELLED_REGIONAL = (
    (
        "CURP",
        re.compile(
            r"\bCURP\s*[:=]\s*(?P<value>(?:[A-Z0-9][ \t-]*(?:\r?\n[ \t]*)?){17}[A-Z0-9])(?!\w)",
            _FLAGS,
        ),
        validate_curp,
    ),
    (
        "RFC",
        re.compile(
            r"\bRFC\s*[:=]\s*(?P<value>(?:[A-Z0-9Ñ&][ \t-]*(?:\r?\n[ \t]*)?){11,12}[A-Z0-9Ñ&])(?!\w)",
            _FLAGS,
        ),
        validate_rfc,
    ),
    (
        "CLABE",
        re.compile(
            r"\bCLABE\s*[:=]\s*(?P<value>(?:[A-Z0-9][ \t-]*(?:\r?\n[ \t]*)?){17}[A-Z0-9])(?!\w)",
            _FLAGS,
        ),
        validate_clabe,
    ),
)
_DIGITS = re.compile(r"(?<![\w+])(?:[0-9][ \t-]*){12,18}[0-9](?!\w|[ \t-]*[0-9])")
_PHONE = re.compile(
    r"(?<![\w])(?:\+?52[ .-]?)?(?:\(?[0-9]{2,3}\)?[ .-]?)?[0-9]{3,4}[ .-]?[0-9]{4}(?!\w)"
)
_DATE = re.compile(
    r"(?<!\d)(?:[12][0-9]{3}-[01][0-9]-[0-3][0-9]|[0-3][0-9][/-][01][0-9][/-](?:[12][0-9]{3}|[0-9]{2}))(?!\d)"
)
# A line-wrapped value may follow a label, but another field label is not its
# value. This matters after physical removal leaves a form's labels intact.
_VALUE_NOT_LABEL = r"(?![ \t]*(?i:nombre(?:[ \t]+completo)?|paciente(?:[ \t]+id)?|patient(?:[ \t]+id)?|name|cliente|customer(?:[ \t]+id)?|empleado|employee(?:[ \t]+id)?|domicilio|direcci[oó]n|address|diagn[oó]stico|diagnosis|correo(?:[ \t]+electr[oó]nico)?|e-?mail|tel[eé]fono|phone|CURP|RFC|CLABE|importe|monto|amount|cuenta(?:[ \t]+bancaria)?|expediente|medicaci[oó]n|tratamiento|fecha[ \t]+de[ \t]+nacimiento|date[ \t]+of[ \t]+birth)[ \t]*[:=])"
_FIELD_ID = re.compile(
    r"\b(?P<label>cuenta(?:\s+bancaria)?|bank\s+account|n[úu]mero\s+de\s+cuenta|empleado|employee(?:\s+id)?|cliente|customer(?:\s+id)?|paciente\s+id|patient\s+id|expediente|pasaporte|passport|contrato|contract|identificador\s+interno|internal\s+id|NSS|INE)\s*(?:n[úu]m(?:ero)?\.?|id|no\.?)?\s*[:=#]\s*(?P<value>"
    + _VALUE_NOT_LABEL
    + r"[A-Z0-9][A-Z0-9_./-]{2,47})",
    _FLAGS,
)
# Institution words after a connector ("Dr. Ramírez del Hospital Ángeles") end a name.
_NAME_WORD = (
    r"(?!(?:Hospital|Cl[ií]nica|Centro|Instituto|Sanatorio|Universidad|Unidad|Servicio)\b)"
    r"[A-ZÁÉÍÓÚÜÑÀÈÌÒÙÇÏ][a-záéíóúüñàèìòùçï]+(?:[-'][A-ZÁÉÍÓÚÜÑÀÈÌÒÙÇÏa-záéíóúüñàèìòùçï]+)?"
)
_NAME_VALUE = _NAME_WORD + r"(?:[ \t]+(?:(?:de|del|la|las|los|y)[ \t]+)?" + _NAME_WORD + r"){1,5}"
_NAME = re.compile(
    r"\b(?i:nombre(?:\s+completo)?|paciente|titular|beneficiari[oa]|contacto|name|patient)\s*[:=]\s*(?P<value>"
    + _VALUE_NOT_LABEL
    + _NAME_VALUE
    + r")"
)
_NAME_FIELD = re.compile(
    r"\b(?:nombre(?:\s+completo)?|paciente|titular|beneficiari[oa]|name|patient)\s*[:=]\s*"
    r"(?P<value>"
    + _VALUE_NOT_LABEL
    + r"[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ'-]{0,63}(?:[ \t]+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ'-]{0,63}){1,7})"
    r"(?=[ \t]*(?:[,;\r\n]|$))",
    _FLAGS,
)
_HONORIFIC = re.compile(r"\b(?:Sr\.?|Sra\.?|Dr\.?|Dra\.?)\s+(?P<value>" + _NAME_VALUE + r")")
_ADDRESS = re.compile(
    r"\b(?:domicilio|direcci[óo]n|address)\s*[:=]\s*(?P<value>"
    + _VALUE_NOT_LABEL
    + r"[^\n;]{4,180}(?:\r?\n[ \t]*(?:(?:col(?:onia)?\.?|C\.?\s*P\.?|c[óo]digo\s+postal|alcald[íi]a|municipio|ciudad|estado)\b[^\n;]{1,120})){0,4})",
    _FLAGS,
)
_STREET = re.compile(
    r"\b(?P<value>(?:Calle|Avenida|Av\.|Calzada|Blvd\.|Boulevard)\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ0-9 .'-]{2,70}?\s+(?:n[úu]m\.?\s*|#\s*)?[0-9]{1,5}(?:[- ][A-Z0-9]{1,4})?)(?=[,;\n]|$)"
)
_SECRET = re.compile(
    r"\b(?P<label>api[_ -]?key|token|auth[_ -]?token|authorization|password|passwd|contrase[ñn]a|secret|clave\s+de\s+acceso)\s*[:=]\s*(?:[\"']?)(?:Bearer\s+)?(?P<value>[^\s\"',;<>]{4,256})",
    _FLAGS,
)
_KNOWN_SECRET = re.compile(r"(?<!\w)(?:AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,255})(?!\w)")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|$)"
)
_HEALTH = re.compile(
    r"\b(?:diabetes(?:\s+(?:mellitus|tipo\s+[12]))?|hipertensi[óo]n(?:\s+arterial)?|VIH|sida|c[áa]ncer|depresi[óo]n|embarazo|asma|insulina|metformina|quimioterapia|hemodi[áa]lisis|alergia(?:s)?"
    r"|ansiedad|esquizofrenia|trastorno\s+bipolar|bipolaridad|epilepsia|hepatitis(?:\s+[ABC])?|tuberculosis|s[íi]filis|gonorrea|VPH|herpes|aborto|adicci[óo]n|alcoholismo|drogadicci[óo]n|anorexia|bulimia|autismo|TDAH|alzh?eimer|parkinson|demencia|leucemia|linfoma|tumor|insuficiencia\s+renal|cirrosis|infarto|EPOC|lupus|esclerosis\s+m[úu]ltiple|COVID(?:-19)?"
    r"|antirretrovirales?|antidepresivos?|fluoxetina|sertralina|litio|metadona|radioterapia|di[áa]lisis)\b",
    _FLAGS,
)
_MEDICATIONS = {
    "insulina",
    "metformina",
    "antirretroviral",
    "antirretrovirales",
    "antidepresivo",
    "antidepresivos",
    "fluoxetina",
    "sertralina",
    "litio",
    "metadona",
}
_TREATMENTS = {
    "quimioterapia",
    "hemodiálisis",
    "hemodialisis",
    "radioterapia",
    "diálisis",
    "dialisis",
}
_SENTENCE_END = re.compile(r"[.!?\n]")
_HEALTH_SUBJECT = re.compile(
    r"\b(?:paciente\b|patient\b|historia\s+cl[íi]nica\b|diagn[óo]stico\s*[:=]|su\s+diagn[óo]stico\b|padece\b|padezco\b|mi\s+(?:diagn[óo]stico|tratamiento)\b)",
    _FLAGS,
)
_AGE = re.compile(r"\b(?:edad|age)\s*[:=]?\s*(?P<value>[0-9]{1,3})(?:\s*a[ñn]os)?\b", _FLAGS)
_DOB_CONTEXT = re.compile(
    r"(?:fecha\s+de\s+nacimiento|nacimiento|naci[óo](?:\s+el)?|dob|date\s+of\s+birth)\s*[:=]?\s*$",
    _FLAGS,
)
_PHONE_CONTEXT = re.compile(
    r"\b(?:tel[ée]fono|tel\.?|m[óo]vil|celular|cel\.?|phone|contacto|llamar|whatsapp"
    r"|(?:mi|su|tu|el)\s+n[úu]mero|n[úu]mero\s+de\s+(?:tel[ée]fono|celular|m[óo]vil|contacto)"
    r"|marca(?:r|me)?\s+al|ll[áa]ma(?:me|r)?\s+al)(?:\s+(?:es|son))?\s*[:=]?\s*$",
    _FLAGS,
)


class RuleDetector:
    """Reusable rule set. Scores are evidence ranks, explicitly not calibrated probabilities."""

    def __init__(self, *, contextual: bool = True, recognizers: Iterable[Detector] = ()) -> None:
        self.contextual = contextual
        self.recognizers = tuple(recognizers)

    def detect(self, text: str) -> list[Finding]:
        findings: list[Finding] = []

        def add(
            kind: str,
            start: int,
            end: int,
            score: float,
            *,
            validation: str = "pattern",
            context: tuple[str, ...] = (),
            risk: str = "high",
            protected: bool = True,
        ) -> None:
            findings.append(
                Finding(
                    kind,
                    start,
                    end,
                    score,
                    "rules.es_MX",
                    validation,
                    context,
                    risk=risk,
                    protected=protected,
                )
            )

        for match in _EMAIL.finditer(text):
            add("EMAIL", *match.span(), 0.95, validation="structural")
        for kind, pattern, validator in (
            ("CURP", _CURP_RE, validate_curp),
            ("RFC", _RFC_RE, validate_rfc),
        ):
            for match in pattern.finditer(text):
                check = validator(match.group())
                add(
                    kind,
                    *match.span(),
                    0.99 if check else 0.6,
                    validation=check.status,
                    context=("checksum_valid",) if check.checksum else ("pattern_compatible",),
                )
        # An explicit regional label also captures OCR-damaged and mistyped values.
        # These are uncertain candidates, never silently substituted or confirmed.
        if self.contextual:
            for kind, pattern, validator in _LABELLED_REGIONAL:
                for match in pattern.finditer(text):
                    check = validator(match.group("value"))
                    add(
                        kind,
                        *match.span("value"),
                        0.99 if check else 0.55,
                        validation=check.status,
                        context=("explicit_identifier_label",),
                    )
        numeric_spans: list[tuple[int, int]] = []
        for match in _DIGITS.finditer(text):
            compact = re.sub(r"[ \t-]", "", match.group())
            if len(compact) == 18:
                check = validate_clabe(compact)
                add("CLABE", *match.span(), 0.99 if check else 0.6, validation=check.status)
                numeric_spans.append(match.span())
            card = validate_card(compact)
            preceding = text[max(0, match.start() - 32) : match.start()]
            if card or re.search(r"(?:tarjeta|card|pan)\s*[:=]?\s*$", preceding, _FLAGS):
                add("PAYMENT_CARD", *match.span(), 0.98 if card else 0.6, validation=card.status)
                numeric_spans.append(match.span())
        for match in _PHONE.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            labelled = bool(_PHONE_CONTEXT.search(text[max(0, match.start() - 40) : match.start()]))
            explicit = match.group().startswith("+52")
            separated = bool(re.search(r"[ ().-]", match.group()))
            if (len(digits) in (10, 12) and (labelled or explicit or separated)) or (
                labelled and 7 <= len(digits) <= 12
            ):
                if not any(
                    start <= match.start() and match.end() <= end for start, end in numeric_spans
                ):
                    add(
                        "PHONE",
                        *match.span(),
                        0.92 if labelled or explicit else 0.75,
                        validation="structural",
                        context=("label",) if labelled else (),
                    )
        for match in _SECRET.finditer(text):
            label = match.group("label").casefold()
            kind = (
                "CREDENTIAL"
                if label in {"password", "passwd", "contraseña", "secret", "clave de acceso"}
                else "AUTH_TOKEN"
                if "token" in label or "authorization" in label
                else "API_KEY"
            )
            add(kind, *match.span("value"), 0.95, context=("credential_label",))
        for match in _KNOWN_SECRET.finditer(text):
            add("CREDENTIAL" if "PRIVATE KEY" in match.group() else "API_KEY", *match.span(), 0.99)
        for match in _PRIVATE_KEY.finditer(text):
            add("CREDENTIAL", *match.span(), 0.99)
        if self.contextual:
            for match in _FIELD_ID.finditer(text):
                label = match.group("label").casefold()
                kind = (
                    "BANK_ACCOUNT"
                    if "cuenta" in label or "account" in label
                    else "EMPLOYEE_ID"
                    if "emple" in label or "employee" in label
                    else "CUSTOMER_ID"
                    if "client" in label or "customer" in label
                    else "PATIENT_ID"
                    if "paciente" in label or "patient" in label or "expediente" in label
                    else "PASSPORT"
                    if "pas" in label
                    else "CONTRACT_ID"
                    if "contr" in label
                    else "NATIONAL_ID"
                    if label in {"nss", "ine"}
                    else "INTERNAL_ID"
                )
                add(kind, *match.span("value"), 0.85, context=("explicit_field_label",))
            for pattern in (_NAME, _NAME_FIELD, _HONORIFIC):
                for match in pattern.finditer(text):
                    add("PERSON", *match.span("value"), 0.88, context=("person_label",))
            for pattern in (_ADDRESS, _STREET):
                for match in pattern.finditer(text):
                    start, end = match.span("value")
                    while end > start and text[end - 1].isspace():
                        end -= 1
                    if pattern is _STREET and (tail := ADDRESS_TAIL.match(text, end)):
                        end = tail.end()
                        while end > start and text[end - 1] in " \t.,;":
                            end -= 1
                    add("ADDRESS", start, end, 0.85, context=("address_structure",))
            for match in _DATE.finditer(text):
                preceding = text[max(0, match.start() - 45) : match.start()]
                kind = "DATE_OF_BIRTH" if _DOB_CONTEXT.search(preceding) else "DATE"
                add(
                    kind,
                    *match.span(),
                    0.85 if kind == "DATE_OF_BIRTH" else 0.7,
                    risk="high" if kind == "DATE_OF_BIRTH" else "medium",
                    protected=kind == "DATE_OF_BIRTH",
                )
            findings.extend(narrative_spanish(text))
            people = [f for f in findings if f.entity_type == "PERSON"]
            boundaries: list[int] | None = None
            for match in _HEALTH.finditer(text):
                nearby = text[max(0, match.start() - 120) : min(len(text), match.end() + 60)]
                # A named person in the same sentence is also a subject association.
                named = False
                if people:
                    if boundaries is None:
                        boundaries = [m.start() for m in _SENTENCE_END.finditer(text)]
                    index = bisect.bisect_left(boundaries, match.start())
                    left = boundaries[index - 1] + 1 if index else 0
                    right = boundaries[index] if index < len(boundaries) else len(text)
                    named = any(left <= p.start and p.end <= right for p in people)
                if named or _HEALTH_SUBJECT.search(nearby):
                    prefix = text[max(0, match.start() - 30) : match.start()]
                    term = match.group().lower()
                    kind = (
                        "DIAGNOSIS"
                        if re.search(r"diagn[óo]stico\s*[:=]\s*$", prefix, _FLAGS)
                        else "MEDICATION"
                        if term in _MEDICATIONS
                        else "TREATMENT"
                        if term in _TREATMENTS
                        else "MEDICAL_CONDITION"
                    )
                    add(
                        kind,
                        *match.span(),
                        0.8,
                        context=("named_subject_association" if named else "patient_association",),
                        risk="high",
                    )
            for match in _AGE.finditer(text):
                add(
                    "AGE",
                    *match.span("value"),
                    0.8,
                    risk="medium",
                    protected=False,
                    context=("age_label",),
                )
        for recognizer in self.recognizers:
            findings.extend(recognizer.detect(text))
        if self.contextual:
            findings.extend(contextual_spanish(text))
        return fuse(findings)

    def detect_batch(self, texts: list[str]) -> list[list[Finding]]:
        return [self.detect(text) for text in texts]


def fuse(findings: Iterable[Finding]) -> list[Finding]:
    """Deduplicate exact category/location spans; retain overlaps and all provenance."""
    groups: dict[tuple[object, ...], Finding] = {}
    for finding in findings:
        key = (finding.start, finding.end, finding.entity_type, finding.location)
        current = groups.get(key)
        if current is None:
            groups[key] = finding
        else:
            best = (
                finding
                if (finding.protected, finding.score, finding.detector)
                > (current.protected, current.score, current.detector)
                else current
            )
            groups[key] = replace(
                best,
                labels=tuple(sorted(set(current.labels + finding.labels))),
                context=tuple(sorted(set(current.context + finding.context))),
                detector="|".join(
                    sorted(set(current.detector.split("|") + finding.detector.split("|")))
                ),
                protected=current.protected or finding.protected,
            )
    return sorted(groups.values(), key=lambda f: (f.start, f.end, f.entity_type, f.detector))


def non_overlapping(findings: Iterable[Finding]) -> list[Finding]:
    """Union overlapping spans so transforming nested findings cannot leave residual fragments.

    The winner supplies the label/operator; all labels and provenance are retained.
    Callers must apply policy before this operation, especially when labels are preserved.
    """
    result: list[Finding] = []
    for finding in sorted(findings, key=lambda f: (f.start, f.end, f.entity_type)):
        if not result or finding.start >= result[-1].end or finding.location != result[-1].location:
            result.append(finding)
            continue
        prior = result.pop()
        winner = max(
            (prior, finding), key=lambda f: (f.protected, f.score, f.end - f.start, f.entity_type)
        )
        result.append(
            replace(
                winner,
                start=min(prior.start, finding.start),
                end=max(prior.end, finding.end),
                labels=tuple(
                    sorted(
                        set(
                            prior.labels + finding.labels + (prior.entity_type, finding.entity_type)
                        )
                    )
                ),
                detector="|".join(
                    sorted(set(prior.detector.split("|") + finding.detector.split("|")))
                ),
                protected=prior.protected or finding.protected,
            )
        )
    return result


__all__ = ["Detector", "RegexRecognizer", "RuleDetector", "fuse", "non_overlapping"]
