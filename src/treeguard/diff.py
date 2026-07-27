"""Deterministic, revision-aware diffing for canonical tree snapshots."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from treeguard.hashing import canonical_digest, without_audit_fields
from treeguard.models import (
    CanonicalNode,
    CanonicalTree,
    freeze_json,
    thaw_json,
)


SCHEMA_VERSION = "tree-diff.v1"
ALGORITHM_VERSION = "treeguard.snapshot-diff.v1"
SUPPORTED_SNAPSHOT_SCHEMA_VERSION = "tree-snapshot.v1"

CHANGE_TYPE_ORDER = (
    "NODE_ADDED",
    "NODE_REMOVED",
    "NODE_MOVED",
    "NODE_LABEL_CHANGED",
    "NODE_NAME_CHANGED",
    "NODE_KIND_CHANGED",
    "SOURCE_TYPE_TOKEN_CHANGED",
    "VALUE_CONTRACT_ADDED",
    "VALUE_CONTRACT_REMOVED",
    "VALUE_TYPE_CHANGED",
    "CARDINALITY_CHANGED",
    "CONSTRAINTS_CHANGED",
    "PLACEHOLDER_CHANGED",
    "REMARK_CHANGED",
    "EXTENSION_CHANGED_UNCLASSIFIED",
    "METADATA_CHANGED_UNCLASSIFIED",
    "ORDER_OBSERVED_CHANGED",
)
_CHANGE_TYPE_RANK = {
    change_type: index for index, change_type in enumerate(CHANGE_TYPE_ORDER)
}


class SnapshotDiffError(ValueError):
    """A comparison that cannot safely produce a TreeDiff."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SnapshotRef:
    snapshot_schema_version: str
    source_map_type: str
    tree_id: str
    tree_version: str
    source_revision: int
    version_record_id: str
    snapshot_hash: str

    @classmethod
    def from_tree(cls, tree: CanonicalTree) -> SnapshotRef:
        return cls(
            snapshot_schema_version=tree.schema_version,
            source_map_type=tree.source_map_type,
            tree_id=tree.tree_id,
            tree_version=tree.tree_version,
            source_revision=tree.source_revision,
            version_record_id=tree.version_record_id,
            snapshot_hash=tree.snapshot_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_schema_version": self.snapshot_schema_version,
            "source_map_type": self.source_map_type,
            "tree_id": self.tree_id,
            "tree_version": self.tree_version,
            "source_revision": self.source_revision,
            "version_record_id": self.version_record_id,
            "snapshot_hash": self.snapshot_hash,
        }


@dataclass(frozen=True, slots=True)
class NodeRef:
    node_hash: str
    parent_node_id: str | None
    kind: str

    @classmethod
    def from_node(cls, node: CanonicalNode) -> NodeRef:
        return cls(
            node_hash=node.node_hash,
            parent_node_id=node.parent_node_id,
            kind=node.kind,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_hash": self.node_hash,
            "parent_node_id": self.parent_node_id,
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class FieldDelta:
    field_path: str
    before: Any
    after: Any
    category: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", freeze_json(self.before))
        object.__setattr__(self, "after", freeze_json(self.after))

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "before": thaw_json(self.before),
            "after": thaw_json(self.after),
            "category": self.category,
        }


@dataclass(frozen=True, slots=True)
class NodeDelta:
    node_id: str
    status: str
    before_ref: NodeRef | None
    after_ref: NodeRef | None
    change_types: tuple[str, ...]
    field_deltas: tuple[FieldDelta, ...]

    def __post_init__(self) -> None:
        if self.status == "ADDED":
            valid = (
                self.before_ref is None
                and self.after_ref is not None
                and self.change_types == ("NODE_ADDED",)
                and not self.field_deltas
            )
        elif self.status == "REMOVED":
            valid = (
                self.before_ref is not None
                and self.after_ref is None
                and self.change_types == ("NODE_REMOVED",)
                and not self.field_deltas
            )
        elif self.status == "MODIFIED":
            valid = (
                self.before_ref is not None
                and self.after_ref is not None
                and bool(self.field_deltas)
                and len(self.change_types) == len(self.field_deltas)
                and "NODE_ADDED" not in self.change_types
                and "NODE_REMOVED" not in self.change_types
            )
        else:
            valid = False
        if not valid:
            raise ValueError(f"inconsistent node delta state: {self.status}")
        if len(set(self.change_types)) != len(self.change_types):
            raise ValueError("node delta change_types must be unique")
        try:
            ordered = tuple(
                sorted(self.change_types, key=lambda item: _CHANGE_TYPE_RANK[item])
            )
        except KeyError as exc:
            raise ValueError(f"unknown change type: {exc.args[0]}") from exc
        if self.change_types != ordered:
            raise ValueError("node delta change_types must use canonical order")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "before_ref": self.before_ref.to_dict() if self.before_ref is not None else None,
            "after_ref": self.after_ref.to_dict() if self.after_ref is not None else None,
            "change_types": list(self.change_types),
            "field_deltas": [delta.to_dict() for delta in self.field_deltas],
        }


@dataclass(frozen=True, slots=True)
class ComparisonIssue:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class DiffSummary:
    node_delta_count: int
    added_count: int
    removed_count: int
    modified_count: int
    change_type_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if min(
            self.node_delta_count,
            self.added_count,
            self.removed_count,
            self.modified_count,
        ) < 0:
            raise ValueError("diff summary counts must be non-negative")
        if self.node_delta_count != (
            self.added_count + self.removed_count + self.modified_count
        ):
            raise ValueError("diff summary status counts are inconsistent")
        if any(
            key not in _CHANGE_TYPE_RANK
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            for key, value in self.change_type_counts.items()
        ):
            raise ValueError("diff summary contains an invalid change type count")
        object.__setattr__(self, "change_type_counts", freeze_json(self.change_type_counts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_delta_count": self.node_delta_count,
            "added_count": self.added_count,
            "removed_count": self.removed_count,
            "modified_count": self.modified_count,
            "change_type_counts": thaw_json(self.change_type_counts),
        }


@dataclass(frozen=True, slots=True)
class TreeDiff:
    schema_version: str
    algorithm_version: str
    scope: str
    base: SnapshotRef
    target: SnapshotRef
    node_deltas: tuple[NodeDelta, ...]
    warnings: tuple[ComparisonIssue, ...]
    summary: DiffSummary
    diff_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported TreeDiff schema_version")
        if self.algorithm_version != ALGORITHM_VERSION:
            raise ValueError("unsupported TreeDiff algorithm_version")
        node_ids = tuple(delta.node_id for delta in self.node_deltas)
        if node_ids != tuple(sorted(node_ids)) or len(node_ids) != len(set(node_ids)):
            raise ValueError("node_deltas must have unique node_id values in sorted order")
        expected_summary = _summarize(self.node_deltas)
        if self.summary.to_dict() != expected_summary.to_dict():
            raise ValueError("TreeDiff summary does not match node_deltas")
        expected_hash = _diff_digest(
            schema_version=self.schema_version,
            algorithm_version=self.algorithm_version,
            scope=self.scope,
            base=self.base,
            target=self.target,
            node_deltas=self.node_deltas,
            warnings=self.warnings,
            summary=self.summary,
        )
        if self.diff_hash != expected_hash:
            raise ValueError("TreeDiff diff_hash does not match its payload")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "scope": self.scope,
            "base": self.base.to_dict(),
            "target": self.target.to_dict(),
            "node_deltas": [delta.to_dict() for delta in self.node_deltas],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "summary": self.summary.to_dict(),
            "diff_hash": self.diff_hash,
        }


def diff_snapshots(before: CanonicalTree, after: CanonicalTree) -> TreeDiff:
    """Compare two ordered snapshots using stable ``node_id`` lineage only."""

    scope, warnings = _validate_snapshot_identity(before, after)
    before_nodes = _index_nodes(before, side="base")
    after_nodes = _index_nodes(after, side="target")

    node_deltas: list[NodeDelta] = []
    for node_id in sorted(before_nodes.keys() | after_nodes.keys()):
        before_node = before_nodes.get(node_id)
        after_node = after_nodes.get(node_id)
        if before_node is None:
            assert after_node is not None
            node_deltas.append(
                NodeDelta(
                    node_id=node_id,
                    status="ADDED",
                    before_ref=None,
                    after_ref=NodeRef.from_node(after_node),
                    change_types=("NODE_ADDED",),
                    field_deltas=(),
                )
            )
            continue
        if after_node is None:
            node_deltas.append(
                NodeDelta(
                    node_id=node_id,
                    status="REMOVED",
                    before_ref=NodeRef.from_node(before_node),
                    after_ref=None,
                    change_types=("NODE_REMOVED",),
                    field_deltas=(),
                )
            )
            continue

        change_types, field_deltas = _compare_node(before_node, after_node)
        if change_types:
            node_deltas.append(
                NodeDelta(
                    node_id=node_id,
                    status="MODIFIED",
                    before_ref=NodeRef.from_node(before_node),
                    after_ref=NodeRef.from_node(after_node),
                    change_types=change_types,
                    field_deltas=field_deltas,
                )
            )

    frozen_deltas = tuple(node_deltas)
    summary = _summarize(frozen_deltas)

    base_ref = SnapshotRef.from_tree(before)
    target_ref = SnapshotRef.from_tree(after)
    diff_hash = _diff_digest(
        schema_version=SCHEMA_VERSION,
        algorithm_version=ALGORITHM_VERSION,
        scope=scope,
        base=base_ref,
        target=target_ref,
        node_deltas=frozen_deltas,
        warnings=warnings,
        summary=summary,
    )
    return TreeDiff(
        schema_version=SCHEMA_VERSION,
        algorithm_version=ALGORITHM_VERSION,
        scope=scope,
        base=base_ref,
        target=target_ref,
        node_deltas=frozen_deltas,
        warnings=warnings,
        summary=summary,
        diff_hash=diff_hash,
    )


def _summarize(node_deltas: tuple[NodeDelta, ...]) -> DiffSummary:
    counts = Counter(
        change_type
        for delta in node_deltas
        for change_type in delta.change_types
    )
    ordered_counts = {
        change_type: counts[change_type]
        for change_type in CHANGE_TYPE_ORDER
        if counts[change_type]
    }
    return DiffSummary(
        node_delta_count=len(node_deltas),
        added_count=sum(delta.status == "ADDED" for delta in node_deltas),
        removed_count=sum(delta.status == "REMOVED" for delta in node_deltas),
        modified_count=sum(delta.status == "MODIFIED" for delta in node_deltas),
        change_type_counts=ordered_counts,
    )


def _diff_digest(
    *,
    schema_version: str,
    algorithm_version: str,
    scope: str,
    base: SnapshotRef,
    target: SnapshotRef,
    node_deltas: tuple[NodeDelta, ...],
    warnings: tuple[ComparisonIssue, ...],
    summary: DiffSummary,
) -> str:
    return canonical_digest(
        {
            "schema_version": schema_version,
            "algorithm_version": algorithm_version,
            "scope": scope,
            "base": base.to_dict(),
            "target": target.to_dict(),
            "node_deltas": [delta.to_dict() for delta in node_deltas],
            "warnings": [warning.to_dict() for warning in warnings],
            "summary": summary.to_dict(),
        }
    )


def _validate_snapshot_identity(
    before: CanonicalTree,
    after: CanonicalTree,
) -> tuple[str, tuple[ComparisonIssue, ...]]:
    if before.tree_id != after.tree_id:
        raise SnapshotDiffError(
            "TREE_ID_MISMATCH",
            "snapshots from different trees cannot be compared",
        )

    if before.schema_version != after.schema_version:
        raise SnapshotDiffError(
            "SNAPSHOT_SCHEMA_VERSION_MISMATCH",
            "snapshots using different canonical contract versions cannot be compared",
        )
    if before.schema_version != SUPPORTED_SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotDiffError(
            "UNSUPPORTED_SNAPSHOT_SCHEMA_VERSION",
            "snapshot contract version is not supported by this diff algorithm",
        )

    if before.source_map_type != after.source_map_type:
        raise SnapshotDiffError(
            "SOURCE_MAP_TYPE_MISMATCH",
            "resource and instance snapshots cannot be compared as one revision lineage",
        )

    if before.tree_version != after.tree_version:
        if before.version_record_id == after.version_record_id:
            raise SnapshotDiffError(
                "VERSION_RECORD_ID_REUSED",
                "different business versions must use different source record identities",
            )
        return "BUSINESS_VERSION", ()

    if before.version_record_id != after.version_record_id:
        raise SnapshotDiffError(
            "VERSION_RECORD_ID_CONFLICT",
            "the same business version has conflicting source record identities",
        )

    if (
        before.source_revision == after.source_revision
        and before.snapshot_hash != after.snapshot_hash
    ):
        raise SnapshotDiffError(
            "SNAPSHOT_CONTENT_CONFLICT",
            "the same business version and source revision have conflicting schema content",
        )
    warnings: tuple[ComparisonIssue, ...] = ()
    if after.source_revision < before.source_revision:
        warnings = (
            ComparisonIssue(
                code="SOURCE_REVISION_DECREASED",
                message=(
                    "target source_revision is lower than base; caller-provided "
                    "comparison order was preserved"
                ),
            ),
        )
    return "SAVE_REVISION", warnings


def _index_nodes(tree: CanonicalTree, *, side: str) -> dict[str, CanonicalNode]:
    indexed: dict[str, CanonicalNode] = {}
    for node in tree.nodes:
        if node.node_id in indexed:
            raise SnapshotDiffError(
                "DUPLICATE_NODE_ID",
                f"{side} snapshot contains duplicate node identities",
            )
        indexed[node.node_id] = node
    return indexed


def _compare_node(
    before: CanonicalNode,
    after: CanonicalNode,
) -> tuple[tuple[str, ...], tuple[FieldDelta, ...]]:
    changes: list[tuple[str, FieldDelta]] = []

    def add(
        change_type: str,
        field_path: str,
        before_value: Any,
        after_value: Any,
        category: str,
    ) -> None:
        if before_value != after_value:
            changes.append(
                (
                    change_type,
                    FieldDelta(
                        field_path=field_path,
                        before=before_value,
                        after=after_value,
                        category=category,
                    ),
                )
            )

    add(
        "NODE_MOVED",
        "parent_node_id",
        before.parent_node_id,
        after.parent_node_id,
        "STRUCTURAL",
    )
    add(
        "NODE_LABEL_CHANGED",
        "label",
        before.label,
        after.label,
        "SEMANTIC",
    )
    add(
        "NODE_NAME_CHANGED",
        "name",
        before.name,
        after.name,
        "SEMANTIC",
    )
    add(
        "NODE_KIND_CHANGED",
        "kind",
        before.kind,
        after.kind,
        "SEMANTIC",
    )
    if before.kind == after.kind:
        add(
            "SOURCE_TYPE_TOKEN_CHANGED",
            "source_node_type",
            before.source_node_type,
            after.source_node_type,
            "INFORMATIONAL",
        )

    before_contract = before.value_contract
    after_contract = after.value_contract
    if before_contract is None and after_contract is not None:
        add(
            "VALUE_CONTRACT_ADDED",
            "value_contract",
            None,
            after_contract.to_dict(),
            "SEMANTIC",
        )
    elif before_contract is not None and after_contract is None:
        add(
            "VALUE_CONTRACT_REMOVED",
            "value_contract",
            before_contract.to_dict(),
            None,
            "SEMANTIC",
        )
    elif before_contract is not None and after_contract is not None:
        add(
            "VALUE_TYPE_CHANGED",
            "value_contract.value_type",
            before_contract.value_type,
            after_contract.value_type,
            "SEMANTIC",
        )
        add(
            "CARDINALITY_CHANGED",
            "value_contract.cardinality",
            before_contract.cardinality,
            after_contract.cardinality,
            "SEMANTIC",
        )
        add(
            "CONSTRAINTS_CHANGED",
            "value_contract.constraints",
            before_contract.constraints,
            after_contract.constraints,
            "SEMANTIC",
        )
        add(
            "PLACEHOLDER_CHANGED",
            "value_contract.placeholder",
            before_contract.placeholder,
            after_contract.placeholder,
            "SEMANTIC",
        )

    add(
        "REMARK_CHANGED",
        "remark",
        before.remark,
        after.remark,
        "SEMANTIC",
    )
    add(
        "EXTENSION_CHANGED_UNCLASSIFIED",
        "extension",
        before.extension,
        after.extension,
        "UNCLASSIFIED",
    )
    add(
        "METADATA_CHANGED_UNCLASSIFIED",
        "metadata_extra",
        without_audit_fields(before.metadata_extra),
        without_audit_fields(after.metadata_extra),
        "UNCLASSIFIED",
    )
    add(
        "ORDER_OBSERVED_CHANGED",
        "order",
        before.order,
        after.order,
        "INFORMATIONAL",
    )

    changes.sort(key=lambda item: _CHANGE_TYPE_RANK[item[0]])
    return (
        tuple(change_type for change_type, _ in changes),
        tuple(field_delta for _, field_delta in changes),
    )


__all__ = [
    "ALGORITHM_VERSION",
    "CHANGE_TYPE_ORDER",
    "ComparisonIssue",
    "DiffSummary",
    "FieldDelta",
    "NodeDelta",
    "NodeRef",
    "SCHEMA_VERSION",
    "SnapshotDiffError",
    "SnapshotRef",
    "SUPPORTED_SNAPSHOT_SCHEMA_VERSION",
    "TreeDiff",
    "diff_snapshots",
]
