# Jointly verified PDF and JSONL export

The RAG export API creates one new local directory with three fixed filenames:

```text
document.safe.pdf
document.safe.jsonl
document.audit.json
```

The output directory is explicit. Original filenames, sender addresses, subjects,
private source metadata and original detected values are not audit fields or
document identifiers. Document IDs use fresh cryptographically random values,
not a predictable hash of source text. The directory and its artifacts still
contain potentially linkable layout/retained information and must be protected.

## API

```python
from pathlib import Path
from deidflow import DeidEngine, Policy
from deidflow.ocr import TesseractOCR

runtime = Path("../../work/tesseract-5.5.4").resolve()
engine = DeidEngine(
    ocr=TesseractOCR(
        executable=str(runtime / "bin/tesseract.exe"),
        tessdata_dir=runtime / "share/tessdata",
        language="spa+eng",
        psm=6,
    )
)
result = engine.deidentify(
    "document.pdf",
    output="new-private-bundle-directory",
    outputs=["pdf", "jsonl"],
    policy=Policy.strict_pdf(),
)
if result.release_approved:
    safe_jsonl = result.safe_jsonl
    safe_pdf = result.safe_pdf
    audit_path = result.audit_path
```

`Policy.strict_pdf()` physically removes selected content and requires an
evaluated local semantic adapter before automated approval. Selecting
`Policy.strict_pdf(require_ner=False)` explicitly accepts a narrower rules-only
gate. It is useful for synthetic fixtures and reviewed deployments, not a claim
that arbitrary unknown PII is absent. A model's presence is not a certificate of
its quality. Categories configured as `keep` remain intentionally retained.

The direct API is `deidflow.rag.export_pdf_bundle(source, output_dir, engine=...,
policy=..., require_table_structure=False)`. Existing PDF-only API calls retain
their previous output-file semantics. Joint output requires a new directory;
no existing directory or file is overwritten.

The CLI accepts the same joint export:

```console
deidflow deidentify document.pdf --output new-private-bundle --outputs pdf jsonl --policy examples/policy-pdf-local.yaml --ocr-executable ../../work/tesseract-5.5.4/bin/tesseract.exe --tessdata-dir ../../work/tesseract-5.5.4/share/tessdata
```

Private Gmail documents must be processed only by the separately executed local
runner, outside the coding-agent session. Do not use agent tools to inspect
private inputs, outputs, annotation excerpts or JSONL. See the private-data
boundary and Gmail instructions for the separate operational workflow.

## One policy decision, two content representations

JSONL is **not** an export of raw native PDF text. It is generated only from OCR
of the actual reconstructed output pixels, after decoded-raster hashes, mask
pixels and actual rerendering have passed verification. The temporary OCR image
can whiten a removal region only after every actual rendered pixel there is
proved solid black. Source text, source findings and original native spans do
not reach the structured-output callback.

The callback streams candidate records into a private staging directory and
records canonical per-page hashes. It does not publish them or grant approval.
Any remaining sensitive finding can still block the whole document. Empty pages
are preserved only according to the PDF backend's existing blank/fully-removed
pixel proof, never merely because OCR returned nothing.

The JSONL candidate is then independently reopened and checked for:

- Exact allowlisted schemas; duplicate keys, unknown fields and nonfinite values
  are rejected rather than ignored.
- Consecutive page coverage, a consistent random document ID, size/pixel/page
  budgets and finite in-bounds coordinates.
- Line/chunk order and previous/next links, token spans and nonwhitespace text
  coverage. Text outside the verified line/token geometry is rejected.
- Canonical page hashes matching the actual verified-output callback, preventing
  an accidentally copied raw/unlabelled source value from passing simply because
  a second detector fails to recognize it.
- A separate sensitive-content scan under the effective policy/domain.

The PDF and JSONL hashes are checked again before publication. Changing either
artifact after its own verification blocks the bundle. The audit records both
sanitized artifact hashes, the policy fingerprint, fixed verification flags,
status, counts and allowlisted issue codes. Arbitrary upstream strings cannot
be copied into the audit. The original source path/text is not an audit field.

PDF success alone never approves JSONL. PDF and structured verification must
both pass; uncertainty in either representation requires review, and a failure
in either blocks the bundle. `release_approved` is the configured automated gate,
not a guarantee of anonymity or a statement about unidentified visual content.

## Structure and table limitations

Each JSONL record represents one page and includes sanitized text, page/raster
dimensions, reading-order lines, token offsets/bounding boxes and chunk links.
Text exists once at page level; line/token offsets reference it. These preserve
available horizontal and vertical layout relationships without copying original
source headers or cell values outside the shared physical policy decisions.

This version does **not** claim reliable table reconstruction: `tables` is empty
and `structure_status` is `lines_only`. Merged cells, multi-page tables, semantic
column assignment and true cell relationships remain unsupported. If a consumer
requires that structure, request `require_table_structure=True` (CLI
`--require-table-structure`). The bundle becomes `REVIEW_REQUIRED` with
`RAG_TABLE_STRUCTURE_UNAVAILABLE`; no fabricated table is presented as verified.

The output PDF remains image-only and loses original selectable text, vector
structure, forms/links and accessibility. JSONL provides a separately gated
retrieval representation. Unknown faces, signatures or QR/barcode payloads are
not made safe merely by exporting OCR text.

## Private staging and atomic publication

Before any candidate is written, staging is restricted to the current user:
0700 on POSIX and an explicit current-user SID ACL on Windows. PNG/OCR source
handling follows the local backend's pipe-based processing. Candidate PDF,
JSONL and audit files are held together until every document-level gate finishes.

Publication renames the entire directory atomically without replacing an
existing destination: Windows exclusive directory rename and Linux
`renameat2(RENAME_NOREPLACE)`. If the platform cannot supply exclusive atomic
publication, export fails closed. macOS/other platforms currently require a
separately implemented publication primitive. A destination created concurrently
is preserved. Failures clean only the exact staging directory created by this
operation after verifying its parent, name and filesystem identity; persistent
user directories/files are never removed.

Review-required bundles may be inspected privately. Blocked/unsupported bundles
have no final artifacts. Consumers must check `release_approved` and the audit,
not infer approval from a path or a filename containing `safe`.

`verify_rag_jsonl(path, engine=..., policy=...)` independently validates and
rescans an existing structured file, but it cannot reconstruct source receipts.
It therefore returns at least `REVIEW_REQUIRED` without the internal export
context, even if no finding is detected. Caller-provided arbitrary hashes are
not a public substitute for actual PDF-to-JSONL provenance.

## Local validation

`tests/test_rag_export.py` covers real two-page Spanish OCR with Python sockets
denied, native-canary removal, shared policy gates, PDF/JSONL tampering, raw-text
injection after PDF success, missing receipts, strict metadata/line/token schema,
multi-line relationships, duplicate keys, bounded records, atomic publication
races, cleanup, no overwrite, unknown audit strings and table-dependent review.
Mechanical adapter tests prove serialization/orchestration behavior only; they
are not OCR/detection accuracy estimates. All tests use synthetic fixtures.
