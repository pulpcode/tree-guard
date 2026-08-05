from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from treeguard.hashing import canonical_digest
from treeguard.navigation_shadow_cli import (
    NavigationShadowCliError,
    _validate_qualification_sources,
    main,
)
from treeguard.navigation_shadow_run import (
    NavigationShadowRunManifest,
    build_shadow_qualification,
)
from treeguard.private_io import read_private_json, write_private_json


class NavigationShadowCliTests(unittest.TestCase):
    def test_prepare_and_aggregate_private_cross_instance_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "run.json"
            prepare_stdout = io.StringIO()
            with redirect_stdout(prepare_stdout):
                exit_code = main(
                    [
                        "prepare-run",
                        "--run-ref", "SR0001",
                        "--contract-commit", "0" * 40,
                        "--provider-mode", "QWEN_LIVE",
                        "--participant-ref", "P01",
                        "--participant-ref", "P02",
                        "--participant-ref", "P03",
                        "--output", str(manifest_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                json.loads(prepare_stdout.getvalue())["status"],
                "SHADOW_RUN_FROZEN",
            )
            manifest = NavigationShadowRunManifest.from_dict(
                read_private_json(manifest_path, max_bytes=64 * 1024)
            )
            sidecar_roots = []
            for participant_index, participant_ref in enumerate(("P01", "P02", "P03")):
                sidecar_root = root / f"sidecars-{participant_ref}"
                sidecar_root.mkdir(mode=0o700)
                case_directory = sidecar_root / f"NC{participant_index:03d}"
                case_directory.mkdir(mode=0o700)
                decision_payload = {
                    "schema_version": "navigation-copilot-policy-decision.v1",
                    "policy_version": "treeguard.navigation-copilot-policy.v1",
                    "semantic_approval": False,
                    "patch_eligible": False,
                    "source_interpretation_hash": f"{participant_index + 1:064x}",
                    "source_candidate_set_hash": "2" * 64,
                    "source_projection_hash": "3" * 64,
                    "source_semantic_draft_hash": "4" * 64,
                    "status": "CANDIDATES_AVAILABLE",
                    "highlighted_candidate_ref": "C001",
                    "reason_code": "COPILOT_UNIQUE_EQUIVALENT",
                    "semantic_status": "SUCCEEDED",
                }
                decision_hash = canonical_digest(decision_payload)
                decision_artifact = {
                    **decision_payload,
                    "decision_hash": decision_hash,
                }
                outcome_payload = {
                    "schema_version": "navigation-copilot-outcome.v1",
                    "record_semantics": "OPERATIONAL_FEEDBACK_ONLY",
                    "semantic_approval": False,
                    "gold_eligible": False,
                    "patch_eligible": False,
                    "source_decision_hash": decision_hash,
                    "action": "SELECT_CANDIDATE",
                    "selected_candidate_ref": "C001",
                    "selected_node_id": "fictional-node",
                    "candidate_miss": False,
                    "user_corrected": False,
                    "duration_ms": 60_000,
                }
                outcome_hash = canonical_digest(outcome_payload)
                outcome_artifact = {
                    **outcome_payload,
                    "outcome_hash": outcome_hash,
                }
                qualification = build_shadow_qualification(
                    manifest,
                    participant_ref,
                    SimpleNamespace(
                        decision_hash=decision_hash,
                        status="CANDIDATES_AVAILABLE",
                    ),
                    SimpleNamespace(
                        source_decision_hash=decision_hash,
                        action="SELECT_CANDIDATE",
                        outcome_hash=outcome_hash,
                        duration_ms=60_000,
                    ),
                    rejection_disposition=None,
                    clarification_used=False,
                    model_degraded=False,
                )
                self.assertTrue(
                    write_private_json(
                        case_directory / "08-policy-decision.json",
                        decision_artifact,
                    )
                )
                self.assertTrue(
                    write_private_json(
                        case_directory / "09-outcome.json",
                        outcome_artifact,
                    )
                )
                self.assertTrue(
                    write_private_json(
                        case_directory / "10-shadow-qualification.json",
                        qualification.to_dict(),
                    )
                )
                sidecar_roots.extend(["--sidecar-root", str(sidecar_root)])

            output = root / "aggregate.json"
            aggregate_stdout = io.StringIO()
            with redirect_stdout(aggregate_stdout):
                exit_code = main(
                    [
                        "aggregate",
                        "--manifest", str(manifest_path),
                        *sidecar_roots,
                        "--output", str(output),
                    ]
                )
            self.assertEqual(exit_code, 0)
            report = json.loads(aggregate_stdout.getvalue())
            self.assertEqual(report["decision"], "COLLECTING")
            self.assertEqual(report["record_count"], 3)
            self.assertEqual(report["participant_count"], 3)
            self.assertNotIn("participant_refs", report)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            tampered_outcome = dict(outcome_artifact)
            tampered_outcome["duration_ms"] = 60_001
            with self.assertRaises(NavigationShadowCliError) as caught:
                _validate_qualification_sources(
                    qualification,
                    decision_artifact,
                    tampered_outcome,
                )
            self.assertEqual(caught.exception.code, "SHADOW_OUTCOME_SOURCE_INVALID")

    def test_prepare_rejects_public_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "prepare-run",
                        "--run-ref", "SR0001",
                        "--contract-commit", "0" * 40,
                        "--provider-mode", "QWEN_LIVE",
                        "--participant-ref", "P01",
                        "--participant-ref", "P02",
                        "--participant-ref", "P03",
                        "--output", str(root / "run.json"),
                    ]
                )
            self.assertEqual(exit_code, 2)
            self.assertFalse((root / "run.json").exists())
            self.assertEqual(
                json.loads(stdout.getvalue())["error_code"],
                "WORKBENCH_SIDECAR_DIRECTORY_UNSAFE",
            )


if __name__ == "__main__":
    unittest.main()
