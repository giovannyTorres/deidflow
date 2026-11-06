"""Unicode detection views with conservative offsets into the unchanged source.

Detectors see a view of the text in which invisible characters are removed
(format controls, category ``Cf``, and every other ``Default_Ignorable_Code_Point``
such as the combining grapheme joiner, variation selectors and Hangul fillers),
NFKC is applied (full-width and mathematical letters, superscript digits,
no-break spaces) and, inside words that mix Latin with Greek or Cyrillic,
look-alike letters are folded to Latin. Findings are projected back to complete
original spans, so a replacement also removes the invisible characters inside
or next to an identifier. Emitted documents are never normalized.

Only words that change are traced. Text is split at ASCII whitespace, which is a
stable boundary for NFKC (a space never composes with its neighbours), so the
view of each word is independent of the others. Unchanged text and words whose
characters map one to one (a no-break space, a full-width letter) need no
coordinate arrays; only words whose length changes (a removed control, an
expansion, a composition) allocate them, and ``max_characters`` bounds that
allocation. Canonical clusters share an original envelope, so projection is
constant time per finding even when combining marks reorder.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from array import array
from dataclasses import dataclass, replace

from deidflow.core import Finding

FORMAT_CONTROL_ISSUE = "UNICODE_FORMAT_CONTROLS_REQUIRE_REVIEW"
DEFAULT_MAX_CHARACTERS = 8_000_000  # traced characters of length-changing words

# Default_Ignorable_Code_Point (Unicode DerivedCoreProperties.txt, stable since 14.0).
# Category Cf is removed as well; most Cf code points are in this list.
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160),
    (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E),
    (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)  # fmt: skip
_IGNORABLE_STARTS = [start for start, _ in _DEFAULT_IGNORABLE]

# Greek and Cyrillic letters that render like Latin ones (Unicode TR39 confusables
# restricted to single letters). Folded only inside words that also contain ASCII
# letters or digits, where a look-alike hides an identifier ("12345678Ζ").
_CONFUSABLE_FROM = "ΑΒΕΖΗΙΚΜΝΟΡΤΥΧαβεικνορτυχϲϳϹАВЕЅІЈКМНОРСТУХҮӀԚԜаеѕіјорсухԁԛԝһӏү"
_CONFUSABLE_TO = "ABEZHIKMNOPTYXaBeikvoptuxcjCABESIJKMHOPCTYXYIQWaesijopcyxdqwhly"
_CONFUSABLES = str.maketrans(_CONFUSABLE_FROM, _CONFUSABLE_TO)
_CONFUSABLE_KEYS = frozenset(_CONFUSABLE_FROM)
_WHITESPACE = re.compile(r"[ \t\n\r\f\v]")
_NON_ASCII = re.compile(r"[^\x00-\x7f]")
_IGNORABLE_CACHE: dict[str, bool] = {}


class NormalizationLimitError(ValueError):
    """The traced coordinate maps would exceed the configured budget."""


def is_ignorable(character: str) -> bool:
    """Invisible characters: category Cf or Default_Ignorable_Code_Point."""
    cached = _IGNORABLE_CACHE.get(character)
    if cached is None:
        point = ord(character)
        index = bisect.bisect_right(_IGNORABLE_STARTS, point) - 1
        cached = unicodedata.category(character) == "Cf" or (
            index >= 0 and point <= _DEFAULT_IGNORABLE[index][1]
        )
        if len(_IGNORABLE_CACHE) < 65_536:
            _IGNORABLE_CACHE[character] = cached
    return cached


@dataclass(frozen=True, slots=True)
class _Piece:
    """A changed word: view [view_start, view_end) replaces source [source_start, source_end)."""

    view_start: int
    view_end: int
    source_start: int
    source_end: int
    starts: array | None  # absolute source start of each view character, if not 1:1
    ends: array | None


@dataclass(frozen=True, slots=True)
class DetectionView:
    text: str
    _pieces: tuple[_Piece, ...] = ()
    _view_starts: tuple[int, ...] = ()

    @property
    def traced_characters(self) -> int:
        """Number of view characters with allocated source-coordinate maps."""
        return sum(len(piece.starts) for piece in self._pieces if piece.starts is not None)

    def _source(self, position: int) -> tuple[int, int]:
        """Original span of the view character at ``position``."""
        index = bisect.bisect_right(self._view_starts, position) - 1
        if index < 0:
            return position, position + 1
        piece = self._pieces[index]
        if position < piece.view_end:
            offset = position - piece.view_start
            if piece.starts is None or piece.ends is None:
                return piece.source_start + offset, piece.source_start + offset + 1
            return piece.starts[offset], piece.ends[offset]
        delta = piece.source_end - piece.view_end
        return position + delta, position + delta + 1

    def bounds(self, start: int, end: int) -> tuple[int, int]:
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(self.text):
            raise ValueError("Invalid normalized detection offsets")
        if not self._pieces:
            return start, end
        return self._source(start)[0], self._source(end - 1)[1]

    def project(self, finding: Finding) -> Finding:
        start, end = self.bounds(finding.start, finding.end)
        if (start, end) == (finding.start, finding.end):
            return finding
        return replace(finding, start=start, end=end)


def _mixed_confusable(word: str) -> bool:
    return any(c in _CONFUSABLE_KEYS for c in word) and any(
        c.isascii() and c.isalnum() for c in word
    )


def _changes(word: str) -> bool:
    return (
        any(is_ignorable(c) for c in word)
        or not unicodedata.is_normalized("NFKC", word)
        or _mixed_confusable(word)
    )


_NFKC_CHARACTER: dict[str, str] = {}


def _one_to_one(word: str) -> str | None:
    """The view of a word whose characters normalize one to one in place, if so.

    Such words (full-width forms, no-break spaces, ordinal indicators) need no
    coordinate maps, so they never allocate tracing arrays whatever their length;
    the view is built with one translation table of the distinct characters.
    """
    table: dict[int, str] = {}
    for character in set(word):
        if is_ignorable(character):
            return None
        normalized = _NFKC_CHARACTER.get(character)
        if normalized is None:
            normalized = unicodedata.normalize("NFKC", character)
            if len(_NFKC_CHARACTER) < 65_536:
                _NFKC_CHARACTER[character] = normalized
        if len(normalized) != 1:
            return None
        if normalized != character:
            table[ord(character)] = normalized
    candidate = word.translate(table)
    return candidate if unicodedata.normalize("NFKC", word) == candidate else None


def _trace(text: str, max_characters: int) -> tuple[str, array, array]:
    """NFKC of ``text`` without ignorables, with each output character's source span."""
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
        if is_ignorable(text[position]):
            position += 1
            continue
        following = position + 1
        while following < len(text) and is_ignorable(text[following]):
            following += 1
        for character in unicodedata.normalize("NFKD", text[position]):
            decomposed += 1
            if decomposed > max_characters:
                raise NormalizationLimitError("Text exceeds normalization tracing budget")
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
    source_starts, source_ends = array("I"), array("I")
    for group in groups:
        original = root(group)
        source_starts.append(starts[original])
        source_ends.append(ends[original])
    return "".join(output), source_starts, source_ends


def _words_to_change(text: str) -> list[tuple[int, int]]:
    """Spans of whitespace-delimited words that contain a character to normalize."""
    spans: list[tuple[int, int]] = []
    word_end = scan_from = 0
    for match in _NON_ASCII.finditer(text):
        position = match.start()
        if position < word_end:
            continue  # same word as the previous non-ASCII character
        start = max(max(text.rfind(c, scan_from, position) for c in " \t\n\r\f\v") + 1, scan_from)
        following = _WHITESPACE.search(text, position)
        word_end = following.start() if following else len(text)
        scan_from = word_end
        if _changes(text[start:word_end]):
            spans.append((start, word_end))
    return spans


def detection_view(text: str, *, max_characters: int = DEFAULT_MAX_CHARACTERS) -> DetectionView:
    """Remove invisible characters, apply NFKC and fold mixed-script look-alikes.

    ``max_characters`` bounds the coordinate arrays of words whose length changes;
    unchanged text and one-to-one replacements allocate none. Exceeding it raises
    ``NormalizationLimitError`` (a ``ValueError``), like the engine's size limits.
    """
    if not isinstance(text, str):
        raise TypeError("Detection input must be a Unicode string")
    if type(max_characters) is not int or max_characters < 1:
        raise ValueError("Invalid normalization budget")
    if text.isascii():
        return DetectionView(text)
    if len(text) > 0xFFFFFFFF:
        raise NormalizationLimitError("Text exceeds normalization tracing budget")
    spans = _words_to_change(text)
    if not spans:
        return DetectionView(text)
    parts: list[str] = []
    pieces: list[_Piece] = []
    view_position = source_position = traced = 0
    for start, end in spans:
        parts.append(text[source_position:start])
        view_position += start - source_position
        word = text[start:end]
        mapped = _one_to_one(word)
        if mapped is not None:
            normalized = mapped.translate(_CONFUSABLES) if _mixed_confusable(mapped) else mapped
            piece = _Piece(view_position, view_position + len(normalized), start, end, None, None)
        else:
            # Temporary and kept maps of this word stay within the remaining budget.
            normalized, starts, ends = _trace(word, max_characters - traced)
            if _mixed_confusable(normalized):
                normalized = normalized.translate(_CONFUSABLES)  # one to one
            traced += len(normalized)
            if traced > max_characters:
                raise NormalizationLimitError("Text exceeds normalization tracing budget")
            piece = _Piece(
                view_position,
                view_position + len(normalized),
                start,
                end,
                array("I", (value + start for value in starts)),
                array("I", (value + start for value in ends)),
            )
        pieces.append(piece)
        parts.append(normalized)
        view_position += len(normalized)
        source_position = end
    parts.append(text[source_position:])
    normalized_text = "".join(parts)
    if normalized_text == text:
        return DetectionView(text)
    return DetectionView(normalized_text, tuple(pieces), tuple(p.view_start for p in pieces))


def ordinal_feature_text(source: str, view: DetectionView) -> str:
    """Retain original ordinal token classes for lexical features/validation.

    The detection view stays NFKC without invisible characters. Its map supplies
    the distinction between source ordinal indicators and ordinary a/o at
    unchanged coordinates; controls and full-width characters are never restored.
    Only changed words are inspected: elsewhere view and source are identical.
    """
    if ("ª" not in source and "º" not in source) or not view._pieces:
        return view.text
    characters: list[str] | None = None
    for piece in view._pieces:
        for index in range(piece.view_start, piece.view_end):
            character = view.text[index]
            if character not in "ao":
                continue
            start, end = view._source(index)
            original = source[start:end]
            restored = None
            if "ª" in original and character == "a":
                restored = "ª"
            elif "º" in original and character == "o":
                restored = "º"
            if restored is not None:
                if characters is None:
                    characters = list(view.text)
                characters[index] = restored
    return view.text if characters is None else "".join(characters)


def has_internal_format_controls(text: str) -> bool:
    """Whether an invisible character separates alphanumerics, allowing combining marks."""
    if text.isascii():
        return False
    alphanumeric = pending = False
    for character in text:
        if is_ignorable(character):
            pending |= alphanumeric
            continue
        if character.isalnum():
            if pending:
                return True
            alphanumeric = True
        elif not unicodedata.category(character).startswith("M"):
            alphanumeric = pending = False
    return False


__all__ = [
    "DEFAULT_MAX_CHARACTERS",
    "FORMAT_CONTROL_ISSUE",
    "DetectionView",
    "NormalizationLimitError",
    "detection_view",
    "has_internal_format_controls",
    "is_ignorable",
    "ordinal_feature_text",
]
