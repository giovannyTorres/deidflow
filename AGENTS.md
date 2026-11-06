# DeidFlow product and engineering contract

DeidFlow is Giovanny's open, free, Spanish-language de-identification library.
Keep Apache-2.0 and the existing third-party attributions. Inference is local:
no LLM, generative model, paid service, telemetry, remote inference or automatic
model download. Optional dependencies must remain optional.

The product must preserve useful context while replacing personal identifiers
with Spanish placeholders. Preserve source text outside transformed spans,
stable entity mappings and explicit relationships. Do not infer that similar
names are the same person. Persist identity state only through the authenticated
encrypted session API; public audit output must not contain source values.

Clinical, financial, legal and general packs must state exactly which model,
rules, policy and evidence they use. A domain label is not evidence of accuracy.
Post-training must separate training, validation and held-out evaluation,
reject split contamination and stage candidates before explicit promotion.

Evaluate privacy leakage, context retention, identity consistency and review
burden together. A high F1 or a passing test suite is not an anonymity guarantee.
Never tune on a test set and present it as untouched evidence. Label fictional
regressions separately from public annotated corpora and deployment evaluation.

Review changes with adversarial cases, especially hidden format channels,
placeholder spoofing, malformed state, expired sessions, stale review receipts,
cross-session identities and nonfinite or missing evaluation metrics. Preserve
incomplete coverage and uncertainty through transformations and verification.

Use narrow tests while editing, then run Ruff, formatting, mypy, the full suite,
coverage, the microbenchmark and wheel smoke tests for the integrated candidate.
Keep reproducible commands, source/model digests, results and remaining limits
in the audit handoff. Preserve concurrent changes from other contributors.
