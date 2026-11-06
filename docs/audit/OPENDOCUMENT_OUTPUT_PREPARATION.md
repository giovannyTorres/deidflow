# OpenDocument output preparation

This branch prepares writer/MIME output after the reader increment. It is not
ready for a master-target PR until the reader has landed and its separate
review/approval gates are satisfied. No remote publication or merge occurred.

## Source and deliberate correction

- Initial reader dependency: `7b0ff3093d31d1c5b2b759c8d95579fb935e0474`.
- Frozen combined transplant reference: `8edf588b21dc684e68cc62c9d6c41b3963de8255`.
- Writer transplant: `ea72a4f`; all 54 original function/class ASTs matched the
  reference, with only `_is_sheet` located in the reader's shared grid section.
- Writer boundary correction: `819e6f1`. ODF package/part reads convert corrupt
  CRC, invalid DEFLATE and unsupported compression into sanitized `DocumentError`;
  the public engine returns `BLOCKED`/`MALFORMED_INPUT` without emitting a file.
  Detector/rewrite callbacks and shared OOXML behavior are outside those guards.
- The corrected reader branch must be integrated by a normal merge before final
  verification; its compressed-extent source-verification correction is pending
  in this preparation snapshot.

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

## Focused evidence before the pending reader merge

The tests were copied to `/var/tmp/odf-output-green`; commands used the shared
development venv with `PYTHONPATH=/workspace/deidflow-odf-output/src` and the
worktree's explicit `pyproject.toml` configuration.

- Original writer tracer: red with `UNSUPPORTED`, then green after transplant.
- Transplanted reader/output tests: **105 passed** in 43.46 seconds, including
  both local LibreOffice integration cases.
- New CRC/DEFLATE/unsupported-method regressions: all three first raised raw
  decoder exceptions, then returned closed results after the boundary guard.
- Updated output-privacy file: **48 passed** in 1.50 seconds.
- Changed-file Ruff/format passed; Python 3.12 mypy passed all 65 source files.
- Assertion audit: all 123 reference assertions, original parameter decorators
  and context expressions are preserved. Expected-value tuples remain code.

The current conservative diff against the initial reader dependency is **1,366
changed code/test lines**, including additions and deletions, all imports,
helpers, corruption setup and assertions. No fixture exclusion is needed here.

The coordinator supplies integrated full-suite, coverage, benchmark, package and
fresh internal review results against final split commits. External Claude
review, CI 11/11, resolved threads and Giovanny's approval remain separate gates.
Synthetic regressions and clean rereads do not establish anonymity.
