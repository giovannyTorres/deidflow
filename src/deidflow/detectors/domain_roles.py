"""Bounded Spanish role/amount rules; no remote models or inferred coreference.

Explicit role labels and bounded creditor grammar supply role metadata. Scores
rank evidence; they are not calibrated probabilities. Monetary spans are additive
findings, never exclusions of overlapping identifiers. Kinship grammar preserves
relationship words without asserting graph edges or resolving people.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from typing import Any

from deidflow.core import Finding
from deidflow.detectors import address_field_boundary
from deidflow.detectors.narrative import coordinated_person_spans

DOMAIN_RULES_VERSION = "domain-roles-1.0.1"
DOMAIN_ROLES = (
    "patient",
    "clinician",
    "family",
    "customer",
    "creditor",
    "debtor",
    "agent",
    "plaintiff",
    "defendant",
    "witness",
    "lawyer",
    "judge",
)

_ROLE_WORDS = {
    "clinical": {
        "paciente": "patient",
        "derechohabiente": "patient",
        "médico": "clinician",
        "médica": "clinician",
        "doctor": "clinician",
        "doctora": "clinician",
        "enfermero": "clinician",
        "enfermera": "clinician",
        "familiar": "family",
        "madre": "family",
        "padre": "family",
        "hija": "family",
        "hijo": "family",
        "hermana": "family",
        "hermano": "family",
    },
    "financial": {
        "cliente": "customer",
        "titular": "customer",
        "beneficiario": "customer",
        "beneficiaria": "customer",
        "acreedor": "creditor",
        "acreedora": "creditor",
        "deudor": "debtor",
        "deudora": "debtor",
        "agente": "agent",
        "ejecutivo": "agent",
        "ejecutiva": "agent",
    },
    "legal": {
        "demandante": "plaintiff",
        "actor": "plaintiff",
        "actora": "plaintiff",
        "demandado": "defendant",
        "demandada": "defendant",
        "testigo": "witness",
        "abogado": "lawyer",
        "abogada": "lawyer",
        "juez": "judge",
        "jueza": "judge",
    },
}
_FEMALE = {
    "médica",
    "doctora",
    "enfermera",
    "madre",
    "hija",
    "hermana",
    "beneficiaria",
    "acreedora",
    "deudora",
    "ejecutiva",
    "actora",
    "demandada",
    "abogada",
    "jueza",
}
_MALE = {
    "médico",
    "doctor",
    "enfermero",
    "padre",
    "hijo",
    "hermano",
    "beneficiario",
    "acreedor",
    "deudor",
    "ejecutivo",
    "actor",
    "demandado",
    "abogado",
    "juez",
}


def _fold(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value.casefold()) if unicodedata.category(c) != "Mn"
    )


_FEMALE_FOLDED = frozenset(_fold(word) for word in _FEMALE)
_MALE_FOLDED = frozenset(_fold(word) for word in _MALE)

_UPPER = "A-ZÁÉÍÓÚÜÑ"
_LOWER = "a-záéíóúüñ"
# These frequently follow the same labels but describe a state, institution or
# condition. Requiring a capitalized name is not sufficient by itself.
_NOT_NAME = (
    r"(?!(?i:Hospital|Clínica|Clinica|Centro|Instituto|Sociedad|Empresa|Banco|"
    r"Tribunal|Juzgado|Fiscalía|Fiscalia|Ministerio|Diabetes|Hipertensión|Hipertension|"
    r"Negativo|Positivo|Estable|Anónimo|Anonimo|Desconocido|Ninguno|Nombre|"
    r"Persona|Paciente|Cliente|Demandante|Demandado|Testigo|Importe|Saldo|Monto)\b)"
)
_WORD = _NOT_NAME + rf"(?:[{_UPPER}][{_LOWER}]+|[{_UPPER}]{{2,}})(?:[-'’][{_UPPER}{_LOWER}]+)?"
_CONNECTOR = r"(?:de[ \t]+la|de[ \t]+los|de[ \t]+las|del|de|van|von|da)"
_NAME = rf"{_WORD}(?:[ \t]+(?:{_CONNECTOR}[ \t]+)?{_WORD}){{0,4}}"
_NUMBER = r"[+-]?(?:\d{1,3}(?:[ ,.]\d{3})+|\d+)(?:[.,]\d{1,2})?"
_CURRENCY = r"(?:MXN|USD|EUR|COP|ARS|CLP|PEN|BRL|pesos|dólares|dolares|euros)"
_MONEY = re.compile(
    rf"(?<![\w\d])(?:[$€£][ \t]*(?P<prefix>{_NUMBER})(?![\w.,])"
    rf"|(?P<suffix>{_NUMBER})[ \t]+(?i:{_CURRENCY})\b)"
)
_AMOUNT_FIELD = re.compile(
    rf"\b(?i:importe|monto|saldo|principal|intereses|cuota|honorarios|salario)"
    rf"[ \t]*:[ \t]*(?:[$€£][ \t]*)?(?P<value>{_NUMBER})(?![\w.,])"
)
_SYMPTOM = (
    r"(?:fiebre|dolor(?:[ \t]+tor[aá]cico)?|tos|disnea|sangrado|n[aá]useas|v[oó]mitos|alergias)"
)
_CLINICAL_NEGATION = (
    rf"(?:no[ \t]+(?:presenta|refiere|tiene|reporta)|niega)[ \t]+{_SYMPTOM}"
    rf"(?:[ \t]+(?:ni|y)[ \t]+{_SYMPTOM}){{0,4}}"
    r"|sin[ \t]+(?:datos|signos)(?:[ \t]+cl[ií]nicos)?[ \t]+de[ \t]+"
    r"(?:alarma|infecci[oó]n|sangrado|deshidrataci[oó]n)"
)
_STATUS = re.compile(
    rf"(?i:(?:{_CLINICAL_NEGATION}|NO[ \t]+(?:APLICA|IDENTIFICAD[OA]|CONSTA|REGISTRAD[OA])"
    r"|SIN[ \t]+(?:IDENTIFICACI[ÓO]N|REGISTRO)))\b"
)
_CLINICAL_STATUS = re.compile(
    r"\b(?i:paciente|derechohabiente)[ \t]*:[ \t]*"
    rf"(?P<value>(?i:{_CLINICAL_NEGATION}))\b"
)
_CREDITOR_PHRASE = re.compile(rf"\b(?i:debe|adeuda)[ \t]+a[ \t]+(?P<value>{_NAME})(?![\w-])")
_KINSHIP_WORD = (
    r"(?:herman[oa]s?|hij[oa]s?|padres?|madres?|abuel[oa]s?|niet[oa]s?|"
    r"t[ií][oa]s?|sobrin[oa]s?|prim[oa]s?|espos[oa]s?|c[oó]nyuges?|familiares?)"
)
_KINSHIP = re.compile(
    r"\b(?:(?i:su|sus|mi|mis|tu|tus|nuestr[oa]s?)[ \t]+"
    r"|(?i:ambos|ambas|ellos|ellas|los[ \t]+dos|las[ \t]+dos)[ \t]+(?i:son|eran)[ \t]+)"
    rf"(?P<value>{_KINSHIP_WORD})(?![\w])"
)
_SPEAKER_RESPONSES = frozenset({"si", "no", "gracias"})


class DomainRoleRecognizer:
    """Recognize explicit domain roles and monetary values in Spanish text.

    ``general`` enables the role vocabularies of all three specialist packs.
    The recognizer does not resolve pronouns, merge names, or assert relations.
    """

    def __init__(self, domain: str) -> None:
        if domain not in (*_ROLE_WORDS, "general"):
            raise ValueError("Unknown domain for Spanish role rules")
        self.domain = domain
        selected = (
            {word: role for words in _ROLE_WORDS.values() for word, role in words.items()}
            if domain == "general"
            else _ROLE_WORDS[domain]
        )
        words = {
            variant: role for word, role in selected.items() for variant in (word, _fold(word))
        }
        self._roles = {_fold(word): role for word, role in words.items()}
        self._pattern = re.compile(
            r"\b(?P<cue>(?i:"
            + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
            + rf"))\b[ \t]*(?::[ \t]*|[ \t]+)(?P<value>{_NAME})(?![\w])"
        )

    def detect(self, text: str) -> list[Finding]:
        findings = []
        for match in self._pattern.finditer(text):
            if _STATUS.match(match.group("value")):
                continue
            # A colon-labelled turn can begin with a complete response, not a
            # name. Require the entire word and following response punctuation:
            # "Cliente: No," is dialogue; "Cliente: No Cárdenas" remains a name.
            if (
                _fold(match.group("value")) in _SPEAKER_RESPONSES
                and ":" in text[match.end("cue") : match.start("value")]
                and re.match(r"[ \t]*[,;.!?…]", text[match.end("value") :])
            ):
                continue
            # A role label may also label a coded identifier, such as CLI-123.
            # Do not manufacture a partial person named CLI from that code.
            if re.match(r"[-_/.]\d", text[match.end("value") :]):
                continue
            cue = _fold(match.group("cue"))
            context = [f"domain:{self.domain}", "explicit_role", f"role:{self._roles[cue]}"]
            if cue in _FEMALE_FOLDED:
                context.append("gender:f")
            elif cue in _MALE_FOLDED:
                context.append("gender:m")
            findings.append(
                Finding(
                    "PERSON",
                    *match.span("value"),
                    0.94,
                    "rules.es_domain_role",
                    context=tuple(context),
                    model_version=DOMAIN_RULES_VERSION,
                    protected=True,
                )
            )
        if self.domain in {"clinical", "general"}:
            findings.extend(
                Finding(
                    "CLINICAL_OBSERVATION",
                    *match.span("value"),
                    0.9,
                    "rules.es_domain_context",
                    context=("explicit_clinical_status",),
                    model_version=DOMAIN_RULES_VERSION,
                    risk="medium",
                )
                for match in _CLINICAL_STATUS.finditer(text)
            )
        if self.domain in {"financial", "general"}:
            findings.extend(
                Finding(
                    "PERSON",
                    *match.span("value"),
                    0.9,
                    "rules.es_domain_role",
                    context=(f"domain:{self.domain}", "financial_creditor_phrase", "role:creditor"),
                    model_version=DOMAIN_RULES_VERSION,
                    protected=True,
                )
                for match in _CREDITOR_PHRASE.finditer(text)
            )
        findings.extend(
            Finding(
                "DEMOGRAPHIC",
                *match.span("value"),
                0.9,
                "rules.es_domain_context",
                context=("explicit_kinship_grammar",),
                model_version=DOMAIN_RULES_VERSION,
                risk="medium",
            )
            for match in _KINSHIP.finditer(text)
        )
        amounts: set[tuple[int, int]] = set()
        for match in _MONEY.finditer(text):
            amounts.add(match.span("prefix" if match.group("prefix") is not None else "suffix"))
        amounts.update(match.span("value") for match in _AMOUNT_FIELD.finditer(text))
        findings.extend(
            Finding(
                "AMOUNT",
                start,
                end,
                0.9,
                "rules.es_domain_amount",
                context=(f"domain:{self.domain}", "explicit_amount"),
                model_version=DOMAIN_RULES_VERSION,
                risk="medium",
            )
            for start, end in sorted(amounts)
        )
        return findings


_PREFIX_WORDS = frozenset({"el", "la", "al", "del", "su", "un", "una", "por", "a"}) | {
    _fold(word) for words in _ROLE_WORDS.values() for word in words
}
_SUFFIX_WORDS = frozenset(
    {
        "niega",
        "no",
        "sin",
        "refiere",
        "presenta",
        "toma",
        "debe",
        "pago",
        "reclama",
        "declara",
        "firmo",
        "comparece",
        "representa",
        "acepta",
        "rechaza",
        "a",
        "al",
        "el",
        "la",
        "y",
        "con",
        "ante",
        "fue",
        "es",
        "ha",
        "sido",
    }
)


def _grammar_only(value: str, allowed: frozenset[str] | set[str]) -> bool:
    # No digits, capitalized names, line breaks, or unrecognized lexical tokens
    # are discarded. Lowercase role/grammar words alone may bound a model span.
    if any(c in value for c in "\r\n") or re.search(r"[^\w \t,:;.-]", value):
        return False
    words = re.findall(r"\w+", value)
    return all(word.islower() and _fold(word) in allowed for word in words)


class DomainModelAdapter:
    """Retain domain language when a model overextends an explicit role name.

    PERSON boundaries are refined around explicit names or full coordinated
    names. PERSON/LOCATION inside explicit clinical negation becomes clinical
    context; PERSON inside lowercase kinship grammar becomes demographic context.
    Review markers survive fusion. Other names and all identifier categories
    retain their original coverage, including ambiguous monetary overlaps.
    """

    def __init__(self, adapter: Any, domain: str) -> None:
        self.adapter = adapter
        self.roles = DomainRoleRecognizer(domain)

    def detect_batch(self, texts: list[str]) -> list[list[Finding]]:
        batches = self.adapter.detect_batch(texts)
        if len(batches) != len(texts):
            raise ValueError("Local domain model returned an invalid batch length")
        result = []
        for text, findings in zip(texts, batches, strict=True):
            role_findings = self.roles.detect(text)
            names = [f for f in role_findings if f.entity_type == "PERSON"]
            statuses = [f for f in role_findings if f.entity_type == "CLINICAL_OBSERVATION"]
            kinship = [f for f in role_findings if "explicit_kinship_grammar" in f.context]
            refined: list[Finding] = []
            for finding in findings:
                if finding.entity_type == "ADDRESS" and not finding.protected:
                    boundary = address_field_boundary(text, finding.start, finding.end)
                    if boundary < finding.end:
                        finding = replace(
                            finding,
                            end=boundary,
                            context=(*finding.context, "domain_boundary_refinement"),
                        )
                if (
                    not finding.protected
                    and finding.entity_type == "PERSON"
                    and any(
                        relation.start <= finding.start and finding.end <= relation.end
                        for relation in kinship
                    )
                ):
                    finding = replace(
                        finding,
                        entity_type="DEMOGRAPHIC",
                        context=(*finding.context, "domain_context_refinement"),
                    )
                if (
                    not finding.protected
                    and finding.entity_type in {"PERSON", "LOCATION"}
                    and any(
                        status.start <= finding.start and finding.end <= status.end
                        for status in statuses
                    )
                ):
                    finding = replace(
                        finding,
                        entity_type="CLINICAL_OBSERVATION",
                        context=(*finding.context, "domain_context_refinement"),
                    )
                candidates = [
                    name
                    for name in names
                    if finding.start <= name.start and name.end <= finding.end
                ]
                if (
                    not finding.protected
                    and finding.entity_type == "PERSON"
                    and len(candidates) == 1
                ):
                    name = candidates[0]
                    prefix = text[finding.start : name.start]
                    suffix = text[name.end : finding.end]
                    if (
                        (prefix or suffix)
                        and _grammar_only(prefix, _PREFIX_WORDS)
                        and _grammar_only(suffix, _SUFFIX_WORDS)
                    ):
                        finding = replace(
                            finding,
                            start=name.start,
                            end=name.end,
                            context=(*finding.context, "domain_boundary_refinement"),
                        )
                spans = (
                    coordinated_person_spans(text, finding.start, finding.end)
                    if finding.entity_type == "PERSON" and not finding.protected
                    else ((finding.start, finding.end),)
                )
                if len(spans) > 1:
                    refined.extend(
                        replace(
                            finding,
                            start=start,
                            end=end,
                            context=(*finding.context, "person_coordination_split"),
                        )
                        for start, end in spans
                    )
                else:
                    refined.append(finding)
            result.append(refined)
        return result


__all__ = ["DOMAIN_ROLES", "DOMAIN_RULES_VERSION", "DomainRoleRecognizer", "DomainModelAdapter"]
