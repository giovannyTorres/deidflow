from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
from benchmark_case_fixtures import canonical, fixture_records, profile_package, save_manifest


def test_published_generic_rfc_checksum_references_use_check_digit_not_full_acceptance(tmp_path):
    from stdnum.mx import rfc

    from deidflow.benchmarks.evaluation_package import load_evaluation_package
    from deidflow.benchmarks.validation_runner import run_validation_benchmark

    package = Path(__file__).resolve().parents[1] / "examples" / "benchmark-mx-validation"
    digest = hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest()
    loaded = load_evaluation_package(package, manifest_sha256=digest)
    units = {row["unit_id"]: row for row in loaded.records["units"]}
    references = {
        units[row["unit_id"]]["text"][row["start"] : row["end"]]: row["validity"]["checksum"]
        for row in loaded.records["validation_vectors"]
        if row["entity_type"] == "RFC"
    }
    # Full strict acceptance rejects both generic serial components. It is not
    # an oracle for the separate ordinary check-digit attribute.
    assert rfc.calc_check_digit("XAXX01010100") == "4"
    assert rfc.calc_check_digit("XEXX01010100") == "0"
    assert not rfc.is_valid("XEXX010101000", validate_check_digits=True)
    assert references["XAXX010101000"] == "invalid"
    assert references["XEXX010101000"] == "valid"
    result = run_validation_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="validation-descriptive-v1",
        output=tmp_path / "result",
    )["result"]
    assert result["metrics"]["RFC"]["checksum"]["mismatched"] == 1
    assert result["metrics"]["RFC"]["checksum"]["matched"] == 6


def validation_package(root):
    records = fixture_records()
    value = "ZAXX010101HDFZZZ07"  # stdnum 2.2 gives check digit 6; deliberately altered.
    texts = ["CURP: " + value, "Cadena de ejercicio: " + value]
    for index, (unit, text) in enumerate(zip(records["units"], texts, strict=True)):
        unit.update(text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
        records["sources"][index]["content_sha256"] = unit["text_sha256"]
    reference = {"pattern": "valid", "structure": "valid", "checksum": "invalid"}
    mention = records["mentions"][0]
    mention.update(entity_type="CURP", start=6, end=24, validity=reference)
    records["mentions"] = [mention]
    records["expectations"] = records["expectations"][:1]
    records["validation_vectors"] = [
        {
            "vector_id": f"v-{index}",
            "unit_id": f"u-{index}",
            "entity_type": "CURP",
            "start": start,
            "end": start + 18,
            "mention_id": "m-1" if index == 1 else None,
            "sensitivity": "sensitive" if index == 1 else "nonpersonal_distractor",
            "validity": reference,
            "provenance": {
                "method": "independent_reference",
                "version": "stdnum-2.2",
                "evidence_ref": "evidence-1",
            },
        }
        for index, start in ((1, 6), (2, 21))
    ]
    manifest, _ = profile_package(root, records, "validation-descriptive-v1", ["CURP"])
    evidence = canonical(
        {
            "tool": "python-stdnum",
            "version": "2.2",
            "algorithm": "CURP weighted check digit",
            "synthetic_prefix": "ZAXX010101HDFZZZ0",
            "expected_digit": "6",
            "altered_digit": "7",
        }
    )
    (root / "evidence.bin").write_bytes(evidence)
    manifest["resources"]["evidence-1"] = {
        "path": "evidence.bin",
        "kind": "binary",
        "sha256": hashlib.sha256(evidence).hexdigest(),
        "bytes": len(evidence),
        "records": 0,
    }
    return manifest, save_manifest(root, manifest)


def test_validation_attributes_are_separate_from_detection_and_reference_sensitivity(tmp_path):
    from deidflow.benchmarks.validation_runner import run_validation_benchmark

    package = tmp_path / "package"
    _, digest = validation_package(package)
    result = run_validation_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="validation-descriptive-v1",
        output=tmp_path / "result",
    )["result"]
    assert result["scope"]["track"] == "validation"
    assert result["metrics"]["CURP"]["checksum"]["matched"] == 2
    assert result["metrics"]["CURP"]["checksum"]["mismatched"] == 0
    assert result["metrics"]["CURP"]["checksum"]["accuracy"] == 1.0
    assert result["metrics"]["CURP"]["structure"]["matched"] == 2
    assert result["reference_sensitivity"] == {"sensitive": 1, "nonpersonal_distractor": 1}
    assert result["reference_evidence_sha256"]
    assert result["quality"] == "DESCRIPTIVE_ONLY"


def test_invalid_candidate_response_does_not_drop_validation_vectors(tmp_path):
    from deidflow.benchmarks.validation_runner import ValidationCandidate, run_validation_benchmark

    package = tmp_path / "package"
    _, digest = validation_package(package)

    def validate(_entity, _value):
        return {"pattern": True, "structure": "valid", "checksum": "invalid"}

    result = run_validation_benchmark(
        package,
        manifest_sha256=digest,
        candidate=ValidationCandidate("candidate-f", "0" * 64, validate),
        profile="validation-descriptive-v1",
        output=tmp_path / "result",
    )["result"]
    assert result["attempt_status"] == "candidate_error"
    assert result["execution"]["required_vectors"] == 2
    assert result["execution"]["failed_vectors"] == 2
    assert result["metrics"]["CURP"] == {"pattern": None, "structure": None, "checksum": None}
    assert result["reference_sensitivity"] == {"sensitive": 1, "nonpersonal_distractor": 1}


@pytest.mark.parametrize(
    "candidate,profile", [("unknown", "validation-descriptive-v1"), ("rules.mx", "unknown")]
)
def test_unsupported_validation_configuration_has_an_explicit_status(tmp_path, candidate, profile):
    from deidflow.benchmarks.validation_runner import run_validation_benchmark

    package = tmp_path / "package"
    _, digest = validation_package(package)
    with pytest.raises(ValueError, match="Unsupported validation benchmark configuration") as error:
        run_validation_benchmark(
            package,
            manifest_sha256=digest,
            candidate=candidate,
            profile=profile,
            output=tmp_path / "result",
        )
    assert error.value.status == "UNSUPPORTED"


def vectors_package(root, cases):
    base = fixture_records()
    records = {
        key: []
        for key in (
            "sources",
            "documents",
            "units",
            "mentions",
            "expectations",
            "validation_vectors",
        )
    }
    records["profile-1"] = base["profile-1"]
    evidence_rows = []
    for index, (entity, value, expected) in enumerate(cases, 1):
        suffix = f"{index:x}"
        text = "Valor ficticio: " + value
        start = len("Valor ficticio: ")
        unit, source, document, mention = (
            deepcopy(base[key][0]) for key in ("units", "sources", "documents", "mentions")
        )
        unit.update(
            unit_id="u-" + suffix,
            case_id="c-" + suffix,
            text=text,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        source.update(source_id="s-" + suffix, content_sha256=unit["text_sha256"])
        document.update(
            case_id="c-" + suffix,
            source_id="s-" + suffix,
            root_document_id="c-" + suffix,
            group_id="g-" + suffix,
            template_family_id="t-" + suffix,
            unit_ids=[unit["unit_id"]],
        )
        reference = dict(zip(("pattern", "structure", "checksum"), expected, strict=True))
        distractor = entity == "PHONE" or (
            entity == "RFC" and value in {"XAXX010101000", "XEXX010101000"}
        )
        mention.update(
            mention_id="m-" + suffix,
            unit_id=unit["unit_id"],
            entity_type=entity,
            start=start,
            end=len(text),
            validity=reference,
        )
        for key, item in (
            ("sources", source),
            ("documents", document),
            ("units", unit),
            ("mentions", mention),
        ):
            if key != "mentions" or not distractor:
                records[key].append(item)
        records["validation_vectors"].append(
            {
                "vector_id": "v-" + suffix,
                "unit_id": unit["unit_id"],
                "entity_type": entity,
                "start": start,
                "end": len(text),
                "mention_id": None if distractor else mention["mention_id"],
                "sensitivity": "nonpersonal_distractor" if distractor else "sensitive",
                "validity": reference,
                "provenance": {
                    "method": "independent_worksheet",
                    "version": "mx-checks-1.0.0",
                    "evidence_ref": "evidence-1",
                },
            }
        )
        evidence_rows.append({"entity": entity, "fictional_value": value, "reference": reference})
    manifest, _ = profile_package(
        root,
        records,
        "validation-descriptive-v1",
        sorted({entity for entity, _value, _expected in cases}),
    )
    manifest["panels"]["known_regression"] = {
        "case_ids": [d["case_id"] for d in records["documents"]],
        "group_ids": [d["group_id"] for d in records["documents"]],
    }
    payload = canonical(
        {
            "reference": "stdnum-2.2 plus independent CLABE reduced-weight worksheet",
            "vectors": evidence_rows,
        }
    )
    (root / "evidence.bin").write_bytes(payload)
    manifest["resources"]["evidence-1"] = {
        "path": "evidence.bin",
        "kind": "binary",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "records": 0,
    }
    return manifest, save_manifest(root, manifest)


@pytest.mark.parametrize(
    "entity,value,expected",
    [
        ("RFC", "ZZZX010101AA1", ("valid", "valid", "valid")),
        ("RFC", "ZZZX010101AA2", ("valid", "valid", "invalid")),
        ("RFC", "ZZZX011301AA4", ("valid", "invalid", "valid")),
        ("RFC", "ZZZ010101AA1", ("valid", "valid", "valid")),
        ("RFC", "XAXX010101000", ("valid", "valid", "invalid")),
        ("RFC", "XEXX010101000", ("valid", "valid", "valid")),
        ("CURP", "ZAXX010101HDFZZZ06", ("valid", "valid", "valid")),
        ("CURP", "ZAXX010231HDFZZZ05", ("valid", "invalid", "valid")),
        ("CURP", "ZAXX010101HDFZZZ07", ("valid", "valid", "invalid")),
        ("CLABE", "002999000000000012", ("valid", "valid", "valid")),
        ("CLABE", "002999000000000013", ("valid", "valid", "invalid")),
        ("PAYMENT_CARD", "9999000011112228", ("valid", "valid", "valid")),
        ("PAYMENT_CARD", "9999000011112229", ("valid", "valid", "invalid")),
        ("RFC", "ZZZX-010101-AA1", ("valid", "valid", "valid")),
        ("CURP", "ZAXX010101HDFZZZ0", ("invalid", "invalid", "unknown")),
        ("PHONE", "0000000000", ("unknown", "unknown", "not_applicable")),
    ],
)
def test_independently_checked_vectors_keep_attribute_states_separate(
    tmp_path, entity, value, expected
):
    from deidflow.benchmarks.validation_runner import run_validation_benchmark

    package = tmp_path / "package"
    _, digest = vectors_package(package, [(entity, value, expected)])
    result = run_validation_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="validation-descriptive-v1",
        output=tmp_path / "result",
    )["result"]
    for attribute, state in zip(("pattern", "structure", "checksum"), expected, strict=True):
        cell = result["metrics"][entity][attribute]
        generic_disagreement = (
            entity == "RFC" and value == "XAXX010101000" and attribute == "checksum"
        )
        assert cell["mismatched"] == int(generic_disagreement)
        if state in {"unknown", "not_applicable"}:
            assert cell["accuracy"] is None
            assert cell["evaluated"] == 0
        else:
            assert cell["matched"] == int(not generic_disagreement)


@pytest.mark.parametrize(
    "damage", ["evidence", "bool_offset", "sensitivity", "validity", "version", "extra"]
)
def test_invalid_validation_reference_never_reaches_the_candidate(tmp_path, damage):
    import json

    from deidflow.benchmarks.validation_runner import run_validation_benchmark

    package = tmp_path / "package"
    manifest, _ = validation_package(package)
    path = package / "validation_vectors.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    row = records[0]
    if damage == "evidence":
        row["provenance"]["evidence_ref"] = "evidence-f"
    elif damage == "bool_offset":
        row["start"] = True
    elif damage == "sensitivity":
        row["sensitivity"] = "nonpersonal_distractor"
    elif damage == "validity":
        row["validity"]["checksum"] = "valid"
    elif damage == "version":
        row["provenance"]["version"] = None
    else:
        row["private-canary@example.test"] = "not allowed"
    payload = b"".join(canonical(row) + b"\n" for row in records)
    path.write_bytes(payload)
    manifest["resources"]["validation_vectors"].update(
        sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload)
    )
    digest = save_manifest(package, manifest)
    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_validation_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="validation-descriptive-v1",
            output=tmp_path / "result",
        )
    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not (tmp_path / "result").exists()
