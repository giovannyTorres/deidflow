# DeidFlow

Local-first Spanish/Mexican sensitive-data detection and verified transformations.
Working development release **0.1.0**, with genuine tests and benchmarks. This is
not certified production privacy infrastructure, a guarantee of anonymity, or a
compliance claim. [Engineering report](docs/engineering-report.md) records evidence
and remaining work. No public repository or package publication was performed.

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
- Local column-model training, annotation import, active-learning selection,
  weak-label export, versioned staged models and critical-recall promotion gates.

The taxonomy is broader than built-in detection coverage. Names/medical text are
not comprehensively recognized by the base installation. See [detection](docs/detection.md).

## Experimental

Learned column priors, per-provenance held-out calibration, schema-level medical
associations, quasi-identifier risk flags and exact repeated-mention grouping.
Image/OCR adapters require reviewed local assets and independent quality checks.
The synthetic column learner tied its deterministic baseline. No automatic
customer model activation exists.

## Unsupported or unmeasured

Automatic PDF/DOCX/XLSX/Parquet output transformation, automatic image release,
private token-level NER training, cross-page clinical/coreference reasoning,
ONNX acceleration and GPU performance. Tesseract was absent, so real OCR accuracy
and throughput are unmeasured; scanned inputs fail closed. DataProfiler was not
measured. Safe unsupported statuses replace misleading successful outputs.

## Measured evidence

Validation on an 8-core Ryzen 7 5700G, 16.96 GB RAM, Windows, Python 3.11.9:

| Workload | Result |
| --- | --- |
| Local tests, including real-model offline inference | 127 passed |
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

See `docs/architecture.md`, `docs/formats.md`, `docs/training.md`,
`docs/security.md`, `docs/third-party-licenses.md` and `docs/roadmap.md`.
