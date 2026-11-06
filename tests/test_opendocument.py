from __future__ import annotations

import base64
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import pytest

from deidflow import DeidEngine, Policy
from deidflow.readers import DocumentError, read_document

NAMESPACES = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "dc": "http://purl.org/dc/elements/1.1/",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "form": "urn:oasis:names:tc:opendocument:xmlns:form:1.0",
    "script": "urn:oasis:names:tc:opendocument:xmlns:script:1.0",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
    "of": "urn:oasis:names:tc:opendocument:xmlns:of:1.2",
    "number": "urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0",
    "loext": "urn:org:documentfoundation:names:experimental:office:xmlns:loext:1.0",
    "calcext": "urn:org:documentfoundation:names:experimental:calc:xmlns:calcext:1.0",
}
NS = " ".join(f'xmlns:{prefix}="{uri}"' for prefix, uri in NAMESPACES.items())
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)

ODT_CONTENT = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {NS} office:version="1.3">
<office:scripts><office:event-listeners><script:event-listener script:language="ooo:script" script:event-name="dom:load" xlink:href="vnd.sun.star.script:Standard.Module1.Avisar?language=Basic&amp;location=document"/></office:event-listeners></office:scripts>
<office:automatic-styles><style:style style:name="T1" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style></office:automatic-styles>
<office:body><office:text>
<office:forms><form:form form:name="Formulario"><form:text form:name="paciente" form:id="control1" form:current-value="Juan Nadie Gómez" form:value="Juan Nadie Gómez"/></form:form></office:forms>
<text:tracked-changes><text:changed-region text:id="ct1"><text:deletion><office:change-info><dc:creator>Dr. Ramón Ortega</dc:creator><dc:date>2024-03-01T10:00:00</dc:date></office:change-info><text:p>Antes vivía en Calle Mayor 5.</text:p></text:deletion></text:changed-region></text:tracked-changes>
<text:user-field-decls><text:user-field-decl office:value-type="string" office:string-value="ana.torres@example.com" text:name="correo"/></text:user-field-decls>
<text:p text:style-name="Standard"><text:span text:style-name="T1">Paciente:</text:span> María<text:s/><text:span text:style-name="T1">López</text:span> García, DNI 1234<text:span>5678Z</text:span>.</text:p>
<text:p>Paciente: <text:sender-firstname>Carmen</text:sender-firstname> <text:sender-lastname>Ruiz Bravo</text:sender-lastname>. Archivo <text:file-name text:display="full">/home/carmen/informes/12345678Z.odt</text:file-name></text:p>
<text:p>Contacto: <text:a xlink:type="simple" xlink:href="mailto:maria.lopez@example.com" office:title="Correo de maria.lopez@example.com">escribir</text:a> <text:change text:change-id="ct1"/>Tratamiento revisado.<office:annotation office:name="c1"><dc:creator>Dr. Ramón Ortega</dc:creator><dc:date>2024-03-01T10:00:00</dc:date><meta:creator-initials>RO</meta:creator-initials><text:p>Llamar al 612 345 678.</text:p></office:annotation> Control en 3 meses.<office:annotation-end office:name="c1"/></text:p>
<text:p>Oculto: <text:hidden-text text:condition="ooow:1" text:string-value="DNI 87654321X" text:is-hidden="true">DNI 87654321X</text:hidden-text>, <text:conditional-text text:condition="ooow:1" text:string-value-if-true="Paciente: Pedro Ruiz Soto" text:string-value-if-false="-" text:current-value="true">Paciente: Pedro Ruiz Soto</text:conditional-text>. Correo: <text:user-field-get text:name="correo">ana.torres@example.com</text:user-field-get></text:p>
<text:p>Nota<text:note text:id="n1" text:note-class="footnote"><text:note-citation>1</text:note-citation><text:note-body><text:p>Correo alternativo pedro.ruiz@example.org</text:p></text:note-body></text:note>: <text:bookmark text:name="ficha 11111111H"/>ver <text:a xlink:type="simple" xlink:href="#ficha 11111111H">ficha</text:a>; índice<text:alphabetical-index-mark text:string-value="rodrigo.diaz@example.com"/>.</text:p>
<text:section text:name="Privado" text:protected="true" text:protection-key="aGFzaA==" text:protection-key-digest-algorithm="http://www.w3.org/2000/09/xmldsig#sha256"><text:p>Sección protegida.</text:p></text:section>
<table:table table:name="Datos"><table:table-column table:number-columns-repeated="2"/><table:table-row><table:table-cell office:value-type="string"><text:p>Teléfono</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="699112233"><text:p>699 112 233</text:p></table:table-cell></table:table-row></table:table>
<text:p><draw:frame draw:name="Foto" text:anchor-type="as-char" svg:width="1cm" svg:height="1cm"><draw:image xlink:href="Pictures/foto.png" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/><svg:title>Foto de Lucía Fernández</svg:title></draw:frame></text:p>
<text:p><draw:frame draw:name="Marco" text:anchor-type="paragraph" svg:width="4cm" svg:height="2cm"><draw:text-box><text:p>Cuadro con DNI 11111111H y correo elena.martin@example.com</text:p></draw:text-box></draw:frame></text:p>
</office:text></office:body></office:document-content>"""
ODT_STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {NS} office:version="1.3"><office:font-face-decls><style:font-face style:name="Times New Roman" svg:font-family="'Times New Roman'"/></office:font-face-decls><office:styles><style:style style:name="Standard" style:family="paragraph"/></office:styles><office:automatic-styles><style:page-layout style:name="pm1"/></office:automatic-styles><office:master-styles><style:master-page style:name="Standard" style:page-layout-name="pm1"><style:header><text:p>Consulta, tel. 915 123 456</text:p></style:header><style:footer><text:p>Página <text:page-number text:select-page="current">1</text:page-number></text:p></style:footer></style:master-page></office:master-styles></office:document-styles>"""
ODT_META = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta {NS} office:version="1.3"><office:meta><meta:initial-creator>Carmen Ruiz Bravo</meta:initial-creator><dc:creator>Carmen Ruiz Bravo</dc:creator><meta:creation-date>2024-03-01T10:00:00</meta:creation-date><dc:date>2024-03-02T11:00:00</dc:date><meta:printed-by>Carmen Ruiz Bravo</meta:printed-by><meta:editing-duration>PT1H</meta:editing-duration><meta:template xlink:type="simple" xlink:href="file:///home/carmen/Plantillas/informe.ott" xlink:title="Plantilla"/><dc:title>Informe de alta</dc:title><meta:user-defined meta:name="Correo paciente">maria.lopez@example.com</meta:user-defined><meta:user-defined meta:name="Company">Clínica San Rafael</meta:user-defined><meta:generator>LibreOffice/24.2.7.2$Linux_X86_64</meta:generator></office:meta></office:document-meta>"""
PRINTER = base64.b64encode(b"\x00\x01printer=Impresora de carmen.ruiz@example.com\x00\x02").decode()
ODT_SETTINGS = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-settings {NS} office:version="1.3"><office:settings><config:config-item-set config:name="ooo:configuration-settings"><config:config-item config:name="PrinterName" config:type="string">Consulta 915 123 456</config:config-item><config:config-item config:name="PrinterSetup" config:type="base64Binary">{PRINTER}</config:config-item><config:config-item config:name="PrintReversed" config:type="boolean">false</config:config-item></config:config-item-set></office:settings></office:document-settings>"""
CERTIFICATE = base64.b64encode(b"0\x82\x01\x0c\x06\x03U\x04\x03\x0c\x1fLOPEZ GARCIA MARIA - 12345678Z").decode()
SIGNATURES = f"""<?xml version="1.0" encoding="UTF-8"?>
<document-signatures xmlns="urn:oasis:names:tc:opendocument:xmlns:digitalsignature:1.0"><Signature xmlns="http://www.w3.org/2000/09/xmldsig#"><KeyInfo><X509Data><X509IssuerSerial><X509IssuerName>CN=AC FNMT Usuarios</X509IssuerName></X509IssuerSerial><X509Certificate>{CERTIFICATE}</X509Certificate></X509Data></KeyInfo></Signature></document-signatures>"""
MACRO = f"""<?xml version="1.0" encoding="UTF-8"?>
<script:module {NS} script:name="Module1" script:language="StarBasic">Sub Avisar
  MsgBox "Llamar a maria.lopez@example.com"
End Sub</script:module>"""


def manifest(media_type: str, parts: dict[str, str]) -> str:
    entries = "".join(
        f'<manifest:file-entry manifest:full-path="{path}" manifest:media-type="{kind}"/>'
        for path, kind in parts.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
        'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" '
        'manifest:version="1.3"><manifest:file-entry manifest:full-path="/" '
        f'manifest:version="1.3" manifest:media-type="{media_type}"/>{entries}</manifest:manifest>'
    )


def write_package(path: Path, media_type: str, parts: dict[str, str | bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo("mimetype"), media_type)
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


def make_odt(path: Path) -> Path:
    media_type = "application/vnd.oasis.opendocument.text"
    parts: dict[str, str | bytes] = {
        "content.xml": ODT_CONTENT,
        "styles.xml": ODT_STYLES,
        "meta.xml": ODT_META,
        "settings.xml": ODT_SETTINGS,
        "Pictures/foto.png": PNG,
        "Thumbnails/thumbnail.png": PNG + b"first page render",
        "Basic/Standard/Module1.xml": MACRO,
        "Configurations2/accelerator/current.xml": "<accel/>",
        "META-INF/documentsignatures.xml": SIGNATURES,
    }
    parts["META-INF/manifest.xml"] = manifest(
        media_type,
        {name: "text/xml" if name.endswith(".xml") else "image/png" for name in parts},
    )
    return write_package(path, media_type, parts)


def cells(*values: str) -> str:
    return "".join(
        f'<table:table-cell office:value-type="string"><text:p>{v}</text:p></table:table-cell>'
        for v in values
    )


SHEET = "'Paciente 12345678Z'"
ODS_CONTENT = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {NS} office:version="1.3"><office:automatic-styles><style:style style:name="gr1" style:family="graphic"><style:graphic-properties draw:fill="solid"/></style:style></office:automatic-styles><office:body><office:spreadsheet>
<table:content-validations><table:content-validation table:name="val1" table:condition="of:cell-content-is-in-list(&quot;Ana Torres&quot;;&quot;Luis Gómez&quot;)" table:allow-empty-cell="true"><table:help-message table:title="Ayuda" table:display="true"><text:p>Elija un médico</text:p></table:help-message></table:content-validation></table:content-validations>
<table:table table:name="Paciente 12345678Z"><table:table-column table:number-columns-repeated="6"/>
<table:table-row>{cells("Nombre", "DNI", "Teléfono", "Fecha de nacimiento", "Importe", "Estado")}</table:table-row>
<table:table-row table:number-rows-repeated="2"><table:table-cell office:value-type="string" table:content-validation-name="val1"><text:p>Laura Gil Mora</text:p></table:table-cell><table:table-cell office:value-type="string"><text:p>11111111H</text:p></table:table-cell><table:table-cell table:number-columns-repeated="3"/><table:table-cell office:value-type="string"><text:p>alta</text:p></table:table-cell></table:table-row>
<table:table-row><table:table-cell office:value-type="string"><office:annotation office:display="false" draw:style-name="gr1" svg:width="3cm" svg:height="1cm" svg:x="2cm" svg:y="0cm"><dc:creator>Luis Gómez Ferrer</dc:creator><dc:date>2024-03-01T10:00:00</dc:date><text:p>Avisar a pedro.ruiz@example.org</text:p></office:annotation><text:p>Pedro <text:span>Ruiz</text:span> Soto</text:p></table:table-cell><table:table-cell office:value-type="string"><text:p>87654321X</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="612345678"><text:p>612345678</text:p></table:table-cell><table:table-cell office:value-type="date" office:date-value="1980-05-17"><text:p>17/05/80</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="120.5"><text:p>120,50 €</text:p></table:table-cell><table:table-cell table:number-columns-repeated="2" office:value-type="string"><text:p>pendiente</text:p></table:table-cell></table:table-row>
<table:table-row><table:table-cell table:formula="of:=&quot;Sr. &quot;&amp;[.A4]" office:value-type="string" office:string-value="Sr. Pedro Ruiz Soto"><text:p>Sr. Pedro Ruiz Soto</text:p></table:table-cell><table:table-cell table:number-columns-repeated="3"/><table:table-cell table:formula="of:=[$'Paciente 12345678Z'.E4]*2" office:value-type="float" office:value="241"><text:p>241</text:p></table:table-cell></table:table-row>
<table:table-row table:number-rows-repeated="1048570"><table:table-cell table:number-columns-repeated="1024"/></table:table-row>
<calcext:conditional-formats><calcext:conditional-format calcext:target-range-address="{SHEET}.A2:{SHEET}.A9"><calcext:condition calcext:apply-style-name="Bad" calcext:value="=&quot;Pedro Ruiz Soto&quot;" calcext:base-cell-address="{SHEET}.A2"/></calcext:conditional-format></calcext:conditional-formats>
</table:table>
<table:named-expressions><table:named-range table:name="Responsable" table:cell-range-address="${SHEET}.$A$2" table:base-cell-address="${SHEET}.$A$2"/><table:named-expression table:name="Firma" table:expression="of:=&quot;Dra. Lucía Fernández&quot;" table:base-cell-address="${SHEET}.$A$1"/></table:named-expressions>
<table:database-ranges><table:database-range table:name="__Anonymous_Sheet_DB__0" table:target-range-address="{SHEET}.A1:{SHEET}.F5" table:display-filter-buttons="true"><table:filter><table:filter-condition table:field-number="0" table:value="Laura Gil Mora" table:operator="="/></table:filter></table:database-range></table:database-ranges>
</office:spreadsheet></office:body></office:document-content>"""
ODS_STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {NS} office:version="1.3"><office:styles><number:number-style style:name="N1"><number:number number:decimal-places="2"/><number:text> €</number:text></number:number-style></office:styles><office:master-styles><style:master-page style:name="Default"><style:header><style:region-left><text:p><text:sheet-name>???</text:sheet-name></text:p></style:region-left><style:region-right><text:p>Responsable: lucia.fernandez@example.com</text:p></style:region-right></style:header></style:master-page></office:master-styles></office:document-styles>"""


def make_ods(path: Path) -> Path:
    media_type = "application/vnd.oasis.opendocument.spreadsheet"
    parts: dict[str, str | bytes] = {
        "content.xml": ODS_CONTENT,
        "styles.xml": ODS_STYLES,
        "meta.xml": ODT_META,
    }
    parts["META-INF/manifest.xml"] = manifest(media_type, {name: "text/xml" for name in parts})
    return write_package(path, media_type, parts)


def package_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", "replace") for name in archive.namelist()
        )


ODT_SECRETS = (
    "López",
    "12345678Z",
    "5678Z",
    "Ruiz Bravo",
    "Carmen",
    "maria.lopez@example.com",
    "612 345 678",
    "Calle Mayor",
    "Ramón",
    "Ortega",
    ">RO<",
    "2024-03",
    "87654321X",
    "Pedro Ruiz",
    "ana.torres@example.com",
    "pedro.ruiz@example.org",
    "11111111H",
    "rodrigo.diaz@example.com",
    "699112233",
    "699 112 233",
    "Lucía",
    "elena.martin@example.com",
    "915 123 456",
    "Juan Nadie",
    "Clínica San Rafael",
    "aGFzaA==",
    "first page render",
    "Impresora",
    "LOPEZ GARCIA",
    "MsgBox",
    "Plantillas",
)


def test_odt_reader_scans_text_hidden_values_and_package_parts(tmp_path):
    graph = read_document(make_odt(tmp_path / "informe.odt"))
    text = "\n".join(f.text for f in graph.fragments)
    for value in (
        "Paciente: María López García, DNI 12345678Z.",  # spans and text:s joined
        "Antes vivía en Calle Mayor 5.",  # tracked deletion
        "Llamar al 612 345 678.",  # comment
        "Dr. Ramón Ortega",  # comment and revision author
        "string-value",
    )[:4]:
        assert value in text, value
    for value in (
        "DNI 87654321X",  # hidden text value
        "ana.torres@example.com",  # user field value
        "Juan Nadie Gómez",  # form control value
        "rodrigo.diaz@example.com",  # index mark
        "ficha 11111111H",  # bookmark name
        "mailto:maria.lopez@example.com",
        "Consulta, tel. 915 123 456",  # header in styles.xml
        "Consulta 915 123 456",  # printer name in settings
        "printer=Impresora de carmen.ruiz@example.com",  # binary printer setup
        "LOPEZ GARCIA MARIA - 12345678Z",  # signing certificate subject
        'MsgBox "Llamar a maria.lopez@example.com"',  # macro source
        "Cuadro con DNI 11111111H y correo elena.martin@example.com",  # text box
        "699112233",  # table cell value apart from the displayed text
    ):
        assert any(value in f.text for f in graph.fragments), value
    paragraph = next(f.text for f in graph.fragments if f.text.startswith("Contacto:"))
    assert paragraph == "Contacto: escribir Tratamiento revisado. Control en 3 meses."
    assert not graph.complete
    assert {
        "office_media_requires_review",
        "office_thumbnail_requires_review",
        "embedded_or_active_content_not_extracted",
        "external_relationships_require_review",
    } <= set(graph.issues)


def test_odt_output_removes_identity_everywhere(tmp_path):
    source = make_odt(tmp_path / "informe.odt")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    package = package_text(result.output_path)
    for secret in ODT_SECRETS:
        assert secret not in package, secret
    with zipfile.ZipFile(result.output_path) as archive:
        names = archive.namelist()
        content = archive.read("content.xml").decode()
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    assert names[0] == "mimetype"
    assert set(names) == {"mimetype", "content.xml", "styles.xml", "meta.xml",
                          "META-INF/manifest.xml"}  # fmt: skip
    # Structure and formatting survive; a replacement lands in the first span.
    assert '<text:span text:style-name="T1">Paciente:</text:span> [PERSON]' in content
    assert "Tratamiento revisado." in content and "Control en 3 meses." in content
    assert "<office:annotation" in content and "<text:note " in content
    assert '<text:a xlink:type="simple" xlink:href="#nombre-1">ficha</text:a>' in content
    assert '<text:bookmark text:name="nombre-1"/>' in content
    assert "text:hidden-text" not in content and "office:forms" not in content
    assert 'office:value-type="string"><text:p>[PHONE]</text:p>' in content
    assert "Times New Roman" in package  # formatting is not content
    graph = read_document(result.output_path)
    assert graph.complete, graph.issues
    assert result.status == "APPROVED", result.issues
    removed = result.audit["office_removed"]
    for key in ("tracked_changes", "authors", "fields_flattened", "hyperlinks_unlinked",
                "media", "thumbnail", "macros", "signatures", "active_content",
                "protection_keys", "personal_properties"):  # fmt: skip
        assert removed.get(key), key


def test_odt_media_can_be_kept_but_then_blocks(tmp_path):
    source = make_odt(tmp_path / "informe.odt")
    result = DeidEngine(country="ES").deidentify(
        source,
        output=tmp_path / "out.odt",
        policy=Policy.strict(require_ner=False),
        office_media="keep",
    )
    assert result.status == "BLOCKED"
    assert "office_media_requires_review" in result.issues
    assert not (tmp_path / "out.odt").exists()


def test_ods_output_uses_headers_and_drops_hidden_values(tmp_path):
    source = make_ods(tmp_path / "pacientes.ods")
    graph = read_document(source)
    assert "ODS_REVIEW_REQUIRED" in graph.issues
    assert "spreadsheet_formulas_require_review" in graph.issues
    texts = {f.text for f in graph.fragments}
    assert {"Laura Gil Mora", "Pedro Ruiz Soto", "1980-05-17", "Paciente 12345678Z"} <= texts
    assert "Avisar a pedro.ruiz@example.org" in texts and "Luis Gómez Ferrer" in texts
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.ods", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    assert result.status == "REVIEW_REQUIRED"
    assert "ODS_REVIEW_REQUIRED" in result.issues
    package = package_text(result.output_path)
    for secret in ("Laura", "Gil Mora", "Pedro", "Ruiz", "11111111H", "87654321X",
                   "612345678", "1980-05-17", "17/05/80", "12345678Z", "Ana Torres",
                   "Luis Gómez", "Lucía", "pedro.ruiz@example.org",
                   "lucia.fernandez@example.com", "Carmen"):  # fmt: skip
        assert secret not in package, secret
    with zipfile.ZipFile(result.output_path) as archive:
        content = archive.read("content.xml").decode()
    assert 'table:name="Hoja1"' in content
    assert "of:=[$Hoja1.E4]*2" in content  # reference follows the renamed sheet
    assert "of:=&quot;Sr." not in content  # formula with a literal: value kept only
    assert "120,50 €" in content and 'office:value="120.5"' in content  # amounts stay
    assert content.count("<text:p>pendiente</text:p>") == 2  # repeated cell expanded
    assert 'table:number-rows-repeated="1048570"' in content  # empty rows not expanded
    assert "val1" not in content and "Elija un médico" not in content  # validation dropped
    assert "Responsable" in content and "Firma" not in content
    graph = read_document(result.output_path)
    assert graph.complete, graph.issues
    removed = result.audit["office_removed"]
    assert removed["criteria"] >= 3 and removed["defined_names"] == 1


def test_ods_repeated_rows_get_one_transformation_each(tmp_path):
    from deidflow.policies import Rule

    source = make_ods(tmp_path / "pacientes.ods")
    policy = Policy(default=Rule("indexed"), require_ner=False)
    result = DeidEngine(country="ES").deidentify(source, output=tmp_path / "out.ods", policy=policy)
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        content = archive.read("content.xml").decode()
    assert "table:number-rows-repeated=\"2\"" not in content
    identifiers = re.findall(r"\[ID_OFICIAL_\d+\]", content)
    assert len(identifiers) == 3 and len(set(identifiers)) == 2  # both copies share one


def test_odf_rejects_malformed_or_unsupported_packages(tmp_path):
    media_type = "application/vnd.oasis.opendocument.text"
    base = {"content.xml": ODT_CONTENT, "META-INF/manifest.xml": manifest(media_type, {})}
    cases = {
        "unknown": {**base, "extra/datos.bin": b"Juan"},
        "dtd": {**base, "content.xml": '<!DOCTYPE x [<!ENTITY a "b">]><x/>'},
        "encrypted": {
            **base,
            "META-INF/manifest.xml": manifest(media_type, {}).replace(
                'manifest:media-type="application/vnd.oasis.opendocument.text"/>',
                'manifest:media-type="application/vnd.oasis.opendocument.text">'
                "<manifest:encryption-data/></manifest:file-entry>",
            ),
        },
    }
    for name, parts in cases.items():
        path = write_package(tmp_path / f"{name}.odt", media_type, parts)
        result = DeidEngine(country="ES").deidentify(
            path, output=tmp_path / f"{name}.out.odt", policy=Policy.strict(require_ner=False)
        )
        assert result.status == "BLOCKED", name
        assert not (tmp_path / f"{name}.out.odt").exists()
    wrong = write_package(tmp_path / "hoja.odt", "application/vnd.oasis.opendocument.spreadsheet",
                          base)  # fmt: skip
    with pytest.raises(DocumentError):
        read_document(wrong)


def test_ods_with_huge_empty_repeats_is_fast(tmp_path):
    source = make_ods(tmp_path / "pacientes.ods")
    start = time.perf_counter()
    read_document(source)
    assert time.perf_counter() - start < 5


def test_eml_odt_attachment_is_rewritten(tmp_path):
    import email
    import email.policy
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = "ana@example.com"
    message["Subject"] = "Informe"
    message.set_content("Adjunto informe.\n")
    message.add_attachment(
        make_odt(tmp_path / "informe.odt").read_bytes(),
        maintype="application",
        subtype="vnd.oasis.opendocument.text",
        filename="Informe Maria Lopez.odt",
    )
    source = tmp_path / "con-odt.eml"
    source.write_bytes(message.as_bytes(policy=email.policy.default))
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.eml", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    parsed = email.message_from_bytes(result.output_path.read_bytes(), policy=email.policy.default)
    attachment = next(p for p in parsed.iter_attachments())
    assert attachment.get_filename() == "adjunto-1.odt"
    attached = tmp_path / "adjunto.odt"
    attached.write_bytes(attachment.get_content())
    assert "12345678Z" not in package_text(attached)


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
@pytest.mark.parametrize("maker", [make_odt, make_ods])
def test_odf_output_opens_in_libreoffice(tmp_path, maker):
    suffix = ".odt" if maker is make_odt else ".ods"
    source = maker(tmp_path / f"fuente{suffix}")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / f"out{suffix}", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    target = "txt:Text" if suffix == ".odt" else "csv"
    converted = subprocess.run(
        ["soffice", "--headless", f"-env:UserInstallation=file://{tmp_path}/lo",
         "--convert-to", target, "--outdir", str(tmp_path / "txt"),
         str(result.output_path)],  # fmt: skip
        capture_output=True,
        timeout=180,
    )
    assert converted.returncode == 0
    text = next((tmp_path / "txt").iterdir()).read_text("utf-8-sig", errors="replace")
    if suffix == ".odt":
        assert "Paciente: [PERSON], DNI [NATIONAL_ID]." in text
        assert "Tratamiento revisado." in text
    else:
        assert "[PERSON]" in text and "Importe" in text and "López" not in text


def test_ods_shapes_tables_manifest_types_and_empty_repeats(tmp_path):
    media_type = "application/vnd.oasis.opendocument.spreadsheet"
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {NS} office:version="1.3"><office:body><office:spreadsheet>
<table:table table:name="Hoja"><table:shapes><draw:frame draw:name="Cuadro" svg:width="4cm" svg:height="2cm" svg:x="1cm" svg:y="1cm"><draw:text-box><table:table table:name="Interna"><table:table-row><table:table-cell office:value-type="string"><text:p>DNI 12345678Z</text:p></table:table-cell></table:table-row></table:table></draw:text-box></draw:frame></table:shapes>
<table:table-row><table:table-cell office:value-type="string"><text:p>Nota</text:p></table:table-cell><table:table-cell table:number-columns-repeated="16000"><text:p/></table:table-cell></table:table-row>
<table:table-row><table:table-cell office:value-type="string"><text:p>Correo maria.lopez@example.com</text:p></table:table-cell></table:table-row>
</table:table></office:spreadsheet></office:body></office:document-content>"""
    parts: dict[str, str | bytes] = {"content.xml": content}
    parts["META-INF/manifest.xml"] = manifest(
        media_type, {"content.xml": "text/xml; DNI 87654321X"}
    )
    source = write_package(tmp_path / "formas.ods", media_type, parts)
    graph = read_document(source)
    assert any(f.text == "DNI 12345678Z" for f in graph.fragments)  # table inside a shape
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.ods", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    package = package_text(result.output_path)
    for secret in ("12345678Z", "87654321X", "maria.lopez@example.com"):
        assert secret not in package, secret
    assert 'table:number-columns-repeated="16000"' in package  # empty cells not expanded
