"""Format-independent, local-offset privacy findings and document graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EntityType(StrEnum):
    PERSON = "PERSON"
    ADDRESS = "ADDRESS"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    RFC = "RFC"
    CURP = "CURP"
    CLABE = "CLABE"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    PAYMENT_CARD = "PAYMENT_CARD"
    NATIONAL_ID = "NATIONAL_ID"
    EMPLOYEE_ID = "EMPLOYEE_ID"
    CUSTOMER_ID = "CUSTOMER_ID"
    PASSPORT = "PASSPORT"
    DOCUMENT_ID = "DOCUMENT_ID"
    REGIONAL_ID = "REGIONAL_ID"
    DIAGNOSIS = "DIAGNOSIS"
    MEDICAL_CONDITION = "MEDICAL_CONDITION"
    TREATMENT = "TREATMENT"
    MEDICATION = "MEDICATION"
    CLINICAL_OBSERVATION = "CLINICAL_OBSERVATION"
    MEDICAL_HISTORY = "MEDICAL_HISTORY"
    PATIENT_ID = "PATIENT_ID"
    MEDICAL_ATTRIBUTE = "MEDICAL_ATTRIBUTE"
    API_KEY = "API_KEY"
    CREDENTIAL = "CREDENTIAL"
    AUTH_TOKEN = "AUTH_TOKEN"
    CONTRACT_ID = "CONTRACT_ID"
    INTERNAL_ID = "INTERNAL_ID"
    CONFIDENTIAL = "CONFIDENTIAL"
    AGE = "AGE"
    LOCATION = "LOCATION"
    DATE = "DATE"
    OCCUPATION = "OCCUPATION"
    DEMOGRAPHIC = "DEMOGRAPHIC"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    fragment_id: str = ""
    page: int | None = None
    row: int | None = None
    column: str | None = None
    cell: str | None = None
    json_path: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    part: str | None = None


@dataclass(frozen=True, slots=True)
class Finding:
    entity_type: str
    start: int
    end: int
    score: float
    detector: str
    validation: str = "pattern"
    context: tuple[str, ...] = ()
    model_version: str = "rules-0.2"
    confidence: float | None = None
    risk: str = "high"
    location: SourceLocation | None = None
    labels: tuple[str, ...] = ()
    protected: bool = False

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Finding offsets must describe a non-empty half-open span")
        if not 0 <= self.score <= 1:
            raise ValueError("Finding score must be between zero and one")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Calibrated confidence must be between zero and one")


@dataclass(slots=True)
class Fragment:
    id: str
    text: str = field(repr=False)
    location: SourceLocation = field(default_factory=SourceLocation)
    kind: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class DocumentGraph:
    document_id: str
    source_format: str
    fragments: list[Fragment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)
    issues: list[str] = field(default_factory=list)
    complete: bool = True


__all__ = ["DocumentGraph", "EntityType", "Finding", "Fragment", "SourceLocation"]
