# OpenDocument reader and verification handoff

This increment adds local ODT/ODS reading and standalone verification. It does
not enable automatic OpenDocument output. The independently reviewed writer is
being prepared as a dependent change; its existence does not authorize a merge.

## Source and scope

- Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
- Frozen combined reference: `8edf588b21dc684e68cc62c9d6c41b3963de8255`.
- Reader source/tests: `b690f19d33b1a3e7c0af26ec84a8f20242481f80`.
- All 41 retained reader/shared function ASTs match the frozen reference.
  `_is_sheet` moved into the shared grid section. The text walk, grid and repeat
  expansion helper are unchanged; there is one implementation of each.
- `engine.py`, `mail.py`, `office.py` and the frozen benchmark/spec tickets are
  unchanged in this increment. Only the public document-reader route is added.

`read_document()` and `DeidEngine.verify()` accept ODT/ODS. Direct deidentify
still returns `UNSUPPORTED`, without an output path or file. E-mail rewriting
still removes unsupported ODT/ODS attachments; registration of a reader does
not permit copying an unprocessed attachment into emitted MIME output.

The reader inspects retained text/attributes, qualified names, package names,
supported metadata and sheet values. Unmodeled media, unknown parts, unresolved
references, XML comments/PIs, opaque ZIP metadata and nonempty configuration,
layout-cache or directory payloads retain incomplete coverage. Ordinary CDATA
marker text is visible and does not trigger the hidden-channel check. XML
nesting is bounded at 128 elements. ODS always carries `ODS_REVIEW_REQUIRED`,
even when its inspected graph is complete and its text contains no findings.

## Focused evidence

Tests were copied to `/var/tmp/odf-reader-green`; `PYTHONPATH` explicitly selected
`/workspace/deidflow-odf-reader/src` while using the shared development venv.

```sh
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m pytest -q -c /workspace/deidflow-odf-reader/pyproject.toml /var/tmp/odf-reader-green/test_opendocument_reader.py /var/tmp/odf-reader-green/test_opendocument_reader_privacy.py
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m ruff check src/deidflow/opendocument.py src/deidflow/readers/__init__.py tests/*opendocument*.py
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m ruff format --check src/deidflow/opendocument.py src/deidflow/readers/__init__.py tests/*opendocument*.py
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m mypy --python-version 3.12 src/deidflow
```

Observed: **55 passed** in 0.96 seconds; changed-file Ruff/format passed; mypy
passed all 65 source files. A copied public reader test first failed on the base
with `UnsupportedFormat`, then passed after extraction. The two direct-output
and two MIME-boundary cases passed before and after reader registration.
The initial Python 3.11 mypy target could not parse the installed NumPy stubs;
the passing target matches the shared venv's Python 3.12 interpreter.

The source/test diff adds 1,517 physical lines. Excluding only 89 lines of
top-level synthetic sample data gives **1,428 conservative code/test lines**.
Imports, builders, validation assertions and expected values are included.

The coordinator runs the integrated full suite, coverage, microbenchmark,
package checks and fresh internal reviews against the split commits. Those
results, external Claude review, CI 11/11, resolved review threads and Giovanny's
approval remain separate gates. This handoff is neither external review nor
an anonymity guarantee. No remote publication or merge occurred.
