# DeidFlow 0.1.0 — engineering report

This is the retained v0.1 baseline report. Current OCR installation, physical PDF
reconstruction and v0.2 validation are in [the OCR/PDF report](pdf-ocr-report.md).

Validation date: **2026-11-02**. Delivery: local installable repository, wheel and
source distribution. This release is functional research/development software
with production-oriented controls; it is **not a validated enterprise privacy
product**. No remote repository, public push, PyPI publication or customer upload
was performed.

## Implemented and executable

All modules in the [architecture module map](architecture.md) are functional.
The library supports compiled Spanish/Mexican identifier detection, contextual
rules, explicit local discriminative NLP, candidate fusion with overlap,
structured schema priors, streaming CSV/TSV and JSONL transformations, bounded
native readers, policy-driven text/dataframe transformation, HMAC tokenization,
output reread verification and a CLI. DocumentGraph retains fragment-local text
and source locations; it is not a Markdown intermediate. Native PDF page
locations are not reliable per-glyph geometry, so automatic PDF rewriting is
unsupported. [Formats](formats.md) gives exact extraction and release boundaries.

Local training provides a real character-ngram/logistic column learner, annotated
span import, weak labels, active-learning candidate selection, integrity-checked
staged models, holdout metrics and critical-recall promotion gates. A customer
model is not automatically selected. Private token-level NER training, BIO
conversion, CRF/BiLSTM/encoder adaptation and LightGBM/CatBoost comparisons remain
future work. The broad taxonomy does not imply every label has a built-in detector.

## Validation

- `pip install -e .` succeeded in the isolated Python 3.11 environment.
- `python -m pytest -q`: **127 passed**, with the real local Spanish model path
  supplied for the optional integration test; no test skips in this run.
- Ruff lint and format checks passed; Mypy passed on 21 source files.
- Wheel and source distributions built successfully with Hatchling.
- The base wheel installed with `--no-deps` into a fresh Python 3.13 environment;
  public detection and transformation APIs ran with sockets denied.
- Real Spanish model load/inference and Spanish Presidio baselines ran with
  socket/DNS denied; recorded network attempts were **zero**.
- Dependency consistency passed. The final local pip-audit response reports
  **no known vulnerabilities** after upgrading Pillow, pip and setuptools.
  See [audit response](dependency-audit.json) and [license inventory](third-party-licenses.md).
- CI includes Linux/Windows and Python 3.11/3.13 jobs, packaging, lint, types,
  tests, dependency auditing and microbenchmark/critical-recall gates. Remote CI
  has not run because no publication was authorized.

Tests include malformed inputs, checksum failures, Unicode and multiline spans,
overlapping candidates, long NLP windows, hidden Office data, ZIP abuse, invalid
OCR boxes, pixel replacement and metadata, schema coverage, deterministic
process ordering, token scopes, domain rules, no-op transformations, failed
verification cleanup, residual-sample saturation and pandas MultiIndex disclosure.

## Detection comparison

Source: [final offline baseline JSON](../benchmarks/results/spanish-model/detection.json).
Seed 1729; **159 synthetic held-out Spanish/Mexican documents, 305 gold spans**.
Train/validation/test templates and entity namespaces are separated; difficult
records include unlabelled names, multiline/split IDs, OCR-like damage and
negatives. The corpus is deliberately small and not representative production
sampling. It was expanded with diagnostic challenge cases during development;
it is an engineering fixture, not an untouched external scientific benchmark.

| Pipeline | Exact precision | Exact recall | Exact F1 | Median documents/s |
| --- | ---: | ---: | ---: | ---: |
| Deterministic patterns without contextual rules | 1.0000 | 0.5934 | 0.7449 | 25,731 |
| DeidFlow contextual rules | 0.9075 | 0.9967 | 0.9500 | 12,376 |
| Local Spanish spaCy | 0.1856 | 0.1016 | 0.1314 | 106.9 |
| Spanish-configured Presidio, same local NLP model | 0.2661 | 0.2033 | 0.2305 | 81.4 |
| DeidFlow rules + same local spaCy | 0.6462 | 1.0000 | 0.7851 | 99.1 |

Contextual rules produced 304 true positives, 31 false positives and one false
negative. True hybrid produced 305 true positives, 167 false positives and zero
false negatives. It recovered an unlabelled name but reduced precision substantially.
This is evidence against blindly enabling that model for these data. The optional
model is spaCy `es_core_news_sm` 3.8.0, loaded explicitly from a private local path.

These full-taxonomy baseline values penalize unsupported Mexican/health/secret
categories in general-purpose NER/Presidio; **they do not establish general
superiority**. PERSON-only comparable metrics are separately recorded: contextual
rules recall .9677/F1 .9836, versus recall 1.0/F1 .6139 for the other model-based
pipelines, reflecting false positive names. Production comparisons require local
domain-specific recognizer configuration, independent corpora and annotation.
DataProfiler is not a text-span baseline and was not measured as a structured
classifier; there are no invented DataProfiler scores.

The JSON records exact and overlap precision/recall/F1, per-type/per-format recall,
document leakage, non-gold character redaction, warm p50/p95, imports/first-call
latency, RSS, CPU, asset metadata and corpus hashes. Only text-format span accuracy
is populated by this corpus; other format accuracy is not inferred from it.
Uncalibrated rule scores have ECE `null`. A separate validation-fitted logistic
mapping evaluated on test candidates obtained **ECE .0217168**; this small
synthetic calibration is experimental and not automatically enabled.

## Full workloads and memory

Source: [workloads.json](../benchmarks/results/workloads.json). Ryzen 7 5700G,
8 physical/16 logical cores, 16,962,179,072 bytes RAM; Windows, Python 3.11.9;
CPU-only. RTX 4060 8 GB is present but unused. Package versions are recorded.

| Workload | Size | Elapsed | Throughput | Sampled peak process RSS |
| --- | ---: | ---: | ---: | ---: |
| CSV complete transform + write + reread | 100,000 rows; 10.49 MB | 22.524 s | 4,439.7 rows/s; .466 MB/s | 41.32 MB |
| CSV complete transform + write + reread | 1,000,000 rows; 104.89 MB | 209.600 s | 4,771.0 rows/s; .500 MB/s | 40.85 MB |
| Generated text stream | 10,000 records | 1.245 s | 8,030.3 records/s | 39.98 MB |
| Native PDF extraction + email detection | 100 pages | .588 s | 170.07 pages/s | 55.18 MB |

Both CSV runs transformed three known sensitive columns and preserved amounts.
Independent streaming ground-truth checks examined every **300,000 / 3,000,000**
sensitive cell, found zero residual gold values, and confirmed all row counts and
amounts. That separate gold check is excluded from timing. The library's own
write/reopen/rescan is included. Both runs explicitly used a rules-only acceptance
policy; default strict policy would require semantic-model review. A single
full-scale repetition per size cannot establish confidence intervals. Peak RSS
is sampled every 10 ms and may miss transient peaks; similar memory observations
are not a universal memory guarantee. CPU utilization was about one occupied core.
Later security changes added no-op/scope/domain checks and medical-schema
association; the full workloads use unchanged placeholder actions and headers.
Use the scripts to remeasure on the final deployment data/policy/host.

The native PDF workload found 100/100 planted emails. It measures extraction plus
detection, not PDF redaction, scanned recall or visual fidelity. Three real
image-only probe PDFs all refused complete scanning because local Tesseract was
absent. OCR error and throughput are **unmeasured**, recorded as null/unavailable.
No GPU, ONNX or scanned-PDF speedup is claimed.

## Optimization experiments

Three repeated paired 10,000-row CSV trials, with identical expected sensitive
cell handling and independent verification, are in
[experiments.json](../benchmarks/results/experiments.json). At batch 1024, the
column fast path measured median **4,691.95 rows/s**, versus **1,783.81 rows/s**
with additional per-cell detection: **2.63× on this workload/host**. This is
whole-column processing, not a measured SIMD/vectorized implementation. At batch
128, rates were 2,586 versus 1,271 rows/s. Sampling never bypasses later cells.

Initial per-text multiprocessing IPC was substantially slower than one worker.
The implementation was changed to bounded batches of up to 64 texts per IPC task,
with reused worker detectors. In
[the final IPC experiment](../benchmarks/results/experiments-batched-ipc.json),
three-repeat medians for 1/2/4 workers were **9,225.90 / 8,412.15 / 9,318.01**
texts/s. Findings and order had identical SHA-256 digests. Maximum process-tree
RSS was 43.63 / 111.05 / 178.27 MB. Four workers' ~1% difference is within observed
variation; there is no material speedup claim. One worker remains the default.

The real NLP batch trial processed 159 documents in .794 seconds, about 2,861
NLP tokens/s, versus about 1,416 tokens/s single-item inference. It is an
exploratory single batch, not a stable enterprise scaling result. CPU-only
microbenchmarks enforce generous absolute/relative budgets and perfect fixture
recall for five critical categories, separately from machine-specific full runs.

## Training results

The synthetic four-label column learner trained on 96 columns, validated on 48,
and tested on 48. It achieved accuracy 1.0 and **tied** its deterministic pattern
baseline. The model remains STAGED; the promotion decision is only eligibility
for manual activation. This is a working offline training/registry demonstration,
not evidence of learned superiority or customer-domain performance. See
[evaluation.json](../benchmarks/results/training-model/evaluation.json) and
[training guide](training.md).

## Security, limitations and next priorities

Default rules are incomplete for arbitrary names, addresses, credentials,
medical relationships and quasi-identifiers. Semantic model presence is not a
quality certificate; caller-supplied adapters/configurations are trusted code.
Post-transformation detection cannot prove no sensitive data remains. Stable
pseudonyms remain linkable; no compliance/anonymity guarantee is made.

Automatic PDF/Office/Parquet rewriting and automatic image release remain
unsupported. Image masks replace actual pixels, reopen and verify lossless PNG
pixels/metadata, and always require independent OCR/review. Native PDF geometry
is incomplete. Structured medical relationships are conservative schema-level
associations; JSON cross-field clinical reasoning is unsupported. Exact mention
grouping deliberately does not infer aliases of unrelated people.

The optional benchmark Spanish model is **GPL-3.0** and retained outside all
distributed artifacts. spaCy code's MIT license does not change its model license.
The base package has no dependencies, and there is no PyMuPDF dependency. Review
all selected native binary/model notices before commercial redistribution. Name
inspection is not legal clearance or a package reservation.

Priorities: representative independent Mexican holdouts; approved local OCR
assets and measured scanned accuracy; safe PDF/Office output with independent
verification; locally trained token/span NER; stronger protected receipts/model
storage; vectorized/Parquet output; and repeated isolated model-memory/throughput
tests. The [roadmap](roadmap.md), [threat model](security.md) and
[license report](third-party-licenses.md) specify these boundaries.
