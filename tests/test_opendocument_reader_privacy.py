import base64
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

import opendocument_privacy_samples as samples
import pytest
from opendocument_samples import make_ods_cell

from deidflow import DeidEngine, Policy
from deidflow.readers import DocumentError, read_document


@pytest.mark.parametrize("value", (samples.SECRET, f"<![CDATA[{samples.SECRET}]]>"))
def test_spreadsheet_raw_cell_text_is_not_silently_skipped(tmp_path, value):
    source = make_ods_cell(tmp_path / "raw.ods", value)
    with pytest.raises(DocumentError, match="cells require paragraph content") as error:
        read_document(source)
    assert samples.SECRET not in str(error.value)
    with pytest.raises(DocumentError, match="cells require paragraph content"):
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False))


@pytest.mark.parametrize(
    "value", (" \n", "<text:p>Importe</text:p>", " \n<text:p>Importe</text:p> \n")
)
def test_spreadsheet_paragraph_cells_and_pretty_print_whitespace_remain_supported(tmp_path, value):
    source = make_ods_cell(tmp_path / "supported.ods", value)
    graph = read_document(source)
    assert graph.complete, graph.issues
    result = DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False))
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert "ODS_REVIEW_REQUIRED" in result.issues


@pytest.mark.parametrize("encoding", ("utf-8", "utf-16le"))
@pytest.mark.parametrize(
    "channel",
    (
        "settings",
        "content_settings",
        "certificate",
        "signature_value",
        "rdf_certificate",
        "rdf_base64",
        "rdf_hex",
    ),
)
def test_opaque_binary_metadata_never_claims_complete_coverage(tmp_path, encoding, channel):
    payload = samples.SECRET.encode(encoding)
    encoded = base64.b64encode(payload).decode()
    if channel in {"settings", "content_settings"}:
        element = f'<config:config-item config:name="PrinterSetup" config:type="base64Binary">{encoded}</config:config-item>'
        body = element if channel == "content_settings" else "<text:p>Informe.</text:p>"
        parts = (
            {}
            if channel == "content_settings"
            else {
                "settings.xml": f'<office:document-settings {samples.NS} xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"><office:settings>{element}</office:settings></office:document-settings>'
            }
        )
        source = samples.package(
            tmp_path,
            body,
            root_attributes='xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"',
            parts=parts,
        )
    else:
        tag = (
            "X509Certificate" if channel in {"certificate", "rdf_certificate"} else "SignatureValue"
        )
        if channel in {"rdf_base64", "rdf_hex"}:
            kind = "base64Binary" if channel == "rdf_base64" else "hexBinary"
            encoded = encoded if channel == "rdf_base64" else payload.hex()
            element = f'<rdf:value rdf:datatype="http://www.w3.org/2001/XMLSchema#{kind}">{encoded}</rdf:value>'
        else:
            element = f"<ds:{tag}>{encoded}</ds:{tag}>"
        name = "manifest.rdf" if channel.startswith("rdf_") else "META-INF/documentsignatures.xml"
        part = f'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{element}</rdf:RDF>'
        source = samples.package(tmp_path, "<text:p>Informe.</text:p>", parts={name: part})
    graph = read_document(source)
    assert not graph.complete
    assert "uninspected_odf_binary_metadata" in graph.issues
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "BLOCKED"
    )
    if encoding == "utf-8" and channel in {"settings", "certificate", "rdf_certificate"}:
        assert any(samples.SECRET in fragment.text for fragment in graph.fragments)


@pytest.mark.parametrize("value", ("", " \n"))
def test_empty_binary_settings_do_not_claim_uninspected_payload(tmp_path, value):
    source = samples.package(
        tmp_path,
        f'<config:config-item config:type="base64Binary">{value}</config:config-item>',
        root_attributes='xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"',
    )
    graph = read_document(source)
    assert graph.complete, graph.issues
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "APPROVED"
    )


@pytest.mark.parametrize("tag", ("s", "tab", "line-break"))
@pytest.mark.parametrize(
    "child", (samples.SECRET, f"<text:span>{samples.SECRET}</text:span>", "<text:span/>", " ")
)
def test_nonempty_whitespace_elements_reject_retained_children(tmp_path, tag, child):
    source = samples.package(tmp_path, f"<text:p>Informe.<text:{tag}>{child}</text:{tag}></text:p>")
    with pytest.raises(DocumentError, match="whitespace elements must be empty") as error:
        read_document(source)
    assert samples.SECRET not in str(error.value)
    with pytest.raises(DocumentError, match="whitespace elements must be empty"):
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False))


def test_empty_whitespace_elements_preserve_visible_separators(tmp_path):
    source = samples.package(
        tmp_path, '<text:p>Informe.<text:s text:c="2"/>A<text:tab/>B<text:line-break/>C</text:p>'
    )
    graph = read_document(source)
    assert graph.complete, graph.issues
    assert any("Informe.  A\tB\nC" in fragment.text for fragment in graph.fragments)
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "APPROVED"
    )


def assert_uninspected_source(source: Path):
    graph = read_document(source)
    assert not graph.complete
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "BLOCKED"
    )


@pytest.mark.parametrize("channel", ("standard_alias", "element_name", "empty_attribute_name"))
def test_sensitive_qualified_names_are_visible_to_standalone_verification(tmp_path, channel):
    attributes, body = samples.QUALIFIED_NAME_CASES[channel]
    source = samples.package(tmp_path, body, root_attributes=attributes)
    assert any("12345678Z" in f.text for f in read_document(source).fragments)
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "BLOCKED"
    )


def test_manifest_content_attributes_are_visible_to_standalone_verification(tmp_path):
    source = samples.package(
        tmp_path,
        "<text:p>Informe.</text:p>",
        media_types={"content.xml": "application/12345678Z"},
    )
    assert any("12345678Z" in f.text for f in read_document(source).fragments)
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "BLOCKED"
    )


def test_reader_rejects_excessive_depth_and_accepts_supported_nested_text(tmp_path):
    supported = samples.package(
        tmp_path, "<text:p>" + "<text:span>" * 32 + "Informe." + "</text:span>" * 32 + "</text:p>"
    )
    assert any("Informe." in f.text for f in read_document(supported).fragments)
    excessive = samples.package(
        tmp_path,
        "<text:p>" + "<text:span>" * 1100 + "Informe." + "</text:span>" * 1100 + "</text:p>",
    )
    with pytest.raises(DocumentError, match="nesting exceeds"):
        read_document(excessive)


@pytest.mark.parametrize("attribute", samples.STRUCTURAL_ATTRIBUTES)
@pytest.mark.parametrize("value", (samples.SECRET, "12345678Z"))
def test_structural_values_are_scanned_and_block_source_verification(tmp_path, attribute, value):
    source = samples.package(
        tmp_path,
        f"<text:p {attribute}={quoteattr(value)}>Informe.</text:p>",
    )
    graph = read_document(source)
    assert any(value in fragment.text for fragment in graph.fragments)
    engine = DeidEngine(country="ES")
    assert engine.verify(source, policy=Policy.strict(require_ner=False)).status != "APPROVED"


@pytest.mark.parametrize("href", samples.UNRESOLVED_LINKS)
def test_unresolved_links_preserve_incomplete_reader_coverage(tmp_path, href):
    source = samples.package(
        tmp_path,
        f"<text:p><text:a xlink:href={quoteattr(href)}>abrir</text:a></text:p>",
        parts={"styles.xml": samples.STYLES},
    )
    graph = read_document(source)
    assert not graph.complete
    assert "unresolved_odf_package_reference" in graph.issues


@pytest.mark.parametrize("href", ("./styles.xml", "st%79les.xml", "nested/../styles.xml"))
def test_real_package_links_keep_reader_coverage_complete(tmp_path, href):
    source = samples.package(
        tmp_path,
        f"<text:p><text:a xlink:href={quoteattr(href)}>abrir</text:a></text:p>",
        parts={"styles.xml": samples.STYLES},
    )
    graph = read_document(source)
    assert graph.complete, graph.issues
    assert "unresolved_odf_package_reference" not in graph.issues


def test_embedded_links_resolve_against_the_owning_part(tmp_path):
    source = samples.package(
        tmp_path,
        '<text:p>Informe.</text:p><draw:frame draw:name="asset">'
        '<draw:object xlink:href="./Object%201"/></draw:frame>',
        parts={"styles.xml": samples.STYLES, "Object 1/content.xml": samples.EMBEDDED_RELATIVE_XML},
        media_types={"Object 1/": "application/vnd.oasis.opendocument.text"},
    )
    with zipfile.ZipFile(source) as archive:
        assert "Object 1/" not in archive.namelist()
    graph = read_document(source)
    assert "unresolved_odf_package_reference" not in graph.issues


def test_standalone_verification_inspects_qualified_names_in_auxiliary_metadata_xml(tmp_path):
    source = samples.package(
        tmp_path,
        "<text:p>Informe.</text:p>",
        parts={"settings.xml": samples.AUXILIARY_SENSITIVE_SETTINGS_XML},
    )
    result = DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False))
    assert result.status == "BLOCKED", result.status
    assert any("12345678Z" in fragment.text for fragment in read_document(source).fragments)


def test_comment_and_pi_markers_inside_cdata_are_visible_text_not_hidden_channels(tmp_path):
    source = samples.package(
        tmp_path, "<text:p><![CDATA[literal <!-- marca --> y <?audit dato?>.]]></text:p>"
    )
    graph = read_document(source)
    assert graph.complete, graph.issues
    assert any("literal <!-- marca --> y <?audit dato?>." in f.text for f in graph.fragments)
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "APPROVED"
    )


def test_empty_directory_entry_is_benign(tmp_path):
    source = samples.package(tmp_path, "<text:p>Informe.</text:p>", parts={"ordinary/": b""})
    assert read_document(source).complete
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "APPROVED"
    )


@pytest.mark.parametrize("encoding", ("utf-8", "utf-16"))
@pytest.mark.parametrize("hidden", (f"<!--{samples.SECRET}-->", f"<?audit {samples.SECRET}?>"))
def test_xml_comments_and_processing_instructions_are_uninspected_until_removed_reader(
    tmp_path, encoding, hidden
):
    content = (
        f'<office:document-content {samples.NS} office:version="1.3">'
        f"<office:body><office:text><text:p>Informe.</text:p>{hidden}"
        "</office:text></office:body></office:document-content>"
    ).encode(encoding)
    source = samples.package(tmp_path, "", parts={"content.xml": content})
    assert_uninspected_source(source)


@pytest.mark.parametrize(
    "name", ("Configurations2/accelerator/current.xml", "layout-cache", "ordinary/")
)
def test_nonempty_opaque_package_channel_is_uninspected_until_removed_reader(tmp_path, name):
    source = samples.package(
        tmp_path, "<text:p>Informe.</text:p>", parts={name: b"\xff" + samples.SECRET.encode()}
    )
    assert_uninspected_source(source)


@pytest.mark.parametrize(
    "channel",
    (
        "archive_comment",
        "member_comment",
        "member_extra",
        "local_extra_only",
        "local_name_mismatch",
        "prefix",
        "suffix",
    ),
)
def test_opaque_zip_metadata_is_uninspected_until_rebuilt_reader(tmp_path, channel):
    source = samples.package(tmp_path, "<text:p>Informe.</text:p>")
    samples.add_zip_metadata(source, channel)
    assert_uninspected_source(source)


@pytest.mark.parametrize("member", ("content.xml", "META-INF/manifest.xml"))
def test_terminal_deflate_suffix_keeps_source_verification_incomplete(tmp_path, member):
    source = samples.package(tmp_path, "<text:p>Informe.</text:p>")
    samples.append_deflate_tail(source, member, samples.SECRET.encode())
    assert_uninspected_source(source)


def test_deflate_validation_does_not_expand_beyond_the_declared_size(tmp_path):
    import struct
    import tracemalloc

    source = samples.package(tmp_path, "<text:p>Informe.</text:p>")
    read_document(source)  # load parser modules before the allocation measurement
    with zipfile.ZipFile(source, "a") as archive:
        info = zipfile.ZipInfo("ordinary/")
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, b"A" * (8 * 1024 * 1024))
        handle = archive.fp
        assert handle is not None
        end = handle.tell()
        info.file_size = 0
        handle.seek(info.header_offset + 22)
        handle.write(struct.pack("<I", 0))
        handle.seek(end)
    tracemalloc.start()
    try:
        graph = read_document(source)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert not graph.complete
    assert peak < 2 * 1024 * 1024
