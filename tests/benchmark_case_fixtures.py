"""Local fictional packages shared by benchmark seam tests."""

from test_benchmark_package import canonical, fixture_records, save_manifest, write_fixture


def profile_package(root, records, profile, labels):
    records["profile-1"]["profile_id"] = profile
    for expectation in records["expectations"]:
        expectation["profile_id"] = profile
    manifest, _ = write_fixture(root, records)
    manifest["profiles"] = {profile: manifest["profiles"]["email-descriptive-v1"]}
    manifest["scope"]["entity_types"] = labels
    for coverage in manifest["annotation_coverage"]:
        coverage["exhaustive_entity_types"] = labels
    return manifest, save_manifest(root, manifest)


__all__ = ["canonical", "fixture_records", "profile_package", "save_manifest"]
