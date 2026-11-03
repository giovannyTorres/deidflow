"""Local numeric-only stage timing and sampled process-tree memory.

Overlapping worker durations are work time, not additive end-to-end latency.
This profiler never receives document text, paths, findings or credentials.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

STAGES = frozenset(
    {
        "loading",
        "rendering",
        "ocr",
        "nlp",
        "rules",
        "context",
        "redaction",
        "reconstruction",
        "verification",
        "hashing",
        "publication",
    }
)
ACTIVE_PROFILER: ContextVar[StageProfiler | None] = ContextVar(
    "deidflow_stage_profiler", default=None
)


class StageProfiler:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._lock = threading.RLock()
        self._local = threading.local()
        self._rows: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "calls": 0,
                "inclusive_work_seconds": 0.0,
                "exclusive_work_seconds": 0.0,
                "sampled_peak_parent_rss_bytes": 0,
                "sampled_peak_tree_rss_bytes": 0,
            }
        )
        self._active: dict[str, int] = defaultdict(int)
        self._done = threading.Event()
        self._monitor: threading.Thread | None = None
        self._started = time.perf_counter()
        self._rss_available = False
        if enabled:
            try:
                import psutil

                self._process = psutil.Process()
                self._rss_available = True
                self._monitor = threading.Thread(target=self._sample, daemon=True)
                self._monitor.start()
            except ImportError:
                pass

    def _sample(self) -> None:
        import psutil

        while not self._done.is_set():
            try:
                own = self._process.memory_info().rss
                tree = own
                for child in self._process.children(recursive=True):
                    try:
                        tree += child.memory_info().rss
                    except psutil.Error:
                        pass
                with self._lock:
                    for name, count in self._active.items():
                        if count:
                            row = self._rows[name]
                            row["sampled_peak_parent_rss_bytes"] = max(
                                row["sampled_peak_parent_rss_bytes"], own
                            )
                            row["sampled_peak_tree_rss_bytes"] = max(
                                row["sampled_peak_tree_rss_bytes"], tree
                            )
            except psutil.Error:
                pass
            self._done.wait(0.01)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        if name not in STAGES:
            raise ValueError("Unknown profiling stage")
        if not self.enabled:
            yield
            return
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        item = [time.perf_counter(), 0.0]
        stack.append(item)
        with self._lock:
            self._active[name] += 1
        try:
            yield
        finally:
            elapsed = time.perf_counter() - item[0]
            stack.pop()
            if stack:
                stack[-1][1] += elapsed
            with self._lock:
                self._active[name] -= 1
                row = self._rows[name]
                row["calls"] += 1
                row["inclusive_work_seconds"] += elapsed
                row["exclusive_work_seconds"] += max(0.0, elapsed - item[1])

    def close(self) -> None:
        self._done.set()
        if self._monitor:
            self._monitor.join(timeout=1)

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "elapsed_seconds": time.perf_counter() - self._started,
                "stages": {name: dict(row) for name, row in sorted(self._rows.items())},
                "memory_sample_interval_ms": 10,
                "rss_available": self._rss_available,
                "timing_semantics": "Worker work times overlap; do not sum as wall time. Memory is sampled process/tree RSS, not a hard admission cap.",
                "nlp_configured": False,
            }
