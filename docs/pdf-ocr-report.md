# DeidFlow 0.2.0 - local Spanish OCR and verified PDF removal

Engineering validation: **2026-11-02**. Everything was built and executed locally.
No repository publication, remote push, document upload or paid service was used.
This extends the [retained v0.1 report](engineering-report.md); it does not claim
universal anonymity, compliance or production-domain accuracy.

## Implemented and installed

**Tesseract 5.5.4** was compiled from pinned upstream commit
`7e548e6eff172f38f97664afe7f7ce40db36c8d6`, with GCC 16.2, CMake and Ninja.
The earlier Windows package-manager binary lagged behind upstream's security
release. The selected release includes upstream security fixes. The local build
disables CURL, libarchive, ScrollView, the legacy engine and OpenMP; LSTM CPU/SIMD
inference remains enabled. [Upstream release](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.4).

The runtime and official pinned `tessdata_fast` Spanish/English weights are in
`../../work/tesseract-5.5.4`, outside the repository and Python artifacts. No PATH
or registry modification was needed. Original native notices are retained there.
Twenty-one native package versions/hashes/licenses and actual executable/DLL/model
hashes are in [build lock](ocr-build-lock.json) and [asset manifest](ocr-assets.json).
The [setup guide](local-ocr.md) and `scripts/install_local_ocr.py` reproduce the
explicit development-time download/build, separate from offline inference.

The OCR adapter now sends PNG through stdin and reads TSV from stdout using
shell-free process arguments, explicit local data paths, timeouts and per-call
settings. It creates no sensitive OCR image/text temporary files and does not
mutate global pytesseract configuration. `pytesseract` is no longer required.
Real testing found and blocked two otherwise silent native fallbacks: disabled
PSM 12 becoming PSM 11, and failed Spanish loading while English still returned
exit code zero. Low-confidence words remain visible to review gates.

## PDF processing and removal proof

`engine.deidentify("input.pdf", output="candidate.pdf")` now uses a dedicated
streaming raster-reconstruction backend. It supports compatible native, scanned
and mixed documents. `Policy.strict_pdf()` explicitly selects physical removal;
the text policy's typed placeholders are not silently substituted.

Each supported page receives native glyph analysis plus OCR. Python/native
character indices are explicitly mapped. Selected glyphs and complete intersecting
OCR tokens are replaced in fresh RGB pixels. A small closed PDF grammar writes
new lossless image-only pages. **No original objects or streams are copied.**
Original text, Info/XMP metadata, attachments, annotations, layers, fonts and
actions therefore have no surviving source representation in the output.

Verification reopens the encoded PDF with a separate parser, checks object and
stream allowlists, compares actual decoded raster hashes and verifies every
masked pixel. It then rerenders and rescans the actual output. Black bars can
make OCR hallucinate letters; only regions independently proved solid black in
the rerendered output are whitened in temporary OCR input. The output PDF itself
is unchanged. A nonconstant pixel fails this exclusion proof.

Source hashes are checked before processing and before release. Output creation
is atomic and nonoverwriting. Blocked/unsupported operations expose no final
candidate. Uncertain OCR, unresolved findings or insufficient semantic coverage
cannot become automatic approval. Standalone verification lacks source receipts
and returns at least review. Full details: [PDF implementation guide](pdf-redaction.md).

Two further defects were diagnosed using real clinical fixtures: black-bar OCR
hallucinations, and empty `Cliente:`/`Domicilio:` fields consuming the next form
label as their value. The latter was corrected in the underlying recognizers,
with tests retaining legitimate values on the following line. Damaged labelled
OCR fields receive uncertain protected candidates, without changing their text
or claiming valid checksums. Updated rules carry `rules-0.2` provenance; v0.1
score calibrators reject them rather than silently applying an old mapping.

## Actual validation

- **208 tests passed**, including real patched Spanish OCR, concurrent calls,
  Spanish accents, corrupt/missing language data, timeouts, malformed TSV,
  native/scanned PDF processing, actual pixel encoding, tampering, hidden text,
  attachments/annotations/metadata, source changes, limits, no overwrite, policy
  semantics, old-calibration rejection and semantic review gates.
- Ruff lint/format and Mypy pass. The base package still has no mandatory
  runtime dependencies; optional backends import lazily.
- The executable example processed the curated clinical PDF through the public
  engine API and passed actual output verification with an explicitly selected
  rules-only removal policy. Default strict policy still requires semantic review.
- The Python dependency audit reports no known vulnerabilities. It does **not**
  audit the separate native binary graph. Native source/patch level, component
  versions, integrity and license evidence are recorded separately.
- Offline Python socket/DNS guards are tested. They are not a system-wide firewall
  attestation for arbitrary executables. The delivered native build has CURL off.

Machine: Windows, Python 3.11.9, Ryzen 7 5700G (8 physical/16 logical cores),
16.96 GB RAM. CPU-only; GPU and cloud execution were not used.

## Genuine end-to-end benchmarks

Sources: [primary session](../benchmarks/results/pdf-ocr.json),
[degraded/repeated session](../benchmarks/results/pdf-ocr-challenge.json), and
[methodology](pdf-ocr-benchmark-methodology.md). Seed 1729, 216 DPI, `spa+eng`,
PSM 6, LSTM mode 1, one OCR thread. Each fixture page has nine known sensitive
values and a retained amount. Full transformation timing includes native analysis,
OCR, masking, fresh PDF writing, encoded-pixel verification, rerender and output
OCR. Additional independent benchmark checks are excluded from that timing.

| Workload | Pages | End-to-end | Pages/s | Sampled peak parent/tree RSS | Release status |
| --- | ---: | ---: | ---: | ---: | --- |
| Native clinical PDF | 100 | 117.947 s | .848 | 253.17 / 303.39 MB | REVIEW_REQUIRED |
| Clean scanned collection | 12 | 12.879 s | .932 | 264.22 / 312.91 MB | REVIEW_REQUIRED |
| Mixed native/scanned PDF | 6 | 6.412 s | .936 | 265.69 / 314.99 MB | APPROVED under explicit rules-only policy |
| Blur/contrast/skew scans | 3 | 3.432 s | .874 | 212.51 / 270.16 MB | REVIEW_REQUIRED |

All **2,420 known sensitive-word regions across 1,089 planted entities** passed
the independent actual-raster black-pixel test. This test uses fixture drawing
geometry tightened to source ink, not detector-selected masks or OCR absence.
Each expected word rectangle must be at least 99.5% near-black; the observed
minimum was 100%. No original text layer, planted metadata, annotations or
forbidden catalog features survived in the examined outputs. These are
fixture-specific observations, not a claim about unannotated sensitive content.

Source OCR on the 100 native pages had **CER .0127% / WER .1087%**. Exact
category/value recovery was 897/900 (**99.67% recall**): three emails were
transcribed differently. All 100 email pixel regions were nevertheless removed
by combined native/OCR protection; uncertainty correctly kept the document in
review. The clean scanned, mixed and three challenge fixtures had zero CER/WER
under the stated normalization, but low OCR confidence still required review for
the scanned/challenge runs. These easy synthetic pages are not representative
clinical-domain recall estimates.

The detection metric is whole normalized gold-value matching, **not original
layout exact-span F1**. Native precision/recall/F1 were .8899/.9967/.9403; the
other three sets were .9000/1.0000/.9474. Nested/partial detections can count as
additional unmatched predictions. The JSON retains per-type recovery and scores.

All **118 normal pages** had their amount confirmed in the additional output OCR
check, and zero observed residual gold values. On the three degraded pages,
independent raw-black-bar output OCR could not read page 3. Its residual total is
therefore **null/UNKNOWN**, its additional overall check is false, and the amount
on that page is unconfirmed by that OCR check. The separate known-pixel check
still passed all 60 challenge word regions. This failure was retained, not
reported as zero leakage or converted to approval.

Three additional repeated transformations of the same three-page native fixture
produced identical output PDF hashes. Median throughput was **1.0249 pages/s**;
individual run times were 2.927, 2.848 and 3.183 seconds. Full workloads have one
timed repetition each. Background load, initialization and document content affect
results; no universal throughput or speedup claim is made.

Results span two explicitly recorded sessions. The first completed 118 pages
before the extra challenge-output checker interrupted final bookkeeping; its
Python network-denial guard was active but its final attempted-connection counter
was not persisted. The resumed challenge/repeat session completed and recorded
zero Python connection attempts. No absent counter is fabricated as zero.

RSS is sampled every 10 ms. Process-tree values include live OCR children and
can miss transient peaks or double-count shared pages. Baselines within a session
share an interpreter, so RSS is not isolated per-workload allocation. The engine's
memory budget is raster admission, **not** a hard RSS/process-tree limit. Decoded
page caches are released, but compressed parser objects/native allocations remain.

## Use and limitations

See `examples/pdf_redaction.py`, `examples/policy-pdf-local.yaml`, the main CLI's
explicit OCR options, and the [local setup](local-ocr.md). Synthetic before/after
PDFs in `examples/pdf/` were rendered with Poppler and visually reviewed: fields
are physically blacked, amounts/title/footer are legible and layout is retained.

The output deliberately loses searchable/selectable text, vectors, accessibility
structure, forms and links. Initial support excludes rotated/cropped/scaled page
geometry, encryption, signature-bearing PDFs and interactive widgets/forms.
PDF operators are `redact`, `suppress` and `keep`; other operators are unsupported.
OCR can still miss unfamiliar data, and native parsers are not an OS sandbox.
Faces, handwritten signatures and barcode/QR payloads are outside this text/OCR
detector's coverage; those pages need separate detectors or private visual review.
Default semantic-model requirements remain; model presence does not certify its
quality. Stable layout and remaining data can permit linkage/reidentification.

Next priorities are independent real-world Spanish/Mexican holdouts, broader
degradation/layout coverage, native security maintenance, supported geometry
extensions and independently protected durable verification receipts. No remote
publication, automatic customer-model activation or guaranteed anonymity is implied.
