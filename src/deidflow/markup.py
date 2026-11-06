"""Read and rewrite HTML documents by source offsets, keeping the markup intact.

Visible text is scanned as one stream (block elements separate lines, table
cells are separated by spaces), so ``<td>Nombre:</td><td>Ana</td>`` gives the
rules their label context. Replacements are placed in the original source at
exact offsets; character references inside a replaced value are replaced whole.
Attribute values that carry content (``alt``, ``title``, ``value``, ``href``,
``content``, ``placeholder``, ``aria-label``, ``data-*``...) are scanned and
rewritten one by one. Comments, scripts, embedded ``data:`` images and
``<iframe srcdoc>`` are removed by the writer, since none can be verified.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser

# rewrite(text) -> (output, [(source_start, source_end, replacement), ...])
Rewrite = Callable[[str], tuple[str, list[tuple[int, int, str]]]]

BLOCK = frozenset(
    {"address", "article", "aside", "blockquote", "body", "br", "dd", "div", "dl", "dt",
     "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
     "head", "header", "hr", "html", "li", "main", "nav", "ol", "p", "pre", "section", "table",
     "tbody", "tfoot", "thead", "title", "tr", "ul"}
)  # fmt: skip
CELL = frozenset({"td", "th", "option", "label"})
CONTENT_ATTRIBUTES = frozenset(
    {"alt", "title", "value", "href", "content", "placeholder", "aria-label", "label",
     "summary", "abbr", "cite", "action", "srcset", "poster", "download", "src", "data",
     "background", "longdesc", "formaction", "ping", "manifest", "codebase", "xlink:href",
     "imagesrcset", "style"}
)  # fmt: skip
# A data: URL with a payload (images, SVG, documents) cannot be verified by text scanning.
_DATA_URL = re.compile(r"(?<![\w-])data:[^\s,]*,\S", re.IGNORECASE)
# CSS string literals and url() arguments: generated content and resource URLs.
_CSS_VALUE = re.compile(
    r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|url\(\s*([^)"\'\s][^)\s]*)\s*\)',
    re.IGNORECASE,
)
_ATTRIBUTE = re.compile(
    r"""([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""", re.DOTALL
)


@dataclass
class Segment:
    start: int  # raw source offsets
    end: int
    text: str  # decoded text
    exact: bool  # raw text equals decoded text, so partial edits are possible


@dataclass
class Markup:
    """Offsets of everything the reader scans and the writer edits."""

    segments: list[Segment | str] = field(default_factory=list)  # str: virtual separator
    attributes: list[tuple[int, int, str, str]] = field(default_factory=list)  # raw span, name
    removable: list[tuple[int, int, str]] = field(default_factory=list)  # raw span, reason
    css: list[tuple[int, int, str]] = field(default_factory=list)  # <style> values, raw span
    comments: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "".join(s if isinstance(s, str) else s.text for s in self.segments)


class _Parser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        for index, character in enumerate(source):
            if character == "\n":
                self.lines.append(index + 1)
        self.result = Markup()
        self.raw_mode: str | None = None  # script/style element being read
        self.raw_start = 0

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self._offset()
        raw = self.get_starttag_text() or ""
        self._tag(tag, start, raw)
        if tag in {"script", "style"}:
            self.raw_mode, self.raw_start = tag, start

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self._offset()
        self._tag(tag, start, self.get_starttag_text() or "")

    def _tag(self, tag: str, start: int, raw: str) -> None:
        if tag in BLOCK:
            self.result.segments.append("\n")
        elif tag in CELL:
            self.result.segments.append(" ")
        name_end = len(tag) + 1
        for match in _ATTRIBUTE.finditer(raw, name_end, max(name_end, len(raw) - 1)):
            name = match.group(1).lower()
            for group in (2, 3, 4):
                if match.group(group) is not None:
                    value_start = start + match.start(group)
                    value_end = start + match.end(group)
                    break
            else:
                continue
            value = html.unescape(self.source[value_start:value_end])
            if _DATA_URL.search(value):
                self.result.removable.append((value_start, value_end, "embedded_data"))
            elif tag == "iframe" and name == "srcdoc":
                self.result.removable.append((value_start, value_end, "iframe_srcdoc"))
            elif name in CONTENT_ATTRIBUTES or name.startswith("data-"):
                self.result.attributes.append((value_start, value_end, name, value))

    def handle_endtag(self, tag: str) -> None:
        if self.raw_mode == tag:
            end = self.source.find(">", self._offset()) + 1
            if tag == "script":
                self.result.removable.append((self.raw_start, end, "script"))
            self.raw_mode = None
        if tag in BLOCK:
            self.result.segments.append("\n")
        elif tag in CELL:
            self.result.segments.append(" ")

    def handle_data(self, data: str) -> None:
        start = self._offset()
        if self.raw_mode == "script":
            self.result.scripts.append(data)
            return
        if self.raw_mode == "style":
            for match in _CSS_VALUE.finditer(data):
                group = next(g for g in (1, 2, 3) if match.group(g) is not None)
                value = match.group(group)
                begin, end = start + match.start(group), start + match.end(group)
                if _DATA_URL.search(value):
                    self.result.removable.append((begin, end, "embedded_data"))
                else:
                    self.result.css.append((begin, end, value))
            return
        self.result.segments.append(Segment(start, start + len(data), data, True))

    def _reference(self, raw: str) -> None:
        start = self._offset()
        if self.raw_mode is not None:
            return
        self.result.segments.append(Segment(start, start + len(raw), html.unescape(raw), False))

    def handle_entityref(self, name: str) -> None:
        start = self._offset()
        raw = (
            "&"
            + name
            + (";" if self.source[start + 1 + len(name) : start + 2 + len(name)] == ";" else "")
        )
        self._reference(raw)

    def handle_charref(self, name: str) -> None:
        start = self._offset()
        raw = (
            "&#"
            + name
            + (";" if self.source[start + 2 + len(name) : start + 3 + len(name)] == ";" else "")
        )
        self._reference(raw)

    def handle_comment(self, data: str) -> None:
        start = self._offset()
        end = self.source.find("-->", start) + 3
        self.result.comments.append(data)
        self.result.removable.append((start, end if end > 2 else len(self.source), "comment"))


def parse(source: str) -> Markup:
    parser = _Parser(source)
    parser.feed(source)
    parser.close()
    return parser.result


@dataclass
class MarkupReport:
    transformations: int = 0
    removed: dict[str, int] = field(default_factory=dict)


def rewrite_html(source: str, rewrite: Rewrite) -> tuple[str, MarkupReport]:
    """Transformed copy of ``source``; markup outside the edited values is unchanged."""
    report = MarkupReport()
    markup = parse(source)
    edits: list[tuple[int, int, str]] = []
    # Visible text as one stream, mapped back to raw offsets.
    spans: list[tuple[Segment, int, int]] = []
    cursor = 0
    for segment in markup.segments:
        if isinstance(segment, str):
            cursor += len(segment)
            continue
        spans.append((segment, cursor, cursor + len(segment.text)))
        cursor += len(segment.text)
    text = markup.text()
    if text.strip():
        _, mappings = rewrite(text)
        report.transformations += len(mappings)
        for start, end, replacement in mappings:
            placed = False
            for segment, a, b in spans:
                if b <= start or a >= end:
                    continue
                if segment.exact:
                    left = segment.start + max(start, a) - a
                    right = segment.start + min(end, b) - a
                else:  # a character reference is replaced whole
                    left, right = segment.start, segment.end
                edits.append(
                    (left, right, html.escape(replacement, quote=False) if not placed else "")
                )
                placed = True
    for start, end, name, value in markup.attributes:
        if not value.strip():
            continue
        if name == "style":
            output, count = rewrite_css(value, rewrite)
        else:
            output, mappings = rewrite(value)
            count = len(mappings)
        if count:
            report.transformations += count
            edits.append((start, end, html.escape(output, quote=True)))
    for start, end, value in markup.css:
        output, mappings = rewrite(value)
        if mappings:
            report.transformations += len(mappings)
            edits.append((start, end, _css_escape(output)))
    for start, end, reason in markup.removable:
        replacement = "" if reason in {"comment", "script", "iframe_srcdoc"} else "data:,"
        edits.append((start, end, replacement))
        report.removed[reason] = report.removed.get(reason, 0) + 1
    return _apply(source, edits), report


def css_values(css: str) -> list[str]:
    """String literals and url() arguments of a CSS text (style attributes, readers)."""
    values = []
    for match in _CSS_VALUE.finditer(css):
        values.append(next(g for g in match.groups() if g is not None))
    return values


def rewrite_css(css: str, rewrite: Rewrite) -> tuple[str, int]:
    """Rewrite each CSS string literal and url() argument; data: URLs are emptied."""
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        group = next(g for g in (1, 2, 3) if match.group(g) is not None)
        value = match.group(group)
        if _DATA_URL.search(value):
            count += 1
            new = "data:,"
        else:
            new, mappings = rewrite(value)
            count += len(mappings)
            new = _css_escape(new)
        text = match.group(0)
        offset = match.start(group) - match.start(0)
        return text[:offset] + new + text[offset + len(value) :]

    return _CSS_VALUE.sub(replace, css), count


def _css_escape(value: str) -> str:
    return re.sub(r"""(["'\\()\n])""", r"\\\1", value)


def _apply(source: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply non-overlapping edits; an edit inside a removed region is dropped."""
    edits.sort(key=lambda e: (e[0], -(e[1] - e[0])))
    kept: list[tuple[int, int, str]] = []
    for edit in edits:
        if kept and edit[0] < kept[-1][1]:
            previous = kept[-1]
            if edit[1] <= previous[1] and previous[2] == "":
                continue  # inside removed content (comment, script)
            if edit[0] >= previous[0] and edit[1] <= previous[1]:
                continue
            raise ValueError("Overlapping HTML edits")
        kept.append(edit)
    parts = []
    cursor = 0
    for start, end, replacement in kept:
        parts.append(source[cursor:start])
        parts.append(replacement)
        cursor = end
    parts.append(source[cursor:])
    return "".join(parts)


__all__ = ["Markup", "MarkupReport", "css_values", "parse", "rewrite_css", "rewrite_html"]
