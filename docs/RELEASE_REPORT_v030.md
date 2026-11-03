# DeidFlow v0.3: local engineering and release assessment

Date: 2026-11-02. The implementation is suitable for supervised technical
evaluation. The measured coverage does not support describing it as an
unattended production anonymizer. Public/private/synthetic evidence remains
separate throughout this report.

## Implemented and preserved

- Existing Python API, CLI, Mexican validators, policy gates, scoped HMAC,
  streaming tables, local NLP and staged column training were extended in place.
- Public MEDDOCAN/TAB acquisition pins authoritative archives and verifies bytes,
  annotation offsets, mappings, licensing and source provenance before evaluation.
  Raw corpora remain outside the repository and package.
- Spanish clinical-field rules were developed from the development partition.
  The held-out test and article-disjoint subset are separate. No public or private
  model was automatically trained or activated.
- PDF rebuilding still uses fresh lossless raster pages, native-glyph/OCR masks,
  decoded hashes, actual pixel proof, output rendering/OCR and source rehashing.
  Bounded Tesseract workers 1/2/4/8 preserve page order, selected masks and pixels.
  Native rotations are unsupported; missing capability and uncertainty preserve
  blocked/review states. Ordinary candidates are current-user-only before writing.
- Optional RAG output publishes PDF, JSONL and audit as one exclusive atomic
  directory. JSONL comes only from verified output pixels and has its own schema,
  receipt, geometry, hash and rescan gates. PDF success cannot approve raw JSONL.
- The Gmail runner uses minimum read-only OAuth, personal-account validation,
  metadata-first filtering, per-attachment human personal attestation, bounded
  downloads, content deduplication, private temporaries and precise owned cleanup.
  Coarsened reports reject arbitrary strings, suppress small cells/complements
  and never calculate unlabeled precision/recall/F1.
- Local review and annotation use localhost, authentication, CSRF/CSP/no-store,
  explicit display/excerpt/export consent, Unicode offsets and opaque references.
  Text spans, fields and page/image regions are supported. Private training exports
  remain local; raw Gmail attachments never enter automatic training.

## Detection evidence

| Independent human-gold evaluation | v0.2 exact F1 | Candidate exact F1 |
|---|---:|---:|
| MEDDOCAN official test,250 documents /5,661 mentions | 0.2433 | 0.5089 |
| MEDDOCAN source-article-disjoint subset,226 /5,131 | 0.2415 | 0.5065 |
| MEDDOCAN matched rules+same local Spanish NER | 0.2931 | 0.4679 |
| TAB actual English judicial text,127 /5,384 | 0.0000 | 0.0000 |

MEDDOCAN is semi-synthetic clinical narrative with artificial identifiers, not
an original private patient collection or Mexican enterprise holdout. TAB is a
separate English contextual-masking task. Generic NER adds recall and false
positives. Rules exact precision/recall is 0.6927/0.4022 on MEDDOCAN. All 250 test
documents still have uncovered sensitive characters, even though rules sensitive
character coverage improved from 0.3500 to 0.5376. Do not equate exact-span or
partial-overlap scores with anonymous output. ECE is unavailable; scores remain
uncalibrated. Full per-type metrics, bootstrap intervals, negatives, leakage
definitions and stratification are in [the quality report](DETECTION_QUALITY.md)
and [public methodology](REAL_WORLD_BENCHMARKS.md).

## Actual performance and operational evidence

The frozen v0.2 archive passed 208 tests. Native 100-page processing reproduced in
94.016 seconds. Its scanned 100-page workload blocked on residual findings; the
failure is preserved. Current profiled native 100 pages took 155.490 seconds with
one worker and 75.307 seconds with eight; both had identical PDF hashes and all
2,000 planted word regions covered, but retained REVIEW_REQUIRED. Current scanned
100 pages also blocked, in 140.170/72.576 seconds. Mixed6 pages passed the explicitly
rules-only fixture gate in 7.872/4.893 seconds. Shared-machine load and profiling
prevent an isolated causal speedup claim. Memory rises with workers: full scanned
eight-worker sampled process-tree RSS reached 1.119 GB.

The 100k/1m CSV workloads independently inspect every expected sensitive cell and
nonsensitive amount. Canonical results use a frozen candidate source snapshot;
interrupted and source-changing development trials remain separate. The complete
measurements, batch p50/p95, throughput, sampled RSS, long Spanish 1.16-million-
character text and 10k-text worker comparison are in [PERFORMANCE.md](PERFORMANCE.md)
and `benchmarks/results/v030/`. There is no blended accuracy or invented
full-scale timing confidence interval.

Public unannotated operational processing evaluated explicit first-three-page
subsets, not entire source documents. An 8-page SCJN resolution subset retained
REVIEW_REQUIRED; a 6-page government form subset blocked. A separate 29-page SCJN
URL returned a non-PDF response and was recorded unavailable without bypassing
restrictions. These tests provide robustness/status/timing evidence, not recall
or F1, nor full-document release approval. SCJN terms restrict the acquired source
to informational/academic use; raw/derived documents are not redistributed or
used as commercial training data. See the source registry and raw aggregate report.

## Verification and dependencies

The complete final candidate suite passed **370 tests, zero failures/skips**, with
the installed real Spanish/English OCR and Spanish NER assets. Existing tests
were preserved. New coverage includes gold adapters, protected-match regressions,
socket-denied inference, RAG raw-text injection/tampering/publication races,
ordered concurrent OCR/failures, rotated/partial/hidden/blank/table PDFs,
canary-safe private errors/reports, approval filtering, localhost authentication,
CRLF/astral Unicode annotation offsets and private export consent.

Ruff lint and format passed (99 Python files); mypy passed 37 source modules;
the microbenchmark guard passed with critical synthetic category recall 1.0 and
relative ratio 1.087. Optional local assets remain outside distributions.
The dependency audit reports zero known vulnerabilities in 111 public packages,
without advisory exclusions; the local editable package is separately identified.
This audit does not cover native binaries, unknown vulnerabilities or certify
privacy. Exact installed licenses and native/model terms are inventoried.
The optional Spanish evaluation model is GPL-3.0 and is not bundled or selected
automatically. No PyMuPDF, generative inference or document-upload service is used.

Build/archive and isolated wheel validation are recorded in `validation.json`
after the final local release gate. Remote CI has not been executed.

## Private-data boundary

**No real Gmail or private-document evaluation was executed.** No real OAuth
credential, account profile, subject, sender, filename, body or attachment was
retrieved by Codex. All private feature tests used synthetic fixtures. Strong
private isolation requires a separate OS account/VM or equivalent policy; a
terminal under the same user is only an operational boundary.

Exact external-terminal commands, setup, per-attachment approval, optional local
OCR/NER, annotation and retention are documented in
[PRIVATE_GMAIL_BENCHMARK.md](PRIVATE_GMAIL_BENCHMARK.md). They must be run by the
user outside Codex. No secrets or original-text exports should be pasted here.

## Release decision and remaining work

Production publication is not justified by these results. A clearly labelled
experimental release can support supervised evaluation, once the copyright
holder chooses public-use terms and the release artifacts pass their final gate.
`LICENSE` currently reserves all rights and makes no public license grant.
The user authorized source publication on GitHub only. The repository preserves
the existing reserved-rights license and explicit experimental scope. No PyPI
upload, private document, endpoint or model publication is part of this release. The user's conditional publication instruction does not
require calling insufficient privacy coverage production-ready.

Priority work is independently annotated Mexican/provider holdouts, free-form
names/addresses and difficult phone/OCR boundaries, representative degraded
layouts, reliable tables, calibrated review thresholds, repeated isolated
performance measurements and separately authorized private evaluation. Model
promotion still requires critical-category holdout checks; no automatic
activation is performed. DOCX/XLSX/Parquet rewriting, native rotated/cropped/forms/
signatures, reliable scanned orientation, visual identifiers and private token-
level NER training remain unsupported or unvalidated.
