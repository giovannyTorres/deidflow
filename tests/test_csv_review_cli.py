"""CSV CLI publication, exact artifact bindings and private failure behavior."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from deidflow import DeidEngine, Finding, Policy, Rule
from deidflow.cli import main
from deidflow.review import ReviewDecision

REVIEWER = "reviewer-0123456789abcdef"
MODEL = "a" * 64
NAME = "Zelmira Salcedo"


class FictionalAdapter:
    def detect_batch(self, texts):
        return [
            [Finding("PERSON", text.index("Azul"), text.index("Azul") + 4, 0.6, "test.color")]
            if "Azul" in text
            else []
            for text in texts
        ]


@pytest.fixture
def review_files(tmp_path, monkeypatch):
    import deidflow.domains as domains

    policy = Policy(
        name="fictional-csv-review",
        default=Rule("indexed"),
        require_ner=True,
        require_human_review=True,
    )
    pack = SimpleNamespace(
        name="financial",
        engine=lambda: DeidEngine(nlp=FictionalAdapter(), model_digest=MODEL),
        policy=lambda: policy,
    )
    monkeypatch.setattr(domains, "get_domain_pack", lambda _: pack)
    source = tmp_path / "private-input.csv"
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\r\n").writerows(
        [
            ["cabecera privada", "detalle", "importe"],
            [NAME, 'Azul, "dosis"\r\ntexto útil', "125.50"],
            [NAME, "contacto@example.test", "125.50"],
        ]
    )
    source.write_bytes(b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8"))
    signing = tmp_path / "signing.key"
    signing.write_bytes(b"s" * 32)
    signing.chmod(0o600)
    plan = tmp_path / "plan.json"
    decisions = tmp_path / "decisions.json"
    return SimpleNamespace(
        source=source,
        signing=signing,
        plan=plan,
        decisions=decisions,
        pack=pack,
        tmp=tmp_path,
    )


def plan_csv(files):
    from deidflow.csv_review import CSVReviewPlan

    assert (
        main(
            [
                "review",
                "plan",
                str(files.source),
                "--format",
                "csv",
                "--pack",
                "financial",
                "--output",
                str(files.plan),
            ]
        )
        == 0
    )
    plan = CSVReviewPlan.from_json(files.plan.read_text(encoding="utf-8"))
    rows = list(csv.reader(io.StringIO(files.source.read_bytes().decode("utf-8-sig"), newline="")))
    decisions = []
    for cell in plan.cells:
        value = rows[cell.row][cell.column]
        for span in cell.review.spans:
            decision = (
                ReviewDecision.reject(span.span_id, reason="false_positive")
                if value[span.start : span.end] == "Azul"
                else ReviewDecision.confirm(span.span_id)
            )
            decisions.append({"row": cell.row, "column": cell.column, "decision": asdict(decision)})
        if value == NAME:
            assert not cell.review.spans
            decisions.append(
                {
                    "row": cell.row,
                    "column": cell.column,
                    "decision": asdict(ReviewDecision.add(0, len(value), "PERSON")),
                }
            )
    files.decisions.write_text(json.dumps(decisions), encoding="utf-8")
    return plan


def apply_args(files, target, *flags):
    return [
        "review",
        "apply",
        str(files.source),
        "--format",
        "csv",
        "--pack",
        "financial",
        "--plan",
        str(files.plan),
        "--decisions",
        str(files.decisions),
        "--reviewer-id",
        REVIEWER,
        "--signing-key-file",
        str(files.signing),
        "--output",
        str(target),
        *flags,
    ]


def verify_args(files, target, filename="approved.csv"):
    return [
        "review",
        "verify",
        str(files.source),
        "--format",
        "csv",
        "--pack",
        "financial",
        "--output",
        str(target / filename),
        "--receipt",
        str(target / "receipt.json"),
        "--signing-key-file",
        str(files.signing),
    ]


def assert_no_stage(files):
    assert not list(files.tmp.glob(".deidflow-product-*"))


def test_csv_corrected_preview_approved_and_exact_byte_verification(review_files, capsys):
    files = review_files
    plan = plan_csv(files)
    assert (plan.row_count, plan.column_count) == (2, 3)
    preview, approved = files.tmp / "preview", files.tmp / "approved"
    original = files.source.read_bytes()
    assert main(apply_args(files, preview)) == 2
    assert {p.name for p in preview.iterdir()} == {"candidate.csv", "receipt.json", "audit.json"}
    assert main(verify_args(files, preview, "candidate.csv")) == 2
    assert main(apply_args(files, approved, "--approve", "--source-complete")) == 0
    assert {p.name for p in approved.iterdir()} == {"approved.csv", "receipt.json", "audit.json"}
    output = (approved / "approved.csv").read_bytes()
    rows = list(csv.reader(io.StringIO(output.decode("utf-8-sig"), newline="")))
    assert rows == [
        ["cabecera privada", "detalle", "importe"],
        ["[PERSONA_1]", 'Azul, "dosis"\r\ntexto útil', "125.50"],
        ["[PERSONA_1]", "[CORREO_1]", "125.50"],
    ]
    assert files.source.read_bytes() == original
    assert NAME.encode() not in output and b"contacto@example.test" not in output
    assert main(verify_args(files, approved)) == 0
    audit = json.loads((approved / "audit.json").read_text())
    assert audit["serialized_output_verified"] and audit["source_unchanged"]
    private_metadata = (
        files.plan.read_text() + (approved / "receipt.json").read_text() + json.dumps(audit)
    )
    assert all(value not in private_metadata for value in (NAME, "cabecera privada"))
    # Larger CSV receipts keep their separate 16 MiB limit; text keeps 4 MiB.
    receipt_path = approved / "receipt.json"
    receipt_path.write_bytes(b" " * (4 * 1024 * 1024) + receipt_path.read_bytes())
    assert main(verify_args(files, approved)) == 0
    (approved / "approved.csv").write_bytes(output + b"\r\n")
    assert main(verify_args(files, approved)) == 2
    (approved / "approved.csv").write_bytes(output)
    files.source.write_bytes(original.replace(b"\r\n", b"\n"))
    assert main(verify_args(files, approved)) == 2
    logs = capsys.readouterr()
    assert all(
        value not in logs.out + logs.err
        for value in (NAME, "contacto@example.test", "cabecera privada", str(files.source))
    )
    assert_no_stage(files)


@pytest.mark.parametrize("flags", [("--approve",), ("--source-complete",)])
def test_csv_each_human_attestation_remains_explicit(review_files, flags):
    files = review_files
    plan_csv(files)
    target = files.tmp / "candidate"
    assert main(apply_args(files, target, *flags)) == 2
    assert (target / "candidate.csv").is_file()
    assert not (target / "approved.csv").exists()
    assert main(verify_args(files, target, "candidate.csv")) == 2


@pytest.mark.parametrize("gate", ["missing_ner", "residual"])
def test_csv_human_flags_do_not_override_release_gates(review_files, gate):
    files = review_files
    if gate == "missing_ner":
        files.pack.engine = lambda: DeidEngine(model_digest=MODEL)
    else:
        policy = replace(
            files.pack.policy(), entities={"EMAIL": Rule("custom", custom="unsafe_fixture")}
        )
        files.pack.policy = lambda: policy
        files.pack.engine = lambda: DeidEngine(
            nlp=FictionalAdapter(),
            model_digest=MODEL,
            custom_transforms={"unsafe_fixture": lambda _: "residual@example.test"},
        )
    plan_csv(files)
    target = files.tmp / "gated"
    assert main(apply_args(files, target, "--approve", "--source-complete")) == 2
    assert (target / "candidate.csv").is_file() and not (target / "approved.csv").exists()
    audit = json.loads((target / "audit.json").read_text())
    assert audit["status"] == ("BLOCKED" if gate == "residual" else "REVIEW_REQUIRED")
    assert main(verify_args(files, target, "candidate.csv")) == 2


def test_csv_missing_decisions_are_not_inferred(review_files, capsys):
    files = review_files
    plan_csv(files)
    files.decisions.write_text("[]")
    target = files.tmp / "incomplete"
    assert main(apply_args(files, target, "--approve", "--source-complete")) == 3
    assert not target.exists()
    assert NAME not in capsys.readouterr().err
    assert_no_stage(files)


@pytest.mark.parametrize("argument", ["--state", "--key-file"])
def test_csv_rejects_persistent_identity_arguments(review_files, argument, capsys):
    files = review_files
    plan_csv(files)
    target = files.tmp / "not-persisted"
    assert main(apply_args(files, target, argument, str(files.tmp / "secret-session"))) == 3
    assert not target.exists()
    assert "secret-session" not in capsys.readouterr().err


@pytest.mark.parametrize("phase", ["transform", "serialized"])
def test_csv_source_race_aborts_without_publishing(review_files, monkeypatch, phase, capsys):
    from deidflow import csv_review, product_cli

    files = review_files
    plan_csv(files)
    original = files.source.read_bytes()
    if phase == "transform":
        apply = csv_review.apply_csv_review

        def raced_apply(*args, **kwargs):
            reviewed = apply(*args, **kwargs)
            files.source.write_bytes(original + b"\r\n")
            return reviewed

        monkeypatch.setattr(csv_review, "apply_csv_review", raced_apply)
    else:
        write = product_cli._write

        def raced_write(path, raw):
            write(path, raw)
            if path.name == "audit.json":
                files.source.write_bytes(original + b"\r\n")

        monkeypatch.setattr(product_cli, "_write", raced_write)
    target = files.tmp / "raced"
    assert main(apply_args(files, target, "--approve", "--source-complete")) == 3
    assert not target.exists()
    assert_no_stage(files)
    assert str(files.source) not in capsys.readouterr().err


def test_csv_serialized_output_tampering_aborts_before_publication(review_files, monkeypatch):
    import deidflow.product_cli as product_cli

    files = review_files
    plan_csv(files)
    write = product_cli._write

    def tampered_write(path, raw):
        write(path, raw + b"\r\n" if path.name == "approved.csv" else raw)

    monkeypatch.setattr(product_cli, "_write", tampered_write)
    target = files.tmp / "tampered"
    assert main(apply_args(files, target, "--approve", "--source-complete")) == 3
    assert not target.exists()
    assert_no_stage(files)


def test_csv_publication_failure_is_private_and_cleans_stage(review_files, monkeypatch, capsys):
    import deidflow.rag as rag

    files = review_files
    plan_csv(files)

    def fail_publish(stage, target):
        raise OSError(f"private path: {files.source}; {NAME}")

    monkeypatch.setattr(rag, "_publish", fail_publish)
    target = files.tmp / "publication-failed"
    assert main(apply_args(files, target, "--approve", "--source-complete")) == 3
    assert not target.exists()
    assert_no_stage(files)
    logs = capsys.readouterr()
    assert NAME not in logs.out + logs.err and str(files.source) not in logs.out + logs.err


def test_csv_output_never_overwrites_existing_files(review_files):
    files = review_files
    plan_csv(files)
    target = files.tmp / "existing"
    target.mkdir()
    retained = target / "user-file"
    retained.write_bytes(b"keep")
    assert main(apply_args(files, target, "--approve", "--source-complete")) == 3
    assert retained.read_bytes() == b"keep" and list(target.iterdir()) == [retained]
    assert main(apply_args(files, files.source, "--approve", "--source-complete")) == 3
    assert_no_stage(files)


def test_csv_verification_rejects_tampered_or_malformed_receipts(review_files):
    files = review_files
    plan_csv(files)
    target = files.tmp / "approved"
    assert main(apply_args(files, target, "--approve", "--source-complete")) == 0
    receipt = target / "receipt.json"
    data = json.loads(receipt.read_text())
    data["signature"] = "0" * 64
    receipt.write_text(json.dumps(data))
    assert main(verify_args(files, target)) == 2
    receipt.write_text('{"signature": 1, "signature": 2}')
    assert main(verify_args(files, target)) == 2


def test_csv_verification_rejects_same_source_inode(review_files):
    files = review_files
    alias = files.tmp / "source-alias.csv"
    alias.hardlink_to(files.source)
    assert main(verify_args(files, files.tmp, alias.name)) == 3


def test_default_text_review_remains_compatible(review_files):
    from deidflow.review import ReviewPlan

    files = review_files
    files.source.write_text("contacto@example.test", encoding="utf-8")
    assert main(["review", "plan", str(files.source), "--output", str(files.plan)]) == 0
    plan = ReviewPlan.from_json(files.plan.read_text())
    files.decisions.write_text(
        json.dumps([asdict(ReviewDecision.confirm(span.span_id)) for span in plan.spans])
    )
    target = files.tmp / "text-review"
    args = apply_args(files, target, "--approve", "--source-complete")
    del args[args.index("--format") : args.index("--format") + 2]
    assert main(args) == 0
    assert (target / "candidate.txt").read_text() == "[CORREO_1]"
    args = verify_args(files, target, "candidate.txt")
    del args[args.index("--format") : args.index("--format") + 2]
    assert main(args) == 0
