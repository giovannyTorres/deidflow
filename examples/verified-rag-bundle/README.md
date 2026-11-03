# Synthetic RAG export example

Two locally generated Spanish pages, processed with installed Tesseract 5.5.4
spa+eng/PSM6 and the explicitly narrower `strict_pdf(require_ner=False)` policy.
Both synthetic emails were physically masked; amount42 and page/line text remain.
The PDF and JSONL passed their serialized structural/pixel/rescan gates, but
low source OCR confidence correctly retained **REVIEW_REQUIRED**. Do not ingest
this example as automatically approved merely because its filename says safe.

`document.audit.json` contains the actual status and hashes. `document.safe.jsonl`
comes only from verified reconstructed pixels. Both pages were rendered with
Poppler and visually inspected locally. No private document, Gmail access or
external inference was involved. This simple fixture does not establish
clinical, table or private-document accuracy.
