"""Read and rewrite a conservative static HTML subset by source offsets.

Visible text is scanned as one stream (block elements separate lines, table
cells are separated by spaces), so ``<td>Nombre:</td><td>Ana</td>`` gives the
rules their label context. Replacements are placed in the original source at
exact offsets; character references inside a replaced value are replaced whole.
Content attributes are scanned and rewritten one by one. Unsupported names,
active/resource attributes, declarations and CSS outside a small static grammar
are removed. Unknown elements and ambiguous raw-text syntax are rejected. This
module does not claim the semantics of a browser or a general CSS parser.
"""

from __future__ import annotations

import html
import html.entities
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

# rewrite(text) -> (output, [(source_start, source_end, replacement), ...])
Rewrite = Callable[[str], tuple[str, list[tuple[int, int, str]]]]

BLOCK = frozenset(
    {"address", "article", "aside", "blockquote", "body", "br", "dd", "div", "dl", "dt",
     "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
     "head", "header", "hr", "html", "li", "main", "nav", "ol", "p", "pre", "section", "table",
     "tbody", "tfoot", "thead", "title", "tr", "ul"}
)  # fmt: skip
CELL = frozenset({"td", "th", "option", "label"})
# This is a static document subset, not a browser/CSS execution engine. Unknown
# names are not harmless metadata: they can themselves contain identifiers.
TAGS = BLOCK | CELL | frozenset(
    {"a", "abbr", "b", "bdi", "bdo", "caption", "code", "col", "colgroup", "data",
     "del", "details", "dfn", "em", "i", "img", "input", "ins", "kbd", "legend",
     "mark", "meta", "q", "s", "samp", "select", "small", "span", "strong", "sub",
     "summary", "sup", "textarea", "time", "u", "var", "wbr", "script", "style",
     "iframe", "object", "embed", "link"}
)  # fmt: skip
CONTENT_ATTRIBUTES = frozenset(
    {"alt", "title", "value", "content", "placeholder", "aria-label", "label", "summary",
     "abbr", "href", "cite", "longdesc"}
)  # fmt: skip
_NUMERIC_ATTRIBUTES = frozenset({"width", "height", "colspan", "rowspan", "span", "size"})
_BOOLEAN_ATTRIBUTES = frozenset({"checked", "disabled", "selected", "multiple", "readonly"})
_ENUM_ATTRIBUTES = {
    "dir": {"ltr", "rtl", "auto"},
    "lang": {"es", "en", "fr", "de", "it", "pt", "ca", "eu", "gl"},
    "charset": {"utf-8"},
    "type": {
        "text",
        "password",
        "email",
        "tel",
        "number",
        "date",
        "checkbox",
        "radio",
        "submit",
        "reset",
        "button",
        "hidden",
    },
    "align": {"left", "right", "center", "justify"},
    "valign": {"top", "middle", "bottom", "baseline"},
    "scope": {"row", "col", "rowgroup", "colgroup"},
}
_URL_ATTRIBUTES = frozenset({"href", "cite", "longdesc"})
_ACTIVE_ATTRIBUTES = frozenset(
    {"src", "srcset", "poster", "data", "background", "action", "formaction", "ping",
     "manifest", "codebase", "xlink:href", "imagesrcset", "srcdoc", "http-equiv"}
)  # fmt: skip
# A data: URL with a payload (images, SVG, documents) cannot be verified by text scanning.
_DATA_SCHEME = re.compile(r"(?<![\w-])data:", re.IGNORECASE)
_COMMENT_CLOSE = re.compile(r"--!?>")


def has_data_payload(value: str) -> bool:
    """True when ``value`` holds a ``data:`` URL with a payload, of any length.

    Linear: each ``data:`` occurrence looks for its comma once, and the search for
    the next occurrence starts after that comma (or stops when there is none).
    """
    position = 0
    while match := _DATA_SCHEME.search(value, position):
        comma = value.find(",", match.end())
        if comma < 0:
            return False
        following = value[comma + 1 : comma + 2]
        gap = value[match.end() : comma]  # gaps of successive iterations are disjoint
        if (
            following
            and not following.isspace()
            and following not in "\"')"
            and not any(c.isspace() for c in gap)
        ):
            return True
        position = comma + 1
    return False


# CSS string literals and url() arguments: generated content and resource URLs.
_CSS_VALUE = re.compile(
    r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|url\(\s*([^()"\'\s][^()\s]*)\s*\)',
    re.IGNORECASE,
)
_ATTRIBUTE = re.compile(
    r"""([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""", re.DOTALL
)
_CHARACTER_REFERENCE = re.compile(r"&(?:#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\f <&#;]{1,32};?)")
_PERCENT_RUN = re.compile(r"(?:%[0-9a-fA-F]{2})+")
_URL_CONTROLS = re.compile(r"[\x00-\x20\x7f]")


def _decode_url_percent_escapes(value: str) -> str:
    for _ in range(3):
        decoded = unquote(value, errors="strict")
        if decoded == value:
            break
        value = decoded
    return value


def _replace_url_source_spans(raw: str, value: str, mappings: list[tuple[int, int, str]]) -> str:
    """Project scan-only URL decoding back to raw attribute text, lazily.

    Decoding never becomes an emitted URL. Percent-encoded UTF-8 scalars and
    HTML references are indivisible source atoms; other bytes remain untouched.
    The bounded map is built only for a value with actual replacements.
    """
    if len(raw) > 1024 * 1024:
        raise ValueError("HTML URL replacement exceeds the mapping limit")
    text = raw
    bounds = [(i, i + 1) for i in range(len(raw))]
    # One HTML-reference pass, then the same three bounded URL-decoding passes.
    for percent in (False, True, True, True):
        pattern = _PERCENT_RUN if percent else _CHARACTER_REFERENCE
        chunks: list[str] = []
        projected: list[tuple[int, int]] = []
        cursor = 0
        for match in pattern.finditer(text):
            chunks.append(text[cursor : match.start()])
            projected.extend(bounds[cursor : match.start()])
            token = match.group()
            consumed = len(token)
            if not percent and not token.startswith("&#"):
                # HTML permits a legacy name without ';' before literal text.
                # Only that recognized prefix is an indivisible source atom.
                for length in range(len(token) - 1, 1, -1):
                    if token[1 : length + 1] in html.entities.html5:
                        consumed = length + 1
                        break
            suffix = token[consumed:]
            token = token[:consumed]
            decoded = unquote(token, errors="strict") if percent else html.unescape(token)
            chunks.append(decoded)
            if decoded == token:
                projected.extend(bounds[match.start() : match.start() + consumed])
            elif percent:
                offset = match.start()
                for character in decoded:
                    end = offset + 3 * len(character.encode("utf-8"))
                    projected.append((bounds[offset][0], bounds[end - 1][1]))
                    offset = end
            else:
                projected.extend(
                    [(bounds[match.start()][0], bounds[match.start() + consumed - 1][1])]
                    * len(decoded)
                )
            chunks.append(suffix)
            projected.extend(bounds[match.start() + consumed : match.end()])
            cursor = match.end()
        chunks.append(text[cursor:])
        projected.extend(bounds[cursor:])
        text, bounds = "".join(chunks), projected
    kept = [i for i, character in enumerate(text) if ord(character) > 32 and ord(character) != 127]
    text = "".join(text[i] for i in kept)
    bounds = [bounds[i] for i in kept]
    if text != value:
        raise ValueError("HTML URL source map is inconsistent")
    edits = []
    for start, end, replacement in mappings:
        if not 0 <= start < end <= len(text):
            raise ValueError("HTML URL replacement has invalid offsets")
        edits.append((bounds[start][0], bounds[end - 1][1], html.escape(replacement, quote=True)))
    return _apply(raw, edits)


def _safe_css(css: str, *, stylesheet: bool) -> bool:
    """Recognize a small static formatting grammar; do not interpret arbitrary CSS.

    Escapes, comments, identifiers in selectors, URLs, generated content, custom
    properties and extension syntax are removed as a unit. Regex extraction of
    string literals cannot establish coverage of a CSS document.
    """
    if len(css) > 65_536 or any(token in css for token in ("\\", "/*", "@", '"', "'")):
        return False
    lengths = {
        "padding",
        "padding-top",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "margin",
        "margin-top",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "width",
        "height",
        "min-width",
        "max-width",
        "font-size",
        "line-height",
        "border-width",
        "border-spacing",
        "text-indent",
    }
    enums = {
        "text-align": {"left", "right", "center", "justify"},
        "font-weight": {
            "normal",
            "bold",
            "100",
            "200",
            "300",
            "400",
            "500",
            "600",
            "700",
            "800",
            "900",
        },
        "font-style": {"normal", "italic", "oblique"},
        "font-family": {
            "serif",
            "sans-serif",
            "monospace",
            "arial",
            "times new roman",
            "verdana",
            "helvetica",
        },
        "display": {"block", "inline", "inline-block", "table", "table-cell", "none"},
        "border-collapse": {"collapse", "separate"},
        "border-style": {"none", "solid", "dotted", "dashed", "double"},
        "white-space": {"normal", "nowrap", "pre", "pre-wrap", "pre-line"},
        "vertical-align": {"top", "middle", "bottom", "baseline"},
        "text-decoration": {"none", "underline", "line-through", "overline"},
    }
    colors = {
        "black",
        "white",
        "red",
        "green",
        "blue",
        "gray",
        "grey",
        "yellow",
        "orange",
        "purple",
        "navy",
        "teal",
        "transparent",
        "inherit",
    }

    def declarations(value: str) -> bool:
        for declaration in value.split(";"):
            if not declaration.strip():
                continue
            name, separator, raw = declaration.partition(":")
            name, raw = name.strip().lower(), raw.strip().lower()
            if not separator:
                return False
            if name in lengths and re.fullmatch(
                r"(?:0|[0-9]{1,4}(?:\.[0-9]{1,3})?(?:px|pt|em|rem|%))(?:\s+(?:0|[0-9]{1,4}(?:\.[0-9]{1,3})?(?:px|pt|em|rem|%))){0,3}",
                raw,
            ):
                continue
            if name in enums and raw in enums[name]:
                continue
            if name in {"color", "background-color", "border-color"} and (
                raw in colors or re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?", raw)
            ):
                continue
            return False
        return True

    if not stylesheet:
        return declarations(css)
    cursor = 0
    rule = re.compile(r"([^{}]+)\{([^{}]*)\}")
    while cursor < len(css):
        while cursor < len(css) and css[cursor].isspace():
            cursor += 1
        if cursor == len(css):
            return True
        match = rule.match(css, cursor)
        if match is None:
            return False
        cursor = match.end()
        for selector in match.group(1).split(","):
            tags = selector.strip().split()
            if not tags or any(tag not in TAGS for tag in tags):
                return False
        if not declarations(match.group(2)):
            return False
    return True


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
    canonical: list[tuple[int, int, str]] = field(default_factory=list)

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
        self.events = 0

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def parse_comment(self, i: int, report: bool = True) -> int:
        # Older supported CPython patch releases do not recognize HTML's --!>
        # terminator. Own this boundary so they neither expose comment bodies as
        # visible text nor consume following prose until a later --> comment.
        raw = self.rawdata
        if not raw.startswith("<!--", i) or raw.startswith(("<!-->", "<!--->"), i):
            raise ValueError("Unsupported HTML comment boundary")
        closing = _COMMENT_CLOSE.search(raw, i + 4)
        if closing is None:
            # parse() supplies the entire source in one feed; incomplete input
            # must not fall back to HTMLParser's final handle_data callback.
            raise ValueError("Unclosed HTML comment")
        if report:
            self.handle_comment(raw[i + 4 : closing.start()])
        return closing.end()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self._offset()
        raw = self.get_starttag_text() or ""
        self._tag(tag, start, raw)
        if tag in {"script", "style"}:
            self.raw_mode, self.raw_start = tag, start

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            raise ValueError("Unsupported self-closing raw-text element")
        start = self._offset()
        self._tag(tag, start, self.get_starttag_text() or "")

    def _tag(self, tag: str, start: int, raw: str) -> None:
        self.events += 1
        if self.events > 100_000 or tag not in TAGS:
            raise ValueError("Unsupported HTML element or element limit exceeded")
        if tag in BLOCK:
            self.result.segments.append("\n")
        elif tag in CELL:
            self.result.segments.append(" ")
        name_end = len(tag) + 1
        cursor = name_end
        for match in _ATTRIBUTE.finditer(raw, name_end, max(name_end, len(raw) - 1)):
            if raw[cursor : match.start()].strip():
                raise ValueError("Unsupported HTML attribute syntax")
            cursor = match.end()
            name = match.group(1).lower()
            for group in (2, 3, 4):
                if match.group(group) is not None:
                    value_start = start + match.start(group)
                    value_end = start + match.end(group)
                    break
            else:
                if name not in _BOOLEAN_ATTRIBUTES:
                    self.result.removable.append(
                        (start + match.start(), start + match.end(), "attribute")
                    )
                continue
            value = html.unescape(self.source[value_start:value_end])
            attribute_span = (start + match.start(), start + match.end())
            if name in _ACTIVE_ATTRIBUTES or name.startswith("on"):
                reason = "embedded_data" if has_data_payload(value) else "attribute"
                if name == "srcdoc":
                    reason = "iframe_srcdoc"
                self.result.removable.append((*attribute_span, reason))
            elif name == "style":
                if not _safe_css(value, stylesheet=False):
                    self.result.removable.append((*attribute_span, "css"))
            elif name in CONTENT_ATTRIBUTES:
                if name in _URL_ATTRIBUTES:
                    # Browser URL parsing ignores embedded ASCII whitespace and
                    # controls. This scheme check is never serialized as a URL.
                    scheme_value = _URL_CONTROLS.sub("", _decode_url_percent_escapes(value))
                    if re.search(r"%[0-9a-fA-F]{2}", scheme_value) or urlsplit(
                        scheme_value
                    ).scheme.lower() not in {"", "http", "https", "mailto", "tel"}:
                        self.result.removable.append((*attribute_span, "attribute"))
                        continue
                    # Retain encoded-PII detection. Its scan offsets are projected
                    # back to the raw attribute when an actual change is required.
                    value = scheme_value
                self.result.attributes.append((value_start, value_end, name, value))
            elif name in _ENUM_ATTRIBUTES and value.lower() in _ENUM_ATTRIBUTES[name]:
                self.result.canonical.append((value_start, value_end, value.lower()))
            elif name in _NUMERIC_ATTRIBUTES and re.fullmatch(r"[0-9]{1,4}%?", value):
                pass
            elif name in _BOOLEAN_ATTRIBUTES and value in {"", name}:
                pass
            else:
                self.result.removable.append((*attribute_span, "attribute"))
        if raw[cursor:-1].strip() not in {"", "/"}:
            raise ValueError("Unsupported HTML attribute syntax")

    def handle_endtag(self, tag: str) -> None:
        if tag not in TAGS:
            raise ValueError("Unsupported HTML element")
        start = self._offset()
        end = self.source.find(">", start) + 1
        if end <= start:
            raise ValueError("Malformed HTML end tag")
        self.result.canonical.append((start, end, f"</{tag}>"))
        if self.raw_mode == tag:
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
            if not _safe_css(data, stylesheet=True):
                self.result.removable.append((start, start + len(data), "css"))
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
        if self.source.startswith("<!--", start):
            body_end = start + 4 + len(data)
            if self.source.startswith("-->", body_end):
                end = body_end + 3
            elif self.source.startswith("--!>", body_end):
                end = body_end + 4
            else:
                raise ValueError("Unsupported HTML comment boundary")
        else:
            # HTMLParser reports bogus <! ... > and </ ... > declarations as
            # comments. Derive their exact boundary from the callback's data,
            # never search onward and accidentally erase clinical prose.
            end = start + 2 + len(data)
            if self.source[end : end + 1] != ">":
                raise ValueError("Unsupported HTML comment boundary")
            end += 1
        self.result.comments.append(data)
        self.result.removable.append((start, end, "comment"))

    def handle_decl(self, decl: str) -> None:
        self._discard_declaration()

    def unknown_decl(self, data: str) -> None:
        self._discard_declaration()

    def handle_pi(self, data: str) -> None:
        self._discard_declaration()

    def _discard_declaration(self) -> None:
        start = self._offset()
        end = self.source.find(">", start) + 1
        if end <= start:
            raise ValueError("Malformed HTML declaration")
        self.result.removable.append((start, end, "declaration"))


def parse(source: str) -> Markup:
    parser = _Parser(source)
    parser.feed(source)
    parser.close()
    if parser.raw_mode is not None:
        raise ValueError("Unclosed HTML raw-text element")
    return parser.result


@dataclass
class MarkupReport:
    transformations: int = 0
    removed: dict[str, int] = field(default_factory=dict)


def rewrite_html(source: str, rewrite: Rewrite) -> tuple[str, MarkupReport]:
    """Transform content and strip unsupported channels from static markup."""
    report = MarkupReport()
    markup = parse(source)
    edits: list[tuple[int, int, str]] = list(markup.canonical)
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
        if output != value:
            report.transformations += count
            if name in _URL_ATTRIBUTES and mappings:
                escaped = _replace_url_source_spans(source[start:end], value, mappings)
            else:
                escaped = html.escape(output, quote=True)
            if source[start - 1] not in "\"'":
                escaped = '"' + escaped + '"'
            edits.append((start, end, escaped))
    for start, end, value in markup.css:
        output, mappings = rewrite(value)
        if mappings:
            report.transformations += len(mappings)
            edits.append((start, end, _css_escape(output)))
    for start, end, reason in markup.removable:
        edits.append((start, end, ""))
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
        if has_data_payload(value):
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


__all__ = [
    "Markup",
    "MarkupReport",
    "css_values",
    "has_data_payload",
    "parse",
    "rewrite_css",
    "rewrite_html",
]
