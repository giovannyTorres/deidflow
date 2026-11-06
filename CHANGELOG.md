# Changelog

## 0.4.0 - 2026-11-05

- Relicensed under Apache-2.0 (`LICENSE`, `NOTICE`); the earlier snapshots
  reserved all rights.
- Added `SpanTagger`, a dependency-free averaged-perceptron BIO tagger with JSON
  model files, hashed features, document-frequency feature pruning, Platt
  calibration, near-miss review candidates and optional NumPy acceleration.
- Added the packaged `es-clinical` model trained on MEDDOCAN train (selected and
  calibrated on dev). Held-out test exact F1 0.958 [0.950, 0.966] versus 0.509
  for the v0.3 rules; ECE 0.008. See `docs/TAGGER.md`.
- Added `scripts/train_span_tagger.py`, span JSONL corpora, `CombinedNER` and
  CLI `--tagger`, `--tagger-sha256`, `--review-margin` and `--version`; CLI
  errors now report the exception class (never its message).
- Verification rescans ignore findings made only of DeidFlow replacement output:
  exact applied ranges during `deidentify_text`, otherwise known placeholder,
  pseudonym, redaction and mask formats. Previously the rules re-detected
  `Domicilio: [ADDRESS]` and blocked every such document. Bracketed source values
  (`[JUAN]`, `[GODE561231GR8]`) and findings that cover source letters or digits
  keep blocking.
- `EntityType` adds `INSURANCE_ID`, `MEDICAL_FACILITY`, `ORGANIZATION`,
  `IP_ADDRESS` and `OTHER_SENSITIVE`, which detectors and corpora already used.
- RAG bundle publication supports macOS (`renamex_np(RENAME_EXCL)`).
- Added `scripts/benchmark_release_gate.py` measuring release decisions and
  output leakage: on MEDDOCAN test, 40 of 149 approved documents still leaked at
  least one sensitive character (11 of 76 with `review_margin=60`).
- Added pinned git acquisition (`acquire_git`) verified against the registry's
  per-file digest manifest, now also checked by archive acquisition.
- Added the Gretel multilingual financial PII corpus (Apache-2.0, pinned revision
  and file hashes) and the packaged `es-finance` tagger trained on its Spanish
  train file. Held-out Spanish test exact F1 0.740 versus 0.308 for the rules;
  57 of 161 approved test documents still leaked at least one sensitive
  character (`docs/TAGGER.md`).
- Added a checksum-validated (ISO 13616 MOD 97-10) IBAN recognizer.
- Added the international identifier pack for 21 Spanish-speaking countries
  (`docs/COUNTRIES.md`), international phones, IPv4/IPv6 and textual Spanish
  dates; `DeidEngine(country=...)` now accepts `"ALL"` (default), an ISO code or
  a list. Adds `TAX_ID`. Validators agree with python-stdnum on random inputs.
- `TAX_ID`, `INSURANCE_ID`, `REGIONAL_ID` and `IP_ADDRESS` count as direct
  identifiers in risk assessment. Generic `LATAM-*`/`BANK-ACCOUNT` fallbacks no
  longer raise the score of digits whose country check digit failed.
- DOCX output: `deidentify("in.docx", output="out.docx")` rewrites the package
  in place (formatting kept, values split across runs replaced), accepts
  tracked changes, removes authors, personal properties, the thumbnail,
  external links, mail-merge settings and data-bearing field codes, and by
  default images and embedded objects (`office_media`, CLI `--office-media`);
  the output is reread and rescanned before release.
- XLSX output: cells are transformed with their column header as context
  (recognized columns whole, as for CSV), changed cells become inline strings,
  the shared-string table is rebuilt so replaced and orphaned values are gone,
  formulas with literals or external references are replaced by their values,
  sheets named after a person are renamed, and pivot caches, external links,
  connections, threaded comments, printer settings and saved paths are removed.
  The XLSX reader no longer forces review for plain cell arithmetic, print
  areas or table definitions, and blanks header/footer formatting codes.
- The DOCX reader scans `fldSimple` instructions and commenter account IDs,
  flags package thumbnails, and no longer forces review for layout-only fields
  such as `PAGE` or `TOC`.
- Added a head-to-head comparison with Presidio and spaCy on the MEDDOCAN and
  Gretel test sets (`docs/COMPARISON.md`): exact F1 0.958 vs 0.363 vs 0.259
  (clinical) and 0.707 vs 0.177 vs 0.115 (financial).
- Added `deidflow.benchmarks.synthetic_es`, a seeded multi-country synthetic
  corpus with check-digit-valid identifiers and template families held out per
  split, and `train_span_tagger.py mixed` to train on several corpora at once.
- Added `redact_margin` (silent over-redaction of near-miss tokens), packaged
  `balanced`/`assurance` operating profiles tuned on validation, a domain router
  (`DomainRouter`, CLI `--tagger builtin:auto`) and direct-identifier leak,
  over-redaction and Wilson-interval metrics in the release-gate benchmark. The
  `assurance` target (<= 2% approved direct-identifier leak) held on validation
  but measured 7.7% on the MEDDOCAN test set (`docs/TAGGER.md`).
- CI: Linux/Windows/macOS × Python 3.11-3.13, coverage gate, wheel smoke test
  without optional dependencies. Release workflow with SBOM, checksums, build
  provenance attestations and opt-in PyPI trusted publishing. Dependabot,
  `SECURITY.md`, `CONTRIBUTING.md`, full project metadata, beta classifier.

## 0.3.0 - 2026-11-02 (local experimental release)

- Added pinned MEDDOCAN/TAB acquisition, verified human gold, frozen v0.2
  comparisons, source-disjoint holdout diagnostics and explicit coverage gaps.
- Added Spanish clinical-field recognizers; MEDDOCAN exact F1 improves from
  0.2433 to0.5089 while remaining insufficient for unattended anonymization.
- Added transactional PDF+JSONL+audit export from verified output pixels with
  independent structured verification and shared release gates.
- Added bounded local Tesseract workers 1/2/4/8, numeric stage timing/RSS,
  permission-hardened PDF candidates and native rotated-glyph refusal.
- Added external-terminal-only read-only personal Gmail infrastructure, individual
  attachment attestation, suppressed aggregates and consented local annotation.
  No real Gmail/private document was accessed in development.
- Added real local benchmarks for 100-page native/scanned PDFs, mixed workloads,
  100k/1m CSV, long Spanish text and public unannotated operational subsets.
- Preserved blocked/review outcomes, original tests, proprietary license terms,
  source provenance and all historical development measurements. Not published.

## 0.2.0 - 2026-11-02

- Installed and source-built patched Tesseract 5.5.4 with pinned Spanish/English
  language data and native dependency/license/hash manifests, outside the package.
- Replaced global OCR configuration with bounded shell-free PNG/TSV subprocess
  pipes; reject partial-language and disabled-mode silent fallbacks.
- Added streaming lossless image-only PDF reconstruction, native glyph/OCR masks,
  actual pixel/closed-object verification and rerendered output OCR.
- Added explicit PDF removal policies, engine/CLI integration, geometry/resource
  limits, source-mutation checks and fail-closed release states.
- Corrected empty-form label parsing, protected damaged OCR fields without
  correction and versioned updated rule provenance separately from old calibration.
- Added real OCR/PDF benchmarks, adversarial regression tests, reproducible native
  setup and visually reviewed synthetic before/after examples.

## 0.1.0

Local baseline package, Mexican/contextual rules, text/tabular transformations,
HMAC tokens, policies, native readers, optional NLP, local column training,
synthetic benchmarks and verification gates. Retained baseline evidence remains
in `docs/engineering-report.md` and the original benchmark results.
