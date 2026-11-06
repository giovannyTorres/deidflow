from __future__ import annotations

import copy
import csv
import io
import json
from dataclasses import replace

import pytest

from deidflow import DeidEngine, Finding, Policy, Rule
from deidflow.csv_review import (
    CSVReviewDecision,
    CSVReviewError,
    CSVReviewPlan,
    apply_csv_review,
    create_csv_review_plan,
    verify_csv_review_receipt,
)
from deidflow.review import ReviewDecision

MODEL = "a" * 64
KEY = b"synthetic-csv-review-key-32-bytes-long"
REVIEWER = "reviewer-" + "b" * 16


def confirm(plan):
    return [
        CSVReviewDecision(cell.row, cell.column, ReviewDecision.confirm(span.span_id))
        for cell in plan.cells
        for span in cell.review.spans
    ]


def apply(engine, source, plan, decisions, policy, **options):
    return apply_csv_review(
        engine,
        source,
        plan,
        decisions,
        policy=policy,
        model_digest=MODEL,
        reviewer_id=REVIEWER,
        signing_key=KEY,
        **options,
    )


def verify(reviewed, source, policy, **options):
    return verify_csv_review_receipt(
        reviewed.receipt,
        source=source,
        output=reviewed.output_bytes,
        policy=policy,
        model_digest=MODEL,
        signing_key=KEY,
        **options,
    )


def rows(output):
    return list(csv.reader(io.StringIO(output.decode("utf-8"), newline=""), strict=True))


class FalsePositive:
    def detect_batch(self, texts):
        return [
            [Finding("PERSON", text.index("Azul"), text.index("Azul") + 4, 0.6, "test")]
            if "Azul" in text
            else []
            for text in texts
        ]


def test_review_corrects_omission_and_false_positive_preserves_amounts_and_identity():
    source = b"nombre,nota,importe\r\nZelmira Salcedo,Azul,1234.50\r\nZelmira Salcedo,,42\r\n"
    engine = DeidEngine(nlp=FalsePositive())
    policy = Policy(default=Rule("indexed"))
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    assert len(plan.cells) == 9 and plan.row_count == 2 and plan.column_count == 3
    decisions = [
        CSVReviewDecision(cell.row, cell.column, ReviewDecision.reject(span.span_id))
        for cell in plan.cells
        for span in cell.review.spans
    ]
    decisions += [
        CSVReviewDecision(row, 0, ReviewDecision.add(0, len("Zelmira Salcedo"), "PERSON"))
        for row in (1, 2)
    ]
    reviewed = apply(engine, source, plan, decisions, policy, approve=True, source_complete=True)
    assert reviewed.result.release_approved, reviewed.result.issues
    assert rows(reviewed.output_bytes) == [
        ["nombre", "nota", "importe"],
        ["[PERSONA_1]", "Azul", "1234.50"],
        ["[PERSONA_1]", "", "42"],
    ]
    assert verify(reviewed, source, policy)
    assert CSVReviewPlan.from_json(plan.to_json()) == plan
    serialized = plan.to_json() + json.dumps(reviewed.receipt)
    assert "Zelmira" not in serialized and "Azul" not in serialized


def test_unicode_quotes_multiline_bom_headers_and_exact_source_bytes():
    source = '\ufeffcorreo@example.test,nota\r\nuno@example.test,"café, dijo ""hola""\r\ncontinuó"\r\n'.encode()
    engine, policy = DeidEngine(), Policy(default=Rule("indexed"), require_ner=False)
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    reviewed = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    )
    assert rows(reviewed.output_bytes) == [
        ["[CORREO_1]", "nota"],
        ["[CORREO_2]", 'café, dijo "hola"\r\ncontinuó'],
    ]
    assert not reviewed.output_bytes.startswith(b"\xef\xbb\xbf")
    assert reviewed.output_bytes.endswith(b"\r\n")
    assert verify(reviewed, source, policy)
    assert not verify(reviewed, source[3:], policy)
    assert not verify(reviewed, source.replace(b"\r\n", b"\n"), policy)


def test_all_source_tokens_including_header_and_late_cell_are_reserved_first():
    source = b"[persona 1],nota\nZelmira,PERSONA_2\n"
    engine, policy = DeidEngine(), Policy(default=Rule("indexed"), require_ner=False)
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    decisions = confirm(plan)
    # Force a PERSON allocation before a later literal token can be processed.
    decisions.append(CSVReviewDecision(1, 0, ReviewDecision.add(0, 7, "PERSON")))
    reviewed = apply(engine, source, plan, decisions, policy)
    assert "[PERSONA_3]" in reviewed.output_bytes.decode()
    assert verify(reviewed, source, policy, require_approved=False)


def test_document_pseudonym_is_shared_across_distinct_cell_plans():
    source = b"correo,nota\r\nuno@example.test,Contacto: uno@example.test\r\n"
    engine = DeidEngine(key=b"synthetic-document-scope-key-32-bytes")
    policy = Policy(default=Rule("pseudonym"), require_ner=False)
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    reviewed = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    )
    token, contact = rows(reviewed.output_bytes)[1]
    assert contact == "Contacto: " + token
    assert "uno@example.test" not in reviewed.output_bytes.decode()
    assert reviewed.result.release_approved
    assert verify(reviewed, source, policy)


@pytest.mark.parametrize("token_scope", ["document", "dataset", "tenant", "session"])
def test_csv_pseudonyms_keep_the_configured_document_or_wider_boundary(token_scope):
    engine = DeidEngine(
        key=b"synthetic-scope-boundaries-key-32-bytes",
        tenant_id="fictional-tenant",
        dataset_id="fictional-dataset",
    )
    policy = Policy(default=Rule("pseudonym"), require_ner=False, token_scope=token_scope)
    outputs = []
    for source in (
        b"correo,nota\nuno@example.test,primera\n",
        b"correo,nota\nuno@example.test,segunda\n",
        b"correo,nota\nuno@example.test,primera\n",
    ):
        plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
        reviewed = apply(
            engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
        )
        assert reviewed.result.release_approved
        assert verify(reviewed, source, policy)
        outputs.append(rows(reviewed.output_bytes)[1][0])
    assert outputs[0] == outputs[2]
    assert (outputs[0] == outputs[1]) is (token_scope != "document")


def test_exact_identity_reuses_compatible_context_without_merging_conflicting_roles():
    class Roles:
        def detect_batch(self, texts):
            result = []
            for text in texts:
                context = (
                    ("role:customer",)
                    if text.startswith("clienta ")
                    else ("role:clinician",)
                    if text.startswith("medica ")
                    else ()
                )
                result.append(
                    [
                        Finding(
                            "PERSON",
                            text.index("Lina"),
                            text.index("Lina") + 4,
                            0.99,
                            "test.roles",
                            context=context,
                        )
                    ]
                    if "Lina" in text
                    else []
                )
            return result

    source = b"primera,segunda,tercera\nclienta Lina,Lina,medica Lina\n"
    engine, policy = DeidEngine(nlp=Roles()), Policy(default=Rule("indexed"))
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    reviewed = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    )
    assert rows(reviewed.output_bytes)[1] == [
        "clienta [CLIENTE_1]",
        "[CLIENTE_1]",
        "medica [MEDICO_1]",
    ]
    assert verify(reviewed, source, policy)


@pytest.mark.parametrize("approve,complete", [(False, False), (True, False), (False, True)])
def test_preview_is_signed_and_cannot_be_approved_without_both_attestations(approve, complete):
    source = b'nota\n""\n'
    engine, policy = DeidEngine(), Policy.strict(require_ner=False)
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    assert len(plan.cells) == 2
    reviewed = apply(engine, source, plan, [], policy, approve=approve, source_complete=complete)
    assert reviewed.result.status == "REVIEW_REQUIRED"
    assert verify(reviewed, source, policy, require_approved=False)
    assert not verify(reviewed, source, policy)


def test_cell_block_and_independent_gate_survive_aggregate_review():
    engine = DeidEngine(custom_transforms={"bad": lambda text: "Contacto: " + text})
    policy = Policy(default=Rule("custom", custom="bad"), require_ner=False)
    source = b"contacto\nuno@example.test\n"
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    reviewed = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    )
    assert reviewed.result.status == "BLOCKED"
    assert "RESIDUAL_FINDINGS" in reviewed.result.issues
    assert verify(reviewed, source, policy, require_approved=False)
    assert not verify(reviewed, source, policy)
    policy = Policy(independent_check="proper_nouns")
    source = b"nota\nvisitar a Zelmira\n"
    plan = create_csv_review_plan(DeidEngine(), source, policy=policy, model_digest=MODEL)
    reviewed = apply(
        DeidEngine(), source, plan, confirm(plan), policy, approve=True, source_complete=True
    )
    assert not reviewed.result.release_approved
    assert "SEMANTIC_MODEL_REQUIRED" in reviewed.result.issues
    assert "POSSIBLE_RESIDUAL_PROPER_NOUN" in reviewed.result.issues


@pytest.mark.parametrize("header", [b"a@example.test,b@example.test", b"a@example.test"])
def test_transformed_duplicate_or_empty_headers_are_blocked(header):
    policy = Policy(
        default=Rule("placeholder" if b"," in header else "suppress"), require_ner=False
    )
    source = header + b"\n" + (b"uno,dos\n" if b"," in header else b"uno\n")
    engine = DeidEngine()
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    reviewed = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    )
    assert reviewed.result.status == "BLOCKED"
    assert "CSV_HEADER_INVALID" in reviewed.result.issues
    assert verify(reviewed, source, policy, require_approved=False)


@pytest.mark.parametrize("changed", ["source", "policy", "model", "domain", "detection"])
def test_stale_plans_bind_complete_csv_configuration(changed):
    source = b"correo,nota\nuno@example.test,Azul\n"
    engine, policy = DeidEngine(), Policy.strict(require_ner=False)
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    options = dict(policy=policy, model_digest=MODEL, domain=None)
    if changed == "source":
        source = source.replace(b"\n", b"\r\n")
    elif changed == "policy":
        options["policy"] = replace(policy, review_below=0.99)
    elif changed == "model":
        options["model_digest"] = "b" * 64
    elif changed == "domain":
        options["domain"] = "financial"
    else:
        engine.nlp = FalsePositive()
    with pytest.raises(CSVReviewError, match="STALE_CSV_REVIEW_PLAN"):
        apply_csv_review(
            engine, source, plan, confirm(plan), reviewer_id=REVIEWER, signing_key=KEY, **options
        )


def test_receipt_authenticates_decisions_cell_coordinates_shape_and_exact_output_bytes():
    source = b"correo\nuno@example.test\nuno@example.test\n"
    engine, policy = DeidEngine(), Policy(default=Rule("indexed"), require_ner=False)
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    reviewed = apply(
        engine, source, plan, confirm(plan), policy, approve=True, source_complete=True
    )
    for field in ("row_count", "decisions", "approve", "status", "plan"):
        edited = copy.deepcopy(reviewed.receipt)
        edited["payload"][field] = None
        assert not verify(replace(reviewed, receipt=edited), source, policy)
    assert not verify(
        replace(reviewed, output_bytes=reviewed.output_bytes.replace(b"\r\n", b"\n")),
        source,
        policy,
    )
    assert not verify(
        replace(reviewed, output_bytes=reviewed.output_bytes + b"extra\r\n"), source, policy
    )
    assert not verify_csv_review_receipt(
        reviewed.receipt,
        source=source,
        output=reviewed.output_bytes,
        policy=policy,
        model_digest=MODEL,
        signing_key=b"x" * 32,
    )
    assert not verify_csv_review_receipt(
        reviewed.receipt,
        source=source,
        output=reviewed.output_bytes,
        policy=policy,
        model_digest="b" * 64,
        signing_key=KEY,
    )


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"a,a\n1,2\n",
        b",a\n1,2\n",
        b"a,b\n1\n",
        b"a\n\x00\n",
        b'a\n"unfinished',
        b'a\nunquoted"quote\n',
        b'a\n"closed"extra\n',
        b"a\n\xff\n",
        b"a\n" * 1002,
        b",".join([b"x"] * 65),
        b"a" * (8 * 1024 * 1024 + 1),
    ],
)
def test_invalid_or_excessive_csv_fails_without_echoing_source(bad):
    with pytest.raises(CSVReviewError) as error:
        create_csv_review_plan(
            DeidEngine(), bad, policy=Policy.strict(require_ner=False), model_digest=MODEL
        )
    assert str(error.value).startswith("CSV_")
    assert "unfinished" not in str(error.value) and "unquoted" not in str(error.value)


def test_json_and_decision_limits_fail_closed():
    source = b"correo\nuno@example.test\n"
    engine, policy = DeidEngine(), Policy.strict(require_ner=False)
    plan = create_csv_review_plan(engine, source, policy=policy, model_digest=MODEL)
    serialized = plan.to_json()
    for bad in (
        serialized[:-1] + ',"schema":1}',
        serialized[:-1] + ',"extra":"private-canary"}',
        serialized.replace('"row_count":1', '"row_count":NaN'),
        '{"schema":' + "[" * 1000 + "0" + "]" * 1000 + "}",
        " " * (16 * 1024 * 1024 + 1),
    ):
        with pytest.raises(CSVReviewError):
            CSVReviewPlan.from_json(bad)
    with pytest.raises(CSVReviewError):
        apply(engine, source, plan, [], policy)
    with pytest.raises(CSVReviewError):
        apply(engine, source, plan, confirm(plan) * 2, policy)
    with pytest.raises(CSVReviewError):
        apply(
            engine,
            source,
            plan,
            [CSVReviewDecision(0, 0, ReviewDecision.confirm("f" * 64))],
            policy,
        )
    with pytest.raises(CSVReviewError):
        CSVReviewDecision(True, 0, ReviewDecision.add(0, 1, "PERSON"))
