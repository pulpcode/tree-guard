"""Allowlisted, size-bounded model input for business-version review."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from treeguard.business_review import (
    BusinessVersionReviewRun,
    verify_business_version_review_against_snapshots,
)
from treeguard.hashing import canonical_digest
from treeguard.lexical import text_terms
from treeguard.models import CanonicalNode, CanonicalTree, freeze_json, thaw_json


SCHEMA_VERSION = "llm-evidence-pack.v1"
PROJECTION_VERSION = "treeguard.llm-projection.v1"
TASK_TYPE = "BUSINESS_VERSION_REVIEW"
DEFAULT_MAX_CANDIDATES = 5
DEFAULT_MAX_PAYLOAD_CHARS = 48_000

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[FXC][0-9]{3}$")
_NODE_VIEW_KEYS = {
    "kind",
    "label",
    "name",
    "path",
    "value_type",
    "cardinality",
    "has_constraints",
}
_FOCUS_KEYS = {"ref", "change_types", "before", "after", "value_evidence"}
_CONTEXT_KEYS = {"ref", "node"}
_VALUE_EVIDENCE_KEYS = {
    "base_direct_observed",
    "base_ancestor_observed",
    "target_direct_observed",
    "target_ancestor_observed",
}
_MODEL_PAYLOAD_KEYS = (
    "schema_version",
    "projection_version",
    "task_type",
    "comparison_semantics",
    "risk_level",
    "gate_status",
    "reason_codes",
    "focus_nodes",
    "context_nodes",
    "candidate_nodes",
)


class EvidenceProjectionError(ValueError):
    """The trusted review evidence cannot be projected into a safe model input."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LLMEvidencePack:
    schema_version: str
    projection_version: str
    task_type: str
    source_run_hash: str
    case_id: str
    base_version: str
    target_version: str
    comparison_semantics: str
    risk_level: str
    gate_status: str
    reason_codes: tuple[str, ...]
    focus_nodes: tuple[Mapping[str, Any], ...]
    context_nodes: tuple[Mapping[str, Any], ...]
    candidate_nodes: tuple[Mapping[str, Any], ...]
    reference_to_node_id: MappingProxyType
    pack_hash: str

    @property
    def allowed_refs(self) -> frozenset[str]:
        return frozenset(self.reference_to_node_id)

    @property
    def candidate_refs(self) -> frozenset[str]:
        return frozenset(item["ref"] for item in self.candidate_nodes)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Detach and recheck the complete pack at a trust boundary."""

        if not isinstance(self.reference_to_node_id, MappingProxyType):
            raise ValueError("LLM evidence reference mapping must be immutable")
        object.__setattr__(
            self,
            "focus_nodes",
            freeze_json(thaw_json(self.focus_nodes)),
        )
        object.__setattr__(
            self,
            "context_nodes",
            freeze_json(thaw_json(self.context_nodes)),
        )
        object.__setattr__(
            self,
            "candidate_nodes",
            freeze_json(thaw_json(self.candidate_nodes)),
        )
        object.__setattr__(
            self,
            "reference_to_node_id",
            MappingProxyType(dict(self.reference_to_node_id)),
        )

        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported LLM evidence schema_version")
        if self.projection_version != PROJECTION_VERSION:
            raise ValueError("unsupported LLM evidence projection_version")
        if self.task_type != TASK_TYPE:
            raise ValueError("unsupported LLM evidence task_type")
        if (
            not _DIGEST.fullmatch(self.source_run_hash)
            or not _DIGEST.fullmatch(self.case_id)
        ):
            raise ValueError("LLM evidence source hashes must be SHA-256 digests")
        if not self.base_version or not self.target_version:
            raise ValueError("LLM evidence versions must be non-empty")
        if self.comparison_semantics != "ENDPOINT_NET_CHANGE":
            raise ValueError("unsupported LLM evidence comparison semantics")
        if self.risk_level not in {"REVIEW_REQUIRED", "HIGH_RISK"}:
            raise ValueError("unsupported LLM evidence risk level")
        if self.gate_status not in {"REVIEWABLE", "UNKNOWN", "BLOCKED"}:
            raise ValueError("unsupported LLM evidence gate status")
        if (
            not isinstance(self.reason_codes, tuple)
            or any(not isinstance(item, str) or not item for item in self.reason_codes)
            or len(self.reason_codes) != len(set(self.reason_codes))
        ):
            raise ValueError("LLM evidence reason codes must be unique strings")
        _validate_projected_groups(
            self.focus_nodes,
            self.context_nodes,
            self.candidate_nodes,
        )
        if not isinstance(self.reference_to_node_id, MappingProxyType):
            raise ValueError("LLM evidence reference mapping must be immutable")
        if any(
            not isinstance(ref, str)
            or not _REFERENCE.fullmatch(ref)
            or not isinstance(node_id, str)
            or not node_id
            for ref, node_id in self.reference_to_node_id.items()
        ):
            raise ValueError("LLM evidence reference mapping is invalid")
        if len(self.reference_to_node_id) != len(
            set(self.reference_to_node_id.values())
        ):
            raise ValueError("LLM evidence node references must be one-to-one")
        expected_refs = {
            item["ref"]
            for group in (self.focus_nodes, self.context_nodes, self.candidate_nodes)
            for item in group
        }
        if expected_refs != set(self.reference_to_node_id):
            raise ValueError("LLM evidence references are inconsistent")
        payload = self._payload()
        if self.pack_hash != canonical_digest(payload):
            raise ValueError("LLM evidence pack_hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "projection_version": self.projection_version,
            "task_type": self.task_type,
            "source_run_hash": self.source_run_hash,
            "case_id": self.case_id,
            "base_version": self.base_version,
            "target_version": self.target_version,
            "comparison_semantics": self.comparison_semantics,
            "risk_level": self.risk_level,
            "gate_status": self.gate_status,
            "reason_codes": list(self.reason_codes),
            "focus_nodes": thaw_json(self.focus_nodes),
            "context_nodes": thaw_json(self.context_nodes),
            "candidate_nodes": thaw_json(self.candidate_nodes),
            "reference_to_node_id": dict(self.reference_to_node_id),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["pack_hash"] = self.pack_hash
        return payload

    def to_model_dict(self) -> dict[str, Any]:
        """Return only the external model view, without stable internal identifiers."""

        payload = self._payload()
        return {key: payload[key] for key in _MODEL_PAYLOAD_KEYS}


def build_business_review_evidence_pack(
    run: BusinessVersionReviewRun,
    before: CanonicalTree,
    after: CanonicalTree,
    *,
    case_index: int = 0,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    max_payload_chars: int = DEFAULT_MAX_PAYLOAD_CHARS,
) -> LLMEvidencePack:
    """Project one trusted ReviewCase without raw VALUE or unclassified metadata."""

    verify_business_version_review_against_snapshots(run, before, after)
    if (
        not isinstance(case_index, int)
        or isinstance(case_index, bool)
        or case_index < 0
        or case_index >= len(run.review_cases)
    ):
        raise EvidenceProjectionError(
            "EVIDENCE_CASE_INDEX_INVALID",
            "case_index does not identify a review case",
        )
    if (
        not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or max_candidates < 0
    ):
        raise EvidenceProjectionError(
            "EVIDENCE_CANDIDATE_LIMIT_INVALID",
            "max_candidates must be a non-negative integer",
        )
    if (
        not isinstance(max_payload_chars, int)
        or isinstance(max_payload_chars, bool)
        or max_payload_chars < 1
    ):
        raise EvidenceProjectionError(
            "EVIDENCE_SIZE_LIMIT_INVALID",
            "max_payload_chars must be a positive integer",
        )

    case = run.review_cases[case_index]
    before_nodes = {node.node_id: node for node in before.nodes}
    after_nodes = {node.node_id: node for node in after.nodes}
    reference_map: dict[str, str] = {}

    focus_items: list[dict[str, Any]] = []
    for index, evidence in enumerate(case.node_evidence, start=1):
        ref = f"F{index:03d}"
        reference_map[ref] = evidence.node_id
        focus_items.append(
            {
                "ref": ref,
                "change_types": list(evidence.change_types),
                "before": _node_view(before_nodes.get(evidence.node_id)),
                "after": _node_view(after_nodes.get(evidence.node_id)),
                "value_evidence": {
                    "base_direct_observed": (
                        evidence.base_direct_value_envelope_observed
                    ),
                    "base_ancestor_observed": (
                        evidence.base_ancestor_value_envelope_observed
                    ),
                    "target_direct_observed": (
                        evidence.target_direct_value_envelope_observed
                    ),
                    "target_ancestor_observed": (
                        evidence.target_ancestor_value_envelope_observed
                    ),
                },
            }
        )

    context_items: list[dict[str, Any]] = []
    for index, node_id in enumerate(case.context_node_ids, start=1):
        ref = f"X{index:03d}"
        reference_map[ref] = node_id
        context_items.append(
            {
                "ref": ref,
                "node": _node_view(after_nodes.get(node_id) or before_nodes.get(node_id)),
            }
        )

    candidate_items: list[dict[str, Any]] = []
    focus_ids = set(case.node_ids)
    ranked_candidates = _rank_candidates(
        tuple(
            node
            for node_id in case.node_ids
            for node in (before_nodes.get(node_id), after_nodes.get(node_id))
            if node is not None
        ),
        after,
        excluded_node_ids=focus_ids | set(case.context_node_ids),
    )
    for index, node in enumerate(ranked_candidates[:max_candidates], start=1):
        ref = f"C{index:03d}"
        reference_map[ref] = node.node_id
        candidate_items.append({"ref": ref, "node": _node_view(node)})

    payload = {
        "schema_version": SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "task_type": TASK_TYPE,
        "source_run_hash": run.run_hash,
        "case_id": case.case_id,
        "base_version": before.tree_version,
        "target_version": after.tree_version,
        "comparison_semantics": run.comparison_semantics,
        "risk_level": case.risk_level,
        "gate_status": case.gate_status,
        "reason_codes": list(case.reason_codes),
        "focus_nodes": focus_items,
        "context_nodes": context_items,
        "candidate_nodes": candidate_items,
        "reference_to_node_id": dict(reference_map),
    }
    model_payload = {key: payload[key] for key in _MODEL_PAYLOAD_KEYS}
    encoded = json.dumps(
        model_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded) > max_payload_chars:
        raise EvidenceProjectionError(
            "EVIDENCE_CONTEXT_BUDGET_EXCEEDED",
            "allowlisted evidence exceeds the configured model-input budget",
        )

    frozen_focus = tuple(freeze_json(item) for item in focus_items)
    frozen_context = tuple(freeze_json(item) for item in context_items)
    frozen_candidates = tuple(freeze_json(item) for item in candidate_items)
    return LLMEvidencePack(
        schema_version=SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        task_type=TASK_TYPE,
        source_run_hash=run.run_hash,
        case_id=case.case_id,
        base_version=before.tree_version,
        target_version=after.tree_version,
        comparison_semantics=run.comparison_semantics,
        risk_level=case.risk_level,
        gate_status=case.gate_status,
        reason_codes=case.reason_codes,
        focus_nodes=frozen_focus,
        context_nodes=frozen_context,
        candidate_nodes=frozen_candidates,
        reference_to_node_id=MappingProxyType(dict(reference_map)),
        pack_hash=canonical_digest(payload),
    )


def _validate_projected_groups(
    focus_nodes: tuple[Mapping[str, Any], ...],
    context_nodes: tuple[Mapping[str, Any], ...],
    candidate_nodes: tuple[Mapping[str, Any], ...],
) -> None:
    if (
        not isinstance(focus_nodes, tuple)
        or not focus_nodes
        or not isinstance(context_nodes, tuple)
        or not isinstance(candidate_nodes, tuple)
    ):
        raise ValueError("LLM evidence node groups must be immutable tuples")

    for item in focus_nodes:
        _validate_mapping(item, _FOCUS_KEYS, "focus node")
        if not _valid_ref(item["ref"], "F"):
            raise ValueError("LLM evidence focus reference is invalid")
        change_types = item["change_types"]
        if (
            not isinstance(change_types, tuple)
            or not change_types
            or any(not isinstance(value, str) or not value for value in change_types)
            or len(change_types) != len(set(change_types))
        ):
            raise ValueError("LLM evidence focus change types are invalid")
        _validate_node_view(item["before"], allow_none=True)
        _validate_node_view(item["after"], allow_none=True)
        if item["before"] is None and item["after"] is None:
            raise ValueError("LLM evidence focus must have a before or after view")
        value_evidence = item["value_evidence"]
        _validate_mapping(value_evidence, _VALUE_EVIDENCE_KEYS, "value evidence")
        if any(not isinstance(value, bool) for value in value_evidence.values()):
            raise ValueError("LLM evidence VALUE observations must be booleans")

    for expected_prefix, group, group_name in (
        ("X", context_nodes, "context node"),
        ("C", candidate_nodes, "candidate node"),
    ):
        for item in group:
            _validate_mapping(item, _CONTEXT_KEYS, group_name)
            if not _valid_ref(item["ref"], expected_prefix):
                raise ValueError(f"LLM evidence {group_name} reference is invalid")
            _validate_node_view(item["node"], allow_none=False)

    refs = [
        item["ref"]
        for group in (focus_nodes, context_nodes, candidate_nodes)
        for item in group
    ]
    if len(refs) != len(set(refs)):
        raise ValueError("LLM evidence node references must be unique")


def _validate_node_view(value: Any, *, allow_none: bool) -> None:
    if value is None and allow_none:
        return
    _validate_mapping(value, _NODE_VIEW_KEYS, "node view")
    if any(
        not isinstance(value[field], str)
        for field in ("kind", "label", "name")
    ):
        raise ValueError("LLM evidence node text fields must be strings")
    path = value["path"]
    if not isinstance(path, tuple) or any(not isinstance(item, str) for item in path):
        raise ValueError("LLM evidence node path must be an immutable string tuple")
    if any(
        value[field] is not None and not isinstance(value[field], str)
        for field in ("value_type", "cardinality")
    ):
        raise ValueError("LLM evidence value contract fields are invalid")
    if not isinstance(value["has_constraints"], bool):
        raise ValueError("LLM evidence constraint signal must be boolean")


def _validate_mapping(value: Any, keys: set[str], name: str) -> None:
    if not isinstance(value, MappingProxyType) or set(value) != keys:
        raise ValueError(f"LLM evidence {name} must use exact immutable fields")


def _valid_ref(value: Any, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and _REFERENCE.fullmatch(value) is not None
    )


def _node_view(node: CanonicalNode | None) -> dict[str, Any] | None:
    if node is None:
        return None
    contract = node.value_contract
    return {
        "kind": node.kind,
        "label": node.label,
        "name": node.name,
        "path": list(node.path_labels),
        "value_type": contract.value_type if contract is not None else None,
        "cardinality": contract.cardinality if contract is not None else None,
        "has_constraints": bool(contract and contract.constraints),
    }


def _rank_candidates(
    focus_nodes: tuple[CanonicalNode, ...],
    tree: CanonicalTree,
    *,
    excluded_node_ids: set[str],
) -> tuple[CanonicalNode, ...]:
    query_terms = set().union(*(_node_terms(node) for node in focus_nodes))
    focus_kinds = {node.kind for node in focus_nodes}
    focus_value_types = {
        node.value_contract.value_type
        for node in focus_nodes
        if node.value_contract is not None
    }
    scored: list[tuple[int, str, CanonicalNode]] = []
    for node in tree.nodes:
        if node.node_id in excluded_node_ids or node.kind == "UNSUPPORTED":
            continue
        overlap = len(query_terms & _node_terms(node))
        if overlap == 0:
            continue
        score = overlap * 10
        if node.kind in focus_kinds:
            score += 2
        if (
            node.value_contract is not None
            and node.value_contract.value_type in focus_value_types
        ):
            score += 1
        scored.append((-score, node.node_id, node))
    return tuple(item[2] for item in sorted(scored))


def _node_terms(node: CanonicalNode) -> set[str]:
    return text_terms(" ".join((node.name, node.label, *node.path_labels)))


__all__ = [
    "DEFAULT_MAX_CANDIDATES",
    "DEFAULT_MAX_PAYLOAD_CHARS",
    "EvidenceProjectionError",
    "LLMEvidencePack",
    "PROJECTION_VERSION",
    "SCHEMA_VERSION",
    "TASK_TYPE",
    "build_business_review_evidence_pack",
]
