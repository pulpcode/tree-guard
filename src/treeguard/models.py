"""Dependency-free canonical contracts used by the file adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


JsonObject = Mapping[str, Any]


def freeze_json(value: Any) -> Any:
    """Recursively detach JSON data from caller-owned mutable containers."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    """Return ordinary JSON containers without exposing canonical internals."""

    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A source-format issue. Locations remain internal to the importing process."""

    severity: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class ValueContract:
    value_type: str
    cardinality: str
    constraints: JsonObject
    placeholder: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", freeze_json(self.constraints))

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "constraints": thaw_json(self.constraints),
            "placeholder": self.placeholder,
        }


@dataclass(frozen=True, slots=True)
class CanonicalNode:
    node_id: str
    parent_node_id: str | None
    child_node_ids: tuple[str, ...]
    kind: str
    source_node_type: str
    label: str
    name: str
    path_labels: tuple[str, ...]
    source_route: str | None
    order: int | None
    value_contract: ValueContract | None
    remark: str | None
    extension: JsonObject
    metadata_extra: JsonObject
    has_instance_value: bool
    node_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "extension", freeze_json(self.extension))
        object.__setattr__(self, "metadata_extra", freeze_json(self.metadata_extra))

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_node_id": self.parent_node_id,
            "child_node_ids": list(self.child_node_ids),
            "kind": self.kind,
            "source_node_type": self.source_node_type,
            "label": self.label,
            "name": self.name,
            "path_labels": list(self.path_labels),
            "source_route": self.source_route,
            "order": self.order,
            "value_contract": (
                self.value_contract.to_dict() if self.value_contract is not None else None
            ),
            "remark": self.remark,
            "extension": thaw_json(self.extension),
            "metadata_extra": thaw_json(self.metadata_extra),
            "has_instance_value": self.has_instance_value,
            "node_hash": self.node_hash,
        }


@dataclass(frozen=True, slots=True)
class CanonicalTree:
    schema_version: str
    source_format: str
    tree_id: str
    tree_version: str
    source_revision: int | None
    version_record_id: str | None
    root_node_ids: tuple[str, ...]
    nodes: tuple[CanonicalNode, ...]
    snapshot_hash: str
    source_metadata_extra: JsonObject

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_metadata_extra",
            freeze_json(self.source_metadata_extra),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_format": self.source_format,
            "tree_id": self.tree_id,
            "tree_version": self.tree_version,
            "source_revision": self.source_revision,
            "version_record_id": self.version_record_id,
            "root_node_ids": list(self.root_node_ids),
            "nodes": [node.to_dict() for node in self.nodes],
            "snapshot_hash": self.snapshot_hash,
            "source_metadata_extra": thaw_json(self.source_metadata_extra),
        }


@dataclass(frozen=True, slots=True)
class ImportResult:
    tree: CanonicalTree | None
    issues: tuple[ValidationIssue, ...]
    observed_node_count: int
    observed_value_count: int
    source_format: str

    @property
    def is_valid(self) -> bool:
        return self.tree is not None and not any(
            issue.severity == "ERROR" for issue in self.issues
        )

    def conformance_report(self) -> dict[str, Any]:
        """Return an aggregate-only report suitable for whitelisted diagnostics."""

        severity_counts = {"ERROR": 0, "WARNING": 0}
        code_counts: dict[str, int] = {}
        for issue in self.issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
            code_counts[issue.code] = code_counts.get(issue.code, 0) + 1

        return {
            "report_version": "treeguard-conformance.v1",
            "valid": self.is_valid,
            "source_format": self.source_format,
            "node_count": self.observed_node_count,
            "value_envelope_count": self.observed_value_count,
            "root_count": len(self.tree.root_node_ids) if self.tree is not None else None,
            "severity_counts": severity_counts,
            "issue_code_counts": dict(sorted(code_counts.items())),
        }
