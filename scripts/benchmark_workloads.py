"""Real bounded-workload benchmarks; generated assets stay in the work directory.

The full million-row transformation includes output re-reading and verification.
Unavailable OCR/GPU/ONNX paths are recorded rather than given invented timings.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from functools import partial
from pathlib import Path
from typing import Any

from deidflow import DeidEngine, Policy
from deidflow.benchmarks.datasets import clabe_check_digit, synthetic_corpus
from deidflow.benchmarks.runner import machine_metadata, measure


def generated_row(index: int) -> dict[str, str]:
    prefix = f"002180{index:011d}"
    return {
        "email": f"persona.{index:09d}@example.org",
        "clabe": prefix + clabe_check_digit(prefix),
        "customer_id": f"CLI-{index:09d}",
        "amount": f"{index % 10000}.50",
        "notes": "Registro sintético para pruebas",
    }


def generate_csv(path: Path, rows: int) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(generated_row(0)))
        writer.writeheader()
        for index in range(rows):
            writer.writerow(generated_row(index))


def _verify_csv(path: Path, rows: int) -> dict[str, Any]:
    checked = leaked = relation_errors = count = 0
    with path.open(encoding="utf-8", newline="") as stream:
        for index, row in enumerate(csv.DictReader(stream)):
            source = generated_row(index)
            count += 1
            for column in ("email", "clabe", "customer_id"):
                checked += 1
                if source[column] in row.get(column, ""):
                    leaked += 1
            relation_errors += int(row.get("amount") != source["amount"])
    return {
        "records": count,
        "expected_records": rows,
        "gold_sensitive_cells_checked": checked,
        "residual_gold_cells": leaked,
        "unchanged_amount_errors": relation_errors,
        "passed": count == rows and leaked == 0 and relation_errors == 0,
    }


def benchmark_csv(
    path: Path, *, rows: int, batch_size: int, repeats: int, schema_fast_path: bool = True
) -> dict[str, Any]:
    source = path / f"synthetic-{rows}.csv"
    if not source.exists():
        generate_csv(source, rows)
    policy = Policy.strict(require_ner=False)
    measurements = []
    verification: dict[str, Any] = {}
    for repeat in range(repeats):
        output = path / f"safe-{rows}-b{batch_size}-{repeat}.csv"
        engine = DeidEngine(
            max_bytes=max(64 * 1024 * 1024, source.stat().st_size + 1),
            schema_fast_path=schema_fast_path,
        )
        measurement, result = measure(
            partial(engine.deidentify, source, policy=policy, output=output, batch_size=batch_size),
            units=rows,
            size_bytes=source.stat().st_size,
        )
        # Independent known-ground-truth check after the library's own verifier.
        verification = (
            _verify_csv(output, rows)
            if output.exists()
            else {"passed": False, "reason": "No output produced"}
        )
        measurement["status"] = str(result.status)
        measurement["library_issues"] = list(result.issues)
        measurement["ground_truth"] = verification
        measurements.append(measurement)
        output.unlink(missing_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {
        "workload": "csv_full_transform_and_reread",
        "rows": rows,
        "columns": 5,
        "gold_sensitive_cells": rows * 3,
        "batch_size": batch_size,
        "schema_fast_path": schema_fast_path,
        "file_bytes": source.stat().st_size,
        "input_sha256": digest.hexdigest(),
        "repeats": repeats,
        "runs": measurements,
        "status": "measured"
        if all(run["ground_truth"]["passed"] for run in measurements)
        else "failed_verification",
    }


def benchmark_text(records: int, batch_sizes: list[int]) -> list[dict[str, Any]]:
    corpus = synthetic_corpus("test", count=150)
    result = []
    for batch in batch_sizes:
        engine = DeidEngine()
        texts = (corpus[i % len(corpus)].text for i in range(records))

        def run(engine: DeidEngine = engine, texts: Any = texts, batch: int = batch) -> int:
            return sum(
                len(findings)
                for findings in engine.scan_many(
                    texts, input_kind="text", batch_size=batch, workers=1
                )
            )

        measurement, findings_count = measure(run, units=records)
        result.append(
            {
                "workload": "free_text_stream",
                "records": records,
                "batch_size": batch,
                "findings": findings_count,
                "runs": [measurement],
                "status": "measured",
                "nlp_tokens_per_second": None,
                "note": "Rules-only text; NLP token rate unavailable without statistical adapter",
            }
        )
    return result


def benchmark_pdf(path: Path, pages: int = 100) -> dict[str, Any]:
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        return {
            "workload": "native_pdf",
            "status": "unavailable",
            "reason": "reportlab fixture generator is not installed",
        }
    source = path / f"native-{pages}.pdf"
    pdf = canvas.Canvas(str(source), pageCompression=1, invariant=1)
    for page in range(pages):
        pdf.drawString(72, 720, f"Correo: pagina.{page}@example.org")
        pdf.drawString(72, 700, "Documento de prueba. Todos los datos son sinteticos.")
        pdf.showPage()
    pdf.save()
    engine = DeidEngine()
    measurement, findings = measure(
        lambda: engine.scan(source), units=pages, size_bytes=source.stat().st_size
    )
    found = sum(f.entity_type == "EMAIL" for f in findings)
    return {
        "workload": "native_pdf",
        "status": "measured",
        "pages": pages,
        "email_findings": found,
        "email_gold": pages,
        "email_recall": found / pages,
        "runs": [measurement],
        "pages_per_second": measurement["records_per_second"],
        "scope": "Native extraction plus detection; no PDF transformation or OCR",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", default="../../work/deidflow-benchmarks")
    parser.add_argument("--output", default="benchmarks/results/workloads.json")
    parser.add_argument("--rows", type=int, nargs="+", default=[100_000, 1_000_000])
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[1024])
    parser.add_argument("--text-records", type=int, default=10_000)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--skip-csv", action="store_true")
    parser.add_argument("--skip-text", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--disable-schema-fast-path", action="store_true")
    args = parser.parse_args()
    if min(args.rows + args.batch_sizes + [args.text_records, args.repeats]) < 1:
        parser.error("Workload sizes must be positive")
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    workloads = []
    if not args.skip_csv:
        for rows in args.rows:
            for batch in args.batch_sizes:
                workloads.append(
                    benchmark_csv(
                        work,
                        rows=rows,
                        batch_size=batch,
                        repeats=args.repeats,
                        schema_fast_path=not args.disable_schema_fast_path,
                    )
                )
                print(
                    json.dumps(
                        {
                            "progress": "csv",
                            "rows": rows,
                            "batch": batch,
                            "status": workloads[-1]["status"],
                        }
                    ),
                    flush=True,
                )
    if not args.skip_text:
        workloads.extend(benchmark_text(args.text_records, args.batch_sizes))
    if not args.skip_pdf:
        workloads.append(benchmark_pdf(work))
    workloads.extend(
        [
            {
                "workload": "scanned_pdf_collection",
                "status": "unavailable",
                "reason": "Requires local OCR executable and Spanish weights; no assets downloaded by benchmark",
            },
            {
                "workload": "gpu_vs_cpu",
                "status": "not_measured",
                "reason": "No GPU-capable discriminative adapter configured",
            },
            {
                "workload": "onnx",
                "status": "not_measured",
                "reason": "No supported local ONNX model configured",
            },
        ]
    )
    report = {
        "schema_version": 1,
        "seed": 1729,
        "machine": machine_metadata(),
        "workloads": workloads,
        "methodology": "End-to-end CSV includes schema classification, all-cell transformation, output write and library re-read verification; separate gold check excluded from timing. Peak RSS is sampled process-tree RSS, not allocation-only memory. Single full-scale repeats unless configured; no statistical speedup claims.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"results": str(output), "workloads": len(workloads)}, indent=2))


if __name__ == "__main__":
    main()
