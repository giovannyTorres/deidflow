"""Rewrite Office Open XML documents (DOCX, XLSX) with sensitive text transformed.

The writer edits the text of a DOCX package in place, so styles, tables and
layout survive; ``rewrite_xlsx`` does the same for workbooks. Hidden content that a reader of the output could recover is
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
    xlsx_part_kind,
    xlsx_part_root,
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
        elif _local(element) == "pageSetup":  # printer settings: drop only the link
            for qualified in referenced:
                element.removeAttribute(qualified)
        else:
            _remove(element)
            report.count("link_references")


def _relationships(
    archive: zipfile.ZipFile, removed_parts: set[str], report: OfficeReport
) -> tuple[dict[str, bytes], dict[str, set[str]]]:
    """Rebuild supported XLSX relationships without retaining hidden metadata."""
    names = archive.namelist()
    allowed_types = _RELATIONSHIP_TYPES | {
        R + "/" + name
        for name in (
            "worksheet",
            "sharedStrings",
            "table",
            "vmlDrawing",
            "calcChain",
            "externalLink",
            "pivotTable",
            "pivotCacheDefinition",
            "pivotCacheRecords",
            "connections",
            "queryTable",
        )
    }
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
            raise DocumentError("XLSX relationship owner is missing")
        document = _parse(archive.read(name))
        if (
            document.documentElement.namespaceURI != PKG_REL
            or _local(document.documentElement) != "Relationships"
        ):
            raise DocumentError("Invalid XLSX relationships part")
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
                    raise DocumentError("Unexpected XLSX relationship content")
                continue
            if relation.namespaceURI != PKG_REL or _local(relation) != "Relationship":
                raise DocumentError("Unsupported XLSX relationship")
            relation_id = relation.getAttribute("Id")
            if not re.fullmatch(r"rId[0-9]+", relation_id) or relation_id in seen_ids:
                raise DocumentError("Unsupported XLSX relationship identifier")
            seen_ids.add(relation_id)
            mode = relation.getAttribute("TargetMode")
            if mode not in {"", "Internal", "External"}:
                raise DocumentError("Unsupported XLSX relationship mode")
            external = relation.getAttribute("TargetMode") == "External"
            target_name = _resolve(owner, relation.getAttribute("Target"))
            if external or target_name in removed_parts:
                ids.add(relation_id)
                report.count("external_links" if external else "relationships")
                continue
            relation_type = relation.getAttribute("Type")
            if relation_type not in allowed_types or target_name not in names:
                raise DocumentError("Unsupported XLSX relationship target or type")
            new_relation = clean.createElementNS(PKG_REL, "Relationship")
            new_relation.setAttribute("Id", relation_id)
            new_relation.setAttribute("Type", relation_type)
            new_relation.setAttribute(
                "Target", posixpath.relpath(target_name, posixpath.dirname(owner) or ".")
            )
            root.appendChild(new_relation)
        dropped_ids[owner] = ids
        rels_out[name] = _serialize(clean)
    return rels_out, dropped_ids


def _targets(archive: zipfile.ZipFile, owner: str) -> dict[str, tuple[str, str]]:
    """Relationship ID -> (resolved internal target, type) for one part."""
    rels = posixpath.join(posixpath.dirname(owner), "_rels", posixpath.basename(owner) + ".rels")
    if rels not in archive.namelist():
        return {}
    document = _parse(archive.read(rels))
    return {
        relation.getAttribute("Id"): (
            _resolve(owner, relation.getAttribute("Target")),
            relation.getAttribute("Type"),
        )
        for relation in document.getElementsByTagNameNS(PKG_REL, "Relationship")
        if relation.getAttribute("TargetMode") != "External"
    }


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


def _content_types(data: bytes, retained: set[str], *, xlsx: bool = False) -> bytes:
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
        kind = xlsx_part_kind(name) if xlsx else docx_part_kind(name)
        if kind in {"relationships", "content_types", "directory"}:
            continue
        if kind == "spreadsheet":
            local = (xlsx_part_root(name) or "").rsplit("}", 1)[-1]
            local = {"sst": "sharedStrings", "styleSheet": "styles"}.get(local, local)
            mime = prefix + "spreadsheetml." + local + "+xml"
            if local == "workbook":
                mime = prefix + "spreadsheetml.sheet.main+xml"
            elif local == "theme":
                mime = prefix + "theme+xml"
        elif kind == "word":
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


def _rewrite_properties(
    data: bytes, rewrite: Rewrite, report: OfficeReport, renames: dict[str, str] | None = None
) -> bytes:
    document = _parse(data)
    for element in list(document.getElementsByTagName("*")):
        local = _local(element)
        if local in _PERSONAL_CORE or local in _PERSONAL_APP:
            _remove(element)
            report.count("personal_properties")
    for element in document.getElementsByTagName("*"):  # sheet names listed in app.xml
        for child in element.childNodes:
            if child.nodeType == child.TEXT_NODE and child.data in (renames or {}):
                child.data = (renames or {})[child.data]
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


# --- XLSX -------------------------------------------------------------------

S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

# (row, column) -> cell text, both one-based.
CellGrid = dict[tuple[int, int], str]
# [(sheet name, grid)] -> per sheet, the new text of every changed cell.
TransformCells = Callable[[list[tuple[str, CellGrid]]], list[CellGrid]]

_REMOVED_XLSX_PREFIXES = (
    "xl/pivotcache/",
    "xl/pivottables/",
    "xl/externallinks/",
    "xl/threadedcomments/",
    "xl/persons/",
    "xl/querytables/",
    "xl/printersettings/",
)
_REMOVED_XLSX_PARTS = {"xl/connections.xml", "xl/calcchain.xml"}
_XLSX_MEDIA_PREFIXES = ("xl/media/", "xl/embeddings/", "xl/charts/", "xl/activex/", "xl/ctrlprops/")
_HEADER_FOOTER = {
    "oddHeader",
    "evenHeader",
    "firstHeader",
    "oddFooter",
    "evenFooter",
    "firstFooter",
}
_INVALID_SHEET = set("[]:*?/\\")


def _column(letters: str) -> int:
    number = 0
    for character in letters:
        number = number * 26 + (ord(character.upper()) - 64)
    return number


def _reference(reference: str) -> tuple[int, int]:
    if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", reference):
        raise DocumentError("Invalid XLSX cell reference")
    letters = "".join(c for c in reference if c.isalpha())
    digits = "".join(c for c in reference if c.isdigit())
    if not letters or not digits:
        raise DocumentError("Invalid XLSX cell reference")
    row, column = int(digits), _column(letters)
    if row > 1048576 or column > 16384:
        raise DocumentError("XLSX cell reference exceeds worksheet bounds")
    return row, column


def _children(element: Node, namespace: str, name: str) -> list[Node]:
    return [
        child
        for child in element.childNodes
        if child.nodeType == child.ELEMENT_NODE
        and child.namespaceURI == namespace
        and _local(child) == name
    ]


def _all_text(element: Node) -> str:
    return "".join(_text_of(t) for t in element.getElementsByTagNameNS(S, "t"))


def _set_inline(cell: Node, text: str) -> None:
    """Replace a cell's value and formula with an inline string."""
    for child in list(cell.childNodes):
        if child.nodeType == child.ELEMENT_NODE and _local(child) in {"f", "v", "is"}:
            cell.removeChild(child)
    document = cell.ownerDocument
    inline = document.createElementNS(S, cell.prefix + ":is" if cell.prefix else "is")
    value = document.createElementNS(S, cell.prefix + ":t" if cell.prefix else "t")
    _set_text(value, text)
    inline.appendChild(value)
    extension = _children(cell, S, "extLst")
    cell.insertBefore(inline, extension[0] if extension else None)
    cell.setAttribute("t", "inlineStr")


def _quoted_sheet(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _rename_references(text: str, renames: dict[str, str]) -> str:
    for old, new in renames.items():
        pattern = re.escape(_quoted_sheet(old)) + "!" + "|(?<![\\w.'])" + re.escape(old) + "!"
        replacement = _quoted_sheet(new) + "!"
        text = re.sub(pattern, replacement.replace("\\", "\\\\"), text)
    return text


def rewrite_xlsx(
    source: Path,
    target: Path,
    transform_cells: TransformCells,
    rewrite: Rewrite,
    *,
    max_bytes: int,
    remove_media: bool = True,
) -> OfficeReport:
    """Write a transformed copy of an XLSX workbook; never overwrites ``source``.

    Changed cells become inline strings. The shared-string table is rebuilt from
    the strings still referenced, so replaced and orphaned values do not remain.
    Formulas that carry string literals or external references, or whose cell
    changed, are replaced by their cached value. Pivot tables and caches,
    external links, data connections, threaded comments, printer settings and
    the calculation chain are removed; with ``remove_media`` also drawings,
    charts, images and embedded objects.
    """
    from deidflow.readers import formula_carries_data

    report = OfficeReport()
    with _archive(source, max_bytes) as archive:
        names = archive.namelist()
        if "xl/workbook.xml" not in names:
            raise DocumentError("Missing XLSX workbook part")
        kinds = {name: xlsx_part_kind(name) for name in names}
        if None in kinds.values():
            raise DocumentError("Unsupported XLSX package part")
        for name, kind in kinds.items():
            if kind == "spreadsheet" and _xml(archive.read(name)).tag != xlsx_part_root(name):
                raise DocumentError("Unexpected XLSX document part root")
        removed_parts: set[str] = set()
        for name in names:
            lower = name.lower()
            if kinds[name] == "directory":
                removed_parts.add(name)
            elif lower.startswith("docprops/thumbnail"):
                removed_parts.add(name)
                report.count("thumbnail")
            elif lower.startswith(_REMOVED_XLSX_PREFIXES) or lower in _REMOVED_XLSX_PARTS:
                removed_parts.add(name)
                report.count("derived_or_linked_parts")
            elif remove_media and kinds[name] == "media":
                removed_parts.add(name)
                report.count("media_parts")
        workbook_targets = _targets(archive, "xl/workbook.xml")
        rels_out, dropped_ids = _relationships(archive, removed_parts, report)

        workbook = _parse(archive.read("xl/workbook.xml"))
        _drop_references(workbook, dropped_ids.get("xl/workbook.xml", set()), report)
        for container in ("pivotCaches", "externalReferences"):
            for element in _elements(workbook, S, container):
                if not _children(element, S, container[:-1]):
                    _remove(element)
        for element in list(workbook.getElementsByTagName("*")):
            if _local(element) == "absPath" and element.parentNode is not None:
                # The folder the workbook was saved in, usually with a user name.
                holder = element
                while holder.parentNode is not None and not (
                    holder.namespaceURI == MC and _local(holder) == "AlternateContent"
                ):
                    holder = holder.parentNode
                _remove(holder if holder.parentNode is not None else element)
                report.count("saved_paths")
            elif _local(element) == "fileSharing" and element.getAttribute("userName"):
                element.setAttribute("userName", _ANONYMOUS["author"])
                report.count("authors")
        sheets: list[tuple[str, str, Node]] = []  # (name, part, sheet element)
        renames: dict[str, str] = {}
        used = {sheet.getAttribute("name") for sheet in _elements(workbook, S, "sheet")}
        for index, sheet in enumerate(_elements(workbook, S, "sheet"), start=1):
            name = sheet.getAttribute("name")
            relation = sheet.getAttributeNS(R, "id")
            part = workbook_targets.get(relation, ("", ""))[0]
            if _standalone(name, rewrite, report) != name:
                new = f"Hoja{index}"
                while new in used:
                    new += "_"
                used.add(new)
                renames[name] = new
                sheet.setAttribute("name", new)
            if not re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", part) or part not in names:
                raise DocumentError("Unsupported XLSX sheet relationship")
            if any(existing[1] == part for existing in sheets):
                raise DocumentError("Duplicate XLSX sheet relationship")
            sheets.append((renames.get(name, name), part, sheet))
        if {name for name in names if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", name)} != {
            part for _, part, _ in sheets
        }:
            raise DocumentError("Unreferenced XLSX worksheet is unsupported")
        for definition in _elements(workbook, S, "definedName"):
            text = _rename_references(_text_of(definition), renames)
            if formula_carries_data(text):
                _remove(definition)
                report.count("defined_names")
            else:
                _set_text(definition, text, preserve=False)

        shared: list[Node] = []
        shared_document = None
        if "xl/sharedStrings.xml" in names:
            shared_document = _parse(archive.read("xl/sharedStrings.xml"))
            shared = _children(shared_document.documentElement, S, "si")

        documents: dict[str, Node] = {}
        cells: list[dict[tuple[int, int], Node]] = []
        grids: list[tuple[str, CellGrid]] = []
        for sheet_name, part, _ in sheets:
            document = _parse(archive.read(part))
            documents[part] = document
            grid: CellGrid = {}
            located: dict[tuple[int, int], Node] = {}
            seen_cells: set[tuple[int, int]] = set()
            for cell in _elements(document, S, "c"):
                position = _reference(cell.getAttribute("r"))
                if position in seen_cells:
                    raise DocumentError("Duplicate XLSX cell reference")
                seen_cells.add(position)
                kind = cell.getAttribute("t") or "n"
                values = _children(cell, S, "v")
                raw = _text_of(values[0]) if values else ""
                if kind == "s" and raw:
                    try:
                        index = int(raw)
                        if index < 0:
                            raise ValueError
                        text = _all_text(shared[index])
                    except (ValueError, IndexError):
                        raise DocumentError("Invalid XLSX shared string reference") from None
                elif kind == "inlineStr":
                    inline = _children(cell, S, "is")
                    text = _all_text(inline[0]) if inline else ""
                elif kind in {"b", "e"}:
                    continue
                else:
                    text = raw
                if text:
                    grid[position] = text
                    located[position] = cell
            grids.append((sheet_name, grid))
            cells.append(located)

        changes = transform_cells(grids)
        for (_, part, _), located, changed in zip(sheets, cells, changes, strict=True):
            document = documents[part]
            report.transformations += len(changed)
            # A changed cell may be the master of a shared formula: record the
            # group before its formula is replaced, so dependents do not keep
            # references to a master that no longer exists.
            removed_groups: set[str] = set()
            for position in changed:
                for formula in _children(located[position], S, "f"):
                    if formula.getAttribute("t") == "shared" and formula.getAttribute("ref"):
                        removed_groups.add(formula.getAttribute("si"))
            for position, text in changed.items():
                _set_inline(located[position], text)
            formulas = _elements(document, S, "f")
            for formula in formulas:
                text = _text_of(formula)
                renamed = _rename_references(text, renames)
                if formula_carries_data(renamed) or formula.parentNode.getAttribute("t") == (
                    "inlineStr"
                ):
                    if formula.getAttribute("t") == "shared" and formula.getAttribute("ref"):
                        removed_groups.add(formula.getAttribute("si"))
                    _remove(formula)
                    report.count("formulas_replaced_by_values")
                elif renamed != text:
                    _set_text(formula, renamed, preserve=False)
            for formula in _elements(document, S, "f"):
                if formula.getAttribute("t") == "shared" and formula.getAttribute("si") in (
                    removed_groups
                ):
                    _remove(formula)
                    report.count("formulas_replaced_by_values")
            for element in document.getElementsByTagName("*"):
                if _local(element) in _HEADER_FOOTER:
                    text = _text_of(element)
                    new = _rewrite_header_footer(text, rewrite, report)
                    if new != text:
                        _set_text(element, new, preserve=False)
            _drop_value_criteria(document, report)
            _drop_references(document, dropped_ids.get(part, set()), report)
            for container in ("oleObjects", "controls", "hyperlinks"):
                for element in _elements(document, S, container):
                    if not any(c.nodeType == c.ELEMENT_NODE for c in element.childNodes):
                        _remove(element)

        # Shared strings: keep only those still referenced, in order.
        if shared_document is not None:
            referenced: list[Node] = []
            for document in documents.values():
                for cell in _elements(document, S, "c"):
                    if cell.getAttribute("t") == "s":
                        values = _children(cell, S, "v")
                        if values and _text_of(values[0]):
                            referenced.append(values[0])
            order: dict[int, int] = {}
            for value in referenced:
                order.setdefault(int(_text_of(value)), len(order))
            root = shared_document.documentElement
            for si in shared:
                root.removeChild(si)
            for old in sorted(order, key=order.__getitem__):
                root.appendChild(shared[old])
            for value in referenced:
                _set_text(value, str(order[int(_text_of(value))]), preserve=False)
            root.setAttribute("count", str(len(referenced)))
            root.setAttribute("uniqueCount", str(len(order)))
            report.count("shared_strings_dropped", len(shared) - len(order))

        tables = _table_headers(archive, sheets, grids, changes, rewrite, report)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for info in archive.infolist():
                name = info.filename
                if name in removed_parts:
                    continue
                if name in rels_out:
                    data = rels_out[name]
                elif name == "[Content_Types].xml":
                    data = _content_types(archive.read(name), set(names) - removed_parts, xlsx=True)
                elif name == "xl/workbook.xml":
                    data = _serialize(workbook)
                elif name == "xl/sharedStrings.xml" and shared_document is not None:
                    data = _serialize(shared_document)
                elif name in documents:
                    data = _serialize(documents[name])
                elif name in tables:
                    data = tables[name]
                elif (
                    name.startswith("xl/") and "comments" in name.lower() and name.endswith(".xml")
                ):
                    data = _rewrite_comments(archive.read(name), rewrite, report)
                elif name.startswith("docProps/") and name.endswith(".xml"):
                    data = _rewrite_properties(archive.read(name), rewrite, report, renames)
                elif name.lower().startswith("customxml/") and name.endswith(".xml"):
                    data = _rewrite_all_text(archive.read(name), rewrite, report)
                elif kinds[name] == "spreadsheet":
                    # Only supported formatting parts can reach this branch;
                    # comments/PI are stripped even when formatting is retained.
                    if name not in {"xl/styles.xml"} and not name.startswith("xl/theme/"):
                        raise DocumentError("Unprocessed XLSX data part")
                    data = _serialize(_parse(archive.read(name)))
                elif kinds[name] == "media":
                    data = archive.read(name)
                else:
                    raise DocumentError("Unsupported XLSX package part")
                out.writestr(_copy_info(info), data)
    return report


def _table_headers(
    archive: zipfile.ZipFile,
    sheets: list[tuple[str, str, Node]],
    grids: list[tuple[str, CellGrid]],
    changes: list[CellGrid],
    rewrite: Rewrite,
    report: OfficeReport,
) -> dict[str, bytes]:
    """Keep table column names equal to their (possibly transformed) header cells."""
    from deidflow.readers import formula_carries_data

    out: dict[str, bytes] = {}
    for (_, part, _), (_, grid), changed in zip(sheets, grids, changes, strict=True):
        for target, kind in _targets(archive, part).values():
            if not kind.endswith("/table") or target not in archive.namelist():
                continue
            document = _parse(archive.read(target))
            table = document.documentElement
            first = table.getAttribute("ref").split(":", 1)[0]
            header_rows = table.getAttribute("headerRowCount")
            row, column = _reference(first) if first else (0, 0)
            for offset, element in enumerate(_elements(document, S, "tableColumn")):
                position = (row, column + offset)
                if header_rows != "0" and position in grid:
                    new = changed.get(position, grid[position])
                    if new != element.getAttribute("name"):
                        element.setAttribute("name", new)
                else:
                    name = element.getAttribute("name")
                    element.setAttribute("name", _standalone(name, rewrite, report))
            for formula in list(document.getElementsByTagName("*")):
                if _local(formula) in {"calculatedColumnFormula", "totalsRowFormula"}:
                    if formula_carries_data(_text_of(formula)):
                        _remove(formula)
                        report.count("formulas_replaced_by_values")
            _drop_value_criteria(document, report)
            out[target] = _serialize(document)
    return out


def _deep_text(element: Node) -> str:
    parts: list[str] = []
    for child in element.childNodes:
        if child.nodeType == child.TEXT_NODE:
            parts.append(child.data)
        elif child.nodeType == child.ELEMENT_NODE:
            parts.append(_deep_text(child))
    return "".join(parts)


def _drop_value_criteria(document: Node, report: OfficeReport) -> None:
    """Remove filter, sort, validation and conditional-format criteria holding values.

    AutoFilter criteria (``<filter val="...">``), custom sort lists, validation
    lists (``"Ana,Luis"``) and text rules keep copies of cell values that the
    cell transformation does not reach. The filter range and buttons stay.
    """
    from deidflow.readers import formula_carries_data

    for element in list(document.getElementsByTagName("*")):
        local = _local(element)
        if local == "filterColumn":
            _remove(element)
            report.count("filter_criteria")
        elif local == "sortCondition" and element.getAttribute("customList"):
            element.removeAttribute("customList")
            report.count("filter_criteria")
        elif local in {"dataValidation", "cfRule"} and (
            formula_carries_data(_deep_text(element)) or element.getAttribute("text")
        ):
            _remove(element)
            report.count("value_criteria")
    for container, item in (
        ("dataValidations", "dataValidation"),
        ("conditionalFormatting", "cfRule"),
    ):
        for element in list(document.getElementsByTagName("*")):
            if _local(element) != container:
                continue
            items = [
                c for c in element.childNodes if c.nodeType == c.ELEMENT_NODE and _local(c) == item
            ]
            if not items:
                _remove(element)
            elif element.hasAttribute("count"):
                element.setAttribute("count", str(len(items)))


def _rewrite_header_footer(text: str, rewrite: Rewrite, report: OfficeReport) -> str:
    """Scan with formatting codes blanked (``&LPaciente: ...``), edit the original."""
    from deidflow.readers import header_footer_text

    masked = header_footer_text(text)
    if not masked.strip():
        return text
    _, mappings = rewrite(masked)
    report.transformations += len(mappings)
    for start, end, replacement in sorted(mappings, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def _rewrite_comments(data: bytes, rewrite: Rewrite, report: OfficeReport) -> bytes:
    document = _parse(data)
    for author in _elements(document, S, "author"):
        if _text_of(author) != _ANONYMOUS["author"]:
            _set_text(author, _ANONYMOUS["author"], preserve=False)
            report.count("authors")
    for comment in _elements(document, S, "comment"):
        segments: list[tuple[Node | None, str]] = [
            (t, _text_of(t)) for t in comment.getElementsByTagNameNS(S, "t")
        ]
        _rewrite_stream(segments, rewrite, report)
    return _serialize(document)


__all__ = ["OfficeReport", "rewrite_docx", "rewrite_xlsx"]
