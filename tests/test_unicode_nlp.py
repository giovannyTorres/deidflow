from deidflow import DeidEngine
from deidflow.nlp.tagger import SpanTagger


def test_existing_model_keeps_original_floor_coverage_with_normalized_detection():
    source = "Vive en Calle Ficción 12, 5º derecha."
    engine = DeidEngine(nlp=SpanTagger.builtin("es-general", profile="balanced"))
    addresses = [
        source[f.start : f.end]
        for f in engine.scan_text(source)
        if f.entity_type == "ADDRESS" and "tagger.local" in f.detector
    ]
    assert "Calle Ficción 12, 5º derecha" in addresses
