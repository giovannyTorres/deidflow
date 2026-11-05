# DeidFlow v0.3.1: release-evidence corrections

Prepared 2026-11-05. This experimental patch corrects release decisions and audit
counts in structured transformations. It remains suitable for supervised
technical evaluation; it does not establish unattended production anonymization.

## Problem and resulting behavior

The v0.3.0 text path retained original finding evidence when deciding whether a
transformed output required review. The structured cell path retained low scores
but discarded unresolved `window_boundary` evidence. Consequently the same
partially detected synthetic name could require review in text and receive
`APPROVED` in CSV/JSON, even while part of the name remained in the output.

JSON key transformations also discarded source uncertainty and omitted their
transformations from the audit count. Inferred-column transformations in the
schema fast path omitted the configured confidence review check.

The patch preserves these source review reasons across text, CSV/TSV, JSON/JSONL
and pandas/Polars transformation paths, including JSON keys. Low-confidence source
findings or unresolved model-window boundaries require `REVIEW_REQUIRED` when no
blocking condition exists; residual findings and incomplete coverage continue to
block release. JSON key replacements now contribute to transformation counts.
The schema fast path honors `review_below` for inferred findings.

The regression fixtures use controlled local adapters and synthetic data. They
exercise the supported adapter contract; they are not measurements of a real NLP
model's frequency of clipped entities, detection recall or output anonymity.

## Validation of this patch

Local validation on Linux, Python 3.12.14:

- Full suite: **407 passed, 11 skipped**. The skips require the separately
  installed Spanish NER model, Tesseract/language assets or optional pytesseract;
  real OCR/NER integration was not rerun in this environment.
- New release-evidence suite: **48 passed**. Against the unchanged v0.3.0 source
  (`68883a5`) in an isolated source copy, the same cases produce **25 failures,
  23 passes**, reproducing the corrected bugs.
- Ruff lint/format and mypy with the actual Python 3.12 target passed.
- The microbenchmark guard passed, including exact recall 1.0 for its synthetic
  EMAIL/CURP/RFC/CLABE/API_KEY fixtures. This is not an independent quality study.
- Built the 0.3.1 sdist and wheel. Installed the wheel without dependencies in a
  separate clean virtual environment, outside the checkout; import/version and
  the synthetic JSON-key uncertainty/count regression passed.

These are local patch checks. Remote CI must be assessed on the actual PR commit;
the successful historical run below is not a substitute. No new public-corpus,
private-data, native-security or dependency-advisory evaluation is claimed.

## Historical evidence and CI correction

The [v0.3.0 report](RELEASE_REPORT_v030.md) and `validation.json` are retained
historical snapshots. Their statement that remote CI had not run was superseded
by [GitHub Actions run 41590013106](https://github.com/giovannyTorres/deidflow/actions/runs/41590013106)
on commit `68883a542288c6d141b624f111e645ce830acc13`.
That run passed Linux/Windows checks with Python 3.11/3.13 and a dependency job.
The inspected Ubuntu/Windows Python 3.11 test logs report **359 passed, 11 skipped**.
The skips include the separately installed Spanish model, local Tesseract/language
assets, a missing optional OCR wrapper and dependent OCR/PDF/RAG integration tests.

The prior **370 passed, zero skips** record describes a separate local Windows
evaluation with real assets. It is neither the remote CI count nor validation of
v0.3.1. Historical performance, public-corpus quality, dependency/license inventories
and artifact hashes retain their original versions; this patch does not refresh
those measurements or extend their applicability.

## Scope and next milestone

No new detector, trained model, OCR capability, format writer or production
review interface is introduced. Public detection limitations remain as documented
in [DETECTION_QUALITY.md](DETECTION_QUALITY.md). The same detector can still miss
the same sensitive content during transformation and reinspection.

The current annotation UI stores labels for evaluation/training; it cannot yet
apply corrections to regenerate and approve a candidate. The next milestone is
a complete local supervised CSV/JSONL workflow for a known schema, with output
verification, explicit export and a domain-specific independent evaluation.
See the [roadmap](roadmap.md#next-milestone-v04-supervised-tabular-workflow).

The existing reserved-rights license and private-data boundaries remain in force.
This patch does not publish a package, access private documents or run Gmail.
