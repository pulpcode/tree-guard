"""Private, bounded JSON file IO for sensitive sidecar workflows."""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any

from treeguard.json_utils import strict_json_loads


def read_private_json(path: Path, *, max_bytes: int) -> Any:
    """Read one private regular JSON file without following a final symlink."""

    if (
        not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or max_bytes < 1
    ):
        raise ValueError("max_bytes must be a positive integer")
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size > max_bytes
            or file_stat.st_mode & 0o077
        ):
            raise OSError("input is not a bounded private regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise OSError("input exceeds its size limit")
        return strict_json_loads(raw.decode("utf-8"))
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def preflight_private_output(path: Path) -> None:
    """Verify that an immutable private output can be created later."""

    try:
        os.lstat(path)
    except FileNotFoundError:
        pass
    except OSError:
        raise OSError("private output path cannot be inspected safely") from None
    else:
        raise OSError("private output path already exists")

    probe = path.parent / (
        f".{path.name}.treeguard-preflight-{secrets.token_hex(8)}.tmp"
    )
    descriptor = -1
    try:
        descriptor = os.open(
            probe,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(descriptor)
        descriptor = -1
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise OSError("private output directory is not writable") from None
    finally:
        try:
            os.unlink(probe)
        except OSError:
            pass


def write_private_json(path: Path, payload: Any) -> bool:
    """Atomically publish one immutable 0600 JSON file without overwriting."""

    try:
        encoded = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return False

    descriptor = -1
    temporary_path = path.parent / (
        f".{path.name}.treeguard-{secrets.token_hex(12)}.tmp"
    )
    published = False
    try:
        descriptor = os.open(
            temporary_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise OSError("private output write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary_path, path, follow_symlinks=False)
        published = True
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        return False
    finally:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
    return published


__all__ = [
    "preflight_private_output",
    "read_private_json",
    "write_private_json",
]
