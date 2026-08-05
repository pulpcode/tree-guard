"""Loopback-only FastAPI boundary for the TreeGuard workbench."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Body, FastAPI, Path as APIPath, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from treeguard.change_intent import IntentValidationError
from treeguard.fire_validation_dataset import (
    FictionalFireValidationDataset,
)
from treeguard.internal_repository import (
    InternalRepositoryClient,
    InternalRepositoryConfig,
)
from treeguard.qinglan_validation_dataset import (
    FictionalQinglanRepositoryOverlay,
    FictionalQinglanSemanticValidationDataset,
    FictionalQinglanValidationDataset,
)
from treeguard.repository_client import (
    ProvisionalRepositoryClient,
    RepositoryClientConfig,
    RepositoryClientError,
)
from treeguard.workbench import (
    WORKBENCH_API_VERSION,
    WorkbenchError,
    WorkbenchService,
)
from treeguard.workbench_governance import (
    DefaultProviderFactory,
    WorkbenchGovernanceError,
    WorkbenchGovernanceService,
    default_sidecar_root,
    model_diagnostics_enabled_from_env,
)
from treeguard.navigation_copilot import NavigationCopilotError
from treeguard.workbench_navigation_copilot import (
    DefaultNavigationProviderFactory,
    WorkbenchNavigationCopilotError,
    WorkbenchNavigationCopilotService,
    navigation_copilot_enabled_from_env,
    shadow_run_binding_from_env,
)
from treeguard.workbench_sidecar import WorkbenchSidecarError
from treeguard.workbench_validation import (
    ValidationWorkbenchError,
    ValidationWorkbenchService,
)


DEFAULT_REPOSITORY_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_SIMULATOR_MODEL_BASE_URL = "http://127.0.0.1:8765/v1"
ERROR_SCHEMA_VERSION = "workbench-error.v1"
_GENERIC_ERROR_MESSAGE = "Request could not be completed."


class CategoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: str
    parent_id: str | None
    name: str
    order: int


class CategoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    items: list[CategoryItem]


class ResourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    category_id: str
    name: str
    head_version: str


class ResourceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    items: list[ResourceItem]


class VersionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int
    version: str
    description: str | None
    is_head: bool


class VersionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    items: list[VersionItem]


class TreeViewNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    parent_ref: str | None
    child_refs: list[str]
    name: str
    label: str
    kind: str
    value_type: str | None
    cardinality: str | None
    order: int | None
    breadcrumb: list[str]


class TreeViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tree_version: str
    node_count: int
    root_refs: list[str]
    nodes: list[TreeViewNode]


class GovernanceCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=256)
    requirement_text: str = Field(min_length=1, max_length=8_000)
    proposed_parent_ref: str | None = Field(
        default=None,
        pattern=r"^N[0-9]{6}$",
    )
    node_kind_hint: Literal["CONCEPT", "PROPERTY", "UNKNOWN"] = "UNKNOWN"
    value_type_hint: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    cardinality_hint: Literal["SINGLE", "MULTIPLE", "UNKNOWN"] = "UNKNOWN"
    model_mode: Literal[
        "SIMULATOR_LIVE",
        "BAILIAN_LIVE",
        "QWEN_LIVE",
    ] = "SIMULATOR_LIVE"
    external_data_approved: bool = False


class GovernanceClarificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_text: str = Field(min_length=1, max_length=8_000)


class GovernanceReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["CONFIRM", "REJECT"]


class GovernanceRecommendationReviewInput(GovernanceReviewInput):
    reviewer_reasoning: str | None = Field(
        default=None,
        min_length=1,
        max_length=8_000,
    )


class GovernanceOperationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    operation_ref: str
    case_ref: str
    kind: str
    status: str
    error_code: str | None
    case_status: str


class NavigationCopilotCapabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["navigation-copilot-capability.v1"]
    enabled: bool
    shadow_only: Literal[True]
    max_model_calls: Literal[2]
    max_display_candidates: Literal[8]
    production_write_enabled: Literal[False]


class NavigationCopilotCaseCreate(GovernanceCaseCreate):
    pass


class NavigationCopilotClarificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_text: str = Field(min_length=1, max_length=8_000)


class NavigationCopilotOutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "SELECT_CANDIDATE",
        "SELECT_OUTSIDE_CANDIDATE",
        "REJECT_ALL",
        "EXIT",
    ]
    selected_candidate_ref: str | None = Field(
        default=None,
        pattern=r"^C[0-9]{3}$",
    )
    selected_node_ref: str | None = Field(
        default=None,
        pattern=r"^N[0-9]{6}$",
    )
    rejection_disposition: Literal[
        "PRESENT_NOT_FOUND",
        "ABSENT",
        "UNKNOWN",
    ] | None = None


class NavigationCopilotInterpretationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["MODEL_VALID", "MODEL_DEGRADED"]
    node_kind: Literal["CONCEPT", "PROPERTY", "UNKNOWN"]
    value_type: str | None
    cardinality: Literal["SINGLE", "MULTIPLE", "UNKNOWN"]
    clarification_question: str | None


class NavigationCopilotCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ref: str
    rank: int = Field(ge=1, le=8)
    node_ref: str
    name: str
    label: str
    kind: Literal["CONCEPT", "PROPERTY"]
    value_type: str | None
    cardinality: Literal["SINGLE", "MULTIPLE"] | None
    path_names: list[str]
    parent_relation: str
    relation: str | None
    reason: str | None


class NavigationCopilotOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    candidate_miss: bool
    user_corrected: bool
    record_semantics: Literal["OPERATIONAL_FEEDBACK_ONLY"]
    semantic_approval: Literal[False]
    gold_eligible: Literal[False]
    patch_eligible: Literal[False]


class NavigationCopilotCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["navigation-copilot-case-view.v1"]
    case_ref: str
    status: str
    model_mode: Literal[
        "SIMULATOR_LIVE",
        "BAILIAN_LIVE",
        "QWEN_LIVE",
    ]
    model_call_count: int = Field(ge=0, le=2)
    interpretation: NavigationCopilotInterpretationView | None
    degradation_codes: list[str]
    candidate_status: Literal[
        "CANDIDATES_AVAILABLE",
        "AMBIGUOUS",
        "NONE",
        "NEED_EVIDENCE",
    ] | None
    highlighted_candidate_ref: str | None
    candidates: list[NavigationCopilotCandidateView] = Field(max_length=8)
    outcome: NavigationCopilotOutcomeView | None
    navigation_target_ref: str | None


class NavigationCopilotAggregateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_version: Literal["navigation-copilot-shadow-aggregate.v1"]
    valid: Literal[True]
    case_count: int = Field(ge=0)
    completed_navigation_count: int = Field(ge=0)
    top8_direct_selection_count: int = Field(ge=0)
    candidate_correction_count: int = Field(ge=0)
    confident_case_count: int = Field(ge=0)
    confident_error_count: int = Field(ge=0)
    clarification_case_count: int = Field(ge=0)
    degraded_case_count: int = Field(ge=0)
    evidence_covered_case_count: int = Field(ge=0)
    median_completion_ms: int | None = Field(default=None, ge=0)
    semantic_approval: Literal[False]
    gold_eligible: Literal[False]
    patch_eligible: Literal[False]


class GovernanceIntentContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None
    role: str | None
    scenario: str | None
    lifecycle: str | None
    ownership: str
    node_kind: str
    value_type: str | None
    cardinality: str
    confirmed_facts: list[str]
    assumptions: list[str]
    evidence_gaps: list[str]
    clarification_question: str | None


class GovernanceIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: str
    content: GovernanceIntentContent


class GovernanceCandidateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ref: str
    rank: int
    kind: str
    label: str
    name: str
    path_labels: list[str]
    path_names: list[str]
    value_type: str | None
    cardinality: str | None
    parent_relation: str


class GovernanceCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    items: list[GovernanceCandidateItem]


class GovernanceCandidateAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ref: str
    relation: str
    reason: str


class GovernanceRecommendationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    candidate_assessments: list[GovernanceCandidateAssessment]
    recommended_action: str
    selected_candidate_ref: str | None
    rationale: str
    uncertainties: list[str]
    evidence_gaps: list[str]
    clarification_question: str | None


class GovernanceRecordView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_version: str
    valid: bool
    record_semantics: str
    status: str
    semantic_approval: bool
    patch_eligible: bool
    gold_eligible: bool


class GovernanceCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    case_ref: str
    status: str
    model_mode: str
    intent: GovernanceIntentView | None
    candidates: GovernanceCandidateView | None
    recommendation: GovernanceRecommendationView | None
    record: GovernanceRecordView | None


class GovernanceModelTraceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user"]
    content: str = Field(max_length=64_000)
    content_truncated: bool


class GovernanceModelTraceUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class GovernanceModelTraceAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal[
        "INTENT_DRAFT",
        "INTENT_CLARIFICATION",
        "SEMANTIC_RECOMMENDATION",
        "CHANGE_UNDERSTANDING",
        "CHANGE_UNDERSTANDING_CLARIFICATION",
        "SEMANTIC_RELATION",
    ]
    attempt: int = Field(ge=1, le=2)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=256)
    thinking_status: Literal["DISABLED"]
    request_messages: list[GovernanceModelTraceMessage] = Field(
        min_length=1,
        max_length=2,
    )
    response_content: str | None = Field(default=None, max_length=64_000)
    response_content_truncated: bool
    validation_status: Literal["PASSED", "FAILED"]
    validation_error_code: str | None
    usage: GovernanceModelTraceUsage | None


class GovernanceModelTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workbench-model-trace-view.v1"]
    case_ref: str
    model_mode: Literal[
        "SIMULATOR_LIVE",
        "BAILIAN_LIVE",
        "QWEN_LIVE",
    ]
    thinking_status: Literal["DISABLED"]
    items: list[GovernanceModelTraceAttempt] = Field(max_length=8)


class ValidationVariantItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_ref: str
    category_id: str
    resource_id: str
    version: str
    benchmark_role: str
    node_count: int = Field(ge=1)
    scenario_count: int = Field(ge=1)


class ValidationDatasetItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_ref: str
    title: str
    fictional: Literal[True]
    gold_eligible: Literal[False]
    limitations: list[str] = Field(min_length=1, max_length=32)
    variants: list[ValidationVariantItem] = Field(
        min_length=1,
        max_length=32,
    )


class ValidationDatasetCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["validation-dataset-catalog.v1"]
    items: list[ValidationDatasetItem] = Field(
        min_length=1,
        max_length=32,
    )


class ValidationScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_text: str
    proposed_parent_ref: str | None
    node_kind_hint: str
    value_type_hint: str | None
    cardinality_hint: str


class ValidationExpectedView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_review_status: str
    candidate_status: str | None
    record_status: str | None
    semantic_approval: Literal[False] | None
    gold_eligible: Literal[False] | None
    patch_eligible: Literal[False] | None


class ValidationScenarioItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_ref: str
    purpose: str
    flow: str
    request: ValidationScenarioRequest
    expected: ValidationExpectedView


class ValidationScenariosResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["validation-scenarios.v1"]
    dataset_ref: str
    variant_ref: str
    benchmark_role: str
    fictional: Literal[True]
    gold_eligible: Literal[False]
    items: list[ValidationScenarioItem] = Field(max_length=128)


class ValidationRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    variant_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    scenario_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    model_mode: Literal[
        "SIMULATOR_LIVE",
        "BAILIAN_LIVE",
        "QWEN_LIVE",
    ]
    external_data_approved: bool = False


class ValidationComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    expected: str | bool
    actual: str | bool | None
    status: Literal["PENDING", "MATCH", "MISMATCH", "NOT_OBSERVED"]


class ValidationComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["validation-comparison.v1"]
    case_ref: str
    dataset_ref: str
    variant_ref: str
    scenario_ref: str
    case_status: str
    status: Literal["IN_PROGRESS", "MATCH", "MISMATCH", "RUN_FAILED"]
    fictional: Literal[True]
    gold_eligible: Literal[False]
    items: list[ValidationComparisonItem]
    limitations: list[str] = Field(min_length=4, max_length=35)


def _services_from_environment() -> tuple[
    WorkbenchService,
    WorkbenchGovernanceService,
    ValidationWorkbenchService,
]:
    repository_mode = os.environ.get(
        "TREEGUARD_WORKBENCH_REPOSITORY_MODE",
        "SIMULATOR",
    )
    base_url = os.environ.get(
        "TREEGUARD_WORKBENCH_REPOSITORY_URL",
        DEFAULT_REPOSITORY_BASE_URL,
    )
    if repository_mode == "SIMULATOR":
        repository = FictionalQinglanRepositoryOverlay(
            ProvisionalRepositoryClient(
                RepositoryClientConfig(base_url=base_url)
            )
        )
        validation_providers = (
            FictionalFireValidationDataset(),
            FictionalQinglanValidationDataset(),
            FictionalQinglanSemanticValidationDataset(),
        )
    elif repository_mode == "INTERNAL":
        repository = InternalRepositoryClient(
            InternalRepositoryConfig(base_url=base_url)
        )
        validation_providers = (FictionalFireValidationDataset(),)
    else:
        raise RepositoryClientError(
            "WORKBENCH_REPOSITORY_MODE_INVALID",
            "unsupported workbench repository mode",
        )
    workbench = WorkbenchService(repository=repository)
    governance = WorkbenchGovernanceService(
        repository=repository,
        sidecar_root=default_sidecar_root(),
        provider_factory=DefaultProviderFactory(
            simulator_base_url=os.environ.get(
                "TREEGUARD_WORKBENCH_SIMULATOR_MODEL_URL",
                DEFAULT_SIMULATOR_MODEL_BASE_URL,
            )
        ),
        diagnostics_enabled=model_diagnostics_enabled_from_env(),
    )
    validation = ValidationWorkbenchService(
        repository=repository,
        governance=governance,
        providers=validation_providers,
    )
    return workbench, governance, validation


def _navigation_copilot_from_environment(
    repository: Any,
) -> WorkbenchNavigationCopilotService | None:
    if navigation_copilot_enabled_from_env():
        shadow_run_manifest, participant_ref = shadow_run_binding_from_env()
        return WorkbenchNavigationCopilotService(
            repository=repository,
            sidecar_root=default_sidecar_root(),
            provider_factory=DefaultNavigationProviderFactory(
                simulator_base_url=os.environ.get(
                    "TREEGUARD_WORKBENCH_SIMULATOR_MODEL_URL",
                    DEFAULT_SIMULATOR_MODEL_BASE_URL,
                )
            ),
            diagnostics_enabled=model_diagnostics_enabled_from_env(),
            shadow_run_manifest=shadow_run_manifest,
            participant_ref=participant_ref,
        )
    return None


def create_app(
    service: WorkbenchService | None = None,
    governance_service: WorkbenchGovernanceService | None = None,
    validation_service: ValidationWorkbenchService | None = None,
    navigation_copilot_service: WorkbenchNavigationCopilotService | None = None,
) -> FastAPI:
    """Create an app with an injectable read-only application service."""

    resolved_service = service
    resolved_governance_service = governance_service
    resolved_validation_service = validation_service
    resolved_navigation_copilot_service = navigation_copilot_service

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if resolved_service is None:
            workbench, governance, validation = _services_from_environment()
            application.state.workbench_service = workbench
            application.state.governance_service = governance
            application.state.validation_service = validation
            application.state.navigation_copilot_service = (
                _navigation_copilot_from_environment(workbench.repository)
            )
        else:
            application.state.workbench_service = resolved_service
            application.state.governance_service = (
                resolved_governance_service
            )
            application.state.validation_service = (
                resolved_validation_service
            )
            application.state.navigation_copilot_service = (
                resolved_navigation_copilot_service
            )
        yield

    application = FastAPI(
        title="TreeGuard Workbench API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def harden_response(
        request: Request,
        call_next: Any,
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.exception_handler(RepositoryClientError)
    async def repository_error_handler(
        request: Request,
        exc: RepositoryClientError,
    ) -> JSONResponse:
        return _error_response(502, exc.code)

    @application.exception_handler(WorkbenchError)
    async def workbench_error_handler(
        request: Request,
        exc: WorkbenchError,
    ) -> JSONResponse:
        return _error_response(409, exc.code)

    @application.exception_handler(WorkbenchGovernanceError)
    async def governance_error_handler(
        request: Request,
        exc: WorkbenchGovernanceError,
    ) -> JSONResponse:
        if (
            exc.code.endswith("_NOT_FOUND")
            or exc.code == "WORKBENCH_DIAGNOSTICS_DISABLED"
        ):
            status_code = 404
        elif exc.code in {
            "WORKBENCH_CASE_STATE_INVALID",
            "WORKBENCH_SIDECAR_DIRECTORY_UNSAFE",
            "WORKBENCH_SIDECAR_WRITE_FAILED",
        }:
            status_code = 409
        elif exc.code == "WORKBENCH_GOVERNANCE_UNAVAILABLE":
            status_code = 503
        else:
            status_code = 422
        return _error_response(status_code, exc.code)

    @application.exception_handler(WorkbenchNavigationCopilotError)
    async def navigation_copilot_error_handler(
        request: Request,
        exc: WorkbenchNavigationCopilotError,
    ) -> JSONResponse:
        if exc.code.endswith("_NOT_FOUND") or exc.code == "WORKBENCH_DIAGNOSTICS_DISABLED":
            status_code = 404
        elif exc.code in {
            "COPILOT_CASE_STATE_INVALID",
            "WORKBENCH_SIDECAR_DIRECTORY_UNSAFE",
            "WORKBENCH_SIDECAR_WRITE_FAILED",
        }:
            status_code = 409
        elif exc.code == "COPILOT_UNAVAILABLE":
            status_code = 503
        else:
            status_code = 422
        return _error_response(status_code, exc.code)

    @application.exception_handler(WorkbenchSidecarError)
    async def workbench_sidecar_error_handler(
        request: Request,
        exc: WorkbenchSidecarError,
    ) -> JSONResponse:
        return _error_response(409, exc.code)

    @application.exception_handler(NavigationCopilotError)
    async def navigation_copilot_contract_error_handler(
        request: Request,
        exc: NavigationCopilotError,
    ) -> JSONResponse:
        return _error_response(422, exc.code)

    @application.exception_handler(ValidationWorkbenchError)
    async def validation_workbench_error_handler(
        request: Request,
        exc: ValidationWorkbenchError,
    ) -> JSONResponse:
        if exc.code.endswith("_NOT_FOUND"):
            status_code = 404
        elif exc.code == "VALIDATION_UNAVAILABLE":
            status_code = 503
        else:
            status_code = 422
        return _error_response(status_code, exc.code)

    @application.exception_handler(IntentValidationError)
    async def intent_error_handler(
        request: Request,
        exc: IntentValidationError,
    ) -> JSONResponse:
        return _error_response(422, exc.code)

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(422, "WORKBENCH_REQUEST_INVALID")

    @application.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {
            "schema_version": "workbench-health.v1",
            "status": "OK",
            "api_version": WORKBENCH_API_VERSION,
        }

    @application.get(
        "/api/v1/navigation-copilot/capability",
        response_model=NavigationCopilotCapabilityResponse,
    )
    async def navigation_copilot_capability(
        request: Request,
    ) -> dict[str, Any]:
        service = getattr(
            request.app.state,
            "navigation_copilot_service",
            None,
        )
        if service is None:
            return {
                "schema_version": "navigation-copilot-capability.v1",
                "enabled": False,
                "shadow_only": True,
                "max_model_calls": 2,
                "max_display_candidates": 8,
                "production_write_enabled": False,
            }
        return service.capability_view()

    @application.get(
        "/api/v1/categories",
        response_model=CategoryListResponse,
    )
    async def categories(request: Request) -> dict[str, Any]:
        return _service(request).categories()

    @application.get(
        "/api/v1/resources",
        response_model=ResourceListResponse,
    )
    async def resources(
        request: Request,
        category_id: Annotated[str, Query(min_length=1, max_length=256)],
    ) -> dict[str, Any]:
        return _service(request).resources(category_id)

    @application.get(
        "/api/v1/resources/{resource_id}/versions",
        response_model=VersionListResponse,
    )
    async def versions(
        request: Request,
        resource_id: Annotated[
            str,
            APIPath(min_length=1, max_length=256),
        ],
    ) -> dict[str, Any]:
        return _service(request).versions(resource_id)

    @application.get(
        "/api/v1/resources/{resource_id}/tree",
        response_model=TreeViewResponse,
    )
    async def tree_view(
        request: Request,
        resource_id: Annotated[
            str,
            APIPath(min_length=1, max_length=256),
        ],
        version: Annotated[str, Query(min_length=1, max_length=256)],
    ) -> dict[str, Any]:
        return _service(request).tree_view(resource_id, version=version)

    @application.post(
        "/api/v1/governance/cases",
        response_model=GovernanceOperationResponse,
        status_code=202,
    )
    async def create_governance_case(
        request: Request,
        payload: Annotated[GovernanceCaseCreate, Body()],
    ) -> dict[str, Any]:
        return _governance(request).create_case(
            resource_id=payload.resource_id,
            version=payload.version,
            requirement_text=payload.requirement_text,
            proposed_parent_ref=payload.proposed_parent_ref,
            node_kind_hint=payload.node_kind_hint,
            value_type_hint=payload.value_type_hint,
            cardinality_hint=payload.cardinality_hint,
            model_mode=payload.model_mode,
            external_data_approved=payload.external_data_approved,
        )

    @application.post(
        "/api/v1/navigation-copilot/cases",
        response_model=GovernanceOperationResponse,
        status_code=202,
    )
    async def create_navigation_copilot_case(
        request: Request,
        payload: Annotated[NavigationCopilotCaseCreate, Body()],
    ) -> dict[str, Any]:
        return _copilot(request).create_case(
            resource_id=payload.resource_id,
            version=payload.version,
            requirement_text=payload.requirement_text,
            proposed_parent_ref=payload.proposed_parent_ref,
            node_kind_hint=payload.node_kind_hint,
            value_type_hint=payload.value_type_hint,
            cardinality_hint=payload.cardinality_hint,
            model_mode=payload.model_mode,
            external_data_approved=payload.external_data_approved,
        )

    @application.get(
        "/api/v1/navigation-copilot/cases/{case_ref}",
        response_model=NavigationCopilotCaseResponse,
    )
    async def navigation_copilot_case(
        request: Request,
        case_ref: Annotated[str, APIPath(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        return _copilot(request).case_view(case_ref)

    @application.get(
        "/api/v1/navigation-copilot/operations/{operation_ref}",
        response_model=GovernanceOperationResponse,
    )
    async def navigation_copilot_operation(
        request: Request,
        operation_ref: Annotated[str, APIPath(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        return _copilot(request).operation_view(operation_ref)

    @application.post(
        "/api/v1/navigation-copilot/cases/{case_ref}/clarification",
        response_model=GovernanceOperationResponse,
        status_code=202,
    )
    async def clarify_navigation_copilot_case(
        request: Request,
        case_ref: Annotated[str, APIPath(min_length=1, max_length=128)],
        payload: Annotated[NavigationCopilotClarificationInput, Body()],
    ) -> dict[str, Any]:
        return _copilot(request).clarify(
            case_ref,
            answer_text=payload.answer_text,
        )

    @application.post(
        "/api/v1/navigation-copilot/cases/{case_ref}/outcome",
        response_model=NavigationCopilotCaseResponse,
    )
    async def complete_navigation_copilot_case(
        request: Request,
        case_ref: Annotated[str, APIPath(min_length=1, max_length=128)],
        payload: Annotated[NavigationCopilotOutcomeInput, Body()],
    ) -> dict[str, Any]:
        return _copilot(request).complete(
            case_ref,
            action=payload.action,
            selected_candidate_ref=payload.selected_candidate_ref,
            selected_node_ref=payload.selected_node_ref,
            rejection_disposition=payload.rejection_disposition,
        )

    @application.get(
        "/api/v1/navigation-copilot/aggregate",
        response_model=NavigationCopilotAggregateResponse,
    )
    async def navigation_copilot_aggregate(
        request: Request,
    ) -> dict[str, Any]:
        return _copilot(request).aggregate_view()

    @application.get(
        "/api/v1/navigation-copilot/cases/{case_ref}/model-traces",
        response_model=GovernanceModelTraceResponse,
    )
    async def navigation_copilot_model_traces(
        request: Request,
        case_ref: Annotated[str, APIPath(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        return _copilot(request).model_trace_view(case_ref)

    @application.get(
        "/api/v1/governance/cases/{case_ref}",
        response_model=GovernanceCaseResponse,
    )
    async def governance_case(
        request: Request,
        case_ref: Annotated[
            str,
            APIPath(min_length=1, max_length=128),
        ],
    ) -> dict[str, Any]:
        return _governance(request).case_view(case_ref)

    @application.get(
        "/api/v1/governance/cases/{case_ref}/model-traces",
        response_model=GovernanceModelTraceResponse,
    )
    async def governance_model_traces(
        request: Request,
        case_ref: Annotated[
            str,
            APIPath(min_length=1, max_length=128),
        ],
    ) -> dict[str, Any]:
        return _governance(request).model_trace_view(case_ref)

    @application.get(
        "/api/v1/validation/datasets",
        response_model=ValidationDatasetCatalogResponse,
    )
    async def validation_datasets(
        request: Request,
    ) -> dict[str, Any]:
        return _validation(request).catalog()

    @application.get(
        "/api/v1/validation/datasets/{dataset_ref}/scenarios",
        response_model=ValidationScenariosResponse,
    )
    async def validation_scenarios(
        request: Request,
        dataset_ref: Annotated[
            str,
            APIPath(
                min_length=1,
                max_length=128,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
            ),
        ],
        variant_ref: Annotated[
            str,
            Query(
                min_length=1,
                max_length=128,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
            ),
        ],
    ) -> dict[str, Any]:
        return _validation(request).scenarios(dataset_ref, variant_ref)

    @application.post(
        "/api/v1/validation/runs",
        response_model=GovernanceOperationResponse,
        status_code=202,
    )
    async def create_validation_run(
        request: Request,
        payload: Annotated[ValidationRunCreate, Body()],
    ) -> dict[str, Any]:
        return _validation(request).create_run(
            dataset_ref=payload.dataset_ref,
            variant_ref=payload.variant_ref,
            scenario_ref=payload.scenario_ref,
            model_mode=payload.model_mode,
            external_data_approved=payload.external_data_approved,
        )

    @application.get(
        "/api/v1/validation/runs/{case_ref}/comparison",
        response_model=ValidationComparisonResponse,
    )
    async def validation_comparison(
        request: Request,
        case_ref: Annotated[
            str,
            APIPath(min_length=1, max_length=128),
        ],
    ) -> dict[str, Any]:
        return _validation(request).comparison(case_ref)

    @application.get(
        "/api/v1/governance/operations/{operation_ref}",
        response_model=GovernanceOperationResponse,
    )
    async def governance_operation(
        request: Request,
        operation_ref: Annotated[
            str,
            APIPath(min_length=1, max_length=128),
        ],
    ) -> dict[str, Any]:
        return _governance(request).operation_view(operation_ref)

    @application.post(
        "/api/v1/governance/cases/{case_ref}/clarification",
        response_model=GovernanceOperationResponse,
        status_code=202,
    )
    async def clarify_governance_case(
        request: Request,
        case_ref: Annotated[
            str,
            APIPath(min_length=1, max_length=128),
        ],
        payload: Annotated[GovernanceClarificationInput, Body()],
    ) -> dict[str, Any]:
        return _governance(request).clarify(
            case_ref,
            answer_text=payload.answer_text,
        )

    @application.post(
        "/api/v1/governance/cases/{case_ref}/intent-review",
        response_model=GovernanceOperationResponse,
        status_code=202,
    )
    async def review_governance_intent(
        request: Request,
        case_ref: Annotated[
            str,
            APIPath(min_length=1, max_length=128),
        ],
        payload: Annotated[GovernanceReviewInput, Body()],
    ) -> dict[str, Any]:
        return _governance(request).review_intent(
            case_ref,
            decision=payload.decision,
        )

    @application.post(
        "/api/v1/governance/cases/{case_ref}/recommendation-review",
        response_model=GovernanceOperationResponse,
        status_code=202,
    )
    async def review_governance_recommendation(
        request: Request,
        case_ref: Annotated[
            str,
            APIPath(min_length=1, max_length=128),
        ],
        payload: Annotated[GovernanceRecommendationReviewInput, Body()],
    ) -> dict[str, Any]:
        return _governance(request).review_recommendation(
            case_ref,
            decision=payload.decision,
            reviewer_reasoning=payload.reviewer_reasoning,
        )

    if resolved_service is not None:
        application.state.workbench_service = resolved_service
        application.state.governance_service = resolved_governance_service
        application.state.validation_service = resolved_validation_service
        application.state.navigation_copilot_service = (
            resolved_navigation_copilot_service
        )
    return application


def _service(request: Request) -> WorkbenchService:
    return request.app.state.workbench_service


def _governance(request: Request) -> WorkbenchGovernanceService:
    service = request.app.state.governance_service
    if service is None:
        raise WorkbenchGovernanceError(
            "WORKBENCH_GOVERNANCE_UNAVAILABLE",
            "governance service is not configured",
        )
    return service


def _validation(request: Request) -> ValidationWorkbenchService:
    service = request.app.state.validation_service
    if service is None:
        raise ValidationWorkbenchError(
            "VALIDATION_UNAVAILABLE",
            "validation service is not configured",
        )
    return service


def _copilot(request: Request) -> WorkbenchNavigationCopilotService:
    service = getattr(
        request.app.state,
        "navigation_copilot_service",
        None,
    )
    if service is None:
        raise WorkbenchNavigationCopilotError(
            "COPILOT_UNAVAILABLE",
            "navigation Copilot is not enabled",
        )
    return service


def _error_response(status_code: int, error_code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": ERROR_SCHEMA_VERSION,
            "error_code": error_code,
            "message": _GENERIC_ERROR_MESSAGE,
        },
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


app = create_app()


__all__ = ["app", "create_app"]
