from __future__ import annotations

import re
import shutil
import subprocess
import zipfile

import pytest
from opendocument_samples import (
    NS,
    ODT_CONTENT,
    make_ods,
    make_odt,
    manifest,
    package_text,
    write_package,
)

from deidflow import DeidEngine, Policy
from deidflow.readers import DocumentError, read_document

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
    assert 'table:number-rows-repeated="2"' not in content
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
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation=file://{tmp_path}/lo",
            "--convert-to",
            target,
            "--outdir",
            str(tmp_path / "txt"),
            str(result.output_path),
        ],  # fmt: skip
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


@pytest.mark.parametrize("suffix", [".ods", ".xlsx"])
def test_eml_spreadsheet_attachment_is_kept_for_review(tmp_path, suffix):
    import email
    import email.policy
    from email.message import EmailMessage

    from test_office_xlsx import make_xlsx

    maker = make_ods if suffix == ".ods" else make_xlsx
    subtype = (
        "vnd.oasis.opendocument.spreadsheet"
        if suffix == ".ods"
        else "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    message = EmailMessage()
    message["From"] = "ana@example.com"
    message["Subject"] = "Hoja"
    message.set_content("Adjunto la hoja.\n")
    message.add_attachment(
        maker(tmp_path / f"hoja{suffix}").read_bytes(),
        maintype="application",
        subtype=subtype,
        filename=f"pacientes{suffix}",
    )
    source = tmp_path / "con-hoja.eml"
    source.write_bytes(message.as_bytes(policy=email.policy.default))
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.eml", policy=Policy.strict(require_ner=False)
    )
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert "INCOMPLETE_COVERAGE" not in result.issues
    parsed = email.message_from_bytes(result.output_path.read_bytes(), policy=email.policy.default)
    attachment = next(parsed.iter_attachments())
    assert attachment.get_filename() == f"adjunto-1{suffix}"


def test_inline_binary_image_is_kept_when_media_retention_is_requested(tmp_path):
    from opendocument_samples import NS, PNG, manifest, write_package

    media_type = "application/vnd.oasis.opendocument.text"
    import base64

    picture = base64.b64encode(PNG).decode()
    content = (
        f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {NS} '
        'office:version="1.3"><office:body><office:text><text:p>Informe.</text:p>'
        '<text:p><draw:frame draw:name="Foto" text:anchor-type="as-char" svg:width="1cm" '
        f'svg:height="1cm"><draw:image><office:binary-data>{picture}</office:binary-data>'
        "</draw:image></draw:frame></text:p></office:text></office:body></office:document-content>"
    )
    parts = {"content.xml": content}
    parts["META-INF/manifest.xml"] = manifest(media_type, {"content.xml": "text/xml"})
    source = write_package(tmp_path / "foto.odt", media_type, parts)
    policy = Policy.strict(require_ner=False)
    kept = DeidEngine().deidentify(
        source, output=tmp_path / "kept.odt", policy=policy, office_media="keep"
    )
    assert kept.status == "BLOCKED"  # retained, uninspected media is never approved
    removed = DeidEngine().deidentify(source, output=tmp_path / "removed.odt", policy=policy)
    assert removed.output_path is not None
    assert "binary-data" not in package_text(removed.output_path)


def test_rewritten_cell_keeps_spacing_of_unchanged_content(tmp_path):
    from opendocument_samples import make_ods_cell

    source = make_ods_cell(
        tmp_path / "dosis.ods",
        '<text:p>Dosis:<text:s text:c="3"/>15 mg<text:tab/>correo ana.lopez@example.com</text:p>',
    )
    result = DeidEngine().deidentify(
        source, output=tmp_path / "salida.ods", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        content = archive.read("content.xml").decode()
    assert "ana.lopez@example.com" not in content
    assert 'Dosis: <text:s text:c="2"/>15 mg<text:tab/>correo [EMAIL]' in content
    cell_text = [f.text for f in read_document(result.output_path).fragments if "Dosis" in f.text]
    assert cell_text and "Dosis:   15 mg\tcorreo [EMAIL]" in cell_text[0]
