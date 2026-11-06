import zipfile
from pathlib import Path

from opendocument_samples import manifest, write_package

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
    resources["META-INF/manifest.xml"] = manifest(MEDIA, entries)
    return write_package(tmp_path / "source.odt", MEDIA, resources)


STYLES = (
    f'<office:document-styles {NS} office:version="1.3"><office:styles/></office:document-styles>'
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


STRUCTURAL_ATTRIBUTES = (
    "style:patient-note",
    "style:name",
    "svg:font-family",
    "text:style-name",
    "xmlns:private",
)


UNRESOLVED_LINKS = (
    "synthetic.patient%40example.test",
    "./synthetic.patient%40example.test",
    "nested/../synthetic.patient@example.test",
    "../styles.xml",
    "missing.xml",
    "styles.xml?contact=synthetic.patient%40example.test",
    "styles.xml#synthetic.patient%40example.test",
)


QUALIFIED_NAME_CASES = {
    "standard_alias": (
        'xmlns:dni-12345678Z="urn:oasis:names:tc:opendocument:xmlns:text:1.0"',
        "<dni-12345678Z:p>Informe.</dni-12345678Z:p>",
    ),
    "element_name": (
        'xmlns:private="urn:deidflow:fixture"',
        "<private:dni-12345678Z>Informe.</private:dni-12345678Z>",
    ),
    "empty_attribute_name": (
        'xmlns:private="urn:deidflow:fixture"',
        '<text:p private:dni-12345678Z="">Informe.</text:p>',
    ),
}


EMBEDDED_RELATIVE_XML = f'<office:document-content {NS} office:version="1.3"><office:body><office:text><text:p><text:a xlink:href="../styles.xml">detalle</text:a></text:p></office:text></office:body></office:document-content>'


AUXILIARY_SENSITIVE_SETTINGS_XML = f'<office:document-settings {NS} xmlns:dni-12345678Z="urn:oasis:names:tc:opendocument:xmlns:config:1.0"><office:settings><dni-12345678Z:config-item-set/></office:settings></office:document-settings>'
