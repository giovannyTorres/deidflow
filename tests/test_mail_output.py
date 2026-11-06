from __future__ import annotations

import email
import email.policy
import re
from email.message import EmailMessage
from pathlib import Path

from deidflow import DeidEngine, Policy
from deidflow.mail import split_addresses
from deidflow.readers import read_document

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def make_message(path: Path) -> Path:
    forwarded = EmailMessage()
    forwarded["From"] = "Pedro Ruiz Soto <pedro.ruiz@example.org>"
    forwarded["To"] = "maria.lopez@example.com"
    forwarded["Subject"] = "Mi DNI es 87654321X"
    forwarded.set_content("Hola, mi teléfono es +34 699 112 233.\n")

    message = EmailMessage()
    message["Received"] = "from mail.example.com (mail.example.com [203.0.113.7]) by mx"
    message["X-Originating-IP"] = "[198.51.100.23]"
    message["DKIM-Signature"] = "v=1; a=rsa-sha256; d=example.com; s=sel; b=abc123"
    message["From"] = "María López García <maria.lopez@example.com>"
    message["To"] = '"Ramón Ortega" <ramon.ortega@example.net>, lucia.f@example.net'
    message["Cc"] = "=?utf-8?q?Luc=C3=ADa_Fern=C3=A1ndez?= <lucia.fernandez@example.net>"
    message["Subject"] = "Resultados. Paciente: María López García, DNI 12345678Z"
    message["Date"] = "Tue, 05 Mar 2024 10:15:00 +0100"
    message["Message-ID"] = "<CA+abc123@mail.example.com>"
    message["In-Reply-To"] = "<orig-1@mail.example.com>"
    message["References"] = "<root-0@mail.example.com> <orig-1@mail.example.com>"
    message.set_content("Nombre: María López García\nTeléfono: 612 34 56 78\n")
    message.add_alternative(
        "<p>Nombre: <b>María</b> López García</p><!-- DNI 12345678Z -->", subtype="html"
    )
    message.add_attachment(
        "Paciente: María López García\nDNI: 12345678Z\n".encode(),
        maintype="text",
        subtype="plain",
        filename="informe_maria_lopez.txt",
    )
    message.add_attachment(PNG, maintype="image", subtype="png", filename="foto_dni.png")
    message.add_attachment(
        b"PK\x05\x06" + bytes(18), maintype="application", subtype="zip", filename="datos.zip"
    )
    message.add_attachment(forwarded)
    message.get_payload()[-1].set_param(
        "filename", "Fwd Pedro Ruiz.eml", header="content-disposition"
    )
    path.write_bytes(message.as_bytes(policy=email.policy.default))
    return path


SECRETS = (
    "María",
    "López",
    "maria.lopez@example.com",
    "Ramón",
    "ramon.ortega@example.net",
    "lucia",
    "Lucía",
    "Luc=C3=ADa",
    "12345678Z",
    "612 34 56 78",
    "203.0.113.7",
    "198.51.100.23",
    "mail.example.com",
    "informe_maria_lopez",
    "foto_dni",
    "Pedro Ruiz",
    "pedro.ruiz@example.org",
    "87654321X",
    "699 112 233",
    "05 Mar",  # Date header
    "10:15:00",
)


def test_address_parsing_is_linear_on_adversarial_headers():
    import time

    for value in ("a" + " " * 200000 + "b", '"' * 200000, "<" * 200000, "a," * 100000):
        start = time.perf_counter()
        split_addresses(value)
        assert time.perf_counter() - start < 2, value[:10]


def test_split_addresses_handles_quotes_groups_and_placeholders():
    assert split_addresses('"Ruiz, Ana" <ana@example.com>, b@example.com') == [
        ("Ruiz, Ana", "ana@example.com"),
        ("", "b@example.com"),
    ]
    assert split_addresses('"[PERSON]" <[EMAIL]>') == [("[PERSON]", "[EMAIL]")]
    assert split_addresses("  Ana Ruiz   <ana@example.com>  ") == [("Ana Ruiz", "ana@example.com")]


def test_eml_output_removes_identity_from_headers_bodies_and_attachments(tmp_path):
    source = make_message(tmp_path / "mensaje.eml")
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.eml", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    raw = result.output_path.read_bytes()
    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    from deidflow.mail import header_text

    headers = "\n".join(header_text(v) for part in parsed.walk() for v in part.values())
    decoded = (
        headers
        + raw.decode("utf-8", "replace")
        + "\n".join(
            part.get_content() if part.get_content_maintype() == "text" else ""
            for part in parsed.walk()
            if not part.is_multipart() and part.get_content_type() != "message/rfc822"
        )
    )
    for inner in parsed.walk():
        if inner.get_content_type() == "message/rfc822":
            for nested in inner.get_payload():
                decoded += nested.as_string() + nested.get_body().get_content()
    for secret in SECRETS:
        assert secret not in decoded, secret
    names = {key.lower() for key in parsed.keys()}
    assert not names & {"received", "x-originating-ip", "dkim-signature", "date"}
    assert parsed["From"] and "[PERSON]" in decoded and "[EMAIL]" in decoded
    pseudonym = r"<df([0-9a-f]{24})@deidflow>"
    reply = re.findall(pseudonym, str(parsed["In-Reply-To"]))
    references = re.findall(pseudonym, str(parsed["References"]))
    assert reply and references[-1] == reply[0]  # replies still thread
    pseudonyms = re.findall(pseudonym, str(parsed["Message-ID"])) + references
    assert len(set(pseudonyms)) == 3
    filenames = [p.get_filename() for p in parsed.walk() if p.get_filename()]
    assert filenames == ["adjunto-1.txt"]  # image and zip removed, text attachment renamed
    text_attachment = next(p for p in parsed.iter_attachments() if p.get_filename())
    assert text_attachment.get_content() == "Paciente: [PERSON]\nDNI: [NATIONAL_ID]\n"
    assert "From: " in raw.decode() and "Subject: " in raw.decode()  # header spelling kept
    removed = result.audit["email_removed"]
    assert removed["media"] == 1 and removed["unsupported_attachments"] == 1
    assert result.status == "REVIEW_REQUIRED"
    assert "EMAIL_ATTACHMENT_REMOVED" in result.issues
    graph = read_document(result.output_path)
    assert graph.complete, graph.issues


def test_eml_reader_extracts_encoded_headers_and_attachments(tmp_path):
    graph = read_document(make_message(tmp_path / "mensaje.eml"))
    text = "\n".join(f.text for f in graph.fragments)
    assert "Lucía Fernández" in text  # RFC 2047 encoded word decoded
    assert "DNI: 12345678Z" in text  # text attachment content
    assert "87654321X" in text  # forwarded message
    assert not graph.complete
    assert {"email_media_requires_review", "email_attachment_not_extracted"} <= set(graph.issues)


def test_docx_attachment_is_rewritten(tmp_path):
    from test_office_output import make_docx

    message = EmailMessage()
    message["From"] = "ana@example.com"
    message["Subject"] = "Informe"
    message.set_content("Adjunto informe.\n")
    message.add_attachment(
        make_docx(tmp_path / "informe.docx").read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="Informe Maria Lopez.docx",
    )
    source = tmp_path / "con-docx.eml"
    source.write_bytes(message.as_bytes(policy=email.policy.default))
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.eml", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    parsed = email.message_from_bytes(result.output_path.read_bytes(), policy=email.policy.default)
    attachment = next(p for p in parsed.iter_attachments())
    assert attachment.get_filename() == "adjunto-1.docx"
    assert b"12345678Z" not in attachment.get_content()


def test_preamble_epilogue_and_structure_parameters_are_not_kept(tmp_path):
    message = EmailMessage()
    message["From"] = "ana@example.com"
    message["Subject"] = "Informe"
    message.set_content("Hola.\n")
    message.add_alternative("<p>Hola.</p>", subtype="html")
    message.preamble = "Contacto alice@example.com"
    message.epilogue = "Contacto bob@example.com"
    message.set_param("private", "carol@example.com")
    del message["MIME-Version"]
    message["MIME-Version"] = "1.0 (dave@example.com)"
    source = tmp_path / "estructura.eml"
    source.write_bytes(message.as_bytes(policy=email.policy.default))
    graph = read_document(source)
    scanned = "\n".join(f.text for f in graph.fragments)
    assert all(v in scanned for v in ("alice@", "bob@", "carol@", "dave@"))
    result = DeidEngine(country="ES").deidentify(
        source, output=tmp_path / "out.eml", policy=Policy.strict(require_ner=False)
    )
    assert result.output_path is not None, result.issues
    raw = result.output_path.read_bytes().decode()
    for value in ("alice@", "bob@", "carol@", "dave@", "private="):
        assert value not in raw, value


def test_indexed_placeholders_are_shared_with_attachments(tmp_path):
    from deidflow.policies import Rule

    message = EmailMessage()
    message["From"] = "remitente@example.com"
    message["Subject"] = "Contactos"
    message.set_content("Contacto alice@example.com\n")
    message.add_attachment(
        b"Contacto bob@example.com\n", maintype="text", subtype="plain", filename="c.txt"
    )
    source = tmp_path / "indices.eml"
    source.write_bytes(message.as_bytes(policy=email.policy.default))
    policy = Policy(default=Rule("indexed"), require_ner=False)
    result = DeidEngine(country="ES").deidentify(source, output=tmp_path / "out.eml", policy=policy)
    assert result.output_path is not None, result.issues
    parsed = email.message_from_bytes(result.output_path.read_bytes(), policy=email.policy.default)
    body = parsed.get_body(preferencelist=("plain",)).get_content()
    attached = next(parsed.iter_attachments()).get_content()
    sender = re.search(r"^From: (.*)$", result.output_path.read_text(), re.MULTILINE)
    assert sender is not None
    tokens = set(re.findall(r"\[[A-Z_]+_\d+\]", body + attached + sender.group(1)))
    assert len(tokens) == 3, (body, attached, sender.group(1))  # three distinct people
