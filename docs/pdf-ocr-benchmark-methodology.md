# Local Spanish OCR and PDF redaction evaluation

`scripts/benchmark_pdf_ocr.py` executes real installed Tesseract, PDFium rendering,
the raster-rebuilding PDF redactor, and a separate ground-truth verifier. It does
not download models, call paid services, use generative inference, or upload data.
Generated originals and transformed PDFs stay in a caller-selected local work
directory. JSON results contain aggregate values, hashes, counts and geometry;
they do not contain recognized plaintext or original gold values.

## Reproduction

Install reviewed local OCR assets following `docs/local-ocr.md`, then run:

```console
python scripts/benchmark_pdf_ocr.py --executable /local/tesseract --tessdata /local/tessdata --work ../../work/pdf-ocr-new-run --output benchmarks/results/pdf-ocr-new.json
```

Default workloads are 100 native-text pages, 12 clean scanned pages, six mixed
native/scanned pages, three degraded scanned pages, and three repeated three-page
native transformations. Use a fresh work directory: transformed PDFs are never
overwritten. For smoke runs use `--native-pages 1 --scanned-pages 1 --mixed-pages 0
--challenge-pages 0 --repeats 0`. Defaults: 216 DPI, Spanish plus English
(`spa+eng`), LSTM OCR mode 1, page segmentation mode 6 and one OCR thread per
process. Match all settings when comparing results. Higher DPI is not assumed
better. The benchmark accepts an explicit rules-only physical-redaction policy;
this narrower gate does not establish that unknown PII is absent. Low confidence,
unrecognized content and verification errors remain visible in status/issues.

## Synthetic fixtures and gold

Seed: 1729. Source PDFs use ReportLab invariant mode. Native pages reference
standard Helvetica; scans use a locally installed Unicode TrueType font (Arial
on this Windows host; reviewed alternatives on Linux). Font rendering and
library versions affect raster bytes and OCR. No fonts, Tesseract binaries or
language data are redistributed with the package.

Each page has an accented fictional name, reserved-domain email, Mexican phone,
structurally compatible CURP/RFC/CLABE, customer ID, multiline address and
diagnosis. Amounts/footer provide utility controls. Synthetic IDs do not confirm
registry status or identity. Nine complete sensitive spans per page are known
before detection. Challenges include deterministic blur, low contrast and slight
raster skew; failures are retained. Info metadata has another planted identity
that must not survive. Hostile forms, rotations, encryption, attachments,
appearances, malformed files and source changes are separate integration tests.

## Accuracy definitions

CER is Levenshtein character edits divided by reference characters. WER uses
whitespace-delimited token edits. Both use Unicode NFC/collapsed whitespace and
retain case, accents and punctuation. Aggregate rates weight reference lengths.
OCR confidence is an engine rank, not a measured error rate or entity probability.

Detection matches category and entire NFC/whitespace-normalized value one-to-one.
Missing OCR values count as missed entities. Precision counts unmatched spans,
including nested partial addresses. These are **gold-value metrics**, not
original-layout exact-span F1. OCR value recovery and detection recall are
reported separately by type. A malformed labelled field may be safely masked
even when its OCR value differs; that does not inflate exact value recovery.

## Independent output checks

The library reopens the PDF, checks its closed structure/encoded image pixels,
renders it and performs OCR/detection. The benchmark then separately checks:

- No original native text, annotations, forbidden catalog features or planted
  metadata; no gold text in decompressed page commands.
- Actual output rendering and OCR, residual gold values by type, retained amounts.
- **OCR absence alone never establishes deletion.** Fixture drawing supplies
  independent expected word geometry for every gold field. Regions are tightened
  to actual source-ink bounds; actual output rectangles must be >=99.5% near-black
  (pixel values below 16). Visible unchanged identifiers therefore fail even when
  OCR misreads them. Unlocatable gold words are indeterminate and fail the check.

The fixture pixel test does not trust detector-selected masks or output OCR.
It still does not prove universal visual privacy: annotation quality, unannotated
source content and unfamiliar entities remain limits. Full-page blackening would
remove sensitive words but lose the separately recorded utility controls.

## Timing and resources

Source OCR timing includes rasterization and real OCR; per-page p50/p95 and first
versus later pages are reported. Each call starts a local process. Full transform
timing includes native analysis, all-page OCR, pixel replacement, new PDF writing,
encoded-pixel checks, rerendering and output OCR. The additional benchmark gold
check is excluded. Full-scale one-repeat runs are separate from small repeats.

RSS samples every 10 ms; process-tree RSS includes live OCR children and can miss
brief peaks or double-count shared pages. CPU is parent-process CPU, excluding
exited OCR children; it is not total machine utilization. Machine/package
versions, executable/language-data hashes, seed, input hashes, DPI, PSM and policy
are recorded. Python DNS/connect are denied and attempts counted during inference;
this is not an OS firewall attestation for arbitrary subprocesses. Installation
and asset acquisition happen separately from inference.

Workloads in one session share an interpreter. Later RSS includes resident
allocations from earlier stages; these numbers are not isolated per-format model
memory or evidence that smaller document batches intrinsically consume more RAM.

Results are development evidence on generated Spanish pages and one host. They
do not establish anonymity, compliance, population recall, performance guarantees
or safe support for every PDF feature.

## Recorded 5.5.4 sessions

`benchmarks/results/pdf-ocr.json` contains the completed 100-native, 12-scanned
and six-mixed-page workloads. All had actual pixel gold checks passed and every
amount recovered by the extra OCR check. Timed transformations took 117.947,
12.879 and 6.412 seconds respectively, including library output verification.
The native and scanned batches require review for source uncertainty/low OCR
confidence; the mixed batch passed the explicitly chosen rules-only gate.

An additional challenge output OCR call originally returned no readable tokens,
interrupting the benchmark's extra checker after those three complete records.
Their measured values remain intact. That first session's Python network guard
was active, but its final attempt counter was not persisted; the JSON uses null
and makes no fabricated zero-attempt claim.

`benchmarks/results/pdf-ocr-challenge.json` records a complete second session:
three degraded scanned pages plus three repeated three-page native runs. The
degraded batch required review. All 60 known sensitive-word regions were actual
opaque black, but the extra OCR engine could not read output page three. Its
OCR residual total is **unknown/null**, the aggregate extra check is incomplete,
and only two amounts were confirmed by OCR. This does not imply that the third
amount was physically erased. The library's independent output check uses
proven constant-pixel mask whitening to avoid black-bar OCR hallucinations; the
benchmark also records the difficulty of OCR on the unchanged black-bar output.

Across the 121 non-repeat fixture pages, 2,420 known sensitive-word rectangles
representing 1,089 planted entities were verified as completely opaque black.
This is narrower than asserting universal zero leakage. The repeated runs had
median 1.0249 pages/second and identical actual PDF SHA-256 values. The second
session's final recorded Python DNS/connect attempt count was zero. Full measured
numbers, source OCR error, asset hashes, confidence and limitations are in the
JSON records and explicit `measurement_sessions` provenance.
