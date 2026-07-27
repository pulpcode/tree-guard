"""Deterministic history evidence mining over one saved revision interval."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from treeguard.diff import (
    CHANGE_TYPE_ORDER,
    NodeDelta,
    SnapshotRef,
    TreeDiff,
    diff_snapshots,
)
from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalNode, CanonicalTree, freeze_json, thaw_json


SCHEMA_VERSION = "history-review.v1"
ALGORITHM_VERSION = "treeguard.history-mining.v1"
POLICY_VERSION = "treeguard.history-review-policy.v1"

INFORMATIONAL_CHANGE_TYPES = {
    "ORDER_OBSERVED_CHANGED",
    "SOURCE_TYPE_TOKEN_CHANGED",
}
HIGH_RISK_CHANGE_TYPES = {
    "NODE_REMOVED",
    "NODE_MOVED",
    "NODE_KIND_CHANGED",
    "VALUE_CONTRACT_ADDED",
    "VALUE_CONTRACT_REMOVED",
    "VALUE_TYPE_CHANGED",
    "CARDINALITY_CHANGED",
    "CONSTRAINTS_CHANGED",
}
UNCLASSIFIED_CHANGE_TYPES = {
    "EXTENSION_CHANGED_UNCLASSIFIED",
    "METADATA_CHANGED_UNCLASSIFIED",
}
REASON_CODE_ORDER = (
    "INTERMEDIATE_REVISIONS_UNOBSERVED",
    "VALUE_MIGRATION_UNSUPPORTED",
    "VALUE_ABSENCE_UNPROVEN",
    "CONSTRAINT_SEMANTICS_UNCLASSIFIED",
    "VALUE_REVALIDATION_REQUIRED",
    "UNCLASSIFIED_CHANGE_PRESENT",
    "UNSUPPORTED_NODE_KIND_PRESENT",
)

_CHANGE_RANK = {value: index for index, value in enumerate(CHANGE_TYPE_ORDER)}
_REASON_RANK = {value: index for index, value in enumerate(REASON_CODE_ORDER)}
_RISK_ORDER = ("REVIEW_REQUIRED", "HIGH_RISK")
_GATE_ORDER = ("REVIEWABLE", "UNKNOWN", "BLOCKED")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class HistoryMiningError(ValueError):
    """The supplied interval cannot safely become history review evidence."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NodeEvidence:
    node_id: str
    change_types: tuple[str, ...]
    base_node_kind: str | None
    target_node_kind: str | None
    base_direct_value_envelope_observed: bool
    base_ancestor_value_envelope_observed: bool
    target_direct_value_envelope_observed: bool
    target_ancestor_value_envelope_observed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id:
            raise ValueError("node evidence requires a non-empty node_id")
        try:
            ordered_changes = _sort_change_types(set(self.change_types))
        except KeyError as exc:
            raise ValueError(f"unknown change type: {exc.args[0]}") from exc
        if (
            not self.change_types
            or len(self.change_types) != len(set(self.change_types))
            or self.change_types != ordered_changes
        ):
            raise ValueError("node evidence change_types must be unique and canonical")
        allowed_kinds = {None, "CONCEPT", "PROPERTY", "UNSUPPORTED"}
        if (
            self.base_node_kind not in allowed_kinds
            or self.target_node_kind not in allowed_kinds
            or (
                self.base_node_kind is None
                and self.target_node_kind is None
            )
        ):
            raise ValueError("node evidence kinds are invalid")
        observations = (
            self.base_direct_value_envelope_observed,
            self.base_ancestor_value_envelope_observed,
            self.target_direct_value_envelope_observed,
            self.target_ancestor_value_envelope_observed,
        )
        if any(not isinstance(value, bool) for value in observations):
            raise ValueError("node evidence observations must be booleans")

    @property
    def base_value_evidence_observed(self) -> bool:
        return (
            self.base_direct_value_envelope_observed
            or self.base_ancestor_value_envelope_observed
        )

    @property
    def target_value_evidence_observed(self) -> bool:
        return (
            self.target_direct_value_envelope_observed
            or self.target_ancestor_value_envelope_observed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "change_types": list(self.change_types),
            "base_node_kind": self.base_node_kind,
            "target_node_kind": self.target_node_kind,
            "base_direct_value_envelope_observed": (
                self.base_direct_value_envelope_observed
            ),
            "base_ancestor_value_envelope_observed": (
                self.base_ancestor_value_envelope_observed
            ),
            "target_direct_value_envelope_observed": (
                self.target_direct_value_envelope_observed
            ),
            "target_ancestor_value_envelope_observed": (
                self.target_ancestor_value_envelope_observed
            ),
        }


@dataclass(frozen=True, slots=True)
class ReviewCase:
    case_id: str
    cluster_status: str
    knowledge_status: str
    context_node_ids: tuple[str, ...]
    risk_level: str
    gate_status: str
    reason_codes: tuple[str, ...]
    node_evidence: tuple[NodeEvidence, ...]

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(item.node_id for item in self.node_evidence)

    @property
    def change_types(self) -> tuple[str, ...]:
        return _sort_change_types(
            {
                change_type
                for item in self.node_evidence
                for change_type in item.change_types
            }
        )

    def __post_init__(self) -> None:
        _validate_digest(self.case_id, "review case_id")
        if self.cluster_status != "STRUCTURAL_CANDIDATE":
            raise ValueError("review case must remain a structural candidate")
        if self.knowledge_status != "EVIDENCE_ONLY":
            raise ValueError("review case cannot claim Gold knowledge")
        _validate_sorted_ids(self.node_ids, "review case node_ids", required=True)
        _validate_sorted_ids(self.context_node_ids, "review case context_node_ids")
        if set(self.node_ids) & set(self.context_node_ids):
            raise ValueError("review case context cannot contain candidate nodes")
        expected_risk = (
            "HIGH_RISK"
            if any(item in HIGH_RISK_CHANGE_TYPES for item in self.change_types)
            else "REVIEW_REQUIRED"
        )
        if self.risk_level != expected_risk:
            raise ValueError("review case risk_level is inconsistent")
        if self.gate_status not in _GATE_ORDER:
            raise ValueError("review case gate_status is invalid")
        try:
            ordered_reasons = tuple(
                sorted(self.reason_codes, key=_REASON_RANK.__getitem__)
            )
        except KeyError as exc:
            raise ValueError(f"unknown history reason code: {exc.args[0]}") from exc
        if (
            self.reason_codes != ordered_reasons
            or len(self.reason_codes) != len(set(self.reason_codes))
        ):
            raise ValueError("review case reason_codes must be unique and canonical")
        if not isinstance(self.node_evidence, tuple):
            raise ValueError("review case node_evidence must be a tuple")
        expected_gate, expected_reasons = _evaluate_evidence_policy(
            self.node_evidence,
            interval_unobserved=(
                "INTERMEDIATE_REVISIONS_UNOBSERVED" in self.reason_codes
            ),
        )
        if self.gate_status != expected_gate or self.reason_codes != expected_reasons:
            raise ValueError("review case safety policy is inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "cluster_status": self.cluster_status,
            "knowledge_status": self.knowledge_status,
            "context_node_ids": list(self.context_node_ids),
            "risk_level": self.risk_level,
            "gate_status": self.gate_status,
            "reason_codes": list(self.reason_codes),
            "node_evidence": [item.to_dict() for item in self.node_evidence],
        }


@dataclass(frozen=True, slots=True)
class InformationalObservation:
    observation_id: str
    basis: str
    node_ids: tuple[str, ...]
    context_node_ids: tuple[str, ...]
    change_types: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_digest(self.observation_id, "informational observation_id")
        if self.basis not in {
            "SINGLE_NODE_INFORMATIONAL",
            "SIBLING_ORDER_CONTEXT",
        }:
            raise ValueError("informational observation basis is invalid")
        _validate_sorted_ids(
            self.node_ids,
            "informational observation node_ids",
            required=True,
        )
        _validate_sorted_ids(
            self.context_node_ids,
            "informational observation context_node_ids",
        )
        if set(self.node_ids) & set(self.context_node_ids):
            raise ValueError("informational context cannot contain observed nodes")
        if (
            not self.change_types
            or len(self.change_types) != len(set(self.change_types))
            or any(item not in INFORMATIONAL_CHANGE_TYPES for item in self.change_types)
            or self.change_types != _sort_change_types(set(self.change_types))
        ):
            raise ValueError("informational change_types must be unique and canonical")
        if self.basis == "SIBLING_ORDER_CONTEXT" and (
            len(self.node_ids) < 2
            or len(self.context_node_ids) != 1
            or self.change_types != ("ORDER_OBSERVED_CHANGED",)
        ):
            raise ValueError("sibling order observations require one shared context")
        if self.basis == "SINGLE_NODE_INFORMATIONAL" and len(self.node_ids) != 1:
            raise ValueError("single-node observations require exactly one node")

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "basis": self.basis,
            "node_ids": list(self.node_ids),
            "context_node_ids": list(self.context_node_ids),
            "change_types": list(self.change_types),
        }


@dataclass(frozen=True, slots=True)
class HistorySummary:
    source_node_delta_count: int
    review_case_count: int
    candidate_node_count: int
    informational_observation_count: int
    informational_only_node_count: int
    suppressed_informational_change_count: int
    risk_level_counts: Mapping[str, int]
    gate_status_counts: Mapping[str, int]
    reason_code_counts: Mapping[str, int]
    candidate_change_type_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        scalar_counts = (
            self.source_node_delta_count,
            self.review_case_count,
            self.candidate_node_count,
            self.informational_observation_count,
            self.informational_only_node_count,
            self.suppressed_informational_change_count,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in scalar_counts
        ):
            raise ValueError("history summary counts must be non-negative integers")
        if self.source_node_delta_count != (
            self.candidate_node_count + self.informational_only_node_count
        ):
            raise ValueError("history summary node accounting is inconsistent")
        count_fields = (
            ("risk_level_counts", set(_RISK_ORDER)),
            ("gate_status_counts", set(_GATE_ORDER)),
            ("reason_code_counts", set(REASON_CODE_ORDER)),
            ("candidate_change_type_counts", set(CHANGE_TYPE_ORDER)),
        )
        for field_name, allowed_keys in count_fields:
            counts = getattr(self, field_name)
            if not isinstance(counts, Mapping) or any(
                key not in allowed_keys
                or not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
                for key, value in counts.items()
            ):
                raise ValueError(f"history summary {field_name} is invalid")
            object.__setattr__(self, field_name, freeze_json(counts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_node_delta_count": self.source_node_delta_count,
            "review_case_count": self.review_case_count,
            "candidate_node_count": self.candidate_node_count,
            "informational_observation_count": self.informational_observation_count,
            "informational_only_node_count": self.informational_only_node_count,
            "suppressed_informational_change_count": (
                self.suppressed_informational_change_count
            ),
            "risk_level_counts": thaw_json(self.risk_level_counts),
            "gate_status_counts": thaw_json(self.gate_status_counts),
            "reason_code_counts": thaw_json(self.reason_code_counts),
            "candidate_change_type_counts": thaw_json(
                self.candidate_change_type_counts
            ),
        }


@dataclass(frozen=True, slots=True)
class HistoryReviewRun:
    schema_version: str
    algorithm_version: str
    policy_version: str
    knowledge_status: str
    source_diff_hash: str
    scope: str
    base: SnapshotRef
    target: SnapshotRef
    revision_gap: int
    interval_completeness: str
    reconstructs_historical_operations: bool
    review_cases: tuple[ReviewCase, ...]
    informational_observations: tuple[InformationalObservation, ...]
    summary: HistorySummary
    run_hash: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.review_cases, tuple)
            or not isinstance(self.informational_observations, tuple)
        ):
            raise ValueError("HistoryReviewRun artifacts must be immutable tuples")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported HistoryReviewRun schema_version")
        if self.algorithm_version != ALGORITHM_VERSION:
            raise ValueError("unsupported HistoryReviewRun algorithm_version")
        if self.policy_version != POLICY_VERSION:
            raise ValueError("unsupported HistoryReviewRun policy_version")
        if self.knowledge_status != "EVIDENCE_ONLY":
            raise ValueError("HistoryReviewRun cannot claim Gold knowledge")
        _validate_digest(self.source_diff_hash, "source_diff_hash")
        if self.scope != "SAVE_REVISION":
            raise ValueError("HistoryReviewRun scope must be SAVE_REVISION")
        for label, snapshot in (("base", self.base), ("target", self.target)):
            if snapshot.snapshot_schema_version != "tree-snapshot.v1":
                raise ValueError(f"{label} snapshot contract is unsupported")
            if (
                not isinstance(snapshot.source_revision, int)
                or isinstance(snapshot.source_revision, bool)
            ):
                raise ValueError(f"{label} source_revision must be an integer")
            if any(
                not isinstance(value, str) or not value
                for value in (
                    snapshot.tree_id,
                    snapshot.tree_version,
                    snapshot.version_record_id,
                )
            ):
                raise ValueError(f"{label} snapshot identity is invalid")
            _validate_digest(snapshot.snapshot_hash, f"{label} snapshot_hash")
        if (
            self.base.source_map_type != "resource"
            or self.target.source_map_type != "resource"
        ):
            raise ValueError("HistoryReviewRun snapshot refs must be resource")
        if (
            self.base.tree_id,
            self.base.tree_version,
            self.base.version_record_id,
        ) != (
            self.target.tree_id,
            self.target.tree_version,
            self.target.version_record_id,
        ):
            raise ValueError("HistoryReviewRun snapshot refs are from different lineages")
        expected_gap = self.target.source_revision - self.base.source_revision
        if (
            not isinstance(self.revision_gap, int)
            or isinstance(self.revision_gap, bool)
            or self.revision_gap != expected_gap
            or self.revision_gap < 1
        ):
            raise ValueError("HistoryReviewRun revision_gap is inconsistent")
        expected_completeness = "ADJACENT" if self.revision_gap == 1 else "GAPPED"
        if self.interval_completeness != expected_completeness:
            raise ValueError("HistoryReviewRun interval completeness is inconsistent")
        if self.reconstructs_historical_operations is not False:
            raise ValueError("HistoryReviewRun cannot claim operation reconstruction")
        interval_unobserved = self.interval_completeness == "GAPPED"
        if any(
            (
                "INTERMEDIATE_REVISIONS_UNOBSERVED" in item.reason_codes
            )
            != interval_unobserved
            for item in self.review_cases
        ):
            raise ValueError("review case revision-gap policy is inconsistent")

        case_keys = tuple(item.node_ids for item in self.review_cases)
        if case_keys != tuple(sorted(case_keys)):
            raise ValueError("review cases must use deterministic order")
        observation_keys = tuple(item.node_ids for item in self.informational_observations)
        if observation_keys != tuple(sorted(observation_keys)):
            raise ValueError("informational observations must use deterministic order")
        candidate_ids = tuple(
            node_id for item in self.review_cases for node_id in item.node_ids
        )
        informational_ids = tuple(
            node_id
            for item in self.informational_observations
            for node_id in item.node_ids
        )
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("review cases contain duplicate candidate nodes")
        if len(informational_ids) != len(set(informational_ids)):
            raise ValueError("informational observations contain duplicate nodes")
        if set(candidate_ids) & set(informational_ids):
            raise ValueError("candidate and informational nodes must be disjoint")
        for item in self.review_cases:
            if item.case_id != canonical_digest(
                _review_case_payload(
                    source_diff_hash=self.source_diff_hash,
                    context_node_ids=item.context_node_ids,
                    risk_level=item.risk_level,
                    gate_status=item.gate_status,
                    reason_codes=item.reason_codes,
                    node_evidence=item.node_evidence,
                )
            ):
                raise ValueError("review case_id does not match its payload")
        for item in self.informational_observations:
            if item.observation_id != canonical_digest(
                _observation_payload(
                    basis=item.basis,
                    node_ids=item.node_ids,
                    context_node_ids=item.context_node_ids,
                    change_types=item.change_types,
                    source_diff_hash=self.source_diff_hash,
                )
            ):
                raise ValueError("informational observation_id does not match its payload")
        _validate_summary_against_run(
            self.summary,
            self.review_cases,
            self.informational_observations,
        )
        payload = self.to_dict()
        supplied_hash = payload.pop("run_hash")
        _validate_digest(supplied_hash, "run_hash")
        if supplied_hash != canonical_digest(payload):
            raise ValueError("HistoryReviewRun run_hash does not match its payload")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "policy_version": self.policy_version,
            "knowledge_status": self.knowledge_status,
            "source_diff_hash": self.source_diff_hash,
            "scope": self.scope,
            "base": self.base.to_dict(),
            "target": self.target.to_dict(),
            "revision_gap": self.revision_gap,
            "interval_completeness": self.interval_completeness,
            "reconstructs_historical_operations": (
                self.reconstructs_historical_operations
            ),
            "review_cases": [item.to_dict() for item in self.review_cases],
            "informational_observations": [
                item.to_dict() for item in self.informational_observations
            ],
            "summary": self.summary.to_dict(),
            "run_hash": self.run_hash,
        }

    def aggregate_report(self) -> dict[str, Any]:
        """Return counts only; the full run remains an internal sensitive artifact."""

        return {
            "report_version": "history-review-aggregate.v1",
            "knowledge_status": self.knowledge_status,
            "interval_completeness": self.interval_completeness,
            "reconstructs_historical_operations": (
                self.reconstructs_historical_operations
            ),
            "summary": {
                "source_node_delta_count": self.summary.source_node_delta_count,
                "review_case_count": self.summary.review_case_count,
                "candidate_node_count": self.summary.candidate_node_count,
                "informational_observation_count": (
                    self.summary.informational_observation_count
                ),
                "informational_only_node_count": (
                    self.summary.informational_only_node_count
                ),
                "suppressed_informational_change_count": (
                    self.summary.suppressed_informational_change_count
                ),
                "risk_level_counts": _allowlisted_counts(
                    self.summary.risk_level_counts,
                    _RISK_ORDER,
                ),
                "gate_status_counts": _allowlisted_counts(
                    self.summary.gate_status_counts,
                    _GATE_ORDER,
                ),
                "reason_code_counts": _allowlisted_counts(
                    self.summary.reason_code_counts,
                    REASON_CODE_ORDER,
                ),
                "candidate_change_type_counts": _allowlisted_counts(
                    self.summary.candidate_change_type_counts,
                    CHANGE_TYPE_ORDER,
                ),
            },
        }


def mine_history_pair(
    before: CanonicalTree,
    after: CanonicalTree,
) -> HistoryReviewRun:
    """Build review evidence from one forward save-revision interval."""

    tree_diff = diff_snapshots(before, after)
    if before.source_map_type != "resource" or after.source_map_type != "resource":
        raise HistoryMiningError(
            "HISTORY_SOURCE_NOT_RESOURCE",
            "history review mining accepts resource snapshots only",
        )
    if tree_diff.scope != "SAVE_REVISION":
        raise HistoryMiningError(
            "HISTORY_SCOPE_NOT_SAVE_REVISION",
            "history review v1 accepts one business version at a time",
        )
    if after.source_revision <= before.source_revision:
        raise HistoryMiningError(
            "HISTORY_REVISION_NOT_FORWARD",
            "target source_revision must be greater than base",
        )
    if tree_diff.warnings:
        raise HistoryMiningError(
            "HISTORY_DIFF_WARNING",
            "history review refuses a TreeDiff containing warnings",
        )

    revision_gap = after.source_revision - before.source_revision
    interval_completeness = "ADJACENT" if revision_gap == 1 else "GAPPED"
    before_nodes = {node.node_id: node for node in before.nodes}
    after_nodes = {node.node_id: node for node in after.nodes}

    candidate_types: dict[str, tuple[str, ...]] = {}
    candidate_deltas: dict[str, NodeDelta] = {}
    informational_deltas: list[NodeDelta] = []
    suppressed_informational_count = 0
    for delta in tree_diff.node_deltas:
        affected_nodes = tuple(
            node
            for node in (before_nodes.get(delta.node_id), after_nodes.get(delta.node_id))
            if node is not None
        )
        has_unsupported_kind = any(node.kind == "UNSUPPORTED" for node in affected_nodes)
        actionable = tuple(
            change_type
            for change_type in delta.change_types
            if change_type not in INFORMATIONAL_CHANGE_TYPES
        )
        if not actionable and has_unsupported_kind:
            actionable = delta.change_types
        if actionable:
            candidate_deltas[delta.node_id] = delta
            candidate_types[delta.node_id] = actionable
            suppressed_informational_count += sum(
                change_type in INFORMATIONAL_CHANGE_TYPES
                for change_type in delta.change_types
                if change_type not in actionable
            )
        else:
            informational_deltas.append(delta)

    components = _structural_components(
        candidate_deltas,
        before,
        after,
    )
    review_cases = tuple(
        _build_review_case(
            node_ids=component,
            candidate_deltas=candidate_deltas,
            candidate_types=candidate_types,
            before_nodes=before_nodes,
            after_nodes=after_nodes,
            before=before,
            after=after,
            tree_diff=tree_diff,
            interval_completeness=interval_completeness,
        )
        for component in components
    )
    informational_observations = _build_informational_observations(
        informational_deltas,
        before,
        after,
        tree_diff.diff_hash,
    )
    summary = _build_summary(
        tree_diff=tree_diff,
        review_cases=review_cases,
        informational_observations=informational_observations,
        candidate_types=candidate_types,
        informational_deltas=informational_deltas,
        suppressed_informational_count=suppressed_informational_count,
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "policy_version": POLICY_VERSION,
        "knowledge_status": "EVIDENCE_ONLY",
        "source_diff_hash": tree_diff.diff_hash,
        "scope": tree_diff.scope,
        "base": tree_diff.base.to_dict(),
        "target": tree_diff.target.to_dict(),
        "revision_gap": revision_gap,
        "interval_completeness": interval_completeness,
        "reconstructs_historical_operations": False,
        "review_cases": [item.to_dict() for item in review_cases],
        "informational_observations": [
            item.to_dict() for item in informational_observations
        ],
        "summary": summary.to_dict(),
    }
    return HistoryReviewRun(
        schema_version=SCHEMA_VERSION,
        algorithm_version=ALGORITHM_VERSION,
        policy_version=POLICY_VERSION,
        knowledge_status="EVIDENCE_ONLY",
        source_diff_hash=tree_diff.diff_hash,
        scope=tree_diff.scope,
        base=tree_diff.base,
        target=tree_diff.target,
        revision_gap=revision_gap,
        interval_completeness=interval_completeness,
        reconstructs_historical_operations=False,
        review_cases=review_cases,
        informational_observations=informational_observations,
        summary=summary,
        run_hash=canonical_digest(payload),
    )


def verify_history_run_against_snapshots(
    run: HistoryReviewRun,
    before: CanonicalTree,
    after: CanonicalTree,
) -> None:
    """Recompute evidence from trusted snapshots and reject a forged artifact."""

    expected = mine_history_pair(before, after)
    if run.to_dict() != expected.to_dict():
        raise HistoryMiningError(
            "HISTORY_RUN_SOURCE_MISMATCH",
            "history review does not match deterministic trusted-snapshot replay",
        )


def _structural_components(
    candidate_deltas: Mapping[str, NodeDelta],
    before: CanonicalTree,
    after: CanonicalTree,
) -> tuple[tuple[str, ...], ...]:
    node_ids = sorted(candidate_deltas)
    parents = {node_id: node_id for node_id in node_ids}

    def find(node_id: str) -> str:
        while parents[node_id] != node_id:
            parents[node_id] = parents[parents[node_id]]
            node_id = parents[node_id]
        return node_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        lower, higher = sorted((left_root, right_root))
        parents[higher] = lower

    root_ids = set(before.root_node_ids) | set(after.root_node_ids)
    for tree in (before, after):
        for node in tree.nodes:
            parent_id = node.parent_node_id
            if (
                node.node_id not in candidate_deltas
                or parent_id not in candidate_deltas
                or parent_id in root_ids
                or "NODE_MOVED" in candidate_deltas[node.node_id].change_types
            ):
                continue
            union(node.node_id, parent_id)

    grouped: dict[str, list[str]] = {}
    for node_id in node_ids:
        grouped.setdefault(find(node_id), []).append(node_id)
    return tuple(sorted(tuple(sorted(group)) for group in grouped.values()))


def _build_review_case(
    *,
    node_ids: tuple[str, ...],
    candidate_deltas: Mapping[str, NodeDelta],
    candidate_types: Mapping[str, tuple[str, ...]],
    before_nodes: Mapping[str, CanonicalNode],
    after_nodes: Mapping[str, CanonicalNode],
    before: CanonicalTree,
    after: CanonicalTree,
    tree_diff: TreeDiff,
    interval_completeness: str,
) -> ReviewCase:
    change_types = _sort_change_types(
        {
            change_type
            for node_id in node_ids
            for change_type in candidate_types[node_id]
        }
    )
    risk_level = (
        "HIGH_RISK"
        if any(item in HIGH_RISK_CHANGE_TYPES for item in change_types)
        else "REVIEW_REQUIRED"
    )

    node_evidence: list[NodeEvidence] = []
    for node_id in node_ids:
        base_node = before_nodes.get(node_id)
        target_node = after_nodes.get(node_id)
        base_direct_value_observed = bool(
            base_node is not None and base_node.has_value_envelope
        )
        target_direct_value_observed = bool(
            target_node is not None and target_node.has_value_envelope
        )
        evidence = NodeEvidence(
            node_id=node_id,
            change_types=candidate_types[node_id],
            base_node_kind=base_node.kind if base_node is not None else None,
            target_node_kind=target_node.kind if target_node is not None else None,
            base_direct_value_envelope_observed=base_direct_value_observed,
            base_ancestor_value_envelope_observed=(
                _ancestor_class_value_envelope_observed(node_id, before_nodes)
            ),
            target_direct_value_envelope_observed=target_direct_value_observed,
            target_ancestor_value_envelope_observed=(
                _ancestor_class_value_envelope_observed(node_id, after_nodes)
            ),
        )
        node_evidence.append(evidence)

    context_node_ids = _external_parent_ids(node_ids, before, after)
    ordered_evidence = tuple(sorted(node_evidence, key=lambda item: item.node_id))
    gate_status, ordered_reasons = _evaluate_evidence_policy(
        ordered_evidence,
        interval_unobserved=interval_completeness == "GAPPED",
    )
    case_payload = _review_case_payload(
        source_diff_hash=tree_diff.diff_hash,
        context_node_ids=context_node_ids,
        risk_level=risk_level,
        gate_status=gate_status,
        reason_codes=ordered_reasons,
        node_evidence=ordered_evidence,
    )
    return ReviewCase(
        case_id=canonical_digest(case_payload),
        cluster_status="STRUCTURAL_CANDIDATE",
        knowledge_status="EVIDENCE_ONLY",
        context_node_ids=context_node_ids,
        risk_level=risk_level,
        gate_status=gate_status,
        reason_codes=ordered_reasons,
        node_evidence=ordered_evidence,
    )


def _build_informational_observations(
    deltas: list[NodeDelta],
    before: CanonicalTree,
    after: CanonicalTree,
    source_diff_hash: str,
) -> tuple[InformationalObservation, ...]:
    before_nodes = {node.node_id: node for node in before.nodes}
    after_nodes = {node.node_id: node for node in after.nodes}
    order_groups: dict[str, list[NodeDelta]] = {}
    singletons: list[NodeDelta] = []
    for delta in deltas:
        base_node = before_nodes.get(delta.node_id)
        target_node = after_nodes.get(delta.node_id)
        if (
            delta.change_types == ("ORDER_OBSERVED_CHANGED",)
            and base_node is not None
            and target_node is not None
            and base_node.parent_node_id is not None
            and base_node.parent_node_id == target_node.parent_node_id
        ):
            order_groups.setdefault(base_node.parent_node_id, []).append(delta)
        else:
            singletons.append(delta)

    observations: list[InformationalObservation] = []
    for parent_id, members in sorted(order_groups.items()):
        if len(members) == 1:
            singletons.extend(members)
            continue
        node_ids = tuple(sorted(delta.node_id for delta in members))
        observations.append(
            _make_observation(
                basis="SIBLING_ORDER_CONTEXT",
                node_ids=node_ids,
                context_node_ids=(parent_id,),
                change_types=("ORDER_OBSERVED_CHANGED",),
                source_diff_hash=source_diff_hash,
            )
        )

    for delta in singletons:
        node_ids = (delta.node_id,)
        observations.append(
            _make_observation(
                basis="SINGLE_NODE_INFORMATIONAL",
                node_ids=node_ids,
                context_node_ids=_external_parent_ids(node_ids, before, after),
                change_types=delta.change_types,
                source_diff_hash=source_diff_hash,
            )
        )
    return tuple(sorted(observations, key=lambda item: item.node_ids))


def _make_observation(
    *,
    basis: str,
    node_ids: tuple[str, ...],
    context_node_ids: tuple[str, ...],
    change_types: tuple[str, ...],
    source_diff_hash: str,
) -> InformationalObservation:
    payload = _observation_payload(
        basis=basis,
        node_ids=node_ids,
        context_node_ids=context_node_ids,
        change_types=change_types,
        source_diff_hash=source_diff_hash,
    )
    return InformationalObservation(
        observation_id=canonical_digest(payload),
        basis=basis,
        node_ids=node_ids,
        context_node_ids=context_node_ids,
        change_types=change_types,
    )


def _external_parent_ids(
    node_ids: tuple[str, ...],
    before: CanonicalTree,
    after: CanonicalTree,
) -> tuple[str, ...]:
    members = set(node_ids)
    parents = {
        node.parent_node_id
        for tree in (before, after)
        for node in tree.nodes
        if node.node_id in members
        and node.parent_node_id is not None
        and node.parent_node_id not in members
    }
    return tuple(sorted(parents))


def _build_summary(
    *,
    tree_diff: TreeDiff,
    review_cases: tuple[ReviewCase, ...],
    informational_observations: tuple[InformationalObservation, ...],
    candidate_types: Mapping[str, tuple[str, ...]],
    informational_deltas: list[NodeDelta],
    suppressed_informational_count: int,
) -> HistorySummary:
    risk_counts = Counter(item.risk_level for item in review_cases)
    gate_counts = Counter(item.gate_status for item in review_cases)
    reason_counts = Counter(
        reason for item in review_cases for reason in item.reason_codes
    )
    change_counts = Counter(
        change_type
        for change_types in candidate_types.values()
        for change_type in change_types
    )
    return HistorySummary(
        source_node_delta_count=len(tree_diff.node_deltas),
        review_case_count=len(review_cases),
        candidate_node_count=len(candidate_types),
        informational_observation_count=len(informational_observations),
        informational_only_node_count=len(informational_deltas),
        suppressed_informational_change_count=suppressed_informational_count,
        risk_level_counts=_ordered_counts(risk_counts, _RISK_ORDER),
        gate_status_counts=_ordered_counts(gate_counts, _GATE_ORDER),
        reason_code_counts=_ordered_counts(reason_counts, REASON_CODE_ORDER),
        candidate_change_type_counts=_ordered_counts(
            change_counts,
            CHANGE_TYPE_ORDER,
        ),
    )


def _ordered_counts(
    counts: Counter[str],
    order: tuple[str, ...],
) -> dict[str, int]:
    return {key: counts[key] for key in order if counts[key]}


def _sort_change_types(values: set[str]) -> tuple[str, ...]:
    return tuple(sorted(values, key=_CHANGE_RANK.__getitem__))


def _ancestor_class_value_envelope_observed(
    node_id: str,
    nodes: Mapping[str, CanonicalNode],
) -> bool:
    node = nodes.get(node_id)
    seen: set[str] = set()
    parent_id = node.parent_node_id if node is not None else None
    while parent_id is not None and parent_id not in seen:
        seen.add(parent_id)
        parent = nodes.get(parent_id)
        if parent is None:
            return False
        if (
            parent.kind == "PROPERTY"
            and parent.value_contract is not None
            and parent.value_contract.value_type.lower() == "class"
            and parent.has_value_envelope
        ):
            return True
        parent_id = parent.parent_node_id
    return False


def _evaluate_evidence_policy(
    node_evidence: tuple[NodeEvidence, ...],
    *,
    interval_unobserved: bool,
) -> tuple[str, tuple[str, ...]]:
    reason_codes: set[str] = set()
    if interval_unobserved:
        reason_codes.add("INTERMEDIATE_REVISIONS_UNOBSERVED")

    for evidence in node_evidence:
        node_change_types = set(evidence.change_types)
        if (
            evidence.base_node_kind == "UNSUPPORTED"
            or evidence.target_node_kind == "UNSUPPORTED"
        ):
            reason_codes.add("UNSUPPORTED_NODE_KIND_PRESENT")
        if node_change_types & UNCLASSIFIED_CHANGE_TYPES:
            reason_codes.add("UNCLASSIFIED_CHANGE_PRESENT")
        if "CONSTRAINTS_CHANGED" in node_change_types:
            reason_codes.add("CONSTRAINT_SEMANTICS_UNCLASSIFIED")
            if evidence.base_value_evidence_observed:
                reason_codes.add("VALUE_REVALIDATION_REQUIRED")

        shape_breaking = bool(
            node_change_types
            & {
                "VALUE_TYPE_CHANGED",
                "CARDINALITY_CHANGED",
                "VALUE_CONTRACT_REMOVED",
            }
        )
        if (
            "NODE_KIND_CHANGED" in node_change_types
            and evidence.base_node_kind == "PROPERTY"
        ):
            shape_breaking = True
        if (
            "NODE_REMOVED" in node_change_types
            and evidence.base_node_kind == "PROPERTY"
        ):
            shape_breaking = True
        if shape_breaking:
            reason_codes.add(
                "VALUE_MIGRATION_UNSUPPORTED"
                if evidence.base_value_evidence_observed
                else "VALUE_ABSENCE_UNPROVEN"
            )

    ordered_reasons = tuple(sorted(reason_codes, key=_REASON_RANK.__getitem__))
    if "VALUE_MIGRATION_UNSUPPORTED" in reason_codes:
        gate_status = "BLOCKED"
    elif reason_codes:
        gate_status = "UNKNOWN"
    else:
        gate_status = "REVIEWABLE"
    return gate_status, ordered_reasons


def _review_case_payload(
    *,
    source_diff_hash: str,
    context_node_ids: tuple[str, ...],
    risk_level: str,
    gate_status: str,
    reason_codes: tuple[str, ...],
    node_evidence: tuple[NodeEvidence, ...],
) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "source_diff_hash": source_diff_hash,
        "cluster_status": "STRUCTURAL_CANDIDATE",
        "knowledge_status": "EVIDENCE_ONLY",
        "context_node_ids": list(context_node_ids),
        "risk_level": risk_level,
        "gate_status": gate_status,
        "reason_codes": list(reason_codes),
        "node_evidence": [item.to_dict() for item in node_evidence],
    }


def _observation_payload(
    *,
    basis: str,
    node_ids: tuple[str, ...],
    context_node_ids: tuple[str, ...],
    change_types: tuple[str, ...],
    source_diff_hash: str,
) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "source_diff_hash": source_diff_hash,
        "basis": basis,
        "node_ids": list(node_ids),
        "context_node_ids": list(context_node_ids),
        "change_types": list(change_types),
    }


def _validate_summary_against_run(
    summary: HistorySummary,
    review_cases: tuple[ReviewCase, ...],
    informational_observations: tuple[InformationalObservation, ...],
) -> None:
    candidate_node_count = sum(len(item.node_ids) for item in review_cases)
    informational_node_count = sum(
        len(item.node_ids) for item in informational_observations
    )
    expected_scalars = (
        (summary.review_case_count, len(review_cases)),
        (summary.candidate_node_count, candidate_node_count),
        (
            summary.informational_observation_count,
            len(informational_observations),
        ),
        (summary.informational_only_node_count, informational_node_count),
    )
    if any(actual != expected for actual, expected in expected_scalars):
        raise ValueError("history summary does not match run artifacts")

    expected_risk = _ordered_counts(
        Counter(item.risk_level for item in review_cases),
        _RISK_ORDER,
    )
    expected_gate = _ordered_counts(
        Counter(item.gate_status for item in review_cases),
        _GATE_ORDER,
    )
    expected_reasons = _ordered_counts(
        Counter(reason for item in review_cases for reason in item.reason_codes),
        REASON_CODE_ORDER,
    )
    if thaw_json(summary.risk_level_counts) != expected_risk:
        raise ValueError("history summary risk counts are inconsistent")
    if thaw_json(summary.gate_status_counts) != expected_gate:
        raise ValueError("history summary gate counts are inconsistent")
    if thaw_json(summary.reason_code_counts) != expected_reasons:
        raise ValueError("history summary reason counts are inconsistent")

    expected_change_counts = _ordered_counts(
        Counter(
            change_type
            for item in review_cases
            for evidence in item.node_evidence
            for change_type in evidence.change_types
        ),
        CHANGE_TYPE_ORDER,
    )
    if thaw_json(summary.candidate_change_type_counts) != expected_change_counts:
        raise ValueError("history summary change counts are inconsistent")
    if summary.suppressed_informational_change_count > (
        len(INFORMATIONAL_CHANGE_TYPES) * candidate_node_count
    ):
        raise ValueError("history summary suppressed count is inconsistent")


def _allowlisted_counts(
    counts: Mapping[str, int],
    order: tuple[str, ...],
) -> dict[str, int]:
    return {key: counts[key] for key in order if key in counts}


def _validate_digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _validate_sorted_ids(
    values: tuple[str, ...],
    field_name: str,
    *,
    required: bool = False,
) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if required and not values:
        raise ValueError(f"{field_name} cannot be empty")
    if (
        any(not isinstance(value, str) or not value for value in values)
        or len(values) != len(set(values))
        or values != tuple(sorted(values))
    ):
        raise ValueError(f"{field_name} must be unique and sorted")


__all__ = [
    "ALGORITHM_VERSION",
    "HistoryMiningError",
    "HistoryReviewRun",
    "HistorySummary",
    "InformationalObservation",
    "POLICY_VERSION",
    "REASON_CODE_ORDER",
    "ReviewCase",
    "SCHEMA_VERSION",
    "mine_history_pair",
    "NodeEvidence",
    "verify_history_run_against_snapshots",
]
