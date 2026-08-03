from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/prepare_fire_m4_silver_semantic_approval.py"
)
RECORDED_AT = "2030-01-02T03:06:00Z"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_semantic_approval_preparation",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4 Silver Semantic approval preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREPARATION = _load_module()


class FireM4SilverSemanticApprovalTests(unittest.TestCase):
    def test_replay_provider_keeps_method_callable(self) -> None:
        sentinel = object()
        provider = PREPARATION.ReplayIntentProvider(sentinel)

        self.assertIs(provider.draft(None, None), sentinel)
        with self.assertRaises(RuntimeError):
            PREPARATION.ReplayIntentProvider(None).draft(None, None)

    def test_all_failed_intent_results_produce_no_semantic_egress(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            silver_dir = root / "silver"
            PREPARATION.INTENT_APPROVAL_PREP.SILVER_FREEZE.prepare(
                RECORDED_AT,
                silver_dir,
            )
            authorization_batch = json.loads(
                (silver_dir / "silver-authorizations.json").read_text()
            )
            authorization_items = {
                item["plan_unit_ref"]: item
                for item in authorization_batch["items"]
            }
            contexts = (
                PREPARATION.INTENT_APPROVAL_PREP.SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
            )
            results = []
            for context in contexts:
                plan_unit_ref = context.reviewed.plan_unit_ref
                request = PREPARATION.IntentRequest.from_dict(
                    {
                        "schema_version": PREPARATION.REQUEST_SCHEMA_VERSION,
                        "requirement_text": (
                            context.reviewed.request.requirement_text
                        ),
                        "proposed_parent_node_id": (
                            context.reviewed.request.proposed_parent_node_id
                        ),
                        "node_kind_hint": (
                            context.reviewed.request.node_kind_hint
                        ),
                        "value_type_hint": (
                            context.reviewed.request.value_type_hint
                        ),
                        "cardinality_hint": (
                            context.reviewed.request.cardinality_hint
                        ),
                    },
                    context.tree,
                )
                results.append(
                    {
                        "authorization_hash": authorization_items[
                            plan_unit_ref
                        ]["authorization"]["authorization_hash"],
                        "calls": [],
                        "draft": None,
                        "failure_code": "FICTIONAL_TEST_FAILURE",
                        "plan_unit_ref": plan_unit_ref,
                        "request_hash": request.request_hash,
                        "scenario_ref": context.scenario_ref,
                        "status": "RUN_FAILED",
                    }
                )
            payload = {
                "schema_version": (
                    "treeguard-m4-silver-bailian-intent-results.v1"
                ),
                "approval_file_sha256": "0" * 64,
                "dataset_ref": "fictional-fire-m4-calibration-silver-v1",
                "evaluation_role": "CALIBRATION",
                "gate_eligible": False,
                "gold_eligible": False,
                "model": PREPARATION.DEFAULT_MODEL,
                "prompt_version": "fictional-test",
                "quality_tier": "SILVER",
                "scenario_count": 8,
                "actual_request_count": 8,
                "draft_ready_count": 0,
                "run_failed_count": 8,
                "results": results,
            }
            result_path = root / "intent-results.json"
            raw = (
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode("utf-8")
            descriptor = os.open(
                result_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as output:
                output.write(raw)
            self.assertEqual(stat.S_IMODE(result_path.stat().st_mode), 0o600)

            approval = PREPARATION.build_approval(
                result_path,
                sha256(raw).hexdigest(),
                silver_dir,
            )

            self.assertEqual(approval["semantic_scenario_count"], 0)
            self.assertEqual(approval["possible_request_body_count"], 0)
            self.assertEqual(approval["maximum_actual_request_count"], 0)
            self.assertEqual(approval["possible_requests"], [])


if __name__ == "__main__":
    unittest.main()
