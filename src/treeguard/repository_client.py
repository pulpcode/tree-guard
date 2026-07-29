"""Read-only client for the provisional clean-room repository contract."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from treeguard.adapter import TreeFormatError, adapt_tree_document
from treeguard.http_utils import build_isolated_opener
from treeguard.json_utils import StrictJSONError, strict_json_loads
from treeguard.models import ImportResult
from treeguard.simulator import (
    SIMULATOR_BEARER_TOKEN,
    SIMULATOR_CONTRACT_STATUS,
    SIMULATOR_TREE_ID,
)


MAX_REPOSITORY_RESPONSE_BYTES = 64_000_000


class RepositoryClientError(RuntimeError):
    """A provisional repository request or response failed closed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RepositoryClientConfig:
    base_url: str
    token: str = field(default=SIMULATOR_BEARER_TOKEN, repr=False)
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlparse(self.base_url)
        try:
            port = parsed.port
        except ValueError:
            port = None
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username is not None
            or parsed.password is not None
            or port is None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise RepositoryClientError(
                "REPOSITORY_SIMULATOR_BASE_URL_INVALID",
                "repository simulator must use an explicit loopback HTTP port",
            )
        if (
            not isinstance(self.token, str)
            or not self.token
            or len(self.token) > 512
            or not self.token.isascii()
            or any(
                ord(character) < 33 or ord(character) > 126
                for character in self.token
            )
        ):
            raise RepositoryClientError(
                "REPOSITORY_SIMULATOR_TOKEN_INVALID",
                "repository simulator token is invalid",
            )
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 60
        ):
            raise RepositoryClientError(
                "REPOSITORY_SIMULATOR_TIMEOUT_INVALID",
                "repository simulator timeout is invalid",
            )


@dataclass(frozen=True, slots=True)
class CategoryRef:
    category_id: str
    parent_id: str | None
    name: str
    order: int


@dataclass(frozen=True, slots=True)
class ResourceHead:
    resource_id: str
    category_id: str
    name: str
    head_version: str
    head_version_record_id: str


@dataclass(frozen=True, slots=True)
class VersionRef:
    position: int
    version: str
    version_record_id: str
    description: str | None
    is_head: bool


class ProvisionalRepositoryClient:
    """Fetch and strictly validate the four provisional read-only endpoints."""

    def __init__(self, config: RepositoryClientConfig) -> None:
        self.config = config
        self._opener = build_isolated_opener()

    def list_categories(self) -> tuple[CategoryRef, ...]:
        payload = self._get("/provisional/v1/categories")
        data = _response_data(
            payload,
            "provisional-simulator-categories.v1",
        )
        if set(data) != {"items", "total"}:
            raise RepositoryClientError(
                "REPOSITORY_CATEGORY_ENVELOPE_INVALID",
                "repository category response metadata is invalid",
            )
        items = _items(data)
        categories = tuple(_category(item) for item in items)
        if len({item.category_id for item in categories}) != len(categories):
            raise RepositoryClientError(
                "REPOSITORY_CATEGORY_DUPLICATE",
                "repository categories must have unique identifiers",
            )
        seen: set[str] = set()
        sibling_positions: dict[str | None, tuple[int, str]] = {}
        for item in categories:
            if item.parent_id is not None and item.parent_id not in seen:
                raise RepositoryClientError(
                    "REPOSITORY_CATEGORY_ORDER_INVALID",
                    "repository category parents must precede their children",
                )
            position = (item.order, item.category_id)
            if position <= sibling_positions.get(item.parent_id, (-1, "")):
                raise RepositoryClientError(
                    "REPOSITORY_CATEGORY_ORDER_INVALID",
                    "repository category siblings are not in canonical order",
                )
            sibling_positions[item.parent_id] = position
            seen.add(item.category_id)
        return categories

    def list_resources(self, category_id: str) -> tuple[ResourceHead, ...]:
        _identifier(category_id, "category_id")
        payload = self._get(
            "/provisional/v1/resources?"
            + urllib.parse.urlencode({"category_id": category_id})
        )
        data = _response_data(
            payload,
            "provisional-simulator-resources.v1",
        )
        if set(data) != {"items", "total"}:
            raise RepositoryClientError(
                "REPOSITORY_RESOURCE_ENVELOPE_INVALID",
                "repository resource response metadata is invalid",
            )
        resources = tuple(_resource(item) for item in _items(data))
        if tuple(
            sorted(resources, key=lambda item: item.resource_id)
        ) != resources:
            raise RepositoryClientError(
                "REPOSITORY_RESOURCE_ORDER_INVALID",
                "repository resources are not in canonical order",
            )
        return resources

    def list_versions(self, resource_id: str) -> tuple[VersionRef, ...]:
        _identifier(resource_id, "resource_id")
        payload = self._get(
            f"/provisional/v1/resources/"
            f"{urllib.parse.quote(resource_id, safe='')}/versions"
        )
        data = _response_data(
            payload,
            "provisional-simulator-versions.v1",
        )
        if (
            set(data) != {
                "resource_id",
                "ordering",
                "items",
                "total",
            }
            or data["resource_id"] != resource_id
            or data["ordering"] != "OLDEST_FIRST"
        ):
            raise RepositoryClientError(
                "REPOSITORY_VERSION_ENVELOPE_INVALID",
                "repository version response metadata is invalid",
            )
        versions = tuple(_version(item) for item in _items(data))
        if tuple(item.position for item in versions) != tuple(
            range(len(versions))
        ):
            raise RepositoryClientError(
                "REPOSITORY_VERSION_ORDER_INVALID",
                "repository versions must use contiguous explicit positions",
            )
        if sum(item.is_head for item in versions) != 1:
            raise RepositoryClientError(
                "REPOSITORY_VERSION_HEAD_INVALID",
                "repository versions must expose exactly one head",
            )
        return versions

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ) -> ImportResult:
        _identifier(resource_id, "resource_id")
        if (version is None) == (version_record_id is None):
            raise RepositoryClientError(
                "REPOSITORY_TREE_SELECTOR_INVALID",
                "select exactly one tree version or version record",
            )
        query = (
            {"version": _identifier(version, "version")}
            if version is not None
            else {
                "version_record_id": _identifier(
                    version_record_id,
                    "version_record_id",
                )
            }
        )
        payload = self._get(
            f"/provisional/v1/resources/"
            f"{urllib.parse.quote(resource_id, safe='')}/tree?"
            + urllib.parse.urlencode(query)
        )
        if (
            not isinstance(payload, dict)
            or set(payload) != {
                "schema_version",
                "contract_status",
                "status",
                "message",
                "data",
            }
            or payload["schema_version"]
            != "provisional-simulator-tree.v1"
            or payload["contract_status"] != SIMULATOR_CONTRACT_STATUS
            or payload["status"] != 0
            or payload["message"] != "OK"
            or not isinstance(payload["data"], dict)
        ):
            raise RepositoryClientError(
                "REPOSITORY_TREE_RESPONSE_INVALID",
                "repository tree response failed its provisional contract",
            )
        try:
            result = adapt_tree_document(payload)
        except (TreeFormatError, TypeError, ValueError):
            raise RepositoryClientError(
                "REPOSITORY_TREE_FORMAT_INVALID",
                "repository tree could not be adapted",
            ) from None
        if not result.is_valid or result.tree is None:
            raise RepositoryClientError(
                "REPOSITORY_TREE_CONFORMANCE_INVALID",
                "repository tree failed canonical conformance",
            )
        if result.tree.tree_id != SIMULATOR_TREE_ID:
            raise RepositoryClientError(
                "REPOSITORY_TREE_IDENTITY_MISMATCH",
                "repository tree identity is inconsistent",
            )
        if version is not None and result.tree.tree_version != version:
            raise RepositoryClientError(
                "REPOSITORY_TREE_VERSION_MISMATCH",
                "repository returned a different business version",
            )
        if (
            version_record_id is not None
            and result.tree.version_record_id != version_record_id
        ):
            raise RepositoryClientError(
                "REPOSITORY_TREE_RECORD_MISMATCH",
                "repository returned a different version record",
            )
        return result

    def _get(self, path: str) -> Any:
        endpoint = self.config.base_url.rstrip("/") + path
        request = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with self._opener.open(
                request,
                timeout=float(self.config.timeout_seconds),
            ) as response:
                raw = response.read(MAX_REPOSITORY_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise RepositoryClientError(
                f"REPOSITORY_SIMULATOR_HTTP_{exc.code}",
                "repository simulator returned an HTTP error",
            ) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise RepositoryClientError(
                "REPOSITORY_SIMULATOR_CONNECTION_FAILED",
                "repository simulator connection failed",
            ) from None
        if len(raw) > MAX_REPOSITORY_RESPONSE_BYTES:
            raise RepositoryClientError(
                "REPOSITORY_SIMULATOR_RESPONSE_TOO_LARGE",
                "repository simulator response exceeded its size limit",
            )
        try:
            return strict_json_loads(raw)
        except (
            StrictJSONError,
            RecursionError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            raise RepositoryClientError(
                "REPOSITORY_SIMULATOR_RESPONSE_NOT_JSON",
                "repository simulator response was not strict JSON",
            ) from None


def _response_data(payload: Any, schema_version: str) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != {
            "schema_version",
            "contract_status",
            "status",
            "message",
            "data",
        }
        or payload["schema_version"] != schema_version
        or payload["contract_status"] != SIMULATOR_CONTRACT_STATUS
        or payload["status"] != 0
        or payload["message"] != "OK"
        or not isinstance(payload["data"], dict)
    ):
        raise RepositoryClientError(
            "REPOSITORY_RESPONSE_INVALID",
            "repository response failed its provisional contract",
        )
    return payload["data"]


def _items(data: dict[str, Any]) -> list[Any]:
    if (
        "items" not in data
        or "total" not in data
        or not isinstance(data["items"], list)
        or not isinstance(data["total"], int)
        or isinstance(data["total"], bool)
        or data["total"] != len(data["items"])
    ):
        raise RepositoryClientError(
            "REPOSITORY_LIST_INVALID",
            "repository list response is invalid",
        )
    return data["items"]


def _category(payload: Any) -> CategoryRef:
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {"category_id", "parent_id", "name", "order"}
    ):
        raise RepositoryClientError(
            "REPOSITORY_CATEGORY_INVALID",
            "repository category is invalid",
        )
    return CategoryRef(
        category_id=_identifier(payload["category_id"], "category_id"),
        parent_id=(
            None
            if payload["parent_id"] is None
            else _identifier(payload["parent_id"], "parent_id")
        ),
        name=_text(payload["name"], "name"),
        order=_position(payload["order"], "order", minimum=1),
    )


def _resource(payload: Any) -> ResourceHead:
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "resource_id",
            "category_id",
            "name",
            "head_version",
            "head_version_record_id",
        }
    ):
        raise RepositoryClientError(
            "REPOSITORY_RESOURCE_INVALID",
            "repository resource is invalid",
        )
    return ResourceHead(
        resource_id=_identifier(payload["resource_id"], "resource_id"),
        category_id=_identifier(payload["category_id"], "category_id"),
        name=_text(payload["name"], "name"),
        head_version=_identifier(payload["head_version"], "head_version"),
        head_version_record_id=_identifier(
            payload["head_version_record_id"],
            "head_version_record_id",
        ),
    )


def _version(payload: Any) -> VersionRef:
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "position",
            "version",
            "version_record_id",
            "description",
            "is_head",
        }
        or not isinstance(payload["is_head"], bool)
    ):
        raise RepositoryClientError(
            "REPOSITORY_VERSION_INVALID",
            "repository version is invalid",
        )
    description = payload["description"]
    if description is not None:
        description = _text(description, "description")
    return VersionRef(
        position=_position(payload["position"], "position", minimum=0),
        version=_identifier(payload["version"], "version"),
        version_record_id=_identifier(
            payload["version_record_id"],
            "version_record_id",
        ),
        description=description,
        is_head=payload["is_head"],
    )


def _identifier(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(ord(character) < 32 for character in value)
    ):
        raise RepositoryClientError(
            "REPOSITORY_IDENTIFIER_INVALID",
            f"repository {field_name} is invalid",
        )
    return value


def _text(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 1_000
        or any(ord(character) < 32 for character in value)
    ):
        raise RepositoryClientError(
            "REPOSITORY_TEXT_INVALID",
            f"repository {field_name} is invalid",
        )
    return value


def _position(value: Any, field_name: str, *, minimum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
    ):
        raise RepositoryClientError(
            "REPOSITORY_POSITION_INVALID",
            f"repository {field_name} is invalid",
        )
    return value


__all__ = [
    "CategoryRef",
    "MAX_REPOSITORY_RESPONSE_BYTES",
    "ProvisionalRepositoryClient",
    "RepositoryClientConfig",
    "RepositoryClientError",
    "ResourceHead",
    "VersionRef",
]
