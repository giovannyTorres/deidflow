"""Read OpenDocument text documents and spreadsheets (ODT, ODS).

Shared XML traversal inspects text, attributes, sheet grids and package parts.
Uninspected source channels preserve incomplete coverage. Automatic rewriting
is not available in this reader increment.
"""

from __future__ import annotations

import base64
import binascii
import posixpath
import re
import zipfile
import zlib
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import unquote, urlsplit
from xml.dom import minidom
from xml.etree import ElementTree as ET
from xml.parsers import expat

from deidflow.office import CellGrid, Node, _local, _parse
from deidflow.readers import DocumentError, _archive, _xml

OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
XLINK = "http://www.w3.org/1999/xlink"
FORM = "urn:oasis:names:tc:opendocument:xmlns:form:1.0"
SCRIPT = "urn:oasis:names:tc:opendocument:xmlns:script:1.0"
CONFIG = "urn:oasis:names:tc:opendocument:xmlns:config:1.0"
MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
CALCEXT = "urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0"
PRESENTATION = "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0"
CHART = "urn:oasis:names:tc:opendocument:xmlns:chart:1.0"

MEDIA_TYPES = {
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}
MAX_REPEAT = 16_384  # repeated rows/cells with content: at most this count each
MAX_EXPANDED_CELLS = 2_000_000  # cell positions with content per sheet
MAX_CLONED_CELLS = 200_000  # cell elements created when splitting repeats
MAX_XML_DEPTH = 128
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


_EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|/|\\)")


# --- shared walk --------------------------------------------------------------


def _parse_odf(data: bytes, *, graph: Any | None = None) -> Node:
    """Inspect original XML before the shared DOM parser strips hidden nodes."""
    depth = 0
    hidden = False

    def start(_name: str, _attributes: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > MAX_XML_DEPTH:
            raise DocumentError("OpenDocument XML nesting exceeds the supported depth")

    def end(_name: str) -> None:
        nonlocal depth
        depth -= 1

    def uninspected(*_arguments: Any) -> None:
        nonlocal hidden
        hidden = True

    def reject_declaration(*_arguments: Any) -> NoReturn:
        raise DocumentError("OpenDocument XML entity declarations are unsupported")

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CommentHandler = uninspected
    parser.ProcessingInstructionHandler = uninspected
    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(data, True)
    except expat.ExpatError:
        raise DocumentError("Malformed OpenDocument XML part") from None
    if hidden and graph is not None:
        from deidflow.readers import _issue

        _issue(graph, "uninspected_odf_xml_channels")
    try:
        return _parse(data)
    except RecursionError:
        raise DocumentError("OpenDocument XML nesting exceeds the supported depth") from None


def _qualified(node: Node) -> tuple[str, str]:
    return node.namespaceURI or "", _local(node)


def _elements(root: Node) -> list[Node]:
    return list(root.getElementsByTagName("*"))


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


def structural_names(root: Node) -> Iterator[str]:
    """Qualified names, including namespace aliases and empty attribute names."""
    seen: set[str] = set()
    for element in _elements(root):
        for name in (element.tagName, *element.attributes.keys()):
            if name not in seen:
                seen.add(name)
                yield name


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


def _is_sheet(table: Node) -> bool:
    parent = table.parentNode
    return parent is not None and _qualified(parent) == (OFFICE, "spreadsheet")


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


def _zip_stream_status(archive: zipfile.ZipFile) -> str:
    """Validate bounded expansion before ZipFile can silently discard stream tails."""
    handle = archive.fp
    if handle is None:
        return "invalid"
    position = handle.tell()
    status = "complete"
    try:
        for info in archive.infolist():
            handle.seek(info.header_offset)
            header = handle.read(30)
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                return "invalid"
            skip = int.from_bytes(header[26:28], "little") + int.from_bytes(header[28:30], "little")
            handle.seek(skip, 1)
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                return "invalid"
            if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
                return "invalid"
            decoder = (
                zlib.decompressobj(-zlib.MAX_WBITS)
                if info.compress_type == zipfile.ZIP_DEFLATED
                else None
            )
            remaining, expanded, checksum = info.compress_size, 0, 0
            while remaining:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    return "invalid"
                remaining -= len(chunk)
                decoded = (
                    decoder.decompress(chunk, info.file_size - expanded + 1) if decoder else chunk
                )
                expanded += len(decoded)
                checksum = zlib.crc32(decoded, checksum)
                if expanded > info.file_size or (decoder and decoder.unconsumed_tail):
                    return "invalid"
                if decoder and decoder.eof:
                    if decoder.unused_data or remaining:
                        status = "trailing"
                    break
            if expanded != info.file_size or checksum != info.CRC or (decoder and not decoder.eof):
                return "invalid"
        return status
    except (OSError, ValueError, zlib.error):
        return "invalid"
    finally:
        handle.seek(position)


def _uninspected_zip_metadata(archive: zipfile.ZipFile) -> bool:
    """Presence-only checks: never interpret opaque ZIP comments/extra payloads."""
    infos = archive.infolist()
    if archive.comment or any(info.comment or info.extra or info.flag_bits & 8 for info in infos):
        return True
    handle = archive.fp
    if handle is None:
        raise DocumentError("OpenDocument archive is unavailable")
    position = handle.tell()
    try:
        expected = 0
        for info in sorted(infos, key=lambda item: item.header_offset):
            if info.header_offset != expected:
                return True  # prefix, gap or unlisted local content
            handle.seek(info.header_offset)
            header = handle.read(30)
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                raise DocumentError("Malformed OpenDocument local ZIP header")
            name_size = int.from_bytes(header[26:28], "little")
            extra_size = int.from_bytes(header[28:30], "little")
            if extra_size:
                return True  # local extras need not appear in ZipInfo.extra
            if (
                int.from_bytes(header[6:8], "little") != info.flag_bits
                or int.from_bytes(header[8:10], "little") != info.compress_type
                or int.from_bytes(header[14:18], "little") != info.CRC
                or int.from_bytes(header[18:22], "little") != info.compress_size
                or int.from_bytes(header[22:26], "little") != info.file_size
            ):
                return True
            encoding = "utf-8" if info.flag_bits & 0x800 else "cp437"
            if handle.read(name_size) != info.filename.encode(encoding):
                return True  # unlisted local names must not bypass member inspection
            if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
                return True
            expected += 30 + name_size + info.compress_size
        handle.seek(0, 2)
        size = handle.tell()
        if size < 22:
            raise DocumentError("Malformed OpenDocument ZIP footer")
        handle.seek(size - 22)
        footer = handle.read(22)
        if footer[:4] != b"PK\x05\x06":
            return True  # trailing data or an uninspected extended container layout
        central_size = int.from_bytes(footer[12:16], "little")
        central_offset = int.from_bytes(footer[16:20], "little")
        return (
            int.from_bytes(footer[20:22], "little") != 0
            or central_offset != expected
            or central_offset + central_size != size - 22
        )
    finally:
        handle.seek(position)


# --- reader -------------------------------------------------------------------


def read_odf(path: Path, graph: Any, max_bytes: int) -> None:
    from deidflow.readers import _fragment, _issue

    suffix = path.suffix.lower()
    with _archive(path, max_bytes) as archive:
        streams = _zip_stream_status(archive)
        if streams != "complete":
            _issue(graph, "unverified_odf_compressed_stream")
        if streams == "invalid":
            return
        entries = check_package(archive, suffix)
        embedded = subdocuments(entries)
        package_members = _package_members(archive.namelist())
        if _uninspected_zip_metadata(archive):
            _issue(graph, "uninspected_odf_container_metadata")
        if suffix == ".ods":
            # As for XLSX: cell display formats and extensions are not all modelled.
            graph.issues.append("ODS_REVIEW_REQUIRED")
        for name in archive.namelist():
            kind = part_kind(name, embedded)
            _fragment(graph, name, part="ZIP", kind="package_member_name")
            if kind is None:
                _issue(graph, "unsupported_odf_package_part")
            elif kind in {"directory", "configuration", "layout_cache"}:
                if archive.getinfo(name).file_size:
                    _issue(graph, "uninspected_odf_package_channel")
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
                        _parse_odf(archive.read(name), graph=graph),
                        graph,
                        name,
                        spreadsheet=False,
                        package_members=package_members,
                    )
            elif kind == "xml":
                document = _parse_odf(archive.read(name), graph=graph)
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
                    _parse_odf(archive.read(name), graph=graph),
                    graph,
                    name,
                    spreadsheet=False,
                    package_members=package_members,
                )
            elif kind == "settings":
                _read_part(
                    _parse_odf(archive.read(name), graph=graph),
                    graph,
                    name,
                    spreadsheet=False,
                    package_members=package_members,
                )
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
                _read_part(
                    _parse_odf(archive.read(name), graph=graph),
                    graph,
                    name,
                    spreadsheet=False,
                    package_members=package_members,
                )
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

    for name in structural_names(document):
        _fragment(graph, name, part=part, kind="structural_name")
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


__all__ = ["MEDIA_TYPES", "read_odf"]
