# Remaining engineering work

This delivery prioritizes functioning, verified components. The following are
explicitly unimplemented or not validated; they are not hidden fallback paths.

## Before commercial use

1. Obtain independently annotated, licensed Mexican clinical, financial,
   administrative and contract corpora, with real-world negatives and difficult
   names/addresses. Set domain-specific critical recall/review targets. Validate
   model/weight redistribution terms and independently review privacy/security.
2. Provision an approved local OCR executable and Spanish language data. Measure
   scanned-page detection, OCR character error, low-confidence regions, raster
   boxes, selective routing and independent visual verification. OCR was not
   available on the validation host.
3. Implement and adversarially verify PDF redaction/removal of all alternate
   representations, attachments, layers, forms, actions, XMP and hidden text.
   Office rewriting must account for revisions, orphan strings, hidden sheets,
   formulas, comments, embedded objects and relationships. It remains unsupported.
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
- Add evaluation stratification, external calibration, abstention criteria,
  semantic drift monitoring and rigorous alias resolution without weak person merges.

## Performance and delivery

- Implement truly vectorized Arrow/Polars validators and output transformations,
  batch-native NLP spans, bounded Parquet output with schema verification and
  structured per-record provenance receipts. No vectorized speedup is claimed.
- Benchmark isolated model memory, >1m heterogeneous rows, statistical text batches,
  repeated full-scale trials and actual scanned collections on representative hosts.
- CUDA consumer-GPU and ONNX encoder adapters, OCR worker pools and parallel file
  rewriting are not validated. Benchmark before selecting them.
- Add maintained dependency hash locks by OS/Python, signed artifacts/SBOMs,
  protected key/model storage, process isolation and platform-specific installation.
  CI is configured locally; it has not run on a remote hosting service.
- Resolve name/trademark and license strategy before any separately authorized
  public repository or package publication.
