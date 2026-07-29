"""Loopback-only FastAPI boundary for the TreeGuard workbench."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, Path as APIPath, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.responses import Response

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


DEFAULT_REPOSITORY_BASE_URL = "http://127.0.0.1:8765"
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


def _service_from_environment() -> WorkbenchService:
    base_url = os.environ.get(
        "TREEGUARD_WORKBENCH_REPOSITORY_URL",
        DEFAULT_REPOSITORY_BASE_URL,
    )
    repository = ProvisionalRepositoryClient(
        RepositoryClientConfig(base_url=base_url)
    )
    return WorkbenchService(repository=repository)


def create_app(service: WorkbenchService | None = None) -> FastAPI:
    """Create an app with an injectable read-only application service."""

    resolved_service = service

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.workbench_service = (
            resolved_service
            if resolved_service is not None
            else _service_from_environment()
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

    if resolved_service is not None:
        application.state.workbench_service = resolved_service
    return application


def _service(request: Request) -> WorkbenchService:
    return request.app.state.workbench_service


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
