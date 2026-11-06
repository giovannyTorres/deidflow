"""Local domain, session and human-review commands with private file output."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, NoReturn

from deidflow.private.security import protect

_MAX_TEXT = 8 * 1024 * 1024
_MAX_JSON = 4 * 1024 * 1024
_MAX_CSV_JSON = 16 * 1024 * 1024


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Paths or mistaken command arguments may themselves contain private data.
        raise ValueError("Invalid command configuration; consult --help")


def _read(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Input must be a regular file")
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Input exceeds the configured limit")
    return raw


def _text(path: Path) -> str:
    return _read(path, _MAX_TEXT).decode("utf-8-sig")


def _key(path: Path) -> bytes:
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError("Key must be a regular local file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as handle:
        actual = os.fstat(handle.fileno())
        if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != (
            initial.st_dev,
            initial.st_ino,
        ):
            raise ValueError("Key file changed during opening")
        if os.name != "nt" and stat.S_IMODE(actual.st_mode) & 0o077:
            raise ValueError("Key file must have user-only permissions")
        key = handle.read(33)
    if len(key) != 32:
        raise ValueError("Key file must contain exactly 32 random bytes")
    return key


def _write(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            protect(path, directory=False)
            handle.write(raw)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def _read_json(path: Path, limit: int = _MAX_JSON) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in items}) != len(items):
            raise ValueError("Duplicate JSON fields")
        return dict(items)

    def invalid(value: str) -> NoReturn:
        raise ValueError("Nonfinite JSON values are unsupported")

    return json.loads(_read(path, limit), object_pairs_hook=pairs, parse_constant=invalid)


@contextmanager
def _bundle(target: Path) -> Iterator[Path]:
    """Publish a complete new directory atomically; never overwrite existing output."""
    from deidflow.rag import _publish

    parent = target.parent.resolve()
    stage = Path(tempfile.mkdtemp(prefix=".deidflow-product-", dir=parent))
    initial = stage.stat()
    try:
        protect(stage, directory=True)
        yield stage
        _publish(stage, target)
    finally:
        if stage.exists():
            current = stage.lstat()
            if stage.is_symlink() or (current.st_dev, current.st_ino) != (
                initial.st_dev,
                initial.st_ino,
            ):
                raise ValueError("Private staging ownership changed")
            shutil.rmtree(stage)


def _pack_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pack", default="general", help="clinical, financial, legal or general")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="deidflow", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    commands.add_parser("domains", help="List installed domain packs and their evidence")
    keygen = commands.add_parser("keygen", help="Create a private random 32-byte key file")
    keygen.add_argument("output", type=Path)

    session = commands.add_parser("session", help="Encrypted local sessions; no model services")
    actions = session.add_subparsers(dest="action", required=True, parser_class=_Parser)
    for action in ("create", "process", "restore", "graph", "relate"):
        sub = actions.add_parser(action)
        _pack_arguments(sub)
        sub.add_argument("--state", type=Path, required=True)
        sub.add_argument("--key-file", type=Path, required=True)
        if action == "create":
            sub.add_argument("--ttl-seconds", type=float)
        else:
            sub.add_argument("--output", type=Path, required=True)
        if action in {"process", "restore"}:
            sub.add_argument("source", type=Path, help="UTF-8 text file")
        if action == "relate":
            sub.add_argument("--relations", type=Path, required=True)

    review = commands.add_parser(
        "review", help="Explicit human span corrections and signed receipts"
    )
    actions = review.add_subparsers(dest="action", required=True, parser_class=_Parser)
    for action in ("plan", "apply", "verify"):
        sub = actions.add_parser(action)
        _pack_arguments(sub)
        sub.add_argument("source", type=Path, help="Original UTF-8 text or CSV file")
        sub.add_argument("--format", choices=("text", "csv"), default="text")
        sub.add_argument("--output", type=Path, required=True)
        if action != "plan":
            sub.add_argument("--signing-key-file", type=Path, required=True)
        if action == "apply":
            sub.add_argument("--state", type=Path, help="Existing encrypted identity session")
            sub.add_argument("--key-file", type=Path, help="Session encryption key file")
            sub.add_argument("--plan", type=Path, required=True)
            sub.add_argument("--decisions", type=Path, required=True)
            sub.add_argument("--reviewer-id", required=True)
            sub.add_argument("--approve", action="store_true")
            sub.add_argument("--source-complete", action="store_true")
        if action == "verify":
            sub.add_argument("--receipt", type=Path, required=True)
    return parser


def _session(args: argparse.Namespace) -> int:
    from deidflow.domains import get_domain_pack
    from deidflow.engine import ReleaseStatus
    from deidflow.session import DeidSession

    pack = get_domain_pack(args.pack)
    key = _key(args.key_file)
    if args.action == "create":
        with pack.session() as session:
            session.save(args.state, key=key, ttl_seconds=args.ttl_seconds)
        print(json.dumps({"status": "SESSION_CREATED", "pack": pack.name}))
        return 0
    with DeidSession.load(
        args.state, key=key, engine=pack.engine(), policy=pack.policy()
    ) as session:
        if args.action == "process":
            result = session.deidentify(_text(args.source), domain=pack.name)
            if result.status in {ReleaseStatus.BLOCKED, ReleaseStatus.UNSUPPORTED}:
                print(json.dumps(result.audit_dict()))
                return 2
            if result.output_text is None:
                raise ValueError("No transformed text was produced")
            with _bundle(args.output) as stage:
                _write(stage / "candidate.txt", result.output_text.encode("utf-8"))
                session.save(stage / "session.df", key=key)
                _write(stage / "graph.json", _json(session.graph()))
                _write(stage / "audit.json", _json(result.audit_dict()))
            print(json.dumps(result.audit_dict()))
            return 0 if result.release_approved else 2
        if args.action == "restore":
            restored = session.reidentify(_text(args.source))
            _write(args.output, restored.text.encode("utf-8"))
            print(json.dumps({"status": "RESTORED_LOCALLY", "restored": restored.restored}))
        elif args.action == "graph":
            _write(args.output, _json(session.graph()))
            print(json.dumps({"status": "GRAPH_WRITTEN"}))
        elif args.action == "relate":
            relations = _read_json(args.relations)
            if not isinstance(relations, list) or len(relations) > 10000:
                raise ValueError("Relations must be a bounded list")
            for relation in relations:
                if not isinstance(relation, dict):
                    raise ValueError("Invalid relation record")
                session.relate(**relation)
            session.save(args.output, key=key)
            print(json.dumps({"status": "RELATIONS_SAVED", "relations": len(relations)}))
        return 0


def _review(args: argparse.Namespace) -> int:
    from deidflow.domains import get_domain_pack
    from deidflow.review import (
        ReviewDecision,
        ReviewPlan,
        apply_review,
        create_review_plan,
        verify_review_receipt,
    )

    pack = get_domain_pack(args.pack)
    engine, policy = pack.engine(), pack.policy()
    digest = engine.model_digest
    if digest is None:
        raise ValueError("Review requires a bound model manifest")
    if args.format == "csv":
        return _review_csv(args, engine=engine, policy=policy, digest=digest, domain=pack.name)
    source = _text(args.source)
    if args.action == "plan":
        plan = create_review_plan(
            engine, source, policy=policy, model_digest=digest, domain=pack.name
        )
        _write(args.output, (plan.to_json() + "\n").encode())
        print(json.dumps({"status": "REVIEW_PLAN_CREATED", "spans": len(plan.spans)}))
        return 0
    key = _key(args.signing_key_file)
    if args.action == "verify":
        valid = verify_review_receipt(
            _read_json(args.receipt),
            source=source,
            output=_text(args.output),
            policy=policy,
            model_digest=digest,
            domain=pack.name,
            signing_key=key,
        )
        print(json.dumps({"status": "REVIEW_VERIFIED" if valid else "REVIEW_INVALID"}))
        return 0 if valid else 2
    plan = ReviewPlan.from_json(_read(args.plan, _MAX_JSON).decode("utf-8"))
    raw = _read_json(args.decisions)
    if not isinstance(raw, list) or len(raw) > 20000 or not all(isinstance(d, dict) for d in raw):
        raise ValueError("Review decisions must be a bounded list")
    if bool(args.state) != bool(args.key_file):
        raise ValueError("Session state and key file must be supplied together")
    from deidflow.session import DeidSession

    session_key = _key(args.key_file) if args.state else None
    context = (
        DeidSession.load(args.state, key=session_key, engine=engine, policy=policy)
        if session_key is not None
        else nullcontext(None)
    )
    decisions = [ReviewDecision(**item) for item in raw]
    with context as session:
        if session is None:
            reviewed = apply_review(
                engine,
                source,
                plan,
                decisions,
                policy=policy,
                model_digest=digest,
                reviewer_id=args.reviewer_id,
                approve=args.approve,
                source_complete=args.source_complete,
                signing_key=key,
                domain=pack.name,
            )
        else:
            reviewed = session.apply_review(
                source,
                plan,
                decisions,
                reviewer_id=args.reviewer_id,
                approve=args.approve,
                source_complete=args.source_complete,
                signing_key=key,
                domain=pack.name,
            )
        result = reviewed.result
        if result.output_text is None:
            raise ValueError("Review did not produce a candidate")
        with _bundle(args.output) as stage:
            _write(stage / "candidate.txt", result.output_text.encode("utf-8"))
            _write(stage / "receipt.json", _json(reviewed.receipt))
            _write(stage / "audit.json", _json(result.audit_dict()))
            if session is not None:
                assert session_key is not None
                session.save(stage / "session.df", key=session_key)
                _write(stage / "graph.json", _json(session.graph()))
    print(json.dumps(result.audit_dict()))
    return 0 if result.release_approved else 2


def _csv_distinct_paths(source: Path, output: Path) -> None:
    """Never review the source as its own output or follow an output symlink."""
    if output.is_symlink() or source.resolve() == output.resolve():
        raise ValueError("CSV output must be a distinct local path")
    if output.exists() and source.samefile(output):
        raise ValueError("CSV output must be a distinct local file")


def _csv_source_unchanged(path: Path, expected: bytes) -> None:
    if _read(path, _MAX_TEXT) != expected:
        raise ValueError("CSV source changed during review")


def _review_csv(
    args: argparse.Namespace, *, engine: Any, policy: Any, digest: str, domain: str
) -> int:
    from deidflow.csv_review import (
        CSVReviewDecision,
        CSVReviewPlan,
        apply_csv_review,
        create_csv_review_plan,
        verify_csv_review_receipt,
    )
    from deidflow.review import ReviewDecision

    if args.action == "apply" and (args.state is not None or args.key_file is not None):
        raise ValueError("CSV review does not support persisted identity sessions")
    _csv_distinct_paths(args.source, args.output)
    source = _read(args.source, _MAX_TEXT)
    if args.action == "plan":
        plan = create_csv_review_plan(
            engine, source, policy=policy, model_digest=digest, domain=domain
        )
        raw_plan = (plan.to_json() + "\n").encode("utf-8")
        if len(raw_plan) > _MAX_CSV_JSON:
            raise ValueError("CSV plan exceeds the configured limit")
        _csv_source_unchanged(args.source, source)
        _write(args.output, raw_plan)
        print(
            json.dumps(
                {
                    "status": "CSV_REVIEW_PLAN_CREATED",
                    "rows": plan.row_count,
                    "columns": plan.column_count,
                    "spans": sum(len(cell.review.spans) for cell in plan.cells),
                }
            )
        )
        return 0
    key = _key(args.signing_key_file)
    if args.action == "verify":
        output = _read(args.output, _MAX_TEXT)
        try:
            receipt = _read_json(args.receipt, _MAX_CSV_JSON)
        except (ValueError, UnicodeError):
            valid = False
        else:
            valid = verify_csv_review_receipt(
                receipt,
                source=source,
                output=output,
                policy=policy,
                model_digest=digest,
                domain=domain,
                signing_key=key,
            )
        _csv_source_unchanged(args.source, source)
        print(json.dumps({"status": "REVIEW_VERIFIED" if valid else "REVIEW_INVALID"}))
        return 0 if valid else 2
    plan = CSVReviewPlan.from_json(_read(args.plan, _MAX_CSV_JSON).decode("utf-8"))
    raw_decisions = _read_json(args.decisions, _MAX_CSV_JSON)
    if not isinstance(raw_decisions, list) or len(raw_decisions) > 20000:
        raise ValueError("CSV review decisions must be a bounded list")
    decisions = []
    for item in raw_decisions:
        if (
            not isinstance(item, dict)
            or set(item) != {"row", "column", "decision"}
            or type(item["row"]) is not int
            or type(item["column"]) is not int
            or not isinstance(item["decision"], dict)
        ):
            raise ValueError("Invalid CSV review decision")
        decisions.append(
            CSVReviewDecision(
                row=item["row"],
                column=item["column"],
                decision=ReviewDecision(**item["decision"]),
            )
        )
    reviewed = apply_csv_review(
        engine,
        source,
        plan,
        decisions,
        policy=policy,
        model_digest=digest,
        reviewer_id=args.reviewer_id,
        approve=args.approve,
        source_complete=args.source_complete,
        signing_key=key,
        domain=domain,
    )
    result = reviewed.result
    output_bytes = reviewed.output_bytes
    if not isinstance(output_bytes, bytes) or len(output_bytes) > _MAX_TEXT:
        raise ValueError("CSV review did not produce a bounded output")
    if result.release_approved and not (args.approve and args.source_complete):
        raise ValueError("CSV approval requires explicit human attestations")
    raw_receipt = _json(reviewed.receipt)
    if len(raw_receipt) > _MAX_CSV_JSON:
        raise ValueError("CSV receipt exceeds the configured limit")
    _csv_source_unchanged(args.source, source)
    audit = result.audit_dict()
    audit.update(format="csv", serialized_output_verified=True, source_unchanged=True)
    filename = "approved.csv" if result.release_approved else "candidate.csv"
    with _bundle(args.output) as stage:
        output_path = stage / filename
        _write(output_path, output_bytes)
        _write(stage / "receipt.json", raw_receipt)
        _write(stage / "audit.json", _json(audit))
        actual_output = _read(output_path, _MAX_TEXT)
        if actual_output != output_bytes or not verify_csv_review_receipt(
            _read_json(stage / "receipt.json", _MAX_CSV_JSON),
            source=source,
            output=actual_output,
            policy=policy,
            model_digest=digest,
            domain=domain,
            signing_key=key,
            require_approved=False,
        ):
            raise ValueError("Serialized CSV review verification failed")
        _csv_source_unchanged(args.source, source)
    print(json.dumps(audit))
    return 0 if result.release_approved else 2


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "keygen":
            _write(args.output, secrets.token_bytes(32))
            print(json.dumps({"status": "KEY_CREATED"}))
            return 0
        if args.command == "domains":
            from deidflow.domains import list_domain_packs

            print(_json([pack.to_dict() for pack in list_domain_packs()]).decode(), end="")
            return 0
        if args.command == "session":
            return _session(args)
        return _review(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_type": type(error).__name__,
                    "error": "Local operation failed; inspect configuration privately",
                }
            ),
            file=sys.stderr,
        )
        return 3


__all__ = ["main"]
