"""Complete CLI lifecycle: persisted identities, explicit review and signed output."""

import json
from dataclasses import asdict

from deidflow.cli import main
from deidflow.review import ReviewDecision


def test_persistent_cli_review_round_trip_and_receipt_binding(tmp_path, capsys):
    key, signing = tmp_path / "encryption.key", tmp_path / "review.key"
    state, source = tmp_path / "initial.df", tmp_path / "input.txt"
    source.write_text("ana@example.test", encoding="utf-8")
    assert main(["keygen", str(key)]) == 0
    assert main(["keygen", str(signing)]) == 0
    assert (
        main(
            [
                "session",
                "create",
                "--pack",
                "general",
                "--state",
                str(state),
                "--key-file",
                str(key),
            ]
        )
        == 0
    )
    first = tmp_path / "first"
    assert (
        main(
            [
                "session",
                "process",
                str(source),
                "--state",
                str(state),
                "--key-file",
                str(key),
                "--output",
                str(first),
            ]
        )
        == 2
    )
    assert "HUMAN_REVIEW_REQUIRED" in json.loads((first / "audit.json").read_text())["issues"]
    candidate = (first / "candidate.txt").read_text()
    assert candidate == "[CORREO_1]"

    plan = tmp_path / "plan.json"
    assert main(["review", "plan", str(source), "--output", str(plan)]) == 0
    decisions = tmp_path / "decisions.json"
    decisions.write_text(
        json.dumps(
            [
                asdict(ReviewDecision.confirm(span["span_id"]))
                for span in json.loads(plan.read_text())["spans"]
            ]
        )
    )
    reviewed = tmp_path / "reviewed"
    assert (
        main(
            [
                "review",
                "apply",
                str(source),
                "--plan",
                str(plan),
                "--decisions",
                str(decisions),
                "--reviewer-id",
                "reviewer-0123456789abcdef",
                "--signing-key-file",
                str(signing),
                "--state",
                str(first / "session.df"),
                "--key-file",
                str(key),
                "--output",
                str(reviewed),
                "--approve",
                "--source-complete",
            ]
        )
        == 0
    )
    assert (reviewed / "candidate.txt").read_text() == candidate
    graph = json.loads((reviewed / "graph.json").read_text())
    assert len(graph["entities"]) == 1 and len(graph["documents"]) == 2
    assert len(graph["occurrences"]) == 2
    assert (
        main(
            [
                "review",
                "verify",
                str(source),
                "--output",
                str(reviewed / "candidate.txt"),
                "--receipt",
                str(reviewed / "receipt.json"),
                "--signing-key-file",
                str(signing),
            ]
        )
        == 0
    )

    restored = tmp_path / "restored.txt"
    assert (
        main(
            [
                "session",
                "restore",
                str(reviewed / "candidate.txt"),
                "--state",
                str(reviewed / "session.df"),
                "--key-file",
                str(key),
                "--output",
                str(restored),
            ]
        )
        == 0
    )
    assert restored.read_text() == source.read_text()
    source.write_text("other@example.test")
    assert (
        main(
            [
                "review",
                "verify",
                str(source),
                "--output",
                str(reviewed / "candidate.txt"),
                "--receipt",
                str(reviewed / "receipt.json"),
                "--signing-key-file",
                str(signing),
            ]
        )
        == 2
    )
    logs = capsys.readouterr()
    assert "ana@example.test" not in logs.out + logs.err
    assert "other@example.test" not in logs.out + logs.err


def test_classic_file_command_accepts_spanish_domain_pack(tmp_path, capsys):
    source, output = tmp_path / "input.txt", tmp_path / "candidate.txt"
    source.write_text("ana@example.test", encoding="utf-8")
    assert main(["deidentify", str(source), "--output", str(output), "--pack", "clinical"]) == 2
    assert "[CORREO_1]" in output.read_text()
    audit = json.loads(capsys.readouterr().out)
    assert audit["status"] == "REVIEW_REQUIRED" and audit["model_sha256"]


def test_persisted_review_requires_both_state_arguments(tmp_path, capsys):
    source, plan, signing = tmp_path / "source.txt", tmp_path / "plan.json", tmp_path / "key"
    source.write_text("ana@example.test")
    assert main(["keygen", str(signing)]) == 0
    assert main(["review", "plan", str(source), "--output", str(plan)]) == 0
    decisions = tmp_path / "decisions.json"
    decisions.write_text("[]")
    target = tmp_path / "must-not-exist"
    assert (
        main(
            [
                "review",
                "apply",
                str(source),
                "--plan",
                str(plan),
                "--decisions",
                str(decisions),
                "--reviewer-id",
                "reviewer-0123456789abcdef",
                "--signing-key-file",
                str(signing),
                "--state",
                str(tmp_path / "unread.df"),
                "--output",
                str(target),
            ]
        )
        == 3
    )
    assert not target.exists()
    assert "unread.df" not in capsys.readouterr().err
