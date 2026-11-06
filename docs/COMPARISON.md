# DeidFlow compared with Presidio and spaCy

Head-to-head on the two public, human-annotated Spanish test sets that DeidFlow
uses and on DeidFlow's synthetic multi-country test set, with identical scoring
for every system. No LLM is used by any of them.
Raw reports: `benchmarks/results/comparison/`. Reproduce with
`scripts/benchmark_public_quality.py ... --spacy-model <es_core_news_lg> --tagger auto=builtin:auto`.

## Systems

| System | Configuration |
| --- | --- |
| **DeidFlow rules** | Deterministic rules only (`DeidEngine(country="ALL")`) |
| **DeidFlow auto** | Packaged taggers through the domain router (`--tagger builtin:auto`: `es-clinical` for clinical text, `es-general` for the rest), no rules |
| **DeidFlow rules + auto** | Product default with a tagger: rules plus router |
| spaCy | `es_core_news_lg` 3.7.0 (GPL-3.0, downloaded from Hugging Face; run on spaCy 3.8.18, which warns about the minor-version mismatch). `PER`, `LOC`, `ORG` mapped to PERSON, LOCATION, ORGANIZATION |
| Presidio | `presidio-analyzer` 2.2.366 out of the box for Spanish on the same spaCy model, `score_threshold=0`; entity names mapped to the shared taxonomy (person, location, organization, e-mail, phone, card, date, Spanish NIF/NIE, IBAN, IP, SSN, nationality) |
| DeidFlow rules + spaCy | Rules plus the spaCy model through `SpacyNER` |

Neither baseline was tuned for these corpora; they are measured as a user
would install them. DeidFlow's taggers were trained on the corpora's training
splits, so the comparison shows what a trained, domain-matched pipeline adds
over general-purpose tools, not an apples-to-apples model architecture study.

## MEDDOCAN test (clinical, 250 documents, 5,661 mentions)

| Pipeline | Exact P | Exact R | Exact F1 [95% CI] | Sensitive-char recall | Docs fully covered | Over-redaction | p50 ms/doc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **DeidFlow auto** | **0.968** | 0.949 | **0.958** [0.950, 0.966] | 0.966 | 150 / 250 | **0.09%** | 27 |
| **DeidFlow rules + auto** | 0.820 | **0.953** | 0.882 [0.875, 0.888] | **0.969** | **162 / 250** | 0.29% | 31 |
| DeidFlow rules | 0.707 | 0.431 | 0.536 [0.527, 0.544] | 0.595 | 0 / 250 | 0.23% | 6 |
| Presidio | 0.355 | 0.372 | 0.363 [0.355, 0.372] | 0.661 | 0 / 250 | 3.87% | 78 |
| spaCy | 0.283 | 0.239 | 0.259 [0.251, 0.267] | 0.496 | 0 / 250 | 3.82% | 59 |
| DeidFlow rules + spaCy | 0.458 | 0.660 | 0.541 [0.533, 0.548] | 0.875 | 0 / 250 | 3.93% | 64 |

## Gretel synthetic financial, Spanish test (461 documents, 1,972 mentions)

| Pipeline | Exact P | Exact R | Exact F1 [95% CI] | Sensitive-char recall | Docs fully covered | Over-redaction | p50 ms/doc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **DeidFlow auto** | **0.784** | 0.705 | **0.743** [0.715, 0.768] | 0.808 | 258 / 461 | **0.80%** | 22 |
| **DeidFlow rules + auto** | 0.591 | **0.744** | 0.659 [0.630, 0.688] | **0.851** | **293 / 461** | 2.35% | 24 |
| DeidFlow rules | 0.430 | 0.266 | 0.329 [0.293, 0.366] | 0.353 | 79 / 461 | 1.81% | 3 |
| Presidio | 0.128 | 0.285 | 0.177 [0.160, 0.194] | 0.637 | 92 / 461 | 8.44% | 41 |
| spaCy | 0.092 | 0.154 | 0.115 [0.098, 0.131] | 0.513 | 76 / 461 | 6.15% | 33 |
| DeidFlow rules + spaCy | 0.178 | 0.405 | 0.247 [0.228, 0.268] | 0.730 | 127 / 461 | 7.46% | 37 |

## Synthetic multi-country test families (600 documents, 3,450 mentions)

Letters, forms, contracts, payslips, court and police documents, school records,
chats and claims from 14 countries (`deidflow.benchmarks.synthetic_es`, seed
1729, Faker 40.44.0), written with template families that were never used for
training or validation. DeidFlow's `es-general-2` saw other families from the
same generator during training; the baselines did not. Treat this as a measure
of coverage of Latin American and Spanish formats and layouts, not of real
documents.

| Pipeline | Exact P | Exact R | Exact F1 [95% CI] | Sensitive-char recall | Docs fully covered | Over-redaction | p50 ms/doc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **DeidFlow auto** | **0.883** | 0.809 | **0.844** [0.831, 0.857] | 0.954 | 388 / 600 | **0.29%** | 4 |
| **DeidFlow rules + auto** | 0.798 | **0.878** | 0.836 [0.826, 0.844] | **0.968** | **432 / 600** | 3.43% | 5 |
| DeidFlow rules | 0.766 | 0.474 | 0.586 [0.573, 0.597] | 0.570 | 0 / 600 | 3.24% | 1 |
| Presidio | 0.487 | 0.427 | 0.455 [0.437, 0.474] | 0.684 | 24 / 600 | 5.64% | 15 |
| spaCy | 0.478 | 0.356 | 0.408 [0.395, 0.424] | 0.610 | 16 / 600 | 5.61% | 11 |
| DeidFlow rules + spaCy | 0.598 | 0.793 | 0.682 [0.670, 0.695] | 0.967 | 388 / 600 | 7.92% | 12 |

"Docs fully covered" counts documents in which every gold sensitive character
is inside some prediction; over-redaction is the share of non-sensitive
characters a pipeline covered. Exact matching requires the same category and
boundaries; overlap scores are in the JSON reports.

## Reading the results

- On the two public sets DeidFlow's packaged taggers more than double the F1 of
  the best general-purpose alternative, while redacting four to forty times
  less non-sensitive text, and run about twice as fast on one CPU core. On the
  synthetic multi-country set the margin is smaller (0.844 against 0.455) and
  DeidFlow's rules plus spaCy reach similar character coverage at twice the
  over-redaction.
- Presidio covers more sensitive characters than spaCy because its regex
  recognizers add e-mails, phones and dates, but its generic NER labels many
  ordinary words, which is why its over-redaction is high.
- Even the best configuration leaves at least one sensitive character
  uncovered in 88 of 250 clinical, 168 of 461 financial and 168 of 600
  synthetic test documents.
  Human review of `REVIEW_REQUIRED` output remains necessary
  ([release-gate results](TAGGER.md#operating-profiles-domain-routing-and-leak-targets)).
- Both public corpora are from Spain or European-style synthetic text; neither
  covers Mexican or other Latin American documents. Latin American coverage is
  measured only on DeidFlow's synthetic set and the identifier check-digit
  tests ([COUNTRIES.md](COUNTRIES.md)), not on an annotated corpus of real
  documents.
