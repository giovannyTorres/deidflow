import email
import email.policy
import time
from email.message import EmailMessage

import pytest
from opendocument_samples import NS, ODT_CONTENT, make_ods, make_odt, manifest, write_package

from deidflow import DeidEngine, Policy
from deidflow.readers import DocumentError, read_document


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


@pytest.mark.parametrize("maker,suffix", ((make_odt, ".odt"), (make_ods, ".ods")))
def test_odf_output_remains_unsupported_until_writer_is_available(tmp_path, maker, suffix):
    source = maker(tmp_path / ("source" + suffix))
    output = tmp_path / ("safe" + suffix)
    result = DeidEngine(country="ES").deidentify(
        source, output=output, policy=Policy.strict(require_ner=False)
    )
    assert result.status == "UNSUPPORTED"
    assert result.output_path is None
    assert not output.exists()


@pytest.mark.parametrize("maker,suffix", ((make_odt, ".odt"), (make_ods, ".ods")))
def test_reader_registration_does_not_retain_unprocessed_email_attachments(tmp_path, maker, suffix):
    payload = maker(tmp_path / ("attachment" + suffix)).read_bytes()
    message = EmailMessage()
    message.set_content("Adjunto informe.\n")
    message.add_attachment(
        payload, maintype="application", subtype="octet-stream", filename="informe" + suffix
    )
    source = tmp_path / "source.eml"
    source.write_bytes(message.as_bytes(policy=email.policy.default))
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.eml", policy=Policy.strict(require_ner=False)
    )
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert "EMAIL_ATTACHMENT_REMOVED" in result.issues
    assert result.output_path is not None
    parsed = email.message_from_bytes(result.output_path.read_bytes(), policy=email.policy.default)
    assert list(parsed.iter_attachments()) == []
    assert all(payload not in (part.get_payload(decode=True) or b"") for part in parsed.walk())


def test_ods_with_huge_empty_repeats_is_fast(tmp_path):
    source = make_ods(tmp_path / "pacientes.ods")
    start = time.perf_counter()
    read_document(source)
    assert time.perf_counter() - start < 5


def test_ods_reader_scans_cells_formulas_and_typed_values(tmp_path):
    graph = read_document(make_ods(tmp_path / "pacientes.ods"))
    assert "ODS_REVIEW_REQUIRED" in graph.issues
    assert "spreadsheet_formulas_require_review" in graph.issues
    texts = {f.text for f in graph.fragments}
    assert {"Laura Gil Mora", "Pedro Ruiz Soto", "1980-05-17", "Paciente 12345678Z"} <= texts
    assert "Avisar a pedro.ruiz@example.org" in texts and "Luis Gómez Ferrer" in texts


def test_clean_ods_standalone_verification_still_requires_review(tmp_path):
    media_type = "application/vnd.oasis.opendocument.spreadsheet"
    content = f"<office:document-content {NS}><office:body><office:spreadsheet/></office:body></office:document-content>"
    source = write_package(
        tmp_path / "clean.ods",
        media_type,
        {
            "content.xml": content,
            "META-INF/manifest.xml": manifest(media_type, {"content.xml": "text/xml"}),
        },
    )
    assert read_document(source).complete
    result = DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False))
    assert result.status == "REVIEW_REQUIRED"
    assert "ODS_REVIEW_REQUIRED" in result.issues


@pytest.mark.parametrize("channel", ("dtd", "encrypted", "wrong_media", "unknown"))
def test_reader_rejects_invalid_packages_and_preserves_unknown_part_uncertainty(tmp_path, channel):
    media_type = "application/vnd.oasis.opendocument.text"
    parts = {"content.xml": ODT_CONTENT, "META-INF/manifest.xml": manifest(media_type, {})}
    if channel == "dtd":
        parts["content.xml"] = '<!DOCTYPE x [<!ENTITY a "b">]><x/>'
    elif channel == "encrypted":
        parts["META-INF/manifest.xml"] = manifest(media_type, {}).replace(
            'manifest:media-type="application/vnd.oasis.opendocument.text"/>',
            'manifest:media-type="application/vnd.oasis.opendocument.text">'
            "<manifest:encryption-data/></manifest:file-entry>",
        )
    elif channel == "wrong_media":
        media_type = "application/vnd.oasis.opendocument.spreadsheet"
    else:
        parts["extra/datos.bin"] = "DNI 12345678Z"
    source = write_package(tmp_path / "source.odt", media_type, parts)
    if channel == "unknown":
        assert not read_document(source).complete
        assert (
            DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
            == "BLOCKED"
        )
    else:
        with pytest.raises(DocumentError):
            read_document(source)
