# Built-in span taggers (`es-clinical`, `es-finance`, `es-general`)

Local statistical detectors for Spanish personal data in free text, packaged
inside the wheel and usable with no optional dependency. `es-clinical` is
trained on clinical case reports (MEDDOCAN); `es-finance` on synthetic financial
documents (Gretel); `es-general` on both plus synthetic letters, forms, e-mails,
contracts, HR, legal, education and government documents from 14 countries
(see [general model](#general-model-es-general)). For unknown content use the
router, `--tagger builtin:auto`, which sends clinical text to `es-clinical` and
everything else to `es-general`.

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
deidflow deidentify carta.txt --output carta.safe.txt --tagger builtin:es-finance
```

```python
from deidflow.nlp import CombinedNER, SpanTagger

both = CombinedNER(SpanTagger.builtin("es-clinical"), SpanTagger.builtin("es-finance"))
engine = DeidEngine(nlp=both)  # broadest coverage, lower precision
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
- For financial text use `es-finance` (below); `es-clinical` scores 0.097 exact
  F1 on the Gretel financial test set.
- Hashed features can still be confirmed by a dictionary attack. A model you
  train on private data with `scripts/train_span_tagger.py jsonl` is sensitive:
  keep `min_feature_docs` high and store the file like the data itself.

## Financial model (`es-finance`)

| Field | Value |
| --- | --- |
| File | `src/deidflow/models/es-finance-gretel-1.json.gz` (1.9 MB) |
| SHA-256 | `f7a28b8fef3ccc1090d171b693f744098b4032008a48b56530c5aabdf371679c` |
| Training data | [Gretel `synthetic_pii_finance_multilingual`](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual), Apache-2.0, revision `7b844d1`, Spanish train file (4,148 LLM-generated financial documents in 60 document types, 17,569 spans). Files pinned by SHA-256 in `benchmarks/public-sources/gretel_finance.json` |
| Protocol | Weights: 3,746 documents. Epoch selection and calibration: a 10% holdout of the train file chosen by a hash of each text (402 documents). The published Spanish **test** file (461 documents, 1,972 mentions) was evaluated once, after freezing. `min_feature_docs` 5 (0.7142 validation F1) beat 10 (0.7060) by more than the 0.002 tie margin |
| Labels | `PERSON`, `ORGANIZATION`, `ADDRESS`, `DATE`, `DATE_OF_BIRTH`, `PHONE`, `EMAIL`, `BANK_ACCOUNT` (IBAN, BBAN, routing, SWIFT/BIC), `PAYMENT_CARD`, `NATIONAL_ID`, `PASSPORT`, `CUSTOMER_ID`, `EMPLOYEE_ID`, `CREDENTIAL`, `API_KEY`, `IP_ADDRESS`, `LOCATION` |

There are no identical texts between the train and test files, but 24% of the
test (category, value) pairs also occur in train, mostly common names and
company names. 440 of 15,825 training spans (2.8%) overlap another span or do not
align with token boundaries and were skipped.

Held-out Gretel Spanish test (`public-gretel-finance-es-test.json`):

| Pipeline | Exact P | Exact R | Exact F1 [95% CI] | Sensitive-character recall | Docs with any uncovered gold character |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rules | 0.427 | 0.241 | 0.308 [0.272, 0.348] | 0.310 | 384 / 461 |
| `es-clinical` (out of domain) | 0.093 | 0.101 | 0.097 [0.080, 0.114] | 0.321 | 394 |
| **`es-finance`** | **0.801** | **0.688** | **0.740 [0.709, 0.768]** | 0.790 | 216 |
| Rules + `es-finance` | 0.606 | 0.725 | 0.660 [0.631, 0.691] | 0.831 | 186 |
| Rules + both models | 0.353 | 0.728 | 0.475 [0.445, 0.506] | **0.847** | **179** |

- `es-finance` ECE on its own domain: 0.051. Calibration does **not** transfer
  across domains: `es-clinical` on financial text has ECE 0.69, and
  `es-finance` on MEDDOCAN 0.20. Use the model that matches the text before
  trusting scores.
- Per-type exact recall (`es-finance`): PASSPORT 0.92, PHONE 0.92, IP_ADDRESS
  0.87, ADDRESS 0.77, BANK_ACCOUNT 0.77, NATIONAL_ID 0.77, PERSON 0.74, EMAIL
  0.74, ORGANIZATION 0.58, DATE 0.55, PAYMENT_CARD 0.41, CUSTOMER_ID 0.35,
  EMPLOYEE_ID 0.37, CREDENTIAL 0.47, LOCATION 0.00 (one test mention).
- On MEDDOCAN test, adding `es-finance` to `es-clinical` raises character
  recall from 0.966 to 0.971 but lowers exact precision from 0.968 to 0.849
  (`public-meddocan-test-with-finance.json`).

End-to-end release decisions on the Gretel Spanish test (`release-gate-gretel-test*.json`):

| Configuration | APPROVED | REVIEW_REQUIRED | BLOCKED | Approved docs that still leak ≥1 gold character | Output sensitive-character recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rules only (`require_ner=False`) | 260 | 199 | 2 | 210 of 260 (80.8%) | 0.310 |
| Rules + `es-finance` | 161 | 287 | 13 | 57 of 161 (35.4%) | 0.831 |
| Rules + `es-finance`, `review_margin=60` | 118 | 332 | 11 | 31 of 118 (26.3%) | 0.868 |

The margin of 60 was chosen on MEDDOCAN dev and not retuned for finance.
Financial text is much harder than clinical headers: prose, company names and
many identifier formats. **Do not run financial documents unattended**; review
`REVIEW_REQUIRED` output, sample approved output, and never use the explicit
rules-only gate for free-form financial text. Mexican financial identifiers
(CLABE, RFC, CURP) come from the deterministic rules; IBANs are now also
validated by checksum. The corpus is LLM-generated and European in style, so
evaluate on your own documents before relying on these numbers.

## General model (`es-general`)

| Field | Value |
| --- | --- |
| File | `src/deidflow/models/es-general-2.json.gz` (3.1 MB) |
| SHA-256 | `f3008720a246e32b7a2adaf4af2ba9a03fb665caadcf698658b029a73042c173` |
| Training data | MEDDOCAN train (CC-BY-4.0), Gretel Spanish train minus its 10% holdout (Apache-2.0), and 5,000 documents of `deidflow.benchmarks.synthetic_es` from 51 training template families (seed 1729, Faker 40.44.0): 9,246 documents, 1.5 M tokens |
| Protocol | Epoch selection and calibration on MEDDOCAN dev, the Gretel holdout and 600 synthetic documents from validation-only template families (1,252 documents); epoch 29 of 30, validation F1 0.8640. Test sets evaluated once after freezing; synthetic test documents come from a third, disjoint set of template families |
| History | `es-general-1` (3,000 synthetic documents from 21 families, validation F1 0.8456) shipped in the first `es-general` release; `es-general-2` added 30 training-only families (more genres and places in running text) without changing the validation or test families |
| Labels | Union of both models' labels plus `TAX_ID`, `INSURANCE_ID`, `REGIONAL_ID` and `IP_ADDRESS` |

The synthetic generator writes documents of many genres (appointment letters,
payslips, rental contracts, court notices, school records, police reports,
customer chats, insurance claims...) with names, companies and streets from
Faker's Spanish locales and identifiers with valid check digits for Mexico,
Spain, Argentina, Colombia, Chile, Peru, Ecuador, Venezuela, Uruguay,
Guatemala, the Dominican Republic, El Salvador, Costa Rica and the United
States. Template families are split three ways, so validation and test
documents use phrasings never seen in training. Values still come from the same
generator, so these figures measure robustness to new layouts and wording, not
to real documents from those countries.

Validation (choice of routing; `rules +` means `DeidEngine(nlp=...)`):

| Validation set | Pipeline | Exact F1 | Sensitive-char recall |
| --- | --- | ---: | ---: |
| MEDDOCAN dev | `es-clinical` / `es-general` | **0.952** / 0.937 | **0.969** / 0.957 |
| Gretel holdout | `es-finance` / `es-general` | 0.714 / **0.722** | 0.766 / **0.793** |
| Synthetic, validation families | previous router / `es-general` | 0.426 / **0.737** | 0.602 / **0.787** |
| Synthetic, validation families | rules + previous router / rules + `es-general` | 0.548 / **0.755** | 0.697 / **0.860** |

`es-general` is weaker than `es-clinical` on clinical text, so the router keeps
`es-clinical` for documents it classifies as clinical and sends financial and
low-evidence documents to `es-general` (which replaced both `es-finance` and
"run both" on those routes). Of the three configurations tried on validation,
this one matched `es-clinical` on MEDDOCAN dev and scored best on the Gretel
holdout; running `es-general` alone scored 0.01 higher F1 on synthetic
validation but 0.013 lower on MEDDOCAN dev.

Validation of `es-general-2` against `es-general-1` (same validation documents,
rules from #27 in both):

| Validation set | Pipeline | `es-general-1` F1 / char recall | `es-general-2` F1 / char recall |
| --- | --- | ---: | ---: |
| MEDDOCAN dev | tagger alone | 0.937 / 0.957 | 0.937 / 0.960 |
| Gretel holdout | rules + `auto` | 0.644 / 0.826 | 0.645 / 0.830 |
| Synthetic validation families | tagger alone | 0.737 / 0.787 | **0.809** / **0.866** |
| Synthetic validation families | rules + `auto` | 0.746 / 0.868 | **0.793** / **0.909** |

Location recall on the synthetic validation families rose from 0.20 to 0.49 and
documents with an uncovered sensitive character fell from 443 to 338 of 600;
clinical documents keep routing to `es-clinical`, so MEDDOCAN is unchanged.

Held-out test results, evaluated once (`benchmarks/results/comparison/`):

| Test set | Pipeline | Exact F1 [95% CI] | Sensitive-char recall | Docs with any uncovered gold char | Over-redaction |
| --- | --- | ---: | ---: | ---: | ---: |
| Synthetic, test families (600 docs, 3,450 mentions) | previous `auto` | 0.544 | 0.773 | 472 | 2.44% |
| | `auto` with `es-general-1` | 0.785 [0.773, 0.797] | 0.929 | 295 | 1.97% |
| | **`auto` (`es-general-2`)** | **0.844** [0.831, 0.857] | 0.954 | 212 | **0.29%** |
| | rules + previous `auto` | 0.624 | 0.842 | 388 | 4.55% |
| | rules + `auto` with `es-general-1` | 0.786 | 0.947 | 236 | 3.72% |
| | **rules + `auto` (`es-general-2`, address rules)** | 0.836 | **0.968** | **168** | 3.43% |
| Gretel Spanish test (461 docs) | previous `auto` | 0.707 [0.658, 0.744] | 0.789 | 216 | 0.89% |
| | rules + previous `auto` | 0.629 | 0.830 | 184 | 2.34% |
| | `auto` with `es-general-1` | 0.740 [0.715, 0.767] | 0.798 | 208 | 0.73% |
| | rules + `auto` with `es-general-1` | 0.655 | 0.838 | 178 | 2.19% |
| | **`auto` (`es-general-2`)** | **0.743** [0.715, 0.768] | 0.808 | 203 | 0.80% |
| | **rules + `auto` (`es-general-2`, address rules)** | 0.659 | **0.851** | **168** | 2.35% |
| MEDDOCAN test (250 docs) | `auto` (all routed to `es-clinical`) | 0.958 | 0.966 | 100 | 0.09% |

On the Gretel test the router now equals `es-finance` used with the domain known
(0.740). `es-finance` remains available as `SpanTagger.builtin("es-finance")`.

End to end with `Policy.strict()` (rules + `auto`, `balanced`; files
`release-gate-v3-*.json` for `es-general-1`, `release-gate-v4-*.json` for
`es-general-2` with the address rules; test sets evaluated once):

| Test set | APPROVED | Approved docs leaking a direct identifier [95% CI] | Approved docs leaking any category | Over-redaction | Output sensitive-character recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gretel, previous router | 161 / 461 | 24 (14.9%) [10.2, 21.2] | 57 (35.4%) | 2.40% | 0.831 |
| Gretel, `auto` | 207 / 461 | 31 (15.0%) [10.8, 20.5] | 69 (33.3%) | 2.41% | 0.838 |
| Synthetic test families, `auto` | 291 / 600 | 46 (15.8%) [12.1, 20.4] | 89 (30.6%) | 3.61% | 0.947 |
| Gretel, `auto` (`es-general-2`) | 196 / 461 | 27 (13.8%) [9.6, 19.3] | 60 (30.6%) | 2.57% | 0.851 |
| Synthetic test families, `auto` (`es-general-2`) | 323 / 600 | 52 (16.1%) [12.5, 20.5] | 94 (29.1%) | 3.34% | 0.968 |

With `es-general-2` more synthetic documents are `BLOCKED` (79 instead of 31,
Gretel 18 instead of 15): in these the first scan missed a name or place that
the verification rescan of the transformed text then found, so the gate
refused to release them instead of approving a leak.

The new route approves more financial documents at the same leak rate, but
about one approved document in seven still leaks a direct identifier.
`es-general-2`'s `assurance` profile (`redact_margin` 320, re-tuned on
validation) reached the 2% validation target by approving 107 of 1,002
validation documents while redacting about 28% of non-sensitive text
(`operating-points-es-general.json`; for `es-general-1` it approved 3). It is
packaged for completeness but is rarely usable.

## Operating profiles, domain routing and leak targets

Three controls were added to trade review load and over-redaction for fewer
leaks, then measured end to end. Every choice below was made on validation data
(MEDDOCAN dev, the Gretel train holdout); test sets were evaluated once.

- `redact_margin`: tokens the model tagged `O` by less than this margin are
  redacted without forcing review (`context` contains `redact_only`).
- `review_margin`: the same, but the document goes to `REVIEW_REQUIRED`.
- Packaged profiles: `SpanTagger.builtin(name, profile="balanced" | "assurance")`
  or CLI `--tagger-profile`. `assurance` is the margin pair that approved the most
  validation documents while keeping the approved **direct-identifier** leak rate
  at or below 2% (`scripts/tune_operating_points.py`, grid in
  `operating-points-*.json`).
- Domain router: `DomainRouter.builtin()` or CLI `--tagger builtin:auto`. A
  Naive Bayes document classifier (hashed features, trained on the training
  splits only) classifies each document as clinical or financial; clinical
  documents go to `es-clinical`, financial ones and those whose evidence margin
  is below 0.5 to `es-general` (until the `es-general` release, to
  `es-finance` and to both models; the measurements below used that version). That threshold was chosen on validation
  as the smallest with at most 1% of documents routed to the wrong single model;
  the misrouted ones were machine formats (BAI, CSV, FIX, MT940, SWIFT, EDI).

Direct identifiers are names, contact data, addresses, dates of birth and every
ID, account, card or credential category (`DIRECT_IDENTIFIERS` in
`deidflow.benchmarks.release_gate`). Dates, ages, places, organizations,
occupations and other quasi-identifiers are counted in the any-category leak.
On validation, organizations were the largest share of leaked spans in the
financial set, and most leaks were whole missed entities, not boundary slivers.

Routing on the held-out test sets (`public-*-test-router.json`): all 250
MEDDOCAN documents went to `es-clinical` (identical results); of 461 Gretel
documents, 433 went to `es-finance`, 24 to both and 4 to `es-clinical`, giving
exact F1 0.707, versus 0.740 when the domain is known and 0.496 when both models
always run.

Held-out release decisions (`release-gate-v2-*.json`, rules + tagger):

| Test set / profile | APPROVED | Approved docs leaking a direct identifier [95% CI] | Approved docs leaking any category | Over-redaction | Output sensitive-character recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| MEDDOCAN, balanced | 149 / 250 | 15 (10.1%) [6.2, 15.9] | 40 (26.8%) | 0.36% | 0.968 |
| MEDDOCAN, assurance | 130 / 250 | 10 (7.7%) [4.2, 13.6] | 27 (20.8%) | 0.44% | 0.976 |
| MEDDOCAN, router + assurance | 130 / 250 | 10 (7.7%) [4.2, 13.6] | 27 (20.8%) | 0.44% | 0.976 |
| Gretel, balanced | 161 / 461 | 24 (14.9%) [10.2, 21.2] | 57 (35.4%) | 2.40% | 0.831 |
| Gretel, assurance | 22 / 461 | 0 (0.0%) [0.0, 14.9] | 2 (9.1%) | 17.6% | 0.973 |
| Gretel, router + assurance | 24 / 461 | 2 (8.3%) [2.3, 25.8] | 4 (16.7%) | 17.5% | 0.970 |

**The 2% target held on validation (1.7% clinical) but not on test (7.7%).**
Validation had about ten leaking approved documents, too few to set a threshold
that generalizes. The financial `assurance` profile reaches zero direct leaks
only by redacting about 18% of non-sensitive text and approving about 5% of
documents, which is rarely usable. Margins and routing cannot fix the misses
the models are confident about: lowering leaks substantially needs better
models (more and in-domain training data, stronger architectures) or human
review. Until a representative holdout shows otherwise, treat every profile as
assisted de-identification.
