# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.4.x | Yes: security fixes |
| < 0.4 | No |

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the repository's
**Security** tab and choose **Report a vulnerability**. Do not open a public
issue for a suspected vulnerability, and never attach real personal data,
credentials or private documents to a report. Synthetic reproductions are
enough. You should receive an acknowledgement within seven days.

## What counts as a vulnerability

- Sensitive text surviving an `APPROVED` result, for example a transformation
  or verification bypass, or a release gate that approves incomplete coverage.
- Source text, findings or keys leaking into logs, exception messages, audit
  records, CLI output or model files.
- Code execution, path traversal, resource exhaustion or sandbox escape from
  untrusted document bytes, archives, PDFs, images or model files loaded with
  `SpanTagger.load`.
- Weaknesses in HMAC pseudonym scoping or in pinned-integrity checks.

Detection misses on ordinary text are quality issues, not vulnerabilities:
please open a normal issue with a synthetic example. No detector guarantees
anonymity; `REVIEW_REQUIRED` and `BLOCKED` results are the intended outcome
whenever coverage is uncertain.

## Trust boundaries

Policies, keys, custom recognizers, custom transformations, spaCy models and
OCR executables are trusted code or configuration. Tagger model files are JSON
(never pickle) and are validated on load, but a model trained on private data
should itself be treated as sensitive. The threat model is described in
[docs/security.md](docs/security.md).
