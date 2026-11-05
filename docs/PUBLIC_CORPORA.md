# Public corpora for testing and training

Which public annotated corpora DeidFlow can use for medical and financial
evaluation or training, under what terms, and how to load them. Raw corpora
always stay outside the repository; only aggregate metrics are committed.

## Integrated and used

| Corpus | Domain / language | Size and gold | License | Status in DeidFlow |
| --- | --- | --- | --- | --- |
| [SPACCC MEDDOCAN](https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN) | Clinical case reports, Spanish (Spain) | 1,000 documents; 22 PHI types; train 500 / dev 250 / test 250 | CC-BY-4.0 | **Trains the built-in `es-clinical` tagger** (train split), selects/calibrates it (dev) and evaluates it once (test). Pinned commit and SHA-256 digest manifest |
| [TAB](https://github.com/NorskRegnesentral/text-anonymization-benchmark) | ECHR court judgments, English | 1,268 documents with masking decisions | MIT | Evaluation only (negative English result for the Spanish rules) |

MEDDOCAN inserts synthetic personal data into published clinical case reports,
so it is realistic clinical Spanish without real patients. It is from Spain,
not Mexico: identifiers such as NHC/NASS and Spanish addresses dominate.

## Integrated and used: financial

| Corpus | Domain / language | Size and gold | License | Status in DeidFlow |
| --- | --- | --- | --- | --- |
| [Gretel `synthetic_pii_finance_multilingual`](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) | LLM-generated financial documents (statements, contracts, invoices, loan forms…); English, **Spanish**, French, German, Italian, Dutch, Swedish | ~56k documents; Spanish: train 4,148 / test 461 documents, 29 PII types with character offsets | Apache-2.0 | **Trains the built-in `es-finance` tagger** (Spanish train file, 10% text-hash holdout for selection and calibration) and evaluates it once on the Spanish test file. Revision `7b844d1` and file SHA-256s pinned in `benchmarks/public-sources/gretel_finance.json` |

Results are in [TAGGER.md](TAGGER.md#financial-model-es-finance): exact F1 0.740
for `es-finance` on the Spanish test file, versus 0.308 for the rules. The corpus
is synthetic and European in style (IBAN, SWIFT, European addresses), not Mexican.

Reproduce, from a machine that can reach `huggingface.co` and its file CDN:

1. Download the pinned files outside the repository and compare their SHA-256
   with `benchmarks/public-sources/gretel_finance.json`:

   ```sh
   REV=7b844d16738527a04264f50214cb426a4cea0897
   BASE=https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual/resolve/$REV
   mkdir -p ../work/gretel-raw
   for f in README.md data/Spanish_train-00000-of-00001.parquet data/Spanish_test-00000-of-00001.parquet; do
     curl -fL -o "../work/gretel-raw/$(basename "$f")" "$BASE/$f"
   done
   sha256sum ../work/gretel-raw/*
   ```

2. Register them (copies outside the repository and pins their SHA-256):

   ```python
   from pathlib import Path
   from deidflow.benchmarks.span_corpus import GRETEL_FINANCE, register_local_files

   files = sorted(Path("../work/gretel-raw").iterdir())
   spec = {**GRETEL_FINANCE, "revision": "7b844d16738527a04264f50214cb426a4cea0897"}
   register_local_files("gretel_finance", files, "../work/public-corpora/verified", spec)
   ```

3. Train on the train file only, then evaluate once on the test file
   (needs `deidflow[tables,training]`):

   ```sh
   python scripts/train_span_tagger.py gretel_finance \
       --corpus ../work/public-corpora/verified/gretel_finance \
       --version es-finance-gretel-1 --min-feature-docs 5 --output es-finance.json.gz
   python scripts/benchmark_public_quality.py gretel_finance \
       --corpus ../work/public-corpora/verified/gretel_finance --split test \
       --tagger clinical=builtin:es-clinical --tagger finance=builtin:es-finance \
       --output benchmarks/results/tagger/public-gretel-finance-es-test.json
   ```

The loader fails closed: a missing field, an unknown PII label or an offset that
does not match the text raises an error instead of dropping gold spans. To train
on your own annotations, export disjoint train/validation/test JSONL files in
the span JSONL format below and run `scripts/train_span_tagger.py jsonl`. Keep
the test file untouched until the
final evaluation.

## Worth adding (access or licensing needs a decision)

| Corpus | Why | Access / license (verify current terms) |
| --- | --- | --- |
| CARMEN-I (Hospital Clínic de Barcelona, PhysioNet) | Real Spanish and Catalan clinical records with PHI annotations; the closest public match to real hospital text | PhysioNet credentialed access and data use agreement; not redistributable and not usable for shipped weights without checking the agreement |
| MEDDOPROF, CANTEMIST, PharmaCoNER, DisTEMIST (Plan TL / BSC) | Spanish clinical occupations, tumour morphology, drugs and diseases; would cover the `OCCUPATION`, `DIAGNOSIS` and `MEDICATION` categories that MEDDOCAN barely annotates | Zenodo, CC-BY-4.0 |
| ai4privacy PII masking sets | Large multilingual synthetic PII sets including Spanish | Check each release: some versions restrict commercial use |
| n2c2/i2b2 2014 de-identification | Standard English clinical benchmark | Data use agreement required |

No public, span-annotated corpus of **Mexican** records (CURP, RFC, CLABE,
Mexican addresses and names in real documents) was found. For production in
Mexico, annotate a private holdout from your own documents with
`deidflow annotate` and evaluate on it before trusting any public number.

## Span JSONL format

One JSON object per line; offsets are Python string offsets, half-open:

```json
{"id": "doc-1", "text": "Cliente: Ana Ruiz", "spans": [{"start": 9, "end": 17, "label": "PERSON"}]}
```

Load it with `deidflow.benchmarks.span_corpus.load_span_jsonl`, which rejects
duplicate IDs or keys, out-of-range offsets and whitespace-only spans.
