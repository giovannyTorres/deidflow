from __future__ import annotations

import io
import os
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from deidflow.ocr import OCRError, TesseractOCR

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


class ImageStub:
    width, height = 100, 50

    def save(self, buffer, *, format):
        assert format == "PNG"
        buffer.write(b"test raster")


@pytest.mark.parametrize(
    "options",
    [
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"timeout": True},
        {"min_confidence": float("nan")},
        {"psm": 0},
        {"psm": 2},
        {"psm": 12},
        {"psm": True},
        {"oem": 5},
        {"language": "spa --psm 6"},
        {"language": "../spa"},
        {"threads": 0},
        {"threads": True},
        {"threads": 33},
    ],
)
def test_ocr_configuration_is_strict(options):
    with pytest.raises(ValueError):
        TesseractOCR(**options)


def test_argv_paths_with_spaces_and_no_global_environment(monkeypatch, tmp_path):
    data = tmp_path / "language data"
    data.mkdir()
    (data / "spa.traineddata").write_bytes(b"model")
    original = os.environ.get("OMP_THREAD_LIMIT")
    captured = []

    def run(arguments, **kwargs):
        captured.append((arguments, kwargs))
        return SimpleNamespace(
            stdout=(HEADER + "5\t1\t1\t1\t1\t1\t2\t3\t10\t11\t42.5\tMaría\n").encode()
        )

    monkeypatch.setattr(subprocess, "run", run)
    ocr = TesseractOCR(
        language="spa", executable="private path/tesseract.exe", tessdata_dir=data, threads=2
    )
    result = ocr.recognize(ImageStub())
    assert result.tokens[0].confidence == 42.5
    assert result.tokens[0].bbox == (2, 3, 12, 14)
    assert captured[0][0][captured[0][0].index("--tessdata-dir") + 1] == str(data.resolve())
    assert captured[0][1]["input"] == b"test raster"
    assert captured[0][1]["env"]["OMP_THREAD_LIMIT"] == "2"
    assert os.environ.get("OMP_THREAD_LIMIT") == original


@pytest.mark.parametrize(
    "line",
    [
        "5\t1\t1\t1\t1\t1\t2\t3\t10\t11\tNaN\tword\n",
        "5\t1\t1\t1\t1\t1\t2\t3\t1000\t11\t99\tword\n",
        "5\t1\t1\t1\t1\t1\t2\t3\t10\t11\t-2\tword\n",
    ],
)
def test_invalid_tsv_fails_closed(monkeypatch, line):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=(HEADER + line).encode())
    )
    with pytest.raises(OCRError, match="invalid token"):
        TesseractOCR().recognize(ImageStub())


def test_failure_sanitizes_subprocess_details(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("private@example.test", 1, stderr=b"sensitive content")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(OCRError) as error:
        TesseractOCR().recognize(ImageStub())
    assert "private" not in str(error.value) and "sensitive" not in str(error.value)


def test_exit_zero_language_fallback_is_rejected(monkeypatch):
    output = (HEADER + "5\t1\t1\t1\t1\t1\t2\t3\t10\t11\t99\tword\n").encode()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=output, stderr=b"Failed loading language 'spa'"),
    )
    with pytest.raises(OCRError, match="execution failed"):
        TesseractOCR().recognize(ImageStub())


def test_missing_language_does_not_start_a_process(monkeypatch, tmp_path):
    def fail(*a, **k):
        raise AssertionError("Unexpected process")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(OCRError, match="language data"):
        TesseractOCR(tessdata_dir=tmp_path).recognize(ImageStub())


@pytest.fixture
def actual_ocr():
    executable = os.getenv("DEIDFLOW_TEST_TESSERACT")
    data = os.getenv("DEIDFLOW_TEST_TESSDATA_DIR") or os.getenv("DEIDFLOW_TEST_TESSDATA")
    if not executable or not data:
        pytest.skip("Provide explicit local Tesseract and language paths for integration")
    return TesseractOCR(executable=executable, tessdata_dir=data, psm=6)


def spanish_image():
    from PIL import Image, ImageDraw, ImageFont

    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path) if font_path.exists() else "DejaVuSans.ttf", 40)
    image = Image.new("RGB", (1800, 400), "white")
    ImageDraw.Draw(image).text(
        (50, 40),
        "Paciente: María Pérez\nCorreo: maria@example.test\nDiagnóstico: hipertensión",
        font=font,
        fill="black",
        spacing=20,
    )
    return image


def test_actual_spanish_accents_network_denied(actual_ocr, monkeypatch):
    def fail(*a, **k):
        raise AssertionError("Network attempted")

    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    with spanish_image() as image:
        result = actual_ocr.recognize(image)
    text = " ".join(t.text for t in result.tokens)
    assert "María" in text and "Pérez" in text and "hipertensión" in text
    assert "maria@example.test" in text
    assert all(0 <= t.confidence <= 100 for t in result.tokens)


def test_actual_parallel_calls_do_not_corrupt_configuration(actual_ocr):
    def invoke(_):
        with spanish_image() as image:
            return " ".join(t.text for t in actual_ocr.recognize(image).tokens)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, range(4)))
    assert len(set(results)) == 1 and "hipertensión" in results[0]


def test_actual_corrupt_spanish_cannot_fall_back_to_english(actual_ocr, tmp_path):
    import shutil

    data = tmp_path / "language data with spaces"
    data.mkdir()
    shutil.copyfile(actual_ocr.tessdata_dir / "eng.traineddata", data / "eng.traineddata")
    (data / "spa.traineddata").write_bytes(b"invalid local model")
    ocr = TesseractOCR(executable=actual_ocr.executable, tessdata_dir=data, psm=6)
    with spanish_image() as image:
        with io.BytesIO() as buffer:
            image.save(buffer, format="PNG")
            raw = subprocess.run(
                [
                    actual_ocr.executable,
                    "stdin",
                    "stdout",
                    "--tessdata-dir",
                    str(data),
                    "-l",
                    "spa+eng",
                    "--psm",
                    "6",
                    "-c",
                    "tessedit_create_tsv=1",
                ],
                input=buffer.getvalue(),
                capture_output=True,
                timeout=30,
            )
        assert raw.returncode == 0 and b"Failed loading language" in raw.stderr
        with pytest.raises(OCRError, match="execution failed"):
            ocr.recognize(image)
