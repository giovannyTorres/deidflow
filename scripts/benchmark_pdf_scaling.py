"""Measured local PDF worker scaling on reproducible synthetic gold fixtures.

All native PDF operations and finding interpretation stay on the calling
thread; only independent local Tesseract subprocesses overlap. No private data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from benchmark_pdf_ocr import (
    generate_pdf,
    page_cases,
    percentile,
    verify_gold_output,
    verify_gold_pixels,
)

from deidflow import DeidEngine, Policy
from deidflow.benchmarks.runner import machine_metadata, measure, offline_network
from deidflow.ocr import TesseractOCR
from deidflow.redactors.pdf import redact_pdf


def run(args):
    args.work.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "machine": machine_metadata(),
        "configuration": {
            "seed": 1729,
            "dpi": 216,
            "psm": 6,
            "language": "spa+eng",
            "memory_admission_budget_mb": 2048,
            "policy": "strict_pdf explicit rules-only require_ner=False",
            "nlp_configured": False,
            "small_pages": args.small_pages,
            "small_repeats": args.repeats,
        },
        "notes": [
            "No private data. Python DNS/connect denied during inference.",
            "Small-sample worker selection does not establish full-scale speedup.",
            "Full-scale workloads have one run per configuration, no run-latency percentile inferred.",
            "Other local benchmark processes may be running; timings are not an isolated machine experiment.",
            "OCR work time overlaps and must not be summed as end-to-end time.",
            "Per-stage memory and peak RSS are samples, not enforced process-tree caps.",
            "Critical gold pixel coverage is checked independently of the detector.",
        ],
        "asset_sha256": {
            "tesseract": hashlib.sha256(args.executable.read_bytes()).hexdigest(),
            "spa": hashlib.sha256((args.tessdata / "spa.traineddata").read_bytes()).hexdigest(),
            "eng": hashlib.sha256((args.tessdata / "eng.traineddata").read_bytes()).hexdigest(),
        },
        "scaling_runs": [],
        "scaling_summary": [],
        "full_runs": [],
    }

    def checkpoint():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def process(source, cases, kind, workers, label, *, complete_gold=False):
        engine = DeidEngine(
            ocr=TesseractOCR(
                executable=str(args.executable),
                tessdata_dir=str(args.tessdata),
                language="spa+eng",
                psm=6,
                min_confidence=50,
                timeout=60,
            ),
            memory_budget_mb=2048,
            max_bytes=128 * 1024 * 1024,
            pdf_workers=workers,
            pdf_profile=True,
        )
        output = args.work / f"{label}-workers-{workers}.pdf"
        measured, result = measure(
            lambda: redact_pdf(
                source,
                output,
                engine=engine,
                policy=Policy.strict_pdf(require_ner=False),
                dpi=216,
            ),
            units=len(cases),
            size_bytes=source.stat().st_size,
        )
        truth = None
        if output.is_file():
            truth = (
                verify_gold_output(output, cases, engine, dpi=216, source=source, kind=kind)
                if complete_gold
                else verify_gold_pixels(source, output, cases, kind=kind, dpi=216)
            )
        value = {
            "label": label,
            "kind": kind,
            "workers": workers,
            "pages": len(cases),
            "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "output_sha256": result.audit.get("sha256"),
            "status": str(result.status),
            "release_approved": result.release_approved,
            "issues": result.issues,
            "metrics": measured,
            "pages_per_second": len(cases) / measured["elapsed_seconds"],
            "documents_per_second": 1 / measured["elapsed_seconds"],
            "performance": result.audit.get("performance"),
            "masks": result.audit.get("masks"),
            "independent_gold": truth,
            "independent_check": "full encoded/metadata/OCR/pixel gold"
            if complete_gold
            else "pixel gold only; library independently rescans serialized output",
        }
        print(
            json.dumps({k: value[k] for k in ("label", "workers", "status", "pages_per_second")}),
            flush=True,
        )
        return value

    with offline_network() as guard:
        cases = page_cases(args.small_pages)
        source = args.work / "small-native.pdf"
        generate_pdf(source, cases, kind="native", dpi=216)
        for repetition in range(args.repeats):
            # Rotate order to reduce persistent first-run ordering bias.
            workers_order = [1, 2, 4, 8]
            workers_order = workers_order[repetition:] + workers_order[:repetition]
            for workers in workers_order:
                report["scaling_runs"].append(
                    process(
                        source,
                        cases,
                        "native",
                        workers,
                        f"small-{repetition}",
                    )
                )
                checkpoint()
        for workers in (1, 2, 4, 8):
            runs = [r for r in report["scaling_runs"] if r["workers"] == workers]
            times = [r["metrics"]["elapsed_seconds"] for r in runs]
            report["scaling_summary"].append(
                {
                    "workers": workers,
                    "median_seconds": statistics.median(times),
                    "p50_document_latency_seconds": percentile(times, 0.5),
                    "p95_document_latency_seconds": percentile(times, 0.95),
                    "peak_tree_rss_bytes": max(
                        r["metrics"]["peak_process_tree_rss_bytes"] or 0 for r in runs
                    ),
                    "all_gold_pixels_masked": all(
                        r["independent_gold"] and r["independent_gold"]["passed"] for r in runs
                    ),
                    "identical_output_sha256": len({r["output_sha256"] for r in runs}) == 1,
                }
            )
        report["all_scaling_output_sha256_identical"] = (
            len({r["output_sha256"] for r in report["scaling_runs"]}) == 1
        )
        best = min(report["scaling_summary"], key=lambda r: r["median_seconds"])["workers"]
        report["selected_full_workers"] = best
        checkpoint()
        for kind, count in (
            ("native", args.full_pages),
            ("scanned", args.full_pages),
            ("mixed", 6),
        ):
            cases = page_cases(count)
            # Reuse the exact baseline bytes if available, without modifying them.
            source = args.baseline_work / f"{kind}.pdf"
            if not source.is_file():
                source = args.work / f"{kind}-source.pdf"
                generate_pdf(source, cases, kind=kind, dpi=216)
            for workers in sorted({1, best}):
                report["full_runs"].append(
                    process(
                        source,
                        cases,
                        kind,
                        workers,
                        f"full-{kind}",
                        complete_gold=True,
                    )
                )
                checkpoint()
        report["network_guard"] = {
            "python_attempted_connections": guard["attempts"],
            "scope": "Python only; no OS firewall claim",
        }
    checkpoint()
    return report


def main():
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[3]
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("benchmarks/results/v030/pdf-scaling.json")
    )
    parser.add_argument("--baseline-work", type=Path, default=root / "work/v030/baseline-pdf")
    parser.add_argument(
        "--executable", type=Path, default=root / "work/tesseract-5.5.4/bin/tesseract.exe"
    )
    parser.add_argument(
        "--tessdata", type=Path, default=root / "work/tesseract-5.5.4/share/tessdata"
    )
    parser.add_argument("--small-pages", type=int, default=6)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--full-pages", type=int, default=100)
    args = parser.parse_args()
    if (
        not 1 <= args.small_pages <= 100
        or not 1 <= args.repeats <= 20
        or not 1 <= args.full_pages <= 1000
    ):
        parser.error("Invalid workload size")
    run(args)


if __name__ == "__main__":
    main()
