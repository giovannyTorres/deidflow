import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

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
