"""Bounded, local document extraction with explicit completeness information."""

from __future__ import annotations

import csv
import io
import json
import math
import posixpath
import re
import tempfile
import uuid
import warnings
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from deidflow.core import DocumentGraph, Fragment, SourceLocation
from deidflow.ocr import OCREngine, OCRError, OCRResult

DEFAULT_MAX_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_PAGES = 10_000
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Only package parts whose contents are explicitly handled may participate in a
# complete DOCX read or rewrite. Unknown/orphan ZIP members are recoverable data,
# even when Word does not render them.
_DOCX_WORD_ROOTS = {
    "document": "document",
    "styles": "styles",
    "stylesWithEffects": "styles",
    "settings": "settings",
    "webSettings": "webSettings",
    "fontTable": "fonts",
    "numbering": "numbering",
    "footnotes": "footnotes",
    "endnotes": "endnotes",
    "comments": "comments",
}
_DOCX_MEDIA_DIRS = (
    "word/media/",
    "word/embeddings/",
    "word/charts/",
    "word/diagrams/",
    "word/activex/",
)


def docx_word_root(name: str) -> str | None:
    """Expected XML root for the supported Word part names."""
    if name.startswith("word/") and name.endswith(".xml"):
        stem = name[5:-4]
        if stem in _DOCX_WORD_ROOTS:
            return _W + _DOCX_WORD_ROOTS[stem]
        if re.fullmatch(r"header[0-9]+", stem):
            return _W + "hdr"
        if re.fullmatch(r"footer[0-9]+", stem):
            return _W + "ftr"
        if re.fullmatch(r"theme/theme[0-9]+", stem):
            return "{http://schemas.openxmlformats.org/drawingml/2006/main}theme"
    return None


def docx_part_kind(name: str) -> str | None:
    """Classify a canonical, explicitly supported DOCX package member."""
    if "\\" in name or name.startswith("/") or posixpath.normpath(name) != name.rstrip("/"):
        return None
    if name.endswith("/"):
        return "directory"
    if name == "[Content_Types].xml":
        return "content_types"
    if name == "_rels/.rels":
        return "relationships"
    directory, base = posixpath.split(name)
    if posixpath.basename(directory) == "_rels" and base.endswith(".rels"):
        owner = posixpath.join(posixpath.dirname(directory), base[:-5])
        if docx_part_kind(owner) in {"word", "properties", "custom", "media"}:
            return "relationships"
        return None
    if name in {"docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"}:
        return "properties"
    if re.fullmatch(r"customXml/item(?:Props)?[0-9]+\.xml", name):
        return "custom"
    if docx_word_root(name) is not None:
        return "word"
    if any(name.lower().startswith(prefix) for prefix in _DOCX_MEDIA_DIRS):
        return "media"
    if name.lower().startswith("docprops/thumbnail") or name == "word/vbaProject.bin":
        return "media"
    return None


_XLSX_REMOVED_PREFIXES = (
    "xl/pivotcache/",
    "xl/pivottables/",
    "xl/externallinks/",
    "xl/threadedcomments/",
    "xl/persons/",
    "xl/querytables/",
    "xl/printersettings/",
)
_XLSX_MEDIA_PREFIXES = (
    "xl/media/",
    "xl/embeddings/",
    "xl/charts/",
    "xl/activex/",
    "xl/ctrlprops/",
    "xl/drawings/",
)


def xlsx_part_root(name: str) -> str | None:
    roots = {
        "xl/workbook.xml": "workbook",
        "xl/sharedStrings.xml": "sst",
        "xl/styles.xml": "styleSheet",
    }
    if name in roots:
        return _S + roots[name]
    for pattern, root in (
        (r"xl/worksheets/sheet[0-9]+\.xml", "worksheet"),
        (r"xl/tables/table[0-9]+\.xml", "table"),
        (r"xl/comments[0-9]+\.xml", "comments"),
    ):
        if re.fullmatch(pattern, name):
            return _S + root
    if re.fullmatch(r"xl/theme/theme[0-9]+\.xml", name):
        return "{http://schemas.openxmlformats.org/drawingml/2006/main}theme"
    return None


def xlsx_part_kind(name: str) -> str | None:
    """Closed supported package boundary for supervised XLSX transformation."""
    if "\\" in name or name.startswith("/") or posixpath.normpath(name) != name.rstrip("/"):
        return None
    if name.endswith("/"):
        return "directory"
    if name == "[Content_Types].xml":
        return "content_types"
    if name == "_rels/.rels":
        return "relationships"
    directory, base = posixpath.split(name)
    if posixpath.basename(directory) == "_rels" and base.endswith(".rels"):
        owner = posixpath.join(posixpath.dirname(directory), base[:-5])
        if xlsx_part_kind(owner) in {"spreadsheet", "properties", "custom", "media", "removed"}:
            return "relationships"
        return None
    common = docx_part_kind(name)
    if common in {"properties", "custom"}:
        return common
    if xlsx_part_root(name) is not None:
        return "spreadsheet"
    lower = name.lower()
    if lower.startswith(_XLSX_REMOVED_PREFIXES) or lower in {
        "xl/connections.xml",
        "xl/calcchain.xml",
    }:
        return "removed"
    if (
        lower.startswith(_XLSX_MEDIA_PREFIXES)
        or lower.startswith("docprops/thumbnail")
        or lower == "xl/vbaproject.bin"
    ):
        return "media"
    return None


# Field instructions that only compute layout values from the document itself.
BENIGN_FIELDS = frozenset(
    {"PAGE", "NUMPAGES", "SECTIONPAGES", "SECTION", "TOC", "PAGEREF", "REF", "NOTEREF", "SEQ",
     "STYLEREF", "TC", "INDEX", "XE"}
)  # fmt: skip


def benign_field(instruction: str) -> bool:
    """True for Word field codes such as PAGE or TOC that carry no document data."""
    words = instruction.split()
    # Switches and bookmark names only: quoted arguments could carry content.
    return bool(words) and words[0].upper() in BENIGN_FIELDS and '"' not in instruction


def _field_instructions(root: ET.Element) -> list[str]:
    """Complete instructions of simple and complex Word fields, in document order."""
    found: list[str] = []
    stack: list[list[str]] = []
    for element in root.iter():
        if element.tag == _W + "fldSimple":
            found.append(element.attrib.get(_W + "instr", ""))
        elif element.tag == _W + "fldChar":
            kind = element.attrib.get(_W + "fldCharType")
            if kind == "begin":
                stack.append([])
            elif kind == "end" and stack:
                found.append("".join(stack.pop()))
        elif element.tag == _W + "instrText":
            if stack:
                stack[-1].append(element.text or "")
            else:
                found.append(element.text or "")
    found.extend("".join(pieces) for pieces in stack)  # unterminated fields
    return found


_EXTERNAL_WORKBOOK = re.compile(r"\[\d+\]|\[[^\]]*\.(?:xl\w*|csv|ods)\]|://", re.IGNORECASE)


def formula_carries_data(formula: str) -> bool:
    """True when a spreadsheet formula holds a string literal or an external reference.

    Cell arithmetic such as ``SUM(B2:B9)`` or ``Tabla1[Importe]`` only reads cells
    that are scanned themselves; ``"Juan"&A1`` or ``[1]Hoja1!A1`` carries content
    or points outside the workbook.
    """
    return '"' in formula or bool(_EXTERNAL_WORKBOOK.search(formula))


# Spreadsheet header/footer codes: sections (&L &C &R), fonts (&"Arial,Bold"), sizes
# (&12) and fields (&P page, &A sheet, &D date...). Font names are not content.
_HEADER_CODE = re.compile(r'&"[^"]*"|&\d+|&[A-Za-z&]')


def header_footer_text(text: str) -> str:
    """Spreadsheet header/footer text with formatting codes blanked, same length."""
    return _HEADER_CODE.sub(lambda match: " " * len(match.group()), text)


class DocumentError(RuntimeError):
    """Input cannot be safely extracted. Does not include source content."""


class UnsupportedFormat(DocumentError):
    """No reader is available for the source format."""


class OptionalDependencyError(DocumentError):
    """An explicitly required local reader dependency is unavailable."""


def _fragment(
    graph: DocumentGraph,
    text: str,
    *,
    kind: str = "text",
    metadata: dict[str, Any] | None = None,
    **location: Any,
) -> None:
    identifier = f"fragment-{len(graph.fragments)}"
    graph.fragments.append(
        Fragment(
            id=identifier,
            text=text,
            location=SourceLocation(fragment_id=identifier, **location),
            kind=kind,
            metadata=metadata or {},
        )
    )


def _issue(graph: DocumentGraph, issue: str) -> None:
    if issue not in graph.issues:
        graph.issues.append(issue)
    graph.complete = False


def _xml(data: bytes) -> ET.Element:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise DocumentError("XML entity declarations are unsupported")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise DocumentError("Malformed XML document part") from None


def _archive(path: Path, max_bytes: int) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path)
        infos = archive.infolist()
        if len(infos) > 10_000:
            raise DocumentError("Archive member limit exceeded")
        total = 0
        names: set[str] = set()
        for info in infos:
            total += info.file_size
            if info.filename in names:
                raise DocumentError("Duplicate archive member")
            names.add(info.filename)
            if info.flag_bits & 1:
                raise DocumentError("Encrypted Office archives are unsupported")
            if info.file_size > max_bytes or total > min(max_bytes * 8, 512 * 1024 * 1024):
                raise DocumentError("Expanded archive size limit exceeded")
            if info.file_size > 1024 * 1024 and info.file_size / max(info.compress_size, 1) > 1000:
                raise DocumentError("Archive compression ratio limit exceeded")
            if ".." in Path(info.filename).parts or info.filename.startswith(("/", "\\")):
                raise DocumentError("Unsafe archive member path")
        return archive
    except (zipfile.BadZipFile, OSError):
        raise DocumentError("Invalid Office archive") from None
    except Exception:
        if "archive" in locals():
            archive.close()
        raise


def _read_metadata(archive: zipfile.ZipFile, graph: DocumentGraph) -> None:
    for name in archive.namelist():
        if name.startswith("docProps/") and name.endswith(".xml"):
            root = _xml(archive.read(name))
            for element in root.iter():
                if element.text and element.text.strip():
                    _fragment(graph, element.text, kind="metadata", part=name)
                for value in element.attrib.values():  # custom property names
                    if value.strip():
                        _fragment(graph, value, kind="metadata", part=name)
        if name.endswith(".rels"):
            root = _xml(archive.read(name))
            for relation in root:
                if relation.attrib.get("TargetMode") == "External":
                    # URI values may themselves contain identity or secrets.
                    _fragment(
                        graph,
                        relation.attrib.get("Target", ""),
                        kind="external_relationship",
                        part=name,
                    )
                    _issue(graph, "external_relationships_require_review")
        lower = name.lower()
        if any(part in lower for part in ("/embeddings/", "vbaproject", "activex")):
            _issue(graph, "embedded_or_active_content_not_extracted")
        if "/media/" in lower:
            _issue(graph, "office_images_require_separate_ocr")
        if lower.startswith("docprops/thumbnail"):
            _issue(graph, "office_thumbnail_requires_review")
        if name.startswith("customXml/") and name.endswith(".xml"):
            root = _xml(archive.read(name))
            for element in root.iter():
                if element.text and element.text.strip():
                    _fragment(graph, element.text, kind="custom_xml", part=name)
                for value in element.attrib.values():
                    if value.strip():
                        _fragment(graph, value, kind="custom_xml", part=name)


def _read_docx(path: Path, graph: DocumentGraph, max_bytes: int) -> None:
    with _archive(path, max_bytes) as archive:
        if "word/document.xml" not in archive.namelist():
            raise DocumentError("Missing DOCX document part")
        if any(docx_part_kind(name) is None for name in archive.namelist()):
            _issue(graph, "unsupported_docx_package_part")
        if any(docx_part_kind(name) == "media" for name in archive.namelist()):
            _issue(graph, "office_media_requires_review")
        _read_metadata(archive, graph)
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            if "/charts/" in name or "/diagrams/" in name:
                _issue(graph, "office_drawing_content_requires_review")
            root = _xml(archive.read(name))
            expected_root = docx_word_root(name)
            if expected_root is not None and root.tag != expected_root:
                raise DocumentError("Unexpected DOCX document part root")
            table_locations: dict[ET.Element, tuple[int, int, int]] = {}
            table_specs: list[dict[str, Any]] = []
            for table_index, table in enumerate(root.iter(_W + "tbl")):
                rows = list(table.findall(_W + "tr"))
                maximum_columns = 0
                for row_index, row_element in enumerate(rows):
                    cells = list(row_element.findall(_W + "tc"))
                    maximum_columns = max(maximum_columns, len(cells))
                    for column_index, cell_element in enumerate(cells):
                        for paragraph in cell_element.iter(_W + "p"):
                            table_locations[paragraph] = (table_index, row_index, column_index)
                table_specs.append(
                    {
                        "part": name,
                        "table": table_index,
                        "rows": len(rows),
                        "columns": maximum_columns,
                    }
                )
            if table_specs:
                graph.metadata.setdefault("tables", []).extend(table_specs)
            # Paragraphs include document tables, headers, footers, footnotes,
            # endnotes, comments, textboxes and both sides of tracked revisions.
            paragraph_nodes: set[ET.Element] = set()
            for index, paragraph in enumerate(root.iter(_W + "p")):
                paragraph_nodes.update(paragraph.iter())
                pieces: list[str] = []
                for child in paragraph.iter():
                    # Text runs of every namespace: w:t, DrawingML a:t, Office Math m:t.
                    if child.tag in {_W + "delText", _W + "instrText"} or (
                        isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == "t"
                    ):
                        pieces.append(child.text or "")
                    elif child.tag == _W + "tab":
                        pieces.append("\t")
                    elif child.tag in {_W + "br", _W + "cr"}:
                        pieces.append("\n")
                if pieces:
                    table_location = table_locations.get(paragraph)
                    extra: dict[str, Any] = {}
                    if table_location is not None:
                        table_index, row_index, column_index = table_location
                        extra = {
                            "column": str(column_index),
                            "cell": f"table:{table_index}/row:{row_index}/column:{column_index}",
                        }
                    _fragment(
                        graph,
                        "".join(pieces),
                        part=name,
                        row=table_location[1] if table_location is not None else index,
                        kind="cell" if table_location is not None else "paragraph",
                        **extra,
                    )
            if any(True for _ in root.iter(_W + "altChunk")):
                _issue(graph, "alternate_content_not_extracted")
            for element in root.iter():
                # Text-bearing metadata needs scanning, but formatting values
                # (font names, style and relationship IDs) are not prose.
                for attribute, value in element.attrib.items():
                    local = attribute.rsplit("}", 1)[-1]
                    if value and (
                        local in {"author", "initials", "title", "descr", "name", "userId"}
                        or (element.tag == _W + "docVar" and local == "val")
                    ):
                        _fragment(graph, value, part=name, kind="metadata")
                if element not in paragraph_nodes and element.text and element.text.strip():
                    _fragment(graph, element.text, part=name, kind="metadata")
                if element.tail and element.tail.strip():
                    _fragment(graph, element.tail, part=name, kind="metadata")
            instructions = _field_instructions(root)
            for instruction in instructions:
                if instruction.strip():
                    _fragment(graph, instruction, part=name, kind="field_instruction")
            if any(not benign_field(instruction) for instruction in instructions):
                _issue(graph, "word_fields_require_review")


def _read_html(source: str, graph: DocumentGraph) -> None:
    from deidflow.markup import css_values, parse

    markup = parse(source)
    graph.issues.append("HTML_REVIEW_REQUIRED")
    _fragment(graph, markup.text(), part="body", kind="html_text")
    for _, _, name, value in markup.attributes:
        for item in css_values(value) if name == "style" else [value]:
            if item.strip():
                _fragment(graph, item, part="attribute", kind="attribute", metadata={"name": name})
    for _, _, value in markup.css:
        if value.strip():
            _fragment(graph, value, part="style", kind="css")
    for comment in markup.comments:
        _fragment(graph, comment, part="comment", kind="comment")
    for script in markup.scripts:
        _fragment(graph, script, part="script", kind="script")
    reasons = {reason for _, _, reason in markup.removable}
    if markup.scripts:
        _issue(graph, "html_scripts_require_review")
    if "embedded_data" in reasons:
        _issue(graph, "html_embedded_data_requires_review")
    if "iframe_srcdoc" in reasons:
        _issue(graph, "html_iframe_srcdoc_requires_review")
    if reasons & {"attribute", "css", "declaration"}:
        _issue(graph, "html_unsupported_channels_require_review")


def _read_eml(
    data: bytes,
    graph: DocumentGraph,
    max_bytes: int,
    ocr: OCREngine | None,
    performance: str,
) -> None:
    from deidflow.mail import (
        ATTACHMENT_SUFFIXES,
        KEPT_HEADERS,
        MAX_DEPTH,
        attachment_bytes,
        header_text,
        parse,
    )

    graph.issues.append("EMAIL_REVIEW_REQUIRED")
    counter = [0]
    extracted_bytes = [0]

    def charge(text: str) -> None:
        extracted_bytes[0] += len(text.encode("utf-8"))
        if extracted_bytes[0] > max_bytes:
            raise DocumentError("E-mail extracted text exceeds the byte limit")

    def emit(text: str, *, part: str, kind: str, metadata: dict[str, Any] | None = None) -> None:
        charge(text)
        _fragment(graph, text, part=part, kind=kind, metadata=metadata)

    def visit(part: Any, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise DocumentError("E-mail nesting limit exceeded")
        for name, value in part.raw_items():
            text = header_text(value)
            if name.lower() not in KEPT_HEADERS:
                emit(name, part="header", kind="email_header_name")
            if text.strip():
                emit(text, part="header", kind="email_header",
                          metadata={"name": name.lower()})  # fmt: skip
        for extra in (getattr(part, "preamble", None), getattr(part, "epilogue", None)):
            if isinstance(extra, str) and extra.strip():
                emit(extra, part="body", kind="email_body")
        filename = part.get_filename()
        # Content-ID is already emitted once with its exact header location.
        for value in (filename, part.get_param("name")):
            if isinstance(value, str) and value.strip():
                emit(header_text(value), part="attachment", kind="metadata")
        content_type = part.get_content_type()
        if part.is_multipart():
            for child in part.iter_parts():
                visit(child, depth + 1)
            return
        if content_type == "message/rfc822":
            for inner in part.get_payload() or []:
                visit(inner, depth + 1)
            return
        disposition = part.get_content_disposition()
        if content_type == "text/plain" and disposition != "attachment":
            emit(part.get_content(), part="body", kind="email_body")
            return
        if content_type == "text/html" and disposition != "attachment":
            text = part.get_content()
            charge(text)
            _read_html(text, graph)
            return
        if content_type.startswith(("image/", "audio/", "video/")):
            _issue(graph, "email_media_requires_review")
            return
        suffix = Path(filename or "").suffix.lower()
        if suffix not in ATTACHMENT_SUFFIXES:
            _issue(graph, "email_attachment_not_extracted")
            return
        raw = attachment_bytes(part)
        counter[0] += 1
        remaining_bytes = max_bytes - extracted_bytes[0]
        if len(raw) > remaining_bytes:
            raise DocumentError("E-mail attachments exceed the remaining byte limit")
        with tempfile.TemporaryDirectory(prefix="deidflow-read-") as folder:
            path = Path(folder) / ("adjunto" + suffix)
            path.write_bytes(raw)
            inner = read_document(path, max_bytes=remaining_bytes, ocr=ocr, performance=performance)
        for fragment in inner.fragments:
            emit(fragment.text, part=f"attachment:{counter[0]}", kind=fragment.kind)
        for issue in inner.issues:
            _issue(graph, issue)
        if not inner.complete:
            _issue(graph, "email_attachment_incomplete")

    visit(parse(data, max_bytes=max_bytes), 0)


def _read_xlsx(path: Path, graph: DocumentGraph, max_bytes: int) -> None:
    with _archive(path, max_bytes) as archive:
        names = archive.namelist()
        if "xl/workbook.xml" not in names:
            raise DocumentError("Missing XLSX workbook part")
        # The reader covers selected workbook data, not every Excel extension or
        # display-format semantic. XLSX output and standalone verification both
        # require human review even after a successful reread.
        graph.issues.append("XLSX_REVIEW_REQUIRED")
        for name in names:
            kind = xlsx_part_kind(name)
            if kind is None:
                _issue(graph, "unsupported_xlsx_package_part")
            elif kind in {"media", "removed"}:
                _issue(graph, "spreadsheet_auxiliary_content_requires_review")
            elif kind == "spreadsheet" and _xml(archive.read(name)).tag != xlsx_part_root(name):
                raise DocumentError("Unexpected XLSX document part root")
        _read_metadata(archive, graph)
        strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = _xml(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(x.itertext()) for x in root.findall(_S + "si")]
            # Deleted spreadsheet values can remain in unreferenced shared
            # strings. Scan the part itself as well as source-cell references.
            for string_index, shared_string in enumerate(strings):
                _fragment(
                    graph,
                    shared_string,
                    part="xl/sharedStrings.xml",
                    kind="shared_string",
                    metadata={"shared_string_index": string_index},
                )
        workbook = _xml(archive.read("xl/workbook.xml"))
        for definition in workbook.iter(_S + "definedName"):
            if definition.text:
                _fragment(graph, definition.text, part="xl/workbook.xml", kind="defined_name")
                if formula_carries_data(definition.text):
                    _issue(graph, "spreadsheet_defined_names_require_review")
        for element in workbook.iter():
            # Saved folder paths and shared-workbook user names.
            for attribute in ("url", "userName"):
                if element.attrib.get(attribute):
                    _fragment(
                        graph, element.attrib[attribute], part="xl/workbook.xml", kind="metadata"
                    )
        relations: dict[str, str] = {}
        relpath = "xl/_rels/workbook.xml.rels"
        if relpath in names:
            for rel in _xml(archive.read(relpath)):
                target = rel.attrib.get("Target", "")
                relations[rel.attrib.get("Id", "")] = (
                    target.lstrip("/") if target.startswith("/") else "xl/" + target
                )
        sheet_names: dict[str, tuple[str, str]] = {}
        rid = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        for sheet in workbook.iter(_S + "sheet"):
            sheet_name = sheet.attrib.get("name", "")
            _fragment(graph, sheet_name, part="xl/workbook.xml", kind="sheet_name")
            sheet_names[relations.get(sheet.attrib.get(rid, ""), "")] = (
                sheet_name,
                sheet.attrib.get("state", "visible"),
            )
        for name in names:
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                root = _xml(archive.read(name))
                _, state = sheet_names.get(name, (name, "unknown"))
                for cell in root.iter(_S + "c"):
                    reference = cell.attrib.get("r", "")
                    row_digits = "".join(
                        character for character in reference if character.isdigit()
                    )
                    row_number = int(row_digits) if row_digits else None
                    column_letters = "".join(
                        character for character in reference if character.isalpha()
                    )
                    value_type = cell.attrib.get("t", "n")
                    value = cell.find(_S + "v")
                    inline = cell.find(_S + "is")
                    text = value.text or "" if value is not None else ""
                    if value_type == "s" and text:
                        try:
                            string_index = int(text)
                            if string_index < 0:
                                raise ValueError
                            text = strings[string_index]
                        except (ValueError, IndexError):
                            raise DocumentError("Invalid XLSX shared string reference") from None
                    elif inline is not None:
                        text = "".join(inline.itertext())
                    if text:
                        _fragment(
                            graph,
                            text,
                            part=name,
                            cell=reference,
                            row=row_number,
                            column=column_letters,
                            kind="cell",
                            metadata={"value_type": value_type, "sheet_state": state},
                        )
                    formula = cell.find(_S + "f")
                    if formula is not None:
                        _fragment(
                            graph,
                            formula.text or "",
                            part=name,
                            cell=reference,
                            row=row_number,
                            column=column_letters,
                            kind="formula",
                        )
                        if formula_carries_data(formula.text or ""):
                            _issue(graph, "spreadsheet_formulas_require_review")
                for element in root.iter():
                    if (
                        element.tag.rsplit("}", 1)[-1]
                        in {
                            "oddHeader",
                            "evenHeader",
                            "firstHeader",
                            "oddFooter",
                            "evenFooter",
                            "firstFooter",
                        }
                        and element.text
                    ):
                        _fragment(
                            graph, header_footer_text(element.text), part=name, kind="header_footer"
                        )
                _criteria_fragments(root, graph, name)
            elif name.startswith("xl/") and "comment" in name.lower() and name.endswith(".xml"):
                root = _xml(archive.read(name))
                for author in root.iter(_S + "author"):
                    if author.text:
                        _fragment(graph, author.text, part=name, kind="metadata")
                for comment in root.iter(_S + "comment"):
                    text_element = comment.find(_S + "text")
                    if text_element is not None:
                        _fragment(
                            graph,
                            "".join(text_element.itertext()),
                            part=name,
                            cell=comment.attrib.get("ref"),
                            kind="comment",
                        )
                if "threaded" in name.lower():
                    for element in root.iter():
                        if element.text and element.text.strip():
                            _fragment(graph, element.text, part=name, kind="threaded_comment")
                    _issue(graph, "threaded_comments_require_review")
            elif (
                name.startswith("xl/")
                and any(
                    x in name
                    for x in ("drawings/", "charts/", "externalLinks/", "pivotCache", "connections")
                )
                and name.endswith(".xml")
            ):
                root = _xml(archive.read(name))
                for element in root.iter():
                    if element.text and element.text.strip():
                        _fragment(graph, element.text, part=name, kind="auxiliary_xml")
                _issue(graph, "spreadsheet_auxiliary_content_requires_review")
            elif (
                name.startswith("xl/")
                and any(
                    x in name
                    for x in ("tables/", "persons/", "metadata", "richData/", "queryTables/")
                )
                and name.endswith(".xml")
            ):
                review = "tables/" not in name  # table definitions are fully scanned below
                root = _xml(archive.read(name))
                for element in root.iter():
                    if element.text and element.text.strip():
                        _fragment(graph, element.text, part=name, kind="auxiliary_xml")
                    for attribute, attribute_value in element.attrib.items():
                        if attribute.rsplit("}", 1)[-1] in {
                            "name",
                            "displayName",
                            "caption",
                            "personId",
                            "userId",
                        }:
                            _fragment(graph, attribute_value, part=name, kind="metadata")
                _criteria_fragments(root, graph, name)
                if review:
                    _issue(graph, "spreadsheet_auxiliary_content_requires_review")


def _criteria_fragments(root: ET.Element, graph: DocumentGraph, part: str) -> None:
    """Filter values, custom sort lists, validation lists and conditional-format text."""
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""
        values: list[str] = []
        if local in {"filter", "customFilter"}:
            values.append(element.attrib.get("val", ""))
        elif local == "sortCondition":
            values.append(element.attrib.get("customList", ""))
        elif local in {"dataValidation", "cfRule"}:
            values.append("".join(element.itertext()))
            values.append(element.attrib.get("text", ""))
        for value in values:
            if value.strip():
                _fragment(graph, value, part=part, kind="criteria")


def _ocr_fragment(
    graph: DocumentGraph,
    result: OCRResult,
    *,
    page: int,
    point_size: tuple[float, float] | None = None,
    confidence_threshold: float = 50,
) -> None:
    if not result.tokens or result.width <= 0 or result.height <= 0:
        raise OCRError("OCR returned no usable token coverage")
    pieces: list[str] = []
    spans: list[dict[str, Any]] = []
    offset = 0
    previous_line: tuple[int, int, int] | None = None
    sx = point_size[0] / result.width if point_size else 1
    sy = point_size[1] / result.height if point_size else 1
    for token in result.tokens:
        if (
            not token.text
            or not token.text.strip()
            or not math.isfinite(token.confidence)
            or not -1 <= token.confidence <= 100
        ):
            raise OCRError("OCR returned invalid token metadata")
        if len(token.bbox) != 4 or not all(math.isfinite(c) for c in token.bbox):
            raise OCRError("OCR returned invalid token coordinates")
        x0, y0, x1, y1 = token.bbox
        if not 0 <= x0 < x1 <= result.width or not 0 <= y0 < y1 <= result.height:
            raise OCRError("OCR token coordinates exceed the raster")
        if pieces:
            separator = " " if token.line == previous_line else "\n"
            pieces.append(separator)
            offset += len(separator)
        start = offset
        pieces.append(token.text)
        offset += len(token.text)
        spans.append(
            {
                "start": start,
                "end": offset,
                "bbox": (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                "confidence": token.confidence,
            }
        )
        previous_line = token.line
        if token.confidence < confidence_threshold:
            _issue(graph, "low_ocr_confidence")
    _fragment(
        graph,
        "".join(pieces),
        page=page,
        bbox=(0, 0, result.width * sx, result.height * sy),
        kind="ocr",
        metadata={
            "tokens": spans,
            "ocr_engine": result.engine,
            "coordinate_system": "top_left",
            "raster_width": result.width,
            "raster_height": result.height,
        },
    )


def _read_image(path: Path, graph: DocumentGraph, ocr: OCREngine | None) -> None:
    if ocr is None:
        _issue(graph, "ocr_required_but_not_configured")
        return
    try:
        from PIL import Image
    except ImportError:
        raise OptionalDependencyError("Install deidflow[ocr] for image extraction") from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                frame_count = getattr(source, "n_frames", 1)
                if frame_count > MAX_PAGES:
                    raise DocumentError("Image frame limit exceeded")
                for index in range(frame_count):
                    source.seek(index)
                    if source.width * source.height > MAX_PIXELS:
                        raise DocumentError("Image pixel limit exceeded")
                    with source.convert("RGB") as image:
                        result = ocr.recognize(image)
                        if (result.width, result.height) != image.size:
                            raise OCRError("OCR result dimensions do not match the raster")
                        _ocr_fragment(
                            graph,
                            result,
                            page=index + 1,
                            confidence_threshold=getattr(ocr, "min_confidence", 50),
                        )
                if source.info:
                    # EXIF/XMP/PNG chunks are not interpreted as trustworthy text.
                    _issue(graph, "image_metadata_requires_review")
    except (DocumentError, OCRError):
        raise
    except Exception:
        raise DocumentError("Image decoding failed") from None


def _page_has_images(page: Any) -> bool:
    try:
        resources = page.get("/Resources", {})
        resources = resources.get_object() if hasattr(resources, "get_object") else resources
        objects = resources.get("/XObject", {})
        objects = objects.get_object() if hasattr(objects, "get_object") else objects
        return any(
            obj.get_object().get("/Subtype") in {"/Image", "/Form"} for obj in objects.values()
        )
    except Exception:
        # A resource tree we cannot inspect is not evidence of completeness.
        return True


def _read_pdf(path: Path, graph: DocumentGraph, ocr: OCREngine | None, performance: str) -> None:
    # PDFium's global native runtime is unsafe across concurrent threads, even
    # when documents differ. Share one reentrant lock with PDF reconstruction.
    from deidflow.pdf_runtime import PDFIUM_LOCK

    with PDFIUM_LOCK:
        _read_pdf_locked(path, graph, ocr, performance)


def _read_pdf_locked(
    path: Path, graph: DocumentGraph, ocr: OCREngine | None, performance: str
) -> None:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise OptionalDependencyError("Install deidflow[pdf] for PDF extraction") from None
    pdfium_document = None
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise DocumentError("Encrypted PDFs are unsupported")
        if len(reader.pages) > MAX_PAGES:
            raise DocumentError("PDF page limit exceeded")
        metadata = reader.metadata
        if metadata:
            for value in metadata.values():
                if isinstance(value, str) and value:
                    _fragment(graph, value, kind="metadata", part="pdf_info")
        pdf_root: Any = reader.trailer["/Root"]
        if any(
            key in pdf_root
            for key in ("/AcroForm", "/Names", "/OpenAction", "/AA", "/Outlines", "/OCProperties")
        ):
            _issue(graph, "pdf_forms_attachments_or_actions_require_review")
        if "/Metadata" in pdf_root:
            xmp = pdf_root["/Metadata"].get_object().get_data()
            if len(xmp) > DEFAULT_MAX_BYTES:
                raise DocumentError("PDF metadata expansion limit exceeded")
            xmp_root = _xml(xmp)
            for element in xmp_root.iter():
                if element.text and element.text.strip():
                    _fragment(graph, element.text, kind="metadata", part="pdf_xmp")
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            if text:
                _fragment(
                    graph,
                    text,
                    page=number,
                    bbox=(0, 0, width, height),
                    kind="pdf_text",
                    metadata={"coordinate_system": "page_container_not_glyphs"},
                )
            if page.get("/Annots"):
                annotations: Any = page["/Annots"]
                for reference in annotations:
                    annotation = reference.get_object()
                    for key in ("/Contents", "/T", "/Subj", "/RC"):
                        value = annotation.get(key)
                        if isinstance(value, str) and value:
                            _fragment(graph, value, page=number, kind="annotation")
                _issue(graph, "pdf_annotations_require_review")
            has_images = _page_has_images(page)
            sparse = len(text.strip()) < 20
            corrupted = bool(text) and text.count("\ufffd") / len(text) > 0.01
            needs_ocr = has_images or sparse or corrupted
            if not needs_ocr:
                continue
            if ocr is None:
                _issue(graph, "pdf_regions_require_ocr")
                continue
            try:
                import pypdfium2 as pdfium
            except ImportError:
                raise OptionalDependencyError(
                    "Install deidflow[ocr] for PDF OCR rendering"
                ) from None
            if pdfium_document is None:
                pdfium_document = pdfium.PdfDocument(path)
            pdfium_page = pdfium_document[number - 1]
            scale = 2 if performance in {"high_throughput", "fast"} else 3
            if width * height * scale * scale > MAX_PIXELS:
                pdfium_page.close()
                raise DocumentError("PDF raster pixel limit exceeded")
            bitmap = pdfium_page.render(scale=scale)
            try:
                with bitmap.to_pil() as image:
                    result = ocr.recognize(image)
                    if (result.width, result.height) != image.size:
                        raise OCRError("OCR result dimensions do not match the raster")
                    _ocr_fragment(
                        graph,
                        result,
                        page=number,
                        point_size=(width, height),
                        confidence_threshold=getattr(ocr, "min_confidence", 50),
                    )
            finally:
                bitmap.close()
                pdfium_page.close()
        graph.metadata["page_count"] = len(reader.pages)
    except (DocumentError, OCRError):
        raise
    except Exception:
        raise DocumentError("PDF extraction failed") from None
    finally:
        if pdfium_document is not None:
            pdfium_document.close()


def _json_fragments(value: Any, graph: DocumentGraph, path: str = "$") -> None:
    if isinstance(value, dict):
        for index, (key, child) in enumerate(value.items()):
            key_path = f"{path}/key:{index}"
            _fragment(graph, key, kind="json_key", json_path=key_path)
            # Locations use ordinal keys so locations themselves cannot disclose
            # customer-supplied JSON keys in logs or finding representations.
            _json_fragments(child, graph, f"{path}/value:{index}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _json_fragments(child, graph, f"{path}/{index}")
    elif isinstance(value, str):
        _fragment(graph, value, json_path=path, kind="json_value")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _fragment(graph, str(value), json_path=path, kind="json_number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError("Duplicate JSON object keys are unsupported")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> None:
    raise DocumentError("Non-finite JSON numbers are unsupported")


def iter_parquet_batches(
    path: str | Path,
    *,
    batch_size: int = 1024,
    columns: list[str] | None = None,
) -> Iterator[Any]:
    """Yield local Arrow RecordBatches without loading the whole Parquet table.

    Column selection is explicit and affects coverage; callers must scan all
    columns for a full privacy assessment. Arrow's parser allocation is not an
    OS-level memory budget. No remote filesystem or URI is accepted.
    """
    if batch_size < 1 or batch_size > 1_000_000:
        raise ValueError("Invalid Parquet batch size")
    source = Path(path)
    if not source.is_file():
        raise DocumentError("Parquet input cannot be accessed")
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise OptionalDependencyError("Install deidflow[tables] for Parquet extraction") from None
    try:
        with pq.ParquetFile(source, memory_map=False, pre_buffer=False) as parquet:
            yield from parquet.iter_batches(
                batch_size=batch_size, columns=columns, use_threads=False
            )
    except Exception:
        raise DocumentError("Parquet extraction failed") from None


def _read_parquet(path: Path, graph: DocumentGraph, max_bytes: int) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise OptionalDependencyError("Install deidflow[tables] for Parquet extraction") from None

    text_bytes = 0
    row_offset = 0
    with pq.ParquetFile(path, memory_map=False, pre_buffer=False) as parquet:
        schema = parquet.schema_arrow
    names = schema.names
    if len(set(names)) != len(names):
        raise DocumentError("Duplicate Parquet field names are unsupported")
    for index, field in enumerate(schema):
        _fragment(graph, field.name, column=str(index), kind="header")
        if pa.types.is_nested(field.type) or pa.types.is_union(field.type):
            _issue(graph, "nested_parquet_fields_require_review")
    if schema.metadata:
        _issue(graph, "parquet_schema_metadata_requires_review")
        for key, value in schema.metadata.items():
            for content in (key, value):
                try:
                    decoded = content.decode("utf-8")
                except UnicodeDecodeError:
                    _issue(graph, "binary_parquet_metadata_not_extracted")
                else:
                    _fragment(graph, decoded, kind="metadata")
    for batch in iter_parquet_batches(path):
        columns = batch.to_pydict()
        for column, name in enumerate(names):
            for offset, value in enumerate(columns[name]):
                if value is None:
                    continue
                if isinstance(value, bytes):
                    try:
                        text = value.decode("utf-8")
                    except UnicodeDecodeError:
                        _issue(graph, "binary_parquet_field_not_extracted")
                        continue
                else:
                    text = str(value)
                text_bytes += len(text.encode("utf-8"))
                if text_bytes > max_bytes or len(graph.fragments) >= 100_000:
                    raise DocumentError(
                        "Parquet document graph limit exceeded; use iter_parquet_batches"
                    )
                _fragment(graph, text, row=row_offset + offset, column=str(column), kind="cell")
        row_offset += batch.num_rows
    graph.metadata["row_count"] = row_offset


def read_document(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    ocr: OCREngine | None = None,
    performance: str = "balanced",
) -> DocumentGraph:
    """Extract a local file without network use or implicit OCR fallback.

    Findings are local to fragment text. ``complete=False`` is a release-gating
    condition, never a successful no-findings scan. CSV/JSONL here are bounded
    document readers; use the structured streaming API for larger datasets.
    """
    source = Path(path)
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    try:
        if not source.is_file() or source.stat().st_size > max_bytes:
            raise DocumentError("Input is missing or exceeds the byte limit")
    except OSError:
        raise DocumentError("Input cannot be accessed") from None
    suffix = source.suffix.lower()
    graph = DocumentGraph(
        document_id=uuid.uuid4().hex,
        source_format=suffix.lstrip("."),
        fragments=[],
        metadata={},
        issues=[],
        complete=True,
    )
    try:
        if suffix in {".txt", ".text", ".md", ".log"}:
            _fragment(graph, source.read_bytes().decode("utf-8"), part="body")
        elif suffix in {".json", ".jsonl", ".ndjson"}:
            content = source.read_bytes().decode("utf-8")
            if suffix == ".json":
                _json_fragments(
                    json.loads(
                        content,
                        object_pairs_hook=_unique_object,
                        parse_constant=_invalid_json_constant,
                    ),
                    graph,
                )
            else:
                for index, line in enumerate(io.StringIO(content)):
                    if line.strip():
                        _json_fragments(
                            json.loads(
                                line,
                                object_pairs_hook=_unique_object,
                                parse_constant=_invalid_json_constant,
                            ),
                            graph,
                            f"$/line:{index}",
                        )
        elif suffix in {".csv", ".tsv"}:
            with source.open(encoding="utf-8", newline="") as stream:
                expected_width: int | None = None
                for row, values in enumerate(
                    csv.reader(stream, delimiter="\t" if suffix == ".tsv" else ",")
                ):
                    if expected_width is None:
                        expected_width = len(values)
                    elif len(values) != expected_width:
                        raise DocumentError("Inconsistent delimited document row width")
                    for column, value in enumerate(values):
                        _fragment(
                            graph,
                            value,
                            row=row,
                            column=str(column),
                            kind="header" if row == 0 else "cell",
                        )
        elif suffix in {".html", ".htm"}:
            _read_html(source.read_bytes().decode("utf-8"), graph)
        elif suffix == ".eml":
            _read_eml(source.read_bytes(), graph, max_bytes, ocr, performance)
        elif suffix == ".docx":
            _read_docx(source, graph, max_bytes)
        elif suffix == ".xlsx":
            _read_xlsx(source, graph, max_bytes)
        elif suffix == ".pdf":
            _read_pdf(source, graph, ocr, performance)
        elif suffix == ".parquet":
            _read_parquet(source, graph, max_bytes)
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            _read_image(source, graph, ocr)
        else:
            raise UnsupportedFormat("Unsupported document format")
    except (DocumentError, OCRError):
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error, RecursionError):
        raise DocumentError("Malformed or unsupported document encoding") from None
    except Exception:
        raise DocumentError("Document extraction failed") from None
    return graph


__all__ = [
    "DocumentError",
    "OptionalDependencyError",
    "UnsupportedFormat",
    "iter_parquet_batches",
    "read_document",
]
