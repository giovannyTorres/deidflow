from __future__ import annotations

import importlib.util
from pathlib import Path


def comparison_module():
    path = Path(__file__).parents[1] / "scripts/compare_bmx_unicode.py"
    spec = importlib.util.spec_from_file_location("bmx_unicode_comparison", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_oracle_rejects_approved_partial_email_even_without_full_literal():
    helper = comparison_module()
    source = "Correo ana\u200d.lopez@example.com"
    observed = {
        "text": "Correo ana\u200d[EMAIL]",
        "state": "APPROVED",
        "mappings": [[11, len(source), 11, 18, ["EMAIL"], "placeholder"]],
    }
    metrics = helper.inspect_probe(source, "EMAIL", 7, observed)
    assert metrics["unsafe_approved"] is True
    assert metrics["full_source_removed"] is False
    assert metrics["leaked_mentions"] == 1


def test_local_worker_pins_runtime_and_returns_real_zwnj_result():
    import subprocess

    import pytest

    helper = comparison_module()
    root = Path(__file__).parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    with pytest.raises(ValueError, match="^Invalid pinned local candidate$"):
        with helper.LocalCandidate(root, "0" * 40):
            pass
    with helper.LocalCandidate(root, revision) as candidate:
        assert candidate.descriptor["revision"] == revision
        assert candidate.descriptor["cache_mode"] == "isolated_empty_cache_prefix"
        assert candidate.descriptor["cache_entries"] == 0
        observed = candidate.request("run", "DNI 1234\u200c5678Z", country="ES")
        assert observed["state"] in {"APPROVED", "REVIEW_REQUIRED", "BLOCKED"}
        assert isinstance(observed["mappings"], list)
        pins = candidate.finish()
        assert pins["source_sha256"] == candidate.descriptor["source_sha256"]
        assert pins["model_sha256"] == candidate.descriptor["model_sha256"]
        assert pins["network_attempts"] == 0
        assert pins["cache_entries"] == 0
        assert pins["loaded_modules"]
        assert all(row["path"].startswith("src/deidflow/") for row in pins["loaded_modules"])


def test_probe_report_is_fictional_and_contains_no_source_values_or_coordinates():
    import json
    import subprocess

    helper = comparison_module()
    root = Path(__file__).parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    with helper.LocalCandidate(root, revision) as candidate:
        report = helper.evaluate_probes(candidate)
        candidate.finish()
    assert report["schema_version"] == "deidflow.unicode-fictional-probes.v1"
    assert report["exposure"] == "known_regression"
    assert len(report["probes"]) == 6
    encoded = json.dumps(report)
    for source_value in ("1234", "612", "lopez", "GOMA", "mappings", "start", "end", "text"):
        assert source_value not in encoded
    assert report["totals"]["required_removals"] == 6


def test_probe_oracle_requires_removal_of_zwnj_with_the_whole_source_span():
    helper = comparison_module()
    source = "DNI 1234\u200c5678Z"
    metrics = helper.inspect_probe(
        source,
        "NATIONAL_ID",
        4,
        {
            "text": "DNI [NATIONAL_ID]",
            "state": "APPROVED",
            "mappings": [[4, len(source), 4, 17, ["NATIONAL_ID"], "placeholder"]],
        },
    )
    assert metrics["full_source_removed"] is True
    assert metrics["unsafe_approved"] is False


def test_comparison_rejects_wrong_runtime_pin_without_publishing_output(tmp_path):
    import pytest

    helper = comparison_module()
    root = Path(__file__).parents[1]
    with pytest.raises(ValueError, match="^Invalid pinned local candidate$"):
        helper.compare(
            [root / "examples/benchmark-mx-identifiers"],
            [("baseline", root, "0" * 40), ("fixed", root, "0" * 40)],
            tmp_path / "comparison",
        )
    assert not (tmp_path / "comparison").exists()


def test_comparison_publishes_aggregate_reports_without_source_packages(tmp_path):
    import json
    import subprocess

    from test_benchmark_perturbations import literal_package

    helper = comparison_module()
    source, _ = literal_package(tmp_path / "source")
    root = Path(__file__).parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    output = tmp_path / "published"
    report = helper.compare(
        [source], [("baseline", root, revision), ("fixed", root, revision)], output
    )
    assert json.loads((output / "report.json").read_text()) == report
    published = [path for path in output.rglob("*") if path.is_file()]
    assert not any(path.suffix == ".jsonl" or path.name == "suite.json" for path in published)
    assert all(path.name == "report.json" for path in published)
    for path in published:
        assert "Ana María Sol" not in path.read_text()
        assert "codepoint_boundaries" not in path.read_text()
