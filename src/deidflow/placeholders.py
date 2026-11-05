"""Indexed, role-aware placeholders that keep "who is who" for LLM processing.

``La señora Verónica Herrera fue atendida por el doctor Jiménez`` becomes
``La señora [PERSONA_1] fue atendida por el doctor [MEDICO_1]``. The same referent
keeps the same placeholder within the allocator's scope (document or session).

The allocator never stores plaintext. Mention tokens are kept only as keyed hashes
under a random per-allocator key, which is enough for conservative coreference
(token-subset matching) and useless outside the process. Original values for later
re-identification belong in an explicit :mod:`deidflow.vault`.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from deidflow.core import Finding
from deidflow.validators import normalize_identifier

LABELS_ES: dict[str, str] = {
    "PERSON": "PERSONA",
    "ADDRESS": "DIRECCION",
    "EMAIL": "CORREO",
    "PHONE": "TELEFONO",
    "DATE_OF_BIRTH": "FECHA_NACIMIENTO",
    "DATE": "FECHA",
    "AGE": "EDAD",
    "LOCATION": "LUGAR",
    "MEDICAL_FACILITY": "CENTRO_MEDICO",
    "ORGANIZATION": "ORGANIZACION",
    "RFC": "RFC",
    "CURP": "CURP",
    "CLABE": "CLABE",
    "BANK_ACCOUNT": "CUENTA",
    "PAYMENT_CARD": "TARJETA",
    "NATIONAL_ID": "ID_OFICIAL",
    "INSURANCE_ID": "NSS",
    "PATIENT_ID": "EXPEDIENTE",
    "EMPLOYEE_ID": "ID_EMPLEADO",
    "CUSTOMER_ID": "ID_CLIENTE",
    "PASSPORT": "PASAPORTE",
    "DOCUMENT_ID": "ID_DOCUMENTO",
    "REGIONAL_ID": "CEDULA",
    "CONTRACT_ID": "CONTRATO",
    "INTERNAL_ID": "ID_INTERNO",
    "DIAGNOSIS": "DIAGNOSTICO",
    "MEDICAL_CONDITION": "CONDICION_MEDICA",
    "TREATMENT": "TRATAMIENTO",
    "MEDICATION": "MEDICAMENTO",
    "CLINICAL_OBSERVATION": "OBSERVACION_CLINICA",
    "MEDICAL_HISTORY": "ANTECEDENTE",
    "MEDICAL_ATTRIBUTE": "DATO_CLINICO",
    "API_KEY": "CLAVE_API",
    "CREDENTIAL": "CREDENCIAL",
    "AUTH_TOKEN": "TOKEN",
    "CONFIDENTIAL": "CONFIDENCIAL",
    "OCCUPATION": "OCUPACION",
    "DEMOGRAPHIC": "DATO_DEMOGRAFICO",
}
ROLE_LABELS_ES: dict[str, str] = {
    "patient": "PACIENTE",
    "clinician": "MEDICO",
    "family": "FAMILIAR",
}
_IDENTIFIERS = {
    "RFC",
    "CURP",
    "CLABE",
    "PAYMENT_CARD",
    "PHONE",
    "BANK_ACCOUNT",
    "NATIONAL_ID",
    "INSURANCE_ID",
    "EMPLOYEE_ID",
    "CUSTOMER_ID",
    "PATIENT_ID",
    "PASSPORT",
    "DOCUMENT_ID",
    "REGIONAL_ID",
    "CONTRACT_ID",
    "INTERNAL_ID",
}
_PARTICLES = frozenset({"de", "del", "la", "las", "los", "y", "e", "van", "von", "da", "di"})
_LABEL = re.compile(r"[A-Z][A-Z0-9_]{0,39}\Z")
PLACEHOLDER = re.compile(
    r"\[[ \t]*(?P<label>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ_]{0,39}?)[ \t_]+"
    r"(?P<index>[0-9]{1,6})[ \t]*\]"
    r"|\b(?P<bare_label>[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ_]{1,39}?)_(?P<bare_index>[0-9]{1,6})\b"
)


def fold(value: str) -> str:
    """Casefold, strip accents, drop punctuation and collapse whitespace."""
    decomposed = unicodedata.normalize("NFD", value.casefold())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", letters).split())


def canonical_placeholder(label: str, index: str | int) -> str:
    return f"[{fold(label).upper().replace(' ', '_')}_{int(index)}]"


def _context_value(findings: Iterable[Finding], prefix: str) -> str | None:
    values = {c[len(prefix) :] for f in findings for c in f.context if c.startswith(prefix)}
    return values.pop() if len(values) == 1 else None


@dataclass
class _Entity:
    placeholder: str
    entity_type: str
    tokens: frozenset[str]
    role: str | None
    gender: str | None


@dataclass
class PlaceholderAllocator:
    """Stateful, deterministic ``[LABEL_n]`` allocation with conservative coreference.

    Person mentions merge only when one token set contains the other, roles and
    grammatical genders do not conflict, and exactly one earlier entity is
    compatible. Ambiguity yields a new placeholder: two people sharing one
    placeholder would be the unsafe error, two placeholders for one person only
    loses some context.
    """

    labels: Mapping[str, str] = field(default_factory=lambda: dict(LABELS_ES))
    role_labels: Mapping[str, str] = field(default_factory=lambda: dict(ROLE_LABELS_ES))
    use_roles: bool = True
    _key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    _counters: dict[str, int] = field(default_factory=dict, repr=False)
    _exact: dict[tuple[str, str], str] = field(default_factory=dict, repr=False)
    _people: list[_Entity] = field(default_factory=list, repr=False)
    _issued: dict[str, tuple[str, str | None]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for label in list(self.labels.values()) + list(self.role_labels.values()):
            if not isinstance(label, str) or not _LABEL.match(label):
                raise ValueError("Placeholder labels must be short uppercase identifiers")

    def _hash(self, value: str) -> str:
        return hmac.new(
            self._key, value.encode("utf-8", "surrogatepass"), hashlib.sha256
        ).hexdigest()

    def _new(self, label: str, entity_type: str, role: str | None) -> str:
        self._counters[label] = self._counters.get(label, 0) + 1
        placeholder = f"[{label}_{self._counters[label]}]"
        self._issued[placeholder] = (entity_type, role)
        return placeholder

    def _label(self, entity_type: str, role: str | None) -> str:
        if (
            entity_type == "PERSON"
            and self.use_roles
            and role is not None
            and role in self.role_labels
        ):
            return self.role_labels[role]
        return self.labels.get(entity_type) or (
            entity_type if _LABEL.match(entity_type) else "DATO"
        )

    def placeholder(self, value: str, entity_type: str, findings: Sequence[Finding] = ()) -> str:
        """Return the stable placeholder for this mention, allocating one if needed."""
        role = _context_value(findings, "role:")
        gender = _context_value(findings, "gender:")
        if entity_type != "PERSON":
            normalized = normalize_identifier(value) if entity_type in _IDENTIFIERS else fold(value)
            label = self._label(entity_type, None)
            key = (label, self._hash(normalized))
            if key not in self._exact:
                self._exact[key] = self._new(label, entity_type, None)
            return self._exact[key]
        tokens = frozenset(self._hash(t) for t in fold(value).split() if t not in _PARTICLES)
        if not tokens:
            tokens = frozenset({self._hash(fold(value))})
        candidates = [
            entity
            for entity in self._people
            if (tokens <= entity.tokens or entity.tokens <= tokens)
            and (role is None or entity.role is None or role == entity.role)
            and (gender is None or entity.gender is None or gender == entity.gender)
        ]
        if len(candidates) == 1:
            entity = candidates[0]
            entity.tokens |= tokens
            entity.role = entity.role or role
            entity.gender = entity.gender or gender
            return entity.placeholder
        placeholder = self._new(self._label("PERSON", role), "PERSON", role)
        self._people.append(_Entity(placeholder, "PERSON", tokens, role, gender))
        return placeholder

    def issued(self) -> dict[str, tuple[str, str | None]]:
        """Placeholder -> (entity type, role). Contains no source values."""
        return dict(self._issued)

    def reset(self) -> None:
        self._counters.clear()
        self._exact.clear()
        self._people.clear()
        self._issued.clear()
        self._key = secrets.token_bytes(32)


__all__ = [
    "LABELS_ES",
    "PLACEHOLDER",
    "ROLE_LABELS_ES",
    "PlaceholderAllocator",
    "canonical_placeholder",
    "fold",
]
