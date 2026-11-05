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
        "license": "CC-BY-4.0",
        "license_url": "https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN/blob/783a6df385c975b328c99bcffb54196a9ba4078a/LICENSE",
        "language": "es",
        "format": "UTF-8 text + BRAT standoff",
        "gold": True,
        "provenance_kind": "semi_synthetic_clinical",
        "already_anonymized": "Released synthetic/enriched PHI, not original private patient records",
        "attribution": "SPACCC MEDDOCAN; 2019 Secretaria de Estado para el Avance Digital (SEAD)",
        "file_digest_manifest_sha256": "ba4823b70e231902fe7d865c1193607631eb0a2d1f30c8591a6fc523388d4cdc",
    },
    "tab": {
        "repository": "https://github.com/NorskRegnesentral/text-anonymization-benchmark",
        "commit": "558e09e26d6b36f5f78440074e6a233946d98bd9",
        "archive_url": "https://codeload.github.com/NorskRegnesentral/text-anonymization-benchmark/zip/558e09e26d6b36f5f78440074e6a233946d98bd9",
        "archive_sha256": "fc9925949e91b0eaf831fa8df0ad19ddc325d48e3aeae1e947d15872ba3eaa22",
        "license": "MIT",
        "license_url": "https://github.com/NorskRegnesentral/text-anonymization-benchmark/blob/558e09e26d6b36f5f78440074e6a233946d98bd9/LICENSE.txt",
        "language": "en",
        "format": "JSON text + human entity/masking annotations",
        "gold": True,
        "provenance_kind": "public_judicial",
        "already_anonymized": "Public ECHR judgments; masking decisions identify DIRECT/QUASI mentions",
        "attribution": "TAB; Copyright 2021-2026 Norsk Regnesentral; Pilan et al. 2022",
        "file_digest_manifest_sha256": "cc6e2eac8ac649c0ea7f8b7c940af19e00af38e69fe50f2fa1c646f9de24f613",
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
        try:
            import certifi

            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
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
    if _digest_manifest(digests) != specification["file_digest_manifest_sha256"]:
        raise ValueError("Extracted public corpus differs from the pinned digest manifest")
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


def _digest_manifest(digests: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()


def _member_target(source: str, parts: tuple[str, ...]) -> PurePosixPath | None:
    """Map a repository-relative member to its extraction path, or ``None`` to skip it."""
    if not parts:
        return None
    path = PurePosixPath(*parts)
    if (
        source == "meddocan"
        and "corpus" in parts
        and "brat" in parts
        and path.suffix in {".txt", ".ann"}
    ):
        split = parts[parts.index("corpus") + 1]
        if split not in {"train", "dev", "test"}:
            raise ValueError("Unknown public corpus split")
        return PurePosixPath(source, split, path.name)
    if source == "tab" and path.name in {"echr_train.json", "echr_dev.json", "echr_test.json"}:
        return PurePosixPath(source, path.name)
    if len(parts) == 1 and path.name in {"README.md", "LICENSE", "LICENSE.txt", "guidelines.md"}:
        return PurePosixPath(source, path.name)
    return None


def _git(git: str, *args: str, cwd: Path, timeout: int, stdin: bytes | None = None) -> bytes:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": ""}
    try:
        completed = subprocess.run(
            [git, "-c", "core.autocrlf=false", *args],
            cwd=cwd,
            input=stdin,
            capture_output=True,
            timeout=timeout,
            env=environment,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ValueError("Pinned public git acquisition failed") from None
    return completed.stdout


def _read_git_blobs(git: str, repository: Path, names: list[str], timeout: int) -> dict[str, bytes]:
    """Read committed bytes directly, bypassing working-tree filters and checkouts."""
    request = "".join("FETCH_HEAD:" + name + "\n" for name in names).encode()
    payload = _git(git, "cat-file", "--batch", cwd=repository, timeout=timeout, stdin=request)
    blobs: dict[str, bytes] = {}
    position = 0
    for name in names:
        header_end = payload.index(b"\n", position)
        fields = payload[position:header_end].split()
        if len(fields) != 3 or fields[1] != b"blob":
            raise ValueError("Pinned public git object is missing or not a file")
        size = int(fields[2])
        start = header_end + 1
        blobs[name] = payload[start : start + size]
        position = start + size + 1
    return blobs


def acquire_git(
    source: str,
    destination: str | Path,
    *,
    max_bytes: int = 128 * 1024**2,
    timeout: int = 600,
) -> dict[str, Any]:
    """Acquire a registry corpus by its pinned Git commit instead of the archive URL.

    Useful where the code-archive host is unavailable. Every selected file is read
    from the commit object and the whole selection must reproduce the registry's
    pinned SHA-256 digest manifest before anything is written.
    """
    if source not in SOURCES or max_bytes < 1 or timeout < 1:
        raise ValueError("Unknown approved public source or invalid limits")
    specification = SOURCES[source]
    git = shutil.which("git")
    if git is None:
        raise ValueError("Git is required for pinned git acquisition")
    root = _outside_repository(Path(destination))
    root.mkdir(parents=True, exist_ok=True)
    repository = root / (source + "-git")
    repository.mkdir(exist_ok=True)
    if not (repository / ".git").is_dir():
        _git(git, "init", "-q", cwd=repository, timeout=timeout)
    _git(
        git,
        "fetch",
        "-q",
        "--depth",
        "1",
        specification["repository"],
        specification["commit"],
        cwd=repository,
        timeout=timeout,
    )
    head = _git(git, "rev-parse", "FETCH_HEAD", cwd=repository, timeout=timeout).decode().strip()
    if head != specification["commit"]:
        raise ValueError("Fetched public commit differs from the pinned commit")
    listing = _git(
        git, "ls-tree", "-r", "-z", "--name-only", "FETCH_HEAD", cwd=repository, timeout=timeout
    )
    selected: dict[str, PurePosixPath] = {}
    for name in sorted(filter(None, listing.decode("utf-8").split("\0"))):
        parts = PurePosixPath(name).parts
        if ".." in parts or PurePosixPath(name).is_absolute():
            raise ValueError("Unsafe public repository path")
        target = _member_target(source, parts)
        if target is not None:
            selected[name] = target
    if not selected or len(selected) > 5000:
        raise ValueError("Unexpected public repository layout")
    blobs = _read_git_blobs(git, repository, list(selected), timeout)
    total = sum(len(content) for content in blobs.values())
    if total > max_bytes * 4:
        raise ValueError("Expanded public corpus exceeds limit")
    digests: dict[str, str] = {}
    for name, target in selected.items():
        key = target.as_posix()
        if key in digests:
            raise ValueError("Duplicate public archive target")
        digests[key] = hashlib.sha256(blobs[name]).hexdigest()
    if _digest_manifest(digests) != specification["file_digest_manifest_sha256"]:
        raise ValueError("Pinned public corpus digest manifest mismatch")
    for name, target in selected.items():
        output = root / target
        output.parent.mkdir(parents=True, exist_ok=True)
        if (
            output.exists()
            and hashlib.sha256(output.read_bytes()).hexdigest() != digests[target.as_posix()]
        ):
            raise ValueError("Existing public corpus file differs from pinned source")
        if not output.exists():
            output.write_bytes(blobs[name])
    manifest = {
        "schema_version": 1,
        "source": source,
        **specification,
        "acquisition": "git commit objects; archive URL not used",
        "extracted_files": len(selected),
        "extracted_bytes": total,
        "file_digest_manifest_sha256": _digest_manifest(digests),
        "raw_documents_committed": False,
        "changes": "No source text edits; source annotation labels mapped only at evaluation time",
    }
    (root / (source + "-provenance.json")).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _verify_by_digest_manifest(root: Path, source: str) -> dict[str, Any]:
    """Hash every file a benchmark could read, so extra or edited inputs fail."""
    digests: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        parts = path.relative_to(root).parts
        if len(parts) == 1:
            included = path.name.startswith("echr_") and path.suffix == ".json"
            included = included or _member_target(source, parts) is not None
        else:
            included = (
                source == "meddocan"
                and len(parts) == 2
                and parts[0] in {"train", "dev", "test"}
                and path.suffix in {".txt", ".ann"}
            )
        if included:
            key = PurePosixPath(source, *parts).as_posix()
            digests[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    if _digest_manifest(digests) != SOURCES[source]["file_digest_manifest_sha256"]:
        raise ValueError("Extracted public corpus differs from pinned digest manifest")
    corpus = {
        key.split("/", 1)[1]: value for key, value in digests.items() if _is_corpus_key(source, key)
    }
    return {
        "file_digest_manifest_sha256": SOURCES[source]["file_digest_manifest_sha256"],
        "verified_corpus_files": len(corpus),
        "corpus_file_digest_sha256": _digest_manifest(corpus),
        "method": "Read-only SHA256 per-file digest manifest equal to the registry pin; no source files modified",
    }


def _is_corpus_key(source: str, key: str) -> bool:
    name = key.rsplit("/", 1)[-1]
    if source == "meddocan":
        return key.count("/") == 2 and name.endswith((".txt", ".ann"))
    return name.startswith("echr_") and name.endswith(".json")


def verify_acquired_corpus(root: str | Path, source: str) -> dict[str, Any]:
    """Read-only check that benchmark inputs are exactly the pinned corpus.

    Uses the pinned archive when present, otherwise the pinned digest manifest
    (for example after :func:`acquire_git`).
    """
    if source not in SOURCES:
        raise ValueError("Unknown approved public source")
    root = _outside_repository(Path(root))
    archive = root.parent / (source + ".zip")
    if not archive.is_file():
        return _verify_by_digest_manifest(root, source)
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
