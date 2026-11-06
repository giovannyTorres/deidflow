from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest


@pytest.mark.parametrize("separator", ("\u2028", "\u2029"))
def test_valid_jsonl_keeps_unicode_separators_inside_document(tmp_path, separator):
    from deidflow.benchmarks.email import run_email_benchmark

    package = write_package(
        tmp_path / "package", [{"id": "neutral", "text": f"Texto{separator}final.", "spans": []}]
    )
    report = run_email_benchmark(
        package, candidate="rules.mx", profile="email-descriptive-v1", output=tmp_path / "report"
    )
    assert report["result"]["documents"] == {"total": 1, "positive": 0, "negative": 1}


@pytest.mark.parametrize("suffix", ("\ud800", "\x00"))
def test_invalid_output_path_uses_generic_error(tmp_path, suffix):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    with pytest.raises(OSError, match="^Cannot write email benchmark report$"):
        run_email_benchmark(
            package,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=str(tmp_path / "canary@example.test") + suffix,
        )


def write_package(root: Path, records) -> Path:
    root.mkdir(exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records).encode()
    (root / "corpus.jsonl").write_bytes(payload)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "df-eval-mx.email.v1",
                "dataset_version": "1.0.0",
                "synthetic": True,
                "corpus_sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return root


def email_package(root: Path) -> Path:
    return write_package(
        root,
        [
            {
                "id": "case-canary-7f82",
                "text": "Correo: canary-7f82@example.test.",
                "spans": [{"entity_type": "EMAIL", "start": 8, "end": 32}],
            },
            {"id": "negative", "text": "No hay datos de contacto.", "spans": []},
        ],
    )


def test_email_package_produces_real_detection_metrics_and_a_descriptive_report(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    output = tmp_path / "result"
    report = run_email_benchmark(
        package, candidate="rules.mx", profile="email-descriptive-v1", output=output
    )

    assert json.loads((output / "report.json").read_text()) == report
    result = report["result"]
    assert result["candidate"]["id"] == "rules.mx"
    assert result["dataset"]["version"] == "1.0.0"
    assert result["dataset"]["panel"] == "known_regression"
    assert result["profile"] == {"id": "email-descriptive-v1", "ratified": False}
    assert result["scope"] == {
        "track": "detection",
        "entity_types": ["EMAIL"],
        "source_format": "text",
        "language": "es",
        "country": "MX",
        "matching": "exact",
    }
    assert result["documents"] == {"total": 2, "positive": 1, "negative": 1}
    assert result["metrics"]["EMAIL"] == {
        "true_positives": 1,
        "false_positives": 0,
        "false_negatives": 0,
        "support": 1,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }
    assert result["quality"] == "DESCRIPTIVE_ONLY"
    assert "PROCESS_NETWORK_ISOLATION_NOT_EVALUATED" in result["limitations"]


def test_repeat_runs_are_deterministic_offline_and_do_not_emit_source(tmp_path, capsys, caplog):
    from deidflow.benchmarks.email import run_email_benchmark
    from deidflow.benchmarks.runner import offline_network

    package = email_package(tmp_path / "private-package-canary@example.test")
    with offline_network() as network:
        first = run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=tmp_path / "first"
        )
        second = run_email_benchmark(
            package,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=tmp_path / "second",
        )

    assert network["attempts"] == 0
    assert first["result"] == second["result"]
    assert set(first) == {"schema_version", "result", "operational"}
    assert set(first["operational"]) == {"started_at", "elapsed_seconds", "python_version"}
    assert first["operational"]["elapsed_seconds"] >= 0
    captured = capsys.readouterr()
    emitted = json.dumps([first, second]) + captured.out + captured.err + caplog.text
    for forbidden in (
        "canary",
        "No hay datos de contacto.",
        str(package),
        "corpus.jsonl",
        "manifest.json",
    ):
        assert forbidden not in emitted


def test_wrong_boundaries_count_as_both_false_positive_and_false_negative(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    corpus = package / "corpus.jsonl"
    records = [json.loads(line) for line in corpus.read_text().splitlines()]
    records[0]["spans"][0]["end"] -= 1
    write_package(package, records)

    report = run_email_benchmark(
        package, candidate="rules.mx", profile="email-descriptive-v1", output=tmp_path / "result"
    )

    assert report["result"]["metrics"]["EMAIL"] == {
        "true_positives": 0,
        "false_positives": 1,
        "false_negatives": 1,
        "support": 1,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }


def test_shipped_fictional_package_works_with_the_public_entrypoint(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    source = Path(__file__).resolve().parents[1] / "examples" / "benchmark-mx-email"
    package = shutil.copytree(source, tmp_path / "package")

    report = run_email_benchmark(
        package, candidate="rules.mx", profile="email-descriptive-v1", output=tmp_path / "result"
    )

    assert report["result"]["documents"] == {"total": 2, "positive": 1, "negative": 1}
    assert report["result"]["metrics"]["EMAIL"]["true_positives"] == 1


def test_missing_denominators_are_null_not_an_accuracy_claim(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    corpus = package / "corpus.jsonl"
    records = [json.loads(line) for line in corpus.read_text().splitlines()]
    write_package(package, records[1:])

    report = run_email_benchmark(
        package, candidate="rules.mx", profile="email-descriptive-v1", output=tmp_path / "result"
    )

    assert report["result"]["metrics"]["EMAIL"] == {
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "support": 0,
        "precision": None,
        "recall": None,
        "f1": None,
    }
    assert report["result"]["quality"] == "DESCRIPTIVE_ONLY"


def test_existing_output_is_preserved_without_exposing_its_name(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    output = tmp_path / "private-output-canary@example.test"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("existing user work", encoding="utf-8")

    with pytest.raises(FileExistsError) as error:
        run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=output
        )

    assert output.name not in str(error.value)
    assert sentinel.read_text() == "existing user work"
    assert set(output.iterdir()) == {sentinel}


def test_output_io_errors_do_not_expose_paths(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    parent = tmp_path / "private-output-canary@example.test"
    parent.write_text("existing user work", encoding="utf-8")

    with pytest.raises(OSError, match="Cannot write email benchmark report") as error:
        run_email_benchmark(
            package,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=parent / "result",
        )

    assert "canary" not in str(error.value)
    assert parent.read_text() == "existing user work"


def test_unrepresentable_output_path_has_a_sanitized_error(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    output = tmp_path / ("private-canary@example.test" * 16)

    with pytest.raises(OSError, match="Cannot write email benchmark report") as error:
        run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=output
        )

    assert "canary" not in str(error.value)
    assert set(tmp_path.iterdir()) == {package}


def test_circular_package_link_has_a_sanitized_error(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = tmp_path / "private-canary@example.test"
    package.symlink_to(package, target_is_directory=True)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid email benchmark package") as error:
        run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=output
        )

    assert "canary" not in str(error.value)
    assert not output.exists()


def test_unreadable_candidate_source_fails_without_echoing_the_os_error(tmp_path, monkeypatch):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    output = tmp_path / "result"

    def unreadable(path):
        raise OSError("private-source-canary@example.test")

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    with pytest.raises(RuntimeError, match="Cannot fingerprint email benchmark candidate") as error:
        run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=output
        )

    assert "canary" not in str(error.value)
    assert not output.exists()


def test_dangling_output_link_is_preserved(tmp_path):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    output = tmp_path / "output"
    target = tmp_path / "private-canary@example.test"
    output.symlink_to(target, target_is_directory=True)

    with pytest.raises(FileExistsError):
        run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=output
        )

    assert output.is_symlink()
    assert not target.exists()


@pytest.mark.parametrize(
    ("candidate", "profile"),
    [("remote-canary@example.test", "email-descriptive-v1"), ("rules.mx", "ratified")],
)
def test_unsupported_configurations_fail_without_a_report(tmp_path, candidate, profile):
    from deidflow.benchmarks.email import run_email_benchmark

    output = tmp_path / "result"

    with pytest.raises(
        ValueError, match="Unsupported email benchmark candidate or profile"
    ) as error:
        run_email_benchmark(
            tmp_path / "missing", candidate=candidate, profile=profile, output=output
        )

    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize("location", ["manifest", "record", "span"])
def test_duplicate_json_keys_cannot_hide_replaced_content(tmp_path, location):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "package")
    manifest = package / "manifest.json"
    if location == "manifest":
        payload = manifest.read_text().replace(
            '"synthetic": true', '"synthetic": false, "synthetic": true'
        )
        manifest.write_text(payload, encoding="utf-8")
    else:
        if location == "record":
            payload = (
                '{"id":"x","text":"private-canary@example.test",'
                '"text":"Sin contacto.","spans":[]}\n'
            )
        else:
            payload = (
                '{"id":"x","text":"Correo: canary-7f82@example.test.",'
                '"spans":[{"entity_type":"EMAIL","start":9000,"start":8,"end":32}]}\n'
            )
        (package / "corpus.jsonl").write_bytes(payload.encode())
        metadata = json.loads(manifest.read_text())
        metadata["corpus_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
        manifest.write_text(json.dumps(metadata), encoding="utf-8")
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid email benchmark package") as error:
        run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=output
        )

    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize("damage", ["missing", "metadata", "checksum", "annotation", "encoding"])
def test_unusable_packages_fail_without_echoing_paths_or_source(tmp_path, damage):
    from deidflow.benchmarks.email import run_email_benchmark

    package = email_package(tmp_path / "private-package-canary@example.test")
    corpus = package / "corpus.jsonl"
    manifest = package / "manifest.json"
    if damage == "missing":
        corpus.unlink()
    elif damage == "metadata":
        data = json.loads(manifest.read_text())
        data["dataset_version"] = "metadata-canary@example.test"
        manifest.write_text(json.dumps(data), encoding="utf-8")
    elif damage == "checksum":
        corpus.write_text("not the declared corpus", encoding="utf-8")
    elif damage == "encoding":
        manifest.write_bytes(manifest.read_text().encode("utf-16"))
    else:
        records = [json.loads(line) for line in corpus.read_text().splitlines()]
        records[0]["spans"][0]["end"] = 500
        write_package(package, records)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid email benchmark package") as error:
        run_email_benchmark(
            package, candidate="rules.mx", profile="email-descriptive-v1", output=output
        )

    assert "canary" not in str(error.value)
    assert not output.exists()
