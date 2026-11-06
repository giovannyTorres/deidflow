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
    parts: dict[str, str] | None = None,
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
