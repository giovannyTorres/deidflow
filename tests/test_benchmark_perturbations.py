from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest

from deidflow.benchmarks.evaluation_package import load_evaluation_package

EXAMPLES = Path(__file__).parents[1] / "examples"


def source_package(name="benchmark-mx-contextual/contextual"):
    path = EXAMPLES / name
    return path, hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest()


def literal_package(destination, text="ß\nAna María Sol\nAna María Sol\n각"):
    from deidflow.benchmarks.synthetic_package import write_package_records

    source, digest = source_package()
    package = load_evaluation_package(source, manifest_sha256=digest)
    records, manifest = deepcopy(package.records), deepcopy(package.manifest)
    records["sources"] = [records["sources"][0]]
    records["documents"] = [records["documents"][0]]
    records["documents"][0]["annotation_state"] = "draft"
    records["sources"][0]["attribution"] = "Explicit test literals for coordinate mechanics only"
    records["units"] = [records["units"][0]]
    records["units"][0].update(text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
    records["sources"][0]["content_sha256"] = records["units"][0]["text_sha256"]
    prototype = records["mentions"][0]
    records["mentions"] = []
    for number, (start, end) in enumerate(((2, 11), (6, 15), (16, 25), (20, 29)), 1):
        row = deepcopy(prototype)
        row.update(
            mention_id=f"m-{number}",
            start=start,
            end=end,
            entity_id=f"i-{number}",
            identity_evidence={"method": "synthetic_identity", "mention_ids": [f"m-{number}"]},
            validity={"pattern": "valid", "structure": "valid", "checksum": "not_applicable"},
        )
        row["annotation_provenance"].update(method="synthetic_fixture", reviews=[])
        row["sensitivity_reference"] = "Explicit test interval; no reviewed reference claim"
        records["mentions"].append(row)
    expectation = records["expectations"][0]
    records["expectations"] = []
    for number in range(1, 5):
        row = deepcopy(expectation)
        row.update(expectation_id=f"e-{number}", mention_id=f"m-{number}")
        records["expectations"].append(row)
    interval = deepcopy(expectation)
    interval.update(
        expectation_id="e-5",
        mention_id=None,
        unit_id="u-1",
        start=0,
        end=1,
        action="preserve",
        allowed_operators=["keep"],
        verification="exact_preservation",
    )
    records["expectations"].append(interval)
    records["validation_vectors"] = [
        {
            "vector_id": "v-1",
            "unit_id": "u-1",
            "entity_type": "PERSON",
            "start": 30,
            "end": 31,
            "mention_id": None,
            "sensitivity": "nonpersonal_distractor",
            "validity": {"pattern": "valid", "structure": "unknown", "checksum": "not_applicable"},
            "provenance": {
                "method": "independent_reference",
                "version": "fixture-1",
                "evidence_ref": "evidence-f",
            },
        }
    ]
    records["evidence-f"] = (
        b"Explicit test interval and states; coordinate mechanics only; no reviewer claim"
    )
    manifest["annotation_coverage"] = [manifest["annotation_coverage"][0]]
    manifest["annotation_coverage"][0]["inspected_ranges"] = [{"start": 0, "end": len(text)}]
    written = write_package_records(destination, records, manifest)
    return destination, written.manifest_sha256


def test_public_suite_is_repeatable_admitted_and_preserves_original_records(tmp_path):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite

    source, digest = source_package()
    left = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=tmp_path / "left",
        seed=17,
        recipes=("uppercase.v1",),
    )
    right = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=tmp_path / "right",
        seed=17,
        recipes=("uppercase.v1",),
    )
    assert left == right
    entry = left["packages"][0]
    loaded = load_evaluation_package(
        tmp_path / "left" / entry["path"], manifest_sha256=entry["manifest_sha256"]
    )
    original = load_evaluation_package(source, manifest_sha256=digest)
    assert len(loaded.records["documents"]) == 20
    for role in ("sources", "documents", "units", "mentions", "expectations"):
        assert loaded.records[role][: len(original.records[role])] == original.records[role]
    assert loaded.records["evidence-3"] == original.records["evidence-3"]
    assert loaded.manifest["generation"]["random_algorithm"] == "none"
    assert loaded.manifest["generation"]["seeds"] == {}
    assert all(r["annotation_state"] == "draft" for r in loaded.records["documents"][10:])
    assert entry["changed_units"] == 10
    assert left["quality"] == "DESCRIPTIVE_ONLY"


@pytest.mark.parametrize(
    "recipe,expected,names",
    [
        ("uppercase.v1", "SS\nANA MARÍA SOL\nANA MARÍA SOL\n각", ("ANA MARÍA", "MARÍA SOL")),
        (
            "nfd.v1",
            "ß\nAna Mari\u0301a Sol\nAna Mari\u0301a Sol\n각",
            ("Ana Mari\u0301a", "Mari\u0301a Sol"),
        ),
        ("crlf.v1", "ß\r\nAna María Sol\r\nAna María Sol\r\n각", ("Ana María", "María Sol")),
    ],
)
def test_unicode_and_crlf_map_crossed_repeated_mentions_intervals_and_vectors(
    tmp_path,
    recipe,
    expected,
    names,
):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite

    source, digest = literal_package(tmp_path / "literal")
    summary = generate_perturbation_suite(
        source, manifest_sha256=digest, destination=tmp_path / "suite", seed=5, recipes=(recipe,)
    )
    entry = summary["packages"][0]
    loaded = load_evaluation_package(
        tmp_path / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
    )
    text = loaded.records["units"][1]["text"]
    assert text == expected
    mentions = loaded.records["mentions"][4:]
    assert [text[m["start"] : m["end"]] for m in mentions] == [*names, *names]
    assert mentions[0]["start"] < mentions[1]["start"] < mentions[0]["end"] < mentions[1]["end"]
    assert mentions[0]["end"] < mentions[2]["start"]
    interval = loaded.records["expectations"][-1]
    assert text[interval["start"] : interval["end"]] == ("SS" if recipe == "uppercase.v1" else "ß")
    vector = loaded.records["validation_vectors"][1]
    assert text[vector["start"] : vector["end"]] == ("각" if recipe == "nfd.v1" else "각")
    assert vector["provenance"]["method"] == "synthetic_derivation"
    assert vector["provenance"]["evidence_ref"] != "evidence-f"
    assert all(m["annotation_provenance"]["reviews"] == [] for m in mentions)
    if recipe != "crlf.v1":
        assert mentions[0]["validity"] == {
            "pattern": "unknown",
            "structure": "unknown",
            "checksum": "not_applicable",
        }
    if recipe == "nfd.v1":
        assert vector["validity"]["pattern"] == "unknown"


def test_all_recipes_change_real_text_preserve_identity_closure_and_root_weight(tmp_path):
    from collections import defaultdict

    from deidflow.benchmarks.perturbation_package import (
        DEFAULT_RECIPES,
        generate_perturbation_suite,
    )

    source, digest = source_package()
    summary = generate_perturbation_suite(
        source, manifest_sha256=digest, destination=tmp_path / "suite", seed=17
    )
    assert set(DEFAULT_RECIPES) == {
        "uppercase.v1",
        "nfd.v1",
        "crlf.v1",
        "separators.v1",
        "ocr_simulated.v1",
        "columns.v1",
        "near_cut.v1",
        "long_low_density.v1",
        "high_density.v1",
    }
    assert summary["serialized_cases"] == 180
    assert summary["unique_cases"] == 100
    weights = defaultdict(float)
    for row in summary["case_weights"]:
        weights[row["root_document_id"]] += row["weight"]
    assert all(total == pytest.approx(1) for total in weights.values())
    assert len([r for r in summary["case_weights"] if r["root_document_id"] == "c-2"]) == 20
    entries = {row["recipe"]: row for row in summary["packages"]}
    assert entries["crlf.v1"]["changed_units"] == 0
    assert entries["columns.v1"]["changed_units"] > 0
    assert (
        entries["long_low_density.v1"]["perturbed_density"]["mentions_per_1000_codepoints"]
        < entries["long_low_density.v1"]["clean_density"]["mentions_per_1000_codepoints"]
    )
    assert (
        entries["high_density.v1"]["perturbed_density"]["mentions_per_1000_codepoints"]
        > entries["high_density.v1"]["clean_density"]["mentions_per_1000_codepoints"]
    )
    for recipe in ("columns.v1", "near_cut.v1", "long_low_density.v1", "high_density.v1"):
        entry = entries[recipe]
        loaded = load_evaluation_package(
            tmp_path / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
        )
        originals, children = loaded.records["mentions"][:47], loaded.records["mentions"][47:]
        assert len(children) == (94 if recipe == "high_density.v1" else 47)
        child_ids = {m["mention_id"] for m in children}
        assert all(
            set(m["identity_evidence"]["mention_ids"]) <= child_ids
            for m in children
            if m["identity_evidence"] is not None
        )
        units = {u["unit_id"]: u["text"] for u in loaded.records["units"]}
        original_values = [units[m["unit_id"]][m["start"] : m["end"]] for m in originals]
        assert [units[m["unit_id"]][m["start"] : m["end"]] for m in children] == (
            original_values * (2 if recipe == "high_density.v1" else 1)
        )
        if recipe == "columns.v1":
            assert loaded.records["units"][10]["text"] != loaded.records["units"][0]["text"]
        if recipe == "near_cut.v1":
            assert children[0]["start"] in {63, 64, 65}


def test_nfd_rejects_a_target_boundary_inside_reordered_combining_characters(tmp_path):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite
    from deidflow.benchmarks.synthetic_package import write_package_records

    source, digest = literal_package(tmp_path / "literal", "a\u0315\u0300" + " " * 28)
    loaded = load_evaluation_package(source, manifest_sha256=digest)
    loaded.records["mentions"][0].update(start=0, end=2)
    # The remaining targets are spaces, so only the first target is unrepresentable.
    rewritten = write_package_records(tmp_path / "reordered", loaded.records, loaded.manifest)
    with pytest.raises(ValueError, match="^Unrepresentable perturbation reference boundary$"):
        generate_perturbation_suite(
            tmp_path / "reordered",
            manifest_sha256=rewritten.manifest_sha256,
            destination=tmp_path / "rejected",
            seed=17,
            recipes=("nfd.v1",),
        )
    assert not (tmp_path / "rejected").exists()


def test_suite_runner_records_real_clean_and_perturbed_metrics_for_each_stratum(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark
    from deidflow.benchmarks.perturbation_package import (
        generate_perturbation_suite,
        run_perturbation_suite,
    )

    source, digest = source_package()
    suite = tmp_path / "suite"
    generated = generate_perturbation_suite(
        source, manifest_sha256=digest, destination=suite, seed=17, recipes=("columns.v1",)
    )
    report = run_perturbation_suite(
        source,
        manifest_sha256=digest,
        suite=suite,
        index_sha256=generated["index_sha256"],
        candidate="rules.mx",
        profile="detection-descriptive-v1",
        output=tmp_path / "reports",
    )
    assert len(report["results"]) == 11  # all documents, then ten declared strata
    assert report["quality"] == "DESCRIPTIVE_ONLY"
    assert "metrics" not in report  # Never pool variants as independent observations.
    row = next(r for r in report["results"] if r["stratum"] == "crossed_mentions")
    entry = generated["packages"][0]
    direct = run_package_benchmark(
        suite / entry["path"],
        manifest_sha256=entry["manifest_sha256"],
        candidate="rules.mx",
        profile="detection-descriptive-v1",
        output=tmp_path / "direct",
        strata=("perturbation:columns.v1:crossed_mentions",),
    )["result"]
    assert row["perturbed"] == direct
    assert row["clean"]["execution"]["required_mentions"] == 4
    assert row["perturbed"]["execution"]["required_mentions"] == 4
    assert row["perturbed"]["metrics"]["PERSON"]["support"] == 4


def test_suite_refuses_existing_or_source_nested_outputs_and_invalid_sources(tmp_path):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite
    from deidflow.benchmarks.synthetic_package import write_package_records

    source, digest = literal_package(tmp_path / "source")
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "sentinel").write_text("keep")
    for target in (existing, source / "nested"):
        with pytest.raises(ValueError):
            generate_perturbation_suite(
                source,
                manifest_sha256=digest,
                destination=target,
                seed=17,
                recipes=("uppercase.v1",),
            )
    assert (existing / "sentinel").read_text() == "keep"
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    loaded = load_evaluation_package(source, manifest_sha256=digest)
    loaded.records["documents"][0].update(panel=None, partition="train")
    training = write_package_records(tmp_path / "training", loaded.records, loaded.manifest)
    with pytest.raises(ValueError, match="^Unsupported textual perturbation configuration$"):
        generate_perturbation_suite(
            tmp_path / "training",
            manifest_sha256=training.manifest_sha256,
            destination=tmp_path / "rejected",
            seed=17,
        )
    assert not (tmp_path / "rejected").exists()


def test_suite_rejects_oversized_source_before_expanding_codepoint_maps(tmp_path):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite

    source, digest = literal_package(tmp_path / "source", "x" * 50001)
    with pytest.raises(ValueError, match="^Unsupported textual perturbation configuration$"):
        generate_perturbation_suite(
            source, manifest_sha256=digest, destination=tmp_path / "rejected", seed=17
        )
    assert not (tmp_path / "rejected").exists()


def test_suite_rejects_reserved_strata_that_would_mix_clean_and_perturbed_cases(tmp_path):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite
    from deidflow.benchmarks.synthetic_package import write_package_records

    source, digest = literal_package(tmp_path / "source")
    loaded = load_evaluation_package(source, manifest_sha256=digest)
    loaded.records["documents"][0]["strata"].append("perturbation:uppercase.v1")
    loaded.manifest["scope"]["optional_strata"].append("perturbation:uppercase.v1")
    reserved = write_package_records(tmp_path / "reserved", loaded.records, loaded.manifest)
    with pytest.raises(ValueError, match="^Unsupported textual perturbation configuration$"):
        generate_perturbation_suite(
            tmp_path / "reserved",
            manifest_sha256=reserved.manifest_sha256,
            destination=tmp_path / "rejected",
            seed=17,
            recipes=("uppercase.v1",),
        )
    assert not (tmp_path / "rejected").exists()


def test_crlf_preserves_a_reference_ending_inside_an_existing_crlf_pair(tmp_path):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite

    source, digest = literal_package(tmp_path / "source", "\r\n" + " " * 29)
    summary = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=tmp_path / "suite",
        seed=17,
        recipes=("crlf.v1",),
    )
    entry = summary["packages"][0]
    loaded = load_evaluation_package(
        tmp_path / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
    )
    interval = loaded.records["expectations"][-1]
    assert loaded.records["units"][1]["text"][interval["start"] : interval["end"]] == "\r"
    assert entry["changed_units"] == 0


def test_nfd_never_moves_inspected_coverage_to_a_different_combining_character(tmp_path):
    from deidflow.benchmarks.perturbation_package import generate_perturbation_suite
    from deidflow.benchmarks.synthetic_package import write_package_records

    source, digest = literal_package(tmp_path / "source", "a\u0315\u0300" + " " * 28)
    loaded = load_evaluation_package(source, manifest_sha256=digest)
    for role in ("mentions", "expectations", "validation_vectors"):
        loaded.records[role] = []
    loaded.manifest["annotation_coverage"][0].update(
        exhaustive_entity_types=[], inspected_ranges=[{"start": 1, "end": 2}]
    )
    partial = write_package_records(tmp_path / "partial", loaded.records, loaded.manifest)
    with pytest.raises(ValueError, match="^Unrepresentable perturbation reference boundary$"):
        generate_perturbation_suite(
            tmp_path / "partial",
            manifest_sha256=partial.manifest_sha256,
            destination=tmp_path / "rejected",
            seed=17,
            recipes=("nfd.v1",),
        )
    assert not (tmp_path / "rejected").exists()


def test_report_budget_stops_remaining_candidate_work_and_leaves_no_output(tmp_path):
    from deidflow.benchmarks.package_runner import DetectionCandidate
    from deidflow.benchmarks.perturbation_package import (
        generate_perturbation_suite,
        run_perturbation_suite,
    )
    from deidflow.benchmarks.synthetic_package import write_package_records
    from deidflow.core import EntityType

    source, digest = literal_package(tmp_path / "source")
    loaded = load_evaluation_package(source, manifest_sha256=digest)
    strata = [f"mechanical-stratum-{n}" for n in range(54)]
    loaded.records["documents"][0]["strata"].extend(strata)
    loaded.manifest["scope"]["optional_strata"].extend(strata)
    labels = sorted(entity.value for entity in EntityType)
    loaded.manifest["scope"]["entity_types"] = labels
    loaded.manifest["annotation_coverage"][0]["exhaustive_entity_types"] = labels
    expanded = write_package_records(tmp_path / "expanded", loaded.records, loaded.manifest)
    generated = generate_perturbation_suite(
        tmp_path / "expanded",
        manifest_sha256=expanded.manifest_sha256,
        destination=tmp_path / "suite",
        seed=17,
    )
    calls = 0

    def detect(text):
        nonlocal calls
        calls += 1
        return []

    candidate = DetectionCandidate("candidate-a", "a" * 64, detect)
    with pytest.raises(ValueError, match="^Invalid perturbation suite evaluation$"):
        run_perturbation_suite(
            tmp_path / "expanded",
            manifest_sha256=expanded.manifest_sha256,
            suite=tmp_path / "suite",
            index_sha256=generated["index_sha256"],
            candidate=candidate,
            profile="detection-descriptive-v1",
            output=tmp_path / "reports",
        )
    assert 0 < calls < 1008  # 9 recipes × 56 pairs × 2 one-unit callbacks.
    assert not (tmp_path / "reports").exists()
