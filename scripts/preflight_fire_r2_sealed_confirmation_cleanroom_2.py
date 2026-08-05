#!/usr/bin/env python3
"""Aggregate-only preflight for the second R2 sealed clean-room dataset."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from treeguard.adapter import adapt_tree_document
from treeguard.json_utils import strict_json_loads
from treeguard.private_io import read_private_json, write_private_json


BASELINE = "03faee0a7a33e0ee413a4d91b70e8f577085751f"
DATASET = "fire-r2-sealed-confirmation-cleanroom-2-v1"
TASK_PREFIX = ".trellis/tasks/08-04-r2-sealed-confirmation-cleanroom-2/"
PUBLIC_FILES = frozenset(
    {
        "scripts/generate_fire_r2_sealed_confirmation_cleanroom_2.py",
        "scripts/preflight_fire_r2_sealed_confirmation_cleanroom_2.py",
        "tests/fixtures/fictional/fire_r2_sealed_confirmation_cleanroom_2/manifest.v1.json",
        "tests/fixtures/fictional/fire_r2_sealed_confirmation_cleanroom_2/tree.v1.json",
        "tests/test_fire_r2_sealed_confirmation_data.py",
    }
)
PRIVATE_FILES = (
    "01-locked-candidates.v1.json",
    "02-text-role-silver.v1.json",
    "03-oracle-map.v1.json",
    "04-engineering-audit.v1.json",
    "05-frozen-set.v1.json",
    "06-precommit-handoff.v1.json",
)
FINAL_FREEZE_DIRECTORY = "07-final-freeze.v1"
FINAL_FREEZE_FILES = ("binding-ledger.v1.json", "freeze-receipt.v1.json")
LEDGER_SCHEMA = "treeguard.fire-r2-c2-binding-ledger.v1"
RECEIPT_SCHEMA = "treeguard.fire-r2-c2-freeze-receipt.v1"
EXECUTION_SCHEMA = "treeguard.fire-r2-c2-execution-binding.v1"
EXECUTION_LOGICAL_NAME = "execution-binding.v1.json"
CONTRACT_VERSION = "treeguard.fire-r2-sealed-confirmation-cleanroom-2.v1"
INTEGRITY_SEMANTICS = "SHA256_INTEGRITY_ONLY_NOT_IDENTITY_GOLD_OR_PRODUCTION_QUALIFICATION"
CATEGORY_PREFIX = {
    "L": "LEXICAL_BASELINE",
    "W": "BOUNDARY_VARIATION",
    "D": "CROSS_BRANCH_INTERFERENCE",
    "H": "EXCLUSION_HARD_NEGATIVE",
    "P": "NON_LITERAL",
    "O": "EXPLICIT_EMPTY",
}
ALL_IDS = tuple(
    [f"L{i:02d}" for i in range(1, 9)]
    + [f"W{i:02d}" for i in range(1, 9)]
    + [f"D{i:02d}" for i in range(1, 7)]
    + [f"H{i:02d}" for i in range(1, 7)]
    + [f"P{i:02d}" for i in range(1, 5)]
    + [f"O{i:02d}" for i in range(1, 5)]
)
FROZEN_IDS = tuple(
    [f"L{i:02d}" for i in range(1, 7)]
    + [f"W{i:02d}" for i in range(1, 7)]
    + [f"D{i:02d}" for i in range(1, 5)]
    + [f"H{i:02d}" for i in range(1, 5)]
    + [f"P{i:02d}" for i in range(1, 5)]
    + [f"O{i:02d}" for i in range(1, 5)]
)
FROZEN_QUOTA = {
    "BOUNDARY_VARIATION": 6,
    "CROSS_BRANCH_INTERFERENCE": 4,
    "EXCLUSION_HARD_NEGATIVE": 4,
    "EXPLICIT_EMPTY": 4,
    "LEXICAL_BASELINE": 6,
    "NON_LITERAL": 4,
}


class GateError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise GateError(code)


def exact_object(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == keys, code)
    return value


def category(candidate_id: str) -> str:
    return CATEGORY_PREFIX.get(candidate_id[:1], "")


def allowed_public_path(path: str) -> bool:
    return path in PUBLIC_FILES or path.startswith(TASK_PREFIX)


def validate_commit_rows(rows: list[tuple[str, str]]) -> None:
    for operation, path in rows:
        require(operation == "A", "FIRE_R2_C2_NON_ADDITION")
        require(allowed_public_path(path), "FIRE_R2_C2_FUNCTION_DIFF_FORBIDDEN")


def git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_PAGER": "cat"},
    )


def validate_prepare_git(repo: Path) -> None:
    require(git(repo, "rev-parse", "HEAD").stdout.strip() == BASELINE, "FIRE_R2_C2_HEAD_INVALID")
    require(not git(repo, "diff", "--cached", "--name-only").stdout.strip(), "FIRE_R2_C2_INDEX_NOT_CLEAN")
    lines = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
    for line in lines:
        require(line.startswith("?? "), "FIRE_R2_C2_TRACKED_CHANGE_FORBIDDEN")
        require(allowed_public_path(line[3:]), "FIRE_R2_C2_FUNCTION_DIFF_FORBIDDEN")


def validate_commit_binding(repo: Path, data_commit: str) -> tuple[str, ...]:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", data_commit)), "FIRE_R2_C2_DATA_COMMIT_INVALID")
    require(git(repo, "rev-parse", "HEAD").stdout.strip() == data_commit, "FIRE_R2_C2_HEAD_NOT_DATA_COMMIT")
    ancestry = git(repo, "merge-base", "--is-ancestor", BASELINE, data_commit, check=False)
    require(ancestry.returncode == 0, "FIRE_R2_C2_BASELINE_NOT_ANCESTOR")
    require(not git(repo, "status", "--porcelain=v1").stdout.strip(), "FIRE_R2_C2_WORKTREE_NOT_CLEAN")
    rows = []
    for line in git(repo, "diff", "--name-status", "--no-renames", BASELINE, data_commit).stdout.splitlines():
        pieces = line.split("\t")
        require(len(pieces) == 2, "FIRE_R2_C2_GIT_DIFF_INVALID")
        rows.append((pieces[0], pieces[1]))
    validate_commit_rows(rows)
    paths = tuple(path for _, path in rows)
    require(tuple(sorted(paths)) == paths, "FIRE_R2_C2_GIT_DIFF_ORDER_INVALID")
    return paths


def load_generator(repo: Path) -> Any:
    source = repo / "scripts/generate_fire_r2_sealed_confirmation_cleanroom_2.py"
    spec = importlib.util.spec_from_file_location("fire_r2_c2_generator", source)
    require(spec is not None and spec.loader is not None, "FIRE_R2_C2_GENERATOR_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_json(path: Path, limit: int) -> Any:
    require(path.is_file() and not path.is_symlink(), "FIRE_R2_C2_PUBLIC_FILE_INVALID")
    raw = path.read_bytes()
    require(len(raw) <= limit, "FIRE_R2_C2_PUBLIC_FILE_TOO_LARGE")
    try:
        return strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise GateError("FIRE_R2_C2_PUBLIC_JSON_INVALID") from error


def contains_exact_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(contains_exact_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(contains_exact_key(item, key) for item in value)
    return False


def validate_public(repo: Path) -> set[str]:
    generator = load_generator(repo)
    tree_path = repo / generator.TREE_FILE
    manifest_path = repo / generator.MANIFEST_FILE
    require(tree_path.read_bytes() == generator._json_bytes(generator.build_tree()), "FIRE_R2_C2_TREE_BYTES_INVALID")
    require(manifest_path.read_bytes() == generator._json_bytes(generator.build_manifest()), "FIRE_R2_C2_MANIFEST_BYTES_INVALID")
    manifest = public_json(manifest_path, 64_000)
    require(manifest == generator.build_manifest(), "FIRE_R2_C2_MANIFEST_INVALID")
    require("data_commit" not in manifest, "FIRE_R2_C2_MANIFEST_SELF_REFERENCE")
    tree_document = public_json(tree_path, 10_000_000)
    require(not contains_exact_key(tree_document, "value"), "FIRE_R2_C2_VALUE_ENVELOPE_FORBIDDEN")
    imported = adapt_tree_document(tree_document, source_hint="fire-r2-cleanroom-two")
    require(imported.tree is not None, "FIRE_R2_C2_TREE_ADAPT_FAILED")
    require(not imported.issues, "FIRE_R2_C2_TREE_ADAPT_ISSUES")
    require(imported.observed_node_count == 521, "FIRE_R2_C2_TREE_COUNT_INVALID")
    require(imported.observed_value_count == 0, "FIRE_R2_C2_VALUE_COUNT_INVALID")
    identifiers = {node.node_id for node in imported.tree.nodes}
    require(len(identifiers) == 521, "FIRE_R2_C2_NODE_ID_INVALID")
    return identifiers


def validate_private_root(root: Path) -> None:
    require(root.is_absolute(), "FIRE_R2_C2_PRIVATE_ROOT_NOT_ABSOLUTE")
    details = os.lstat(root)
    require(stat.S_ISDIR(details.st_mode), "FIRE_R2_C2_PRIVATE_ROOT_INVALID")
    require(stat.S_IMODE(details.st_mode) == 0o700, "FIRE_R2_C2_PRIVATE_ROOT_MODE_INVALID")
    require(details.st_uid == os.getuid(), "FIRE_R2_C2_PRIVATE_ROOT_OWNER_INVALID")


def private_json(root: Path, filename: str) -> Any:
    path = root / filename
    details = os.lstat(path)
    require(stat.S_ISREG(details.st_mode), "FIRE_R2_C2_PRIVATE_FILE_INVALID")
    require(stat.S_IMODE(details.st_mode) == 0o600, "FIRE_R2_C2_PRIVATE_FILE_MODE_INVALID")
    require(details.st_uid == os.getuid(), "FIRE_R2_C2_PRIVATE_FILE_OWNER_INVALID")
    try:
        return read_private_json(path, max_bytes=2_000_000)
    except (OSError, UnicodeError, ValueError) as error:
        raise GateError("FIRE_R2_C2_PRIVATE_JSON_INVALID") from error


def _regular_file_bytes(
    path: Path,
    *,
    max_bytes: int,
    private: bool,
) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        details = os.fstat(descriptor)
        mode = stat.S_IMODE(details.st_mode)
        require(stat.S_ISREG(details.st_mode), "FIRE_R2_C2_BOUND_FILE_INVALID")
        require(details.st_uid == os.getuid(), "FIRE_R2_C2_BOUND_FILE_OWNER_INVALID")
        if private:
            require(mode == 0o600, "FIRE_R2_C2_BOUND_PRIVATE_MODE_INVALID")
        else:
            require(mode in {0o644, 0o755}, "FIRE_R2_C2_BOUND_PUBLIC_MODE_INVALID")
        require(details.st_size <= max_bytes, "FIRE_R2_C2_BOUND_FILE_TOO_LARGE")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(max_bytes + 1)
        require(len(raw) <= max_bytes, "FIRE_R2_C2_BOUND_FILE_TOO_LARGE")
        return raw
    except GateError:
        raise
    except OSError as error:
        raise GateError("FIRE_R2_C2_BOUND_FILE_INVALID") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_record(path: str, raw: bytes) -> dict[str, Any]:
    return {"byte_length": len(raw), "path": path, "sha256": _sha256(raw)}


def expected_execution_binding() -> dict[str, Any]:
    return {
        "candidate_limit": 20,
        "enable_thinking": False,
        "gate_k_values": [8, 20],
        "max_attempts_per_unit": 2,
        "maximum_actual_call_count": 112,
        "model_id": "qwen3.6-35b-a3b",
        "prompt_version": "treeguard.retrieval-role-extraction.zh.v2",
        "r1_strategy_id": "treeguard.decoupled-role-evidence-retrieval.v1",
        "r2_strategy_id": "treeguard.boundary-tolerant-role-lexical-retrieval.v1",
        "role_contract_version": "retrieval-role-model-output.v1",
        "round_count": 2,
        "scenario_count": 28,
        "schema_version": EXECUTION_SCHEMA,
        "temperature": 0,
    }


def load_execution_binding(path: Path) -> tuple[dict[str, Any], bytes]:
    require(path.is_absolute(), "FIRE_R2_C2_EXECUTION_BINDING_PATH_INVALID")
    raw = _regular_file_bytes(path, max_bytes=32_000, private=True)
    try:
        value = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise GateError("FIRE_R2_C2_EXECUTION_BINDING_JSON_INVALID") from error
    binding = exact_object(
        value,
        {
            "candidate_limit",
            "enable_thinking",
            "gate_k_values",
            "max_attempts_per_unit",
            "maximum_actual_call_count",
            "model_id",
            "prompt_version",
            "r1_strategy_id",
            "r2_strategy_id",
            "role_contract_version",
            "round_count",
            "scenario_count",
            "schema_version",
            "temperature",
        },
        "FIRE_R2_C2_EXECUTION_BINDING_FIELDS_INVALID",
    )
    for field in (
        "schema_version",
        "model_id",
        "prompt_version",
        "role_contract_version",
        "r1_strategy_id",
        "r2_strategy_id",
    ):
        require(type(binding[field]) is str, "FIRE_R2_C2_EXECUTION_BINDING_TYPE_INVALID")
    for field in (
        "temperature",
        "candidate_limit",
        "round_count",
        "scenario_count",
        "max_attempts_per_unit",
        "maximum_actual_call_count",
    ):
        require(type(binding[field]) is int, "FIRE_R2_C2_EXECUTION_BINDING_TYPE_INVALID")
    require(type(binding["enable_thinking"]) is bool, "FIRE_R2_C2_EXECUTION_BINDING_TYPE_INVALID")
    require(
        type(binding["gate_k_values"]) is list
        and all(type(item) is int for item in binding["gate_k_values"]),
        "FIRE_R2_C2_EXECUTION_BINDING_TYPE_INVALID",
    )
    require(binding == expected_execution_binding(), "FIRE_R2_C2_EXECUTION_BINDING_VALUE_INVALID")
    return binding, raw


def build_binding_ledger(
    repo: Path,
    root: Path,
    data_commit: str,
    public_paths: tuple[str, ...],
    execution_binding: dict[str, Any],
    execution_binding_raw: bytes,
) -> dict[str, Any]:
    require(public_paths and tuple(sorted(set(public_paths))) == public_paths, "FIRE_R2_C2_PUBLIC_BINDING_ORDER_INVALID")
    public_records = []
    for relative in public_paths:
        require(allowed_public_path(relative), "FIRE_R2_C2_FUNCTION_DIFF_FORBIDDEN")
        raw = _regular_file_bytes(repo / relative, max_bytes=12_000_000, private=False)
        public_records.append(_file_record(relative, raw))
    private_records = []
    for filename in PRIVATE_FILES:
        raw = _regular_file_bytes(root / filename, max_bytes=2_000_000, private=True)
        private_records.append(_file_record(filename, raw))
    return {
        "contract_version": CONTRACT_VERSION,
        "data_commit": data_commit,
        "dataset_id": DATASET,
        "denominator": 28,
        "execution_binding": execution_binding,
        "execution_binding_file": {
            "byte_length": len(execution_binding_raw),
            "logical_name": EXECUTION_LOGICAL_NAME,
            "sha256": _sha256(execution_binding_raw),
        },
        "function_baseline_commit": BASELINE,
        "integrity_semantics": INTEGRITY_SEMANTICS,
        "opened": False,
        "positive_count": 24,
        "private_files": private_records,
        "public_files": public_records,
        "quota": FROZEN_QUOTA,
        "schema_version": LEDGER_SCHEMA,
        "sealed": True,
        "zero_target_count": 4,
    }


def _private_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _receipt(ledger_raw: bytes, data_commit: str) -> dict[str, Any]:
    return {
        "data_commit": data_commit,
        "dataset_id": DATASET,
        "integrity_semantics": INTEGRITY_SEMANTICS,
        "ledger_byte_length": len(ledger_raw),
        "ledger_sha256": _sha256(ledger_raw),
        "opened": False,
        "schema_version": RECEIPT_SCHEMA,
        "sealed": True,
    }


def _validate_freeze_directory(directory: Path, expected_ledger: dict[str, Any]) -> None:
    try:
        details = os.lstat(directory)
        require(stat.S_ISDIR(details.st_mode), "FIRE_R2_C2_FINAL_DIRECTORY_INVALID")
        require(stat.S_IMODE(details.st_mode) == 0o700, "FIRE_R2_C2_FINAL_DIRECTORY_MODE_INVALID")
        require(details.st_uid == os.getuid(), "FIRE_R2_C2_FINAL_DIRECTORY_OWNER_INVALID")
        require(tuple(sorted(os.listdir(directory))) == FINAL_FREEZE_FILES, "FIRE_R2_C2_FINAL_DIRECTORY_FIELDS_INVALID")
    except GateError:
        raise
    except OSError as error:
        raise GateError("FIRE_R2_C2_FINAL_DIRECTORY_INVALID") from error

    ledger_raw = _regular_file_bytes(directory / FINAL_FREEZE_FILES[0], max_bytes=2_000_000, private=True)
    try:
        ledger = strict_json_loads(ledger_raw.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise GateError("FIRE_R2_C2_LEDGER_JSON_INVALID") from error
    require(ledger == expected_ledger, "FIRE_R2_C2_LEDGER_BINDING_INVALID")
    require(ledger_raw == _private_json_bytes(ledger), "FIRE_R2_C2_LEDGER_BYTES_INVALID")
    require(tuple(item["path"] for item in ledger["public_files"]) == tuple(sorted(item["path"] for item in ledger["public_files"])), "FIRE_R2_C2_LEDGER_PUBLIC_ORDER_INVALID")
    require(tuple(item["path"] for item in ledger["private_files"]) == PRIVATE_FILES, "FIRE_R2_C2_LEDGER_PRIVATE_ORDER_INVALID")

    receipt_raw = _regular_file_bytes(directory / FINAL_FREEZE_FILES[1], max_bytes=64_000, private=True)
    try:
        receipt = strict_json_loads(receipt_raw.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise GateError("FIRE_R2_C2_RECEIPT_JSON_INVALID") from error
    expected_receipt = _receipt(ledger_raw, expected_ledger["data_commit"])
    require(receipt == expected_receipt, "FIRE_R2_C2_RECEIPT_BINDING_INVALID")
    require(receipt_raw == _private_json_bytes(receipt), "FIRE_R2_C2_RECEIPT_BYTES_INVALID")


def _atomic_rename_noreplace(root_descriptor: int, temporary_name: str) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    old_name = os.fsencode(temporary_name)
    new_name = os.fsencode(FINAL_FREEZE_DIRECTORY)
    if sys.platform == "darwin":
        rename = library.renameatx_np
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(root_descriptor, old_name, root_descriptor, new_name, 0x00000004)
    elif sys.platform.startswith("linux"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(root_descriptor, old_name, root_descriptor, new_name, 0x00000001)
    else:
        raise GateError("FIRE_R2_C2_ATOMIC_NOREPLACE_UNSUPPORTED")
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise GateError("FIRE_R2_C2_FINAL_DIRECTORY_EXISTS")
        raise GateError("FIRE_R2_C2_FINAL_RENAME_FAILED")


def _remove_own_freeze_directory(directory: Path) -> None:
    for filename in FINAL_FREEZE_FILES:
        try:
            os.unlink(directory / filename)
        except FileNotFoundError:
            pass
    try:
        os.rmdir(directory)
    except FileNotFoundError:
        pass


def publish_final_freeze(root: Path, ledger: dict[str, Any]) -> None:
    validate_private_root(root)
    final_directory = root / FINAL_FREEZE_DIRECTORY
    try:
        os.lstat(final_directory)
    except FileNotFoundError:
        pass
    except OSError as error:
        raise GateError("FIRE_R2_C2_FINAL_DIRECTORY_INVALID") from error
    else:
        raise GateError("FIRE_R2_C2_FINAL_DIRECTORY_EXISTS")

    temporary_name = f".{FINAL_FREEZE_DIRECTORY}.treeguard-{secrets.token_hex(12)}.tmp"
    temporary_directory = root / temporary_name
    root_descriptor = -1
    published = False
    try:
        root_descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        os.mkdir(temporary_name, mode=0o700, dir_fd=root_descriptor)
        require(write_private_json(temporary_directory / FINAL_FREEZE_FILES[0], ledger), "FIRE_R2_C2_LEDGER_WRITE_FAILED")
        ledger_raw = _regular_file_bytes(temporary_directory / FINAL_FREEZE_FILES[0], max_bytes=2_000_000, private=True)
        require(write_private_json(temporary_directory / FINAL_FREEZE_FILES[1], _receipt(ledger_raw, ledger["data_commit"])), "FIRE_R2_C2_RECEIPT_WRITE_FAILED")
        _validate_freeze_directory(temporary_directory, ledger)
        temporary_descriptor = os.open(temporary_directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)
        _atomic_rename_noreplace(root_descriptor, temporary_name)
        published = True
        os.fsync(root_descriptor)
    except GateError:
        if published:
            _remove_own_freeze_directory(final_directory)
        else:
            _remove_own_freeze_directory(temporary_directory)
        raise
    except OSError as error:
        if published:
            _remove_own_freeze_directory(final_directory)
        else:
            _remove_own_freeze_directory(temporary_directory)
        raise GateError("FIRE_R2_C2_FINAL_PUBLISH_FAILED") from error
    finally:
        if root_descriptor >= 0:
            os.close(root_descriptor)


def verify_final_freeze(root: Path, expected_ledger: dict[str, Any]) -> None:
    validate_private_root(root)
    _validate_freeze_directory(root / FINAL_FREEZE_DIRECTORY, expected_ledger)


def has_digest_field(value: Any) -> bool:
    if isinstance(value, dict):
        if any("digest" in key.lower() or "hash" in key.lower() for key in value):
            return True
        return any(has_digest_field(item) for item in value.values())
    if isinstance(value, list):
        return any(has_digest_field(item) for item in value)
    return False


def validate_private(repo: Path, root: Path, node_ids: set[str]) -> dict[str, int]:
    validate_private_root(root)
    resolved_repo = repo.resolve()
    require(resolved_repo not in root.resolve().parents, "FIRE_R2_C2_PRIVATE_ROOT_IN_REPO")
    documents = [private_json(root, name) for name in PRIVATE_FILES]
    require(not any(has_digest_field(document) for document in documents), "FIRE_R2_C2_PREMATURE_DIGEST")

    locked = exact_object(
        documents[0],
        {"candidate_count", "candidates", "dataset_id", "schema_version", "stage"},
        "FIRE_R2_C2_LOCKED_FIELDS_INVALID",
    )
    require(locked["schema_version"] == "treeguard.fire-r2-c2-locked-candidates.v1", "FIRE_R2_C2_LOCKED_SCHEMA_INVALID")
    require(locked["dataset_id"] == DATASET and locked["stage"] == "LOCKED_REQUESTS", "FIRE_R2_C2_LOCKED_HEADER_INVALID")
    candidates = locked["candidates"]
    require(locked["candidate_count"] == 36 and isinstance(candidates, list) and len(candidates) == 36, "FIRE_R2_C2_CANDIDATE_COUNT_INVALID")
    requests: dict[str, str] = {}
    for item, expected_id in zip(candidates, ALL_IDS, strict=True):
        item = exact_object(
            item,
            {"candidate_id", "primary_category", "request_text", "request_version", "scenario_brief"},
            "FIRE_R2_C2_CANDIDATE_FIELDS_INVALID",
        )
        require(item["candidate_id"] == expected_id, "FIRE_R2_C2_CANDIDATE_ORDER_INVALID")
        require(item["primary_category"] == category(expected_id), "FIRE_R2_C2_CATEGORY_INVALID")
        require(item["request_version"] == "v1", "FIRE_R2_C2_REQUEST_VERSION_INVALID")
        require(isinstance(item["request_text"], str) and 1 <= len(item["request_text"]) <= 600, "FIRE_R2_C2_REQUEST_TEXT_INVALID")
        require(isinstance(item["scenario_brief"], str) and 1 <= len(item["scenario_brief"]) <= 300, "FIRE_R2_C2_BRIEF_INVALID")
        requests[expected_id] = item["request_text"]

    silver = exact_object(
        documents[1],
        {"dataset_id", "entries", "schema_version", "source_stage", "stage"},
        "FIRE_R2_C2_SILVER_FIELDS_INVALID",
    )
    require(silver["schema_version"] == "treeguard.fire-r2-c2-text-silver.v1", "FIRE_R2_C2_SILVER_SCHEMA_INVALID")
    require(silver["dataset_id"] == DATASET and silver["source_stage"] == "LOCKED_REQUESTS" and silver["stage"] == "TEXT_ROLE_SILVER", "FIRE_R2_C2_SILVER_HEADER_INVALID")
    require(isinstance(silver["entries"], list) and len(silver["entries"]) == 36, "FIRE_R2_C2_SILVER_COUNT_INVALID")
    for entry, expected_id in zip(silver["entries"], ALL_IDS, strict=True):
        entry = exact_object(entry, {"candidate_id", "request_version", "roles"}, "FIRE_R2_C2_SILVER_ENTRY_INVALID")
        require(entry["candidate_id"] == expected_id and entry["request_version"] == "v1", "FIRE_R2_C2_SILVER_SOURCE_INVALID")
        require(isinstance(entry["roles"], list) and entry["roles"], "FIRE_R2_C2_ROLES_INVALID")
        names = []
        for role in entry["roles"]:
            role = exact_object(role, {"end", "role", "start", "text"}, "FIRE_R2_C2_ROLE_FIELDS_INVALID")
            names.append(role["role"])
            require(role["role"] in {"TARGET", "SCOPE", "EXCLUSION"}, "FIRE_R2_C2_ROLE_INVALID")
            start, end = role["start"], role["end"]
            require(isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool), "FIRE_R2_C2_SPAN_TYPE_INVALID")
            require(0 <= start < end <= len(requests[expected_id]), "FIRE_R2_C2_SPAN_RANGE_INVALID")
            require(requests[expected_id][start:end] == role["text"], "FIRE_R2_C2_SPAN_BINDING_INVALID")
        require("TARGET" in names, "FIRE_R2_C2_TARGET_MISSING")
        if expected_id.startswith("H"):
            require("EXCLUSION" in names, "FIRE_R2_C2_HARD_NEGATIVE_EXCLUSION_MISSING")

    oracle = exact_object(
        documents[2],
        {"dataset_id", "entries", "schema_version", "source_stage", "stage"},
        "FIRE_R2_C2_ORACLE_FIELDS_INVALID",
    )
    require(oracle["schema_version"] == "treeguard.fire-r2-c2-oracle-map.v1", "FIRE_R2_C2_ORACLE_SCHEMA_INVALID")
    require(oracle["dataset_id"] == DATASET and oracle["source_stage"] == "TEXT_ROLE_SILVER" and oracle["stage"] == "ORACLE_MAPPED", "FIRE_R2_C2_ORACLE_HEADER_INVALID")
    require(isinstance(oracle["entries"], list) and len(oracle["entries"]) == 36, "FIRE_R2_C2_ORACLE_COUNT_INVALID")
    oracle_by_id = {}
    for entry, expected_id in zip(oracle["entries"], ALL_IDS, strict=True):
        entry = exact_object(
            entry,
            {"acceptable_node_ids", "candidate_id", "excluded_node_ids", "primary_category", "request_version", "status", "tags"},
            "FIRE_R2_C2_ORACLE_ENTRY_INVALID",
        )
        require(entry["candidate_id"] == expected_id and entry["request_version"] == "v1", "FIRE_R2_C2_ORACLE_SOURCE_INVALID")
        require(entry["primary_category"] == category(expected_id), "FIRE_R2_C2_ORACLE_CATEGORY_INVALID")
        accepted, excluded = entry["acceptable_node_ids"], entry["excluded_node_ids"]
        require(isinstance(accepted, list) and len(accepted) == len(set(accepted)), "FIRE_R2_C2_ACCEPTED_INVALID")
        require(isinstance(excluded, list) and len(excluded) == len(set(excluded)), "FIRE_R2_C2_EXCLUDED_INVALID")
        require((set(accepted) | set(excluded)) <= node_ids and not set(accepted) & set(excluded), "FIRE_R2_C2_ORACLE_NODE_INVALID")
        if expected_id.startswith("O"):
            require(entry["status"] == "EXPLICIT_EMPTY" and not accepted, "FIRE_R2_C2_EMPTY_INVALID")
        else:
            require(entry["status"] == "HAS_TARGET" and bool(accepted), "FIRE_R2_C2_POSITIVE_INVALID")
        if expected_id.startswith("H"):
            require(bool(excluded), "FIRE_R2_C2_HARD_NEGATIVE_TARGET_INVALID")
        require(isinstance(entry["tags"], list) and all(isinstance(tag, str) and tag for tag in entry["tags"]), "FIRE_R2_C2_TAGS_INVALID")
        oracle_by_id[expected_id] = entry

    audit = exact_object(
        documents[3],
        {"dataset_id", "entries", "schema_version", "source_stage", "stage"},
        "FIRE_R2_C2_AUDIT_FIELDS_INVALID",
    )
    require(audit["schema_version"] == "treeguard.fire-r2-c2-engineering-audit.v1", "FIRE_R2_C2_AUDIT_SCHEMA_INVALID")
    require(audit["dataset_id"] == DATASET and audit["source_stage"] == "ORACLE_MAPPED" and audit["stage"] == "ENGINEERING_AUDITED", "FIRE_R2_C2_AUDIT_HEADER_INVALID")
    require(isinstance(audit["entries"], list) and len(audit["entries"]) == 36, "FIRE_R2_C2_AUDIT_COUNT_INVALID")
    required_checks = ["CLEANROOM_SOURCE", "NATURAL_LANGUAGE", "TEXT_ONLY_SILVER", "ORACLE_AFTER_SILVER", "NO_RESULT_SELECTION"]
    for entry, expected_id in zip(audit["entries"], ALL_IDS, strict=True):
        entry = exact_object(entry, {"candidate_id", "checks", "decision", "note", "primary_category"}, "FIRE_R2_C2_AUDIT_ENTRY_INVALID")
        require(entry["candidate_id"] == expected_id and entry["primary_category"] == category(expected_id), "FIRE_R2_C2_AUDIT_SOURCE_INVALID")
        require(entry["decision"] == "PASS" and entry["checks"] == required_checks, "FIRE_R2_C2_AUDIT_NOT_PASS")
        require(isinstance(entry["note"], str) and entry["note"], "FIRE_R2_C2_AUDIT_NOTE_INVALID")

    frozen = exact_object(
        documents[4],
        {"dataset_id", "quota", "schema_version", "selected_candidate_ids", "selection_rule", "source_stage", "stage"},
        "FIRE_R2_C2_FROZEN_FIELDS_INVALID",
    )
    require(frozen["schema_version"] == "treeguard.fire-r2-c2-frozen-set.v1", "FIRE_R2_C2_FROZEN_SCHEMA_INVALID")
    require(frozen["dataset_id"] == DATASET and frozen["source_stage"] == "ENGINEERING_AUDITED" and frozen["stage"] == "FROZEN_SELECTION", "FIRE_R2_C2_FROZEN_HEADER_INVALID")
    require(frozen["selection_rule"] == "LOWEST_ORDINAL_PASSING_PER_CATEGORY", "FIRE_R2_C2_SELECTION_RULE_INVALID")
    require(tuple(frozen["selected_candidate_ids"]) == FROZEN_IDS and frozen["quota"] == FROZEN_QUOTA, "FIRE_R2_C2_FROZEN_SET_INVALID")
    observed = Counter(oracle_by_id[item]["primary_category"] for item in FROZEN_IDS)
    require(dict(observed) == FROZEN_QUOTA, "FIRE_R2_C2_FROZEN_QUOTA_INVALID")

    handoff = exact_object(
        documents[5],
        {"blocked_by", "data_commit", "dataset_id", "finalizable", "function_baseline_commit", "schema_version", "source_stage", "stage"},
        "FIRE_R2_C2_HANDOFF_FIELDS_INVALID",
    )
    require(handoff["schema_version"] == "treeguard.fire-r2-c2-precommit-handoff.v1", "FIRE_R2_C2_HANDOFF_SCHEMA_INVALID")
    require(handoff["dataset_id"] == DATASET and handoff["source_stage"] == "FROZEN_SELECTION" and handoff["stage"] == "PRECOMMIT_HANDOFF", "FIRE_R2_C2_HANDOFF_HEADER_INVALID")
    require(handoff["function_baseline_commit"] == BASELINE and handoff["data_commit"] is None, "FIRE_R2_C2_HANDOFF_COMMITS_INVALID")
    require(handoff["finalizable"] is False and handoff["blocked_by"] == "DATA_COMMIT_REQUIRED", "FIRE_R2_C2_HANDOFF_GATE_INVALID")

    public_blob = b"\n".join((repo / path).read_bytes() for path in sorted(PUBLIC_FILES) if (repo / path).is_file())
    for request_text in requests.values():
        require(request_text.encode("utf-8") not in public_blob, "FIRE_R2_C2_PRIVATE_REQUEST_LEAK")
    return {"candidate_count": 36, "frozen_count": 28, "positive_count": 24, "zero_target_count": 4}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--mode",
        choices=("prepare", "commit-binding", "finalize", "verify-frozen"),
        required=True,
    )
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--data-commit")
    parser.add_argument("--execution-binding", type=Path)
    options = parser.parse_args()
    repo = options.repo_root.resolve()
    if options.mode == "commit-binding":
        require(options.private_root is None, "FIRE_R2_C2_COMMIT_BINDING_PRIVATE_ROOT_FORBIDDEN")
        require(options.data_commit is not None, "FIRE_R2_C2_DATA_COMMIT_REQUIRED")
        require(options.execution_binding is None, "FIRE_R2_C2_EXECUTION_BINDING_FORBIDDEN")
        validate_public(repo)
        validate_commit_binding(repo, options.data_commit)
        print('{"status":"DATA_COMMIT_BOUND"}')
        return 0
    if options.mode in {"finalize", "verify-frozen"}:
        require(options.private_root is not None, "FIRE_R2_C2_PRIVATE_ROOT_REQUIRED")
        require(options.data_commit is not None, "FIRE_R2_C2_DATA_COMMIT_REQUIRED")
        require(options.execution_binding is not None, "FIRE_R2_C2_EXECUTION_BINDING_REQUIRED")
        public_paths = validate_commit_binding(repo, options.data_commit)
        node_ids = validate_public(repo)
        validate_private(repo, options.private_root, node_ids)
        execution_binding, execution_binding_raw = load_execution_binding(options.execution_binding)
        ledger = build_binding_ledger(
            repo,
            options.private_root,
            options.data_commit,
            public_paths,
            execution_binding,
            execution_binding_raw,
        )
        if options.mode == "finalize":
            publish_final_freeze(options.private_root, ledger)
            print('{"status":"FINAL_FREEZE_CREATED"}')
        else:
            verify_final_freeze(options.private_root, ledger)
            print('{"status":"FINAL_FREEZE_VALID"}')
        return 0
    require(options.execution_binding is None, "FIRE_R2_C2_EXECUTION_BINDING_FORBIDDEN")
    require(options.private_root is not None, "FIRE_R2_C2_PRIVATE_ROOT_REQUIRED")
    require(options.data_commit is None, "FIRE_R2_C2_PREMATURE_DATA_COMMIT")
    node_ids = validate_public(repo)
    summary = validate_private(repo, options.private_root, node_ids)
    validate_prepare_git(repo)
    print(json.dumps({**summary, "blocked_by": "DATA_COMMIT_REQUIRED", "final_freeze_ready": False, "status": "PRECOMMIT_REVIEW_READY"}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as error:
        print(json.dumps({"error_code": error.code, "status": "STOPPED"}, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2) from None
