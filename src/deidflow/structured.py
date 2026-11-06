"""Bounded column profiles, full-cell policies and exhaustive value scanning."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any

from deidflow.core import Finding, SourceLocation
from deidflow.detectors import CORE_RULES_VERSION, RuleDetector, fuse

_HEADERS = {
    "nombre": "PERSON",
    "nombre_completo": "PERSON",
    "name": "PERSON",
    "patient_name": "PERSON",
    "paciente": "PERSON",
    "email": "EMAIL",
    "correo": "EMAIL",
    "correo_electronico": "EMAIL",
    "telefono": "PHONE",
    "teléfono": "PHONE",
    "phone": "PHONE",
    "curp": "CURP",
    "rfc": "RFC",
    "clabe": "CLABE",
    "cuenta": "BANK_ACCOUNT",
    "account_number": "BANK_ACCOUNT",
    "tarjeta": "PAYMENT_CARD",
    "domicilio": "ADDRESS",
    "direccion": "ADDRESS",
    "dirección": "ADDRESS",
    "address": "ADDRESS",
    "fecha_nacimiento": "DATE_OF_BIRTH",
    "date_of_birth": "DATE_OF_BIRTH",
    "dob": "DATE_OF_BIRTH",
    "id_cliente": "CUSTOMER_ID",
    "customer_id": "CUSTOMER_ID",
    "id_empleado": "EMPLOYEE_ID",
    "employee_id": "EMPLOYEE_ID",
    "expediente": "PATIENT_ID",
    "patient_id": "PATIENT_ID",
    "pasaporte": "PASSPORT",
    "api_key": "API_KEY",
    "password": "CREDENTIAL",
    "token": "AUTH_TOKEN",
}


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    entity_type: str | None
    score: float
    evidence: tuple[str, ...]
    sample_size: int
    mean_length: float
    uniqueness: float
    entropy: float
    digit_fraction: float
    validator_hit_rate: float
    unknown_identifier: bool = False

    @property
    def model_version(self) -> str:
        # Exact header mappings are unchanged. Inferred schema categories depend
        # on current core detections and cannot reuse their old calibration.
        return "rules-0.2" if self.evidence == ("header_exact",) else f"schema-{CORE_RULES_VERSION}"


def profile_table(
    headers: list[str], rows: list[list[Any]], detector: RuleDetector
) -> list[ColumnProfile]:
    profiles = [
        profile_column(h, [r[j] for r in rows[:128]], detector) for j, h in enumerate(headers)
    ]
    # A diagnosis vocabulary on its own is not evidence of personal health data.
    # These are conservative schema associations, not identity or causality claims.
    subjects = {"PERSON", "PATIENT_ID", "CUSTOMER_ID", "EMAIL", "CURP", "RFC"}
    if any(p.entity_type in subjects for p in profiles):
        medical = {
            "diagnóstico": "DIAGNOSIS",
            "diagnostico": "DIAGNOSIS",
            "diagnosis": "DIAGNOSIS",
            "medicación": "MEDICATION",
            "medicacion": "MEDICATION",
            "medication": "MEDICATION",
            "tratamiento": "TREATMENT",
            "treatment": "TREATMENT",
            "historia_clinica": "MEDICAL_HISTORY",
            "clinical_observation": "CLINICAL_OBSERVATION",
        }
        profiles = [
            replace(
                p,
                entity_type=medical[h.strip().lower()],
                score=0.85,
                evidence=("health_subject_schema",),
            )
            if h.strip().lower() in medical and p.entity_type is None
            else p
            for h, p in zip(headers, profiles, strict=True)
        ]
    return profiles


def profile_column(
    name: str, values: list[Any], detector: RuleDetector | None = None
) -> ColumnProfile:
    detector = detector or RuleDetector()
    text = [str(v) for v in values if v is not None and str(v).strip()]
    header = re.sub(r"[\s-]+", "_", name.strip().lower())
    characters = Counter("".join(text))
    count = sum(characters.values())
    entropy = (
        -sum((n / count) * math.log2(n / count) for n in characters.values()) if count else 0.0
    )
    hits: Counter[str] = Counter()
    for value in text:
        hits.update(
            {
                f.entity_type
                for f in detector.detect(value)
                if f.end - f.start >= len(value.strip()) * 0.8
            }
        )
    kind: str | None = None
    score = 0.0
    evidence: tuple[str, ...] = ()
    if header in _HEADERS:
        kind, score, evidence = _HEADERS[header], 0.95, ("header_exact",)
    elif hits:
        label, n = hits.most_common(1)[0]
        rate = n / max(1, len(text))
        if len(text) >= 3 and rate >= 0.8:
            kind, score, evidence = label, min(0.94, rate), ("value_pattern_rate",)
    uniqueness = len(set(text)) / max(1, len(text))
    lengths = Counter(len(v) for v in text)
    unknown = (
        kind is None
        and len(text) >= 3
        and uniqueness > 0.8
        and max(lengths.values(), default=0) / len(text) > 0.8
        and any(any(c.isdigit() for c in v) and any(c.isalpha() for c in v) for v in text)
    )
    return ColumnProfile(
        name,
        kind,
        score,
        evidence,
        len(text),
        sum(map(len, text)) / max(1, len(text)),
        uniqueness,
        entropy,
        sum(c.isdigit() * n for c, n in characters.items()) / max(1, count),
        max(hits.values(), default=0) / max(1, len(text)),
        unknown,
    )


def scan_cell(
    value: Any, profile: ColumnProfile, detector: RuleDetector, *, row: int, column: str
) -> list[Finding]:
    if value is None or str(value) == "":
        return []
    text = str(value)
    location = SourceLocation(fragment_id=f"r{row}c{column}", row=row, column=column)
    from dataclasses import replace

    findings = [replace(f, location=location) for f in detector.detect(text)]
    if profile.entity_type:
        findings.append(
            Finding(
                profile.entity_type,
                0,
                len(text),
                profile.score,
                "schema.column",
                model_version=profile.model_version,
                validation="contextual",
                context=profile.evidence,
                location=location,
                protected=True,
            )
        )
    return fuse(findings)


def dataframe_columns(frame: Any) -> tuple[list[str], dict[str, list[Any]], str]:
    module = type(frame).__module__.split(".")[0]
    if module == "pandas":
        if frame.columns.has_duplicates or not all(isinstance(c, str) for c in frame.columns):
            raise ValueError("DataFrame columns must be unique strings")
        # Replace missing values before string conversion; never turn NaN into an identifier.
        return (
            list(frame.columns),
            {
                c: frame[c].astype(object).where(frame[c].notna(), None).tolist()
                for c in frame.columns
            },
            module,
        )
    if module == "polars":
        return frame.columns, frame.to_dict(as_series=False), module
    raise TypeError("Expected a pandas or Polars DataFrame")
