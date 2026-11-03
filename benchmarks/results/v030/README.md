# v0.3 candidate measurements

All documents visible to the coding assistant were synthetic or legitimately
acquired public sources. No private Gmail operation or private original was
accessed. Inference was local; online acquisition/install/auditing were separate.

## Primary artifacts

- `baseline-pdf.json`: unchanged v0.2.0 Git archive `0b79d3d`, including the real
  blocked100-page scanned trial. The historical117.95-second result remains in
  the v0.2 report; the reproduced native baseline here is94.016seconds.
- `pdf-scaling.json`: candidate1/2/4/8 local OCR-worker experiments and full100-page
  native/scanned workloads, with stage work time, sampled memory, actual statuses
  and independent gold output checks. Blocked output has no assumed gold pass.
- `tabular-and-text.json`: the canonical synthetic tabular/text comparison.
  Candidate CSV trials use one immutable source snapshot; baseline and text
  trials are retained from the initial completed run with their exact original
  provenance. It contains no source records or per-document private strings.
- `public-documents.json`: unlabeled operational public-PDF trials, including
  partial three-page processing and failed acquisition. These are not supervised
  precision/recall/F1 measurements. Consult `docs/public-document-sources.json`
  for source permissions and retention restrictions.
- `cpu-observation.json`: ten one-second system-wide utilization samples during
  concurrent PDF/CSV activity. Background work is included; this is not per-job
  child CPU attribution or a saturation claim for every worker configuration.

Public gold quality artifacts are one directory above, and have a separate
corpus, licensing and evaluation contract. They must not be pooled with
synthetic operational workloads or unlabeled public/private documents.

Canonical CSV observations:

| Rows | Frozen v0.2 seconds | Candidate seconds | Candidate rows/s | Candidate sampled RSS MB |
|---|---:|---:|---:|---:|
| 100,000 | 17.704 | 19.269 | 5,189.76 | 41.210 |
| 1,000,000 | 183.864 | 185.274 | 5,397.41 | 38.793 |

Both candidate trials passed the complete independent sensitive-cell and amount
checks, retained identical serialized output hashes to the corresponding
baseline, and attempted zero inference network connections. The measured elapsed
differences are +8.84% and +0.77%; differing background load and one trial per
configuration prevent a causal or statistically significant regression claim.

## Tabular source identity and interruptions

The canonical candidate CSV pair is assembled from:

1. `tabular-stable-snapshot.json`: completed100,000-row trial; its original
   process was interrupted during the following1,000,000-row trial.
2. `tabular-stable-million-resumed.json`: only the missing1,000,000-row trial,
   executed in a new process using the **identical immutable source snapshot**.

Both whole-source SHA256 values before and after must equal
`1d26f08550f2b1031467c7410bfe3639d4a9fe51a4b8d54ceab123d8bb1a7a3a`.
The canonical assembler validates those values, matching baseline input/output
hashes, all expected sensitive cells, every unchanged amount, zero inference
network attempts and ordered text-worker prediction hashes. Interrupted
temporary files outside Git are not counted as final outputs.

Legacy baseline and text trials record the owning `engine.py` hash before and
after. Their full-source hash was **not recorded** and is not retrospectively
invented. The frozen baseline is independently identified by its archived Git
commit. Candidate text results retain this narrower provenance boundary.

The installed distribution was deliberately still0.2.0 while candidate code
was evaluated before the version gate. The `implementation`, module import
assertion and code hashes distinguish candidate code from the frozen baseline.
Final package metadata changes do not retroactively alter recorded metadata.

## Preserved development evidence

- `tabular-and-text-initial.json` retains every initial trial. Its candidate
  million-row trial observed an engine source change and is excluded from the
  primary final CSV comparison.
- `tabular-optimized.json` retains runs whose whole-source hash changed during
  concurrent development. They are not labeled as stable final measurements.
- `tabular-optimized-clean100k.json` is a separate completed clean100k trial.
  It is preserved; the canonical pair uses the matched snapshot trial instead
  of selecting whichever100k measurement is fastest.

Single full-scale trials do not establish a confidence interval or isolated
causal speedup. Machine/background activity differs. End-to-end CSV timing
includes transformation, writing and mandatory library reread/rescan. The
independent complete gold check is outside the timed call. Column-batch p50/p95
measure `_rows` service time; they are not per-record latencies. Text iterator
wait p50/p95 also must not be presented as independent request service latency.

## Reproduce the method

From the source repository with the existing local environment, unchanged
baseline archive and explicitly installed optional dependencies:

```powershell
$python = '..\..\.venv\Scripts\python.exe'
& $python scripts/benchmark_enterprise_workloads.py --baseline ../../work/deidflow-v0.2.0 --snapshot-current --rows 100000 1000000 --workers 1 2 4 8 --work ../../work/v030-enterprise-new --output benchmarks/results/v030/tabular-new.json
```

This measures a new verified snapshot of the selected checkout; it does not
recreate an untouched historical holdout or promise identical timing on another
host. Generated data and source snapshots remain in the configured local work
directory. Existing inputs, private datasets and Gmail credentials are not used.
