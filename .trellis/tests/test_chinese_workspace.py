from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import add_session  # noqa: E402
from common.developer import init_developer  # noqa: E402
from common.task_store import _has_subagent_platform  # noqa: E402
from common.task_context import _resolve_allowed_context_path  # noqa: E402


class ChineseWorkspaceTest(unittest.TestCase):
    def test_get_current_session_accepts_chinese_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            index = Path(temp_dir) / "index.md"
            index.write_text("- **会话总数**：12\n", encoding="utf-8")

            self.assertEqual(add_session.get_current_session(index), 12)

    def test_generated_session_uses_chinese_headings(self) -> None:
        content = add_session.generate_session_content(
            session_num=2,
            title="规范审查",
            commit="abc1234",
            summary="完成最小审查",
            extra_content="- 更新规范",
            today="2026-07-28",
            branch="main",
        )

        self.assertIn("## 会话 2：规范审查", content)
        self.assertIn("### 摘要", content)
        self.assertIn("### 主要变更", content)
        self.assertIn("### 验证", content)
        self.assertNotIn("### Summary", content)

    def test_new_developer_workspace_is_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / ".trellis").mkdir()

            self.assertTrue(init_developer("agent-alias", repo_root))

            workspace = repo_root / ".trellis" / "workspace" / "agent-alias"
            index = (workspace / "index.md").read_text(encoding="utf-8")
            journal = (workspace / "journal-1.md").read_text(encoding="utf-8")
            self.assertIn("## 当前状态", index)
            self.assertIn("**会话总数**：0", index)
            self.assertIn("# 工作日志：agent-alias", journal)

    def test_update_index_preserves_chinese_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dev_dir = Path(temp_dir)
            (dev_dir / "journal-1.md").write_text(
                "# 工作日志：agent-alias\n", encoding="utf-8"
            )
            index = dev_dir / "index.md"
            index.write_text(
                """# 工作区索引

<!-- @@@auto:current-status -->
- **活动文件**：`journal-1.md`
- **会话总数**：0
- **最近活动**：-
<!-- @@@/auto:current-status -->

<!-- @@@auto:active-documents -->
| 文件 | 行数 | 状态 |
|---|---:|---|
| `journal-1.md` | ~1 | 活动 |
<!-- @@@/auto:active-documents -->

<!-- @@@auto:session-history -->
| # | 日期 | 标题 | 提交 | 分支 |
|---:|---|---|---|---|
<!-- @@@/auto:session-history -->
""",
                encoding="utf-8",
            )

            self.assertTrue(
                add_session.update_index(
                    index_file=index,
                    dev_dir=dev_dir,
                    title="规范审查",
                    commit="abc1234",
                    new_session=1,
                    active_file="journal-1.md",
                    today="2026-07-28",
                    branch="main",
                )
            )

            updated = index.read_text(encoding="utf-8")
            self.assertIn("**会话总数**：1", updated)
            self.assertIn("| 1 | 2026-07-28 | 规范审查 |", updated)
            self.assertIn("| 文件 | 行数 | 状态 |", updated)

    def test_codex_inline_does_not_seed_jsonl_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / ".codex").mkdir()

            self.assertFalse(_has_subagent_platform(repo_root))

    def test_context_paths_are_confined_to_spec_and_current_research(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            task_dir = repo_root / ".trellis" / "tasks" / "demo-task"
            spec_file = repo_root / ".trellis" / "spec" / "backend" / "index.md"
            research_file = task_dir / "research" / "note.md"
            code_file = repo_root / "src" / "secret.py"
            other_research = (
                repo_root
                / ".trellis"
                / "tasks"
                / "other-task"
                / "research"
                / "note.md"
            )
            for path in (spec_file, research_file, code_file, other_research):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            (task_dir / "task.json").write_text("{}", encoding="utf-8")

            _, spec_path = _resolve_allowed_context_path(
                repo_root, task_dir, ".trellis/spec/backend/index.md"
            )
            _, research_path = _resolve_allowed_context_path(
                repo_root,
                task_dir,
                ".trellis/tasks/demo-task/research/note.md",
            )
            self.assertEqual(spec_path, ".trellis/spec/backend/index.md")
            self.assertEqual(
                research_path,
                ".trellis/tasks/demo-task/research/note.md",
            )

            rejected = [
                "src/secret.py",
                "../outside.md",
                str(code_file.resolve()),
                ".trellis/tasks/other-task/research/note.md",
            ]
            for candidate in rejected:
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        _resolve_allowed_context_path(
                            repo_root, task_dir, candidate
                        )

            outside = repo_root / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            link = task_dir / "research" / "escape.md"
            link.symlink_to(outside)
            with self.assertRaises(ValueError):
                _resolve_allowed_context_path(
                    repo_root,
                    task_dir,
                    ".trellis/tasks/demo-task/research/escape.md",
                )


if __name__ == "__main__":
    unittest.main()
