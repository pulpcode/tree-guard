from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

import httpx

from treeguard.adapter import adapt_tree_document
from treeguard.models import ImportResult
from treeguard.repository_client import (
    CategoryRef,
    RepositoryClientError,
    ResourceHead,
    VersionRef,
)
from treeguard.simulator import build_fictional_tree
from treeguard.web import create_app
from treeguard.workbench import WorkbenchService, build_tree_view


@dataclass
class FakeRepository:
    result: ImportResult
    fail_categories: bool = False

    def list_categories(self) -> tuple[CategoryRef, ...]:
        if self.fail_categories:
            raise RepositoryClientError(
                "REPOSITORY_TEST_FAILURE",
                "sensitive upstream URL and response",
            )
        return (
            CategoryRef(
                category_id="fictional-root-category",
                parent_id=None,
                name="虚构资料库",
                order=1,
            ),
            CategoryRef(
                category_id="fictional-catalog-category",
                parent_id="fictional-root-category",
                name="虚构藏品目录",
                order=1,
            ),
        )

    def list_resources(self, category_id: str) -> tuple[ResourceHead, ...]:
        return (
            ResourceHead(
                resource_id="fictional-museum-resource",
                category_id=category_id,
                name="虚构博物馆藏品目录",
                head_version="SIM-V2",
                head_version_record_id="fictional-record-sim-v2",
            ),
        )

    def list_versions(self, resource_id: str) -> tuple[VersionRef, ...]:
        return (
            VersionRef(
                position=0,
                version="SIM-V1",
                version_record_id="fictional-record-sim-v1",
                description=None,
                is_head=False,
            ),
            VersionRef(
                position=1,
                version="SIM-V2",
                version_record_id="fictional-record-sim-v2",
                description="Fictional head",
                is_head=True,
            ),
        )

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ) -> ImportResult:
        return self.result


def _fictional_result(node_count: int = 5) -> ImportResult:
    return adapt_tree_document(build_fictional_tree(node_count=node_count))


class WorkbenchServiceTests(unittest.TestCase):
    def test_tree_view_projects_2001_nodes_through_exact_allowlist(self) -> None:
        result = _fictional_result(node_count=2001)
        self.assertTrue(result.is_valid)
        assert result.tree is not None

        view = build_tree_view(result.tree)

        self.assertEqual(view["schema_version"], "workbench-tree-view.v1")
        self.assertEqual(view["node_count"], 2001)
        self.assertEqual(view["root_refs"], ["N000001"])
        self.assertEqual(
            set(view),
            {
                "schema_version",
                "tree_version",
                "node_count",
                "root_refs",
                "nodes",
            },
        )
        self.assertEqual(
            set(view["nodes"][0]),
            {
                "ref",
                "parent_ref",
                "child_refs",
                "name",
                "label",
                "kind",
                "value_type",
                "cardinality",
                "order",
                "breadcrumb",
            },
        )
        encoded = json.dumps(view, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "node_id",
            "snapshot_hash",
            "metadata_extra",
            "source_route",
            "fictional-museum-root",
            "raw_constraints",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_catalog_responses_omit_version_record_identifiers(self) -> None:
        service = WorkbenchService(FakeRepository(_fictional_result()))

        resources = service.resources("fictional-catalog-category")
        versions = service.versions("fictional-museum-resource")

        self.assertNotIn(
            "version_record_id",
            json.dumps([resources, versions], sort_keys=True),
        )
        self.assertEqual(resources["items"][0]["head_version"], "SIM-V2")
        self.assertTrue(versions["items"][1]["is_head"])


class WorkbenchAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_catalog_and_tree_endpoints(self) -> None:
        service = WorkbenchService(FakeRepository(_fictional_result()))
        async with _client(service) as client:
            health = await client.get("/api/v1/health")
            categories = await client.get("/api/v1/categories")
            resources = await client.get(
                "/api/v1/resources",
                params={"category_id": "fictional-catalog-category"},
            )
            versions = await client.get(
                "/api/v1/resources/fictional-museum-resource/versions"
            )
            tree = await client.get(
                "/api/v1/resources/fictional-museum-resource/tree",
                params={"version": "SIM-V2"},
            )

        for response in (health, categories, resources, versions, tree):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(
                response.headers["x-content-type-options"],
                "nosniff",
            )
        self.assertEqual(tree.json()["node_count"], 5)

    async def test_repository_failure_returns_fixed_non_sensitive_error(
        self,
    ) -> None:
        service = WorkbenchService(
            FakeRepository(_fictional_result(), fail_categories=True)
        )
        async with _client(service) as client:
            response = await client.get("/api/v1/categories")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {
                "schema_version": "workbench-error.v1",
                "error_code": "REPOSITORY_TEST_FAILURE",
                "message": "Request could not be completed.",
            },
        )
        self.assertNotIn("sensitive", response.text)

    async def test_invalid_query_uses_fixed_error_contract(self) -> None:
        service = WorkbenchService(FakeRepository(_fictional_result()))
        async with _client(service) as client:
            response = await client.get(
                "/api/v1/resources",
                params={"category_id": ""},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error_code"],
            "WORKBENCH_REQUEST_INVALID",
        )
        self.assertNotIn("category_id", response.text)


def _client(service: WorkbenchService) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://treeguard.test",
    )


if __name__ == "__main__":
    unittest.main()
