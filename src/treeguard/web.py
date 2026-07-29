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
    model_mode: Literal["SIMULATOR_LIVE", "BAILIAN_LIVE"] = "SIMULATOR_LIVE"
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


def _services_from_environment() -> tuple[
    WorkbenchService,
    WorkbenchGovernanceService,
]:
    base_url = os.environ.get(
        "TREEGUARD_WORKBENCH_REPOSITORY_URL",
        DEFAULT_REPOSITORY_BASE_URL,
    )
    repository = ProvisionalRepositoryClient(
        RepositoryClientConfig(base_url=base_url)
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
    )
    return workbench, governance


def create_app(
    service: WorkbenchService | None = None,
    governance_service: WorkbenchGovernanceService | None = None,
) -> FastAPI:
    """Create an app with an injectable read-only application service."""

    resolved_service = service
    resolved_governance_service = governance_service

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if resolved_service is None:
            workbench, governance = _services_from_environment()
            application.state.workbench_service = workbench
            application.state.governance_service = governance
        else:
            application.state.workbench_service = resolved_service
            application.state.governance_service = (
                resolved_governance_service
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
        if exc.code.endswith("_NOT_FOUND"):
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
