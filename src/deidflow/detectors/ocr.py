"""Conservative labelled-field candidates for damaged OCR, without correction.

These are uncertain findings, not assertions that a damaged value is a valid ID.
They preserve the exact OCR offsets and require review under the default policy.
"""

from __future__ import annotations

import re

from deidflow.core import Finding

_FIELDS = re.compile(
    r"(?im)\b(?P<label>correo(?:[ \t]+electr[oó]nico)?|e-?mail|tel[eé]fono|tel\.?|celular|m[oó]vil|phone|CURP|RFC|CLABE|cuenta(?:[ \t]+bancaria)?|nombre(?:[ \t]+completo)?|paciente|domicilio|direcci[oó]n|fecha[ \t]+de[ \t]+nacimiento|pasaporte|expediente|id[ \t]+(?:cliente|empleado)|api[ _-]?key|contrase[nñ]a|diagn[oó]stico|tratamiento|medicaci[oó]n)"
    r"[ \t]*[:=][ \t]*(?P<value>[^\r\n]{1,240})"
)


def ocr_field_candidates(text: str, existing: list[Finding]) -> list[Finding]:
    candidates: list[Finding] = []
    identified = any(
        finding.entity_type
        in {"PERSON", "EMAIL", "CURP", "PATIENT_ID", "CUSTOMER_ID", "EMPLOYEE_ID", "RFC"}
        for finding in existing
    )
    for match in _FIELDS.finditer(text):
        label = match.group("label").lower()
        start, end = match.span("value")
        while start < end and text[start].isspace():
            start += 1
        while end > start and (text[end - 1].isspace() or text[end - 1] in ".,;"):
            end -= 1
        if end <= start or not any(c.isalnum() for c in text[start:end]):
            continue
        if label.startswith(("diagn", "tratamiento", "medicaci")):
            # A damaged clinical value can evade a vocabulary rule, then become
            # legible after redaction changes the OCR layout. Protect the entire
            # labelled value conservatively only when a subject was identified;
            # uncertainty remains visible to the release gate.
            if not identified:
                continue
            kind = (
                "DIAGNOSIS"
                if label.startswith("diagn")
                else "TREATMENT"
                if label.startswith("tratamiento")
                else "MEDICATION"
            )
        elif label.startswith(("correo", "email", "e-mail")):
            kind = "EMAIL"
        elif label.startswith(("tel", "celular", "móvil", "movil", "phone")):
            kind = "PHONE"
        elif label.upper() in {"CURP", "RFC", "CLABE"}:
            kind = label.upper()
        elif label.startswith("cuenta"):
            kind = "BANK_ACCOUNT"
        elif label.startswith(("nombre", "paciente")):
            kind = "PERSON"
        elif label.startswith(("domicilio", "direcci")):
            kind = "ADDRESS"
        elif label.startswith("fecha"):
            kind = "DATE_OF_BIRTH"
        elif label.startswith("pasaporte"):
            kind = "PASSPORT"
        elif label.startswith("expediente"):
            kind = "PATIENT_ID"
        elif "cliente" in label:
            kind = "CUSTOMER_ID"
        elif "empleado" in label:
            kind = "EMPLOYEE_ID"
        elif label.startswith("api"):
            kind = "API_KEY"
        else:
            kind = "CREDENTIAL"
        # Do not add a low-rank duplicate when an exact recognizer has already
        # covered all meaningful characters. Spaces in formatted IDs are benign.
        if all(
            not text[i].isalnum()
            or any(f.entity_type == kind and f.start <= i < f.end for f in existing)
            for i in range(start, end)
        ):
            continue
        candidates.append(
            Finding(
                kind,
                start,
                end,
                0.6,
                "ocr.label_context",
                validation="ocr_uncertain",
                context=("labelled_ocr_value_unvalidated",),
                model_version="ocr-context-0.3",
                protected=True,
            )
        )
    return candidates
