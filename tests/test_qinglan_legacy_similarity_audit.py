from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_qinglan_legacy_similarity import (
    REQUIRED_FROZEN_ARTIFACTS,
    run_audit,
)


def _node(
    node_id: str,
    name: str,
    node_type: str,
    children: dict[str, dict] | None = None,
) -> dict:
    metadata = {
        "node_id": node_id,
        "node_name": name,
        "node_type": node_type,
    }
    if node_type == "property":
        metadata.update({"is_list": False, "value_type": "string"})
    result = {"metadata": metadata}
    if children:
        result["subnodes"] = children
    return result


def _tree(prefix: str, names: tuple[str, str, str], *, cleanroom: bool) -> dict:
    root, branch, facet = names
    document = {
        "map_topology": {
            f"{prefix}-root": _node(
                f"{prefix}-1",
                root,
                "concept",
                {
                    f"{prefix}-branch": _node(
                        f"{prefix}-2",
                        branch,
                        "concept",
                        {
                            f"{prefix}-facet": _node(
                                f"{prefix}-3",
                                facet,
                                "property",
                            )
                        },
                    )
                },
            )
        },
        "metadata": {},
    }
    if cleanroom:
        document["metadata"] = {
            "source_class": "CLEANROOM_SYNTHETIC",
            "fictional": True,
            "derived_from_real": False,
            "gold_eligible": False,
            "patch_eligible": False,
        }
    return document


def _scenario(text: str, *, cleanroom: bool) -> dict:
    item = {"request": {"requirement_text": text}}
    if cleanroom:
        item.update(
            {
                "source_class": "CLEANROOM_SYNTHETIC",
                "fictional": True,
                "gold_eligible": False,
                "patch_eligible": False,
            }
        )
    return item


class QinglanLegacySimilarityAuditTests(unittest.TestCase):
    def _arrange(
        self,
        root: Path,
        *,
        new_names: tuple[str, str, str],
        legacy_names: tuple[str, str, str],
    ) -> tuple[Path, Path]:
        run_dir = root / "run"
        legacy_dir = root / "legacy"
        run_dir.mkdir()
        legacy_dir.mkdir()

        documents = {
            "tree.json": _tree("new", new_names, cleanroom=True),
            "scenarios.json": [
                _scenario("记录青色容器的静默温度。", cleanroom=True)
            ],
            "semantic-blueprint.json": {
                "source_class": "CLEANROOM_SYNTHETIC"
            },
        }
        for name in REQUIRED_FROZEN_ARTIFACTS:
            value = documents.get(name, {"fixture": name})
            (run_dir / name).write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        artifacts = []
        for name in sorted(REQUIRED_FROZEN_ARTIFACTS):
            artifacts.append(
                {
                    "path": name,
                    "byte_sha256": hashlib.sha256(
                        (run_dir / name).read_bytes()
                    ).hexdigest(),
                }
            )
        freeze_manifest = {
            "candidate_state": "FROZEN",
            "dataset_ref": "fictional-test-v1",
            "run_ref": "fictional-test-v1-run-001",
            "source_class": "CLEANROOM_SYNTHETIC",
            "fictional": True,
            "derived_from_real": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "artifacts": artifacts,
        }
        (run_dir / "freeze-manifest.json").write_text(
            json.dumps(freeze_manifest, sort_keys=True),
            encoding="utf-8",
        )

        (legacy_dir / "tree-small.json").write_text(
            json.dumps(
                _tree("old", legacy_names, cleanroom=False),
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (legacy_dir / "scenarios-small.json").write_text(
            json.dumps(
                {
                    "items": [
                        _scenario("校验红色轨道的脉冲密度。", cleanroom=False)
                    ]
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return run_dir, legacy_dir

    def test_disjoint_abstract_inputs_are_accepted_without_content_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, legacy_dir = self._arrange(
                Path(directory),
                new_names=("蓝庭", "容器区", "静默温度"),
                legacy_names=("赤站", "轨道区", "脉冲密度"),
            )

            result = run_audit(run_dir, legacy_dir)

        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["finding_codes"], [])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("赤站", serialized)
        self.assertNotIn("轨道区", serialized)
        self.assertNotIn("脉冲密度", serialized)

    def test_exact_node_copy_is_rejected_by_frozen_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, legacy_dir = self._arrange(
                Path(directory),
                new_names=("蓝庭", "容器区", "静默温度"),
                legacy_names=("赤站", "远航区", "静默温度"),
            )

            result = run_audit(run_dir, legacy_dir)

        self.assertEqual(result["decision"], "REJECT")
        self.assertIn("NODE_EXACT_OVERLAP", result["finding_codes"])
        self.assertIn("SUBJECT_FACET_COPY", result["checks"])

    def test_changed_frozen_artifact_stops_before_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, legacy_dir = self._arrange(
                Path(directory),
                new_names=("蓝庭", "容器区", "静默温度"),
                legacy_names=("赤站", "轨道区", "脉冲密度"),
            )
            (run_dir / "tree.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "frozen artifact changed"):
                run_audit(run_dir, legacy_dir)

    def test_additional_frozen_artifact_is_also_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir, legacy_dir = self._arrange(
                Path(directory),
                new_names=("蓝庭", "容器区", "静默温度"),
                legacy_names=("赤站", "轨道区", "脉冲密度"),
            )
            extra_path = run_dir / "tree-scope-review.json"
            extra_path.write_text(
                json.dumps({"decision": "CONFIRM_SCOPE"}, sort_keys=True),
                encoding="utf-8",
            )
            manifest_path = run_dir / "freeze-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"].append(
                {
                    "path": extra_path.name,
                    "byte_sha256": hashlib.sha256(
                        extra_path.read_bytes()
                    ).hexdigest(),
                }
            )
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True),
                encoding="utf-8",
            )

            self.assertEqual(
                run_audit(run_dir, legacy_dir)["decision"],
                "ACCEPT",
            )
            extra_path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "frozen artifact changed"):
                run_audit(run_dir, legacy_dir)


if __name__ == "__main__":
    unittest.main()
