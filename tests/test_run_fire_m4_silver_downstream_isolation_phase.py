from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/run_fire_m4_silver_downstream_isolation_phase.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_silver_downstream_isolation_phase_run_test",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load downstream isolation runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_module()


class FireM4SilverDownstreamIsolationRunTests(unittest.TestCase):
    def test_approval_requires_exact_bytes_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            approval_path = Path(temporary) / "approval.json"
            expected = {
                "evaluation_role": "DOWNSTREAM_ISOLATION",
                "end_to_end_eligible": False,
            }
            raw = (
                json.dumps(expected, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            descriptor = os.open(
                approval_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as output:
                output.write(raw)
            digest = sha256(raw).hexdigest()
            with patch.object(
                RUNNER.APPROVAL_PREP,
                "build_approval",
                return_value=expected,
            ):
                loaded = RUNNER.read_approval(
                    approval_path,
                    digest,
                    Path("reference"),
                    "1" * 64,
                    Path("intent-results"),
                    "2" * 64,
                    Path("silver"),
                )
                self.assertEqual(loaded, expected)
                with self.assertRaises(
                    RUNNER.M4SilverDownstreamIsolationRunError
                ) as captured:
                    RUNNER.read_approval(
                        approval_path,
                        "0" * 64,
                        Path("reference"),
                        "1" * 64,
                        Path("intent-results"),
                        "2" * 64,
                        Path("silver"),
                    )
            self.assertEqual(
                captured.exception.code,
                "SILVER_DOWNSTREAM_ISOLATION_APPROVAL_INVALID",
            )

    def test_provider_rejects_unapproved_body_before_network(self) -> None:
        provider = RUNNER.SEMANTIC_RUNNER.ApprovedSemanticProvider(
            RUNNER.BailianConfig(
                api_key="NOT_USED",
                base_url=RUNNER.DEFAULT_BASE_URL,
                model=RUNNER.DEFAULT_MODEL,
            ),
            set(),
            [],
        )

        with self.assertRaises(RuntimeError):
            provider._post_json({"outside": "approval"})

        self.assertEqual(
            provider.policy_error,
            "SILVER_SEMANTIC_BODY_NOT_APPROVED",
        )


if __name__ == "__main__":
    unittest.main()
