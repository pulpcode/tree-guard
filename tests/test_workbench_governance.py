from __future__ import annotations

import json
import stat
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from treeguard.adapter import adapt_tree_document
from treeguard.ai_review import (
    INTENT_CLARIFICATION_PROMPT_VERSION,
    INTENT_PROMPT_VERSION,
    ModelTraceAttempt,
    ModelTraceMessage,
    ModelTraceSink,
    SEMANTIC_PROMPT_VERSION,
)
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentClarificationAnswer,
    IntentClarificationRound,
    IntentConfirmation,
    IntentRequest,
)
from treeguard.models import CanonicalTree, ImportResult
from treeguard.repository_client import CategoryRef, ResourceHead, VersionRef
from treeguard.retrieval import CandidateSet
from treeguard.semantic_recommendation import (
    SemanticRecommendationDraft,
    build_semantic_candidate_projection,
)
from treeguard.simulator import build_fictional_tree
from treeguard.web import create_app
from treeguard.workbench import WorkbenchService
from treeguard.workbench_governance import (
    WorkbenchGovernanceService,
    model_diagnostics_enabled_from_env,
)


@dataclass
class FakeRepository:
    result: ImportResult

    def list_categories(self) -> tuple[CategoryRef, ...]:
        return ()

    def list_resources(self, category_id: str) -> tuple[ResourceHead, ...]:
        return ()

    def list_versions(self, resource_id: str) -> tuple[VersionRef, ...]:
        return ()

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ) -> ImportResult:
        return self.result


class InlineExecutor:
    def submit(self, function: Any) -> None:
        function()


class FictionalIntentProvider:
    def draft(
        self,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> ChangeIntentDraft:
        return ChangeIntentDraft.from_model_dict(
            _intent_payload(question=None),
            request,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-test-model",
            prompt_version=INTENT_PROMPT_VERSION,
        )

    def clarify(
        self,
        request: IntentRequest,
        initial_draft: ChangeIntentDraft,
        answer: IntentClarificationAnswer,
        tree: CanonicalTree,
    ) -> IntentClarificationRound:
        return IntentClarificationRound.from_model_dict(
            _intent_payload(question=None),
            request,
            initial_draft,
            answer,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-test-model",
            prompt_version=INTENT_CLARIFICATION_PROMPT_VERSION,
        )


class ClarifyingIntentProvider(FictionalIntentProvider):
    def __init__(self, *, unresolved_after_answer: bool = False) -> None:
        self.unresolved_after_answer = unresolved_after_answer

    def draft(
        self,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> ChangeIntentDraft:
        return ChangeIntentDraft.from_model_dict(
            _intent_payload(question="虚构计量单位应如何选择？"),
            request,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-test-model",
            prompt_version=INTENT_PROMPT_VERSION,
        )

    def clarify(
        self,
        request: IntentRequest,
        initial_draft: ChangeIntentDraft,
        answer: IntentClarificationAnswer,
        tree: CanonicalTree,
    ) -> IntentClarificationRound:
        return IntentClarificationRound.from_model_dict(
            _intent_payload(
                question=(
                    "仍需由专家确定一个虚构计量约束。"
                    if self.unresolved_after_answer
                    else None
                )
            ),
            request,
            initial_draft,
            answer,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-test-model",
            prompt_version=INTENT_CLARIFICATION_PROMPT_VERSION,
        )


class CountingIntentProvider(FictionalIntentProvider):
    def __init__(self) -> None:
        self.draft_calls = 0

    def draft(
        self,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> ChangeIntentDraft:
        self.draft_calls += 1
        return super().draft(request, tree)


class FictionalSemanticProvider:
    def recommend(
        self,
        confirmation: IntentConfirmation,
        candidate_set: CandidateSet,
        tree: CanonicalTree,
    ) -> SemanticRecommendationDraft:
        projection = build_semantic_candidate_projection(
            confirmation,
            candidate_set,
            tree,
        )
        assessments = [
            {
                "candidate_ref": candidate.candidate_ref,
                "relation": (
                    "SEMANTICALLY_EQUIVALENT"
                    if index == 0
                    else "NOT_EQUIVALENT"
                ),
                "reason": "完全虚构的候选比较。",
            }
            for index, candidate in enumerate(projection.candidates)
        ]
        return SemanticRecommendationDraft.from_model_dict(
            {
                "schema_version": "semantic-recommendation-model-output.v1",
                "candidate_assessments": assessments,
                "recommended_action": "USE_EXISTING_NODE",
                "selected_candidate_ref": "C001",
                "rationale": "首个虚构候选与需求等价。",
                "uncertainties": [],
                "evidence_gaps": [],
                "clarification_question": None,
            },
            confirmation,
            candidate_set,
            tree,
            model_provider="FICTIONAL_TEST_PROVIDER",
            model_capability="JSON_OBJECT",
            model_name="fictional-test-model",
            prompt_version=SEMANTIC_PROMPT_VERSION,
        )


@dataclass(frozen=True)
class FictionalProviderFactory:
    intent: FictionalIntentProvider = FictionalIntentProvider()
    semantic: FictionalSemanticProvider = FictionalSemanticProvider()

    def intent_provider(
        self,
        mode: str,
        trace_sink: ModelTraceSink | None = None,
    ) -> FictionalIntentProvider:
        if trace_sink is not None:
            trace_sink(
                _model_trace(
                    stage="INTENT_DRAFT",
                    prompt_version=INTENT_PROMPT_VERSION,
                )
            )
        return self.intent

    def semantic_provider(
        self,
        mode: str,
        trace_sink: ModelTraceSink | None = None,
    ) -> FictionalSemanticProvider:
        if trace_sink is not None:
            trace_sink(
                _model_trace(
                    stage="SEMANTIC_RECOMMENDATION",
                    prompt_version=SEMANTIC_PROMPT_VERSION,
                )
            )
        return self.semantic


def _model_trace(*, stage: str, prompt_version: str) -> ModelTraceAttempt:
    return ModelTraceAttempt(
        stage=stage,
        attempt=1,
        provider="FICTIONAL_TEST_PROVIDER",
        model="fictional-test-model",
        prompt_version=prompt_version,
        thinking_status="DISABLED",
        request_messages=(
            ModelTraceMessage(
                role="system",
                content="只处理完全虚构的测试输入。",
                content_truncated=False,
            ),
            ModelTraceMessage(
                role="user",
                content='{"fictional_requirement":"陈列高度"}',
                content_truncated=False,
            ),
        ),
        response_content='{"fictional_result":"合同有效"}',
        response_content_truncated=False,
        validation_status="PASSED",
        validation_error_code=None,
        usage=(
            ("prompt_tokens", 20),
            ("completion_tokens", 10),
            ("total_tokens", 30),
        ),
    )


def _intent_payload(
    *,
    question: str | None,
    subject: str | None = "陈列高度",
) -> dict[str, Any]:
    return {
        "schema_version": "change-intent-model-output.v1",
        "subject": subject,
        "role": "藏品尺寸记录",
        "scenario": "虚构展览",
        "lifecycle": "目录使用期",
        "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
        "node_kind": "PROPERTY",
        "value_type": "float",
        "cardinality": "SINGLE",
        "confirmed_facts": ["需要记录完全虚构的陈列高度。"],
        "assumptions": [],
        "evidence_gaps": [],
        "clarification_question": question,
    }


def _result() -> ImportResult:
    return adapt_tree_document(build_fictional_tree(node_count=20))


def _id_factory() -> Any:
    values = iter(("001", "002", "003", "004", "005", "006"))
    return lambda: next(values)


class WorkbenchGovernanceServiceTests(unittest.TestCase):
    def test_model_diagnostics_environment_is_strict(self) -> None:
        with patch.dict(
            "os.environ",
            {"TREEGUARD_WORKBENCH_MODEL_DIAGNOSTICS": "1"},
            clear=False,
        ):
            self.assertTrue(model_diagnostics_enabled_from_env())
        with patch.dict(
            "os.environ",
            {"TREEGUARD_WORKBENCH_MODEL_DIAGNOSTICS": "yes"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "flag must be zero or one",
            ):
                model_diagnostics_enabled_from_env()

    def test_model_diagnostics_are_opt_in_and_memory_only(self) -> None:
        repository = FakeRepository(_result())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            disabled = WorkbenchGovernanceService(
                repository=repository,
                sidecar_root=root,
                provider_factory=FictionalProviderFactory(),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            operation = disabled.create_case(
                resource_id="fictional-museum-resource",
                version="SIM-V2",
                requirement_text="记录虚构藏品的陈列高度。",
                proposed_parent_ref=None,
                node_kind_hint="UNKNOWN",
                value_type_hint=None,
                cardinality_hint="UNKNOWN",
                model_mode="SIMULATOR_LIVE",
                external_data_approved=False,
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "model diagnostics are disabled",
            ):
                disabled.model_trace_view(operation["case_ref"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            enabled = WorkbenchGovernanceService(
                repository=repository,
                sidecar_root=root,
                provider_factory=FictionalProviderFactory(),
                diagnostics_enabled=True,
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            operation = enabled.create_case(
                resource_id="fictional-museum-resource",
                version="SIM-V2",
                requirement_text="记录虚构藏品的陈列高度。",
                proposed_parent_ref=None,
                node_kind_hint="UNKNOWN",
                value_type_hint=None,
                cardinality_hint="UNKNOWN",
                model_mode="SIMULATOR_LIVE",
                external_data_approved=False,
            )
            trace = enabled.model_trace_view(operation["case_ref"])

            self.assertEqual(
                trace["schema_version"],
                "workbench-model-trace-view.v1",
            )
            self.assertEqual(trace["model_mode"], "SIMULATOR_LIVE")
            self.assertEqual(trace["thinking_status"], "DISABLED")
            self.assertEqual(len(trace["items"]), 1)
            self.assertEqual(
                trace["items"][0]["request_messages"][1]["content"],
                '{"fictional_requirement":"陈列高度"}',
            )
            self.assertEqual(
                {path.name for path in (root / operation["case_ref"]).iterdir()},
                {"01-intent-request.json", "02-intent-draft.json"},
            )

    def test_complete_case_is_private_replayable_sidecar(self) -> None:
        repository = FakeRepository(_result())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            service = WorkbenchGovernanceService(
                repository=repository,
                sidecar_root=root,
                provider_factory=FictionalProviderFactory(),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
                now_factory=lambda: "2026-07-29T12:00:00Z",
            )

            operation = service.create_case(
                resource_id="fictional-museum-resource",
                version="SIM-V2",
                requirement_text="记录虚构藏品的陈列高度。",
                proposed_parent_ref="N000003",
                node_kind_hint="PROPERTY",
                value_type_hint="float",
                cardinality_hint="SINGLE",
                model_mode="SIMULATOR_LIVE",
                external_data_approved=False,
            )
            self.assertEqual(operation["status"], "SUCCEEDED")
            case_ref = operation["case_ref"]
            self.assertEqual(service.case_view(case_ref)["status"], "INTENT_REVIEW")

            intent_operation = service.review_intent(
                case_ref,
                decision="CONFIRM",
            )
            self.assertEqual(intent_operation["status"], "SUCCEEDED")
            review_view = service.case_view(case_ref)
            self.assertEqual(
                review_view["status"],
                "RECOMMENDATION_REVIEW",
            )
            self.assertEqual(
                review_view["recommendation"]["recommended_action"],
                "USE_EXISTING_NODE",
            )

            final_operation = service.review_recommendation(
                case_ref,
                decision="CONFIRM",
                reviewer_reasoning="虚构演示中接受该受约束建议。",
            )
            self.assertEqual(final_operation["status"], "SUCCEEDED")
            final_view = service.case_view(case_ref)
            self.assertEqual(final_view["status"], "COMPLETED")
            self.assertEqual(final_view["record"]["status"], "CONFIRMED")
            self.assertFalse(final_view["record"]["semantic_approval"])
            self.assertFalse(final_view["record"]["gold_eligible"])
            self.assertFalse(final_view["record"]["patch_eligible"])

            case_directory = root / case_ref
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE(case_directory.stat().st_mode),
                0o700,
            )
            expected_files = {
                "01-intent-request.json",
                "02-intent-draft.json",
                "05-intent-review-action.json",
                "06-intent-confirmation.json",
                "07-candidate-set.json",
                "08-recommendation-draft.json",
                "09-recommendation-review-action.json",
                "10-recommendation-record.json",
            }
            self.assertEqual(
                {path.name for path in case_directory.iterdir()},
                expected_files,
            )
            for path in case_directory.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            encoded_view = json.dumps(final_view, ensure_ascii=False)
            self.assertNotIn("fictional-museum-root", encoded_view)
            self.assertNotIn("snapshot_hash", encoded_view)
            self.assertNotIn("draft_hash", encoded_view)
            self.assertNotIn("reviewer_reasoning", encoded_view)

    def test_one_clarification_round_either_resolves_or_stops(self) -> None:
        for unresolved, expected_status in (
            (False, "INTENT_REVIEW"),
            (True, "CLARIFICATION_LIMIT_REACHED"),
        ):
            with self.subTest(unresolved=unresolved):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary) / "sidecars"
                    service = WorkbenchGovernanceService(
                        repository=FakeRepository(_result()),
                        sidecar_root=root,
                        provider_factory=FictionalProviderFactory(
                            intent=ClarifyingIntentProvider(
                                unresolved_after_answer=unresolved
                            )
                        ),
                        executor=InlineExecutor(),
                        id_factory=_id_factory(),
                        now_factory=lambda: "2026-07-29T12:00:00Z",
                    )
                    operation = service.create_case(
                        resource_id="fictional-museum-resource",
                        version="SIM-V2",
                        requirement_text="记录虚构藏品的陈列高度。",
                        proposed_parent_ref=None,
                        node_kind_hint="UNKNOWN",
                        value_type_hint=None,
                        cardinality_hint="UNKNOWN",
                        model_mode="SIMULATOR_LIVE",
                        external_data_approved=False,
                    )
                    case_ref = operation["case_ref"]
                    waiting = service.case_view(case_ref)
                    self.assertEqual(
                        waiting["status"],
                        "NEEDS_CLARIFICATION",
                    )
                    self.assertEqual(
                        waiting["intent"]["content"][
                            "clarification_question"
                        ],
                        "虚构计量单位应如何选择？",
                    )

                    clarified = service.clarify(
                        case_ref,
                        answer_text="本次虚构演示采用厘米。",
                    )

                    self.assertEqual(clarified["status"], "SUCCEEDED")
                    self.assertEqual(
                        service.case_view(case_ref)["status"],
                        expected_status,
                    )
                    case_directory = root / case_ref
                    self.assertTrue(
                        (case_directory / "03-clarification-answer.json").exists()
                    )
                    self.assertTrue(
                        (case_directory / "04-clarification-round.json").exists()
                    )

    def test_bailian_requires_approval_before_creating_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            service = WorkbenchGovernanceService(
                repository=FakeRepository(_result()),
                sidecar_root=root,
                provider_factory=FictionalProviderFactory(),
                executor=InlineExecutor(),
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "explicit external data approval",
            ):
                service.create_case(
                    resource_id="fictional-museum-resource",
                    version="SIM-V2",
                    requirement_text="记录一个完全虚构字段。",
                    proposed_parent_ref=None,
                    node_kind_hint="UNKNOWN",
                    value_type_hint=None,
                    cardinality_hint="UNKNOWN",
                    model_mode="BAILIAN_LIVE",
                    external_data_approved=False,
                )

            self.assertFalse(root.exists())

    def test_polling_completed_operation_does_not_repeat_model_call(self) -> None:
        intent_provider = CountingIntentProvider()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            service = WorkbenchGovernanceService(
                repository=FakeRepository(_result()),
                sidecar_root=root,
                provider_factory=FictionalProviderFactory(
                    intent=intent_provider
                ),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )

            operation = service.create_case(
                resource_id="fictional-museum-resource",
                version="SIM-V2",
                requirement_text="记录虚构藏品的陈列高度。",
                proposed_parent_ref=None,
                node_kind_hint="UNKNOWN",
                value_type_hint=None,
                cardinality_hint="UNKNOWN",
                model_mode="SIMULATOR_LIVE",
                external_data_approved=False,
            )
            operation_ref = operation["operation_ref"]
            case_ref = operation["case_ref"]

            first_poll = service.operation_view(operation_ref)
            second_poll = service.operation_view(operation_ref)
            service.case_view(case_ref)
            service.case_view(case_ref)

            self.assertEqual(first_poll, second_poll)
            self.assertEqual(first_poll["status"], "SUCCEEDED")
            self.assertEqual(intent_provider.draft_calls, 1)
            self.assertEqual(
                {
                    path.name
                    for path in (root / case_ref).iterdir()
                },
                {
                    "01-intent-request.json",
                    "02-intent-draft.json",
                },
            )


class WorkbenchGovernanceAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_http_flow_exposes_only_runtime_views(self) -> None:
        repository = FakeRepository(_result())
        with tempfile.TemporaryDirectory() as temporary:
            governance = WorkbenchGovernanceService(
                repository=repository,
                sidecar_root=Path(temporary) / "sidecars",
                provider_factory=FictionalProviderFactory(),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
                now_factory=lambda: "2026-07-29T12:00:00Z",
            )
            app = create_app(
                WorkbenchService(repository),
                governance,
            )
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                created = await client.post(
                    "/api/v1/governance/cases",
                    json={
                        "resource_id": "fictional-museum-resource",
                        "version": "SIM-V2",
                        "requirement_text": "记录虚构藏品的陈列高度。",
                        "proposed_parent_ref": "N000003",
                        "node_kind_hint": "PROPERTY",
                        "value_type_hint": "float",
                        "cardinality_hint": "SINGLE",
                        "model_mode": "SIMULATOR_LIVE",
                        "external_data_approved": False,
                    },
                )
                self.assertEqual(created.status_code, 202)
                operation = created.json()
                case_ref = operation["case_ref"]
                polled = await client.get(
                    f"/api/v1/governance/operations/"
                    f"{operation['operation_ref']}"
                )
                case = await client.get(
                    f"/api/v1/governance/cases/{case_ref}"
                )
                diagnostics = await client.get(
                    f"/api/v1/governance/cases/{case_ref}/model-traces"
                )
                reviewed = await client.post(
                    f"/api/v1/governance/cases/{case_ref}/intent-review",
                    json={"decision": "CONFIRM"},
                )

            self.assertEqual(polled.json()["status"], "SUCCEEDED")
            self.assertEqual(case.json()["status"], "INTENT_REVIEW")
            self.assertEqual(diagnostics.status_code, 404)
            self.assertEqual(
                diagnostics.json()["error_code"],
                "WORKBENCH_DIAGNOSTICS_DISABLED",
            )
            self.assertEqual(reviewed.status_code, 202)
            encoded = json.dumps(
                [operation, polled.json(), case.json(), reviewed.json()],
                ensure_ascii=False,
            )
            self.assertNotIn("fictional-museum-root", encoded)
            self.assertNotIn("source_snapshot_hash", encoded)
            self.assertNotIn(str(temporary), encoded)

    async def test_model_trace_endpoint_is_allowlisted_when_enabled(self) -> None:
        repository = FakeRepository(_result())
        with tempfile.TemporaryDirectory() as temporary:
            governance = WorkbenchGovernanceService(
                repository=repository,
                sidecar_root=Path(temporary) / "sidecars",
                provider_factory=FictionalProviderFactory(),
                diagnostics_enabled=True,
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            app = create_app(WorkbenchService(repository), governance)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                created = await client.post(
                    "/api/v1/governance/cases",
                    json={
                        "resource_id": "fictional-museum-resource",
                        "version": "SIM-V2",
                        "requirement_text": "记录虚构藏品的陈列高度。",
                    },
                )
                case_ref = created.json()["case_ref"]
                response = await client.get(
                    f"/api/v1/governance/cases/{case_ref}/model-traces"
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["model_mode"], "SIMULATOR_LIVE")
            self.assertEqual(payload["thinking_status"], "DISABLED")
            self.assertEqual(payload["items"][0]["validation_status"], "PASSED")
            self.assertEqual(payload["items"][0]["usage"]["total_tokens"], 30)
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("fixture-key", encoded)
            self.assertNotIn(str(temporary), encoded)
            self.assertNotIn("node-", encoded)

    async def test_null_subject_remains_a_valid_runtime_view(self) -> None:
        class NullSubjectIntentProvider(FictionalIntentProvider):
            def draft(
                self,
                request: IntentRequest,
                tree: CanonicalTree,
            ) -> ChangeIntentDraft:
                return ChangeIntentDraft.from_model_dict(
                    _intent_payload(question=None, subject=None),
                    request,
                    tree,
                    model_provider="FICTIONAL_TEST_PROVIDER",
                    model_capability="JSON_OBJECT",
                    model_name="fictional-test-model",
                    prompt_version=INTENT_PROMPT_VERSION,
                )

        repository = FakeRepository(_result())
        with tempfile.TemporaryDirectory() as temporary:
            governance = WorkbenchGovernanceService(
                repository=repository,
                sidecar_root=Path(temporary) / "sidecars",
                provider_factory=FictionalProviderFactory(
                    intent=NullSubjectIntentProvider()
                ),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            app = create_app(WorkbenchService(repository), governance)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                created = await client.post(
                    "/api/v1/governance/cases",
                    json={
                        "resource_id": "fictional-museum-resource",
                        "version": "SIM-V2",
                        "requirement_text": "记录一个主体尚不确定的虚构字段。",
                    },
                )
                case_ref = created.json()["case_ref"]
                case = await client.get(
                    f"/api/v1/governance/cases/{case_ref}"
                )

            self.assertEqual(created.status_code, 202)
            self.assertEqual(case.status_code, 200)
            self.assertIsNone(
                case.json()["intent"]["content"]["subject"]
            )


if __name__ == "__main__":
    unittest.main()
