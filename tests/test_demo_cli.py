from __future__ import annotations

import io
import json
import os
import re
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from treeguard.ai_review import BailianConfig, BailianProviderError
from treeguard.demo_cli import (
    _fictional_intent_model_output,
    _fictional_semantic_model_output,
    main,
)
from treeguard.governance_cli import main as governance_main


def _run(arguments: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(arguments)
    return exit_code, json.loads(stdout.getvalue())


def _run_governance(arguments: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = governance_main(arguments)
    return exit_code, json.loads(stdout.getvalue())


def _provider_response(payload: dict) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps(payload)},
            }
        ]
    }


class GovernanceDemoCLITests(unittest.TestCase):
    def test_offline_confirm_and_reject_are_private_and_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            reports: dict[str, dict] = {}
            for decision in ("confirm", "reject"):
                output = root / decision
                code, report = _run(
                    [
                        "--output-dir",
                        str(output),
                        "--review-decision",
                        decision,
                    ]
                )
                reports[decision] = report
                expected_status = (
                    "CONFIRMED" if decision == "confirm" else "REJECTED"
                )
                self.assertEqual(code, 0)
                self.assertEqual(report["record_status"], expected_status)
                self.assertEqual(
                    report["steps"]["replay_recommendation"],
                    expected_status,
                )
                self.assertTrue(report["fictional_demo"])
                self.assertFalse(report["semantic_approval"])
                self.assertFalse(report["patch_eligible"])
                self.assertFalse(report["gold_eligible"])
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
                self.assertEqual(
                    {
                        stat.S_IMODE(path.stat().st_mode)
                        for path in output.iterdir()
                    },
                    {0o600},
                )
                completion = json.loads(
                    (output / "12-demo-completion.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(completion, report)

            aggregate = json.dumps(reports, sort_keys=True)
            self.assertNotIn("fictional-height", aggregate)
            self.assertNotIn("陈列高度", aggregate)
            self.assertNotIn(directory_name, aggregate)
            self.assertIsNone(re.search(r"\b[0-9a-f]{64}\b", aggregate))

    def test_offline_runs_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            outputs = [root / "first", root / "second"]
            reports = [
                _run(
                    [
                        "--output-dir",
                        str(output),
                        "--review-decision",
                        "confirm",
                    ]
                )
                for output in outputs
            ]
            file_sets = [
                {
                    path.name: path.read_bytes()
                    for path in output.iterdir()
                }
                for output in outputs
            ]

        self.assertEqual([code for code, _ in reports], [0, 0])
        self.assertEqual(reports[0][1], reports[1][1])
        self.assertEqual(file_sets[0], file_sets[1])

    def test_existing_public_and_symlink_output_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            existing = root / "existing"
            existing.mkdir(mode=0o755)
            target = root / "target"
            target.mkdir()
            symlink = root / "linked"
            symlink.symlink_to(target, target_is_directory=True)
            fifo = root / "fifo"
            os.mkfifo(fifo)

            for output in (existing, symlink, fifo):
                with self.subTest(output=output.name):
                    code, report = _run(
                        [
                            "--output-dir",
                            str(output),
                            "--review-decision",
                            "confirm",
                        ]
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(
                        report["error_code"],
                        "DEMO_OUTPUT_DIRECTORY_INVALID",
                    )
                    self.assertFalse(report["completed"])
                    self.assertFalse(
                        (output / "12-demo-completion.json").exists()
                    )

    def test_live_requires_approval_before_output_or_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "not-created"
            with patch(
                "treeguard.demo_cli.governance_main"
            ) as formal_cli:
                code, report = _run(
                    [
                        "--output-dir",
                        str(output),
                        "--review-decision",
                        "confirm",
                        "--mode",
                        "bailian-live",
                    ]
                )

        self.assertEqual(code, 2)
        self.assertEqual(
            report["error_code"],
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertFalse(output.exists())
        formal_cli.assert_not_called()

    def test_live_mode_uses_formal_providers_with_mock_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            offline = root / "offline"
            offline_code, _ = _run(
                [
                    "--output-dir",
                    str(offline),
                    "--review-decision",
                    "confirm",
                ]
            )
            self.assertEqual(offline_code, 0)
            semantic_payload = _fictional_semantic_model_output(
                offline / "07-candidate-set.json"
            )
            responses = [
                _provider_response(_fictional_intent_model_output()),
                _provider_response(semantic_payload),
            ]
            live = root / "live"
            with (
                patch(
                    "treeguard.governance_cli.BailianConfig.from_env",
                    return_value=BailianConfig(api_key="fictional-key"),
                ),
                patch(
                    (
                        "treeguard.ai_review."
                        "BailianAIReviewProvider._post_json"
                    ),
                    side_effect=responses,
                ) as transport,
            ):
                code, report = _run(
                    [
                        "--output-dir",
                        str(live),
                        "--review-decision",
                        "confirm",
                        "--mode",
                        "bailian-live",
                        "--external-data-approved",
                    ]
                )

        self.assertEqual(code, 0)
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(report["mode"], "BAILIAN_LIVE")
        self.assertTrue(report["ai"]["intent_called"])
        self.assertTrue(report["ai"]["semantic_called"])
        self.assertNotIn("fictional-key", json.dumps(report))
        self.assertFalse((live / "03-intent-model-output.json").exists())
        self.assertFalse((live / "08-semantic-model-output.json").exists())

    def test_live_clarification_stops_before_automatic_confirmation(
        self,
    ) -> None:
        intent_payload = _fictional_intent_model_output()
        intent_payload["evidence_gaps"] = [
            "The fictional measurement unit is unknown."
        ]
        intent_payload["clarification_question"] = (
            "Which fictional measurement unit should be used?"
        )
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "live"
            with (
                patch(
                    "treeguard.governance_cli.BailianConfig.from_env",
                    return_value=BailianConfig(api_key="fictional-key"),
                ),
                patch(
                    (
                        "treeguard.ai_review."
                        "BailianAIReviewProvider._post_json"
                    ),
                    return_value=_provider_response(intent_payload),
                ) as transport,
            ):
                code, report = _run(
                    [
                        "--output-dir",
                        str(output),
                        "--review-decision",
                        "confirm",
                        "--mode",
                        "bailian-live",
                        "--external-data-approved",
                    ]
                )
            draft_exists = (output / "04-intent-draft.json").exists()
            action_exists = (
                output / "05-intent-review-action.json"
            ).exists()
            completion_exists = (
                output / "12-demo-completion.json"
            ).exists()

        self.assertEqual(code, 2)
        self.assertEqual(
            report["error_code"],
            "INTENT_CLARIFICATION_REQUIRED",
        )
        self.assertEqual(report["failed_step"], "CLARIFY")
        self.assertEqual(report["status"], "NEEDS_CLARIFICATION")
        self.assertTrue(report["ai"]["called"])
        self.assertEqual(report["ai"]["status"], "COMPLETED")
        self.assertEqual(transport.call_count, 1)
        self.assertTrue(draft_exists)
        self.assertFalse(action_exists)
        self.assertFalse(completion_exists)

    def test_live_semantic_failure_preserves_call_truth_and_no_completion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "live"
            with (
                patch(
                    "treeguard.governance_cli.BailianConfig.from_env",
                    return_value=BailianConfig(api_key="fictional-key"),
                ),
                patch(
                    (
                        "treeguard.ai_review."
                        "BailianAIReviewProvider._post_json"
                    ),
                    side_effect=[
                        _provider_response(
                            _fictional_intent_model_output()
                        ),
                        BailianProviderError(
                            "BAILIAN_CONNECTION_FAILED",
                            "fictional transport failure",
                        ),
                    ],
                ) as transport,
            ):
                code, report = _run(
                    [
                        "--output-dir",
                        str(output),
                        "--review-decision",
                        "confirm",
                        "--mode",
                        "bailian-live",
                        "--external-data-approved",
                    ]
                )

            self.assertEqual(code, 3)
            self.assertEqual(
                report["error_code"],
                "BAILIAN_CONNECTION_FAILED",
            )
            self.assertEqual(report["failed_step"], "RECOMMEND")
            self.assertTrue(report["ai"]["called"])
            self.assertEqual(transport.call_count, 2)
            self.assertFalse(
                (output / "12-demo-completion.json").exists()
            )
            self.assertFalse(
                (output / "11-recommendation-record.json").exists()
            )

    def test_formal_replay_rejects_tampered_demo_candidate_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "run"
            code, _ = _run(
                [
                    "--output-dir",
                    str(output),
                    "--review-decision",
                    "confirm",
                ]
            )
            self.assertEqual(code, 0)
            candidate_path = output / "07-candidate-set.json"
            tampered = json.loads(candidate_path.read_text(encoding="utf-8"))
            tampered["candidates"][0]["label"] = "TAMPERED"
            candidate_path.write_text(
                json.dumps(tampered),
                encoding="utf-8",
            )
            replay_code, replay_report = _run_governance(
                [
                    "replay-recommendation",
                    str(output / "01-fictional-tree.json"),
                    str(output / "02-intent-request.json"),
                    str(output / "04-intent-draft.json"),
                    str(output / "05-intent-review-action.json"),
                    str(output / "06-intent-confirmation.json"),
                    str(candidate_path),
                    str(output / "09-recommendation-draft.json"),
                    str(output / "10-recommendation-review-action.json"),
                    str(output / "11-recommendation-record.json"),
                ]
            )

        self.assertEqual(replay_code, 2)
        self.assertEqual(
            replay_report["error_code"],
            "CANDIDATE_SET_INVALID",
        )

    def test_step_failure_has_no_completion_marker(self) -> None:
        real_main = governance_main

        def fail_recommend(arguments: list[str]) -> int:
            if arguments[0] == "recommend":
                print(
                    json.dumps(
                        {
                            "valid": False,
                            "error_code": "FICTIONAL_STEP_FAILURE",
                            "ai": {"called": False},
                        }
                    )
                )
                return 2
            return real_main(arguments)

        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "run"
            with patch(
                "treeguard.demo_cli.governance_main",
                side_effect=fail_recommend,
            ):
                code, report = _run(
                    [
                        "--output-dir",
                        str(output),
                        "--review-decision",
                        "confirm",
                    ]
                )

            self.assertEqual(code, 2)
            self.assertEqual(
                report["error_code"],
                "FICTIONAL_STEP_FAILURE",
            )
            self.assertEqual(report["failed_step"], "RECOMMEND")
            self.assertFalse(
                (output / "12-demo-completion.json").exists()
            )
            self.assertFalse(
                (output / "11-recommendation-record.json").exists()
            )

    def test_review_decision_is_required_and_bounded(self) -> None:
        for arguments in (
            ["--output-dir", "unused"],
            [
                "--output-dir",
                "unused",
                "--review-decision",
                "revise",
            ],
        ):
            with self.subTest(arguments=arguments):
                with (
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as raised,
                ):
                    main(arguments)
                self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
