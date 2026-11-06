# Remaining engineering work

This delivery prioritizes functioning, verified components. The following are
explicitly unimplemented or not validated; they are not hidden fallback paths.

v0.4 adds the Apache-2.0 license, a trained dependency-free Spanish span tagger
(MEDDOCAN test exact F1 0.958), end-to-end release-gate leakage measurement,
pinned git corpus acquisition, a financial corpus loader and tag-driven release
automation. The leakage measurement shows that approved clinical documents can
still contain sensitive characters; the items below remain open.

v0.3 adds pinned public-gold acquisition/comparison, source-disjoint evaluation,
local private review/annotation, joint PDF+JSONL gates, numeric stage profiling
and measured bounded OCR workers. These are implemented. Remaining clinical and
English detection gaps, real private evaluation and production acceptance targets
are documented in the current quality/security reports.

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
   DOCX rewriting is implemented with hidden-content removal and package checks.
   XLSX rewriting now removes supported hidden copies and produces supervised
   candidates. Broader Excel extension/formula semantics and safe automatic
   release remain unvalidated.
4. Strengthen independent verification beyond the detector used for transformation;
   implement signed transformation receipts, integrity-protected private audit
   stores and private review workflows. Policies/keys/adapters remain trusted code.

## Supervised tabular release workflow

The local annotation interface currently stores labels for evaluation and
training. It is not yet a complete human-correction and output-approval workflow.
The next operational milestone is a local, single-user workflow for a known
CSV/JSONL schema and one independently evaluated domain:

1. Connect import, detection, original/candidate comparison, manual corrections,
   regeneration, verification and explicit export. Newly marked sensitive values
   must disappear from the exported artifact; source changes invalidate review.
2. Link the approval receipt to source/output hashes, policy and model versions,
   human corrections and the reviewer without recording original values in logs.
3. Measure residual sensitive content, retained utility and total review time
   on an authorized, independently annotated holdout. Fix acceptance thresholds
   before tuning and compare with the manual workflow.
4. Separate candidate and approved output locations. Blocked files must never
   enter approved exports. Require the OCR/NER integrations used by the selected
   workflow to run in CI rather than accepting unexpected skipped tests.
5. Validate retention, recovery, resource isolation and key storage in a limited
   supervised pilot before expanding deployment topology or supported formats.

## Accuracy and customer adaptation

- Token/span NER with BIO conversion is delivered (`SpanTagger`, trained on
  public MEDDOCAN). Still open: training and evaluating on representative
  Mexican clinical/financial annotations and external financial holdouts beyond
  the published Gretel evaluation. Encoder (transformer/ONNX) adapters remain
  unvalidated.
- Reduce misses that survive into `APPROVED` output (an independent second
  detector for verification, document-level abstention, organization/phone
  coverage).
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
- SBOM, checksums and build-provenance attestations are produced by the release
  workflow. Still open: hash-pinned dependency locks per OS/Python, protected
  key/model storage, process isolation and platform-specific installation.
- License resolved (Apache-2.0). Name/trademark clearance and enabling PyPI
  trusted publishing remain the owner's decision.
