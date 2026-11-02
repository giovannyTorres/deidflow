"""Pixel replacement for single-frame raster images; no overlay-only masks."""

from __future__ import annotations

import math
import os
import tempfile
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from deidflow.readers import MAX_PIXELS, DocumentError, OptionalDependencyError

from .pdf import redact_pdf, verify_pdf


@dataclass(frozen=True)
class ImageRedactionResult:
    output_path: Path
    masks: tuple[tuple[int, int, int, int], ...]
    pixels_verified: bool
    metadata_removed: bool
    # A verified black mask does not establish whether OCR found every item.
    status: str = "REVIEW_REQUIRED"


def verify_pixels(
    path: str | Path,
    masks: Iterable[tuple[int, int, int, int]],
) -> bool:
    """Reopen encoded output and verify solid replacement and metadata removal."""
    try:
        from PIL import Image
    except ImportError:
        raise OptionalDependencyError("Install deidflow[ocr] for image redaction") from None
    try:
        with Image.open(path) as image:
            if image.format != "PNG" or image.mode != "RGB" or image.info or image.getexif():
                return False
            checked = 0
            for box in masks:
                x0, y0, x1, y1 = box
                if not 0 <= x0 < x1 <= image.width or not 0 <= y0 < y1 <= image.height:
                    return False
                with image.crop(box) as region:
                    if any(bounds != (0, 0) for bounds in region.getextrema()):
                        return False
                checked += 1
        return checked > 0
    except Exception:
        return False


def redact_image(
    source: str | Path,
    output: str | Path,
    boxes: Iterable[tuple[float, float, float, float]],
    *,
    padding: int = 2,
    max_bytes: int = 64 * 1024 * 1024,
) -> ImageRedactionResult:
    """Replace pixels, remove ancillary metadata and verify lossless PNG output.

    Boxes use raster coordinates with top-left origin and exclusive right/bottom
    bounds. Multi-frame inputs and output formats other than PNG are rejected.
    The caller must separately re-OCR and scan the actual output before release;
    this operator never reports automatic release approval.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise OptionalDependencyError("Install deidflow[ocr] for image redaction") from None
    src, dst = Path(source), Path(output)
    if src.resolve() == dst.resolve():
        raise DocumentError("Image redaction requires a distinct output path")
    if dst.suffix.lower() != ".png":
        raise DocumentError("Only lossless PNG image output is supported")
    if padding < 0 or max_bytes <= 0:
        raise ValueError("Invalid image redaction limits")
    try:
        if not src.is_file() or src.stat().st_size > max_bytes:
            raise DocumentError("Image input is missing or exceeds the byte limit")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(src) as original:
                if getattr(original, "n_frames", 1) != 1:
                    raise DocumentError("Automatic multi-frame image redaction is unsupported")
                if original.width * original.height > MAX_PIXELS:
                    raise DocumentError("Image pixel limit exceeded")
                masks: list[tuple[int, int, int, int]] = []
                for box in boxes:
                    if len(box) != 4 or not all(math.isfinite(value) for value in box):
                        raise DocumentError("Invalid image mask coordinates")
                    x0, y0, x1, y1 = box
                    if not 0 <= x0 < x1 <= original.width or not 0 <= y0 < y1 <= original.height:
                        raise DocumentError("Image mask is outside the source raster")
                    masks.append(
                        (
                            max(0, math.floor(x0) - padding),
                            max(0, math.floor(y0) - padding),
                            min(original.width, math.ceil(x1) + padding),
                            min(original.height, math.ceil(y1) + padding),
                        )
                    )
                if not masks:
                    raise DocumentError("Image redaction requires at least one explicit mask")
                # A new image prevents EXIF/XMP/comments or original alpha from
                # being propagated into the sanitized encoded output.
                with Image.new("RGB", original.size, "white") as clean:
                    with original.convert("RGBA") as rgba:
                        clean.paste(rgba, mask=rgba.getchannel("A"))
                    draw = ImageDraw.Draw(clean)
                    for x0, y0, x1, y1 in masks:
                        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(0, 0, 0))
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    descriptor, temporary = tempfile.mkstemp(
                        prefix=".deidflow-", suffix=".png", dir=dst.parent
                    )
                    os.close(descriptor)
                    try:
                        clean.save(temporary, format="PNG")
                        if not verify_pixels(temporary, masks):
                            raise DocumentError("Encoded image mask verification failed")
                        os.replace(temporary, dst)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
        return ImageRedactionResult(dst, tuple(masks), True, True)
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("Image redaction failed") from None


__all__ = ["ImageRedactionResult", "redact_image", "verify_pixels", "redact_pdf", "verify_pdf"]
