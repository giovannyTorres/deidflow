"""Explicitly configured, local OCR. Importing this module starts no processes."""

from __future__ import annotations

from dataclasses import dataclass, field
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
        timeout: float = 60,
        min_confidence: float = 50,
    ) -> None:
        if timeout <= 0 or not 0 <= min_confidence <= 100:
            raise ValueError("Invalid OCR limits")
        self.language = language
        self.executable = executable
        self.timeout = timeout
        self.min_confidence = min_confidence

    def recognize(self, image: Any) -> OCRResult:
        try:
            import pytesseract
        except ImportError:
            raise OCRError("Install deidflow[ocr] and a local Tesseract executable") from None
        # Passing a custom executable via process-global pytesseract settings is
        # unsafe under threads. Explicit executables use a lock shared by all
        # adapters, and the prior setting is always restored.
        from ._lock import TESSERACT_LOCK

        try:
            with TESSERACT_LOCK:
                previous = pytesseract.pytesseract.tesseract_cmd
                if self.executable is not None:
                    pytesseract.pytesseract.tesseract_cmd = self.executable
                try:
                    data = pytesseract.image_to_data(
                        image,
                        lang=self.language,
                        output_type=pytesseract.Output.DICT,
                        timeout=self.timeout,
                    )
                finally:
                    pytesseract.pytesseract.tesseract_cmd = previous
        except Exception:
            raise OCRError("Local OCR execution failed") from None
        tokens: list[OCRToken] = []
        for i, value in enumerate(data["text"]):
            if not str(value).strip():
                continue
            confidence = float(data["conf"][i])
            # Do not silently drop low-confidence recognized words. They stay in
            # the graph and force review through the reader's completeness flag.
            left, top = float(data["left"][i]), float(data["top"][i])
            width, height = float(data["width"][i]), float(data["height"][i])
            tokens.append(
                OCRToken(
                    str(value),
                    (left, top, left + width, top + height),
                    confidence,
                    (
                        int(data["block_num"][i]),
                        int(data["par_num"][i]),
                        int(data["line_num"][i]),
                    ),
                )
            )
        if not tokens:
            raise OCRError("OCR returned no readable tokens")
        return OCRResult(tuple(tokens), image.width, image.height, "tesseract")


__all__ = ["OCREngine", "OCRError", "OCRResult", "OCRToken", "TesseractOCR"]
