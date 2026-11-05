# Changelog

## 0.3.1 - Unreleased (experimental candidate)

- Preserve low-confidence and unresolved model-window evidence through CSV/TSV,
  JSON/JSONL and DataFrame transformations instead of approving a candidate after
  its uncertainty disappears from the output rescan.
- Apply source-confidence review to inferred-column transformations in the schema
  fast path, matching the configured review threshold.
- Preserve source review evidence for JSON object keys and include their actual
  transformations in audit counts.
- Add synthetic cross-format regressions for release decisions and audit counts.
  These test orchestration, not real-model detection quality or anonymity.
- Record the successful historical v0.3.0 GitHub Actions run separately from
  patch validation; prioritize a complete supervised tabular workflow for v0.4.

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
