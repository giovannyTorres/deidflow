"""Contracts for source-aware metadata at normalized model boundaries."""

import pytest

from deidflow.core import Finding
from deidflow.detectors.domain_roles import DomainModelAdapter, DomainRoleRecognizer
from deidflow.normalization import detection_view


def test_domain_wrapper_keeps_external_models_on_the_full_normalized_view():
    class NormalizedOnlyAdapter:
        def detect_batch(self, texts):
            if texts != ["No Ana"]:
                raise ValueError("External model requires the normalized input contract")
            return [[Finding("PERSON", 3, 6, 1.0, "external.normalized")]]

    source = "Nº Ａ\u200bna"
    view = detection_view(source)
    adapter = DomainModelAdapter(NormalizedOnlyAdapter(), "general")
    (findings,) = adapter.detect_views([source], [view])
    assert [(f.entity_type, f.start, f.end) for f in findings] == [("PERSON", 3, 6)]
    assert view.text == "No Ana"
    assert view.bounds(3, 6) == (3, 7)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Paciente: Ana Ficticia Nº", "Ana Ficticia"),
        ("Paciente: Ana Ficticia No", "Ana Ficticia No"),
    ],
)
def test_role_metadata_distinguishes_source_ordinal_from_an_ordinary_name_word(source, expected):
    view = detection_view(source)
    findings = DomainRoleRecognizer("clinical").detect_view(source, view)
    people = [f for f in findings if f.entity_type == "PERSON"]
    assert [source[f.start : f.end] for f in people] == [expected]
