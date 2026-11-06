"""Rewrite Office Open XML documents with sensitive text transformed.

The writer edits the text of a DOCX package in place, so styles, tables and
layout survive. Hidden content that a reader of the output could recover is
removed rather than transformed: tracked deletions and the authors and dates of
revisions and comments, personal document properties, the page thumbnail,
external links, mail-merge settings and data-bearing field codes. Images,
charts, diagrams and embedded objects cannot be checked without OCR, so by
default they are removed too. The caller verifies the result by reading it back.

XML is edited with ``xml.dom.minidom`` because it keeps every namespace
declaration and prefix as written; Word rejects packages whose
``mc:Ignorable`` prefixes lose their declarations. Parts are checked with the
reader's XML guard (no DTDs or entities) before parsing.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.dom import minidom

from deidflow.readers import (
    DocumentError,
    _archive,
    _xml,
    benign_field,
    docx_part_kind,
    docx_word_root,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

# DOM nodes; the minidom stubs are too narrow for generic tree edits.
Node = Any

# rewrite(text) -> (output, [(source_start, source_end, replacement), ...])
Rewrite = Callable[[str], tuple[str, list[tuple[int, int, str]]]]

_MEDIA_DIRS = ("word/media/", "word/embeddings/", "word/charts/", "word/diagrams/", "word/activeX/")
_PERSONAL_CORE = {"creator", "lastModifiedBy", "created", "modified", "lastPrinted"}
_PERSONAL_APP = {"Company", "Manager", "HyperlinkBase"}
_ANONYMOUS = {"author": "DeidFlow", "initials": "DF"}
_REMOVED_ATTRIBUTES = {"date", "dateUtc"}
_RELATIONSHIP_TYPES = {
    R + "/" + name
    for name in (
        "officeDocument",
        "styles",
        "stylesWithEffects",
        "settings",
        "webSettings",
        "fontTable",
        "numbering",
        "theme",
        "footnotes",
        "endnotes",
        "header",
        "footer",
        "comments",
        "customXml",
        "customXmlProps",
        "extended-properties",
        "custom-properties",
        "hyperlink",
        "image",
        "chart",
        "diagramData",
        "diagramLayout",
        "diagramQuickStyle",
        "diagramColors",
        "oleObject",
        "package",
        "control",
        "attachedTemplate",
    )
} | {
    PKG_REL + "/metadata/core-properties",
    PKG_REL + "/metadata/thumbnail",
    "http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects",
}


@dataclass
class OfficeReport:
    transformations: int = 0
    removed: dict[str, int] = field(default_factory=dict)

    def count(self, what: str, n: int = 1) -> None:
        if n:
            self.removed[what] = self.removed.get(what, 0) + n


def _parse(data: bytes) -> Node:
    _xml(data)  # rejects DTDs, entities and malformed XML
    document = minidom.parseString(data)

    def remove_hidden(node: Node) -> None:
        for child in list(node.childNodes):
            if child.nodeType in {child.COMMENT_NODE, child.PROCESSING_INSTRUCTION_NODE}:
                node.removeChild(child)
            else:
                remove_hidden(child)

    remove_hidden(document)
    return document


def _serialize(document: Node) -> bytes:
    return document.toxml(encoding="UTF-8")


def _local(node: Node) -> str:
    return node.localName or node.nodeName.rsplit(":", 1)[-1]


def _elements(root: Node, namespace: str, name: str) -> list[Node]:
    return list(root.getElementsByTagNameNS(namespace, name))


def _remove(node: Node) -> None:
    if node.parentNode is not None:
        node.parentNode.removeChild(node)


def _unwrap(node: Node) -> None:
    parent = node.parentNode
    if parent is None:
        return
    while node.firstChild is not None:
        parent.insertBefore(node.firstChild, node)
    parent.removeChild(node)


def _text_of(element: Node) -> str:
    return "".join(
        c.data for c in element.childNodes if c.nodeType in {c.TEXT_NODE, c.CDATA_SECTION_NODE}
    )


def _set_text(element: Node, text: str, *, preserve: bool = True) -> None:
    for child in list(element.childNodes):
        element.removeChild(child)
    if text:
        element.appendChild(element.ownerDocument.createTextNode(text))
    if preserve and text != text.strip():
        element.setAttribute("xml:space", "preserve")


def _rewrite_stream(
    segments: list[tuple[Node | None, str]], rewrite: Rewrite, report: OfficeReport
) -> None:
    """Apply replacements over a sequence of text elements and virtual separators.

    A replacement lands in the first text element it overlaps; the rest of the
    replaced source text is deleted from the following elements.
    """
    text = "".join(value for _, value in segments)
    if not text.strip():
        return
    _, mappings = rewrite(text)
    if not mappings:
        return
    report.transformations += len(mappings)
    spans: list[tuple[Node, int, int]] = []
    cursor = 0
    for element, value in segments:
        if element is not None:
            spans.append((element, cursor, cursor + len(value)))
        cursor += len(value)
    current = {id(element): _text_of(element) for element, _, _ in spans}
    for start, end, replacement in sorted(mappings, key=lambda m: m[0], reverse=True):
        placed = False
        for element, a, b in spans:
            if b <= start or a >= end or a == b:
                continue
            value = current[id(element)]
            left, right = max(start, a) - a, min(end, b) - a
            if not placed:
                value = value[:left] + replacement + value[right:]
                placed = True
            else:
                value = value[:left] + value[right:]
            current[id(element)] = value
        if not placed:
            raise DocumentError("Replacement could not be placed in document text")
    for element, _, _ in spans:
        if current[id(element)] != _text_of(element):
            _set_text(element, current[id(element)])


def _standalone(value: str, rewrite: Rewrite, report: OfficeReport) -> str:
    if not value.strip():
        return value
    output, mappings = rewrite(value)
    report.transformations += len(mappings)
    return output


def _accept_revisions(root: Node, report: OfficeReport) -> None:
    for name in ("del", "moveFrom", "moveFromRangeStart", "moveFromRangeEnd"):
        for element in _elements(root, W, name):
            _remove(element)
            report.count("tracked_deletions")
    for name in ("ins", "moveTo"):
        for element in _elements(root, W, name):
            _unwrap(element)
    for name in ("moveToRangeStart", "moveToRangeEnd"):
        for element in _elements(root, W, name):
            _remove(element)
    for name in ("rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange", "tcPrChange",
                 "tblGridChange", "tblPrExChange", "numberingChange"):  # fmt: skip
        for element in _elements(root, W, name):
            _remove(element)
            report.count("formatting_revisions")


def _flatten_fields(root: Node, rewrite: Rewrite, report: OfficeReport) -> None:
    """Remove data-bearing field codes, keep their displayed result text."""
    for simple in _elements(root, W, "fldSimple"):
        instruction = simple.getAttributeNS(W, "instr")
        if benign_field(instruction):
            continue
        _unwrap(simple)
        report.count("field_codes")
    stack: list[dict[str, object]] = []
    for run in _elements(root, W, "r"):
        for child in list(run.childNodes):
            if child.nodeType != child.ELEMENT_NODE or child.namespaceURI != W:
                continue
            name = _local(child)
            if name == "fldChar":
                kind = child.getAttributeNS(W, "fldCharType")
                if kind == "begin":
                    stack.append({"parts": [child], "instruction": []})
                elif stack:
                    stack[-1]["parts"].append(child)  # type: ignore[attr-defined]
                    if kind == "end":
                        current = stack.pop()
                        instruction = "".join(current["instruction"])  # type: ignore[arg-type]
                        if not benign_field(instruction):
                            for part in current["parts"]:  # type: ignore[attr-defined]
                                _remove(part)
                            report.count("field_codes")
            elif name == "instrText" and stack:
                stack[-1]["instruction"].append(_text_of(child))  # type: ignore[attr-defined]
                stack[-1]["parts"].append(child)  # type: ignore[attr-defined]
    # Benign instructions that remain are still scanned.
    for element in _elements(root, W, "instrText"):
        text = _text_of(element)
        new = _standalone(text, rewrite, report)
        if new != text:
            _set_text(element, new)


def _rewrite_word_part(
    data: bytes,
    rewrite: Rewrite,
    report: OfficeReport,
    *,
    remove_media: bool,
    dropped_ids: set[str],
) -> bytes:
    root = _parse(data)
    _accept_revisions(root, report)
    if remove_media:
        _remove_drawings(root, report)
    if dropped_ids:
        _drop_references(root, dropped_ids, report)
    for element in root.getElementsByTagName("*"):
        if _local(element) == "presenceInfo":  # account e-mail addresses of commenters
            _remove(element)
            report.count("authors")
    _flatten_fields(root, rewrite, report)
    for element in _elements(root, W, "mailMerge"):
        _remove(element)
        report.count("mail_merge")
    segments: list[tuple[Node | None, str]] = []

    def walk(node: Node) -> None:
        for child in node.childNodes:
            if child.nodeType != child.ELEMENT_NODE:
                continue
            namespace, name = child.namespaceURI, _local(child)
            if name == "t":  # WordprocessingML, DrawingML and Office Math text
                segments.append((child, _text_of(child)))
            elif namespace == W and name == "tab":
                segments.append((None, "\t"))
            elif namespace == W and name in {"br", "cr"}:
                segments.append((None, "\n"))
            elif namespace == W and name == "instrText":
                continue
            else:
                walk(child)
                if (namespace in {W, A} and name == "p") or (namespace == W and name == "tc"):
                    segments.append((None, "\n"))

    walk(root)
    _rewrite_stream(segments, rewrite, report)
    for element in root.getElementsByTagName("*"):
        # Content outside the rendered text stream is still recoverable XML.
        # Transform metadata/extension text rather than silently retaining it.
        if _local(element) not in {"t", "instrText"}:
            for child in element.childNodes:
                if (
                    child.nodeType in {child.TEXT_NODE, child.CDATA_SECTION_NODE}
                    and child.data.strip()
                ):
                    child.data = _standalone(child.data, rewrite, report)
        _anonymize_attributes(element, rewrite, report)
    return _serialize(root)


def _anonymize_attributes(element: Node, rewrite: Rewrite, report: OfficeReport) -> None:
    attributes = element.attributes
    if attributes is None:
        return
    for qualified in list(attributes.keys()):
        local = qualified.rsplit(":", 1)[-1]
        value = element.getAttribute(qualified)
        if local in _ANONYMOUS and value:
            if value != _ANONYMOUS[local]:
                element.setAttribute(qualified, _ANONYMOUS[local])
                report.count("authors")
        elif local in _REMOVED_ATTRIBUTES:
            element.removeAttribute(qualified)
            report.count("revision_dates_and_user_ids")
        elif local in {"descr", "title", "userId"} and value:
            element.setAttribute(qualified, _standalone(value, rewrite, report))
        elif local in {"name", "val"} and _local(element) == "docVar" and value:
            element.setAttribute(qualified, _standalone(value, rewrite, report))


def _remove_drawings(root: Node, report: OfficeReport) -> None:
    """Drop drawings that show images, charts, diagrams or embedded objects."""
    markers = (
        (A, "blip"),
        ("http://schemas.openxmlformats.org/drawingml/2006/chart", "chart"),
        ("http://schemas.openxmlformats.org/drawingml/2006/diagram", "relIds"),
        ("http://schemas.openxmlformats.org/drawingml/2006/picture", "pic"),
        ("urn:schemas-microsoft-com:vml", "imagedata"),
    )
    for name in ("drawing", "pict", "object"):
        for element in _elements(root, W, name):
            if name == "object" or any(_elements(element, ns, local) for ns, local in markers):
                _remove(element)
                report.count("media")


def _rels_owner(rels: str) -> str:
    directory, base = posixpath.split(rels)
    return posixpath.join(posixpath.dirname(directory), base[: -len(".rels")])


def _resolve(owner: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))


def _drop_references(root: Node, ids: set[str], report: OfficeReport) -> None:
    """Remove elements that reference removed relationships (unwrap hyperlinks)."""
    for element in list(root.getElementsByTagName("*")):
        if element.parentNode is None:
            continue
        attributes = element.attributes
        if attributes is None:
            continue
        referenced = [
            q
            for q in attributes.keys()
            if element.getAttributeNode(q).namespaceURI == R and element.getAttribute(q) in ids
        ]
        if not referenced:
            continue
        if element.namespaceURI == W and _local(element) == "hyperlink":
            _unwrap(element)
            report.count("hyperlinks_unlinked")
        else:
            _remove(element)
            report.count("link_references")


def rewrite_docx(
    source: Path,
    target: Path,
    rewrite: Rewrite,
    *,
    max_bytes: int,
    remove_media: bool = True,
) -> OfficeReport:
    """Write a transformed copy of ``source``; never overwrites ``source``."""
    report = OfficeReport()
    with _archive(source, max_bytes) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            raise DocumentError("Missing DOCX document part")
        kinds = {name: docx_part_kind(name) for name in names}
        if None in kinds.values():
            raise DocumentError("Unsupported DOCX package part")
        for name, kind in kinds.items():
            if kind == "word" and _xml(archive.read(name)).tag != docx_word_root(name):
                raise DocumentError("Unexpected DOCX document part root")
        removed_parts: set[str] = set()
        for name in names:
            lower = name.lower()
            if kinds[name] == "directory":
                removed_parts.add(name)
            elif lower.startswith("docprops/thumbnail"):
                removed_parts.add(name)
                report.count("thumbnail")
            elif remove_media and (
                any(lower.startswith(d.lower()) for d in _MEDIA_DIRS) or "vbaproject" in lower
            ):
                removed_parts.add(name)
                report.count("media_parts")
        # Relationships: drop external targets and those pointing at removed parts.
        rels_out: dict[str, bytes] = {}
        dropped_ids: dict[str, set[str]] = {}
        for name in names:
            if not name.endswith(".rels") or name in removed_parts:
                continue
            owner = _rels_owner(name)
            if owner in removed_parts:
                removed_parts.add(name)
                continue
            if owner and owner not in names:
                raise DocumentError("DOCX relationship owner is missing")
            document = _parse(archive.read(name))
            if (
                document.documentElement.namespaceURI != PKG_REL
                or _local(document.documentElement) != "Relationships"
            ):
                raise DocumentError("Invalid DOCX relationships part")
            clean = minidom.Document()
            root = clean.createElementNS(PKG_REL, "Relationships")
            root.setAttribute("xmlns", PKG_REL)
            clean.appendChild(root)
            ids: set[str] = set()
            seen_ids: set[str] = set()
            for relation in document.documentElement.childNodes:
                if relation.nodeType != relation.ELEMENT_NODE:
                    if (
                        relation.nodeType in {relation.TEXT_NODE, relation.CDATA_SECTION_NODE}
                        and relation.data.strip()
                    ):
                        raise DocumentError("Unexpected DOCX relationship content")
                    continue
                if relation.namespaceURI != PKG_REL or _local(relation) != "Relationship":
                    raise DocumentError("Unsupported DOCX relationship")
                relation_id = relation.getAttribute("Id")
                if not re.fullmatch(r"rId[0-9]+", relation_id) or relation_id in seen_ids:
                    raise DocumentError("Unsupported DOCX relationship identifier")
                seen_ids.add(relation_id)
                mode = relation.getAttribute("TargetMode")
                if mode not in {"", "Internal", "External"}:
                    raise DocumentError("Unsupported DOCX relationship mode")
                external = relation.getAttribute("TargetMode") == "External"
                target_name = _resolve(owner, relation.getAttribute("Target"))
                if external or target_name in removed_parts:
                    ids.add(relation_id)
                    report.count("external_links" if external else "relationships")
                    continue
                relation_type = relation.getAttribute("Type")
                if relation_type not in _RELATIONSHIP_TYPES or target_name not in names:
                    raise DocumentError("Unsupported DOCX relationship target or type")
                new_relation = clean.createElementNS(PKG_REL, "Relationship")
                new_relation.setAttribute("Id", relation_id)
                new_relation.setAttribute("Type", relation_type)
                new_relation.setAttribute(
                    "Target", posixpath.relpath(target_name, posixpath.dirname(owner) or ".")
                )
                root.appendChild(new_relation)
            dropped_ids[owner] = ids
            rels_out[name] = _serialize(clean)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for info in archive.infolist():
                name = info.filename
                if name in removed_parts:
                    continue
                if name in rels_out:
                    data = rels_out[name]
                elif name == "[Content_Types].xml":
                    data = _content_types(archive.read(name), set(names) - removed_parts)
                elif name.startswith("word/") and name.endswith(".xml"):
                    data = _rewrite_word_part(
                        archive.read(name),
                        rewrite,
                        report,
                        remove_media=remove_media,
                        dropped_ids=dropped_ids.get(name, set()),
                    )
                elif name.startswith("docProps/") and name.endswith(".xml"):
                    data = _rewrite_properties(archive.read(name), rewrite, report)
                elif name.lower().startswith("customxml/") and name.endswith(".xml"):
                    data = _rewrite_all_text(archive.read(name), rewrite, report)
                elif kinds[name] == "media":
                    data = archive.read(name)
                else:
                    raise DocumentError("Unsupported DOCX package part")
                out.writestr(_copy_info(info), data)
    return report


def _copy_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    copy = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
    copy.compress_type = zipfile.ZIP_DEFLATED
    copy.external_attr = 0o600 << 16
    return copy


def _content_types(data: bytes, retained: set[str]) -> bytes:
    """Rebuild declarations; source metadata/extra attributes are not payloads."""
    document = _parse(data)
    if (
        document.documentElement.namespaceURI != CONTENT_TYPES
        or _local(document.documentElement) != "Types"
    ):
        raise DocumentError("Invalid DOCX content types part")
    clean = minidom.Document()
    root = clean.createElementNS(CONTENT_TYPES, "Types")
    root.setAttribute("xmlns", CONTENT_TYPES)
    clean.appendChild(root)
    for extension, mime in (
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
    ):
        default = clean.createElementNS(CONTENT_TYPES, "Default")
        default.setAttribute("Extension", extension)
        default.setAttribute("ContentType", mime)
        root.appendChild(default)
    prefix = "application/vnd.openxmlformats-officedocument."
    for name in sorted(retained):
        kind = docx_part_kind(name)
        if kind in {"relationships", "content_types", "directory"}:
            continue
        if kind == "word":
            local = (docx_word_root(name) or "").rsplit("}", 1)[-1]
            local = {"hdr": "header", "ftr": "footer", "fonts": "fontTable"}.get(local, local)
            mime = prefix + "wordprocessingml." + local + "+xml"
            if local == "document":
                mime = prefix + "wordprocessingml.document.main+xml"
            elif local == "theme":
                mime = prefix + "theme+xml"
            elif name == "word/stylesWithEffects.xml":
                mime = "application/vnd.ms-word.stylesWithEffects+xml"
        elif name == "docProps/core.xml":
            mime = "application/vnd.openxmlformats-package.core-properties+xml"
        elif name == "docProps/app.xml":
            mime = prefix + "extended-properties+xml"
        elif name == "docProps/custom.xml":
            mime = prefix + "custom-properties+xml"
        elif name.startswith("customXml/itemProps"):
            mime = prefix + "customXmlProperties+xml"
        elif kind == "custom":
            mime = "application/xml"
        else:
            # Retained media can only reach a blocked candidate, never release.
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
                Path(name).suffix.lower(), "application/octet-stream"
            )
        override = clean.createElementNS(CONTENT_TYPES, "Override")
        override.setAttribute("PartName", "/" + name)
        override.setAttribute("ContentType", mime)
        root.appendChild(override)
    return _serialize(clean)


def _rewrite_properties(data: bytes, rewrite: Rewrite, report: OfficeReport) -> bytes:
    document = _parse(data)
    for element in list(document.getElementsByTagName("*")):
        local = _local(element)
        if local in _PERSONAL_CORE or local in _PERSONAL_APP:
            _remove(element)
            report.count("personal_properties")
    _rewrite_text_nodes(document, rewrite, report)
    return _serialize(document)


def _rewrite_all_text(data: bytes, rewrite: Rewrite, report: OfficeReport) -> bytes:
    document = _parse(data)
    _rewrite_text_nodes(document, rewrite, report)
    return _serialize(document)


def _rewrite_text_nodes(document: Node, rewrite: Rewrite, report: OfficeReport) -> None:
    """Transform every text node and attribute value (data parts, properties)."""
    for element in document.getElementsByTagName("*"):
        for child in element.childNodes:
            if child.nodeType in {child.TEXT_NODE, child.CDATA_SECTION_NODE} and child.data.strip():
                child.data = _standalone(child.data, rewrite, report)
        attributes = element.attributes
        for qualified in list(attributes.keys()) if attributes is not None else []:
            if qualified == "xmlns" or qualified.startswith("xmlns:"):
                continue
            value = element.getAttribute(qualified)
            new = _standalone(value, rewrite, report)
            if new != value:
                element.setAttribute(qualified, new)


__all__ = ["OfficeReport", "rewrite_docx"]
