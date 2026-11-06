from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace

import pytest

from deidflow import DeidEngine, Finding, Policy, Rule
from deidflow.placeholders import PlaceholderAllocator
from deidflow.review import (
    ReviewDecision,
    ReviewError,
    ReviewPlan,
    apply_review,
    create_review_plan,
    verify_review_receipt,
)

MODEL = "a" * 64
REVIEWER = "reviewer-" + "b" * 16
KEY = b"synthetic-review-signing-key-32-bytes"


def apply(engine, source, plan, decisions, policy, **options):
    return apply_review(
        engine,
        source,
        plan,
        decisions,
        policy=policy,
        model_digest=MODEL,
        reviewer_id=REVIEWER,
        **options,
    )


def confirm(plan):
    return [ReviewDecision.confirm(span.span_id) for span in plan.spans]


def check(receipt, source, output, policy, **options):
    return verify_review_receipt(
        receipt, source=source, output=output, policy=policy, model_digest=MODEL, **options
    )


def test_empty_plan_binds_runtime_rules_but_historical_receipt_still_verifies(monkeypatch):
    import deidflow.review as review_module

    engine, policy, source = DeidEngine(), Policy.strict(require_ner=False), "sin datos especiales"
    current_version = review_module.CORE_RULES_VERSION
    monkeypatch.setattr(review_module, "CORE_RULES_VERSION", "rules-0.2")
    prior_plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    assert prior_plan.spans == ()
    prior_review = apply(
        engine, source, prior_plan, [], policy, approve=True, source_complete=True, signing_key=KEY
    )
    monkeypatch.setattr(review_module, "CORE_RULES_VERSION", current_version)
    with pytest.raises(ReviewError, match="STALE_REVIEW_PLAN"):
        apply(engine, source, prior_plan, [], policy)
    assert check(
        prior_review.receipt, source, prior_review.result.output_text, policy, signing_key=KEY
    )
    legacy = json.loads(prior_plan.to_json())
    legacy.pop("rules_version")
    legacy["schema"] = 1
    with pytest.raises(ReviewError):
        ReviewPlan.from_json(json.dumps(legacy))


def test_complete_human_review_is_explicit_and_receipt_is_bound():
    engine, policy = DeidEngine(), Policy.strict(require_ner=False)
    source = "Contacto: persona@example.test"
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    preview = apply(engine, source, plan, confirm(plan), policy)
    assert preview.result.status == "REVIEW_REQUIRED"
    assert set(preview.result.issues) == {"HUMAN_APPROVAL_REQUIRED", "HUMAN_SOURCE_REVIEW_REQUIRED"}
    approved = apply(
        engine,
        source,
        plan,
        confirm(plan),
        policy,
        approve=True,
        source_complete=True,
        signing_key=KEY,
    )
    assert approved.result.release_approved
    assert approved.result.output_text == "Contacto: [EMAIL]"
    assert check(approved.receipt, source, approved.result.output_text, policy, signing_key=KEY)
    assert not check(
        approved.receipt, source, approved.result.output_text + "edited", policy, signing_key=KEY
    )
    assert not check(
        approved.receipt, source + ".", approved.result.output_text, policy, signing_key=KEY
    )
    assert not check(
        approved.receipt,
        source,
        approved.result.output_text,
        replace(policy, review_below=0.9),
        signing_key=KEY,
    )
    assert not verify_review_receipt(
        approved.receipt,
        source=source,
        output=approved.result.output_text,
        policy=policy,
        model_digest="b" * 64,
        signing_key=KEY,
    )
    serialized = json.dumps(approved.receipt) + plan.to_json()
    assert "persona@example.test" not in serialized
    assert ReviewPlan.from_json(plan.to_json()) == plan


class ContextAdapter:
    def detect_batch(self, texts):
        return [
            [
                Finding(
                    "PERSON", text.index("Azul"), text.index("Azul") + 4, 0.6, "test.false_positive"
                )
            ]
            if "Azul" in text
            else []
            for text in texts
        ]


def test_add_missed_identifier_reject_false_positive_preserves_context():
    engine = DeidEngine(nlp=ContextAdapter())
    policy = Policy.strict()
    source = "Azul mejoró el síntoma; Zelmira Salcedo respondió."
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    assert not any(source[s.start : s.end] == "Zelmira Salcedo" for s in plan.spans)
    decisions = [
        ReviewDecision.reject(s.span_id, reason="public_context")
        if source[s.start : s.end] == "Azul"
        else ReviewDecision.confirm(s.span_id)
        for s in plan.spans
    ]
    start = source.index("Zelmira Salcedo")
    decisions.append(ReviewDecision.add(start, start + len("Zelmira Salcedo"), "PERSON"))
    reviewed = apply(engine, source, plan, decisions, policy, approve=True, source_complete=True)
    assert reviewed.result.release_approved
    assert reviewed.result.output_text == "Azul mejoró el síntoma; [PERSON] respondió."
    assert source == "Azul mejoró el síntoma; Zelmira Salcedo respondió."


def test_false_positive_exemption_follows_offsets_only_after_prior_replacement():
    engine, policy = DeidEngine(nlp=ContextAdapter()), Policy.strict()
    source = "persona@example.test y Azul"
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    decisions = [
        ReviewDecision.reject(s.span_id)
        if source[s.start : s.end] == "Azul"
        else ReviewDecision.confirm(s.span_id)
        for s in plan.spans
    ]
    reviewed = apply(engine, source, plan, decisions, policy, approve=True, source_complete=True)
    assert reviewed.result.release_approved and reviewed.result.output_text == "[EMAIL] y Azul"


def test_rejection_does_not_exempt_new_residual_subspan():
    class ChangedResidual(ContextAdapter):
        def detect_batch(self, texts):
            result = super().detect_batch(texts)
            for text, findings in zip(texts, result, strict=True):
                if "[EMAIL]" in text and "Azul" in text:
                    findings.append(
                        Finding(
                            "EMAIL",
                            text.index("Azul"),
                            text.index("Azul") + 3,
                            0.99,
                            "test.output_only",
                        )
                    )
            return result

    engine, policy = DeidEngine(nlp=ChangedResidual()), Policy.strict()
    source = "persona@example.test y Azul"
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    decisions = [
        ReviewDecision.reject(s.span_id)
        if source[s.start : s.end] == "Azul"
        else ReviewDecision.confirm(s.span_id)
        for s in plan.spans
    ]
    result = apply(
        engine, source, plan, decisions, policy, approve=True, source_complete=True
    ).result
    assert result.status == "BLOCKED" and "RESIDUAL_FINDINGS" in result.issues


def test_partial_span_correction_rebuilds_from_original():
    class Partial:
        def detect_batch(self, texts):
            return [
                [Finding("PERSON", 0, 3, 0.5, "test.partial", context=("window_boundary",))]
                if text.startswith("Ana ")
                else []
                for text in texts
            ]

    source = "Ana López conserva el contexto."
    engine, policy = DeidEngine(nlp=Partial()), Policy.strict()
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    decisions = [
        ReviewDecision.reject(plan.spans[0].span_id, reason="span_correction"),
        ReviewDecision.add(0, len("Ana López"), "PERSON", reason="span_correction"),
    ]
    result = apply(
        engine, source, plan, decisions, policy, approve=True, source_complete=True
    ).result
    assert result.output_text == "[PERSON] conserva el contexto." and result.release_approved


@pytest.mark.parametrize("changed", ["source", "policy", "model", "detection"])
def test_stale_plan_rejected(changed):
    engine, policy = DeidEngine(), Policy.strict(require_ner=False)
    source = "persona@example.test"
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    options = dict(policy=policy, model_digest=MODEL, reviewer_id=REVIEWER)
    if changed == "source":
        source += "."
    elif changed == "policy":
        options["policy"] = replace(policy, review_below=0.99)
    elif changed == "model":
        options["model_digest"] = "b" * 64
    else:

        class Other:
            def detect_batch(self, texts):
                return [[Finding("PERSON", 0, 3, 0.5, "test.new")] for _ in texts]

        engine.nlp = Other()
    with pytest.raises(ReviewError, match="STALE_REVIEW_PLAN"):
        apply_review(engine, source, plan, confirm(plan), **options)


def test_recomputed_unsigned_plan_cannot_remove_unreviewed_findings():
    source = "persona@example.test"
    engine, policy = DeidEngine(), Policy.strict(require_ner=False)
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    data = json.loads(plan.to_json())
    data["spans"] = []
    unsigned = {k: v for k, v in data.items() if k != "plan_digest"}
    data["plan_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    altered = ReviewPlan.from_json(json.dumps(data))
    with pytest.raises(ReviewError, match="STALE_REVIEW_PLAN"):
        apply(engine, source, altered, [], policy, approve=True, source_complete=True)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "extra", "out_of_range"])
def test_invalid_decisions_never_approve(kind):
    source = "persona@example.test"
    engine, policy = DeidEngine(), Policy.strict(require_ner=False)
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    decisions = confirm(plan)
    if kind == "missing":
        decisions = []
    elif kind == "duplicate":
        decisions += confirm(plan)
    elif kind == "extra":
        decisions.append(ReviewDecision.confirm("f" * 64))
    else:
        decisions.append(ReviewDecision.add(0, len(source) + 1, "PERSON"))
    with pytest.raises(ReviewError):
        apply(engine, source, plan, decisions, policy, approve=True, source_complete=True)


@pytest.mark.parametrize("approve,complete", [(False, False), (True, False), (False, True)])
def test_human_attestations_cannot_be_omitted(approve, complete):
    engine, policy, source = DeidEngine(), Policy.strict(require_ner=False), "texto inocuo"
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    result = apply(
        engine, source, plan, confirm(plan), policy, approve=approve, source_complete=complete
    ).result
    assert not result.release_approved


def test_human_review_does_not_bypass_missing_model_or_independent_checks():
    engine, source = DeidEngine(), "visitar a Zelmira"
    policy = Policy(independent_check="proper_nouns")
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    result = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    ).result
    assert not result.release_approved
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues
    assert "POSSIBLE_RESIDUAL_PROPER_NOUN" in result.issues


def test_signed_receipt_tampering_wrong_key_and_unsigned_limits():
    engine, policy, source = DeidEngine(), Policy.strict(require_ner=False), "texto inocuo"
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    preview = apply(engine, source, plan, [], policy, signing_key=KEY)
    edited = copy.deepcopy(preview.receipt)
    edited["payload"].update(status="APPROVED", approve=True, source_complete=True, issues=[])
    edited["digest"] = hashlib.sha256(
        json.dumps(
            edited["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    assert not check(edited, source, source, policy, signing_key=KEY)
    approved = apply(
        engine, source, plan, [], policy, approve=True, source_complete=True, signing_key=KEY
    )
    assert not check(approved.receipt, source, source, policy, signing_key=b"z" * 32)
    unsigned = apply(engine, source, plan, [], policy, approve=True, source_complete=True)
    assert not check(unsigned.receipt, source, source, policy)
    assert check(unsigned.receipt, source, source, policy, require_signed=False)


def test_bounded_schema_rejects_plaintext_reasons_nan_duplicate_json_and_extra_status():
    with pytest.raises(ReviewError):
        ReviewDecision.reject("a" * 64, reason="This reveals persona@example.test")
    with pytest.raises(ReviewError):
        ReviewDecision.add(True, 4, "PERSON")
    engine, policy, source = DeidEngine(), Policy.strict(require_ner=False), "persona@example.test"
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    for bad in (
        plan.to_json().replace('"score":0.95', '"score":NaN'),
        plan.to_json()[:-1] + ',"schema":1}',
        plan.to_json()[:-1] + ',"status":"APPROVED"}',
    ):
        with pytest.raises(ReviewError):
            ReviewPlan.from_json(bad)


def test_shared_allocator_keeps_reviewed_mapping_across_documents():
    policy = Policy(default=Rule("indexed"), require_ner=False)
    engine, allocator = DeidEngine(), PlaceholderAllocator()
    outputs = []
    for source in ("uno@example.test", "dos@example.test", "uno@example.test"):
        plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
        outputs.append(
            apply(
                engine,
                source,
                plan,
                confirm(plan),
                policy,
                approve=True,
                source_complete=True,
                placeholders=allocator,
            ).result.output_text
        )
    assert outputs == ["[CORREO_1]", "[CORREO_2]", "[CORREO_1]"]


def test_generalization_cannot_hide_retained_sensitive_source_from_review_rescan():
    source = "ana@example.test"
    engine = DeidEngine()
    policy = Policy(
        default=Rule("generalize", replacement="Contacto: " + source), require_ner=False
    )
    plan = create_review_plan(engine, source, policy=policy, model_digest=MODEL)
    result = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    ).result
    assert result.status == "BLOCKED" and "RESIDUAL_FINDINGS" in result.issues


def test_confirmation_resolves_boundary_flags_and_preserves_domain_role():
    class RoleAdapter:
        def detect_batch(self, texts):
            return [
                [
                    Finding(
                        "PERSON",
                        0,
                        4,
                        0.5,
                        "test.customer",
                        context=(
                            "role:customer",
                            "gender:f",
                            "window_boundary",
                            "domain_boundary_refinement",
                        ),
                    )
                ]
                if text == "Lina"
                else []
                for text in texts
            ]

    engine = DeidEngine(nlp=RoleAdapter())
    policy = Policy(default=Rule("indexed"))
    allocator = PlaceholderAllocator(role_labels={"customer": "CLIENTE"})
    plan = create_review_plan(engine, "Lina", policy=policy, model_digest=MODEL)
    result = apply(
        engine,
        "Lina",
        plan,
        confirm(plan),
        policy,
        approve=True,
        source_complete=True,
        placeholders=allocator,
    ).result
    assert result.output_text == "[CLIENTE_1]" and result.release_approved


def test_review_manifest_must_match_engine_when_engine_exposes_digest():
    engine = DeidEngine()
    engine.model_digest = "b" * 64
    with pytest.raises(ReviewError, match="REVIEW_MODEL_DIGEST_MISMATCH"):
        create_review_plan(
            engine, "texto", policy=Policy.strict(require_ner=False), model_digest=MODEL
        )
