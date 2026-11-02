"""Explicit Windows source build of pinned, patched Tesseract 5.5.4.

Requires local CMake, Ninja, UCRT GCC/G++, bsdtar with zstd, and certifi for
download CA trust. Uses docs/ocr-build-lock.json; does not modify PATH/registry.
No part of this development installer is called during inference.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

BUILD_OPTIONS = {
    "CMAKE_BUILD_TYPE": "Release",
    "BUILD_TRAINING_TOOLS": "OFF",
    "BUILD_TESTS": "OFF",
    "GRAPHICS_DISABLED": "ON",
    "DISABLED_LEGACY_ENGINE": "ON",
    "DISABLE_ARCHIVE": "ON",
    "DISABLE_CURL": "ON",
    "OPENMP_BUILD": "OFF",
    "BUILD_SHARED_LIBS": "ON",
    "ENABLE_NATIVE": "OFF",
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(url: str, target: Path, expected: str, tls: ssl.SSLContext) -> Path:
    if not target.exists():
        request = urllib.request.Request(
            url, headers={"User-Agent": "DeidFlow-explicit-local-build"}
        )
        with (
            urllib.request.urlopen(request, timeout=90, context=tls) as response,
            target.open("xb") as stream,
        ):
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
    if digest(target) != expected:
        raise RuntimeError("Pinned local build asset digest mismatch")
    return target


def checked_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and digest(target) != digest(source):
        raise RuntimeError("Existing installation differs; choose a new destination")
    if not target.exists():
        shutil.copyfile(source, target)


def run(arguments: list[str], *, timeout: int = 1200) -> str:
    result = subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return result.stdout


def install(destination: Path, work_dir: Path, bsdtar: str, workers: int) -> dict[str, Any]:
    if os.name != "nt" or not 1 <= workers <= 16:
        raise ValueError("The pinned build targets Windows x64 and 1-16 build workers")
    try:
        import certifi
    except ImportError:
        raise RuntimeError(
            "Install certifi in the development environment for verified TLS"
        ) from None
    tls = ssl.create_default_context(cafile=certifi.where())
    repository = Path(__file__).resolve().parents[1]
    lock = json.loads((repository / "docs/ocr-build-lock.json").read_text(encoding="utf-8"))
    destination, work_dir = destination.resolve(), work_dir.resolve()
    cache, deps, sources, build = [
        work_dir / name
        for name in ("ocr554-packages", "ocr554-deps", "ocr554-source", "ocr554-build")
    ]
    for directory in (cache, deps, sources, destination):
        directory.mkdir(parents=True, exist_ok=True)

    def package(record: dict[str, Any]) -> Path:
        return fetch(record["source"], cache / record["filename"], record["sha256"], tls)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, 4)) as pool:
        archives = list(pool.map(package, lock["packages"]))
    for archive in archives:
        run([bsdtar, "-xf", str(archive), "-C", str(deps)])
    source_archive = fetch(
        lock["source_archive"], cache / "tesseract-5.5.4.tar.gz", lock["source_sha256"], tls
    )
    source = sources / ("tesseract-" + lock["source_commit"])
    with tarfile.open(source_archive, "r:gz") as archive:
        if not source.exists():
            archive.extractall(sources, filter="data")
        for item in archive.getmembers():
            if item.isfile():
                original = archive.extractfile(item)
                if original is None or hashlib.sha256(original.read()).hexdigest() != digest(
                    sources / item.name
                ):
                    raise RuntimeError("Source tree differs from the pinned upstream archive")
    prefix = deps / "ucrt64"
    arguments = [
        "cmake",
        "-S",
        str(source),
        "-B",
        str(build),
        "-G",
        "Ninja",
        f"-DCMAKE_INSTALL_PREFIX={destination.as_posix()}",
        f"-DCMAKE_PREFIX_PATH={prefix.as_posix()}",
    ]
    arguments += [f"-D{name}={value}" for name, value in BUILD_OPTIONS.items()]
    configure = run(arguments)
    build_output = run(["cmake", "--build", str(build), "--parallel", str(workers)])
    run(["cmake", "--install", str(build)])
    for library in (prefix / "bin").glob("*.dll"):
        checked_copy(library, destination / "bin" / library.name)
    data = destination / "share/tessdata"
    for model in lock["models"]:
        url = f"https://raw.githubusercontent.com/{lock['model_repository']}/{lock['model_commit']}/{model['name']}"
        asset = fetch(url, cache / model["name"], model["sha256"], tls)
        checked_copy(asset, data / model["name"])
    if (prefix / "share/licenses").exists():
        shutil.copytree(
            prefix / "share/licenses", destination / "share/licenses", dirs_exist_ok=True
        )
    checked_copy(source / "LICENSE", destination / "share/licenses/tesseract/LICENSE")
    license_url = f"https://raw.githubusercontent.com/{lock['model_repository']}/{lock['model_commit']}/LICENSE"
    license_target = data / "LICENSE.tessdata_fast"
    if not license_target.exists():
        with urllib.request.urlopen(license_url, timeout=60, context=tls) as response:
            license_target.write_bytes(response.read())
    executable = destination / "bin/tesseract.exe"
    version = run([str(executable), "--version"], timeout=15)
    if version.splitlines()[0] != "tesseract 5.5.4":
        raise RuntimeError("Built OCR version does not match the pinned source")
    languages = run([str(executable), "--list-langs", "--tessdata-dir", str(data)], timeout=15)
    if not all(name in languages.splitlines() for name in ("spa", "eng")):
        raise RuntimeError("Built OCR lacks required local languages")
    binaries = [
        {
            "path": p.relative_to(destination).as_posix(),
            "sha256": digest(p),
            "bytes": p.stat().st_size,
        }
        for p in sorted((destination / "bin").iterdir())
        if p.suffix.lower() in {".dll", ".exe"}
    ]
    manifest = {
        "engine": "tesseract",
        "version": "5.5.4",
        "source_commit": lock["source_commit"],
        "source_sha256": lock["source_sha256"],
        "source_archive": lock["source_archive"],
        "tag_verification": lock["tag_verification"],
        "languages": ["spa", "eng"],
        "runtime_relative_path": "bin/tesseract.exe",
        "data_relative_path": "share/tessdata",
        "runtime_sha256": digest(executable),
        "models": lock["models"],
        "model_repository": lock["model_repository"],
        "model_commit": lock["model_commit"],
        "native_packages": lock["packages"],
        "binaries": binaries,
        "build_options": BUILD_OPTIONS,
        "native_reported_versions": version.splitlines()[1:],
        "compiler": run(["g++", "--version"], timeout=15).splitlines()[0],
        "installer_executed": False,
        "system_path_changed": False,
        "registry_changed": False,
        "runtime_downloads": False,
        "assets_bundled_in_python_package": False,
        "native_security_audit": "Upstream patched source and pinned current dependencies; not proof that native components have no vulnerabilities",
    }
    (destination.parent / "local-ocr-assets.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (work_dir / "ocr554-configure.log").write_text(configure, encoding="utf-8")
    (work_dir / "ocr554-build.log").write_text(build_output, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--bsdtar", default="bsdtar")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    manifest = install(args.destination, args.work_dir, args.bsdtar, args.workers)
    print(
        json.dumps(
            {
                "version": manifest["version"],
                "languages": manifest["languages"],
                "registry_changed": False,
                "system_path_changed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
