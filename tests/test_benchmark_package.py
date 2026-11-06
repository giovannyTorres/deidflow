from __future__ import annotations

import hashlib
import json
import stat
import warnings
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile, ZipInfo

import pytest


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def fixture_records():
    texts = ["Correo: a.b@example.test.", "No hay datos de contacto."]
    units = [
        {
            "unit_id": f"u-{index}",
            "case_id": f"c-{index}",
            "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "content_role": "body",
            "locator": {"kind": "text", "index": 0},
        }
        for index, text in enumerate(texts, 1)
    ]
    sources = [
        {
            "source_id": f"s-{index}",
            "revision": "1.0.0",
            "content_sha256": unit["text_sha256"],
            "origin_kind": "synthetic",
            "language": "es",
            "country": "MX",
            "domain": "general",
            "origin_reference": None,
            "terms_reference": None,
            "license": "Apache-2.0",
            "attribution": "DeidFlow: fixture ficticio original",
            "permissions": dict.fromkeys(
                ["evaluation", "annotation", "derivation", "training", "redistribution"], True
            ),
            "permission_review": {
                "status": "synthetic_fixture",
                "evidence_ref": None,
                "reviewed_at": "2026-11-06T00:00:00Z",
            },
            "personal_data_status": "fictional",
            "exposure": {
                "training": "unknown",
                "tuning": "unknown",
                "prior_evaluation": True,
                "candidate_exposure": "known",
            },
        }
        for index, unit in enumerate(units, 1)
    ]
    documents = [
        {
            "case_id": f"c-{index}",
            "source_id": f"s-{index}",
            "root_document_id": f"c-{index}",
            "group_id": f"g-{index}",
            "template_family_id": f"t-{index}",
            "parent_case_id": None,
            "variant_id": None,
            "partition": None,
            "panel": "known_regression",
            "format": "text",
            "strata": ["standard"],
            "capabilities_required": ["text_detection"],
            "artifact_ref": None,
            "artifact_sha256": None,
            "unit_ids": [f"u-{index}"],
            "perturbation_recipe": None,
            "annotation_state": "draft",
        }
        for index in (1, 2)
    ]
    mentions = [
        {
            "mention_id": f"m-{index}",
            "unit_id": "u-1",
            "entity_type": "EMAIL",
            "start": start,
            "end": 24,
            "region_ref": None,
            "certainty": "confirmed",
            "validity": dict.fromkeys(["pattern", "structure", "checksum"], "unknown"),
            "sensitivity_reference": "synthetic_sensitive_identifier",
            "entity_id": None,
            "identity_evidence": None,
            "annotation_provenance": {
                "method": "synthetic_fixture",
                "manual_version": "1.0.0",
                "reviews": [],
            },
        }
        for index, start in enumerate((8, 10), 1)
    ]
    expectations = [
        {
            "expectation_id": f"e-{index}",
            "profile_id": "email-descriptive-v1",
            "case_id": "c-1",
            "mention_id": f"m-{index}",
            "unit_id": None,
            "start": None,
            "end": None,
            "action": "remove",
            "allowed_operators": ["placeholder"],
            "verification": "complete_removal",
            "coverage_required": "complete",
            "acceptable_release_states": ["REVIEW_REQUIRED"],
        }
        for index in (1, 2)
    ]
    return {
        "sources": sources,
        "documents": documents,
        "units": units,
        "mentions": mentions,
        "expectations": expectations,
        "profile-1": {
            "profile_id": "email-descriptive-v1",
            "ratified": False,
            "clinical_policy": "not_evaluated",
            "quasi_identifier_policy": "not_evaluated",
            "precedence": [],
        },
    }


def write_fixture(root: Path, records=None):
    root.mkdir(exist_ok=True)
    records = fixture_records() if records is None else records
    resources = {}
    for role, value in records.items():
        kind = "jsonl" if isinstance(value, list) else "json"
        payload = (
            b"".join(canonical(row) + b"\n" for row in value)
            if kind == "jsonl"
            else canonical(value)
        )
        name = role + (".jsonl" if kind == "jsonl" else ".json")
        (root / name).write_bytes(payload)
        resources[role] = {
            "path": name,
            "kind": kind,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "records": len(value) if kind == "jsonl" else 1,
        }
    manifest = {
        "schema_version": "df-eval-mx.package.v1",
        "dataset_version": "1.0.0",
        "taxonomy_version": "df-eval-mx.taxonomy.v1",
        "annotation_version": "df-eval-mx.annotation.v1",
        "dataset_id": "d-1",
        "created_at": "2026-11-06T00:00:00Z",
        "resources": resources,
        "partitions": {
            name: {"case_ids": [], "group_ids": []}
            for name in ("train", "validation", "calibration", "blind_test")
        },
        "panels": {
            "known_regression": {"case_ids": ["c-1", "c-2"], "group_ids": ["g-1", "g-2"]},
            "external_transfer": {"case_ids": [], "group_ids": []},
        },
        "scope": {
            "language": "es",
            "country": "MX",
            "entity_types": ["EMAIL"],
            "formats": ["text"],
            "required_strata": ["standard"],
            "optional_strata": [],
        },
        "profiles": {
            "email-descriptive-v1": {
                "resource": "profile-1",
                "sha256": resources["profile-1"]["sha256"],
            }
        },
        "generation": {
            "generator_version": "fixture-v1",
            "random_algorithm": "none",
            "seeds": {},
            "resources": [],
            "perturbation_rules": [],
        },
        "freeze": {
            "status": "unfrozen",
            "frozen_at": None,
            "resource_sha256": {},
            "exposure": "known_regression",
            "custody": None,
        },
        "annotation_coverage": [
            {
                "unit_id": unit["unit_id"],
                "exhaustive_entity_types": ["EMAIL"],
                "inspected_ranges": [
                    {"start": 0, "end": len(unit["text"]) if isinstance(unit["text"], str) else 0}
                ],
                "limitations": [],
            }
            for unit in records["units"]
        ],
    }
    return manifest, save_manifest(root, manifest)


def save_manifest(root: Path, manifest) -> str:
    payload = canonical(manifest)
    (root / "manifest.json").write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_versioned_package_preserves_overlapping_mentions_through_the_real_detector(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "package"
    _, digest = write_fixture(package)
    output = tmp_path / "result"

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=output,
    )

    assert report == json.loads((output / "report.json").read_text())
    result = report["result"]
    assert result["admission"] == {
        "status": "valid",
        "sources": 2,
        "documents": 2,
        "units": 2,
        "mentions": 2,
        "expectations": 2,
    }
    assert result["attempt_status"] == "completed"
    assert result["quality"] == "DESCRIPTIVE_ONLY"
    assert result["metrics"]["EMAIL"] == {
        "true_positives": 1,
        "false_positives": 0,
        "false_negatives": 1,
        "support": 2,
        "precision": 1.0,
        "recall": 0.5,
        "f1": 2 / 3,
    }


@pytest.mark.parametrize(
    "damage", ["sha256", "bytes", "records", "changed_byte", "manifest_digest"]
)
def test_integrity_failures_reject_the_entire_package_before_reporting(tmp_path, damage):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "private-canary@example.test"
    manifest, digest = write_fixture(package)
    if damage in {"sha256", "bytes", "records"}:
        manifest["resources"]["units"][damage] = "0" * 64 if damage == "sha256" else 1
        digest = save_manifest(package, manifest)
    elif damage == "changed_byte":
        units = package / "units.jsonl"
        units.write_bytes(units.read_bytes().replace(b"a.b@", b"z.b@"))
    else:
        digest = "0" * 64
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "df-eval-mx.package.v999"),
        ("taxonomy_version", "unknown"),
        ("annotation_version", "unknown"),
        ("dataset_version", "private-canary@example.test"),
        ("dataset_id", "private-canary@example.test"),
        ("created_at", "2026-11-06T10:00:00"),
        ("scope", None),
        ("unknown", "private-canary@example.test"),
    ],
)
def test_unknown_or_invalid_manifest_contracts_cannot_reach_a_report(tmp_path, field, value):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "package"
    manifest, _ = write_fixture(package)
    manifest[field] = value
    digest = save_manifest(package, manifest)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize("surface", ["manifest", "resource"])
@pytest.mark.parametrize(
    "damage", ["duplicate", "nan", "infinity", "overflow", "surrogate", "utf8", "bom"]
)
def test_json_is_strict_on_every_input_surface(tmp_path, surface, damage):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "package"
    manifest, _ = write_fixture(package)
    path = package / ("manifest.json" if surface == "manifest" else "sources.jsonl")
    payload = path.read_bytes()
    if damage == "duplicate":
        payload = payload.replace(
            b'"dataset_version":' if surface == "manifest" else b'"attribution":',
            b'"dataset_version":"0.0.0","dataset_version":'
            if surface == "manifest"
            else b'"attribution":"private-canary@example.test","attribution":',
            1,
        )
    elif damage in {"nan", "infinity", "overflow", "surrogate"}:
        token = {
            "nan": b"NaN",
            "infinity": b"Infinity",
            "overflow": b"1e999",
            "surrogate": b'"\\ud800"',
        }[damage]
        if surface == "manifest":
            payload = payload.replace(b'"custody":null', b'"custody":' + token, 1)
        else:
            payload = payload.replace(b'"origin_reference":null', b'"origin_reference":' + token, 1)
    elif damage == "utf8":
        payload += b"\xff"
    else:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)
    if surface == "resource":
        manifest["resources"]["sources"]["sha256"] = hashlib.sha256(payload).hexdigest()
        manifest["resources"]["sources"]["bytes"] = len(payload)
        digest = save_manifest(package, manifest)
    else:
        digest = hashlib.sha256(payload).hexdigest()
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "private-canary@example.test"),
        ("revision", "unknown"),
        ("content_sha256", "wrong"),
        ("origin_kind", "personal"),
        ("license", "unknown"),
        ("permissions", {"evaluation": False}),
        ("permission_review", {"status": "unreviewed", "evidence_ref": None}),
        ("personal_data_status", "uncertain"),
        ("exposure", {"training": False}),
        ("unknown", True),
    ],
)
def test_source_contract_and_permission_failures_are_not_accepted(tmp_path, field, value):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    records["sources"][0][field] = value
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize(
    "role,field,value",
    [
        ("documents", "case_id", "private-canary@example.test"),
        ("documents", "group_id", None),
        ("documents", "template_family_id", "unknown"),
        ("documents", "partition", "blind_test"),
        ("documents", "annotation_state", "approved"),
        ("documents", "unit_ids", ["u-1", "u-1"]),
        ("units", "text_sha256", "0" * 64),
        ("units", "text", True),
        ("units", "locator", {"kind": "text", "index": True}),
        ("units", "content_role", "unknown"),
    ],
)
def test_document_and_unit_contracts_preserve_original_coordinates(tmp_path, role, field, value):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    records[role][0][field] = value
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize(
    "role,field,value",
    [
        ("mentions", "start", True),
        ("mentions", "end", 1000),
        ("mentions", "start", -1),
        ("mentions", "end", 8),
        ("mentions", "entity_type", "UNKNOWN"),
        ("mentions", "certainty", "guessed"),
        ("mentions", "validity", {"checksum": "valid"}),
        ("mentions", "sensitivity_reference", None),
        ("mentions", "annotation_provenance", {}),
        ("expectations", "action", "upload"),
        ("expectations", "allowed_operators", ["unknown"]),
        ("expectations", "acceptable_release_states", ["success"]),
        ("expectations", "start", 0),
        ("profile-1", "ratified", True),
        ("profile-1", "unknown", "private-canary@example.test"),
    ],
)
def test_mentions_profiles_and_expectations_have_explicit_contracts(tmp_path, role, field, value):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    (records[role] if role == "profile-1" else records[role][0])[field] = value
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not output.exists()


@pytest.mark.parametrize(
    "container,path,value",
    [
        ("records", ("documents", 0, "source_id"), "s-fff"),
        ("records", ("documents", 0, "root_document_id"), "c-fff"),
        ("records", ("documents", 0, "unit_ids"), ["u-fff"]),
        ("records", ("units", 0, "case_id"), "c-2"),
        ("records", ("sources", 0, "content_sha256"), "0" * 64),
        ("records", ("expectations", 0, "case_id"), "c-2"),
        ("manifest", ("panels", "known_regression", "case_ids"), ["c-1"]),
        ("manifest", ("panels", "known_regression", "group_ids"), ["g-fff"]),
        ("manifest", ("annotation_coverage", 0, "unit_id"), "u-fff"),
        ("manifest", ("annotation_coverage", 0, "exhaustive_entity_types"), ["PERSON"]),
        ("manifest", ("annotation_coverage", 0, "inspected_ranges"), [{"start": 0, "end": 1000}]),
        ("manifest", ("freeze", "status"), "frozen"),
        ("manifest", ("generation", "resources"), ["missing"]),
    ],
)
def test_broken_relations_are_rejected_as_dataset_errors(tmp_path, container, path, value):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "package"
    records = fixture_records()
    manifest, _ = write_fixture(package, records)
    target = records if container == "records" else manifest
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    if container == "records":
        manifest, _ = write_fixture(package, records)
    digest = save_manifest(package, manifest)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert not output.exists()


@pytest.mark.parametrize(
    "damage", ["duplicate_mention", "contradiction", "lineage_cycle", "cross_partition_group"]
)
def test_duplicated_or_contradictory_annotations_do_not_get_scores(tmp_path, damage):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    if damage == "duplicate_mention":
        records["mentions"].append({**records["mentions"][0], "mention_id": "m-3"})
    elif damage == "contradiction":
        records["expectations"][0].update(
            action="preserve", allowed_operators=["keep"], verification="exact_preservation"
        )
    elif damage == "lineage_cycle":
        records["documents"][0].update(
            parent_case_id="c-1",
            variant_id="v-1",
            perturbation_recipe={
                "version": "1.0.0",
                "operation": "format",
                "seed": 1,
                "parameters": {},
            },
        )
    else:
        for document, partition in zip(records["documents"], ("train", "blind_test"), strict=True):
            document.update(panel=None, partition=partition, group_id="g-1")
    package = tmp_path / "package"
    manifest, digest = write_fixture(package, records)
    if damage == "cross_partition_group":
        manifest["panels"]["known_regression"] = {"case_ids": [], "group_ids": []}
        manifest["partitions"]["train"] = {"case_ids": ["c-1"], "group_ids": ["g-1"]}
        manifest["partitions"]["blind_test"] = {"case_ids": ["c-2"], "group_ids": ["g-1"]}
        digest = save_manifest(package, manifest)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert not output.exists()


def test_a_zip_package_and_a_directory_produce_identical_results_without_extraction(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "package"
    _, digest = write_fixture(package)
    archive = tmp_path / "private-canary@example.test.zip"
    with ZipFile(archive, "w") as stream:
        for member in package.iterdir():
            stream.write(member, member.name)
    directory = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=tmp_path / "directory-result",
    )
    zipped = run_package_benchmark(
        archive,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=tmp_path / "zip-result",
    )

    assert directory["result"] == zipped["result"]
    assert not (tmp_path / "extracted").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "traversal",
        "absolute",
        "backslash",
        "escaped_link",
        "zip_duplicate",
        "zip_traversal",
        "zip_link",
    ],
)
def test_references_and_archive_members_cannot_escape_or_hide_duplicates(tmp_path, damage):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "package"
    manifest, digest = write_fixture(package)
    target = package
    if damage in {"traversal", "absolute", "backslash"}:
        external = tmp_path / "private-canary@example.test"
        external.write_bytes((package / "units.jsonl").read_bytes())
        manifest["resources"]["units"]["path"] = {
            "traversal": "../private-canary@example.test",
            "absolute": str(external),
            "backslash": "..\\private-canary@example.test",
        }[damage]
        digest = save_manifest(package, manifest)
    elif damage == "escaped_link":
        units = package / "units.jsonl"
        external = tmp_path / "private-canary@example.test"
        units.replace(external)
        units.symlink_to(external)
    else:
        target = tmp_path / "input.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(target, "w") as stream:
                for member in package.iterdir():
                    stream.write(member, member.name)
                if damage == "zip_duplicate":
                    stream.writestr("units.jsonl", (package / "units.jsonl").read_bytes())
                elif damage == "zip_traversal":
                    stream.writestr("../private-canary@example.test", "never extract this")
                else:
                    info = ZipInfo("private-canary@example.test")
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    stream.writestr(info, "../outside")
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            target,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)
    assert not output.exists()


def test_binary_evidence_is_hash_checked_but_never_executed(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    records["sources"][0]["permission_review"]["evidence_ref"] = "evidence-1"
    package = tmp_path / "package"
    manifest, _ = write_fixture(package, records)
    payload = b'raise RuntimeError("private-canary@example.test: must never execute")\n'
    (package / "evidence.bin").write_bytes(payload)
    manifest["resources"]["evidence-1"] = {
        "path": "evidence.bin",
        "kind": "binary",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "records": 0,
    }
    digest = save_manifest(package, manifest)

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    assert report["result"]["admission"]["status"] == "valid"
    assert "canary" not in json.dumps(report)


def test_unknown_resource_contracts_do_not_become_an_unversioned_extension(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    records["unknown"] = {"private-canary@example.test": "not a contract"}
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=tmp_path / "result",
        )

    assert error.value.status == "INVALID_RUN"


@pytest.mark.parametrize(
    "damage", ["bool_offset", "outside", "score", "confidence", "shape", "exception"]
)
def test_malformed_candidate_responses_remain_errors_with_their_required_support(
    tmp_path, damage, capsys, caplog
):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark

    package = tmp_path / "package"
    _, digest = write_fixture(package)

    def detect(text):
        if not text.startswith("Correo:"):
            return []
        if damage == "exception":
            raise RuntimeError("private-canary@example.test")
        response = SimpleNamespace(entity_type="EMAIL", start=8, end=24, score=0.9, confidence=None)
        if damage == "bool_offset":
            response.start = True
        elif damage == "outside":
            response.end = 1000
        elif damage == "score":
            response.score = float("nan")
        elif damage == "confidence":
            response.confidence = float("inf")
        elif damage == "shape":
            return {"private-canary@example.test": "not predictions"}
        return [response]

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate=DetectionCandidate("candidate-1", "0" * 64, detect),
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    result = report["result"]
    assert result["admission"]["status"] == "valid"
    assert result["attempt_status"] == "candidate_error"
    assert result["metrics"]["EMAIL"] is None
    assert result["execution"] == {
        "required_documents": 2,
        "completed_documents": 1,
        "failed_documents": 1,
        "required_units": 2,
        "completed_units": 1,
        "failed_units": 1,
        "required_mentions": 2,
    }
    assert result["diagnostics"] == [{"code": "CANDIDATE_ERROR", "count": 1}]
    captured = capsys.readouterr()
    assert "canary" not in json.dumps(report) + captured.out + captured.err + caplog.text


def test_invalid_data_is_rejected_before_a_candidate_can_mask_the_error(tmp_path):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark

    package = tmp_path / "package"
    manifest, _ = write_fixture(package)
    manifest["resources"]["units"]["sha256"] = "0" * 64
    digest = save_manifest(package, manifest)

    def detect(_text):
        raise RuntimeError("private-canary@example.test")

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate=DetectionCandidate("candidate-1", "0" * 64, detect),
            profile="email-descriptive-v1",
            output=tmp_path / "result",
        )

    assert error.value.status == "INVALID_RUN"


def test_training_cases_are_validated_but_excluded_from_the_regression_panel(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    records["documents"][1].update(partition="train", panel=None)
    package = tmp_path / "package"
    manifest, _ = write_fixture(package, records)
    manifest["panels"]["known_regression"] = {"case_ids": ["c-1"], "group_ids": ["g-1"]}
    manifest["partitions"]["train"] = {"case_ids": ["c-2"], "group_ids": ["g-2"]}
    digest = save_manifest(package, manifest)

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    assert report["result"]["admission"]["documents"] == 2
    assert report["result"]["execution"]["required_documents"] == 1
    assert report["result"]["execution"]["required_units"] == 1


@pytest.mark.parametrize("limitation", ["partial_coverage", "ambiguous", "scope", "profile_absent"])
def test_valid_but_unsupported_evaluations_do_not_turn_into_favorable_metrics(tmp_path, limitation):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    if limitation == "ambiguous":
        records["mentions"][0]["certainty"] = "ambiguous"
    elif limitation == "profile_absent":
        records["profile-1"]["profile_id"] = "other-descriptive-v1"
        for expectation in records["expectations"]:
            expectation["profile_id"] = "other-descriptive-v1"
    package = tmp_path / "package"
    manifest, _ = write_fixture(package, records)
    if limitation == "partial_coverage":
        manifest["annotation_coverage"][0].update(
            exhaustive_entity_types=[],
            inspected_ranges=[{"start": 8, "end": 24}],
            limitations=["PARTIAL_INSPECTION"],
        )
    elif limitation == "scope":
        manifest["scope"]["entity_types"].append("PERSON")
    elif limitation == "profile_absent":
        manifest["profiles"] = {
            "other-descriptive-v1": manifest["profiles"]["email-descriptive-v1"]
        }
    digest = save_manifest(package, manifest)
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Unsupported EMAIL evaluation configuration") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=output,
        )

    assert error.value.status == "UNSUPPORTED"
    assert not output.exists()


@pytest.mark.parametrize(
    "variant", ["crossed", "unicode_crlf", "explicit_precedence", "derived_case"]
)
def test_legitimate_annotation_and_lineage_variants_still_reach_descriptive_metrics(
    tmp_path, variant
):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    if variant in {"crossed", "unicode_crlf"}:
        unit = records["units"][0]
        unit["text"] = (
            "Correo: a@b.test.c@d.test."
            if variant == "crossed"
            else "😀 Café\r\nCorreo: a.b@example.test."
        )
        unit["text_sha256"] = hashlib.sha256(unit["text"].encode()).hexdigest()
        records["sources"][0]["content_sha256"] = unit["text_sha256"]
        coordinates = [(8, 18), (10, 25)] if variant == "crossed" else [(16, 32), (18, 32)]
        for mention, (start, end) in zip(records["mentions"], coordinates, strict=True):
            mention.update(start=start, end=end)
    elif variant == "explicit_precedence":
        records["expectations"][0].update(
            action="preserve", allowed_operators=["keep"], verification="exact_preservation"
        )
        records["profile-1"]["precedence"] = ["preserve", "remove"]
    else:
        records["documents"][1].update(
            root_document_id="c-1",
            parent_case_id="c-1",
            variant_id="v-1",
            group_id="g-1",
            template_family_id="t-1",
            perturbation_recipe={
                "version": "1.0.0",
                "operation": "fixture_variant",
                "seed": 1,
                "parameters": {},
            },
        )
    package = tmp_path / "package"
    manifest, digest = write_fixture(package, records)
    if variant == "derived_case":
        manifest["panels"]["known_regression"]["group_ids"] = ["g-1"]
        digest = save_manifest(package, manifest)

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    assert report["result"]["admission"]["mentions"] == 2
    assert report["result"]["metrics"]["EMAIL"]["true_positives"] == 1
    assert report["result"]["metrics"]["EMAIL"]["false_negatives"] == 1
    assert report["result"]["quality"] == "DESCRIPTIVE_ONLY"


def test_a_document_may_contain_multiple_text_units(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    text = "Texto ficticio adicional."
    records["units"].append(
        {
            "unit_id": "u-3",
            "case_id": "c-1",
            "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "content_role": "body",
            "locator": {"kind": "text", "index": 1},
        }
    )
    records["documents"][0]["unit_ids"].append("u-3")
    digest = hashlib.sha256()
    for unit in (records["units"][0], records["units"][2]):
        name, content = unit["unit_id"].encode(), unit["text"].encode()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(content).to_bytes(8, "big") + content)
    records["sources"][0]["content_sha256"] = digest.hexdigest()
    package = tmp_path / "package"
    _, trusted = write_fixture(package, records)

    report = run_package_benchmark(
        package,
        manifest_sha256=trusted,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    assert report["result"]["execution"]["required_documents"] == 2
    assert report["result"]["execution"]["required_units"] == 3
    assert report["result"]["execution"]["completed_units"] == 3
    assert report["result"]["metrics"]["EMAIL"]["support"] == 2


@pytest.mark.parametrize(
    "candidate,profile",
    [("private-canary@example.test", "email-descriptive-v1"), ("rules.mx", "unknown")],
)
def test_unsupported_selectors_have_a_safe_explicit_status(tmp_path, candidate, profile):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    package = tmp_path / "package"
    _, digest = write_fixture(package)
    with pytest.raises(ValueError, match="Unsupported EMAIL evaluation configuration") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate=candidate,
            profile=profile,
            output=tmp_path / "result",
        )

    assert error.value.status == "UNSUPPORTED"
    assert "canary" not in str(error.value)


@pytest.mark.parametrize("bad_hash", [False, True])
def test_native_artifact_references_are_validated_before_declaring_the_track_unsupported(
    tmp_path, bad_hash
):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    payload = b"fictional native payload; not a claim of valid DOCX"
    artifact_hash = hashlib.sha256(payload).hexdigest()
    records["documents"][0].update(
        format="docx",
        artifact_ref="artifact-1",
        artifact_sha256="0" * 64 if bad_hash else artifact_hash,
    )
    package = tmp_path / "package"
    manifest, _ = write_fixture(package, records)
    (package / "artifact.bin").write_bytes(payload)
    manifest["scope"]["formats"].append("docx")
    manifest["resources"]["artifact-1"] = {
        "path": "artifact.bin",
        "kind": "binary",
        "sha256": artifact_hash,
        "bytes": len(payload),
        "records": 0,
    }
    digest = save_manifest(package, manifest)

    expected_message = (
        "Invalid evaluation package" if bad_hash else "Unsupported EMAIL evaluation configuration"
    )
    with pytest.raises(ValueError, match=expected_message) as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=tmp_path / "result",
        )

    assert error.value.status == ("INVALID_RUN" if bad_hash else "UNSUPPORTED")


def test_shipped_package_is_reproducible_offline_and_omits_source_values(tmp_path, capsys, caplog):
    from deidflow.benchmarks.package_runner import run_package_benchmark
    from deidflow.benchmarks.runner import offline_network

    package = Path(__file__).resolve().parents[1] / "examples" / "benchmark-mx-package"
    trusted = "7fd7f5a4808a85b3c73c9561c82b40eb06e91f9dd2e4c8165bc3b7b4bc8ddeb8"
    with offline_network() as network:
        first = run_package_benchmark(
            package,
            manifest_sha256=trusted,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=tmp_path / "first",
        )
        second = run_package_benchmark(
            package,
            manifest_sha256=trusted,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=tmp_path / "second",
        )

    assert network["attempts"] == 0
    assert first["result"] == second["result"]
    assert first["result"]["metrics"]["EMAIL"]["support"] == 2
    captured = capsys.readouterr()
    emitted = json.dumps([first, second]) + captured.out + captured.err + caplog.text
    for forbidden in (
        "a.b@example.test",
        "No hay datos de contacto.",
        str(package),
        "manifest.json",
        "units.jsonl",
        '"c-1"',
        '"u-1"',
    ):
        assert forbidden not in emitted


def test_permission_review_preserves_an_explicit_utc_date(tmp_path):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    for source in records["sources"]:
        source["permission_review"]["reviewed_at"] = "2026-11-06T00:00:00Z"
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate="rules.mx",
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    assert report["result"]["admission"]["status"] == "valid"


def test_exact_scoring_deduplicates_predictions_without_rescuing_partial_boundaries(tmp_path):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark
    from deidflow.core import Finding

    package = tmp_path / "package"
    _, digest = write_fixture(package)

    def detect(text):
        return (
            [
                Finding("EMAIL", 8, 24, 0.9, "fixture"),
                Finding("EMAIL", 8, 24, 0.9, "fixture"),
                Finding("EMAIL", 8, 23, 0.9, "fixture"),
            ]
            if text.startswith("Correo:")
            else []
        )

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate=DetectionCandidate("candidate-f", "0" * 64, detect),
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    assert report["result"]["metrics"]["EMAIL"] == {
        "true_positives": 1,
        "false_positives": 1,
        "false_negatives": 1,
        "support": 2,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }


def test_thousands_of_valid_crossed_mentions_do_not_require_recursive_overlap_matching(tmp_path):
    from deidflow.benchmarks.package_runner import DetectionCandidate, run_package_benchmark
    from deidflow.core import Finding

    records = fixture_records()
    text = "a" * 2102
    records["units"][0].update(text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
    records["sources"][0]["content_sha256"] = records["units"][0]["text_sha256"]
    template = records["mentions"][0]
    records["mentions"] = [
        {**template, "mention_id": f"m-{index + 1}", "start": index, "end": index + 2}
        for index in range(2100)
    ]
    records["expectations"] = []
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)

    def detect(source):
        return (
            [Finding("EMAIL", index, index + 2, 0.9, "fixture") for index in range(2100)]
            if source.startswith("aa")
            else []
        )

    report = run_package_benchmark(
        package,
        manifest_sha256=digest,
        candidate=DetectionCandidate("candidate-f", "0" * 64, detect),
        profile="email-descriptive-v1",
        output=tmp_path / "result",
    )

    assert report["result"]["attempt_status"] == "completed"
    assert report["result"]["metrics"]["EMAIL"] == {
        "true_positives": 2100,
        "false_positives": 0,
        "false_negatives": 0,
        "support": 2100,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }


@pytest.mark.parametrize("date", ["missing", "2026-11-06T00:00:00", "private-canary@example.test"])
def test_permission_review_requires_a_valid_utc_date(tmp_path, date):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    if date == "missing":
        records["sources"][0]["permission_review"].pop("reviewed_at", None)
    else:
        records["sources"][0]["permission_review"]["reviewed_at"] = date
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=tmp_path / "result",
        )

    assert error.value.status == "INVALID_RUN"
    assert "canary" not in str(error.value)


@pytest.mark.parametrize(
    "action,operator,verification",
    [
        ("remove", "keep", "complete_removal"),
        ("preserve", "placeholder", "exact_preservation"),
        ("generalize", "keep", "unverifiable"),
    ],
)
def test_an_operator_cannot_contradict_its_own_required_action(
    tmp_path, action, operator, verification
):
    from deidflow.benchmarks.package_runner import run_package_benchmark

    records = fixture_records()
    for expectation in records["expectations"]:
        expectation.update(action=action, allowed_operators=[operator], verification=verification)
    package = tmp_path / "package"
    _, digest = write_fixture(package, records)

    with pytest.raises(ValueError, match="Invalid evaluation package") as error:
        run_package_benchmark(
            package,
            manifest_sha256=digest,
            candidate="rules.mx",
            profile="email-descriptive-v1",
            output=tmp_path / "result",
        )

    assert error.value.status == "INVALID_RUN"
