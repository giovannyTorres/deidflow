from __future__ import annotations

import csv
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy
from deidflow.readers import formula_carries_data, read_document

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/comments1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"/>
<Override PartName="/xl/tables/table1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>
<Override PartName="/xl/calcChain.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml"/>
<Override PartName="/xl/externalLinks/externalLink1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""
PACKAGE_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG}">
<Relationship Id="rId1" Type="{RELS}/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""
WORKBOOK = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{MAIN}" xmlns:r="{RELS}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:x15ac="http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac" mc:Ignorable="x15ac">
<fileSharing userName="Juan Pérez"/>
<mc:AlternateContent><mc:Choice Requires="x15ac"><x15ac:absPath url="C:\\Users\\juan.perez\\Documents\\"/></mc:Choice></mc:AlternateContent>
<sheets><sheet name="Pacientes" sheetId="1" r:id="rId1"/><sheet name="Exp. 11111112L" sheetId="2" r:id="rId2"/></sheets>
<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">Pacientes!$A$1:$E$3</definedName><definedName name="Responsable">"Dra. Lucía Fernández"</definedName></definedNames>
<externalReferences><externalReference r:id="rId6"/></externalReferences>
</workbook>"""
WORKBOOK_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG}">
<Relationship Id="rId1" Type="{RELS}/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="{RELS}/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="{RELS}/sharedStrings" Target="sharedStrings.xml"/>
<Relationship Id="rId4" Type="{RELS}/styles" Target="styles.xml"/>
<Relationship Id="rId5" Type="{RELS}/calcChain" Target="calcChain.xml"/>
<Relationship Id="rId6" Type="{RELS}/externalLink" Target="externalLinks/externalLink1.xml"/>
</Relationships>"""
STRINGS = [
    "Nombre",  # 0
    "DNI",  # 1
    "Teléfono",  # 2
    "Total",  # 3
    "Nota",  # 4
    "María López García",  # 5
    "12345678Z",  # 6
    "Pedro Ruiz Soto",  # 7
    "87654321X",  # 8
    "Avisar al correo maria.lopez@example.com",  # 9
    "Antiguo paciente Rodrigo Díaz Vela, DNI 11111112L",  # 10: orphan (deleted cell)
]
SHARED = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst xmlns="{MAIN}" count="11" uniqueCount="11">'
    + "".join(f"<si><t>{text}</t></si>" for text in STRINGS)
    + "</sst>"
)


def _s(ref: str, index: int) -> str:
    return f'<c r="{ref}" t="s"><v>{index}</v></c>'


SHEET1 = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{MAIN}" xmlns:r="{RELS}"><sheetData>
<row r="1">{_s("A1", 0)}{_s("B1", 1)}{_s("C1", 2)}{_s("D1", 3)}{_s("E1", 4)}</row>
<row r="2">{_s("A2", 5)}{_s("B2", 6)}<c r="C2"><v>612345678</v></c><c r="D2"><v>120</v></c>{_s("E2", 9)}</row>
<row r="3">{_s("A3", 7)}{_s("B3", 8)}<c r="C3"><v>698765432</v></c><c r="D3"><v>80</v></c><c r="E3" t="str"><f>"Sr. "&amp;A3</f><v>Sr. Pedro Ruiz Soto</v></c></row>
<row r="4"><c r="D4"><f>SUM(D2:D3)</f><v>200</v></c><c r="E4"><f>'Exp. 11111112L'!A1+1</f><v>401</v></c></row>
</sheetData>
<headerFooter><oddHeader>&amp;LPaciente: María López García</oddHeader></headerFooter>
<legacyDrawing r:id="rId1"/><tableParts count="1"><tablePart r:id="rId2"/></tableParts>
</worksheet>"""
SHEET1_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG}">
<Relationship Id="rId1" Type="{RELS}/vmlDrawing" Target="../drawings/vmlDrawing1.vml"/>
<Relationship Id="rId2" Type="{RELS}/table" Target="../tables/table1.xml"/>
<Relationship Id="rId3" Type="{RELS}/comments" Target="../comments1.xml"/>
</Relationships>"""
SHEET2 = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{MAIN}"><sheetData>
<row r="1"><c r="A1"><f>Pacientes!D4*2</f><v>400</v></c><c r="B1"><f>[1]Hoja1!A1</f><v>7</v></c></row>
</sheetData></worksheet>"""
COMMENTS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<comments xmlns="{MAIN}"><authors><author>Dr. Ramón Ortega</author></authors><commentList>
<comment ref="A2" authorId="0"><text><r><t>Paciente: </t></r><r><rPr><b/></rPr><t>María López</t></r><r><t>, tel. 612 34 56 78</t></r></text></comment>
</commentList></comments>"""
TABLE = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<table xmlns="{MAIN}" id="1" name="Tabla1" displayName="Tabla1" ref="A1:E3"><autoFilter ref="A1:E3"/>
<tableColumns count="5"><tableColumn id="1" name="Nombre"/><tableColumn id="2" name="DNI"/><tableColumn id="3" name="Teléfono"/><tableColumn id="4" name="Total"/><tableColumn id="5" name="Nota"/></tableColumns></table>"""
CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Ramón Ortega</dc:creator></cp:coreProperties>"""
STYLES = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{MAIN}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="1"><xf/></cellXfs></styleSheet>'


def make_xlsx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("[Content_Types].xml", CONTENT_TYPES)
        out.writestr("_rels/.rels", PACKAGE_RELS)
        out.writestr("xl/workbook.xml", WORKBOOK)
        out.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        out.writestr("xl/sharedStrings.xml", SHARED)
        out.writestr("xl/styles.xml", STYLES)
        out.writestr("xl/worksheets/sheet1.xml", SHEET1)
        out.writestr("xl/worksheets/_rels/sheet1.xml.rels", SHEET1_RELS)
        out.writestr("xl/worksheets/sheet2.xml", SHEET2)
        out.writestr("xl/comments1.xml", COMMENTS)
        out.writestr("xl/drawings/vmlDrawing1.vml", "<xml/>")
        out.writestr("xl/tables/table1.xml", TABLE)
        out.writestr("xl/calcChain.xml", f'<calcChain xmlns="{MAIN}"><c r="D4" i="1"/></calcChain>')
        out.writestr(
            "xl/externalLinks/externalLink1.xml",
            f'<externalLink xmlns="{MAIN}"><externalBook><sheetNames><sheetName val="Nóminas Pedro Ruiz"/></sheetNames></externalBook></externalLink>',
        )
        out.writestr("docProps/core.xml", CORE)
    return path


def _package(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {n: archive.read(n).decode("utf-8", "replace") for n in archive.namelist()}


def test_formula_classification():
    assert not formula_carries_data("SUM(B2:B9)")
    assert not formula_carries_data("SUM(Tabla1[Importe])")
    assert formula_carries_data('"Sr. "&A3')
    assert formula_carries_data("[1]Hoja1!A1")
    assert formula_carries_data("'C:\\datos\\[nominas.xlsx]Hoja1'!A1")


def test_xlsx_output_transforms_cells_and_removes_hidden_content(tmp_path):
    source = make_xlsx(tmp_path / "pacientes.xlsx")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.xlsx", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    parts = _package(result.output_path)
    text = "\n".join(parts.values())
    for secret in (
        "María",
        "López",
        "Pedro Ruiz",
        "12345678Z",
        "87654321X",
        "612345678",
        "698765432",
        "612 34 56 78",
        "maria.lopez@example.com",
        "Rodrigo",  # orphaned shared string
        "11111112L",
        "Juan Pérez",  # shared-workbook user
        "juan.perez",  # saved folder path
        "Ramón",
        "Lucía",
        "Nóminas",
    ):
        assert secret not in text, secret
    assert "xl/calcChain.xml" not in parts and "xl/externalLinks/externalLink1.xml" not in parts
    workbook = parts["xl/workbook.xml"]
    assert 'name="Hoja2"' in workbook and "_xlnm.Print_Area" in workbook
    assert "Responsable" not in workbook and "externalReference" not in workbook
    sheet1, sheet2 = parts["xl/worksheets/sheet1.xml"], parts["xl/worksheets/sheet2.xml"]
    assert "<f>SUM(D2:D3)</f>" in sheet1  # cell arithmetic survives
    assert "<f>'Hoja2'!A1+1</f>" in sheet1  # references follow the renamed sheet
    # A formula with a string literal is replaced by its (transformed) cached value.
    assert "&quot;Sr. &quot;" not in sheet1 and "Sr. [PERSON]" in sheet1
    assert "<f>Pacientes!D4*2</f>" in sheet2 and "[1]" not in sheet2
    assert "<legacyDrawing" not in sheet1  # Uninspected VML shapes are removed.
    assert "xl/drawings/vmlDrawing1.vml" not in parts
    table = parts["xl/tables/table1.xml"]
    assert 'name="Nombre"' in table and 'name="DNI"' in table
    assert "DeidFlow" in parts["xl/comments1.xml"]
    graph = read_document(result.output_path)
    assert graph.complete, graph.issues
    assert result.audit["office_removed"]["shared_strings_dropped"] >= 1
    assert result.status == "REVIEW_REQUIRED" and not result.release_approved


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_xlsx_output_opens_in_libreoffice(tmp_path):
    source = make_xlsx(tmp_path / "pacientes.xlsx")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.xlsx", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None
    converted = subprocess.run(
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation=file://{tmp_path}/lo",
            "--convert-to",
            "csv",
            "--outdir",
            str(tmp_path / "csv"),
            str(result.output_path),
        ],
        capture_output=True,
        timeout=120,
    )
    assert converted.returncode == 0
    rows = list(csv.reader((tmp_path / "csv" / "out.csv").open(encoding="utf-8")))
    assert rows[0] == ["Nombre", "DNI", "Teléfono", "Total", "Nota"]
    assert rows[1][0] == "[PERSON]" and rows[1][3] == "120" and rows[3][3] == "200"


def _with_sheet(path: Path, sheet: str, table: str | None = None) -> Path:
    source = make_xlsx(path.with_name("base.xlsx"))
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(path, "w") as out:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                data = sheet.encode()
            elif table is not None and info.filename == "xl/tables/table1.xml":
                data = table.encode()
            out.writestr(info.filename, data)
    return path


def test_filter_validation_and_conditional_criteria_do_not_keep_values(tmp_path):
    criteria = (
        '<autoFilter ref="A1:E3"><filterColumn colId="3"><filters>'
        '<filter val="maria.lopez@example.com"/></filters></filterColumn>'
        '<sortState ref="A2:E3"><sortCondition ref="A2:A3" customList="Pedro Ruiz Soto,Ana"/>'
        "</sortState></autoFilter>"
    )
    rules = (
        '<conditionalFormatting sqref="A2:A3"><cfRule type="containsText" priority="1" '
        'operator="containsText" text="12345678Z"><formula>NOT(ISERROR(SEARCH("12345678Z",A2)))'
        "</formula></cfRule></conditionalFormatting>"
        '<dataValidations count="1"><dataValidation type="list" sqref="A2:A3">'
        '<formula1>"Pedro Ruiz Soto,87654321X"</formula1></dataValidation></dataValidations>'
    )
    sheet = SHEET1.replace("</sheetData>\n", "</sheetData>\n" + criteria + rules)
    table = TABLE.replace(
        '<autoFilter ref="A1:E3"/>',
        '<autoFilter ref="A1:E3"><filterColumn colId="1"><filters><filter val="87654321X"/>'
        "</filters></filterColumn></autoFilter>",
    )
    source = _with_sheet(tmp_path / "criteria.xlsx", sheet, table)
    graph = read_document(source)
    scanned = {f.text for f in graph.fragments if f.kind == "criteria"}
    assert "maria.lopez@example.com" in scanned and "87654321X" in scanned
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.xlsx", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    text = "\n".join(_package(result.output_path).values())
    for secret in ("maria.lopez@example.com", "12345678Z", "87654321X", "Pedro Ruiz"):
        assert secret not in text, secret
    sheet1 = _package(result.output_path)["xl/worksheets/sheet1.xml"]
    assert '<autoFilter ref="A1:E3">' in sheet1 and "dataValidations" not in sheet1


def test_changed_shared_formula_master_takes_its_dependents_along(tmp_path):
    sheet = SHEET1.replace(
        "</sheetData>",
        '<row r="6"><c r="G6" t="str"><f t="shared" ref="G6:G7" si="0">IF(D2&gt;100,E2,D2)</f>'
        "<v>Avisar al correo maria.lopez@example.com</v></c></row>"
        '<row r="7"><c r="G7"><f t="shared" si="0"/><v>80</v></c></row></sheetData>',
    )
    source = _with_sheet(tmp_path / "shared.xlsx", sheet)
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.xlsx", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    sheet1 = _package(result.output_path)["xl/worksheets/sheet1.xml"]
    assert "maria.lopez@example.com" not in sheet1
    assert 'si="0"' not in sheet1  # no orphaned shared-formula dependent
    assert '<c r="G7"><v>80</v></c>' in sheet1
