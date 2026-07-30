"""Read-only adapter for the confirmed internal information-tree HTTP API."""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from treeguard.adapter import TreeFormatError, adapt_tree_document
from treeguard.http_utils import (
    build_isolated_opener,
    is_protected_environment_host,
)
from treeguard.json_utils import StrictJSONError, strict_json_loads
from treeguard.models import ImportResult
from treeguard.repository_client import (
    CategoryRef,
    RepositoryClientError,
    ResourceHead,
    VersionRef,
)


INTERNAL_CATEGORY_PATH = "/api/v1/category/query-list"
INTERNAL_RESOURCE_LIST_PATH = "/api/v1/resource/list"
INTERNAL_VERSION_INFO_PATH = "/api/v1/resource/version-info"
INTERNAL_TREE_PATH = "/api/v1/resource/tree"
MAX_INTERNAL_REPOSITORY_RESPONSE_BYTES = 64_000_000

_BUSINESS_VERSION = re.compile(
    r"^[A-Za-z]+"
    r"(?P<before>[0-9]+(?:\.[0-9]+)*)"
    r"[A-Za-z]+"
    r"(?P<after>[0-9]+(?:\.[0-9]+)*)$"
)


@dataclass(frozen=True, slots=True)
class InternalRepositoryConfig:
    """Runtime-only configuration for the protected-environment repository."""

    base_url: str
    timeout_seconds: float = 30.0
    page_size: int = 50
    max_items: int = 20_000

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_BASE_URL_INVALID",
                "internal repository base_url is invalid",
            )
        parsed = urllib.parse.urlparse(self.base_url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_BASE_URL_INVALID",
                "internal repository base_url is malformed",
            ) from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or not is_protected_environment_host(parsed.hostname)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
            or (parsed.scheme == "http" and port is None)
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_BASE_URL_INVALID",
                "internal repository must use an explicit protected-environment endpoint",
            )
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 300
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TIMEOUT_INVALID",
                "internal repository timeout is invalid",
            )
        if (
            not isinstance(self.page_size, int)
            or isinstance(self.page_size, bool)
            or self.page_size < 1
            or self.page_size > 200
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_PAGE_SIZE_INVALID",
                "internal repository page size is invalid",
            )
        if (
            not isinstance(self.max_items, int)
            or isinstance(self.max_items, bool)
            or self.max_items < self.page_size
            or self.max_items > 100_000
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_ITEM_LIMIT_INVALID",
                "internal repository item limit is invalid",
            )


class InternalRepositoryClient:
    """Map the internal four-endpoint API into the Workbench read contract."""

    def __init__(self, config: InternalRepositoryConfig) -> None:
        self.config = config
        self._opener = build_isolated_opener()
        self._cache_lock = threading.RLock()
        self._heads_by_resource: dict[str, ResourceHead] = {}
        self._versions_by_resource: dict[str, dict[str, str]] = {}
        self._records_by_resource: dict[str, set[str]] = {}

    def list_categories(self) -> tuple[CategoryRef, ...]:
        payload = self._get(
            INTERNAL_CATEGORY_PATH,
            {"leaf_only": "false"},
        )
        envelope = _success_payload(payload, "category/query-list")
        data = envelope.get("data")
        if (
            not isinstance(data, dict)
            or not _is_non_negative_integer(data.get("concurrentVersion"))
            or not isinstance(data.get("data"), list)
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_CATEGORY_RESPONSE_INVALID",
                "internal category response is invalid",
            )
        categories: dict[str, tuple[CategoryRef, bool]] = {}
        for raw_item in data["data"]:
            item, is_root = _category(raw_item)
            if item.category_id in categories:
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_CATEGORY_DUPLICATE",
                    "internal category identifiers must be unique",
                )
            categories[item.category_id] = (item, is_root)
        return _canonical_categories(categories)

    def list_resources(self, category_id: str) -> tuple[ResourceHead, ...]:
        category_id = _identifier(category_id, "category_id")
        page_no = 1
        expected_total: int | None = None
        resources: list[ResourceHead] = []
        resource_ids: set[str] = set()
        record_ids: set[str] = set()
        page_signatures: set[tuple[str, ...]] = set()
        maximum_pages = (
            self.config.max_items + self.config.page_size - 1
        ) // self.config.page_size

        while page_no <= maximum_pages:
            payload = self._get(
                INTERNAL_RESOURCE_LIST_PATH,
                {
                    "category_id": category_id,
                    "page_no": str(page_no),
                    "page_size": str(self.config.page_size),
                },
            )
            envelope = _success_payload(payload, "resource/list")
            metadata = envelope.get("metadata")
            raw_items = envelope.get("data")
            if (
                not isinstance(metadata, dict)
                or not _is_non_negative_integer(metadata.get("total"))
                or not isinstance(raw_items, list)
                or len(raw_items) > self.config.page_size
            ):
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_RESOURCE_RESPONSE_INVALID",
                    "internal resource list response is invalid",
                )
            total = metadata["total"]
            if total > self.config.max_items:
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_RESOURCE_LIMIT_EXCEEDED",
                    "internal resource list exceeds the configured limit",
                )
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_RESOURCE_TOTAL_CHANGED",
                    "internal resource total changed during pagination",
                )
            if not raw_items and len(resources) < total:
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_RESOURCE_PAGE_EMPTY",
                    "internal resource pagination ended before its declared total",
                )

            page = [
                _resource(raw_item, category_id)
                for raw_item in raw_items
            ]
            signature = tuple(
                item.head_version_record_id for item in page
            )
            if signature and signature in page_signatures:
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_RESOURCE_PAGE_REPEATED",
                    "internal resource pagination repeated a page",
                )
            page_signatures.add(signature)
            if (
                len({item.resource_id for item in page}) != len(page)
                or len(
                    {
                        item.head_version_record_id
                        for item in page
                    }
                )
                != len(page)
            ):
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_RESOURCE_DUPLICATE",
                    "internal resource page contains duplicate identities",
                )
            for item in page:
                if (
                    item.resource_id in resource_ids
                    or item.head_version_record_id in record_ids
                ):
                    raise RepositoryClientError(
                        "INTERNAL_REPOSITORY_RESOURCE_DUPLICATE",
                        "internal resource list contains duplicate identities",
                    )
                resource_ids.add(item.resource_id)
                record_ids.add(item.head_version_record_id)
            resources.extend(page)
            if len(resources) > total:
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_RESOURCE_TOTAL_MISMATCH",
                    "internal resource list exceeded its declared total",
                )
            if len(resources) == total:
                break
            page_no += 1
        else:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_RESOURCE_LIMIT_EXCEEDED",
                "internal resource pagination exceeded its page limit",
            )

        ordered = tuple(
            sorted(resources, key=lambda item: item.resource_id)
        )
        with self._cache_lock:
            for item in ordered:
                self._heads_by_resource[item.resource_id] = item
        return ordered

    def list_versions(self, resource_id: str) -> tuple[VersionRef, ...]:
        resource_id = _identifier(resource_id, "resource_id")
        payload = self._get(
            INTERNAL_VERSION_INFO_PATH,
            {"resource_id": resource_id},
        )
        envelope = _success_payload(payload, "resource/version-info")
        raw_items = envelope.get("data")
        if (
            not isinstance(raw_items, list)
            or not raw_items
            or len(raw_items) > self.config.max_items
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_VERSION_RESPONSE_INVALID",
                "internal version response is invalid",
            )

        parsed: list[
            tuple[
                tuple[tuple[int, ...], tuple[int, ...]],
                str,
                str,
                str | None,
                str,
            ]
        ] = []
        versions_seen: set[str] = set()
        records_seen: set[str] = set()
        sort_keys_seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_VERSION_INVALID",
                    "internal version item is invalid",
                )
            item_resource_id = _identifier(
                raw_item.get("resource_id"),
                "resource_id",
            )
            if item_resource_id != resource_id:
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_VERSION_RESOURCE_MISMATCH",
                    "internal version belongs to a different resource",
                )
            version = _identifier(raw_item.get("version"), "version")
            record_id = _identifier(raw_item.get("id"), "id")
            description = _optional_text(raw_item.get("description"))
            category_id = _identifier(
                raw_item.get("category_id"),
                "category_id",
            )
            sort_key = parse_business_version(version)
            if (
                version in versions_seen
                or record_id in records_seen
                or sort_key in sort_keys_seen
            ):
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_VERSION_DUPLICATE",
                    "internal versions contain duplicate or ambiguous identities",
                )
            versions_seen.add(version)
            records_seen.add(record_id)
            sort_keys_seen.add(sort_key)
            parsed.append(
                (sort_key, version, record_id, description, category_id)
            )
        category_ids = {item[4] for item in parsed}
        if len(category_ids) != 1:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_VERSION_CATEGORY_MISMATCH",
                "internal versions belong to different categories",
            )
        category_id = next(iter(category_ids))
        with self._cache_lock:
            head = self._heads_by_resource.get(resource_id)
        if head is None:
            self.list_resources(category_id)
            with self._cache_lock:
                head = self._heads_by_resource.get(resource_id)
        if (
            head is None
            or head.category_id != category_id
            or not any(
                item[1] == head.head_version
                and item[2] == head.head_version_record_id
                for item in parsed
            )
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_HEAD_IDENTITY_MISMATCH",
                "resource current/default version is absent from its version list",
            )

        parsed.sort(key=lambda item: item[0])
        versions = tuple(
            VersionRef(
                position=position,
                version=item[1],
                version_record_id=item[2],
                description=item[3],
                is_head=(
                    item[1] == head.head_version
                    and item[2] == head.head_version_record_id
                ),
            )
            for position, item in enumerate(parsed)
        )
        if sum(item.is_head for item in versions) != 1:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_HEAD_IDENTITY_MISMATCH",
                "resource current/default version identity is ambiguous",
            )

        with self._cache_lock:
            self._versions_by_resource[resource_id] = {
                item.version: item.version_record_id for item in versions
            }
            self._records_by_resource[resource_id] = {
                item.version_record_id for item in versions
            }
        return versions

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ) -> ImportResult:
        resource_id = _identifier(resource_id, "resource_id")
        if (version is None) == (version_record_id is None):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TREE_SELECTOR_INVALID",
                "select exactly one business version or version record",
            )
        if version is not None:
            version = _identifier(version, "version")
            query = {"resource_id": resource_id, "version": version}
        else:
            version_record_id = _identifier(
                version_record_id,
                "version_record_id",
            )
            query = {"id": version_record_id}

        payload = self._get(INTERNAL_TREE_PATH, query)
        envelope = _success_payload(payload, "resource/tree")
        if not isinstance(envelope.get("data"), dict):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TREE_RESPONSE_INVALID",
                "internal tree response is invalid",
            )
        try:
            result = adapt_tree_document(envelope)
        except (TreeFormatError, TypeError, ValueError):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TREE_FORMAT_INVALID",
                "internal tree could not be adapted",
            ) from None
        if not result.is_valid or result.tree is None:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TREE_CONFORMANCE_INVALID",
                "internal tree failed canonical conformance",
            )
        tree = result.tree
        if tree.tree_id != resource_id:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TREE_IDENTITY_MISMATCH",
                "internal tree belongs to a different resource",
            )
        if version is not None and tree.tree_version != version:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TREE_VERSION_MISMATCH",
                "internal tree returned a different business version",
            )
        if (
            version_record_id is not None
            and tree.version_record_id != version_record_id
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_TREE_RECORD_MISMATCH",
                "internal tree returned a different version record",
            )
        with self._cache_lock:
            versions = self._versions_by_resource.get(resource_id)
            records = self._records_by_resource.get(resource_id)
            if (
                version is not None
                and versions is not None
                and versions.get(version) != tree.version_record_id
            ):
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_TREE_RECORD_MISMATCH",
                    "version list and full tree record identifiers are inconsistent",
                )
            if (
                version_record_id is not None
                and records is not None
                and version_record_id not in records
            ):
                raise RepositoryClientError(
                    "INTERNAL_REPOSITORY_TREE_RECORD_MISMATCH",
                    "selected tree record is absent from the version list",
                )
        return result

    def _get(self, path: str, query: dict[str, str]) -> Any:
        endpoint = (
            self.config.base_url.rstrip("/")
            + path
            + "?"
            + urllib.parse.urlencode(sorted(query.items()))
        )
        request = urllib.request.Request(
            endpoint,
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with self._opener.open(
                request,
                timeout=float(self.config.timeout_seconds),
            ) as response:
                raw = response.read(
                    MAX_INTERNAL_REPOSITORY_RESPONSE_BYTES + 1
                )
        except urllib.error.HTTPError as exc:
            raise RepositoryClientError(
                f"INTERNAL_REPOSITORY_HTTP_{exc.code}",
                "internal repository returned an HTTP error",
            ) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_CONNECTION_FAILED",
                "internal repository connection failed",
            ) from None
        if len(raw) > MAX_INTERNAL_REPOSITORY_RESPONSE_BYTES:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_RESPONSE_TOO_LARGE",
                "internal repository response exceeded its size limit",
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
                "INTERNAL_REPOSITORY_RESPONSE_NOT_JSON",
                "internal repository response was not strict JSON",
            ) from None


def parse_business_version(
    version: str,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return the confirmed numeric ordering key around the middle letters."""

    version = _identifier(version, "version")
    match = _BUSINESS_VERSION.fullmatch(version)
    if match is None:
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_VERSION_FORMAT_INVALID",
            "business version does not match the confirmed ordering format",
        )
    return (
        _normalized_numeric_segment(match.group("before")),
        _normalized_numeric_segment(match.group("after")),
    )


def _normalized_numeric_segment(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in value.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _success_payload(payload: Any, operation: str) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or payload.get("status") != 200
        or "data" not in payload
    ):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_RESPONSE_INVALID",
            f"internal {operation} response is invalid",
        )
    return payload


def _category(payload: Any) -> tuple[CategoryRef, bool]:
    if not isinstance(payload, dict) or not isinstance(
        payload.get("isRoot"),
        bool,
    ):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_CATEGORY_INVALID",
            "internal category item is invalid",
        )
    category_id = _identifier(payload.get("id"), "id")
    parent_value = payload.get("parentId")
    parent_id = (
        None
        if parent_value is None or parent_value == ""
        else _identifier(parent_value, "parentId")
    )
    item = CategoryRef(
        category_id=category_id,
        parent_id=parent_id,
        name=_text(payload.get("name"), "name"),
        order=_non_negative_integer(payload.get("order"), "order"),
    )
    return item, payload["isRoot"]


def _canonical_categories(
    categories: dict[str, tuple[CategoryRef, bool]],
) -> tuple[CategoryRef, ...]:
    children: dict[str | None, list[CategoryRef]] = {}
    for category, is_root in categories.values():
        if is_root != (category.parent_id is None):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_CATEGORY_ROOT_INVALID",
                "internal category root metadata is inconsistent",
            )
        if (
            category.parent_id is not None
            and category.parent_id not in categories
        ):
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_CATEGORY_PARENT_MISSING",
                "internal category parent is missing",
            )
        children.setdefault(category.parent_id, []).append(category)
    for values in children.values():
        values.sort(key=lambda item: (item.order, item.category_id))

    ordered: list[CategoryRef] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(category: CategoryRef) -> None:
        if category.category_id in visiting:
            raise RepositoryClientError(
                "INTERNAL_REPOSITORY_CATEGORY_CYCLE",
                "internal categories contain a cycle",
            )
        if category.category_id in visited:
            return
        visiting.add(category.category_id)
        ordered.append(category)
        for child in children.get(category.category_id, []):
            visit(child)
        visiting.remove(category.category_id)
        visited.add(category.category_id)

    for root in children.get(None, []):
        visit(root)
    if len(visited) != len(categories):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_CATEGORY_CYCLE",
            "internal categories are not a rooted forest",
        )
    return tuple(ordered)


def _resource(payload: Any, requested_category_id: str) -> ResourceHead:
    if not isinstance(payload, dict):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_RESOURCE_INVALID",
            "internal resource item is invalid",
        )
    category_id = _identifier(payload.get("category_id"), "category_id")
    if category_id != requested_category_id:
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_RESOURCE_CATEGORY_MISMATCH",
            "internal resource belongs to a different category",
        )
    return ResourceHead(
        resource_id=_identifier(payload.get("resource_id"), "resource_id"),
        category_id=category_id,
        name=_text(payload.get("resource_name"), "resource_name"),
        head_version=_identifier(payload.get("version"), "version"),
        head_version_record_id=_identifier(payload.get("id"), "id"),
    )


def _identifier(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_IDENTIFIER_INVALID",
            f"internal repository {field_name} is invalid",
        )
    return value


def _text(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 1_000
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_TEXT_INVALID",
            f"internal repository {field_name} is invalid",
        )
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_TEXT_INVALID",
            "internal repository description is invalid",
        )
    if not value.strip():
        return None
    return _text(value, "description")


def _is_non_negative_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _non_negative_integer(value: Any, field_name: str) -> int:
    if not _is_non_negative_integer(value):
        raise RepositoryClientError(
            "INTERNAL_REPOSITORY_POSITION_INVALID",
            f"internal repository {field_name} is invalid",
        )
    return value


__all__ = [
    "INTERNAL_CATEGORY_PATH",
    "INTERNAL_RESOURCE_LIST_PATH",
    "INTERNAL_TREE_PATH",
    "INTERNAL_VERSION_INFO_PATH",
    "InternalRepositoryClient",
    "InternalRepositoryConfig",
    "MAX_INTERNAL_REPOSITORY_RESPONSE_BYTES",
    "parse_business_version",
]
