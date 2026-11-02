# Local PDF removal by raster reconstruction

DeidFlow can remove selected sensitive content from supported native and scanned
PDFs using **new image-only PDF reconstruction**. This is not an overlay on the
original content. Every source page is rendered locally, scanned with explicitly
installed Spanish OCR, physically masked, written from new RGB pixels and
independently verified. No original PDF stream, text object, metadata, annotation,
attachment, JavaScript, hyperlink, layer or font is copied into the output.

The tradeoff is deliberate: the result loses searchable/selectable text, vectors,
forms, links, document signatures and original accessibility structure. Raster
quality is bounded by the selected DPI. The original file is preserved.

## Usage

Install `deidflow[pdf,ocr]`, provision the local executable/language data as
described in [local OCR setup](local-ocr.md), and provide explicit asset paths:

```python
from deidflow import DeidEngine, Policy
from deidflow.ocr import TesseractOCR

ocr = TesseractOCR(
    language="spa+eng",
    executable="/private/local/tesseract/tesseract.exe",
    tessdata_dir="/private/local/tesseract/tessdata",
    psm=6,
    threads=1,
)
engine = DeidEngine(ocr=ocr, pdf_dpi=216, pdf_max_pages=1000)
result = engine.deidentify("input.pdf", output="candidate.pdf")
if result.release_approved:
    consume_path = result.output_path
else:
    # REVIEW_REQUIRED candidates may be inspected privately. BLOCKED and
    # UNSUPPORTED results do not expose a final output file.
    print(result.audit_dict())
```

The PDF default is `Policy.strict_pdf()`: physical redaction, with a semantic
adapter required for automatic approval. Supplying an evaluated, explicitly
local NLP adapter can satisfy that configuration gate. Adapter presence is not a
proof of model quality. `Policy.strict_pdf(require_ner=False)` explicitly accepts
the narrower rules-only gate, used by synthetic throughput benchmarks.

PDF policies support **redact**, **suppress** and **keep**. Both removal actions
replace actual pixels with black. Placeholder insertion, pseudonyms, numeric/date
transformations, partial masks, generalization and custom operators return
`UNSUPPORTED`; they are never silently replaced by a different operator. Ordinary
`Policy.strict()` requests typed placeholders and is consequently not the PDF
policy. Domain overrides are applied during both detection selection and output
verification. Protected identifier candidates cannot be discarded by thresholds.

The direct function is also available:

```python
from deidflow.redactors.pdf import redact_pdf

result = redact_pdf(
    "input.pdf",
    "candidate.pdf",
    engine=engine,
    policy=Policy.strict_pdf(),
    dpi=216,
    padding=3,
    max_pages=1000,
    memory_budget_mb=256,
)
```

## Physical removal and verification

1. A strict native preflight rejects encrypted/signed/form PDFs and unsupported
   rotation, cropping or nondefault user-unit geometry. Input bytes and page
   count are bounded. The source SHA-256 is recorded before processing and
   checked again before release to detect changes during the operation.
2. Native text is read by PDFium's internal character codepoints with an explicit
   Python-index-to-PDF-character mapping. The implementation does not assume that
   extracted-text indices match glyph indices. Native findings use per-character
   geometry converted by the actual rendered bitmap's coordinate converter.
3. Every nonblank page is OCRed, including pages with native text. OCR findings
   map back to complete intersecting tokens, so a substring never leaves the
   remainder of a sensitive token visible. Configurable padding extends masks.
   Labelled fields damaged by OCR can be protected as uncertain candidates;
   values are not silently corrected or claimed to be registry-confirmed.
4. Selected native and OCR regions are replaced in a fresh RGB raster. A bounded
   streaming writer emits only a new Catalog, Pages, Page, image and image-draw
   stream grammar. It never calls a source-page clone/copy operation. Images are
   lossless Flate RGB; no original image metadata or text layer survives.
5. The encoded output is reopened with a separate PDF parser. The catalog,
   trailer, page tree, resources, image schema and drawing commands must match a
   closed allowlist. Each decoded output image must match the exact intended
   raster SHA-256; every pixel in every removal region must be RGB zero.
   Decoded page buffers are explicitly released after each verification page.
6. The actual generated PDF is independently rendered again with PDFium, then
   OCRed and scanned. OCR can hallucinate letters in black redaction bars. To
   avoid those false residuals, the OCR input may whiten a removal region only
   **after every actual re-rendered pixel in that region is proved solid black**.
   The output PDF is never whitened or modified by this step. A nonconstant pixel
   in a supposed removal region fails verification; intended coordinates alone
   cannot exempt any pixel from checking. All other rendered pixels are OCRed.
7. Disallowed residual findings block release. Low confidence, uncertain source
   findings, unresolved model boundaries or missing semantic coverage require
   review. Empty OCR is accepted only for an exactly white page, or after proof
   that all remaining pixels outside verified masks are white. An unreadable
   photograph, OCR execution error or missing language cannot become approval.
8. Only a nonblocked candidate receives the final filename, using atomic
   nonoverwriting link creation. In-place rewriting and existing outputs are
   rejected. Temporary candidates are removed on failure.

`audit` records page/raster dimensions, removal boxes, raster hashes, counts,
source/output SHA-256 and verification flags; recognized plaintext is excluded.
Layout and linkage metadata can still be private, so protect audit reports.
`APPROVED` means configured checks passed, never that every possible identity or
attribute is absent. Stable layouts, amounts and remaining clinical information
can still contribute to reidentification.

## Supported boundaries

The initial validated geometry is an unrotated page with matching MediaBox and
CropBox, zero lower-left origin and unit scale. Rotated/cropped/scaled PDFs,
encrypted PDFs, interactive AcroForms/widgets and signature-bearing PDFs return
`UNSUPPORTED`. No workflow silently invalidates a preserved signature or claims
an interactive form was retained. Attachments, Info/XMP metadata, ordinary
annotation payloads and invisible source text are removed by new reconstruction;
native hidden text inside a page is conservatively masked when detected.
Unsupported native glyph geometry blocks rather than leaving a finding unmasked.

Both a per-page raster admission estimate and a pixel ceiling are enforced.
The implementation processes one page at a time and does not retain all decoded
page pixels. Compressed PDF parsing, image codecs, native-library allocations and
the external OCR process are outside a hard Python RSS cap. These limits do not
replace operating-system sandboxing for hostile PDFs. PDFium is serialized with
a process-wide lock because separate documents are not safe concurrent entry
points; use bounded isolated processes for independently parallel native parsing.

Standalone `engine.verify("existing.pdf")` or `verify_pdf()` inspects actual
rendered pixels and findings, but cannot reconstruct the original source-to-mask
receipt. It returns at least `REVIEW_REQUIRED` without that internal context,
even when OCR finds nothing. The redaction operation performs the stronger
receipt-based checks while its candidate is private.

## Validation and benchmarks

`tests/test_pdf_redaction.py` exercises actual PDF encoding/decoding, native glyph
mapping, decoded pixel hashes, mask tampering, source mutation, metadata and
attachment removal, invisible text, annotation payloads, geometry refusal,
missing/failed OCR, residual findings, semantic policy gates, per-page decoded
buffer release, output cleanup and no overwrite. An explicitly provisioned local
Tesseract integration test runs with Python sockets denied. Mechanical adapter
tests do not serve as OCR-accuracy benchmarks.

The real benchmark in `scripts/benchmark_pdf_ocr.py` generates native, scanned and
mixed Spanish/Mexican documents with known gold. It reports actual OCR character
and word error, detection recovery, page throughput, sampled process-tree RSS,
status distribution and independent output pixel/gold checks. Source OCR errors
and uncertain protection are reported separately; an OCR substitute is not
credited as exact original-text recovery. See the benchmark report for measured
values, machine details, repeats and remaining limitations.
