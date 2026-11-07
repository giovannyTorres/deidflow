"""Bounded local resources; never extract or acquire benchmark input."""

from __future__ import annotations

import json
import math
import re
import stat
import zlib
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

MAX_MANIFEST_BYTES = 65_536
MAX_RESOURCE_BYTES = 2 * 1024**2
MAX_PACKAGE_BYTES = 16 * 1024**2
MAX_RESOURCES = 128
MAX_RECORDS = 10_000


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise ValueError


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError
    return result


def _unicode_and_depth(value: Any, depth: int = 0) -> None:
    if depth > 32:
        raise ValueError
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, item in value.items():
            key.encode("utf-8")
            _unicode_and_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _unicode_and_depth(item, depth + 1)


def strict_json(payload: bytes) -> Any:
    value = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=_constant,
        parse_float=_float,
    )
    _unicode_and_depth(value)
    return value


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _safe_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or "\\" in name
        or ":" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise ValueError


def read_member(root: Path, name: str, limit: int) -> bytes:
    _safe_name(name)
    path = root / name
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError
    return content


class PackageReader:
    """Read directories or ZIPs without extracting attacker-controlled members."""

    def __init__(self, path: str | Path) -> None:
        self.root = Path(path).resolve()
        self.archive: ZipFile | None = None
        if self.root.is_dir():
            return
        if not self.root.is_file() or self.root.stat().st_size > MAX_PACKAGE_BYTES:
            raise ValueError
        self.archive = ZipFile(self.root)
        try:
            members = self.archive.infolist()
            if len(members) > 256:
                raise ValueError
            names = set()
            total = 0
            for member in members:
                name = member.filename.removesuffix("/") if member.is_dir() else member.filename
                _safe_name(name)
                mode = member.external_attr >> 16
                total += member.file_size
                if (
                    member.filename != member.orig_filename
                    or member.filename in names
                    or member.flag_bits & 1
                    or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or member.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                    or member.file_size > MAX_RESOURCE_BYTES
                    or member.file_size > 100 * max(1, member.compress_size)
                    or total > MAX_PACKAGE_BYTES
                ):
                    raise ValueError
                names.add(member.filename)
        except Exception:
            self.archive.close()
            raise

    def read(self, name: str, limit: int) -> bytes:
        _safe_name(name)
        if self.archive is None:
            return read_member(self.root, name, limit)
        member = self.archive.getinfo(name)
        if member.is_dir() or member.file_size > limit:
            raise ValueError
        try:
            with self.archive.open(member) as stream:
                payload = stream.read(limit + 1)
        except (BadZipFile, zlib.error, EOFError):
            raise ValueError from None
        if len(payload) > limit:
            raise ValueError
        return payload

    def close(self) -> None:
        if self.archive is not None:
            self.archive.close()
