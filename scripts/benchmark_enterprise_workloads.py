"""Fresh-process v0.2/current synthetic CSV and Spanish text measurements.

Raw generated data stay in a newly allocated local work directory. Results are
numeric aggregates/hashes, not source records. This never accesses Gmail.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def fixtures() -> Any:
    path = Path(__file__).with_name("benchmark_workloads.py")
    spec = importlib.util.spec_from_file_location("_enterprise_synthetic_fixtures", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Synthetic fixture loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def source_tree_digest(root: Path) -> str:
    """Bind results to all Python implementation modules, not only engine.py."""
    hashed = hashlib.sha256()
    for path in sorted((root / "src/deidflow").rglob("*.py")):
        hashed.update(path.relative_to(root / "src").as_posix().encode() + b"\0")
        hashed.update(bytes.fromhex(digest(path)))
    return hashed.hexdigest()


def snapshot_source(root: Path, directory: Path) -> Path:
    """Copy code into a new run directory and verify a consistent snapshot."""
    before = source_tree_digest(root)
    target = directory / "source-candidate"
    (target / "src").mkdir(parents=True)
    shutil.copytree(
        root / "src/deidflow",
        target / "src/deidflow",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    if before != source_tree_digest(root) or before != source_tree_digest(target):
        raise RuntimeError("Implementation changed while the benchmark snapshot was copied")
    return target


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def long_spanish_text(sections: int = 100, seed: int = 1729) -> tuple[str, list[tuple[int, int]]]:
    if sections < 1:
        raise ValueError("Positive section count required")
    paragraph = "La gestión documental requiere preservar las relaciones útiles y revisar los resultados con cuidado. Este párrafo sintético describe procesos administrativos sin identificar a ninguna persona. "
    parts: list[str] = []
    gold = []
    offset = 0
    for index in range(sections):
        part = paragraph * 60 + "\nCorreo: "
        parts.append(part)
        offset += len(part)
        value = f"evaluacion.{seed}.{index:06d}@example.org"
        gold.append((offset, offset + len(value)))
        parts.append(value + "\n\n")
        offset += len(value) + 2
    return "".join(parts), gold


def text_batch(records: int, seed: int = 1729):
    for index in range(records):
        yield f"Registro administrativo sintético. Correo: evaluacion.{seed}.{index:06d}@example.org. Importe autorizado: 42 pesos."


def signature(findings: Any) -> bytes:
    return (
        json.dumps([(f.entity_type, f.start, f.end) for f in findings], separators=(",", ":"))
        + "\n"
    ).encode()


def worker(job: dict[str, Any]) -> dict[str, Any]:
    import deidflow.engine as owner
    from deidflow import DeidEngine, Policy
    from deidflow.benchmarks.runner import machine_metadata, measure

    source = Path(job["source_root"]).resolve()
    owning_path = Path(owner.__file__).resolve()
    if not owning_path.is_relative_to(source / "src"):
        raise RuntimeError("Requested baseline implementation was not imported")
    code_before = digest(owning_path)
    tree_before = source_tree_digest(source)
    common = {
        "implementation": job["implementation"],
        "source_engine_sha256": code_before,
        "source_tree_sha256": tree_before,
        "machine": machine_metadata(),
        "seed": job["seed"],
    }
    if job["kind"] == "csv":
        fixture = fixtures()
        path, output = Path(job["input"]), Path(job["output"])
        engine = DeidEngine(max_bytes=max(64 * 1024**2, path.stat().st_size + 1))
        latencies = []
        original = engine._rows

        def rows(*args, **kwargs):
            start = time.perf_counter()
            result = original(*args, **kwargs)
            latencies.append(time.perf_counter() - start)
            return result

        engine._rows = rows
        measurements, result = measure(
            lambda: engine.deidentify(
                path,
                output=output,
                policy=Policy.strict(require_ner=False),
                batch_size=job["batch_size"],
            ),
            units=job["rows"],
            size_bytes=path.stat().st_size,
        )
        truth = fixture._verify_csv(output, job["rows"]) if output.exists() else {"passed": False}
        output_digest = digest(output) if output.exists() else None
        return {
            **common,
            "workload": "synthetic_csv",
            "rows": job["rows"],
            "columns": 5,
            "batch_size": job["batch_size"],
            "input_bytes": path.stat().st_size,
            "input_sha256": digest(path),
            "output_sha256": output_digest,
            "status": str(result.status),
            "issues": result.issues,
            "measurement": measurements,
            "independent_ground_truth": truth,
            "column_processing_seconds": sum(latencies),
            "column_batch_latency_p50_seconds": percentile(latencies, 0.5),
            "column_batch_latency_p95_seconds": percentile(latencies, 0.95),
            "column_batches": len(latencies),
            "whole_request_latency_seconds": measurements["elapsed_seconds"],
            "source_engine_sha256_after": digest(owning_path),
            "source_tree_sha256_after": source_tree_digest(source),
            "source_tree_changed_during_measurement": source_tree_digest(source) != tree_before,
            "code_changed_during_measurement": digest(owning_path) != code_before,
            "scope": "One complete transform/write/reread; separate all-cell gold check excluded from timing. Batch latency is column-processing time, not individual record latency.",
        }
    if job["kind"] == "long_text":
        text, gold = long_spanish_text(job["sections"], job["seed"])
        engine = DeidEngine()
        measurement, findings = measure(
            lambda: engine.scan_text(text), units=1, size_bytes=len(text.encode())
        )
        matches = sum(
            any(f.entity_type == "EMAIL" and (f.start, f.end) == span for f in findings)
            for span in gold
        )
        return {
            **common,
            "workload": "long_spanish_text",
            "characters": len(text),
            "input_bytes": len(text.encode()),
            "gold_email_spans": len(gold),
            "gold_email_exact_matches": matches,
            "email_gold_recall": matches / len(gold),
            "prediction_sha256": hashlib.sha256(signature(findings)).hexdigest(),
            "findings": len(findings),
            "measurement": measurement,
            "source_engine_sha256_after": digest(owning_path),
            "source_tree_sha256_after": source_tree_digest(source),
            "source_tree_changed_during_measurement": source_tree_digest(source) != tree_before,
            "code_changed_during_measurement": digest(owning_path) != code_before,
            "scope": "Rules-only long document exceeding optional NLP window size; no statistical token-throughput claim.",
        }
    if job["kind"] == "text_batch":
        engine = DeidEngine()

        def run():
            hashed = hashlib.sha256()
            count = findings = 0
            intervals: list[float] = []
            before = time.perf_counter()
            for found in engine.scan_many(
                text_batch(job["records"], job["seed"]),
                input_kind="text",
                workers=job["workers"],
                batch_size=job["batch_size"],
            ):
                now = time.perf_counter()
                intervals.append(now - before)
                before = now
                count += 1
                findings += len(found)
                hashed.update(signature(found))
            return {
                "records": count,
                "findings": findings,
                "prediction_sha256": hashed.hexdigest(),
                "iterator_wait_p50_seconds": percentile(intervals, 0.5),
                "iterator_wait_p95_seconds": percentile(intervals, 0.95),
            }

        measurement, result = measure(run, units=job["records"])
        return {
            **common,
            "workload": "spanish_text_batch",
            "workers": job["workers"],
            "batch_size": job["batch_size"],
            **result,
            "measurement": measurement,
            "source_engine_sha256_after": digest(owning_path),
            "source_tree_sha256_after": source_tree_digest(source),
            "source_tree_changed_during_measurement": source_tree_digest(source) != tree_before,
            "code_changed_during_measurement": digest(owning_path) != code_before,
            "scope": "End-to-end includes process startup and ordered hashing. Iterator wait intervals are not per-document service latencies.",
        }
    raise ValueError("Unknown synthetic benchmark job")


def run_child(job: dict[str, Any], directory: Path) -> dict[str, Any]:
    directory = directory.resolve()
    config = directory / f"job-{secrets.token_hex(6)}.json"
    config.write_text(json.dumps(job), encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(job["source_root"]) / "src")
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker-job", str(config)],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if process.returncode:
        raise RuntimeError("Fresh-process synthetic benchmark failed")
    return json.loads(process.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    workspace = Path(__file__).resolve().parents[3]
    parser.add_argument("--worker-job", type=Path)
    parser.add_argument("--baseline", type=Path, default=workspace / "work/deidflow-v0.2.0")
    parser.add_argument("--current", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work", type=Path, default=workspace / "work/v030-enterprise")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "benchmarks/results/v030/tabular-and-text.json",
    )
    parser.add_argument("--rows", nargs="+", type=int, default=[100000, 1000000])
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--text-records", type=int, default=10000)
    parser.add_argument("--long-sections", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--skip-text", action="store_true")
    parser.add_argument("--skip-csv", action="store_true")
    parser.add_argument(
        "--snapshot-current",
        action="store_true",
        help="Measure a verified local code copy, avoiding concurrent source edits",
    )
    parser.add_argument(
        "--implementations",
        choices=["baseline", "candidate"],
        nargs="+",
        default=["baseline", "candidate"],
    )
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
            print(json.dumps({"error": "SYNTHETIC_WORKLOAD_FAILED"}))
            return 1
    if min(args.rows + [args.batch_size, args.text_records, args.long_sections]) < 1 or any(
        w not in {1, 2, 4, 8} for w in args.workers
    ):
        parser.error("Positive workload sizes and supported bounded workers required")
    args.work = args.work.resolve()
    args.output = args.output.resolve()
    args.work.mkdir(parents=True, exist_ok=True)
    directory = args.work / ("run-" + secrets.token_hex(6))
    directory.mkdir()
    for name, root in (("baseline", args.baseline), ("candidate", args.current)):
        if name in args.implementations and not (root / "src/deidflow/engine.py").is_file():
            parser.error("A valid source checkout is required")
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "seed": args.seed,
        "baseline_commit": "0b79d3d",
        "scope": "Synthetic ground-truth CSV and Spanish text; fresh child processes import the requested source tree. No private Gmail access. Single full-scale trials with possible background workload; not a statistical speedup claim.",
        "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    sources = []
    if "baseline" in args.implementations:
        sources.append(("v0.2.0", args.baseline.resolve()))
    if "candidate" in args.implementations:
        current = (
            snapshot_source(args.current.resolve(), directory)
            if args.snapshot_current
            else args.current.resolve()
        )
        sources.append(("candidate_v0.3", current))
    report["candidate_source_isolation"] = (
        "verified_local_snapshot" if args.snapshot_current else "requested_source_tree"
    )
    if not args.skip_csv:
        fixture = fixtures()
        for count in args.rows:
            source = directory / f"synthetic-{count}.csv"
            fixture.generate_csv(source, count)
            for label, root in sources:
                job = {
                    "kind": "csv",
                    "implementation": label,
                    "source_root": str(root),
                    "seed": args.seed,
                    "input": str(source),
                    "output": str(directory / f"{label}-{count}.safe.csv"),
                    "rows": count,
                    "batch_size": args.batch_size,
                }
                result = run_child(job, directory)
                report["results"].append(result)
                save()
                print(
                    json.dumps(
                        {
                            "workload": "synthetic_csv",
                            "implementation": label,
                            "rows": count,
                            "seconds": result["measurement"]["elapsed_seconds"],
                            "gold_passed": result["independent_ground_truth"]["passed"],
                        }
                    ),
                    flush=True,
                )
    if not args.skip_text:
        for label, root in sources:
            base = {
                "implementation": label,
                "source_root": str(root),
                "seed": args.seed,
                "batch_size": args.batch_size,
            }
            result = run_child(
                {**base, "kind": "long_text", "sections": args.long_sections}, directory
            )
            report["results"].append(result)
            save()
            print(
                json.dumps(
                    {
                        "workload": "long_spanish_text",
                        "implementation": label,
                        "seconds": result["measurement"]["elapsed_seconds"],
                        "gold_email_recall": result["email_gold_recall"],
                    }
                ),
                flush=True,
            )
            for count in args.workers:
                result = run_child(
                    {**base, "kind": "text_batch", "workers": count, "records": args.text_records},
                    directory,
                )
                report["results"].append(result)
                save()
                print(
                    json.dumps(
                        {
                            "workload": "spanish_text_batch",
                            "implementation": label,
                            "workers": count,
                            "seconds": result["measurement"]["elapsed_seconds"],
                        }
                    ),
                    flush=True,
                )
    worker_consistency = {}
    for label, _ in sources:
        hashes = {
            r["prediction_sha256"]
            for r in report["results"]
            if r["implementation"] == label and r["workload"] == "spanish_text_batch"
        }
        worker_consistency[label] = len(hashes) == 1 if hashes else None
    report["worker_output_consistency"] = worker_consistency
    report["source_integrity_passed"] = all(
        not r.get("source_tree_changed_during_measurement", False)
        and not r.get("code_changed_during_measurement", False)
        for r in report["results"]
    )
    report["completed"] = True
    save()
    return (
        0
        if all(
            r.get("independent_ground_truth", {}).get("passed", True)
            and r.get("email_gold_recall", 1) == 1
            for r in report["results"]
        )
        and all(value is not False for value in report["worker_output_consistency"].values())
        and report["source_integrity_passed"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
