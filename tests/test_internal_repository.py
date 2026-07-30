import copy
import json
import os
import unittest
import urllib.parse
from unittest.mock import patch

from treeguard.internal_repository import (
    INTERNAL_CATEGORY_PATH,
    INTERNAL_RESOURCE_LIST_PATH,
    INTERNAL_TREE_PATH,
    INTERNAL_VERSION_INFO_PATH,
    InternalRepositoryClient,
    InternalRepositoryConfig,
    parse_business_version,
)
from treeguard.repository_client import RepositoryClientError
from treeguard.simulator import build_fictional_tree
from treeguard.web import _services_from_environment


RESOURCE_ID = "fictional-fire-resource"
CATEGORY_ID = "fictional-fire-category"
CURRENT_VERSION = "V0.0.0.0J0.1.0"
CURRENT_RECORD_ID = "fictional-version-record-001"
LATEST_VERSION = "V0.0.0.0J0.2.0"
LATEST_RECORD_ID = "fictional-version-record-002"


class _MemoryResponse:
    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class _RoutingOpener:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.requests = []

    def open(self, request, timeout: float):
        self.requests.append(request)
        parsed = urllib.parse.urlsplit(request.full_url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        return _MemoryResponse(self.handler(parsed.path, query))


def _client(
    handler,
    *,
    page_size: int = 2,
    max_items: int = 20,
) -> InternalRepositoryClient:
    client = InternalRepositoryClient(
        InternalRepositoryConfig(
            base_url="http://10.20.30.40:8080",
            page_size=page_size,
            max_items=max_items,
        )
    )
    client._opener = _RoutingOpener(handler)
    return client


def _tree_payload(
    *,
    version: str = LATEST_VERSION,
    record_id: str = LATEST_RECORD_ID,
) -> dict:
    tree = copy.deepcopy(build_fictional_tree(version="SIM-V2"))
    tree["metadata"].update(
        {
            "id": record_id,
            "map_id": RESOURCE_ID,
            "version": version,
            "category_id": CATEGORY_ID,
        }
    )
    return {"status": 200, "message": "success", "data": tree}


def _resource_row(
    resource_id: str,
    record_id: str,
    version: str,
    name: str,
) -> dict:
    return {
        "id": record_id,
        "resource_id": resource_id,
        "resource_name": name,
        "version": version,
        "category_id": CATEGORY_ID,
        "category_name": "虚构消防分类",
        "type": "resource",
        "unrelated_audit_field": "ignored",
    }


def _version_row(
    version: str,
    record_id: str,
    *,
    description: str = "",
) -> dict:
    return {
        "id": record_id,
        "resource_id": RESOURCE_ID,
        "resource_name": "虚构消防信息树",
        "category_id": CATEGORY_ID,
        "version": version,
        "description": description,
        "approve_status": "fictional",
    }


class InternalRepositoryContractTests(unittest.TestCase):
    def test_four_endpoints_map_to_workbench_contract(self) -> None:
        resources = [
            _resource_row(
                "fictional-another-resource",
                "fictional-another-record",
                "V0.0.0.0J0.1.0",
                "虚构辅助信息树",
            ),
            _resource_row(
                RESOURCE_ID,
                CURRENT_RECORD_ID,
                CURRENT_VERSION,
                "虚构消防信息树",
            ),
            _resource_row(
                "fictional-third-resource",
                "fictional-third-record",
                "V0.0.0.0J0.3.0",
                "虚构第三信息树",
            ),
        ]

        def handler(path: str, query: dict[str, str]) -> dict:
            if path == INTERNAL_CATEGORY_PATH:
                self.assertEqual(query, {"leaf_only": "false"})
                return {
                    "status": 200,
                    "message": "success",
                    "data": {
                        "concurrentVersion": 7,
                        "data": [
                            {
                                "id": CATEGORY_ID,
                                "name": "虚构消防分类",
                                "order": 2,
                                "isRoot": False,
                                "parentId": "fictional-root-category",
                            },
                            {
                                "id": "fictional-root-category",
                                "name": "虚构业务分类",
                                "order": 1,
                                "isRoot": True,
                            },
                        ],
                    },
                }
            if path == INTERNAL_RESOURCE_LIST_PATH:
                self.assertEqual(query["category_id"], CATEGORY_ID)
                self.assertEqual(query["page_size"], "2")
                page_no = int(query["page_no"])
                start = (page_no - 1) * 2
                return {
                    "status": 200,
                    "message": "success",
                    "metadata": {"total": len(resources)},
                    "data": resources[start : start + 2],
                }
            if path == INTERNAL_VERSION_INFO_PATH:
                self.assertEqual(query, {"resource_id": RESOURCE_ID})
                return {
                    "status": 200,
                    "message": "success",
                    "data": [
                        _version_row(LATEST_VERSION, LATEST_RECORD_ID),
                        _version_row(
                            CURRENT_VERSION,
                            CURRENT_RECORD_ID,
                            description="虚构初始版本",
                        ),
                    ],
                }
            if path == INTERNAL_TREE_PATH:
                self.assertEqual(
                    query,
                    {"resource_id": RESOURCE_ID, "version": LATEST_VERSION},
                )
                return _tree_payload()
            raise AssertionError(f"unexpected path: {path}")

        client = _client(handler)
        categories = client.list_categories()
        listed_resources = client.list_resources(CATEGORY_ID)
        versions = client.list_versions(RESOURCE_ID)
        imported = client.fetch_tree(RESOURCE_ID, version=LATEST_VERSION)

        self.assertEqual(
            [item.category_id for item in categories],
            ["fictional-root-category", CATEGORY_ID],
        )
        self.assertEqual(len(listed_resources), 3)
        self.assertEqual(
            [item.version for item in versions],
            [CURRENT_VERSION, LATEST_VERSION],
        )
        self.assertTrue(versions[0].is_head)
        self.assertFalse(versions[1].is_head)
        self.assertIsNone(versions[1].description)
        self.assertTrue(imported.is_valid)
        self.assertEqual(imported.tree.tree_id, RESOURCE_ID)
        self.assertEqual(imported.tree.version_record_id, LATEST_RECORD_ID)
        for request in client._opener.requests:
            self.assertNotIn("Authorization", dict(request.header_items()))

    def test_direct_record_selector_uses_id_only(self) -> None:
        def handler(path: str, query: dict[str, str]) -> dict:
            self.assertEqual(path, INTERNAL_TREE_PATH)
            self.assertEqual(query, {"id": LATEST_RECORD_ID})
            return _tree_payload()

        client = _client(handler)
        imported = client.fetch_tree(
            RESOURCE_ID,
            version_record_id=LATEST_RECORD_ID,
        )

        self.assertTrue(imported.is_valid)
        self.assertEqual(imported.tree.version_record_id, LATEST_RECORD_ID)

    def test_head_identity_mismatch_fails_closed(self) -> None:
        def handler(path: str, query: dict[str, str]) -> dict:
            if path == INTERNAL_RESOURCE_LIST_PATH:
                return {
                    "status": 200,
                    "metadata": {"total": 1},
                    "data": [
                        _resource_row(
                            RESOURCE_ID,
                            "different-head-record",
                            LATEST_VERSION,
                            "虚构消防信息树",
                        )
                    ],
                }
            if path == INTERNAL_VERSION_INFO_PATH:
                return {
                    "status": 200,
                    "data": [
                        _version_row(LATEST_VERSION, LATEST_RECORD_ID),
                    ],
                }
            raise AssertionError(path)

        client = _client(handler)
        client.list_resources(CATEGORY_ID)

        with self.assertRaises(RepositoryClientError) as caught:
            client.list_versions(RESOURCE_ID)

        self.assertEqual(
            caught.exception.code,
            "INTERNAL_REPOSITORY_HEAD_IDENTITY_MISMATCH",
        )

    def test_tree_record_must_match_version_list(self) -> None:
        def handler(path: str, query: dict[str, str]) -> dict:
            if path == INTERNAL_RESOURCE_LIST_PATH:
                return {
                    "status": 200,
                    "metadata": {"total": 1},
                    "data": [
                        _resource_row(
                            RESOURCE_ID,
                            LATEST_RECORD_ID,
                            LATEST_VERSION,
                            "虚构消防信息树",
                        )
                    ],
                }
            if path == INTERNAL_VERSION_INFO_PATH:
                return {
                    "status": 200,
                    "data": [
                        _version_row(LATEST_VERSION, LATEST_RECORD_ID),
                    ],
                }
            if path == INTERNAL_TREE_PATH:
                return _tree_payload(record_id="different-tree-record")
            raise AssertionError(path)

        client = _client(handler)
        client.list_versions(RESOURCE_ID)

        with self.assertRaises(RepositoryClientError) as caught:
            client.fetch_tree(RESOURCE_ID, version=LATEST_VERSION)

        self.assertEqual(
            caught.exception.code,
            "INTERNAL_REPOSITORY_TREE_RECORD_MISMATCH",
        )

    def test_versions_resolve_current_default_when_not_preloaded(self) -> None:
        requested_paths: list[str] = []

        def handler(path: str, query: dict[str, str]) -> dict:
            requested_paths.append(path)
            if path == INTERNAL_VERSION_INFO_PATH:
                return {
                    "status": 200,
                    "data": [
                        _version_row(LATEST_VERSION, LATEST_RECORD_ID),
                        _version_row(CURRENT_VERSION, CURRENT_RECORD_ID),
                    ],
                }
            if path == INTERNAL_RESOURCE_LIST_PATH:
                self.assertEqual(query["category_id"], CATEGORY_ID)
                return {
                    "status": 200,
                    "metadata": {"total": 1},
                    "data": [
                        _resource_row(
                            RESOURCE_ID,
                            CURRENT_RECORD_ID,
                            CURRENT_VERSION,
                            "虚构消防信息树",
                        )
                    ],
                }
            raise AssertionError(path)

        versions = _client(handler).list_versions(RESOURCE_ID)

        self.assertEqual(
            requested_paths,
            [INTERNAL_VERSION_INFO_PATH, INTERNAL_RESOURCE_LIST_PATH],
        )
        self.assertEqual(
            [item.is_head for item in versions],
            [True, False],
        )

    def test_pagination_rejects_empty_page_before_total(self) -> None:
        def handler(path: str, query: dict[str, str]) -> dict:
            page_no = int(query["page_no"])
            return {
                "status": 200,
                "metadata": {"total": 2},
                "data": (
                    [
                        _resource_row(
                            RESOURCE_ID,
                            LATEST_RECORD_ID,
                            LATEST_VERSION,
                            "虚构消防信息树",
                        )
                    ]
                    if page_no == 1
                    else []
                ),
            }

        client = _client(handler, page_size=1)

        with self.assertRaises(RepositoryClientError) as caught:
            client.list_resources(CATEGORY_ID)

        self.assertEqual(
            caught.exception.code,
            "INTERNAL_REPOSITORY_RESOURCE_PAGE_EMPTY",
        )

    def test_pagination_rejects_repeated_page(self) -> None:
        row = _resource_row(
            RESOURCE_ID,
            LATEST_RECORD_ID,
            LATEST_VERSION,
            "虚构消防信息树",
        )

        def handler(path: str, query: dict[str, str]) -> dict:
            return {
                "status": 200,
                "metadata": {"total": 2},
                "data": [row],
            }

        with self.assertRaises(RepositoryClientError) as caught:
            _client(handler, page_size=1).list_resources(CATEGORY_ID)

        self.assertEqual(
            caught.exception.code,
            "INTERNAL_REPOSITORY_RESOURCE_PAGE_REPEATED",
        )

    def test_pagination_rejects_total_drift_and_limit(self) -> None:
        def drifting_handler(path: str, query: dict[str, str]) -> dict:
            page_no = int(query["page_no"])
            return {
                "status": 200,
                "metadata": {"total": 2 if page_no == 1 else 3},
                "data": [
                    _resource_row(
                        f"fictional-resource-{page_no}",
                        f"fictional-record-{page_no}",
                        LATEST_VERSION,
                        f"虚构信息树 {page_no}",
                    )
                ],
            }

        with self.assertRaises(RepositoryClientError) as drift:
            _client(
                drifting_handler,
                page_size=1,
            ).list_resources(CATEGORY_ID)
        self.assertEqual(
            drift.exception.code,
            "INTERNAL_REPOSITORY_RESOURCE_TOTAL_CHANGED",
        )

        def oversized_handler(path: str, query: dict[str, str]) -> dict:
            return {
                "status": 200,
                "metadata": {"total": 3},
                "data": [],
            }

        with self.assertRaises(RepositoryClientError) as limit:
            _client(
                oversized_handler,
                page_size=1,
                max_items=2,
            ).list_resources(CATEGORY_ID)
        self.assertEqual(
            limit.exception.code,
            "INTERNAL_REPOSITORY_RESOURCE_LIMIT_EXCEEDED",
        )

    def test_versions_reject_ambiguous_numeric_order(self) -> None:
        def handler(path: str, query: dict[str, str]) -> dict:
            return {
                "status": 200,
                "data": [
                    _version_row(
                        "V0.0J0.1",
                        "fictional-version-record-short",
                    ),
                    _version_row(
                        "V0.0.0J0.1.0",
                        "fictional-version-record-long",
                    ),
                ],
            }

        with self.assertRaises(RepositoryClientError) as caught:
            _client(handler).list_versions(RESOURCE_ID)

        self.assertEqual(
            caught.exception.code,
            "INTERNAL_REPOSITORY_VERSION_DUPLICATE",
        )

    def test_version_parser_compares_both_numeric_segments(self) -> None:
        versions = [
            "V0.0.0.1J0.0.1",
            "V0.0.0.0J0.2.0",
            "V0.0.0.0J0.1.9",
        ]

        self.assertEqual(
            sorted(versions, key=parse_business_version),
            [
                "V0.0.0.0J0.1.9",
                "V0.0.0.0J0.2.0",
                "V0.0.0.1J0.0.1",
            ],
        )
        with self.assertRaises(RepositoryClientError) as caught:
            parse_business_version("V0.1.0")
        self.assertEqual(
            caught.exception.code,
            "INTERNAL_REPOSITORY_VERSION_FORMAT_INVALID",
        )

    def test_public_or_implicit_http_endpoint_is_rejected(self) -> None:
        for base_url in (
            "https://example.com",
            "http://10.20.30.40",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaises(RepositoryClientError):
                    InternalRepositoryConfig(base_url=base_url)

    def test_workbench_selects_internal_repository_explicitly(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TREEGUARD_WORKBENCH_REPOSITORY_MODE": "INTERNAL",
                "TREEGUARD_WORKBENCH_REPOSITORY_URL": (
                    "http://10.20.30.40:8080"
                ),
            },
            clear=True,
        ):
            workbench, governance, validation = _services_from_environment()

        self.assertIsInstance(
            workbench.repository,
            InternalRepositoryClient,
        )
        self.assertIs(governance.repository, workbench.repository)
        self.assertIs(validation.repository, workbench.repository)

    def test_workbench_rejects_unknown_repository_mode(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"TREEGUARD_WORKBENCH_REPOSITORY_MODE": "AUTO"},
                clear=True,
            ),
            self.assertRaises(RepositoryClientError) as caught,
        ):
            _services_from_environment()

        self.assertEqual(
            caught.exception.code,
            "WORKBENCH_REPOSITORY_MODE_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
