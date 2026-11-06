import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest
from opendocument_privacy_samples import NS, SECRET, STYLES, add_zip_metadata, package

from deidflow import DeidEngine, Policy
from deidflow.readers import DocumentError, read_document


def assert_uninspected_source(source: Path):
    graph = read_document(source)
    assert not graph.complete
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "BLOCKED"
    )


@pytest.mark.parametrize("channel", ("standard_alias", "element_name", "empty_attribute_name"))
def test_sensitive_qualified_names_are_visible_to_standalone_verification(tmp_path, channel):
    if channel == "standard_alias":
        attributes = 'xmlns:dni-12345678Z="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        body = "<dni-12345678Z:p>Informe.</dni-12345678Z:p>"
    else:
        attributes = 'xmlns:private="urn:deidflow:fixture"'
        body = (
            "<private:dni-12345678Z>Informe.</private:dni-12345678Z>"
            if channel == "element_name"
            else '<text:p private:dni-12345678Z="">Informe.</text:p>'
        )
    source = package(tmp_path, body, root_attributes=attributes)
    assert any("12345678Z" in f.text for f in read_document(source).fragments)
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "BLOCKED"
    )


def test_manifest_content_attributes_are_visible_to_standalone_verification(tmp_path):
    source = package(
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
    supported = package(
        tmp_path, "<text:p>" + "<text:span>" * 32 + "Informe." + "</text:span>" * 32 + "</text:p>"
    )
    assert any("Informe." in f.text for f in read_document(supported).fragments)
    excessive = package(
        tmp_path,
        "<text:p>" + "<text:span>" * 1100 + "Informe." + "</text:span>" * 1100 + "</text:p>",
    )
    with pytest.raises(DocumentError, match="nesting exceeds"):
        read_document(excessive)


@pytest.mark.parametrize(
    "attribute",
    (
        "style:patient-note",
        "style:name",
        "svg:font-family",
        "text:style-name",
        "xmlns:private",
    ),
)
@pytest.mark.parametrize("value", (SECRET, "12345678Z"))
def test_sensitive_unmodeled_structural_attribute_is_inspected_and_fails_closed_reader(
    tmp_path, attribute, value
):
    source = package(
        tmp_path,
        f"<text:p {attribute}={quoteattr(value)}>Informe.</text:p>",
    )
    graph = read_document(source)
    assert any(value in fragment.text for fragment in graph.fragments)
    engine = DeidEngine(country="ES")
    assert engine.verify(source, policy=Policy.strict(require_ner=False)).status != "APPROVED"


@pytest.mark.parametrize(
    "href",
    (
        "synthetic.patient%40example.test",
        "./synthetic.patient%40example.test",
        "nested/../synthetic.patient@example.test",
        "../styles.xml",
        "missing.xml",
        "styles.xml?contact=synthetic.patient%40example.test",
        "styles.xml#synthetic.patient%40example.test",
    ),
)
def test_unresolved_relative_or_encoded_link_is_unlinked_without_losing_text_reader(tmp_path, href):
    source = package(
        tmp_path,
        f"<text:p><text:a xlink:href={quoteattr(href)}>abrir</text:a></text:p>",
        parts={"styles.xml": STYLES},
    )
    graph = read_document(source)
    assert not graph.complete
    assert "unresolved_odf_package_reference" in graph.issues


@pytest.mark.parametrize("href", ("./styles.xml", "st%79les.xml", "nested/../styles.xml"))
def test_real_package_target_preserves_unchanged_uri_spelling_reader(tmp_path, href):
    source = package(
        tmp_path,
        f"<text:p><text:a xlink:href={quoteattr(href)}>abrir</text:a></text:p>",
        parts={"styles.xml": STYLES},
    )
    graph = read_document(source)
    assert graph.complete, graph.issues
    assert "unresolved_odf_package_reference" not in graph.issues


def test_implicit_embedded_directory_and_owner_relative_target_are_resolved_reader(tmp_path):
    embedded = (
        f'<office:document-content {NS} office:version="1.3">'
        "<office:body><office:text><text:p>"
        '<text:a xlink:href="../styles.xml">detalle</text:a>'
        "</text:p></office:text></office:body></office:document-content>"
    )
    source = package(
        tmp_path,
        '<text:p>Informe.</text:p><draw:frame draw:name="asset">'
        '<draw:object xlink:href="./Object%201"/></draw:frame>',
        parts={"styles.xml": STYLES, "Object 1/content.xml": embedded},
        media_types={"Object 1/": "application/vnd.oasis.opendocument.text"},
    )
    with zipfile.ZipFile(source) as archive:
        assert "Object 1/" not in archive.namelist()
    graph = read_document(source)
    assert "unresolved_odf_package_reference" not in graph.issues


def test_standalone_verification_inspects_qualified_names_in_auxiliary_metadata_xml(tmp_path):
    settings = (
        "<office:document-settings "
        f"{NS} "
        'xmlns:dni-12345678Z="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
        "<office:settings><dni-12345678Z:config-item-set/></office:settings>"
        "</office:document-settings>"
    )
    source = package(tmp_path, "<text:p>Informe.</text:p>", parts={"settings.xml": settings})
    result = DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False))
    assert result.status == "BLOCKED", result.status
    assert any("12345678Z" in fragment.text for fragment in read_document(source).fragments)


def test_comment_and_pi_markers_inside_cdata_are_visible_text_not_hidden_channels(tmp_path):
    source = package(
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
    source = package(tmp_path, "<text:p>Informe.</text:p>", parts={"ordinary/": b""})
    assert read_document(source).complete
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "APPROVED"
    )


@pytest.mark.parametrize("encoding", ("utf-8", "utf-16"))
@pytest.mark.parametrize("hidden", (f"<!--{SECRET}-->", f"<?audit {SECRET}?>"))
def test_xml_comments_and_processing_instructions_are_uninspected_until_removed_reader(
    tmp_path, encoding, hidden
):
    content = (
        f'<office:document-content {NS} office:version="1.3">'
        f"<office:body><office:text><text:p>Informe.</text:p>{hidden}"
        "</office:text></office:body></office:document-content>"
    ).encode(encoding)
    source = package(tmp_path, "", parts={"content.xml": content})
    assert_uninspected_source(source)


@pytest.mark.parametrize(
    "name", ("Configurations2/accelerator/current.xml", "layout-cache", "ordinary/")
)
def test_nonempty_opaque_package_channel_is_uninspected_until_removed_reader(tmp_path, name):
    source = package(tmp_path, "<text:p>Informe.</text:p>", parts={name: b"\xff" + SECRET.encode()})
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
    source = package(tmp_path, "<text:p>Informe.</text:p>")
    add_zip_metadata(source, channel)
    assert_uninspected_source(source)
