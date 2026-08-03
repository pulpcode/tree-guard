from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/prepare_fire_m4_silver_intent_approval.py"
RECORDED_AT = "2030-01-02T03:06:00Z"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_intent_approval_preparation",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M4 Silver Intent approval preparation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREPARATION = _load_module()


class FireM4SilverIntentApprovalTests(unittest.TestCase):
    def test_approval_is_exact_private_and_contains_no_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            silver_dir = root / "silver"
            PREPARATION.SILVER_FREEZE.prepare(RECORDED_AT, silver_dir)

            path, digest = PREPARATION.write_approval(silver_dir, root)
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))

            self.assertEqual(sha256(raw).hexdigest(), digest)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(payload["quality_tier"], "SILVER")
            self.assertFalse(payload["gold_eligible"])
            self.assertFalse(payload["gate_eligible"])
            self.assertFalse(payload["contains_oracle"])
            self.assertFalse(payload["contains_credentials"])
            self.assertEqual(payload["scenario_count"], 8)
            self.assertEqual(
                payload["possible_request_body_count"],
                PREPARATION.POSSIBLE_REQUEST_BODY_COUNT,
            )
            self.assertEqual(payload["maximum_actual_request_count"], 16)
            self.assertEqual(
                len(
                    {
                        item["wire_sha256"]
                        for item in payload["possible_requests"]
                    }
                ),
                PREPARATION.POSSIBLE_REQUEST_BODY_COUNT,
            )
            self.assertEqual(
                {
                    item["retry_code"]
                    for item in payload["possible_requests"]
                    if item["retry_code"] is not None
                },
                set(PREPARATION.RETRY_CODES),
            )
            wire_text = "".join(
                item["wire_body_text"] for item in payload["possible_requests"]
            )
            for forbidden in (
                '"acceptable_node_ids"',
                '"authorization_hash"',
                '"oracle"',
                '"target_node_id"',
            ):
                self.assertNotIn(forbidden, wire_text)


if __name__ == "__main__":
    unittest.main()
