from __future__ import annotations

import csv
import json
import re
import socket

import pytest
from hypothesis import given
from hypothesis import strategies as st

from deidflow import DeidEngine, Finding, Policy, ReleaseStatus, Rule
from deidflow.cli import main
from deidflow.detectors import RegexRecognizer
from deidflow.transformations import token, transform_text


def test_strict_requires_semantic_coverage_even_no_findings():
    result = DeidEngine().deidentify_text("Texto sin coincidencias.")
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues
    assert result.audit["anonymity_proven"] is False


def test_offline_no_network(monkeypatch, tmp_path):
    def fail(*a, **k):
        raise AssertionError("Network access attempted")

    monkeypatch.setattr(socket, "socket", fail)
    engine = DeidEngine()
    source = tmp_path / "in.txt"
    source.write_text("Email: persona@example.test", encoding="utf-8")
    result = engine.deidentify(
        source, output=tmp_path / "out.txt", policy=Policy.strict(require_ner=False)
    )
    assert result.release_approved
    assert "persona@example.test" not in result.output_path.read_text()


def test_windows_multiline_byte_verification(tmp_path):
    source = tmp_path / "in.txt"
    source.write_bytes(b"correo: a@example.test\r\nnext\nend\r\n")
    result = DeidEngine().deidentify(
        source, output=tmp_path / "out.txt", policy=Policy.strict(require_ner=False)
    )
    assert result.release_approved
    assert result.output_path.read_bytes() == b"correo: [EMAIL]\r\nnext\nend\r\n"


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=100))
def test_offsets_transform_preserves_untouched_unicode(prefix):
    text = prefix + " a@example.test fin"
    start = len(prefix) + 1
    output, mapping = transform_text(
        text, [Finding("EMAIL", start, start + 14, 1, "test")], Policy()
    )
    assert output == prefix + " [EMAIL] fin"
    assert mapping[0].source_start == start


def test_overlap_union_has_no_sensitive_tail():
    text = "abcdefghi"
    found = [Finding("PERSON", 0, 5, 0.9, "a"), Finding("EMAIL", 3, 9, 0.95, "b")]
    output, mappings = transform_text(text, found, Policy())
    assert len(mappings) == 1 and mappings[0].source_end == 9
    assert not any(c in output.lower() for c in "fghi") or output == "[EMAIL]"


def test_tokens_scope_key_and_normalization():
    key = b"x" * 32
    a = token("café", "PERSON", key=key, scope="tenant:a")
    assert a == token("cafe\u0301", "PERSON", key=key, scope="tenant:a")
    assert a != token("café", "PERSON", key=key, scope="tenant:b")
    assert a != token("café", "PERSON", key=b"y" * 32, scope="tenant:a")
    with pytest.raises(ValueError):
        token("value", "PERSON", key=b"short", scope="a")


def test_dataset_consistency_and_no_plaintext_repr():
    engine = DeidEngine(key=b"x" * 32, tenant_id="tenant", dataset_id="dataset")
    policy = Policy(default=Rule("pseudonym"), token_scope="dataset", require_ner=False)
    a = engine.deidentify_text("a@example.test", policy=policy)
    b = engine.deidentify_text("a@example.test", policy=policy)
    assert a.output_text == b.output_text
    assert "a@example.test" not in repr(a)
    assert a.release_approved


def test_pseudonym_requires_explicit_secret_and_scope():
    with pytest.raises(ValueError, match="secret"):
        DeidEngine().deidentify_text("a@example.test", policy=Policy(default=Rule("pseudonym")))
    with pytest.raises(ValueError, match="tenant_id"):
        DeidEngine(key=b"x" * 32).deidentify_text("text", policy=Policy(token_scope="tenant"))


@pytest.mark.parametrize(
    "data",
    [
        {"unk": True},
        {"default": {"action": "oops"}},
        {"default": {"extra": 1}},
        {"require_ner": "false"},
        {"entities": {"EMAIL": {"threshold": 2}}},
    ],
)
def test_invalid_policy_rejected(data):
    with pytest.raises(ValueError):
        Policy.from_dict(data)


@pytest.mark.parametrize(
    "action,options,expected",
    [
        ("redact", {}, "██████████"),
        ("suppress", {}, ""),
        ("generalize", {"replacement": "2020"}, "2020"),
        ("date_shift", {"shift_days": 2}, "2024-01-03"),
        ("mask", {}, "******1-01"),
    ],
)
def test_operators(action, options, expected):
    value = "2024-01-01"
    output, _ = transform_text(
        value, [Finding("DATE", 0, 10, 1, "test")], Policy(default=Rule(action, **options))
    )
    assert output == expected


def test_bucket_and_custom_failure_sanitization():
    result, _ = transform_text(
        "42", [Finding("AGE", 0, 2, 1, "test")], Policy(default=Rule("bucket", width=10))
    )
    assert result == "[40,50)"

    def fail(value):
        raise ValueError(value)

    with pytest.raises(ValueError) as error:
        transform_text(
            "secret",
            [Finding("CONFIDENTIAL", 0, 6, 1, "test")],
            Policy(default=Rule("custom", custom="a")),
            custom={"a": fail},
        )
    assert "secret" not in str(error.value)


def test_custom_noop_blocked():
    engine = DeidEngine(custom_transforms={"noop": lambda x: x})
    result = engine.deidentify_text(
        "a@example.test", policy=Policy(default=Rule("custom", custom="noop"), require_ner=False)
    )
    assert result.status == ReleaseStatus.BLOCKED


def test_protected_highrisk_cannot_be_thresholded_out():
    result = DeidEngine().deidentify_text(
        "a@example.test", policy=Policy(default=Rule(threshold=1), require_ner=False)
    )
    assert result.output_text == "[EMAIL]"


def test_stream_csv_all_values_and_equivalent_fast_path(tmp_path):
    source = tmp_path / "input.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["nombre", "email", "amount", "notes"])
        for i in range(260):
            writer.writerow(
                [
                    "Nombre Sintetico",
                    f"persona{i}@example.test",
                    str(i),
                    "a@example.test" if i == 259 else "sin datos",
                ]
            )
    policy = Policy.strict(require_ner=False)
    outputs = []
    for fast in (True, False):
        output = tmp_path / f"out{fast}.csv"
        result = DeidEngine(schema_fast_path=fast).deidentify(
            source, output=output, policy=policy, batch_size=100
        )
        assert result.release_approved and result.records == 260
        outputs.append(output.read_bytes())
        assert b"a@example.test" not in outputs[-1]
    assert outputs[0] == outputs[1]
    found = list(DeidEngine().scan_csv(source, batch_size=50))
    assert any(f.location.row == 259 and f.entity_type == "EMAIL" for f in found)


def test_late_sensitive_cell_after_profile_sample(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("notes\n" + "ordinary\n" * 140 + "late@example.test\n", encoding="utf-8")
    result = DeidEngine().deidentify(
        source, output=tmp_path / "out.csv", policy=Policy.strict(require_ner=False)
    )
    assert result.release_approved
    assert "late@example.test" not in result.output_path.read_text()


@pytest.mark.parametrize("suffix", [".json", ".jsonl"])
def test_json_nested_keys_values_numbers(tmp_path, suffix):
    source = tmp_path / ("input" + suffix)
    source.write_text(
        json.dumps(
            {"nombre": "Nombre Completo", "id_cliente": 1234, "array": ["a@example.test", 4]}
        ),
        encoding="utf-8",
    )
    result = DeidEngine().deidentify(
        source, output=tmp_path / ("out" + suffix), policy=Policy.strict(require_ner=False)
    )
    assert result.release_approved
    value = json.loads(result.output_path.read_text())
    assert value["nombre"] == "[PERSON]" and value["id_cliente"] == "[CUSTOMER_ID]"
    assert value["array"] == ["[EMAIL]", 4]


def test_failure_keeps_no_final_or_temp_artifact(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("a@example.test", encoding="utf-8")
    policy = Policy(default=Rule("custom", custom="noop"), require_ner=False)
    result = DeidEngine(custom_transforms={"noop": lambda x: x}).deidentify(
        source, output=tmp_path / "out.txt", policy=policy
    )
    assert result.status == ReleaseStatus.BLOCKED
    assert not (tmp_path / "out.txt").exists()
    assert not list(tmp_path.glob(".deidflow-*"))


def test_format_unsupported_and_no_overwrite(tmp_path):
    missing_ocr = DeidEngine().deidentify(tmp_path / "file.pdf", output=tmp_path / "out.pdf")
    assert missing_ocr.status == ReleaseStatus.BLOCKED
    assert missing_ocr.issues == ["LOCAL_OCR_REQUIRED"]
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("previous")
    with pytest.raises(FileExistsError):
        DeidEngine().deidentify(a, output=b)
    assert b.read_text() == "previous"


def test_verification_detects_tampering(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("a@example.test", encoding="utf-8")
    result = DeidEngine().verify(source, expected_sha256="0" * 64)
    assert result.issues == ["OUTPUT_DIGEST_MISMATCH"]


def test_parallel_order_and_consistency():
    values = [f"p{i}@example.test" for i in range(12)]
    engine = DeidEngine()
    expected = list(engine.scan_many(values, input_kind="text"))
    actual = list(engine.scan_many(values, input_kind="text", workers=2, batch_size=4))
    assert expected == actual


def test_limits_and_invalid_adapter():
    with pytest.raises(ValueError):
        DeidEngine(max_bytes=5).scan_text("too much")
    with pytest.raises(ValueError):
        DeidEngine(offline=False)

    class Bad:
        def detect_batch(self, texts):
            return []

    with pytest.raises(ValueError, match="batch length"):
        DeidEngine(nlp=Bad()).scan_text("text")


def test_dataframe_dtype_and_location():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"email": ["a@example.test", None], "amount": [1.5, 2.5]})
    result = DeidEngine().deidentify_dataframe(frame, policy=Policy.strict(require_ner=False))
    assert result.release_approved
    assert result.dataframe["amount"].dtype == frame["amount"].dtype
    assert result.dataframe["email"].iloc[0] == "[EMAIL]"
    assert DeidEngine().scan_dataframe(frame)[0].location.column == "email"


def test_polars_and_sensitive_index():
    pl = pytest.importorskip("polars")
    frame = pl.DataFrame({"email": ["a@example.test"], "amount": [2]})
    result = DeidEngine().deidentify_dataframe(frame, policy=Policy.strict(require_ner=False))
    assert result.release_approved and result.dataframe["amount"].dtype == frame["amount"].dtype
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"value": [1]}, index=["identity@example.test"])
    assert (
        DeidEngine().deidentify_dataframe(frame, policy=Policy.strict(require_ner=False)).status
        == ReleaseStatus.REVIEW_REQUIRED
    )


def test_cli_never_prints_plaintext(tmp_path, capsys):
    path = tmp_path / "input.txt"
    path.write_text("a@example.test", encoding="utf-8")
    assert main(["scan", str(path)]) == 0
    assert "a@example.test" not in capsys.readouterr().out


def test_many_allowed_residuals_cannot_hide_late_disallowed(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("notes\n" + "2024-01-01\n" * 150 + "real@example.test\n", encoding="utf-8")
    policy = Policy(
        default=Rule("keep"), entities={"EMAIL": Rule("custom", custom="leak")}, require_ner=False
    )
    engine = DeidEngine(custom_transforms={"leak": lambda x: "another@example.test"})
    result = engine.deidentify(source, output=tmp_path / "out.csv", policy=policy)
    assert result.status == ReleaseStatus.BLOCKED
    assert not (tmp_path / "out.csv").exists()
    assert engine.verify(source, policy=policy).status == ReleaseStatus.BLOCKED


def test_domain_override_applies_in_every_gate(tmp_path):
    recognizer = RegexRecognizer("CONFIDENTIAL", re.compile("secret"), score=0.5, risk="medium")
    engine = DeidEngine(recognizers=[recognizer])
    policy = Policy(
        default=Rule("keep"),
        domains={"finance": {"CONFIDENTIAL": Rule(threshold=0.9)}},
        require_ner=False,
    )
    result = engine.deidentify_text("secret", policy=policy, domain="finance")
    assert result.status == ReleaseStatus.BLOCKED
    path = tmp_path / "input.txt"
    path.write_text("secret")
    assert engine.verify(path, policy=policy, domain="finance").status == ReleaseStatus.BLOCKED


def test_scope_framing_prevents_identifier_collisions():
    p = Policy(token_scope="dataset")
    a = DeidEngine(tenant_id="a:b", dataset_id="c")._scope(p, "doc")
    b = DeidEngine(tenant_id="a", dataset_id="b:c")._scope(p, "doc")
    assert a != b
    p = Policy(token_scope="document")
    assert DeidEngine(tenant_id="a")._scope(p, "doc") != DeidEngine(tenant_id="b")._scope(p, "doc")


@pytest.mark.parametrize("value", ["EMAIL", {"EMAIL": False}, [False], [None], 7])
def test_residual_allowlist_requires_explicit_category_list(value):
    with pytest.raises(ValueError):
        Policy.from_dict({"allow_residual_types": value})
    with pytest.raises(ValueError):
        Policy(allow_residual_types=value)


def test_policy_nested_python_schema_rejected():
    with pytest.raises(ValueError):
        Policy(domains={"finance": {"EMAIL": {"action": "keep"}}})
    with pytest.raises(ValueError):
        Rule("custom", custom=["name"])


def test_multiindex_and_numeric_index_findings_not_approved():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(
        {"amount": [42]}, index=pd.MultiIndex.from_tuples([("private@example.test", "east")])
    )
    engine = DeidEngine()
    assert any(f.entity_type == "EMAIL" for f in engine.scan_dataframe(frame))
    result = engine.deidentify_dataframe(frame, policy=Policy.strict(require_ner=False))
    assert result.status == ReleaseStatus.REVIEW_REQUIRED


def test_bool_dtype_never_casts_placeholder_to_true():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"id_cliente": [True]})
    result = DeidEngine().deidentify_dataframe(frame, policy=Policy.strict(require_ner=False))
    assert result.dataframe.iloc[0, 0] == "[CUSTOMER_ID]"


def test_noop_cannot_pass_residual_exemption():
    policy = Policy(
        default=Rule("custom", custom="noop"), allow_residual_types=("EMAIL",), require_ner=False
    )
    result = DeidEngine(custom_transforms={"noop": lambda x: x}).deidentify_text(
        "a@example.test", policy=policy
    )
    assert result.status == ReleaseStatus.BLOCKED
    assert result.issues == ["INCOMPLETE_TRANSFORMATION"]


def test_jsonl_verification_rejects_hidden_duplicate_key(tmp_path):
    path = tmp_path / "input.jsonl"
    path.write_text('{"key":"a@example.test","key":4}\n')
    with pytest.raises(ValueError, match="Duplicate"):
        DeidEngine().verify(path, policy=Policy.strict(require_ner=False))


def test_adapter_exceptions_cannot_contain_input():
    class Leaky:
        def detect_batch(self, texts):
            raise RuntimeError(texts[0])

    with pytest.raises(RuntimeError) as error:
        DeidEngine(nlp=Leaky()).scan_text("private@example.test")
    assert "private@example.test" not in str(error.value)


def test_short_masks_and_zero_shift():
    output, _ = transform_text(
        "123", [Finding("EMPLOYEE_ID", 0, 3, 1, "test")], Policy(default=Rule("mask"))
    )
    assert output == "***"
    from deidflow.transformations import IncompleteTransformationError

    with pytest.raises(IncompleteTransformationError):
        transform_text(
            "2024-01-01", [Finding("DATE", 0, 10, 1, "test")], Policy(default=Rule("date_shift"))
        )


def test_risk_flags_are_not_probabilities():
    from deidflow.risk import assess

    risk = assess([Finding("AGE", 0, 2, 0.8, "test"), Finding("LOCATION", 3, 5, 0.8, "test")])
    assert risk.quasi_identifier_groups == 1 and risk.anonymity_proven is False


def test_structured_standalone_verify_requires_receipt(tmp_path):
    engine = DeidEngine()
    # A value outside every recognizer still needs a transformation receipt.
    for suffix, content in (
        (".csv", "nombre,amount\nZoila Quintanar,42\n"),
        (".jsonl", '{"nombre":"Zoila Quintanar"}\n'),
        (".json", '{"nombre":"Zoila Quintanar"}'),
    ):
        path = tmp_path / ("input" + suffix)
        path.write_text(content, encoding="utf-8")
        result = engine.verify(path, policy=Policy.strict(require_ner=False))
        assert result.status == ReleaseStatus.REVIEW_REQUIRED
        assert "SCHEMA_TRANSFORMATION_RECEIPT_REQUIRED" in result.issues


def test_structured_standalone_verify_blocks_recognized_given_name(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("nombre,amount\nMaria Perez,42\n", encoding="utf-8")
    result = DeidEngine().verify(path, policy=Policy.strict(require_ner=False))
    assert result.status == ReleaseStatus.BLOCKED
    assert "RESIDUAL_FINDINGS" in result.issues


def test_medical_schema_requires_subject_association():
    pd = pytest.importorskip("pandas")
    engine = DeidEngine()
    without = pd.DataFrame({"diagnóstico": ["diabetes"]})
    assert not any(f.entity_type == "DIAGNOSIS" for f in engine.scan_dataframe(without))
    with_subject = pd.DataFrame({"nombre": ["Maria Perez"], "diagnóstico": ["diabetes"]})
    assert any(f.entity_type == "DIAGNOSIS" for f in engine.scan_dataframe(with_subject))
    result = engine.deidentify_dataframe(with_subject, policy=Policy.strict(require_ner=False))
    assert result.dataframe.iloc[0, 1] == "[DIAGNOSIS]"
    keep = Policy(entities={"DIAGNOSIS": Rule("keep")}, require_ner=False)
    result = engine.deidentify_dataframe(with_subject, policy=keep)
    assert result.dataframe.iloc[0, 1] == "diabetes" and result.dataframe.iloc[0, 0] == "[PERSON]"


def test_jsonl_streaming_over_whole_file_limit(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_text('{"email":"a@example.test"}\n' * 20, encoding="utf-8")
    engine = DeidEngine(max_bytes=64)
    result = engine.deidentify(
        source, output=tmp_path / "out.jsonl", policy=Policy.strict(require_ner=False)
    )
    assert result.release_approved and result.records == 20
