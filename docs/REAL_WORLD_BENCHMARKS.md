# Public real-world validation

Executed locally on 2026-11-02. These measurements validate limited detection behavior. They do not establish automatic privacy-safe release of arbitrary documents. The runner records package version 0.2.0 while evaluating candidate changes before the release gate.

## Acquired sources and permissions

| Source | Provenance and task | Evaluated human gold | Reuse evidence |
|---|---|---|---|
| MEDDOCAN | Spanish clinical narratives from published SciELO cases, enriched with synthetic PHI: **semi-synthetic clinical**, not private patient records or a Mexican enterprise sample | dev 250 / 5,801 spans; test 250 / 5,661 spans | Official repository CC-BY-4.0; attribution in manifests |
| TAB v1 | Actual public English ECHR cases with contextual masking decisions: **public judicial**, separate from MEDDOCAN | Reviewed annotator per document; DIRECT/QUASI only; test 127 / 5,384 spans | Official corpus README explicitly identifies TAB as MIT; preserve copyright/license notices |

The [MEDDOCAN maintainers](https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN/tree/783a6df385c975b328c99bcffb54196a9ba4078a) describe construction, human review and [annotation guidelines](https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN/tree/783a6df385c975b328c99bcffb54196a9ba4078a/guidelines). [TAB's corpus description and license statement](https://github.com/NorskRegnesentral/text-anonymization-benchmark/tree/558e09e26d6b36f5f78440074e6a233946d98bd9) apply to the corpus, rather than merely describing the evaluation code. The research paper has separate licensing and is not redistributed. No authentication or access restriction was bypassed. MEDDOCAN was available in its official repository; gated Zenodo access was unnecessary.

Pinned archive URLs, commits, SHA256 hashes, formats, anonymity status, attribution and license URLs are in `benchmarks/public-sources/{meddocan,tab}.json`. Raw downloads stay under workspace `work/public-corpora/verified/`, outside the source repository. No raw documents, entity values, per-document filenames or individual prediction coordinates are committed. Acquisition validates the pinned hash and extracts bounded selected members. The benchmark validates every corpus file against that archive before inference. Gold offsets and annotated substrings must match the original Unicode text exactly.

## Experimental contract

1. The frozen baseline is a Git archive of v0.2.0 commit `0b79d3d`, executed in a separate subprocess with the same Python environment. Final reports record its source SHA256. No model download occurs during inference.
2. MEDDOCAN dev was measured before any edits: `public-meddocan-dev-before.json`. Only development errors informed generic contextual rules; no corpus names, PHI values or source vocabularies were embedded. Rules were frozen before the first test evaluation. Future tuning needs a new holdout.
3. The official test is accompanied by a metadata-selected source-article-disjoint subset: exclude test article stems occurring in train/dev. Selection uses no predictions or error labels. No classifier was trained on either public corpus.
4. All Spanish NER runs use the same separately provisioned local `es_core_news_sm-3.8.0` asset. spaCy, Presidio Spanish and both DeidFlow hybrids receive identical texts and gold. This optional GPL-licensed benchmark asset is not bundled in DeidFlow; consult the license inventory before distributing models.
5. Current and frozen inference deny socket connections and DNS. Reports record current inference network attempts. Online acquisition is an explicit separate operation.
6. Exact category/span matching and maximum one-to-one overlap matching are reported separately. Full mapped taxonomy is primary; a fixed target subset and PERSON-only scores are secondary. The target subset does not imply every baseline recognizes every category. PERSON-only supplies a narrower shared NER task. All mappings, aliases and clinical-category exclusions appear in JSON.

TAB uses the lexicographically first annotator appearing in both `quality_checked` and `annotations`; divergent annotations are not unioned. NO_MASK mentions are negative for this contextual task. TAB's published coreference metrics are not reproduced by this span adapter, and this is not a TAB leaderboard claim.

## Held-out Spanish clinical results

250 documents and 5,661 human gold mentions. Detection metrics do not measure OCR, PDF transformation or release approval.

<!-- MEDDOCAN_TABLE -->

| Pipeline | Exact P | Exact R | Exact F1 | F1 95% CI | Overlap F1 | p50 ms/document |
|---|---:|---:|---:|---:|---:|---:|
| deidflow_v0.2.0_rules | 0.5361 | 0.1574 | 0.2433 | [0.2368, 0.2501] | 0.3867 | 1.77 |
| deidflow_candidate_rules | 0.6927 | 0.4022 | 0.5089 | [0.5004, 0.5177] | 0.6784 | 2.87 |
| deidflow_v0.2.0_rules_plus_spacy | 0.2914 | 0.2948 | 0.2931 | [0.2850, 0.3025] | 0.4266 | 101.44 |
| spacy_spanish | 0.1985 | 0.1441 | 0.1670 | [0.1585, 0.1775] | 0.2303 | 157.01 |
| presidio_spanish | 0.2343 | 0.2782 | 0.2544 | [0.2480, 0.2627] | 0.3056 | 211.27 |
| deidflow_candidate_rules_plus_spacy | 0.4145 | 0.5370 | 0.4679 | [0.4602, 0.4756] | 0.5939 | 181.56 |

<!-- END_MEDDOCAN_TABLE -->

Rules exact F1 improves from 0.2433 to 0.5089. General NER increases candidate recall but adds false positives, lowering candidate exact F1 to 0.4679. The task includes clinical identifiers and demographics that generic NER does not target, so full-taxonomy rankings are not universal product comparisons.

Sensitive-character recall improves from 0.3500 to 0.5376 for rules and from 0.6384 to 0.7593 for the matched hybrid. All 250 documents still contain at least one uncovered sensitive character. These detection coverage scores do not inspect transformed outputs.

The source-article-disjoint subset excludes 24 test documents, retaining **226 documents / 5,131 gold mentions**:

<!-- SOURCE_TABLE -->

| Pipeline | Exact P | Exact R | Exact F1 | F1 95% CI | Overlap F1 | p50 ms/document |
|---|---:|---:|---:|---:|---:|---:|
| deidflow_v0.2.0_rules | 0.5333 | 0.1561 | 0.2415 | [0.2348, 0.2482] | 0.3853 | 1.91 |
| deidflow_candidate_rules | 0.6916 | 0.3995 | 0.5065 | [0.4975, 0.5161] | 0.6757 | 3.09 |

<!-- END_SOURCE_TABLE -->

The gain persists (0.2415 to 0.5065). This does not establish unseen identities, templates or providers. Official MEDDOCAN splits have zero identical texts but share 15/18/7 source article stems across train-dev/train-test/dev-test. Recurring category/value hashes are reported in `public-split-integrity.json`. TAB dev/test also has zero identical texts and recurring entity strings. TAB training overlap was not measured because some training records lack reviewed gold; unchecked annotations are not silently substituted.

## Public English judicial negative result

<!-- TAB_TABLE -->

| Pipeline | Exact P | Exact R | Exact F1 | F1 95% CI | Overlap F1 | p50 ms/document |
|---|---:|---:|---:|---:|---:|---:|
| deidflow_v0.2.0_rules | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | 0.0015 | 2.51 |
| deidflow_candidate_rules | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | 0.0015 | 3.55 |

<!-- END_TAB_TABLE -->

Both rule versions have exact F1 **0.0000** on TAB test. Overlap recall is 0.0007. This exposes the practical English narrative limitation of the Spanish/Mexican rule pipeline. English spaCy/Presidio are explicitly unavailable because no reviewed local English model was provisioned. Applying a Spanish model to English would not be a comparable baseline.

## Metric definitions and limits

- JSON reports include per-type recall, source/language/format/domain strata, frequency strata, false-redaction character rate, uncertainty-candidate proxy and document bootstrap 95% CIs (500 resamples, seed1729). CIs require at least 20 documents and do not account for provider/source correlations.
- `document_leakage_rate` means at least one gold mention lacks a typed exact/overlap match under the selected contract. `entity_level_recall` is overlap mention recall; it is not identity resolution.
- `coverage_leakage` separately measures union-of-predicted-span sensitive-character coverage regardless of category, and complete coverage of all occurrences of category/casefolded-value groups. These groups are not verified personal identities. Detection coverage is not transformed-output verification. Partial overlap must not be used as a release gate.
- False-redaction rate is the fraction of annotated nonsensitive characters covered by predictions. It is not specificity over an invented universe of negative entity spans; incomplete annotation can affect it.
- Scores are not calibrated probabilities. ECE remains null. The low-score/invalid-candidate document fraction is an uncertainty proxy, not an actual transformation review-required rate.
- Text corpora lack original page images/table geometry. OCR CER/WER, native-vs-scan quality, table reconstruction and actual output leakage are unavailable here. Separate PDF regression/operational reports have their own scope. Public unannotated PDFs cannot establish detection recall or F1.
- CPU timings describe one pass after current-detector warmup, with per-document p50/p95, RSS and throughput for current detectors. They are not controlled multi-run speedup claims: model loading, baseline coldness, process state and shared-machine load differ. Unmeasured baseline resource values are not invented. No GPU inference was used.

[LeakageBench](https://arxiv.org/abs/2609.02207) is a methodological reference for distinguishing entity localization from document risk. No LeakageBench images, gold, weights or published scores are used as DeidFlow evidence; its vision-language models are not executed.

## Reproduction

PowerShell from the repository, with the workspace environment, frozen baseline and explicitly installed local Spanish evaluation model. Acquisition is online; benchmark inference blocks networking.

```powershell
$python = '..\..\.venv\Scripts\python.exe'
& $python scripts/acquire_public_corpus.py meddocan --destination ../../work/public-corpora/verified --manifest benchmarks/public-sources/meddocan.json
& $python scripts/acquire_public_corpus.py tab --destination ../../work/public-corpora/verified --manifest benchmarks/public-sources/tab.json
& $python scripts/benchmark_public_quality.py meddocan --corpus ../../work/public-corpora/verified/meddocan --baseline ../../work/deidflow-v0.2.0 --split test --spacy-model ../../work/models/es_core_news_sm-3.8.0/es_core_news_sm/es_core_news_sm-3.8.0 --output benchmarks/results/public-meddocan-test.json --ci-repeats 500
& $python scripts/benchmark_public_quality.py meddocan --corpus ../../work/public-corpora/verified/meddocan --baseline ../../work/deidflow-v0.2.0 --split test --rules-only --source-group-holdout --output benchmarks/results/public-meddocan-source-disjoint.json --ci-repeats 500
& $python scripts/benchmark_public_quality.py tab --corpus ../../work/public-corpora/verified/tab --baseline ../../work/deidflow-v0.2.0 --split test --rules-only --output benchmarks/results/public-tab-test.json --ci-repeats 500
```

Re-running evaluation does not restore an untouched holdout for later tuning. Preserve the measured pre-change development artifact. Final detector and safety changes need separate regression validation before a local release.
