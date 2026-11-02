from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def benchmark_module():
    path = Path(__file__).resolve().parents[1] / "scripts/benchmark_pdf_ocr.py"
    spec = importlib.util.spec_from_file_location("deidflow_pdf_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_edit_distance_and_normalized_error_rates(benchmark_module):
    assert benchmark_module.edit_distance("kitten", "sitting") == 3
    assert benchmark_module.edit_distance("", "abc") == 3
    assert benchmark_module.transcription_metrics("café\nprueba", "cafe\u0301 prueba")["cer"] == 0
    assert benchmark_module.transcription_metrics("uno dos", "uno tres")["wer"] == 0.5


def test_seeded_cases_gold_matches_original_text(benchmark_module):
    cases = benchmark_module.page_cases(3)
    assert cases == benchmark_module.page_cases(3)
    assert len({case.identifier for case in cases}) == 3
    for case in cases:
        for gold in case.gold:
            assert gold.value in case.text
    assert benchmark_module.page_cases(3, challenge=True) == benchmark_module.page_cases(
        3, challenge=True
    )


def test_value_recall_does_not_hide_missing_ocr_entities(benchmark_module):
    from deidflow import DeidEngine

    case = benchmark_module.page_cases(1)[0]
    metric = benchmark_module.gold_value_metrics([case], ["No datos"], DeidEngine())
    assert metric["gold_value_recall"] == 0
    assert metric["gold_entities"] == len(case.gold)
    actual = benchmark_module.gold_value_metrics([case], [case.text], DeidEngine())
    assert actual["gold_value_recall"] == 1
    assert actual["gold_value_precision"] <= 1


def test_real_native_and_scanned_fixture_content(benchmark_module, tmp_path):
    pytest.importorskip("reportlab")
    pytest.importorskip("PIL")
    from pypdf import PdfReader

    case = benchmark_module.page_cases(1)
    native, scanned = tmp_path / "native.pdf", tmp_path / "scan.pdf"
    benchmark_module.generate_pdf(native, case, kind="native")
    benchmark_module.generate_pdf(scanned, case, kind="scanned")
    assert "paciente.000000@example.test" in PdfReader(native).pages[0].extract_text()
    assert not PdfReader(scanned).pages[0].extract_text()
    first = native.read_bytes()
    benchmark_module.generate_pdf(native, case, kind="native")
    assert first == native.read_bytes()


def test_alignment_and_workload_validation(benchmark_module):
    from deidflow import DeidEngine

    with pytest.raises(ValueError):
        benchmark_module.evaluate_transcription(benchmark_module.page_cases(1), [])
    with pytest.raises(ValueError):
        benchmark_module.gold_value_metrics(benchmark_module.page_cases(1), [], DeidEngine())
    assert benchmark_module.percentile([], 0.5) is None
    assert benchmark_module.percentile([1, 3], 0.5) == 2


def test_gold_pixel_check_rejects_unchanged_visible_pii(benchmark_module, tmp_path):
    pytest.importorskip("pypdfium2")
    cases = benchmark_module.page_cases(1)
    source = tmp_path / "source.pdf"
    benchmark_module.generate_pdf(source, cases, kind="native")
    result = benchmark_module.verify_gold_pixels(source, source, cases, kind="native", dpi=216)
    assert result["passed"] is False
    assert result["unmasked_gold_word_regions"] > 0
    assert result["indeterminate_gold_word_regions"] == 0


def test_gold_pixel_check_validates_actual_opaque_raster(benchmark_module, tmp_path):
    pytest.importorskip("pypdfium2")
    from reportlab.pdfgen.canvas import Canvas

    cases = benchmark_module.page_cases(1)
    source, output = tmp_path / "source.pdf", tmp_path / "black.pdf"
    benchmark_module.generate_pdf(source, cases, kind="native")
    canvas = Canvas(str(output), pagesize=(612, 792), invariant=1)
    canvas.rect(0, 0, 612, 792, stroke=0, fill=1)
    canvas.showPage()
    canvas.save()
    result = benchmark_module.verify_gold_pixels(source, output, cases, kind="native", dpi=216)
    assert result["passed"] and result["gold_words_checked"] > 9


def test_extra_output_ocr_failure_is_unknown_not_zero_leakage(benchmark_module, tmp_path):
    pytest.importorskip("pypdfium2")
    from deidflow import DeidEngine
    from deidflow.ocr import OCRError

    class Unreadable:
        def recognize(self, image):
            raise OCRError("No readable tokens")

    cases = benchmark_module.page_cases(1)
    source = tmp_path / "source.pdf"
    benchmark_module.generate_pdf(source, cases, kind="native")
    result = benchmark_module.verify_gold_output(
        source, cases, DeidEngine(ocr=Unreadable()), dpi=216, source=source, kind="native"
    )
    assert result["output_ocr_complete"] is False
    assert result["output_ocr_failed_pages"] == [1]
    assert result["residual_gold_values_in_output_ocr"] is None
    assert result["passed"] is False
