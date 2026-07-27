"""Adapter for the observed information-tree export format."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from treeguard.hashing import canonical_digest, without_audit_fields
from treeguard.models import (
    CanonicalNode,
    CanonicalTree,
    ImportResult,
    JsonObject,
    ValueContract,
    freeze_json,
    thaw_json,
)
from treeguard.validation import IssueCollector, duplicate_non_null


MAX_DEPTH = 128
MAX_NODES = 100_000
ROUTE_SEPARATOR = "/-/"
OBSERVED_VALUE_TYPES = {
    "boolean",
    "class",
    "entity_code",
    "float",
    "integer",
    "space_code",
    "string",
    "time_code",
}
MAPPED_TREE_METADATA = {
    "concurrent_version",
    "id",
    "map_id",
    "map_type",
    "version",
}
MAPPED_NODE_METADATA = {
    "extension",
    "is_list",
    "node_id",
    "node_label",
    "node_label_route",
    "node_name",
    "node_order",
    "node_type",
    "parent_node_id",
    "remark",
    "value_constraints",
    "value_placeholder",
    "value_type",
}


class TreeFormatError(ValueError):
    """Raised when a file cannot be decoded into a tree document."""


@dataclass(slots=True)
class _NodeDraft:
    node_id: str
    parent_node_id: str | None
    child_node_ids: list[str] = field(default_factory=list)
    kind: str = "UNSUPPORTED"
    source_node_type: str = ""
    label: str = ""
    name: str = ""
    path_labels: tuple[str, ...] = ()
    source_route: str | None = None
    order: int | None = None
    value_contract: ValueContract | None = None
    remark: str | None = None
    extension: JsonObject = field(default_factory=dict)
    metadata_extra: JsonObject = field(default_factory=dict)
    has_value_envelope: bool = False


def load_tree_export(
    path: str | Path,
    *,
    allow_curl_transcript: bool = False,
) -> ImportResult:
    """Load a pure JSON export, or an explicitly allowed one-line curl transcript."""

    source_path = Path(path)
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TreeFormatError(f"cannot read tree export: {exc}") from exc

    source_hint = "file"
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        if not allow_curl_transcript:
            raise TreeFormatError(
                "expected a pure JSON document; curl transcripts require explicit opt-in"
            ) from exc
        first_line, separator, response_text = text.partition("\n")
        if not separator or not first_line.lstrip().startswith("curl "):
            raise TreeFormatError(
                "transcript mode only accepts one curl command line followed by JSON"
            ) from exc
        try:
            document = json.loads(response_text)
        except json.JSONDecodeError as response_exc:
            raise TreeFormatError("curl transcript response is not valid JSON") from response_exc
        source_hint = "curl-transcript"

    return adapt_tree_document(document, source_hint=source_hint)


def adapt_tree_document(
    document: Any,
    *,
    source_hint: str = "memory",
) -> ImportResult:
    """Convert a direct export or API response envelope to a canonical flat tree."""

    if not isinstance(document, dict):
        raise TreeFormatError("tree document must be a JSON object")

    source_format = "tree-export.v1"
    payload = document
    if isinstance(document.get("data"), dict) and {
        "metadata",
        "map_topology",
    }.issubset(document["data"]):
        payload = document["data"]
        source_format = "tree-api-response.v1"
    if source_hint == "curl-transcript":
        source_format += "+curl-transcript"

    metadata = payload.get("metadata")
    topology = payload.get("map_topology")
    if not isinstance(metadata, dict):
        raise TreeFormatError("tree metadata must be a JSON object")
    if not isinstance(topology, dict):
        raise TreeFormatError("map_topology must be a JSON object")

    collector = IssueCollector()
    tree_id = _required_string(metadata, "map_id", "tree.metadata", collector)
    tree_version = _required_string(metadata, "version", "tree.metadata", collector)
    version_record_id = _required_string(metadata, "id", "tree.metadata", collector)
    source_map_type = _required_string(
        metadata,
        "map_type",
        "tree.metadata",
        collector,
    ).lower()
    normalized_map_type = source_map_type
    if normalized_map_type == "instance":
        collector.warning(
            "INSTANCE_TREE_SCHEMA_PROJECTION",
            "tree.metadata",
            "instance input cannot be used for governance Patch generation",
        )
    elif normalized_map_type and normalized_map_type != "resource":
        collector.warning(
            "UNSUPPORTED_MAP_TYPE",
            "tree.metadata",
            "unknown map_type cannot be used for governance Patch generation",
        )
    source_revision = metadata.get("concurrent_version")
    if not _is_integer(source_revision):
        collector.error(
            "INVALID_SOURCE_REVISION",
            "tree.metadata",
            "concurrent_version must be an integer",
        )
        source_revision = 0

    if len(topology) != 1:
        collector.error(
            "INVALID_ROOT_COUNT",
            "tree.map_topology",
            "exactly one topology root is required",
        )

    drafts: list[_NodeDraft] = []
    seen_ids: set[str] = set()
    seen_routes: set[str] = set()
    value_count = 0
    visited_node_count = 0
    node_limit_reached = False

    def walk_node(
        wrapper: Any,
        *,
        container_key: str,
        expected_parent_id: str | None,
        parent_path: tuple[str, ...],
        depth: int,
    ) -> _NodeDraft | None:
        nonlocal node_limit_reached, value_count, visited_node_count

        if node_limit_reached:
            return None
        if visited_node_count >= MAX_NODES:
            collector.error(
                "MAX_NODE_COUNT_EXCEEDED",
                "tree.map_topology",
                "tree is too large",
            )
            node_limit_reached = True
            return None
        location = f"nodes[{visited_node_count}]"
        visited_node_count += 1
        if depth > MAX_DEPTH:
            collector.error("MAX_DEPTH_EXCEEDED", location, "tree nesting is too deep")
            return None
        if not isinstance(wrapper, dict):
            collector.error("INVALID_NODE_OBJECT", location, "node wrapper must be an object")
            return None
        node_metadata = wrapper.get("metadata")
        if not isinstance(node_metadata, dict):
            collector.error("INVALID_NODE_METADATA", location, "node metadata must be an object")
            return None

        unknown_wrapper_fields = set(wrapper) - {"metadata", "subnodes", "value"}
        if unknown_wrapper_fields:
            collector.error(
                "UNCLASSIFIED_NODE_ENVELOPE_FIELD",
                location,
                "unknown node wrapper fields require explicit classification",
            )

        node_id = _required_string(node_metadata, "node_id", location, collector)
        if not node_id:
            node_id = f"__invalid_node_{len(drafts)}"
        elif node_id in seen_ids:
            collector.error("DUPLICATE_NODE_ID", location, "node_id must be globally unique")
        seen_ids.add(node_id)

        label = _required_string(node_metadata, "node_label", location, collector)
        name = _required_string(node_metadata, "node_name", location, collector)
        if label and container_key != label:
            collector.warning(
                "CONTAINER_KEY_LABEL_MISMATCH",
                location,
                "container key differs from node_label",
            )

        actual_parent = node_metadata.get("parent_node_id")
        if expected_parent_id is None:
            if actual_parent not in (None, ""):
                collector.error(
                    "ROOT_PARENT_PRESENT",
                    location,
                    "root node must not declare a parent",
                )
            parent_node_id = None
        else:
            parent_node_id = _optional_string(actual_parent)
            if parent_node_id != expected_parent_id:
                collector.error(
                    "PARENT_ID_MISMATCH",
                    location,
                    "declared parent_node_id differs from the containing node",
                )

        path_labels = parent_path + (label,)
        expected_route = ROUTE_SEPARATOR.join(path_labels)
        source_route = _optional_string(node_metadata.get("node_label_route"))
        if source_route is not None:
            if source_route in seen_routes:
                collector.warning(
                    "DUPLICATE_SOURCE_ROUTE",
                    location,
                    "node_label_route is not unique",
                )
            seen_routes.add(source_route)
            if source_route != expected_route:
                collector.warning(
                    "SOURCE_ROUTE_MISMATCH",
                    location,
                    "stored node_label_route differs from the nested structure",
                )

        source_node_type = node_metadata.get("node_type")
        if not isinstance(source_node_type, str) or not source_node_type:
            collector.error("INVALID_NODE_TYPE", location, "node_type must be a string")
            source_node_type = ""
        normalized_type = source_node_type.lower()
        if normalized_type == "concept":
            kind = "CONCEPT"
        elif normalized_type == "property":
            kind = "PROPERTY"
        else:
            kind = "UNSUPPORTED"
            collector.warning(
                "UNSUPPORTED_NODE_TYPE",
                location,
                "unknown node_type is preserved but cannot enter Patch generation",
            )

        raw_order = node_metadata.get("node_order")
        order = raw_order if _is_integer(raw_order) else None
        if order is None:
            collector.warning("MISSING_NODE_ORDER", location, "node_order is missing or invalid")

        value_contract: ValueContract | None = None
        if kind == "PROPERTY":
            value_type = node_metadata.get("value_type")
            is_list = node_metadata.get("is_list")
            if not isinstance(value_type, str) or not value_type:
                collector.error(
                    "MISSING_VALUE_TYPE",
                    location,
                    "property nodes require a string value_type",
                )
                value_type = "unknown"
            elif value_type not in OBSERVED_VALUE_TYPES:
                collector.warning(
                    "UNOBSERVED_VALUE_TYPE",
                    location,
                    "value_type was not present in the supplied format samples",
                )
            if not isinstance(is_list, bool):
                collector.error(
                    "INVALID_CARDINALITY",
                    location,
                    "property nodes require boolean is_list",
                )
                is_list = False
            constraints = node_metadata.get("value_constraints", {})
            if not isinstance(constraints, dict):
                collector.warning(
                    "INVALID_CONSTRAINTS",
                    location,
                    "value_constraints is not an object and was omitted",
                )
                constraints = {}
            placeholder = node_metadata.get("value_placeholder")
            if placeholder is not None and not isinstance(placeholder, str):
                collector.warning(
                    "INVALID_VALUE_PLACEHOLDER",
                    location,
                    "value_placeholder is not a string and was omitted",
                )
                placeholder = None
            value_contract = ValueContract(
                value_type=value_type,
                cardinality="MULTIPLE" if is_list else "SINGLE",
                constraints=constraints,
                placeholder=placeholder,
            )
        elif kind == "CONCEPT" and (
            "value_type" in node_metadata or "is_list" in node_metadata
        ):
            collector.warning(
                "CONCEPT_VALUE_CONTRACT_PRESENT",
                location,
                "concept node unexpectedly contains property value fields",
            )

        remark = node_metadata.get("remark")
        if remark is not None and not isinstance(remark, str):
            collector.warning("INVALID_REMARK", location, "remark is not a string")
            remark = None
        extension = node_metadata.get("extension", {})
        if not isinstance(extension, dict):
            collector.warning("INVALID_EXTENSION", location, "extension is not an object")
            extension = {}
        extension = freeze_json(extension)

        has_value_envelope = "value" in wrapper and wrapper.get("value") is not None
        if has_value_envelope:
            value_count += 1
            _validate_value_envelope(wrapper.get("value"), node_metadata, location, collector)

        metadata_extra = freeze_json(
            {
                key: value
                for key, value in node_metadata.items()
                if key not in MAPPED_NODE_METADATA
            }
        )
        draft = _NodeDraft(
            node_id=node_id,
            parent_node_id=parent_node_id,
            kind=kind,
            source_node_type=source_node_type,
            label=label,
            name=name,
            path_labels=path_labels,
            source_route=source_route,
            order=order,
            value_contract=value_contract,
            remark=remark,
            extension=extension,
            metadata_extra=metadata_extra,
            has_value_envelope=has_value_envelope,
        )
        drafts.append(draft)

        subnodes = wrapper.get("subnodes", {})
        if subnodes is None:
            subnodes = {}
        if not isinstance(subnodes, dict):
            collector.error("INVALID_SUBNODES", location, "subnodes must be an object")
            return draft
        if subnodes and kind == "PROPERTY":
            value_type = value_contract.value_type if value_contract is not None else None
            if value_type != "class":
                collector.error(
                    "NON_CLASS_PROPERTY_HAS_CHILDREN",
                    location,
                    "only class properties may contain schema children",
                )

        child_drafts: list[_NodeDraft] = []
        for child_key, child_wrapper in subnodes.items():
            child = walk_node(
                child_wrapper,
                container_key=str(child_key),
                expected_parent_id=node_id,
                parent_path=path_labels,
                depth=depth + 1,
            )
            if child is not None:
                child_drafts.append(child)
                if kind == "PROPERTY" and child.kind != "PROPERTY":
                    collector.error(
                        "PROPERTY_HAS_NON_PROPERTY_CHILD",
                        location,
                        "class property children must be property nodes",
                    )
            if node_limit_reached:
                break

        if duplicate_non_null([child.order for child in child_drafts]):
            collector.warning(
                "DUPLICATE_SIBLING_ORDER",
                location,
                "two or more children share node_order",
            )
        child_labels = [child.label for child in child_drafts if child.label]
        if len(child_labels) != len(set(child_labels)):
            collector.error(
                "DUPLICATE_SIBLING_LABEL",
                location,
                "node_label must be unique among siblings",
            )
        child_drafts.sort(
            key=lambda child: (
                child.order is None,
                child.order if child.order is not None else 0,
                child.node_id,
            )
        )
        draft.child_node_ids.extend(child.node_id for child in child_drafts)
        return draft

    root_drafts: list[_NodeDraft] = []
    for root_key, root_wrapper in topology.items():
        root = walk_node(
            root_wrapper,
            container_key=str(root_key),
            expected_parent_id=None,
            parent_path=(),
            depth=0,
        )
        if root is not None:
            root_drafts.append(root)
        if node_limit_reached:
            break

    if collector.has_errors:
        return ImportResult(
            tree=None,
            issues=collector.issues,
            observed_node_count=visited_node_count,
            observed_value_count=value_count,
            source_format=source_format,
        )

    canonical_nodes: list[CanonicalNode] = []
    for draft in drafts:
        value_contract_dict = (
            draft.value_contract.to_dict() if draft.value_contract is not None else None
        )
        node_hash = canonical_digest(
            {
                "node_id": draft.node_id,
                "parent_node_id": draft.parent_node_id,
                "child_node_ids": draft.child_node_ids,
                "kind": draft.kind,
                "source_node_type": draft.source_node_type,
                "label": draft.label,
                "name": draft.name,
                "path_labels": draft.path_labels,
                "order": draft.order,
                "value_contract": value_contract_dict,
                "remark": draft.remark,
                "extension": thaw_json(draft.extension),
                "metadata_extra": without_audit_fields(draft.metadata_extra),
            }
        )
        canonical_nodes.append(
            CanonicalNode(
                node_id=draft.node_id,
                parent_node_id=draft.parent_node_id,
                child_node_ids=tuple(draft.child_node_ids),
                kind=draft.kind,
                source_node_type=draft.source_node_type,
                label=draft.label,
                name=draft.name,
                path_labels=draft.path_labels,
                source_route=draft.source_route,
                order=draft.order,
                value_contract=draft.value_contract,
                remark=draft.remark,
                extension=draft.extension,
                metadata_extra=draft.metadata_extra,
                has_value_envelope=draft.has_value_envelope,
                node_hash=node_hash,
            )
        )

    canonical_nodes.sort(key=lambda node: node.node_id)
    root_drafts.sort(key=lambda root: root.node_id)

    snapshot_hash = canonical_digest(
        {
            "tree_id": tree_id,
            "root_node_ids": sorted(root.node_id for root in root_drafts),
            "nodes": sorted(
                (
                    {"node_id": node.node_id, "node_hash": node.node_hash}
                    for node in canonical_nodes
                ),
                key=lambda item: item["node_id"],
            ),
        }
    )
    tree_metadata_extra = {
        key: value for key, value in metadata.items() if key not in MAPPED_TREE_METADATA
    }
    tree = CanonicalTree(
        schema_version="tree-snapshot.v1",
        source_format=source_format,
        source_map_type=source_map_type,
        tree_id=tree_id,
        tree_version=tree_version,
        source_revision=source_revision,
        version_record_id=version_record_id,
        root_node_ids=tuple(root.node_id for root in root_drafts),
        nodes=tuple(canonical_nodes),
        snapshot_hash=snapshot_hash,
        source_metadata_extra=tree_metadata_extra,
    )
    return ImportResult(
        tree=tree,
        issues=collector.issues,
        observed_node_count=visited_node_count,
        observed_value_count=value_count,
        source_format=source_format,
    )


def _required_string(
    obj: JsonObject,
    key: str,
    location: str,
    collector: IssueCollector,
) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        collector.error("MISSING_REQUIRED_STRING", location, f"{key} must be a string")
        return ""
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_value_envelope(
    value: Any,
    node_metadata: JsonObject,
    location: str,
    collector: IssueCollector,
) -> None:
    """Validate only linkage metadata; instance payload is intentionally not retained."""

    if not isinstance(value, dict):
        collector.warning("INVALID_VALUE_ENVELOPE", location, "value is not an object")
        return
    value_metadata = value.get("metadata")
    if not isinstance(value_metadata, dict):
        collector.warning(
            "MISSING_VALUE_METADATA",
            location,
            "value metadata is missing; instance payload was still discarded",
        )
        return
    checks = (
        ("node_id", "VALUE_NODE_ID_MISMATCH"),
        ("value_type", "VALUE_TYPE_MISMATCH"),
        ("is_list", "VALUE_CARDINALITY_MISMATCH"),
    )
    for key, code in checks:
        if value_metadata.get(key) != node_metadata.get(key):
            collector.warning(code, location, f"value metadata {key} differs from property")
