# Local customer models

The implemented learner is a CPU character-ngram TF-IDF plus logistic-regression
column classifier. It learns a column prior from a header and at most 64 values;
it is **not** a definitive PII decision or a replacement for exhaustive scanning.
It needs `pip install -e ".[training]"`. No pretrained weights, network request,
paid API, or telemetry is involved. A local Spanish discriminative spaCy model
can independently be loaded through `SpacyNER`; model training for token-level
NER, CRF, BiLSTM, and encoder adaptation remains future work.

`ColumnSample(header, values, label, split, template_id, entity_group)` accepts
arbitrary customer labels. Use separate train, validation, and test partitions.
Supply truthful source-template IDs and subject/entity-group IDs. The trainer
rejects a template/group crossing partitions. That check cannot infer hidden
near-duplicates from missing IDs: deduplicate and split the underlying documents
before constructing samples. Empty values, unknown splits, single-class training,
unseen validation labels, and absent validation partitions fail explicitly.

```python
from deidflow.training import ColumnSample, train_column_model, LocalColumnModel

# Replace these short examples with a representative privately annotated corpus.
samples = [
    ColumnSample("correo", ("demo.a@example.org",), "EMAIL", "train", "train-mail", "subject-a"),
    ColumnSample("importe", ("100", "120"), "NON_SENSITIVE", "train", "train-money", "subject-b"),
    ColumnSample(
        "email", ("demo.v@example.net",), "EMAIL", "validation", "validation-mail", "subject-v"
    ),
    ColumnSample(
        "total", ("90", "130"), "NON_SENSITIVE", "validation", "validation-money", "subject-w"
    ),
]
train_column_model(samples, "private-models/customer-A/version-1", version="version-1")
model = LocalColumnModel("private-models/customer-A/version-1")
prediction = model.predict("columna_19", ["new@example.com"])
assert prediction.calibrated is False
```

The output directory must not exist, preventing accidental model overwrite.
Each model directory contains weights, a versioned manifest, software versions,
label schema, seed, train/validation counts, metrics, a SHA-256 integrity digest,
and `activation: STAGED`. No engine automatically selects a newly trained model.
Keep base NLP weights outside customer model directories and explicitly select
which local path an application uses. Treat these directories as a minimal
versioned local registry; there is no remote model server or automatic rollout.

`LocalColumnModel` explicitly deserializes trusted local joblib assets. A digest
detects accidental modification, **not** a malicious publisher replacing both
weights and manifest. Joblib/pickle can execute code: do not load untrusted model
files. Keep manifests and weights access-controlled. Learned vocabularies may
retain fragments of customer examples; they require the same privacy treatment
as training data. DeidFlow does not implement encrypted model storage or an
enterprise key-management service.

`model.evaluate(test_samples)` reports held-out accuracy and per-label precision
and recall. `promotion_gate(candidate, baseline, critical_categories=[...])`
blocks critical recall regression, absent critical holdout categories, nonfinite
metrics, and recall below the configured minimum (default .95). It returns a
decision; it never activates a model. Baseline and candidate must be evaluated
on the same representative holdout and annotation definitions. The code cannot
prove that externally supplied metrics are honest. The synthetic demonstration
does not justify production activation.

Run the reproducible training demonstration:

```console
python scripts/train_synthetic_columns.py --output benchmarks/results/training-model-new
```

The checked-in evaluation uses 96 training, 48 validation, and 48 test columns
covering EMAIL, CLABE, CUSTOMER_ID, and NON_SENSITIVE. Its pattern baseline and
trained model are evaluated separately. It demonstrates mechanics on easy
synthetic patterns, not an improvement over deterministic classification or
evidence of customer-domain accuracy. Model probabilities are uncalibrated.

`select_active_learning(predictions, count=20)` returns indices with the largest
class-distribution entropy and deterministic ties. It selects candidates for
human annotation; entropy is not calibrated privacy risk. `weak_annotations`
exports local rule-based silver spans and marks them unreviewed; do not treat
them as independently annotated test gold.

`import_span_annotations` reads bounded UTF-8 JSONL records of exactly
`{"text": ..., "spans": [{"start": 0, "end": 3, "label": "PERSON"}]}`. It validates
Unicode character offsets and optional schemas and emits errors without source
text. Overlapping span annotations are allowed. Token BIO conversion, automatic
annotation tools, and private NER training are currently unsupported: convert
annotations with an explicitly reviewed offset mapping rather than guessing.

`fit_score_calibrator` fits a logistic score mapping on validation candidates
from **one exact detector/model provenance** with known correct/incorrect exact
span labels. It rejects incompatible provenance, insufficient observations, and
a single outcome class. `ScoreCalibrator.apply` adds a confidence value while
retaining the candidate and its protected flag. It never lowers a high-risk
deterministic match's protection. Serialize this small mapping as JSON, then
assess it on a distinct test split:

```console
python scripts/benchmark_calibration.py
```

The recorded calibration experiment fits validation templates and measures ECE
on test templates. Raw rule ranks are not probabilities, so their ECE is `null`.
The fitted mapping is experimental and susceptible to domain shift; it is not
automatically enabled in the engine.
