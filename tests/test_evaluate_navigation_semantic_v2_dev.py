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
    evaluate_end_to_end_development_units,
    evaluate_understanding_development_units,
    main,
)
from treeguard.ai_review import BailianProviderError
from treeguard.change_understanding_v2 import ChangeUnderstandingV2
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


class ReplayUnderstandingProvider:
    def __init__(self, expected_by_request, *, clarify=False):
        self.expected_by_request = expected_by_request
        self.clarify = clarify
        self.calls = 0

    def understand(
        self,
        request,
        tree,
        *,
        clarification_question=None,
        clarification_answer=None,
    ):
        self.calls += 1
        expected = self.expected_by_request[request.request_hash]
        if not self.clarify:
            return expected
        target = expected.role_evidence.spans[0].text
        return ChangeUnderstandingV2.from_model_dict(
            {
                "schema_version": "change-understanding-model-output.v2",
                "node_kind": expected.structural_intent.node_kind,
                "value_type": expected.structural_intent.value_type,
                "cardinality": expected.structural_intent.cardinality,
                "clarification_question": "请确认这个虚构目标。",
                "spans": [{"role": "TARGET", "text": target}],
            },
            request,
            tree,
            model_provider="DETERMINISTIC_TEST_PROVIDER",
            model_capability="SOURCE_BOUND_FIXTURE",
            model_name="fixture-model",
            prompt_version="fixture-understanding.v2",
        )


class FailingUnderstandingProvider:
    def __init__(self):
        self.calls = 0

    def understand(
        self,
        request,
        tree,
        *,
        clarification_question=None,
        clarification_answer=None,
    ):
        self.calls += 1
        raise BailianProviderError(
            "BAILIAN_CONNECTION_FAILED",
            "private understanding response canary",
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

    def test_understanding_aggregate_measures_false_clarification_without_text(self):
        _, units = build_development_units()
        expected = {
            unit.request.request_hash: unit.interpretation.understanding
            for unit in units
        }
        provider = ReplayUnderstandingProvider(expected, clarify=True)

        report = evaluate_understanding_development_units(provider)

        self.assertEqual(provider.calls, 11)
        self.assertEqual(report["model_valid_count"], 11)
        self.assertEqual(report["profile_match_count"], 11)
        self.assertEqual(report["unexpected_clarification_count"], 11)
        self.assertEqual(report["provider_failure_count"], 0)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "requirement_text",
            "clarification_question",
            "request_hash",
            "node_id",
            "oracle",
            "虚构目标",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_end_to_end_uses_model_understanding_before_semantic(self):
        _, units = build_development_units()
        understanding = ReplayUnderstandingProvider(
            {
                unit.request.request_hash: unit.interpretation.understanding
                for unit in units
            }
        )
        semantic = TargetOnlyProvider(
            {
                unit.projection.projection_hash: unit.expected_candidate_ref
                for unit in units
            }
        )

        report = evaluate_end_to_end_development_units(
            understanding,
            semantic,
        )

        self.assertEqual(understanding.calls, 11)
        self.assertEqual(semantic.calls, 11)
        self.assertEqual(report["understanding_valid_count"], 11)
        self.assertEqual(report["unexpected_clarification_count"], 0)
        self.assertEqual(report["retrieval_eligible_count"], 11)
        self.assertEqual(report["semantic_valid_count"], 11)
        self.assertEqual(report["correct_highlight_count"], 10)
        self.assertEqual(report["incorrect_highlight_count"], 0)
        self.assertEqual(report["safe_nonhighlight_count"], 1)
        self.assertEqual(report["failure_code_counts"], {})
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "requirement_text",
            "candidate_ref",
            "node_id",
            "request_hash",
            "oracle",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_end_to_end_stops_before_semantic_on_clarification_or_failure(self):
        _, units = build_development_units()
        expected = {
            unit.request.request_hash: unit.interpretation.understanding
            for unit in units
        }
        semantic_expected = {
            unit.projection.projection_hash: unit.expected_candidate_ref
            for unit in units
        }
        for understanding, expected_clarifications, expected_failures in (
            (ReplayUnderstandingProvider(expected, clarify=True), 11, 0),
            (FailingUnderstandingProvider(), 0, 11),
        ):
            with self.subTest(provider=type(understanding).__name__):
                semantic = TargetOnlyProvider(semantic_expected)
                report = evaluate_end_to_end_development_units(
                    understanding,
                    semantic,
                )
                self.assertEqual(understanding.calls, 11)
                self.assertEqual(semantic.calls, 0)
                self.assertEqual(
                    report["unexpected_clarification_count"],
                    expected_clarifications,
                )
                self.assertEqual(
                    report["provider_failure_count"],
                    expected_failures,
                )
                self.assertEqual(report["retrieval_eligible_count"], 0)
                self.assertEqual(report["semantic_valid_count"], 0)
                self.assertNotIn(
                    "private understanding response canary",
                    json.dumps(report),
                )

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

    def test_understanding_live_configuration_failure_uses_stage_report(self):
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
            exit_code = main(["--live", "--stage", "understanding"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "report_version": (
                    "treeguard.navigation-understanding-v2-dev-evaluation.v1"
                ),
                "status": "BAILIAN_API_KEY_MISSING",
            },
        )


if __name__ == "__main__":
    unittest.main()
