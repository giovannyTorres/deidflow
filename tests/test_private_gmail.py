from __future__ import annotations

import base64
import json
import socket
from pathlib import Path

import pytest

from deidflow import DeidEngine
from deidflow.private.cli import main
from deidflow.private.gmail import (
    Attachment,
    GoogleReadOnlyTransport,
    PrivateConfig,
    attachment_bytes,
    candidate,
    connect,
    iter_parts,
    metadata_fields,
)
from deidflow.private.reports import OperationalMetrics, validate_report
from deidflow.private.review import review_server
from deidflow.private.runner import PersonalApprovals, benchmark, discovery
from deidflow.private.security import (
    PrivateError,
    cleanup_owned,
    private_path,
    require_external_terminal,
    temporary_workspace,
)

CANARY = "SYNTHETIC_PRIVATE_CANARY"


def config(tmp_path: Path, **options):
    defaults = dict(
        account="fictional.owner@gmail.com",
        private_root=str(tmp_path / "private"),
        token_file=str(tmp_path / "private" / "token.json"),
        personal_senders=("fictional.friend@example.org",),
        max_attachments=100,
    )
    return PrivateConfig(**(defaults | options))


class SyntheticGmail:
    synthetic_only = True

    def __init__(self, count=20, *, corporate=False, duplicate=False):
        self.count, self.corporate, self.duplicate = count, corporate, duplicate
        self.calls = []

    def data(self, i):
        return (CANARY + f"{0 if self.duplicate else i}@example.test").encode()

    def get(self, path, *, params=None, max_bytes=1_000_000):
        self.calls.append((path, params))
        if path == "profile":
            return {"emailAddress": "fictional.owner@gmail.com"}
        if path == "messages":
            offset = 10 if params.get("pageToken") == "next" else 0
            end = min(offset + 10, self.count)
            result = {"messages": [{"id": "m" + str(i)} for i in range(offset, end)]}
            if end < self.count:
                result["nextPageToken"] = "next"
            return result
        identifier = int(path.split("/")[1][1:])
        if "/attachments/" in path:
            data = self.data(identifier)
            return {"size": len(data), "data": base64.urlsafe_b64encode(data).decode().rstrip("=")}
        if params["format"] == "metadata":
            return {
                "id": "m" + str(identifier),
                "payload": {
                    "headers": [
                        {"name": "From", "value": "fictional.friend@example.org"},
                        {
                            "name": "To",
                            "value": "someone@bbva.com"
                            if self.corporate
                            else "fictional.owner@gmail.com",
                        },
                        {"name": "Subject", "value": CANARY + " personal family document"},
                    ]
                },
            }
        return {
            "id": "m" + str(identifier),
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "filename": CANARY + str(identifier) + ".txt",
                        "mimeType": "text/plain",
                        "body": {
                            "size": len(self.data(identifier)),
                            "attachmentId": "a" + str(identifier),
                        },
                    }
                ],
            },
        }


def approve_all(cfg, transport):
    store = PersonalApprovals(cfg)
    for i in range(transport.count):
        store.decide(
            Attachment("m" + str(i), "a" + str(i), ".txt", "txt", len(transport.data(i))),
            "PERSONAL",
            attest_personal=True,
        )


def test_external_boundary_precedes_any_config_or_auth(monkeypatch, capsys):
    monkeypatch.setenv("CODEX_THREAD_ID", "synthetic-agent")
    monkeypatch.setattr(
        PrivateConfig, "load", lambda _: (_ for _ in ()).throw(AssertionError("must not read"))
    )
    assert main(["--inventory", "--config", CANARY, "--external-terminal-ack"]) == 3
    value = capsys.readouterr()
    assert CANARY not in value.out + value.err
    assert "EXTERNAL_TERMINAL_REQUIRED" in value.err


def test_bad_cli_does_not_echo_private_values(capsys):
    assert main(["--inventory", "--config", CANARY, "--unknown", CANARY]) == 3
    assert CANARY not in "".join(capsys.readouterr())


@pytest.mark.parametrize(
    "values",
    [
        ({}, False),
        ({"CODEX_THREAD_ID": "a"}, True),
        ({"CODEX_SESSION_ID": "a"}, True),
        ({"CODEX_RUN_ID": "a"}, True),
    ],
)
def test_external_terminal_ack_is_not_bypassed(values):
    environment, ack = values
    with pytest.raises(PrivateError, match="EXTERNAL_TERMINAL_REQUIRED"):
        require_external_terminal(ack, environ=environment)


def test_external_terminal_clean_environment_is_admitted():
    require_external_terminal(True, environ={})


@pytest.mark.parametrize(
    "options",
    [
        {"account": "someone@bbva.com"},
        {"personal_senders": ()},
        {"max_messages": False},
        {"max_attachment_bytes": 2**32},
        {"allowed_extensions": (".exe",)},
        {"after": "bad-date"},
    ],
)
def test_config_is_strict_and_corporate_account_rejected(tmp_path, options):
    with pytest.raises(PrivateError):
        config(tmp_path, **options)


def test_config_unknown_keys_and_strings_never_appear_in_errors(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"unknown": CANARY}))
    with pytest.raises(PrivateError) as error:
        PrivateConfig.load(p)
    assert CANARY not in str(error.value)


def test_codex_and_repository_paths_are_rejected(tmp_path):
    for directory in ("Codex", ".codex", ".CODEX"):
        with pytest.raises(PrivateError):
            private_path(tmp_path / directory / "private")
    root = tmp_path / "repository"
    (root / ".git").mkdir(parents=True)
    with pytest.raises(PrivateError):
        private_path(root / "private")


def test_no_real_connection_without_external_ack(tmp_path):
    with pytest.raises(PrivateError, match="EXTERNAL_TERMINAL_REQUIRED"):
        connect(config(tmp_path))


def test_discovery_all_mail_pagination_and_no_bodies(tmp_path):
    transport = SyntheticGmail()
    metrics = OperationalMetrics()
    rows = list(discovery(config(tmp_path), transport, metrics))
    assert len(rows) == 20 and metrics.counts["candidate_attachments"] == 20
    listing = [p for path, p in transport.calls if path == "messages"]
    assert len(listing) == 2 and "in:inbox" not in listing[0]["q"]
    assert all("attachments/" not in path for path, _ in transport.calls)
    assert "data" not in metadata_fields() and "snippet" not in metadata_fields()
    assert any(p.get("format") == "metadata" for _, p in transport.calls if p)


def test_uncertain_or_work_message_never_fetches_attachment_tree(tmp_path):
    transport = SyntheticGmail(count=5, corporate=True)
    assert not list(discovery(config(tmp_path), transport, OperationalMetrics()))
    assert not any(p and p.get("format") == "full" for _, p in transport.calls)


def test_wrong_account_profile_blocks_before_any_message_read(tmp_path):
    class WrongAccount(SyntheticGmail):
        def get(self, path, **kwargs):
            if path == "profile":
                self.calls.append((path, kwargs))
                return {"emailAddress": CANARY + "@bbva.com"}
            raise AssertionError("No message operation should occur")

    transport = WrongAccount()
    with pytest.raises(PrivateError, match="PERSONAL_ACCOUNT_REQUIRED") as error:
        list(discovery(config(tmp_path), transport, OperationalMetrics()))
    assert CANARY not in str(error.value)
    assert [p for p, _ in transport.calls] == ["profile"]


def test_sender_allowlist_does_not_approve_forwarded_attachment(tmp_path):
    cfg, transport = config(tmp_path), SyntheticGmail(count=2)
    report = benchmark(cfg, transport, DeidEngine(), run=True, synthetic_test=True)
    assert report["state"] == "INSUFFICIENT_COHORT"
    assert not any("/attachments/" in path for path, _ in transport.calls)


def test_private_end_to_end_synthetic_canaries_are_not_emitted(tmp_path, monkeypatch, capsys):
    transport, cfg = SyntheticGmail(), config(tmp_path)
    approve_all(cfg, transport)
    monkeypatch.setattr(
        socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network"))
    )
    report = benchmark(cfg, transport, DeidEngine(), run=True, synthetic_test=True)
    assert validate_report(report) == report
    assert report["counts"]["processed_documents"] == 20
    assert report["documents_by_broad_category"]["personal"] == 20
    assert CANARY not in json.dumps(report)
    assert CANARY not in "".join(capsys.readouterr())
    root = Path(cfg.private_root)
    assert not list(root.glob(".deidflow-session-*"))
    assert not any(
        CANARY in p.read_bytes().decode("utf-8", errors="ignore")
        for p in root.rglob("*")
        if p.is_file()
    )


def test_private_adapter_errors_and_debug_output_cannot_escape(tmp_path, capsys):
    import logging

    class BrokenEngine:
        def read(self, source):
            print(CANARY)
            logging.critical(CANARY)
            raise RuntimeError(CANARY)

    cfg, transport = config(tmp_path), SyntheticGmail(count=10)
    approve_all(cfg, transport)
    result = benchmark(cfg, transport, BrokenEngine(), run=True, synthetic_test=True)
    assert result["counts"]["processing_failures"] == 10
    assert CANARY not in json.dumps(result)
    assert CANARY not in "".join(capsys.readouterr())


def test_inventory_never_downloads_even_approved(tmp_path):
    transport, cfg = SyntheticGmail(), config(tmp_path)
    approve_all(cfg, transport)
    result = benchmark(cfg, transport, DeidEngine(), synthetic_test=True)
    assert result["mode"] == "INVENTORY"
    assert not any("/attachments/" in path for path, _ in transport.calls)
    assert result["measurements"]["estimated_processing_seconds"] is None


def test_content_dedup_is_bounded_and_aggregate(tmp_path):
    transport, cfg = SyntheticGmail(count=10, duplicate=True), config(tmp_path)
    approve_all(cfg, transport)
    result = benchmark(cfg, transport, DeidEngine(), run=True, synthetic_test=True)
    assert result["state"] == "INSUFFICIENT_COHORT"  # Ten copies cannot qualify one original.
    assert result["counts"]["content_duplicates"] is None
    assert result["counts"]["processed_documents"] is None
    assert len([p for p, _ in transport.calls if "/attachments/" in p]) == 10


def test_duplicate_downloads_still_consume_the_total_byte_budget(tmp_path):
    transport = SyntheticGmail(count=10, duplicate=True)
    cfg = config(tmp_path, max_total_bytes=len(transport.data(0)) * 2)
    approve_all(cfg, transport)
    result = benchmark(cfg, transport, DeidEngine(), run=True, synthetic_test=True)
    assert result["truncated"] is True
    assert len([p for p, _ in transport.calls if "/attachments/" in p]) == 2


def test_small_cohort_all_record_measurements_suppressed():
    metrics = OperationalMetrics()
    metrics.counts["candidate_attachments"] = 1
    metrics.formats["pdf"] = 1
    metrics.categories["health"] = 1
    result = metrics.emit(mode="INVENTORY")
    assert result["cohort_band"] == "LT10"
    for key in (
        "counts",
        "measurements",
        "by_format",
        "documents_by_broad_category",
        "size_distribution",
    ):
        assert set(result[key].values()) == {None}


@pytest.mark.parametrize("rare_count", [1, 4, 6, 9])
def test_rates_cannot_reconstruct_suppressed_small_cells_or_complements(rare_count):
    metrics = OperationalMetrics()
    metrics.unique_content_documents = 10
    metrics.counts.update(
        candidate_attachments=10,
        processed_documents=10,
        processing_failures=rare_count,
        review_required_documents=rare_count,
        verification_failed_documents=rare_count,
        unsupported_attachments=rare_count,
    )
    report = metrics.emit(mode="RUN")
    for key in (
        "processing_success_rate",
        "review_required_rate",
        "verification_failure_rate",
        "unsupported_rate",
    ):
        assert report["measurements"][key] is None


@pytest.mark.parametrize("count, expected", [(0, 0.0), (5, 0.5), (10, 1.0)])
def test_rates_allow_zero_balanced_cells_and_complete_cohorts(count, expected):
    metrics = OperationalMetrics()
    metrics.unique_content_documents = 10
    metrics.counts.update(
        candidate_attachments=10, processed_documents=10, unsupported_attachments=count
    )
    assert metrics.emit(mode="RUN")["measurements"]["unsupported_rate"] == expected


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update({"filename": CANARY}),
        lambda r: r["counts"].update({"source": CANARY}),
        lambda r: r["measurements"].update({"latency_p50_seconds": CANARY}),
        lambda r: r.update({"accuracy": CANARY}),
        lambda r: r["counts"].update({"messages_examined": True}),
    ],
)
def test_report_allowlist_rejects_canaries_and_wrong_types(mutate):
    report = OperationalMetrics().emit(mode="INVENTORY")
    mutate(report)
    with pytest.raises(PrivateError, match="PRIVATE_REPORT_INVALID") as error:
        validate_report(report)
    assert CANARY not in str(error.value)


def test_attachment_metadata_size_mime_and_body_guards(tmp_path):
    cfg = config(tmp_path)
    part = {
        "filename": "../../" + CANARY + ".pdf",
        "mimeType": "image/png",
        "body": {"size": 4, "attachmentId": "ok"},
    }
    assert candidate(part, "m1", cfg) == (None, "unsupported_attachments")
    with pytest.raises(PrivateError):
        list(iter_parts({"body": {"data": CANARY}}))
    with pytest.raises(PrivateError):
        list(iter_parts({"parts": [{}]}, depth=8))


def test_attachment_decoding_rejects_size_mismatch(tmp_path):
    cfg = config(tmp_path)
    item = Attachment("m1", "a1", ".txt", "txt", 2)
    with pytest.raises(PrivateError):
        attachment_bytes(SyntheticGmail(), item, cfg)


def test_approvals_are_opaque_account_scoped_and_require_human_attestation(tmp_path):
    cfg = config(tmp_path)
    store = PersonalApprovals(cfg)
    item = Attachment("m1", "a1", ".txt", "txt", 42)
    with pytest.raises(PrivateError):
        store.decide(item, "PERSONAL")
    store.decide(item, "PERSONAL", attest_personal=True)
    assert store.approved(item)
    assert CANARY not in store.path.read_text()
    other = PersonalApprovals(config(tmp_path, account="other.fictional@gmail.com"))
    assert not other.approved(item)


def test_local_metadata_review_requires_each_personal_attestation(tmp_path, capsys):
    cfg, transport = config(tmp_path), SyntheticGmail(count=2)
    server = review_server(cfg, transport)
    try:
        response = server.application("GET", "/api/catalog", None)
        catalog = json.loads(response[1])
        assert len(catalog["entries"]) == 2
        assert CANARY in catalog["entries"][0]["filename"]
        identity = catalog["entries"][0]["id"]
        request = {"id": identity, "decision": "PERSONAL", "attest_personal": False}
        with pytest.raises(PrivateError, match="CONSENT"):
            server.application("POST", "/api/approve", request)
        server.application("POST", "/api/approve", request | {"attest_personal": True})
        decisions = PersonalApprovals(cfg).decisions
        assert decisions == {identity: "PERSONAL"}
        assert CANARY not in PersonalApprovals(cfg).path.read_text()
        assert not any("/attachments/" in path for path, _ in transport.calls)
        assert CANARY not in "".join(capsys.readouterr())
    finally:
        server.server_close()


def test_cleanup_only_its_owned_child_and_preserves_persistent_files(tmp_path):
    persistent = tmp_path / "persistent.txt"
    persistent.write_text(CANARY)
    root = tmp_path / "private"
    with temporary_workspace(root) as workspace:
        (workspace / "owned.txt").write_text(CANARY)
    assert not workspace.exists() and persistent.read_text() == CANARY
    with pytest.raises(PrivateError):
        cleanup_owned(root, root)


def test_gmail_transport_rejects_mutating_or_external_resource_paths():
    transport = object.__new__(GoogleReadOnlyTransport)
    for path in (
        "messages/m1/trash",
        "drafts",
        "https://example.test",
        "../profile",
        "messages/m1/modify",
    ):
        with pytest.raises(PrivateError):
            transport.get(path)
