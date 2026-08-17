"""Isolated Workbench application service for the navigation Copilot Shadow."""

from __future__ import annotations

import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from treeguard.ai_review import (
    BailianConfig,
    BailianNavigationSemanticProvider,
    BailianNavigationUnderstandingProvider,
    BailianProviderError,
    InternalQwenConfig,
    InternalQwenNavigationSemanticProvider,
    InternalQwenNavigationUnderstandingProvider,
    LoopbackSimulatorConfig,
    LoopbackSimulatorNavigationSemanticProvider,
    LoopbackSimulatorNavigationUnderstandingProvider,
    ModelTraceAttempt,
    ModelTraceSink,
)
from treeguard.change_intent import IntentRequest
from treeguard.change_understanding_v2 import ChangeUnderstandingV2
from treeguard.models import CanonicalTree
from treeguard.navigation_copilot import (
    NavigationCandidateSet,
    NavigationClarificationAnswer,
    NavigationClarificationRound,
    NavigationInterpretation,
    NavigationOutcome,
    NavigationPolicyDecision,
    NavigationPolicyDecisionV2,
    NavigationSemanticDraft,
    NavigationSemanticDraftV2,
    NavigationSemanticProjection,
    NavigationSemanticProjectionV2,
    NavigationShadowObservation,
    apply_navigation_policy,
    apply_navigation_policy_v2,
    build_navigation_candidate_set,
    build_navigation_outcome,
    build_navigation_semantic_projection,
    build_navigation_semantic_projection_v2,
    navigation_shadow_aggregate,
)
from treeguard.navigation_shadow_run import (
    NavigationShadowQualification,
    NavigationShadowRunError,
    NavigationShadowRunManifest,
    build_shadow_qualification,
)
from treeguard.private_io import read_private_json, write_private_json
from treeguard.simulator import SIMULATOR_BEARER_TOKEN
from treeguard.workbench import (
    ReadOnlyTreeRepository,
    WorkbenchError,
    build_tree_reference_index,
)
from treeguard.workbench_governance import MODEL_MODES
from treeguard.workbench_sidecar import (
    WorkbenchSidecarError,
    create_private_directory,
    ensure_private_directory,
    validate_private_directory,
)


COPILOT_CASE_VIEW_VERSION = "navigation-copilot-case-view.v1"
COPILOT_CAPABILITY_VIEW_VERSION = "navigation-copilot-capability.v1"
COPILOT_OPERATION_VIEW_VERSION = "workbench-operation-view.v1"
COPILOT_MODEL_TRACE_VIEW_VERSION = "workbench-model-trace-view.v1"
_MAX_MODEL_TRACE_ATTEMPTS = 8
_MAX_LOGICAL_MODEL_CALLS = 2


class WorkbenchNavigationCopilotError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class NavigationUnderstandingProvider(Protocol):
    def understand(
        self,
        request: IntentRequest,
        tree: CanonicalTree,
        *,
        clarification_question: str | None = None,
        clarification_answer: str | None = None,
    ) -> ChangeUnderstandingV2: ...


class NavigationSemanticProvider(Protocol):
    def compare(
        self,
        projection: NavigationSemanticProjection | NavigationSemanticProjectionV2,
        tree: CanonicalTree,
    ) -> NavigationSemanticDraft | NavigationSemanticDraftV2: ...


class NavigationProviderFactory(Protocol):
    def understanding_provider(
        self,
        mode: str,
        trace_sink: ModelTraceSink | None = None,
    ) -> NavigationUnderstandingProvider: ...

    def semantic_provider(
        self,
        mode: str,
        trace_sink: ModelTraceSink | None = None,
    ) -> NavigationSemanticProvider: ...


class OperationExecutor(Protocol):
    def submit(self, function: Callable[[], None]) -> Any: ...


@dataclass(frozen=True, slots=True)
class DefaultNavigationProviderFactory:
    simulator_base_url: str

    def understanding_provider(
        self,
        mode: str,
        trace_sink: ModelTraceSink | None = None,
    ) -> NavigationUnderstandingProvider:
        if mode == "BAILIAN_LIVE":
            return BailianNavigationUnderstandingProvider(
                BailianConfig.from_env(), trace_sink=trace_sink
            )
        if mode == "QWEN_LIVE":
            return InternalQwenNavigationUnderstandingProvider(
                InternalQwenConfig.from_env(), trace_sink=trace_sink
            )
        return LoopbackSimulatorNavigationUnderstandingProvider(
            LoopbackSimulatorConfig(
                api_key=SIMULATOR_BEARER_TOKEN,
                base_url=self.simulator_base_url,
            ),
            trace_sink=trace_sink,
        )

    def semantic_provider(
        self,
        mode: str,
        trace_sink: ModelTraceSink | None = None,
    ) -> NavigationSemanticProvider:
        if mode == "BAILIAN_LIVE":
            return BailianNavigationSemanticProvider(
                BailianConfig.from_env(), trace_sink=trace_sink
            )
        if mode == "QWEN_LIVE":
            return InternalQwenNavigationSemanticProvider(
                InternalQwenConfig.from_env(), trace_sink=trace_sink
            )
        return LoopbackSimulatorNavigationSemanticProvider(
            LoopbackSimulatorConfig(
                api_key=SIMULATOR_BEARER_TOKEN,
                base_url=self.simulator_base_url,
            ),
            trace_sink=trace_sink,
        )


@dataclass(slots=True)
class _CopilotCase:
    case_ref: str
    model_mode: str
    tree: CanonicalTree
    request: IntentRequest
    directory: Path
    started_ms: int
    status: str
    logical_model_calls: int = 0
    initial_interpretation: NavigationInterpretation | None = None
    clarification_answer: NavigationClarificationAnswer | None = None
    clarification_round: NavigationClarificationRound | None = None
    interpretation: NavigationInterpretation | None = None
    candidate_set: NavigationCandidateSet | None = None
    projection: NavigationSemanticProjection | NavigationSemanticProjectionV2 | None = None
    semantic_draft: NavigationSemanticDraft | NavigationSemanticDraftV2 | None = None
    decision: NavigationPolicyDecision | NavigationPolicyDecisionV2 | None = None
    outcome: NavigationOutcome | None = None
    qualification: NavigationShadowQualification | None = None
    degradation_codes: list[str] = field(default_factory=list)
    model_traces: list[ModelTraceAttempt] = field(default_factory=list)


@dataclass(slots=True)
class _Operation:
    operation_ref: str
    case_ref: str
    kind: str
    status: str = "PENDING"
    error_code: str | None = None


@dataclass(slots=True)
class WorkbenchNavigationCopilotService:
    repository: ReadOnlyTreeRepository
    sidecar_root: Path
    provider_factory: NavigationProviderFactory
    diagnostics_enabled: bool = False
    shadow_run_manifest: NavigationShadowRunManifest | None = None
    participant_ref: str | None = None
    semantic_contract_version: str = "v1"
    executor: OperationExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="treeguard-navigation-copilot",
        )
    )
    id_factory: Callable[[], str] = field(
        default_factory=lambda: lambda: secrets.token_hex(10)
    )
    clock_ms: Callable[[], int] = field(
        default_factory=lambda: lambda: int(time.monotonic() * 1_000)
    )
    recorded_at_factory: Callable[[], str] = field(
        default_factory=lambda: lambda: "UNVERIFIED_RUNTIME_TIME"
    )
    _cases: dict[str, _CopilotCase] = field(default_factory=dict, init=False)
    _operations: dict[str, _Operation] = field(default_factory=dict, init=False)
    _completed: list[NavigationShadowObservation] = field(
        default_factory=list, init=False
    )
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.semantic_contract_version not in {"v1", "v2"}:
            raise WorkbenchNavigationCopilotError(
                "COPILOT_SEMANTIC_CONTRACT_INVALID",
                "semantic contract version is unsupported",
            )
        if (
            self.semantic_contract_version == "v2"
            and self.shadow_run_manifest is not None
        ):
            raise WorkbenchNavigationCopilotError(
                "COPILOT_SEMANTIC_V2_SHADOW_FORBIDDEN",
                "semantic v2 is isolated from the production Shadow run",
            )
        if (self.shadow_run_manifest is None) != (self.participant_ref is None):
            raise WorkbenchNavigationCopilotError(
                "COPILOT_SHADOW_RUN_CONFIG_INVALID",
                "Shadow run manifest and participant must be configured together",
            )
        if (
            self.shadow_run_manifest is not None
            and self.participant_ref not in self.shadow_run_manifest.participant_refs
        ):
            raise WorkbenchNavigationCopilotError(
                "COPILOT_SHADOW_PARTICIPANT_INVALID",
                "participant is not registered in the frozen Shadow run",
            )

    def capability_view(self) -> dict[str, Any]:
        return {
            "schema_version": COPILOT_CAPABILITY_VIEW_VERSION,
            "enabled": True,
            "shadow_only": True,
            "max_model_calls": _MAX_LOGICAL_MODEL_CALLS,
            "max_display_candidates": 8,
            "production_write_enabled": False,
        }

    def create_case(
        self,
        *,
        resource_id: str,
        version: str,
        requirement_text: str,
        proposed_parent_ref: str | None,
        node_kind_hint: str,
        value_type_hint: str | None,
        cardinality_hint: str,
        model_mode: str,
        external_data_approved: bool,
    ) -> dict[str, Any]:
        if model_mode not in MODEL_MODES:
            raise WorkbenchNavigationCopilotError(
                "COPILOT_MODEL_MODE_INVALID",
                "unsupported Copilot model mode",
            )
        if (
            self.shadow_run_manifest is not None
            and model_mode != self.shadow_run_manifest.provider_mode
        ):
            raise WorkbenchNavigationCopilotError(
                "COPILOT_SHADOW_PROVIDER_MISMATCH",
                "case provider does not match the frozen Shadow run",
            )
        if model_mode == "BAILIAN_LIVE" and not external_data_approved:
            raise WorkbenchNavigationCopilotError(
                "EXTERNAL_DATA_APPROVAL_REQUIRED",
                "Bailian mode requires explicit approval",
            )
        result = self.repository.fetch_tree(resource_id, version=version)
        if not result.is_valid or result.tree is None:
            raise WorkbenchError(
                "WORKBENCH_TREE_NOT_AVAILABLE",
                "repository did not return a valid canonical tree",
            )
        tree = result.tree
        references = build_tree_reference_index(tree)
        if proposed_parent_ref is not None and (
            proposed_parent_ref not in references.node_id_by_ref
        ):
            raise WorkbenchNavigationCopilotError(
                "COPILOT_CONTEXT_REF_INVALID",
                "selected context is not in the trusted tree",
            )
        request = IntentRequest.from_dict(
            {
                "schema_version": "intent-request.v1",
                "requirement_text": requirement_text,
                "proposed_parent_node_id": (
                    references.node_id_by_ref[proposed_parent_ref]
                    if proposed_parent_ref is not None
                    else None
                ),
                "node_kind_hint": node_kind_hint,
                "value_type_hint": value_type_hint,
                "cardinality_hint": cardinality_hint,
            },
            tree,
        )
        ensure_private_directory(self.sidecar_root)
        case_ref = self._new_ref("NC")
        directory = self.sidecar_root / case_ref
        create_private_directory(directory)
        self._publish(directory, "01-intent-request.json", request.to_dict())
        case = _CopilotCase(
            case_ref=case_ref,
            model_mode=model_mode,
            tree=tree,
            request=request,
            directory=directory,
            started_ms=self.clock_ms(),
            status="UNDERSTANDING_RUNNING",
        )
        with self._lock:
            self._cases[case_ref] = case
        return self._start_operation(
            case_ref,
            kind="COPILOT_UNDERSTANDING",
            work=lambda: self._run_initial_understanding(case_ref),
        )

    def clarify(self, case_ref: str, *, answer_text: str) -> dict[str, Any]:
        with self._lock:
            case = self._require_case(case_ref)
            if (
                case.status != "NEEDS_CLARIFICATION"
                or case.initial_interpretation is None
            ):
                raise WorkbenchNavigationCopilotError(
                    "COPILOT_CASE_STATE_INVALID",
                    "case is not waiting for clarification",
                )
            answer = NavigationClarificationAnswer.create(
                case.initial_interpretation,
                answer_text=answer_text,
                recorded_at=self.recorded_at_factory(),
            )
            self._publish(
                case.directory,
                "03-clarification-answer.json",
                answer.to_dict(),
            )
            case.clarification_answer = answer
            case.status = "CLARIFICATION_RUNNING"
        return self._start_operation(
            case_ref,
            kind="COPILOT_CLARIFICATION",
            work=lambda: self._run_clarification(case_ref),
        )

    def complete(
        self,
        case_ref: str,
        *,
        action: str,
        selected_candidate_ref: str | None,
        selected_node_ref: str | None,
        rejection_disposition: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            case = self._require_case(case_ref)
            if (
                case.status != "AWAITING_OUTCOME"
                or case.decision is None
                or case.candidate_set is None
            ):
                raise WorkbenchNavigationCopilotError(
                    "COPILOT_CASE_STATE_INVALID",
                    "case is not waiting for a final outcome",
                )
            references = build_tree_reference_index(case.tree)
            selected_node_id = None
            if selected_node_ref is not None:
                selected_node_id = references.node_id_by_ref.get(selected_node_ref)
                if selected_node_id is None:
                    raise WorkbenchNavigationCopilotError(
                        "COPILOT_OUTCOME_NODE_REF_INVALID",
                        "selected node reference is not in the trusted snapshot",
                    )
            outcome = build_navigation_outcome(
                case.decision,
                case.candidate_set,
                case.tree,
                action=action,
                selected_candidate_ref=selected_candidate_ref,
                selected_node_id=selected_node_id,
                duration_ms=max(0, self.clock_ms() - case.started_ms),
            )
            qualification = None
            if self.shadow_run_manifest is not None:
                try:
                    qualification = build_shadow_qualification(
                        self.shadow_run_manifest,
                        self.participant_ref or "",
                        case.decision,
                        outcome,
                        rejection_disposition=rejection_disposition,
                        clarification_used=case.clarification_answer is not None,
                        model_degraded=bool(case.degradation_codes),
                    )
                except NavigationShadowRunError as exc:
                    raise WorkbenchNavigationCopilotError(
                        exc.code,
                        "Shadow qualification rejected the final outcome",
                    ) from None
            self._publish(case.directory, "09-outcome.json", outcome.to_dict())
            if qualification is not None:
                self._publish(
                    case.directory,
                    "10-shadow-qualification.json",
                    qualification.to_dict(),
                )
            case.outcome = outcome
            case.qualification = qualification
            case.status = "COMPLETED"
            self._completed.append(
                NavigationShadowObservation(
                    decision=case.decision,
                    outcome=outcome,
                    clarification_used=case.clarification_answer is not None,
                    model_degraded=bool(case.degradation_codes),
                )
            )
        return self.case_view(case_ref)

    def case_view(self, case_ref: str) -> dict[str, Any]:
        with self._lock:
            case = self._require_case(case_ref)
            references = build_tree_reference_index(case.tree)
            assessment_by_ref = {
                item.candidate_ref: item
                for item in (
                    case.semantic_draft.candidate_assessments
                    if case.semantic_draft is not None
                    else ()
                )
            }
            candidate_items = []
            if case.candidate_set is not None:
                node_by_id = {node.node_id: node for node in case.tree.nodes}
                for index, candidate in enumerate(
                    case.candidate_set.candidates[:8], start=1
                ):
                    node = node_by_id[candidate.node_id]
                    contract = node.value_contract
                    candidate_ref = f"C{index:03d}"
                    assessment = assessment_by_ref.get(candidate_ref)
                    candidate_items.append(
                        {
                            "candidate_ref": candidate_ref,
                            "rank": index,
                            "node_ref": references.ref_by_node_id[node.node_id],
                            "name": node.name,
                            "label": node.label,
                            "kind": node.kind,
                            "value_type": (
                                contract.value_type
                                if contract is not None
                                else None
                            ),
                            "cardinality": (
                                contract.cardinality
                                if contract is not None
                                else None
                            ),
                            "path_names": _candidate_path_names(
                                case.tree, node.node_id
                            ),
                            "parent_relation": candidate.score.parent_relation,
                            "relation": (
                                assessment.relation
                                if assessment is not None
                                else None
                            ),
                            "reason": (
                                assessment.reason
                                if assessment is not None
                                else None
                            ),
                        }
                    )
            interpretation = case.interpretation or case.initial_interpretation
            structural = (
                interpretation.structural_intent
                if interpretation is not None
                else None
            )
            navigation_target_ref = None
            if case.outcome is not None and case.outcome.selected_node_id is not None:
                navigation_target_ref = references.ref_by_node_id[
                    case.outcome.selected_node_id
                ]
            return {
                "schema_version": COPILOT_CASE_VIEW_VERSION,
                "case_ref": case.case_ref,
                "status": case.status,
                "model_mode": case.model_mode,
                "model_call_count": case.logical_model_calls,
                "interpretation": (
                    {
                        "status": interpretation.status,
                        "node_kind": (
                            structural.node_kind if structural is not None else case.request.node_kind_hint
                        ),
                        "value_type": (
                            structural.value_type if structural is not None else case.request.value_type_hint
                        ),
                        "cardinality": (
                            structural.cardinality if structural is not None else case.request.cardinality_hint
                        ),
                        "clarification_question": (
                            structural.clarification_question
                            if structural is not None
                            else None
                        ),
                    }
                    if interpretation is not None
                    else None
                ),
                "degradation_codes": list(case.degradation_codes),
                "candidate_status": (
                    case.decision.status if case.decision is not None else None
                ),
                "highlighted_candidate_ref": (
                    case.decision.highlighted_candidate_ref
                    if case.decision is not None
                    else None
                ),
                "candidates": candidate_items,
                "outcome": (
                    {
                        "action": case.outcome.action,
                        "candidate_miss": case.outcome.candidate_miss,
                        "user_corrected": case.outcome.user_corrected,
                        "record_semantics": "OPERATIONAL_FEEDBACK_ONLY",
                        "semantic_approval": False,
                        "gold_eligible": False,
                        "patch_eligible": False,
                    }
                    if case.outcome is not None
                    else None
                ),
                "navigation_target_ref": navigation_target_ref,
            }

    def operation_view(self, operation_ref: str) -> dict[str, Any]:
        with self._lock:
            operation = self._operations.get(operation_ref)
            if operation is None:
                raise WorkbenchNavigationCopilotError(
                    "COPILOT_OPERATION_NOT_FOUND",
                    "operation reference is unknown",
                )
            case = self._require_case(operation.case_ref)
            return {
                "schema_version": COPILOT_OPERATION_VIEW_VERSION,
                "operation_ref": operation.operation_ref,
                "case_ref": operation.case_ref,
                "kind": operation.kind,
                "status": operation.status,
                "error_code": operation.error_code,
                "case_status": case.status,
            }

    def model_trace_view(self, case_ref: str) -> dict[str, Any]:
        if not self.diagnostics_enabled:
            raise WorkbenchNavigationCopilotError(
                "WORKBENCH_DIAGNOSTICS_DISABLED",
                "model diagnostics are disabled",
            )
        with self._lock:
            case = self._require_case(case_ref)
            return {
                "schema_version": COPILOT_MODEL_TRACE_VIEW_VERSION,
                "case_ref": case.case_ref,
                "model_mode": case.model_mode,
                "thinking_status": "DISABLED",
                "items": [item.to_dict() for item in case.model_traces],
            }

    def aggregate_view(self) -> dict[str, Any]:
        with self._lock:
            return navigation_shadow_aggregate(tuple(self._completed))

    def _run_initial_understanding(self, case_ref: str) -> None:
        with self._lock:
            case = self._require_case(case_ref)
            self._consume_model_call(case)
            request, tree, mode = case.request, case.tree, case.model_mode
        try:
            understanding = self.provider_factory.understanding_provider(
                mode, self._trace_sink(case_ref)
            ).understand(request, tree)
            interpretation = NavigationInterpretation.valid(
                understanding, request, tree
            )
        except BailianProviderError as exc:
            interpretation = NavigationInterpretation.degraded(
                request, tree, degradation_code=exc.code
            )
            with self._lock:
                self._require_case(case_ref).degradation_codes.append(exc.code)
        with self._lock:
            case = self._require_case(case_ref)
            self._publish(
                case.directory,
                "02-interpretation.json",
                interpretation.to_dict(),
            )
            case.initial_interpretation = interpretation
            case.interpretation = interpretation
            if interpretation.needs_clarification:
                case.status = "NEEDS_CLARIFICATION"
                return
        self._continue_after_interpretation(case_ref, skip_semantic=False)

    def _run_clarification(self, case_ref: str) -> None:
        with self._lock:
            case = self._require_case(case_ref)
            assert case.initial_interpretation is not None
            assert case.clarification_answer is not None
            initial = case.initial_interpretation
            answer = case.clarification_answer
            question = initial.structural_intent.clarification_question
            assert question is not None
            self._consume_model_call(case)
            request, tree, mode = case.request, case.tree, case.model_mode
        try:
            understanding = self.provider_factory.understanding_provider(
                mode, self._trace_sink(case_ref)
            ).understand(
                request,
                tree,
                clarification_question=question,
                clarification_answer=answer.answer_text,
            )
            revised = NavigationInterpretation.valid(
                understanding, request, tree
            )
        except BailianProviderError as exc:
            revised = NavigationInterpretation.degraded(
                request, tree, degradation_code=exc.code
            )
            with self._lock:
                self._require_case(case_ref).degradation_codes.append(exc.code)
        round_artifact = NavigationClarificationRound.create(
            initial, answer, revised
        )
        with self._lock:
            case = self._require_case(case_ref)
            self._publish(
                case.directory,
                "04-clarification-round.json",
                round_artifact.to_dict(),
            )
            case.clarification_round = round_artifact
            case.interpretation = revised
            if revised.needs_clarification:
                case.status = "CLARIFICATION_LIMIT_REACHED"
                return
        self._continue_after_interpretation(case_ref, skip_semantic=True)

    def _continue_after_interpretation(
        self,
        case_ref: str,
        *,
        skip_semantic: bool,
    ) -> None:
        with self._lock:
            case = self._require_case(case_ref)
            assert case.interpretation is not None
            request, interpretation, tree = (
                case.request,
                case.interpretation,
                case.tree,
            )
        candidate_set = build_navigation_candidate_set(
            request, interpretation, tree
        )
        projection = None
        if candidate_set.status == "CANDIDATES_READY":
            projection = (
                build_navigation_semantic_projection_v2(
                    request, interpretation, candidate_set, tree
                )
                if self.semantic_contract_version == "v2"
                else build_navigation_semantic_projection(
                    request, interpretation, candidate_set, tree
                )
            )
        semantic_draft = None
        semantic_status = "NOT_APPLICABLE"
        if candidate_set.status == "CANDIDATES_READY" and skip_semantic:
            semantic_status = "SKIPPED_CLARIFICATION_PATH"
        elif candidate_set.status == "CANDIDATES_READY":
            with self._lock:
                case = self._require_case(case_ref)
                self._consume_model_call(case)
                mode = case.model_mode
            assert projection is not None
            try:
                semantic_draft = self.provider_factory.semantic_provider(
                    mode, self._trace_sink(case_ref)
                ).compare(projection, tree)
                semantic_status = "SUCCEEDED"
            except BailianProviderError as exc:
                semantic_status = "DEGRADED"
                with self._lock:
                    self._require_case(case_ref).degradation_codes.append(exc.code)
        decision = (
            apply_navigation_policy_v2(
                interpretation,
                candidate_set,
                projection,
                semantic_draft,
                semantic_status=semantic_status,
            )
            if self.semantic_contract_version == "v2"
            else apply_navigation_policy(
                interpretation,
                candidate_set,
                projection,
                semantic_draft,
                semantic_status=semantic_status,
            )
        )
        with self._lock:
            case = self._require_case(case_ref)
            self._publish(
                case.directory,
                "05-candidate-set.json",
                candidate_set.to_dict(),
            )
            if projection is not None:
                self._publish(
                    case.directory,
                    "06-semantic-projection.json",
                    projection.to_dict(),
                )
            if semantic_draft is not None:
                self._publish(
                    case.directory,
                    "07-semantic-draft.json",
                    semantic_draft.to_dict(),
                )
            self._publish(
                case.directory,
                "08-policy-decision.json",
                decision.to_dict(),
            )
            case.candidate_set = candidate_set
            case.projection = projection
            case.semantic_draft = semantic_draft
            case.decision = decision
            case.status = "AWAITING_OUTCOME"

    def _consume_model_call(self, case: _CopilotCase) -> None:
        if case.logical_model_calls >= _MAX_LOGICAL_MODEL_CALLS:
            raise WorkbenchNavigationCopilotError(
                "COPILOT_MODEL_CALL_BUDGET_EXHAUSTED",
                "case exhausted its model call budget",
            )
        case.logical_model_calls += 1

    def _start_operation(
        self,
        case_ref: str,
        *,
        kind: str,
        work: Callable[[], None],
    ) -> dict[str, Any]:
        operation = _Operation(
            operation_ref=self._new_ref("NCOP"),
            case_ref=case_ref,
            kind=kind,
        )
        with self._lock:
            self._operations[operation.operation_ref] = operation

        def execute() -> None:
            with self._lock:
                operation.status = "RUNNING"
            try:
                work()
            except Exception as exc:
                with self._lock:
                    operation.status = "FAILED"
                    operation.error_code = _operation_error_code(exc)
                    case = self._cases.get(case_ref)
                    if case is not None:
                        case.status = "FAILED"
                return
            with self._lock:
                operation.status = "SUCCEEDED"

        self.executor.submit(execute)
        return self.operation_view(operation.operation_ref)

    def _new_ref(self, prefix: str) -> str:
        for _ in range(8):
            reference = f"{prefix}_{self.id_factory()}"
            with self._lock:
                if (
                    reference not in self._cases
                    and reference not in self._operations
                ):
                    return reference
        raise WorkbenchNavigationCopilotError(
            "COPILOT_REFERENCE_GENERATION_FAILED",
            "could not allocate a unique runtime reference",
        )

    def _trace_sink(self, case_ref: str) -> ModelTraceSink | None:
        if not self.diagnostics_enabled:
            return None

        def append(trace: ModelTraceAttempt) -> None:
            with self._lock:
                case = self._require_case(case_ref)
                if len(case.model_traces) < _MAX_MODEL_TRACE_ATTEMPTS:
                    case.model_traces.append(trace)

        return append

    def _require_case(self, case_ref: str) -> _CopilotCase:
        case = self._cases.get(case_ref)
        if case is None:
            raise WorkbenchNavigationCopilotError(
                "COPILOT_CASE_NOT_FOUND",
                "case reference is unknown",
            )
        return case

    @staticmethod
    def _publish(directory: Path, name: str, payload: Any) -> None:
        if not write_private_json(directory / name, payload):
            raise WorkbenchNavigationCopilotError(
                "WORKBENCH_SIDECAR_WRITE_FAILED",
                "private sidecar artifact could not be published",
            )


def navigation_copilot_enabled_from_env() -> bool:
    value = os.environ.get("TREEGUARD_WORKBENCH_NAVIGATION_COPILOT")
    if value in {None, "", "0"}:
        return False
    if value == "1":
        return True
    raise WorkbenchNavigationCopilotError(
        "COPILOT_FEATURE_CONFIG_INVALID",
        "navigation Copilot feature flag must be zero or one",
    )


def shadow_run_binding_from_env(
) -> tuple[NavigationShadowRunManifest | None, str | None]:
    manifest_path = os.environ.get(
        "TREEGUARD_WORKBENCH_NAVIGATION_COPILOT_RUN_MANIFEST"
    )
    participant_ref = os.environ.get(
        "TREEGUARD_WORKBENCH_NAVIGATION_COPILOT_PARTICIPANT_REF"
    )
    build_commit = os.environ.get("TREEGUARD_WORKBENCH_BUILD_COMMIT")
    if manifest_path is None and participant_ref is None:
        return None, None
    if not manifest_path or not participant_ref or not build_commit:
        raise WorkbenchNavigationCopilotError(
            "COPILOT_SHADOW_RUN_CONFIG_INVALID",
            "Shadow run configuration is incomplete",
        )
    path = Path(manifest_path)
    if not path.is_absolute():
        raise WorkbenchNavigationCopilotError(
            "COPILOT_SHADOW_RUN_CONFIG_INVALID",
            "Shadow run manifest path must be absolute",
        )
    try:
        validate_private_directory(path.parent)
        manifest = NavigationShadowRunManifest.from_dict(
            read_private_json(path, max_bytes=64 * 1024)
        )
    except (
        OSError,
        UnicodeError,
        NavigationShadowRunError,
        WorkbenchSidecarError,
    ):
        raise WorkbenchNavigationCopilotError(
            "COPILOT_SHADOW_RUN_CONFIG_INVALID",
            "Shadow run manifest could not be verified",
        ) from None
    if manifest.contract_commit != build_commit:
        raise WorkbenchNavigationCopilotError(
            "COPILOT_SHADOW_BUILD_MISMATCH",
            "running build does not match the frozen Shadow run",
        )
    if participant_ref not in manifest.participant_refs:
        raise WorkbenchNavigationCopilotError(
            "COPILOT_SHADOW_PARTICIPANT_INVALID",
            "participant is not registered in the frozen Shadow run",
        )
    return manifest, participant_ref


def _operation_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    if isinstance(exc, (TypeError, ValueError)):
        return "COPILOT_INPUT_INVALID"
    return "COPILOT_OPERATION_FAILED"


def _candidate_path_names(tree: CanonicalTree, node_id: str) -> list[str]:
    node_by_id = {node.node_id: node for node in tree.nodes}
    names = []
    visited = set()
    cursor: str | None = node_id
    while cursor is not None:
        node = node_by_id.get(cursor)
        if node is None or cursor in visited:
            raise WorkbenchNavigationCopilotError(
                "WORKBENCH_TREE_RELATION_INVALID",
                "candidate path could not be projected",
            )
        visited.add(cursor)
        names.append(node.name)
        cursor = node.parent_node_id
    names.reverse()
    return names


__all__ = [
    "COPILOT_CAPABILITY_VIEW_VERSION",
    "COPILOT_CASE_VIEW_VERSION",
    "DefaultNavigationProviderFactory",
    "WorkbenchNavigationCopilotError",
    "WorkbenchNavigationCopilotService",
    "navigation_copilot_enabled_from_env",
    "shadow_run_binding_from_env",
]
