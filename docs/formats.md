# Format extraction and release boundaries

`deidflow.readers.read_document(path, max_bytes=64*1024*1024, ocr=None)`
returns a `DocumentGraph`. Each finding points to one fragment and a half-open
Python Unicode character span within that fragment. The graph is never rendered
through Markdown. `complete=False` and `issues` signal extraction gaps; an empty
finding list on an incomplete graph must never approve a release.

| Format | Extraction | Automatic output |
|---|---|---|
| UTF-8 TXT, Markdown, log | Exact text, including original CR/LF | Same format (`.txt`, `.text`, `.md`, `.log`) |
| E-mail (`.eml`) | Headers (RFC 2047 decoded), text and HTML bodies, attached messages, supported attachments read recursively | Rewritten message (see below) |
| HTML (`.html`, `.htm`) | Visible text as one stream, content attributes (`alt`, `title`, `href`, `value`, `content`...), comments, scripts | In-place rewrite by source offsets (see below) |
| JSON/JSONL | All string keys/values and numeric values, ordinal JSON locations | See structured engine |
| CSV/TSV | All headers and cells; quoted multiline cells preserved | Use streaming table engine for large files |
| DOCX | OOXML paragraphs, tables, revisions, headers, footers, footnotes, endnotes, comments, property metadata, field instructions, external relationship targets | In-place DOCX rewrite, verified by rereading (see below) |
| XLSX | Visible/hidden/very-hidden sheets, cells, formulas and cached values, comments, headers/footers, names and metadata | Supervised XLSX rewrite; always `REVIEW_REQUIRED` or `BLOCKED` |
| PDF | Native pypdf text, page coordinates, Info metadata and annotation text; selective page OCR when configured | Lossless image-only reconstruction with physical removal and verified output; supported geometry only |
| PNG/JPEG/TIFF | Every frame through explicit local OCR adapter | Separate pixel operator; always review required |
| Parquet | All flat columns through bounded Arrow batches; graph size limits apply | Automatic Parquet rewrite unsupported |
| DataFrames | See structured engine | See structured engine |

## Unicode detection and original offsets

Built-in rules and NLP adapters receive a detection view with Unicode format
controls (category `Cf`) removed and NFKC applied. Source text is retained;
findings project to complete original canonical clusters, including adjacent
inserted controls. Compatibility expansions and reordered combining marks do
not expose partially replaced original characters. Lexical features and boundary validation also use
source ordinal provenance, since NFKC merges `º`/`ª` with ordinary `o`/`a`.
Built-in models keep NFKC token coordinates while consuming this semantic
metadata. NLP routers/combinators forward it; external adapters retain the
existing `detect_batch` normalized-text interface.

Text, structured cells, Office, HTML and e-mail writers transform original spans
and reread the emitted artifact. A remaining format control between alphanumeric
characters yields `UNICODE_FORMAT_CONTROLS_REQUIRE_REVIEW` and prevents approval,
without inventing a sensitive entity. This fallback does not prove completeness
of detection. HTML entities are checked after decoding by the existing parser.

ASCII and already normalized identity views allocate no maps. Nonidentity views
bound decomposition/tracing to one million characters by default; the NLP path
also checks its batch mapping budget. These are admission estimates, not an RSS
or process-isolation guarantee. Unicode behavior uses the interpreter's Unicode
database and is recorded with the candidate evidence.

The corrected candidate retains master predictions on synthetic validation and
MEDDOCAN dev; Gretel evidence remains pending. See [the audit handoff](audit/unicode-normalization/README.md).
ODT/ODS coverage remains pending the separate OpenDocument PR.

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
formulas and defined names that hold string literals or external-workbook
references, drawings, external relationships, embedded objects, active content,
Office images and package thumbnails force review. Formulas such as
`SUM(B2:B9)`, print areas and table definitions are scanned without forcing
review. Spreadsheet header/footer formatting codes (`&L`, `&"Arial,Bold"`) are
blanked before scanning. Field
instructions, including `fldSimple` instructions, are scanned.
All recognized text is still returned. Both deleted and inserted revision text
are scanned. Unreferenced XLSX shared strings are scanned as source parts, since
deleted cell values can remain in the archive. Invalid negative shared-string
references and inconsistent CSV/TSV row widths are rejected. No claim is made
that every possible proprietary extension or
embedded binary is covered.

## E-mail output

`engine.deidentify("mensaje.eml", output="mensaje.safe.eml")` rewrites a MIME
message:

- **Headers** are kept on an allowlist. In `From`, `To`, `Cc`, `Reply-To` and the
  other address headers each display name is transformed as a person and each
  address as an e-mail; `Subject`, `Comments` and `Keywords` are scanned as text;
  `Message-ID`, `In-Reply-To`, `References` and `Content-ID` become keyed
  pseudonyms (`<df…@deidflow>`). Thread IDs are stable within a message; pass the
  same explicit engine key to preserve threading across separate messages.
  Without a key, each rewrite uses a fresh key. Trace and vendor
  headers (`Received`, `X-*`, `DKIM-Signature`, `Authentication-Results`…),
  which carry IP addresses, host names and mailbox details, and `Date` are
  removed.
- **MIME structure** headers are rebuilt from known media types, validated
  transfer encoding, disposition and `MIME-Version: 1.0`. Text is decoded strictly
  and rewritten as UTF-8. Unknown multipart subtypes are normalized to
  `multipart/mixed`; sanitized attachments receive the canonical type for their
  output format. Language tags, related-type metadata, other parameters,
  comments and file names are dropped and boundaries regenerated.
  Multipart preambles and epilogues (never displayed) are removed.
- **Bodies**: `text/plain` is rewritten as text and `text/html` as HTML (above).
- **Attachments** are renamed `adjunto-<n><ext>` and de-identified with the same
  engine and policy when their format is supported (text, Markdown, CSV/TSV,
  JSON/JSONL, HTML, DOCX, XLSX, PDF); a blocked or unsupported attachment is
  removed (`EMAIL_ATTACHMENT_REMOVED`) and one that needs review makes the
  message need review (`EMAIL_ATTACHMENT_REVIEW_REQUIRED`). Images, audio and
  video are removed with `office_media="remove"` (default). Attached messages
  are processed recursively, up to eight levels. Attachments share the message's
pseudonym scope and indexed-placeholder allocator, so `[CORREO_1]` in the body
and in an attachment is the same address and different people never share an
index.

Malformed transfer encodings, unsupported charsets and malformed encapsulated
messages block output rather than silently dropping undecodable bytes. Parsing
is bounded before recursive rewriting: eight levels, 512 parts, 8,192 headers,
65,536 characters per header value, 128 per header name, the configured
input byte limit and a cumulative decoded-payload limit. Headers, rewritten bodies
and expanded attachments share an output byte budget; the serialized message is
checked again. Extracted attachment text shares the reader's byte budget.

The output is reread (headers, bodies and attachments) and rescanned like
other formats; `audit["email_removed"]` counts what was removed. E-mail output
and standalone verification always require human review (`EMAIL_REVIEW_REQUIRED`).
Retaining uninspected media still blocks release; this review requirement does
not waive incomplete coverage.
During the writer's immediate rescan, exact message-ID and MIME-boundary spans
minted by that invocation are recognized only in their matching structural header
locations. This private, temporary provenance is not a public authorization
receipt or a syntax-based exemption. Body text, other header fields, and standalone
verification receive the full scan, including source values that look like
generated IDs or boundaries. Standalone verification can therefore conservatively
block a real output when its model flags these structural tokens; it cannot infer
their origin from their spelling.

## HTML output

`engine.deidentify("page.html", output="page.safe.html")` rewrites a conservative
static HTML subset at source offsets. Ordinary text, headings, tables and inline
formatting retain their layout; unsupported content is removed or rejected.
Visible text is scanned as one stream (block elements start new lines, table
cells are separated by spaces), so `<td>Nombre:</td><td>Ana</td>` keeps its label
context; a value split by inline tags (`<b>María</b> López`) or written with
character references (`L&oacute;pez`) is replaced across them, references whole.
Known content attributes (`alt`, `title`, `href`, `value`, `content`,
`placeholder`, `aria-label`...) are scanned one by one (`href="mailto:..."`
becomes `mailto:[EMAIL]`). URL percent escapes are decoded before scanning.
Unknown attributes, event handlers, `id`, `class`, `data-*`, resource/loading
attributes (`src`, `srcset`, `action`, `srcdoc`...), comments, scripts, declarations
and processing instructions are removed, including their names. Structural
attributes use bounded numeric values or finite enumerations. Unknown element
names, malformed attribute syntax and unclosed script/style elements block output.

CSS is retained only when the complete block matches a small static formatting
grammar: known HTML tag selectors; bounded lengths; fixed colors, font families
and layout keywords. CSS comments, escapes, class/ID selectors, URLs, generated
content, custom properties and extension syntax cause the entire affected
stylesheet or style attribute to be removed. This deliberately loses some styling
and remote images; it does not claim general CSS or browser execution coverage.

The output is reread and rescanned. Both output and standalone verification require
human review (`HTML_REVIEW_REQUIRED`); unsupported retained source channels mark
coverage incomplete and block release. Input must be UTF-8. These fictional
regression tests establish handling of the documented channels, not universal
anonymity or completeness for every HTML extension or obfuscated identifier.

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
Only `.docx` is rewritten; `.doc`, `.docm` and `.dotx` remain unsupported. A
tested output opens in LibreOffice; Microsoft Word was not available for
testing.

## XLSX output

`engine.deidentify("in.xlsx", output="out.xlsx")` edits the workbook in place.
The source is preserved. Every successfully transformed XLSX candidate and
standalone `verify()` result remains `REVIEW_REQUIRED`; a clean rescan does not
establish complete Excel coverage. Do not automatically distribute candidates.

- The first nonempty row of each sheet is its header. Columns the profiler
  recognizes from header and values (`Nombre`, `DNI`, `RFC`, `Teléfono`,
  `Correo`...) are transformed whole, as for CSV. Every other cell is scanned
  as `Header: value`, so labelled-value rules and the tagger see the field
  name. Numbers are scanned as text, so a phone or ID stored as a number is
  found.
- Changed cells become inline strings and keep their style. The shared-string
  table is rebuilt from the strings still referenced, so replaced values and
  orphaned strings of deleted cells do not stay in the file.
- Formulas that hold a string literal or an external-workbook reference, or
  whose cell changed, are replaced by their cached (transformed) value; cell
  arithmetic such as `SUM(D2:D3)` stays. The calculation chain is removed and
  rebuilt by Excel. Defined names with literals are removed; print areas stay.
- A sheet whose name contains a finding is renamed `Hoja<n>`, and formulas,
  print areas and the sheet list in the document properties follow it.
- Comment authors become `DeidFlow` and comment text is transformed; header
  and footer text is transformed around its formatting codes; table column
  names follow their header cells.
- Pivot tables and their caches (which hold copies of the data), external
  links, data connections and query tables, threaded comments and their
  people list, printer settings, the saved-folder path and shared-workbook
  user names are removed. Pivot tables therefore become their displayed
  values. With `office_media="remove"` (default) drawings, charts, images,
  form controls and embedded objects are removed as well.
  This includes VML comment shapes; comment text remains, but its legacy visual
  shape is not retained. Keeping any media blocks output rather than approving
  uninspected bytes.

Unknown ZIP parts, invalid roots/relationships, duplicate cells and unreferenced
worksheets block output. Known package relationships and content types are
rebuilt; directory entries and XML comments/processing instructions are omitted.
Sparse-sheet expansion is checked against the configured memory budget.
In-cell images and dynamic-array metadata (`xl/richData`, `xl/metadata.xml`) are
outside the supported package set and block transformation.

The reread uses the same detectors. Custom number formats, named definitions and
Excel-specific extension semantics are not exhaustively sanitized or evaluated;
their presence is one reason human review remains mandatory. The first-row
header heuristic also needs review for title rows, sparse layouts and merged
cells. Formatting and ordinary arithmetic are retained where supported; neither
the output nor the test counts establish anonymous data.

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
