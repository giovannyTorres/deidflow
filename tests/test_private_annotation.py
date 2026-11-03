from __future__ import annotations

import copy
import http.client
import json
import shutil
import subprocess
import threading

import pytest

from deidflow import DeidEngine
from deidflow.private.annotation import _OFFSET_SCRIPT, AnnotationStore, annotation_server, main
from deidflow.private.security import PrivateError

CANARY = "SYNTHETIC_PRIVATE_CANARY"


def store(tmp_path, *, allow=False, text=None):
    source = tmp_path / "samples"
    source.mkdir(exist_ok=True)
    (source / "original.txt").write_text(
        text or "Nombre: María Ejemplo\nCorreo: " + CANARY + "@example.test",
        encoding="utf-8",
        newline="\n",
    )
    return AnnotationStore(
        source, tmp_path / "private", DeidEngine(), consent_display=True, allow_store_excerpts=allow
    )


def payload(app, **changes):
    identity = app.catalog()[0]["id"]
    description = app.describe(identity)
    text = description["fragments"][0]["text"]
    start = text.index(CANARY)
    record = {
        "kind": "span",
        "entity_type": "EMAIL",
        "status": "MISSED",
        "fragment_id": "0",
        "start": start,
        "end": start + len(CANARY),
        "page": None,
        "bbox": None,
        "group_id": "group1",
        "corrected_text": None,
    }
    record.update(changes)
    return {
        "document_id": identity,
        "source_sha256": description["source_sha256"],
        "store_excerpts": False,
        "annotations": [record],
    }


def test_original_display_requires_explicit_consent(tmp_path):
    with pytest.raises(PrivateError, match="CONSENT"):
        AnnotationStore(tmp_path, tmp_path / "private", DeidEngine())


def test_default_annotation_storage_has_no_original_excerpt(tmp_path):
    app = store(tmp_path)
    request = payload(app)
    assert app.save(request) == 1
    saved = (app.records / (request["document_id"] + ".json")).read_text()
    assert CANARY not in saved
    assert app.load(request["document_id"])[0]["status"] == "MISSED"
    assert "filename" not in json.dumps(app.catalog())


def test_storing_original_excerpt_needs_two_explicit_consents(tmp_path):
    app = store(tmp_path)
    request = payload(app)
    request["store_excerpts"] = True
    with pytest.raises(PrivateError, match="CONSENT"):
        app.save(request)
    allowed = store(tmp_path, allow=True)
    request = payload(allowed)
    request["store_excerpts"] = True
    assert allowed.save(request) == 1
    saved = (allowed.records / (request["document_id"] + ".json")).read_text()
    assert CANARY in saved


def test_ocr_correction_is_private_excerpt_not_implicit_training(tmp_path):
    app = store(tmp_path)
    request = payload(app, status="OCR_ERROR", corrected_text=CANARY + " corrected")
    with pytest.raises(PrivateError, match="CONSENT"):
        app.save(request)


@pytest.mark.parametrize(
    "changes",
    [
        {"start": True},
        {"end": 10**9},
        {"entity_type": "<script>"},
        {"status": "APPROVED"},
        {"kind": "upload"},
        {"kind": [CANARY]},
        {"status": {"private": CANARY}},
        {"page": 1},
        {"bbox": [0, 0, 1, 1]},
        {"unknown": CANARY},
    ],
)
def test_annotation_schema_rejects_malformed_coordinates_and_unknown_fields(tmp_path, changes):
    app = store(tmp_path)
    request = payload(app, **changes)
    with pytest.raises(PrivateError) as error:
        app.save(request)
    assert CANARY not in str(error.value)


def test_multiple_mentions_multiline_offsets_and_false_positives(tmp_path):
    app = store(tmp_path, text=CANARY + "\n" + CANARY)
    request = payload(app)
    second = copy.deepcopy(request["annotations"][0])
    second["start"] = len(CANARY) + 1
    second["end"] = len(CANARY) * 2 + 1
    second["status"] = "FALSE_POSITIVE"
    request["annotations"].append(second)
    assert app.save(request) == 2
    with pytest.raises(PrivateError, match="CONSENT"):
        app.export_training(tmp_path / "training.jsonl")
    assert app.export_training(tmp_path / "training.jsonl", consent_original_text=True) == 1
    row = json.loads((tmp_path / "training.jsonl").read_text())
    assert row["text"] == CANARY + "\n" + CANARY
    assert len(row["spans"]) == 1  # False-positive annotations are never gold spans.


def test_source_change_invalidates_annotations(tmp_path):
    app = store(tmp_path)
    request = payload(app)
    app.save(request)
    (app.source_dir / "original.txt").write_text("changed")
    with pytest.raises(PrivateError, match="SOURCE_CHANGED"):
        app.describe(request["document_id"])


def test_image_region_annotation_and_png_metadata_stripping(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    source = tmp_path / "images"
    source.mkdir()
    image = Image.new("RGB", (100, 100), "white")
    image.save(source / "private.png")
    app = AnnotationStore(source, tmp_path / "private", DeidEngine(), consent_display=True)
    identity = app.catalog()[0]["id"]
    description = app.describe(identity)
    record = {
        "kind": "region",
        "entity_type": "PERSON",
        "status": "MISSED",
        "fragment_id": None,
        "start": None,
        "end": None,
        "page": 1,
        "bbox": [0.1, 0.2, 0.6, 0.7],
        "group_id": None,
        "corrected_text": None,
    }
    request = {
        "document_id": identity,
        "source_sha256": description["source_sha256"],
        "store_excerpts": False,
        "annotations": [record],
    }
    assert app.save(request) == 1
    assert app.render(identity, 1).startswith(b"\x89PNG")
    request["annotations"][0]["bbox"] = [0, 0, float("nan"), 1]
    with pytest.raises(PrivateError):
        app.save(request)


def test_structured_field_annotation_requires_whole_field(tmp_path):
    source = tmp_path / "tables"
    source.mkdir()
    (source / "sample.csv").write_text("email\n" + CANARY + "@example.test\n")
    app = AnnotationStore(source, tmp_path / "private", DeidEngine(), consent_display=True)
    identity = app.catalog()[0]["id"]
    description = app.describe(identity)
    field = next(f for f in description["fragments"] if f["kind"] == "cell")
    record = {
        "kind": "field",
        "entity_type": "EMAIL",
        "status": "CONFIRMED",
        "fragment_id": field["id"],
        "start": 0,
        "end": len(field["text"]),
        "page": None,
        "bbox": None,
        "group_id": None,
        "corrected_text": None,
    }
    request = {
        "document_id": identity,
        "source_sha256": description["source_sha256"],
        "store_excerpts": False,
        "annotations": [record],
    }
    assert app.save(request) == 1
    record["start"] = 1
    with pytest.raises(PrivateError):
        app.save(request)


def test_local_http_requires_bearer_csrf_and_exact_origin_no_upload(tmp_path, capsys):
    app = store(tmp_path)
    server = annotation_server(app)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/api/catalog")
        response = connection.getresponse()
        assert response.status == 403 and CANARY not in response.read().decode()
        headers = {"Authorization": "Bearer " + server.token}
        connection.request("GET", "/api/catalog", headers=headers)
        response = connection.getresponse()
        assert response.status == 200
        catalog = json.loads(response.read())
        assert CANARY not in json.dumps(catalog)
        assert "Content-Security-Policy" in response.headers
        identity = catalog["entries"][0]["id"]
        connection.request("GET", "/api/sample?id=" + identity, headers=headers)
        response = connection.getresponse()
        assert response.status == 200 and CANARY in response.read().decode()
        connection.request(
            "GET", "/api/catalog", headers=headers | {"Origin": "https://evil.example"}
        )
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.request(
            "POST",
            "/api/annotations",
            body=json.dumps(payload(app)),
            headers=headers | {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 400
        response.read()
        connection.request(
            "POST",
            "/api/upload",
            body=CANARY,
            headers=headers
            | {"Content-Type": "multipart/form-data", "X-DeidFlow-CSRF": server.token},
        )
        response = connection.getresponse()
        assert response.status == 400
        response.read()
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert CANARY not in "".join(capsys.readouterr())


def test_annotation_cli_rejects_agent_before_reading_source(monkeypatch, capsys):
    monkeypatch.setenv("CODEX_SESSION_ID", "synthetic-agent")
    assert (
        main(
            [
                "--source-dir",
                CANARY,
                "--private-root",
                CANARY,
                "--external-terminal-ack",
                "--consent-display-originals",
            ]
        )
        == 3
    )
    assert CANARY not in "".join(capsys.readouterr())


def test_browser_selection_preserves_python_offsets_after_crlf_and_astral_unicode():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the actual browser offset function")
    program = (
        _OFFSET_SCRIPT
        + r"""
const original='🙂\r\nMaría\r\nfin';
const displayed=original.replace(/\r\n/g,'\n');
const start=displayed.indexOf('María');
process.stdout.write(JSON.stringify([sourceOffset(original,displayed,start),sourceOffset(original,displayed,start+5)]));
"""
    )
    result = subprocess.run([node, "-e", program], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [3, 8]
