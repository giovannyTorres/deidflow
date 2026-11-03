# Detection quality and remaining gaps

The candidate adds bounded Spanish contextual recognizers and preserves existing protected candidates. Held-out MEDDOCAN exact F1 improves from 0.2433 to 0.5089; remaining recall is insufficient for unattended release. [Public validation](REAL_WORLD_BENCHMARKS.md) documents permissions, independent human gold, taxonomies, baselines and uncertainty.

## Development evidence and changes

Before edits, frozen v0.2 rules and the untouched candidate each measured dev exact F1 0.2379 on 250 documents. Development false negatives included explicit surname fields, clinical/insurance/professional IDs, short/written calendar dates and patient-linked demographics. No test examples, PHI values or identity dictionaries were copied into recognizers.

Generic additions in `detectors/clinical.py` cover:

- Explicit name/surname and clinician/referrer fields, bounded before another label. Context is evidence, not registry confirmation of a person.
- Clinical, insurance and professional identifiers with explicit labels; DNI/NIE/NIF context plus checksum evidence. Invalid checksums remain protected and uncertain rather than disappearing. A valid checksum does not verify a real registry record.
- International-prefix phones with bounded punctuation/line breaks. Held-out phone recall does not improve, so no phone-quality gain is claimed.
- Full Spanish written and short numeric calendar dates, with calendar validation. DOB requires preceding birth context.
- Patient-associated numeric ages and sex/demographic mentions. Numeric age boundaries preserve existing age-bucketing behavior; MEDDOCAN often annotates a wider phrase, explaining the exact/overlap gap.

Rules dev exact F1 rises to 0.4930. Rules were frozen before test evaluation. Exact candidate fusion preserves protection and provenance; overlaps remain represented. `clinical-context-0.3` identifies these recognizers separately from package release version. Property tests vary surrounding text around critical identifiers and assert prior protected candidates remain protected. Synthetic fixtures check invalid dates, empty fields, checksum evidence and age bucketing. Existing detection tests remain intact.

## Held-out per-type recall

MEDDOCAN official test: 250 documents / 5,661 gold mentions. Exact matching requires category and both boundaries; overlap requires category and any shared character, using one-to-one assignment.

<!-- TYPE_TABLE -->

| Gold type | v0.2 exact R | Candidate exact R | Candidate overlap R |
|---|---:|---:|---:|
| ADDRESS | 0.0024 | 0.0024 | 0.5981 |
| AGE | 0.0405 | 0.0405 | 0.9093 |
| DATE | 0.8167 | 0.8380 | 0.8380 |
| DEMOGRAPHIC | 0.0000 | 0.8829 | 0.8829 |
| EMAIL | 0.9920 | 0.9920 | 0.9920 |
| INSURANCE_ID | 0.0000 | 0.9848 | 0.9848 |
| LOCATION | 0.0000 | 0.0000 | 0.0000 |
| MEDICAL_FACILITY | 0.0000 | 0.0000 | 0.0000 |
| OCCUPATION | 0.0000 | 0.0000 | 0.0000 |
| ORGANIZATION | 0.0000 | 0.0000 | 0.0000 |
| OTHER_SENSITIVE | 0.0000 | 0.0000 | 0.0000 |
| PATIENT_ID | 0.0000 | 0.9441 | 0.9472 |
| PERSON | 0.1125 | 0.3293 | 0.3838 |
| PHONE | 0.0303 | 0.0303 | 0.0909 |
| REGIONAL_ID | 0.0000 | 0.9915 | 0.9915 |

<!-- END_TYPE_TABLE -->

Explicit clinical/insurance/professional IDs improve markedly. Free-form names, addresses, facilities/organizations/locations, occupations and phones remain weak. This predominantly Spain-Spanish clinical corpus does not establish Mexican administrative or financial accuracy.

With the same optional Spanish NER model, hybrid exact recall increases from 0.2948 to 0.5370 and F1 from 0.2931 to 0.4679. Candidate rules alone have higher precision/F1 on this task. Generic NER adds recall and false positives; validation and independent output verification remain necessary. PERSON-only and fixed target-subset results allow inspection of taxonomy differences.

## Safety interpretation

All 250 MEDDOCAN test documents still miss an exact typed gold mention and leave at least one annotated sensitive character uncovered. Rules sensitive-character recall increases from 0.3500 to 0.5376; the matched hybrid increases from 0.6384 to 0.7593. Partial overlap can score a name while exposing characters. Final reports separately measure sensitive-character coverage and complete category/value coverage; these remain detection diagnostics.

TAB exposes an unchanged negative result: exact F1 is 0.0 on 127 real public English judgments. Spanish rules are not validated for unrestricted English judicial anonymization. No English NER baseline or private Gmail accuracy was executed by the coding agent.

Scores are heuristic, not calibrated probabilities. ECE is unavailable, and uncertain-candidate rate is not actual transformation review-required rate. Text-only corpora cannot measure OCR/layout quality. Public unannotated documents do not contribute supervised metrics.

## Artifacts and next evidence

- `public-meddocan-dev-before.json`: measured before detector edits; preserve as development baseline.
- `public-meddocan-dev-after.json`: development selection evidence, not held-out quality.
- `public-meddocan-test.json`: final official test with frozen/current rules and matched hybrids, spaCy and Presidio Spanish.
- `public-meddocan-source-disjoint.json`: metadata-selected article-disjoint subset.
- `public-tab-test-before.json` and `public-tab-test.json`: English negative result before/after.
- `public-split-integrity.json`: exact-text, recurring value and article overlap diagnostics.

Artifacts contain aggregate metrics without excerpts or per-record findings and remain local. Future tuning requires a fresh source/provider holdout, independently reviewed Mexican operational annotations and boundary improvements that preserve safe transformation behavior. Existing verification failures must keep blocking automatic approval.
