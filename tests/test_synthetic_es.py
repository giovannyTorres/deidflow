from __future__ import annotations

import pytest

pytest.importorskip("faker")

from deidflow import DeidEngine  # noqa: E402
from deidflow.benchmarks.synthetic_es import HELD_OUT, PROFILES, TEMPLATES, generate  # noqa: E402


def _family(example):
    return example.template_id.split(":", 1)[0]


def test_generation_is_seeded_and_spans_are_valid():
    first = list(generate(60, split="train", seed=7))
    second = list(generate(60, split="train", seed=7))
    assert [(e.text, e.spans) for e in first] == [(e.text, e.spans) for e in second]
    assert [e.text for e in generate(60, split="train", seed=8)] != [e.text for e in first]
    for example in first:
        previous_end = 0
        for span in sorted(example.spans, key=lambda s: s.start):
            value = example.text[span.start : span.end]
            assert value and value == value.strip(), (example.source_id, value)
            assert span.start >= previous_end
            previous_end = span.end


def test_template_families_are_disjoint_across_splits():
    families = {family for family, _ in TEMPLATES}
    assert HELD_OUT["validation"] <= families and HELD_OUT["test"] <= families
    assert not HELD_OUT["validation"] & HELD_OUT["test"]
    seen = {
        split: {_family(e) for e in generate(len(TEMPLATES), split=split)}
        for split in ("train", "validation", "test")
    }
    assert seen["validation"] == HELD_OUT["validation"]
    assert seen["test"] == HELD_OUT["test"]
    assert not seen["train"] & (HELD_OUT["validation"] | HELD_OUT["test"])
    with pytest.raises(ValueError):
        next(generate(1, split="dev"))


@pytest.mark.parametrize("code", sorted(PROFILES))
def test_generated_identifiers_are_found_by_the_country_rules(code):
    engine = DeidEngine(country=code)
    kinds = {"NATIONAL_ID", "TAX_ID"}
    total = found = 0
    for example in generate(80, split="train", countries=(code,), seed=11):
        findings = engine.scan_text(example.text)
        for span in example.spans:
            if span.entity_type not in kinds:
                continue
            total += 1
            found += any(
                f.start <= span.start and f.end >= span.end and f.score >= 0.5 for f in findings
            )
    assert total and found / total >= 0.95, (code, found, total)
