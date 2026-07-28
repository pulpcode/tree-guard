from __future__ import annotations

import copy
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from treeguard import adapt_tree_document
from treeguard.ai_review import (
    AIReviewDraft,
    BailianProviderError,
)
from treeguard.business_review import mine_business_version_pair
from treeguard.evidence import build_business_review_evidence_pack
from treeguard.expert_cli import _read_json_file, main
from treeguard.expert_synthesis import BailianExpertSynthesisProvider
from treeguard.hashing import canonical_digest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
ACTION_CONTRACT_PATH = (
    PROJECT_ROOT / "contracts" / "expert-review-action.v1.schema.json"
)
NOW = "2026-07-28T03:00:00Z"


def _find_source_node(document: dict, node_id: str) -> dict:
    def walk(wrapper: dict) -> dict | None:
        if wrapper["metadata"]["node_id"] == node_id:
            return wrapper
        for child in wrapper.get("subnodes", {}).values():
            found = walk(child)
            if found is not None:
                return found
        return None

    for root in document["map_topology"].values():
        found = walk(root)
        if found is not None:
            return found
    raise AssertionError(f"fixture node not found: {node_id}")


def _prepare_sources(directory: Path) -> tuple[Path, Path, Path, str]:
    before_document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    after_document = copy.deepcopy(before_document)
    before_document["metadata"].update({"version": "V1", "id": "record-v1"})
    after_document["metadata"].update({"version": "V2", "id": "record-v2"})
    _find_source_node(after_document, "node-008")["metadata"]["node_name"] = (
        "Revised display height"
    )
    before_path = directory / "before.json"
    after_path = directory / "after.json"
    before_path.write_text(json.dumps(before_document), encoding="utf-8")
    after_path.write_text(json.dumps(after_document), encoding="utf-8")
    before_path.chmod(0o600)
    after_path.chmod(0o600)

    before_result = adapt_tree_document(before_document)
    after_result = adapt_tree_document(after_document)
    assert before_result.tree is not None
    assert after_result.tree is not None
    run = mine_business_version_pair(
        before_result.tree,
        after_result.tree,
        base_position=0,
        target_position=1,
    )
    pack = build_business_review_evidence_pack(
        run,
        before_result.tree,
        after_result.tree,
    )
    ai_draft = AIReviewDraft.from_model_dict(
        {
            "schema_version": "ai-review-model-output.v1",
            "change_summary": "One property name changed.",
            "observations": [
                {
                    "statement": "The focus property name changed.",
                    "evidence_refs": ["F001"],
                }
            ],
            "hypotheses": [
                {
                    "statement": "The new name may clarify its meaning.",
                    "evidence_refs": ["F001"],
                }
            ],
            "candidate_assessments": [],
            "placement_assessment": {
                "status": "NEED_EVIDENCE",
                "reason": "A name change cannot prove placement.",
                "evidence_refs": ["F001"],
            },
            "suggested_disposition": "NEED_EVIDENCE",
            "questions_for_expert": ["Why was the name changed?"],
            "uncertainties": ["The version description is unavailable."],
        },
        pack,
    )
    bundle_path = directory / "ai-bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "review": None,
                "evidence_pack": None,
                "ai_review_draft": ai_draft.to_dict(),
                "model_call": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    bundle_path.chmod(0o600)
    return before_path, after_path, bundle_path, pack.case_id


def _write_action(
    path: Path,
    action_type: str,
    payload: dict,
    *,
    case_id: str,
    expected_session_hash: str | None = None,
    action_label: str | None = None,
    actor_role: str = "DOMAIN_EXPERT",
    actor_ref: str = "expert-local-01",
    recorded_at: str = NOW,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "expert-review-action.v1",
                "action_id": canonical_digest(
                    {"expert-cli-test-action": action_label or path.name}
                ),
                "case_id": case_id,
                "expected_session_hash": expected_session_hash,
                "action_type": action_type,
                "actor_role": actor_role,
                "actor_ref": actor_ref,
                "recorded_at": recorded_at,
                "payload": payload,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _run(arguments: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(arguments)
    return exit_code, json.loads(stdout.getvalue())


def _valid_synthesis_response() -> dict:
    payload = {
        "schema_version": "expert-synthesis-model-output.v1",
        "expert_claims": [
            {
                "statement": "The expert described a context extension.",
                "evidence_refs": ["T001"],
            }
        ],
        "hypotheses": [],
        "uncertainties": [],
        "risks": [],
        "evidence_requests": [],
        "questions_for_expert": [],
    }
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps(payload)},
            }
        ]
    }


class ExpertReviewCLITests(unittest.TestCase):
    def test_atomic_apply_then_replay_uses_secure_files_and_safe_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            action = directory / "thought.json"
            output = directory / "session-001.json"
            raw_text = "expert-thought-canary 这是一段尚未分类的自由思考。"
            _write_action(
                action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": raw_text, "evidence_refs": ["F001"]},
                case_id=case_id,
            )
            action_contract = json.loads(
                ACTION_CONTRACT_PATH.read_text(encoding="utf-8")
            )
            self.assertEqual(
                set(action_contract["required"]),
                set(json.loads(action.read_text(encoding="utf-8"))),
            )

            exit_code, report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(action),
                    "--internal-output",
                    str(output),
                ]
            )
            stored = json.loads(output.read_text(encoding="utf-8"))
            original_bytes = output.read_bytes()
            mode = stat.S_IMODE(output.stat().st_mode)
            replay_code, replay_report = _run(
                [
                    "replay",
                    str(before),
                    str(after),
                    str(bundle),
                    str(output),
                ]
            )

            self.assertEqual(output.read_bytes(), original_bytes)

        self.assertEqual(exit_code, 0)
        self.assertEqual(replay_code, 0)
        self.assertEqual(mode, 0o600)
        self.assertEqual(stored["state"], "DELIBERATING")
        self.assertEqual(
            stored["events"][0]["payload"]["raw_text"],
            raw_text,
        )
        self.assertEqual(report["operation"], "APPLY")
        self.assertEqual(replay_report["operation"], "REPLAY")
        for safe_report in (report, replay_report):
            encoded = json.dumps(safe_report, ensure_ascii=False)
            self.assertNotIn("expert-thought-canary", encoded)
            self.assertNotIn("F001", encoded)
            self.assertNotIn(stored["session_hash"], encoded)

    def test_status_and_final_are_separate_hash_anchored_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            thought_action = directory / "thought.json"
            first_session = directory / "session-001.json"
            _write_action(
                thought_action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": "保留共享主干并增加场景扩展。", "evidence_refs": []},
                case_id=case_id,
            )
            self.assertEqual(
                _run(
                    [
                        "apply",
                        str(before),
                        str(after),
                        str(bundle),
                        str(thought_action),
                        "--internal-output",
                        str(first_session),
                    ]
                )[0],
                0,
            )

            status_action = directory / "status.json"
            provisional_session = directory / "session-002.json"
            first = json.loads(first_session.read_text(encoding="utf-8"))
            _write_action(
                status_action,
                "EXPERT_STATUS_RECORDED",
                {
                    "target_state": "PROVISIONAL",
                    "rationale": "已有暂定语义结论。",
                    "evidence_refs": ["T001"],
                    "proposed_disposition": "KEEP_CONTEXT_EXTENSION",
                },
                case_id=case_id,
                expected_session_hash=first["session_hash"],
            )
            status_code, _ = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(status_action),
                    "--session-input",
                    str(first_session),
                    "--internal-output",
                    str(provisional_session),
                ]
            )
            provisional = json.loads(
                provisional_session.read_text(encoding="utf-8")
            )

            stale_action = directory / "stale-final.json"
            stale_output = directory / "should-not-exist.json"
            _write_action(
                stale_action,
                "EXPERT_FINAL_DECISION_RECORDED",
                {
                    "target_state": "APPROVED",
                    "final_disposition": "KEEP_CONTEXT_EXTENSION",
                    "rationale": "最终裁决。",
                    "evidence_refs": ["T001"],
                    "ai_draft_relation": "REVISED",
                },
                case_id=case_id,
                expected_session_hash="0" * 64,
            )
            stale_code, stale_report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(stale_action),
                    "--session-input",
                    str(provisional_session),
                    "--internal-output",
                    str(stale_output),
                ]
            )

            final_action = directory / "final.json"
            final_output = directory / "session-003.json"
            _write_action(
                final_action,
                "EXPERT_FINAL_DECISION_RECORDED",
                {
                    "target_state": "APPROVED",
                    "final_disposition": "KEEP_CONTEXT_EXTENSION",
                    "rationale": "最终裁决。",
                    "evidence_refs": ["T001"],
                    "ai_draft_relation": "REVISED",
                },
                case_id=case_id,
                expected_session_hash=provisional["session_hash"],
            )
            final_code, final_report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(final_action),
                    "--session-input",
                    str(provisional_session),
                    "--internal-output",
                    str(final_output),
                ]
            )

        self.assertEqual(status_code, 0)
        self.assertEqual(stale_code, 2)
        self.assertEqual(
            stale_report["error_code"],
            "EXPERT_SESSION_CONCURRENT_MODIFICATION",
        )
        self.assertFalse(stale_output.exists())
        self.assertEqual(final_code, 0)
        self.assertEqual(final_report["state"], "APPROVED")
        self.assertFalse(final_report["patch_eligible"])

    def test_live_requires_data_and_exact_payload_approvals(self) -> None:
        first_code, first_report = _run(
            [
                "apply",
                "missing.json",
                "missing.json",
                "missing.json",
                "missing.json",
                "--internal-output",
                "missing-output.json",
                "--live-synthesis",
            ]
        )
        second_code, second_report = _run(
            [
                "apply",
                "missing.json",
                "missing.json",
                "missing.json",
                "missing.json",
                "--internal-output",
                "missing-output.json",
                "--live-synthesis",
                "--external-data-approved",
            ]
        )

        self.assertEqual(first_code, 2)
        self.assertEqual(
            first_report["error_code"],
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertEqual(second_code, 2)
        self.assertEqual(
            second_report["error_code"],
            "EXTERNAL_EXPERT_PAYLOAD_APPROVAL_REQUIRED",
        )

    def test_provider_failure_does_not_write_partial_thought_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            action = directory / "thought.json"
            output = directory / "session.json"
            live_recorded_at = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
            _write_action(
                action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": "只在获批后发送。", "evidence_refs": ["F001"]},
                case_id=case_id,
                recorded_at=live_recorded_at,
            )
            prepare_code, prepare_report = _run(
                [
                    "prepare-approval",
                    str(before),
                    str(after),
                    str(bundle),
                    str(action),
                    "--internal-output",
                    str(directory / "approval-request.json"),
                ]
            )
            pending_approval = json.loads(
                (directory / "approval-request.json").read_text(
                    encoding="utf-8"
                )
            )
            pending_approval.update(
                {
                    "approval_status": "APPROVED",
                    "approved_by": "security-reviewer-01",
                    "approved_at": live_recorded_at,
                }
            )
            approved_path = directory / "approval-approved.json"
            approved_path.write_text(
                json.dumps(pending_approval, ensure_ascii=False),
                encoding="utf-8",
            )
            approved_path.chmod(0o600)
            with (
                patch.dict(
                    os.environ,
                    {"BAILIAN_API_KEY": "fictional-test-key"},
                    clear=True,
                ),
                patch.object(
                    BailianExpertSynthesisProvider,
                    "_post_json",
                    side_effect=BailianProviderError(
                        "BAILIAN_CONNECTION_FAILED",
                        "fictional connection failure",
                    ),
                ),
            ):
                exit_code, report = _run(
                    [
                        "apply",
                        str(before),
                        str(after),
                        str(bundle),
                        str(action),
                        "--internal-output",
                        str(output),
                        "--live-synthesis",
                        "--external-data-approved",
                        "--external-approval-file",
                        str(approved_path),
                    ]
                )

            self.assertFalse(output.exists())

        self.assertEqual(prepare_code, 0)
        self.assertEqual(exit_code, 3)
        self.assertEqual(report["error_code"], "BAILIAN_CONNECTION_FAILED")
        self.assertTrue(report["ai"]["called"])

    def test_live_synthesis_records_approved_request_without_state_escalation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            action = directory / "thought-live.json"
            approval_request = directory / "approval-request.json"
            approved_path = directory / "approval-approved.json"
            output = directory / "session-live.json"
            raw_text = "external-thought-canary 完全虚构的专家思考。"
            recorded_at = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
            _write_action(
                action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": raw_text, "evidence_refs": ["F001"]},
                case_id=case_id,
                recorded_at=recorded_at,
            )
            prepare_code, prepare_report = _run(
                [
                    "prepare-approval",
                    str(before),
                    str(after),
                    str(bundle),
                    str(action),
                    "--internal-output",
                    str(approval_request),
                ]
            )
            approved = json.loads(
                approval_request.read_text(encoding="utf-8")
            )
            approved.update(
                {
                    "approval_status": "APPROVED",
                    "approved_by": "security-reviewer-01",
                    "approved_at": recorded_at,
                }
            )
            approved_path.write_text(
                json.dumps(approved, ensure_ascii=False),
                encoding="utf-8",
            )
            approved_path.chmod(0o600)
            with (
                patch.dict(
                    os.environ,
                    {"BAILIAN_API_KEY": "fictional-test-key"},
                    clear=True,
                ),
                patch.object(
                    BailianExpertSynthesisProvider,
                    "_post_json",
                    return_value=_valid_synthesis_response(),
                ),
            ):
                exit_code, report = _run(
                    [
                        "apply",
                        str(before),
                        str(after),
                        str(bundle),
                        str(action),
                        "--internal-output",
                        str(output),
                        "--live-synthesis",
                        "--external-data-approved",
                        "--external-approval-file",
                        str(approved_path),
                    ]
                )
            stored = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(prepare_code, 0)
        self.assertEqual(
            prepare_report["status"],
            "APPROVAL_REQUEST_WRITTEN",
        )
        self.assertNotIn("approval_payload_hash", prepare_report)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["state"], "DELIBERATING")
        self.assertTrue(report["ai"]["called"])
        self.assertEqual(len(stored["events"]), 2)
        self.assertEqual(
            stored["events"][1]["payload"]["external_approval"][
                "approval_status"
            ],
            "APPROVED",
        )
        encoded_report = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("external-thought-canary", encoded_report)
        self.assertNotIn(approved["approval_payload_hash"], encoded_report)

    def test_live_existing_output_is_rejected_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            action = directory / "thought-live.json"
            approval_request = directory / "approval-request.json"
            approved_path = directory / "approval-approved.json"
            existing_output = directory / "existing-session.json"
            recorded_at = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
            _write_action(
                action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": "preflight before network", "evidence_refs": []},
                case_id=case_id,
                recorded_at=recorded_at,
            )
            self.assertEqual(
                _run(
                    [
                        "prepare-approval",
                        str(before),
                        str(after),
                        str(bundle),
                        str(action),
                        "--internal-output",
                        str(approval_request),
                    ]
                )[0],
                0,
            )
            approved = json.loads(
                approval_request.read_text(encoding="utf-8")
            )
            approved.update(
                {
                    "approval_status": "APPROVED",
                    "approved_by": "security-reviewer-01",
                    "approved_at": recorded_at,
                }
            )
            approved_path.write_text(
                json.dumps(approved),
                encoding="utf-8",
            )
            approved_path.chmod(0o600)
            existing_output.write_text("keep-me", encoding="utf-8")
            with (
                patch.dict(
                    os.environ,
                    {"BAILIAN_API_KEY": "fictional-test-key"},
                    clear=True,
                ),
                patch.object(
                    BailianExpertSynthesisProvider,
                    "_post_json",
                ) as post_json,
            ):
                exit_code, report = _run(
                    [
                        "apply",
                        str(before),
                        str(after),
                        str(bundle),
                        str(action),
                        "--internal-output",
                        str(existing_output),
                        "--live-synthesis",
                        "--external-data-approved",
                        "--external-approval-file",
                        str(approved_path),
                    ]
                )
            post_json.assert_not_called()
            existing_contents = existing_output.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            report["error_code"],
            "INTERNAL_OUTPUT_WRITE_FAILED",
        )
        self.assertEqual(existing_contents, "keep-me")

    def test_replay_rejects_tampering_and_wrong_source_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            action = directory / "thought.json"
            output = directory / "session.json"
            _write_action(
                action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": "原始思考。", "evidence_refs": []},
                case_id=case_id,
            )
            self.assertEqual(
                _run(
                    [
                        "apply",
                        str(before),
                        str(after),
                        str(bundle),
                        str(action),
                        "--internal-output",
                        str(output),
                    ]
                )[0],
                0,
            )
            tampered = json.loads(output.read_text(encoding="utf-8"))
            tampered["events"][0]["payload"]["raw_text"] = "篡改"
            tampered_path = directory / "tampered.json"
            tampered_path.write_text(
                json.dumps(tampered, ensure_ascii=False),
                encoding="utf-8",
            )
            tampered_path.chmod(0o600)
            tamper_code, tamper_report = _run(
                [
                    "replay",
                    str(before),
                    str(after),
                    str(bundle),
                    str(tampered_path),
                ]
            )

            wrong_bundle = json.loads(bundle.read_text(encoding="utf-8"))
            wrong_bundle["ai_review_draft"]["source_pack_hash"] = "0" * 64
            wrong_bundle_path = directory / "wrong-bundle.json"
            wrong_bundle_path.write_text(
                json.dumps(wrong_bundle),
                encoding="utf-8",
            )
            wrong_bundle_path.chmod(0o600)
            wrong_code, wrong_report = _run(
                [
                    "replay",
                    str(before),
                    str(after),
                    str(wrong_bundle_path),
                    str(output),
                ]
            )

        self.assertEqual(tamper_code, 2)
        self.assertEqual(tamper_report["error_code"], "EXPERT_EVENT_HASH_INVALID")
        self.assertEqual(wrong_code, 2)
        self.assertEqual(wrong_report["error_code"], "AI_REVIEW_PACK_MISMATCH")

    def test_apply_refuses_overwrite_and_ai_action_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            action = directory / "thought.json"
            output = directory / "existing.json"
            output.write_text("keep-me", encoding="utf-8")
            _write_action(
                action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": "原始思考。", "evidence_refs": []},
                case_id=case_id,
            )
            overwrite_code, overwrite_report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(action),
                    "--internal-output",
                    str(output),
                ]
            )

            forged_action = directory / "forged-ai.json"
            forged_output = directory / "forged-output.json"
            _write_action(
                forged_action,
                "AI_SYNTHESIS_RECORDED",
                {},
                case_id=case_id,
                actor_role="AI_ASSISTANT",
            )
            forged_code, forged_report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(forged_action),
                    "--internal-output",
                    str(forged_output),
                ]
            )

            self.assertEqual(output.read_text(encoding="utf-8"), "keep-me")
            self.assertFalse(forged_output.exists())

        self.assertEqual(overwrite_code, 2)
        self.assertEqual(
            overwrite_report["error_code"],
            "INTERNAL_OUTPUT_WRITE_FAILED",
        )
        self.assertEqual(forged_code, 2)
        self.assertEqual(forged_report["error_code"], "EXPERT_ACTION_TYPE_INVALID")

    def test_duplicate_json_public_input_and_fifo_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            before, after, bundle, case_id = _prepare_sources(directory)
            duplicate_action = directory / "duplicate-action.json"
            duplicate_action.write_text(
                (
                    "{"
                    '"schema_version":"expert-review-action.v1",'
                    f'"action_id":"{canonical_digest({"duplicate": True})}",'
                    f'"case_id":"{case_id}",'
                    '"expected_session_hash":null,'
                    '"action_type":"EXPERT_THOUGHT_SUBMITTED",'
                    '"actor_role":"DOMAIN_EXPERT",'
                    '"actor_ref":"expert-local-01",'
                    '"actor_ref":"forged-local-02",'
                    f'"recorded_at":"{NOW}",'
                    '"payload":{"raw_text":"ambiguous","evidence_refs":[]}'
                    "}"
                ),
                encoding="utf-8",
            )
            duplicate_action.chmod(0o600)
            duplicate_code, duplicate_report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(duplicate_action),
                    "--internal-output",
                    str(directory / "duplicate-output.json"),
                ]
            )

            public_action = directory / "public-action.json"
            _write_action(
                public_action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": "private input required", "evidence_refs": []},
                case_id=case_id,
            )
            public_action.chmod(0o644)
            public_code, public_report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(public_action),
                    "--internal-output",
                    str(directory / "public-output.json"),
                ]
            )

            malformed_role_action = directory / "malformed-role-action.json"
            _write_action(
                malformed_role_action,
                "EXPERT_THOUGHT_SUBMITTED",
                {"raw_text": "invalid actor role shape", "evidence_refs": []},
                case_id=case_id,
            )
            malformed_role = json.loads(
                malformed_role_action.read_text(encoding="utf-8")
            )
            malformed_role["actor_role"] = {}
            malformed_role_action.write_text(
                json.dumps(malformed_role),
                encoding="utf-8",
            )
            malformed_role_action.chmod(0o600)
            malformed_code, malformed_report = _run(
                [
                    "apply",
                    str(before),
                    str(after),
                    str(bundle),
                    str(malformed_role_action),
                    "--internal-output",
                    str(directory / "malformed-output.json"),
                ]
            )

            fifo_path = directory / "input.fifo"
            os.mkfifo(fifo_path, 0o600)
            with self.assertRaises(OSError):
                _read_json_file(fifo_path, max_bytes=64_000)

        self.assertEqual(duplicate_code, 2)
        self.assertEqual(
            duplicate_report["error_code"],
            "EXPERT_REVIEW_INPUT_INVALID",
        )
        self.assertEqual(public_code, 2)
        self.assertEqual(
            public_report["error_code"],
            "EXPERT_REVIEW_INPUT_INVALID",
        )
        self.assertEqual(malformed_code, 2)
        self.assertEqual(
            malformed_report["error_code"],
            "EXPERT_ACTION_ACTOR_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
