# DeidFlow compared with Presidio and spaCy

Head-to-head on the two public, human-annotated Spanish test sets that DeidFlow
uses, with identical scoring for every system. No LLM is used by any of them.
Raw reports: `benchmarks/results/comparison/`. Reproduce with
`scripts/benchmark_public_quality.py ... --spacy-model <es_core_news_lg> --tagger auto=builtin:auto`.

## Systems

| System | Configuration |
| --- | --- |
| **DeidFlow rules** | Deterministic rules only (`DeidEngine(country="ALL")`) |
| **DeidFlow auto** | Packaged taggers through the domain router (`--tagger builtin:auto`), no rules |
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
| **DeidFlow auto** | **0.968** | 0.949 | **0.958** [0.950, 0.966] | 0.966 | 150 / 250 | **0.09%** | 28 |
| **DeidFlow rules + auto** | 0.819 | **0.953** | 0.881 [0.874, 0.887] | **0.969** | **161 / 250** | 0.29% | 32 |
| DeidFlow rules | 0.699 | 0.417 | 0.522 [0.513, 0.530] | 0.556 | 0 / 250 | 0.22% | 6 |
| Presidio | 0.355 | 0.372 | 0.363 [0.355, 0.372] | 0.661 | 0 / 250 | 3.87% | 80 |
| spaCy | 0.283 | 0.239 | 0.259 [0.251, 0.267] | 0.496 | 0 / 250 | 3.82% | 61 |
| DeidFlow rules + spaCy | 0.452 | 0.646 | 0.531 [0.524, 0.539] | 0.861 | 0 / 250 | 3.92% | 66 |

## Gretel synthetic financial, Spanish test (461 documents, 1,972 mentions)

| Pipeline | Exact P | Exact R | Exact F1 [95% CI] | Sensitive-char recall | Docs fully covered | Over-redaction | p50 ms/doc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **DeidFlow auto** | **0.732** | 0.684 | **0.707** [0.658, 0.744] | 0.789 | 245 / 461 | **0.89%** | 18 |
| **DeidFlow rules + auto** | 0.558 | **0.722** | 0.629 [0.589, 0.663] | **0.830** | **277 / 461** | 2.34% | 19 |
| DeidFlow rules | 0.423 | 0.259 | 0.321 [0.287, 0.358] | 0.331 | 79 / 461 | 1.68% | 3 |
| Presidio | 0.128 | 0.285 | 0.177 [0.160, 0.194] | 0.637 | 92 / 461 | 8.44% | 42 |
| spaCy | 0.092 | 0.154 | 0.115 [0.098, 0.131] | 0.513 | 76 / 461 | 6.15% | 32 |
| DeidFlow rules + spaCy | 0.175 | 0.398 | 0.243 [0.224, 0.264] | 0.722 | 123 / 461 | 7.42% | 37 |

"Docs fully covered" counts documents in which every gold sensitive character
is inside some prediction; over-redaction is the share of non-sensitive
characters a pipeline covered. Exact matching requires the same category and
boundaries; overlap scores are in the JSON reports.

## Reading the results

- On both sets DeidFlow's packaged taggers more than double the F1 of the best
  general-purpose alternative, while redacting four to forty times less
  non-sensitive text, and run two to three times faster on one CPU core.
- Presidio covers more sensitive characters than spaCy because its regex
  recognizers add e-mails, phones and dates, but its generic NER labels many
  ordinary words, which is why its over-redaction is high.
- Even the best configuration leaves at least one sensitive character
  uncovered in 89 of 250 clinical and 184 of 461 financial test documents.
  Human review of `REVIEW_REQUIRED` output remains necessary
  ([release-gate results](TAGGER.md#operating-profiles-domain-routing-and-leak-targets)).
- Both corpora are from Spain or European-style synthetic text; neither covers
  Mexican or other Latin American documents. The international identifier pack
  ([COUNTRIES.md](COUNTRIES.md)) is verified by check-digit tests and synthetic
  documents, not by an annotated Latin American corpus.
