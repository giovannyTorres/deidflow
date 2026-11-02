# Reproducible evaluation

Run from the repository root after installing the benchmark extra:

```console
python scripts/benchmark_detection.py --output benchmarks/results/new-run --count 150 --repeats 3
python scripts/benchmark_workloads.py --output benchmarks/results/new-workloads.json
python scripts/benchmark_calibration.py --output benchmarks/results/new-calibration
```

The first command writes UTF-8 JSONL train/validation/test corpora and their
SHA-256 digests. The default seed is 1729. Source templates and entity namespaces
are disjoint across these partitions. The test corpus has distinct narratives,
multiline addresses, line-wrapped CLABE, an unlabelled person, an OCR-corrupted
identifier, a mixed-language example, and negatives
including general medical discussion. Annotation offsets are half-open Python
Unicode character indices, including original formatting. Examples are wholly
fictional; `example.org` addresses do not identify customers. Structurally valid
identifiers are not claims that an account, tax registration, or person exists.

This deliberately small synthetic corpus is a regression fixture, not a random
sample of Mexican documents. Many records share a handful of templates and
entity types. It cannot establish production accuracy, population-level
confidence intervals, legal compliance, or superiority over other libraries.
Do not select a model on this test split. Corpus changes need new digests and
must not silently replace the reference against which a model was chosen.

The rules-only baseline disables contextual rules. The contextual-rules engine
adds labels, subject associations, and schema-independent deterministic context;
calling it a statistical hybrid would be inaccurate. When a **local** Spanish
spaCy model directory is supplied, the runner also measures Spanish spaCy,
Spanish-configured Presidio, and rules plus the same local Spanish NER model:

```console
python scripts/benchmark_detection.py --spacy-model /trusted/local/es_model --output benchmarks/results/spanish-model
```

No model is downloaded at inference. Presidio receives `lang_code="es"`,
`supported_languages=["es"]`, and the same existing local Spanish NLP model.
Its built-in recognizers remain a general Spanish baseline; there is no claim
that they include Mexican RFC/CURP/CLABE recognizers. The output records their
missing coverage as measured errors rather than suppressing unsupported gold
labels. Native entity labels are explicitly mapped to the DeidFlow taxonomy.
spaCy PER/PERSON and LOC/GPE are mapped to PERSON and LOCATION. Organization
mentions are not automatically classified as confidential personal information.
Unavailable baselines are reported with a reason and **no fabricated scores**.
The runner denies socket connections and DNS during model loading and inference,
including swallowed connection attempts. Presidio's tldextract is explicitly
configured with no suffix-list URLs and the installed bundled suffix snapshot.

The private validation run used `es_core_news_sm` 3.8.0 weights obtained from
the official release. Their GPL-3.0 license applies to that model; weights are
outside the repository and are not distributed with DeidFlow. The code adapter
does not select a commercial-use license for a customer's model. Review each
model's terms separately. See the repository licensing report.

DataProfiler supports structured and character-level unstructured labelers, but
the package and a reviewed compatible local labeler were unavailable here. The
runner records that missing baseline explicitly. This delivery does not claim
measured DataProfiler accuracy or implement an untested adapter. It does not
invoke automatic labeler/model downloads. A future comparison must use equivalent
schemas, taxonomies, rows, and local model versions. See the
[official DataProfiler API/source](https://github.com/capitalone/DataProfiler).

Exact precision/recall/F1 require identical label, start, and end. Identical
same-label predictions are deduplicated; distinct overlapping predictions remain
visible. Separate overlap metrics require the same label and any intersecting
character span, with one-to-one matching. `entity_level_recall` is overlap
recall; `recall_by_type` and `recall_by_format` follow the selected matching rule.
Document leakage is the fraction of gold-positive documents with at least one
unmatched gold span. This is detection leakage under these gold definitions,
not a claim that every redaction output was tested. False-redaction rate is the
union of predicted non-gold characters divided by all non-gold characters.
ECE uses exact prediction correctness and only explicitly calibrated confidence
values. Rule ranks are never silently treated as calibrated probabilities.

Performance uses one warm-up document, then three sequential complete corpus
runs by default. p50/p95 are per-document elapsed latency quantiles across warm
runs. Records/s and decimal MB/s are measured wall-clock rates. Cold start is a
fresh Python subprocess including imports and a first rule scan. RSS is sampled
every 10ms with psutil; process-tree RSS sums live children and includes resident
models and imports. This can miss brief allocation peaks and double-count shared
pages. Sequential baselines share an interpreter, so RSS is not an isolated
per-model memory comparison. CPU utilization is process CPU seconds / wall
seconds × 100, where 100% means one occupied core. It is not whole-machine CPU
utilization or child CPU accounting. Runs shorter than 100ms have CPU utilization
`null` because OS accounting granularity can dominate such short intervals.
Machine and package versions are recorded. The first-call field can include lazy
model loading; explicit spaCy/Presidio factory loading is separately timed.
NLP token rates use the supplied model's actual tokenizer, without counting raw
characters as tokens.
Background processes are not controlled; small latency differences are not
statistically established improvements.

The full CSV command generates 100,000- and 1,000,000-row files in a separate
work directory with five columns: email, CLABE, customer ID, amount, and notes.
It streams generation and processing. Each row has three known sensitive cells.
The timed operation includes schema classification, complete transformation,
writing, and the library's independent output re-read. A second streaming check
then verifies **every** known sensitive input cell is absent, row count matches,
and every amount is preserved. That extra gold check is excluded from timing.
The input file digest, byte size, batch size, records, status, and measured memory
are recorded. Full workloads default to one repeat to keep runtime practical;
do not infer a stable speedup from a single full run. Increase `--repeats` for
machine-specific comparisons. Input-size limits are explicitly raised to permit
the generated large CSV; batch memory remains bounded.

`--batch-sizes 128 1024 8192` measures batch-size experiments. The free-text
workload consumes a generator; the PDF workload creates 100 real selectable-text
pages and measures extraction plus email detection, including ground-truth email
recall. It does not measure PDF redaction. `scripts/ocr_probe.py` creates actual
image-only PDFs and records incomplete coverage and the engine's refusal to
silently scan them when local OCR is absent. OCR error/throughput are null when
OCR is unavailable. No CUDA, ONNX, scanned-page recall, or DataProfiler superiority
is inferred from CPU rule performance.

`python scripts/benchmark_experiments.py` compares schema fast paths on identical
10,000-row CSV inputs and text workers 1/2/4, with three repeats and bounded
batches. It independently verifies every sensitive CSV cell and hashes ordered
text findings to check equivalent results across worker counts. The initial
`experiments.json` exposed severe per-item IPC overhead. After introducing
64-text IPC groups, the text-only rerun is recorded separately in
`experiments-batched-ipc.json`; the original measurements are retained. Use
`--skip-csv --batch-sizes 1024` to reproduce that focused rerun. Multiprocessing
startup, serialization, and checksum overhead are included in these timers.
Extra workers are not assumed to improve throughput.

`python scripts/benchmark_micro.py --check` is a CI safety rail using five
alternating timing repeats of the engine wrapper and the same directly called
contextual rules. It requires exact recall 1.0 on the fixture's EMAIL, RFC, CURP,
CLABE, and API_KEY cases, at most 5ms per short record, and at most 5× overhead
against the same-run direct detector. These deliberately generous budgets catch
gross regressions without treating different CI machines as identical hardware.
They are not fine-grained release performance promises; full machine-specific
benchmarks remain separate.

The checked-in machine-specific results are evidence for this implementation and
environment only. Hardware differs across deployments; a million-record batch
does not establish a universal throughput or memory guarantee. Re-run the
appropriate workload after changes to data, policy, models, dependencies, worker
count, machine, or OCR assets. A production benchmark should additionally use
licensed external corpora, independent human annotation, domain-stratified
holdouts, OCR character error, table cell coverage, and isolated model-memory
processes. Those gaps are explicit rather than filled with placeholder numbers.
