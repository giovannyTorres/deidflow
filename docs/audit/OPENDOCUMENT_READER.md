# OpenDocument reader and verification handoff

This increment adds local ODT/ODS reading and standalone verification. It does
not enable automatic OpenDocument output. The independently reviewed writer is
being prepared as a dependent change; its existence does not authorize a merge.

## Source and scope

- Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
- Frozen combined reference: `8cb3c5fc3a3568102620f69931c5990b2a64dba5`.
- Initial reader source/tests: `b690f19d33b1a3e7c0af26ec84a8f20242481f80`.
- Compressed-stream reader source/tests: `9a27b832b6e15b461650dbabd6b49f3db5098cba`.
- Current reader source/tests: `93242156e9cb259a01b6dba66bde7c3000f9c49c`.
- The initial 42 retained reader/shared function ASTs matched the frozen reference.
  `_is_sheet` moved into the shared grid section. The text walk, grid and repeat
  expansion helper each have one shared implementation. Subsequent review fixes
  deliberately strengthen the walk, cell-text grammar and binary coverage flags.
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
Compressed streams are checked before ordinary ZIP decoding, with bounded
expansion, exact length, CRC and end-of-stream validation. Trailing compressed
payload bytes preserve incomplete coverage; invalid streams do not reach XML
decoding. A declared-zero member expanding to 8 MiB stays below the regression's
2 MiB allocation bound.

Review corrections `e96677f`, `807ff3a` and `b40727f` close two reported privacy
gaps and an equivalent skipped-text case. ODF spaces/tabs/line breaks reject
retained child content; ODS cells reject direct non-whitespace character/CDATA
content while preserving valid paragraphs and pretty-print whitespace. Nonempty
declared binary settings are incomplete anywhere in inspected XML; signature
parts and opaque certificate/DSIG or typed-binary RDF material remain incomplete.
Printable-string extraction still supplies useful findings but never proves
coverage of arbitrary binary data. No new encoding decoder or dependency was
introduced. Existing `office:binary-data`/media incompleteness remains intact.

## Focused evidence

Tests were copied to `/var/tmp/odf-reader-green`; `PYTHONPATH` explicitly selected
`/workspace/deidflow-odf-reader/src` while using the shared development venv.

```sh
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m pytest -q -c /workspace/deidflow-odf-reader/pyproject.toml /var/tmp/odf-reader-green/test_opendocument_reader.py /var/tmp/odf-reader-green/test_opendocument_reader_privacy.py
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m ruff check src/deidflow/opendocument.py src/deidflow/readers/__init__.py tests/*opendocument*.py
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m ruff format --check src/deidflow/opendocument.py src/deidflow/readers/__init__.py tests/*opendocument*.py
PYTHONPATH=/workspace/deidflow-odf-reader/src /workspace/deidflow/.venv/bin/python -m mypy --python-version 3.12 src/deidflow
```

Observed: **92 passed** in 1.20 seconds; global Ruff/format passed (190 Python
files); mypy passed all 65 source files. A copied public reader test first failed on the base
with `UnsupportedFormat`, then passed after extraction. The two direct-output
and two MIME-boundary cases passed before and after reader registration.
The initial Python 3.11 mypy target could not parse the installed NumPy stubs;
the passing target matches the shared venv's Python 3.12 interpreter.

The source/test diff adds 1,789 physical lines. Excluding only 116 lines of
synthetic input sample data gives **1,673 conservative code/test lines**. The
additional review corrections and public regressions are retained above the
approximate 1,500-line guide. Imports, builders, namespace/base64 generation,
validation assertions and expected values are included. Repeated manifest/ZIP
fixture plumbing is shared without removing any case or assertion.

The coordinator runs the integrated full suite, coverage, microbenchmark,
package checks and fresh internal reviews against the split commits. Those
results, external Claude review, CI 11/11, resolved review threads and Giovanny's
approval remain separate gates. This handoff is neither external review nor
an anonymity guarantee. No remote publication or merge occurred.
