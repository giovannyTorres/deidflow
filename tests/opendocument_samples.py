from __future__ import annotations

import base64
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

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


CERTIFICATE = base64.b64encode(
    b"0\x82\x01\x0c\x06\x03U\x04\x03\x0c\x1fLOPEZ GARCIA MARIA - 12345678Z"
).decode()


SIGNATURES = f"""<?xml version="1.0" encoding="UTF-8"?>
<document-signatures xmlns="urn:oasis:names:tc:opendocument:xmlns:digitalsignature:1.0"><Signature xmlns="http://www.w3.org/2000/09/xmldsig#"><KeyInfo><X509Data><X509IssuerSerial><X509IssuerName>CN=AC FNMT Usuarios</X509IssuerName></X509IssuerSerial><X509Certificate>{CERTIFICATE}</X509Certificate></X509Data></KeyInfo></Signature></document-signatures>"""


MACRO = f"""<?xml version="1.0" encoding="UTF-8"?>
<script:module {NS} script:name="Module1" script:language="StarBasic">Sub Avisar
  MsgBox "Llamar a maria.lopez@example.com"
End Sub</script:module>"""


def manifest(media_type: str, parts: dict[str, str]) -> str:
    entries = "".join(
        f"<manifest:file-entry manifest:full-path={quoteattr(path)} manifest:media-type={quoteattr(kind)}/>"
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
def make_ods_cell(path: Path, cell_content: str) -> Path:
    media_type = "application/vnd.oasis.opendocument.spreadsheet"
    content = f'<office:document-content {NS}><office:body><office:spreadsheet><table:table table:name="Hoja"><table:table-row><table:table-cell>{cell_content}</table:table-cell></table:table-row></table:table></office:spreadsheet></office:body></office:document-content>'
    return write_package(
        path,
        media_type,
        {
            "content.xml": content,
            "META-INF/manifest.xml": manifest(media_type, {"content.xml": "text/xml"}),
        },
    )
