# Format extraction and release boundaries

`deidflow.readers.read_document(path, max_bytes=64*1024*1024, ocr=None)`
returns a `DocumentGraph`. Each finding points to one fragment and a half-open
Python Unicode character span within that fragment. The graph is never rendered
through Markdown. `complete=False` and `issues` signal extraction gaps; an empty
finding list on an incomplete graph must never approve a release.

| Format | Extraction | Automatic output |
|---|---|---|
| UTF-8 TXT | Exact text, including original CR/LF | See text engine |
| JSON/JSONL | All string keys/values and numeric values, ordinal JSON locations | See structured engine |
| CSV/TSV | All headers and cells; quoted multiline cells preserved | Use streaming table engine for large files |
| DOCX | OOXML paragraphs, tables, revisions, headers, footers, footnotes, endnotes, comments, property metadata, field instructions, external relationship targets | In-place DOCX rewrite, verified by rereading (see below) |
| XLSX | Visible/hidden/very-hidden sheets, cells, formulas and cached values, comments, headers/footers, names and metadata | Unsupported in-place release |
| PDF | Native pypdf text, page coordinates, Info metadata and annotation text; selective page OCR when configured | Lossless image-only reconstruction with physical removal and verified output; supported geometry only |
| PNG/JPEG/TIFF | Every frame through explicit local OCR adapter | Separate pixel operator; always review required |
| Parquet | All flat columns through bounded Arrow batches; graph size limits apply | Automatic Parquet rewrite unsupported |
| DataFrames | See structured engine | See structured engine |

## DOCX and XLSX

The readers use Python's standard ZIP/XML implementations and do not need Word,
Excel, python-docx or openpyxl. They validate archive size/member/ratio limits,
reject duplicate members and XML DTD/entity declarations, and never extract ZIP
members to filesystem paths. Limits cover 10,000 members, 64 MiB per member by
default, and the smaller of 8× the input byte limit or 512 MiB total expansion.

Tables preserve source part, row/column/cell references and table dimensions.
XLSX physical row numbers are one-based and spreadsheet references remain A1
style; CSV rows and DOCX table rows/columns are zero-based. DOCX page numbers are
not inferred: OOXML does not contain reliable rendered page boundaries.

Data-bearing Word fields (any field other than layout fields such as `PAGE`,
`NUMPAGES`, `TOC`, `REF` or `SEQ` without quoted arguments), spreadsheet
formulas/defined names, drawings, external relationships, embedded objects,
active content, Office images and package thumbnails force review. Field
instructions, including `fldSimple` instructions, are scanned.
All recognized text is still returned. Both deleted and inserted revision text
are scanned. Unreferenced XLSX shared strings are scanned as source parts, since
deleted cell values can remain in the archive. Invalid negative shared-string
references and inconsistent CSV/TSV row widths are rejected. No claim is made
that every possible proprietary extension or
embedded binary is covered.

## DOCX output

Only explicitly supported package parts are accepted for rewriting. An unknown
part, even an unreferenced XML or binary file, blocks the operation without
publishing an output. This prevents hidden package contents from bypassing the
text rescan; it can also reject documents with unsupported vendor extensions.
Relationship IDs must use `rId` followed by digits, and retained relationships
must point to an existing, supported part. Package relationships and content-type
declarations are rebuilt; XML comments, processing instructions and ZIP directory
entries are discarded. These checks do not establish complete coverage of every
possible XML extension inside a supported part.

`engine.deidentify("in.docx", output="out.docx")` (CLI `deidflow deidentify`)
edits the package in place, so styles, tables, numbering and page layout are
kept. Text is scanned per part (body, each header and footer, footnotes,
endnotes, comments) with paragraphs and table cells joined, so labels in one
cell give context to values in the next; a value split across differently
formatted runs is replaced in its first run. Before writing, the writer:

- accepts tracked changes (deleted and moved-from text is dropped) and removes
  revision and comment authors, initials, dates and commenter account details;
- removes personal properties (`creator`, `lastModifiedBy`, created, modified
  and printed dates, `Company`, `Manager`, `HyperlinkBase`) and transforms the
  remaining property, custom-property and custom-XML text;
- removes the package thumbnail (a rendering of the first page), every
  external relationship (hyperlinks become plain text, attached templates are
  dropped), mail-merge settings and data-bearing field codes (their displayed
  result text stays and is scanned); layout fields stay;
- transforms alternative text (`descr`, `title`) and document variables;
- with `office_media="remove"` (default, CLI `--office-media remove`) removes
  images, charts, diagrams, embedded objects and macros, which cannot be
  checked without OCR. `"keep"` copies them, and the result is `BLOCKED` as
  incomplete coverage.

The output is then read back with the same reader and rescanned; residual
findings, extraction gaps or uncertain source findings block or require review
exactly as for text. `result.audit["office_removed"]` counts what was removed.
Only `.docx` is rewritten; `.doc`, `.docm`, `.dotx` and XLSX output remain
unsupported. A tested output opens in LibreOffice; Microsoft Word was not
available for testing.

## Native PDF and OCR

Install `deidflow[pdf,ocr]` for pypdf, pypdfium2 and Pillow. The
Tesseract binary and requested `spa`/`eng` traineddata must already exist locally.
The adapter never installs assets or contacts a service:

```python
from deidflow.ocr import TesseractOCR
from deidflow.readers import read_document

ocr = TesseractOCR(
    language="spa+eng",
    executable=r"..\..\work\tesseract-5.5.4\bin\tesseract.exe",
    tessdata_dir=r"..\..\work\tesseract-5.5.4\share\tessdata",
)
graph = read_document("scan.pdf", ocr=ocr)
assert graph.complete, graph.issues
```

The PDF reader extracts native text first. Sparse/corrupt text or image/form
resources trigger OCR for that page. Native text-only pages avoid rasterization.
Routing is conservative and works at page granularity, not region granularity;
images such as logos can therefore trigger full-page OCR. `high_throughput`
renders routed pages at 144 DPI, while the default renders at 216 DPI. OCR is
never silently substituted with an empty successful result. Missing OCR marks
the graph incomplete; execution failure raises `OCRError`.

Native PDF bounding boxes describe page containers, **not glyph-accurate masks**.
Native span offsets index extracted text, not PDF content-stream bytes. OCR token
metadata records character offsets, confidence and top-left-origin boxes; PDF OCR
boxes are scaled into page points. These records can be inspected to locate
findings, but cannot justify native PDF overlay redaction. The separate
[PDF reconstruction backend](pdf-redaction.md) uses PDFium glyph mapping plus
OCR and new image-only pages, never an overlay on original content. PDFs with forms,
attachments/actions or annotations require review. Rotated/cropped pages and
complex resource trees require additional specialized QA.

OCR confidence below 50 by default marks the graph incomplete. Low-confidence
words remain in the text; they are not dropped to inflate apparent quality.
Tesseract execution has a timeout and explicit shell-free process arguments;
PNG/TSV travel through pipes without process-global executable settings or
sensitive temporary OCR files. OCR engine confidence is not calibrated entity
confidence. OCR text reconstruction introduces spaces and line breaks, so spans
refer to that reconstruction, linked back to token boxes.

## Pixel replacement

```python
from deidflow.redactors import redact_image

result = redact_image("input.png", "review.png", [(10, 20, 150, 70)])
assert result.pixels_verified
assert result.status == "REVIEW_REQUIRED"
```

The operator accepts explicit top-left-origin raster masks, replaces the actual
pixels with solid black, flattens alpha onto white, removes ancillary metadata,
writes lossless RGB PNG and reopens it to verify every masked pixel. It rejects
in-place overwriting, multi-frame images, non-PNG outputs, empty or invalid
masks, and rasters above 40 million pixels. Coordinates are padded by two pixels
by default. This verifies replacement, not detection completeness. Re-OCR the
actual generated image, rescan it and have a reviewer inspect it before release.
PNG compression and embedded metadata are not treated as trustworthy OCR text.

## Resource and security limits

The ordinary document reader intentionally loads bounded documents. Use
streaming readers for large CSV/JSONL/Parquet workloads. Text is strict UTF-8;
malformed Unicode fails explicitly. Duplicate JSON keys and non-finite JSON
numbers fail explicitly instead of silently dropping data. Encrypted documents,
legacy DOC/XLS, PPTX and unknown formats are unsupported.

`iter_parquet_batches(path, batch_size=1024)` yields Arrow RecordBatches without
loading the complete table. Pass every column for complete coverage; selecting
columns intentionally limits coverage. The graph reader limits extracted cell
text to `max_bytes` and 100,000 fragments. Nested fields, undecodable binary
fields and custom schema metadata require review; readable metadata are scanned.
An empty file's field names are still scanned. Arrow's internal parser buffers
are outside the graph size limit, so use process limits for hostile files.

The original `scripts/ocr_probe.py` records missing-asset failure behavior from
v0.1. For current installed OCR and real character/word-error, physical-pixel
verification and throughput measurements, use `scripts/benchmark_pdf_ocr.py` and
the [v0.2 OCR/PDF report](pdf-ocr-report.md). See [local setup](local-ocr.md) for
the pinned, compiled Tesseract 5.5.4 runtime and explicit Spanish data paths.

These checks reduce common abuse; they are not an operating-system sandbox.
Adversarial compressed PDF streams, recursive PDF structures, malformed image
decoders and executable OCR dependencies remain attack surfaces. Enterprises
should run untrusted parsers/OCR in an isolated worker with CPU, wall-time, memory
and filesystem limits. The current Python API does not enforce an OS-level
process memory cap. Parser errors contain fixed messages, never source text.

## Backend licensing

- Python stdlib ZIP/XML: Python Software Foundation license.
- pypdf: BSD-3-Clause; native extraction only.
- pypdfium2: Apache-2.0/BSD-3-Clause wrapper, bundled PDFium BSD-style third-party
  components; distribute its bundled notices with any commercial redistribution.
- Pillow 13: MIT-CMU and linked codec notices.
- Tesseract: Apache-2.0; separately review installed traineddata
  and executable distributions, including their bundled notices.
- PyMuPDF is not used and is not a dependency.

Review the resolved dependency inventory and actual installed asset licenses
before redistribution. No model-weight license is granted by DeidFlow.
The current OCR adapter does not depend on pytesseract; native libraries and
language weights stay outside Python distributions.
