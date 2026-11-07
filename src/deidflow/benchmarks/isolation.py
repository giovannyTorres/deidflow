"""Optional Linux process isolation. Absence never accredits strict custody.

This entry point executes a pinned local program, not an in-process callback.
Only counts cross the public boundary; stdout, stderr and syscall traces remain
temporary private material and are removed after inspection.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ._package_io import MAX_PACKAGE_BYTES, MAX_RESOURCE_BYTES, is_sha256, strict_json
from .email import _write_report


@dataclass(frozen=True)
class IsolationLimits:
    wall_seconds: float = 5.0
    memory_bytes: int = 512 * 1024**2
    output_bytes: int = MAX_RESOURCE_BYTES
    expanded_bytes: int = MAX_PACKAGE_BYTES
    archive_members: int = 1024
    nesting_depth: int = 32
    pixels: int = 20_000_000

    def __post_init__(self) -> None:
        if (
            type(self.wall_seconds) not in {float, int}
            or not math.isfinite(self.wall_seconds)
            or not 0.1 <= self.wall_seconds <= 60
            or any(
                type(value) is not int or value <= 0
                for name, value in asdict(self).items()
                if name != "wall_seconds"
            )
            or not 32 * 1024**2 <= self.memory_bytes <= 8 * 1024**3
            or self.output_bytes > MAX_PACKAGE_BYTES
        ):
            raise ValueError("Invalid isolated benchmark limits")


@dataclass(frozen=True)
class LocalAsset:
    asset_id: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class _AdmissionMeasurements:
    expanded_bytes: int
    archive_members: int
    nesting_depth: int
    pixels: int

    def exceeds(self, limits: IsolationLimits) -> bool:
        return any(
            type(value) is not int or not 0 <= value <= getattr(limits, name)
            for name, value in asdict(self).items()
        )


def _read_file(path: Path, maximum: int) -> bytes:
    import stat

    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError
    return payload


# File-size and CPU-time limit signals (POSIX); absent on Windows.
_LIMIT_SIGNALS = [getattr(signal, name) for name in ("SIGXFSZ", "SIGXCPU") if hasattr(signal, name)]
_LIMIT_RETURN_CODES = {-number for number in _LIMIT_SIGNALS} | {128 + n for n in _LIMIT_SIGNALS}


def _set_limits(limits: IsolationLimits) -> None:
    if sys.platform == "win32":
        raise OSError("POSIX resource limits are unavailable on Windows")
    import resource

    cpu = math.ceil(limits.wall_seconds) + 1
    for kind, requested in (
        (resource.RLIMIT_AS, limits.memory_bytes),
        (resource.RLIMIT_FSIZE, limits.output_bytes),
        (resource.RLIMIT_CPU, cpu),
        (resource.RLIMIT_CORE, 0),
        (resource.RLIMIT_NOFILE, 128),
    ):
        _soft, inherited_hard = resource.getrlimit(kind)
        applied = (
            requested
            if inherited_hard == resource.RLIM_INFINITY
            else min(requested, inherited_hard)
        )
        resource.setrlimit(kind, (applied, applied))


def _runtime_mounts() -> list[Path]:
    return list(
        dict.fromkeys(
            Path(path)
            for path in ("/usr", "/lib", "/lib64", sys.base_prefix)
            if Path(path).exists()
        )
    )


def _command(root: Path, bwrap: str, strace: str) -> list[str]:
    command = [
        strace,
        "-ff",
        "-qq",
        "-ttt",
        "-s",
        "4096",
        "-e",
        "trace=network,process,memory,ptrace,io_uring_setup,io_uring_enter,io_uring_register",
        "-o",
        str(root / "trace"),
        bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
    ]
    # Preserve alias mount points required by ELF loaders while keeping roots RO.
    for path in _runtime_mounts():
        command.extend(("--ro-bind", str(path), str(path)))
    command.extend(
        (
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            str(root / "task"),
            "/task",
            "--ro-bind",
            str(root / "inputs"),
            "/inputs",
            "--ro-bind",
            str(root / "assets"),
            "/assets",
            "--chdir",
            "/task",
            "--",
            str(Path(sys.executable).resolve()),
            "-I",
            "-S",
            "-B",
            "/task/candidate.py",
        )
    )
    return command


def _trace_summary(root: Path, maximum: int) -> tuple[bool, int, int, int]:
    files = list(root.glob("trace.*"))
    if not files or len(files) > 1024:
        return False, 0, 0, 0
    records = []
    entry = None
    interpreter = str(Path(sys.executable).resolve())
    for path in files:
        raw = _read_file(path, maximum)
        if len(raw) >= maximum:
            return False, 0, 0, 0
        for line in raw.decode("utf-8", errors="replace").splitlines():
            timestamp, _, call = line.partition(" ")
            try:
                at = float(timestamp)
            except ValueError:
                continue
            records.append((at, call))
            if (
                call.startswith("execve(" + json.dumps(interpreter))
                and '"/task/candidate.py"' in call
                and re.search(r"= 0$", call)
            ):
                entry = at if entry is None else min(entry, at)
    if entry is None:
        return False, 0, 0, 0
    network_calls = {
        "socket",
        "socketpair",
        "connect",
        "bind",
        "listen",
        "accept",
        "accept4",
        "sendto",
        "recvfrom",
        "sendmsg",
        "recvmsg",
        "sendmmsg",
        "recvmmsg",
        "shutdown",
        "getsockname",
        "getpeername",
        "setsockopt",
        "getsockopt",
    }
    network = memory = integrity = 0
    for at, call in records:
        if at < entry:
            continue  # Trusted bubblewrap namespace setup, before candidate exec.
        name = call.partition("(")[0]
        network += int(name in network_calls)
        memory += int(name in {"mmap", "mremap", "brk"} and "ENOMEM" in call)
        integrity += int(
            (name in {"clone", "clone3"} and "CLONE_UNTRACED" in call)
            or name in {"ptrace", "io_uring_setup", "io_uring_enter", "io_uring_register"}
        )
    return True, network, memory, integrity


def _response(raw: bytes, required_mentions: int) -> dict[str, int]:
    value = strict_json(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"status", "counts"}
        or value["status"] != "COMPLETED"
        or not isinstance(value["counts"], dict)
    ):
        raise ValueError
    maxima = {
        "completed_documents": 1,
        "completed_mentions": required_mentions,
        "true_positives": required_mentions,
        "false_positives": 10_000,
        "false_negatives": required_mentions,
        "removed_mentions": required_mentions,
        "leaked_mentions": required_mentions,
        "joint_success_documents": 1,
    }
    if "completed_documents" not in value["counts"] or any(
        key not in maxima or type(count) is not int or not 0 <= count <= maxima[key]
        for key, count in value["counts"].items()
    ):
        raise ValueError
    return dict(value["counts"])


def run_isolated_case(
    script: str | Path,
    *,
    script_sha256: str,
    input_payload: dict[str, Any],
    case_id: str,
    required_mentions: int,
    output: str | Path,
    limits: IsolationLimits | None = None,
    assets: tuple[LocalAsset, ...] = (),
    reference_root: Path | None = None,
    expanded_bytes: int = 0,
    archive_members: int = 0,
    nesting_depth: int = 0,
    pixels: int = 0,
) -> dict[str, Any]:
    """Stage only authorized input and assets; never mount the caller's cwd."""
    limits = limits or IsolationLimits()
    if (
        not isinstance(case_id, str)
        or re.fullmatch(r"c-[0-9a-f]{1,32}", case_id) is None
        or type(required_mentions) is not int
        or not 0 <= required_mentions <= 10_000
        or not is_sha256(script_sha256)
    ):
        raise ValueError("Invalid isolated benchmark configuration")
    result: dict[str, Any] = {
        "case_id": case_id,
        "program_sha256": script_sha256,
        "mechanism": "linux-bwrap-strace.v1",
        "reference_boundary_declared": reference_root is not None,
        "status": "UNSUPPORTED",
        "counts": None,
        "required_support": {"documents": 1, "mentions": required_mentions},
        "network_attempts": 0,
        "memory_limit_events": 0,
        "audit_integrity_events": 0,
        "strict_custody_accredited": False,
        "capabilities": {
            "native_network_namespace": False,
            "native_syscall_audit": False,
            "restricted_filesystem": False,
        },
        "limits": {
            **asdict(limits),
            "hard_memory_kind": "RLIMIT_AS_ADDRESS_SPACE",
            "admission_metadata": "caller_declared_expansion_members_depth_pixels",
        },
        "quality": "DESCRIPTIVE_ONLY",
    }
    try:
        payload = json.dumps(input_payload, allow_nan=False, ensure_ascii=False).encode("utf-8")
        strict_json(payload)
        measurements = _AdmissionMeasurements(
            expanded_bytes=expanded_bytes,
            archive_members=archive_members,
            nesting_depth=nesting_depth,
            pixels=pixels,
        )
        if len(payload) > MAX_RESOURCE_BYTES or measurements.exceeds(limits):
            result["status"] = "ADMISSION_LIMIT"
        else:
            code = _read_file(Path(script), MAX_RESOURCE_BYTES)
            if hashlib.sha256(code).hexdigest() != script_sha256:
                raise ValueError
            loaded_assets: dict[str, bytes] = {}
            for asset in assets:
                if (
                    not isinstance(asset, LocalAsset)
                    or re.fullmatch(r"asset-[0-9a-f]{1,32}", asset.asset_id) is None
                    or asset.asset_id in loaded_assets
                    or not is_sha256(asset.sha256)
                ):
                    raise ValueError
                if reference_root is not None and asset.path.resolve().is_relative_to(
                    reference_root.resolve()
                ):
                    raise ValueError
                blob = _read_file(asset.path, MAX_RESOURCE_BYTES)
                if hashlib.sha256(blob).hexdigest() != asset.sha256:
                    raise ValueError
                loaded_assets[asset.asset_id] = blob
            if sum(map(len, loaded_assets.values())) + len(payload) + len(code) > MAX_PACKAGE_BYTES:
                result["status"] = "ADMISSION_LIMIT"
            elif (
                sys.platform == "linux"
                and (bwrap := shutil.which("bwrap"))
                and (strace := shutil.which("strace"))
                and not (
                    reference_root is not None
                    and any(
                        reference_root.resolve().is_relative_to(root.resolve())
                        or root.resolve().is_relative_to(reference_root.resolve())
                        for root in _runtime_mounts()
                    )
                )
            ):
                _execute(result, code, payload, loaded_assets, limits, bwrap, strace)
    except subprocess.SubprocessError:
        result["status"] = "UNSUPPORTED"
    except FileNotFoundError:
        result["status"] = "MISSING_ASSET"
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        result["status"] = "INVALID_RUN"
    report = {"schema_version": "df-eval-mx.isolated-case.v1", "result": result}
    _write_report(Path(output), report)
    return report


def _execute(
    result: dict[str, Any],
    code: bytes,
    payload: bytes,
    assets: dict[str, bytes],
    limits: IsolationLimits,
    bwrap: str,
    strace: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="deidflow-isolated-") as directory:
        root = Path(directory)
        for name in ("task", "inputs", "assets"):
            (root / name).mkdir(mode=0o700)
        (root / "task" / "candidate.py").write_bytes(code)
        (root / "inputs" / "input.json").write_bytes(payload)
        for name, blob in assets.items():
            (root / "assets" / name).write_bytes(blob)
        timed_out = False
        with (root / "stdout").open("wb") as stdout, (root / "stderr").open("wb") as stderr:
            process = subprocess.Popen(
                _command(root, bwrap, strace),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                env={"PATH": "/usr/bin:/bin"},
                start_new_session=True,
                preexec_fn=lambda: _set_limits(limits),
            )
            try:
                process.wait(timeout=limits.wall_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                if sys.platform == "win32":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        audited, network, memory, integrity = _trace_summary(root, limits.output_bytes)
        result.update(
            network_attempts=network, memory_limit_events=memory, audit_integrity_events=integrity
        )
        result["capabilities"] = dict.fromkeys(result["capabilities"], audited)
        result["capabilities"]["native_syscall_audit"] = audited and not integrity
        if timed_out:
            result["status"] = "TIMEOUT"
        elif network or integrity:
            result["status"] = "LOCAL_POLICY_VIOLATION"
        elif memory or process.returncode in _LIMIT_RETURN_CODES:
            result["status"] = "RESOURCE_LIMIT"
        elif not audited:
            result["status"] = "UNSUPPORTED"
        elif process.returncode:
            result["status"] = "CANDIDATE_ERROR"
        else:
            try:
                result["counts"] = _response(
                    _read_file(root / "stdout", limits.output_bytes),
                    result["required_support"]["mentions"],
                )
                result["status"] = "COMPLETED"
                result["strict_custody_accredited"] = result["reference_boundary_declared"]
            except (ValueError, OSError, UnicodeError, RecursionError):
                result["status"] = "MALFORMED_RESPONSE"
