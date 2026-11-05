# Remaining engineering work

This delivery prioritizes functioning, verified components. The following are
explicitly unimplemented or not validated; they are not hidden fallback paths.

v0.3 adds pinned public-gold acquisition/comparison, source-disjoint evaluation,
local private review/annotation, joint PDF+JSONL gates, numeric stage profiling
and measured bounded OCR workers. These are implemented. Remaining clinical and
English detection gaps, real private evaluation and production acceptance targets
are documented in the current quality/security reports.

v0.3.1 corrects the propagation of source uncertainty across structured formats,
inferred-column confidence checks and JSON key transformation counts. It does
not close the remaining detection gaps. See the [patch assessment](RELEASE_REPORT_v031.md).

## Next milestone: v0.4 supervised tabular workflow

Start with local CSV/JSONL processing for a known schema in one selected domain.
The existing annotation interface stores labels; applying human corrections and
approving a revised artifact remain unimplemented.

1. Connect import, detection, original/candidate review, manual corrections,
   regeneration, verification and explicit export. A newly marked sensitive
   value must disappear from the exported artifact; a source change must invalidate
   prior review. Blocked artifacts must never enter the approved export path.
2. Link the output receipt to source/output hashes, policy and model versions,
   human changes and the approval decision, without logging original values.
3. Evaluate an independently annotated, authorized holdout from the selected
   domain. Set acceptance criteria before tuning; measure residual sensitive
   content in transformed output, retained useful information, completion rate
   and total human review time against the manual workflow.
4. Provide reproducible installation and a safe preflight diagnostic for missing
   dependencies/assets. Add required integration CI with pinned OCR/NER assets
   and fail on unexpected skips. Keep candidate and approved outputs separate.
5. Run a supervised local single-user pilot before expanding formats, connectors
   or deployment topology. Worker isolation, resource limits, retention and
   recovery procedures must match the selected deployment.

## Before commercial use

1. Obtain independently annotated, licensed Mexican clinical, financial,
   administrative and contract corpora, with real-world negatives and difficult
   names/addresses. Set domain-specific critical recall/review targets. Validate
   model/weight redistribution terms and independently review privacy/security.
2. Expand the installed, source-built Tesseract 5.5.4 Spanish OCR evaluation from
   synthetic fixtures to independently annotated real document layouts, degraded
   regions, selective routing, external quality holdouts and visual verification.
3. Extend the implemented lossless image-only PDF reconstruction to safely support
   rotated/cropped geometry and additional source features. Current reconstruction
   discards original objects, metadata, attachments and hidden text, and verifies
   actual output pixels and OCR. Searchable/vector-preserving redaction, forms
   and signature workflows need separate implementation and adversarial review.
   Office rewriting must account for revisions, orphan strings, hidden sheets,
   formulas, comments, embedded objects and relationships. Office rewriting remains unsupported.
4. Strengthen independent verification beyond the detector used for transformation;
   implement signed transformation receipts, integrity-protected private audit
   stores and private review workflows. Policies/keys/adapters remain trusted code.

## Accuracy and customer adaptation

- Train/evaluate local token/span NER with BIO conversion and representative
  Spanish/Mexican customer annotations. CRF, BiLSTM/encoder adaptation and
  LightGBM/CatBoost alternatives remain experiments, not delivered adapters.
- Expand regional IDs, health terminology and subject relationships, spatial and
  multi-line layout, cross-page references and clinical negation. Current medical
  table association is schema-level; JSON cross-field medical association is not
  implemented. The taxonomy includes labels without built-in detectors.
- Compare DataProfiler on equivalent structured labels after provisioning a
  reviewed local labeler. The existing column learner equals a simple pattern
  baseline on its easy synthetic holdout; no model advantage is claimed.
- Extend the implemented evaluation stratification with external calibration, abstention criteria,
  semantic drift monitoring and rigorous alias resolution without weak person merges.

## Performance and delivery

- Implement truly vectorized Arrow/Polars validators and output transformations,
  batch-native NLP spans, bounded Parquet output with schema verification and
  structured per-record provenance receipts. No vectorized speedup is claimed.
- Benchmark isolated model memory, >1m heterogeneous rows, statistical text batches,
  repeated full-scale trials and actual scanned collections on representative hosts.
- CUDA consumer-GPU and ONNX encoder adapters and parallel file rewriting remain
  unvalidated. OCR workers1/2/4/8 are measured on synthetic fixtures in v0.3;
  representative real collections and repeated full-scale trials remain necessary.
- Add maintained dependency hash locks by OS/Python, signed artifacts/SBOMs,
  protected key/model storage, process isolation and platform-specific installation.
  [GitHub Actions run 41590013106](https://github.com/giovannyTorres/deidflow/actions/runs/41590013106)
  passed on v0.3.0 commit `68883a5` across Linux/Windows and Python 3.11/3.13.
  The inspected Python 3.11 jobs passed 359 tests and skipped 11 asset/dependency
  integrations; this is not evidence that all real OCR/NER paths ran in CI.
- Source is already public on GitHub under reserved-rights terms. Resolve
  name/trademark and recipient license terms before broader distribution or a
  separately authorized package publication. No PyPI package has been published.
