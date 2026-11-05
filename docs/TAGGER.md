# Built-in span tagger (`es-clinical`)

A local statistical detector for Spanish personal data in free text, packaged
inside the wheel and usable with no optional dependency:

```python
from deidflow import DeidEngine
from deidflow.nlp import SpanTagger

engine = DeidEngine(nlp=SpanTagger.builtin("es-clinical"))
result = engine.deidentify_text(text)  # rules + tagger, Policy.strict()
if result.release_approved:
    use(result.output_text)  # still not proof of anonymity
```

```sh
deidflow deidentify note.txt --output note.safe.txt --tagger builtin:es-clinical
deidflow deidentify note.txt --output note.safe.txt --tagger builtin:es-clinical --review-margin 60
```

## Model

| Field | Value |
| --- | --- |
| File | `src/deidflow/models/es-clinical-meddocan-1.json.gz` (398 KB) |
| SHA-256 | `dc824100552ddb5bae036d128da9cfe4e31aba68b7cb74c2ab1252ddc0952da9`, checked on every `builtin()` load |
| Algorithm | Averaged structured perceptron (Collins 2002), first-order BIO transitions with hard BIO constraints, Viterbi decoding |
| Features | Feature set `es-1`: token, shape, affixes, ±2 token context, field label before the last colon on the line, line position |
| Inference | Pure Python; NumPy is used automatically when installed (identical spans, ~2.6× faster) |
| Scores | Platt-calibrated probability that a span is exactly right (type and boundaries), from `log1p(margin)`; also in `Finding.confidence` |
| Format | JSON (gzip), never pickle. Features are stored as keyed 64-bit BLAKE2b digests, and only features seen in at least 10 training documents are kept |
| Labels | `PERSON`, `ADDRESS`, `LOCATION`, `DATE`, `AGE`, `DEMOGRAPHIC`, `PATIENT_ID`, `INSURANCE_ID`, `REGIONAL_ID`, `EMAIL`, `PHONE`, `MEDICAL_FACILITY`, `ORGANIZATION`, `OCCUPATION`, `OTHER_SENSITIVE` |

## Training data and protocol

[SPACCC MEDDOCAN](https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN) at commit
`783a6df`, CC-BY-4.0 (attribution in `NOTICE`), acquired by
`acquire_git` and verified against the pinned per-file SHA-256 manifest.

1. Weights: official **train** split (500 documents, 11,333 spans; 7 spans that
   do not align with token boundaries are counted and skipped).
2. Epoch selection (early stopping on exact span F1), calibration and the
   feature-frequency threshold: official **dev** split only. Candidates
   (`min_feature_docs` 2, 3, 5 on an earlier feature set; 5 and 10 on the final
   one) scored 0.9518–0.9541 dev F1. Rule fixed before testing: highest dev F1,
   preferring the larger threshold within 0.002, so 10 was selected.
3. The official **test** split was evaluated once, after the model file and its
   hash were frozen. Training is deterministic; `scripts/train_span_tagger.py`
   reproduces the file byte for byte.

## Held-out results (MEDDOCAN test, 250 documents, 5,661 gold mentions)

Exact typed span matching; 95% document-bootstrap intervals. Raw reports:
`benchmarks/results/tagger/`. They were run from the 0.4.0 candidate source
before the editable install was refreshed, so their machine metadata records
package version 0.3.0; the tagger model hash in each report identifies the
evaluated model. Inference ran with sockets and DNS denied (zero attempts).

| Pipeline | Exact P | Exact R | Exact F1 [95% CI] | Sensitive-character recall | Docs with any uncovered gold character | p50 ms/doc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v0.2.0 rules | 0.536 | 0.157 | 0.243 [0.237, 0.250] | 0.350 | 250 | 1.7 |
| v0.3.0 rules | 0.693 | 0.402 | 0.509 [0.500, 0.518] | 0.538 | 250 | 4.2 |
| **Tagger** | **0.968** | **0.949** | **0.958 [0.950, 0.966]** | 0.966 | 100 | 29.8 |
| Rules + tagger (product default) | 0.820 | 0.952 | 0.881 [0.875, 0.887] | **0.969** | **91** | 32.6 |

- Source-article-disjoint subset (226 documents whose source articles are absent
  from train/dev): tagger F1 0.956 [0.948, 0.964], so the gain is not explained
  by shared source articles.
- Expected calibration error of tagger scores on test: **0.008** (0.011 for the
  hybrid). Scores were fitted on dev only.
- Per-type exact recall (tagger): REGIONAL_ID 1.00, INSURANCE_ID 0.995,
  DEMOGRAPHIC 0.98, DATE 0.98, EMAIL 0.98, AGE 0.97, PATIENT_ID 0.96,
  LOCATION 0.96, PERSON 0.95, ADDRESS 0.95, MEDICAL_FACILITY 0.80, PHONE 0.79,
  ORGANIZATION 0.22, OCCUPATION 0.00, OTHER_SENSITIVE 0.00 (the last three are
  rare in training data).
- The hybrid has lower exact precision because rule and tagger spans for the
  same entity often differ in boundaries and both are kept. For redaction that
  is harmless (overlaps are merged); it is why character coverage, not exact
  F1, is the relevant number for the product default.

## End-to-end release decisions (test split)

`scripts/benchmark_release_gate.py` runs `deidentify_text` with
`Policy.strict()` and counts a gold character as leaked when no applied
transformation covers it.

| Configuration | APPROVED | REVIEW_REQUIRED | BLOCKED | Approved docs that still leak ≥1 gold character | Output sensitive-character recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rules only (`require_ner=False`) | 2 | 248 | 0 | 2 of 2 | 0.538 |
| Rules + tagger | 149 | 77 | 24 | 40 of 149 (26.8%) | 0.968 |
| Rules + tagger, `review_margin=30` | 113 | 103 | 34 | 23 of 113 (20.4%) | 0.974 |
| Rules + tagger, `review_margin=60` | 76 | 132 | 42 | 11 of 76 (14.5%) | 0.978 |

The margins were chosen on dev (`release-gate-dev-margin*.json`) before this
measurement. **`APPROVED` is not proof of anonymity.** The rescan uses the same
detectors, so it cannot see what they missed: a meaningful share of approved
clinical documents still contain at least one sensitive character. On dev, the
leaked spans in approved documents were mostly organizations, patient
identifiers, locations, names and dates, and about a quarter were partial
boundary misses (for example the last characters of a span). Use `review_margin` to trade
throughput for recall, route `REVIEW_REQUIRED` to people, and audit a sample of
approved output.

## Limits

- Spain-Spanish clinical case reports with synthetic PHI. Mexican identifiers
  (CURP, RFC, CLABE) come from the deterministic rules, not this model, and no
  Mexican or financial documents were used for training. Evaluate on your own
  annotated holdout before relying on it.
- The financial Gretel corpus loader is implemented but was not executed (see
  [PUBLIC_CORPORA.md](PUBLIC_CORPORA.md)).
- Hashed features can still be confirmed by a dictionary attack. A model you
  train on private data with `scripts/train_span_tagger.py jsonl` is sensitive:
  keep `min_feature_docs` high and store the file like the data itself.
