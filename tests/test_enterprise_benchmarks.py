"""Reproducibility and acquisition guards for public/synthetic measurements."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from urllib.error import HTTPError

import pytest


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


enterprise = load_script("benchmark_enterprise_workloads")
public = load_script("benchmark_public_documents")


def test_span_gold_and_long_window_fixture():
    text, spans = enterprise.long_spanish_text(7)
    assert len(text) > 50000
    assert len(spans) == 7
    assert all(text[start:end].endswith("@example.org") for start, end in spans)
    assert len(set(text[start:end] for start, end in spans)) == 7
    assert (text, spans) == enterprise.long_spanish_text(7)


def test_wrong_baseline_import_cannot_produce_comparison(tmp_path):
    with pytest.raises(RuntimeError, match="Requested baseline implementation was not imported"):
        enterprise.worker({"source_root": str(tmp_path)})


def test_source_snapshot_remains_fixed_during_later_edits(tmp_path):
    root = tmp_path / "source"
    package = root / "src/deidflow"
    package.mkdir(parents=True)
    implementation = package / "engine.py"
    implementation.write_text("revision = 1\n", encoding="utf-8")
    snapshot = enterprise.snapshot_source(root, tmp_path / "run")
    pinned = enterprise.source_tree_digest(snapshot)
    implementation.write_text("revision = 2\n", encoding="utf-8")
    assert enterprise.source_tree_digest(snapshot) == pinned
    assert enterprise.source_tree_digest(root) != pinned


def test_csv_independent_verifier_checks_every_cell_and_preserved_amount(tmp_path):
    fixture = enterprise.fixtures()
    source = tmp_path / "synthetic.csv"
    fixture.generate_csv(source, 23)
    failed = fixture._verify_csv(source, 23)
    assert failed["gold_sensitive_cells_checked"] == 69
    assert failed["residual_gold_cells"] == 69
    assert not failed["passed"]
    import csv

    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for column in ("email", "clabe", "customer_id"):
            row[column] = "[REDACTED]"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    assert fixture._verify_csv(source, 23)["passed"]
    rows[0]["amount"] = "999999"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    assert fixture._verify_csv(source, 23)["unchanged_amount_errors"] == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://www.scjn.gob.mx/a",
        "https://evil.example/a",
        "https://www.scjn.gob.mx.evil.example/a",
        "https://user:secret@www.scjn.gob.mx/a",
        "https://www.scjn.gob.mx:999/a",
        "https://www.scjn.gob.mx:wrong/a",
    ],
)
def test_unapproved_download_and_redirect_urls_rejected(url):
    assert not public.valid_url(url)


class Response(io.BytesIO):
    def __init__(self, data, url, headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers or {}
        self.status = 200

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error

    def open(self, request, timeout):
        assert timeout == 45
        if self.error:
            raise self.error
        return self.response


def source():
    return {
        "id": "scjn-ar118-2025",
        "url": public.SOURCE_URLS["scjn-ar118-2025"],
        "license_status": "restricted_or_uncertain",
    }


def test_registry_does_not_allow_arbitrary_url_even_on_approved_host(tmp_path):
    item = source()
    item["url"] = "https://www.scjn.gob.mx/arbitrary.pdf"
    with pytest.raises(ValueError):
        public.acquire(item, tmp_path)


def test_acquire_pdf_hash_and_no_raw_source_in_report(tmp_path):
    item = source()
    data = b"%PDF-1.7\nPUBLIC_FIXTURE_SENTINEL"
    result = public.acquire(item, tmp_path, opener=Opener(Response(data, item["url"])))
    assert result["acquisition_status"] == "available"
    assert result["bytes"] == len(data)
    assert len(result["sha256"]) == 64
    assert "PUBLIC_FIXTURE_SENTINEL" not in str(result)
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.parametrize(
    "data,headers",
    [(b"<html>denied</html>", {}), (b"%PDF-1.7", {"Content-Length": str(public.MAX_BYTES + 1)})],
)
def test_non_pdf_and_excess_size_fail_without_partial(tmp_path, data, headers):
    item = source()
    result = public.acquire(item, tmp_path, opener=Opener(Response(data, item["url"], headers)))
    assert result["acquisition_status"] == "unavailable"
    assert not list(tmp_path.iterdir())


def test_http403_recorded_without_retry_or_bypass(tmp_path):
    item = source()
    error = HTTPError(item["url"], 403, "Forbidden", {}, None)
    result = public.acquire(item, tmp_path, opener=Opener(error=error))
    assert result["http_status"] == 403
    assert result["reason"] == "HTTP_ACCESS_FAILED"
    assert not list(tmp_path.iterdir())


def test_failed_acquisition_preserves_preexisting_file(tmp_path):
    item = source()
    existing = tmp_path / (item["id"] + ".partial")
    existing.write_bytes(b"USER_EXISTING")
    result = public.acquire(item, tmp_path, opener=Opener(Response(b"%PDF-1.7", item["url"])))
    assert result["acquisition_status"] == "unavailable"
    assert existing.read_bytes() == b"USER_EXISTING"


def test_streamed_response_is_bounded_without_content_length(tmp_path, monkeypatch):
    monkeypatch.setattr(public, "MAX_BYTES", 8)
    item = source()
    result = public.acquire(
        item, tmp_path, opener=Opener(Response(b"%PDF-1.7\nEXCESS", item["url"]))
    )
    assert result["reason"] == "DOWNLOAD_BYTE_LIMIT_EXCEEDED"
    assert not list(tmp_path.iterdir())


def test_existing_download_target_is_never_replaced(tmp_path):
    item = source()
    existing = tmp_path / (item["id"] + ".source.pdf")
    existing.write_bytes(b"USER_EXISTING")
    result = public.acquire(item, tmp_path, opener=Opener(Response(b"%PDF-1.7", item["url"])))
    assert result["acquisition_status"] == "unavailable"
    assert existing.read_bytes() == b"USER_EXISTING"
    assert not list(tmp_path.glob("*.partial"))


def test_arbitrary_network_redirect_is_not_followed():
    from urllib.error import URLError
    from urllib.request import Request

    with pytest.raises(URLError):
        public.GovernmentRedirects().redirect_request(
            Request(source()["url"]), None, 302, "Found", {}, "https://evil.example/sensitive"
        )
