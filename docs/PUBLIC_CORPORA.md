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

## Ready to use: financial

| Corpus | Domain / language | Size and gold | License | Status |
| --- | --- | --- | --- | --- |
| [Gretel `synthetic_pii_finance_multilingual`](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) | LLM-generated financial documents (statements, contracts, invoices, loan forms…); English, **Spanish**, French, German, Italian, Dutch, Swedish | ~56k documents (about 4.6k Spanish); 29 PII types with character offsets | Apache-2.0 | Loader, label mapping and evaluation implemented (`load_gretel_finance`, `benchmark_public_quality.py gretel_finance`). **Not yet executed**: the Hugging Face host was not reachable from the build environment |

Steps, from a machine that can reach Hugging Face:

```sh
# 1. Download a pinned revision (outside the repository)
git clone https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual ../work/gretel-raw
git -C ../work/gretel-raw log -1 --format=%H        # record this revision

# 2. Register the files: copies them outside the repository and pins their SHA-256
python - <<'EOF'
from pathlib import Path
from deidflow.benchmarks.span_corpus import GRETEL_FINANCE, register_local_files
files = sorted(Path("../work/gretel-raw").rglob("*.parquet"))
print(register_local_files("gretel_finance", files, "../work/public-corpora/verified", GRETEL_FINANCE))
EOF

# 3. Evaluate rules and the tagger on the Spanish documents (needs deidflow[tables])
python scripts/benchmark_public_quality.py gretel_finance \
    --corpus ../work/public-corpora/verified/gretel_finance --split test --language Spanish \
    --tagger src/deidflow/models/es-clinical-meddocan-1.json.gz \
    --output benchmarks/results/tagger/public-gretel-finance-es.json
```

The loader fails closed: a missing field, an unknown PII label or an offset that
does not match the text raises an error instead of dropping gold spans. To train
a financial tagger, export disjoint train/validation/test JSONL files (for
example split by `document_type`) in the span JSONL format below and run
`scripts/train_span_tagger.py jsonl`. Keep the test file untouched until the
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
