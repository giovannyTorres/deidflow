"""Generic character-span corpora: DeidFlow span JSONL and the Gretel finance set.

Span JSONL is one object per line::

    {"id": "doc-1", "text": "...", "spans": [{"start": 0, "end": 5, "label": "PERSON"}]}

Offsets are Python string (Unicode code point) offsets, half-open. Every span is
checked against its text; malformed records fail instead of being skipped.

The Gretel ``synthetic_pii_finance_multilingual`` dataset (Apache-2.0) is
LLM-generated financial documents with character-offset PII spans in seven
languages, including Spanish. Its loader reads a locally downloaded Parquet or
JSONL export, keeps one language and maps the published labels onto the
DeidFlow taxonomy. Unknown labels raise an error, so a schema change cannot
silently drop gold spans.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from .datasets import Example, GoldSpan
from .public_corpus import PublicCorpus, _outside_repository

MAX_LINE_BYTES = 8 * 1024**2

GRETEL_FINANCE: dict[str, Any] = {
    "repository": "https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual",
    "license": "Apache-2.0",
    "license_url": "https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual",
    "provenance_kind": "synthetic_financial",
    "already_anonymized": "Synthetic documents generated with Gretel Navigator; no real customer data",
    "attribution": "Gretel.ai, synthetic_pii_finance_multilingual (Apache-2.0)",
    "gold": True,
    "text_field": "generated_text",
    "spans_field": "pii_spans",
    "language_field": "language",
}

GRETEL_LABELS: dict[str, str] = {
    "account_pin": "CREDENTIAL",
    "api_key": "API_KEY",
    "bank_routing_number": "BANK_ACCOUNT",
    "bban": "BANK_ACCOUNT",
    "company": "ORGANIZATION",
    "credit_card_number": "PAYMENT_CARD",
    "credit_card_security_code": "PAYMENT_CARD",
    "customer_id": "CUSTOMER_ID",
    "date": "DATE",
    "date_of_birth": "DATE_OF_BIRTH",
    "date_time": "DATE",
    "driver_license_number": "NATIONAL_ID",
    "email": "EMAIL",
    "employee_id": "EMPLOYEE_ID",
    "first_name": "PERSON",
    "iban": "BANK_ACCOUNT",
    "ipv4": "IP_ADDRESS",
    "ipv6": "IP_ADDRESS",
    "last_name": "PERSON",
    "local_latlng": "LOCATION",
    "name": "PERSON",
    "passport_number": "PASSPORT",
    "password": "CREDENTIAL",
    "phone_number": "PHONE",
    "ssn": "NATIONAL_ID",
    "street_address": "ADDRESS",
    "swift_bic_code": "BANK_ACCOUNT",
    "time": "DATE",
    "user_name": "CREDENTIAL",
}


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    if len({key for key, _ in items}) != len(items):
        raise ValueError("Duplicate JSON keys are not allowed in span corpora")
    return dict(items)


def _reject(value: str) -> None:
    raise ValueError("Non-finite JSON numbers are not allowed in span corpora")


def _json_lines(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as stream:
        for number, line in enumerate(stream, 1):
            if len(line) > MAX_LINE_BYTES:
                raise ValueError(f"Span corpus line {number} exceeds the size limit")
            if not line.strip():
                continue
            try:
                record = json.loads(
                    line.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject
                )
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError(f"Span corpus line {number} is not valid JSON") from None
            if not isinstance(record, dict):
                raise ValueError(f"Span corpus line {number} is not an object")
            yield record


def _spans(
    text: str, raw: Any, labels: Mapping[str, str] | None, where: str
) -> tuple[GoldSpan, ...]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw, parse_constant=_reject)
        except json.JSONDecodeError:
            raise ValueError(where + ": spans field is not valid JSON") from None
    if not isinstance(raw, list):
        raise ValueError(where + ": spans must be a list")
    spans = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(where + ": span must be an object")
        start, end, label = item.get("start"), item.get("end"), item.get("label")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError(where + ": span offsets are outside the text")
        if not isinstance(label, str) or not label:
            raise ValueError(where + ": span label must be a nonempty string")
        if labels is not None:
            if label not in labels:
                raise ValueError(where + f": unknown span label {label!r}")
            label = labels[label]
        if not text[start:end].strip():
            raise ValueError(where + ": span covers only whitespace")
        spans.add(GoldSpan(label, start, end))
    return tuple(sorted(spans, key=lambda s: (s.start, s.end, s.entity_type)))


def load_span_jsonl(
    path: str | Path,
    *,
    split: str = "test",
    source: str = "span-jsonl",
    language: str = "es",
    provenance_kind: str = "local_annotated",
    labels: Mapping[str, str] | None = None,
) -> PublicCorpus:
    """Load DeidFlow span JSONL; ``labels`` optionally maps and restricts labels."""
    path = Path(path)
    examples = []
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    for number, record in enumerate(_json_lines(path), 1):
        identifier, text = record.get("id", str(number)), record.get("text")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError(f"Span corpus line {number}: id must be a unique nonempty string")
        if not isinstance(text, str):
            raise ValueError(f"Span corpus line {number}: text must be a string")
        seen.add(identifier)
        spans = _spans(text, record.get("spans", []), labels, f"Span corpus line {number}")
        counts.update(span.entity_type for span in spans)
        examples.append(
            Example(identifier, text, spans, split, f"{source}-{split}", challenge=provenance_kind)
        )
    if not examples:
        raise ValueError("Span corpus contains no documents")
    return PublicCorpus(
        source,
        language,
        provenance_kind,
        tuple(examples),
        {
            "official_split": split,
            "labels": dict(sorted(counts.items())),
            "gold_span_count": sum(counts.values()),
            "text_bytes": sum(len(e.text.encode()) for e in examples),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "gold_verified_against_text": True,
        },
    )


def _gretel_records(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as parquet
        except ImportError:
            raise RuntimeError("Reading Parquet requires deidflow[tables]") from None
        table = parquet.read_table(path)
        yield from table.to_pylist()
    elif path.suffix in {".jsonl", ".json"}:
        yield from _json_lines(path)
    else:
        raise ValueError("Gretel finance files must be Parquet or JSONL")


def load_gretel_finance(
    files: Iterable[str | Path],
    *,
    language: str = "Spanish",
    split: str = "test",
) -> PublicCorpus:
    """Load one language of the Gretel finance corpus from local files."""
    examples = []
    counts: Counter[str] = Counter()
    original: Counter[str] = Counter()
    documents_by_language: Counter[str] = Counter()
    document_types: Counter[str] = Counter()
    for file in files:
        path = Path(file)
        for number, record in enumerate(_gretel_records(path), 1):
            where = f"{path.name} record {number}"
            for field in (GRETEL_FINANCE["text_field"], GRETEL_FINANCE["spans_field"]):
                if field not in record:
                    raise ValueError(where + f": missing expected field {field!r}")
            record_language = str(record.get(GRETEL_FINANCE["language_field"], ""))
            documents_by_language[record_language] += 1
            if record_language != language:
                continue
            text = record[GRETEL_FINANCE["text_field"]]
            if not isinstance(text, str):
                raise ValueError(where + ": text must be a string")
            raw = record[GRETEL_FINANCE["spans_field"]]
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, list):
                original.update(str(item.get("label")) for item in parsed if isinstance(item, dict))
            spans = _spans(text, raw, GRETEL_LABELS, where)
            counts.update(span.entity_type for span in spans)
            document_types[str(record.get("document_type", ""))] += 1
            examples.append(
                Example(
                    f"{path.stem}-{number}",
                    text,
                    spans,
                    split,
                    f"gretel-finance-{split}",
                    challenge="synthetic_financial",
                )
            )
    if not examples:
        raise ValueError(f"No {language} documents found in the Gretel finance files")
    return PublicCorpus(
        "gretel_finance",
        language,
        "synthetic_financial",
        tuple(examples),
        {
            "official_split": split,
            "original_labels": dict(sorted(original.items())),
            "labels": dict(sorted(counts.items())),
            "documents_by_language": dict(sorted(documents_by_language.items())),
            "document_types": len(document_types),
            "gold_span_count": sum(counts.values()),
            "text_bytes": sum(len(e.text.encode()) for e in examples),
            "gold_verified_against_text": True,
        },
    )


def gretel_files(root: str | Path, split: str) -> list[Path]:
    """Data files of one published split (``train`` or ``test``) in a registered directory."""
    if split not in {"train", "test"}:
        raise ValueError("The Gretel finance corpus publishes only train and test splits")
    files = sorted(
        path
        for path in Path(root).iterdir()
        if path.is_file()
        and path.suffix in {".parquet", ".jsonl"}
        and (path.name.startswith(split + "-") or ("_" + split + "-") in path.name)
    )
    if not files:
        raise ValueError(f"No Gretel finance {split} files found")
    return files


def hash_split(
    examples: Iterable[Example], *, validation_fraction: float = 0.1, salt: str = "deidflow"
) -> tuple[list[Example], list[Example]]:
    """Deterministic train/validation split keyed by a hash of each document's text.

    Identical texts always land on the same side, so exact duplicates cannot leak
    across the split. Returns ``(train, validation)`` with updated split names.
    """
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between zero and one")
    from dataclasses import replace

    train, validation = [], []
    for example in examples:
        digest = hashlib.sha256((salt + "\0" + example.text).encode()).digest()
        if int.from_bytes(digest[:8], "big") / 2**64 < validation_fraction:
            validation.append(replace(example, split="validation"))
        else:
            train.append(replace(example, split="train"))
    if not train or not validation:
        raise ValueError("Split produced an empty partition")
    return train, validation


def register_local_files(
    source: str,
    files: Iterable[str | Path],
    destination: str | Path,
    specification: Mapping[str, Any],
) -> dict[str, Any]:
    """Copy downloaded corpus files outside the repository and pin their SHA-256."""
    root = _outside_repository(Path(destination)) / source
    root.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for file in files:
        path = Path(file)
        if not path.is_file():
            raise ValueError("Corpus file not found")
        target = root / path.name
        if target.name in digests:
            raise ValueError("Duplicate corpus file name")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Registered corpus file differs from the new copy")
        if not target.exists():
            shutil.copyfile(path, target)
        digests[target.name] = digest
    if not digests:
        raise ValueError("No corpus files supplied")
    manifest = {
        "schema_version": 1,
        "source": source,
        **dict(specification),
        "files": dict(sorted(digests.items())),
        "file_digest_manifest_sha256": hashlib.sha256(
            json.dumps(digests, sort_keys=True).encode()
        ).hexdigest(),
        "raw_documents_committed": False,
    }
    (root.parent / (source + "-provenance.json")).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def verify_registered_files(root: str | Path, source: str) -> dict[str, Any]:
    """Recheck registered files against the manifest written at registration."""
    root = _outside_repository(Path(root))
    manifest = json.loads((root.parent / (source + "-provenance.json")).read_text("utf-8"))
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.iterdir()
        if path.is_file()
    }
    if actual != manifest["files"]:
        raise ValueError("Registered corpus files differ from their manifest")
    return {
        "file_digest_manifest_sha256": manifest["file_digest_manifest_sha256"],
        "verified_corpus_files": len(actual),
        "method": "SHA256 per file equal to the manifest recorded at registration",
    }


__all__ = [
    "GRETEL_FINANCE",
    "GRETEL_LABELS",
    "gretel_files",
    "hash_split",
    "load_gretel_finance",
    "load_span_jsonl",
    "register_local_files",
    "verify_registered_files",
]
