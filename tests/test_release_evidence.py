"""Release decisions must retain source uncertainty across serialization formats."""

from __future__ import annotations

import csv
import json

import pytest

from deidflow import DeidEngine, Finding, Policy, ReleaseStatus


class PartialNameAdapter:
    """Controlled source-only prediction; no model accuracy is implied."""

    def __init__(self, score, context):
        self.score = score
        self.context = context

    def detect_batch(self, texts):
        return [
            [Finding("PERSON", 0, 3, self.score, "test.partial_name", context=self.context)]
            if text.startswith("Ana ")
            else []
            for text in texts
        ]


FORMATS = ["text", "txt", "csv", "tsv", "json", "jsonl", "pandas", "polars"]
UNCERTAINTY = [
    pytest.param(0.75, ("window_boundary",), "UNRESOLVED_MODEL_WINDOW_BOUNDARY", id="boundary"),
    pytest.param(0.5, (), "UNCERTAIN_SOURCE_FINDINGS", id="confidence"),
]


def transform(tmp_path, format_name, engine, text, *, header="notes", policy=None):
    if format_name == "text":
        result = engine.deidentify_text(text, policy=policy)
        return result, result.output_text
    if format_name in {"pandas", "polars"}:
        module = pytest.importorskip(format_name)
        frame = module.DataFrame({header: [text]})
        result = engine.deidentify_dataframe(frame, policy=policy)
        return result, result.dataframe[header].to_list()[0]
    source = tmp_path / f"input.{format_name}"
    output = tmp_path / f"output.{format_name}"
    if format_name in {"csv", "tsv"}:
        with source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t" if format_name == "tsv" else ",")
            writer.writerow([header])
            writer.writerow([text])
    elif format_name in {"json", "jsonl"}:
        source.write_text(json.dumps({header: text}) + "\n", encoding="utf-8")
    else:
        source.write_text(text, encoding="utf-8")
    result = engine.deidentify(source, output=output, policy=policy)
    serialized = output.read_text(encoding="utf-8")
    if format_name in {"json", "jsonl"}:
        return result, json.loads(serialized)[header]
    if format_name in {"csv", "tsv"}:
        with output.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t" if format_name == "tsv" else ","))
        return result, rows[1][0]
    return result, serialized


@pytest.mark.parametrize("format_name", FORMATS)
@pytest.mark.parametrize("score,context,issue", UNCERTAINTY)
def test_source_uncertainty_survives_transformation(tmp_path, format_name, score, context, issue):
    engine = DeidEngine(nlp=PartialNameAdapter(score, context))
    result, output = transform(tmp_path, format_name, engine, "Ana López")

    assert output == "[PERSON] López"
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert not result.release_approved
    assert result.issues == [issue]
    assert result.audit["transformations"] == 1


@pytest.mark.parametrize("suffix", ["json", "jsonl"])
@pytest.mark.parametrize("score,context,issue", UNCERTAINTY)
@pytest.mark.parametrize("sensitive_value", [False, True])
def test_nested_json_key_evidence_and_transformation_counts(
    tmp_path, suffix, score, context, issue, sensitive_value
):
    engine = DeidEngine(nlp=PartialNameAdapter(score, context))
    source = tmp_path / f"input.{suffix}"
    output = tmp_path / f"output.{suffix}"
    value = "Ana López" if sensitive_value else "dato"
    data = {"Ana López": {"notes": value}, "group": [{"Ana Gómez": "dato"}]}
    source.write_text(json.dumps(data) + "\n", encoding="utf-8")

    result = engine.deidentify(source, output=output)

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "[PERSON] López": {"notes": "[PERSON] López" if sensitive_value else "dato"},
        "group": [{"[PERSON] Gómez": "dato"}],
    }
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert not result.release_approved
    assert result.issues == [issue]
    assert result.audit["transformations"] == 2 + int(sensitive_value)


@pytest.mark.parametrize("format_name", ["csv", "json", "pandas", "polars"])
@pytest.mark.parametrize("fast_path", [True, False])
def test_schema_confidence_gate_does_not_depend_on_fast_path(tmp_path, format_name, fast_path):
    engine = DeidEngine(schema_fast_path=fast_path)
    policy = Policy(require_ner=False, review_below=0.99)
    result, output = transform(
        tmp_path, format_name, engine, "Ana López", header="nombre", policy=policy
    )

    assert output == "[PERSON]"
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert result.issues == ["UNCERTAIN_SOURCE_FINDINGS"]
    assert result.audit["transformations"] == 1


@pytest.mark.parametrize("format_name", FORMATS)
def test_confident_rules_only_output_remains_approved(tmp_path, format_name):
    result, output = transform(
        tmp_path,
        format_name,
        DeidEngine(),
        "persona@example.test",
        policy=Policy.strict(require_ner=False),
    )

    assert output == "[EMAIL]"
    assert result.release_approved
    assert result.issues == []
    assert result.audit["transformations"] == 1


class ResidualNameAdapter(PartialNameAdapter):
    def detect_batch(self, texts):
        findings = super().detect_batch(texts)
        for text, found in zip(texts, findings, strict=True):
            if not found and text.endswith(" López"):
                found.append(Finding("PERSON", len(text) - 5, len(text), 0.9, "test.residual"))
        return findings


@pytest.mark.parametrize("suffix", ["txt", "csv", "json", "jsonl"])
def test_residual_findings_block_even_with_source_review_issues(tmp_path, suffix):
    engine = DeidEngine(nlp=ResidualNameAdapter(0.75, ("window_boundary",)))
    source = tmp_path / f"input.{suffix}"
    output = tmp_path / f"output.{suffix}"
    source.write_text(
        {
            "txt": "Ana López",
            "csv": "notes\nAna López\n",
            "json": json.dumps({"notes": "Ana López"}),
            "jsonl": json.dumps({"notes": "Ana López"}) + "\n",
        }[suffix],
        encoding="utf-8",
    )

    result = engine.deidentify(source, output=output)

    assert result.status == ReleaseStatus.BLOCKED
    assert "RESIDUAL_FINDINGS" in result.issues
    assert "UNRESOLVED_MODEL_WINDOW_BOUNDARY" in result.issues
    assert not result.release_approved
    assert not output.exists()


@pytest.mark.parametrize("format_name", ["csv", "jsonl", "pandas", "polars"])
def test_earlier_batch_uncertainty_is_not_overwritten(tmp_path, format_name):
    engine = DeidEngine(nlp=PartialNameAdapter(0.75, ("window_boundary",)))
    values = ["Ana López", "ordinary"]
    if format_name in {"pandas", "polars"}:
        module = pytest.importorskip(format_name)
        result = engine.deidentify_dataframe(module.DataFrame({"notes": values}), batch_size=1)
        assert result.dataframe["notes"].to_list() == ["[PERSON] López", "ordinary"]
    else:
        source = tmp_path / f"input.{format_name}"
        output = tmp_path / f"output.{format_name}"
        content = (
            "notes\n" + "\n".join(values) + "\n"
            if format_name == "csv"
            else "".join(json.dumps({"notes": value}) + "\n" for value in values)
        )
        source.write_text(content, encoding="utf-8")
        result = engine.deidentify(source, output=output, batch_size=1)
        assert "ordinary" in output.read_text(encoding="utf-8")

    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert result.issues == ["UNRESOLVED_MODEL_WINDOW_BOUNDARY"]
    assert result.audit["transformations"] == 1
