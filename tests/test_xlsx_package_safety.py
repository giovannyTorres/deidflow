from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from test_office_xlsx import (
    CONTENT_TYPES,
    MAIN,
    PKG,
    RELS,
    STYLES,
    WORKBOOK_RELS,
    make_xlsx,
)

from deidflow import DeidEngine, Finding, Policy
from deidflow.nlp import SpanTagger

CANARY = b"synthetic.leak@example.test"


@pytest.fixture(scope="module")
def engine() -> DeidEngine:
    return DeidEngine(nlp=SpanTagger.builtin("es-clinical"))


def _update(path: Path, changes: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts.update(changes)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def _clean_xlsx(path: Path) -> Path:
    """A complete small workbook with no sensitive values or hidden features."""
    types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    parts = {
        "[Content_Types].xml": types,
        "_rels/.rels": (
            f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" '
            f'Type="{RELS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            f'<workbook xmlns="{MAIN}" xmlns:r="{RELS}"><sheets>'
            '<sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" '
            f'Type="{RELS}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{RELS}/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{MAIN}"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Total</t></is></c></row>'
            '<row r="2"><c r="A2"><v>100</v></c></row></sheetData></worksheet>'
        ),
        "xl/styles.xml": STYLES,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


@pytest.mark.parametrize(
    "score,context,issue",
    [
        (0.5, (), "UNCERTAIN_SOURCE_FINDINGS"),
        (0.75, ("window_boundary",), "UNRESOLVED_MODEL_WINDOW_BOUNDARY"),
    ],
)
def test_xlsx_source_uncertainty_survives_cell_transformation(tmp_path, score, context, issue):
    class PartialName:
        def detect_batch(self, texts):
            return [
                [
                    Finding(
                        "PERSON",
                        text.index("Ana "),
                        text.index("Ana ") + 3,
                        score,
                        "test.partial",
                        context=context,
                    )
                ]
                if "Ana " in text
                else []
                for text in texts
            ]

    source = _clean_xlsx(tmp_path / "source.xlsx")
    _update(
        source,
        {
            "xl/worksheets/sheet1.xml": (
                f'<worksheet xmlns="{MAIN}"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>notes</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Ana López</t></is></c></row>'
                "</sheetData></worksheet>"
            )
        },
    )
    result = DeidEngine(nlp=PartialName()).deidentify(source, output=tmp_path / "out.xlsx")
    assert result.status == "REVIEW_REQUIRED" and issue in result.issues
    assert "XLSX_REVIEW_REQUIRED" in result.issues
    assert result.output_path is not None
    with zipfile.ZipFile(result.output_path) as archive:
        assert b"[PERSON] L\xc3\xb3pez" in archive.read("xl/worksheets/sheet1.xml")


def test_xlsx_sparse_grid_memory_guard():
    from deidflow.readers import DocumentError

    engine = DeidEngine(memory_budget_mb=16)
    grid = {(i, i): "x" for i in range(1, 1000)}
    with pytest.raises(DocumentError, match="memory budget"):
        engine._sheet_cells(grid, Policy.strict(), "test", None, [], [])


def test_sheet_unknown_identifier_evidence_survives():
    engine = DeidEngine()
    issues: list[str] = []
    engine._sheet_cells(
        {(1, 1): "custom", (2, 1): "AB12XY", (3, 1): "CD34ZW", (4, 1): "EF56UV"},
        Policy.strict(require_ner=False),
        "test",
        None,
        [],
        issues,
    )
    assert "UNKNOWN_IDENTIFIER_CANDIDATE" in issues


@pytest.mark.parametrize("related", [False, True])
@pytest.mark.parametrize(
    "part",
    ["extra/data.xml", "extra/data.bin", "xl/private.xml", "xl/private.bin"],
)
def test_unknown_xlsx_parts_block_without_output(tmp_path, engine, part, related):
    source = make_xlsx(tmp_path / "source.xlsx")
    changes: dict[str, bytes | str] = {part: b"<private>" + CANARY + b"</private>"}
    if related:
        changes["[Content_Types].xml"] = CONTENT_TYPES.replace(
            "</Types>",
            f'<Override PartName="/{part}" ContentType="application/xml"/></Types>',
        )
        changes["xl/_rels/workbook.xml.rels"] = WORKBOOK_RELS.replace(
            "</Relationships>",
            f'<Relationship Id="rId99" Type="{RELS}/customXml" Target="/{part}"/></Relationships>',
        )
    _update(source, changes)
    original = source.read_bytes()
    output = tmp_path / "candidate.xlsx"
    result = engine.deidentify(source, output=output, policy=Policy.strict())
    assert result.status == "BLOCKED"
    assert not result.release_approved and result.output_path is None
    assert not output.exists() and not list(tmp_path.glob(".deidflow-*"))
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "part",
    [
        "xl/charts/payload.bin",
        "xl/CHARTS/payload.bin",
        "xl/drawings/vmlDrawing1.vml",
        "xl/media/payload.bin",
    ],
)
def test_retained_opaque_xlsx_media_blocks(tmp_path, engine, part):
    source = make_xlsx(tmp_path / "source.xlsx")
    _update(source, {part: b"<xml><private>" + CANARY + b"</private></xml>"})
    output = tmp_path / "candidate.xlsx"
    result = engine.deidentify(source, output=output, policy=Policy.strict(), office_media="keep")
    assert result.status == "BLOCKED"
    assert not result.release_approved and not output.exists()


@pytest.mark.parametrize(
    "part",
    ["xl/charts/payload.bin", "xl/CHARTS/payload.bin", "xl/drawings/vmlDrawing1.vml"],
)
def test_default_xlsx_media_removal_discards_hidden_bytes(tmp_path, engine, part):
    source = make_xlsx(tmp_path / "source.xlsx")
    _update(source, {part: b"<xml><private>" + CANARY + b"</private></xml>"})
    result = engine.deidentify(source, output=tmp_path / "candidate.xlsx", policy=Policy.strict())
    assert result.status == "REVIEW_REQUIRED"
    assert not result.release_approved and result.output_path is not None
    with zipfile.ZipFile(result.output_path) as archive:
        assert part not in archive.namelist()
        assert all(CANARY not in archive.read(name) for name in archive.namelist())
        assert b"legacyDrawing" not in archive.read("xl/worksheets/sheet1.xml")


def test_clean_xlsx_always_requires_human_review_and_preserves_styles(tmp_path, engine):
    source = _clean_xlsx(tmp_path / "clean.xlsx")
    output = tmp_path / "candidate.xlsx"
    result = engine.deidentify(source, output=output, policy=Policy.strict())
    assert result.status == "REVIEW_REQUIRED"
    assert not result.release_approved and result.output_path == output
    verified = engine.verify(output, policy=Policy.strict())
    assert verified.status == "REVIEW_REQUIRED" and not verified.release_approved
    with zipfile.ZipFile(output) as archive:
        styles = archive.read("xl/styles.xml")
        sheet = archive.read("xl/worksheets/sheet1.xml")
        assert b'val="Calibri"' in styles and b'val="11"' in styles
        assert b"<v>100</v>" in sheet and b"<t>Total</t>" in sheet
