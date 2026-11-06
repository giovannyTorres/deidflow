"""Private JSONL transport for one explicitly pinned, offline local runtime."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

LIMIT = 4 * 1024 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False).encode()


def files_digest(root, paths):
    framed = hashlib.sha256()
    for path in sorted(paths):
        if not path.resolve().is_relative_to(root):
            raise ValueError
        name, payload = path.relative_to(root).as_posix().encode(), path.read_bytes()
        framed.update(len(name).to_bytes(8, "big") + name)
        framed.update(len(payload).to_bytes(8, "big") + payload)
    return framed.hexdigest()


def emit(value):
    payload = canonical(value)
    if len(payload) > LIMIT:
        raise ValueError
    sys.stdout.buffer.write(payload + b"\n")
    sys.stdout.buffer.flush()


def main():
    root, revision, expected_source = Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3]
    actual_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    if actual_revision != revision:
        raise ValueError
    sys.path.insert(0, str(root / "src"))
    attempts = 0

    def deny(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Offline local candidate")

    with ExitStack() as stack:
        for operation in (
            "getaddrinfo",
            "create_connection",
            "socket.connect",
            "socket.connect_ex",
        ):
            stack.enter_context(patch("socket." + operation, deny))
        from deidflow import DeidEngine
        from deidflow.core import Finding
        from deidflow.policies import Policy, Rule
        from deidflow.transformations import transform_text

        def snapshot():
            live_revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            if live_revision != revision:
                raise ValueError
            modules = []
            for name, module in sorted(sys.modules.items()):
                if name == "deidflow" or name.startswith("deidflow."):
                    path = Path(module.__file__ or "").resolve()
                    if not path.is_relative_to(root / "src/deidflow"):
                        raise ValueError
                    modules.append(
                        {
                            "module": name,
                            "path": path.relative_to(root).as_posix(),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                    )
            return {
                "revision": live_revision,
                "source_clean": not bool(
                    subprocess.check_output(
                        [
                            "git",
                            "status",
                            "--porcelain",
                            "--untracked-files=all",
                            "--",
                            "src/deidflow",
                        ],
                        cwd=root,
                        text=True,
                    )
                ),
                "source_sha256": files_digest(root, (root / "src/deidflow").rglob("*.py")),
                "model_sha256": files_digest(
                    root,
                    (
                        p
                        for p in (root / "src/deidflow/models").rglob("*")
                        if p.is_file() and p.suffix not in {".py", ".pyc"}
                    ),
                ),
                "declarations_sha256": files_digest(
                    root, [root / "pyproject.toml", *root.glob("requirements*.txt")]
                ),
                "dependencies_sha256": hashlib.sha256(
                    canonical(
                        sorted(
                            (d.metadata["Name"], d.version)
                            for d in importlib.metadata.distributions()
                        )
                    )
                ).hexdigest(),
                "python": platform.python_version(),
                "loaded_modules": modules,
                "network_attempts": attempts,
            }

        before = snapshot()
        if before["source_sha256"] != expected_source:
            raise ValueError
        emit({"ready": before})
        engines: dict[str, DeidEngine] = {}
        response: dict[str, Any]
        while True:
            line = sys.stdin.buffer.readline(LIMIT + 1)
            if not line or len(line) > LIMIT:
                raise ValueError
            request = json.loads(line)
            if request == {"operation": "finish"}:
                after = snapshot()
                if attempts or any(
                    after[k] != before[k]
                    for k in (
                        "source_sha256",
                        "model_sha256",
                        "declarations_sha256",
                        "dependencies_sha256",
                    )
                ):
                    raise ValueError
                emit({"finished": after})
                return
            try:
                operation, text, country = request["operation"], request["text"], request["country"]
                if operation not in {"detect", "run", "transform"} or not isinstance(text, str):
                    raise ValueError
                if country not in {"MX", "ES"} or len(text.encode()) > LIMIT // 2:
                    raise ValueError
                with redirect_stdout(sys.stderr):
                    if operation == "transform":
                        config = request["policy"]
                        policy = Policy(
                            **{
                                **config,
                                "default": Rule(**config["default"]),
                                "entities": {k: Rule(**v) for k, v in config["entities"].items()},
                                "domains": {
                                    k: {a: Rule(**b) for a, b in v.items()}
                                    for k, v in config["domains"].items()
                                },
                            }
                        )
                        findings = [
                            Finding(a, b, c, 1.0, "benchmark-gold", protected=True)
                            for a, b, c in request["gold"]
                        ]
                        output, maps = transform_text(text, findings, policy)
                        response = {
                            "text": output,
                            "mappings": [asdict(m) for m in maps],
                            "state": "APPROVED",
                        }
                    else:
                        if country not in engines:
                            engines[country] = DeidEngine(country=country, offline=True)
                        engine = engines[country]
                        if operation == "detect":
                            response = {
                                "findings": [
                                    [str(f.entity_type), f.start, f.end, f.score, f.confidence]
                                    for f in engine.scan_text(text)
                                ]
                            }
                        else:
                            result = engine.deidentify_text(
                                text, policy=Policy.strict(require_ner=False)
                            )
                            response = {
                                "text": result.output_text,
                                "state": result.status.value,
                                "mappings": [asdict(m) for m in result.mappings],
                            }
                if "mappings" in response:
                    response["mappings"] = [
                        [
                            m[k]
                            for k in (
                                "source_start",
                                "source_end",
                                "output_start",
                                "output_end",
                                "entity_types",
                                "action",
                            )
                        ]
                        for m in response["mappings"]
                    ]
                emit(response)
            except Exception:
                emit({"error": "LOCAL_CANDIDATE_ERROR"})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit({"error": "INVALID_PINNED_LOCAL_CANDIDATE"})
        sys.exit(1)
