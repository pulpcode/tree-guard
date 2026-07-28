#!/usr/bin/env python3
"""
Task JSONL context management.

Provides:
    cmd_add_context   - Add entry to JSONL context file
    cmd_validate      - Validate JSONL context files
    cmd_list_context  - List JSONL context entries

Note:
    TreeGuard's supported Codex inline workflow does not consume JSONL context.
    These commands remain for Trellis compatibility and enforce an allowlist so
    a future/manual consumer cannot read arbitrary local paths.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .log import Colors, colored
from .paths import get_repo_root
from .task_utils import resolve_task_dir


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_allowed_context_path(
    repo_root: Path,
    target_dir: Path,
    raw_path: str,
) -> tuple[Path, str]:
    """Resolve one context entry inside the approved spec/research roots.

    TreeGuard's Codex workflow does not consume JSONL, but the generic Trellis
    commands remain present. Fail closed so a manually edited manifest cannot
    turn a future consumer into an arbitrary local-file reader.
    """
    candidate = Path(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("path must be repository-relative and must not contain '..'")

    repo_resolved = repo_root.resolve()
    tasks_root = (repo_resolved / ".trellis" / "tasks").resolve()
    task_resolved = target_dir.resolve()
    if (
        task_resolved.parent != tasks_root
        or task_resolved.name == "archive"
        or not (task_resolved / "task.json").is_file()
    ):
        raise ValueError("context is allowed only for an active task directory")

    try:
        resolved = (repo_resolved / candidate).resolve(strict=True)
    except OSError as exc:
        raise ValueError("path does not exist") from exc

    spec_root = (repo_resolved / ".trellis" / "spec").resolve()
    research_root = task_resolved / "research"
    if not (
        (_is_within(spec_root, repo_resolved) and _is_within(resolved, spec_root))
        or _is_within(resolved, research_root)
    ):
        raise ValueError(
            "path must be under .trellis/spec or the current task research directory"
        )

    normalized = resolved.relative_to(repo_resolved).as_posix()
    return resolved, normalized


# =============================================================================
# Command: add-context
# =============================================================================

def cmd_add_context(args: argparse.Namespace) -> int:
    """Add entry to JSONL context file."""
    repo_root = get_repo_root()
    target_dir = resolve_task_dir(args.dir, repo_root)

    jsonl_name = args.file
    path = args.path
    reason = args.reason or "Added manually"

    if not target_dir.is_dir():
        print(colored(f"Error: Directory not found: {target_dir}", Colors.RED))
        return 1

    # Support shorthand
    if not jsonl_name.endswith(".jsonl"):
        jsonl_name = f"{jsonl_name}.jsonl"

    jsonl_file = target_dir / jsonl_name
    try:
        full_path, path = _resolve_allowed_context_path(repo_root, target_dir, path)
    except ValueError as exc:
        print(colored(f"Error: Invalid context path: {exc}", Colors.RED))
        return 1

    entry_type = "directory" if full_path.is_dir() else "file"
    if entry_type == "directory":
        path = f"{path}/"

    # Check if already exists
    if jsonl_file.is_file():
        content = jsonl_file.read_text(encoding="utf-8")
        if f'"{path}"' in content:
            print(colored(f"Warning: Entry already exists for {path}", Colors.YELLOW))
            return 0

    # Add entry
    entry: dict
    if entry_type == "directory":
        entry = {"file": path, "type": "directory", "reason": reason}
    else:
        entry = {"file": path, "reason": reason}

    with jsonl_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(colored(f"Added {entry_type}: {path}", Colors.GREEN))
    return 0


# =============================================================================
# Command: validate
# =============================================================================

def cmd_validate(args: argparse.Namespace) -> int:
    """Validate JSONL context files."""
    repo_root = get_repo_root()
    target_dir = resolve_task_dir(args.dir, repo_root)

    if not target_dir.is_dir():
        print(colored("Error: task directory required", Colors.RED))
        return 1

    print(colored("=== Validating Context Files ===", Colors.BLUE))
    print(f"Target dir: {target_dir}")
    print()

    total_errors = 0
    for jsonl_name in ["implement.jsonl", "check.jsonl"]:
        jsonl_file = target_dir / jsonl_name
        errors = _validate_jsonl(jsonl_file, repo_root, target_dir)
        total_errors += errors

    print()
    if total_errors == 0:
        print(colored("✓ All validations passed", Colors.GREEN))
        return 0
    else:
        print(colored(f"✗ Validation failed ({total_errors} errors)", Colors.RED))
        return 1


def _validate_jsonl(jsonl_file: Path, repo_root: Path, target_dir: Path) -> int:
    """Validate a single JSONL file.

    Seed rows (no ``file`` field — typically ``{"_example": "..."}``) are
    skipped silently; they are self-describing comments, not real entries.
    """
    file_name = jsonl_file.name
    errors = 0

    if not jsonl_file.is_file():
        print(f"  {colored(f'{file_name}: not found (skipped)', Colors.YELLOW)}")
        return 0

    line_num = 0
    real_entries = 0
    for line in jsonl_file.read_text(encoding="utf-8").splitlines():
        line_num += 1
        if not line.strip():
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            print(f"  {colored(f'{file_name}:{line_num}: Invalid JSON', Colors.RED)}")
            errors += 1
            continue

        file_path = data.get("file")
        entry_type = data.get("type", "file")

        if not file_path:
            # Seed / comment row — skip silently
            continue

        real_entries += 1
        if not isinstance(file_path, str) or entry_type not in ("file", "directory"):
            print(f"  {colored(f'{file_name}:{line_num}: Invalid entry fields', Colors.RED)}")
            errors += 1
            continue

        try:
            full_path, _ = _resolve_allowed_context_path(
                repo_root, target_dir, file_path.rstrip("/")
            )
        except ValueError as exc:
            print(
                f"  {colored(f'{file_name}:{line_num}: Invalid context path: {exc}', Colors.RED)}"
            )
            errors += 1
            continue

        if entry_type == "directory" and not full_path.is_dir():
            print(f"  {colored(f'{file_name}:{line_num}: Not a directory: {file_path}', Colors.RED)}")
            errors += 1
        elif entry_type == "file" and not full_path.is_file():
            print(f"  {colored(f'{file_name}:{line_num}: Not a file: {file_path}', Colors.RED)}")
            errors += 1

    if errors == 0:
        print(f"  {colored(f'{file_name}: ✓ ({real_entries} entries)', Colors.GREEN)}")
    else:
        print(f"  {colored(f'{file_name}: ✗ ({errors} errors)', Colors.RED)}")

    return errors


# =============================================================================
# Command: list-context
# =============================================================================

def cmd_list_context(args: argparse.Namespace) -> int:
    """List JSONL context entries."""
    repo_root = get_repo_root()
    target_dir = resolve_task_dir(args.dir, repo_root)

    if not target_dir.is_dir():
        print(colored("Error: task directory required", Colors.RED))
        return 1

    print(colored("=== Context Files ===", Colors.BLUE))
    print()

    for jsonl_name in ["implement.jsonl", "check.jsonl"]:
        jsonl_file = target_dir / jsonl_name
        if not jsonl_file.is_file():
            continue

        print(colored(f"[{jsonl_name}]", Colors.CYAN))

        count = 0
        seed_only = True
        for line in jsonl_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            file_path = data.get("file")
            if not file_path:
                # Seed / comment row — don't count as a real entry
                continue
            seed_only = False

            count += 1
            entry_type = data.get("type", "file")
            reason = data.get("reason", "-")

            if entry_type == "directory":
                print(f"  {colored(f'{count}.', Colors.GREEN)} [DIR] {file_path}")
            else:
                print(f"  {colored(f'{count}.', Colors.GREEN)} {file_path}")
            print(f"     {colored('→', Colors.YELLOW)} {reason}")

        if seed_only:
            print(f"  {colored('(no curated entries yet — only seed row)', Colors.YELLOW)}")

        print()

    return 0
