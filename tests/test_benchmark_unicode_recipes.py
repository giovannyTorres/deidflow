from __future__ import annotations

import hashlib
import json

import pytest
from test_benchmark_perturbations import literal_package

from deidflow.benchmarks.evaluation_package import load_evaluation_package
from deidflow.benchmarks.package_runner import DetectionCandidate
from deidflow.benchmarks.perturbation_package import (
    generate_perturbation_suite,
    run_perturbation_suite,
)
from deidflow.benchmarks.synthetic_package import canonical_json, write_package_records


def test_fullwidth_targets_identifiers_and_projects_crossed_mentions(tmp_path):
    source, digest = literal_package(tmp_path / "source")
    generated = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=tmp_path / "suite",
        seed=0,
        recipes=("fullwidth.v1",),
    )
    entry = generated["packages"][0]
    child = load_evaluation_package(
        tmp_path / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
    )
    text = child.records["units"][1]["text"]
    assert text == "ß\nＡｎａ Ｍａｒíａ Ｓｏｌ\nＡｎａ Ｍａｒíａ Ｓｏｌ\n각"
    assert [text[m["start"] : m["end"]] for m in child.records["mentions"][4:]] == [
        "Ａｎａ Ｍａｒíａ",
        "Ｍａｒíａ Ｓｏｌ",
        "Ａｎａ Ｍａｒíａ",
        "Ｍａｒíａ Ｓｏｌ",
    ]
    original = load_evaluation_package(source, manifest_sha256=digest)
    for role, rows in original.records.items():
        assert (
            child.records[role][: len(rows)] == rows
            if isinstance(rows, list)
            else child.records[role] == rows
        )
    assert (
        child.records["validation_vectors"][1]["validity"]
        == original.records["validation_vectors"][0]["validity"]
    )


def test_format_controls_stay_inside_crossed_targets_and_preserve_unknowns(tmp_path):
    source, digest = literal_package(tmp_path / "source")
    arguments = dict(manifest_sha256=digest, seed=0, recipes=("format_chars.v1",))
    generated = generate_perturbation_suite(source, destination=tmp_path / "suite", **arguments)
    repeated = generate_perturbation_suite(source, destination=tmp_path / "repeat", **arguments)
    assert generated == repeated
    entry = generated["packages"][0]
    child = load_evaluation_package(
        tmp_path / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
    )
    text = child.records["units"][1]["text"]
    assert text == (
        "ß\nA\u2060n\ufeffa M\u200da\u2060r\ufeffí\u00ada S\u2060o\ufeffl\n"
        "A\u200dn\u2060a M\u200ba\u200dr\u2060í\ufeffa S\u200do\u2060l\n각"
    )
    assert [text[m["start"] : m["end"]] for m in child.records["mentions"][4:]] == [
        "A\u2060n\ufeffa M\u200da\u2060r\ufeffí\u00ada",
        "M\u200da\u2060r\ufeffí\u00ada S\u2060o\ufeffl",
        "A\u200dn\u2060a M\u200ba\u200dr\u2060í\ufeffa",
        "M\u200ba\u200dr\u2060í\ufeffa S\u200do\u2060l",
    ]
    assert all(
        m["validity"]
        == {"pattern": "unknown", "structure": "unknown", "checksum": "not_applicable"}
        for m in child.records["mentions"][4:]
    )
    vector = child.records["validation_vectors"][1]
    assert vector["validity"] == {
        "pattern": "valid",
        "structure": "unknown",
        "checksum": "not_applicable",
    }


@pytest.mark.parametrize(
    "corruption", ["text", "map", "seed", "parameters", "mention", "validity", "coverage"]
)
def test_semantically_forged_unicode_data_is_rejected_before_candidate_work(tmp_path, corruption):
    source, digest = literal_package(tmp_path / "source")
    original = load_evaluation_package(source, manifest_sha256=digest)
    original.records["validation_vectors"] = []
    source = tmp_path / "without-vectors"
    digest = write_package_records(source, original.records, original.manifest).manifest_sha256
    suite = tmp_path / "suite"
    generate_perturbation_suite(
        source, manifest_sha256=digest, destination=suite, seed=0, recipes=("fullwidth.v1",)
    )
    index = json.loads((suite / "suite.json").read_bytes())
    entry = index["packages"][0]
    path = suite / entry["path"]
    child = load_evaluation_package(path, manifest_sha256=entry["manifest_sha256"])
    unit = child.records["units"][1]
    evidence_id = child.manifest["generation"]["perturbation_rules"][-1]
    evidence = json.loads(child.records[evidence_id])
    if corruption == "text":
        unit["text"] = "private-canary" + unit["text"][14:]
        unit["text_sha256"] = hashlib.sha256(unit["text"].encode()).hexdigest()
        child.records["sources"][1]["content_sha256"] = unit["text_sha256"]
    elif corruption == "map":
        evidence["codepoint_boundaries"]["u-1"][0][0] = [0, 2]
    elif corruption == "seed":
        index["seed"] = evidence["seed"] = 1
        child.records["documents"][1]["perturbation_recipe"]["seed"] = 1
    elif corruption == "parameters":
        child.records["documents"][1]["perturbation_recipe"]["parameters"][unit["unit_id"]][
            "changed_codepoints"
        ] += 1
    elif corruption == "mention":
        child.records["mentions"][4]["start"] += 1
    elif corruption == "validity":
        child.records["mentions"][4]["validity"]["pattern"] = "valid"
    else:
        child.manifest["annotation_coverage"][1]["limitations"].append("private-canary")
    child.records[evidence_id] = canonical_json(evidence)
    path.rename(tmp_path / "untampered")
    entry["manifest_sha256"] = write_package_records(
        path, child.records, child.manifest
    ).manifest_sha256
    payload = canonical_json(index)
    (suite / "suite.json").write_bytes(payload)
    calls = []
    with pytest.raises(ValueError, match="^Invalid perturbation suite evaluation$"):
        run_perturbation_suite(
            source,
            manifest_sha256=digest,
            suite=suite,
            index_sha256=hashlib.sha256(payload).hexdigest(),
            candidate=DetectionCandidate(
                "candidate-a", "a" * 64, lambda text: calls.append(text) or []
            ),
            profile="detection-descriptive-v1",
            output=tmp_path / "reports",
        )
    assert calls == []
    assert not (tmp_path / "reports").exists()


def test_unicode_admission_accepts_real_suites_and_leaves_distractors_unchanged(tmp_path):
    from pathlib import Path

    source = Path(__file__).parents[1] / "examples/benchmark-mx-identifiers"
    digest = hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest()
    suite = tmp_path / "suite"
    generated = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=suite,
        seed=17,
        recipes=("format_chars.v1", "fullwidth.v1"),
    )
    for entry in generated["packages"]:
        assert entry["changed_units"] == 27
        package = load_evaluation_package(
            suite / entry["path"], manifest_sha256=entry["manifest_sha256"]
        )
        original, children = package.records["units"][:36], package.records["units"][36:]
        vectors = package.records["validation_vectors"][:36]
        units = {row["unit_id"]: n for n, row in enumerate(original)}
        for vector in vectors:
            if vector["sensitivity"] == "nonpersonal_distractor":
                number = units[vector["unit_id"]]
                assert original[number]["text"] == children[number]["text"]
    report = run_perturbation_suite(
        source,
        manifest_sha256=digest,
        suite=suite,
        index_sha256=generated["index_sha256"],
        candidate=DetectionCandidate("candidate-a", "a" * 64, lambda text: []),
        profile="detection-descriptive-v1",
        output=tmp_path / "reports",
    )
    assert len(report["results"]) == 32
    assert all(
        pair[track]["attempt_status"] == "completed"
        for pair in report["results"]
        for track in ("clean", "perturbed")
    )


def test_nested_reference_end_is_not_extended_by_an_outer_control(tmp_path):
    source, digest = literal_package(tmp_path / "source")
    original = load_evaluation_package(source, manifest_sha256=digest)
    original.records["mentions"][1]["end"] = 10
    source = tmp_path / "nested"
    digest = write_package_records(source, original.records, original.manifest).manifest_sha256
    generated = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=tmp_path / "suite",
        seed=0,
        recipes=("format_chars.v1",),
    )
    entry = generated["packages"][0]
    child = load_evaluation_package(
        tmp_path / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
    )
    mention = child.records["mentions"][5]
    assert (
        child.records["units"][1]["text"][mention["start"] : mention["end"]]
        == "M\u200da\u2060r\ufeffí"
    )


def test_overlapping_inspected_ranges_remain_admissible_after_unicode_projection(tmp_path):
    source, digest = literal_package(tmp_path / "source")
    original = load_evaluation_package(source, manifest_sha256=digest)
    original.manifest["annotation_coverage"][0]["inspected_ranges"] = [
        {"start": 16, "end": 31},
        {"start": 0, "end": 16},
        {"start": 5, "end": 10},
    ]
    source = tmp_path / "coverage"
    digest = write_package_records(source, original.records, original.manifest).manifest_sha256
    generated = generate_perturbation_suite(
        source,
        manifest_sha256=digest,
        destination=tmp_path / "suite",
        seed=0,
        recipes=("format_chars.v1",),
    )
    report = run_perturbation_suite(
        source,
        manifest_sha256=digest,
        suite=tmp_path / "suite",
        index_sha256=generated["index_sha256"],
        candidate=DetectionCandidate("candidate-a", "a" * 64, lambda text: []),
        profile="detection-descriptive-v1",
        output=tmp_path / "reports",
    )
    assert all(
        pair[track]["attempt_status"] == "completed"
        for pair in report["results"]
        for track in ("clean", "perturbed")
    )
