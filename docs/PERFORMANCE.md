# Local performance validation, v0.3 candidate

Measured on 2026-11-02, Windows, Python 3.11.9, Ryzen 7 5700G (8 physical / 16 logical CPUs), 16.96 GB RAM. All inference used local assets with Python DNS/connect denied. No private document was used. Downloads, installation and advisory acquisition were separate online operations. GPU performance was not measured.

The package version deliberately remained 0.2.0 while these candidate experiments ran. Frozen v0.2 is Git commit `0b79d3d`, independently archived and imported through its own source path; its 208 existing tests passed again. Candidate artifact hashes identify the changed code. Version labels in installed-distribution metadata must not be used to conflate the two implementations.

## Baseline reproduction

`benchmarks/results/v030/baseline-pdf.json` reproduces 100 native pages, 100 scanned pages and six mixed pages with seed1729, 216 DPI, PSM6, local spa+eng Tesseract 5.5.4 and an explicitly selected rules-only physical-redaction policy. The same source PDF bytes are reused by the candidate. The historical 117.95-second native result is retained in the v0.2 report, rather than substituted for this new baseline.

| Frozen v0.2 workload | Seconds | Pages/s | Status | Independent output gold |
|---|---:|---:|---|---|
| Native PDF, 100 pages | 94.016 | 1.064 | REVIEW_REQUIRED | Passed |
| Scanned PDF, 100 pages | 96.444 | 1.037 | BLOCKED | No output; residual DIAGNOSIS finding |
| Mixed PDF, 6 pages | 5.988 | 1.002 | APPROVED, explicit rules-only | Passed |

Native source transcription CER/WER was 0.000127 / 0.001087; scanned CER/WER 0.0000254 / 0.0002174; mixed 0/0. These are clean synthetic rendered text, not real-world OCR accuracy. The same OCR assets/settings are used in the candidate. The candidate does not claim a general OCR transcription improvement. Existing degraded-scan results, including unknown output OCR, remain in `pdf-ocr-challenge.json` and are not converted into zero leakage.

## Instrumentation and bounded concurrency

`StageProfiler` records document loading, rendering, OCR, rule detection, NLP when configured, context, redaction, reconstruction, encoded/pixel verification, hashing and publication. Stage rows contain inclusive/exclusive work seconds and sampled parent/process-tree peak RSS; they never receive document text or paths. OCR includes both source recognition and output verification recognition. The separate verification row measures structural/pixel checks, not the entire second OCR pass. Very short stages can finish between memory samples; a zero sampled peak does not mean zero allocation. All detailed stage rows are retained in `pdf-scaling.json`.

Parallelism overlaps only the independent installed Tesseract subprocesses. PDFium, native glyph interpretation, local NER/rules and output writing remain ordered in the parent under the PDFium lock. A bounded deque contains at most the configured workers' pages. Images and queued work are closed on errors. The default remains one worker; two, four or eight must be selected explicitly. Arbitrary custom OCR adapters cannot be assumed thread safe and are unsupported with concurrent OCR.

Raster admission uses the same conservative pixels-per-worker estimate and 2048 MiB configured budget for every scaling run. This bounds admitted page buffers, not all Python/native/model RSS. OCR child memory, parser allocations and model state must still be monitored by the host. The per-page pixel cap, input/output byte limits, parser/geometry gates, confidence thresholds, selected findings, pixel verification and output rescan are preserved.

## Worker scaling and full workloads

Candidate measurements and comparisons are added below from the completed raw artifacts. Small experiments use six native pages, three repetitions per worker, rotated worker order and identical source bytes. Their p50/p95 are whole-document trial latencies, not individual page latencies. Full workloads use one timed trial per configuration; p50/p95 cannot be inferred from one end-to-end trial. The independent extra output OCR records per-page p50/p95 separately.

<!-- PDF_RESULTS -->

| Workers | Six-page median s | Six-page p95 s | Peak tree RSS MB |
|---|---:|---:|---:|
| 1 | 7.837 | 8.577 | 227.45 |
| 2 | 5.029 | 6.003 | 314.90 |
| 4 | 4.668 | 4.721 | 461.53 |
| 8 | 4.270 | 4.334 | 462.82 |

| Full workload | Workers | Seconds | Pages/s | Peak tree RSS MB | Status / independent gold |
|---|---:|---:|---:|---:|---|
| Native 100 | 1 | 155.490 | 0.643 | 255.74 | REVIEW_REQUIRED; passed 2,000 known word regions |
| Native 100 | 8 | 75.307 | 1.328 | 510.71 | REVIEW_REQUIRED; same output SHA256; all 2,000 regions |
| Scanned 100 | 1 | 140.170 | 0.713 | 277.81 | BLOCKED, residual findings; no final output |
| Scanned 100 | 8 | 72.576 | 1.378 | 1,118.71 | BLOCKED, residual findings; no final output |
| Mixed6 | 1 | 7.872 | 0.762 | 284.53 | APPROVED, explicit rules-only; all 120 known regions |
| Mixed6 | 8 | 4.893 | 1.226 | 475.27 | APPROVED, identical PDF hash; all 120 regions |

The concurrent candidate native trial was 2.06 times as fast as its sequential candidate trial and 20% shorter than the newly reproduced 94.016-second v0.2 trial. The candidate sequential trial was slower than v0.2. Shared-machine load and profiling overhead prevent attributing the entire difference to one change. More workers cost memory; eight did not produce eightfold scaling. Default one-worker behavior is preserved. A faster blocked scan is not a successful privacy release.

The final ordinary-PDF user-only candidate ACL hardening was added after these timing experiments. It does not change selected content, OCR settings or output pixels; its failure/cleanup path and final actual-OCR output behavior are covered by regression tests. These experiment timings are not a measured release-binary SLA.

<!-- END_PDF_RESULTS -->

Every small-worker configuration must retain identical output PDF SHA256 and all known gold word regions must be opaque. Full-scale checks additionally inspect actual serialized PDF structure/metadata, extracted text, independent output OCR, planted-value absence and source-ink-tightened gold word rectangles. Passing these fixtures verifies their known regions, not every unknown visual identifier. Review status remains a review status even when all planted regions were removed.

## Tabular and long Spanish text

`benchmark_enterprise_workloads.py` imports each implementation in a fresh subprocess. CSV inputs have the same seed, five columns and batch size1024. All expected sensitive cells and all nonsensitive amounts are independently checked after the actual output is reopened. Timing includes transformation, writing and the library's mandatory reread/rescan; independent gold validation is measured outside that timed call. Long Spanish documents and 10,000 short texts exercise exhaustive scanning and 1/2/4/8 ordered text workers.

<!-- TABULAR_RESULTS -->

| CSV workload | Frozen v0.2 s | Candidate s | Candidate rows/s | Candidate MB/s | Candidate peak RSS MB |
|---|---:|---:|---:|---:|---:|
| 100,000 rows | 17.704 | 19.269 | 5,189.76 | 0.544 | 41.21 |
| 1,000,000 rows | 183.864 | 185.274 | 5,397.41 | 0.566 | 38.79 |

Candidate column-batch p50/p95 was 0.0940/0.1010 seconds for 100k and 0.0894/0.1203 seconds for1m. These are batch-processing latencies, not individual-record latency or repeated full-request percentiles. Every one of 300,000 and 3,000,000 expected sensitive cells and all 100k/1m amounts passed independent checks. Input and transformed output SHA256 matched the frozen baseline. No privacy-critical recognizer was disabled. The candidate took 8.84% longer on 100k and 0.77% longer on1m in these single trials; a universal tabular speedup is not claimed.

The canonical candidate source snapshot is `1d26f08550f2b1031467c7410bfe3639d4a9fe51a4b8d54ceab123d8bb1a7a3a`, unchanged before/after both jobs, with zero inference network attempts. The first stable report checkpoint contained 100k only because the chat interrupted its process; the missing1m job was resumed from exactly that immutable snapshot in a fresh process. `tabular-and-text.json` verifies and records the hashes of both inputs to its canonical merge. Neither interrupted candidates nor measurements with source changes are treated as stable final trials. Legacy baseline/text results record engine-file integrity only; whole-tree integrity cannot be inferred retrospectively.

| Text experiment | Frozen v0.2 s | Candidate s | Candidate peak tree RSS MB |
|---|---:|---:|---:|
| Long Spanish,1,162,500 characters | 0.872 | 1.214 | 40.35 |
| 10,000 texts,1 worker | 1.487 | 1.532 | 37.46 |
| 10,000 texts,2 workers | 1.414 | 1.108 | 96.69 |
| 10,000 texts,4 workers | 1.036 | 0.809 | 152.14 |
| 10,000 texts,8 workers | 1.072 | 1.050 | 260.16 |

Both long-text detectors found all 100 planted email mentions. This does not measure unknown names or all PII in a document. Ordered output prediction hashes/counts are identical across text worker counts. Four workers outperform eight on this small workload; process startup, transfer costs and memory matter. Candidate long-text and one-worker timings regress. Text iterator wait intervals are measured separately and are not service-latency percentiles. CSV/text full-scale trials have one repetition; no confidence intervals or synthetic p50/p95 full-request values are fabricated.

<!-- END_TABULAR_RESULTS -->

The clinical recognizers add work on ordinary columns. A necessary-condition early-out skips their patterns only when none can possibly match. Every finding and its metadata stayed identical on MEDDOCAN dev+test (500 documents); arbitrary-text property tests also compare enabled/unconditional execution. `public-trigger-equivalence.json` records the hashes. Initial slower runs are preserved, including trials whose whole-source hash changed during concurrent development; they are not silently substituted for a frozen final trial. No critical detector is disabled for speed.

## Operating limits and interpretation

The Windows machine was shared with other local validation jobs. Timings are observed results, not an isolated causal estimate of speedup or a throughput SLA. Repeating the runs on a quiescent representative host is necessary for capacity planning. Full-scale runs have no statistical timing confidence interval. The small-sample p95 from three trials is descriptive and unstable.

RSS is sampled every10ms and includes surviving OCR descendants. The ordinary CPU field measures only the parent and excludes exited child CPU. `cpu-observation.json` separately records ten one-second system-wide utilization samples while PDF/CSV jobs were active, including background activity. It is not attributed solely to a workload and does not establish CPU saturation of each process.

Public unannotated operational PDFs, their partial coverage and failures are separate in `public-documents.json` and `public-document-sources.json`. They provide no detection precision, recall or F1. Private Gmail benchmarks were not executed; their operational report uses a separate coarsened schema and cannot be merged with public or synthetic accuracy.

## Reproduce locally

From the repository, after installing the optional benchmark/PDF/OCR dependencies and explicit local OCR assets:

```powershell
$python = '..\..\.venv\Scripts\python.exe'
# Use new work/output directories for every run; existing outputs are never overwritten.
& $python scripts/benchmark_pdf_scaling.py --work ../../work/v030/pdf-new-run --output benchmarks/results/v030/pdf-new-run.json
& $python scripts/benchmark_enterprise_workloads.py --help
& $python scripts/benchmark_public_documents.py --help
```

The frozen baseline must be an unchanged archive of `0b79d3d` at `../../work/deidflow-v0.2.0`; generating a baseline from the candidate invalidates the comparison. Public downloads require explicit acquisition and appropriate source terms. These commands must never be pointed at private documents from the coding-agent session.
