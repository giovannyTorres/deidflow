"""Reproducible synthetic data, exact-span metrics and measured workloads."""

from .datasets import Example, GoldSpan, read_corpus, synthetic_corpus, write_corpus
from .metrics import DetectionMetrics, evaluate

__all__ = [
    "DetectionMetrics",
    "Example",
    "GoldSpan",
    "evaluate",
    "read_corpus",
    "synthetic_corpus",
    "write_corpus",
]
