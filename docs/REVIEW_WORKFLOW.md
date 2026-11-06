# Supervised text corrections

`deidflow.review` provides a local text-review workflow. A reviewer can add a
missed identifier, reject a false positive, or correct a span boundary while
preserving surrounding clinical, financial or other useful context. The output
is rebuilt from the original text and reviewed offsets, then scanned again.
Editing a JSON `status` field never changes the engine's release decision.

This API handles **complete Unicode text**, not PDF page extraction, OCR,
spreadsheets or streaming tables. Do not pass a truncated extraction and claim
that the original file was completely reviewed. Existing format-specific
coverage and release gates still apply to those formats.

## Create a plan and inspect the source privately

```python
from deidflow import DeidEngine, Policy
from deidflow.nlp import SpanTagger
from deidflow.review import (
    ReviewDecision,
    create_review_plan,
    apply_review,
    verify_review_receipt,
)

engine = DeidEngine(nlp=SpanTagger.builtin("es-clinical"))
policy = Policy.strict()
source = "Texto completo que se revisará localmente."

# A trusted deployment manifest should identify the rules, model assets and
# relevant configuration. Obtain its actual SHA-256 from that manifest.
model_digest = deployment_manifest_sha256
plan = create_review_plan(engine, source, policy=policy, model_digest=model_digest)

for span in plan.spans:
    # Show only in an authorized private review surface; never in public logs.
    private_review_ui(span.span_id, span.entity_type, source[span.start : span.end])
```

Offsets are Python Unicode code-point offsets, with an inclusive start and
exclusive end. They refer to the exact original string, not UTF-8 bytes or
offsets in the candidate output. Do not normalize text or line endings between
planning and applying decisions.

A plan contains source length/hash, policy hash, declared model-manifest hash,
domain hash, core rules version and bounded span metadata. It contains no copied
source values. `plan.to_json()` and `ReviewPlan.from_json(...)` round-trip this
bounded schema. New plans use schema 2 and bind the core rules version even when no spans were
found. Plans from older rule versions or schema 1 must be recreated before
applying decisions. Verification of an existing signed receipt remains a check
of that historical decision, not approval under the currently installed rules.
Duplicate JSON keys, extra fields and nonfinite numbers are rejected. Source
hashes, offsets and types can themselves be sensitive: keep plans private.

`model_digest` is **declared provenance supplied by the trusted application**.
The review module does not independently hash installed model weights or
attest model identity. Before applying decisions it reruns detection on the
exact source and requires the complete plan, including evidence fingerprints,
to match. The application remains responsible for loading the model identified
by its manifest and updating the digest when rules, assets or configuration
change. If the engine exposes `model_digest`, the supplied digest must also
match that configured value.

## Record explicit corrections

Every proposed span requires exactly one `confirm` or `reject`. Missing,
duplicate and unknown span decisions fail. Additions use source offsets and an
existing `EntityType` name. A boundary correction is a rejection plus an added
replacement span.

```python
decisions = [
    ReviewDecision.confirm(plan.spans[0].span_id),
    ReviewDecision.reject(plan.spans[1].span_id, reason="false_positive"),
    ReviewDecision.add(missed_start, missed_end, "PERSON"),
]
```

These are illustrative decisions, not instructions to confirm all detections
without inspection. Allowed rejection reasons are `false_positive`,
`public_context`, `not_personal` and `span_correction`. Additions use
`missed_identifier` or `span_correction`. Reasons are fixed codes: free-form
comments that could contain sensitive values are deliberately unsupported.

Rejecting a detection exempts only the exact type and span, projected into an
unchanged portion of the output. It does not exempt all names, the whole
document, another occurrence of the same word, a newly detected subspan, or an
overlapping span modified by another decision.

## Apply, review and approve

```python
preview = apply_review(
    engine,
    source,
    plan,
    decisions,
    policy=policy,
    model_digest=model_digest,
    reviewer_id="reviewer-" + opaque_reviewer_hex_id,
)
# preview.result.output_text is private; preview cannot be APPROVED.

reviewed = apply_review(
    engine,
    source,
    plan,
    decisions,
    policy=policy,
    model_digest=model_digest,
    reviewer_id="reviewer-" + opaque_reviewer_hex_id,
    approve=True,
    source_complete=True,
    signing_key=review_signing_key,
)
```

The reviewer identifier must be `reviewer-` followed by 16–64 lowercase hex
characters. Use an opaque internal identifier, not a person's name or email.
The application must authenticate its human reviewer separately.

`approve=True` is an explicit human approval of this exact reviewed text.
`source_complete=True` attests that the human inspected the **entire supplied
source**, including parts where the detector found nothing, for the intended
use and applicable policy. It is not inferred from an empty finding list or a
successful transformation. Without both attestations the candidate requires
review. A UI or CLI must not silently set these flags on the user's behalf.

Human confirmation resolves the reviewed source span's low-confidence or
boundary uncertainty. Residual detections outside exact false-positive
exceptions still block output. Missing required semantic-model configuration
and independent proper-noun findings still require review. `APPROVED` therefore
means the software checks and explicit human attestations were completed; it
does not prove anonymity, perfect human review, or regulatory compliance.

The returned `ReviewedText` has the ordinary `Result` and a receipt. A blocked
or review-required `Result` can still contain a candidate `output_text`; do not
release it based on its existence. Always inspect `release_approved`.

Pass a session's existing `PlaceholderAllocator` as `placeholders=...` to keep
indexed identities stable. `Result.mappings` retains source/output coordinates
for integration with the session graph. The review module does not implement
its own mapping vault, session persistence or tabular streaming system. Shared
allocators are mutable and belong to the trusted application's session.

## Receipt integrity and authorization boundaries

```python
valid = verify_review_receipt(
    reviewed.receipt,
    source=source,
    output=reviewed.result.output_text,
    policy=policy,
    model_digest=model_digest,
    signing_key=review_signing_key,
)
```

By default verification requires a signed, approved receipt with both human
attestations. It checks source/output/policy/model/domain bindings, bounded
schema, payload digest and HMAC-SHA256. Any changed decision, status or text
invalidates the signature. A signing key must contain at least 32 bytes and
must come from protected application storage. Do not put it in command-line
arguments, logs, plans or receipts. Key rotation, authorization and revocation
belong to the host application.

HMAC authenticates holders of the shared key; it is not a digital signature
identifying an individual reviewer. The recorded opaque reviewer ID is an
application assertion. Receipt verification does not rerun the detector or
prove model accuracy. It verifies that the signed record is bound to the
supplied artifact and configuration.

Without a signing key, a receipt has only an unkeyed digest. The default verifier
rejects it. `require_signed=False` permits checking accidental corruption and
artifact bindings only; anyone able to modify such a receipt can recalculate
its digest. **Never treat unsigned verification as authorization.** Setting
`require_approved=False` checks a preview or blocked receipt's integrity without
authorizing release.

There is no automatic approval import. Reusing a plan on changed source,
policy, declared model digest, domain or changed detection evidence fails as
stale. Applying even a checksum-recomputed plan that removed findings fails
because detection is rerun independently of the saved plan.

Bounds: at most 8 MiB source text (also limited by `engine.max_bytes`), 10,000
proposed spans, 20,000 decisions and 4 MiB serialized records. Errors use fixed
codes rather than echoing source values. This workflow does not write files,
send data, or publish candidates by itself.
