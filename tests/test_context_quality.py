from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from deidflow import DeidEngine, Finding, Policy, ReleaseStatus, Result, Rule
from deidflow.benchmarks.context_quality import (
    ContextCase,
    ContextSpan,
    ExpectedRelation,
    SensitiveSpan,
    evaluate_context_sessions,
    load_context_cases,
    measure_context_case,
)
from deidflow.benchmarks.runner import offline_network
from deidflow.llm import DeidSession
from deidflow.transformations import SourceMap, transform_text


def case() -> ContextCase:
    return ContextCase(
        "sample",
        "clinical",
        "session",
        "Ana: no suspender 5 mg.",
        (SensitiveSpan(0, 3, "PERSON", "patient"),),
        (ContextSpan(5, 22, "dose"),),
    )


def test_actual_output_context_and_sensitive_character_accounting():
    sample = case()
    output, mappings = transform_text(
        sample.text,
        [Finding("PERSON", 0, 3, 1, "test")],
        Policy(default=Rule("indexed"), require_ner=False),
    )
    result = Result(ReleaseStatus.REVIEW_REQUIRED, output_text=output, mappings=mappings)
    measured = measure_context_case(sample, result)
    assert measured.counts["removed_sensitive_characters"] == 3
    assert measured.counts["retained_nonsensitive_characters"] == len(sample.text) - 3
    assert measured.counts["retained_required_context_spans"] == 1
    assert measured.counts["literal_sensitive_value_survivors"] == 0
    assert measured.counts["joint_success_documents"] == 1
    assert measured.mentions == [("patient", "[PERSONA_1]")]


def test_over_redaction_is_not_rewarded_as_context_preservation():
    sample = case()
    output, mappings = transform_text(
        sample.text,
        [Finding("PERSON", 0, 22, 1, "test")],
        Policy(default=Rule("indexed"), require_ner=False),
    )
    measured = measure_context_case(
        sample, Result(ReleaseStatus.APPROVED, output_text=output, mappings=mappings)
    )
    assert measured.counts["removed_sensitive_characters"] == 3
    assert measured.counts["retained_required_context_spans"] == 0
    assert measured.counts["exact_indexed_sensitive_spans"] == 0
    assert measured.counts["joint_success_documents"] == 0


def test_declared_map_does_not_hide_unmapped_output_edits_or_copied_identifiers():
    sample = case()
    forged = Result(
        ReleaseStatus.APPROVED,
        output_text="[PERSONA_1]: suspender 5 mg.",
        mappings=[SourceMap(0, 3, 0, 11, ("PERSON",), "indexed")],
    )
    result = measure_context_case(sample, forged)
    assert result.counts["valid_source_map_documents"] == 0
    assert result.counts["removed_sensitive_characters"] == 0
    copied = Result(
        ReleaseStatus.APPROVED,
        output_text="[PERSONA_1] Ana: no suspender 5 mg.",
        mappings=[SourceMap(0, 3, 0, 15, ("PERSON",), "indexed")],
    )
    result = measure_context_case(sample, copied)
    assert result.counts["literal_sensitive_value_survivors"] == 1
    assert result.counts["joint_success_documents"] == 0


def test_mask_and_custom_replacements_do_not_receive_full_removal_credit():
    sample = ContextCase(
        "mask",
        "financial",
        "session",
        "Cuenta: 12345678.",
        (SensitiveSpan(8, 16, "BANK_ACCOUNT", "account"),),
        (),
    )
    masked = Result(
        ReleaseStatus.APPROVED,
        output_text="Cuenta: ****5678.",
        mappings=[SourceMap(8, 16, 8, 16, ("BANK_ACCOUNT",), "mask")],
    )
    measured = measure_context_case(sample, masked)
    assert measured.counts["removed_sensitive_characters"] == 4
    assert measured.counts["fully_replaced_sensitive_spans"] == 0
    uncertain = replace(masked, mappings=[replace(masked.mappings[0], action="custom")])
    assert measure_context_case(sample, uncertain).counts["removed_sensitive_characters"] == 0


@pytest.mark.parametrize(
    "action,replacement",
    [
        ("indexed", "[PERSONA_1] Garcia"),
        ("indexed", "[GARCIA_1]"),
        ("placeholder", "[PERSON] Garcia"),
        ("placeholder", "[GARCIA]"),
        ("pseudonym", "[DF_PERSON_" + "A" * 32 + "] Garcia"),
        ("redact", "████ Garcia"),
        ("suppress", "Garcia"),
        ("mask", "ana garcia"),
    ],
)
def test_claimed_erasure_action_never_hides_a_surviving_value_suffix(action, replacement):
    sample = ContextCase(
        "forged",
        "general",
        "session",
        "Ana Garcia",
        (SensitiveSpan(0, 10, "PERSON", "person"),),
        (),
    )
    forged = Result(
        ReleaseStatus.APPROVED,
        output_text=replacement,
        mappings=[SourceMap(0, 10, 0, len(replacement), ("PERSON",), action)],
    )
    counts = measure_context_case(sample, forged).counts
    assert counts["valid_source_map_documents"] == 1
    assert counts["removed_sensitive_characters"] == 0
    assert counts["joint_success_documents"] == 0
    assert counts["approved_documents_with_unremoved_sensitive_data"] == 1


def test_missing_output_never_counts_as_privacy_and_utility_success():
    result = measure_context_case(case(), Result(ReleaseStatus.BLOCKED))
    assert result.counts["output_documents"] == 0
    assert result.counts["joint_success_documents"] == 0
    assert result.counts["retained_required_context_spans"] == 0


def test_fictional_corpus_is_validated_and_fixed():
    path = Path(__file__).resolve().parents[1] / "benchmarks/context-cases-es.jsonl"
    cases, digest = load_context_cases(path)
    assert len(cases) == 40
    assert len({case.session_id for case in cases}) == 20
    assert {case.domain for case in cases} == {"clinical", "financial", "legal", "general"}
    assert len(digest) == 64
    assert sum(len(case.relations) for case in cases) == 20


def test_loader_rejects_false_context_and_cross_document_identity(tmp_path):
    row = asdict(case())
    row["preserve"] = [{"start": 0, "end": 3, "category": "dose"}]
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        load_context_cases(path)
    first = asdict(case())
    second = asdict(replace(case(), id="another", text="Eva: no suspender 5 mg."))
    path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting values"):
        load_context_cases(path)


def test_session_coverage_and_identity_work_without_network():
    text = "Correo: caso@example.org. No suspender 5 mg."
    start, end = text.index("caso@"), text.index(". No")
    first = ContextCase(
        "first", "clinical", "session", text, (SensitiveSpan(start, end, "EMAIL", "email"),), ()
    )
    second = replace(first, id="second")
    with offline_network() as guard:
        report = evaluate_context_sessions(
            [first, second],
            lambda domain: DeidSession(
                DeidEngine(), policy=Policy(default=Rule("indexed"), require_ner=False)
            ),
        )
    assert guard["attempts"] == 0
    assert report["aggregate"]["same_entity_consistency_rate"] == 1
    assert report["aggregate"]["sensitive_character_removal_rate"] == 1
    serialized = json.dumps(report)
    assert "caso@example.org" not in serialized
    assert "No suspender" not in serialized


def test_identity_metric_penalizes_unstable_tokens_and_keeps_domains_separate():
    class Unstable:
        def __init__(self):
            self.count = 0

        def deidentify(self, text, *, domain):
            self.count += 1
            token = f"[PERSONA_{self.count}]"
            return Result(
                ReleaseStatus.REVIEW_REQUIRED,
                output_text=token + text[3:],
                mappings=[SourceMap(0, 3, 0, len(token), ("PERSON",), "indexed")],
            )

        def close(self):
            pass

    report = evaluate_context_sessions(
        [case(), replace(case(), id="second")], lambda domain: Unstable()
    )
    assert report["aggregate"]["same_entity_consistency_rate"] == 0
    assert report["aggregate"]["identity_pairs"] == 1


def test_relation_fidelity_checks_direction_evidence_and_unexpected_edges():
    class GraphSession:
        def __init__(self, wrong_evidence=False, extra=False):
            self.edges = []
            self.wrong_evidence = wrong_evidence
            self.extra = extra

        def deidentify(self, text, *, domain):
            output, mappings = transform_text(
                text,
                [Finding("PERSON", 0, 3, 1, "test"), Finding("PERSON", 9, 12, 1, "test")],
                Policy(default=Rule("indexed"), require_ner=False),
            )
            return Result(ReleaseStatus.REVIEW_REQUIRED, output_text=output, mappings=mappings)

        def graph(self):
            return {
                "occurrences": [
                    {"id": "occ-a", "entity_id": "[PERSONA_1]"},
                    {"id": "occ-b", "entity_id": "[PERSONA_2]"},
                ],
                "relations": self.edges,
            }

        def relate(self, source, relation, target, *, evidence_ids, provenance):
            edge = dict(
                source=source,
                relation=relation,
                target=target,
                provenance=provenance,
                evidence_ids=[] if self.wrong_evidence else evidence_ids,
            )
            self.edges.append(edge)
            if self.extra:
                self.edges.append({**edge, "source": target, "target": source})

        def close(self):
            pass

    sample = ContextCase(
        "relation",
        "clinical",
        "group",
        "Ana cuida Eva.",
        (SensitiveSpan(0, 3, "PERSON", "a"), SensitiveSpan(9, 12, "PERSON", "b")),
        (),
        (ExpectedRelation("a", "atiende_a", "b"),),
    )
    good = evaluate_context_sessions([sample], lambda domain: GraphSession())["aggregate"]
    assert good["declared_relation_fidelity"] == 1
    assert good["declared_relation_precision"] == 1
    bad = evaluate_context_sessions([sample], lambda domain: GraphSession(wrong_evidence=True))[
        "aggregate"
    ]
    assert bad["declared_relation_fidelity"] == 0
    extra = evaluate_context_sessions([sample], lambda domain: GraphSession(extra=True))[
        "aggregate"
    ]
    assert extra["declared_relation_fidelity"] == 1
    assert extra["declared_relation_precision"] == 0.5
    assert extra["unexpected_relations"] == 1
