"""Private runtime boundaries and exact ownership of temporary files."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import secrets
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

_MARKERS = (
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
    "CODEX_RUN_ID",
    "CODEX_CI",
    "CODEX_SANDBOX_NETWORK_DISABLED",
)
_OWNER = "deidflow-private-owned-v1"


class PrivateError(RuntimeError):
    """Only fixed public error codes may cross the private-runtime boundary."""

    def __init__(self, code: str = "PRIVATE_OPERATION_FAILED") -> None:
        self.code = (
            code
            if code
            in {
                "EXTERNAL_TERMINAL_REQUIRED",
                "PRIVATE_PATH_REQUIRED",
                "PRIVATE_PERMISSIONS_FAILED",
                "PRIVATE_CONFIG_INVALID",
                "PRIVATE_AUTH_REQUIRED",
                "PRIVATE_AUTH_FAILED",
                "PERSONAL_ACCOUNT_REQUIRED",
                "READ_ONLY_SCOPE_REQUIRED",
                "PRIVATE_API_FAILED",
                "PRIVATE_RESPONSE_INVALID",
                "PRIVATE_LIMIT_EXCEEDED",
                "PRIVATE_OPERATION_FAILED",
                "ANNOTATION_CONSENT_REQUIRED",
                "ANNOTATION_INVALID",
                "SOURCE_CHANGED",
                "PRIVATE_REPORT_INVALID",
            }
            else "PRIVATE_OPERATION_FAILED"
        )
        super().__init__(self.code)


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Argparse normally echoes unknown values/paths to stderr.
        raise PrivateError("PRIVATE_CONFIG_INVALID")


def require_external_terminal(acknowledged: bool, *, environ: dict[str, str] | None = None) -> None:
    values = os.environ if environ is None else environ
    if acknowledged is not True or any(values.get(k) for k in _MARKERS):
        raise PrivateError("EXTERNAL_TERMINAL_REQUIRED")


def private_path(path: str | Path) -> Path:
    """Reject repositories/Codex workspaces, symlinks and ambiguous paths."""
    try:
        if not Path(path).expanduser().is_absolute():
            raise PrivateError("PRIVATE_PATH_REQUIRED")
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_absolute() or any(
            p.casefold() in {"codex", ".codex"} for p in resolved.parts
        ):
            raise PrivateError("PRIVATE_PATH_REQUIRED")
        for ancestor in (Path(path).expanduser(), *Path(path).expanduser().parents):
            if ancestor.exists() and ancestor.is_symlink():
                raise PrivateError("PRIVATE_PATH_REQUIRED")
        if any((p / ".git").exists() for p in (resolved, *resolved.parents)):
            raise PrivateError("PRIVATE_PATH_REQUIRED")
        return resolved
    except PrivateError:
        raise
    except Exception:
        raise PrivateError("PRIVATE_PATH_REQUIRED") from None


def protect(path: Path, *, directory: bool) -> None:
    """User-only POSIX mode or protected Windows DACL; never print identities."""
    try:
        if os.name != "nt":
            path.chmod(0o700 if directory else 0o600)
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise OSError
            return
        # Use a fixed OS command solely for the current security identifier.
        root = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        result = subprocess.run(
            [str(root / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        import csv

        sid = next(csv.reader([result.stdout.strip()]))[-1]
        if not sid.startswith("S-1-") or not all(c in "S-0123456789" for c in sid):
            raise OSError
        descriptor = ctypes.c_void_p()
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
        ]
        convert.restype = ctypes.c_int
        inheritance = "OICI" if directory else ""
        if not convert(f"D:P(A;{inheritance};FA;;;{sid})", 1, ctypes.byref(descriptor), None):
            raise OSError
        try:
            present, defaulted, dacl = ctypes.c_int(), ctypes.c_int(), ctypes.c_void_p()
            get_dacl = advapi.GetSecurityDescriptorDacl
            get_dacl.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_int),
            ]
            if not get_dacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
            ):
                raise OSError
            setter = advapi.SetNamedSecurityInfoW
            setter.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_int,
                ctypes.c_ulong,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            setter.restype = ctypes.c_ulong
            if setter(str(path), 1, 0x80000004, None, None, dacl, None) != 0:
                raise OSError
        finally:
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree(descriptor)
    except Exception:
        raise PrivateError("PRIVATE_PERMISSIONS_FAILED") from None


def secure_directory(path: str | Path) -> Path:
    target = private_path(path)
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect(target, directory=True)
    return target


def write_private(path: Path, data: bytes, *, overwrite: bool = False) -> None:
    private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("wb" if overwrite else "xb") as handle:
        protect(path, directory=False)
        handle.write(data)


@contextmanager
def temporary_workspace(root: Path) -> Iterator[Path]:
    parent = secure_directory(root)
    path = Path(tempfile.mkdtemp(prefix=".deidflow-session-", dir=parent))
    protect(path, directory=True)
    nonce = secrets.token_hex(32)
    marker = path / ".deidflow-owned.json"
    write_private(
        marker, json.dumps({"owner": _OWNER, "nonce": nonce, "directory": path.name}).encode()
    )
    try:
        yield path
    finally:
        cleanup_owned(path, parent, nonce=nonce)


def cleanup_owned(path: Path, parent: Path, *, nonce: str | None = None) -> None:
    """Delete only a validated child lease created by this runner, never root."""
    try:
        if (
            path.is_symlink()
            or path.resolve().parent != parent.resolve()
            or not path.name.startswith(".deidflow-session-")
        ):
            raise ValueError
        marker = json.loads((path / ".deidflow-owned.json").read_text(encoding="utf-8"))
        if (
            set(marker) != {"owner", "nonce", "directory"}
            or marker["owner"] != _OWNER
            or marker["directory"] != path.name
            or not isinstance(marker["nonce"], str)
            or len(marker["nonce"]) != 64
            or (nonce is not None and marker["nonce"] != nonce)
        ):
            raise ValueError
        shutil.rmtree(path)
    except Exception:
        raise PrivateError("PRIVATE_OPERATION_FAILED") from None
