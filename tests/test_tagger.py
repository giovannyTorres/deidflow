from __future__ import annotations

import gzip
import json
import math
import random

import pytest

from deidflow import DeidEngine, Policy
from deidflow.benchmarks.datasets import Example, GoldSpan
from deidflow.nlp.tagger import (
    BUILTIN_MODELS,
    SpanTagger,
    allowed_transition,
    bio_tags,
    token_features,
    tokenize,
)

np = pytest.importorskip("numpy")

from deidflow.training.tagger import fit_platt, train_span_tagger  # noqa: E402

FIRST = ["Ana", "Luis", "Marta", "Jorge", "Elena", "Raúl", "Sofía", "Pedro", "Lucía", "Iván"]
LAST = ["Ruiz", "Gómez", "Soto", "Vega", "Mora", "Paz", "Lara", "Cano", "Ríos", "León"]
CITY = ["Puebla", "Toluca", "Mérida", "Oaxaca", "León", "Morelia", "Durango", "Colima"]


SYLLABLES = ["ba", "ce", "di", "lo", "mu", "ra", "se", "ti", "vo", "ña", "ga", "re", "mon"]


def _word(rng: random.Random) -> str:
    return "".join(rng.choice(SYLLABLES) for _ in range(rng.randrange(2, 4))).capitalize()


def _document(rng: random.Random, index: int, split: str) -> Example:
    # Pseudo-words keep word identity from being enough; the model must learn context.
    name = " ".join(_word(rng) for _ in range(rng.randrange(2, 4)))
    city = rng.choice(CITY)
    record = str(rng.randrange(100000, 999999))
    pieces: list[tuple[str, str | None]] = [
        ("Datos del paciente.\nNombre: ", None),
        (name, "PERSON"),
        (".\nNHC: ", None),
        (record, "PATIENT_ID"),
        (".\nLocalidad: ", None),
        (city, "LOCATION"),
        (".\nInforme: paciente con dolor abdominal y fiebre de tres días.\n", None),
    ]
    text = ""
    spans = []
    for piece, kind in pieces:
        if kind:
            spans.append(GoldSpan(kind, len(text), len(text) + len(piece)))
        text += piece
    return Example(f"{split}-{index}", text, tuple(spans), split, f"synthetic-{split}")


@pytest.fixture(scope="module")
def toy_model() -> dict:
    rng = random.Random(7)
    train = [_document(rng, i, "train") for i in range(120)]
    validation = [_document(rng, i, "validation") for i in range(30)]
    model, report = train_span_tagger(train, validation, epochs=6, patience=2, seed=3)
    assert report["selected_validation_exact_f1"] > 0.95
    return model


def test_tokenizer_offsets_and_bio_alignment():
    text = "Nombre: María Luna, NHC 1234."
    tokens = tokenize(text)
    assert [text[s:e] for s, e in tokens][:4] == ["Nombre", ":", "María", "Luna"]
    tags, skipped = bio_tags(tokens, [("PERSON", 8, 18), ("PATIENT_ID", 24, 26)])
    assert tags[2:4] == ["B-PERSON", "I-PERSON"] and skipped == 1


def test_bio_constraint_and_line_label_features():
    assert not allowed_transition("O", "I-PERSON")
    assert allowed_transition("B-PERSON", "I-PERSON") and allowed_transition("I-DATE", "O")
    text = "Edad: 70 Sexo: H\nMédico: Ana"
    features = token_features(text, tokenize(text))
    assert "lab1|sc=sexo|0" in features[5]  # "H" follows the inline "Sexo:" label
    assert "bol" in features[6] and "nolab" in features[6]


def test_training_is_deterministic_and_generalizes(toy_model):
    rng = random.Random(7)
    train = [_document(rng, i, "train") for i in range(120)]
    validation = [_document(rng, i, "validation") for i in range(30)]
    again, _ = train_span_tagger(train, validation, epochs=6, patience=2, seed=3)
    assert json.dumps(again, sort_keys=True) == json.dumps(toy_model, sort_keys=True)
    tagger = SpanTagger(toy_model)
    unseen = "Datos del paciente.\nNombre: Beatriz Olmedo Fuentes.\nNHC: 482913.\n"
    found = {(f.entity_type, unseen[f.start : f.end]) for f in tagger.detect(unseen)}
    assert ("PATIENT_ID", "482913") in found
    assert any(kind == "PERSON" and "Olmedo" in value for kind, value in found)


def test_training_refuses_test_split_examples():
    example = Example("x", "Nombre: Ana Ruiz", (GoldSpan("PERSON", 8, 16),), "test", "t")
    with pytest.raises(ValueError, match="Test"):
        train_span_tagger([example], [example])


def test_model_file_has_no_plaintext_features(toy_model):
    serialized = json.dumps(toy_model)
    for value in ("Ruiz", "ruiz", "w=ruiz", "nombre", "Puebla"):
        assert value not in serialized
    assert toy_model["metadata"]["feature_hashing"].startswith("keyed BLAKE2b")


def test_numpy_and_pure_python_decoders_agree(toy_model):
    fast = SpanTagger(toy_model, accelerate=True)
    slow = SpanTagger(toy_model, accelerate=False)
    assert fast.accelerated and not slow.accelerated
    rng = random.Random(11)
    words = FIRST + LAST + CITY + ["Nombre", ":", "NHC", "\n", "123456", "dolor", "."]
    for _ in range(40):
        text = " ".join(rng.choice(words) for _ in range(rng.randrange(1, 60)))
        a, b = fast.predict(text), slow.predict(text)
        assert [(s.entity_type, s.start, s.end) for s in a] == [
            (s.entity_type, s.start, s.end) for s in b
        ]
        assert all(
            math.isclose(x.margin, y.margin, abs_tol=1e-6) for x, y in zip(a, b, strict=True)
        )


def test_long_text_is_segmented_without_losing_offsets(toy_model):
    tagger = SpanTagger(toy_model, max_segment_tokens=64)
    block = "Datos del paciente.\nNombre: Ana Ruiz Soto.\nNHC: 123456.\n"
    text = block * 40
    findings = [f for f in tagger.detect(text) if f.entity_type == "PATIENT_ID"]
    assert len(findings) == 40
    assert all(text[f.start : f.end] == "123456" for f in findings)


def test_calibrated_scores_and_engine_integration(toy_model):
    assert toy_model["calibration"] is None or toy_model["calibration"]["method"] == "platt"
    model = dict(
        toy_model, calibration={"method": "platt", "feature": "log1p_margin", "a": 1.0, "b": 0.0}
    )
    tagger = SpanTagger(model)
    text = "Datos del paciente.\nNombre: Beatriz Olmedo Fuentes.\nNHC: 482913.\n"
    findings = tagger.detect(text)
    assert findings and all(f.confidence == f.score for f in findings)
    engine = DeidEngine(nlp=tagger)
    result = engine.deidentify_text(text, policy=Policy.strict())
    assert "482913" not in result.output_text
    assert "SEMANTIC_MODEL_REQUIRED" not in result.issues


def test_near_miss_candidates_require_review(toy_model):
    tagger = SpanTagger(toy_model, review_margin=1e5)
    findings = tagger.detect("Datos del paciente.\nNombre: Ana Ruiz.\n")
    candidates = [f for f in findings if "near_miss" in f.context]
    assert candidates and all(f.score == 0.5 for f in candidates)
    assert all(f.validation == "statistical_candidate" for f in candidates)


def test_label_mapping_filters_and_renames(toy_model):
    tagger = SpanTagger(toy_model, labels={"PATIENT_ID": "INTERNAL_ID"})
    findings = tagger.detect("Nombre: Ana Ruiz.\nNHC: 123456.\n")
    assert findings and {f.entity_type for f in findings} == {"INTERNAL_ID"}


def test_model_loading_is_strict(tmp_path, toy_model):
    payload = json.dumps(toy_model).encode()
    path = tmp_path / "model.json.gz"
    path.write_bytes(gzip.compress(payload, mtime=0))
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert SpanTagger.load(path, sha256=digest).tags == tuple(toy_model["labels"])
    with pytest.raises(ValueError, match="SHA-256"):
        SpanTagger.load(path, sha256="0" * 64)
    with pytest.raises(ValueError, match="JSON"):
        SpanTagger.from_bytes(b"\x80\x04\x95 pickle")
    with pytest.raises(ValueError, match="Non-finite|non-finite"):
        SpanTagger.from_bytes(payload.replace(b'"start": [', b'"start": [NaN, ', 1))
    for broken in (
        dict(toy_model, format="other"),
        dict(toy_model, feature_set="other"),
        dict(toy_model, labels=["B-X", "O"]),
        dict(toy_model, weights={"not-a-digest": [[0, 1.0]]}),
        dict(toy_model, weights={"0123456789abcdef": [[999, 1.0]]}),
        dict(toy_model, calibration={"method": "isotonic"}),
        dict(toy_model, transitions=[[0.0]]),
    ):
        with pytest.raises(ValueError):
            SpanTagger(broken)


def test_platt_fit_is_finite_on_separable_data():
    a, b = fit_platt([0.0, 0.5, 4.0, 5.0, 6.0], [0, 0, 1, 1, 1])
    assert math.isfinite(a) and math.isfinite(b) and a > 0
    low = 1 / (1 + math.exp(-(a * 0.0 + b)))
    high = 1 / (1 + math.exp(-(a * 6.0 + b)))
    assert low < 0.5 < high < 1


@pytest.mark.parametrize(
    ("name", "text", "expected", "license_"),
    [
        (
            "es-clinical",
            "Datos del paciente.\nNombre: Ernesto.\nApellidos: Rivera Bueno.\nNHC: 368503.\n",
            ("PATIENT_ID", "368503"),
            "CC-BY-4.0",
        ),
        (
            "es-finance",
            "Estimado Sr. Carlos Méndez, le escribimos de Banco Ejemplo S.A. sobre su préstamo.",
            ("ORGANIZATION", "Banco Ejemplo S.A."),
            "Apache-2.0",
        ),
    ],
)
def test_builtin_models_load_with_pinned_digest(name, text, expected, license_):
    assert name in BUILTIN_MODELS
    tagger = SpanTagger.builtin(name)
    found = {(f.entity_type, text[f.start : f.end]) for f in tagger.detect(text)}
    assert expected in found
    assert tagger.metadata["training_data"]["license"] == license_
    assert tagger.model_version == BUILTIN_MODELS[name][0].removesuffix(".json.gz")


def test_unknown_builtin_model_is_rejected():
    with pytest.raises(ValueError, match="Unknown built-in"):
        SpanTagger.builtin("missing-model")


def test_cli_uses_builtin_or_pinned_tagger(tmp_path, capsys, toy_model):
    from deidflow.cli import main

    source = tmp_path / "note.txt"
    source.write_text("Datos del paciente.\nNombre: Ernesto Rivera Bueno.\nNHC: 368503.\n", "utf-8")
    assert main(["scan", str(source), "--tagger", "builtin:es-clinical"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["by_type"].get("PATIENT_ID") == 1 and "368503" not in json.dumps(report)
    model = tmp_path / "toy.json"
    model.write_text(json.dumps(toy_model), "utf-8")
    assert main(["scan", str(source), "--tagger", str(model), "--tagger-sha256", "0" * 64]) == 3
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "BLOCKED" and error["error_type"] == "ValueError"
    output = tmp_path / "out.txt"
    code = main(
        ["deidentify", str(source), "--output", str(output), "--tagger", "builtin:es-clinical"]
    )
    assert code in {0, 2} and "368503" not in output.read_text("utf-8")


def test_combined_adapters_fuse_findings(toy_model):
    from deidflow.nlp import CombinedNER

    first, second = (
        SpanTagger(toy_model),
        SpanTagger(toy_model, labels={"PATIENT_ID": "INTERNAL_ID"}),
    )
    text = "Nombre: Ana Ruiz.\nNHC: 123456.\n"
    combined = CombinedNER(first, second).detect(text)
    kinds = {f.entity_type for f in combined if text[f.start : f.end] == "123456"}
    assert kinds == {"PATIENT_ID", "INTERNAL_ID"}
    with pytest.raises(ValueError):
        CombinedNER()


@pytest.mark.parametrize(
    ("text", "start", "end", "expected"),
    [
        ("Domicilio: [ADDRESS]", 11, 20, True),
        ("Nombre: [PERSON].", 8, 15, True),  # partial token from a statistical rescan
        ("x [LOCATION] [LOCATION].", 3, 22, True),
        ("████ ████", 0, 9, True),
        ("Dr. [PERSON]", 0, 12, False),  # letters outside the placeholder remain
        ("****1234", 0, 8, False),  # partial masks keep source digits
        ("[DF_PERSON_ABCD2345] y Ana", 0, 26, False),
        ("Ana", 0, 3, False),
        ("RFC: [GODE561231GR8]", 5, 20, False),  # bracketed source values stay sensitive
        ("Nombre: [JUAN].", 8, 14, False),
        ("[DF_PERSON_562TAESGXPVTGFSOY2I7LPXCPG263BY3]", 0, 44, True),
    ],
)
def test_replacement_only_spans(text, start, end, expected):
    from deidflow.transformations import replacement_only

    assert replacement_only(text, start, end) is expected


def test_builtin_tagger_release_gate_end_to_end():
    engine = DeidEngine(nlp=SpanTagger.builtin("es-clinical"))
    text = "Datos del paciente.\nNombre: Ernesto Rivera Bueno.\nNHC: 368503.\nDomicilio: Calle Mayor 5.\n"
    result = engine.deidentify_text(text)
    assert result.status == "APPROVED", result.issues
    for value in ("Ernesto", "Rivera", "368503", "Calle Mayor"):
        assert value not in result.output_text
    assert result.audit["replacement_only_rescan_findings"] >= 1
    # A rescan finding that still covers source letters keeps blocking release.
    leaky = engine._gate(
        policy=Policy.strict(),
        residual=[
            f for f in engine.scan_text("Nombre: Ernesto Rivera.") if f.entity_type == "PERSON"
        ],
    )
    assert leaky.status == "BLOCKED"


def test_bracketed_source_values_are_not_exempted(tmp_path):
    from deidflow.transformations import replacement_only

    source = tmp_path / "rfc.txt"
    source.write_text("RFC: [GODE561231GR8]\n", "utf-8")
    assert DeidEngine().verify(source, policy=Policy.strict(require_ner=False)).status == "BLOCKED"
    tagger = SpanTagger.builtin("es-clinical")
    assert [f.entity_type for f in tagger.detect("Nombre: [JUAN].")] == ["PERSON"]
    # With transformation ranges, only the exact applied output counts.
    assert replacement_only("[MY_TYPE] y [JUAN]", 0, 9, ranges=[(0, 9)])
    assert not replacement_only("[MY_TYPE] y [JUAN]", 12, 18, ranges=[(0, 9)])
