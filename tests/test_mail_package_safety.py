from __future__ import annotations

import email.policy
import hashlib
import hmac
import json
from email.message import EmailMessage

import pytest

from deidflow import DeidEngine, Policy
from deidflow.mail import parse, rewrite_message
from deidflow.nlp import SpanTagger
from deidflow.policies import Rule
from deidflow.readers import read_document

CANARY = b"synthetic.leak@example.test"


@pytest.fixture(scope="module")
def engine():
    return DeidEngine(nlp=SpanTagger.builtin("es-clinical"))


def _deidentify(tmp_path, engine, source, **kwargs):
    path = tmp_path / "source.eml"
    path.write_bytes(source)
    return engine.deidentify(path, output=tmp_path / "out.eml", policy=Policy.strict(), **kwargs)


def test_opaque_multipart_subtype_is_rebuilt(tmp_path, engine):
    source = (
        b'Content-Type: multipart/private@example.test; boundary="abc"\r\n\r\n'
        b"--abc\r\nContent-Type: text/plain\r\n\r\nHola.\r\n--abc--\r\n"
    )
    result = _deidentify(tmp_path, engine, source)
    assert result.output_path is not None, result.issues
    raw = result.output_path.read_bytes()
    assert b"private@example.test" not in raw
    assert parse(raw).get_content_type() == "multipart/mixed"
    assert "EMAIL_MULTIPART_NORMALIZED" in result.issues


def test_source_reader_exposes_opaque_header_names_types_and_boundaries(tmp_path):
    source = tmp_path / "source.eml"
    source.write_bytes(
        b'Content-Type: multipart/private@example.test; boundary="private-boundary@example.test"\r\n'
        b"X-private-header@example.test: ok\r\n\r\n"
        b"--private-boundary@example.test\r\nContent-Type: text/plain\r\n\r\nHola.\r\n"
        b"--private-boundary@example.test--\r\n"
    )
    graph = read_document(source)
    extracted = "\n".join(fragment.text for fragment in graph.fragments)
    assert "private@example.test" in extracted
    assert "private-boundary@example.test" in extracted
    assert "X-private-header@example.test" in extracted
    assert "EMAIL_REVIEW_REQUIRED" in graph.issues


def test_language_id_comments_and_related_type_do_not_survive(tmp_path, engine):
    message = EmailMessage()
    message["Message-ID"] = "<original@example.test> (synthetic.leak@example.test)"
    message["References"] = "<parent@example.test> synthetic.leak@example.test"
    message.set_content("Hola.\n")
    message.make_related()
    message.set_param("type", "application/private-person")
    message["Content-Language"] = "Juan-Perez"
    source = message.as_bytes(policy=email.policy.default)
    result = _deidentify(tmp_path, engine, source)
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert result.output_path is not None
    assert CANARY not in result.output_path.read_bytes()
    raw, _ = rewrite_message(
        source,
        rewrite=lambda text: (
            engine.deidentify_text(text, policy=Policy.strict()).output_text or "",
            [],
        ),
        whole=lambda value, kind: f"[{kind}]",
        attachment=lambda source, output: ("BLOCKED", []),
        rewrite_html=lambda text: (
            engine.deidentify_text(text, policy=Policy.strict()).output_text or ""
        ),
        key=b"k" * 32,
    )
    parsed = parse(raw)
    assert parsed.get("Content-Language") is None
    assert parsed.get_param("type") is None
    assert CANARY not in raw and b"Juan-Perez" not in raw
    assert b"original@example.test" not in raw and b"parent@example.test" not in raw


def test_sanitized_attachment_uses_canonical_mime_type(tmp_path, engine):
    message = EmailMessage()
    message.set_content("Hola.\n")
    message.add_attachment(
        b"Hola.\n", maintype="application", subtype="private@example.test", filename="note.txt"
    )
    result = _deidentify(tmp_path, engine, message.as_bytes(policy=email.policy.default))
    assert result.output_path is not None, result.issues
    raw = result.output_path.read_bytes()
    attachment = next(parse(raw).iter_attachments())
    assert attachment.get_content_type() == "text/plain"
    assert attachment.get_filename() == "adjunto-1.txt"
    assert b"private@example.test" not in raw


@pytest.mark.parametrize(
    "source",
    [
        b"Content-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: base64\n\nSG9sYQ== garbage private@example.test",
        b"Content-Type: text/plain\nContent-Transfer-Encoding: base64\n\n%%%",
        b"Content-Type: text/plain\nContent-Transfer-Encoding: quoted-printable\n\nHola=GG",
        b"Content-Type: text/plain\nContent-Transfer-Encoding: x-private\n\nprivate@example.test",
        b"Content-Type: text/plain; charset=does-not-exist\n\nHola",
        b"Content-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: 8bit\n\nHola\xff",
        b"Content-Type: message/rfc822\nContent-Transfer-Encoding: base64\n\nc3ludGhldGljQGV4YW1wbGUudGVzdA==",
        b"Content-Type: message/rfc822\n\nmalformed raw private@example.test",
        b'Content-Type: multipart/mixed; boundary="missing"\n\nprivate@example.test',
        b"Subject: =?bad-charset?b?c3ludGhldGljQGV4YW1wbGUudGVzdA==?=\n\nHola",
        b"Subject: =?utf-8?b?%%%?=\n\nHola",
        b"Subject: =?utf-8?q?private=GG?=\n\nHola",
    ],
)
def test_malformed_or_opaque_encoded_content_blocks(tmp_path, engine, source):
    result = _deidentify(tmp_path, engine, source)
    assert result.status == "BLOCKED"
    assert not result.release_approved and result.output_path is None
    assert not (tmp_path / "out.eml").exists()
    assert not list(tmp_path.glob(".deidflow-*"))


def test_unknown_media_type_is_removed_even_when_media_kept(tmp_path, engine):
    message = EmailMessage()
    message.set_content("Hola.\n")
    message.add_attachment(
        CANARY, maintype="image", subtype="private@example.test", filename="private.bin"
    )
    result = _deidentify(
        tmp_path, engine, message.as_bytes(policy=email.policy.default), office_media="keep"
    )
    assert result.output_path is not None, result.issues
    assert CANARY not in result.output_path.read_bytes()
    assert b"private@example.test" not in result.output_path.read_bytes()
    assert "EMAIL_ATTACHMENT_REMOVED" in result.issues


def _rewrite_without_callbacks(data: bytes, **limits):
    def forbidden(*args):
        pytest.fail("A transformation ran before MIME budget validation")

    return rewrite_message(
        data,
        rewrite=forbidden,
        whole=forbidden,
        attachment=forbidden,
        rewrite_html=forbidden,
        key=b"k" * 32,
        **limits,
    )


def test_part_budget_is_enforced_before_callbacks():
    message = EmailMessage()
    message.set_content("Hola.\n")
    for _ in range(6):
        message.add_attachment(b"data", maintype="text", subtype="plain", filename="a.txt")
    with pytest.raises(ValueError, match="structure limit"):
        _rewrite_without_callbacks(message.as_bytes(), max_parts=4)


def test_nesting_budget_is_enforced_by_parser_before_callbacks():
    data = b"Content-Type: text/plain\r\n\r\nHola."
    for _ in range(40):
        data = b"Content-Type: message/rfc822\r\n\r\n" + data
    with pytest.raises(ValueError, match="structure limit"):
        _rewrite_without_callbacks(data, max_depth=4)


def test_total_decoded_payload_budget_precedes_callbacks():
    message = EmailMessage()
    message.set_content("Hola.\n")
    for _ in range(3):
        message.add_attachment(b"a" * 80, maintype="text", subtype="plain", filename="a.txt")
    with pytest.raises(ValueError, match="decoded size limit"):
        _rewrite_without_callbacks(message.as_bytes(), max_decoded_bytes=150)


def test_raw_input_budget_precedes_parser_and_callbacks():
    with pytest.raises(ValueError, match="size limit"):
        _rewrite_without_callbacks(b"Subject: Hello\n\n" + b"a" * 100, max_bytes=50)


def test_header_expansion_budget_precedes_callbacks():
    source = b"References: " + b"<x> " * 20_000 + b"\r\n\r\nHola."
    with pytest.raises(ValueError, match="header limit"):
        _rewrite_without_callbacks(source)


def test_expanded_attachment_outputs_share_one_message_budget():
    message = EmailMessage()
    message.set_content("Hola.\n")
    for _ in range(3):
        message.add_attachment(b"small", maintype="text", subtype="plain", filename="a.txt")
    calls = []

    def expand_attachment(source, output):
        calls.append(source.name)
        output.write_bytes(b"a" * 1200)
        return "APPROVED", []

    with pytest.raises(ValueError, match="output size limit"):
        rewrite_message(
            message.as_bytes(),
            rewrite=lambda text: (text, []),
            whole=lambda value, kind: value,
            attachment=expand_attachment,
            rewrite_html=lambda text: text,
            key=b"k" * 32,
            max_bytes=2000,
        )
    assert len(calls) == 2  # stop before expanding the third attachment


def test_clinical_mail_ids_are_usable_only_with_invocation_provenance(tmp_path, engine):
    message = EmailMessage()
    message["Message-ID"] = "<original@example.test>"
    message["References"] = "<parent@example.test> <root@example.test>"
    message.set_content("Dosis: 5 mg cada 8 horas.\n")
    message.add_alternative("<p>Dosis: 5 mg cada 8 horas.</p>", subtype="html")
    message.get_payload()[0]["Content-ID"] = "<body@example.test>"
    result = _deidentify(tmp_path, engine, message.as_bytes())
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert result.output_path is not None
    output = parse(result.output_path.read_bytes())
    assert "5 mg cada 8 horas" in output.get_body(preferencelist=("plain",)).get_content()
    assert "original@example.test" not in result.output_path.read_text()
    assert not any("generated" in name for name in result.audit)
    assert "original@example.test" not in json.dumps(result.audit)
    # A standalone caller has no private writer report: it gets the ordinary
    # rescan, even for this genuine output and for the same engine instance.
    verified = engine.verify(result.output_path, policy=Policy.strict())
    assert verified.status == "BLOCKED"
    assert "RESIDUAL_FINDINGS" in verified.issues


@pytest.mark.parametrize("location", ["body", "subject", "comments"])
def test_minted_id_copied_into_content_is_not_exempt(tmp_path, location):
    key = b"synthetic-secret-key-32-bytes-long"
    original_id = "<original@example.test>"
    token = (
        "<df" + hmac.new(key, original_id.encode(), hashlib.sha256).hexdigest()[:24] + "@deidflow>"
    )
    engine = DeidEngine(nlp=SpanTagger.builtin("es-clinical"), key=key)
    message = EmailMessage()
    message["Message-ID"] = original_id
    message.set_content("Hola.\n" if location != "body" else "Contacto: private@example.test\n")
    if location != "body":
        message[location] = "Contacto: private@example.test"
    source, output = tmp_path / "source.eml", tmp_path / "out.eml"
    source.write_bytes(message.as_bytes())
    # Deliberately unsafe replacement reproduces a residual equal to a minted
    # header ID. Its body/Subject/Comments location must still block.
    policy = Policy(entities={"EMAIL": Rule("generalize", replacement=token)})
    result = engine.deidentify(source, output=output, policy=policy)
    assert result.status == "BLOCKED"
    assert "RESIDUAL_FINDINGS" in result.issues
    assert not output.exists()


def test_source_forged_generated_id_is_transformed_in_body(tmp_path):
    key = b"synthetic-secret-key-32-bytes-long"
    original_id = "<original@example.test>"
    token = (
        "<df" + hmac.new(key, original_id.encode(), hashlib.sha256).hexdigest()[:24] + "@deidflow>"
    )
    engine = DeidEngine(nlp=SpanTagger.builtin("es-clinical"), key=key)
    message = EmailMessage()
    message["Message-ID"] = original_id
    message.set_content(f"Contacto: {token}\n")
    result = _deidentify(tmp_path, engine, message.as_bytes())
    assert result.status == "REVIEW_REQUIRED", result.issues
    output = parse(result.output_path.read_bytes())
    assert str(output["Message-ID"]) == token
    assert token not in output.get_content()


def test_source_generated_looking_boundary_is_scanned_and_replaced(tmp_path, engine):
    boundary = "===============6123456789012345678=="
    message = EmailMessage()
    message.set_content("Hola.\n")
    message.make_mixed()
    message.set_boundary(boundary)
    source = tmp_path / "source.eml"
    source.write_bytes(message.as_bytes())
    graph = read_document(source)
    assert any(boundary in fragment.text for fragment in graph.fragments)
    result = _deidentify(tmp_path, engine, source.read_bytes())
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert boundary not in result.output_path.read_text()


def test_shared_key_keeps_message_thread_ids_stable(tmp_path):
    engine = DeidEngine(nlp=SpanTagger.builtin("es-clinical"), key=b"shared-test-key" * 3)
    identifiers = []
    for index in range(2):
        message = EmailMessage()
        message["Message-ID"] = "<thread@example.test>"
        message.set_content("Hola.\n")
        folder = tmp_path / str(index)
        folder.mkdir()
        result = _deidentify(folder, engine, message.as_bytes())
        assert result.status == "REVIEW_REQUIRED", result.issues
        identifiers.append(str(parse(result.output_path.read_bytes())["Message-ID"]))
    assert identifiers[0] == identifiers[1]
