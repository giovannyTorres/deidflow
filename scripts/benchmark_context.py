"""Evaluate fixed fictional Spanish privacy/context cases with networking denied."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import deidflow
from deidflow import DeidEngine, Policy, __version__
from deidflow.benchmarks.context_quality import evaluate_context_sessions, load_context_cases
from deidflow.benchmarks.runner import offline_network
from deidflow.llm import DeidSession
from deidflow.nlp.router import DomainRouter
from deidflow.nlp.tagger import BUILTIN_MODELS


def _revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(deidflow.__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _source_state() -> dict[str, Any]:
    root = Path(deidflow.__file__).resolve().parent
    digest = hashlib.sha256()
    files = sorted(root.rglob("*.py"))
    for path in files:
        name, content = path.relative_to(root).as_posix().encode("utf-8"), path.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(content).to_bytes(8, "big") + content)
    try:
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout
        )
    except (OSError, subprocess.SubprocessError):
        dirty = None
    return {
        "python_sources_sha256": digest.hexdigest(),
        "python_source_files": len(files),
        "git_worktree_dirty": dirty,
        "model_resource_sha256": {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "models").iterdir())
            if path.is_file() and (path.name.endswith(".json") or path.name.endswith(".json.gz"))
        },
    }


def _checkpoint(session: Any) -> Any:
    """Exercise encrypted persistence with a fresh allocator and private temp file."""
    if not callable(getattr(session, "save", None)) or not callable(
        getattr(type(session), "load", None)
    ):
        raise RuntimeError("Selected session API does not support encrypted checkpoints")
    key = secrets.token_bytes(32)
    with tempfile.TemporaryDirectory(prefix="deidflow-context-") as directory:
        path = Path(directory) / "session.enc"
        session.save(path, key=key)
        restored = type(session).load(path, key=key, engine=session.engine, policy=session.policy)
    session.close()
    return restored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "benchmarks/context-cases-es.jsonl",
    )
    parser.add_argument("--pipeline", choices=["baseline", "domains", "both"], default="both")
    parser.add_argument("--profile", choices=["balanced", "assurance"], default="balanced")
    parser.add_argument(
        "--checkpoint-between-documents",
        action="store_true",
        help="Require encrypted save/load between each pair of documents (vault extra)",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path, help="Optional per-domain aggregate CSV")
    parser.add_argument(
        "--compare-to", type=Path, help="Prior report with exactly the same corpus digest"
    )
    args = parser.parse_args()
    if args.output.exists() or (args.csv is not None and args.csv.exists()):
        parser.error("Output already exists; choose a new report path")
    cases, digest = load_context_cases(args.cases)
    report: dict[str, Any] = {
        "schema_version": 1,
        "evidence_type": "fictional_regression",
        "corpus_sha256": digest,
        "documents": len(cases),
        "sessions": len({case.session_id for case in cases}),
        "package_version": __version__,
        "git_revision": _revision(),
        "source_state": _source_state(),
        "builtin_model_digests": {name: value[1] for name, value in sorted(BUILTIN_MODELS.items())},
        "profile": args.profile,
        "pipelines": {},
        "limitations": [
            "Authored fictional regression cases, not a representative clinical/financial/legal population.",
            "Do not fit or select models on these cases and then claim independent held-out quality.",
            "Source-character removal and exact literal-value survival do not prove protection from re-identification.",
            "Declared relation fidelity tests storage, not automatic relation extraction or coreference.",
            "Byte-for-byte semantic context guarantees are limited to annotated source spans in these cases.",
            "No PDF, image/OCR, Office package, HTML or cross-format quality is measured by this text-only suite.",
        ],
    }
    with offline_network() as guard:
        if args.pipeline in {"baseline", "both"}:
            engine = DeidEngine(nlp=DomainRouter.builtin(profile=args.profile))
            report["pipelines"]["policy_llm_auto"] = evaluate_context_sessions(
                cases,
                lambda domain: DeidSession(engine, policy=Policy.llm()),
                checkpoint=_checkpoint if args.checkpoint_between_documents else None,
            )
        if args.pipeline in {"domains", "both"}:
            from deidflow.domains import get_domain_pack

            packs = {domain: get_domain_pack(domain) for domain in {case.domain for case in cases}}
            report["pipelines"]["domain_packs"] = evaluate_context_sessions(
                cases,
                lambda domain: packs[domain].session(profile=args.profile),
                checkpoint=_checkpoint if args.checkpoint_between_documents else None,
            )
        report["network_guard"] = {
            "attempts": guard["attempts"],
            "scope": "Python DNS/connect calls during inference",
        }
    if args.compare_to is not None:
        previous = json.loads(args.compare_to.read_text(encoding="utf-8"))
        if (
            previous.get("corpus_sha256") != digest
            or previous.get("evidence_type") != "fictional_regression"
        ):
            parser.error("Comparison requires the same fictional corpus digest and evidence type")
        report["comparison"] = {
            "baseline_revision": previous.get("git_revision"),
            "baseline_package_version": previous.get("package_version"),
            "baseline_profile": previous.get("profile"),
            "baseline_aggregates": {
                name: value["aggregate"] for name, value in previous["pipelines"].items()
            },
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    if args.csv is not None:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fields = sorted(
            {
                key
                for result in report["pipelines"].values()
                for row in result["domains"].values()
                for key in row
            }
        )
        with args.csv.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=["pipeline", "domain", *fields], lineterminator="\n"
            )
            writer.writeheader()
            for pipeline, result in report["pipelines"].items():
                for domain, row in result["domains"].items():
                    writer.writerow({"pipeline": pipeline, "domain": domain, **row})
    print(
        json.dumps(
            {name: value["aggregate"] for name, value in report["pipelines"].items()},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
