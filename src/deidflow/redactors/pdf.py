"""Physically remove detected PDF content by rebuilding a lossless raster-only PDF.

The output is written from new RGB pixels and a tiny closed PDF grammar. No
original PDF objects, metadata, text, actions or attachments are copied. This
trades away searchability, vectors, forms, links and document signatures.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, BinaryIO

from deidflow.core import Finding
from deidflow.engine import ReleaseStatus, Result
from deidflow.ocr import OCRError, OCRResult
from deidflow.pdf_runtime import PDFIUM_LOCK
from deidflow.policies import Policy

_SUPPORTED = {"keep", "redact", "suppress"}
_MAX_CHARS = 250_000
_MAX_PIXELS = 40_000_000


class PDFRedactionError(RuntimeError):
    """Sanitized failure; never includes source text or a parser exception."""


class PDFUnsupportedError(PDFRedactionError):
    """A source feature has not been validated for raster removal."""


def _source_digest(path: Path, max_bytes: int) -> str:
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise PDFRedactionError("PDF input is missing or exceeds the byte limit")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(min(1024**2, max_bytes - total + 1)):
            total += len(chunk)
            if total > max_bytes:
                raise PDFRedactionError("PDF input grew beyond the byte limit")
            digest.update(chunk)
    return digest.hexdigest()


def _dependencies() -> tuple[Any, Any, Any, Any]:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
        from PIL import Image, ImageDraw
        from pypdf import PdfReader
    except ImportError:
        raise PDFRedactionError("Install deidflow[pdf,ocr] for local PDF redaction") from None
    return pdfium, Image, ImageDraw, PdfReader


def _policy_supported(policy: Policy, domain: str | None) -> bool:
    rules = [
        policy.default,
        *policy.entities.values(),
        *policy.domains.get(domain or "", {}).values(),
    ]
    return all(rule.action in _SUPPORTED for rule in rules)


def _selected(finding: Finding, policy: Policy, domain: str | None) -> bool:
    rule = policy.rule(finding.entity_type, domain)
    return rule.action != "keep" and (finding.protected or finding.score >= rule.threshold)


def _disallowed(finding: Finding, policy: Policy, domain: str | None) -> bool:
    return (
        policy.rule(finding.entity_type, domain).action != "keep"
        and finding.entity_type not in policy.allow_residual_types
    )


def _box(
    box: tuple[float, float, float, float], width: int, height: int, padding: int
) -> tuple[int, int, int, int]:
    if not all(math.isfinite(value) for value in box):
        raise PDFRedactionError("Invalid raster mask coordinates")
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        raise PDFRedactionError("Empty raster mask coordinates")
    result = (
        max(0, math.floor(x0) - padding),
        max(0, math.floor(y0) - padding),
        min(width, math.ceil(x1) + padding),
        min(height, math.ceil(y1) + padding),
    )
    if not 0 <= result[0] < result[2] <= width or not 0 <= result[1] < result[3] <= height:
        raise PDFRedactionError("Raster mask does not intersect the page")
    return result


def _ocr_text(
    result: OCRResult, size: tuple[int, int]
) -> tuple[str, list[tuple[int, int, tuple[float, float, float, float]]], bool]:
    if (result.width, result.height) != size or not result.tokens:
        raise PDFRedactionError("OCR returned incomplete raster coverage")
    parts: list[str] = []
    spans = []
    offset = 0
    previous = None
    low = False
    for token in result.tokens:
        if (
            not isinstance(token.text, str)
            or not token.text.strip()
            or not math.isfinite(token.confidence)
            or not -1 <= token.confidence <= 100
        ):
            raise PDFRedactionError("OCR returned invalid token metadata")
        x0, y0, x1, y1 = token.bbox
        if (
            not all(math.isfinite(v) for v in token.bbox)
            or not 0 <= x0 < x1 <= size[0]
            or not 0 <= y0 < y1 <= size[1]
        ):
            raise PDFRedactionError("OCR token coordinates exceed the raster")
        if parts:
            separator = " " if token.line == previous else "\n"
            parts.append(separator)
            offset += len(separator)
        start = offset
        parts.append(token.text)
        offset += len(token.text)
        spans.append((start, offset, token.bbox))
        previous = token.line
        low = low or token.confidence < 50
    return "".join(parts), spans, low


def _native_text(textpage: Any, raw: Any) -> tuple[str, list[int]]:
    # PDFium's returned text indices need not equal its internal character
    # indices. Read codepoints one-by-one, retaining the explicit mapping.
    count = textpage.count_chars()
    if count > _MAX_CHARS:
        raise PDFRedactionError("Native PDF character limit exceeded")
    chars, indices = [], []
    for i in range(count):
        value = int(raw.FPDFText_GetUnicode(textpage, i))
        if value == 0:
            continue
        if value > 0x10FFFF or 0xD800 <= value <= 0xDFFF:
            raise PDFRedactionError("Native PDF Unicode mapping is unsupported")
        chars.append(chr(value))
        indices.append(i)
    return "".join(chars), indices


def _native_masks(
    textpage: Any,
    converter: Any,
    text: str,
    indices: list[int],
    findings: list[Finding],
    policy: Policy,
    domain: str | None,
    width: int,
    height: int,
    padding: int,
) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for finding in findings:
        if not _selected(finding, policy, domain):
            continue
        mapped = 0
        for offset in range(finding.start, finding.end):
            if text[offset].isspace():
                continue
            left, bottom, right, top = textpage.get_charbox(indices[offset], loose=True)
            if right <= left or top <= bottom:
                raise PDFRedactionError("Sensitive native glyph lacks reliable geometry")
            points = [
                converter.to_bitmap(x, y)
                for x, y in ((left, bottom), (left, top), (right, bottom), (right, top))
            ]
            box = (
                float(min(p[0] for p in points)),
                float(min(p[1] for p in points)),
                float(max(p[0] for p in points)),
                float(max(p[1] for p in points)),
            )
            boxes.append(_box(box, width, height, padding))
            mapped += 1
        if not mapped:
            raise PDFRedactionError("Sensitive native finding could not be mapped")
    return boxes


def _ocr_masks(
    text: str,
    spans: list[tuple[int, int, tuple[float, float, float, float]]],
    findings: list[Finding],
    policy: Policy,
    domain: str | None,
    width: int,
    height: int,
    padding: int,
) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for finding in findings:
        if not 0 <= finding.start < finding.end <= len(text):
            raise PDFRedactionError("Sensitive OCR finding has invalid offsets")
        if not _selected(finding, policy, domain):
            continue
        matched = [box for start, end, box in spans if start < finding.end and end > finding.start]
        if not matched:
            raise PDFRedactionError("Sensitive OCR finding could not be mapped")
        boxes.extend(_box(box, width, height, padding) for box in matched)
    return boxes


def _blank(image: Any) -> bool:
    return all(low == high == 255 for low, high in image.getextrema())


def _empty_after_masks(image: Any, masks: list[tuple[int, int, int, int]], ImageDraw: Any) -> bool:
    # Empty OCR after removal is accepted only if every nonwhite pixel was in a
    # removed region. A photograph or unreadable text elsewhere cannot pass.
    with image.copy() as remaining:
        draw = ImageDraw.Draw(remaining)
        for x0, y0, x1, y1 in masks:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill="white")
        return _blank(remaining)


class _RasterWriter:
    """A bounded streaming PDF1.4 writer with only RGB image/page objects."""

    def __init__(self, handle: BinaryIO, max_bytes: int) -> None:
        self.handle, self.max_bytes = handle, max_bytes
        self.offsets: dict[int, int] = {}
        self.pages: list[int] = []
        self.next_id = 3
        self._write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        self._object(1, b"<< /Type /Catalog /Pages 2 0 R >>")

    def _write(self, data: bytes) -> None:
        if self.handle.tell() + len(data) > self.max_bytes:
            raise PDFRedactionError("Sanitized PDF output byte limit exceeded")
        self.handle.write(data)

    def _start(self, identifier: int) -> None:
        self.offsets[identifier] = self.handle.tell()
        self._write(f"{identifier} 0 obj\n".encode())

    def _object(self, identifier: int, data: bytes) -> None:
        self._start(identifier)
        self._write(data + b"\nendobj\n")

    def page(self, image: Any, point_size: tuple[float, float]) -> None:
        image_id, length_id, content_id, page_id = range(self.next_id, self.next_id + 4)
        self.next_id += 4
        width, height = image.size
        self._start(image_id)
        self._write(
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {length_id} 0 R >>\nstream\n".encode()
        )
        beginning = self.handle.tell()
        compressor = zlib.compressobj(level=6)
        # Copy one small band at a time, never the document or encoded image.
        for y in range(0, height, 32):
            with image.crop((0, y, width, min(height, y + 32))) as band:
                self._write(compressor.compress(band.tobytes()))
        self._write(compressor.flush())
        length = self.handle.tell() - beginning
        self._write(b"\nendstream\nendobj\n")
        self._object(length_id, str(length).encode())
        w, h = point_size
        commands = f"q\n{w:.8f} 0 0 {h:.8f} 0 0 cm\n/Im0 Do\nQ\n".encode()
        self._object(
            content_id,
            f"<< /Length {len(commands)} >>\nstream\n".encode() + commands + b"endstream",
        )
        self._object(
            page_id,
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.8f} {h:.8f}] /Resources << /XObject << /Im0 {image_id} 0 R >> >> /Contents {content_id} 0 R >>".encode(),
        )
        self.pages.append(page_id)

    def finish(self) -> None:
        kids = " ".join(f"{p} 0 R" for p in self.pages)
        self._object(2, f"<< /Type /Pages /Count {len(self.pages)} /Kids [{kids}] >>".encode())
        beginning = self.handle.tell()
        self._write(f"xref\n0 {self.next_id}\n0000000000 65535 f \n".encode())
        for identifier in range(1, self.next_id):
            self._write(f"{self.offsets[identifier]:010d} 00000 n \n".encode())
        self._write(
            f"trailer\n<< /Size {self.next_id} /Root 1 0 R >>\nstartxref\n{beginning}\n%%EOF\n".encode()
        )


def _preflight(
    path: Path, PdfReader: Any, max_pages: int, max_bytes: int
) -> tuple[Any, list[tuple[float, float]]]:
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise PDFRedactionError("PDF input is missing or exceeds the byte limit")
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        raise PDFUnsupportedError("Encrypted PDF redaction is unsupported")
    root = reader.trailer["/Root"]
    if "/Perms" in root or "/AcroForm" in root:
        raise PDFUnsupportedError("PDF signatures and interactive forms are unsupported")
    if not 1 <= len(reader.pages) <= max_pages:
        raise PDFRedactionError("PDF page count exceeds configured limits")
    dimensions = []
    for page in reader.pages:
        media, crop = tuple(map(float, page.mediabox)), tuple(map(float, page.cropbox))
        if (
            page.rotation % 360
            or media != crop
            or media[:2] != (0.0, 0.0)
            or float(page.get("/UserUnit", 1)) != 1
        ):
            raise PDFUnsupportedError("Rotated, cropped or scaled PDF geometry is unsupported")
        if any(ref.get_object().get("/Subtype") == "/Widget" for ref in page.get("/Annots", [])):
            raise PDFUnsupportedError("Interactive PDF widgets are unsupported")
        width, height = media[2:]
        if not all(math.isfinite(v) and v > 0 for v in (width, height)):
            raise PDFRedactionError("Invalid PDF page dimensions")
        dimensions.append((width, height))
    return None, dimensions


def _verify_encoded(path: Path, receipts: list[dict[str, Any]], PdfReader: Any) -> None:
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted or set(reader.trailer) != {"/Size", "/Root"}:
        raise PDFRedactionError("Sanitized PDF trailer verification failed")
    expected_size = 3 + 4 * len(receipts)
    if (
        reader.trailer["/Size"] != expected_size
        or reader.xref_objStm
        or set(reader.xref.get(0, {})) != set(range(1, expected_size))
        or any(
            generation not in {0, 65535} and entries for generation, entries in reader.xref.items()
        )
    ):
        raise PDFRedactionError("Sanitized PDF contains unexpected indirect objects")
    root = reader.trailer["/Root"]
    if set(root) != {"/Type", "/Pages"} or root["/Type"] != "/Catalog":
        raise PDFRedactionError("Sanitized PDF catalog verification failed")
    pages = root["/Pages"]
    if (
        set(pages) != {"/Type", "/Count", "/Kids"}
        or pages.get("/Type") != "/Pages"
        or pages.get("/Count") != len(receipts)
        or len(pages["/Kids"]) != len(receipts)
        or len(reader.pages) != len(receipts)
    ):
        raise PDFRedactionError("Sanitized PDF page-tree verification failed")
    for page, receipt in zip(reader.pages, receipts, strict=True):
        if set(page) != {"/Type", "/Parent", "/MediaBox", "/Resources", "/Contents"}:
            raise PDFRedactionError("Sanitized PDF contains unexpected page objects")
        resources = page["/Resources"]
        if set(resources) != {"/XObject"} or set(resources["/XObject"]) != {"/Im0"}:
            raise PDFRedactionError("Sanitized PDF contains unexpected resources")
        image = resources["/XObject"]["/Im0"].get_object()
        if (
            set(image)
            - {
                "/Type",
                "/Subtype",
                "/Width",
                "/Height",
                "/ColorSpace",
                "/BitsPerComponent",
                "/Filter",
                "/Length",
            }
            or image.get("/Subtype") != "/Image"
            or image.get("/ColorSpace") != "/DeviceRGB"
            or image.get("/BitsPerComponent") != 8
            or image.get("/Filter") != "/FlateDecode"
        ):
            raise PDFRedactionError("Sanitized PDF image schema verification failed")
        width, height = receipt["raster_width"], receipt["raster_height"]
        if image["/Width"] != width or image["/Height"] != height:
            raise PDFRedactionError("Sanitized PDF raster dimensions changed")
        data = image.get_data()
        if (
            len(data) != width * height * 3
            or hashlib.sha256(data).hexdigest() != receipt["raster_sha256"]
        ):
            raise PDFRedactionError("Sanitized PDF actual raster verification failed")
        # The content stream must contain exactly the newly authored image draw.
        w, h = receipt["page_width"], receipt["page_height"]
        expected = f"q\n{w:.8f} 0 0 {h:.8f} 0 0 cm\n/Im0 Do\nQ\n".encode()
        if page.get_contents().get_data() != expected or page.extract_text():
            raise PDFRedactionError("Sanitized PDF contains unexpected content streams")
        # Verify every removed source region in decoded *output* image bytes.
        for x0, y0, x1, y1 in receipt["masks"]:
            for y in range(y0, y1):
                start = (y * width + x0) * 3
                if any(data[start : start + (x1 - x0) * 3]):
                    raise PDFRedactionError("Sanitized PDF mask pixels were not replaced")
        # EncodedStreamObject caches the full decoded RGB raster. Clear that
        # cache explicitly so verification does not retain every page's pixels.
        image.decoded_self = None
        del data


def _scan_page(
    image: Any, engine: Any
) -> tuple[str, list[tuple[int, int, tuple[float, float, float, float]]], list[Finding], bool, int]:
    if _blank(image):
        return "", [], [], False, 0
    result = engine.ocr.recognize(image)
    text, spans, _ = _ocr_text(result, image.size)
    threshold = getattr(engine.ocr, "min_confidence", 50)
    low = any(token.confidence < threshold for token in result.tokens)
    return text, spans, engine.scan_ocr_text(text), low, len(result.tokens)


def _verification_image(image: Any, masks: list[tuple[int, int, int, int]], ImageDraw: Any) -> Any:
    """Whiten proven constant *rendered* regions for OCR, never the output PDF.

    OCR can hallucinate letters in black bars. A region is excluded only after
    checking every actual re-rendered pixel is RGB zero. Intent-only masks,
    altered pixels and incomplete removals cannot pass this proof.
    """
    clean = image.copy()
    draw = ImageDraw.Draw(clean)
    try:
        for box in masks:
            with image.crop(box) as region:
                if any(bounds != (0, 0) for bounds in region.getextrema()):
                    raise PDFRedactionError("Rendered PDF mask is not an actual solid removal")
            x0, y0, x1, y1 = box
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill="white")
        return clean
    except Exception:
        clean.close()
        raise


def _verify_rendered(
    path: Path,
    engine: Any,
    policy: Policy,
    domain: str | None,
    dpi: int,
    receipts: list[dict[str, Any]],
    pdfium: Any,
    ImageDraw: Any,
) -> tuple[list[Finding], list[str]]:
    residual: list[Finding] = []
    issues: list[str] = []
    with pdfium.PdfDocument(path) as document:
        if len(document) != len(receipts):
            raise PDFRedactionError("Sanitized PDF rendered page count changed")
        for page, receipt in zip(document, receipts, strict=True):
            bitmap = page.render(
                scale=dpi / 72,
                draw_annots=True,
                may_draw_forms=False,
                fill_color=(255, 255, 255, 255),
            )
            try:
                with bitmap.to_pil() as raster, raster.convert("RGB") as image:
                    if image.size != (receipt["raster_width"], receipt["raster_height"]):
                        raise PDFRedactionError("Sanitized PDF render geometry changed")
                    with _verification_image(image, receipt["masks"], ImageDraw) as ocr_image:
                        try:
                            _, _, found, low, count = _scan_page(ocr_image, engine)
                        except OCRError:
                            if not receipt["all_unmasked_pixels_white"] or not _blank(ocr_image):
                                raise PDFRedactionError(
                                    "Sanitized PDF OCR verification failed"
                                ) from None
                            found, low, count = [], False, 0
                    receipt["actual_solid_regions_excluded_from_ocr"] = len(receipt["masks"])
                    receipt["verification_ocr_tokens"] = count
                    receipt["rendered_verification"] = True
                    if low and "LOW_OUTPUT_OCR_CONFIDENCE" not in issues:
                        issues.append("LOW_OUTPUT_OCR_CONFIDENCE")
                    residual.extend(f for f in found if _disallowed(f, policy, domain))
                    residual = residual[:100]
            finally:
                bitmap.close()
                page.close()
    return residual, issues


def redact_pdf(
    source: str | Path,
    output: str | Path,
    *,
    engine: Any,
    policy: Policy | None = None,
    dpi: int = 216,
    padding: int = 3,
    max_pages: int = 1000,
    max_bytes: int | None = None,
    memory_budget_mb: int | None = None,
    domain: str | None = None,
) -> Result:
    """Rebuild and independently verify an unsearchable image-only local PDF.

    Only redact/suppress/keep policy actions are supported. Unlike the ordinary
    text policy, the PDF default physically removes every selected finding.
    Nonempty OCR is mandatory except for an exactly white source page or when
    verified masks cover every nonwhite pixel. No automatic model download occurs.
    """
    policy = policy or Policy.strict_pdf()
    src, dst = Path(source), Path(output)
    if src.resolve() == dst.resolve() or dst.suffix.lower() != ".pdf":
        raise ValueError("PDF redaction requires a distinct .pdf output path")
    if dst.exists():
        raise FileExistsError("PDF output already exists")
    if (
        type(dpi) is not int
        or not 72 <= dpi <= 600
        or type(padding) is not int
        or not 1 <= padding <= 32
        or type(max_pages) is not int
        or not 1 <= max_pages <= 1000
    ):
        raise ValueError("Invalid PDF redaction limits")
    if not _policy_supported(policy, domain):
        return Result(ReleaseStatus.UNSUPPORTED, issues=["PDF_POLICY_ACTION_UNSUPPORTED"])
    if engine.ocr is None:
        return Result(ReleaseStatus.BLOCKED, issues=["LOCAL_OCR_REQUIRED"])
    limit = max_bytes if max_bytes is not None else engine.max_bytes
    budget = memory_budget_mb if memory_budget_mb is not None else engine.memory_budget_mb
    if type(limit) is not int or limit < 1 or type(budget) is not int or budget < 16:
        raise ValueError("Invalid PDF byte or memory limit")
    temporary: Path | None = None
    receipts: list[dict[str, Any]] = []
    issues: list[str] = []
    originals: list[Finding] = []
    counts: Counter[str] = Counter()
    try:
        pdfium, Image, ImageDraw, PdfReader = _dependencies()
        with PDFIUM_LOCK:
            source_sha256 = _source_digest(src, limit)
            _, dimensions = _preflight(src, PdfReader, max_pages, limit)
            dst.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=".deidflow-", suffix=".pdf", dir=dst.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle, pdfium.PdfDocument(src) as document:
                if len(document) != len(dimensions):
                    raise PDFRedactionError("Independent PDF parsers disagree on page count")
                writer = _RasterWriter(handle, max_bytes=limit * 4)
                for number, (point_width, point_height) in enumerate(dimensions, 1):
                    width, height = (
                        math.ceil(point_width * dpi / 72),
                        math.ceil(point_height * dpi / 72),
                    )
                    if width * height > _MAX_PIXELS or width * height * 16 > budget * 1024**2:
                        raise PDFRedactionError("PDF page exceeds configured raster memory budget")
                    page = document[number - 1]
                    textpage = page.get_textpage()
                    bitmap = None
                    try:
                        native, indices = _native_text(textpage, pdfium.raw)
                        native_findings = engine.scan_text(native) if native else []
                        bitmap = page.render(
                            scale=dpi / 72,
                            draw_annots=True,
                            may_draw_forms=False,
                            fill_color=(255, 255, 255, 255),
                        )
                        with (
                            bitmap.to_pil() as raster,
                            Image.new("RGB", raster.size, "white") as image,
                        ):
                            image.paste(raster)
                            text, spans, ocr_findings, low, token_count = _scan_page(image, engine)
                            if low and "LOW_SOURCE_OCR_CONFIDENCE" not in issues:
                                issues.append("LOW_SOURCE_OCR_CONFIDENCE")
                            findings = native_findings + ocr_findings
                            originals.extend(findings[: max(0, 100 - len(originals))])
                            counts.update(f.entity_type for f in findings)
                            if (
                                any(f.score < policy.review_below for f in findings)
                                and "UNCERTAIN_SOURCE_FINDINGS" not in issues
                            ):
                                issues.append("UNCERTAIN_SOURCE_FINDINGS")
                            if (
                                any("window_boundary" in f.context for f in findings)
                                and "UNRESOLVED_MODEL_WINDOW_BOUNDARY" not in issues
                            ):
                                issues.append("UNRESOLVED_MODEL_WINDOW_BOUNDARY")
                            if (
                                any(
                                    policy.rule(f.entity_type, domain).action != "keep"
                                    and not _selected(f, policy, domain)
                                    for f in findings
                                )
                                and "SOURCE_FINDING_BELOW_POLICY_THRESHOLD" not in issues
                            ):
                                issues.append("SOURCE_FINDING_BELOW_POLICY_THRESHOLD")
                            masks = _native_masks(
                                textpage,
                                bitmap.get_posconv(page),
                                native,
                                indices,
                                native_findings,
                                policy,
                                domain,
                                image.width,
                                image.height,
                                padding,
                            )
                            masks += _ocr_masks(
                                text,
                                spans,
                                ocr_findings,
                                policy,
                                domain,
                                image.width,
                                image.height,
                                padding,
                            )
                            masks = sorted(set(masks))
                            draw = ImageDraw.Draw(image)
                            for x0, y0, x1, y1 in masks:
                                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(0, 0, 0))
                            receipt = {
                                "page": number,
                                "page_width": point_width,
                                "page_height": point_height,
                                "raster_width": image.width,
                                "raster_height": image.height,
                                "raster_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                                "masks": masks,
                                "native_findings": len(native_findings),
                                "ocr_findings": len(ocr_findings),
                                "source_ocr_tokens": token_count,
                                "all_unmasked_pixels_white": _empty_after_masks(
                                    image, masks, ImageDraw
                                ),
                            }
                            writer.page(image, (point_width, point_height))
                            receipts.append(receipt)
                    finally:
                        if bitmap is not None:
                            bitmap.close()
                        textpage.close()
                        page.close()
                writer.finish()
            _verify_encoded(temporary, receipts, PdfReader)
            residual, verification_issues = _verify_rendered(
                temporary, engine, policy, domain, dpi, receipts, pdfium, ImageDraw
            )
            result = engine._gate(
                policy=policy,
                residual=residual,
                original=originals,
                issues=issues + verification_issues,
                domain=domain,
            )
            result.records = len(receipts)
            result.audit.update(
                {
                    "format": "pdf",
                    "pdf_mode": "lossless_raster_rebuild",
                    "dpi": dpi,
                    "pages": len(receipts),
                    "masks": sum(len(r["masks"]) for r in receipts),
                    "source_findings_by_type": dict(counts),
                    "page_receipts": receipts,
                    "text_layer_removed": True,
                    "original_objects_copied": False,
                    "encoded_pixels_verified": True,
                    "output_rerendered_and_ocr_verified": True,
                    "source_sha256": source_sha256,
                }
            )
            if result.status == ReleaseStatus.BLOCKED:
                return result
            if _source_digest(src, limit) != source_sha256:
                return Result(ReleaseStatus.BLOCKED, issues=["SOURCE_CHANGED_DURING_PROCESSING"])
            with temporary.open("rb") as handle:
                result.audit["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
            os.link(temporary, dst)
            result.output_path = dst
            return result
    except PDFUnsupportedError:
        return Result(
            ReleaseStatus.UNSUPPORTED,
            issues=["PDF_SOURCE_FEATURE_UNSUPPORTED"],
            records=len(receipts),
        )
    except (PDFRedactionError, OCRError):
        return Result(
            ReleaseStatus.BLOCKED,
            issues=["PDF_REDACTION_OR_VERIFICATION_FAILED"],
            records=len(receipts),
        )
    except Exception:
        return Result(
            ReleaseStatus.BLOCKED, issues=["PDF_PROCESSING_FAILED"], records=len(receipts)
        )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_pdf(
    source: str | Path,
    *,
    engine: Any,
    policy: Policy | None = None,
    dpi: int = 216,
    domain: str | None = None,
) -> Result:
    """Standalone output verification is review-only without an internal receipt.

    This does not trust placeholder-looking text or a caller-provided declaration
    of prior masking. The redaction function verifies its candidate separately.
    """
    policy = policy or Policy.strict_pdf()
    if engine.ocr is None:
        return Result(ReleaseStatus.BLOCKED, issues=["LOCAL_OCR_REQUIRED"])
    if type(dpi) is not int or not 72 <= dpi <= 600:
        raise ValueError("Invalid PDF verification DPI")
    try:
        pdfium, _, _, PdfReader = _dependencies()
        with PDFIUM_LOCK:
            _, dimensions = _preflight(
                Path(source), PdfReader, getattr(engine, "pdf_max_pages", 1000), engine.max_bytes
            )
            residual: list[Finding] = []
            issues = ["PDF_TRANSFORMATION_RECEIPT_REQUIRED"]
            with pdfium.PdfDocument(source) as document:
                for index, (w, h) in enumerate(dimensions):
                    if (
                        math.ceil(w * dpi / 72) * math.ceil(h * dpi / 72) * 16
                        > engine.memory_budget_mb * 1024**2
                    ):
                        raise PDFRedactionError("PDF verification exceeds raster memory budget")
                    page = document[index]
                    bitmap = page.render(
                        scale=dpi / 72,
                        draw_annots=True,
                        may_draw_forms=False,
                        fill_color=(255, 255, 255, 255),
                    )
                    try:
                        with bitmap.to_pil() as raster, raster.convert("RGB") as image:
                            _, _, found, low, _ = _scan_page(image, engine)
                            if low and "LOW_OUTPUT_OCR_CONFIDENCE" not in issues:
                                issues.append("LOW_OUTPUT_OCR_CONFIDENCE")
                            residual.extend(f for f in found if _disallowed(f, policy, domain))
                            residual = residual[:100]
                    finally:
                        bitmap.close()
                        page.close()
            result = engine._gate(policy=policy, residual=residual, issues=issues, domain=domain)
            result.records = len(dimensions)
            result.output_path = Path(source)
            return result
    except Exception:
        return Result(ReleaseStatus.BLOCKED, issues=["PDF_VERIFICATION_FAILED"])


__all__ = ["PDFRedactionError", "redact_pdf", "verify_pdf"]
