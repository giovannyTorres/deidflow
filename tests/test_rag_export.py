from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus, Result
from deidflow.ocr import OCRResult, OCRToken, TesseractOCR
from deidflow.rag import (
    RAGExportError,
    _canonical,
    _page_record,
    _validate_page,
    _verify_rag_jsonl,
    export_pdf_bundle,
    verify_rag_jsonl,
)

CANARY = "private-canary-7491@example.test"


def _pdf(path: Path, pages: int = 1) -> None:
    canvas = pytest.importorskip("reportlab.pdfgen.canvas").Canvas(str(path), pagesize=(300, 200))
    for _ in range(pages):
        canvas.drawString(20, 170, "Documento sintetico")
        canvas.drawString(20, 130, "Correo: " + CANARY)
        canvas.drawString(20, 90, "Importe: 42 pesos")
        canvas.showPage()
    canvas.save()


class SafeMechanicalOCR:
    """Only tests export mechanics, never OCR accuracy or detection quality."""

    min_confidence = 50

    def recognize(self, image):
        return OCRResult(
            (
                OCRToken("Importe:", (10, 10, 80, 25), 99, (1, 1, 1)),
                OCRToken("42", (85, 10, 110, 25), 99, (1, 1, 1)),
                OCRToken("pesos", (115, 10, 155, 25), 99, (1, 1, 1)),
            ),
            image.width,
            image.height,
            "synthetic-mechanics",
        )


def _engine():
    return DeidEngine(ocr=SafeMechanicalOCR(), pdf_dpi=144)


def _policy():
    return Policy.strict_pdf(require_ner=False)


def _record(text="Importe: 42 pesos"):
    return _page_record(
        {
            "page": 1,
            "page_width": 300,
            "page_height": 200,
            "raster_width": 600,
            "raster_height": 400,
            "text": text,
            "spans": [(0, len(text), (10, 10, 160, 25))],
        },
        "a" * 32,
    )


def test_bundle_matches_verified_pdf_and_excludes_original_canary(tmp_path):
    source = tmp_path / "private-source-canary.pdf"
    _pdf(source)
    result = export_pdf_bundle(source, tmp_path / "bundle", engine=_engine(), policy=_policy())
    assert result.release_approved, result.audit_dict()
    assert result.safe_jsonl.exists() and result.audit_path.exists()
    assert {p.name for p in result.output_path.parent.iterdir()} == {
        "document.safe.pdf",
        "document.safe.jsonl",
        "document.audit.json",
    }
    page = json.loads(result.safe_jsonl.read_text())
    assert page["text"] == "Importe: 42 pesos"
    assert page["lines"][0]["start"] == 0
    audit = json.loads(result.audit_path.read_text())
    assert CANARY not in json.dumps(audit) and "private-source-canary" not in json.dumps(audit)
    assert audit["status"] == "APPROVED"
    assert (
        audit["artifacts"]["pdf_sha256"]
        == hashlib.sha256(result.output_path.read_bytes()).hexdigest()
    )
    assert (
        audit["artifacts"]["jsonl_sha256"]
        == hashlib.sha256(result.safe_jsonl.read_bytes()).hexdigest()
    )
    assert not list(tmp_path.glob(".deidflow-rag-*"))


def test_pdf_pass_does_not_grant_approval_to_unverified_jsonl(tmp_path, monkeypatch):
    import deidflow.redactors.pdf as pdf

    source = tmp_path / "source.pdf"
    _pdf(source)
    original = pdf.redact_pdf

    def tamper(source, output, **kwargs):
        result = original(source, output, **kwargs)
        path = Path(output).parent / "document.safe.jsonl"
        record = json.loads(path.read_text())
        record["text"] = "Unlabelled Original Person"
        path.write_bytes(_canonical(record) + b"\n")
        return result

    monkeypatch.setattr(pdf, "redact_pdf", tamper)
    result = export_pdf_bundle(source, tmp_path / "bundle", engine=_engine(), policy=_policy())
    assert result.status == ReleaseStatus.BLOCKED
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".deidflow-rag-*"))


def test_pdf_mutation_after_callback_is_not_approved(tmp_path, monkeypatch):
    import deidflow.redactors.pdf as pdf

    source = tmp_path / "source.pdf"
    _pdf(source)
    original = pdf.redact_pdf

    def mutate(source, output, **kwargs):
        result = original(source, output, **kwargs)
        with Path(output).open("ab") as handle:
            handle.write(CANARY.encode())
        return result

    monkeypatch.setattr(pdf, "redact_pdf", mutate)
    result = export_pdf_bundle(source, tmp_path / "bundle", engine=_engine(), policy=_policy())
    assert result.status == ReleaseStatus.BLOCKED and not (tmp_path / "bundle").exists()


def test_missing_page_receipts_cannot_publish_pdf_only(tmp_path, monkeypatch):
    import deidflow.redactors.pdf as pdf

    def missing(source, output, **kwargs):
        Path(output).write_bytes(b"fake approved document")
        return Result(
            ReleaseStatus.APPROVED,
            output_path=Path(output),
            records=1,
            audit={"encoded_pixels_verified": True, "output_rerendered_and_ocr_verified": True},
        )

    monkeypatch.setattr(pdf, "redact_pdf", missing)
    result = export_pdf_bundle(
        tmp_path / "source.pdf", tmp_path / "bundle", engine=_engine(), policy=_policy()
    )
    assert result.status == ReleaseStatus.BLOCKED
    assert not (tmp_path / "bundle").exists()


def test_review_requirement_survives_joint_gate_and_table_requirement(tmp_path):
    source = tmp_path / "source.pdf"
    _pdf(source)
    default = export_pdf_bundle(source, tmp_path / "strict", engine=_engine())
    assert default.status == ReleaseStatus.REVIEW_REQUIRED
    assert "SEMANTIC_MODEL_REQUIRED" in default.issues
    table = export_pdf_bundle(
        source,
        tmp_path / "tables",
        engine=_engine(),
        policy=_policy(),
        require_table_structure=True,
    )
    assert table.status == ReleaseStatus.REVIEW_REQUIRED
    assert "RAG_TABLE_STRUCTURE_UNAVAILABLE" in table.issues
    assert json.loads(table.safe_jsonl.read_text())["tables"] == []


def test_standalone_jsonl_is_not_a_transformation_receipt(tmp_path):
    path = tmp_path / "page.jsonl"
    path.write_bytes(_canonical(_record()) + b"\n")
    result = verify_rag_jsonl(path, engine=_engine(), policy=_policy())
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "RAG_TRANSFORMATION_RECEIPT_REQUIRED" in result.issues


@pytest.mark.parametrize("tamper", ["missing_lines", "unmapped_suffix", "missing_tokens"])
def test_unattested_plaintext_cannot_hide_outside_geometry(tmp_path, tamper):
    record = _record()
    if tamper == "missing_lines":
        record["lines"] = []
    elif tamper == "unmapped_suffix":
        record["text"] += "\nOriginal Unlabelled Person"
    else:
        record["lines"][0]["tokens"] = []
    path = tmp_path / "page.jsonl"
    path.write_bytes(_canonical(record) + b"\n")
    assert (
        verify_rag_jsonl(path, engine=_engine(), policy=_policy()).status == ReleaseStatus.BLOCKED
    )


def test_engine_joint_output_route_is_not_pdf_only(tmp_path):
    source = tmp_path / "source.pdf"
    _pdf(source)
    result = _engine().deidentify(
        source, output=tmp_path / "bundle", outputs=["pdf", "jsonl"], policy=_policy()
    )
    assert result.release_approved and result.safe_jsonl.exists() and result.audit_path.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"private_filename": CANARY},
        {"page": True},
        {"document_id": CANARY},
        {"tables": [{"text": CANARY}]},
        {"schema_version": 2},
    ],
)
def test_schema_rejects_metadata_injection(tmp_path, change):
    record = _record()
    record.update(change)
    path = tmp_path / "page.jsonl"
    path.write_bytes(_canonical(record) + b"\n")
    result = verify_rag_jsonl(path, engine=_engine(), policy=_policy())
    assert result.status == ReleaseStatus.BLOCKED
    assert CANARY not in repr(result.audit_dict())


def test_duplicate_keys_and_unbounded_pages_fail(tmp_path):
    path = tmp_path / "page.jsonl"
    path.write_text('{"text":"' + CANARY + '","text":"safe"}\n')
    assert (
        verify_rag_jsonl(path, engine=_engine(), policy=_policy()).status == ReleaseStatus.BLOCKED
    )
    path.write_bytes(_canonical(_record()) + b"\n")
    engine = DeidEngine(ocr=SafeMechanicalOCR(), max_bytes=16)
    assert verify_rag_jsonl(path, engine=engine, policy=_policy()).status == ReleaseStatus.BLOCKED


def test_serialized_sensitive_residual_blocks_even_with_matching_record_hash(tmp_path):
    record = _record(CANARY)
    path = tmp_path / "page.jsonl"
    path.write_bytes(_canonical(record) + b"\n")
    result = _verify_rag_jsonl(
        path,
        engine=_engine(),
        policy=_policy(),
        expected_record_hashes=[hashlib.sha256(_canonical(record)).hexdigest()],
        expected_document_id="a" * 32,
    )
    assert result.status == ReleaseStatus.BLOCKED


def test_existing_output_and_publication_race_never_overwrite(tmp_path, monkeypatch):
    import deidflow.rag as rag

    source = tmp_path / "source.pdf"
    _pdf(source)
    target = tmp_path / "bundle"
    original = rag._publish

    def race(stage, destination):
        destination.mkdir()
        (destination / "user-file.txt").write_text(CANARY)
        original(stage, destination)

    monkeypatch.setattr(rag, "_publish", race)
    result = export_pdf_bundle(source, target, engine=_engine(), policy=_policy())
    assert result.status == ReleaseStatus.BLOCKED
    assert (target / "user-file.txt").read_text() == CANARY
    with pytest.raises(FileExistsError):
        export_pdf_bundle(source, target, engine=_engine(), policy=_policy())


def test_multiline_offsets_and_relationships_are_validated():
    page = {
        "page": 1,
        "page_width": 300,
        "page_height": 200,
        "raster_width": 600,
        "raster_height": 400,
        "text": "Importe42\nEstado activo",
        "spans": [(0, 9, (10, 10, 100, 25)), (10, 23, (10, 30, 130, 45))],
    }
    record = _page_record(page, "a" * 32)
    _validate_page(record, page_number=1, document_id="a" * 32)
    assert len(record["lines"]) == 2
    assert record["lines"][0]["next_id"] == record["lines"][1]["chunk_id"]
    record["lines"][0]["bbox"][2] = 9999
    with pytest.raises(RAGExportError):
        _validate_page(record, page_number=1, document_id="a" * 32)


def test_audit_suppresses_unknown_upstream_strings(tmp_path, monkeypatch):
    import deidflow.redactors.pdf as pdf

    source = tmp_path / "source.pdf"
    _pdf(source)
    original = pdf.redact_pdf

    def strange(source, output, **kwargs):
        result = original(source, output, **kwargs)
        result.issues.append(CANARY)
        return result

    monkeypatch.setattr(pdf, "redact_pdf", strange)
    result = export_pdf_bundle(source, tmp_path / "bundle", engine=_engine(), policy=_policy())
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert CANARY not in result.audit_path.read_text()
    assert result.issues == ["UPSTREAM_REVIEW_REQUIRED"]


def test_real_ocr_bundle_contains_only_verified_output_text(tmp_path, monkeypatch):
    executable = os.getenv("DEIDFLOW_TEST_TESSERACT")
    data = os.getenv("DEIDFLOW_TEST_TESSDATA_DIR")
    if not executable or not data:
        pytest.skip("Set explicit local OCR assets for real integration")
    source = tmp_path / "source.pdf"
    _pdf(source, pages=2)

    def deny(*args, **kwargs):
        raise AssertionError("Network denied")

    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    engine = DeidEngine(
        ocr=TesseractOCR(executable=executable, tessdata_dir=data, language="spa+eng", psm=6),
        pdf_dpi=216,
    )
    result = export_pdf_bundle(source, tmp_path / "bundle", engine=engine, policy=_policy())
    assert result.status in {ReleaseStatus.APPROVED, ReleaseStatus.REVIEW_REQUIRED}, (
        result.audit_dict()
    )
    lines = result.safe_jsonl.read_text(encoding="utf-8")
    assert CANARY not in lines and "42" in lines
    records = [json.loads(line) for line in lines.splitlines()]
    assert [record["page"] for record in records] == [1, 2]
    assert len({record["document_id"] for record in records}) == 1
