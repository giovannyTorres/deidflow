from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy, ReleaseStatus
from deidflow.ocr import OCRError, TesseractOCR
from deidflow.performance import ACTIVE_PROFILER, StageProfiler
from deidflow.redactors.pdf import _ocr_jobs


def test_stage_profiler_has_numeric_allowlisted_data_and_nested_work():
    profile = StageProfiler(True)
    try:
        with profile.stage("verification"), profile.stage("rules"):
            time.sleep(0.002)
        value = profile.report()
        assert value["stages"]["rules"]["calls"] == 1
        assert (
            value["stages"]["verification"]["exclusive_work_seconds"]
            <= value["stages"]["verification"]["inclusive_work_seconds"]
        )
        with pytest.raises(ValueError) as error:
            with profile.stage("private-canary@example.test"):
                pass
        assert "private-canary" not in str(error.value)
        assert "private-canary" not in json.dumps(profile.report())
    finally:
        profile.close()


def test_ocr_queue_bounded_ordered_and_closes_every_image(monkeypatch):
    from deidflow.redactors import pdf

    lock = threading.Lock()
    active = peak = 0

    class Image:
        closed = False

        def __init__(self, index):
            self.index = index

        def close(self):
            self.closed = True

    images = [Image(i) for i in range(13)]

    def recognize(image, *args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.003)
        with lock:
            active -= 1
        return image.index

    monkeypatch.setattr(pdf, "_recognize_prepared", recognize)
    output = list(
        _ocr_jobs(iter({"image": image} for image in images), None, 4, StageProfiler(False))
    )
    assert [value for _, value in output] == list(range(13))
    assert peak <= 4 and all(image.closed for image in images)


def _real_ocr():
    executable = os.getenv("DEIDFLOW_TEST_TESSERACT")
    if not executable or not Path(executable).is_file():
        pytest.skip("Explicit local OCR assets required")
    return TesseractOCR(
        executable=executable, tessdata_dir=os.getenv("DEIDFLOW_TEST_TESSDATA_DIR"), psm=6
    )


def _source(path: Path, pages: int = 4):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas").Canvas(
        str(path), pagesize=(300, 200), invariant=1
    )
    for i in range(pages):
        canvas.setFont("Helvetica", 12)
        canvas.drawString(20, 170, "Informe de prueba")
        canvas.drawString(20, 130, f"Correo: demo{i}@example.test")
        canvas.drawString(20, 90, "Importe: 42 pesos")
        canvas.showPage()
    canvas.save()


def test_actual_parallel_ocr_preserves_pixels_order_status_and_hash(tmp_path):
    source = tmp_path / "source.pdf"
    _source(source)
    hashes = []
    masks = []
    decisions = []
    for workers in (1, 2, 4, 8):
        engine = DeidEngine(
            ocr=_real_ocr(), pdf_workers=workers, pdf_profile=True, memory_budget_mb=1024
        )
        result = engine.deidentify(
            source,
            output=tmp_path / f"safe-{workers}.pdf",
            policy=Policy.strict_pdf(require_ner=False),
        )
        # Supported OCR runtimes may split the planted email before @. The
        # unvalidated OCR candidate must retain its review gate in every worker
        # mode; runtime accuracy is not a precondition for testing parallelism.
        decision = (result.status, tuple(result.issues))
        assert decision in {
            (ReleaseStatus.APPROVED, ()),
            (ReleaseStatus.REVIEW_REQUIRED, ("UNCERTAIN_SOURCE_FINDINGS",)),
        }, result.issues
        decisions.append(decision)
        assert result.output_path is not None
        assert hashlib.sha256(result.output_path.read_bytes()).hexdigest() == result.audit["sha256"]
        hashes.append(result.audit["sha256"])
        masks.append([page["masks"] for page in result.audit["page_receipts"]])
        assert [p["page"] for p in result.audit["page_receipts"]] == [1, 2, 3, 4]
        assert result.audit["performance"]["stages"]["ocr"]["calls"] == 8
        assert ACTIVE_PROFILER.get() is None
    assert len(set(hashes)) == 1 and all(value == masks[0] for value in masks)
    assert len(set(decisions)) == 1


def test_parallel_rag_uses_actual_verified_pixels(tmp_path):
    source = tmp_path / "source.pdf"
    _source(source, 2)
    decisions, hashes = [], []
    for workers in (1, 2):
        result = DeidEngine(
            ocr=_real_ocr(), pdf_workers=workers, pdf_profile=True, memory_budget_mb=512
        ).deidentify(
            source,
            output=tmp_path / f"bundle-{workers}",
            outputs=["pdf", "jsonl"],
            policy=Policy.strict_pdf(require_ner=False),
        )
        decision = (result.status, tuple(result.issues))
        assert decision in {
            (ReleaseStatus.APPROVED, ()),
            (ReleaseStatus.REVIEW_REQUIRED, ("UNCERTAIN_SOURCE_FINDINGS",)),
        }, result.issues
        decisions.append(decision)
        assert result.safe_jsonl and result.audit_path and result.safe_pdf
        assert result.audit["joint_artifact_verification"] is True
        audit = json.loads(result.audit_path.read_text(encoding="utf-8"))
        assert audit["verification"]["shared_verified_pixel_decisions"] is True
        digest = hashlib.sha256(result.safe_pdf.read_bytes()).hexdigest()
        assert digest == audit["artifacts"]["pdf_sha256"]
        assert (
            hashlib.sha256(result.safe_jsonl.read_bytes()).hexdigest()
            == (audit["artifacts"]["jsonl_sha256"])
        )
        hashes.append(digest)
        text = result.safe_jsonl.read_text(encoding="utf-8")
        assert "@example.test" not in text and "example.test" not in text
        assert "42" in text
        assert [json.loads(line)["page"] for line in text.splitlines()] == [1, 2]
    assert len(set(decisions)) == len(set(hashes)) == 1


def test_parallel_custom_adapter_is_not_silently_assumed_threadsafe(tmp_path):
    class Custom:
        def recognize(self, image):
            raise AssertionError("Must not run")

    result = DeidEngine(ocr=Custom(), pdf_workers=2).deidentify(
        tmp_path / "in.pdf", output=tmp_path / "out.pdf"
    )
    assert result.status == ReleaseStatus.UNSUPPORTED


def test_parallel_failure_blocks_and_restores_profiler(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    _source(source, 2)

    def fail(*args):
        raise OCRError("Fixed local failure")

    monkeypatch.setattr(TesseractOCR, "recognize", fail)
    result = DeidEngine(
        ocr=TesseractOCR(), pdf_workers=2, pdf_profile=True, memory_budget_mb=512
    ).deidentify(source, output=tmp_path / "out.pdf", policy=Policy.strict_pdf(require_ner=False))
    assert result.status == ReleaseStatus.BLOCKED
    assert not (tmp_path / "out.pdf").exists()
    assert not list(tmp_path.glob(".deidflow-*"))
    assert ACTIVE_PROFILER.get() is None


def test_bad_output_schema_and_worker_limits_rejected(tmp_path):
    with pytest.raises(ValueError):
        DeidEngine().deidentify(tmp_path / "in.pdf", output=tmp_path / "out", outputs=[["pdf"]])
    for value in (0, 9, True):
        with pytest.raises(ValueError):
            DeidEngine(pdf_workers=value)
    for value in ("true", 1):
        with pytest.raises(ValueError):
            DeidEngine().deidentify(
                tmp_path / "in.pdf", output=tmp_path / "out", require_table_structure=value
            )
    with pytest.raises(ValueError):
        DeidEngine().deidentify(
            tmp_path / "in.pdf", output=tmp_path / "out.pdf", require_table_structure=True
        )


def test_damaged_ocr_clinical_field_requires_subject_and_review():
    engine = DeidEngine()
    text = "Paciente: María Prueba Torres\nDiagnóstico: d1abctes\nTratamiento: observaci0n"
    findings = engine.scan_ocr_text(text)
    clinical = [f for f in findings if f.entity_type in {"DIAGNOSIS", "TREATMENT"}]
    assert {text[f.start : f.end] for f in clinical} == {"d1abctes", "observaci0n"}
    assert all(f.protected and f.score == 0.6 for f in clinical)
    assert not engine.scan_ocr_text("Diagnóstico: ejemplo didáctico\nTratamiento: introducción")


def test_pdf_permissions_failure_closes_empty_candidate_and_blocks(tmp_path, monkeypatch):
    from deidflow.private import security

    source = tmp_path / "source.pdf"
    _source(source, 1)
    observed = []

    def deny(path, *, directory):
        assert not directory and path.stat().st_size == 0
        observed.append(path)
        raise security.PrivateError("PRIVATE_PERMISSIONS_FAILED")

    monkeypatch.setattr(security, "protect", deny)
    result = DeidEngine(ocr=TesseractOCR()).deidentify(
        source, output=tmp_path / "out.pdf", policy=Policy.strict_pdf(require_ner=False)
    )
    assert observed
    assert result.status == ReleaseStatus.BLOCKED
    assert result.issues == ["PDF_PROCESSING_FAILED"]
    assert not (tmp_path / "out.pdf").exists()
    assert not list(tmp_path.glob(".deidflow-*"))
