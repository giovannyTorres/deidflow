from __future__ import annotations

import gzip
import json
import math

import pytest

from deidflow import DeidEngine, Policy
from deidflow.benchmarks.datasets import Example, GoldSpan
from deidflow.benchmarks.release_gate import (
    DIRECT_IDENTIFIERS,
    CachedTagger,
    release_gate_metrics,
    wilson_interval,
)
from deidflow.nlp.router import DEFAULT_MIN_EVIDENCE, DomainRouter, train_router
from deidflow.nlp.tagger import SpanTagger, builtin_profiles

CLINICAL = [
    f"Paciente de {n} años con dolor abdominal, fiebre y hematuria; se indica ecografía renal."
    for n in range(20, 60)
]
FINANCIAL = [
    f"Estimado cliente, su préstamo {n} y el estado de cuenta bancaria incluyen intereses y saldo."
    for n in range(20, 60)
]


class _Fixed:
    def __init__(self, label):
        self.label = label

    def detect(self, text):
        from deidflow.core import Finding

        return [Finding(self.label, 0, min(3, len(text)), 0.9, "fixed")] if text else []


def test_router_routes_by_domain_and_falls_back_to_both():
    model = train_router({"clinical": CLINICAL, "financial": FINANCIAL}, min_docs=2)
    payload = json.dumps(model)
    assert "fiebre" not in payload and "préstamo" not in payload  # hashed features only
    router = DomainRouter(
        model, {"clinical": _Fixed("PERSON"), "financial": _Fixed("ORGANIZATION")}
    )
    assert router.min_evidence == DEFAULT_MIN_EVIDENCE
    assert router.route("Paciente con fiebre y hematuria, ecografía renal.") == "clinical"
    assert router.route("Estado de cuenta bancaria del préstamo con intereses.") == "financial"
    assert router.route("") == "mixed"
    mixed = router.detect("zzz qqq")  # no known evidence: both taggers run
    assert {f.entity_type for f in mixed} == {"PERSON", "ORGANIZATION"}
    with pytest.raises(ValueError):
        DomainRouter(model, {"clinical": _Fixed("PERSON")})
    with pytest.raises(ValueError):
        DomainRouter(dict(model, format="other"), {"clinical": None, "financial": None})


def test_builtin_router_and_cli(tmp_path, capsys):
    router = DomainRouter.builtin()
    assert set(router.taggers) == {"clinical", "financial"}
    clinical = "Paciente de 70 años con hematuria macroscópica. Se realiza ecografía renal."
    financial = "Estimado cliente, adjuntamos el estado de cuenta de su préstamo hipotecario."
    assert router.route(clinical) == "clinical" and router.route(financial) == "financial"
    from deidflow.cli import main

    source = tmp_path / "note.txt"
    source.write_text("Datos del paciente.\nNombre: Ernesto Rivera Bueno.\nNHC: 368503.\n", "utf-8")
    assert main(["scan", str(source), "--tagger", "builtin:auto"]) == 0
    assert json.loads(capsys.readouterr().out)["by_type"].get("PATIENT_ID") == 1
    with pytest.raises(SystemExit):  # the router takes a profile, not explicit margins
        main(["scan", str(source), "--tagger", "builtin:auto", "--review-margin", "5"])


def test_redact_margin_redacts_without_review_and_review_margin_wins():
    model = json.loads(gzip.decompress(open_model("es-clinical")))
    text = "Datos del paciente.\nNombre: Ana Ruiz.\nComentario: llamó la vecina Lucía.\n"
    base = SpanTagger(model)
    huge = 1e5
    redact = SpanTagger(model, redact_margin=huge)
    review = SpanTagger(model, review_margin=huge, redact_margin=huge)
    extra = [f for f in redact.detect(text) if "near_miss" in f.context]
    assert extra and all(f.score == 0.75 and "redact_only" in f.context for f in extra)
    assert all(f.score == 0.5 for f in review.detect(text) if "near_miss" in f.context)
    assert not [f for f in base.detect(text) if "near_miss" in f.context]
    with pytest.raises(ValueError):
        SpanTagger(model, redact_margin=0)


def open_model(name):
    from importlib import resources

    from deidflow.nlp.tagger import BUILTIN_MODELS

    return resources.files("deidflow.models").joinpath(BUILTIN_MODELS[name][0]).read_bytes()


def test_packaged_profiles_apply_and_explicit_margins_win():
    profiles = builtin_profiles()
    assert set(profiles) >= {"es-clinical", "es-finance"}
    for name, entries in profiles.items():
        for profile, settings in entries.items():
            tagger = SpanTagger.builtin(name, profile=profile)
            assert tagger.review_margin == settings.get("review_margin")
            assert tagger.redact_margin == settings.get("redact_margin")
    explicit = SpanTagger.builtin("es-clinical", profile="balanced", redact_margin=7.0)
    assert explicit.redact_margin == 7.0
    with pytest.raises(ValueError, match="Unknown profile"):
        SpanTagger.builtin("es-clinical", profile="nonexistent")


def test_wilson_interval_bounds():
    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(0, 50)
    assert low == 0.0 and 0.05 < high < 0.08
    low, high = wilson_interval(5, 10)
    assert math.isclose(low + high, 1.0, abs_tol=1e-9)


def test_release_gate_metrics_count_direct_identifier_leaks():
    text = "Paciente: Ana Ruiz. Trabaja en Acme Corp."
    example = Example(
        "x",
        text,
        (GoldSpan("PERSON", 10, 18), GoldSpan("ORGANIZATION", 31, 40)),
        "test",
        "t",
    )
    assert "PERSON" in DIRECT_IDENTIFIERS and "ORGANIZATION" not in DIRECT_IDENTIFIERS
    engine = DeidEngine(nlp=CachedTagger(_PersonOnly(), [text]))
    metrics = release_gate_metrics(engine, [example], Policy.strict())
    assert metrics["status_counts"] == {"APPROVED": 1}
    assert metrics["approved_leak_rate"] == 1.0  # the organization stayed
    assert metrics["approved_direct_identifier_leak_rate"] == 0.0
    assert metrics["over_redaction_rate"] == 9 / 20  # "Paciente:" of 20 non-gold characters


class _PersonOnly:
    def decode(self, text):
        return text

    def spans(self, text, decoded):
        # Covers the "Paciente: " label too, so some non-gold text is over-redacted.
        return [(0, 18)] if "Ana Ruiz" in text else []

    def to_findings(self, spans):
        from deidflow.core import Finding

        return [Finding("PERSON", s, e, 0.95, "fixed") for s, e in spans]

    def detect(self, text):
        return self.to_findings(self.spans(text, self.decode(text)))


@pytest.mark.parametrize("name", ["es-clinical", "es-finance"])
def test_cached_tagger_matches_live_inference_for_every_margin_pair(name):
    texts = [
        "Juan Pérez vive en Madrid y trabaja en Acme Corp. Su teléfono es 5551234567.",
        "Datos del paciente.\nNombre: Ernesto Rivera Bueno.\nNHC: 368503.\nVive con su hermana.",
        "Estimado Sr. Carlos Méndez, le escribimos de Banco Ejemplo S.A. sobre su préstamo.",
    ]
    tagger = SpanTagger.builtin(name)
    cached = CachedTagger(tagger, texts)
    grid = (None, 5.0, 20.0, 40.0, 160.0, 320.0)
    for review in grid:
        for redact in grid:
            tagger.review_margin, tagger.redact_margin = review, redact
            for text in texts:
                live = [
                    (f.entity_type, f.start, f.end, f.score, f.context) for f in tagger.detect(text)
                ]
                again = [
                    (f.entity_type, f.start, f.end, f.score, f.context) for f in cached.detect(text)
                ]
                assert again == live, (review, redact, text)
