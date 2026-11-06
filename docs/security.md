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
- Source uncertainty survives structured transformations, including JSON keys
  and inferred table fields. Low scores and unresolved model-window boundaries
  require review even when the transformed output has no detected residuals.
- DOCX rewriting checks supported package parts before transformation and
  rereads the candidate before release. Unknown parts, including orphan XML or
  binary payloads, block output rather than being silently copied. Supported
  DOCX output can be APPROVED; this is not proof of complete PII detection.
  XLSX rewriting validates a separate supported package set and always requires
  review, including standalone verification. Unknown parts block output; VML,
  drawings and cached/linked auxiliary parts are removed by default. Retained
  media blocks output. Custom formats and Excel extension semantics are not a
  certified anonymization surface; inspect candidates privately before use.
  Automatic standalone image release cannot return APPROVED.
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
key or scope changes the linkage namespace. The HMAC operator does not retain
a reversible mapping store. The separate opt-in `DeidSession` workflow can keep
an explicit vault, as described below.

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

Original files are not altered. PDF candidates receive current-user-only
permissions before any pixels are written; permission failure blocks processing
and closes the file before cleanup. RAG staging and private workflows also have
protected directories. Other temporary candidates use the destination
directory's access controls and are deleted on failure. Callers must secure that
directory and exclude it from automatic synchronization. Deletion is not secure
physical erasure. Python cannot reliably erase all plaintext copies from memory.
DocumentGraph, pandas/Polars and OCR objects intentionally hold private data.

## Local LLM sessions

The opt-in LLM workflow performs local pseudonymization only. `DeidSession`
never sends text or calls a provider. Exact NFC values may reuse issued tokens;
partial names and inferred aliases do not establish identity. Source token
collisions and unknown restoration tokens are rejected. An LLM can still misuse
a valid token, so inspect restored content privately; token membership is not
proof of attribution or model truthfulness.

Reversible sessions default to a plaintext in-memory vault. Supply an
`EncryptedVault` explicitly when required; an empty supplied vault is preserved.
The optional `vault` extra supplies cryptography. Persisted v2 vaults authenticate
their version, session ID, expiry and entries. Legacy v1 is rejected, and a
populated vault requires its matching allocator for resumption. Key storage and
OS clock integrity remain host responsibilities. Session close clears mappings;
this is not guaranteed physical memory erasure.

The proper-noun verifier is an optional text heuristic, not an independent
anonymity guarantee. Formats where it has not run explicitly require review.
Policy fingerprints now include this option; existing approval receipts must be
revalidated when changing application versions or policies.

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
validity. DOCX rewriting accepts tracked changes and removes deleted revision
text and personal revision metadata. XLSX output is a supervised candidate only;
other Office output remains unsupported.
Native graph PDF extraction cannot prove visual/text equivalence or locate every glyph.
The PDF removal backend uses its separate explicit character/glyph mapping and
refuses unsupported geometry. It trades away searchability/vector structure,
preserves original files, and rehashes the source before release. These controls
verify selected removal, not detection completeness.
Exact repeated mention grouping does not establish person identity or resolve
ambiguous aliases. Quasi-identifier flags are heuristics, not measured attack risk.

Training/model files can retain private n-grams. Joblib/pickle assets can execute
code; load only authenticated, trusted local files. `SpanTagger` model files are
JSON only: loading validates the schema, dimensions, finite weights, size
(256 MiB, also after decompression) and an optional SHA-256, and never executes
code. Their features are keyed 64-bit BLAKE2b digests and rare features are
dropped (`min_feature_docs`), but a dictionary attack can still confirm whether a
common token was a feature, so treat privately trained tagger files as sensitive.

Verification rescans ignore a finding only when every letter and digit it covers
lies inside DeidFlow replacement output. During `deidentify_text` that means the
exact output ranges of the applied placeholder, redaction, suppression,
pseudonym or generalization operators. Elsewhere (file verification, tables) it
means the known formats only: typed placeholders for taxonomy categories such as
`[PERSON]`, pseudonyms `[DF_TYPE_<32 base32 characters>]`, `[GENERALIZED]`,
redaction blocks and full masks. Arbitrary bracketed source text such as `[JUAN]`
or `[GODE561231GR8]` stays detectable. A finding that still covers any source letter or digit,
including the visible digits of a partial mask, keeps blocking release. The
rescan reuses the same detectors, so it cannot reveal what they missed:
`benchmarks/results/tagger/release-gate-*.json` measures how often approved
documents still contain gold sensitive characters. Hashes detect modification,
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
## Context and persistent-session controls (0.6)

`Policy.context()` and the domain packs require explicit human review by default.
The review API binds decisions to the original text, policy, declared/bound model
configuration and rebuilt output; `approve` and `source_complete` must both be
explicitly supplied. Residual, coverage and configuration failures still prevent
approval. Receipts can be HMAC authenticated with a caller-managed key; this
authenticates key possession, not a reviewer's real-world identity.

Session snapshots authenticate the allocator, values, graph, policy, model
binding and expiry together. Wrong keys, unknown fields, inconsistent mappings,
expired states and dangling graph references are rejected. Public graphs omit
original values but remain linkable and potentially sensitive. Exact equality
and compatible missing role/gender metadata do not prove two mentions refer to
one real-world person; explicit conflicts and ambiguity are not silently merged.
Keys and restored outputs must remain in the trusted local environment. Expiry
is an API policy, not erasure or revocation of copies held with the encryption key.

See [sessions](SESSIONS.md), [review](REVIEW_WORKFLOW.md) and
[audit guide](AUDIT_GUIDE.md) for trust boundaries and reproducible checks.
