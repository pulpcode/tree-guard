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
    PROJECT_ROOT
    / "scripts/prepare_fire_m4_silver_downstream_isolation_approval.py"
)
RECORDED_AT = "2030-01-02T03:06:00Z"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_downstream_isolation_preparation",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load downstream isolation preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREPARATION = _load_module()


def _write_private_json(path: Path, payload: dict) -> str:
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(raw)
    return sha256(raw).hexdigest()


class FireM4SilverDownstreamIsolationPreparationTests(unittest.TestCase):
    def _sources(self, root: Path):
        silver_dir = root / "silver"
        PREPARATION.SEMANTIC_PREP.INTENT_APPROVAL_PREP.SILVER_FREEZE.prepare(
            RECORDED_AT,
            silver_dir,
        )
        contexts = {
            context.reviewed.plan_unit_ref: context
            for context in PREPARATION.SEMANTIC_PREP.INTENT_APPROVAL_PREP.SILVER_FREEZE.CALIBRATION_PREP.load_calibration_execution_contexts()
        }
        authorization_batch = json.loads(
            (silver_dir / "silver-authorizations.json").read_text()
        )
        authorization_items = {
            item["plan_unit_ref"]: item
            for item in authorization_batch["items"]
        }
        results = []
        reference_items = []
        for plan_unit_ref in sorted(contexts):
            context = contexts[plan_unit_ref]
            request = PREPARATION.build_intent_request(context)
            authorization_hash = authorization_items[plan_unit_ref][
                "authorization"
            ]["authorization_hash"]
            results.append(
                {
                    "authorization_hash": authorization_hash,
                    "plan_unit_ref": plan_unit_ref,
                    "request_hash": request.request_hash,
                    "status": "RUN_FAILED",
                }
            )
            if plan_unit_ref not in PREPARATION.REFERENCE_REFS:
                continue
            reference_items.append(
                {
                    "assessment_codes": [],
                    "authorization_hash": authorization_hash,
                    "intent": {
                        "assumptions": [],
                        "cardinality": request.cardinality_hint,
                        "clarification_question": None,
                        "confirmed_facts": ["这是完全虚构的测试字段。"],
                        "evidence_gaps": [],
                        "lifecycle": None,
                        "node_kind": request.node_kind_hint,
                        "ownership": "UNKNOWN",
                        "role": None,
                        "scenario": None,
                        "schema_version": "change-intent-model-output.v1",
                        "subject": "完全虚构的测试字段",
                        "value_type": request.value_type_hint,
                    },
                    "plan_unit_ref": plan_unit_ref,
                    "request_hash": request.request_hash,
                }
            )
        intent_results = {
            "schema_version": "treeguard-m4-silver-bailian-intent-results.v1",
            "dataset_ref": "fictional-fire-m4-calibration-silver-v1",
            "evaluation_role": "CALIBRATION",
            "quality_tier": "SILVER",
            "gold_eligible": False,
            "gate_eligible": False,
            "scenario_count": 8,
            "actual_request_count": 8,
            "results": results,
        }
        intent_results_path = root / "intent-results.json"
        intent_results_sha256 = _write_private_json(
            intent_results_path,
            intent_results,
        )
        reference = {
            "assessment_authority": "CODEX_ASSISTED",
            "dataset_ref": "fictional-fire-m4-calibration-silver-v1",
            "end_to_end_eligible": False,
            "gate_eligible": False,
            "gold_eligible": False,
            "intended_use": "DOWNSTREAM_ISOLATION_ONLY",
            "items": reference_items,
            "quality_tier": "SILVER",
            "recorded_at": RECORDED_AT,
            "schema_version": "treeguard-m4-silver-reference-intents.v1",
            "source_intent_results_sha256": intent_results_sha256,
            "status": "SILVER_REFERENCE_ACCEPTED",
        }
        reference_path = root / "reference-intents.json"
        reference_sha256 = _write_private_json(reference_path, reference)
        return (
            silver_dir,
            intent_results_path,
            intent_results_sha256,
            reference_path,
            reference_sha256,
        )

    def test_build_is_source_bound_and_never_calls_intent_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sources = self._sources(Path(temporary))

            approval = PREPARATION.build_approval(
                sources[3],
                sources[4],
                sources[1],
                sources[2],
                sources[0],
            )

            self.assertEqual(approval["scenario_count"], 5)
            self.assertEqual(len(approval["intent_replay"]), 5)
            self.assertFalse(approval["intent_provider_called"])
            self.assertFalse(approval["end_to_end_eligible"])
            self.assertFalse(approval["gate_eligible"])
            self.assertFalse(approval["gold_eligible"])
            self.assertEqual(
                approval["possible_request_body_count"],
                approval["semantic_scenario_count"]
                * (1 + len(PREPARATION.SEMANTIC_PREP.SEMANTIC_RETRY_CODES)),
            )
            self.assertEqual(
                {
                    item["retry_code"]
                    for item in approval["possible_requests"]
                },
                {None, *PREPARATION.SEMANTIC_PREP.SEMANTIC_RETRY_CODES},
            )

    def test_reference_policy_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = self._sources(root)
            payload = json.loads(sources[3].read_text())
            payload["end_to_end_eligible"] = True
            tampered = root / "tampered-reference.json"
            digest = _write_private_json(tampered, payload)

            with self.assertRaises(
                PREPARATION.M4SilverDownstreamIsolationError
            ) as captured:
                PREPARATION.build_approval(
                    tampered,
                    digest,
                    sources[1],
                    sources[2],
                    sources[0],
                )

            self.assertEqual(
                captured.exception.code,
                "SILVER_REFERENCE_INTENTS_INVALID",
            )

    def test_private_reference_requires_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = self._sources(root)
            os.chmod(sources[3], 0o644)

            with self.assertRaises(
                PREPARATION.M4SilverDownstreamIsolationError
            ) as captured:
                PREPARATION.build_approval(
                    sources[3],
                    sources[4],
                    sources[1],
                    sources[2],
                    sources[0],
                )

            self.assertEqual(stat.S_IMODE(sources[3].stat().st_mode), 0o644)
            self.assertEqual(
                captured.exception.code,
                "SILVER_REFERENCE_INTENTS_INVALID",
            )


if __name__ == "__main__":
    unittest.main()
