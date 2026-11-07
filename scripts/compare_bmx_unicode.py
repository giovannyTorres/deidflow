"""Pinned local development regression comparison; never an independent test set."""

from __future__ import annotations

import hashlib
import json
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


def transformation_output(observed):
    from deidflow.benchmarks.transformation_metrics import TransformationOutput
    from deidflow.transformations import SourceMap

    maps = tuple(
        SourceMap(source_start, source_end, output_start, output_end, tuple(entity_types), action)
        for source_start, source_end, output_start, output_end, entity_types, action in observed[
            "mappings"
        ]
    )
    return TransformationOutput(observed["text"], maps, observed["state"])


def inspect_probe(text, label, start, observed):
    """Inspect the complete independently supplied sensitive source interval."""
    from deidflow.benchmarks.transformation_metrics import TextRequirement, inspect_text_output

    requirement = TextRequirement(
        start,
        len(text),
        "remove",
        ("placeholder",),
        ("APPROVED", "REVIEW_REQUIRED", "BLOCKED", "UNSUPPORTED"),
        label,
        ((start, len(text)),),
    )
    checked = inspect_text_output(text, [requirement], transformation_output(observed))
    return {
        "state": observed["state"],
        "full_source_removed": checked["removed_mentions"] == 1,
        "leaked_mentions": checked["leaked_mentions"],
        "unverifiable_mentions": checked["unverifiable_mentions"],
        "unsafe_approved": observed["state"] == "APPROVED" and checked["leaked_mentions"] > 0,
        "retention_required_chars": checked["retention_required_chars"],
        "retained_chars": checked["retained_chars"],
        "verification_complete": checked["verification_complete"],
    }


class LocalCandidate:
    """Real target engines live in their own checked source namespace."""

    def __init__(self, root, revision):
        self.root, self.revision = Path(root).resolve(), revision
        framed = hashlib.sha256()
        for path in sorted((self.root / "src/deidflow").rglob("*.py")):
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("Invalid pinned local candidate")
            name, payload = path.relative_to(self.root).as_posix().encode(), path.read_bytes()
            framed.update(len(name).to_bytes(8, "big") + name)
            framed.update(len(payload).to_bytes(8, "big") + payload)
        self.source_sha256 = framed.hexdigest()
        self.process: subprocess.Popen[bytes] | None = None
        # A reader thread is portable; select() does not support pipes on Windows.
        self.lines: queue.Queue[bytes] = queue.Queue()

    def __enter__(self):
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(Path(__file__).with_name("_bmx_unicode_worker.py")),
                    str(self.root),
                    self.revision,
                    self.source_sha256,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            threading.Thread(target=self._read_lines, daemon=True).start()
            self.descriptor = self._receive()["ready"]
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise ValueError("Invalid pinned local candidate") from None

    def _read_lines(self):
        stream = self.process.stdout if self.process is not None else None
        if stream is None:
            self.lines.put(b"")
            return
        while True:
            try:
                line = stream.readline(4 * 1024 * 1024 + 1)
            except (OSError, ValueError):
                line = b""
            self.lines.put(line)
            if not line.endswith(b"\n"):
                return  # end of stream, or a line over the limit

    def _receive(self):
        if self.process is None or self.process.stdout is None:
            raise ValueError("Invalid pinned local candidate")
        try:
            line = self.lines.get(timeout=30)
        except queue.Empty:
            raise ValueError("Invalid pinned local candidate") from None
        if not line.endswith(b"\n"):
            raise ValueError("Invalid pinned local candidate")
        try:
            response = json.loads(line)
        except (ValueError, RecursionError):
            raise ValueError("Invalid pinned local candidate") from None
        if not isinstance(response, dict) or "error" in response:
            raise ValueError("Invalid pinned local candidate")
        return response

    def request(self, operation, text, *, country="MX", **extra):
        payload = (
            json.dumps(
                {"operation": operation, "text": text, "country": country, **extra},
                ensure_ascii=True,
                allow_nan=False,
            ).encode()
            + b"\n"
        )
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError("Invalid pinned local candidate")
        if self.process is None or self.process.stdin is None:
            raise ValueError("Invalid pinned local candidate")
        try:
            self.process.stdin.write(payload)
            self.process.stdin.flush()
            return self._receive()
        except (OSError, ValueError):
            raise ValueError("Invalid pinned local candidate") from None

    def finish(self):
        if self.process is None or self.process.stdin is None:
            raise ValueError("Invalid pinned local candidate")
        self.process.stdin.write(b'{"operation":"finish"}\n')
        self.process.stdin.flush()
        descriptor = self._receive()["finished"]
        if self.process.wait(timeout=5) != 0:
            raise ValueError("Invalid pinned local candidate")
        return descriptor

    def __exit__(self, *args):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            if self.process.stdin is not None:
                self.process.stdin.close()
            if self.process.stdout is not None:
                self.process.stdout.close()


# Deliberately fictitious, exposed development fixtures. Spans are authored here,
# never inferred from either candidate's predictions or normalized output.
PROBES = (
    ("H1-1", "NATIONAL_ID", 4, "DNI 1234\u200b5678Z"),
    ("H1-2", "NATIONAL_ID", 4, "DNI 1234\u00ad5678Z"),
    ("H1-3", "PHONE", 5, "Tel. 612\u2060345\u2060678"),
    ("H1-4", "EMAIL", 7, "Correo ana\u200d.lopez@example.com"),
    ("H1-5", "CURP", 5, "CURP GOMA800101HDFRRN0\u200b9"),
    ("H2-1", "EMAIL", 7, "Correo ａｎａ.lopez@example.com"),
)


def evaluate_probes(candidate):
    rows = []
    for identifier, label, start, text in PROBES:
        findings = candidate.request("detect", text, country="ES")["findings"]
        coverage = {
            i
            for entity, a, b, *_ in findings
            if entity == label
            for i in range(max(start, a), min(len(text), b))
        }
        observed = candidate.request("run", text, country="ES")
        rows.append(
            {
                "id": identifier,
                "entity_type": label,
                "detection": {
                    "exact_typed_match": any(
                        entity == label and a == start and b == len(text)
                        for entity, a, b, *_ in findings
                    ),
                    "required_source_codepoints": len(text) - start,
                    "covered_source_codepoints": len(coverage),
                },
                "removal": inspect_probe(text, label, start, observed),
            }
        )
    return {
        "schema_version": "deidflow.unicode-fictional-probes.v1",
        "exposure": "known_regression",
        "country": "ES",
        "offline": True,
        "policy": "Policy.strict(require_ner=False)",
        "fixture_sha256": hashlib.sha256(
            json.dumps(PROBES, ensure_ascii=True).encode()
        ).hexdigest(),
        "probes": rows,
        "supplemental_zwnj": inspect_probe(
            "DNI 1234\u200c5678Z",
            "NATIONAL_ID",
            4,
            candidate.request("run", "DNI 1234\u200c5678Z", country="ES"),
        ),
        "totals": {
            "required_removals": len(rows),
            "full_source_removed": sum(r["removal"]["full_source_removed"] for r in rows),
            "confirmed_residual": sum(r["removal"]["leaked_mentions"] for r in rows),
            "unsafe_approved": sum(r["removal"]["unsafe_approved"] for r in rows),
        },
        "quality": "DESCRIPTIVE_ONLY",
        "limitations": ["FICTIONAL_DEVELOPMENT_REGRESSION", "NO_INDEPENDENT_EVIDENCE"],
    }


def evaluate_transformations(candidate, package, digest, case_ids=None):
    """Gold supplied to the transformer; this does not measure detection."""
    from dataclasses import asdict

    from deidflow.benchmarks.evaluation_package import load_evaluation_package
    from deidflow.benchmarks.transformation_metrics import (
        inspect_text_output,
        requirements_for_unit,
    )
    from deidflow.benchmarks.transformation_runner import transformation_policy

    loaded = load_evaluation_package(package, manifest_sha256=digest)
    records, profile = loaded.records, "transformation-descriptive-v1"
    mentions = {row["mention_id"]: row for row in records["mentions"]}
    precedence = records[loaded.manifest["profiles"][profile]["resource"]]["precedence"]
    totals: dict[str, int] = {}
    units = 0
    for unit in records["units"]:
        if case_ids is not None and unit["case_id"] not in case_ids:
            continue
        requirements, _ = requirements_for_unit(
            records["expectations"], mentions, unit["unit_id"], profile, precedence
        )
        gold, policy = transformation_policy(requirements)
        observed = candidate.request(
            "transform",
            unit["text"],
            policy=asdict(policy),
            gold=[[f.entity_type, f.start, f.end] for f in gold],
        )
        checked = inspect_text_output(unit["text"], requirements, transformation_output(observed))
        for key, value in checked.items():
            if type(value) is int:
                totals[key] = totals.get(key, 0) + value
        units += 1
    return {
        "track": "transformation_gold_supplied",
        "required_units": units,
        "metrics": totals,
        "quality": "DESCRIPTIVE_ONLY",
    }


def evaluator_snapshot():
    """Bind loaded evaluator modules and distinguish uncontrolled caller caches."""
    source_root = Path(__file__).resolve().parents[1] / "src/deidflow"
    modules = []
    for name, module in sorted(sys.modules.items()):
        if name == "deidflow" or name.startswith("deidflow."):
            path = Path(module.__file__ or "").resolve()
            if not path.is_relative_to(source_root):
                raise ValueError("Invalid comparison evaluator")
            modules.append(
                {
                    "module": name,
                    "path": path.relative_to(source_root.parent.parent).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    cache_entries = (
        sum(1 for _ in Path(sys.pycache_prefix).rglob("*")) if sys.pycache_prefix else None
    )
    return {
        "cache_mode": "isolated_empty_cache_prefix"
        if sys.pycache_prefix and sys.dont_write_bytecode and cache_entries == 0
        else "caller_cache_not_execution_pinned",
        "cache_entries": cache_entries,
        "loaded_modules": modules,
    }


def compare(sources, targets, destination, seed=17):
    """Publish only after pinned local execution and unchanged-resource checks."""
    from contextlib import ExitStack
    from tempfile import TemporaryDirectory

    from deidflow.benchmarks.email import _source_digest
    from deidflow.benchmarks.evaluation_package import load_evaluation_package
    from deidflow.benchmarks.package_runner import DetectionCandidate
    from deidflow.benchmarks.perturbation_package import (
        generate_perturbation_suite,
        run_perturbation_suite,
    )
    from deidflow.core import Finding

    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Comparison destination already exists")
    if [label for label, _, _ in targets] != ["baseline", "fixed"]:
        raise ValueError("Invalid pinned local candidate")
    for source in sources:
        if destination.resolve().is_relative_to(Path(source).resolve()):
            raise ValueError("Invalid comparison output")
    for _, root, revision in targets:
        try:
            actual = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            dirty = subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=all", "--", "src/deidflow"],
                cwd=root,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            raise ValueError("Invalid pinned local candidate") from None
        if actual != revision or dirty:
            raise ValueError("Invalid pinned local candidate")
    destination.parent.mkdir(parents=True, exist_ok=True)
    helper_pins = {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("compare_bmx_unicode.py", "_bmx_unicode_worker.py")
    }
    harness_pin = _source_digest()
    with TemporaryDirectory(prefix=".unicode-comparison-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        with ExitStack() as stack:
            candidates = {
                label: stack.enter_context(LocalCandidate(root, revision))
                for label, root, revision in targets
            }
            report: dict[str, Any] = {
                "schema_version": "deidflow.unicode-development-comparison.v1",
                "quality": "DESCRIPTIVE_ONLY",
                "exposure": "known_regression",
                "helper_sha256": helper_pins,
                "evaluator_source_sha256": harness_pin,
                "candidate_before": {label: c.descriptor for label, c in candidates.items()},
                "evaluator_before": evaluator_snapshot(),
                "probes": {label: evaluate_probes(c) for label, c in candidates.items()},
                "corpora": [],
                "limitations": [
                    "FICTIONAL_DEVELOPMENT_REGRESSION",
                    "NO_UNTOUCHED_TEST_CLAIM",
                    "NO_MODEL_ADOPTION_EVIDENCE",
                    "PYTHON_SOCKET_GUARD_NOT_OS_SANDBOX",
                ],
            }
            for number, source in enumerate(sources, 1):
                source = Path(source)
                digest = hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest()
                original = load_evaluation_package(source, manifest_sha256=digest)
                if any(
                    row["panel"] != "known_regression" for row in original.records["documents"]
                ) or any(
                    row["origin_kind"] != "synthetic" or row["personal_data_status"] != "fictional"
                    for row in original.records["sources"]
                ):
                    raise ValueError("Comparison accepts fictional known regression only")
                base = staging / f"corpus-{number}"
                suite = generate_perturbation_suite(
                    source,
                    manifest_sha256=digest,
                    destination=base / "suite",
                    seed=seed,
                    recipes=("format_chars.v1", "fullwidth.v1"),
                )
                corpus: dict[str, Any] = {
                    "source_manifest_sha256": digest,
                    "suite_index_sha256": suite["index_sha256"],
                    "seed": seed,
                    "required_documents": len(original.records["documents"]),
                    "candidates": {},
                    "recipe_support": [],
                }
                from collections import Counter

                source_characters = Counter("".join(u["text"] for u in original.records["units"]))
                original_ids = {r["case_id"] for r in original.records["documents"]}
                for entry in suite["packages"]:
                    derived = load_evaluation_package(
                        base / "suite" / entry["path"], manifest_sha256=entry["manifest_sha256"]
                    )
                    additions = (
                        Counter(
                            "".join(
                                u["text"]
                                for u in derived.records["units"]
                                if u["case_id"] not in original_ids
                            )
                        )
                        - source_characters
                    )
                    corpus["recipe_support"].append(
                        {
                            "recipe": entry["recipe"],
                            "changed_units": entry["changed_units"],
                            "inserted_format_controls": {
                                f"U+{ord(c):04X}": additions[c]
                                for c in "\u00ad\u200b\u200d\u2060\ufeff"
                            },
                            "added_fullwidth_codepoints": sum(
                                n for c, n in additions.items() if "！" <= c <= "～"
                            ),
                        }
                    )
                for label, candidate in candidates.items():

                    def detect(text, local=candidate):
                        return [
                            Finding(entity, a, b, score, "pinned-local", confidence=confidence)
                            for entity, a, b, score, confidence in local.request("detect", text)[
                                "findings"
                            ]
                        ]

                    detection = run_perturbation_suite(
                        source,
                        manifest_sha256=digest,
                        suite=base / "suite",
                        index_sha256=suite["index_sha256"],
                        candidate=DetectionCandidate(
                            "candidate-" + label.encode().hex(), candidate.source_sha256, detect
                        ),
                        profile="detection-descriptive-v1",
                        output=base / label / "detection",
                    )
                    clean = evaluate_transformations(candidate, source, digest)
                    transformations = []
                    original_ids = {r["case_id"] for r in original.records["documents"]}
                    for entry in suite["packages"]:
                        package = base / "suite" / entry["path"]
                        derived = load_evaluation_package(
                            package, manifest_sha256=entry["manifest_sha256"]
                        )
                        child_ids = {
                            r["case_id"] for r in derived.records["documents"]
                        } - original_ids
                        transformations.append(
                            {
                                "recipe": entry["recipe"],
                                "clean": clean,
                                "perturbed": evaluate_transformations(
                                    candidate, package, entry["manifest_sha256"], child_ids
                                ),
                            }
                        )
                    detailed_path = base / label / "detection/report.json"
                    corpus["candidates"][label] = {
                        "detection": {
                            "report": detailed_path.relative_to(staging).as_posix(),
                            "report_sha256": hashlib.sha256(detailed_path.read_bytes()).hexdigest(),
                            "all_cases": [
                                pair for pair in detection["results"] if pair["stratum"] is None
                            ],
                        },
                        "transformation": transformations,
                    }
                # Derived texts, maps and gold remain private temporary inputs.
                # Source/seed/index pins permit their independent reproduction.
                shutil.rmtree(base / "suite")
                report["corpora"].append(corpus)
            report["candidate_after"] = {label: c.finish() for label, c in candidates.items()}
            for resource in ("model_sha256", "declarations_sha256", "dependencies_sha256"):
                if (
                    report["candidate_after"]["baseline"][resource]
                    != report["candidate_after"]["fixed"][resource]
                ):
                    raise ValueError("Candidate resources differ")
            report["evaluator_after"] = evaluator_snapshot()
            if report["evaluator_before"]["cache_mode"] != report["evaluator_after"]["cache_mode"]:
                raise ValueError("Comparison evaluator cache changed")
            if _source_digest() != harness_pin or any(
                hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != digest
                for name, digest in helper_pins.items()
            ):
                raise ValueError("Comparison evaluator changed")
        payload = (
            json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n"
        )
        (staging / "report.json").write_text(payload)
        destination.mkdir()
        try:
            for member in staging.iterdir():
                member.rename(destination / member.name)
        except OSError:
            shutil.rmtree(destination)
            raise ValueError("Invalid comparison output") from None
    return report


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--fixed-root", type=Path, required=True)
    parser.add_argument("--baseline-revision", default="44d04b16fb1ec545161c4ef0c14f516c7b0d9d29")
    parser.add_argument("--fixed-revision", default="3de9d732dca9a6df106a757836f0c8194be73916")
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    from tempfile import TemporaryDirectory

    # Establish source compilation before the first evaluator import, even when
    # ignored source-tree pyc files already exist in the checkout.
    if any(name == "deidflow" or name.startswith("deidflow.") for name in sys.modules):
        raise SystemExit("Invalid comparison evaluator")
    with TemporaryDirectory(prefix=".bmx-evaluator-cache-") as cache_prefix:
        sys.pycache_prefix, sys.dont_write_bytecode = cache_prefix, True
        try:
            compare(
                args.source,
                [
                    ("baseline", args.baseline_root, args.baseline_revision),
                    ("fixed", args.fixed_root, args.fixed_revision),
                ],
                args.output,
                args.seed,
            )
            if any(Path(cache_prefix).rglob("*")):
                raise ValueError
        except (ValueError, OSError, KeyError, TypeError, RecursionError):
            raise SystemExit("Invalid local Unicode development comparison") from None


if __name__ == "__main__":
    main()
