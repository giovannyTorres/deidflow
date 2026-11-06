"""Pack contracts and fictional context regressions, not population-quality estimates."""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from deidflow.core import EntityType, Finding
from deidflow.detectors import RuleDetector
from deidflow.detectors.domain_roles import DomainModelAdapter, DomainRoleRecognizer
from deidflow.detectors.narrative import NarrativeRecognizer, coordinated_person_spans
from deidflow.domains import get_domain_pack, list_domain_packs
from deidflow.engine import ReleaseStatus
from deidflow.policies import Policy
from deidflow.session import DeidSession


def test_pack_inventory_is_versioned_immutable_and_json_safe():
    packs = list_domain_packs()
    assert tuple(p.name for p in packs) == ("clinical", "financial", "legal", "general")
    for pack in packs:
        assert get_domain_pack(f"{pack.name}@1.0.0") is pack
        assert get_domain_pack(pack.name, version="1.0.0") is pack
        assert pack.language == "es" and pack.supervised_review
        assert re.fullmatch(r"[a-f0-9]{64}", pack.model_sha256)
        assert re.fullmatch(r"[a-f0-9]{64}", pack.fingerprint())
        metadata = pack.to_dict()
        json.dumps(metadata)
        metadata["limitations"].clear()
        assert pack.limitations
    assert "not a trained or validated specialist legal model" in " ".join(packs[2].limitations)


@pytest.mark.parametrize(
    "name,version",
    [("medical", None), ("clinical", "2"), ("clinical@1.0.0", "2"), ("clinical@", None)],
)
def test_unknown_pack_or_version_fails(name, version):
    with pytest.raises(ValueError):
        get_domain_pack(name, version=version)


@pytest.mark.parametrize("name", [p.name for p in list_domain_packs()])
def test_policies_index_identifiers_and_preserve_useful_categories(name):
    pack = get_domain_pack(name)
    policy = pack.policy()
    assert policy.require_ner and policy.token_scope == "session"
    assert policy.require_human_review
    assert policy.independent_check == "proper_nouns"
    for kind in EntityType:
        expected = "keep" if kind in pack.preserved_types else "indexed"
        assert policy.rule(kind).action == expected
    assert policy.rule("AGE").action == "indexed"
    assert pack.policy(sensitive_types=("MEDICATION", "AMOUNT")).rule("AMOUNT").action == "indexed"
    assert pack.policy(preserve_context=False).rule("MEDICATION").action == "indexed"
    assert policy.fingerprint() == pack.session(model="rules").policy.fingerprint()


@pytest.mark.parametrize(
    "options",
    [
        {"sensitive_types": "MEDICATION"},
        {"sensitive_types": ["TYPO"]},
        {"preserve_context": "yes"},
        {"verify_proper_nouns": 0},
        {"dates": "unsafe"},
        {"dates": "shift"},
        {"shift_days": 1},
        {"dates": "shift", "shift_days": True},
        {"dates": "shift", "shift_days": 40000},
    ],
)
def test_invalid_policy_options_fail(options):
    with pytest.raises(ValueError):
        get_domain_pack("general").policy(**options)


@pytest.mark.parametrize(
    "options",
    [
        {"model": "auto"},
        {"profile": "fast"},
        {"adapter": object()},
        {"model": "custom"},
        {"model": "custom", "adapter": object(), "adapter_digest": "a" * 64},
        {"adapter_digest": "a" * 64},
    ],
)
def test_invalid_model_choices_fail(options):
    with pytest.raises(ValueError):
        get_domain_pack("general").engine(**options)


def test_model_registry_drift_does_not_silently_change_a_pack():
    pack = replace(get_domain_pack("clinical"), model_sha256="0" * 64)
    with pytest.raises(ValueError, match="pin"):
        pack.engine()


def test_digest_binds_pack_model_profile_and_countries():
    pack = get_domain_pack("clinical")
    baseline = pack.engine(model="rules", country="ES,MX").model_digest
    assert baseline == pack.engine(model="rules", country=["MX", "ES"]).model_digest
    variants = [
        pack.engine(model="rules", country="MX"),
        pack.engine(model="rules", profile="assurance", country="ES,MX"),
        pack.engine(country="ES,MX"),
        get_domain_pack("legal").engine(model="rules", country="ES,MX"),
    ]
    assert all(engine.model_digest != baseline for engine in variants)
    assert pack.engine().model_digest == pack.engine(model="builtin").model_digest


@pytest.mark.parametrize(
    "domain,text,role",
    [
        ("clinical", "Paciente: Ana López", "patient"),
        ("clinical", "La médica Ana López niega fiebre.", "clinician"),
        ("financial", "El acreedor Juan Pérez reclama el pago.", "creditor"),
        ("financial", "Deudora: ANA LÓPEZ", "debtor"),
        ("legal", "La demandante Ana López comparece.", "plaintiff"),
        ("legal", "Testigo: Luis de la Cruz", "witness"),
        ("general", "Agente: Rosa Pérez", "agent"),
    ],
)
def test_explicit_roles_have_exact_source_offsets(domain, text, role):
    findings = [f for f in DomainRoleRecognizer(domain).detect(text) if f.entity_type == "PERSON"]
    assert len(findings) == 1
    assert f"role:{role}" in findings[0].context
    assert text[findings[0].start : findings[0].end] in {
        "Ana López",
        "Juan Pérez",
        "ANA LÓPEZ",
        "Luis de la Cruz",
        "Rosa Pérez",
    }


@pytest.mark.parametrize(
    "text",
    [
        "Paciente: Diabetes",
        "Paciente: estable",
        "Paciente: Hospital General",
        "Cliente: [CLIENTE_1]",
        "Demandante: 123456789",
    ],
)
def test_role_rules_do_not_turn_labels_conditions_or_tokens_into_people(text):
    assert not DomainRoleRecognizer("general").detect(text)


@pytest.mark.parametrize(
    "domain,text",
    [
        ("clinical", "Paciente: NO PRESENTA FIEBRE. Niega disnea."),
        ("clinical", "Paciente: SIN DATOS DE ALARMA."),
        ("clinical", "Paciente: NO REFIERE TOS NI DISNEA."),
        ("clinical", "Paciente: SIN SIGNOS CLÍNICOS DE INFECCIÓN."),
        ("financial", "Cliente: NO APLICA."),
        ("legal", "Demandante: NO IDENTIFICADO."),
    ],
)
def test_uppercase_observations_are_not_person_names_or_automatic_release(domain, text):
    assert not any(f.entity_type == "PERSON" for f in DomainRoleRecognizer(domain).detect(text))
    result = get_domain_pack(domain).session().deidentify(text)
    assert result.output_text == text
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "HUMAN_REVIEW_REQUIRED" in result.issues


def test_clinical_status_category_refinement_requires_review_and_can_be_sensitive():
    pack = get_domain_pack("clinical")
    text = "Paciente: NO PRESENTA FIEBRE."
    result = pack.session().deidentify(text)
    assert result.output_text == text
    assert "DOMAIN_CONTEXT_REFINED" in result.issues
    sensitive = pack.session(
        policy=pack.policy(sensitive_types=("CLINICAL_OBSERVATION",))
    ).deidentify(text)
    assert "NO PRESENTA FIEBRE" not in sensitive.output_text


def test_clinical_model_preserves_negation_medication_dose_and_explicit_roles():
    session = get_domain_pack("clinical").session()
    text = "Paciente: Ana López niega diabetes y toma metformina 500 mg. Médico: Luis Pérez."
    result = session.deidentify(text)
    assert result.output_text == (
        "Paciente: [PACIENTE_1] niega diabetes y toma metformina 500 mg. Médico: [MEDICO_1]."
    )
    assert session.reidentify(result.output_text).text == text
    # The native clinical model overextends PERSON into 'niega'. Refinement must
    # be retained as uncertainty even after fusion with the exact name rule.
    findings = session.engine.scan_text(text)
    assert any("domain_boundary_refinement" in f.context for f in findings)
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "DOMAIN_BOUNDARY_REFINED" in result.issues


def test_financial_context_and_same_role_identity_survive_across_documents():
    session = get_domain_pack("financial").session()
    first = session.deidentify(
        "Cliente: Ana López debe 6,500.00 MXN al acreedor Juan Pérez. No hay mora."
    )
    second = session.deidentify(
        "Cliente: Ana López pagó 500 MXN; acreedor Juan Pérez recibió el pago."
    )
    assert "[CLIENTE_1]" in first.output_text and "[CLIENTE_1]" in second.output_text
    assert "[ACREEDOR_1]" in first.output_text and "[ACREEDOR_1]" in second.output_text
    assert "6,500.00 MXN" in first.output_text and "No hay mora." in first.output_text
    assert "500 MXN" in second.output_text
    assert session.graph()["relations"] == []  # Text does not assert graph relations.
    assert len(session.graph()["entities"]) == 2


def test_legal_general_model_keeps_negation_claim_amount_and_contract_terms():
    session = get_domain_pack("legal").session()
    text = (
        "Demandante: Ana López reclama 6500 MXN al demandado Juan Pérez. "
        "El testigo Luis Gómez no firmó el contrato: ABC-334."
    )
    result = session.deidentify(text)
    assert "[DEMANDANTE_1] reclama 6500 MXN al demandado [DEMANDADO_1]" in result.output_text
    assert "[TESTIGO_1] no firmó el contrato: [CONTRATO_1]" in result.output_text
    assert all(
        raw not in result.output_text
        for raw in ("Ana López", "Juan Pérez", "Luis Gómez", "ABC-334")
    )


def test_explicitly_sensitive_medication_and_money_are_indexed_in_spanish():
    pack = get_domain_pack("clinical")
    session = pack.session(
        model="rules", policy=pack.policy(sensitive_types=("MEDICATION", "AMOUNT"))
    )
    result = session.deidentify("Paciente: Ana López toma metformina 500 mg. Importe: 6500 MXN.")
    assert "[MEDICAMENTO_1] 500 mg" in result.output_text
    assert "[IMPORTE_1] MXN" in result.output_text
    assert result.status == ReleaseStatus.REVIEW_REQUIRED
    assert "SEMANTIC_MODEL_REQUIRED" in result.issues


def test_amount_preservation_never_hides_overlapping_identifiers():
    pack = get_domain_pack("financial")
    session = pack.session(model="rules")
    result = session.deidentify("Monto: 4111111111111111 MXN; tarjeta: 4111111111111111.")
    assert "4111111111111111" not in result.output_text  # Valid Luhn card, even after currency cue.
    result = session.deidentify("Monto: 6500 MXN; cuenta: 6500.")
    assert "Monto: 6500 MXN" in result.output_text
    assert "cuenta: [CUENTA_1]" in result.output_text


def test_dates_default_to_indexed_and_explicit_shifts_preserve_intervals_not_birthdates():
    pack = get_domain_pack("clinical")
    text = "Nacimiento: 1990-01-03. Consulta: 2025-01-10; control: 2025-01-17."
    default = pack.session(model="rules").deidentify(text).output_text
    assert "[FECHA_NACIMIENTO_1]" in default and "[FECHA_1]" in default and "[FECHA_2]" in default
    shifted = pack.session(
        model="rules", policy=pack.policy(dates="shift", shift_days=30)
    ).deidentify(text)
    assert "[FECHA_NACIMIENTO_1]" in shifted.output_text
    assert "2025-02-09" in shifted.output_text and "2025-02-16" in shifted.output_text
    assert shifted.status != ReleaseStatus.APPROVED
    explicit = pack.policy(dates="shift", shift_days=30, sensitive_types=("DATE",))
    assert explicit.rule("DATE").action == "indexed" and explicit.allow_residual_types == ()
    assert pack.policy(dates="keep").rule("DATE_OF_BIRTH").action == "indexed"


class StaticAdapter:
    def __init__(self, finding):
        self.finding = finding

    def detect_batch(self, texts):
        return [[self.finding] for _ in texts]


@pytest.mark.parametrize(
    "tail,refines",
    [
        (" niega", True),
        (" no presenta", True),
        (" y Juan Gómez", False),
        (" ABC123", False),
        ("\nniega", False),
    ],
)
def test_model_refinement_is_bounded_and_preserves_unknown_extra_identity(tail, refines):
    text = "Paciente: Ana López" + tail
    model = StaticAdapter(Finding("PERSON", 10, len(text), 0.3, "synthetic"))
    findings = DomainModelAdapter(model, "clinical").detect_batch([text])[0]
    if len(findings) > 1:
        # Coordination may separate the people, but must retain both identities.
        assert [text[f.start : f.end] for f in findings] == ["Ana López", "Juan Gómez"]
        assert all("domain_boundary_refinement" not in f.context for f in findings)
        return
    finding = findings[0]
    assert (finding.end == len("Paciente: Ana López")) == refines
    assert ("domain_boundary_refinement" in finding.context) == refines


def test_model_refinement_does_not_narrow_nonperson_identifiers():
    text = "Paciente: Ana López niega"
    original = Finding("BANK_ACCOUNT", 10, len(text), 0.3, "synthetic")
    refined = DomainModelAdapter(StaticAdapter(original), "clinical").detect_batch([text])[0][0]
    assert refined == original


@pytest.mark.parametrize(
    "kind,protected", [("PERSON", True), ("LOCATION", True), ("BANK_ACCOUNT", False)]
)
def test_context_refinement_does_not_override_protected_or_identifier_predictions(kind, protected):
    text = "Paciente: NO PRESENTA FIEBRE"
    original = Finding(kind, 10, len(text), 0.9, "synthetic", protected=protected)
    assert (
        DomainModelAdapter(StaticAdapter(original), "clinical").detect_batch([text])[0][0]
        == original
    )


def test_context_refinement_does_not_discard_an_extra_name_outside_observation():
    text = "Paciente: NO PRESENTA FIEBRE Ana López"
    original = Finding("PERSON", 10, len(text), 0.3, "synthetic")
    assert (
        DomainModelAdapter(StaticAdapter(original), "clinical").detect_batch([text])[0][0]
        == original
    )


def test_custom_adapter_requires_pinned_configuration():
    adapter = StaticAdapter(Finding("PERSON", 0, 3, 0.9, "synthetic"))
    pack = get_domain_pack("general")
    with pytest.raises(ValueError, match="SHA-256"):
        pack.engine(model="custom", adapter=adapter)
    engine = pack.engine(model="custom", adapter=adapter, adapter_digest="a" * 64)
    assert (
        engine.model_digest
        != pack.engine(model="custom", adapter=adapter, adapter_digest="b" * 64).model_digest
    )


def test_pack_session_snapshot_rejects_different_model_or_policy(tmp_path):
    pytest.importorskip("cryptography")
    pack = get_domain_pack("financial")
    session = pack.session(model="rules")
    session.deidentify("Cliente: Ana López")
    path, key = tmp_path / "financial.enc", b"s" * 32
    session.save(path, key=key)
    restored = DeidSession.load(
        path, key=key, engine=pack.engine(model="rules"), policy=pack.policy()
    )
    assert "[CLIENTE_1]" in restored.deidentify("Cliente: Ana López").output_text
    with pytest.raises(ValueError):
        DeidSession.load(path, key=key, engine=pack.engine(), policy=pack.policy())
    with pytest.raises(ValueError):
        DeidSession.load(
            path,
            key=key,
            engine=pack.engine(model="rules"),
            policy=pack.policy(preserve_context=False),
        )


@pytest.mark.parametrize("verb", ["debe", "adeuda"])
def test_financial_creditor_grammar_finds_names_without_session_history(verb):
    text = f"La titular {verb} a Néstor Barajas Luna el principal pactado; sin recargo."
    findings = DomainRoleRecognizer("financial").detect(text)
    assert any(
        text[f.start : f.end] == "Néstor Barajas Luna" and "role:creditor" in f.context
        for f in findings
    )
    result = get_domain_pack("financial").session(model="rules").deidentify(text)
    assert "Néstor" not in result.output_text
    assert f"{verb} a [ACREEDOR_1]" in result.output_text
    assert "sin recargo" in result.output_text


def test_financial_creditor_rule_does_not_truncate_a_company_into_a_person():
    assert not DomainRoleRecognizer("financial").detect(
        "La titular debe a Banco Nacional el saldo."
    )


@pytest.mark.parametrize(
    "label,code,kind",
    [
        ("Cuenta", "884212058913", "BANK_ACCOUNT"),
        ("Cliente", "CLI.2026.17", "CUSTOMER_ID"),
        ("Contrato", "AB/2026-17", "CONTRACT_ID"),
        ("Expediente", "P-4856", "PATIENT_ID"),
    ],
)
def test_labelled_identifier_boundaries_preserve_internal_punctuation(label, code, kind):
    source = f"{label}: {code}. Seguimiento posterior."
    findings = [f for f in RuleDetector().detect(source) if f.entity_type == kind]
    assert any(source[f.start : f.end] == code for f in findings)
    assert all(not source[f.start : f.end].endswith(".") for f in findings)
    session = get_domain_pack("general").session(model="rules")
    first = session.deidentify(source)
    second = session.deidentify(f"{label}: {code}; seguimiento.")
    token = re.search(r"\[[A-Z_]+_\d+\]", first.output_text).group()
    assert token in second.output_text
    assert f"{token}. Seguimiento" in first.output_text


@pytest.mark.parametrize("text", ["Cliente: CLI-123456.", "Cliente: CLI.2026.17."])
def test_code_prefix_is_not_a_partial_person_name(text):
    assert not any(
        f.entity_type == "PERSON" for f in DomainRoleRecognizer("financial").detect(text)
    )


def test_coordinated_full_names_are_separate_and_preserve_the_conjunction():
    text = "Contrato entre Ana López Salas y Luis Pérez Solís. No se permite cederlo."
    engine = get_domain_pack("legal").engine()
    findings = engine.scan_text(text)
    assert any("person_coordination_split" in f.context for f in findings)
    result = engine.deidentify_text(text, policy=get_domain_pack("legal").policy())
    output = result.output_text
    assert "PERSON_COORDINATION_SPLIT" in result.issues
    assert "[PERSONA_1] y [PERSONA_2]" in output
    assert "No se permite cederlo." in output
    narrative = [f for f in NarrativeRecognizer().detect(text) if f.entity_type == "PERSON"]
    assert {text[f.start : f.end] for f in narrative} == {"Ana López Salas", "Luis Pérez Solís"}


def test_compound_surname_is_not_split_without_a_second_full_given_name():
    text = "José Ortega y Gasset"
    assert coordinated_person_spans(text, 0, len(text)) == ((0, len(text)),)
    assert any(text[f.start : f.end] == text for f in NarrativeRecognizer().detect(text))


def test_unprotected_model_coordination_split_keeps_all_name_characters():
    text = "Ana López Salas y Luis Pérez Solís"
    original = Finding("PERSON", 0, len(text), 0.7, "synthetic")
    result = DomainModelAdapter(StaticAdapter(original), "legal").detect_batch([text])[0]
    assert [text[f.start : f.end] for f in result] == ["Ana López Salas", "Luis Pérez Solís"]
    assert all("person_coordination_split" in f.context for f in result)
    protected = replace(original, protected=True)
    assert DomainModelAdapter(StaticAdapter(protected), "legal").detect_batch([text])[0] == [
        protected
    ]


@pytest.mark.parametrize(
    "text,noun",
    [
        ("Ambos son hermanos.", "hermanos"),
        ("Viaja con su hermano [FAMILIAR_1].", "hermano"),
        ("Ellas eran primas.", "primas"),
        ("Habla con nuestra madre.", "madre"),
    ],
)
def test_kinship_predicates_are_context_and_not_person_names(text, noun):
    start = text.index(noun)
    model = StaticAdapter(Finding("PERSON", start, start + len(noun), 0.8, "synthetic"))
    result = DomainModelAdapter(model, "general").detect_batch([text])[0][0]
    assert result.entity_type == "DEMOGRAPHIC"
    assert "domain_context_refinement" in result.context
    assert text[result.start : result.end] == noun


def test_kinship_refinement_does_not_filter_arbitrary_lowercase_names():
    text = "Nombre: hermanos"
    original = Finding("PERSON", 8, len(text), 0.8, "synthetic")
    assert (
        DomainModelAdapter(StaticAdapter(original), "general").detect_batch([text])[0][0]
        == original
    )


def test_kinship_model_false_positive_survives_source_and_output_verification_as_context():
    pack = get_domain_pack("general")
    text = "Nombre: Ana López. Familiar: Luis Pérez. Ambos son hermanos."
    result = pack.session().deidentify(text)
    assert "Ambos son hermanos." in result.output_text
    assert "HUMAN_REVIEW_REQUIRED" in result.issues
    assert "RESIDUAL_FINDINGS" not in result.issues


@pytest.mark.parametrize("domain", ["financial", "general"])
@pytest.mark.parametrize(
    "text",
    [
        "Cliente: Sí, acepto la propuesta.",
        "Agente: Gracias, confirmaré su solicitud.",
        "Cliente: No, rechacé ese cargo.",
        "Cliente: Sí. Agente: Gracias. Cliente: No.",
    ],
)
def test_complete_punctuated_speaker_responses_preserve_affirmation_and_negation(domain, text):
    assert not any(f.entity_type == "PERSON" for f in DomainRoleRecognizer(domain).detect(text))
    result = get_domain_pack(domain).session().deidentify(text)
    assert result.output_text == text
    assert "HUMAN_REVIEW_REQUIRED" in result.issues


@pytest.mark.parametrize(
    "text,name",
    [
        ("Cliente: No Cárdenas.", "No Cárdenas"),
        ("Agente: Gracias López.", "Gracias López"),
        ("Cliente: Sí Elena.", "Sí Elena"),
        ("El cliente No, llegó temprano.", "No"),
        ("Cliente: No", "No"),
    ],
)
def test_speaker_response_guard_does_not_ban_names_or_unpunctuated_single_words(text, name):
    findings = DomainRoleRecognizer("financial").detect(text)
    assert any(f.entity_type == "PERSON" and text[f.start : f.end] == name for f in findings)


@pytest.mark.parametrize(
    "text",
    ["Número de cliente: No.", "ID de cliente: Gracias.", "Cliente ID: No.", "Cliente: NO-2144."],
)
def test_explicit_identifiers_are_not_reclassified_as_dialogue(text):
    findings = RuleDetector().detect(text)
    assert any(f.entity_type == "CUSTOMER_ID" for f in findings)
    assert not any("explicit_speaker_response" in f.context for f in findings)


def test_bare_customer_response_with_period_is_context_and_requires_review():
    pack = get_domain_pack("general")
    for text in ("Cliente: No.", "Cliente: Gracias, revisaré la propuesta."):
        result = pack.session(model="rules").deidentify(text)
        assert result.output_text == text
        assert "DOMAIN_CONTEXT_REFINED" in result.issues


@pytest.mark.parametrize("separator", [". ", ", ", " ", "; ", "\n"])
def test_address_stops_at_next_explicit_field_and_keeps_street_abbreviations(separator):
    address = "Av. del Parque 24 Int. 2 C.P. 03100"
    text = f"Dirección: {address}{separator}Grupo sanguíneo: AB-. Teléfono: 5512345678."
    findings = RuleDetector().detect(text)
    assert any(f.entity_type == "ADDRESS" and text[f.start : f.end] == address for f in findings)
    assert not any(
        f.entity_type == "ADDRESS" and "sanguíneo" in text[f.start : f.end] for f in findings
    )
    assert any(
        f.entity_type == "MEDICAL_ATTRIBUTE" and text[f.start : f.end] == "AB-" for f in findings
    )
    assert any(f.entity_type == "PHONE" and text[f.start : f.end] == "5512345678" for f in findings)


def test_address_field_order_and_multiple_addresses_keep_independent_coverage():
    text = (
        "Tipo de sangre: A+. Domicilio: Calle Norte 18 Teléfono: 5512345678 "
        "Dirección: Av. Sur 23. Correo: persona@example.test."
    )
    findings = RuleDetector().detect(text)
    addresses = {text[f.start : f.end] for f in findings if f.entity_type == "ADDRESS"}
    assert "Calle Norte 18" in addresses and "Av. Sur 23" in addresses
    assert any(f.entity_type == "EMAIL" for f in findings)
    result = get_domain_pack("general").session(model="rules").deidentify(text)
    assert "Tipo de sangre: A+." in result.output_text
    assert all(
        value not in result.output_text
        for value in ("Calle Norte", "Av. Sur", "5512345678", "persona@example.test")
    )


def test_postal_and_locality_continuations_are_still_part_of_address():
    text = (
        "Domicilio: Av. del Parque 24\nC.P. 03100\nCol. Centro\n"
        "Ciudad: México\nTipo de sangre: O+. Teléfono: 5512345678."
    )
    addresses = [
        text[f.start : f.end] for f in RuleDetector().detect(text) if f.entity_type == "ADDRESS"
    ]
    assert any("C.P. 03100" in value and "Ciudad: México" in value for value in addresses)
    assert all("Tipo de sangre" not in value for value in addresses)


def test_default_pack_preserves_blood_type_but_strict_policy_replaces_it():
    text = "Domicilio: Av. del Parque 24. Tipo de sangre: O+. Teléfono: 5512345678."
    pack = get_domain_pack("general")
    result = pack.session().deidentify(text)
    assert (
        result.output_text
        == "Domicilio: [DIRECCION_1]. Tipo de sangre: O+. Teléfono: [TELEFONO_1]."
    )
    strict = pack.engine(model="rules").deidentify_text(
        text, policy=Policy.strict(require_ner=False)
    )
    assert "O+" not in strict.output_text
    sensitive = pack.session(
        model="rules", policy=pack.policy(sensitive_types=("MEDICAL_ATTRIBUTE",))
    ).deidentify(text)
    assert "O+" not in sensitive.output_text


def test_model_address_cannot_absorb_partial_next_header_without_review():
    text = "Domicilio: Av. del Parque 24 Tipo de sangre: O+."
    start, end = text.index("Av."), text.index("Tipo") + len("Tipo")
    original = Finding("ADDRESS", start, end, 0.8, "synthetic")
    result = DomainModelAdapter(StaticAdapter(original), "general").detect_batch([text])[0][0]
    assert text[result.start : result.end] == "Av. del Parque 24"
    assert "domain_boundary_refinement" in result.context
    protected = replace(original, protected=True)
    assert (
        DomainModelAdapter(StaticAdapter(protected), "general").detect_batch([text])[0][0]
        == protected
    )


def test_model_address_refinement_requires_a_complete_explicit_header():
    text = "Av. del Parque 24 Tipo de sangre"
    original = Finding("ADDRESS", 0, len(text), 0.8, "synthetic")
    assert (
        DomainModelAdapter(StaticAdapter(original), "general").detect_batch([text])[0][0]
        == original
    )


def test_empty_address_before_a_new_field_does_not_create_an_empty_finding():
    text = "Domicilio:     Tipo de sangre: O+."
    findings = RuleDetector().detect(text)
    assert not any(f.entity_type == "ADDRESS" for f in findings)
    assert any(f.entity_type == "MEDICAL_ATTRIBUTE" for f in findings)
