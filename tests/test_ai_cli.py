from __future__ import annotations

import copy
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from treeguard.ai_cli import _write_internal_output, main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def find_source_node(document: dict, node_id: str) -> dict:
    def walk(wrapper: dict) -> dict | None:
        if wrapper["metadata"]["node_id"] == node_id:
            return wrapper
        for child in wrapper.get("subnodes", {}).values():
            found = walk(child)
            if found is not None:
                return found
        return None

    for root in document["map_topology"].values():
        found = walk(root)
        if found is not None:
            return found
    raise AssertionError(f"fixture node not found: {node_id}")


def version_files(directory: Path) -> tuple[Path, Path]:
    before = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    after = copy.deepcopy(before)
    before["metadata"].update({"version": "V1", "id": "record-v1"})
    after["metadata"].update({"version": "V2", "id": "record-v2"})
    find_source_node(after, "node-008")["metadata"]["node_name"] = "Revised height"
    before_path = directory / "before.json"
    after_path = directory / "after.json"
    before_path.write_text(json.dumps(before), encoding="utf-8")
    after_path.write_text(json.dumps(after), encoding="utf-8")
    return before_path, after_path


class AIReviewCLITests(unittest.TestCase):
    def test_offline_smoke_outputs_aggregate_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            before_path, after_path = version_files(Path(directory_name))
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main([str(before_path), str(after_path)])
            report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "EVIDENCE_PACK_READY")
        self.assertFalse(report["ai"]["called"])
        encoded = json.dumps(report, sort_keys=True)
        self.assertNotIn("node-008", encoded)
        self.assertNotIn("record-v1", encoded)

    def test_live_failure_is_fail_closed_without_sensitive_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            before_path, after_path = version_files(Path(directory_name))
            stdout = io.StringIO()
            previous_directory = Path.cwd()
            os.chdir(directory_name)
            try:
                with (
                    patch.dict("os.environ", {}, clear=True),
                    redirect_stdout(stdout),
                ):
                    exit_code = main(
                        [
                            str(before_path),
                            str(after_path),
                            "--live",
                            "--external-data-approved",
                        ]
                    )
            finally:
                os.chdir(previous_directory)
            report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["valid"])
        self.assertEqual(report["status"], "REJECTED")
        self.assertFalse(report["ai"]["called"])
        self.assertEqual(report["ai"]["status"], "NOT_CALLED")
        self.assertEqual(report["error_code"], "BAILIAN_API_KEY_MISSING")

    def test_live_requires_explicit_external_data_approval(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["not-read.json", "not-read.json", "--live"])
        report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["error_code"], "EXTERNAL_DATA_APPROVAL_REQUIRED")

    def test_internal_output_requires_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before_path, after_path = version_files(directory)
            output_path = directory / "internal.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        str(before_path),
                        str(after_path),
                        "--internal-output",
                        str(output_path),
                    ]
                )
            internal = json.loads(output_path.read_text(encoding="utf-8"))
            output_mode = stat.S_IMODE(output_path.stat().st_mode)

        self.assertEqual(exit_code, 0)
        self.assertIn("review", internal)
        self.assertIn("evidence_pack", internal)
        self.assertIn(
            "reference_to_node_id",
            internal["evidence_pack"],
        )
        self.assertIsNone(internal["ai_review_draft"])
        self.assertEqual(output_mode, 0o600)

    def test_internal_output_failure_returns_fixed_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before_path, after_path = version_files(directory)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        str(before_path),
                        str(after_path),
                        "--internal-output",
                        str(directory),
                    ]
                )
            report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["error_code"], "INTERNAL_OUTPUT_WRITE_FAILED")

    def test_internal_output_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before_path, after_path = version_files(directory)
            output_path = directory / "existing.json"
            output_path.write_text("keep-me", encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        str(before_path),
                        str(after_path),
                        "--internal-output",
                        str(output_path),
                    ]
                )
            report = json.loads(stdout.getvalue())
            existing = output_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["error_code"], "INTERNAL_OUTPUT_WRITE_FAILED")
        self.assertEqual(existing, "keep-me")

    def test_internal_output_publish_failure_leaves_no_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            output_path = directory / "atomic.json"
            real_write = os.write
            write_count = 0

            def partial_then_fail(descriptor, value):
                nonlocal write_count
                write_count += 1
                if write_count == 1:
                    return real_write(descriptor, value[:5])
                raise OSError("fictional disk failure")

            with patch(
                "treeguard.ai_cli.os.write",
                side_effect=partial_then_fail,
            ):
                written = _write_internal_output(
                    output_path,
                    {"sensitive": "canary"},
                )
            leftovers = tuple(directory.iterdir())

        self.assertFalse(written)
        self.assertFalse(output_path.exists())
        self.assertEqual(leftovers, ())

    def test_internal_output_link_failure_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            output_path = directory / "atomic.json"
            with patch(
                "treeguard.ai_cli.os.link",
                side_effect=OSError("fictional publish failure"),
            ):
                written = _write_internal_output(
                    output_path,
                    {"sensitive": "canary"},
                )
            leftovers = tuple(directory.iterdir())

        self.assertFalse(written)
        self.assertFalse(output_path.exists())
        self.assertEqual(leftovers, ())


if __name__ == "__main__":
    unittest.main()
