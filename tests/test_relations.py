"""Value-free identity graphs and explicit, evidenced relationships."""

from __future__ import annotations

import json

import pytest

from deidflow import DeidEngine, Finding, Policy, Rule
from deidflow.core import EntityType
from deidflow.llm import DeidSession as CompatibilitySession
from deidflow.placeholders import LABELS_ES, ROLE_LABELS_ES, PlaceholderAllocator
from deidflow.review import ReviewDecision, create_review_plan, verify_review_receipt
from deidflow.session import DeidSession

MODEL = "a" * 64
REVIEWER = "reviewer-" + "b" * 16


def session(**kwargs):
    return DeidSession(
        DeidEngine(), policy=Policy(default=Rule("indexed"), require_ner=False), **kwargs
    )


def test_neutral_default_and_compatibility_import():
    assert CompatibilitySession is DeidSession
    current = DeidSession(DeidEngine())
    assert current.policy.name == "context"
    result = current.deidentify("sin identificadores")
    assert result.status == "REVIEW_REQUIRED"
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues
    assert "HUMAN_REVIEW_REQUIRED" in result.issues


def test_every_entity_and_domain_role_has_a_spanish_label():
    assert {kind.value for kind in EntityType} <= LABELS_ES.keys()
    assert LABELS_ES["AMOUNT"] == "IMPORTE"
    allocator = PlaceholderAllocator()
    for role, label in ROLE_LABELS_ES.items():
        finding = Finding("PERSON", 0, 3, 0.99, "synthetic", context=(f"role:{role}",))
        assert allocator.placeholder("Ana", "PERSON", [finding]) == f"[{label}_1]"


def test_graph_tracks_exact_identity_occurrences_and_offsets_without_values():
    current = session()
    first = current.deidentify("Contacto: ana@example.test; otro: beto@example.test")
    second = current.deidentify("ana@example.test")
    graph = current.graph()
    assert [entity["id"] for entity in graph["entities"]] == ["[CORREO_1]", "[CORREO_2]"]
    assert len(graph["documents"]) == 2 and len(graph["occurrences"]) == 3
    assert graph["occurrences"][0]["entity_id"] == graph["occurrences"][2]["entity_id"]
    assert [document["sequence"] for document in graph["documents"]] == [1, 2]
    assert graph["documents"][0]["id"] == first.audit["document_id"]
    assert graph["documents"][1]["id"] == second.audit["document_id"]
    for mapping, occurrence in zip(first.mappings, graph["occurrences"], strict=False):
        assert (occurrence["start"], occurrence["end"]) == (
            mapping.source_start,
            mapping.source_end,
        )
        assert (
            first.output_text[occurrence["output_start"] : occurrence["output_end"]]
            == occurrence["entity_id"]
        )
    serialized = json.dumps(graph)
    assert "example.test" not in serialized and "allocator" not in serialized
    assert "hash" not in serialized and "key" not in serialized
    graph["entities"][0]["id"] = "mutated"
    graph["documents"].clear()
    assert len(current.graph()["documents"]) == 2
    assert current.graph()["entities"][0]["id"] == "[CORREO_1]"
    assert current.graph()["relations"] == []


def test_relationship_requires_human_evidence_for_both_known_endpoints():
    current = session()
    current.deidentify("ana@example.test y beto@example.test")
    evidence = [item["id"] for item in current.graph()["occurrences"]]
    relation = current.relate("[CORREO_1]", "relacionado_con", "[CORREO_2]", evidence_ids=evidence)
    assert relation["provenance"] == "human"
    assert relation["evidence_ids"] == evidence
    assert (
        current.relate("[CORREO_1]", "relacionado_con", "[CORREO_2]", evidence_ids=evidence)
        == relation
    )
    assert len(current.graph()["relations"]) == 1
    relation["evidence_ids"].clear()
    assert current.graph()["relations"][0]["evidence_ids"] == evidence
    for source, kind, target, ids, provenance in (
        ("[CORREO_1]", "relacionado_con", "[CORREO_1]", evidence, "human"),
        ("[CORREO_1]", "relacionado_con", "[CORREO_9]", evidence, "human"),
        ("[CORREO_1]", "same_person", "[CORREO_2]", evidence, "human"),
        ("[CORREO_1]", "relacionado_con", "[CORREO_2]", evidence, "inferred"),
        ("[CORREO_1]", "relacionado_con", "[CORREO_2]", evidence[:1], "human"),
        ("[CORREO_1]", "relacionado_con", "[CORREO_2]", ["occ_" + "a" * 32], "human"),
        ("[CORREO_1]", "relacionado_con", "[CORREO_2]", evidence * 2, "human"),
        ("[CORREO_1]", "relacionado_con", "[CORREO_2]", [], "human"),
        ([], "relacionado_con", "[CORREO_2]", evidence, "human"),
    ):
        with pytest.raises(ValueError):
            current.relate(source, kind, target, evidence_ids=ids, provenance=provenance)
    assert len(current.graph()["relations"]) == 1


def test_relations_and_occurrence_ids_survive_save_load(tmp_path):
    pytest.importorskip("cryptography")
    current = session()
    current.deidentify("ana@example.test y beto@example.test")
    current.relate(
        "[CORREO_1]",
        "contraparte_de",
        "[CORREO_2]",
        evidence_ids=[item["id"] for item in current.graph()["occurrences"]],
    )
    graph = current.graph()
    path = tmp_path / "relations.enc"
    current.save(path, key=b"r" * 32)
    restored = DeidSession.load(path, key=b"r" * 32, engine=DeidEngine())
    assert restored.graph() == graph
    current.close()
    assert current._occurrences == [] and current._relations == [] and current.placeholders() == {}
    with pytest.raises(ValueError, match="closed"):
        current.graph()


def test_manual_review_reuses_session_identity_and_records_added_spans():
    current = session(model_digest=MODEL)
    current.deidentify("ana@example.test")
    source = "Zelmira Salcedo: ana@example.test"
    plan = create_review_plan(current.engine, source, policy=current.policy, model_digest=MODEL)
    decisions = [ReviewDecision.confirm(span.span_id) for span in plan.spans]
    decisions.append(ReviewDecision.add(0, len("Zelmira Salcedo"), "PERSON"))
    signing_key = b"s" * 32
    reviewed = current.apply_review(
        source,
        plan,
        decisions,
        reviewer_id=REVIEWER,
        approve=True,
        source_complete=True,
        signing_key=signing_key,
    )
    assert reviewed.result.release_approved
    assert reviewed.result.output_text == "[PERSONA_1]: [CORREO_1]"
    assert current.reidentify(reviewed.result.output_text).text == source
    graph = current.graph()
    assert len(graph["documents"]) == 2 and len(graph["occurrences"]) == 3
    assert reviewed.result.audit["occurrence_ids"] == [
        item["id"] for item in graph["occurrences"][-2:]
    ]
    assert verify_review_receipt(
        reviewed.receipt,
        source=source,
        output=reviewed.result.output_text,
        policy=current.policy,
        model_digest=MODEL,
        signing_key=signing_key,
    )
    before = current.graph()
    with pytest.raises(ValueError, match="STALE"):
        current.apply_review(source + " modified", plan, decisions, reviewer_id=REVIEWER)
    assert current.graph() == before


def test_session_review_requires_bound_model_and_preserves_pending_status():
    unbound = session()
    source = "ana@example.test"
    plan = create_review_plan(unbound.engine, source, policy=unbound.policy, model_digest=MODEL)
    decisions = [ReviewDecision.confirm(span.span_id) for span in plan.spans]
    with pytest.raises(ValueError, match="digest"):
        unbound.apply_review(source, plan, decisions, reviewer_id=REVIEWER)
    bound = session(model_digest=MODEL)
    reviewed = bound.apply_review(source, plan, decisions, reviewer_id=REVIEWER)
    assert reviewed.result.status == "REVIEW_REQUIRED"
    assert bound.graph()["documents"][0]["status"] == "REVIEW_REQUIRED"
    assert bound.reidentify(reviewed.result.output_text).text == source


def test_session_policy_needs_explicit_review_attestation_to_release():
    current = DeidSession(
        DeidEngine(),
        policy=Policy(default=Rule("indexed"), require_ner=False, require_human_review=True),
        model_digest=MODEL,
    )
    source = "ana@example.test"
    pending = current.deidentify(source)
    assert pending.status == "REVIEW_REQUIRED" and "HUMAN_REVIEW_REQUIRED" in pending.issues
    plan = create_review_plan(current.engine, source, policy=current.policy, model_digest=MODEL)
    decisions = [ReviewDecision.confirm(span.span_id) for span in plan.spans]
    reviewed = current.apply_review(
        source, plan, decisions, reviewer_id=REVIEWER, approve=True, source_complete=True
    )
    assert reviewed.result.release_approved
    assert [item["status"] for item in current.graph()["documents"]] == [
        "REVIEW_REQUIRED",
        "APPROVED",
    ]


def test_changed_vault_values_are_never_restored():
    current = session()
    current.deidentify("ana@example.test")
    current.vault.put("[CORREO_1]", "beto@example.test")
    for strict in (True, False):
        with pytest.raises(ValueError, match="conflicts"):
            current.reidentify("[CORREO_1]", strict=strict)


def context(*items):
    return [Finding("PERSON", 0, 3, 0.99, "synthetic.context", context=items)]


def test_compatible_context_reuses_only_exact_values_and_updates_metadata_without_renaming():
    allocator = PlaceholderAllocator(compatible_context=True)
    token = allocator.placeholder("Ana López", "PERSON")
    assert token == "[PERSONA_1]"
    assert allocator.placeholder("Ana López", "PERSON", context("role:patient")) == token
    assert allocator.placeholder("Ana Lo\u0301pez", "PERSON", context("gender:f")) == token
    assert (
        allocator.placeholder("Ana López", "PERSON", context("role:patient", "gender:f")) == token
    )
    assert allocator.issued()[token] == ("PERSON", "patient")
    assert allocator.context_metadata()[token] == ("patient", "f")
    assert len(allocator._exact) == 4
    for value, kind in (
        ("Ana", "PERSON"),
        ("ANA LÓPEZ", "PERSON"),
        ("Ana Lopez", "PERSON"),
        ("Ana López", "ORGANIZATION"),
    ):
        assert allocator.placeholder(value, kind) != token
    strict = PlaceholderAllocator()
    assert strict.placeholder("Ana", "PERSON") != strict.placeholder(
        "Ana", "PERSON", context("role:patient")
    )


@pytest.mark.parametrize(
    "field,first,second", [("role", "patient", "clinician"), ("gender", "f", "m")]
)
def test_explicit_context_conflicts_split_and_ambiguous_old_none_key_never_wins(
    field, first, second
):
    allocator = PlaceholderAllocator(compatible_context=True)
    original = allocator.placeholder("Ana", "PERSON")
    assert allocator.placeholder("Ana", "PERSON", context(f"{field}:{first}")) == original
    distinct = allocator.placeholder("Ana", "PERSON", context(f"{field}:{second}"))
    assert distinct != original
    assert allocator.placeholder("Ana", "PERSON", context(f"{field}:{first}")) == original
    assert allocator.placeholder("Ana", "PERSON", context(f"{field}:{second}")) == distinct
    before = allocator._dump_state()
    with pytest.raises(ValueError, match="Ambiguous"):
        allocator.placeholder("Ana", "PERSON")
    assert allocator._dump_state() == before


def test_partial_context_must_still_disambiguate_both_known_constraints():
    allocator = PlaceholderAllocator(compatible_context=True)
    female = allocator.placeholder("Alex", "PERSON", context("role:patient", "gender:f"))
    male = allocator.placeholder("Alex", "PERSON", context("role:patient", "gender:m"))
    assert female != male
    with pytest.raises(ValueError, match="Ambiguous"):
        allocator.placeholder("Alex", "PERSON", context("role:patient"))
    assert allocator.placeholder("Alex", "PERSON", context("gender:f")) == female
    with pytest.raises(ValueError, match="Conflicting"):
        allocator.placeholder("Alex", "PERSON", context("role:patient", "role:clinician"))
    with pytest.raises(ValueError, match="Conflicting"):
        allocator.placeholder("Alex", "PERSON", context("gender:f", "gender:m"))


def test_unknown_custom_types_use_generic_labels_unless_explicitly_configured():
    class Custom:
        def detect_batch(self, texts):
            return [
                [Finding("MARIANA_SANCHEZ", 0, len(text), 0.99, "custom")]
                if text == "secreto"
                else []
                for text in texts
            ]

    current = DeidSession(
        DeidEngine(nlp=Custom()), policy=Policy(default=Rule("indexed"), require_ner=False)
    )
    assert current.deidentify("secreto").output_text == "[DATO_SENSIBLE_1]"
    graph = json.dumps(current.graph())
    assert "MARIANA_SANCHEZ" not in graph and "secreto" not in graph
    custom = PlaceholderAllocator(labels={"CUSTOM": "DATO_LOCAL"})
    assert custom.placeholder("valor", "CUSTOM") == "[DATO_LOCAL_1]"


def test_neutral_sessions_enable_compatible_context_only_for_their_default_allocator():
    assert session().allocator.compatible_context is True
    strict = PlaceholderAllocator()
    assert session(allocator=strict).allocator.compatible_context is False
    with pytest.raises(ValueError, match="boolean"):
        PlaceholderAllocator(compatible_context=1)


def test_large_catalog_lookup_does_not_traverse_unrelated_identities():
    class CountedIdentities(dict):
        visited = 0

        def items(self):
            for pair in super().items():
                self.visited += 1
                yield pair

    allocator = PlaceholderAllocator(compatible_context=True)
    tokens = [allocator.placeholder(f"Persona sintética {i}", "PERSON") for i in range(5000)]
    counted = CountedIdentities(allocator._exact)
    allocator._exact = counted
    assert (
        allocator.placeholder("Persona sintética 2500", "PERSON", context("role:patient"))
        == tokens[2500]
    )
    assert allocator.placeholder("Persona sintética 2500", "PERSON") == tokens[2500]
    assert allocator.placeholder("Persona nueva", "PERSON") == "[PERSONA_5001]"
    assert allocator.placeholder("Persona sintética 2500", "ORGANIZATION") == "[ORGANIZACION_1]"
    different = allocator.placeholder("Persona sintética 2500", "PERSON", context("role:clinician"))
    assert different != tokens[2500]
    with pytest.raises(ValueError, match="Ambiguous"):
        allocator.placeholder("Persona sintética 2500", "PERSON")
    assert allocator.placeholder("Persona sintética 4999", "PERSON") == tokens[4999]
    # An operation-count guard catches the previous quadratic scan without a
    # machine-dependent timing threshold, while exercising real allocations.
    assert counted.visited == 0


def test_candidate_index_is_derived_validated_and_cleared():
    allocator = PlaceholderAllocator(compatible_context=True)
    token = allocator.placeholder("Ana", "PERSON")
    allocator.placeholder("Ana", "PERSON", context("role:patient", "gender:f"))
    state = allocator._dump_state()
    assert "value_index" not in state and "_value_index" not in state
    restored = PlaceholderAllocator._from_state(state)
    assert restored._value_index == allocator._value_index
    assert restored.placeholder("Ana", "PERSON", context("gender:f")) == token
    invalid = {**state, "value_index": {"untrusted": [token]}}
    with pytest.raises(ValueError):
        PlaceholderAllocator._from_state(invalid)
    restored._value_index.clear()
    with pytest.raises(ValueError, match="inconsistent"):
        restored._dump_state()
    allocator.reset()
    assert allocator._value_index == {} and allocator._contexts == {}
    assert allocator.placeholder("Ana", "PERSON") == "[PERSONA_1]"
