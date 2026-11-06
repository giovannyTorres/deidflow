# OpenDocument output preparation

This branch prepares writer/MIME output after the reader increment. It is not
ready for a master-target PR until the reader has landed and its separate
review/approval gates are satisfied. No PR, issue or release was published, and no merge into master occurred.

## Source and deliberate correction

- Initial reader dependency: `7b0ff3093d31d1c5b2b759c8d95579fb935e0474`.
- Corrected reader dependency: `8f3ff4cc6471ae1ac8c803d4be49b745efdffae5`,
  with source/tests frozen at `93242156e9cb259a01b6dba66bde7c3000f9c49c`.
- Final frozen combined reference: `8cb3c5fc3a3568102620f69931c5990b2a64dba5`.
- Writer transplant: `ea72a4f`; all 54 original function/class ASTs matched the
  initial `8edf588` reference, with only `_is_sheet` located in the reader's
  shared grid section.
- Writer boundary correction: `819e6f1`. ODF package/part reads convert corrupt
  CRC, invalid DEFLATE and unsupported compression into sanitized `DocumentError`;
  the public engine returns `BLOCKED`/`MALFORMED_INPUT` without emitting a file.
  Detector/rewrite callbacks and shared OOXML behavior are outside those guards.
- Normal reader merges: `796dff0` and `e328392`. Prior source/tests:
  `b9fb054f008b86d10cdd857c2cd24764cd385284`. Review corrections deliberately
  strengthen the shared walk, cell grammar and opaque binary coverage in addition
  to the writer's ZIP-read guards; `_zip_input_errors` remains writer-only.
- Writer media-placement correction: `b7ffbe0`. Binary data under arbitrary text
  parents blocks before scrub; supported media removal keeps surrounding prose.
- Writer cell-context correction and current source/tests:
  `96f3b252814a9b2edcd39ef4f1fbab45aaada155`. Changed cells clear only shared-walk
  main text holders while retaining paragraph/span containers, deferred comments,
  text boxes and their anchors. The later shared rewrite transforms the retained
  auxiliary text. A scratch reader check before cell/field flattening rejects
  retained opaque binary metadata rather than erasing its coverage marker.
  All 42 shared reader function/class ASTs remain identical to the frozen reader.

The writer appends to the same OpenDocument backend and uses its existing text
walk, attribute inventory, grid and repeat expansion. It enables same-format
ODT/ODS output and canonical attachment MIME types. The intermediate reader-only
unsupported-output tests are superseded by the corresponding output regressions.
All original assertions, parameter cases and context managers remain represented
across the final reader/output test union. Pure-reader functions occur once.

ODT output and rewritten ODT attachments are covered. Every ODS output requires
review. A retained ODS attachment currently blocks the final EML reread because
the mail reader treats its review-only issue as incomplete coverage. Registration
of an ODS MIME type does not establish successful retained attachment output.
Uninspected retained media and unknown package parts still block. Structural
metadata, qualified XML names, collisions and nesting limits preserve the frozen
privacy corrections. The frozen benchmark/spec tickets remain untouched.

The shared walk now rejects retained children in ODF space/tab/line-break
elements. ODS grids reject direct non-whitespace text/CDATA while accepting
paragraph cells and harmless pretty-print whitespace. Nonempty declared binary
settings are incomplete anywhere in inspected XML; signature parts and opaque
certificate/DSIG or typed-binary RDF material keep uncertainty even when readable
runs are extracted. Standard settings/signature/RDF parts are removed and the
clean rewrite verifies independently. Retained off-path binary settings block
output rather than receiving an approval based on partial string extraction.

## Focused evidence

The tests were copied to `/var/tmp/odf-output-green`; commands used the shared
development venv with `PYTHONPATH=/workspace/deidflow-odf-output/src` and the
worktree's explicit `pyproject.toml` configuration.

- Original writer tracer: red with `UNSUPPORTED`, then green after transplant.
- Transplanted reader/output tests: **105 passed** in 43.46 seconds, including
  both local LibreOffice integration cases.
- New CRC/DEFLATE/unsupported-method regressions: all three first raised raw
  decoder exceptions, then returned closed results after the boundary guard.
- Updated output-privacy file: **48 passed** in 1.50 seconds.
- Prior merged reader/output selection: **179 passed** in 42.10 seconds,
  including both LibreOffice cases, terminal suffix rewrite/verification and the
  declared-zero/8 MiB expansion control. Thread counts were explicitly limited.
- Further review corrections: all **32 new writer controls passed** in 1.07
  seconds, covering malformed whitespace/cells, benign grammar controls, UTF-8/
  UTF-16LE metadata removal and retained off-path binary blocking. Reader source
  coverage has **92 passing focused cases**.
- Media-placement regressions: two unsupported-parent cases failed first; all
  **three controls passed** after the correction, including supported image
  removal with clinical context retained.
- Cell-context regressions: all **eight cases failed first**, then passed after
  the correction. They cover retained/redacted inline annotations and text boxes,
  anchors, multiple paragraphs, and config/DSIG/typed-RDF binary metadata both in
  changed cells and personal fields.
- Current copied reader/output focused selection: **188 passed, two LibreOffice
  cases deselected** in 2.79 seconds. No new full-suite, LibreOffice, benchmark or
  remote operation was run during these writer corrections.
- Global Ruff passed; all 193 Python files passed formatting; Python 3.12 mypy
  passed all 65 source files.
- Assertion audit: all 128 final-reference assertions and 12 original parameter/
  skip decorators are preserved, with 215 assertions across the split tree.
  Expected-value tuples remain code. Exception/assertion contexts are preserved;
  one fixture-only ZIP-writing context is replaced by the shared package builder.

The current conservative diff against the corrected reader dependency is **1,617
changed code/test lines**, including additions and deletions, all imports,
helpers, corruption setup and assertions. No fixture exclusion is needed here.

The coordinator supplies integrated full-suite, coverage, benchmark, package and
fresh internal review results against final split commits. External Claude
review, CI 11/11, resolved threads and Giovanny's approval remain separate gates.
Synthetic regressions and clean rereads do not establish anonymity.
