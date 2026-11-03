# Private Gmail benchmark and annotation

This workflow has been implemented and tested with synthetic transports and synthetic documents. No real account, private attachment, real OAuth credential or private annotation dataset was accessed during development. Real Gmail measurements and real detection accuracy remain unvalidated.

Run the following steps yourself in a separately launched terminal outside Codex. Prefer closing Codex first. A separate OS account or VM with access to the private directory provides a stronger boundary than a separate terminal under the same account. Never paste an account, sender list, subject, filename, document, token, annotation or original-text training export into this chat. The CLI rejects known Codex environment markers; do not remove those markers to launch it from Codex.

## One-time local setup

Install into the existing local Python environment from the local checkout, replacing the checkout path if needed:

```powershell
python -m pip install -e "C:\path\to\deidflow[private-gmail,pdf,ocr,nlp,tables,benchmarks]"
```

The optional Gmail dependencies are Google's `google-auth` and `google-auth-oauthlib`. OAuth is lazy-imported and never uses browser cookies, Codex connectors, an existing browser profile or credentials discovered from a home directory. The runner uses the ordinary Google OAuth desktop application flow with PKCE and a `127.0.0.1` callback. Configure your own desktop OAuth client and enable the Gmail API outside Codex, following [Google's desktop OAuth instructions](https://developers.google.com/identity/protocols/oauth2/native-app). Gmail read-only access is a restricted scope and Google's consent/verification rules still apply. This local implementation does not publish an OAuth app. See [Google's Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).

Create a private directory outside every Git checkout and every directory named `Codex`. On Windows, `%LOCALAPPDATA%\DeidFlowPrivate` is an example. Copy `examples/private-gmail.example.json` there, and edit the copy locally with your account, absolute paths, exact personal sender allowlist, date window and limits. The checked-in example is entirely fictional. Keep the downloaded desktop client JSON there too. Do not place the edited configuration in the project. Token files and private outputs receive a protected current-user DACL on Windows, or mode `0600`/`0700` on POSIX. The directory must be on a filesystem supporting those protections.

The account must exactly match the configured address and use `gmail.com` or `googlemail.com`. Every other domain is rejected. Tokens must request exactly `https://www.googleapis.com/auth/gmail.readonly`; broader tokens are rejected. A wrong selected account is rejected after its profile is checked and before messages are listed or a newly issued token is saved. Existing token files are never silently replaced during authorization.

In your external PowerShell terminal:

```powershell
$privateDir = Join-Path $env:LOCALAPPDATA 'DeidFlowPrivate'
$privateConfig = Join-Path $privateDir 'config.json'
deidflow benchmark private-gmail --authorize --config $privateConfig --external-terminal-ack
```

Select the intended personal account in Google's browser consent screen. The account address is checked locally and never printed. Authentication failures produce fixed codes without raw Google errors.

## Inventory, provenance review and run

```powershell
deidflow benchmark private-gmail --inventory --config $privateConfig --external-terminal-ack --report (Join-Path $privateDir 'inventory.json')
deidflow benchmark private-gmail --review-personal --config $privateConfig --external-terminal-ack --consent-display-metadata
```

Inventory uses a bounded all-mail search, `has:attachment -in:spam -in:trash`, with optional dates; it does not restrict to inbox. Message headers are requested first. Only an exact configured sender and non-work metadata can pass the first filter. Default BBVA/corporate domain and work-subject exclusions cannot be disabled by an empty configuration. An uncertain or missing sender/subject is skipped. The MIME tree request excludes bodies, encoded document data and snippets. Nested attachments, MIME/extension compatibility, count and size limits are checked. Inventory and the provenance review do not download attachment bytes. Gmail listing and metadata semantics are documented in [messages.list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list) and [messages.get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get).

MIME traversal supports eight nested levels and fails closed if a deeper level is observed. The provenance review opens a local browser UI. It shows filenames, subjects and senders only in that browser after the display consent flag. The URL/token is not printed; if opening a browser fails, open the protected `.local-review-url` file locally yourself. For **each** attachment, inspect the provenance and explicitly attest that it is personal, unrelated to an employer, and authorized for local processing. Exclude work material, forwarded corporate files and uncertain material. There is no approve-all action. A sender allowlist cannot establish the provenance of an attachment. The UI stores HMAC references and fixed PERSONAL/EXCLUDE decisions, without names, subjects or content. It does not inspect the attachment for you.

Then, still outside Codex:

```powershell
deidflow benchmark private-gmail --run --local-only --config $privateConfig --external-terminal-ack --report (Join-Path $privateDir 'run.json')
```

Without individual personal approvals, `--run` skips every unknown attachment. `--local-only` is mandatory for document processing. Gmail retrieval and OAuth still require Google's network endpoints; extraction, detection, OCR and transformation run locally. The transport offers GET only for profile, message listing/metadata and attachment retrieval. It has no send, drafts, labels, delete, archive or other mutation operation.

Provide `--ocr-executable C:\path\to\tesseract.exe --tessdata-dir C:\path\to\tessdata` for local Spanish/English OCR (`spa+eng`), and `--model C:\path\to\local\spacy-model` for local NER. No model download is started by the runner. Use trusted local executables and model packages. Strict policy and verification govern the status; missing capability or uncertainty can produce REVIEW_REQUIRED, BLOCKED or UNSUPPORTED, never an automatic safety guarantee.

Each run creates its own protected private temporary child directory. Document inputs and transformed outputs use random filenames; content SHA-256 is held in memory for exact deduplication and is not exported. Downloaded duplicates still consume the total byte budget. The runner removes its own input/output files and validated owned temporary directory on normal completion and caught interruption. An abrupt process/OS termination can leave a private child behind. `cleanup_owned(child, parent)` in `deidflow.private.security` refuses the root, unrelated paths, symlinks and children without a valid ownership marker. Persistent originals, credentials and annotations are never included in temporary cleanup. No transformed private documents are retained by this benchmark.

## Understanding an operational report

The schema permits fixed enums, numeric values, booleans and nulls. It rejects unknown fields and contains no subjects, addresses, filenames, snippets, individual IDs, per-document hashes or exception strings. `validate_report` in `deidflow.private.reports` validates this schema. The CLI validates before writing or printing it. Report output paths must also be outside repositories and Codex, and must not already exist.

Reports suppress all measurements for cohorts below 10. RUN uses the number of distinct successfully downloaded contents for this threshold, even when processing later fails; duplicate copies and failed downloads cannot qualify a single original. INVENTORY uses metadata candidate count because byte deduplication would require downloading documents. It is an inventory estimate, not a unique-document count. Individual count cells below 5 are null, and remaining counts round down to multiples of 5. Rates round to tenths, time quantiles to seconds and sampled peak process-tree RSS to 16 MiB. RSS is null when optional `psutil` is unavailable. Pages count observed page locations, not a promised page total for unsupported files. Time estimates stay null unless `seconds_per_attachment` is explicitly calibrated by the user.

Rates are also suppressed when either the numerator or its complement contains only one to four observations; zero, balanced cells of at least five, and full cohorts can be reported. These rules are conservative disclosure reduction, **not differential privacy, anonymization proof or a guarantee against inference**. Repeated overlapping queries, differencing and auxiliary knowledge can weaken suppression. Broad category values mean documents with detector findings, not true incidence or ground truth. An unlabeled run reports throughput, size, exclusions, processing states, failures, OCR uncertainty and review burden. It does not calculate precision, recall, F1 or claim real detection accuracy.

## Local annotation and gold data

The private review queue stores only HMAC references and fixed review reasons. Reopen the provenance review to see those reasons beside metadata. To annotate an original, explicitly save a selected, approved personal original yourself into another private source directory, using your ordinary local tools. The runner intentionally does not persist attachment originals or automatically populate an original-text dataset.

```powershell
deidflow annotate --source-dir (Join-Path $privateDir 'selected-originals') --private-root (Join-Path $privateDir 'annotation-data') --external-terminal-ack --consent-display-originals
```

The UI reads configured local files through opaque IDs; it has no upload endpoint. It displays local extracted text, detector candidates and rasterized PDF/image pages. Select text or draw a box, edit boundaries/type, mark missed entities, false positives or OCR errors, and group repeated mentions. Span offsets use Python Unicode codepoints and preserve CRLF offsets; image/PDF boxes use finite normalized coordinates and page numbers. Structured-field annotations cover a whole extracted field. Metadata labels/geometry persist privately by default without original excerpts.

Original excerpts and typed OCR corrections require both `--allow-store-excerpts` at launch **and** the UI's explicit per-save consent checkbox. Treat those saved corrections as private original data. Exporting original text for training has another explicit consent:

```powershell
deidflow annotate --source-dir (Join-Path $privateDir 'selected-originals') --private-root (Join-Path $privateDir 'annotation-data') --external-terminal-ack --consent-display-originals --export-training (Join-Path $privateDir 'private-training.jsonl') --consent-export-original-text
```

JSONL export includes confirmed/missed text spans and fields and omits false positives. Page boxes and OCR corrections remain in private sidecars: the exporter does not guess their text alignment or silently apply corrections. Edited originals invalidate previous annotations by content digest. Annotation is top-level file based, with bounded document count/bytes; directory recursion, collaborative editing, PDF byte serving, cloud synchronization and automatic training are unsupported. None of these private artifacts should be returned to Codex.

Both UIs bind only to `127.0.0.1`, use random bearer authorization, same-origin checks, a CSRF token, restrictive CSP and no-store responses. Stop them with Ctrl+C. Review [PRIVACY_BOUNDARIES.md](PRIVACY_BOUNDARIES.md) before a private run.
