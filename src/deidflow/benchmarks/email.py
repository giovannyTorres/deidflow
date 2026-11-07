"""BMX-01: local, descriptive EMAIL detection; no models or external services."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deidflow import DeidEngine, __version__
from deidflow.detectors import CORE_RULES_VERSION

from .datasets import Example, GoldSpan
from .metrics import evaluate


@dataclass(frozen=True)
class _EmailPackage:
    manifest_sha256: str
    version: str
    corpus_sha256: str
    examples: list[Example]


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError


def _read_member(root: Path, name: str, limit: int) -> bytes:
    path = root / name
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError
    return payload


def _load_package(path: str | Path) -> _EmailPackage:
    try:
        root = Path(path).resolve()
        manifest_bytes = _read_member(root, "manifest.json", 4096)
        manifest = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
        corpus_bytes = _read_member(root, "corpus.jsonl", 1_048_576)
        corpus_digest = hashlib.sha256(corpus_bytes).hexdigest()
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {"schema_version", "dataset_version", "synthetic", "corpus_sha256"}
            or manifest["schema_version"] != "df-eval-mx.email.v1"
            or manifest["synthetic"] is not True
            or manifest["corpus_sha256"] != corpus_digest
            or not isinstance(manifest["dataset_version"], str)
            or re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", manifest["dataset_version"])
            is None
        ):
            raise ValueError
        examples: list[Example] = []
        ids: set[str] = set()
        for line in corpus_bytes.decode("utf-8").removesuffix("\n").split("\n"):
            record = json.loads(
                line, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
            )
            if (
                not isinstance(record, dict)
                or set(record) != {"id", "text", "spans"}
                or not isinstance(record["id"], str)
                or not record["id"]
                or record["id"] in ids
                or not isinstance(record["text"], str)
                or not isinstance(record["spans"], list)
            ):
                raise ValueError
            record["text"].encode("utf-8")
            spans: list[GoldSpan] = []
            for span in record["spans"]:
                if (
                    not isinstance(span, dict)
                    or set(span) != {"entity_type", "start", "end"}
                    or span["entity_type"] != "EMAIL"
                    or type(span["start"]) is not int
                    or type(span["end"]) is not int
                    or not 0 <= span["start"] < span["end"] <= len(record["text"])
                ):
                    raise ValueError
                spans.append(GoldSpan(**span))
            if len(set(spans)) != len(spans):
                raise ValueError
            examples.append(
                Example(
                    record["id"], record["text"], tuple(spans), "known_regression", "email-smoke"
                )
            )
            ids.add(record["id"])
        if not examples:
            raise ValueError
        return _EmailPackage(
            hashlib.sha256(manifest_bytes).hexdigest(),
            manifest["dataset_version"],
            corpus_digest,
            examples,
        )
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        raise ValueError("Invalid email benchmark package") from None


def _source_digest() -> str:
    try:
        root = Path(__file__).resolve().parents[1]
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*.py")):
            name = path.relative_to(root).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(name).to_bytes(8, "big") + name)
            digest.update(len(content).to_bytes(8, "big") + content)
        return digest.hexdigest()
    except OSError:
        raise RuntimeError("Cannot fingerprint email benchmark candidate") from None


def _write_report(destination: Path, report: dict[str, Any]) -> None:
    payload = (
        json.dumps(report, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    )
    try:
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        # Windows reports a file in a parent position as an existing path too.
        if os.path.lexists(destination):  # a dangling link is an existing entry
            raise FileExistsError(
                "Benchmark output already exists; choose a new directory"
            ) from None
        raise OSError("Cannot write email benchmark report") from None
    except (OSError, ValueError):
        raise OSError("Cannot write email benchmark report") from None
    report_path = destination / "report.json"
    created_report = False
    try:
        with report_path.open("x", encoding="utf-8") as stream:
            created_report = True
            stream.write(payload)
    except (OSError, ValueError):
        if created_report:
            with suppress(OSError):
                report_path.unlink()
        with suppress(OSError):
            destination.rmdir()
        raise OSError("Cannot write email benchmark report") from None


def run_email_benchmark(
    package: str | Path, *, candidate: str, profile: str, output: str | Path
) -> dict[str, Any]:
    """Evaluate a versioned fictional package and create a new report directory.

    This initial slice supports only ``rules.mx`` and ``email-descriptive-v1``.
    It neither evaluates transformation nor qualifies a deployment or dataset's
    independence. The deterministic ``result`` is separate from ``operational``.
    """
    if candidate != "rules.mx" or profile != "email-descriptive-v1":
        raise ValueError("Unsupported email benchmark candidate or profile")
    destination = Path(output)
    started = datetime.now(UTC).isoformat()
    before = time.perf_counter()
    loaded = _load_package(package)
    examples = loaded.examples
    engine = DeidEngine(language="es", country="MX", performance="balanced", offline=True)
    predictions = [
        [finding for finding in engine.scan_text(example.text) if finding.entity_type == "EMAIL"]
        for example in examples
    ]
    metrics = evaluate(examples, predictions)
    tp, fp, fn = metrics.true_positives, metrics.false_positives, metrics.false_negatives
    positives = sum(bool(example.spans) for example in examples)
    report = {
        "schema_version": "df-eval-mx.email-report.v1",
        "result": {
            "candidate": {
                "id": candidate,
                "deidflow_version": __version__,
                "rules_version": CORE_RULES_VERSION,
                "source_sha256": _source_digest(),
                "nlp": None,
                "offline": True,
                "performance": "balanced",
            },
            "dataset": {
                "id": "sha256:" + loaded.manifest_sha256,
                "version": loaded.version,
                "corpus_sha256": loaded.corpus_sha256,
                "panel": "known_regression",
                "synthetic": True,
            },
            "profile": {"id": profile, "ratified": False},
            "scope": {
                "track": "detection",
                "entity_types": ["EMAIL"],
                "source_format": "text",
                "language": "es",
                "country": "MX",
                "matching": "exact",
            },
            "documents": {
                "total": len(examples),
                "positive": positives,
                "negative": len(examples) - positives,
            },
            "metrics": {
                "EMAIL": {
                    "true_positives": tp,
                    "false_positives": fp,
                    "false_negatives": fn,
                    "support": tp + fn,
                    "precision": tp / (tp + fp) if tp + fp else None,
                    "recall": tp / (tp + fn) if tp + fn else None,
                    "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                }
            },
            "quality": "DESCRIPTIVE_ONLY",
            "limitations": [
                "EMAIL_ONLY_KNOWN_SYNTHETIC_REGRESSION",
                "TRANSFORMATION_NOT_EVALUATED",
                "DATASET_INDEPENDENCE_NOT_EVALUATED",
                "PROCESS_NETWORK_ISOLATION_NOT_EVALUATED",
            ],
        },
        "operational": {
            "started_at": started,
            "elapsed_seconds": time.perf_counter() - before,
            "python_version": platform.python_version(),
        },
    }
    _write_report(destination, report)
    return report
