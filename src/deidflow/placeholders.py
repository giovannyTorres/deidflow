"""Indexed, role-aware pseudonyms with exact-value identity and source collision guards.

The allocator keeps keyed hashes, never source values. Equal Unicode-normalized
values with identical type/role/gender reuse a token. Optional compatible-context
linkage carries forward missing metadata only for one compatible exact-value
identity; conflicting explicit metadata and name aliases never establish identity. Re-identification belongs in an explicit local vault.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

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
    "IP_ADDRESS": "DIRECCION_IP",
    "TAX_ID": "ID_FISCAL",
    "OTHER_SENSITIVE": "DATO_SENSIBLE",
    "AMOUNT": "IMPORTE",
}
ROLE_LABELS_ES: dict[str, str] = {
    "patient": "PACIENTE",
    "clinician": "MEDICO",
    "family": "FAMILIAR",
    "customer": "CLIENTE",
    "creditor": "ACREEDOR",
    "debtor": "DEUDOR",
    "agent": "AGENTE",
    "plaintiff": "DEMANDANTE",
    "defendant": "DEMANDADO",
    "witness": "TESTIGO",
    "lawyer": "ABOGADO",
    "judge": "JUEZ",
}
_MAX_IDENTITIES = 100000
_TYPE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
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
    compatible_context: bool = False
    _key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    _counters: dict[str, int] = field(default_factory=dict, repr=False)
    _exact: dict[tuple[str, str | None, str | None, str], str] = field(
        default_factory=dict, repr=False
    )
    _issued: dict[str, tuple[str, str | None]] = field(default_factory=dict, repr=False)
    _contexts: dict[str, tuple[str | None, str | None]] = field(default_factory=dict, repr=False)
    _value_index: dict[tuple[str, str], set[str]] = field(
        default_factory=dict, init=False, repr=False
    )
    _reserved: set[str] = field(default_factory=set, repr=False)
    _vault_session_id: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.compatible_context) is not bool:
            raise ValueError("compatible_context must be a boolean")
        for label in list(self.labels.values()) + list(self.role_labels.values()):
            if not isinstance(label, str) or not _LABEL.match(label):
                raise ValueError("Placeholder labels must be short uppercase identifiers")

    def _hash(self, value: str) -> str:
        return hmac.new(
            self._key, value.encode("utf-8", "surrogatepass"), hashlib.sha256
        ).hexdigest()

    def _new(self, label: str, entity_type: str, role: str | None) -> str:
        if len(self._issued) >= _MAX_IDENTITIES:
            raise ValueError("Placeholder capacity exceeded")
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
        return self.labels.get(entity_type) or "DATO_SENSIBLE"

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
        if len(self._reserved | tokens) > _MAX_IDENTITIES:
            raise ValueError("Reserved placeholder capacity exceeded")
        self._reserved.update(tokens)

    @staticmethod
    def _compatible(known: str | None, observed: str | None) -> bool:
        return known is None or observed is None or known == observed

    def placeholder(self, value: str, entity_type: str, findings: Sequence[Finding] = ()) -> str:
        """Allocate exact values; optionally retain uniquely compatible known context.

        Compatible context never normalizes names beyond NFC, changes entity type,
        or merges conflicting explicit roles/genders. Ambiguous missing context
        fails closed, including when an old metadata-free lookup key exists.
        """
        if not isinstance(value, str) or not value:
            raise ValueError("Placeholder values must be nonempty Unicode text")
        if not isinstance(entity_type, str) or not entity_type:
            raise ValueError("Placeholder entity type must be a nonempty string")
        role = _context_value(findings, "role:") if entity_type == "PERSON" else None
        gender = _context_value(findings, "gender:") if entity_type == "PERSON" else None
        if self.compatible_context and entity_type == "PERSON":
            for prefix in ("role:", "gender:"):
                observed = {
                    c[len(prefix) :] for f in findings for c in f.context if c.startswith(prefix)
                }
                if len(observed) > 1:
                    raise ValueError("Conflicting explicit identity context")
        if any(v is not None and not 1 <= len(v) <= 64 for v in (role, gender)):
            raise ValueError("Invalid identity context")
        normalized = unicodedata.normalize("NFC", value)
        digest = self._hash(normalized)
        key = (entity_type, role, gender, digest)
        token: str | None = None
        if self.compatible_context:
            candidates = set()
            for issued_token in self._value_index.get((entity_type, digest), ()):
                known_role, known_gender = self._contexts[issued_token]
                if self._compatible(known_role, role) and self._compatible(known_gender, gender):
                    candidates.add(issued_token)
            if len(candidates) > 1:
                raise ValueError("Ambiguous exact identity; explicit role or gender required")
            if candidates:
                token = candidates.pop()
        else:
            token = self._exact.get(key)
        if token is None:
            token = self._new(self._label(entity_type, role), entity_type, role)
            self._contexts[token] = (role, gender)
        else:
            known_role, known_gender = self._contexts[token]
            self._contexts[token] = (known_role or role, known_gender or gender)
        self._exact[key] = token
        self._value_index.setdefault((entity_type, digest), set()).add(token)
        return token

    def issued(self) -> dict[str, tuple[str, str | None]]:
        """Token -> (type, known explicit role), without renaming any issued token."""
        return {
            token: (kind, self._contexts[token][0]) for token, (kind, _) in self._issued.items()
        }

    def context_metadata(self) -> dict[str, tuple[str | None, str | None]]:
        """Known explicit (role, gender) constraints, without original source values."""
        return dict(self._contexts)

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
        identities: dict[str, tuple[str, str | None, str | None, str]] = {}
        for identity_key, token in self._exact.items():
            identities.setdefault(token, identity_key)
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
        if set(values) != set(self._issued):
            raise ValueError("Vault mappings are incomplete for the session allocator")
        self._vault_session_id = session_id

    def _dump_state(self) -> dict[str, Any]:
        """Private sensitive state; serialize ONLY inside authenticated encryption."""
        state = {
            "version": 2,
            "key": self._key.hex(),
            "labels": dict(self.labels),
            "role_labels": dict(self.role_labels),
            "use_roles": self.use_roles,
            "compatible_context": self.compatible_context,
            "contexts": {
                token: {"role": role, "gender": gender}
                for token, (role, gender) in self._contexts.items()
            },
            "counters": dict(self._counters),
            "identities": [
                {"token": token, "type": kind, "role": role, "gender": gender, "hash": digest}
                for (kind, role, gender, digest), token in self._exact.items()
            ],
            "reserved": sorted(self._reserved),
            "vault_session_id": self._vault_session_id,
        }
        validated = self._from_state(state)
        if (
            validated._issued != self._issued
            or validated._contexts != self._contexts
            or validated._value_index != self._value_index
        ):
            raise ValueError("Allocator state is inconsistent")
        return state

    @classmethod
    def _from_state(cls, state: Any) -> PlaceholderAllocator:
        """Validate decrypted session state; never load unauthenticated inputs here."""
        try:
            if not isinstance(state, dict):
                raise ValueError
            version = state.get("version")
            if type(version) is not int or version not in {1, 2}:
                raise ValueError
            fields = {
                "version",
                "key",
                "labels",
                "role_labels",
                "use_roles",
                "counters",
                "identities",
                "reserved",
                "vault_session_id",
            }
            if version == 2:
                fields |= {"compatible_context", "contexts"}
            if set(state) != fields:
                raise ValueError
            compatible = state.get("compatible_context", False)
            if type(compatible) is not bool:
                raise ValueError
            if not isinstance(state["key"], str) or not _HASH.fullmatch(state["key"]):
                raise ValueError
            if type(state["use_roles"]) is not bool:
                raise ValueError
            for name in ("labels", "role_labels"):
                mapping = state[name]
                if (
                    not isinstance(mapping, dict)
                    or len(mapping) > 256
                    or any(
                        not isinstance(k, str)
                        or not 1 <= len(k) <= 64
                        or not isinstance(v, str)
                        or not _LABEL.fullmatch(v)
                        for k, v in mapping.items()
                    )
                ):
                    raise ValueError
            counters = state["counters"]
            if (
                not isinstance(counters, dict)
                or len(counters) > 512
                or any(
                    not isinstance(k, str)
                    or not _LABEL.fullmatch(k)
                    or type(v) is not int
                    or not 1 <= v <= 999999
                    for k, v in counters.items()
                )
            ):
                raise ValueError
            identities, reserved = state["identities"], state["reserved"]
            if not isinstance(identities, list) or len(identities) > _MAX_IDENTITIES * 4:
                raise ValueError
            if not isinstance(reserved, list) or len(reserved) > _MAX_IDENTITIES:
                raise ValueError
            bound = state["vault_session_id"]
            if bound is not None and (
                not isinstance(bound, str) or not _SESSION_ID.fullmatch(bound)
            ):
                raise ValueError
            allocator = cls(
                labels=dict(state["labels"]),
                role_labels=dict(state["role_labels"]),
                use_roles=state["use_roles"],
                compatible_context=compatible,
                _key=bytes.fromhex(state["key"]),
            )
            allocator._counters = dict(counters)
            allocator._vault_session_id = bound

            def token_parts(token: Any) -> tuple[str, int]:
                if not isinstance(token, str) or not (match := PLACEHOLDER.fullmatch(token)):
                    raise ValueError
                label = match.group("label")
                index = match.group("index")
                if label is None or index is None or canonical_placeholder(label, index) != token:
                    raise ValueError
                return label, int(index)

            origins: dict[str, tuple[str, str | None, str | None, str]] = {}
            for entry in identities:
                if not isinstance(entry, dict) or set(entry) != {
                    "token",
                    "type",
                    "role",
                    "gender",
                    "hash",
                }:
                    raise ValueError
                token, kind, role, gender, digest = (
                    entry[k] for k in ("token", "type", "role", "gender", "hash")
                )
                label, index = token_parts(token)
                if not isinstance(kind, str) or not _TYPE.fullmatch(kind):
                    raise ValueError
                if any(
                    v is not None and (not isinstance(v, str) or not 1 <= len(v) <= 64)
                    for v in (role, gender)
                ):
                    raise ValueError
                if kind != "PERSON" and (role is not None or gender is not None):
                    raise ValueError
                if not isinstance(digest, str) or not _HASH.fullmatch(digest):
                    raise ValueError
                key = (kind, role, gender, digest)
                if key in allocator._exact:
                    raise ValueError
                if index < 1 or counters.get(label, 0) < index:
                    raise ValueError
                if token not in allocator._issued:
                    if (
                        len(allocator._issued) >= _MAX_IDENTITIES
                        or allocator._label(kind, role) != label
                    ):
                        raise ValueError
                    allocator._issued[token] = (kind, role)
                    allocator._contexts[token] = (role, gender)
                    origins[token] = key
                else:
                    origin = origins[token]
                    known_role, known_gender = allocator._contexts[token]
                    if (
                        not compatible
                        or origin[0] != kind
                        or origin[3] != digest
                        or not cls._compatible(known_role, role)
                        or not cls._compatible(known_gender, gender)
                    ):
                        raise ValueError
                    allocator._contexts[token] = (known_role or role, known_gender or gender)
                allocator._exact[key] = token
                allocator._value_index.setdefault((kind, digest), set()).add(token)
            if version == 2:
                contexts = state["contexts"]
                if not isinstance(contexts, dict) or set(contexts) != set(allocator._issued):
                    raise ValueError
                for token, expected in allocator._contexts.items():
                    record = contexts[token]
                    if (
                        not isinstance(record, dict)
                        or set(record) != {"role", "gender"}
                        or record["role"] != expected[0]
                        or record["gender"] != expected[1]
                    ):
                        raise ValueError
            for token in reserved:
                token_parts(token)
                if token in allocator._reserved or token in allocator._issued:
                    raise ValueError
                allocator._reserved.add(token)
            return allocator
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ValueError("Invalid encrypted allocator state") from None

    def reset(self) -> None:
        self._counters.clear()
        self._exact.clear()
        self._reserved.clear()
        self._issued.clear()
        self._contexts.clear()
        self._value_index.clear()
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
