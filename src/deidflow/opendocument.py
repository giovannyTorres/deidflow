"""Read and rewrite OpenDocument text documents and spreadsheets (ODT, ODS).

OpenDocument is the format of LibreOffice and of many public administrations.
The reader and the writer share one walk over the XML, so everything the reader
scans is exactly what the writer transforms:

- **Text** of ``content.xml`` and ``styles.xml`` (headers, footers) as one
  stream: paragraphs, headings, lists, tables, footnotes, comments, text boxes,
  captions, alternative text (``svg:title``/``svg:desc``) and the displayed text
  of fields. Spaces (``text:s``), tabs and line breaks are part of the stream.
- **Spreadsheet cells** (ODS) as a grid, so column headers give context, like
  XLSX. Cell values stored apart from the displayed text (``office:value``,
  ``office:date-value``, ``office:string-value``) are scanned too.
- **Attributes that carry content**: descriptions, index keys, bibliography
  fields, link titles; object, bookmark and section names; links; formulas,
  conditions and range addresses.

The writer removes what it cannot keep safely: tracked changes (accepting
them), comment authors and dates, personal metadata (authors, dates, printer,
template, editing time), view settings, the page thumbnail, macros and event
handlers, form controls, digital signatures, password hashes of protected
sections, external links (hyperlinks are unlinked, linked images and sections
removed), pivot tables, data-source links, filter values and data-carrying
validations, conditional formats and named expressions. Fields that hold
personal data (sender, author, file name, dates, variables, database fields,
hidden and conditional text) become their displayed text. Images and embedded
objects (charts) are removed by default, since they cannot be checked without
OCR. Spreadsheet output always needs review, as for XLSX.

XML is edited with ``xml.dom.minidom`` (see ``deidflow.office``) after the
reader's guard rejects DTDs and entity declarations.
"""

from __future__ import annotations

import base64
import binascii
import posixpath
import re
import zipfile
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from xml.dom import minidom
from xml.etree import ElementTree as ET

from deidflow.office import (
    CellGrid,
    Node,
    OfficeReport,
    Rewrite,
    TransformCells,
    _local,
    _parse,
    _remove,
    _rewrite_stream,
    _serialize,
    _standalone,
    _unwrap,
)
from deidflow.readers import DocumentError, _archive, _xml

OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
DC = "http://purl.org/dc/elements/1.1/"
XLINK = "http://www.w3.org/1999/xlink"
FORM = "urn:oasis:names:tc:opendocument:xmlns:form:1.0"
SCRIPT = "urn:oasis:names:tc:opendocument:xmlns:script:1.0"
CONFIG = "urn:oasis:names:tc:opendocument:xmlns:config:1.0"
MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
CALCEXT = "urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0"
LOEXT = "urn:org:documentfoundation:names:experimental:office:xmlns:loext:1.0"
PRESENTATION = "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0"
CHART = "urn:oasis:names:tc:opendocument:xmlns:chart:1.0"

MEDIA_TYPES = {
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}
MAX_REPEAT = 16_384  # repeated rows/cells with content: at most this count each
MAX_EXPANDED_CELLS = 2_000_000  # cell positions with content per sheet
MAX_CLONED_CELLS = 200_000  # cell elements created when splitting repeats
_TEXT_NODES = {minidom.Node.TEXT_NODE, minidom.Node.CDATA_SECTION_NODE}

# Text elements that end a block of text (a fragment boundary for the reader);
# other text elements (spans, links, fields, marks) are inline.
_TEXT_BLOCKS = frozenset(
    {"p", "h", "list-item", "list-header", "section", "note-body", "note-citation",
     "index-title", "index-body", "numbered-paragraph", "table-of-content",
     "alphabetical-index", "illustration-index", "table-index", "object-index",
     "user-index", "bibliography", "changed-region", "deletion"}
)  # fmt: skip

# Content attributes, scanned and transformed in place.
_DATA_ATTRIBUTES = frozenset(
    {(TEXT, name) for name in (
        "description", "string-value", "string-value-phonetic", "key1", "key2",
        "key1-phonetic", "key2-phonetic", "address", "annote", "author", "booktitle",
        "chapter", "edition", "editor", "howpublished", "identifier", "institution",
        "isbn", "issn", "journal", "month", "note", "number", "organizations", "pages",
        "publisher", "report-type", "school", "series", "title", "url", "volume", "year",
        "custom1", "custom2", "custom3", "custom4", "custom5", "label", "value",
    )}
    | {(OFFICE, "title"), (XLINK, "title"), (TABLE, "title"), (META, "name"),
       (STYLE, "display-name")}
)  # fmt: skip
# Typed values stored apart from the displayed text.
_VALUE_ATTRIBUTES = frozenset(
    {(OFFICE, "value"), (OFFICE, "string-value"), (OFFICE, "date-value"),
     (OFFICE, "time-value"), (OFFICE, "boolean-value"), (TEXT, "date-value"),
     (TEXT, "time-value")}
)  # fmt: skip
_TYPED_VALUES = (
    (OFFICE, "value"), (OFFICE, "string-value"), (OFFICE, "date-value"),
    (OFFICE, "time-value"), (OFFICE, "boolean-value"), (OFFICE, "currency"),
)  # fmt: skip
# Names of bookmarks, sections, frames, tables, variables... renamed consistently.
_NAME_ATTRIBUTES = frozenset(
    {(TEXT, "name"), (TEXT, "ref-name"), (DRAW, "name"), (OFFICE, "name"), (TABLE, "name")}
)
# Formulas and conditions: never edited as text (sheet references are renamed).
_FORMULA_ATTRIBUTES = frozenset(
    {(TABLE, "formula"), (TABLE, "expression"), (TABLE, "condition"), (TEXT, "formula"),
     (TEXT, "condition"), (STYLE, "condition"), (CALCEXT, "value"), (TABLE, "value")}
)  # fmt: skip
_ADDRESS_ATTRIBUTES = frozenset(
    {(TABLE, "cell-range-address"), (TABLE, "base-cell-address"),
     (TABLE, "target-range-address"), (TABLE, "cell-address"), (TABLE, "print-ranges"),
     (TABLE, "source-cell-range-addresses"), (TABLE, "target-cell-address"),
     (CALCEXT, "base-cell-address"), (CALCEXT, "target-range-address"),
     (DRAW, "notify-on-update-of-ranges"), (CHART, "cell-range-address"),
     (CHART, "values-cell-range-address"), (CHART, "label-cell-address")}
)  # fmt: skip
# Fields whose content is personal or document data: kept as static text.
_FLATTENED_FIELDS = frozenset(
    {"sender-firstname", "sender-lastname", "sender-initials", "sender-title",
     "sender-position", "sender-email", "sender-phone-private", "sender-fax",
     "sender-company", "sender-phone-work", "sender-street", "sender-city",
     "sender-postal-code", "sender-country", "sender-state-or-province", "author-name",
     "author-initials", "initial-creator", "creator", "creation-date", "creation-time",
     "print-date", "print-time", "printed-by", "modification-date", "modification-time",
     "editing-cycles", "editing-duration", "title", "subject", "description", "keywords",
     "user-defined", "file-name", "template-name", "database-display", "database-next",
     "database-row-select", "database-row-number", "database-name", "hidden-text",
     "conditional-text", "execute-macro", "drop-down", "text-input", "user-field-get",
     "user-field-input", "variable-get", "variable-set", "variable-input", "expression",
     "table-formula", "date", "time", "placeholder", "meta-field", "dde-connection"}
)  # fmt: skip
_PERSONAL_META = frozenset(
    {(META, "initial-creator"), (DC, "creator"), (META, "creation-date"), (DC, "date"),
     (META, "printed-by"), (META, "print-date"), (META, "editing-cycles"),
     (META, "editing-duration"), (META, "template"), (META, "auto-reload"),
     (META, "hyperlink-behaviour"), (META, "generator")}
)  # fmt: skip
# Custom properties that Word and LibreOffice fill from the user profile (as in DOCX).
_PERSONAL_PROPERTIES = frozenset({"company", "manager", "hyperlinkbase"})
_ANNOTATION_PERSONAL = frozenset({"creator", "date", "date-string", "creator-initials",
                                  "sender-initials"})  # fmt: skip
_EMBEDDING = frozenset(
    {"image", "object", "object-ole", "plugin", "applet", "floating-frame"}
)  # draw:* elements that show a picture or an embedded object
_ACTIVE = frozenset(
    {(OFFICE, "scripts"), (OFFICE, "event-listeners"), (SCRIPT, "event-listener"),
     (PRESENTATION, "event-listener"), (TEXT, "script"), (OFFICE, "forms"),
     (DRAW, "control")}
)  # fmt: skip
# Empty containers that LibreOffice writes in every document.
_ACTIVE_CONTAINERS = frozenset({(OFFICE, "scripts"), (OFFICE, "event-listeners"),
                                (OFFICE, "forms")})  # fmt: skip


def _active(element: Node) -> bool:
    key = _qualified(element)
    if key not in _ACTIVE:
        return False
    return key not in _ACTIVE_CONTAINERS or any(
        child.nodeType == child.ELEMENT_NODE for child in element.childNodes
    )


_REMOVED_ELEMENTS = {
    (TEXT, "tracked-changes"): "tracked_changes",
    (TABLE, "tracked-changes"): "tracked_changes",
    (TEXT, "change"): "tracked_changes",
    (TEXT, "change-start"): "tracked_changes",
    (TEXT, "change-end"): "tracked_changes",
    (TEXT, "hidden-paragraph"): "hidden_content",
    (TABLE, "data-pilot-tables"): "pivot_tables",
    (TABLE, "dde-links"): "external_links",
    (TABLE, "table-source"): "external_links",
    (TABLE, "cell-range-source"): "external_links",
    (TEXT, "section-source"): "external_links",
    (TEXT, "dde-connection-decls"): "external_links",
    (OFFICE, "dde-source"): "external_links",
    (TABLE, "database-source-sql"): "data_sources",
    (TABLE, "database-source-table"): "data_sources",
    (TABLE, "database-source-query"): "data_sources",
    (TABLE, "filter"): "criteria",
}
_EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|/|\\)")
_SHEET_REFERENCE = "(?<![\\w'])"


# --- shared walk --------------------------------------------------------------


def _qualified(node: Node) -> tuple[str, str]:
    return node.namespaceURI or "", _local(node)


def _elements(root: Node) -> list[Node]:
    return list(root.getElementsByTagName("*"))


def _attached(node: Node) -> bool:
    """False for elements inside a subtree removed earlier in the same pass."""
    while node.parentNode is not None:
        node = node.parentNode
    return bool(node.nodeType == node.DOCUMENT_NODE)


def _deferred(node: Node) -> bool:
    """Comments, notes and shapes inside a paragraph are scanned as their own text."""
    parent = node.parentNode
    if parent is None or parent.nodeType != parent.ELEMENT_NODE or parent.namespaceURI != TEXT:
        return False
    namespace, local = _qualified(node)
    return (
        (namespace == OFFICE and local == "annotation")
        or (namespace == TEXT and local == "note")
        or (namespace == DRAW and local != "a")
    )


def _block(node: Node) -> bool:
    namespace, local = _qualified(node)
    if namespace == TEXT:
        return local in _TEXT_BLOCKS
    return not (namespace == DRAW and local == "a") and not (
        namespace == OFFICE and local == "annotation-end"
    )


# Text elements that only hold other elements; whitespace in them is indentation.
_TEXT_CONTAINERS = frozenset(
    {"list", "tracked-changes", "sequence-decls", "user-field-decls", "variable-decls",
     "dde-connection-decls", "changed-region", "insertion", "deletion", "format-change",
     "note", "note-body", "section", "list-item", "list-header", "index-body"}
)  # fmt: skip


def _whitespace_content(node: Node) -> bool:
    """Whitespace counts only inside paragraphs, headings and inline elements."""
    parent = node.parentNode
    if parent is None or parent.namespaceURI != TEXT:
        return False
    local = _local(parent)
    return local in {"p", "h"} or (local not in _TEXT_BLOCKS and local not in _TEXT_CONTAINERS)


def _count(node: Node) -> int:
    try:
        return max(1, min(int(node.getAttributeNS(TEXT, "c") or "1"), 1024))
    except ValueError:
        return 1


def _cell_text_child(node: Node) -> bool:
    return node.nodeType == node.ELEMENT_NODE and node.namespaceURI == TEXT


def _cell_deferred(cell: Node) -> list[Node]:
    """Comments and shapes of a spreadsheet cell, whose text is not part of the grid."""
    found: list[Node] = []
    stack = list(cell.childNodes)
    while stack:
        node = stack.pop()
        if node.nodeType != node.ELEMENT_NODE:
            continue
        if node.parentNode is cell and not _cell_text_child(node):
            found.append(node)
        elif _deferred(node):
            found.append(node)
        else:
            stack.extend(node.childNodes)
    return found


# (holder, text, block boundary): the holder is a text node, a space/tab/line-break
# element whose value is virtual, or None for a separator between blocks.
Piece = tuple[Node | None, str, bool]


def _walk(root: Node, pieces: list[Piece], deferred: deque[Node], skip_cells: bool) -> None:
    stack: list[tuple[Node, bool]] = [(root, False)]
    while stack:
        node, closing = stack.pop()
        if closing:
            if _block(node):
                pieces.append((None, "\n", True))
            continue
        if node.nodeType in _TEXT_NODES:
            if node.data and (node.data.strip() or _whitespace_content(node)):
                pieces.append((node, node.data, False))
            continue
        if node.nodeType != node.ELEMENT_NODE:
            continue
        namespace, local = _qualified(node)
        if node is not root and _deferred(node):
            deferred.append(node)
            continue
        if namespace == OFFICE and local == "binary-data":
            continue
        if namespace == TEXT and local in {"s", "tab", "line-break"}:
            value = {"tab": "\t", "line-break": "\n"}.get(local) or " " * _count(node)
            pieces.append((node, value, False))  # the element itself holds the value
            continue
        if (
            skip_cells
            and namespace == TABLE
            and local in {"table-cell", "covered-table-cell"}
            and _sheet_cell(node)
        ):
            deferred.extend(_cell_deferred(node))
            continue
        stack.append((node, True))
        stack.extend((child, False) for child in reversed(node.childNodes))


def stream(root: Node, *, skip_cells: bool = False) -> list[Piece]:
    """Text of ``root`` in reading order, then its comments, notes and shapes."""
    if root.nodeType == root.DOCUMENT_NODE:
        root = root.documentElement
    pieces: list[Piece] = []
    deferred: deque[Node] = deque([root])
    while deferred:
        _walk(deferred.popleft(), pieces, deferred, skip_cells)
        pieces.append((None, "\n", True))
    return pieces


def blocks(pieces: list[Piece]) -> list[str]:
    """Reader fragments: the stream split at block boundaries."""
    found: list[str] = []
    current: list[str] = []
    for _, value, boundary in pieces:
        if boundary:
            text = "".join(current)
            if text.strip():
                found.append(text)
            current = []
        else:
            current.append(value)
    if "".join(current).strip():
        found.append("".join(current))
    return found


def paragraph_text(node: Node) -> str:
    """Text of ``node`` itself, without its comments, notes and shapes."""
    pieces: list[Piece] = []
    _walk(node, pieces, deque(), False)
    return "".join(value for _, value, boundary in pieces if not boundary)


def formula_carries_data(formula: str) -> bool:
    """True for string literals and references to other documents (``'file:...'#$Hoja1.A1``)."""
    return '"' in formula or "'#" in formula or bool(re.search(r"://", formula))


def _href_kind(href: str) -> str:
    href = _decoded_href(href)
    if not href:
        return "empty"
    if href.startswith("#"):
        return "internal"
    if _EXTERNAL.match(href):
        return "external"
    return "package"


def _decoded_href(href: str) -> str:
    try:
        return unquote(href, errors="strict")
    except UnicodeError:
        raise DocumentError("Malformed OpenDocument link encoding") from None


def _package_target(href: str, part: str) -> str | None:
    try:
        parsed = urlsplit(href)
        path = _decoded_href(parsed.path)
    except ValueError:
        return None
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in path
        or re.search(r"%(?:2f|5c)", parsed.path, re.IGNORECASE)
        or any(ord(character) <= 32 or ord(character) == 127 for character in href)
        or path.startswith("/")
    ):
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(part), path))
    return None if target in {".", ".."} or target.startswith("../") else target.rstrip("/")


def _package_members(names: list[str]) -> set[str]:
    """Actual ZIP members plus implicit directories, built once per archive."""
    members: set[str] = set()
    for name in names:
        if len(name) > 4096 or name.count("/") > 32:
            raise DocumentError("OpenDocument package path exceeds the reference limit")
        members.add(name.rstrip("/"))
        members.update(name[:index] for index, character in enumerate(name) if character == "/")
        if len(members) > 20_000:
            raise DocumentError("OpenDocument reference inventory exceeds the limit")
    return members


def _href_name(href: str) -> str:
    return _decoded_href(href)[1:].split("|", 1)[0]


def attributes(root: Node) -> Iterator[tuple[Node, str, str]]:
    """(element, qualified attribute name, kind) of every scanned attribute."""
    for element in _elements(root):
        attributes_ = element.attributes
        if attributes_ is None:
            continue
        in_form = False
        # Controls and their form: the office:forms element itself only holds settings.
        holder = element if _qualified(element) != (OFFICE, "forms") else None
        while holder is not None and holder.nodeType == holder.ELEMENT_NODE:
            if (holder.namespaceURI, _local(holder)) in {(OFFICE, "forms"), (DRAW, "control")}:
                in_form = True
                break
            holder = holder.parentNode
        for qualified in list(attributes_.keys()):
            node = attributes_[qualified]
            key = (node.namespaceURI or "", node.localName or qualified.rsplit(":", 1)[-1])
            if not node.value.strip():
                continue
            if qualified == "xmlns" or qualified.startswith("xmlns:"):
                kind = "structural"
            elif in_form and key[0] == FORM:
                kind = "data"
            elif key == (XLINK, "href"):
                kind = "href"
            elif key in _DATA_ATTRIBUTES:
                kind = "data"
            elif key in _VALUE_ATTRIBUTES:
                kind = "value"
            elif key in _NAME_ATTRIBUTES:
                kind = "name"
            elif key in _FORMULA_ATTRIBUTES:
                kind = "formula"
            elif key in _ADDRESS_ATTRIBUTES:
                kind = "address"
            else:
                # Retained attributes are never invisible to the reader. Values
                # with unmodeled structural meaning may be inspected, but not
                # replaced blindly: changing one could break definitions/references.
                kind = "structural"
            yield element, qualified, kind


# --- spreadsheet grid ---------------------------------------------------------


def _repeat(node: Node, name: str) -> int:
    try:
        return max(1, int(node.getAttributeNS(TABLE, name) or "1"))
    except ValueError:
        raise DocumentError("Invalid OpenDocument repetition count") from None


def _owned(element: Node, table: Node) -> bool:
    holder = element.parentNode
    while holder is not None and holder is not table:
        if holder.nodeType == holder.ELEMENT_NODE and _qualified(holder) == (TABLE, "table"):
            return False
        holder = holder.parentNode
    return holder is table


def _rows(table: Node) -> list[Node]:
    return [r for r in table.getElementsByTagNameNS(TABLE, "table-row") if _owned(r, table)]


def _cells(row: Node) -> list[Node]:
    return [
        child
        for child in row.childNodes
        if child.nodeType == child.ELEMENT_NODE
        and child.namespaceURI == TABLE
        and _local(child) in {"table-cell", "covered-table-cell"}
    ]


def cell_text(cell: Node) -> str:
    """Displayed text of a cell; its typed value when nothing is displayed."""
    paragraphs = [paragraph_text(c) for c in cell.childNodes if _cell_text_child(c)]
    text = "\n".join(paragraphs)
    if text.strip():
        return text
    for namespace, name in _TYPED_VALUES[:5]:
        value = cell.getAttributeNS(namespace, name)
        if value:
            return value
    return ""


def _has_content(cell: Node) -> bool:
    """Text, a typed value, a comment or a shape; an empty paragraph is not content."""
    return bool(cell_text(cell)) or any(
        child.nodeType == child.ELEMENT_NODE and not _cell_text_child(child)
        for child in cell.childNodes
    )


def _sheet_cell(cell: Node) -> bool:
    """A cell of a spreadsheet sheet (read as a grid), not of a table inside a shape."""
    holder = cell.parentNode
    while holder is not None and not (
        holder.nodeType == holder.ELEMENT_NODE and _qualified(holder) == (TABLE, "table")
    ):
        holder = holder.parentNode
    return holder is not None and _is_sheet(holder)


def _expand(table: Node) -> None:
    """Split repeated rows and cells that hold content into single elements."""
    budget = 0
    for row in _rows(table):
        rows = _repeat(row, "number-rows-repeated")
        if rows > 1 and any(_has_content(cell) for cell in _cells(row)):
            if rows > MAX_REPEAT:
                raise DocumentError("OpenDocument repeated rows with content exceed limits")
            budget += rows * max(1, len(_cells(row)))
            if budget > MAX_CLONED_CELLS:
                raise DocumentError("OpenDocument sheet exceeds the cell limit")
            row.removeAttributeNS(TABLE, "number-rows-repeated")
            anchor = row
            for _ in range(rows - 1):
                copy = row.cloneNode(True)
                row.parentNode.insertBefore(copy, anchor.nextSibling)
                anchor = copy
    for row in _rows(table):
        for cell in _cells(row):
            columns = _repeat(cell, "number-columns-repeated")
            if columns > 1 and _has_content(cell):
                if columns > MAX_REPEAT:
                    raise DocumentError("OpenDocument repeated cells with content exceed limits")
                budget += columns
                if budget > MAX_CLONED_CELLS:
                    raise DocumentError("OpenDocument sheet exceeds the cell limit")
                cell.removeAttributeNS(TABLE, "number-columns-repeated")
                anchor = cell
                for _ in range(columns - 1):
                    copy = cell.cloneNode(True)
                    row.insertBefore(copy, anchor.nextSibling)
                    anchor = copy


def sheet_grid(table: Node, *, expand: bool) -> tuple[CellGrid, dict[tuple[int, int], Node]]:
    """Cells with text, by one-based (row, column).

    With ``expand``, repeated rows and cells that hold content are split into
    single elements first, so each position has its own element to rewrite.
    """
    if expand:
        _expand(table)
    grid: CellGrid = {}
    located: dict[tuple[int, int], Node] = {}
    total = 0
    row_number = 0
    for row in _rows(table):
        rows = _repeat(row, "number-rows-repeated")
        cells = _cells(row)
        if not any(_has_content(cell) for cell in cells):
            row_number += rows
            continue
        if rows > MAX_REPEAT:
            raise DocumentError("OpenDocument repeated rows with content exceed limits")
        for _ in range(rows):
            row_number += 1
            column = 0
            for cell in cells:
                columns = _repeat(cell, "number-columns-repeated")
                if not _has_content(cell):
                    column += columns
                    continue
                if columns > MAX_REPEAT:
                    raise DocumentError("OpenDocument repeated cells with content exceed limits")
                text = cell_text(cell)
                for _ in range(columns):
                    column += 1
                    total += 1
                    if total > MAX_EXPANDED_CELLS:
                        raise DocumentError("OpenDocument sheet exceeds the cell limit")
                    if text:
                        grid[(row_number, column)] = text
                        located[(row_number, column)] = cell
    return grid, located


def sheets(document: Node) -> list[Node]:
    return [
        table
        for spreadsheet in document.getElementsByTagNameNS(OFFICE, "spreadsheet")
        for table in spreadsheet.childNodes
        if table.nodeType == table.ELEMENT_NODE and _qualified(table) == (TABLE, "table")
    ]


# --- package ------------------------------------------------------------------


def manifest(archive: zipfile.ZipFile) -> dict[str, str]:
    """Manifest entries (full path -> media type); encrypted packages are refused."""
    root = _xml(archive.read("META-INF/manifest.xml"))
    if root.tag != f"{{{MANIFEST}}}manifest":
        raise DocumentError("Invalid OpenDocument manifest")
    entries: dict[str, str] = {}
    for entry in root:
        if entry.tag != f"{{{MANIFEST}}}file-entry":
            raise DocumentError("Unsupported OpenDocument manifest entry")
        if any(child.tag.endswith("encryption-data") for child in entry.iter()):
            raise DocumentError("Encrypted OpenDocument packages are unsupported")
        entries[entry.attrib.get(f"{{{MANIFEST}}}full-path", "")] = entry.attrib.get(
            f"{{{MANIFEST}}}media-type", ""
        )
    return entries


def subdocuments(entries: dict[str, str]) -> set[str]:
    """Embedded objects: directories of charts or other documents, OLE object files."""
    found = set()
    for path, media_type in entries.items():
        if path in {"/", ""} or path.startswith(("Configurations2", "META-INF/")):
            continue
        if media_type.startswith("application/vnd.oasis.opendocument."):
            found.add(path if path.endswith("/") else path + "/")
        elif "oleobject" in media_type.lower():
            found.add(path)
    return found


def part_kind(name: str, embedded: set[str]) -> str | None:
    if name.endswith("/"):
        return "directory"
    if name == "mimetype":
        return "mimetype"
    if name == "META-INF/manifest.xml":
        return "manifest"
    if name.startswith("META-INF/") and "signatures" in name.lower() and name.endswith(".xml"):
        return "signature"
    if name in {"content.xml", "styles.xml", "meta.xml"}:
        return "xml"
    if name == "settings.xml":
        return "settings"
    if name == "manifest.rdf":
        return "rdf"
    if name.startswith("Thumbnails/"):
        return "thumbnail"
    if name.startswith(("Pictures/", "media/", "ObjectReplacements/")):
        return "media"
    if any(
        name.startswith(item) if item.endswith("/") else name == item for item in embedded
    ) or re.match(r"Object \d+(?:/|$)", name):
        return "embedded"
    if name.startswith(("Basic/", "Scripts/", "Dialogs/")):
        return "macro"
    if name.startswith("Configurations2/"):
        return "configuration"
    if name == "layout-cache":
        return "layout_cache"
    return None


def check_package(archive: zipfile.ZipFile, suffix: str) -> dict[str, str]:
    names = archive.namelist()
    for required in ("mimetype", "content.xml", "META-INF/manifest.xml"):
        if required not in names:
            raise DocumentError("Missing OpenDocument package part")
    if archive.read("mimetype").decode("ascii", "replace").strip() != MEDIA_TYPES[suffix]:
        raise DocumentError("OpenDocument media type does not match the file extension")
    return manifest(archive)


def binary_strings(data: str) -> list[str]:
    """Readable strings of base64 data: certificate subjects (often a national ID), printers."""
    try:
        raw = base64.b64decode("".join(data.split()), validate=True)
    except (binascii.Error, ValueError):
        return [data]
    text = raw.decode("utf-8", "replace")
    return re.findall(r"[^\x00-\x1f\x7f-\x9f�]{4,}", text)


# --- reader -------------------------------------------------------------------


def read_odf(path: Path, graph: Any, max_bytes: int) -> None:
    from deidflow.readers import _fragment, _issue

    suffix = path.suffix.lower()
    with _archive(path, max_bytes) as archive:
        entries = check_package(archive, suffix)
        embedded = subdocuments(entries)
        package_members = _package_members(archive.namelist())
        if suffix == ".ods":
            # As for XLSX: cell display formats and extensions are not all modelled.
            graph.issues.append("ODS_REVIEW_REQUIRED")
        for name in archive.namelist():
            kind = part_kind(name, embedded)
            if kind is None:
                _issue(graph, "unsupported_odf_package_part")
            elif kind == "thumbnail":
                _issue(graph, "office_thumbnail_requires_review")
            elif kind == "media":
                _issue(graph, "office_media_requires_review")
            elif kind == "macro":
                _issue(graph, "embedded_or_active_content_not_extracted")
                if name.endswith(".xml"):
                    _all_text(_xml(archive.read(name)), graph, name, "macro")
            elif kind == "embedded":
                _issue(graph, "office_drawing_content_requires_review")
                if name.endswith(".xml"):
                    _read_part(
                        _parse(archive.read(name)), graph, name,
                        spreadsheet=False, package_members=package_members,
                    )
            elif kind == "xml":
                document = _parse(archive.read(name))
                if document.documentElement.namespaceURI != OFFICE:
                    raise DocumentError("Unexpected OpenDocument part root")
                _read_part(
                    document,
                    graph,
                    name,
                    spreadsheet=suffix == ".ods" and name == "content.xml",
                    package_members=package_members,
                )
            elif kind == "manifest":
                _read_part(
                    _parse(archive.read(name)), graph, name,
                    spreadsheet=False, package_members=package_members,
                )
            elif kind == "settings":
                root = _xml(archive.read(name))
                for item in root.iter(f"{{{CONFIG}}}config-item"):
                    value = item.text or ""
                    value_type = item.attrib.get(f"{{{CONFIG}}}type")
                    if value_type == "base64Binary":
                        for text in binary_strings(value):
                            _fragment(graph, text, part=name, kind="settings")
                    elif value_type == "string" and value.strip():
                        _fragment(graph, value, part=name, kind="settings")
            elif kind in {"rdf", "signature"}:
                root = _xml(archive.read(name))
                for element in root.iter():
                    value = element.text or ""
                    if element.tag.endswith("X509Certificate"):
                        for text in binary_strings(value):
                            _fragment(graph, text, part=name, kind="certificate")
                    elif value.strip():
                        _fragment(graph, value, part=name, kind="metadata")
                    for attribute in element.attrib.values():
                        if attribute.strip():
                            _fragment(graph, attribute, part=name, kind="metadata")


def _all_text(root: ET.Element, graph: Any, part: str, kind: str) -> None:
    from deidflow.readers import _fragment

    for element in root.iter():
        for value in (element.text, element.tail, *element.attrib.values()):
            if value and value.strip():
                _fragment(graph, value, part=part, kind=kind)


def _read_part(
    document: Node, graph: Any, part: str, *, spreadsheet: bool, package_members: set[str]
) -> None:
    from deidflow.readers import _fragment, _issue

    for element in _elements(document):
        key = _qualified(element)
        if _active(element):
            _issue(graph, "embedded_or_active_content_not_extracted")
        if key == (OFFICE, "binary-data"):
            _issue(graph, "office_media_requires_review")
        if key[0] == DRAW and key[1] in _EMBEDDING:
            _issue(graph, "office_media_requires_review")
    kind = "metadata" if part == "meta.xml" else "paragraph"
    for text in blocks(stream(document, skip_cells=spreadsheet)):
        if any(character.isalnum() for character in text):  # not format punctuation
            _fragment(graph, text, part=part, kind=kind)
    for element, qualified, attribute_kind in attributes(document):
        value = element.getAttribute(qualified)
        if attribute_kind == "href":
            decoded = _decoded_href(value)
            _fragment(graph, decoded, part=part, kind="link_target")
            kind = _href_kind(value)
            if kind == "external":
                _issue(graph, "external_relationships_require_review")
            elif kind == "package" and _package_target(value, part) not in package_members:
                _issue(graph, "unresolved_odf_package_reference")
            continue
        if attribute_kind == "value" and _qualified(element) in {
            (TABLE, "table-cell"),
            (TABLE, "covered-table-cell"),
        }:
            if value == cell_text(element):
                continue
        _fragment(graph, value, part=part, kind=f"attribute_{attribute_kind}")
        if attribute_kind == "formula" and formula_carries_data(value):
            _issue(graph, "spreadsheet_formulas_require_review")
    if spreadsheet:
        for sheet in sheets(document):
            _fragment(graph, sheet.getAttributeNS(TABLE, "name"), part=part, kind="sheet_name")
            grid, _ = sheet_grid(sheet, expand=False)
            for (row, column), text in sorted(grid.items()):
                _fragment(
                    graph,
                    text,
                    part=part,
                    row=row,
                    column=str(column),
                    cell=f"{sheet.getAttributeNS(TABLE, 'name')}:{row}:{column}",
                    kind="cell",
                )


# --- writer -------------------------------------------------------------------


def _flatten(element: Node) -> None:
    """Replace an element by a text node with its displayed text."""
    text = paragraph_text(element)
    parent = element.parentNode
    if parent is None:
        return
    if text:
        parent.insertBefore(element.ownerDocument.createTextNode(text), element)
    parent.removeChild(element)


def _frame(element: Node) -> Node:
    """The draw:frame (or other shape) holding an image or object."""
    holder = element.parentNode
    if holder is not None and holder.namespaceURI == DRAW and _local(holder) == "frame":
        return holder
    return element


def _drop_typed_value(element: Node) -> None:
    for namespace, name in _TYPED_VALUES:
        if element.hasAttributeNS(namespace, name):
            element.removeAttributeNS(namespace, name)
    if element.hasAttributeNS(OFFICE, "value-type"):
        element.setAttributeNS(OFFICE, _prefixed(element, OFFICE, "value-type"), "string")
    if element.hasAttributeNS(CALCEXT, "value-type"):
        element.setAttributeNS(CALCEXT, _prefixed(element, CALCEXT, "value-type"), "string")
    for namespace, name in ((TEXT, "date-value"), (TEXT, "time-value"), (TABLE, "formula")):
        if element.hasAttributeNS(namespace, name):
            element.removeAttributeNS(namespace, name)


def _prefix(document: Node, namespace: str) -> str:
    root = document.documentElement
    for index in range(root.attributes.length):
        attribute = root.attributes.item(index)
        if attribute.name.startswith("xmlns:") and attribute.value == namespace:
            return str(attribute.name[6:])
    raise DocumentError("OpenDocument namespace declaration is missing")


def _prefixed(element: Node, namespace: str, local: str) -> str:
    node = element.getAttributeNodeNS(namespace, local)
    return node.name if node is not None else local


def _rename_sheets(text: str, renames: dict[str, str]) -> str:
    for old, new in renames.items():
        quoted = "'" + old.replace("'", "''") + "'"
        text = re.sub(
            re.escape(quoted) + r"(?=\.)|" + _SHEET_REFERENCE + re.escape(old) + r"(?=\.)",
            new,
            text,
        )
    return text


def _set_cell(cell: Node, text: str) -> None:
    for child in list(cell.childNodes):
        if _cell_text_child(child) or child.nodeType in _TEXT_NODES:
            cell.removeChild(child)
    _drop_typed_value(cell)
    document = cell.ownerDocument
    prefix = _prefix(document, TEXT)
    for line in text.split("\n"):
        paragraph = document.createElementNS(TEXT, f"{prefix}:p")
        if line:
            paragraph.appendChild(document.createTextNode(line))
        cell.appendChild(paragraph)


class _Writer:
    def __init__(
        self,
        rewrite: Rewrite,
        report: OfficeReport,
        *,
        remove_media: bool,
        removed_parts: set[str],
        package_members: set[str],
    ) -> None:
        self.rewrite = rewrite
        self.report = report
        self.remove_media = remove_media
        self.removed_parts = removed_parts
        self.package_members = package_members
        self.names: dict[str, str] = {}
        self.sheet_renames: dict[str, str] = {}

    def scrub(self, document: Node, *, part: str) -> None:
        """Removals and flattening, before any text is scanned."""
        report = self.report
        for element in _elements(document):
            if not _attached(element):
                continue
            key = _qualified(element)
            if key in _REMOVED_ELEMENTS:
                _remove(element)
                report.count(_REMOVED_ELEMENTS[key])
            elif key in _ACTIVE:
                if _active(element):
                    report.count("active_content")
                _remove(element)
            elif key[0] == OFFICE and key[1] == "annotation":
                for child in list(element.childNodes):
                    if child.nodeType == child.ELEMENT_NODE and (
                        _local(child) in _ANNOTATION_PERSONAL
                    ):
                        element.removeChild(child)
                        report.count("authors")
        for element in _elements(document):
            if not _attached(element):
                continue
            key = _qualified(element)
            if key[0] == TEXT and key[1] in _FLATTENED_FIELDS:
                _flatten(element)
                report.count("fields_flattened")
        for element in _elements(document):
            if not _attached(element):
                continue
            for local in ("protection-key", "protection-key-digest-algorithm",
                          "protection-key-digest-algorithm-2"):  # fmt: skip
                for namespace in (TEXT, TABLE, LOEXT):
                    if element.hasAttributeNS(namespace, local):
                        element.removeAttributeNS(namespace, local)
                        report.count("protection_keys")
            href = element.getAttributeNS(XLINK, "href")
            key = _qualified(element)
            kind = _href_kind(href)
            if kind == "external" or (
                kind == "package"
                and (
                    _package_target(href, part) not in self.package_members
                    or _package_target(href, part) in self.removed_parts
                )
            ):
                if key in {(TEXT, "a"), (DRAW, "a")}:
                    _unwrap(element)
                    report.count("hyperlinks_unlinked")
                else:
                    _remove(_frame(element) if key[0] == DRAW else element)
                    report.count("external_links" if kind == "external" else "media")
            elif self.remove_media and key[0] == DRAW and key[1] in _EMBEDDING:
                _remove(_frame(element))
                report.count("media")
        for element in _elements(document):
            if not _attached(element):
                continue
            key = _qualified(element)
            if key == (OFFICE, "binary-data") or (
                self.remove_media
                and key
                in {
                    (STYLE, "background-image"),
                    (DRAW, "fill-image"),
                    (TEXT, "list-level-style-image"),
                }  # fmt: skip
            ):
                holder = element.parentNode if key == (OFFICE, "binary-data") else element
                _remove(_frame(holder) if holder.namespaceURI == DRAW else holder)
                report.count("media")
        if self.remove_media:
            for element in _elements(document):
                if element.hasAttributeNS(DRAW, "fill-image-name"):
                    element.removeAttributeNS(DRAW, "fill-image-name")
                    if element.getAttributeNS(DRAW, "fill") == "bitmap":
                        element.setAttributeNS(DRAW, _prefixed(element, DRAW, "fill"), "none")

    def collect_names(self, documents: list[Node]) -> None:
        """Names that carry data get neutral names, the same in every part."""
        for document in documents:
            for element, qualified, kind in attributes(document):
                if kind != "name":
                    continue
                if _qualified(element) == (TABLE, "table") and _is_sheet(element):
                    continue
                value = element.getAttribute(qualified)
                if (
                    value not in self.names
                    and _standalone(value, self.rewrite, OfficeReport()) != value
                ):
                    self.names[value] = f"nombre-{len(self.names) + 1}"

    def criteria(self, document: Node) -> None:
        """Drop validations, named expressions, conditional formats and maps with data."""
        report = self.report
        dropped_validations: set[str] = set()
        for element in _elements(document):
            if not _attached(element):
                continue
            key = _qualified(element)
            if key == (TABLE, "content-validation"):
                condition = _rename_sheets(
                    element.getAttributeNS(TABLE, "condition"), self.sheet_renames
                )
                if formula_carries_data(condition):
                    dropped_validations.add(element.getAttributeNS(TABLE, "name"))
                    _remove(element)
                    report.count("criteria")
            elif key in {(TABLE, "named-range"), (TABLE, "named-expression")}:
                name = element.getAttributeNS(TABLE, "name")
                expression = _rename_sheets(
                    element.getAttributeNS(TABLE, "expression")
                    + element.getAttributeNS(TABLE, "cell-range-address"),
                    self.sheet_renames,
                )
                if formula_carries_data(expression) or (
                    _standalone(name, self.rewrite, OfficeReport()) != name
                ):
                    _remove(element)
                    report.count("defined_names")
            elif key[0] == CALCEXT and element.hasAttributeNS(CALCEXT, "value"):
                if formula_carries_data(element.getAttributeNS(CALCEXT, "value")):
                    _remove(element)
                    report.count("criteria")
            elif key == (STYLE, "map"):
                if formula_carries_data(element.getAttributeNS(STYLE, "condition")):
                    _remove(element)
                    report.count("criteria")
        for element in _elements(document):
            if _qualified(element) == (CALCEXT, "conditional-format") and not any(
                child.nodeType == child.ELEMENT_NODE for child in element.childNodes
            ):
                _remove(element)
            if element.getAttributeNS(TABLE, "content-validation-name") in dropped_validations:
                element.removeAttributeNS(TABLE, "content-validation-name")
        for container in ("content-validations", "named-expressions"):
            for element in document.getElementsByTagNameNS(TABLE, container):
                if not any(child.nodeType == child.ELEMENT_NODE for child in element.childNodes):
                    _remove(element)

    def text_formulas(self, document: Node) -> None:
        for element in _elements(document):
            if not _attached(element):
                continue
            key = _qualified(element)
            for attribute in ((TEXT, "condition"), (TEXT, "formula")):
                value = element.getAttributeNS(*attribute)
                if value and formula_carries_data(value):
                    element.removeAttributeNS(*attribute)
                    if (
                        key == (TEXT, "section")
                        and element.getAttributeNS(TEXT, "display") == "condition"
                    ):
                        element.setAttributeNS(TEXT, _prefixed(element, TEXT, "display"), "true")
                    self.report.count("formulas_replaced_by_values")

    def rename_sheets(self, document: Node) -> None:
        used = {sheet.getAttributeNS(TABLE, "name") for sheet in sheets(document)}
        for index, sheet in enumerate(sheets(document), start=1):
            name = sheet.getAttributeNS(TABLE, "name")
            if _standalone(name, self.rewrite, self.report) != name:
                new = f"Hoja{index}"
                while new in used:
                    new += "_"
                used.add(new)
                self.sheet_renames[name] = new
                sheet.setAttributeNS(TABLE, _prefixed(sheet, TABLE, "name"), new)

    def cells(self, document: Node, transform_cells: TransformCells) -> None:
        tables = sheets(document)
        grids: list[tuple[str, CellGrid]] = []
        located: list[dict[tuple[int, int], Node]] = []
        for table in tables:
            grid, cells = sheet_grid(table, expand=True)
            grids.append((table.getAttributeNS(TABLE, "name"), grid))
            located.append(cells)
        changes = transform_cells(grids)
        for cells, changed in zip(located, changes, strict=True):
            self.report.transformations += len(changed)
            for position, text in changed.items():
                _set_cell(cells[position], text)
            for position, cell in cells.items():
                if position in changed:
                    continue
                self._typed_value(cell)
        for table in tables:
            for row in _rows(table):
                for cell in _cells(row):
                    formula = cell.getAttributeNS(TABLE, "formula")
                    if not formula:
                        continue
                    renamed = _rename_sheets(formula, self.sheet_renames)
                    if formula_carries_data(renamed):
                        cell.removeAttributeNS(TABLE, "formula")
                        self.report.count("formulas_replaced_by_values")
                    elif renamed != formula:
                        cell.setAttributeNS(TABLE, _prefixed(cell, TABLE, "formula"), renamed)

    def _typed_value(self, element: Node) -> None:
        """Values kept apart from an unchanged displayed text are checked on their own."""
        for namespace, name in _VALUE_ATTRIBUTES:
            value = element.getAttributeNS(namespace, name)
            if value and _standalone(value, self.rewrite, self.report) != value:
                _drop_typed_value(element)
                self.report.count("typed_values")
                return

    def text(self, document: Node, *, spreadsheet: bool) -> None:
        holders = [
            (element, paragraph_text(element))
            for element in _elements(document)
            if any(element.hasAttributeNS(*key) for key in _VALUE_ATTRIBUTES)
            and not (spreadsheet and _qualified(element)[0] == TABLE)
        ]
        pieces = stream(document, skip_cells=spreadsheet)
        replaced: list[tuple[int, int]] = []

        def rewrite(text: str) -> tuple[str, list[tuple[int, int, str]]]:
            output, mappings = self.rewrite(text)
            replaced.extend((start, end) for start, end, _ in mappings)
            return output, mappings

        _rewrite_stream(
            [(node if _is_text(node) else None, value) for node, value, _ in pieces],
            rewrite,
            self.report,
        )
        # Spaces, tabs and line breaks inside a replaced value go with it.
        cursor = 0
        for node, value, _ in pieces:
            start, cursor = cursor, cursor + len(value)
            if node is not None and not _is_text(node) and _attached(node):
                if any(a <= start and cursor <= b for a, b in replaced):
                    _remove(node)
        for element, before in holders:
            if paragraph_text(element) != before:
                _drop_typed_value(element)  # the displayed value changed
            else:
                self._typed_value(element)

    def attributes(self, document: Node) -> None:
        report = self.report
        for element, qualified, kind in list(attributes(document)):
            if not _attached(element):
                continue
            value = element.getAttribute(qualified)
            if kind == "data":
                new = _standalone(value, self.rewrite, report)
                if new != value:
                    element.setAttribute(qualified, new)
            elif kind == "structural":
                if _standalone(value, self.rewrite, OfficeReport()) != value:
                    raise DocumentError("Sensitive OpenDocument structural metadata is unsupported")
            elif kind == "name":
                if value in self.names:
                    element.setAttribute(qualified, self.names[value])
            elif kind == "href" and _href_kind(value) == "internal":
                target = _href_name(value)
                decoded = _decoded_href(value)
                if target in self.names:
                    element.setAttribute(
                        qualified, "#" + self.names[target] + decoded[1 + len(target) :]
                    )
                elif _standalone(decoded, self.rewrite, OfficeReport()) != decoded:
                    if _qualified(element) in {(TEXT, "a"), (DRAW, "a")}:
                        _unwrap(element)
                    else:
                        element.removeAttribute(qualified)
                    report.count("hyperlinks_unlinked")
            elif kind in {"formula", "address"}:
                renamed = _rename_sheets(value, self.sheet_renames)
                if renamed != value:
                    element.setAttribute(qualified, renamed)

    def meta(self, document: Node) -> None:
        for element in _elements(document):
            if not _attached(element):
                continue
            key = _qualified(element)
            if key in _PERSONAL_META or (
                key == (META, "user-defined")
                and element.getAttributeNS(META, "name").lower() in _PERSONAL_PROPERTIES
            ):
                _remove(element)
                self.report.count("personal_properties")


def _is_text(node: Node | None) -> bool:
    return node is not None and node.nodeType in _TEXT_NODES


def _is_sheet(table: Node) -> bool:
    parent = table.parentNode
    return parent is not None and _qualified(parent) == (OFFICE, "spreadsheet")


def rewrite_odf(
    source: Path,
    target: Path,
    rewrite: Rewrite,
    transform_cells: TransformCells,
    *,
    max_bytes: int,
    remove_media: bool = True,
) -> OfficeReport:
    """Write a transformed copy of an ODT or ODS package; never overwrites ``source``."""
    report = OfficeReport()
    suffix = source.suffix.lower()
    spreadsheet = suffix == ".ods"
    with _archive(source, max_bytes) as archive:
        entries = check_package(archive, suffix)
        embedded = subdocuments(entries)
        names = archive.namelist()
        package_members = _package_members(names)
        kinds = {name: part_kind(name, embedded) for name in names}
        if None in kinds.values():
            raise DocumentError("Unsupported OpenDocument package part")
        removed: set[str] = set()
        for name, kind in kinds.items():
            if kind in {"directory", "settings", "rdf", "configuration", "layout_cache"}:
                removed.add(name)
            elif kind == "thumbnail":
                removed.add(name)
                report.count("thumbnail")
            elif kind == "signature":
                removed.add(name)
                report.count("signatures")
            elif kind == "macro":
                removed.add(name)
                report.count("macros")
            elif remove_media and kind in {"media", "embedded"}:
                removed.add(name)
                report.count("media_parts")
        removed_targets = {name.rstrip("/") for name in removed} | {
            directory.rstrip("/") for directory in embedded if remove_media
        }
        writer = _Writer(
            rewrite, report, remove_media=remove_media,
            removed_parts=removed_targets, package_members=package_members,
        )
        documents = {
            name: _parse(archive.read(name))
            for name in ("content.xml", "styles.xml", "meta.xml")
            if name in names
        }
        for name, document in documents.items():
            if document.documentElement.namespaceURI != OFFICE:
                raise DocumentError("Unexpected OpenDocument part root")
            writer.scrub(document, part=name)
        if "meta.xml" in documents:
            writer.meta(documents["meta.xml"])
        if spreadsheet:
            writer.rename_sheets(documents["content.xml"])
        writer.collect_names([d for n, d in documents.items() if n != "meta.xml"])
        for document in documents.values():
            writer.criteria(document)
            writer.text_formulas(document)
        if spreadsheet:
            writer.cells(documents["content.xml"], transform_cells)
        for name, document in documents.items():
            writer.text(document, spreadsheet=spreadsheet and name == "content.xml")
            writer.attributes(document)
        retained = [name for name in names if name not in removed]
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as out:
            mimetype = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
            mimetype.compress_type = zipfile.ZIP_STORED
            out.writestr(mimetype, MEDIA_TYPES[suffix].encode("ascii"))
            for name in retained:
                if name == "mimetype":
                    continue
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                if name in documents:
                    data = _serialize(documents[name])
                elif name == "META-INF/manifest.xml":
                    data = _manifest_xml(entries, retained, suffix)
                elif kinds[name] in {"media", "embedded"}:
                    data = archive.read(name)  # kept only with remove_media=False: never released
                else:
                    raise DocumentError("Unprocessed OpenDocument package part")
                out.writestr(info, data)
    return report


def _manifest_xml(entries: dict[str, str], retained: list[str], suffix: str) -> bytes:
    document = minidom.Document()
    root = document.createElementNS(MANIFEST, "manifest:manifest")
    root.setAttribute("xmlns:manifest", MANIFEST)
    root.setAttribute("manifest:version", "1.3")
    document.appendChild(root)
    paths = (
        ["/"]
        + sorted(
            {
                name.split("/", 1)[0] + "/"
                for name in retained
                if "/" in name
                and name.split("/", 1)[0] + "/" in entries
                and not name.startswith("META-INF/")
            }  # fmt: skip
        )
        + [name for name in retained if name not in {"mimetype", "META-INF/manifest.xml"}]
    )
    for path in paths:
        entry = document.createElementNS(MANIFEST, "manifest:file-entry")
        entry.setAttribute("manifest:full-path", path)
        if path == "/":
            entry.setAttribute("manifest:version", "1.3")
        media_type = (
            MEDIA_TYPES[suffix] if path == "/"
            else "text/xml" if path.endswith(".xml")
            else entries.get(path, "")
        )
        if not re.fullmatch(r"[\w.+-]{1,64}/[\w.+-]{1,128}", media_type):  # not free text
            media_type = "text/xml" if path.endswith(".xml") else "application/octet-stream"
        entry.setAttribute("manifest:media-type", media_type)
        root.appendChild(entry)
    return _serialize(document)


__all__ = ["MEDIA_TYPES", "read_odf", "rewrite_odf"]
