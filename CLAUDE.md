# Claude Code audit entry point

Read [AGENTS.md](AGENTS.md) and [the audit guide](docs/AUDIT_GUIDE.md).
Audit actual behavior and reproduce claims; do not accept prose, test counts or
the `APPROVED` status as proof that sensitive data cannot remain.

Prioritize privacy leaks, lost context, incorrect entity relationships,
cross-session restoration, unauthenticated persisted state and contaminated
model evaluation. Report a minimal reproduction and expected behavior for each
finding. Keep fixes compatible with the open, free, offline, no-LLM contract.

The presence of this file does not mean a Claude Code audit has been performed
or passed. Record the reviewed commit and observed results when conducting one.
