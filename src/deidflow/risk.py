"""Inspectable risk flags, not an anonymity certificate or attack probability."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from deidflow.core import Finding


@dataclass(frozen=True)
class RiskAssessment:
    finding_count: int
    by_type: dict[str, int]
    direct_identifier_count: int
    quasi_identifier_groups: int
    health_subject_groups: int
    flags: tuple[str, ...]
    anonymity_proven: bool = False


def assess(findings: list[Finding]) -> RiskAssessment:
    quasi = {"AGE", "LOCATION", "DATE", "OCCUPATION", "DEMOGRAPHIC"}
    health = {
        "DIAGNOSIS",
        "MEDICAL_CONDITION",
        "TREATMENT",
        "MEDICATION",
        "MEDICAL_HISTORY",
        "MEDICAL_ATTRIBUTE",
        "CLINICAL_OBSERVATION",
    }
    direct = {
        "PERSON",
        "EMAIL",
        "PHONE",
        "ADDRESS",
        "CURP",
        "RFC",
        "CLABE",
        "PAYMENT_CARD",
        "BANK_ACCOUNT",
        "PATIENT_ID",
        "CUSTOMER_ID",
        "EMPLOYEE_ID",
        "PASSPORT",
        "NATIONAL_ID",
    }
    groups: dict[tuple[object, ...], set[str]] = defaultdict(set)
    for finding in findings:
        location = finding.location
        key = (location.page, location.row) if location else (None, None)
        groups[key].add(finding.entity_type)
    q = sum(len(kinds & quasi) >= 2 for kinds in groups.values())
    h = sum(bool(kinds & health) and bool(kinds & direct) for kinds in groups.values())
    flags = []
    if q:
        flags.append("QUASI_IDENTIFIER_COMBINATION")
    if h:
        flags.append("HEALTH_WITH_IDENTIFIABLE_SUBJECT_CANDIDATE")
    if any(f.validation == "invalid" for f in findings):
        flags.append("INVALID_IDENTIFIER_STILL_SENSITIVE_CANDIDATE")
    return RiskAssessment(
        len(findings),
        dict(Counter(f.entity_type for f in findings)),
        sum(f.entity_type in direct for f in findings),
        q,
        h,
        tuple(flags),
    )
