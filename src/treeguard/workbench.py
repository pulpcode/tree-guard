"""Read-only application service and allowlisted DTOs for the local workbench."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from treeguard.models import CanonicalTree, ImportResult
from treeguard.repository_client import (
    CategoryRef,
    ResourceHead,
    VersionRef,
)


WORKBENCH_API_VERSION = "workbench-api.v1"
TREE_VIEW_SCHEMA_VERSION = "workbench-tree-view.v1"


class WorkbenchError(RuntimeError):
    """A workbench application operation failed its local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ReadOnlyTreeRepository(Protocol):
    """Narrow repository boundary consumed by the workbench application layer."""

    def list_categories(self) -> tuple[CategoryRef, ...]: ...

    def list_resources(self, category_id: str) -> tuple[ResourceHead, ...]: ...

    def list_versions(self, resource_id: str) -> tuple[VersionRef, ...]: ...

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ) -> ImportResult: ...


@dataclass(frozen=True, slots=True)
class WorkbenchService:
    """Expose repository facts through UI-specific positive allowlists."""

    repository: ReadOnlyTreeRepository

    def categories(self) -> dict[str, Any]:
        return {
            "schema_version": "workbench-categories.v1",
            "items": [
                {
                    "category_id": item.category_id,
                    "parent_id": item.parent_id,
                    "name": item.name,
                    "order": item.order,
                }
                for item in self.repository.list_categories()
            ],
        }

    def resources(self, category_id: str) -> dict[str, Any]:
        return {
            "schema_version": "workbench-resources.v1",
            "items": [
                {
                    "resource_id": item.resource_id,
                    "category_id": item.category_id,
                    "name": item.name,
                    "head_version": item.head_version,
                }
                for item in self.repository.list_resources(category_id)
            ],
        }

    def versions(self, resource_id: str) -> dict[str, Any]:
        return {
            "schema_version": "workbench-versions.v1",
            "items": [
                {
                    "position": item.position,
                    "version": item.version,
                    "description": item.description,
                    "is_head": item.is_head,
                }
                for item in self.repository.list_versions(resource_id)
            ],
        }

    def tree_view(
        self,
        resource_id: str,
        *,
        version: str,
    ) -> dict[str, Any]:
        result = self.repository.fetch_tree(resource_id, version=version)
        if not result.is_valid or result.tree is None:
            raise WorkbenchError(
                "WORKBENCH_TREE_NOT_AVAILABLE",
                "repository did not return a valid canonical tree",
            )
        return build_tree_view(result.tree)


@dataclass(frozen=True, slots=True)
class TreeReferenceIndex:
    """Internal mapping between one browser view and canonical node identities."""

    ordered_node_ids: tuple[str, ...]
    ref_by_node_id: Mapping[str, str]
    node_id_by_ref: Mapping[str, str]


def build_tree_reference_index(tree: CanonicalTree) -> TreeReferenceIndex:
    """Build the deterministic response-scoped reference mapping for one tree."""

    nodes_by_id = {node.node_id: node for node in tree.nodes}
    ordered_node_ids: list[str] = []
    visited: set[str] = set()
    pending = list(reversed(tree.root_node_ids))
    while pending:
        node_id = pending.pop()
        if node_id in visited or node_id not in nodes_by_id:
            raise WorkbenchError(
                "WORKBENCH_TREE_RELATION_INVALID",
                "canonical tree relation could not be projected",
            )
        visited.add(node_id)
        ordered_node_ids.append(node_id)
        pending.extend(reversed(nodes_by_id[node_id].child_node_ids))
    if len(ordered_node_ids) != len(tree.nodes):
        raise WorkbenchError(
            "WORKBENCH_TREE_RELATION_INVALID",
            "canonical tree relation could not be projected",
        )
    ref_by_node_id = {
        node_id: f"N{index:06d}"
        for index, node_id in enumerate(ordered_node_ids, start=1)
    }
    return TreeReferenceIndex(
        ordered_node_ids=tuple(ordered_node_ids),
        ref_by_node_id=MappingProxyType(ref_by_node_id),
        node_id_by_ref=MappingProxyType(
            {
                reference: node_id
                for node_id, reference in ref_by_node_id.items()
            }
        ),
    )


def build_tree_view(tree: CanonicalTree) -> dict[str, Any]:
    """Project a canonical tree into the browser's exact read-only allowlist."""

    nodes_by_id = {node.node_id: node for node in tree.nodes}
    reference_index = build_tree_reference_index(tree)
    references = reference_index.ref_by_node_id

    def breadcrumb(node_id: str) -> list[str]:
        names: list[str] = []
        cursor: str | None = node_id
        visited: set[str] = set()
        while cursor is not None:
            if cursor in visited or cursor not in nodes_by_id:
                raise WorkbenchError(
                    "WORKBENCH_TREE_RELATION_INVALID",
                    "canonical tree relation could not be projected",
                )
            visited.add(cursor)
            node = nodes_by_id[cursor]
            names.append(node.name)
            cursor = node.parent_node_id
        names.reverse()
        return names

    projected_nodes: list[dict[str, Any]] = []
    for node_id in reference_index.ordered_node_ids:
        node = nodes_by_id[node_id]
        value_contract = node.value_contract
        projected_nodes.append(
            {
                "ref": references[node.node_id],
                "parent_ref": (
                    references[node.parent_node_id]
                    if node.parent_node_id is not None
                    else None
                ),
                "child_refs": [
                    references[child_id] for child_id in node.child_node_ids
                ],
                "name": node.name,
                "label": node.label,
                "kind": node.kind,
                "value_type": (
                    value_contract.value_type
                    if value_contract is not None
                    else None
                ),
                "cardinality": (
                    value_contract.cardinality
                    if value_contract is not None
                    else None
                ),
                "order": node.order,
                "breadcrumb": breadcrumb(node.node_id),
            }
        )

    return {
        "schema_version": TREE_VIEW_SCHEMA_VERSION,
        "tree_version": tree.tree_version,
        "node_count": len(projected_nodes),
        "root_refs": [references[node_id] for node_id in tree.root_node_ids],
        "nodes": projected_nodes,
    }


__all__ = [
    "ReadOnlyTreeRepository",
    "TreeReferenceIndex",
    "TREE_VIEW_SCHEMA_VERSION",
    "WORKBENCH_API_VERSION",
    "WorkbenchError",
    "WorkbenchService",
    "build_tree_reference_index",
    "build_tree_view",
]
