"""Explicit pinned public acquisition and independently annotated corpus adapters.

Only public URLs from this registry are acquired. No acquisition runs during
inference; raw corpus files are deliberately kept outside the source repository.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import ssl
import subprocess
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .datasets import Example, GoldSpan

SOURCES: dict[str, dict[str, Any]] = {
    "meddocan": {
        "repository": "https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN",
        "commit": "783a6df385c975b328c99bcffb54196a9ba4078a",
        "archive_url": "https://codeload.github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN/zip/783a6df385c975b328c99bcffb54196a9ba4078a",
        "archive_sha256": "555470b36d90d04094aedf1a72bff079cb5dbcef98c8e40627a6beafc205ed1b",
        "file_digest_manifest_sha256": "ba4823b70e231902fe7d865c1193607631eb0a2d1f30c8591a6fc523388d4cdc",
        "license": "CC-BY-4.0",
        "license_url": "https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN/blob/783a6df385c975b328c99bcffb54196a9ba4078a/LICENSE",
        "language": "es",
        "format": "UTF-8 text + BRAT standoff",
        "gold": True,
        "provenance_kind": "semi_synthetic_clinical",
        "already_anonymized": "Released synthetic/enriched PHI, not original private patient records",
        "attribution": "SPACCC MEDDOCAN; 2019 Secretaria de Estado para el Avance Digital (SEAD)",
    },
    "tab": {
        "repository": "https://github.com/NorskRegnesentral/text-anonymization-benchmark",
        "commit": "558e09e26d6b36f5f78440074e6a233946d98bd9",
        "archive_url": "https://codeload.github.com/NorskRegnesentral/text-anonymization-benchmark/zip/558e09e26d6b36f5f78440074e6a233946d98bd9",
        "archive_sha256": "fc9925949e91b0eaf831fa8df0ad19ddc325d48e3aeae1e947d15872ba3eaa22",
        "file_digest_manifest_sha256": "cc6e2eac8ac649c0ea7f8b7c940af19e00af38e69fe50f2fa1c646f9de24f613",
        "license": "MIT",
        "license_url": "https://github.com/NorskRegnesentral/text-anonymization-benchmark/blob/558e09e26d6b36f5f78440074e6a233946d98bd9/LICENSE.txt",
        "language": "en",
        "format": "JSON text + human entity/masking annotations",
        "gold": True,
        "provenance_kind": "public_judicial",
        "already_anonymized": "Public ECHR judgments; masking decisions identify DIRECT/QUASI mentions",
        "attribution": "TAB; Copyright 2021-2026 Norsk Regnesentral; Pilan et al. 2022",
    },
}

MEDDOCAN_LABELS = {
    "CORREO_ELECTRONICO": "EMAIL",
    "NUMERO_TELEFONO": "PHONE",
    "NUMERO_FAX": "PHONE",
    "NOMBRE_PERSONAL_SANITARIO": "PERSON",
    "NOMBRE_SUJETO_ASISTENCIA": "PERSON",
    "FAMILIARES_SUJETO_ASISTENCIA": "PERSON",
    "CALLE": "ADDRESS",
    "PAIS": "LOCATION",
    "TERRITORIO": "LOCATION",
    "FECHAS": "DATE",
    "EDAD_SUJETO_ASISTENCIA": "AGE",
    "SEXO_SUJETO_ASISTENCIA": "DEMOGRAPHIC",
    "ID_SUJETO_ASISTENCIA": "PATIENT_ID",
    "ID_CONTACTO_ASISTENCIAL": "PATIENT_ID",
    "ID_ASEGURAMIENTO": "INSURANCE_ID",
    "ID_TITULACION_PERSONAL_SANITARIO": "REGIONAL_ID",
    "ID_EMPLEO_PERSONAL_SANITARIO": "EMPLOYEE_ID",
    "HOSPITAL": "MEDICAL_FACILITY",
    "CENTRO_SALUD": "MEDICAL_FACILITY",
    "INSTITUCION": "ORGANIZATION",
    "PROFESION": "OCCUPATION",
    "OTROS_SUJETO_ASISTENCIA": "OTHER_SENSITIVE",
}
TAB_LABELS = {
    "PERSON": "PERSON",
    "LOC": "LOCATION",
    "ORG": "ORGANIZATION",
    "DEM": "DEMOGRAPHIC",
    "DATETIME": "DATE",
    "CODE": "CODE",
    "MISC": "MISC",
    "QUANTITY": "QUANTITY",
}


@dataclass(frozen=True)
class PublicCorpus:
    source: str
    language: str
    provenance_kind: str
    examples: tuple[Example, ...]
    metadata: dict[str, Any]


def _outside_repository(destination: Path) -> Path:
    destination = destination.resolve()
    repository = Path(__file__).resolve().parents[3]
    if destination == repository or repository in destination.parents:
        raise ValueError("Raw public corpora must stay outside the source repository")
    return destination


def acquire(
    source: str, destination: str | Path, *, max_bytes: int = 128 * 1024**2
) -> dict[str, Any]:
    if source not in SOURCES or max_bytes < 1:
        raise ValueError("Unknown approved public source or invalid size limit")
    root = _outside_repository(Path(destination))
    root.mkdir(parents=True, exist_ok=True)
    specification = SOURCES[source]
    archive = root / (source + ".zip")
    if archive.exists():
        payload = archive.read_bytes()
    else:
        context = _tls_context()
        request = urllib.request.Request(
            specification["archive_url"],
            headers={"User-Agent": "DeidFlow-explicit-public-acquisition"},
        )
        with urllib.request.urlopen(request, timeout=90, context=context) as response:
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("Public archive exceeds size limit")
    if (
        len(payload) > max_bytes
        or hashlib.sha256(payload).hexdigest() != specification["archive_sha256"]
    ):
        raise ValueError("Pinned public archive integrity mismatch")
    if not archive.exists():
        archive.write_bytes(payload)
    target = root / source
    target.mkdir(exist_ok=True)
    files = 0
    decoded_size = 0
    digests: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        for info in bundle.infolist():
            path = PurePosixPath(info.filename)
            if (
                info.flag_bits & 1
                or ".." in path.parts
                or path.is_absolute()
                or info.file_size > max_bytes
            ):
                raise ValueError("Unsafe public archive")
            name = path.name
            output: Path | None = None
            parts = path.parts
            if (
                source == "meddocan"
                and "corpus" in parts
                and "brat" in parts
                and path.suffix in {".txt", ".ann"}
            ):
                split = parts[parts.index("corpus") + 1]
                if split not in {"train", "dev", "test"}:
                    raise ValueError("Unknown public corpus split")
                output = target / split / name
            elif source == "tab" and name in {"echr_train.json", "echr_dev.json", "echr_test.json"}:
                output = target / name
            elif len(parts) == 2 and name in {
                "README.md",
                "LICENSE",
                "LICENSE.txt",
                "guidelines.md",
            }:
                output = target / name
            if output is None:
                continue
            decoded_size += info.file_size
            if decoded_size > max_bytes * 4 or files > 5000:
                raise ValueError("Expanded public corpus exceeds limit")
            content = bundle.read(info)
            relative = output.relative_to(root).as_posix()
            digest = hashlib.sha256(content).hexdigest()
            if relative in digests:
                raise ValueError("Duplicate public archive target")
            digests[relative] = digest
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists() and hashlib.sha256(output.read_bytes()).hexdigest() != digest:
                raise ValueError("Existing public corpus file differs from pinned source")
            if not output.exists():
                output.write_bytes(content)
            files += 1
    manifest = {
        "schema_version": 1,
        "source": source,
        **specification,
        "downloaded_bytes": len(payload),
        "extracted_files": files,
        "extracted_bytes": decoded_size,
        "file_digest_manifest_sha256": hashlib.sha256(
            json.dumps(digests, sort_keys=True).encode()
        ).hexdigest(),
        "raw_documents_committed": False,
        "changes": "No source text edits; source annotation labels mapped only at evaluation time",
    }
    (root / (source + "-provenance.json")).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _tls_context() -> ssl.SSLContext:
    """Honor an explicitly configured CA bundle (corporate proxies) before certifi."""
    for variable in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        cafile = os.environ.get(variable)
        if cafile and Path(cafile).is_file():
            return ssl.create_default_context(cafile=cafile)
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def file_digest_manifest(root: str | Path) -> dict[str, str]:
    """Per-file SHA256 digests keyed exactly as ``acquire()`` records them."""
    root = Path(root)
    digests = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and (
            path.suffix in {".txt", ".ann"}
            or path.name in {"README.md", "LICENSE", "LICENSE.txt", "guidelines.md"}
            or path.name in {"echr_train.json", "echr_dev.json", "echr_test.json"}
        ):
            digests[path.relative_to(root.parent).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


def acquire_from_checkout(
    source: str, checkout: str | Path, destination: str | Path
) -> dict[str, Any]:
    """Build the corpus from a git checkout at the pinned commit.

    GitHub regenerates codeload ZIPs, so archive bytes are not reproducible. The
    per-file digest manifest pinned at acquisition time is: every extracted file
    must match it exactly.
    """
    if source not in SOURCES:
        raise ValueError("Unknown approved public source")
    specification = SOURCES[source]
    checkout = Path(checkout)
    git = shutil.which("git")
    if git is None:
        raise ValueError("git is required to verify the checkout commit")
    head = subprocess.run(
        [git, "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    ).stdout.strip()
    if head != specification["commit"]:
        raise ValueError("Checkout is not at the pinned public commit")
    root = _outside_repository(Path(destination))
    target = root / source
    if target.exists():
        raise ValueError("Destination corpus directory already exists")
    copies: list[tuple[Path, Path]] = []
    if source == "meddocan":
        for split in ("train", "dev", "test"):
            for path in sorted((checkout / "corpus" / split).rglob("*")):
                if path.suffix in {".txt", ".ann"} and "brat" in path.parts:
                    copies.append((path, target / split / path.name))
    else:
        for path in sorted(checkout.rglob("echr_*.json")):
            if path.name in {"echr_train.json", "echr_dev.json", "echr_test.json"}:
                copies.append((path, target / path.name))
    for name in ("README.md", "LICENSE", "LICENSE.txt", "guidelines.md"):
        if (checkout / name).is_file():
            copies.append((checkout / name, target / name))
    if len({destination for _, destination in copies}) != len(copies):
        raise ValueError("Duplicate public corpus target")
    for origin, copy in copies:
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(origin.read_bytes())
    digests = file_digest_manifest(target)
    actual = hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()
    if actual != specification["file_digest_manifest_sha256"]:
        shutil.rmtree(target)
        raise ValueError("Checkout files differ from the pinned per-file digest manifest")
    manifest = {
        "schema_version": 1,
        "source": source,
        **specification,
        "method": "git_checkout_at_pinned_commit",
        "extracted_files": len(digests),
        "file_digest_manifest_sha256": actual,
        "raw_documents_committed": False,
    }
    (root / (source + "-provenance.json")).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def verify_acquired_corpus(root: str | Path, source: str) -> dict[str, Any]:
    """Read-only check that benchmark inputs are exactly the pinned corpus.

    Uses the pinned archive when present, otherwise the pinned per-file digest
    manifest (checkout-based acquisition).
    """
    if source not in SOURCES:
        raise ValueError("Unknown approved public source")
    root = _outside_repository(Path(root))
    archive = root.parent / (source + ".zip")
    if not archive.is_file():
        manifest = file_digest_manifest(root)
        pinned = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        if pinned != SOURCES[source].get("file_digest_manifest_sha256"):
            raise ValueError("Public corpus differs from the pinned per-file digest manifest")
        return {
            "file_digest_manifest_sha256": pinned,
            "verified_corpus_files": len(manifest),
            "method": "Read-only per-file digests equal to the pinned acquisition manifest",
        }
    payload = archive.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SOURCES[source]["archive_sha256"]:
        raise ValueError("Pinned public archive integrity mismatch")
    digests: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        for info in bundle.infolist():
            path = PurePosixPath(info.filename)
            relative = None
            if (
                source == "meddocan"
                and "corpus" in path.parts
                and "brat" in path.parts
                and path.suffix in {".txt", ".ann"}
            ):
                split = path.parts[path.parts.index("corpus") + 1]
                if split not in {"train", "dev", "test"}:
                    raise ValueError("Unknown public corpus split")
                relative = Path(split) / path.name
            elif source == "tab" and path.name in {
                "echr_train.json",
                "echr_dev.json",
                "echr_test.json",
            }:
                relative = Path(path.name)
            if relative is None:
                continue
            key = relative.as_posix()
            if key in digests:
                raise ValueError("Duplicate public archive target")
            digest = hashlib.sha256(bundle.read(info)).hexdigest()
            target = root / relative
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("Extracted public corpus differs from pinned archive")
            digests[key] = digest
    actual = (
        {
            p.relative_to(root).as_posix()
            for split in ("train", "dev", "test")
            for p in (root / split).iterdir()
            if p.is_file() and p.suffix in {".txt", ".ann"}
        }
        if source == "meddocan"
        else {p.name for p in root.glob("echr_*.json")}
    )
    if not digests or actual != set(digests):
        raise ValueError("Unexpected or missing public corpus files")
    return {
        "archive_sha256": SOURCES[source]["archive_sha256"],
        "verified_corpus_files": len(digests),
        "corpus_file_digest_sha256": hashlib.sha256(
            json.dumps(digests, sort_keys=True).encode()
        ).hexdigest(),
        "method": "Read-only byte equality with the SHA256-pinned source archive; no source files modified",
    }


def load_meddocan(root: str | Path, split: str = "test") -> PublicCorpus:
    if split not in {"train", "dev", "test"}:
        raise ValueError("Unknown public corpus split")
    root = Path(root)
    examples = []
    source_counts: Counter[str] = Counter()
    for text_path in sorted((root / split).glob("*.txt")):
        text = text_path.read_bytes().decode("utf-8")
        spans = []
        for line in text_path.with_suffix(".ann").read_text(encoding="utf-8").splitlines():
            if not line.startswith("T"):
                continue
            try:
                _, description, annotated = line.split("\t", 2)
                label, coordinates = description.split(" ", 1)
                if label not in MEDDOCAN_LABELS or ";" in coordinates:
                    raise ValueError
                start, end = map(int, coordinates.split())
                if not 0 <= start < end <= len(text) or text[start:end] != annotated:
                    raise ValueError
            except (ValueError, KeyError):
                raise ValueError("Invalid public BRAT annotation or unknown label") from None
            source_counts[label] += 1
            spans.append(GoldSpan(MEDDOCAN_LABELS[label], start, end))
        examples.append(
            Example(
                text_path.stem,
                text,
                tuple(spans),
                split,
                "official-meddocan-" + split,
                challenge="public_clinical",
            )
        )
    if not examples:
        raise ValueError("No public BRAT documents found")
    return PublicCorpus(
        "meddocan",
        "es",
        "semi_synthetic_clinical",
        tuple(examples),
        {
            "official_split": split,
            "original_labels": dict(source_counts),
            "gold_span_count": sum(len(e.spans) for e in examples),
            "text_bytes": sum(len(e.text.encode()) for e in examples),
            "gold_verified_against_text": True,
        },
    )


def load_tab(root: str | Path, split: str = "test") -> PublicCorpus:
    if split not in {"train", "dev", "test"}:
        raise ValueError("Unknown public corpus split")
    path = Path(root) / f"echr_{split}.json"
    documents = json.loads(path.read_text(encoding="utf-8"))
    examples = []
    annotators: Counter[str] = Counter()
    ignored_no_mask = 0
    for document in documents:
        eligible = sorted(set(document.get("quality_checked", [])) & set(document["annotations"]))
        if not eligible:
            raise ValueError("TAB document has no reviewed annotator")
        selected = eligible[0]
        annotators[selected] += 1
        text = document["text"]
        spans = set()
        for mention in document["annotations"][selected]["entity_mentions"]:
            if mention["identifier_type"] == "NO_MASK":
                ignored_no_mask += 1
                continue
            if (
                mention["identifier_type"] not in {"DIRECT", "QUASI"}
                or mention["entity_type"] not in TAB_LABELS
            ):
                raise ValueError("Unknown TAB gold category")
            start, end = mention["start_offset"], mention["end_offset"]
            if not 0 <= start < end <= len(text) or text[start:end] != mention["span_text"]:
                raise ValueError("TAB gold offset mismatch")
            spans.add(GoldSpan(TAB_LABELS[mention["entity_type"]], start, end))
        examples.append(
            Example(
                str(document["doc_id"]),
                text,
                tuple(sorted(spans, key=lambda s: (s.start, s.end, s.entity_type))),
                split,
                "official-tab-" + split,
                challenge="public_judicial",
            )
        )
    return PublicCorpus(
        "tab",
        "en",
        "public_judicial",
        tuple(examples),
        {
            "official_split": split,
            "annotator_selection": "lexicographically first quality_checked annotator; no union of divergent gold",
            "selected_annotator_counts": dict(annotators),
            "ignored_no_mask_mentions": ignored_no_mask,
            "gold_span_count": sum(len(e.spans) for e in examples),
            "text_bytes": sum(len(e.text.encode()) for e in examples),
            "gold_verified_against_text": True,
        },
    )


MEDDOCAN_ROLES = {
    "NOMBRE_SUJETO_ASISTENCIA": "patient",
    "NOMBRE_PERSONAL_SANITARIO": "clinician",
    "FAMILIARES_SUJETO_ASISTENCIA": "family",
}


def load_meddocan_roles(root: str | Path, split: str = "test") -> list[list[tuple[int, int, str]]]:
    """Person-role gold spans per document, aligned with ``load_meddocan`` order."""
    if split not in {"train", "dev", "test"}:
        raise ValueError("Unknown public corpus split")
    documents = []
    for text_path in sorted((Path(root) / split).glob("*.txt")):
        spans = []
        for line in text_path.with_suffix(".ann").read_text(encoding="utf-8").splitlines():
            if not line.startswith("T"):
                continue
            label, coordinates = line.split("\t", 2)[1].split(" ", 1)
            if label in MEDDOCAN_ROLES and ";" not in coordinates:
                start, end = map(int, coordinates.split())
                spans.append((start, end, MEDDOCAN_ROLES[label]))
        documents.append(spans)
    return documents


def load_public(root: str | Path, source: str, split: str = "test") -> PublicCorpus:
    if source == "meddocan":
        return load_meddocan(root, split)
    if source == "tab":
        return load_tab(root, split)
    raise ValueError("Unknown approved public source")


def split_integrity(root: str | Path, source: str) -> dict[str, Any]:
    """Report overlap without exporting document IDs or entity values.

    Exact equality is not a semantic near-duplicate detector. These diagnostics
    describe the published split; no inferred identity groups are asserted.
    """
    splits = ("train", "dev", "test") if source == "meddocan" else ("dev", "test")
    corpora = {split: load_public(root, source, split) for split in splits}
    documents = {
        split: {hashlib.sha256(e.text.encode()).hexdigest() for e in corpus.examples}
        for split, corpus in corpora.items()
    }
    entities = {
        split: {
            hashlib.sha256(
                (s.entity_type + "\0" + e.text[s.start : s.end].casefold()).encode()
            ).hexdigest()
            for e in corpus.examples
            for s in e.spans
        }
        for split, corpus in corpora.items()
    }
    pairs = {}
    comparisons = (
        (("train", "dev"), ("train", "test"), ("dev", "test"))
        if source == "meddocan"
        else (("dev", "test"),)
    )
    for left, right in comparisons:
        item = {
            "identical_document_texts": len(documents[left] & documents[right]),
            "shared_category_value_hashes": len(entities[left] & entities[right]),
        }
        if source == "meddocan":

            def groups(split: str) -> set[str]:
                return {e.id.rsplit("-", 1)[0] for e in corpora[split].examples}

            item["shared_source_article_identifiers"] = len(groups(left) & groups(right))
        pairs[left + "_vs_" + right] = item
    return {
        "method": "Published official splits; exact text/category-value hashes and MEDDOCAN source article ID stems",
        "pairs": pairs,
        "guarantees": "Does not certify unseen identities, unseen templates, or absence of semantic near-duplicates",
        "training_overlap": "measured"
        if source == "meddocan"
        else "not measured: TAB training includes annotations without quality_checked review; no unreviewed training gold was silently substituted",
    }
