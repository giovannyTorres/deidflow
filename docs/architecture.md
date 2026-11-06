# Architecture and API

DeidFlow 0.2.0 is a working, local development release with explicit release
gates. It is not certified production privacy infrastructure. Python 3.11+;
`src/` package; no base runtime dependencies. Optional backends import lazily.

## Data flow

1. Native readers build a `DocumentGraph`, never Markdown. Each `Fragment`
   retains extracted text, fragment-local Unicode offsets, source location,
   section/page/cell/part metadata and completeness warnings.
2. Reusable compiled `RuleDetector` recognizers return typed `Finding` objects.
   Mexican identifiers distinguish pattern/structure/checksum evidence from
   registry confirmation (which is never performed).
3. An explicitly provided local `SpacyNER` or application adapter supplies batched
   spans. Long spaCy inputs use overlapping windows; unresolved boundaries require
   review. Candidates retain provenance and overlap, and scores are evidence
   ranks unless explicitly calibrated. No incompatible score averaging occurs.
4. `Policy` selects actions by category and optional domain. Selected intersecting
   spans are unioned before substitution, preventing a nested candidate tail from
   surviving. Source maps describe original and resulting character intervals.
5. File transformations write a private temporary candidate in the destination
   directory, reopen actual serialized content and rescan. CSV verifies row count
   and headers. Only non-blocked candidates receive the final filename, using
   an atomic hard link that cannot overwrite an existing file. Temporary files
   are removed on failure. This requires a filesystem that supports hard links.
   PDF files use a separate streaming raster-reconstruction path: exact native
   glyph mapping plus OCR, new lossless pixels, closed object grammar, decoded
   pixel hashes/masks and actual output rerender/OCR. No source objects are copied.
6. Status is APPROVED, REVIEW_REQUIRED, BLOCKED or UNSUPPORTED. APPROVED means the
   configured automated checks passed. It does not establish anonymity.

## Public examples

```python
from deidflow import DeidEngine, Policy, Rule

engine = DeidEngine(language="es", country="ALL", offline=True)
findings = engine.scan_text("correo: persona@example.test")
result = engine.deidentify_text("correo: persona@example.test")
assert result.status == "REVIEW_REQUIRED"  # Strict semantic-model gate.

# Explicitly selecting a narrower, rules-only acceptance policy is possible.
policy = Policy.strict(require_ner=False)
result = engine.deidentify("input.csv", policy=policy, output="candidate.csv")
if result.release_approved:
    consume_path = result.output_path
```

`scan(path)` returns findings for complete extraction, and refuses incomplete
coverage. Inspect `engine.read(path).issues` to investigate unsupported regions.
The iterable `scan_csv(path, batch_size=1024)` streams every applicable record;
collecting `scan(path)` naturally retains its resulting findings in memory.
`scan_dataframe`, `deidentify_dataframe`, `scan_many`, `deidentify_many`,
`profile`, `verify` and `benchmark` are executable APIs. `readers.iter_parquet_batches`
provides Arrow record batches for large Parquet inputs; automatic Parquet output
transformation is currently unsupported. DOCX and XLSX output is rewritten in
place (`deidflow.office`). See `docs/formats.md` for details.

Standalone structured `verify()` lacks the original transformation receipt. It
therefore requires review for nonempty identity-schema fields, even when text
rules find nothing. It never treats arbitrary placeholder-looking input as proof
of prior transformation. Internal verification after an actual transformation
has the processing context and checks the generated file independently.

## Structured execution

Header priors, value hit rates, length, character composition, entropy and
uniqueness classify columns. Sampling informs the prior; it never exempts later
values from processing. Known columns receive whole-field transformations; other
values receive deterministic scanning and a single batched statistical pass.
Medical columns are associated with identifiable-subject columns at table-schema
level. This conservative association may overclassify rows with missing identity.
It is not a clinical relation extractor. General medical vocabulary without a
subject schema is not automatically treated as personal health information.

CSV/TSV processing and reread verification are bounded batches. Numeric amounts
remain unchanged when not selected. DataFrame dtypes are retained where a
lossless conversion permits; changed dtypes are recorded. The DataFrame API
already receives a materialized table and copies it; it is not a streaming API.
Indices and schema text are inspected for disclosure. The initial fast path uses
compiled Python/column processing, not SIMD vectorized Arrow regex execution;
vectorization remains an optimization experiment rather than a marketing claim.

The optional `training.LocalColumnModel` is a separately evaluated learned prior.
It does not automatically modify the engine's classifier. A customer can use its
prediction for review or supply explicitly reviewed recognizers/adapters. New
models are staged and never automatically activated. Rule score calibration is
optional, per-provenance and evaluated separately.

## Bounded execution

`scan_many(..., input_kind="text", workers=2)` uses bounded process batches with
deterministic order for built-in CPU rules. Custom recognizers and statistical
adapters use one process; model calls are guarded by an engine lock. File-batch
transformations are sequential, avoiding inconsistent private token state. Memory
budgets reject oversized batches; they are admission bounds rather than a hard
operating-system RSS limit. Multiprocessing adds interpreter memory and can be
slower for small texts. There are no persisted plaintext caches or token maps.

The fast/balanced/assurance profiles primarily affect document/OCR routing in
this version. They do not select an unverified model or silently skip detectors.
CPU is tested. CUDA selection in the local spaCy adapter fails explicitly if
unavailable; no GPU/ONNX throughput claim is made.

## Module map

| Module | Functional responsibility |
| --- | --- |
| `core` | Taxonomy, findings, fragments, locations, graph |
| `validators` | RFC/CURP/CLABE/card structural and checksum checks |
| `detectors` | Compiled rules, custom recognizers, fusion, exact keyed grouping |
| `nlp` | Explicit local spaCy adapter, batched inference, windows |
| `structured` | Column priors, features, health-schema association |
| `policies` | Typed Python/YAML configuration and fingerprints |
| `transformations` | Redaction, placeholders, keyed tokens, shift/bucket/mask/custom |
| `engine` | Public APIs, streaming, processes, release verification |
| `readers`, `ocr`, `redactors` | Native extraction, local OCR process, actual image masking and verified PDF reconstruction |
| `risk` | Inspectable quasi-identifier/health association flags |
| `training` | Local column learner, annotation import, active learning, promotion gate |
| `benchmarks` | Synthetic gold, detection metrics, measured performance |
| `cli` | Safe aggregate JSON results and status exit codes |
