from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.evaluate_navigation_semantic_v2_dev import (
    build_development_units,
    evaluate_development_units,
    main,
)
from treeguard.ai_review import BailianProviderError
from treeguard.navigation_copilot import NavigationSemanticDraftV2


class TargetOnlyProvider:
    def __init__(self, expected_by_projection):
        self.expected_by_projection = expected_by_projection
        self.calls = 0

    def compare(self, projection, tree):
        self.calls += 1
        expected = self.expected_by_projection[projection.projection_hash]
        return NavigationSemanticDraftV2.from_model_dict(
            {
                "schema_version": "navigation-copilot-semantic-output.v2",
                "candidate_assessments": [
                    {
                        "candidate_ref": item.candidate_ref,
                        "relation": (
                            "SEMANTICALLY_EQUIVALENT"
                            if item.candidate_ref == expected
                            else "NOT_EQUIVALENT"
                        ),
                        "reason": "Bounded fictional development assessment.",
                    }
                    for item in projection.candidates
                ],
            },
            projection,
            tree,
            model_provider="DETERMINISTIC_TEST_PROVIDER",
            model_name="fixture-model",
            prompt_version="fixture-semantic.v2",
        )


class FailingProvider:
    def __init__(self):
        self.calls = 0

    def compare(self, projection, tree):
        self.calls += 1
        raise BailianProviderError(
            "BAILIAN_CONNECTION_FAILED",
            "private response canary must not enter the report",
        )


class NavigationSemanticV2DevelopmentEvaluationTests(unittest.TestCase):
    def test_existing_cleanroom_dataset_builds_eleven_oracle_isolated_units(self):
        _, units = build_development_units()

        self.assertEqual(len(units), 11)
        self.assertTrue(all(unit.expected_candidate_ref for unit in units))
        for unit in units:
            model_input = unit.projection.to_model_dict()
            self.assertIn("requirement_text", model_input)
            self.assertNotIn("expected_candidate_ref", model_input)
            self.assertNotIn("oracle", model_input)

    def test_repository_fixture_tampering_fails_cleanroom_replay(self):
        source_root = (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "fictional"
            / "fire_validation"
        )
        with tempfile.TemporaryDirectory() as directory_name:
            data_root = Path(directory_name)
            for name in (
                "manifest.json",
                "tree-medium.json",
                "scenarios-medium.json",
            ):
                shutil.copyfile(source_root / name, data_root / name)
            scenarios_path = data_root / "scenarios-medium.json"
            scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
            scenarios["items"][0]["request"]["requirement_text"] = (
                "Untrusted imported request canary."
            )
            scenarios_path.write_text(
                json.dumps(scenarios, ensure_ascii=False),
                encoding="utf-8",
            )

            with (
                patch(
                    "scripts.evaluate_navigation_semantic_v2_dev.DATA_ROOT",
                    data_root,
                ),
                self.assertRaisesRegex(ValueError, "clean-room generator"),
            ):
                build_development_units()

    def test_aggregate_scores_strict_policy_without_item_content(self):
        _, units = build_development_units()
        expected = {
            unit.projection.projection_hash: unit.expected_candidate_ref
            for unit in units
        }
        provider = TargetOnlyProvider(expected)

        report = evaluate_development_units(provider)

        self.assertEqual(provider.calls, 11)
        self.assertEqual(report["planned_unit_count"], 11)
        self.assertEqual(report["retrieval_eligible_count"], 11)
        self.assertEqual(report["model_valid_count"], 11)
        self.assertEqual(report["correct_highlight_count"], 10)
        self.assertEqual(report["incorrect_highlight_count"], 0)
        self.assertEqual(report["safe_nonhighlight_count"], 1)
        self.assertEqual(report["failure_code_counts"], {})
        self.assertFalse(report["qualification_eligible"])
        for forbidden in (
            "requirement_text",
            "candidate_ref",
            "node_id",
            "projection_hash",
            "oracle",
        ):
            self.assertNotIn(forbidden, report)

    def test_provider_failures_remain_fixed_aggregate_only(self):
        provider = FailingProvider()

        report = evaluate_development_units(provider)

        self.assertEqual(provider.calls, 11)
        self.assertEqual(report["model_valid_count"], 0)
        self.assertEqual(report["provider_failure_count"], 11)
        self.assertEqual(
            report["failure_code_counts"],
            {"BAILIAN_CONNECTION_FAILED": 11},
        )
        self.assertEqual(report["policy_status_counts"], {})
        self.assertNotIn("private response canary", json.dumps(report))

    def test_live_configuration_failure_returns_stable_aggregate(self):
        output = StringIO()
        with (
            patch(
                "scripts.evaluate_navigation_semantic_v2_dev.BailianConfig.from_env",
                side_effect=BailianProviderError(
                    "BAILIAN_API_KEY_MISSING",
                    "test-only configuration failure",
                ),
            ),
            redirect_stdout(output),
        ):
            exit_code = main(["--live"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "report_version": (
                    "treeguard.navigation-semantic-v2-dev-evaluation.v1"
                ),
                "status": "BAILIAN_API_KEY_MISSING",
            },
        )


if __name__ == "__main__":
    unittest.main()
