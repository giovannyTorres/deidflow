# v0.3 local security review

Review date: 2026-11-02. This is a source/test and dependency review of the local
implementation, not an independent penetration test, compliance certification or
production approval. All work remained local; no repository, package, original
document, private dataset, endpoint or model was published.

Final PDF hardening restricts an empty ordinary-PDF candidate to the current user
before writing document pixels. An ACL error explicitly closes the descriptor,
returns a fixed blocked status and removes the owned candidate; a regression test
checks the Windows-relevant cleanup path. Protected RAG directories and private
workspaces retain their independent controls. Native glyph rotation is also
explicitly unsupported instead of assuming horizontal geometry. Scanned image
orientation/layout and non-text visual identity remain detection limitations.

## Evidence and scope

The private suite passed 65 authored synthetic tests at handoff:

```powershell
python -m pytest tests/test_private_gmail.py tests/test_private_annotation.py -q
python -m ruff check src/deidflow/private tests/test_private_gmail.py tests/test_private_annotation.py
python -m mypy src/deidflow/private --follow-imports=silent
```

Ruff and mypy also passed for the private implementation. Fixtures use fictional
addresses, synthetic metadata, synthetic attachment bytes and a distinctly marked
test transport. The end-to-end document test invokes the actual local engine
while sockets are denied; loopback HTTP tests separately exercise the real review
server. A Node execution tests the actual browser selection-offset function for
astral Unicode and CRLF. These checks validate the synthetic paths and do not
substitute for real Gmail authorization or private-document evaluation.

**No real Gmail operation was run**, including inventory, profile inspection,
authorization, provenance review, attachment download or annotation. No account
address, message/attachment metadata, user credentials or private original was
read through Codex, tools, connectors, browser profiles or filesystem discovery.
Real OAuth and real private evaluation remain user-run external steps, described
in [PRIVATE_GMAIL_BENCHMARK.md](PRIVATE_GMAIL_BENCHMARK.md).

The installed-dependency audit in
[dependency-audit-v030.json](dependency-audit-v030.json) records 111 audited
distributions and zero known reported vulnerabilities, without ignored
advisories. The unpublished local DeidFlow distribution is explicitly skipped
because it is not available on PyPI; it is reviewed by local code/tests instead.
This is a database snapshot, not proof that dependencies or native binaries have
no vulnerabilities. License metadata for 108 installed distributions and the
111-package non-editable Windows/Python lock were regenerated independently.
Native OCR binaries, model weights and public documents have separate provenance
and license records; see [third-party-licenses.md](third-party-licenses.md).

## Private workflow controls reviewed

| Boundary | Implemented control and synthetic evidence | Material limit |
| --- | --- | --- |
| Accidental launch in Codex | Explicit external-terminal acknowledgment; known Codex environment markers rejected before configuration/authentication reads; CLI errors do not echo supplied arguments | Same-user processes can bypass guards; this is operational separation, not an OS sandbox |
| Private paths | Absolute paths; repository, `Codex`, `.codex` and symlink paths rejected; user-only Windows DACL or POSIX modes | Does not stop administrators, same-user malware, backups, swap or crash dumps |
| Gmail identity and permission | Exact personal account/profile match; only gmail.com/googlemail.com; declared/granted scopes limited to gmail.readonly; fixed GET endpoint allowlist; no mailbox writes/drafts | Real consent/token exchange was not exercised; trusted supplied OAuth files and intended account selection remain prerequisites |
| Work/provenance intake | Positive exact sender list; immutable default BBVA/work exclusions; uncertain metadata skipped; HMAC per-attachment PERSONAL attestation before any byte download | Personal senders can forward work; heuristics and user judgment cannot guarantee corporate-material exclusion |
| Intake limits | All-mail bounded pagination excluding spam/trash; metadata fields omit snippets/body data; MIME/extension/count/date/size filters; nesting limit fails closed; bounded actual response bytes | Public/private parsers still process potentially malicious data; a process/VM sandbox is not provided |
| Download and temporary storage | Random filenames in a protected owned private child; memory-only SHA-256 exact deduplication; duplicates consume byte budget; ownership-validated cleanup refuses roots/unrelated paths | Abrupt termination can leave owned private files; persistent private sources/credentials/annotations are not temporary files |
| Output and errors | Logging/stdout/stderr suppressed around private processing; fixed error codes; strict aggregate schema; synthetic canaries in metadata, content, debug output, exceptions and malformed requests do not escape | Suppression does not establish anonymous output or defend against a compromised interpreter/custom adapter |
| Small cohorts and cells | Minimum 10 distinct downloaded contents for RUN; inventory metadata candidates clearly distinguished; minimum cell 5; counts round down to 5; rates suppress rare numerators and complements | No differential privacy; repeated/overlapping queries, differencing and external knowledge can weaken disclosure reduction |
| Local review UI | Bind 127.0.0.1 only; fresh bearer and CSRF token; exact Host/Origin checks; no CORS permission, external resources, access logs or upload endpoint; CSP/no-store | Browser extensions and same-user processes can inspect authorized displayed content; browser must stay outside model control |
| Annotation/training | Explicit original-display consent; validated finite boxes and Unicode ranges; repeated/multiline spans, false-positive states and whole fields; extra launch + save consent for excerpts/corrections; extra export consent | Original-text JSONL is private sensitive data; box-to-text alignment/correction application are not inferred; no automatic training or export to Codex |

Canary tests also reject unknown report keys, unknown annotation fields, nonfinite
geometry, malformed MIME/base64 and invalid source ranges. Source mutation
invalidates existing annotations. A wrong/corporate account is blocked before
message reads. Sender allowlisting alone does not authorize attachment download.

## Safe RAG bundle review

The Safe RAG implementation was separately reviewed against its synthetic
`tests/test_rag_export.py` suite. It stages fixed-name PDF/JSONL/audit files in a
new protected temporary directory, refuses preexisting bundle destinations and
uses a no-replace atomic publication step. Ownership-bound cleanup and concurrent
destination/failure cases are tested. Blocking states are not published as
approved bundles.

Searchable JSONL is derived from the encoded/rerendered output after pixel proof
and whitening proven-solid mask regions; it is not built from native source text.
Private page receipts bind the exact structured OCR records. Rereading rejects
unknown/duplicate fields, nonfinite or inconsistent geometry, unattested text and
offsets, broken page/chunk/line/token links and residual findings. Standalone JSONL
without a private receipt remains under review. Final PDF/JSONL byte hashes are
rechecked, and audit fields are fixed enums/counts/hashes with random document
IDs, without original filenames or recognized text.

The joint PDF/JSONL gate retains uncertainty from either artifact. Requiring table
structure yields review because true logical table reconstruction is unsupported;
the exporter does not invent tables. Tests include offline synthetic two-page OCR
canaries, tampered PDF/JSONL bytes, schema/text injection, split/overlapping OCR
masking and atomic failure cleanup. These are code-level evidence, not a formal
anonymity proof: the local OS, OCR/runtime and internal callbacks remain trusted,
undetected entities remain possible, review candidates may physically exist and
every consumer must check `release_approved`. Protected temporary files are not a
strong sandbox or forensic erasure mechanism.

## Processing and release limitations

Strict transformation and PDF verification gates should be interpreted as
processing evidence. An APPROVED artifact is not a formal anonymity guarantee,
and verification cannot prove absence of all contextual identifiers. Missing
capability, uncertain OCR, incomplete extraction and residual findings must retain
the engine's blocking/review status. Unlabeled public/private documents support
operational measurements only, not precision, recall, F1 or real-world detection
accuracy. Synthetic gold metrics must remain separately labeled.

The built-in document path uses local extraction, OCR, detection and transformation.
OAuth/Gmail retrieval necessarily uses Google network endpoints. Custom executable,
model and adapter code are trusted code; `--local-only` does not impose an OS
network firewall or audit arbitrary third-party plugins. No publication, remote
telemetry, hosted inference or private-data connector is part of this workflow.

The GPL Spanish model is an external evaluation asset, and SCJN public documents
have separate restricted/uncertain content terms, including a prohibition on
commercializing portal information. Their availability does not authorize
commercial redistribution or training. Original public documents, derived PDFs,
native OCR binaries and private assets are excluded from the Python package.

For stronger private isolation, close Codex and run under a separate OS
account/VM that holds the credentials and original files. Do not return private
reports for automatic inspection, and never return originals, filenames, subjects,
annotations, tokens or training exports. Read
[PRIVACY_BOUNDARIES.md](PRIVACY_BOUNDARIES.md) for the complete operational boundary.
