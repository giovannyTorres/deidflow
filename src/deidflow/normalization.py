"""Unicode detection views with conservative offsets into the unchanged source.

Tracing is bounded by the decomposed view size; ASCII identity views allocate no
maps; already normalized text also keeps its original budget. Canonical clusters share an original envelope, so projection is constant
time even when combining marks reorder or one scalar expands into several.
"""

from __future__ import annotations

import unicodedata
from array import array
from dataclasses import dataclass, replace

from deidflow.core import Finding

FORMAT_CONTROL_ISSUE = "UNICODE_FORMAT_CONTROLS_REQUIRE_REVIEW"
DEFAULT_MAX_CHARACTERS = 1_000_000


@dataclass(frozen=True, slots=True)
class DetectionView:
    text: str
    _starts: array | None = None
    _ends: array | None = None

    @property
    def traced_characters(self) -> int:
        """Number of emitted characters with allocated source-coordinate maps."""
        return len(self._starts) if self._starts is not None else 0

    def bounds(self, start: int, end: int) -> tuple[int, int]:
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(self.text):
            raise ValueError("Invalid normalized detection offsets")
        if self._starts is None or self._ends is None:
            return start, end
        return self._starts[start], self._ends[end - 1]

    def project(self, finding: Finding) -> Finding:
        start, end = self.bounds(finding.start, finding.end)
        if (start, end) == (finding.start, finding.end):
            return finding
        return replace(finding, start=start, end=end)


def detection_view(text: str, *, max_characters: int = DEFAULT_MAX_CHARACTERS) -> DetectionView:
    """Remove Cf and apply NFKC, retaining whole original canonical clusters.

    ``max_characters`` bounds nonidentity decomposition/tracing allocations, not
    the caller's original text budget. Identity views need no tracing allocation and
    keep their original size limit. Reaching the tracing budget fails closed.
    """
    if not isinstance(text, str):
        raise TypeError("Detection input must be a Unicode string")
    if type(max_characters) is not int or max_characters < 1:
        raise ValueError("Invalid normalization budget")
    if text.isascii():
        return DetectionView(text)
    if not any(unicodedata.category(c) == "Cf" for c in text) and unicodedata.is_normalized(
        "NFKC", text
    ):
        return DetectionView(text)
    if len(text) > 0xFFFFFFFF:
        raise ValueError("Text exceeds normalization tracing budget")
    parents, starts, ends = array("I"), array("I"), array("I")
    output: list[str] = []
    groups = array("I")
    segment: dict[int, list[str]] = {}
    segment_start = segment_end = 0
    decomposed = 0
    starter = -1
    last_class = 0

    def root(group: int) -> int:
        while parents[group] != group:
            parents[group] = parents[parents[group]]
            group = parents[group]
        return group

    def flush() -> None:
        nonlocal starter, last_class
        if not segment:
            return
        group = len(parents)
        parents.append(group)
        starts.append(segment_start)
        ends.append(segment_end)
        # At most 256 canonical classes: stable buckets avoid quadratic insertion
        # and unbounded sorting of adversarial combining sequences.
        for combining_class in sorted(segment):
            for character in segment[combining_class]:
                if starter >= 0 and (last_class < combining_class or last_class == 0):
                    combined = unicodedata.normalize("NFC", output[starter] + character)
                    if len(combined) == 1:
                        output[starter] = combined
                        previous, current = root(groups[starter]), root(group)
                        if previous != current:
                            parents[current] = previous
                            starts[previous] = min(starts[previous], starts[current])
                            ends[previous] = max(ends[previous], ends[current])
                        continue
                if combining_class == 0:
                    starter = len(output)
                output.append(character)
                groups.append(group)
                last_class = combining_class
        segment.clear()

    position = previous_end = 0
    while position < len(text):
        if unicodedata.category(text[position]) == "Cf":
            position += 1
            continue
        following = position + 1
        while following < len(text) and unicodedata.category(text[following]) == "Cf":
            following += 1
        for character in unicodedata.normalize("NFKD", text[position]):
            decomposed += 1
            if decomposed > max_characters:
                raise ValueError("Text exceeds normalization tracing budget")
            combining_class = unicodedata.combining(character)
            if combining_class == 0:
                flush()
            if not segment:
                segment_start, segment_end = previous_end, following
            else:
                segment_start = min(segment_start, previous_end)
                segment_end = max(segment_end, following)
            segment.setdefault(combining_class, []).append(character)
        previous_end = position + 1
        position = following
    flush()
    normalized = "".join(output)
    if normalized == text:
        return DetectionView(text)
    source_starts, source_ends = array("I"), array("I")
    for group in groups:
        original = root(group)
        source_starts.append(starts[original])
        source_ends.append(ends[original])
    return DetectionView(normalized, source_starts, source_ends)


def ordinal_feature_text(source: str, view: DetectionView) -> str:
    """Retain original ordinal token classes for lexical features/validation.

    The detection view stays Cf-free NFKC. Its map supplies the distinction
    between source ordinal indicators and ordinary a/o at unchanged coordinates;
    controls and fullwidth characters are never restored to the feature text.
    """
    if "ª" not in source and "º" not in source:
        return view.text
    characters = list(view.text)
    for index, character in enumerate(characters):
        if character in "ao":
            start, end = view.bounds(index, index + 1)
            original = source[start:end]
            if "ª" in original and character == "a":
                characters[index] = "ª"
            elif "º" in original and character == "o":
                characters[index] = "º"
    return "".join(characters)


def has_internal_format_controls(text: str) -> bool:
    """Whether Cf separates alphanumeric characters, allowing combining marks."""
    alphanumeric = pending = False
    for character in text:
        category = unicodedata.category(character)
        if category == "Cf":
            pending |= alphanumeric
        elif character.isalnum():
            if pending:
                return True
            alphanumeric = True
        elif not category.startswith("M"):
            alphanumeric = pending = False
    return False
