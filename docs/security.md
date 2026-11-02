# Security and threat model

## Boundaries

Documents and datasets can contain direct identifiers, quasi-identifiers,
credentials, hostile archives, malformed Unicode and hidden Office/PDF content.
The intended user is an application operating on local files in a private
directory. Attackers may control document bytes, not trusted Python code, model
directories, keys or policy configuration. User-defined regex, transformations
and model adapters run trusted local code; they are not a sandbox.

No generative inference, paid service, telemetry, automatic model download or
document upload exists in the implementation. Installed dependencies/assets are
required for optional functionality. Package installation, dependency auditing,
and explicit development-only model acquisition use the network; detection does
not. Tests deny sockets for the base pipeline and an actual local Spanish model.

## Release controls

- Strict defaults require an explicitly configured semantic adapter. Rules-only
  output is REVIEW_REQUIRED even with no detected findings. The caller may
  explicitly choose `Policy.strict(require_ner=False)`; this accepts narrower
  coverage, not anonymous data. Adapter presence is a configuration check, not a
  guarantee of model quality. Evaluate the adapter on a representative holdout.
- Every implemented file transformation reopens and scans the generated content.
  Residual findings outside explicit keep/exemption rules block release. The
  bounded diagnostic sample is filtered only after checking effective domain
  rules, so many permitted findings cannot hide a later disallowed one.
- Non-keep operators that return the exact sensitive source span unchanged fail.
  Short partial masks fully replace their content. Partial masks, date shifts,
  generalization and stable pseudonyms retain information and can permit linkage.
- Office rewriting and automatic standalone image release cannot return APPROVED.
  Supported PDFs use new raster-only reconstruction, closed object grammar and
  actual decoded-pixel/mask verification plus rerender/OCR. Source content is not
  copied; verified constant black regions alone can be whitened in temporary OCR
  input, preventing bar hallucinations without exempting retained pixels.
  Unsupported PDF geometry/forms/signatures remain fail-closed. Image pixel replacement verifies real raster pixels and removes
  metadata, but still requires independent OCR/review. Missing OCR makes an
  image-only PDF incomplete, and `scan()` refuses to imply complete coverage.
- Standalone structured verification cannot prove whole-field identity removal
  without transformation context. Sensitive schema fields require review.
- Unknown policy keys and malformed nested values are rejected. The audit
  records a canonical SHA-256 policy fingerprint. Do not mutate trusted policy
  dictionaries concurrently while a processing operation is running.

## Keys, privacy and logs

Pseudonyms use HMAC-SHA256 with explicit >=256-bit secret keys and 160-bit
Base32 tokens. Scope components are unambiguously framed and include tenant
context. Per-document, dataset, tenant and session scopes have distinct domains.
Canonicalization uses Unicode NFC and intentionally retains case. Changing the
key or scope changes the linkage namespace. No reversible mapping store exists.

Keys are supplied by the caller; use a secret manager or protected OS storage.
Do not put keys in a command line, repository or audit. Key rotation, encrypted
storage, ACL management, revocation, multiuser isolation and backup policies are
the host application's responsibilities. There is no KMS integration.

The library does not log source text. CLI output contains aggregate counts and
safe status codes. Model/custom transformation failures are sanitized at the
adapter boundary. Findings expose source locations deliberately, including table
column references; these are private API data, not safe public log content.
`Result.audit_dict()` excludes original text, findings and filenames. Audit
hashes and aggregate categories can themselves be sensitive in some contexts.

Original files are not altered. Temporary candidates use the destination
directory's access controls and are deleted on failure. Callers must secure that
directory and exclude it from automatic synchronization. Deletion is not secure
physical erasure. Python cannot reliably erase all plaintext copies from memory.
DocumentGraph, pandas/Polars and OCR objects intentionally hold private data.

## Hostile inputs and limits

Readers cap input and expanded ZIP sizes, member counts, compression ratios,
pages and image pixels; reject entity declarations and unsafe archive members;
and flag encrypted, active, embedded or unextracted content. Empty/invalid OCR
results, NaN confidence and invalid raster boxes fail explicitly. JSON duplicate
keys and nonfinite numbers are rejected, preventing hidden overwritten values.
CSV row widths are checked. Output paths cannot overwrite existing files.

These guards reduce common abuse; they are not complete parser isolation. Native
image/PDF libraries and third-party models have their own attack surfaces.
Run untrusted inputs in resource-constrained worker processes or containers with
OS-level network restrictions. Current memory budgets are not hard RSS caps.
User regex patterns require independent ReDoS review; arbitrary trusted regex
does not receive a reliable timeout in the standard Python engine.

## Detection limits

No automated detector proves the absence of unknown PII. Rules miss unlabelled
names, free-form addresses, unknown secrets, multilingual variants, novel
identifiers and domain-specific medical relationships. OCR can miss content or
misread identifiers; damaged-ID candidates are not silently corrected into
validity. Office revision text is scanned but automatic rewriting is unsupported.
Native graph PDF extraction cannot prove visual/text equivalence or locate every glyph.
The PDF removal backend uses its separate explicit character/glyph mapping and
refuses unsupported geometry. It trades away searchability/vector structure,
preserves original files, and rehashes the source before release. These controls
verify selected removal, not detection completeness.
Exact repeated mention grouping does not establish person identity or resolve
ambiguous aliases. Quasi-identifier flags are heuristics, not measured attack risk.

Training/model files can retain private n-grams. Joblib/pickle assets can execute
code; load only authenticated, trusted local files. Hashes detect modification,
not publisher identity. Critical recall promotion gates depend on representative,
honest held-out metrics and never activate models by themselves.

## Local security validation

Regression cases cover domain-aware release gates, residual-sample saturation,
scope delimiter collisions, unchanged transforms, nested policy mistakes,
pandas MultiIndex leakage, lossy boolean casts, socket-denied inference, hidden
OOXML strings, duplicate archives, bad OCR geometry and malformed files.
`docs/dependency-audit.json` records the final pip-audit response; inventory and
native/model-license qualifications are in `docs/third-party-licenses.md`.
An audit with no known advisories is not evidence of vulnerability absence.
The locally compiled OCR runtime is Tesseract 5.5.4 with pinned language/native
assets and CURL/archive/legacy/graphics disabled. Native dependency hashes and
licenses are recorded separately; pip-audit does not audit those binaries.
Faces, handwritten signatures and barcode/QR payloads are outside current text/OCR
detection coverage. Use separately evaluated detectors or private visual review;
successful removal of detected text does not cover these visual identifiers.
