import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

import opendocument_privacy_samples as samples
import pytest
from opendocument_privacy_samples import (
    NS,
    SECRET,
    STYLES,
    add_zip_metadata,
    append_deflate_tail,
    package,
)
from opendocument_samples import make_ods_cell

from deidflow import DeidEngine, Policy
from deidflow.readers import read_document


@pytest.mark.parametrize("container", ("text:p", "text:span", "draw:image"))
def test_binary_media_removal_preserves_context_or_blocks_unsupported_placement(
    tmp_path, container
):
    binary = f"<{container}><office:binary-data>Ynl0ZXM=</office:binary-data></{container}>"
    body = (
        "<text:p>Tratamiento: 15 mg diarios."
        + ("<office:binary-data>Ynl0ZXM=</office:binary-data>" if container == "text:p" else binary)
        + " Control en tres meses.</text:p>"
    )
    source = package(
        tmp_path,
        body,
    )
    output = tmp_path / "safe.odt"
    engine = DeidEngine(country="ES")
    policy = Policy.strict(require_ner=False)
    result = engine.deidentify(source, output=output, policy=policy)
    if container != "draw:image":
        assert result.status == "BLOCKED"
        assert result.issues == ["MALFORMED_INPUT"]
        assert result.output_path is None and not output.exists()
    else:
        assert result.output_path is not None, result.issues
        with zipfile.ZipFile(result.output_path) as archive:
            content = archive.read("content.xml").decode()
        assert "Tratamiento: 15 mg diarios." in content
        assert "Control en tres meses." in content
        assert "binary-data" not in content and "draw:image" not in content
        assert engine.verify(result.output_path, policy=policy).status == "APPROVED"


@pytest.mark.parametrize("tag", ("s", "tab", "line-break"))
@pytest.mark.parametrize("child", (SECRET, f"<text:span>{SECRET}</text:span>", "<text:span/>", " "))
def test_whitespace_element_children_block_output_without_emitting_file(tmp_path, tag, child):
    source = package(tmp_path, f"<text:p>Informe.<text:{tag}>{child}</text:{tag}></text:p>")
    output = tmp_path / "safe.odt"
    result = DeidEngine(country="ES").deidentify(
        source, output=output, policy=Policy.strict(require_ner=False)
    )
    assert result.status == "BLOCKED"
    assert result.issues == ["MALFORMED_INPUT"]
    assert result.output_path is None
    assert not output.exists()


def test_empty_whitespace_elements_still_rewrite_and_verify(tmp_path):
    source = package(
        tmp_path, '<text:p>Informe.<text:s text:c="2"/>A<text:tab/>B<text:line-break/>C</text:p>'
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    graph = read_document(result.output_path)
    assert graph.complete, graph.issues
    assert any("Informe.  A\tB\nC" in fragment.text for fragment in graph.fragments)
    assert (
        DeidEngine(country="ES")
        .verify(result.output_path, policy=Policy.strict(require_ner=False))
        .status
        == "APPROVED"
    )


@pytest.mark.parametrize("value", (SECRET, f"<![CDATA[{SECRET}]]>"))
def test_direct_spreadsheet_cell_text_blocks_output_without_emitting_file(tmp_path, value):
    source = make_ods_cell(tmp_path / "raw.ods", value)
    output = tmp_path / "safe.ods"
    result = DeidEngine(country="ES").deidentify(
        source, output=output, policy=Policy.strict(require_ner=False)
    )
    assert result.status == "BLOCKED"
    assert result.issues == ["MALFORMED_INPUT"]
    assert result.output_path is None
    assert not output.exists()


@pytest.mark.parametrize(
    "value", (" \n", "<text:p>Importe</text:p>", " \n<text:p>Importe</text:p> \n")
)
def test_supported_spreadsheet_cells_still_emit_reviewable_output(tmp_path, value):
    source = make_ods_cell(tmp_path / "supported.ods", value)
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.ods", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    assert read_document(result.output_path).complete
    assert (
        DeidEngine(country="ES")
        .verify(result.output_path, policy=Policy.strict(require_ner=False))
        .status
        == "REVIEW_REQUIRED"
    )


@pytest.mark.parametrize("encoding", ("utf-8", "utf-16le"))
@pytest.mark.parametrize(
    "channel",
    ("settings", "certificate", "signature_value", "rdf_certificate", "rdf_base64", "rdf_hex"),
)
def test_removed_opaque_metadata_produces_independently_verified_output(
    tmp_path, encoding, channel
):
    source = samples.binary_metadata_package(tmp_path, encoding, channel)
    engine = DeidEngine(country="ES")
    policy = Policy.strict(require_ner=False)
    assert not read_document(source).complete
    assert engine.verify(source, policy=policy).status == "BLOCKED"
    result = engine.deidentify(source, output=tmp_path / "safe.odt", policy=policy)
    assert result.output_path is not None, result.issues
    assert read_document(result.output_path).complete
    assert engine.verify(result.output_path, policy=policy).status == "APPROVED"
    with zipfile.ZipFile(result.output_path) as archive:
        assert not {"settings.xml", "manifest.rdf", "META-INF/documentsignatures.xml"} & set(
            archive.namelist()
        )


@pytest.mark.parametrize("encoding", ("utf-8", "utf-16le"))
def test_opaque_binary_settings_retained_outside_settings_part_block_output(tmp_path, encoding):
    source = samples.binary_metadata_package(tmp_path, encoding, "content_settings")
    output = tmp_path / "safe.odt"
    result = DeidEngine(country="ES").deidentify(
        source, output=output, policy=Policy.strict(require_ner=False)
    )
    assert result.status == "BLOCKED"
    assert "uninspected_odf_binary_metadata" in result.issues
    assert result.output_path is None
    assert not output.exists()


@pytest.mark.parametrize("failure", ("crc", "deflate", "unsupported_compression"))
def test_corrupt_zip_input_returns_blocked_without_emitting_output(tmp_path, failure):
    source = package(tmp_path, "<text:p>Informe.</text:p>")
    if failure == "deflate":
        with zipfile.ZipFile(source) as archive:
            entries = [(info.filename, archive.read(info)) for info in archive.infolist()]
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in entries:
                archive.writestr(name, value)
    raw = bytearray(source.read_bytes())
    central = raw.index(b"PK\x01\x02")
    if failure == "crc":
        raw[central + 16] ^= 1
    elif failure == "unsupported_compression":
        raw[8:10] = (99).to_bytes(2, "little")
        raw[central + 10 : central + 12] = (99).to_bytes(2, "little")
    else:
        name_size = int.from_bytes(raw[26:28], "little")
        extra_size = int.from_bytes(raw[28:30], "little")
        raw[30 + name_size + extra_size] = 7  # invalid DEFLATE block type
    source.write_bytes(raw)
    output = tmp_path / "safe.odt"
    result = DeidEngine(country="ES").deidentify(
        source, output=output, policy=Policy.strict(require_ner=False)
    )
    assert result.status == "BLOCKED"
    assert result.issues == ["MALFORMED_INPUT"]
    assert result.output_path is None
    assert not output.exists()


def test_style_display_label_is_scanned_and_transformed_without_breaking_style_reference(tmp_path):
    source = package(
        tmp_path,
        '<text:p text:style-name="P1">Informe.</text:p>',
        styles=f'<style:style style:name="P1" style:family="paragraph" style:display-name={quoteattr(SECRET)}/>',
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        emitted = archive.read("content.xml").decode()
    assert SECRET not in emitted, result.status
    assert 'style:name="P1"' in emitted and 'text:style-name="P1"' in emitted
    assert 'style:display-name="[EMAIL]"' in emitted
    assert any(SECRET in fragment.text for fragment in read_document(source).fragments)


def test_unresolved_package_href_cannot_hide_sensitive_target(tmp_path):
    source = package(
        tmp_path, f"<text:p><text:a xlink:href={quoteattr(SECRET)}>abrir</text:a></text:p>"
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        emitted = archive.read("content.xml").decode()
    assert SECRET not in emitted, result.status
    assert "abrir" in emitted and "text:a" not in emitted
    graph = read_document(source)
    assert not graph.complete
    assert "unresolved_odf_package_reference" in graph.issues
    assert any(SECRET in fragment.text for fragment in graph.fragments)


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
def test_sensitive_unmodeled_structural_attribute_is_inspected_and_fails_closed(
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
    result = engine.deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.status == "BLOCKED"
    assert result.output_path is None
    assert not (tmp_path / "safe.odt").exists()


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
def test_unresolved_relative_or_encoded_link_is_unlinked_without_losing_text(tmp_path, href):
    source = package(
        tmp_path,
        f"<text:p><text:a xlink:href={quoteattr(href)}>abrir</text:a></text:p>",
        parts={"styles.xml": STYLES},
    )
    graph = read_document(source)
    assert not graph.complete
    assert "unresolved_odf_package_reference" in graph.issues
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        emitted = archive.read("content.xml").decode()
    assert "abrir" in emitted and "text:a" not in emitted
    assert href not in emitted


@pytest.mark.parametrize("href", ("./styles.xml", "st%79les.xml", "nested/../styles.xml"))
def test_real_package_target_preserves_unchanged_uri_spelling(tmp_path, href):
    source = package(
        tmp_path,
        f"<text:p><text:a xlink:href={quoteattr(href)}>abrir</text:a></text:p>",
        parts={"styles.xml": STYLES},
    )
    graph = read_document(source)
    assert graph.complete, graph.issues
    assert "unresolved_odf_package_reference" not in graph.issues
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        emitted = archive.read("content.xml").decode()
    assert f"xlink:href={quoteattr(href)}" in emitted and "abrir" in emitted


def test_implicit_embedded_directory_and_owner_relative_target_are_resolved(tmp_path):
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
    engine = DeidEngine(country="ES")
    result = engine.deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        assert "Object 1/content.xml" not in archive.namelist()
        assert "draw:object" not in archive.read("content.xml").decode()
    kept = engine.deidentify(
        source,
        output=tmp_path / "kept.odt",
        office_media="keep",
        policy=Policy.strict(require_ner=False),
    )
    assert kept.status == "BLOCKED" and kept.output_path is None


def test_encoded_separator_is_not_used_as_a_package_membership_shortcut(tmp_path):
    href = "nested%2F..%2Fstyles.xml"
    source = package(
        tmp_path,
        f"<text:p><text:a xlink:href={quoteattr(href)}>abrir</text:a></text:p>",
        parts={"styles.xml": STYLES},
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        emitted = archive.read("content.xml").decode()
    assert "text:a" not in emitted and "abrir" in emitted


def test_manifest_metadata_cannot_hide_identifier_in_syntactically_valid_media_type(tmp_path):
    source = package(
        tmp_path,
        "<text:p>Informe.</text:p>",
        media_types={"content.xml": "application/12345678Z"},
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        emitted = archive.read("META-INF/manifest.xml").decode()
    assert "12345678Z" not in emitted, result.status
    assert 'manifest:media-type="text/xml"' in emitted
    assert any("12345678Z" in fragment.text for fragment in read_document(source).fragments)


@pytest.mark.parametrize("channel", ("standard_alias", "element_name", "empty_attribute_name"))
def test_sensitive_xml_qualified_name_is_inspected_and_blocks_without_rewriting_syntax(
    tmp_path, channel
):
    identifier = "12345678Z"
    if channel == "standard_alias":
        root_attributes = 'xmlns:dni-12345678Z="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        body = "<dni-12345678Z:p>Informe.</dni-12345678Z:p>"
    else:
        root_attributes = 'xmlns:private="urn:deidflow:fixture"'
        body = (
            "<private:dni-12345678Z>Informe.</private:dni-12345678Z>"
            if channel == "element_name"
            else '<text:p private:dni-12345678Z="">Informe.</text:p>'
        )
    source = package(tmp_path, body, root_attributes=root_attributes)
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.status == "BLOCKED", result.status
    assert result.output_path is None and not (tmp_path / "safe.odt").exists()
    assert any(identifier in fragment.text for fragment in read_document(source).fragments)


def test_neutral_names_do_not_collapse_existing_distinct_bookmarks(tmp_path):
    from xml.etree import ElementTree as ET

    source = package(
        tmp_path,
        '<text:p><text:bookmark text:name="nombre-1"/>'
        '<text:bookmark text:name="12345678Z"/>'
        '<text:a xlink:href="#nombre-1">primero</text:a>'
        '<text:a xlink:href="#12345678Z">segundo</text:a></text:p>',
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        document = ET.fromstring(archive.read("content.xml"))
    text_uri = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    bookmarks = document.findall(f".//{{{text_uri}}}bookmark")
    links = document.findall(f".//{{{text_uri}}}a")
    assert [node.attrib[f"{{{text_uri}}}name"] for node in bookmarks] == ["nombre-1", "nombre-2"]
    assert [node.attrib["{http://www.w3.org/1999/xlink}href"] for node in links] == [
        "#nombre-1",
        "#nombre-2",
    ]
    assert [node.text for node in links] == ["primero", "segundo"]


def test_excessive_xml_depth_fails_closed_without_raw_recursion_error_or_partial_file(tmp_path):
    source = package(
        tmp_path,
        "<text:p>" + "<text:span>" * 1100 + "Informe." + "</text:span>" * 1100 + "</text:p>",
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.status == "BLOCKED"
    assert result.output_path is None and not (tmp_path / "safe.odt").exists()
    assert result.issues == ["MALFORMED_INPUT"]


def test_normal_nested_text_remains_supported(tmp_path):
    source = package(
        tmp_path,
        "<text:p>" + "<text:span>" * 32 + "Informe." + "</text:span>" * 32 + "</text:p>",
    )
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "safe.odt", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    assert any(
        "Informe." in fragment.text for fragment in read_document(result.output_path).fragments
    )


def assert_uninspected_source_but_clean_rewrite(source: Path, tmp_path: Path):
    graph = read_document(source)
    assert not graph.complete
    engine = DeidEngine(country="ES")
    policy = Policy.strict(require_ner=False)
    assert engine.verify(source, policy=policy).status == "BLOCKED"
    result = engine.deidentify(source, output=tmp_path / "safe.odt", policy=policy)
    assert result.output_path is not None, result.issues
    assert read_document(result.output_path).complete
    assert engine.verify(result.output_path, policy=policy).status == "APPROVED"


@pytest.mark.parametrize("encoding", ("utf-8", "utf-16"))
@pytest.mark.parametrize("hidden", (f"<!--{SECRET}-->", f"<?audit {SECRET}?>"))
def test_xml_comments_and_processing_instructions_are_uninspected_until_removed(
    tmp_path, encoding, hidden
):
    content = (
        f'<office:document-content {NS} office:version="1.3">'
        f"<office:body><office:text><text:p>Informe.</text:p>{hidden}"
        "</office:text></office:body></office:document-content>"
    ).encode(encoding)
    source = package(tmp_path, "", parts={"content.xml": content})
    assert_uninspected_source_but_clean_rewrite(source, tmp_path)


@pytest.mark.parametrize(
    "name", ("Configurations2/accelerator/current.xml", "layout-cache", "ordinary/")
)
def test_nonempty_opaque_package_channel_is_uninspected_until_removed(tmp_path, name):
    source = package(tmp_path, "<text:p>Informe.</text:p>", parts={name: b"\xff" + SECRET.encode()})
    assert_uninspected_source_but_clean_rewrite(source, tmp_path)


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
def test_opaque_zip_metadata_is_uninspected_until_rebuilt(tmp_path, channel):
    source = package(tmp_path, "<text:p>Informe.</text:p>")
    add_zip_metadata(source, channel)
    assert_uninspected_source_but_clean_rewrite(source, tmp_path)


@pytest.mark.parametrize("member", ("content.xml", "META-INF/manifest.xml"))
def test_terminal_deflate_suffix_is_uninspected_until_recompressed(tmp_path, member):
    source = package(tmp_path, "<text:p>Informe.</text:p>")
    append_deflate_tail(source, member, SECRET.encode())
    assert_uninspected_source_but_clean_rewrite(source, tmp_path)
