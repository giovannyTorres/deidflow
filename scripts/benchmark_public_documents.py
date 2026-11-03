"""Acquire allowlisted government PDFs and measure local, unannotated operation.

Only aggregate counts, source provenance, hashes and fixed diagnostic codes leave
the private local work directory. This is not detection-quality evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import ssl
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

REPOSITORY = Path(__file__).resolve().parents[1]
WORKSPACE = REPOSITORY.parents[1]
ALLOWED_HOSTS = {"www2.scjn.gob.mx", "www.scjn.gob.mx", "bicentenario.scjn.gob.mx", "www.gob.mx"}
MAX_BYTES = 32 * 1024**2
SOURCE_URLS = {
    "scjn-ar118-2025": "https://www2.scjn.gob.mx/juridica/Engroses/Cerrados/Publico/Proyecto/AR118_2025.pdf",
    "scjn-ct-vt-j2-2025": "https://www.scjn.gob.mx/sites/default/files/resoluciones/2025-07/CT-VT-J-2-2025.pdf",
    "gob-solicitud-2024": "https://www.gob.mx/cms/uploads/attachment/file/902077/Formato_de_solicitud_2024.pdf",
}


def valid_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
    except ValueError:
        return False


class GovernmentRedirects(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not valid_url(newurl):
            raise URLError("UNAPPROVED_REDIRECT")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def acquire(source: dict[str, Any], directory: Path, *, opener=None) -> dict[str, Any]:
    """Return fixed diagnostics; partial downloads are removed on every failure."""
    if SOURCE_URLS.get(source["id"]) != source["url"] or not valid_url(source["url"]):
        raise ValueError("Source is outside the government registry")
    if opener is None:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
        opener = build_opener(HTTPSHandler(context=context), GovernmentRedirects())
    target = directory / (source["id"] + ".source.pdf")
    partial = directory / (source["id"] + ".partial")
    result = {
        "source_id": source["id"],
        "source_url": source["url"],
        "gold_annotations": False,
        "license_status": source["license_status"],
        "raw_redistribution": False,
        "tls_verification": True,
    }
    created_partial = False
    status = None
    received = 0
    failure_reason = "VERIFIED_DOWNLOAD_FAILED"
    try:
        request = Request(source["url"], headers={"User-Agent": "DeidFlow-local-research/0.3"})
        with opener.open(request, timeout=45) as response:
            status = response.status
            if not valid_url(response.geturl()):
                failure_reason = "UNAPPROVED_REDIRECT"
                raise ValueError("Redirect outside allowed government hosts")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_BYTES:
                failure_reason = "DOWNLOAD_BYTE_LIMIT_EXCEEDED"
                raise ValueError("Download exceeds limit")
            with partial.open("xb") as handle:
                created_partial = True
                while chunk := response.read(min(1024**2, MAX_BYTES - received + 1)):
                    received += len(chunk)
                    if received > MAX_BYTES:
                        failure_reason = "DOWNLOAD_BYTE_LIMIT_EXCEEDED"
                        raise ValueError("Download exceeds limit")
                    handle.write(chunk)
            with partial.open("rb") as handle:
                if not handle.read(1024).lstrip().startswith(b"%PDF-"):
                    failure_reason = "HTTP_RESPONSE_NOT_PDF"
                    raise ValueError("Response is not PDF")
            # Newly allocated run directory; do not replace any existing output.
            if target.exists():
                raise ValueError("Existing download target")
            os.link(partial, target)
            partial.unlink()
            return {
                **result,
                "acquisition_status": "available",
                "http_status": response.status,
                "bytes": received,
                "sha256": digest(target),
            }
    except HTTPError as error:
        error.close()
        return {
            **result,
            "acquisition_status": "unavailable",
            "http_status": error.code,
            "reason": "HTTP_ACCESS_FAILED",
        }
    except Exception:
        return {
            **result,
            "acquisition_status": "unavailable",
            "http_status": status,
            "bytes_received": received,
            "reason": failure_reason,
        }
    finally:
        if created_partial:
            partial.unlink(missing_ok=True)


def worker(job: dict[str, Any]) -> dict[str, Any]:
    from pypdf import PdfReader, PdfWriter

    import deidflow.engine as owner
    from deidflow import DeidEngine, Policy
    from deidflow.benchmarks.runner import machine_metadata, measure
    from deidflow.ocr import TesseractOCR

    if not Path(owner.__file__).resolve().is_relative_to(REPOSITORY / "src"):
        raise RuntimeError("Current source checkout was not imported")
    original = Path(job["input"])
    directory = original.parent
    reader = PdfReader(original)
    total_pages = len(reader.pages)
    if not 1 <= total_pages <= 1000:
        raise ValueError("Public document page limit exceeded")
    selected_pages = min(job["max_pages"], total_pages)
    native_chars = sum(len(page.extract_text() or "") for page in reader.pages)
    subset = directory / (job["source_id"] + ".prefix.pdf")
    writer = PdfWriter()
    for page in list(reader.pages)[:selected_pages]:
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata({str(k): str(v) for k, v in reader.metadata.items() if v is not None})
    with subset.open("xb") as handle:
        writer.write(handle)

    class CountingOCR(TesseractOCR):
        # No recognized string is ever returned to the coordinator or report.
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = self.tokens = self.low_confidence_tokens = 0
            self.elapsed = 0.0

        def recognize(self, image):
            start = time.perf_counter()
            result = super().recognize(image)
            self.elapsed += time.perf_counter() - start
            self.calls += 1
            self.tokens += len(result.tokens)
            self.low_confidence_tokens += sum(
                t.confidence < self.min_confidence for t in result.tokens
            )
            return result

    ocr = CountingOCR(
        executable=str(WORKSPACE / "work/tesseract-5.5.4/bin/tesseract.exe"),
        tessdata_dir=WORKSPACE / "work/tesseract-5.5.4/share/tessdata",
        language="spa+eng",
        psm=6,
    )
    engine = DeidEngine(ocr=ocr)

    def scan():
        graph = engine.read(subset)
        findings = Counter()
        for fragment in graph.fragments:
            items = (
                engine.scan_ocr_text(fragment.text)
                if fragment.kind == "ocr"
                else engine.scan_text(fragment.text)
            )
            findings.update(f.entity_type for f in items)
        return {
            "extraction_complete": graph.complete,
            "issues": graph.issues,
            "fragments": len(graph.fragments),
            "fragments_by_kind": dict(Counter(f.kind for f in graph.fragments)),
            "extracted_characters": sum(len(f.text) for f in graph.fragments),
            "findings_by_type": dict(sorted(findings.items())),
            "findings": sum(findings.values()),
        }

    scan_measurement, scan_result = measure(
        scan, units=selected_pages, size_bytes=subset.stat().st_size
    )
    scan_ocr = {
        "calls": ocr.calls,
        "tokens": ocr.tokens,
        "low_confidence_tokens": ocr.low_confidence_tokens,
        "elapsed_seconds": ocr.elapsed,
    }
    output = directory / (job["source_id"] + ".safe.pdf")
    transform_measurement, result = measure(
        lambda: engine.deidentify(subset, output=output, policy=Policy.strict_pdf()),
        units=selected_pages,
        size_bytes=subset.stat().st_size,
    )
    return {
        "implementation": "candidate_v0.3",
        "machine": machine_metadata(),
        "source_engine_sha256": digest(Path(owner.__file__)),
        "original_pages": total_pages,
        "original_native_extraction_characters": native_chars,
        "processed_pages": selected_pages,
        "page_numbers_1_based": list(range(1, selected_pages + 1)),
        "coverage": "first_pages_subset"
        if selected_pages < total_pages
        else "all_page_content_in_derived_container",
        "source_container_features_not_retained": True,
        "coverage_note": "Operational scan and transform use an explicit first-page derived container. Page objects and string PDF-info metadata are copied; full original document/container safety is not assessed.",
        "scan": {**scan_result, "measurement": scan_measurement, "ocr": scan_ocr},
        "transform": {
            "status": str(result.status),
            "release_approved": result.release_approved,
            "issues": result.issues,
            "output_exists": output.exists(),
            "output_sha256": digest(output) if output.exists() else None,
            "measurement": transform_measurement,
            "ocr": {
                "calls": ocr.calls - scan_ocr["calls"],
                "tokens": ocr.tokens - scan_ocr["tokens"],
                "low_confidence_tokens": ocr.low_confidence_tokens
                - scan_ocr["low_confidence_tokens"],
                "elapsed_seconds": ocr.elapsed - scan_ocr["elapsed_seconds"],
            },
        },
        "scope": "Rules-only local operational run; required statistical NER is absent and cannot be bypassed. Unannotated public data support no precision, recall, F1, OCR error rate or complete anonymity claim. OCR confidence is an engine score, not an error-rate estimate.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-job", type=Path)
    parser.add_argument(
        "--registry", type=Path, default=REPOSITORY / "docs/public-document-sources.json"
    )
    parser.add_argument("--work", type=Path, default=WORKSPACE / "work/public-documents")
    parser.add_argument(
        "--output", type=Path, default=REPOSITORY / "benchmarks/results/v030/public-documents.json"
    )
    parser.add_argument("--max-pages", type=int, default=3)
    args = parser.parse_args()
    if args.worker_job:
        try:
            from deidflow.benchmarks.runner import offline_network

            with offline_network() as network:
                result = worker(json.loads(args.worker_job.read_text(encoding="utf-8")))
            result["inference_network_attempts"] = network["attempts"]
            print(json.dumps(result))
            return 0
        except Exception:
            print(json.dumps({"operational_status": "failed", "reason": "LOCAL_PIPELINE_FAILED"}))
            return 1
    if not 1 <= args.max_pages <= 100:
        parser.error("A bounded positive page limit is required")
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    # Registry entries may add metadata, but may not add arbitrary acquisition URLs.
    if any(SOURCE_URLS.get(s["id"]) != s["url"] for s in registry["sources"]):
        parser.error("Only explicitly approved source URLs may be acquired")
    args.work = args.work.resolve()
    if not args.work.is_relative_to(WORKSPACE / "work/public-documents"):
        parser.error("Raw documents must stay in the local public-documents work directory")
    directory = args.work / ("run-" + secrets.token_hex(6))
    directory.mkdir(parents=True)
    report = {
        "schema_version": 1,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "gold_annotations": False,
        "quality_metrics": None,
        "raw_redistribution": False,
        "scope": registry["scope"],
        "max_pages_per_source": args.max_pages,
        "source_registry": "docs/public-document-sources.json",
        "background_load": "Concurrent local synthetic/PDF development benchmarks may affect wall time; one run, no speedup claim.",
        "sources": [],
    }
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for source in registry["sources"]:
        entry = acquire(source, directory)
        if entry["acquisition_status"] == "available":
            config = directory / (source["id"] + ".job.json")
            config.write_text(
                json.dumps(
                    {
                        "source_id": source["id"],
                        "input": str(directory / (source["id"] + ".source.pdf")),
                        "max_pages": args.max_pages,
                    }
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPOSITORY / "src")
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker-job", str(config)],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            try:
                operational = json.loads(process.stdout)
            except (ValueError, TypeError):
                operational = {"operational_status": "failed", "reason": "LOCAL_PIPELINE_FAILED"}
            entry["operational"] = operational
        report["sources"].append(entry)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "source_id": source["id"],
                    "acquisition_status": entry["acquisition_status"],
                    "http_status": entry.get("http_status"),
                    "pipeline_status": entry.get("operational", {})
                    .get("transform", {})
                    .get("status"),
                }
            ),
            flush=True,
        )
    report["completed"] = True
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
