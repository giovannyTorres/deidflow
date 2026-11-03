"""Explicitly configured, local OCR. Importing this module starts no processes."""

from __future__ import annotations

import csv
import io
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class OCRError(RuntimeError):
    """OCR could not complete; messages never include recognized content."""


@dataclass(frozen=True)
class OCRToken:
    text: str = field(repr=False)
    bbox: tuple[float, float, float, float]
    confidence: float
    line: tuple[int, int, int] = (0, 0, 0)


@dataclass(frozen=True)
class OCRResult:
    tokens: tuple[OCRToken, ...]
    width: int
    height: int
    engine: str


class OCREngine(Protocol):
    def recognize(self, image: Any) -> OCRResult: ...


class TesseractOCR:
    """Run an installed Tesseract executable; never install or download assets.

    ``language`` must correspond to locally installed traineddata. A timeout,
    missing executable, missing language, or empty result raises OCRError.
    OCR confidence is an engine score, not a calibrated probability.
    """

    def __init__(
        self,
        *,
        language: str = "spa+eng",
        executable: str | None = None,
        tessdata_dir: str | Path | None = None,
        psm: int = 3,
        oem: int = 1,
        threads: int = 1,
        timeout: float = 60,
        min_confidence: float = 50,
    ) -> None:
        if (
            type(timeout) not in {int, float}
            or not math.isfinite(timeout)
            or timeout <= 0
            or type(min_confidence) not in {int, float}
            or not math.isfinite(min_confidence)
            or not 0 <= min_confidence <= 100
        ):
            raise ValueError("Invalid OCR limits")
        if (
            not isinstance(language, str)
            or len(language) > 128
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\+[A-Za-z][A-Za-z0-9_]*)*", language)
        ):
            raise ValueError("Invalid local OCR language selection")
        if type(psm) is not int or psm not in {3, 4, 5, 6, 7, 8, 9, 10, 11, 13}:
            raise ValueError("OCR page segmentation must produce readable text")
        if type(oem) is not int or oem not in {0, 1, 2, 3}:
            raise ValueError("Invalid local OCR engine mode")
        if type(threads) is not int or not 1 <= threads <= 32:
            raise ValueError("OCR threads must be between one and 32")
        if executable is not None and (not isinstance(executable, str) or not executable):
            raise ValueError("Invalid local OCR executable")
        self.tessdata_dir = Path(tessdata_dir).resolve() if tessdata_dir is not None else None
        if self.tessdata_dir is not None and any(c in str(self.tessdata_dir) for c in '"\r\n'):
            raise ValueError("Invalid local OCR data directory")
        self.language = language
        self.executable = executable
        self.psm, self.oem, self.threads = psm, oem, threads
        self.timeout = timeout
        self.min_confidence = min_confidence

    def recognize(self, image: Any) -> OCRResult:
        if (
            type(image.width) is not int
            or type(image.height) is not int
            or image.width <= 0
            or image.height <= 0
            or image.width * image.height > 40_000_000
        ):
            raise OCRError("OCR raster dimensions exceed supported limits")
        if self.tessdata_dir is not None:
            if not self.tessdata_dir.is_dir() or any(
                not (self.tessdata_dir / f"{language}.traineddata").is_file()
                for language in self.language.split("+")
            ):
                raise OCRError("Required local OCR language data are unavailable")
        arguments = [
            self.executable or "tesseract",
            "stdin",
            "stdout",
            "-l",
            self.language,
            "--psm",
            str(self.psm),
            "--oem",
            str(self.oem),
        ]
        if self.tessdata_dir is not None:
            arguments += ["--tessdata-dir", str(self.tessdata_dir)]
        arguments += ["-c", "tessedit_create_tsv=1"]
        try:
            # Direct argv avoids shell quoting bugs and process-global executable
            # settings. Image bytes and TSV stay in pipes, not plaintext temp files.
            with io.BytesIO() as buffer:
                image.save(buffer, format="PNG")
                environment = os.environ.copy()
                environment["OMP_THREAD_LIMIT"] = str(self.threads)
                process = subprocess.run(
                    arguments,
                    input=buffer.getvalue(),
                    capture_output=True,
                    timeout=self.timeout,
                    check=True,
                    env=environment,
                    creationflags=0x08000000 if os.name == "nt" else 0,  # Win32 CREATE_NO_WINDOW
                )
                diagnostics = getattr(process, "stderr", b"").decode("utf-8").lower()
                if any(
                    marker in diagnostics
                    for marker in (
                        "failed loading language",
                        "error opening data file",
                        "could not initialize tesseract",
                        "using psm",
                        "read_params_file: can't open",
                    )
                ):
                    raise ValueError("OCR requested settings were not honored")
        except Exception:
            raise OCRError("Local OCR execution failed") from None
        tokens: list[OCRToken] = []
        try:
            rows = csv.DictReader(io.StringIO(process.stdout.decode("utf-8")), delimiter="\t")
            required = {
                "level",
                "page_num",
                "block_num",
                "par_num",
                "line_num",
                "word_num",
                "left",
                "top",
                "width",
                "height",
                "conf",
                "text",
            }
            if (
                rows.fieldnames is None
                or len(rows.fieldnames) != len(required)
                or set(rows.fieldnames) != required
            ):
                raise ValueError
            for row in rows:
                value = row["text"]
                if (
                    not isinstance(value, str)
                    or None in row
                    or any(row.get(key) is None for key in required)
                ):
                    raise ValueError
                if not value.strip():
                    continue
                confidence = float(row["conf"])
                # Keep low-confidence words: dropping them silently reduces coverage.
                left, top = float(row["left"]), float(row["top"])
                width, height = float(row["width"]), float(row["height"])
                line = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
                if (
                    not all(math.isfinite(v) for v in (confidence, left, top, width, height))
                    or not -1 <= confidence <= 100
                    or not 0 <= left < left + width <= image.width
                    or not 0 <= top < top + height <= image.height
                    or int(row["level"]) != 5
                    or int(row["page_num"]) != 1
                    or any(n < 0 for n in line)
                ):
                    raise ValueError
                tokens.append(
                    OCRToken(
                        str(value),
                        (left, top, left + width, top + height),
                        confidence,
                        line,
                    )
                )
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, UnicodeError):
            raise OCRError("Local OCR returned invalid token metadata") from None
        if not tokens:
            raise OCRError("OCR returned no readable tokens")
        return OCRResult(tuple(tokens), image.width, image.height, "tesseract")


__all__ = ["OCREngine", "OCRError", "OCRResult", "OCRToken", "TesseractOCR"]
