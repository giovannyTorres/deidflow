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
- Added the Gretel multilingual financial PII corpus loader and evaluation path
  (Apache-2.0); not executed yet because the host was unreachable.
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
