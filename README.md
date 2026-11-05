# DeidFlow

Local-first Spanish/Mexican sensitive-data detection and verified transformations.
Working experimental development release **0.3.0**, with genuine tests and benchmarks. This is
not certified production privacy infrastructure, a guarantee of anonymity, or a
compliance claim. [Current engineering/release assessment](docs/RELEASE_REPORT_v030.md),
[performance](docs/PERFORMANCE.md), [detection quality](docs/DETECTION_QUALITY.md),
[v0.2 OCR/PDF report](docs/pdf-ocr-report.md), the
[2026-11 metrics audit and production plan (Spanish)](docs/AUDITORIA_Y_PLAN_PRODUCCION.md) and the
[v0.1 baseline report](docs/engineering-report.md) record evidence
and remaining work. Source code is published on [GitHub](https://github.com/giovannyTorres/deidflow).
No package is uploaded to PyPI. The current [license](LICENSE) reserves all rights;
this source publication does not grant public reuse rights.

```sh
python -m pip install -e .
python -m pip install -e ".[dev,pdf,ocr,tables,yaml,training,benchmarks,nlp]"
pytest
```

No mandatory runtime dependencies, generative models, remote inference, telemetry
or runtime model downloads. Optional assets are explicitly installed and locally
loaded. Python 3.11+; base wheel additionally smoke-tested on Python 3.13.

```python
from deidflow import DeidEngine, Policy

engine = DeidEngine(language="es", country="MX", offline=True)
findings = engine.scan_text("correo: persona@example.test")
result = engine.deidentify_text("correo: persona@example.test")
assert result.status == "REVIEW_REQUIRED"  # Semantic coverage is required by default.

# With an evaluated, explicitly supplied local semantic adapter:
# from deidflow.nlp import SpacyNER
# engine = DeidEngine(nlp=SpacyNER("/trusted/local/spanish-model"))
# result = engine.deidentify("input.csv", policy=Policy.strict(), output="candidate.csv")
# if result.release_approved:
#     pass_to_next_stage(result.output_path)
```

`Policy.strict(require_ner=False)` explicitly accepts the narrower rules-only
verification gate. It never establishes anonymous data. Always inspect
`release_approved`, not merely the existence of an output path.

## Implemented

- Typed document graph, source locations, taxonomy, provenance and span mappings.
- Compiled Mexican RFC/CURP/CLABE/card validators, email/phone/secret recognizers,
  labelled names/addresses/IDs and contextual clinical rules; custom recognizers.
- Batched local spaCy adapter with long-document overlap and overlapping spans.
- Column profiles, exhaustive streaming CSV/TSV processing, JSON/JSONL, pandas and
  Polars APIs, bounded Parquet readers, native DOCX/XLSX/PDF extraction.
- Redaction, typed placeholders, scoped HMAC pseudonyms, generalization,
  suppression, ISO date shifts, numeric buckets, partial masks and custom actions.
- Strict Python/YAML policies, domain overrides, reread verification and release
  states; actual image-pixel masking with mandatory review.
- Bounded ordered text multiprocessing, CLI and executable RAG preprocessing examples.
- Explicit local Spanish/English Tesseract 5.5.4, compiled from pinned patched
  source; shell-free image/TSV pipes, timeout, per-call settings and asset hashes.
- Physical PDF removal by streaming **new lossless image-only pages**. Output
  pixels, closed PDF structure, actual rerendering and OCR are verified; original
  streams/metadata/attachments/text are never copied. See [PDF guide](docs/pdf-redaction.md).
- Local column-model training, annotation import, active-learning selection,
  weak-label export, versioned staged models and critical-recall promotion gates.
- Pinned public-gold acquisition, independent baseline comparisons and held-out
  Spanish clinical-field improvements with explicit negative English results.
- Bounded local PDF OCR workers and numeric stage time/memory profiling.
- Jointly gated PDF/JSONL/audit export for RAG, derived from actual sanitized pixels.
  Lines and chunks are preserved; merged/multi-page table reconstruction is unsupported.
- Synthetic-tested read-only private Gmail runner and authenticated localhost
  review/annotation, requiring user execution outside Codex and explicit consent.

The taxonomy is broader than built-in detection coverage. Names/medical text are
not comprehensively recognized by the base installation. See [detection](docs/detection.md).

## Experimental

Learned column priors, per-provenance held-out calibration, schema-level medical
associations, quasi-identifier risk flags and exact repeated-mention grouping.
OCR accuracy depends on layout, image quality and independently evaluated local assets.
The synthetic column learner tied its deterministic baseline. No automatic
customer model activation exists.

## Unsupported or unmeasured

DOCX/XLSX/Parquet output transformation, automatic standalone image release,
private token-level NER training, cross-page clinical/coreference reasoning,
ONNX acceleration and GPU performance. PDF rotation/cropping, interactive forms,
encryption/signatures, searchable/vector output and non-removal PDF operators
remain unsupported. Missing/failed OCR blocks release. DataProfiler was not
measured. Safe unsupported statuses replace misleading successful outputs.

## Measured evidence

The following are retained **v0.1 baseline** measurements on an 8-core Ryzen 7
5700G, 16.96 GB RAM, Windows, Python 3.11.9. Current v0.2 OCR/PDF measurements and
validation are recorded in [the dedicated report](docs/pdf-ocr-report.md).

| Workload | Result |
| --- | --- |
| v0.1 local tests, including real-model offline inference | 127 passed |
| Synthetic contextual-rules detection, 159 documents / 305 gold spans | Precision 90.75%, recall 99.67%, exact F1 95.00% |
| Actual rules + local Spanish spaCy on the same corpus | Precision 64.62%, recall 100%, exact F1 78.51% |
| 100,000-row CSV, transform + write + reread | 22.52 s; 4,440 rows/s; sampled peak RSS 41.32 MB |
| 1,000,000-row CSV, transform + write + reread | 209.60 s; 4,771 rows/s; sampled peak RSS 40.85 MB |
| Independent full CSV gold verification | All 3 million expected sensitive cells checked; zero residual gold values |
| 100-page native PDF extraction + detection | 0.588 s; 100/100 planted emails found |

These results are synthetic and machine-specific. Full-scale CSV workloads had
one timed repetition and explicitly accepted a rules-only policy. They do not
measure all possible leakage. True hybrid NER adds false positives on this corpus;
it is not automatically better. The [methodology](docs/benchmark-methodology.md)
and [raw results](benchmarks/results) record baseline coverage, per-type metrics,
latency, sampled memory, calibration and optimization experiments.

## Public gold evaluation of the v0.3 candidate

Independent human gold exposes substantially lower accuracy than the easy
synthetic fixtures above. On MEDDOCAN's 250 held-out Spanish clinical documents,
exact rules F1 improves from 0.2433 (frozen v0.2) to 0.5089; with the same local
Spanish NER model, F1 improves from 0.2931 to 0.4679. The source-article-disjoint
subset retains the gain. MEDDOCAN has synthetic PHI inserted into published
clinical narratives; it does not represent private Mexican records. On127 actual
public English TAB judgments, both rule versions score exact F1 0.0.

Every MEDDOCAN test document still misses an exact typed gold mention. Partial
span overlap is not proof of removal, and these text corpora do not measure OCR
or transformed PDF leakage. Scores remain uncalibrated; public ECE and an actual
transformation review-required rate are unavailable. Synthetic hard negatives and
property tests protect boundary parsing, checksum evidence and existing critical
candidates, but do not establish real-world specificity. Corpus provenance,
licenses, confidence intervals, per-type errors and baseline configurations are in
[real-world benchmarks](docs/REAL_WORLD_BENCHMARKS.md) and
[detection quality](docs/DETECTION_QUALITY.md). Raw public data stay outside Git.

## CLI and reproduction

```sh
deidflow scan input.txt
deidflow deidentify input.csv --output candidate.csv --policy examples/policies.yaml
deidflow verify candidate.csv
python scripts/benchmark_detection.py --output benchmarks/results/new-run
python scripts/benchmark_workloads.py --output benchmarks/results/new-workloads.json
python scripts/benchmark_micro.py --check
python examples/rag_preprocessing.py
```

CLI exit codes: 0 = scan completed or release approved; 2 = review/blocked/
unsupported result; 3 = processing error. Scan completion is not release approval.
Standalone structured verification requires review for sensitive schema fields
without transformation context. Large CSV users should consume `scan_csv()` as
an iterator, and choose bounded batches. Default whole-document limits still
apply to graph-based readers; see [format support](docs/formats.md).

`requirements-lock-windows-py311.txt` is the final tested dependency snapshot.
Use it as constraints in a matching environment; it is not a cross-platform lock.
The optional Spanish model used for real baseline comparison is **GPL-3.0** and
kept outside the repository/package. Select and review model terms independently.
No PyMuPDF dependency exists.

## Local Spanish OCR and PDF removal

The local native executable and `spa+eng` language assets are installed outside
the repository under `../../work/tesseract-5.5.4`. No runtime download occurs.
The [setup guide](docs/local-ocr.md) records the reproducible source build,
component licenses, hashes, configuration and native-security boundaries.

```python
from pathlib import Path
from deidflow import DeidEngine, Policy
from deidflow.ocr import TesseractOCR

runtime = Path("../../work/tesseract-5.5.4").resolve()
ocr = TesseractOCR(
    executable=str(runtime / "bin/tesseract.exe"),
    tessdata_dir=runtime / "share/tessdata",
    language="spa+eng",
    psm=6,
)
engine = DeidEngine(ocr=ocr, pdf_dpi=216)
result = engine.deidentify("input.pdf", output="candidate.pdf")
# PDF default: Policy.strict_pdf(), requiring an evaluated local semantic adapter.
# Policy.strict_pdf(require_ner=False) explicitly chooses a narrower rules-only gate.
if result.release_approved:
    approved_path = result.output_path
```

PDF supports `redact`, `suppress` and `keep`. `Policy.strict()` requests typed
placeholders; use `Policy.strict_pdf()` for physical removal. Unsupported PDF
operators return `UNSUPPORTED`, never a silent substitute. The output loses text
search/selection and vector/accessibility/form structure. The original is preserved.

```powershell
deidflow deidentify input.pdf --output candidate.pdf --policy examples/policy-pdf-local.yaml --ocr-executable ../../work/tesseract-5.5.4/bin/tesseract.exe --tessdata-dir ../../work/tesseract-5.5.4/share/tessdata --pdf-dpi 216
python examples/pdf_redaction.py examples/pdf/original-demo.pdf ../../work/reviewed-demo.pdf --rules-only
```

The [synthetic before/after examples](examples/pdf) have been visually checked.
Their fixture-specific pixel and OCR results do not prove anonymity of new data.

See `docs/architecture.md`, `docs/formats.md`, `docs/training.md`,
`docs/security.md`, `docs/third-party-licenses.md` and `docs/roadmap.md`.
