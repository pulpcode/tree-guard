from __future__ import annotations

import io
import json
import os
import shutil
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from treeguard.ai_review import BailianConfig, BailianProviderError
from treeguard.governance_cli import main
from treeguard.hashing import canonical_digest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def _write_private(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


def _model_payload() -> dict:
    return {
        "schema_version": "change-intent-model-output.v1",
        "subject": "Display height",
        "role": "Catalog measurement",
        "scenario": "Imaginary exhibition",
        "lifecycle": "Catalog lifetime",
        "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
        "node_kind": "PROPERTY",
        "value_type": "float",
        "cardinality": "SINGLE",
        "confirmed_facts": ["A display height is requested."],
        "assumptions": [],
        "evidence_gaps": [],
        "clarification_question": None,
    }


def _prepare_inputs(directory: Path):
    tree = directory / "tree.json"
    shutil.copyfile(FIXTURE_PATH, tree)
    tree.chmod(0o600)
    request = directory / "request.json"
    _write_private(
        request,
        {
            "schema_version": "intent-request.v1",
            "requirement_text": "secret-intent-canary: record display height.",
            "proposed_parent_node_id": "node-004",
            "node_kind_hint": "PROPERTY",
            "value_type_hint": "float",
            "cardinality_hint": "SINGLE",
        },
    )
    model = directory / "model.json"
    _write_private(model, _model_payload())
    return tree, request, model


def _run(arguments: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(arguments)
    return exit_code, json.loads(stdout.getvalue())


class GovernanceCLITests(unittest.TestCase):
    def test_file_workflow_is_private_replayable_and_aggregate_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            tree, request, model = _prepare_inputs(directory)
            draft_path = directory / "draft.json"
            draft_code, draft_report = _run(
                [
                    "draft",
                    str(tree),
                    str(request),
                    "--model-output-file",
                    str(model),
                    "--internal-output",
                    str(draft_path),
                ]
            )
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            action_path = directory / "action.json"
            _write_private(
                action_path,
                {
                    "schema_version": "intent-review-action.v1",
                    "expected_draft_hash": draft["draft_hash"],
                    "decision": "CONFIRM_FOR_RETRIEVAL",
                    "reviewer_ref": "fictional-steward",
                    "recorded_at": "2030-01-02T03:04:05Z",
                    "confirmed_intent": draft["intent"],
                },
            )
            confirmation_path = directory / "confirmation.json"
            confirm_code, confirm_report = _run(
                [
                    "confirm",
                    str(tree),
                    str(request),
                    str(draft_path),
                    str(action_path),
                    "--internal-output",
                    str(confirmation_path),
                ]
            )
            candidates_path = directory / "candidates.json"
            search_code, search_report = _run(
                [
                    "search",
                    str(tree),
                    str(request),
                    str(draft_path),
                    str(action_path),
                    str(confirmation_path),
                    "--internal-output",
                    str(candidates_path),
                ]
            )
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            output_modes = {
                stat.S_IMODE(path.stat().st_mode)
                for path in (draft_path, confirmation_path, candidates_path)
            }

            tampered = json.loads(
                confirmation_path.read_text(encoding="utf-8")
            )
            tampered["reviewer_ref"] = "different-fictional-reviewer"
            tampered_payload = dict(tampered)
            tampered_payload.pop("confirmation_hash")
            tampered["confirmation_hash"] = canonical_digest(tampered_payload)
            tampered_path = directory / "tampered-confirmation.json"
            _write_private(tampered_path, tampered)
            tampered_output = directory / "tampered-candidates.json"
            tampered_code, tampered_report = _run(
                [
                    "search",
                    str(tree),
                    str(request),
                    str(draft_path),
                    str(action_path),
                    str(tampered_path),
                    "--internal-output",
                    str(tampered_output),
                ]
            )

        self.assertEqual(draft_code, 0)
        self.assertEqual(confirm_code, 0)
        self.assertEqual(search_code, 0)
        self.assertFalse(draft_report["ai"]["called"])
        self.assertEqual(confirm_report["status"], "CONFIRMED_FOR_RETRIEVAL")
        self.assertFalse(confirm_report["semantic_approval"])
        self.assertFalse(confirm_report["patch_eligible"])
        self.assertEqual(search_report["status"], "CANDIDATES_READY")
        self.assertFalse(search_report["allows_addition"])
        self.assertEqual(candidates["candidates"][0]["node_id"], "node-008")
        self.assertEqual(output_modes, {0o600})
        aggregate = json.dumps(
            [draft_report, confirm_report, search_report],
            sort_keys=True,
        )
        self.assertNotIn("secret-intent-canary", aggregate)
        self.assertNotIn("node-008", aggregate)
        self.assertNotIn("draft_hash", aggregate)
        self.assertEqual(tampered_code, 2)
        self.assertEqual(
            tampered_report["error_code"],
            "INTENT_CONFIRMATION_SOURCE_MISMATCH",
        )
        self.assertFalse(tampered_output.exists())

    def test_live_requires_approval_before_reading_inputs(self) -> None:
        code, report = _run(
            [
                "draft",
                "missing-tree.json",
                "missing-request.json",
                "--live",
                "--internal-output",
                "not-created.json",
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(
            report["error_code"],
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertFalse(report["ai"]["called"])

    def test_private_input_and_exact_model_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            tree, request, model = _prepare_inputs(directory)
            request.chmod(0o644)
            public_code, public_report = _run(
                [
                    "draft",
                    str(tree),
                    str(request),
                    "--model-output-file",
                    str(model),
                    "--internal-output",
                    str(directory / "public-output.json"),
                ]
            )
            request.chmod(0o600)
            invalid = _model_payload()
            invalid["approval"] = True
            _write_private(model, invalid)
            invalid_output = directory / "invalid-output.json"
            invalid_code, invalid_report = _run(
                [
                    "draft",
                    str(tree),
                    str(request),
                    "--model-output-file",
                    str(model),
                    "--internal-output",
                    str(invalid_output),
                ]
            )

        self.assertEqual(public_code, 2)
        self.assertEqual(
            public_report["error_code"],
            "GOVERNANCE_INPUT_INVALID",
        )
        self.assertEqual(invalid_code, 2)
        self.assertEqual(
            invalid_report["error_code"],
            "INTENT_MODEL_FIELDS_INVALID",
        )
        self.assertFalse(invalid_output.exists())

    def test_live_transport_failure_reports_ai_called_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            tree, request, _ = _prepare_inputs(directory)
            output = directory / "live-output.json"
            with (
                patch(
                    "treeguard.governance_cli.BailianConfig.from_env",
                    return_value=BailianConfig(api_key="fixture-key"),
                ),
                patch(
                    "treeguard.governance_cli.BailianIntentDraftProvider.draft",
                    side_effect=BailianProviderError(
                        "BAILIAN_CONNECTION_FAILED",
                        "fictional connection failure",
                    ),
                ),
            ):
                code, report = _run(
                    [
                        "draft",
                        str(tree),
                        str(request),
                        "--live",
                        "--external-data-approved",
                        "--internal-output",
                        str(output),
                    ]
                )

        self.assertEqual(code, 3)
        self.assertEqual(report["error_code"], "BAILIAN_CONNECTION_FAILED")
        self.assertTrue(report["ai"]["called"])
        self.assertFalse(output.exists())

    def test_live_request_encoding_failure_is_preflight_not_ai_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            tree, request, _ = _prepare_inputs(directory)
            output = directory / "live-output.json"
            with (
                patch(
                    "treeguard.governance_cli.BailianConfig.from_env",
                    return_value=BailianConfig(api_key="fixture-key"),
                ),
                patch(
                    "treeguard.governance_cli.BailianIntentDraftProvider.draft",
                    side_effect=BailianProviderError(
                        "BAILIAN_REQUEST_INVALID",
                        "fictional local encoding failure",
                    ),
                ),
            ):
                code, report = _run(
                    [
                        "draft",
                        str(tree),
                        str(request),
                        "--live",
                        "--external-data-approved",
                        "--internal-output",
                        str(output),
                    ]
                )

        self.assertEqual(code, 2)
        self.assertEqual(report["error_code"], "BAILIAN_REQUEST_INVALID")
        self.assertFalse(report["ai"]["called"])
        self.assertFalse(output.exists())

    def test_live_output_failure_preserves_ai_called_truth(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            tree, request, _ = _prepare_inputs(directory)
            output = directory / "live-output.json"
            provider_response = {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(_model_payload()),
                        },
                    }
                ]
            }
            with (
                patch(
                    "treeguard.governance_cli.BailianConfig.from_env",
                    return_value=BailianConfig(api_key="fixture-key"),
                ),
                patch(
                    "treeguard.ai_review.BailianIntentDraftProvider._post_json",
                    return_value=provider_response,
                ),
                patch(
                    "treeguard.governance_cli.write_private_json",
                    return_value=False,
                ),
            ):
                code, report = _run(
                    [
                        "draft",
                        str(tree),
                        str(request),
                        "--live",
                        "--external-data-approved",
                        "--internal-output",
                        str(output),
                    ]
                )

        self.assertEqual(code, 2)
        self.assertEqual(report["error_code"], "INTERNAL_OUTPUT_WRITE_FAILED")
        self.assertTrue(report["ai"]["called"])
        self.assertFalse(output.exists())

    def test_existing_output_is_rejected_before_live_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            tree, request, _ = _prepare_inputs(directory)
            output = directory / "existing.json"
            output.write_text("keep", encoding="utf-8")
            with patch(
                "treeguard.governance_cli.BailianIntentDraftProvider.draft"
            ) as provider_call:
                code, report = _run(
                    [
                        "draft",
                        str(tree),
                        str(request),
                        "--live",
                        "--external-data-approved",
                        "--internal-output",
                        str(output),
                    ]
                )
            existing = output.read_text(encoding="utf-8")

        self.assertEqual(code, 2)
        self.assertEqual(
            report["error_code"],
            "INTERNAL_OUTPUT_WRITE_FAILED",
        )
        provider_call.assert_not_called()
        self.assertEqual(existing, "keep")


if __name__ == "__main__":
    unittest.main()
