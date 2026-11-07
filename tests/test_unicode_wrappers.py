import pytest

from deidflow import DeidEngine
from deidflow.benchmarks.release_gate import CachedTagger
from deidflow.core import Finding
from deidflow.nlp import CombinedNER
from deidflow.nlp.router import DomainRouter
from deidflow.nlp.tagger import SpanTagger, feature_key


@pytest.mark.parametrize("wrapper", ["combined", "router", "cached"])
def test_wrapped_model_keeps_original_ordinal_address_coverage(wrapper):
    source = "Vive en Calle Ficción 12, 5º derecha."
    tagger = SpanTagger.builtin("es-general", profile="balanced")
    if wrapper == "combined":
        adapter = CombinedNER(tagger)
    elif wrapper == "router":
        model = {
            "format": "deidflow.domain-router",
            "format_version": 1,
            "domains": ["first", "second"],
            "weights": {},
            "unknown": [0, 0],
        }
        adapter = DomainRouter(model, {"first": tagger, "second": tagger})
    else:
        adapter = CachedTagger(tagger, [source])
    addresses = [
        source[f.start : f.end]
        for f in DeidEngine(nlp=adapter).scan_text(source)
        if f.entity_type == "ADDRESS" and "tagger.local" in f.detector
    ]
    assert "Calle Ficción 12, 5º derecha" in addresses


def test_cached_normalized_alias_does_not_replace_original_ordinal_features():
    ordinal = "Vive en Calle Ficción 12, 5º derecha."
    ordinary = "Vive en Calle Ficción 12, 5o derecha."
    tagger = SpanTagger.builtin("es-general", profile="balanced")
    engine = DeidEngine(nlp=CachedTagger(tagger, [ordinary, ordinal]))
    texts = [ordinary, ordinal, ordinary]
    predictions = engine.scan_texts(texts)
    addresses = [
        [
            text[f.start : f.end]
            for f in row
            if f.entity_type == "ADDRESS" and "tagger.local" in f.detector
        ]
        for text, row in zip(texts, predictions, strict=True)
    ]
    assert addresses == [
        ["Calle Ficción 12"],
        ["Calle Ficción 12, 5º derecha"],
        ["Calle Ficción 12"],
    ]


@pytest.mark.parametrize("wrapper", ["combined", "router", "cached"])
def test_external_children_still_receive_full_nfkc_detection_text(wrapper):
    class LiteralAdapter:
        def __init__(self, detector):
            self.detector = detector

        def detect(self, text):
            assert text == "No Ana"
            return [Finding("LOCATION", 0, 2, 0.9, self.detector)]

        def detect_batch(self, texts):
            return [self.detect(text) for text in texts]

    first = LiteralAdapter("external.first")
    if wrapper == "combined":
        adapter = CombinedNER(first)
    elif wrapper == "router":
        model = {
            "format": "deidflow.domain-router",
            "format_version": 1,
            "domains": ["first", "second"],
            "weights": {
                feature_key("w=nº"): [0, -8],
                feature_key("w=no"): [-8, 0],
            },
            "unknown": [-8, -8],
        }
        adapter = DomainRouter(model, {"first": first, "second": LiteralAdapter("external.second")})
    else:
        adapter = CachedTagger(first, [])
    source = "Ｎº Ａｎａ"
    found = DeidEngine(nlp=adapter).scan_text(source)
    assert [(f.detector, source[f.start : f.end]) for f in found] == [("external.first", "Ｎº")]
