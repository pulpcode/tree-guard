"""Shared private directory boundary for Workbench sidecar services."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class WorkbenchSidecarError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def ensure_private_directory(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    except OSError:
        raise WorkbenchSidecarError(
            "WORKBENCH_SIDECAR_DIRECTORY_UNSAFE",
            "private sidecar directory could not be created",
        ) from None
    try:
        file_stat = os.lstat(path)
    except OSError:
        raise WorkbenchSidecarError(
            "WORKBENCH_SIDECAR_DIRECTORY_UNSAFE",
            "private sidecar directory could not be inspected",
        ) from None
    current_uid = os.getuid() if hasattr(os, "getuid") else None
    if (
        not stat.S_ISDIR(file_stat.st_mode)
        or file_stat.st_mode & 0o077
        or (current_uid is not None and file_stat.st_uid != current_uid)
    ):
        raise WorkbenchSidecarError(
            "WORKBENCH_SIDECAR_DIRECTORY_UNSAFE",
            "private sidecar directory is not private",
        )


def create_private_directory(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
    except OSError:
        raise WorkbenchSidecarError(
            "WORKBENCH_SIDECAR_DIRECTORY_UNSAFE",
            "private case directory could not be created",
        ) from None
    ensure_private_directory(path)


__all__ = [
    "WorkbenchSidecarError",
    "create_private_directory",
    "ensure_private_directory",
]
