from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from treeguard import adapt_tree_document
from treeguard.ai_review import AIReviewDraft, BailianConfig, BailianProviderError
from treeguard.business_review import mine_business_version_pair
from treeguard.evidence import build_business_review_evidence_pack
from treeguard.expert_review import (
    APPROVED,
    DELIBERATING,
    DOMAIN_EXPERT,
    NEED_EVIDENCE,
    PROVISIONAL,
    SCHEMA_STEWARD,
    ExpertReviewError,
    ExpertReviewSession,
    open_expert_review_session,
    record_ai_synthesis,
    record_expert_final_decision,
    record_expert_status,
    submit_expert_thought,
    verify_expert_review_session_against_sources,
)
from treeguard.expert_synthesis import (
    BailianExpertSynthesisProvider,
    ExpertSynthesisDraft,
    ExpertSynthesisValidationError,
)
from treeguard.hashing import canonical_digest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
SESSION_CONTRACT_PATH = (
    PROJECT_ROOT / "contracts" / "expert-review-session.v1.schema.json"
)
SYNTHESIS_CONTRACT_PATH = (
    PROJECT_ROOT / "contracts" / "expert-synthesis-draft.v1.schema.json"
)
MODEL_CONTRACT_PATH = (
    PROJECT_ROOT / "contracts" / "expert-synthesis-model-output.v1.schema.json"
)
APPROVAL_CONTRACT_PATH = (
    PROJECT_ROOT
    / "contracts"
    / "external-expert-synthesis-approval.v1.schema.json"
)
NOW = "2026-07-28T03:00:00Z"


def _action_id(label: str) -> str:
    return canonical_digest({"expert-test-action": label})


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


def _canonical_version(document: dict, version: str, record_id: str):
    source = copy.deepcopy(document)
    source["metadata"]["version"] = version
    source["metadata"]["id"] = record_id
    result = adapt_tree_document(source)
    if result.tree is None:
        raise AssertionError("fictional fixture failed canonicalization")
    return result.tree


def _sources():
    before_document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    after_document = copy.deepcopy(before_document)
    _find_source_node(after_document, "node-008")["metadata"]["node_name"] = (
        "Revised display height"
    )
    before = _canonical_version(before_document, "V1", "record-v1")
    after = _canonical_version(after_document, "V2", "record-v2")
    run = mine_business_version_pair(
        before,
        after,
        base_position=0,
        target_position=1,
    )
    pack = build_business_review_evidence_pack(run, before, after)
    model_payload = {
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
    }
    return pack, AIReviewDraft.from_model_dict(model_payload, pack)


def _synthesis_model_payload(*, thought_ref: str = "T001") -> dict:
    return {
        "schema_version": "expert-synthesis-model-output.v1",
        "expert_claims": [
            {
                "statement": "The expert considers the field context-specific.",
                "evidence_refs": [thought_ref],
            }
        ],
        "hypotheses": [
            {
                "statement": "A shared core plus an extension may fit.",
                "evidence_refs": [thought_ref, "F001"],
            }
        ],
        "uncertainties": [
            {
                "statement": "The reusable boundary is not yet confirmed.",
                "evidence_refs": [thought_ref],
            }
        ],
        "risks": [],
        "evidence_requests": [
            {
                "statement": "Confirm fields shared by ordinary tasks.",
                "evidence_refs": [thought_ref],
            }
        ],
        "questions_for_expert": ["Which fields are stable across task types?"],
    }


def _external_approval(pack, ai_draft, session) -> dict:
    provider = BailianExpertSynthesisProvider(
        BailianConfig(api_key="test-secret")
    )
    approval_payload_hash = provider.approval_payload_hash(
        pack,
        ai_draft,
        (
            (
                session.events[0].payload["thought_ref"],
                session.events[0].payload["raw_text"],
            ),
        ),
    )
    return {
        "schema_version": "external-expert-synthesis-approval.v1",
        "approval_status": "APPROVED",
        "approval_payload_hash": approval_payload_hash,
        "provider": "BAILIAN_OPENAI_COMPATIBLE",
        "endpoint": (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/"
            "chat/completions"
        ),
        "model": "qwen3.6-35b-a3b",
        "prompt_version": "treeguard.expert-synthesis.zh.v1",
        "approved_by": "security-reviewer-01",
        "approved_at": NOW,
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
    }


def _session_with_thought():
    pack, ai_draft = _sources()
    session = open_expert_review_session(
        pack,
        ai_draft,
        session_id=canonical_digest({"fixture": "expert-session"}),
    )
    session = submit_expert_thought(
        session,
        pack,
        ai_draft,
        action_id=_action_id("initial-thought"),
        actor_role=DOMAIN_EXPERT,
        actor_ref="expert-local-01",
        recorded_at=NOW,
        raw_text="  我目前倾向共享人员主干，特殊任务字段保留为扩展。\n但边界还需核实。  ",
        evidence_refs=("F001",),
    )
    return pack, ai_draft, session


class ExpertReviewTests(unittest.TestCase):
    def test_free_text_is_verbatim_and_contracts_match_runtime_fields(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        schema = json.loads(SESSION_CONTRACT_PATH.read_text(encoding="utf-8"))
        synthesis_schema = json.loads(
            SYNTHESIS_CONTRACT_PATH.read_text(encoding="utf-8")
        )
        model_schema = json.loads(MODEL_CONTRACT_PATH.read_text(encoding="utf-8"))
        approval_schema = json.loads(
            APPROVAL_CONTRACT_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(session.state, DELIBERATING)
        self.assertEqual(
            session.events[0].payload["raw_text"],
            "  我目前倾向共享人员主干，特殊任务字段保留为扩展。\n但边界还需核实。  ",
        )
        self.assertEqual(session.events[0].payload["thought_ref"], "T001")
        self.assertEqual(set(schema["required"]), set(session.to_dict()))

        synthesis = ExpertSynthesisDraft.from_model_dict(
            _synthesis_model_payload(),
            pack,
            ai_draft,
            source_session_hash=session.session_hash,
            source_thought_refs=("T001",),
        )
        self.assertEqual(
            set(synthesis_schema["required"]),
            set(synthesis.to_dict()),
        )
        self.assertEqual(
            set(model_schema["required"]),
            set(synthesis.to_model_dict()),
        )
        self.assertEqual(
            set(approval_schema["required"]),
            set(_external_approval(pack, ai_draft, session)),
        )

    def test_full_review_path_and_ai_never_changes_state(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        synthesis = ExpertSynthesisDraft.from_model_dict(
            _synthesis_model_payload(),
            pack,
            ai_draft,
            source_session_hash=session.session_hash,
            source_thought_refs=("T001",),
        )
        forged_approval = _external_approval(pack, ai_draft, session)
        forged_approval["approval_payload_hash"] = "0" * 64
        with self.assertRaises(ExpertReviewError) as approval_error:
            record_ai_synthesis(
                session,
                pack,
                ai_draft,
                action_id=_action_id("forged-ai-synthesis"),
                actor_ref="bailian-json-assistant",
                recorded_at=NOW,
                provider="BAILIAN_OPENAI_COMPATIBLE",
                model="qwen3.6-35b-a3b",
                prompt_version="treeguard.expert-synthesis.zh.v1",
                external_approval=forged_approval,
                synthesis_draft=synthesis,
            )
        self.assertEqual(
            approval_error.exception.code,
            "EXTERNAL_EXPERT_PAYLOAD_APPROVAL_REQUIRED",
        )
        late_approval = _external_approval(pack, ai_draft, session)
        late_approval["approved_at"] = "2026-07-28T03:00:01Z"
        with self.assertRaises(ExpertReviewError) as approval_time_error:
            record_ai_synthesis(
                session,
                pack,
                ai_draft,
                action_id=_action_id("late-approval-ai-synthesis"),
                actor_ref="bailian-json-assistant",
                recorded_at=NOW,
                provider="BAILIAN_OPENAI_COMPATIBLE",
                model="qwen3.6-35b-a3b",
                prompt_version="treeguard.expert-synthesis.zh.v1",
                external_approval=late_approval,
                synthesis_draft=synthesis,
            )
        self.assertEqual(
            approval_time_error.exception.code,
            "EXTERNAL_APPROVAL_TIME_INVALID",
        )
        session = record_ai_synthesis(
            session,
            pack,
            ai_draft,
            action_id=_action_id("ai-synthesis"),
            actor_ref="bailian-json-assistant",
            recorded_at=NOW,
            provider="BAILIAN_OPENAI_COMPATIBLE",
            model="qwen3.6-35b-a3b",
            prompt_version="treeguard.expert-synthesis.zh.v1",
            external_approval=_external_approval(pack, ai_draft, session),
            synthesis_draft=synthesis,
        )
        self.assertEqual(session.state, DELIBERATING)
        malformed_refs = session.to_dict()
        malformed_refs["events"][-1]["payload"]["draft"][
            "source_thought_refs"
        ] = [{}]
        with self.assertRaises(ExpertReviewError) as refs_error:
            ExpertReviewSession.from_dict(
                malformed_refs,
                pack,
                ai_draft,
            )
        self.assertEqual(
            refs_error.exception.code,
            "EXPERT_SYNTHESIS_DRAFT_INVALID",
        )

        session = record_expert_status(
            session,
            pack,
            ai_draft,
            action_id=_action_id("need-evidence"),
            actor_ref="expert-local-01",
            recorded_at=NOW,
            target_state=NEED_EVIDENCE,
            rationale="需要确认普通任务中的稳定字段边界。",
            evidence_refs=("T001",),
            proposed_disposition=None,
        )
        self.assertEqual(session.state, NEED_EVIDENCE)
        session = submit_expert_thought(
            session,
            pack,
            ai_draft,
            action_id=_action_id("steward-follow-up"),
            actor_role=SCHEMA_STEWARD,
            actor_ref="steward-local-01",
            recorded_at=NOW,
            raw_text="结构侧确认共享主干可保持稳定，特殊字段可放入场景扩展。",
            evidence_refs=("F001",),
        )
        self.assertEqual(session.state, DELIBERATING)
        session = record_expert_status(
            session,
            pack,
            ai_draft,
            action_id=_action_id("provisional-after-follow-up"),
            actor_ref="expert-local-01",
            recorded_at=NOW,
            target_state=PROVISIONAL,
            rationale="现有证据足以形成暂定语义结论。",
            evidence_refs=("T001", "T002"),
            proposed_disposition="KEEP_CONTEXT_EXTENSION",
        )
        self.assertEqual(session.state, PROVISIONAL)
        expected_hash = session.session_hash
        session = record_expert_final_decision(
            session,
            pack,
            ai_draft,
            action_id=_action_id("approved-final"),
            actor_ref="expert-local-01",
            recorded_at=NOW,
            target_state=APPROVED,
            final_disposition="KEEP_CONTEXT_EXTENSION",
            rationale="确认共享稳定字段，并保留特殊任务扩展。",
            evidence_refs=("T001", "T002"),
            ai_draft_relation="REVISED",
            expected_session_hash=expected_hash,
        )

        self.assertEqual(session.state, APPROVED)
        self.assertEqual(
            session.events[-1].payload["expected_session_hash"],
            expected_hash,
        )
        verify_expert_review_session_against_sources(session, pack, ai_draft)
        replayed = ExpertReviewSession.from_dict(
            session.to_dict(),
            pack,
            ai_draft,
        )
        self.assertEqual(replayed, session)
        self.assertFalse(session.aggregate_report()["patch_eligible"])
        self.assertFalse(session.aggregate_report()["gold_eligible"])

    def test_provisional_is_invalidated_by_more_expert_thought(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        session = record_expert_status(
            session,
            pack,
            ai_draft,
            action_id=_action_id("provisional-before-reopen"),
            actor_ref="expert-local-01",
            recorded_at=NOW,
            target_state=PROVISIONAL,
            rationale="先形成暂定结论。",
            evidence_refs=("T001",),
            proposed_disposition="KEEP_CONTEXT_EXTENSION",
        )
        session = submit_expert_thought(
            session,
            pack,
            ai_draft,
            action_id=_action_id("reopening-thought"),
            actor_role=DOMAIN_EXPERT,
            actor_ref="expert-local-01",
            recorded_at=NOW,
            raw_text="补充：仍需区分指挥人员和普通人员。",
        )
        self.assertEqual(session.state, DELIBERATING)
        with self.assertRaises(ExpertReviewError) as error:
            record_expert_final_decision(
                session,
                pack,
                ai_draft,
                action_id=_action_id("invalid-direct-final"),
                actor_ref="expert-local-01",
                recorded_at=NOW,
                target_state=APPROVED,
                final_disposition="KEEP_CONTEXT_EXTENSION",
                rationale="不应从讨论态直接批准。",
                evidence_refs=("T002",),
                ai_draft_relation="NOT_USED",
                expected_session_hash=session.session_hash,
            )
        self.assertEqual(error.exception.code, "EXPERT_FINAL_STATE_INVALID")

    def test_final_is_expert_only_concurrent_and_terminal(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        session = record_expert_status(
            session,
            pack,
            ai_draft,
            action_id=_action_id("provisional-for-concurrency"),
            actor_ref="expert-local-01",
            recorded_at=NOW,
            target_state=PROVISIONAL,
            rationale="形成暂定结论。",
            evidence_refs=("T001",),
            proposed_disposition="KEEP_CONTEXT_EXTENSION",
        )
        with self.assertRaises(ExpertReviewError) as stale_error:
            record_expert_final_decision(
                session,
                pack,
                ai_draft,
                action_id=_action_id("stale-final"),
                actor_ref="expert-local-01",
                recorded_at=NOW,
                target_state=APPROVED,
                final_disposition="KEEP_CONTEXT_EXTENSION",
                rationale="错误的并发锚点。",
                evidence_refs=("T001",),
                ai_draft_relation="ACCEPTED",
                expected_session_hash="0" * 64,
            )
        self.assertEqual(
            stale_error.exception.code,
            "EXPERT_SESSION_CONCURRENT_MODIFICATION",
        )
        session = record_expert_final_decision(
            session,
            pack,
            ai_draft,
            action_id=_action_id("valid-final"),
            actor_ref="expert-local-01",
            recorded_at=NOW,
            target_state=APPROVED,
            final_disposition="KEEP_CONTEXT_EXTENSION",
            rationale="最终裁决。",
            evidence_refs=("T001",),
            ai_draft_relation="REVISED",
            expected_session_hash=session.session_hash,
        )
        with self.assertRaises(ExpertReviewError) as terminal_error:
            submit_expert_thought(
                session,
                pack,
                ai_draft,
                action_id=_action_id("terminal-thought"),
                actor_role=DOMAIN_EXPERT,
                actor_ref="expert-local-01",
                recorded_at=NOW,
                raw_text="终态后不得追加。",
            )
        self.assertEqual(terminal_error.exception.code, "EXPERT_SESSION_TERMINAL")

    def test_tampering_and_wrong_sources_are_rejected(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        mutations = (
            lambda value: value["events"][0]["payload"].__setitem__(
                "raw_text", "tampered"
            ),
            lambda value: value["events"][0].__setitem__("actor_ref", "other"),
            lambda value: value["events"][0].__setitem__("sequence", 2),
            lambda value: value["events"][0].__setitem__("event_type", {}),
            lambda value: value["events"][0].__setitem__(
                "previous_event_hash", "0" * 64
            ),
            lambda value: value.__setitem__("state", PROVISIONAL),
            lambda value: value.__setitem__("session_hash", "0" * 64),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                stored = session.to_dict()
                mutate(stored)
                with self.assertRaises(ExpertReviewError):
                    ExpertReviewSession.from_dict(stored, pack, ai_draft)

        forged_pack = copy.copy(pack)
        object.__setattr__(forged_pack, "pack_hash", "0" * 64)
        with self.assertRaises(ExpertReviewError) as source_error:
            ExpertReviewSession.from_dict(
                session.to_dict(),
                forged_pack,
                ai_draft,
            )
        self.assertEqual(
            source_error.exception.code,
            "EXPERT_SESSION_SOURCE_INVALID",
        )

    def test_multi_event_deletion_reordering_duplication_and_transplant_fail(
        self,
    ) -> None:
        pack, ai_draft, session = _session_with_thought()
        session = submit_expert_thought(
            session,
            pack,
            ai_draft,
            action_id=_action_id("second-ledger-thought"),
            actor_role=DOMAIN_EXPERT,
            actor_ref="expert-local-01",
            recorded_at=NOW,
            raw_text="第二条追加思考。",
        )
        mutations = (
            lambda value: value["events"].pop(0),
            lambda value: value["events"].reverse(),
            lambda value: value["events"].append(
                copy.deepcopy(value["events"][-1])
            ),
            lambda value: value.__setitem__(
                "session_id",
                canonical_digest({"transplanted": True}),
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                stored = session.to_dict()
                mutate(stored)
                with self.assertRaises(ExpertReviewError):
                    ExpertReviewSession.from_dict(stored, pack, ai_draft)

    def test_inputs_are_detached_and_aggregate_contains_no_sensitive_text(self) -> None:
        pack, ai_draft = _sources()
        session = open_expert_review_session(
            pack,
            ai_draft,
            session_id=canonical_digest({"fixture": "detach"}),
        )
        refs = ["F001"]
        text = "sensitive-canary 专家思考"
        session = submit_expert_thought(
            session,
            pack,
            ai_draft,
            action_id=_action_id("detach-thought"),
            actor_role=DOMAIN_EXPERT,
            actor_ref="actor-sensitive-canary",
            recorded_at=NOW,
            raw_text=text,
            evidence_refs=tuple(refs),
        )
        refs[0] = "F999"
        encoded_event = json.dumps(session.to_dict(), ensure_ascii=False)
        encoded_report = json.dumps(
            session.aggregate_report(),
            ensure_ascii=False,
            sort_keys=True,
        )

        self.assertIn("F001", encoded_event)
        for canary in (
            "sensitive-canary",
            "actor-sensitive-canary",
            "F001",
            session.session_id,
            session.session_hash,
        ):
            self.assertNotIn(canary, encoded_report)

    def test_model_output_cannot_smuggle_state_or_unknown_refs(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        payload = _synthesis_model_payload()
        payload["final_state"] = APPROVED
        with self.assertRaises(ExpertSynthesisValidationError) as fields_error:
            ExpertSynthesisDraft.from_model_dict(
                payload,
                pack,
                ai_draft,
                source_session_hash=session.session_hash,
                source_thought_refs=("T001",),
            )
        self.assertEqual(
            fields_error.exception.code,
            "EXPERT_SYNTHESIS_FIELDS_INVALID",
        )

        payload = _synthesis_model_payload()
        payload["expert_claims"][0]["evidence_refs"] = ["F001"]
        with self.assertRaises(ExpertSynthesisValidationError) as thought_error:
            ExpertSynthesisDraft.from_model_dict(
                payload,
                pack,
                ai_draft,
                source_session_hash=session.session_hash,
                source_thought_refs=("T001",),
            )
        self.assertEqual(
            thought_error.exception.code,
            "EXPERT_SYNTHESIS_THOUGHT_REF_REQUIRED",
        )

        empty = {
            "schema_version": "expert-synthesis-model-output.v1",
            "expert_claims": [],
            "hypotheses": [],
            "uncertainties": [],
            "risks": [],
            "evidence_requests": [],
            "questions_for_expert": [],
        }
        with self.assertRaises(ExpertSynthesisValidationError) as empty_error:
            ExpertSynthesisDraft.from_model_dict(
                empty,
                pack,
                ai_draft,
                source_session_hash=session.session_hash,
                source_thought_refs=("T001",),
            )
        self.assertEqual(
            empty_error.exception.code,
            "EXPERT_SYNTHESIS_EMPTY",
        )

    def test_action_ids_time_order_and_audit_identifiers_are_strict(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        with self.assertRaises(ExpertReviewError) as duplicate_error:
            submit_expert_thought(
                session,
                pack,
                ai_draft,
                action_id=_action_id("initial-thought"),
                actor_role=DOMAIN_EXPERT,
                actor_ref="expert-local-01",
                recorded_at=NOW,
                raw_text="重复提交不得生成 T002。",
            )
        self.assertEqual(
            duplicate_error.exception.code,
            "EXPERT_ACTION_ALREADY_APPLIED",
        )

        with self.assertRaises(ExpertReviewError) as time_error:
            submit_expert_thought(
                session,
                pack,
                ai_draft,
                action_id=_action_id("past-thought"),
                actor_role=DOMAIN_EXPERT,
                actor_ref="expert-local-01",
                recorded_at="2026-07-28T02:59:59Z",
                raw_text="时间倒序。",
            )
        self.assertEqual(
            time_error.exception.code,
            "EXPERT_EVENT_TIME_ORDER_INVALID",
        )

        with self.assertRaises(ExpertReviewError) as timestamp_error:
            submit_expert_thought(
                session,
                pack,
                ai_draft,
                action_id=_action_id("newline-time"),
                actor_role=DOMAIN_EXPERT,
                actor_ref="expert-local-01",
                recorded_at="2026-07-28\n03:00:01+00:00",
                raw_text="非法时间分隔符。",
            )
        self.assertEqual(
            timestamp_error.exception.code,
            "EXPERT_TIMESTAMP_INVALID",
        )

        with self.assertRaises(ExpertReviewError) as actor_error:
            submit_expert_thought(
                session,
                pack,
                ai_draft,
                action_id=_action_id("bad-actor"),
                actor_role=DOMAIN_EXPERT,
                actor_ref="expert\nforged",
                recorded_at=NOW,
                raw_text="非法 actor。",
            )
        self.assertEqual(
            actor_error.exception.code,
            "EXPERT_IDENTIFIER_INVALID",
        )

    def test_final_must_match_provisional_and_accepted_ai_disposition(self) -> None:
        pack, ai_draft, session = _session_with_thought()
        session = record_expert_status(
            session,
            pack,
            ai_draft,
            action_id=_action_id("final-policy-provisional"),
            actor_ref="expert-local-01",
            recorded_at=NOW,
            target_state=PROVISIONAL,
            rationale="暂定保留场景扩展。",
            evidence_refs=("T001",),
            proposed_disposition="KEEP_CONTEXT_EXTENSION",
        )
        with self.assertRaises(ExpertReviewError) as mismatch_error:
            record_expert_final_decision(
                session,
                pack,
                ai_draft,
                action_id=_action_id("mismatched-final"),
                actor_ref="expert-local-01",
                recorded_at=NOW,
                target_state=APPROVED,
                final_disposition="REVIEW_PLACEMENT",
                rationale="不能静默改成另一结论。",
                evidence_refs=("T001",),
                ai_draft_relation="REVISED",
                expected_session_hash=session.session_hash,
            )
        self.assertEqual(
            mismatch_error.exception.code,
            "EXPERT_FINAL_PROVISIONAL_MISMATCH",
        )

        with self.assertRaises(ExpertReviewError) as relation_error:
            record_expert_final_decision(
                session,
                pack,
                ai_draft,
                action_id=_action_id("false-ai-acceptance"),
                actor_ref="expert-local-01",
                recorded_at=NOW,
                target_state=APPROVED,
                final_disposition="KEEP_CONTEXT_EXTENSION",
                rationale="初审是 NEED_EVIDENCE，不能标成原样接受。",
                evidence_refs=("T001",),
                ai_draft_relation="ACCEPTED",
                expected_session_hash=session.session_hash,
            )
        self.assertEqual(
            relation_error.exception.code,
            "EXPERT_FINAL_AI_RELATION_INVALID",
        )

    def test_bailian_requires_exact_payload_approval_before_network(self) -> None:
        pack, ai_draft, session = _session_with_thought()

        class RecordingProvider(BailianExpertSynthesisProvider):
            def __init__(self):
                super().__init__(
                    BailianConfig(api_key="expert-synthesis-secret", max_attempts=1)
                )
                self.requests = []

            def _post_json(self, body):
                self.requests.append(body)
                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    _synthesis_model_payload(),
                                    ensure_ascii=False,
                                )
                            },
                        }
                    ]
                }

        provider = RecordingProvider()
        thoughts = (
            (
                "T001",
                session.events[0].payload["raw_text"],
            ),
        )
        with self.assertRaises(BailianProviderError) as approval_error:
            provider.synthesize(
                pack,
                ai_draft,
                source_session_hash=session.session_hash,
                expert_thoughts=thoughts,
                approved_external_payload_hash=None,
            )
        self.assertEqual(
            approval_error.exception.code,
            "EXTERNAL_EXPERT_PAYLOAD_APPROVAL_REQUIRED",
        )
        self.assertEqual(provider.requests, [])

        approval_hash = provider.approval_payload_hash(
            pack,
            ai_draft,
            thoughts,
        )
        draft = provider.synthesize(
            pack,
            ai_draft,
            source_session_hash=session.session_hash,
            expert_thoughts=thoughts,
            approved_external_payload_hash=approval_hash,
        )
        encoded_request = json.dumps(
            provider.requests,
            ensure_ascii=False,
            sort_keys=True,
        )
        sent_user_payload = json.loads(
            provider.requests[0]["messages"][1]["content"]
        )
        self.assertEqual(draft.source_session_hash, session.session_hash)
        self.assertEqual(
            sent_user_payload["expert_thoughts"][0]["raw_text"],
            session.events[0].payload["raw_text"],
        )
        for forbidden in (
            "node-008",
            pack.case_id,
            pack.pack_hash,
            session.session_hash,
            "expert-local-01",
            "expert-synthesis-secret",
        ):
            self.assertNotIn(forbidden, encoded_request)


if __name__ == "__main__":
    unittest.main()
