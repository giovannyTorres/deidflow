"""Optional, offline discriminative NLP adapters; no runtime model downloads."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from threading import Lock
from typing import Any

from deidflow.core import Finding
from deidflow.detectors import fuse


class SpacyNER:
    """Lazy spaCy model adapter with bounded, overlapping windows and batched inference.

    ``model_path`` must be an installed local model directory. Loading never invokes
    a download command. A single adapter serializes pipeline access, so shared model
    state cannot be mutated by simultaneous calls. Use separate process instances
    for CPU parallelism. Model weights and their license remain the user's choice.
    """

    def __init__(
        self,
        model_path: str | Path,
        *,
        batch_size: int = 32,
        window_chars: int = 50000,
        overlap_chars: int = 512,
        device: str = "cpu",
        labels: dict[str, str] | None = None,
    ) -> None:
        if batch_size < 1 or window_chars < 64 or not 0 <= overlap_chars < window_chars // 2:
            raise ValueError("Invalid NLP batch/window settings")
        if device not in {"cpu", "cuda"}:
            raise ValueError("Unsupported NLP device")
        if labels is not None and not labels:
            raise ValueError("NLP label mapping must not be empty")
        self.model_path = Path(model_path)
        self.batch_size = batch_size
        self.window_chars = window_chars
        self.overlap_chars = overlap_chars
        self.device = device
        self.labels = (
            dict(labels)
            if labels is not None
            else {"PER": "PERSON", "PERSON": "PERSON", "LOC": "LOCATION", "GPE": "LOCATION"}
        )
        self._nlp: Any = None
        self._lock = Lock()
        self.model_version = "unloaded"

    def _load(self) -> Any:
        if self._nlp is None:
            if not self.model_path.is_dir():
                raise ValueError("A local spaCy model directory is required")
            try:
                import spacy
            except ImportError:
                raise ImportError("Install deidflow[nlp] for the local spaCy adapter") from None
            if self.device == "cuda":
                spacy.require_gpu()
            else:
                spacy.require_cpu()
            try:
                self._nlp = spacy.load(self.model_path)
            except Exception:
                raise ValueError("Local spaCy model could not be loaded") from None
            if not (
                "ner" in self._nlp.pipe_names
                or "entity_ruler" in self._nlp.pipe_names
                or "span_ruler" in self._nlp.pipe_names
            ):
                self._nlp = None
                raise ValueError("Local model must contain an entity recognition component")
            self._nlp.max_length = max(self._nlp.max_length, self.window_chars + 1)
            self.model_version = str(self._nlp.meta.get("version", "unknown"))
        return self._nlp

    def _windows(self, texts: list[str]) -> Iterator[tuple[str, tuple[int, int, int, int]]]:
        for document, text in enumerate(texts):
            if not text:
                yield "", (document, 0, 0, 0)
                continue
            start = 0
            while start < len(text):
                end = min(len(text), start + self.window_chars)
                yield text[start:end], (document, start, end - start, len(text))
                if end == len(text):
                    break
                start = end - self.overlap_chars

    def detect_batch(self, texts: list[str]) -> list[list[Finding]]:
        result: list[list[Finding]] = [[] for _ in texts]
        with self._lock:
            nlp = self._load()
            try:
                for doc, (index, offset, window_length, total_length) in nlp.pipe(
                    self._windows(texts), as_tuples=True, batch_size=self.batch_size
                ):
                    # Span rulers/classifiers may retain overlapping candidates in
                    # doc.spans rather than doc.ents. Read both without flattening
                    # away overlapping sensitive mentions.
                    entities = list(doc.ents)
                    for span_group in doc.spans.values():
                        entities.extend(span_group)
                    for entity in entities:
                        kind = self.labels.get(entity.label_)
                        if kind is None:
                            continue
                        partial = (entity.start_char == 0 and offset > 0) or (
                            entity.end_char == window_length
                            and offset + window_length < total_length
                        )
                        result[index].append(
                            Finding(
                                kind,
                                offset + entity.start_char,
                                offset + entity.end_char,
                                0.75,
                                "spacy.local",
                                validation="statistical",
                                context=("window_boundary",) if partial else (),
                                model_version=self.model_version,
                                risk="medium" if kind == "LOCATION" else "high",
                            )
                        )
            except Exception:
                # Third-party exceptions may include input text; replace them without a chained traceback.
                raise RuntimeError(
                    "Local NLP inference failed; processing must be blocked"
                ) from None
        # A complete overlapping-window detection supersedes a clipped fragment of
        # the same category. Complete detections remain exact in original offsets.
        cleaned: list[list[Finding]] = []
        for document_findings in result:
            complete = [f for f in document_findings if "window_boundary" not in f.context]
            kept = [
                f
                for f in document_findings
                if "window_boundary" not in f.context
                or not any(
                    g.entity_type == f.entity_type and g.start <= f.start and g.end >= f.end
                    for g in complete
                )
            ]
            cleaned.append(fuse(kept))
        return cleaned

    def detect(self, text: str) -> list[Finding]:
        return self.detect_batch([text])[0]


__all__ = ["SpacyNER"]
