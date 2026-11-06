"""Indexed, role-aware pseudonyms with exact-value identity and source collision guards.

The allocator keeps keyed hashes, never source values. Equal Unicode-normalized
values with identical type/role/gender reuse a token; partial names and aliases
never establish identity. Re-identification belongs in an explicit local vault.
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
_LABEL = re.compile(r"[A-Z](?:[A-Z0-9_]{0,38}[A-Z0-9])?\Z")
PLACEHOLDER = re.compile(
    r"\[[ \t]*(?P<label>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ_]{0,39}?)[ \t_]+"
    r"(?P<index>[0-9]{1,6})[ \t]*\]"
    r"|\b(?P<bare_label>[A-ZÁÉÍÓÚÜÑ][A-Z0-9ÁÉÍÓÚÜÑ_]{0,39}?)_(?P<bare_index>[0-9]{1,6})\b"
)


def fold(value: str) -> str:
    """Casefold, strip accents, drop punctuation and collapse whitespace."""
    decomposed = unicodedata.normalize("NFD", value.casefold())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", letters).split())


def canonical_placeholder(label: str, index: str | int) -> str:
    if not isinstance(label, str):
        raise ValueError("Invalid placeholder label")
    normalized = fold(label).upper().replace(" ", "_")
    if not _LABEL.fullmatch(normalized):
        raise ValueError("Invalid placeholder label")
    if type(index) is not int and (
        not isinstance(index, str) or not re.fullmatch(r"[0-9]{1,6}", index)
    ):
        raise ValueError("Invalid placeholder index")
    number = int(index)
    if not 0 <= number <= 999999:
        raise ValueError("Invalid placeholder index")
    return f"[{normalized}_{number}]"


def _context_value(findings: Iterable[Finding], prefix: str) -> str | None:
    values = {c[len(prefix) :] for f in findings for c in f.context if c.startswith(prefix)}
    return values.pop() if len(values) == 1 else None


@dataclass
class PlaceholderAllocator:
    """Allocate exact-value placeholders within one trusted document/session.

    Call ``reserve_source`` before transforming input. Literal placeholder-like
    source text is never allocated or accepted as a generated token. A source
    token colliding with an earlier issued token fails explicitly.
    """

    labels: Mapping[str, str] = field(default_factory=lambda: dict(LABELS_ES))
    role_labels: Mapping[str, str] = field(default_factory=lambda: dict(ROLE_LABELS_ES))
    use_roles: bool = True
    _key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    _counters: dict[str, int] = field(default_factory=dict, repr=False)
    _exact: dict[tuple[str, str | None, str | None, str], str] = field(
        default_factory=dict, repr=False
    )
    _issued: dict[str, tuple[str, str | None]] = field(default_factory=dict, repr=False)
    _reserved: set[str] = field(default_factory=set, repr=False)
    _vault_session_id: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        for label in list(self.labels.values()) + list(self.role_labels.values()):
            if not isinstance(label, str) or not _LABEL.match(label):
                raise ValueError("Placeholder labels must be short uppercase identifiers")

    def _hash(self, value: str) -> str:
        return hmac.new(
            self._key, value.encode("utf-8", "surrogatepass"), hashlib.sha256
        ).hexdigest()

    def _new(self, label: str, entity_type: str, role: str | None) -> str:
        while True:
            index = self._counters.get(label, 0) + 1
            if index > 999999:
                raise ValueError("Placeholder capacity exceeded")
            self._counters[label] = index
            placeholder = f"[{label}_{index}]"
            if placeholder not in self._reserved and placeholder not in self._issued:
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

    def reserve_source(self, text: str) -> None:
        """Reserve all accepted token spellings before allocating output tokens."""
        if not isinstance(text, str):
            raise TypeError("Placeholder source must be Unicode text")
        tokens = {
            canonical_placeholder(
                match.group("label") or match.group("bare_label"),
                match.group("index") or match.group("bare_index"),
            )
            for match in PLACEHOLDER.finditer(text)
        }
        if tokens.intersection(self._issued):
            raise ValueError("Source contains a previously issued placeholder")
        self._reserved.update(tokens)

    def placeholder(self, value: str, entity_type: str, findings: Sequence[Finding] = ()) -> str:
        """Return a stable token only for the exact same value, type, role and gender."""
        if not isinstance(value, str) or not value:
            raise ValueError("Placeholder values must be nonempty Unicode text")
        if not isinstance(entity_type, str) or not entity_type:
            raise ValueError("Placeholder entity type must be a nonempty string")
        role = _context_value(findings, "role:") if entity_type == "PERSON" else None
        gender = _context_value(findings, "gender:") if entity_type == "PERSON" else None
        normalized = unicodedata.normalize("NFC", value)
        key = (entity_type, role, gender, self._hash(normalized))
        if key not in self._exact:
            self._exact[key] = self._new(self._label(entity_type, role), entity_type, role)
        return self._exact[key]

    def issued(self) -> dict[str, tuple[str, str | None]]:
        """Placeholder -> (entity type, role). Contains no source values."""
        return dict(self._issued)

    def bind_vault(self, session_id: str, values: Mapping[str, str | None]) -> None:
        """Bind an empty vault or validate a resumed vault against this allocator.

        Token names alone are insufficient: different allocators both issue
        ``[PERSONA_1]``. Resumption requires the existing session binding and
        every value's keyed identity, preserving its original type/role/gender.
        No plaintext or serialized allocator state is retained here.
        """
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Vault requires an opaque session identity")
        if (
            self._vault_session_id not in {None, session_id}
            or values
            and self._vault_session_id != session_id
        ):
            raise ValueError("A populated vault requires its matching session allocator")
        identities = {placeholder: key for key, placeholder in self._exact.items()}
        for placeholder, value in values.items():
            identity = identities.get(placeholder)
            if (
                identity is None
                or not isinstance(value, str)
                or self._issued.get(placeholder) != identity[:2]
                or not hmac.compare_digest(
                    identity[3], self._hash(unicodedata.normalize("NFC", value))
                )
            ):
                raise ValueError("Vault values do not match the session allocator")
        self._vault_session_id = session_id

    def reset(self) -> None:
        self._counters.clear()
        self._exact.clear()
        self._reserved.clear()
        self._issued.clear()
        self._vault_session_id = None
        self._key = secrets.token_bytes(32)


__all__ = [
    "LABELS_ES",
    "PLACEHOLDER",
    "ROLE_LABELS_ES",
    "PlaceholderAllocator",
    "canonical_placeholder",
    "fold",
]
