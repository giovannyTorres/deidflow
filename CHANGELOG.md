# Changelog

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
