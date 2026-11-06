"""Opt-in LLM policy preserves current gates across structured output paths."""

import json

import pytest

from deidflow import DeidEngine, Finding, Policy, ReleaseStatus, Rule
from deidflow.transformations import transform_text


@pytest.mark.parametrize("format_name", ["csv", "tsv", "json", "jsonl", "pandas", "polars"])
def test_indexed_output_keeps_scope_and_does_not_skip_requested_review(tmp_path, format_name):
    values = ["ana@example.test", "luis@example.test", "ana@example.test"]
    policy = Policy.llm(require_ner=False)
    engine = DeidEngine()
    if format_name in {"pandas", "polars"}:
        module = pytest.importorskip(format_name)
        result = engine.deidentify_dataframe(
            module.DataFrame({"email": values}), policy=policy, batch_size=1
        )
        serialized = result.dataframe["email"].to_list()
    else:
        source, output = tmp_path / f"in.{format_name}", tmp_path / f"out.{format_name}"
        if format_name in {"csv", "tsv"}:
            source.write_text("email\n" + "\n".join(values) + "\n")
        elif format_name == "json":
            source.write_text(json.dumps({"email": values}))
        else:
            source.write_text("".join(json.dumps({"email": value}) + "\n" for value in values))
        result = engine.deidentify(source, output=output, policy=policy, batch_size=1)
        content = output.read_text()
        if format_name in {"csv", "tsv"}:
            serialized = content.splitlines()[1:]
        elif format_name == "json":
            serialized = json.loads(content)["email"]
        else:
            serialized = [json.loads(line)["email"] for line in content.splitlines()]
    assert serialized == ["[CORREO_1]", "[CORREO_2]", "[CORREO_1]"]
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "INDEPENDENT_CHECK_REQUIRES_REVIEW" in result.issues
    assert not result.release_approved
    assert result.audit["transformations"] == 3


def test_standalone_verify_cannot_ignore_requested_independent_check(tmp_path):
    policy = Policy(require_ner=False, independent_check="proper_nouns")
    for suffix, text in (
        ("txt", "ordinary"),
        ("csv", "notes\nordinary\n"),
        ("json", '{"notes": "ordinary"}'),
    ):
        path = tmp_path / f"candidate.{suffix}"
        path.write_text(text)
        result = DeidEngine().verify(path, policy=policy)
        assert result.status == ReleaseStatus.REVIEW_REQUIRED
        assert "INDEPENDENT_CHECK_REQUIRES_REVIEW" in result.issues


class TokenDetector:
    def detect_batch(self, texts):
        return [
            [Finding("PERSON", 0, len(text), 0.9, "test")] if text.startswith("[CORREO_") else []
            for text in texts
        ]


def test_indexed_txt_reread_exempts_only_minted_tokens(tmp_path):
    source, output = tmp_path / "input.txt", tmp_path / "output.txt"
    source.write_text("ana@example.test")
    policy = Policy(default=Rule("indexed"))
    result = DeidEngine(nlp=TokenDetector()).deidentify(source, output=output, policy=policy)
    assert result.release_approved
    assert output.read_text() == "[CORREO_1]"
    # Standalone verification has no evidence that this is a generated token.
    assert (
        DeidEngine(nlp=TokenDetector()).verify(output, policy=policy).status
        == ReleaseStatus.BLOCKED
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2024-02-28", "2024-02-29"),
        ("28/02/2024", "29/02/2024"),
        ("31.12.2024", "01.01.2025"),
        ("31-12-2024", "01-01-2025"),
        ("30 de abril de 2024", "1 de mayo de 2024"),
        ("30 de Septiembre del 2024", "1 de Octubre del 2024"),
    ],
)
def test_spanish_date_shift_preserves_supported_format(value, expected):
    result, _ = transform_text(
        value,
        [Finding("DATE", 0, len(value), 1.0, "test")],
        Policy(default=Rule("date_shift", shift_days=1)),
    )
    assert result == expected


@pytest.mark.parametrize(
    "value",
    ["29/02/2023", "01/01/24", "12/31/2024", "ayer", "12 de primavera de 2024", "9999-12-31"],
)
def test_date_shift_rejects_invalid_ambiguous_or_overflow_without_echo(value):
    with pytest.raises(ValueError, match="ISO or Spanish") as error:
        transform_text(
            value,
            [Finding("DATE", 0, len(value), 1.0, "test")],
            Policy(default=Rule("date_shift", shift_days=1)),
        )
    assert value not in str(error.value)


def test_untransformed_csv_headers_cannot_collide_with_minted_tokens(tmp_path):
    source, output = tmp_path / "in.csv", tmp_path / "out.csv"
    source.write_text("[CORREO_1]\nana@example.test\n")
    result = DeidEngine().deidentify(
        source, output=output, policy=Policy(default=Rule("indexed"), require_ner=False)
    )
    assert output.read_text().splitlines() == ["[CORREO_1]", "[CORREO_2]"]
    assert result.audit["transformations"] == 1


def test_untransformed_dataframe_index_cannot_collide_with_minted_tokens():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"email": ["ana@example.test"]}, index=["[CORREO_1]"])
    result = DeidEngine().deidentify_dataframe(
        frame, policy=Policy(default=Rule("indexed"), require_ner=False)
    )
    assert result.dataframe["email"].to_list() == ["[CORREO_2]"]
