"""Allowlisted, coarsened operational reports; no record-level strings or gold metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .security import PrivateError

FORMATS = (
    "pdf",
    "docx",
    "xlsx",
    "csv",
    "tsv",
    "txt",
    "json",
    "jsonl",
    "parquet",
    "png",
    "jpeg",
    "tiff",
    "other",
)
CATEGORIES = ("personal", "health", "credentials", "quasi_identifier", "other")
COUNTERS = (
    "messages_examined",
    "candidate_attachments",
    "eligible_attachments",
    "personally_approved_attachments",
    "unapproved_attachments",
    "work_or_uncertain_exclusions",
    "filter_exclusions",
    "unsupported_attachments",
    "oversize_attachments",
    "metadata_duplicate_candidates",
    "content_duplicates",
    "processed_documents",
    "processing_failures",
    "incomplete_documents",
    "ocr_uncertain_documents",
    "review_required_documents",
    "verification_failed_documents",
    "approved_documents",
    "unreadable_or_encrypted_documents",
    "approximate_pages_observed",
)
MEASURES = (
    "total_size_mib",
    "processing_success_rate",
    "unsupported_rate",
    "review_required_rate",
    "verification_failure_rate",
    "documents_per_second",
    "mb_per_second",
    "latency_p50_seconds",
    "latency_p95_seconds",
    "peak_process_tree_mib",
    "estimated_processing_seconds",
)


def _count(value: int, minimum: int = 5) -> int | None:
    return (value // 5) * 5 if value >= minimum else None


@dataclass
class OperationalMetrics:
    counts: dict[str, int] = field(default_factory=lambda: {k: 0 for k in COUNTERS})
    formats: dict[str, int] = field(default_factory=lambda: {k: 0 for k in FORMATS})
    categories: dict[str, int] = field(default_factory=lambda: {k: 0 for k in CATEGORIES})
    size_bins: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in ("lt_1_mib", "1_to_10_mib", "10_to_64_mib")}
    )
    total_bytes: int = 0
    processed_bytes: int = 0
    unique_content_documents: int = 0
    latencies: list[float] = field(default_factory=list, repr=False)
    elapsed_seconds: float = 0
    peak_rss: int = 0
    truncated: bool = False

    def emit(self, *, mode: str, seconds_per_attachment: float | None = None) -> dict[str, Any]:
        candidates = self.counts["candidate_attachments"]
        n = self.unique_content_documents if mode == "RUN" else candidates
        enough = n >= 10
        band = (
            "LT10"
            if n < 10
            else "10_49"
            if n < 50
            else "50_199"
            if n < 200
            else "200_999"
            if n < 1000
            else "1000_PLUS"
        )
        processed = self.counts["processed_documents"]
        samples = sorted(self.latencies)

        def quantile(p: float) -> float | None:
            if len(samples) < 10:
                return None
            return float(round(samples[min(len(samples) - 1, int((len(samples) - 1) * p))]))

        def rate(numerator: int, denominator: int | None = None) -> float | None:
            denominator = processed if denominator is None else denominator
            if not enough or denominator < 10 or not 0 <= numerator <= denominator:
                return None
            # A coarse rate must not reconstruct a count suppressed for rarity,
            # including the complementary cell (for example nine of ten).
            if 0 < numerator < 5 or 0 < denominator - numerator < 5:
                return None
            return round(numerator / denominator, 1)

        values: dict[str, float | None] = {
            "total_size_mib": float(round(self.total_bytes / 1024**2)) if enough else None,
            "processing_success_rate": rate(max(0, processed - self.counts["processing_failures"])),
            "unsupported_rate": rate(self.counts["unsupported_attachments"], candidates),
            "review_required_rate": rate(self.counts["review_required_documents"]),
            "verification_failure_rate": rate(self.counts["verification_failed_documents"]),
            "documents_per_second": float(round(processed / max(self.elapsed_seconds, 0.001)))
            if enough and processed >= 10
            else None,
            "mb_per_second": round(
                self.processed_bytes / 1024**2 / max(self.elapsed_seconds, 0.001), 1
            )
            if enough and processed >= 10
            else None,
            "latency_p50_seconds": quantile(0.5) if enough else None,
            "latency_p95_seconds": quantile(0.95) if enough else None,
            "peak_process_tree_mib": float(math.ceil(self.peak_rss / 1024**2 / 16) * 16)
            if enough and mode == "RUN" and self.peak_rss > 0
            else None,
            "estimated_processing_seconds": float(
                math.ceil(self.counts["eligible_attachments"] * seconds_per_attachment / 10) * 10
            )
            if enough and seconds_per_attachment is not None
            else None,
        }
        report = {
            "schema_version": 1,
            "mode": mode,
            "state": "AGGREGATED" if enough else "INSUFFICIENT_COHORT",
            "cohort_band": band,
            "truncated": self.truncated,
            "privacy": {
                "minimum_cohort": 10,
                "minimum_cell": 5,
                "count_rounding": 5,
                "differential_privacy": False,
            },
            "counts": {k: _count(v) if enough else None for k, v in self.counts.items()},
            "by_format": {k: _count(v) if enough else None for k, v in self.formats.items()},
            "documents_by_broad_category": {
                k: _count(v) if enough else None for k, v in self.categories.items()
            },
            "size_distribution": {
                k: _count(v) if enough else None for k, v in self.size_bins.items()
            },
            "measurements": values,
            "estimation": "USER_CALIBRATION"
            if seconds_per_attachment is not None
            else "UNAVAILABLE",
            "accuracy": "UNLABELED_OPERATIONAL_ONLY",
        }
        validate_report(report)
        return report


def validate_report(report: Any) -> dict[str, Any]:
    try:
        expected = {
            "schema_version",
            "mode",
            "state",
            "cohort_band",
            "truncated",
            "privacy",
            "counts",
            "by_format",
            "documents_by_broad_category",
            "size_distribution",
            "measurements",
            "estimation",
            "accuracy",
        }
        if (
            not isinstance(report, dict)
            or set(report) != expected
            or report["schema_version"] != 1
            or type(report["schema_version"]) is not int
        ):
            raise ValueError
        enums = {
            "mode": {"INVENTORY", "RUN"},
            "state": {"AGGREGATED", "INSUFFICIENT_COHORT"},
            "cohort_band": {"LT10", "10_49", "50_199", "200_999", "1000_PLUS"},
            "estimation": {"USER_CALIBRATION", "UNAVAILABLE"},
            "accuracy": {"UNLABELED_OPERATIONAL_ONLY"},
        }
        if (
            any(
                type(report[k]) is not str or report[k] not in allowed
                for k, allowed in enums.items()
            )
            or type(report["truncated"]) is not bool
        ):
            raise ValueError
        if report["privacy"] != {
            "minimum_cohort": 10,
            "minimum_cell": 5,
            "count_rounding": 5,
            "differential_privacy": False,
        }:
            raise ValueError
        if (
            any(
                type(report["privacy"][k]) is not int
                for k in ("minimum_cohort", "minimum_cell", "count_rounding")
            )
            or type(report["privacy"]["differential_privacy"]) is not bool
        ):
            raise ValueError
        if report["state"] == "AGGREGATED" and report["cohort_band"] == "LT10":
            raise ValueError
        for key, keys in (
            ("counts", COUNTERS),
            ("by_format", FORMATS),
            ("documents_by_broad_category", CATEGORIES),
            ("size_distribution", ("lt_1_mib", "1_to_10_mib", "10_to_64_mib")),
        ):
            values = report[key]
            if (
                not isinstance(values, dict)
                or set(values) != set(keys)
                or any(
                    v is not None and (type(v) is not int or v < 5 or v % 5)
                    for v in values.values()
                )
            ):
                raise ValueError
        values = report["measurements"]
        if (
            not isinstance(values, dict)
            or set(values) != set(MEASURES)
            or any(
                v is not None and (type(v) not in {float, int} or not math.isfinite(v) or v < 0)
                for v in values.values()
            )
        ):
            raise ValueError
        if report["state"] == "INSUFFICIENT_COHORT" and (
            report["cohort_band"] != "LT10"
            or any(
                v is not None
                for k in (
                    "counts",
                    "by_format",
                    "documents_by_broad_category",
                    "size_distribution",
                    "measurements",
                )
                for v in report[k].values()
            )
        ):
            raise ValueError
        return report
    except (TypeError, ValueError, KeyError):
        raise PrivateError("PRIVATE_REPORT_INVALID") from None
