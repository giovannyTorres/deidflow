# Contributing

DeidFlow is licensed under the Apache License 2.0. Unless you state otherwise,
contributions you submit are licensed under the same terms (Apache-2.0,
section 5).

## Development setup

```sh
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,pdf,ocr,tables,yaml,training,benchmarks,nlp]"
```

## Checks (the same ones CI runs)

```sh
ruff check .
ruff format --check .
mypy --python-version 3.13 src/deidflow     # use your interpreter's version
pytest -q
python scripts/benchmark_micro.py --check
python -m build && twine check --strict dist/*
```

## Rules for privacy-relevant changes

- Never commit real personal data, private documents, credentials, raw public
  corpora or model files trained on private data. Use synthetic fixtures.
- Detector or model changes must report public held-out metrics measured with
  `scripts/benchmark_public_quality.py`. Tune only on development splits; a
  test split that has been used for tuning is no longer a holdout.
- Keep failures closed: an unsupported input or uncertain detection must
  produce `REVIEW_REQUIRED`, `BLOCKED` or `UNSUPPORTED`, never a silent pass.
- Exceptions and logs must not include document text. Raise with `from None`
  when a third-party exception might carry input.
- The base package has no runtime dependencies; optional features import their
  dependencies lazily.

## Releasing

1. Update `version` in `pyproject.toml` and `src/deidflow/__init__.py`, and add
   a `CHANGELOG.md` entry.
2. Merge to the default branch with green checks.
3. Tag `vX.Y.Z` and push the tag. The release workflow builds the sdist and
   wheel, writes an SBOM and checksums, records build provenance attestations
   and attaches everything to a GitHub release. PyPI publishing runs only when
   the repository variable `PUBLISH_TO_PYPI` is `true` and a trusted publisher
   is configured.
