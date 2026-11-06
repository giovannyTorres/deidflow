import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest

from deidflow import DeidEngine, Policy
from deidflow.readers import read_document

SECRET = "synthetic.patient@example.test"
NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"'
    ' xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"'
)
MEDIA = "application/vnd.oasis.opendocument.text"


def package(
    tmp_path: Path,
    body: str,
    *,
    styles: str = "",
    root_attributes: str = "",
    parts: dict[str, str | bytes] | None = None,
    media_types: dict[str, str] | None = None,
) -> Path:
    content = (
        f'<office:document-content {NS} office:version="1.3" {root_attributes}>'
        f"<office:automatic-styles>{styles}</office:automatic-styles>"
        f"<office:body><office:text>{body}</office:text></office:body>"
        "</office:document-content>"
    )
    resources = {"content.xml": content, **(parts or {})}
    entries = {name: "text/xml" for name in resources} | (media_types or {})
    manifest = (
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        f'<manifest:file-entry manifest:full-path="/" manifest:media-type="{MEDIA}"/>'
        + "".join(
            f"<manifest:file-entry manifest:full-path={quoteattr(name)} manifest:media-type={quoteattr(kind)}/>"
            for name, kind in entries.items()
        )
        + "</manifest:manifest>"
    )
    source = tmp_path / "source.odt"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("mimetype", MEDIA)
        for name, value in resources.items():
            archive.writestr(name, value)
        archive.writestr("META-INF/manifest.xml", manifest)
    return source


STYLES = (
    f'<office:document-styles {NS} office:version="1.3"><office:styles/></office:document-styles>'
)


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


@pytest.mark.parametrize(
    "name", ("Configurations2/accelerator/current.xml", "layout-cache", "ordinary/")
)
def test_nonempty_opaque_package_channel_is_uninspected_until_removed(tmp_path, name):
    source = package(tmp_path, "<text:p>Informe.</text:p>", parts={name: b"\xff" + SECRET.encode()})
    assert_uninspected_source_but_clean_rewrite(source, tmp_path)


def test_empty_directory_entry_is_benign(tmp_path):
    source = package(tmp_path, "<text:p>Informe.</text:p>", parts={"ordinary/": b""})
    assert read_document(source).complete
    assert (
        DeidEngine(country="ES").verify(source, policy=Policy.strict(require_ner=False)).status
        == "APPROVED"
    )


def add_zip_metadata(source: Path, channel: str) -> None:
    import struct

    with zipfile.ZipFile(source) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    payload = SECRET.encode()
    if channel in {"prefix", "suffix"}:
        raw = source.read_bytes()
        source.write_bytes(payload + raw if channel == "prefix" else raw + payload)
        return
    with zipfile.ZipFile(source, "w") as archive:
        for info, value in entries:
            if info.filename == "content.xml":
                if channel == "member_comment":
                    info.comment = payload
                elif channel in {"member_extra", "local_extra_only"}:
                    info.extra = struct.pack("<HH", 0xBEEF, len(payload)) + payload
            archive.writestr(info, value)
            if channel == "local_extra_only" and info.filename == "content.xml":
                info.extra = b""  # local header written; central directory written at close
        if channel == "archive_comment":
            archive.comment = payload
        if channel == "local_name_mismatch":
            info = zipfile.ZipInfo("dni-12345678Z/")
            archive.writestr(info, b"")
            info.filename = "ordinary/"
            info.orig_filename = "ordinary/"
    if channel == "local_extra_only":
        with zipfile.ZipFile(source) as archive:
            assert archive.getinfo("content.xml").extra == b""
            assert b"Informe." in archive.read("content.xml")


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


def append_deflate_tail(source: Path, member: str, payload: bytes) -> None:
    import struct

    with zipfile.ZipFile(source) as archive:
        entries = {info.filename: archive.read(info) for info in archive.infolist()}
    with zipfile.ZipFile(source, "w") as archive:
        for name, value in entries.items():
            if name != member:
                archive.writestr(name, value, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(member, entries[member], compress_type=zipfile.ZIP_DEFLATED)
        info = archive.getinfo(member)
        handle = archive.fp
        assert handle is not None
        handle.write(payload)
        info.compress_size += len(payload)
        archive.start_dir = handle.tell()
        handle.seek(info.header_offset + 18)
        handle.write(struct.pack("<I", info.compress_size))
        handle.seek(archive.start_dir)
    with zipfile.ZipFile(source) as archive:
        assert archive.read(member) == entries[member]  # standard reader discards suffix


@pytest.mark.parametrize("member", ("content.xml", "META-INF/manifest.xml"))
def test_terminal_deflate_suffix_is_uninspected_until_recompressed(tmp_path, member):
    source = package(tmp_path, "<text:p>Informe.</text:p>")
    append_deflate_tail(source, member, SECRET.encode())
    assert_uninspected_source_but_clean_rewrite(source, tmp_path)


def test_deflate_validation_does_not_expand_beyond_the_declared_size(tmp_path):
    import struct
    import tracemalloc

    source = package(tmp_path, "<text:p>Informe.</text:p>")
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
