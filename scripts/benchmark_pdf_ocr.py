"""Real local Spanish OCR and raster-rebuilt PDF evaluation.

Assets are generated locally. Inference denies Python DNS/connect access and
does not install/download Tesseract or language data. Small-repeat and full-scale
timings are deliberately separate. Synthetic gold values never enter result logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import statistics
import subprocess
import time
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from deidflow import DeidEngine, Policy, Rule
from deidflow.benchmarks.runner import machine_metadata, measure, offline_network
from deidflow.validators import clabe_check_digit


@dataclass(frozen=True)
class GoldValue:
    entity_type: str
    value: str


@dataclass(frozen=True)
class PageCase:
    identifier: str
    lines: tuple[str, ...]
    gold: tuple[GoldValue, ...]
    utility: str
    degradation: str = "clean"

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def edit_distance(reference: Sequence[Any], observed: Sequence[Any]) -> int:
    """Exact Levenshtein distance with O(min(n,m)) additional memory."""
    if len(reference) < len(observed):
        reference, observed = observed, reference
    previous = list(range(len(observed) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(observed, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def transcription_metrics(reference: str, observed: str) -> dict[str, Any]:
    reference, observed = normalized(reference), normalized(observed)
    chars = edit_distance(reference, observed)
    words = edit_distance(reference.split(), observed.split())
    return {
        "character_errors": chars,
        "reference_characters": len(reference),
        "cer": chars / max(1, len(reference)),
        "word_errors": words,
        "reference_words": len(reference.split()),
        "wer": words / max(1, len(reference.split())),
    }


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    point = (len(values) - 1) * quantile
    lo, hi = math.floor(point), math.ceil(point)
    return values[lo] + (values[hi] - values[lo]) * (point - lo)


def page_cases(count: int, *, seed: int = 1729, challenge: bool = False) -> list[PageCase]:
    if count < 1:
        raise ValueError("At least one page is required")
    rng = random.Random(seed)
    output = []
    names = ("María Ejemplo Torres", "José Prueba Márquez", "Lucía Ficticia López")
    for index in range(count):
        name = names[index % len(names)]
        email = f"paciente.{index:06d}@example.test"
        prefix = f"002180{index:011d}"
        clabe = prefix + clabe_check_digit(prefix)
        customer = f"CLI-{index:06d}"
        amount = f"{1234 + index}.50 MXN"
        address = f"Calle Luna {14 + index}\nColonia Centro\nCP 06000"
        lines = (
            "Documento clínico sintético para pruebas locales",
            f"Paciente: {name}",
            f"Correo: {email}",
            "Teléfono: +52 55 1234 5678",
            "CURP: RACW050729MMCSHNA2",
            "RFC: GODE561231GR8",
            f"CLABE: {clabe}",
            f"Cliente: {customer}",
            f"Domicilio: Calle Luna {14 + index}",
            "Colonia Centro",
            "CP 06000",
            "Diagnóstico: diabetes",
            f"Importe autorizado: {amount}",
            "Contenido ficticio; ninguna identidad ha sido confirmada.",
        )
        gold = (
            GoldValue("PERSON", name),
            GoldValue("EMAIL", email),
            GoldValue("PHONE", "+52 55 1234 5678"),
            GoldValue("CURP", "RACW050729MMCSHNA2"),
            GoldValue("RFC", "GODE561231GR8"),
            GoldValue("CLABE", clabe),
            GoldValue("CUSTOMER_ID", customer),
            GoldValue("ADDRESS", address),
            GoldValue("DIAGNOSIS", "diabetes"),
        )
        degradation = rng.choice(("blur", "low_contrast", "skew")) if challenge else "clean"
        output.append(PageCase(f"page-{index:04d}", lines, gold, amount, degradation))
    return output


def _scanned_image(case: PageCase, *, dpi: int, seed: int):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    width, height = round(612 * dpi / 72), round(792 * dpi / 72)
    background, foreground = (255, 0) if case.degradation != "low_contrast" else (245, 160)
    image = Image.new("RGB", (width, height), (background,) * 3)
    font = ImageFont.truetype(str(fixture_font()), round(12 * dpi / 72))
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(case.lines):
        draw.text(
            (round(45 * dpi / 72), round((55 + index * 26) * dpi / 72)),
            line,
            font=font,
            fill=(foreground,) * 3,
        )
    if case.degradation == "blur":
        result = image.filter(ImageFilter.GaussianBlur(1.6))
        image.close()
        image = result
    elif case.degradation == "skew":
        rng = random.Random(seed)
        rotated = image.rotate(1.5, fillcolor="white", resample=Image.Resampling.BICUBIC)
        image.close()
        image = rotated
        draw = ImageDraw.Draw(image)
        for _ in range(500):
            x, y = rng.randrange(width), rng.randrange(height)
            draw.point((x, y), fill=(100, 100, 100))
    return image


def fixture_font() -> Path:
    alternatives = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    )
    font = next((path for path in alternatives if path.is_file()), None)
    if font is None:
        raise RuntimeError("A local Unicode TrueType font is required for scanned fixtures")
    return font


def gold_word_boxes(
    case: PageCase, *, scanned: bool, dpi: int
) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Independent drawn-word geometry, before detector/OCR selection.

    Boxes are tightened against actual original ink during output verification.
    This prevents OCR transcription errors from being mistaken for deletion.
    """
    import math

    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfbase.pdfmetrics import getAscentDescent, stringWidth

    width, height = round(612 * dpi / 72), round(792 * dpi / 72)
    font = ImageFont.truetype(str(fixture_font()), round(12 * dpi / 72)) if scanned else None
    ascent, descent = getAscentDescent("Helvetica", 12)
    output = []
    for gold in case.gold:
        for segment in gold.value.splitlines():
            for line_number, line in enumerate(case.lines):
                start = line.find(segment)
                if start < 0:
                    continue
                for word_match in re.finditer(r"\S+", segment):
                    prefix = line[: start + word_match.start()]
                    word = word_match.group()
                    if scanned:
                        with Image.new("RGB", (1, 1)) as scratch:
                            draw = ImageDraw.Draw(scratch)
                            x = round(45 * dpi / 72) + font.getlength(prefix)
                            y = round((55 + line_number * 26) * dpi / 72)
                            box = draw.textbbox((x, y), word, font=font)
                    else:
                        x0 = (45 + stringWidth(prefix, "Helvetica", 12)) * dpi / 72
                        x1 = x0 + stringWidth(word, "Helvetica", 12) * dpi / 72
                        baseline = 737 - line_number * 26
                        box = (
                            x0,
                            (792 - baseline - ascent) * dpi / 72,
                            x1,
                            (792 - baseline - descent) * dpi / 72,
                        )
                    if scanned and case.degradation == "skew":
                        theta = math.radians(1.5)
                        cx, cy = width / 2, height / 2
                        points = [
                            (
                                math.cos(theta) * (x - cx) + math.sin(theta) * (y - cy) + cx,
                                -math.sin(theta) * (x - cx) + math.cos(theta) * (y - cy) + cy,
                            )
                            for x in (box[0], box[2])
                            for y in (box[1], box[3])
                        ]
                        box = (
                            min(p[0] for p in points),
                            min(p[1] for p in points),
                            max(p[0] for p in points),
                            max(p[1] for p in points),
                        )
                    output.append(
                        (
                            gold.entity_type,
                            (
                                max(0, math.floor(box[0]) - 1),
                                max(0, math.floor(box[1]) - 1),
                                min(width, math.ceil(box[2]) + 1),
                                min(height, math.ceil(box[3]) + 1),
                            ),
                        )
                    )
                break
    return output


def verify_gold_pixels(
    source: Path, output: Path, cases: Sequence[PageCase], *, kind: str, dpi: int
) -> dict[str, Any]:
    """Check ground-truth word ink independently of OCR and detector receipts."""
    import pypdfium2 as pdfium

    checked: Counter[str] = Counter()
    masked: Counter[str] = Counter()
    indeterminate = 0
    worst = 1.0
    with pdfium.PdfDocument(source) as original, pdfium.PdfDocument(output) as redacted:
        for number, case in enumerate(cases):
            with closing(original[number]) as before_page, closing(redacted[number]) as after_page:
                with (
                    closing(before_page.render(scale=dpi / 72)) as before_bitmap,
                    closing(after_page.render(scale=dpi / 72)) as after_bitmap,
                ):
                    with (
                        before_bitmap.to_pil().convert("L") as before,
                        after_bitmap.to_pil().convert("L") as after,
                    ):
                        scanned = kind in {"scanned", "scanned-challenge"} or (
                            kind == "mixed" and number % 2 == 1
                        )
                        for entity_type, box in gold_word_boxes(case, scanned=scanned, dpi=dpi):
                            with before.crop(box) as region:
                                ink = region.point(lambda pixel: 255 if pixel < 210 else 0)
                                ink_box = ink.getbbox()
                                ink.close()
                            if ink_box is None:
                                indeterminate += 1
                                continue
                            actual = (
                                box[0] + ink_box[0],
                                box[1] + ink_box[1],
                                box[0] + ink_box[2],
                                box[1] + ink_box[3],
                            )
                            with after.crop(actual) as region:
                                histogram = region.histogram()
                                black_fraction = sum(histogram[:16]) / max(
                                    1, region.width * region.height
                                )
                            checked[entity_type] += 1
                            masked[entity_type] += int(black_fraction >= 0.995)
                            worst = min(worst, black_fraction)
    return {
        "gold_words_checked": sum(checked.values()),
        "gold_words_opaque_black": sum(masked.values()),
        "unmasked_gold_word_regions": sum(checked.values()) - sum(masked.values()),
        "indeterminate_gold_word_regions": indeterminate,
        "minimum_black_pixel_fraction": worst,
        "gold_word_mask_rate_by_type": {
            kind: masked[kind] / count for kind, count in checked.items()
        },
        "passed": bool(checked)
        and sum(checked.values()) == sum(masked.values())
        and not indeterminate,
        "definition": "Known drawn field word boxes tightened to source ink; actual rerendered output word rectangle must be >=99.5% near-black. Independent of OCR matching. This is fixture-specific geometry, not general visual privacy proof.",
    }


def generate_pdf(
    path: Path, cases: Sequence[PageCase], *, kind: str, dpi: int = 216, seed: int = 1729
) -> None:
    """Generate native/scanned/mixed fixtures without copying customer material."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    if kind not in {"native", "scanned", "mixed"}:
        raise ValueError("Unknown PDF fixture type")
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), pagesize=(612, 792), invariant=1, pageCompression=1)
    canvas.setTitle("Synthetic local privacy benchmark")
    canvas.setAuthor("metadata-secret@example.test")
    for index, case in enumerate(cases):
        if kind == "native" or (kind == "mixed" and index % 2 == 0):
            canvas.setFont("Helvetica", 12)
            for line_number, line in enumerate(case.lines):
                canvas.drawString(45, 737 - line_number * 26, line)
        else:
            with _scanned_image(case, dpi=dpi, seed=seed + index) as image:
                canvas.drawImage(ImageReader(image), 0, 0, width=612, height=792)
        canvas.showPage()
    canvas.save()


def recognize_pages(
    path: Path, engine: DeidEngine, *, dpi: int, failed_pages: list[int] | None = None
) -> tuple[list[str], list[float], list[float]]:
    import pypdfium2 as pdfium

    from deidflow.ocr import OCRError

    text, latencies, confidences = [], [], []
    with pdfium.PdfDocument(path) as document:
        for number in range(len(document)):
            start = time.perf_counter()
            with closing(document[number]) as page:
                with closing(page.render(scale=dpi / 72)) as bitmap:
                    with bitmap.to_pil().convert("RGB") as image:
                        try:
                            result = engine.ocr.recognize(image)
                        except OCRError:
                            if failed_pages is None:
                                raise
                            failed_pages.append(number + 1)
                            text.append("")
                            latencies.append(time.perf_counter() - start)
                            continue
                        parts = []
                        previous_line = None
                        for token in result.tokens:
                            if parts:
                                parts.append(" " if token.line == previous_line else "\n")
                            parts.append(token.text)
                            previous_line = token.line
                            confidences.append(token.confidence)
                        text.append("".join(parts))
            latencies.append(time.perf_counter() - start)
    return text, latencies, confidences


def gold_value_metrics(
    cases: Sequence[PageCase], texts: Sequence[str], engine: DeidEngine
) -> dict[str, Any]:
    if len(cases) != len(texts):
        raise ValueError("Page alignment differs from ground truth")
    total_by_type: Counter[str] = Counter()
    found_by_type: Counter[str] = Counter()
    ocr_recovered_by_type: Counter[str] = Counter()
    predictions, matched = 0, 0
    for case, text in zip(cases, texts, strict=True):
        findings = engine.scan_ocr_text(text)
        predictions += len(findings)
        used = set()
        for gold in case.gold:
            total_by_type[gold.entity_type] += 1
            value = normalized(gold.value)
            if value in normalized(text):
                ocr_recovered_by_type[gold.entity_type] += 1
            for index, finding in enumerate(findings):
                if (
                    index not in used
                    and finding.entity_type == gold.entity_type
                    and normalized(text[finding.start : finding.end]) == value
                ):
                    used.add(index)
                    matched += 1
                    found_by_type[gold.entity_type] += 1
                    break
    total = sum(total_by_type.values())
    precision, recall = matched / max(1, predictions), matched / max(1, total)
    return {
        "gold_entities": total,
        "predicted_entities": predictions,
        "matched_gold_values": matched,
        "gold_value_precision": precision,
        "gold_value_recall": recall,
        "gold_value_f1": 2 * precision * recall / max(1e-15, precision + recall),
        "recall_by_type": {
            kind: found_by_type[kind] / count for kind, count in total_by_type.items()
        },
        "ocr_exact_value_recovery_by_type": {
            kind: ocr_recovered_by_type[kind] / count for kind, count in total_by_type.items()
        },
        "definition": "One-to-one category + NFC/whitespace-normalized whole value matching on OCR text; not original-layout exact-span F1",
    }


def evaluate_transcription(cases: Sequence[PageCase], texts: Sequence[str]) -> dict[str, Any]:
    if len(cases) != len(texts):
        raise ValueError("Page alignment differs from ground truth")
    metrics = [
        transcription_metrics(case.text, text) for case, text in zip(cases, texts, strict=True)
    ]
    total_chars = sum(metric["reference_characters"] for metric in metrics)
    total_words = sum(metric["reference_words"] for metric in metrics)
    return {
        "character_error_rate": sum(metric["character_errors"] for metric in metrics)
        / max(1, total_chars),
        "word_error_rate": sum(metric["word_errors"] for metric in metrics) / max(1, total_words),
        "reference_characters": total_chars,
        "reference_words": total_words,
        "normalization": "Unicode NFC, whitespace collapsed, case and punctuation retained",
    }


def verify_gold_output(
    path: Path, cases: Sequence[PageCase], engine: DeidEngine, *, dpi: int, source: Path, kind: str
) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(path, strict=True)
    dangerous = {
        "/AcroForm",
        "/Names",
        "/Metadata",
        "/OpenAction",
        "/AA",
        "/Outlines",
        "/OCProperties",
    }
    root = reader.trailer["/Root"]
    retained_objects = sorted(dangerous.intersection(root))
    text_pages = sum(bool(page.extract_text()) for page in reader.pages)
    annotations = sum(bool(page.get("/Annots")) for page in reader.pages)
    metadata = " ".join(str(value) for value in (reader.metadata or {}).values())
    metadata_leaks = int("metadata-secret@example.test" in metadata)
    # Decompressed non-image streams must not carry a copy of original strings.
    stream_leaks = 0
    source_values = {gold.value for case in cases for gold in case.gold}
    for page in reader.pages:
        content = page.get_contents()
        decoded = content.get_data() if content else b""
        stream_leaks += sum(value.encode("utf-8") in decoded for value in source_values)
    failed_pages: list[int] = []
    texts, latencies, _ = recognize_pages(path, engine, dpi=dpi, failed_pages=failed_pages)
    residual = Counter()
    utility_preserved = 0
    for case, text in zip(cases, texts, strict=True):
        for gold in case.gold:
            if normalized(gold.value) in normalized(text):
                residual[gold.entity_type] += 1
        utility_preserved += int(case.utility in normalized(text))
    pixels = verify_gold_pixels(source, path, cases, kind=kind, dpi=dpi)
    return {
        "pages": len(reader.pages),
        "expected_pages": len(cases),
        "native_text_pages": text_pages,
        "annotation_pages": annotations,
        "forbidden_catalog_keys": retained_objects,
        "metadata_gold_leaks": metadata_leaks,
        "original_values_in_page_content_streams": stream_leaks,
        "residual_gold_values_in_output_ocr": sum(residual.values()) if not failed_pages else None,
        "residual_gold_values_observed_in_readable_output_pages": sum(residual.values()),
        "output_ocr_failed_pages": failed_pages,
        "output_ocr_complete": not failed_pages,
        "residual_gold_by_type": dict(residual),
        "gold_values_checked": sum(len(case.gold) for case in cases),
        "utility_amount_pages_preserved": utility_preserved,
        "independent_gold_pixels": pixels,
        "output_ocr_page_latency_p50_seconds": percentile(latencies, 0.5),
        "output_ocr_page_latency_p95_seconds": percentile(latencies, 0.95),
        "passed": not failed_pages
        and pixels["passed"]
        and len(reader.pages) == len(cases)
        and not any(
            (
                text_pages,
                annotations,
                retained_objects,
                metadata_leaks,
                stream_leaks,
                sum(residual.values()),
            )
        ),
        "limitations": "Gold OCR absence is not absence of all PII; actual embedded pixel/hash verification is performed by library independently",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    from deidflow.ocr import TesseractOCR
    from deidflow.redactors.pdf import redact_pdf

    args.work.mkdir(parents=True, exist_ok=True)
    ocr = TesseractOCR(
        language=args.language,
        executable=str(args.executable),
        tessdata_dir=str(args.tessdata),
        psm=args.psm,
        oem=1,
        min_confidence=50,
        timeout=60,
    )
    engine = DeidEngine(ocr=ocr, memory_budget_mb=256, max_bytes=128 * 1024 * 1024)
    policy = Policy(default=Rule("redact"), require_ner=False)
    result = {
        "schema_version": 1,
        "seed": args.seed,
        "machine": machine_metadata(),
        "configuration": {
            "language": args.language,
            "dpi": args.dpi,
            "psm": args.psm,
            "oem": 1,
            "critical_ocr_confidence": 50,
            "policy": "explicit rules-only full redaction",
        },
        "asset_sha256": {
            "executable": hashlib.sha256(args.executable.read_bytes()).hexdigest(),
            "spa_traineddata": hashlib.sha256(
                (args.tessdata / "spa.traineddata").read_bytes()
            ).hexdigest(),
            "eng_traineddata": hashlib.sha256(
                (args.tessdata / "eng.traineddata").read_bytes()
            ).hexdigest(),
        },
        "workloads": [],
        "tesseract_version": subprocess.run(
            [str(args.executable), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.splitlines()[0],
        "notes": [
            "RSS is sampled every10ms and process-tree includes local OCR subprocesses",
            "CPU accounting excludes exited OCR child CPU",
            "Full-scale workloads have one repetition; small-native repeats are separate",
            "No customer data or cloud inference",
        ],
    }
    workloads = [
        ("native", args.native_pages, False),
        ("scanned", args.scanned_pages, False),
        ("mixed", args.mixed_pages, False),
        ("scanned-challenge", args.challenge_pages, True),
    ]
    with offline_network() as guard:
        for name, count, challenge in workloads:
            if not count:
                continue
            cases = page_cases(count, seed=args.seed, challenge=challenge)
            path = args.work / (name + ".pdf")
            generate_pdf(
                path, cases, kind="scanned" if challenge else name, dpi=args.dpi, seed=args.seed
            )
            source_metrics, (texts, latencies, confidence) = measure(
                partial(recognize_pages, path, engine, dpi=args.dpi),
                units=count,
                size_bytes=path.stat().st_size,
            )
            source_metrics["pages_per_second"] = source_metrics["records_per_second"]
            source_metrics["page_latency_p50_seconds"] = percentile(latencies, 0.5)
            source_metrics["page_latency_p95_seconds"] = percentile(latencies, 0.95)
            source_metrics["first_page_seconds"] = latencies[0]
            source_metrics["later_pages_latency_p50_seconds"] = percentile(latencies[1:], 0.5)
            source_metrics["later_pages_latency_p95_seconds"] = percentile(latencies[1:], 0.95)
            output = args.work / (name + "-redacted.pdf")
            if output.exists():
                raise FileExistsError("Use a fresh work directory for reproducible output")
            processing, result_object = measure(
                partial(redact_pdf, path, output, engine=engine, policy=policy, dpi=args.dpi),
                units=count,
                size_bytes=path.stat().st_size,
            )
            item = {
                "workload": name,
                "pages": count,
                "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_ocr": source_metrics,
                "transcription": evaluate_transcription(cases, texts),
                "detection": gold_value_metrics(cases, texts, engine),
                "ocr_confidence_minimum": min(confidence, default=None),
                "ocr_confidence_p50": percentile(confidence, 0.5),
                "end_to_end": processing,
                "status": str(result_object.status),
                "issues": result_object.issues,
                "residual_findings_by_type": dict(
                    Counter(f.entity_type for f in result_object.findings)
                ),
                "library_audit": result_object.audit,
                "output_ground_truth": verify_gold_output(
                    output, cases, engine, dpi=args.dpi, source=path, kind=name
                )
                if output.exists()
                else None,
            }
            result["workloads"].append(item)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "workload": name,
                        "status": item["status"],
                        "pages": count,
                        "seconds": processing["elapsed_seconds"],
                        "cer": item["transcription"]["character_error_rate"],
                        "gold_check": item["output_ground_truth"]
                        and item["output_ground_truth"]["passed"],
                    }
                )
            )
        if args.repeats:
            small = page_cases(args.repeat_pages, seed=args.seed)
            source = args.work / "repeated-native.pdf"
            generate_pdf(source, small, kind="native", dpi=args.dpi, seed=args.seed)
            repeats = []
            for index in range(args.repeats):
                output = args.work / f"repeated-{index:02d}.pdf"
                metrics, processed = measure(
                    partial(redact_pdf, source, output, engine=engine, policy=policy, dpi=args.dpi),
                    units=len(small),
                    size_bytes=source.stat().st_size,
                )
                repeats.append(
                    {**metrics, "status": str(processed.status), "issues": processed.issues}
                )
            result["repeat_experiment"] = {
                "pages": len(small),
                "repeats": args.repeats,
                "runs": repeats,
                "median_pages_per_second": statistics.median(
                    r["records_per_second"] for r in repeats
                ),
            }
        result["network_guard"] = {
            "python_attempted_connections": guard["attempts"],
            "scope": "Python DNS/connect denied; local Tesseract child process executes installed assets, no system-wide firewall claim",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    workspace = Path(__file__).resolve().parents[3]
    parser.add_argument(
        "--executable", type=Path, default=workspace / "work/tesseract-5.5.4/bin/tesseract.exe"
    )
    parser.add_argument(
        "--tessdata", type=Path, default=workspace / "work/tesseract-5.5.4/share/tessdata"
    )
    parser.add_argument("--work", type=Path, default=workspace / "work/pdf-ocr-benchmark")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/pdf-ocr.json"))
    parser.add_argument("--native-pages", type=int, default=100)
    parser.add_argument("--scanned-pages", type=int, default=12)
    parser.add_argument("--mixed-pages", type=int, default=6)
    parser.add_argument("--challenge-pages", type=int, default=3)
    parser.add_argument("--repeat-pages", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--dpi", type=int, default=216)
    parser.add_argument("--psm", type=int, default=6)
    parser.add_argument("--language", default="spa+eng")
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if (
        any(
            count < 0
            for count in (
                args.native_pages,
                args.scanned_pages,
                args.mixed_pages,
                args.challenge_pages,
                args.repeats,
            )
        )
        or args.repeat_pages < 1
        or not 144 <= args.dpi <= 600
    ):
        parser.error("Invalid benchmark workload limits")
    run(args)


if __name__ == "__main__":
    main()
