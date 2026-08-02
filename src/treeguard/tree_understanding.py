"""Deterministic full-tree diagnostics for later bounded LLM understanding."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from treeguard.hashing import canonical_digest
from treeguard.model_safety import contains_internal_identifier
from treeguard.models import CanonicalNode, CanonicalTree, freeze_json, thaw_json


SCHEMA_VERSION = "tree-diagnostic-profile.v1"
ALGORITHM_VERSION = "treeguard.tree-diagnostic-profile.v1"
AGGREGATE_REPORT_VERSION = "treeguard-tree-diagnostic-aggregate.v1"
SUPPORTED_TREE_SCHEMA_VERSION = "tree-snapshot.v1"
MODEL_INPUT_SCHEMA_VERSION = "tree-understanding-model-input.v1"
MODEL_OUTPUT_SCHEMA_VERSION = "tree-understanding-model-output.v1"
DRAFT_SCHEMA_VERSION = "tree-understanding-draft.v1"
PROJECTION_VERSION = "treeguard.tree-understanding-projection.v1"
TASK_TYPE = "TREE_VALIDATION_PREPARATION"
MODEL_PROVENANCE_STATUS = "UNVERIFIED_MODEL_OUTPUT"
REVIEW_STATUS = "PENDING_HUMAN_REVIEW"
DEFAULT_MAX_MODEL_NODES = 64
DEFAULT_MAX_MODEL_FINDINGS = 20
MAX_MODEL_NODES = 128
MAX_MODEL_FINDINGS = 50
MAX_MODEL_INPUT_CHARS = 48_000
MAX_VIRTUAL_SCENARIOS = 8

SCENARIO_PLAN_SCHEMA_VERSION = "scenario-preparation-plan.v1"
SCENARIO_PLAN_ALGORITHM_VERSION = "treeguard.scenario-preparation-plan.v1"
SCENARIO_MODEL_INPUT_SCHEMA_VERSION = "scenario-preparation-model-input.v1"
SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION = "scenario-preparation-model-output.v1"
SCENARIO_CANDIDATE_SCHEMA_VERSION = "scenario-preparation-candidate.v1"
SCENARIO_BATCH_SCHEMA_VERSION = "scenario-preparation-batch.v1"
SCENARIO_PROJECTION_VERSION = "treeguard.scenario-preparation-projection.v1"
SCENARIO_TASK_TYPE = "TREE_CHANGE_SCENARIO_PREPARATION"
SCENARIO_STAGE_NOT_RUN = "NOT_RUN"
SCENARIO_REQUIREMENT_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_REQUIREMENT_TEXT__"
)
SCENARIO_ASPECT_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_REQUESTED_ASPECT__"
)
SCENARIO_RATIONALE_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_RATIONALE__"
)
SCENARIO_EVIDENCE_GAP_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_EVIDENCE_GAP__"
)
SCENARIO_MODEL_TEXT_SENTINELS = (
    SCENARIO_REQUIREMENT_TEMPLATE_SENTINEL,
    SCENARIO_ASPECT_TEMPLATE_SENTINEL,
    SCENARIO_RATIONALE_TEMPLATE_SENTINEL,
    SCENARIO_EVIDENCE_GAP_TEMPLATE_SENTINEL,
)
DEFAULT_MAX_PLAN_UNITS = 16
MAX_PLAN_UNITS = 32
DEFAULT_SCENARIO_MODEL_NODES = 48
MAX_SCENARIO_MODEL_NODES = 64
MAX_SCENARIO_MODEL_INPUT_CHARS = 48_000

SCENARIO_FAMILY_ORDER = (
    "CLEAR_EXISTING_REUSE",
    "NEW_NODE_PLACEMENT",
    "HOMONYM_CLARIFICATION",
    "WRONG_PARENT_OR_CROSS_BRANCH",
    "KIND_CONFLICT",
    "CARDINALITY_CONFLICT",
    "INSUFFICIENT_EVIDENCE",
    "UNBOUNDED_COMBINATION",
)
SCENARIO_FAMILIES = set(SCENARIO_FAMILY_ORDER)
PLANNING_MODES = {"BRANCH_LOCAL", "CONTRAST", "AMBIGUITY"}
TARGET_STAGE_ORDER = ("INTENT", "RETRIEVAL", "RECOMMENDATION")
TARGET_STAGES = set(TARGET_STAGE_ORDER)
PLAN_UNIT_ROLES = {"RISK_CHALLENGE", "BRANCH_COVERAGE"}
FAMILY_PLAN_STATUSES = {"PLANNED", "NOT_APPLICABLE", "OMITTED_BUDGET"}
FAMILY_PREPARATION_OUTCOMES = {
    "CANDIDATE_READY",
    "FAILED",
    "NOT_EXECUTED",
    "NOT_APPLICABLE",
    "OMITTED_BUDGET",
}
PARENT_HINT_POLICIES = {
    "ABSENT",
    "CORRECT",
    "INTENTIONALLY_CONFLICTING",
}
REQUEST_HINT_POLICIES = {
    "ABSENT",
    "MATCHING",
    "INTENTIONALLY_CONFLICTING",
    "SEED_DEFINED",
}
BATCH_STATUSES = {"SUCCESS", "PARTIAL", "FAILED"}
PREPARATION_SOURCE_STATUSES = {
    "UNVERIFIED_MODEL_GENERATION",
    "FIXTURE_REPLAY",
}
SCENARIO_PROJECTION_UNIT_FAILURE_CODES = {
    "SCENARIO_PREPARATION_PROJECTION_REQUIRED_SCOPE_TOO_LARGE",
    "SCENARIO_PREPARATION_PROJECTION_TOO_LARGE",
}

FINDING_DISPOSITIONS = {
    "POTENTIAL_ISSUE",
    "EXPECTED_PATTERN",
    "NEED_EVIDENCE",
}
GENERATION_STATUSES = {
    "SCENARIOS_PROPOSED",
    "NEED_EVIDENCE",
    "ABSTAIN",
}
VALIDATION_GOALS = {
    "RETRIEVAL",
    "SEMANTIC_DISTINCTION",
    "PLACEMENT",
    "TYPE_CARDINALITY",
    "CLARIFICATION",
    "CROSS_BRANCH_REUSE",
}

FINDING_CODE_ORDER = (
    "NAME_REUSED_ACROSS_PATHS",
    "NAME_CONTRACT_CONFLICT",
    "CHILD_CONTRACT_VECTOR_REUSED",
)
_FINDING_CODE_RANK = {
    code: index for index, code in enumerate(FINDING_CODE_ORDER)
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_NODE_REFERENCE = re.compile(r"^N(?:00[1-9]|0[1-9][0-9]|1[01][0-9]|12[0-8])$")
_FINDING_REFERENCE = re.compile(r"^D(?:00[1-9]|0[1-4][0-9]|050)$")
_SCENARIO_REFERENCE = re.compile(r"^S00[1-8]$")
_PLAN_UNIT_REFERENCE = re.compile(
    r"^U(?:00[1-9]|0[12][0-9]|03[0-2])$"
)
_RUN_CANDIDATE_REFERENCE = re.compile(
    r"^C(?:00[1-9]|0[12][0-9]|03[0-2])$"
)
_TEMPORARY_PROJECTION_REFERENCE_IN_TEXT = re.compile(
    r"(?<![A-Za-z0-9_])[NDS][0-9]{3}(?![A-Za-z0-9_])"
)
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SURROGATE_CHARACTER = re.compile(r"[\ud800-\udfff]")
_NONE = "NONE"
_MAX_TEXT_CHARS = 1_000
_MAX_LIST_ITEMS = 20
_MODEL_OUTPUT_KEYS = {
    "schema_version",
    "summary",
    "finding_assessments",
    "generation_status",
    "virtual_scenarios",
    "uncertainties",
    "evidence_gaps",
}
_DRAFT_KEYS = _MODEL_OUTPUT_KEYS | {
    "model_provider",
    "model_capability",
    "model_name",
    "prompt_version",
    "model_provenance_status",
    "review_status",
    "semantic_approval",
    "gold_eligible",
    "patch_eligible",
    "source_snapshot_hash",
    "source_profile_hash",
    "source_projection_hash",
    "draft_hash",
}
_NODE_VIEW_KEYS = {
    "node_ref",
    "parent_ref",
    "depth",
    "name",
    "kind",
    "value_type",
    "cardinality",
    "direct_child_count",
    "included_child_refs",
}
_FINDING_VIEW_KEYS = {
    "finding_ref",
    "code",
    "node_refs",
    "occurrence_count",
}
_FINDING_ASSESSMENT_KEYS = {
    "finding_ref",
    "disposition",
    "reason",
}
_SCENARIO_KEYS = {
    "scenario_ref",
    "title",
    "natural_language_request",
    "validation_goal",
    "supporting_node_refs",
    "source_finding_refs",
    "rationale",
}
_SCENARIO_MODEL_OUTPUT_KEYS = {
    "schema_version",
    "plan_unit_ref",
    "scenario_ref",
    "planning_mode",
    "scenario_family",
    "target_stage",
    "requirement_text",
    "proposed_parent_ref",
    "node_kind_hint",
    "value_type_hint",
    "cardinality_hint",
    "supporting_node_refs",
    "source_signal_refs",
    "requested_aspects",
    "rationale",
    "uncertainties",
    "evidence_gaps",
}
_SCENARIO_REQUESTED_ASPECT_KEYS = {"aspect", "supporting_node_refs"}
_NEW_NODE_SEED_KEYS = {
    "parent_node_id",
    "proposed_name",
    "node_kind_hint",
    "value_type_hint",
    "cardinality_hint",
}
_SCENARIO_PLAN_KEYS = {
    "schema_version",
    "algorithm_version",
    "source_snapshot_hash",
    "source_profile_hash",
    "max_plan_units",
    "node_limit",
    "new_node_placement_seed",
    "family_statuses",
    "units",
    "covered_branch_node_ids",
    "omitted_branch_node_ids",
    "plan_hash",
}
_SCENARIO_CANDIDATE_KEYS = {
    "schema_version",
    "model_provider",
    "model_capability",
    "model_name",
    "prompt_version",
    "model_provenance_status",
    "review_status",
    "semantic_approval",
    "gold_eligible",
    "patch_eligible",
    "source_snapshot_hash",
    "source_profile_hash",
    "source_plan_hash",
    "source_projection_hash",
    "plan_unit_ref",
    "scenario_ref",
    "planning_mode",
    "scenario_family",
    "target_stage",
    "requirement_text",
    "proposed_parent_ref",
    "node_kind_hint",
    "value_type_hint",
    "cardinality_hint",
    "supporting_node_refs",
    "source_signal_refs",
    "requested_aspects",
    "rationale",
    "uncertainties",
    "evidence_gaps",
    "draft_hash",
}
_SCENARIO_BATCH_KEYS = {
    "schema_version",
    "preparation_source_status",
    "review_status",
    "semantic_approval",
    "gold_eligible",
    "patch_eligible",
    "source_snapshot_hash",
    "source_profile_hash",
    "source_plan_hash",
    "status",
    "planned_unit_count",
    "attempted_unit_count",
    "completed_unit_count",
    "failed_unit_count",
    "not_executed_unit_count",
    "omitted_target_count",
    "candidates",
    "failures",
    "not_executed",
    "omitted_family_refs",
    "omitted_branch_node_ids",
    "family_outcomes",
    "branch_coverage",
    "target_stage_coverage",
    "projected_node_coverage",
    "batch_hash",
}
_SCENARIO_BATCH_CANDIDATE_KEYS = {
    "candidate_ref",
    "plan_unit_ref",
    "local_scenario_ref",
    "source_draft_hash",
    "draft",
}
_SCENARIO_FAILURE_KEYS = {"plan_unit_ref", "error_code"}
_SCENARIO_NOT_EXECUTED_KEYS = {"plan_unit_ref", "reason_code"}


class TreeUnderstandingError(ValueError):
    """A trusted tree/profile pair cannot produce a deterministic diagnostic."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TreeDiagnosticFinding:
    """One mechanically derived candidate signal, never a semantic verdict."""

    code: str
    node_ids: tuple[str, ...]
    occurrence_count: int

    def __post_init__(self) -> None:
        if self.code not in _FINDING_CODE_RANK:
            raise ValueError("unsupported tree diagnostic finding code")
        if (
            not isinstance(self.node_ids, tuple)
            or len(self.node_ids) < 2
            or self.node_ids != tuple(sorted(self.node_ids))
            or len(self.node_ids) != len(set(self.node_ids))
            or any(not isinstance(node_id, str) or not node_id for node_id in self.node_ids)
        ):
            raise ValueError(
                "tree diagnostic finding node_ids must be sorted unique strings"
            )
        if (
            not isinstance(self.occurrence_count, int)
            or isinstance(self.occurrence_count, bool)
            or self.occurrence_count != len(self.node_ids)
        ):
            raise ValueError(
                "tree diagnostic finding occurrence_count must match node_ids"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "node_ids": list(self.node_ids),
            "occurrence_count": self.occurrence_count,
        }


@dataclass(frozen=True, slots=True)
class TopLevelBranchProfile:
    """Aggregate shape for one child branch beneath a canonical root."""

    root_node_id: str
    branch_node_id: str
    node_count: int
    max_relative_depth: int
    max_direct_child_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.root_node_id, str)
            or not self.root_node_id
            or not isinstance(self.branch_node_id, str)
            or not self.branch_node_id
        ):
            raise ValueError("tree diagnostic branch references must be non-empty")
        for name, minimum in (
            ("node_count", 1),
            ("max_relative_depth", 0),
            ("max_direct_child_count", 0),
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < minimum
            ):
                raise ValueError(f"tree diagnostic branch {name} is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_node_id": self.root_node_id,
            "branch_node_id": self.branch_node_id,
            "node_count": self.node_count,
            "max_relative_depth": self.max_relative_depth,
            "max_direct_child_count": self.max_direct_child_count,
        }


@dataclass(frozen=True, slots=True)
class TreeDiagnosticProfile:
    """Immutable internal profile bound to one canonical tree snapshot."""

    schema_version: str
    algorithm_version: str
    source_snapshot_hash: str
    source_tree_id: str
    source_tree_version: str
    node_count: int
    root_count: int
    max_depth: int
    kind_counts: Mapping[str, int]
    value_type_counts: Mapping[str, int]
    cardinality_counts: Mapping[str, int]
    depth_counts: Mapping[str, int]
    top_level_branches: tuple[TopLevelBranchProfile, ...]
    findings: tuple[TreeDiagnosticFinding, ...]
    profile_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "kind_counts",
            freeze_json(dict(self.kind_counts)),
        )
        object.__setattr__(
            self,
            "value_type_counts",
            freeze_json(dict(self.value_type_counts)),
        )
        object.__setattr__(
            self,
            "cardinality_counts",
            freeze_json(dict(self.cardinality_counts)),
        )
        object.__setattr__(
            self,
            "depth_counts",
            freeze_json(dict(self.depth_counts)),
        )
        self.validate()

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported tree diagnostic profile schema_version")
        if self.algorithm_version != ALGORITHM_VERSION:
            raise ValueError("unsupported tree diagnostic profile algorithm_version")
        if (
            not _DIGEST.fullmatch(self.source_snapshot_hash)
            or not _DIGEST.fullmatch(self.profile_hash)
        ):
            raise ValueError("tree diagnostic hashes must be SHA-256 digests")
        if (
            not isinstance(self.source_tree_id, str)
            or not self.source_tree_id
            or not isinstance(self.source_tree_version, str)
            or not self.source_tree_version
        ):
            raise ValueError("tree diagnostic source references must be non-empty")
        if (
            not isinstance(self.node_count, int)
            or isinstance(self.node_count, bool)
            or self.node_count < 1
            or not isinstance(self.root_count, int)
            or isinstance(self.root_count, bool)
            or self.root_count < 1
            or self.root_count > self.node_count
            or not isinstance(self.max_depth, int)
            or isinstance(self.max_depth, bool)
            or self.max_depth < 0
        ):
            raise ValueError("tree diagnostic profile counts are invalid")
        for name in (
            "kind_counts",
            "value_type_counts",
            "cardinality_counts",
            "depth_counts",
        ):
            counts = getattr(self, name)
            _validate_count_map(counts, name)
            if sum(counts.values()) != self.node_count:
                raise ValueError(
                    f"tree diagnostic {name} must account for every node"
                )
        if (
            not isinstance(self.top_level_branches, tuple)
            or not self.top_level_branches
            or any(
                not isinstance(item, TopLevelBranchProfile)
                for item in self.top_level_branches
            )
        ):
            raise ValueError(
                "tree diagnostic top-level branches must be a non-empty tuple"
            )
        branch_order = tuple(
            (item.root_node_id, item.branch_node_id)
            for item in self.top_level_branches
        )
        if (
            branch_order != tuple(sorted(branch_order))
            or len(branch_order) != len(set(branch_order))
        ):
            raise ValueError(
                "tree diagnostic top-level branches must be sorted and unique"
            )
        if (
            not isinstance(self.findings, tuple)
            or any(
                not isinstance(item, TreeDiagnosticFinding)
                for item in self.findings
            )
            or self.findings != tuple(sorted(self.findings, key=_finding_sort_key))
            or len(self.findings)
            != len({(item.code, item.node_ids) for item in self.findings})
        ):
            raise ValueError("tree diagnostic findings must be sorted and unique")
        if self.profile_hash != canonical_digest(self._payload()):
            raise ValueError(
                "tree diagnostic profile_hash does not match its payload"
            )

    def _payload(self) -> dict[str, Any]:
        return _profile_payload(
            schema_version=self.schema_version,
            algorithm_version=self.algorithm_version,
            source_snapshot_hash=self.source_snapshot_hash,
            source_tree_id=self.source_tree_id,
            source_tree_version=self.source_tree_version,
            node_count=self.node_count,
            root_count=self.root_count,
            max_depth=self.max_depth,
            kind_counts=self.kind_counts,
            value_type_counts=self.value_type_counts,
            cardinality_counts=self.cardinality_counts,
            depth_counts=self.depth_counts,
            top_level_branches=self.top_level_branches,
            findings=self.findings,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["profile_hash"] = self.profile_hash
        return payload

    def aggregate_report(self) -> dict[str, Any]:
        """Return counts only; internal names, IDs and hashes remain excluded."""

        code_counts = Counter(finding.code for finding in self.findings)
        return {
            "report_version": AGGREGATE_REPORT_VERSION,
            "profile_schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "node_count": self.node_count,
            "root_count": self.root_count,
            "max_depth": self.max_depth,
            "top_level_branch_count": len(self.top_level_branches),
            "finding_count": len(self.findings),
            "finding_code_counts": dict(sorted(code_counts.items())),
        }


@dataclass(frozen=True, slots=True)
class TreeUnderstandingNodeView:
    """One allowlisted node in a single model-projection scope."""

    node_ref: str
    parent_ref: str | None
    depth: int
    name: str
    kind: str
    value_type: str | None
    cardinality: str | None
    direct_child_count: int
    included_child_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if _NODE_REFERENCE.fullmatch(self.node_ref) is None:
            raise ValueError("tree understanding node_ref is invalid")
        if (
            self.parent_ref is not None
            and _NODE_REFERENCE.fullmatch(self.parent_ref) is None
        ):
            raise ValueError("tree understanding parent_ref is invalid")
        if (
            not isinstance(self.depth, int)
            or isinstance(self.depth, bool)
            or self.depth < 0
        ):
            raise ValueError("tree understanding node depth is invalid")
        _required_text(self.name, "name")
        if (
            not isinstance(self.kind, str)
            or self.kind not in {"CONCEPT", "PROPERTY"}
        ):
            raise ValueError("tree understanding node kind is unsupported")
        if self.value_type is not None:
            _required_text(self.value_type, "value_type")
        if (
            self.cardinality is not None
            and self.cardinality not in {"SINGLE", "MULTIPLE"}
        ):
            raise ValueError("tree understanding cardinality is unsupported")
        if (
            not isinstance(self.direct_child_count, int)
            or isinstance(self.direct_child_count, bool)
            or self.direct_child_count < 0
        ):
            raise ValueError("tree understanding direct_child_count is invalid")
        if (
            not isinstance(self.included_child_refs, tuple)
            or self.included_child_refs
            != tuple(sorted(self.included_child_refs))
            or len(self.included_child_refs)
            != len(set(self.included_child_refs))
            or any(
                _NODE_REFERENCE.fullmatch(ref) is None
                for ref in self.included_child_refs
            )
        ):
            raise ValueError(
                "tree understanding included child refs must be sorted and unique"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_ref": self.node_ref,
            "parent_ref": self.parent_ref,
            "depth": self.depth,
            "name": self.name,
            "kind": self.kind,
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "direct_child_count": self.direct_child_count,
            "included_child_refs": list(self.included_child_refs),
        }


@dataclass(frozen=True, slots=True)
class TreeUnderstandingFindingView:
    """One structural signal expressed only through projection-local refs."""

    finding_ref: str
    code: str
    node_refs: tuple[str, ...]
    occurrence_count: int

    def __post_init__(self) -> None:
        if _FINDING_REFERENCE.fullmatch(self.finding_ref) is None:
            raise ValueError("tree understanding finding_ref is invalid")
        if (
            not isinstance(self.code, str)
            or self.code not in _FINDING_CODE_RANK
        ):
            raise ValueError("tree understanding finding code is unsupported")
        if (
            not isinstance(self.node_refs, tuple)
            or len(self.node_refs) < 2
            or self.node_refs != tuple(sorted(self.node_refs))
            or len(self.node_refs) != len(set(self.node_refs))
            or any(
                _NODE_REFERENCE.fullmatch(ref) is None
                for ref in self.node_refs
            )
        ):
            raise ValueError(
                "tree understanding finding node refs must be sorted and unique"
            )
        if (
            not isinstance(self.occurrence_count, int)
            or isinstance(self.occurrence_count, bool)
            or self.occurrence_count != len(self.node_refs)
        ):
            raise ValueError("tree understanding finding count is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_ref": self.finding_ref,
            "code": self.code,
            "node_refs": list(self.node_refs),
            "occurrence_count": self.occurrence_count,
        }


@dataclass(frozen=True, slots=True)
class TreeUnderstandingProjection:
    """Bounded internal projection with a separately allowlisted model view."""

    source_snapshot_hash: str
    source_profile_hash: str
    node_limit: int
    finding_limit: int
    total_node_count: int
    root_count: int
    max_depth: int
    included_node_count: int
    omitted_node_count: int
    total_finding_count: int
    included_finding_count: int
    omitted_finding_count: int
    coverage_complete: bool
    nodes: tuple[TreeUnderstandingNodeView, ...]
    findings: tuple[TreeUnderstandingFindingView, ...]
    reference_to_node_id: Mapping[str, str]
    projection_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_to_node_id",
            MappingProxyType(dict(self.reference_to_node_id)),
        )
        self.validate()

    @property
    def node_refs(self) -> tuple[str, ...]:
        return tuple(item.node_ref for item in self.nodes)

    @property
    def finding_refs(self) -> tuple[str, ...]:
        return tuple(item.finding_ref for item in self.findings)

    def validate(self) -> None:
        for value in (
            self.source_snapshot_hash,
            self.source_profile_hash,
            self.projection_hash,
        ):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise ValueError(
                    "tree understanding projection hashes must be SHA-256 digests"
                )
        if (
            not isinstance(self.node_limit, int)
            or isinstance(self.node_limit, bool)
            or self.node_limit < 1
            or self.node_limit > MAX_MODEL_NODES
            or not isinstance(self.finding_limit, int)
            or isinstance(self.finding_limit, bool)
            or self.finding_limit < 0
            or self.finding_limit > MAX_MODEL_FINDINGS
        ):
            raise ValueError("tree understanding projection limits are invalid")
        count_values = (
            self.total_node_count,
            self.root_count,
            self.max_depth,
            self.included_node_count,
            self.omitted_node_count,
            self.total_finding_count,
            self.included_finding_count,
            self.omitted_finding_count,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in count_values
        ):
            raise ValueError("tree understanding projection counts are invalid")
        if (
            self.total_node_count < 1
            or self.root_count < 1
            or self.root_count > self.total_node_count
            or self.included_node_count < 1
            or self.included_node_count > self.node_limit
            or self.included_finding_count > self.finding_limit
            or self.included_node_count + self.omitted_node_count
            != self.total_node_count
            or self.included_finding_count + self.omitted_finding_count
            != self.total_finding_count
            or not isinstance(self.coverage_complete, bool)
            or self.coverage_complete
            != (
                self.omitted_node_count == 0
                and self.omitted_finding_count == 0
            )
        ):
            raise ValueError(
                "tree understanding projection coverage is inconsistent"
            )
        if (
            not isinstance(self.nodes, tuple)
            or len(self.nodes) != self.included_node_count
            or any(
                not isinstance(item, TreeUnderstandingNodeView)
                for item in self.nodes
            )
        ):
            raise ValueError("tree understanding projection nodes are invalid")
        expected_node_refs = tuple(
            f"N{index:03d}" for index in range(1, len(self.nodes) + 1)
        )
        if self.node_refs != expected_node_refs:
            raise ValueError(
                "tree understanding node refs must be contiguous and ordered"
            )
        allowed_node_refs = set(expected_node_refs)
        nodes_by_ref = {node.node_ref: node for node in self.nodes}
        for node in self.nodes:
            if not set(node.included_child_refs).issubset(allowed_node_refs):
                raise ValueError(
                    "tree understanding node relations use unknown refs"
                )
            if len(node.included_child_refs) > node.direct_child_count:
                raise ValueError(
                    "tree understanding included children exceed source count"
                )
            if node.parent_ref is None:
                if node.depth != 0:
                    raise ValueError(
                        "tree understanding projected roots must have depth zero"
                    )
            elif (
                node.parent_ref not in allowed_node_refs
                or nodes_by_ref[node.parent_ref].depth != node.depth - 1
                or node.node_ref
                not in nodes_by_ref[node.parent_ref].included_child_refs
            ):
                raise ValueError(
                    "tree understanding parent relation is inconsistent"
                )
            if any(
                nodes_by_ref[child_ref].parent_ref != node.node_ref
                for child_ref in node.included_child_refs
            ):
                raise ValueError(
                    "tree understanding child relation is inconsistent"
                )
        if max(node.depth for node in self.nodes) > self.max_depth:
            raise ValueError(
                "tree understanding projected depth exceeds tree shape"
            )
        if (
            not isinstance(self.findings, tuple)
            or len(self.findings) != self.included_finding_count
            or any(
                not isinstance(item, TreeUnderstandingFindingView)
                for item in self.findings
            )
        ):
            raise ValueError(
                "tree understanding projection findings are invalid"
            )
        expected_finding_refs = tuple(
            f"D{index:03d}" for index in range(1, len(self.findings) + 1)
        )
        if self.finding_refs != expected_finding_refs:
            raise ValueError(
                "tree understanding finding refs must be contiguous and ordered"
            )
        if any(
            not set(finding.node_refs).issubset(allowed_node_refs)
            for finding in self.findings
        ):
            raise ValueError(
                "tree understanding findings use unknown node refs"
            )
        if (
            not isinstance(self.reference_to_node_id, MappingProxyType)
            or set(self.reference_to_node_id) != allowed_node_refs
            or len(self.reference_to_node_id)
            != len(set(self.reference_to_node_id.values()))
            or any(
                not isinstance(node_id, str) or not node_id
                for node_id in self.reference_to_node_id.values()
            )
        ):
            raise ValueError(
                "tree understanding reference mapping is inconsistent"
            )
        model_payload = self.to_model_dict()
        if _serialized_char_count(model_payload) > MAX_MODEL_INPUT_CHARS:
            raise ValueError(
                "tree understanding projection exceeds its size limit"
            )
        if self.projection_hash != canonical_digest(model_payload):
            raise ValueError(
                "tree understanding projection_hash does not match its payload"
            )

    def to_model_dict(self) -> dict[str, Any]:
        """Return the bounded Qwen view without stable identifiers or hashes."""

        return _tree_understanding_model_payload(
            total_node_count=self.total_node_count,
            root_count=self.root_count,
            max_depth=self.max_depth,
            included_node_count=self.included_node_count,
            omitted_node_count=self.omitted_node_count,
            total_finding_count=self.total_finding_count,
            included_finding_count=self.included_finding_count,
            omitted_finding_count=self.omitted_finding_count,
            coverage_complete=self.coverage_complete,
            nodes=self.nodes,
            findings=self.findings,
        )


@dataclass(frozen=True, slots=True)
class TreeUnderstandingFindingAssessment:
    finding_ref: str
    disposition: str
    reason: str

    def __post_init__(self) -> None:
        if _FINDING_REFERENCE.fullmatch(self.finding_ref) is None:
            raise ValueError("tree understanding assessment ref is invalid")
        if (
            not isinstance(self.disposition, str)
            or self.disposition not in FINDING_DISPOSITIONS
        ):
            raise ValueError(
                "tree understanding finding disposition is unsupported"
            )
        _required_text(self.reason, "reason")

    def to_dict(self) -> dict[str, str]:
        return {
            "finding_ref": self.finding_ref,
            "disposition": self.disposition,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class VirtualValidationScenario:
    scenario_ref: str
    title: str
    natural_language_request: str
    validation_goal: str
    supporting_node_refs: tuple[str, ...]
    source_finding_refs: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        if _SCENARIO_REFERENCE.fullmatch(self.scenario_ref) is None:
            raise ValueError("virtual validation scenario ref is invalid")
        _required_text(self.title, "title")
        _required_text(
            self.natural_language_request,
            "natural_language_request",
        )
        if (
            not isinstance(self.validation_goal, str)
            or self.validation_goal not in VALIDATION_GOALS
        ):
            raise ValueError("virtual validation goal is unsupported")
        _validate_ref_tuple(
            self.supporting_node_refs,
            _NODE_REFERENCE,
            "supporting node refs",
            require_non_empty=True,
        )
        _validate_ref_tuple(
            self.source_finding_refs,
            _FINDING_REFERENCE,
            "source finding refs",
            require_non_empty=False,
        )
        _required_text(self.rationale, "rationale")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_ref": self.scenario_ref,
            "title": self.title,
            "natural_language_request": self.natural_language_request,
            "validation_goal": self.validation_goal,
            "supporting_node_refs": list(self.supporting_node_refs),
            "source_finding_refs": list(self.source_finding_refs),
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class TreeUnderstandingDraft:
    """Locally validated Qwen output that still requires human review."""

    model_provider: str
    model_capability: str
    model_name: str
    prompt_version: str
    source_snapshot_hash: str
    source_profile_hash: str
    source_projection_hash: str
    summary: str
    finding_assessments: tuple[TreeUnderstandingFindingAssessment, ...]
    generation_status: str
    virtual_scenarios: tuple[VirtualValidationScenario, ...]
    uncertainties: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    draft_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "model_provider",
            "model_capability",
            "model_name",
            "prompt_version",
        ):
            _required_text(getattr(self, field_name), field_name)
        for value in (
            self.source_snapshot_hash,
            self.source_profile_hash,
            self.source_projection_hash,
            self.draft_hash,
        ):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise ValueError(
                    "tree understanding draft hashes must be SHA-256 digests"
                )
        _required_text(self.summary, "summary")
        if (
            not isinstance(self.finding_assessments, tuple)
            or len(self.finding_assessments) > MAX_MODEL_FINDINGS
            or any(
                not isinstance(
                    item,
                    TreeUnderstandingFindingAssessment,
                )
                for item in self.finding_assessments
            )
        ):
            raise ValueError(
                "tree understanding finding assessments are invalid"
            )
        expected_finding_refs = tuple(
            f"D{index:03d}"
            for index in range(1, len(self.finding_assessments) + 1)
        )
        if (
            tuple(
                item.finding_ref for item in self.finding_assessments
            )
            != expected_finding_refs
        ):
            raise ValueError(
                "tree understanding finding assessments must be contiguous"
            )
        if (
            not isinstance(self.generation_status, str)
            or self.generation_status not in GENERATION_STATUSES
        ):
            raise ValueError(
                "tree understanding generation status is unsupported"
            )
        if (
            not isinstance(self.virtual_scenarios, tuple)
            or len(self.virtual_scenarios) > MAX_VIRTUAL_SCENARIOS
            or any(
                not isinstance(item, VirtualValidationScenario)
                for item in self.virtual_scenarios
            )
        ):
            raise ValueError(
                "tree understanding virtual scenarios are invalid"
            )
        expected_scenario_refs = tuple(
            f"S{index:03d}"
            for index in range(1, len(self.virtual_scenarios) + 1)
        )
        if (
            tuple(
                item.scenario_ref for item in self.virtual_scenarios
            )
            != expected_scenario_refs
        ):
            raise ValueError(
                "virtual validation scenario refs must be contiguous"
            )
        _validate_text_tuple(self.uncertainties, "uncertainties")
        _validate_text_tuple(self.evidence_gaps, "evidence_gaps")
        _validate_generation_policy(
            self.generation_status,
            self.virtual_scenarios,
            self.uncertainties,
            self.evidence_gaps,
        )
        if self.draft_hash != canonical_digest(self._payload()):
            raise ValueError(
                "tree understanding draft_hash does not match its payload"
            )

    @property
    def review_status(self) -> str:
        return REVIEW_STATUS

    @property
    def semantic_approval(self) -> bool:
        return False

    @property
    def gold_eligible(self) -> bool:
        return False

    @property
    def patch_eligible(self) -> bool:
        return False

    @classmethod
    def from_model_dict(
        cls,
        payload: Any,
        projection: TreeUnderstandingProjection,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
        *,
        model_provider: str,
        model_capability: str,
        model_name: str,
        prompt_version: str,
    ) -> "TreeUnderstandingDraft":
        verify_tree_understanding_projection_against_sources(
            projection,
            profile,
            tree,
        )
        if not isinstance(payload, dict) or set(payload) != _MODEL_OUTPUT_KEYS:
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_FIELDS_INVALID",
                "tree understanding model output must use exact fields",
            )
        if payload["schema_version"] != MODEL_OUTPUT_SCHEMA_VERSION:
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_VERSION_INVALID",
                "tree understanding model output version is unsupported",
            )
        summary = _parse_required_text(payload["summary"], "summary")
        assessments = _parse_finding_assessments(
            payload["finding_assessments"],
            projection,
        )
        generation_status = _parse_enum(
            payload["generation_status"],
            GENERATION_STATUSES,
            "TREE_UNDERSTANDING_MODEL_GENERATION_STATUS_INVALID",
        )
        scenarios = _parse_virtual_scenarios(
            payload["virtual_scenarios"],
            projection,
        )
        uncertainties = _parse_text_tuple(
            payload["uncertainties"],
            "uncertainties",
        )
        evidence_gaps = _parse_text_tuple(
            payload["evidence_gaps"],
            "evidence_gaps",
        )
        try:
            _validate_generation_policy(
                generation_status,
                scenarios,
                uncertainties,
                evidence_gaps,
            )
        except ValueError:
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_GENERATION_POLICY_INVALID",
                "tree understanding output violates generation policy",
            ) from None
        text_values = (
            summary,
            *(item.reason for item in assessments),
            *(
                text
                for scenario in scenarios
                for text in (
                    scenario.title,
                    scenario.natural_language_request,
                    scenario.rationale,
                )
            ),
            *uncertainties,
            *evidence_gaps,
        )
        if contains_internal_identifier(
            text_values,
            (node.node_id for node in tree.nodes),
        ):
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_INTERNAL_ID_FORBIDDEN",
                "tree understanding output contains an internal identifier",
            )
        metadata = {
            "model_provider": _parse_required_text(
                model_provider,
                "model_provider",
            ),
            "model_capability": _parse_required_text(
                model_capability,
                "model_capability",
            ),
            "model_name": _parse_required_text(
                model_name,
                "model_name",
            ),
            "prompt_version": _parse_required_text(
                prompt_version,
                "prompt_version",
            ),
        }
        draft_payload = {
            "schema_version": DRAFT_SCHEMA_VERSION,
            **metadata,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "review_status": REVIEW_STATUS,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "source_snapshot_hash": tree.snapshot_hash,
            "source_profile_hash": profile.profile_hash,
            "source_projection_hash": projection.projection_hash,
            "summary": summary,
            "finding_assessments": [
                item.to_dict() for item in assessments
            ],
            "generation_status": generation_status,
            "virtual_scenarios": [
                item.to_dict() for item in scenarios
            ],
            "uncertainties": list(uncertainties),
            "evidence_gaps": list(evidence_gaps),
        }
        return cls(
            **metadata,
            source_snapshot_hash=tree.snapshot_hash,
            source_profile_hash=profile.profile_hash,
            source_projection_hash=projection.projection_hash,
            summary=summary,
            finding_assessments=assessments,
            generation_status=generation_status,
            virtual_scenarios=scenarios,
            uncertainties=uncertainties,
            evidence_gaps=evidence_gaps,
            draft_hash=canonical_digest(draft_payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        projection: TreeUnderstandingProjection,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
    ) -> "TreeUnderstandingDraft":
        if not isinstance(payload, dict) or set(payload) != _DRAFT_KEYS:
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_DRAFT_FIELDS_INVALID",
                "stored tree understanding draft must use exact fields",
            )
        if (
            payload["schema_version"] != DRAFT_SCHEMA_VERSION
            or payload["model_provenance_status"]
            != MODEL_PROVENANCE_STATUS
            or payload["review_status"] != REVIEW_STATUS
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_DRAFT_POLICY_INVALID",
                "stored tree understanding draft violates pending-review policy",
            )
        model_payload = {
            key: payload[key] for key in _MODEL_OUTPUT_KEYS
        }
        model_payload["schema_version"] = MODEL_OUTPUT_SCHEMA_VERSION
        draft = cls.from_model_dict(
            model_payload,
            projection,
            profile,
            tree,
            model_provider=payload["model_provider"],
            model_capability=payload["model_capability"],
            model_name=payload["model_name"],
            prompt_version=payload["prompt_version"],
        )
        if payload != draft.to_dict():
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_DRAFT_SOURCE_MISMATCH",
                "stored tree understanding draft does not match trusted sources",
            )
        return draft

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": DRAFT_SCHEMA_VERSION,
            "model_provider": self.model_provider,
            "model_capability": self.model_capability,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "review_status": REVIEW_STATUS,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_profile_hash": self.source_profile_hash,
            "source_projection_hash": self.source_projection_hash,
            "summary": self.summary,
            "finding_assessments": [
                item.to_dict() for item in self.finding_assessments
            ],
            "generation_status": self.generation_status,
            "virtual_scenarios": [
                item.to_dict() for item in self.virtual_scenarios
            ],
            "uncertainties": list(self.uncertainties),
            "evidence_gaps": list(self.evidence_gaps),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["draft_hash"] = self.draft_hash
        return payload

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_OUTPUT_SCHEMA_VERSION,
            "summary": self.summary,
            "finding_assessments": [
                item.to_dict() for item in self.finding_assessments
            ],
            "generation_status": self.generation_status,
            "virtual_scenarios": [
                item.to_dict() for item in self.virtual_scenarios
            ],
            "uncertainties": list(self.uncertainties),
            "evidence_gaps": list(self.evidence_gaps),
        }


@dataclass(frozen=True, slots=True)
class NewNodePlacementSeed:
    """Trusted overlay for a node that cannot be inferred from the current tree."""

    parent_node_id: str
    proposed_name: str
    node_kind_hint: str
    value_type_hint: str | None
    cardinality_hint: str | None

    def __post_init__(self) -> None:
        _required_text(self.parent_node_id, "parent_node_id")
        _required_text(self.proposed_name, "proposed_name")
        if self.node_kind_hint not in {"CONCEPT", "PROPERTY"}:
            raise ValueError("new-node seed kind is unsupported")
        if self.node_kind_hint == "CONCEPT":
            if self.value_type_hint is not None or self.cardinality_hint is not None:
                raise ValueError("concept new-node seed cannot carry a value contract")
        else:
            _required_text(self.value_type_hint, "value_type_hint")
            if self.cardinality_hint not in {"SINGLE", "MULTIPLE"}:
                raise ValueError("property new-node seed cardinality is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_node_id": self.parent_node_id,
            "proposed_name": self.proposed_name,
            "node_kind_hint": self.node_kind_hint,
            "value_type_hint": self.value_type_hint,
            "cardinality_hint": self.cardinality_hint,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPlanUnit:
    """One deterministic, bounded scenario-generation assignment."""

    plan_unit_ref: str
    unit_role: str
    planning_mode: str
    scenario_family: str
    target_stage: str
    primary_anchor_node_id: str
    anchor_node_ids: tuple[str, ...]
    allowed_branch_node_ids: tuple[str, ...]
    finding_code: str | None
    parent_hint_policy: str
    proposed_parent_node_id: str | None
    node_kind_hint_policy: str
    node_kind_hint: str | None
    value_type_hint_policy: str
    value_type_hint: str | None
    cardinality_hint_policy: str
    cardinality_hint: str | None
    node_limit: int

    def __post_init__(self) -> None:
        if _PLAN_UNIT_REFERENCE.fullmatch(self.plan_unit_ref) is None:
            raise ValueError("scenario plan unit reference is invalid")
        if self.unit_role not in PLAN_UNIT_ROLES:
            raise ValueError("scenario plan unit role is unsupported")
        if self.planning_mode not in PLANNING_MODES:
            raise ValueError("scenario planning mode is unsupported")
        if self.scenario_family not in SCENARIO_FAMILIES:
            raise ValueError("scenario family is unsupported")
        if self.target_stage not in TARGET_STAGES:
            raise ValueError("scenario target stage is unsupported")
        _required_text(self.primary_anchor_node_id, "primary_anchor_node_id")
        _validate_internal_id_tuple(self.anchor_node_ids, "anchor_node_ids")
        if self.primary_anchor_node_id not in self.anchor_node_ids:
            raise ValueError("primary scenario anchor must be included")
        _validate_internal_id_tuple(
            self.allowed_branch_node_ids,
            "allowed_branch_node_ids",
        )
        if len(self.allowed_branch_node_ids) > 3:
            raise ValueError("scenario plan unit branch scope is too broad")
        if self.planning_mode == "BRANCH_LOCAL" and len(
            self.allowed_branch_node_ids
        ) != 1:
            raise ValueError("branch-local plan units require exactly one branch")
        if self.planning_mode == "CONTRAST" and len(self.anchor_node_ids) < 2:
            raise ValueError("contrast plan units require at least two anchors")
        if (
            self.finding_code is not None
            and self.finding_code not in _FINDING_CODE_RANK
        ):
            raise ValueError("scenario plan finding code is unsupported")
        if self.parent_hint_policy not in PARENT_HINT_POLICIES:
            raise ValueError("scenario parent hint policy is unsupported")
        if (self.parent_hint_policy == "ABSENT") != (
            self.proposed_parent_node_id is None
        ):
            raise ValueError("scenario parent hint policy and value disagree")
        if self.proposed_parent_node_id is not None:
            _required_text(self.proposed_parent_node_id, "proposed_parent_node_id")
            if self.proposed_parent_node_id not in self.anchor_node_ids:
                raise ValueError("planned parent hint must be an explicit anchor")
        _validate_planned_hint(
            self.node_kind_hint_policy,
            self.node_kind_hint,
            "node_kind_hint",
            {"CONCEPT", "PROPERTY"},
        )
        _validate_planned_hint(
            self.value_type_hint_policy,
            self.value_type_hint,
            "value_type_hint",
            None,
        )
        _validate_planned_hint(
            self.cardinality_hint_policy,
            self.cardinality_hint,
            "cardinality_hint",
            {"SINGLE", "MULTIPLE"},
        )
        if (
            not isinstance(self.node_limit, int)
            or isinstance(self.node_limit, bool)
            or self.node_limit < 1
            or self.node_limit > MAX_SCENARIO_MODEL_NODES
        ):
            raise ValueError("scenario plan unit node limit is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_unit_ref": self.plan_unit_ref,
            "unit_role": self.unit_role,
            "planning_mode": self.planning_mode,
            "scenario_family": self.scenario_family,
            "target_stage": self.target_stage,
            "primary_anchor_node_id": self.primary_anchor_node_id,
            "anchor_node_ids": list(self.anchor_node_ids),
            "allowed_branch_node_ids": list(self.allowed_branch_node_ids),
            "finding_code": self.finding_code,
            "parent_hint_policy": self.parent_hint_policy,
            "proposed_parent_node_id": self.proposed_parent_node_id,
            "node_kind_hint_policy": self.node_kind_hint_policy,
            "node_kind_hint": self.node_kind_hint,
            "value_type_hint_policy": self.value_type_hint_policy,
            "value_type_hint": self.value_type_hint,
            "cardinality_hint_policy": self.cardinality_hint_policy,
            "cardinality_hint": self.cardinality_hint,
            "node_limit": self.node_limit,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationPlan:
    """Source-bound sparse plan; stable identifiers never enter its model view."""

    schema_version: str
    algorithm_version: str
    source_snapshot_hash: str
    source_profile_hash: str
    max_plan_units: int
    node_limit: int
    new_node_placement_seed: NewNodePlacementSeed | None
    family_statuses: Mapping[str, str]
    units: tuple[ScenarioPlanUnit, ...]
    covered_branch_node_ids: tuple[str, ...]
    omitted_branch_node_ids: tuple[str, ...]
    plan_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "family_statuses",
            MappingProxyType(dict(self.family_statuses)),
        )
        self.validate()

    @property
    def plan_unit_refs(self) -> tuple[str, ...]:
        return tuple(unit.plan_unit_ref for unit in self.units)

    def validate(self) -> None:
        if self.schema_version != SCENARIO_PLAN_SCHEMA_VERSION:
            raise ValueError("unsupported scenario preparation plan schema")
        if self.algorithm_version != SCENARIO_PLAN_ALGORITHM_VERSION:
            raise ValueError("unsupported scenario preparation plan algorithm")
        for digest in (
            self.source_snapshot_hash,
            self.source_profile_hash,
            self.plan_hash,
        ):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("scenario preparation hashes must be SHA-256")
        if (
            not isinstance(self.max_plan_units, int)
            or isinstance(self.max_plan_units, bool)
            or self.max_plan_units < 1
            or self.max_plan_units > MAX_PLAN_UNITS
        ):
            raise ValueError("scenario preparation plan limit is invalid")
        if (
            not isinstance(self.node_limit, int)
            or isinstance(self.node_limit, bool)
            or self.node_limit < 1
            or self.node_limit > MAX_SCENARIO_MODEL_NODES
        ):
            raise ValueError("scenario preparation node limit is invalid")
        if self.new_node_placement_seed is not None and not isinstance(
            self.new_node_placement_seed,
            NewNodePlacementSeed,
        ):
            raise ValueError("scenario preparation new-node seed is invalid")
        if (
            not isinstance(self.family_statuses, MappingProxyType)
            or tuple(self.family_statuses) != SCENARIO_FAMILY_ORDER
            or any(
                value not in FAMILY_PLAN_STATUSES
                for value in self.family_statuses.values()
            )
        ):
            raise ValueError("scenario family statuses are invalid")
        if (
            not isinstance(self.units, tuple)
            or not self.units
            or len(self.units) > self.max_plan_units
            or any(not isinstance(unit, ScenarioPlanUnit) for unit in self.units)
        ):
            raise ValueError("scenario plan units are invalid")
        expected_refs = tuple(
            f"U{index:03d}" for index in range(1, len(self.units) + 1)
        )
        if self.plan_unit_refs != expected_refs:
            raise ValueError("scenario plan unit refs must be contiguous")
        for family in SCENARIO_FAMILY_ORDER:
            has_risk_unit = any(
                unit.unit_role == "RISK_CHALLENGE"
                and unit.scenario_family == family
                for unit in self.units
            )
            if (self.family_statuses[family] == "PLANNED") != has_risk_unit:
                raise ValueError("scenario family status disagrees with risk units")
        _validate_internal_id_tuple(
            self.covered_branch_node_ids,
            "covered_branch_node_ids",
            require_non_empty=False,
        )
        _validate_internal_id_tuple(
            self.omitted_branch_node_ids,
            "omitted_branch_node_ids",
            require_non_empty=False,
        )
        if set(self.covered_branch_node_ids) & set(self.omitted_branch_node_ids):
            raise ValueError("covered and omitted branches must be disjoint")
        if self.plan_hash != canonical_digest(self._payload()):
            raise ValueError("scenario preparation plan hash is invalid")

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
    ) -> "ScenarioPreparationPlan":
        """Rebuild a stored plan from the trusted tree/profile and seed input."""

        if not isinstance(payload, dict) or set(payload) != _SCENARIO_PLAN_KEYS:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_PLAN_FIELDS_INVALID",
                "stored scenario plan must use exact fields",
            )
        if (
            payload["schema_version"] != SCENARIO_PLAN_SCHEMA_VERSION
            or payload["algorithm_version"] != SCENARIO_PLAN_ALGORITHM_VERSION
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_PLAN_VERSION_INVALID",
                "stored scenario plan version is unsupported",
            )
        seed_payload = payload["new_node_placement_seed"]
        seed: NewNodePlacementSeed | None
        if seed_payload is None:
            seed = None
        elif isinstance(seed_payload, dict) and set(seed_payload) == _NEW_NODE_SEED_KEYS:
            try:
                seed = NewNodePlacementSeed(**seed_payload)
            except (TypeError, ValueError):
                raise TreeUnderstandingError(
                    "SCENARIO_PREPARATION_NEW_NODE_SEED_INVALID",
                    "stored new-node seed is invalid",
                ) from None
        else:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_NEW_NODE_SEED_INVALID",
                "stored new-node seed must use exact fields",
            )
        expected = build_scenario_preparation_plan(
            tree,
            profile,
            max_plan_units=payload["max_plan_units"],
            node_limit=payload["node_limit"],
            new_node_placement_seed=seed,
        )
        if payload != expected.to_dict():
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_PLAN_SOURCE_MISMATCH",
                "stored scenario plan does not match trusted sources",
            )
        return expected

    def _payload(self) -> dict[str, Any]:
        return _scenario_plan_payload(
            source_snapshot_hash=self.source_snapshot_hash,
            source_profile_hash=self.source_profile_hash,
            max_plan_units=self.max_plan_units,
            node_limit=self.node_limit,
            new_node_placement_seed=self.new_node_placement_seed,
            family_statuses=self.family_statuses,
            units=self.units,
            covered_branch_node_ids=self.covered_branch_node_ids,
            omitted_branch_node_ids=self.omitted_branch_node_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["plan_hash"] = self.plan_hash
        return payload


@dataclass(frozen=True, slots=True)
class ScenarioPreparationSignalView:
    """A mechanical signal reduced to refs from one projection scope."""

    signal_ref: str
    code: str
    node_refs: tuple[str, ...]
    source_occurrence_count: int

    def __post_init__(self) -> None:
        if self.signal_ref != "D001" or self.code not in _FINDING_CODE_RANK:
            raise ValueError("scenario preparation signal is invalid")
        _validate_ref_tuple(
            self.node_refs,
            _NODE_REFERENCE,
            "scenario signal node refs",
            require_non_empty=True,
        )
        if (
            not isinstance(self.source_occurrence_count, int)
            or isinstance(self.source_occurrence_count, bool)
            or self.source_occurrence_count < len(self.node_refs)
        ):
            raise ValueError("scenario signal occurrence count is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_ref": self.signal_ref,
            "code": self.code,
            "node_refs": list(self.node_refs),
            "source_occurrence_count": self.source_occurrence_count,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationProjection:
    """Per-unit positive-allowlist model view plus trusted reverse mappings."""

    source_snapshot_hash: str
    source_profile_hash: str
    source_plan_hash: str
    plan_unit_ref: str
    unit_role: str
    planning_mode: str
    scenario_family: str
    target_stage: str
    parent_hint_policy: str
    node_kind_hint_policy: str
    value_type_hint_policy: str
    cardinality_hint_policy: str
    proposed_new_node_name: str | None
    node_kind_hint: str | None
    value_type_hint: str | None
    cardinality_hint: str | None
    node_limit: int
    total_node_count: int
    root_count: int
    top_level_branch_count: int
    included_node_count: int
    omitted_node_count: int
    allowed_branch_count: int
    nodes: tuple[TreeUnderstandingNodeView, ...]
    signal: ScenarioPreparationSignalView | None
    primary_anchor_ref: str
    anchor_refs: tuple[str, ...]
    evidence_node_refs: tuple[str, ...]
    proposed_parent_ref: str | None
    reference_to_node_id: Mapping[str, str]
    reference_to_branch_node_id: Mapping[str, str | None]
    projection_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_to_node_id",
            MappingProxyType(dict(self.reference_to_node_id)),
        )
        object.__setattr__(
            self,
            "reference_to_branch_node_id",
            MappingProxyType(dict(self.reference_to_branch_node_id)),
        )
        self.validate()

    @property
    def node_refs(self) -> tuple[str, ...]:
        return tuple(node.node_ref for node in self.nodes)

    @property
    def signal_refs(self) -> tuple[str, ...]:
        return ("D001",) if self.signal is not None else ()

    def validate(self) -> None:
        for digest in (
            self.source_snapshot_hash,
            self.source_profile_hash,
            self.source_plan_hash,
            self.projection_hash,
        ):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("scenario projection hashes must be SHA-256")
        if _PLAN_UNIT_REFERENCE.fullmatch(self.plan_unit_ref) is None:
            raise ValueError("scenario projection unit ref is invalid")
        if (
            self.unit_role not in PLAN_UNIT_ROLES
            or self.planning_mode not in PLANNING_MODES
            or self.scenario_family not in SCENARIO_FAMILIES
            or self.target_stage not in TARGET_STAGES
            or self.parent_hint_policy not in PARENT_HINT_POLICIES
        ):
            raise ValueError("scenario projection plan fields are invalid")
        _validate_planned_hint(
            self.node_kind_hint_policy,
            self.node_kind_hint,
            "node_kind_hint",
            {"CONCEPT", "PROPERTY"},
        )
        _validate_planned_hint(
            self.value_type_hint_policy,
            self.value_type_hint,
            "value_type_hint",
            None,
        )
        _validate_planned_hint(
            self.cardinality_hint_policy,
            self.cardinality_hint,
            "cardinality_hint",
            {"SINGLE", "MULTIPLE"},
        )
        if self.proposed_new_node_name is not None:
            _required_text(self.proposed_new_node_name, "proposed_new_node_name")
        if (self.scenario_family == "NEW_NODE_PLACEMENT") != (
            self.proposed_new_node_name is not None
        ):
            raise ValueError("new-node name must appear only for its seeded family")
        if (
            not isinstance(self.node_limit, int)
            or isinstance(self.node_limit, bool)
            or self.node_limit < 1
            or self.node_limit > MAX_SCENARIO_MODEL_NODES
        ):
            raise ValueError("scenario projection node limit is invalid")
        counts = (
            self.total_node_count,
            self.root_count,
            self.top_level_branch_count,
            self.included_node_count,
            self.omitted_node_count,
            self.allowed_branch_count,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in counts
        ) or (
            self.total_node_count < 1
            or self.root_count < 1
            or self.top_level_branch_count < 1
            or self.included_node_count < 1
            or self.included_node_count > self.node_limit
            or self.included_node_count + self.omitted_node_count
            != self.total_node_count
            or self.allowed_branch_count < 1
            or self.allowed_branch_count > 3
        ):
            raise ValueError("scenario projection counts are invalid")
        if (
            not isinstance(self.nodes, tuple)
            or len(self.nodes) != self.included_node_count
            or any(
                not isinstance(node, TreeUnderstandingNodeView)
                for node in self.nodes
            )
        ):
            raise ValueError("scenario projection nodes are invalid")
        expected_refs = tuple(
            f"N{index:03d}" for index in range(1, len(self.nodes) + 1)
        )
        if self.node_refs != expected_refs:
            raise ValueError("scenario projection refs must be contiguous")
        allowed_refs = set(expected_refs)
        _validate_ref_tuple(
            self.anchor_refs,
            _NODE_REFERENCE,
            "scenario anchor refs",
            require_non_empty=True,
        )
        _validate_ref_tuple(
            self.evidence_node_refs,
            _NODE_REFERENCE,
            "scenario evidence refs",
            require_non_empty=True,
        )
        if (
            not set(self.anchor_refs).issubset(allowed_refs)
            or not set(self.evidence_node_refs).issubset(allowed_refs)
            or not set(self.anchor_refs).issubset(self.evidence_node_refs)
            or self.primary_anchor_ref not in self.anchor_refs
            or self.primary_anchor_ref not in self.evidence_node_refs
        ):
            raise ValueError("scenario projection anchor refs are inconsistent")
        if self.proposed_parent_ref is not None and (
            self.proposed_parent_ref not in self.anchor_refs
            or self.proposed_parent_ref not in self.evidence_node_refs
        ):
            raise ValueError("scenario projected parent ref is inconsistent")
        if (self.parent_hint_policy == "ABSENT") != (
            self.proposed_parent_ref is None
        ):
            raise ValueError("scenario projected parent policy is inconsistent")
        if self.signal is not None and not set(self.signal.node_refs).issubset(
            self.evidence_node_refs
        ):
            raise ValueError("scenario signal refs exceed evidence scope")
        if (
            not isinstance(self.reference_to_node_id, MappingProxyType)
            or set(self.reference_to_node_id) != allowed_refs
            or len(set(self.reference_to_node_id.values())) != len(allowed_refs)
            or not isinstance(self.reference_to_branch_node_id, MappingProxyType)
            or set(self.reference_to_branch_node_id) != allowed_refs
        ):
            raise ValueError("scenario projection reverse mappings are invalid")
        evidence_branches = {
            self.reference_to_branch_node_id[ref]
            for ref in self.evidence_node_refs
            if self.reference_to_branch_node_id[ref] is not None
        }
        if (
            not evidence_branches
            or len(evidence_branches) > self.allowed_branch_count
            or (
                self.planning_mode == "BRANCH_LOCAL"
                and len(evidence_branches) != 1
            )
        ):
            raise ValueError("scenario projection violates its planning mode")
        payload = self.to_model_dict()
        if _serialized_char_count(payload) > MAX_SCENARIO_MODEL_INPUT_CHARS:
            raise ValueError("scenario projection exceeds its character limit")
        if self.projection_hash != canonical_digest(payload):
            raise ValueError("scenario projection hash is invalid")

    def to_model_dict(self) -> dict[str, Any]:
        return _scenario_model_input_payload(
            plan_unit_ref=self.plan_unit_ref,
            unit_role=self.unit_role,
            planning_mode=self.planning_mode,
            scenario_family=self.scenario_family,
            target_stage=self.target_stage,
            parent_hint_policy=self.parent_hint_policy,
            node_kind_hint_policy=self.node_kind_hint_policy,
            value_type_hint_policy=self.value_type_hint_policy,
            cardinality_hint_policy=self.cardinality_hint_policy,
            proposed_new_node_name=self.proposed_new_node_name,
            node_kind_hint=self.node_kind_hint,
            value_type_hint=self.value_type_hint,
            cardinality_hint=self.cardinality_hint,
            total_node_count=self.total_node_count,
            root_count=self.root_count,
            top_level_branch_count=self.top_level_branch_count,
            included_node_count=self.included_node_count,
            omitted_node_count=self.omitted_node_count,
            allowed_branch_count=self.allowed_branch_count,
            nodes=self.nodes,
            signal=self.signal,
            primary_anchor_ref=self.primary_anchor_ref,
            anchor_refs=self.anchor_refs,
            evidence_node_refs=self.evidence_node_refs,
            proposed_parent_ref=self.proposed_parent_ref,
        )


@dataclass(frozen=True, slots=True)
class ScenarioRequestedAspect:
    aspect: str
    supporting_node_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.aspect, "aspect")
        _validate_ref_tuple(
            self.supporting_node_refs,
            _NODE_REFERENCE,
            "requested aspect refs",
            require_non_empty=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "aspect": self.aspect,
            "supporting_node_refs": list(self.supporting_node_refs),
        }


@dataclass(frozen=True, slots=True)
class ScenarioCandidateDraft:
    """One locally validated candidate that remains non-Gold and non-Patch."""

    model_provider: str
    model_capability: str
    model_name: str
    prompt_version: str
    source_snapshot_hash: str
    source_profile_hash: str
    source_plan_hash: str
    source_projection_hash: str
    plan_unit_ref: str
    scenario_ref: str
    planning_mode: str
    scenario_family: str
    target_stage: str
    requirement_text: str
    proposed_parent_ref: str | None
    node_kind_hint: str | None
    value_type_hint: str | None
    cardinality_hint: str | None
    supporting_node_refs: tuple[str, ...]
    source_signal_refs: tuple[str, ...]
    requested_aspects: tuple[ScenarioRequestedAspect, ...]
    rationale: str
    uncertainties: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    draft_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "model_provider",
            "model_capability",
            "model_name",
            "prompt_version",
        ):
            _required_text(getattr(self, field_name), field_name)
        for digest in (
            self.source_snapshot_hash,
            self.source_profile_hash,
            self.source_plan_hash,
            self.source_projection_hash,
            self.draft_hash,
        ):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("scenario candidate hashes must be SHA-256")
        if (
            _PLAN_UNIT_REFERENCE.fullmatch(self.plan_unit_ref) is None
            or self.scenario_ref != "S001"
            or self.planning_mode not in PLANNING_MODES
            or self.scenario_family not in SCENARIO_FAMILIES
            or self.target_stage not in TARGET_STAGES
        ):
            raise ValueError("scenario candidate plan fields are invalid")
        _required_text(self.requirement_text, "requirement_text")
        if self.proposed_parent_ref is not None and _NODE_REFERENCE.fullmatch(
            self.proposed_parent_ref
        ) is None:
            raise ValueError("scenario candidate parent ref is invalid")
        if self.node_kind_hint is not None and self.node_kind_hint not in {
            "CONCEPT",
            "PROPERTY",
        }:
            raise ValueError("scenario candidate node kind hint is invalid")
        if self.value_type_hint is not None:
            _required_text(self.value_type_hint, "value_type_hint")
        if self.cardinality_hint is not None and self.cardinality_hint not in {
            "SINGLE",
            "MULTIPLE",
        }:
            raise ValueError("scenario candidate cardinality hint is invalid")
        _validate_ref_tuple(
            self.supporting_node_refs,
            _NODE_REFERENCE,
            "scenario candidate supporting refs",
            require_non_empty=True,
        )
        _validate_ref_tuple(
            self.source_signal_refs,
            _FINDING_REFERENCE,
            "scenario candidate signal refs",
            require_non_empty=False,
        )
        if (
            not isinstance(self.requested_aspects, tuple)
            or not self.requested_aspects
            or len(self.requested_aspects) > 3
            or any(
                not isinstance(item, ScenarioRequestedAspect)
                for item in self.requested_aspects
            )
            or len({item.aspect for item in self.requested_aspects})
            != len(self.requested_aspects)
        ):
            raise ValueError("scenario requested aspects are invalid")
        if self.planning_mode == "BRANCH_LOCAL" and len(self.requested_aspects) != 1:
            raise ValueError("branch-local candidates require one primary aspect")
        aspect_refs = {
            ref
            for aspect in self.requested_aspects
            for ref in aspect.supporting_node_refs
        }
        if aspect_refs != set(self.supporting_node_refs):
            raise ValueError("requested aspects must account for all supporting refs")
        _required_text(self.rationale, "rationale")
        _validate_text_tuple(self.uncertainties, "uncertainties")
        _validate_text_tuple(self.evidence_gaps, "evidence_gaps")
        if _scenario_candidate_text_policy_invalid(
            self.requirement_text,
            self.requested_aspects,
            self.rationale,
            self.uncertainties,
            self.evidence_gaps,
        ):
            raise ValueError("scenario candidate text policy is invalid")
        if _scenario_candidate_family_policy_invalid(
            self.scenario_family,
            self.uncertainties,
            self.evidence_gaps,
        ):
            raise ValueError("scenario candidate family policy is invalid")
        if self.draft_hash != canonical_digest(self._payload()):
            raise ValueError("scenario candidate draft hash is invalid")

    @property
    def review_status(self) -> str:
        return REVIEW_STATUS

    @property
    def semantic_approval(self) -> bool:
        return False

    @property
    def gold_eligible(self) -> bool:
        return False

    @property
    def patch_eligible(self) -> bool:
        return False

    @classmethod
    def from_model_dict(
        cls,
        payload: Any,
        projection: ScenarioPreparationProjection,
        plan: ScenarioPreparationPlan,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
        *,
        model_provider: str,
        model_capability: str,
        model_name: str,
        prompt_version: str,
    ) -> "ScenarioCandidateDraft":
        verify_scenario_preparation_projection_against_sources(
            projection,
            plan,
            profile,
            tree,
        )
        if not isinstance(payload, dict) or set(payload) != _SCENARIO_MODEL_OUTPUT_KEYS:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_FIELDS_INVALID",
                "scenario model output must use exact fields",
            )
        if payload["schema_version"] != SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_VERSION_INVALID",
                "scenario model output schema is unsupported",
            )
        _verify_scenario_model_echo(payload, projection)
        requirement_text = _parse_required_text(
            payload["requirement_text"],
            "requirement_text",
            code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
        )
        proposed_parent_ref = _parse_optional_projection_ref(
            payload["proposed_parent_ref"],
            projection,
            "SCENARIO_PREPARATION_MODEL_PARENT_REF_INVALID",
        )
        if proposed_parent_ref != projection.proposed_parent_ref:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_HINT_POLICY_INVALID",
                "model parent hint does not match the deterministic plan",
            )
        node_kind_hint = _parse_optional_enum(
            payload["node_kind_hint"],
            {"CONCEPT", "PROPERTY"},
            "SCENARIO_PREPARATION_MODEL_HINT_POLICY_INVALID",
        )
        value_type_hint = _parse_optional_text(
            payload["value_type_hint"],
            "value_type_hint",
            code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
        )
        cardinality_hint = _parse_optional_enum(
            payload["cardinality_hint"],
            {"SINGLE", "MULTIPLE"},
            "SCENARIO_PREPARATION_MODEL_HINT_POLICY_INVALID",
        )
        if (
            node_kind_hint != projection.node_kind_hint
            or value_type_hint != projection.value_type_hint
            or cardinality_hint != projection.cardinality_hint
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_HINT_POLICY_INVALID",
                "model request hints do not match the deterministic plan",
            )
        supporting_refs = _parse_projection_refs(
            payload["supporting_node_refs"],
            allowed_refs=set(projection.evidence_node_refs),
            pattern=_NODE_REFERENCE,
            code="SCENARIO_PREPARATION_MODEL_NODE_REF_INVALID",
            field_name="supporting_node_refs",
            require_non_empty=True,
        )
        if projection.primary_anchor_ref not in supporting_refs:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_PRIMARY_ANCHOR_MISSING",
                "candidate evidence must include the planned primary anchor",
            )
        source_signal_refs = _parse_projection_refs(
            payload["source_signal_refs"],
            allowed_refs=set(projection.signal_refs),
            pattern=_FINDING_REFERENCE,
            code="SCENARIO_PREPARATION_MODEL_SIGNAL_REF_INVALID",
            field_name="source_signal_refs",
            require_non_empty=projection.signal is not None,
        )
        if source_signal_refs != projection.signal_refs:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_SIGNAL_REF_INVALID",
                "candidate must cover the planned mechanical signal",
            )
        requested_aspects = _parse_requested_aspects(
            payload["requested_aspects"],
            allowed_refs=set(supporting_refs),
            planning_mode=projection.planning_mode,
        )
        aspect_refs = {
            ref
            for aspect in requested_aspects
            for ref in aspect.supporting_node_refs
        }
        if aspect_refs != set(supporting_refs):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_ASPECT_EVIDENCE_INVALID",
                "requested aspects must account for all supporting refs",
            )
        rationale = _parse_required_text(
            payload["rationale"],
            "rationale",
            code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
        )
        uncertainties = _parse_text_tuple(
            payload["uncertainties"],
            "uncertainties",
            code="SCENARIO_PREPARATION_MODEL_TEXT_LIST_INVALID",
            item_code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
        )
        evidence_gaps = _parse_text_tuple(
            payload["evidence_gaps"],
            "evidence_gaps",
            code="SCENARIO_PREPARATION_MODEL_TEXT_LIST_INVALID",
            item_code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
        )
        if _scenario_candidate_text_policy_invalid(
            requirement_text,
            requested_aspects,
            rationale,
            uncertainties,
            evidence_gaps,
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_TEXT_POLICY_INVALID",
                "scenario model output retained template text or exposed a temporary reference",
            )
        if _scenario_candidate_family_policy_invalid(
            projection.scenario_family,
            uncertainties,
            evidence_gaps,
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_FAMILY_POLICY_INVALID",
                "scenario model output omitted the disclosure required by its family",
            )
        text_values = (
            requirement_text,
            *(aspect.aspect for aspect in requested_aspects),
            rationale,
            *uncertainties,
            *evidence_gaps,
        )
        if contains_internal_identifier(
            text_values,
            (node.node_id for node in tree.nodes),
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_INTERNAL_ID_FORBIDDEN",
                "scenario model output contains an internal identifier",
            )
        metadata = {
            "model_provider": _parse_required_text(
                model_provider,
                "model_provider",
                code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
            ),
            "model_capability": _parse_required_text(
                model_capability,
                "model_capability",
                code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
            ),
            "model_name": _parse_required_text(
                model_name,
                "model_name",
                code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
            ),
            "prompt_version": _parse_required_text(
                prompt_version,
                "prompt_version",
                code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
            ),
        }
        draft_payload = _scenario_candidate_payload(
            **metadata,
            source_snapshot_hash=tree.snapshot_hash,
            source_profile_hash=profile.profile_hash,
            source_plan_hash=plan.plan_hash,
            source_projection_hash=projection.projection_hash,
            plan_unit_ref=projection.plan_unit_ref,
            planning_mode=projection.planning_mode,
            scenario_family=projection.scenario_family,
            target_stage=projection.target_stage,
            requirement_text=requirement_text,
            proposed_parent_ref=proposed_parent_ref,
            node_kind_hint=node_kind_hint,
            value_type_hint=value_type_hint,
            cardinality_hint=cardinality_hint,
            supporting_node_refs=supporting_refs,
            source_signal_refs=source_signal_refs,
            requested_aspects=requested_aspects,
            rationale=rationale,
            uncertainties=uncertainties,
            evidence_gaps=evidence_gaps,
        )
        return cls(
            **metadata,
            source_snapshot_hash=tree.snapshot_hash,
            source_profile_hash=profile.profile_hash,
            source_plan_hash=plan.plan_hash,
            source_projection_hash=projection.projection_hash,
            plan_unit_ref=projection.plan_unit_ref,
            scenario_ref="S001",
            planning_mode=projection.planning_mode,
            scenario_family=projection.scenario_family,
            target_stage=projection.target_stage,
            requirement_text=requirement_text,
            proposed_parent_ref=proposed_parent_ref,
            node_kind_hint=node_kind_hint,
            value_type_hint=value_type_hint,
            cardinality_hint=cardinality_hint,
            supporting_node_refs=supporting_refs,
            source_signal_refs=source_signal_refs,
            requested_aspects=requested_aspects,
            rationale=rationale,
            uncertainties=uncertainties,
            evidence_gaps=evidence_gaps,
            draft_hash=canonical_digest(draft_payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        projection: ScenarioPreparationProjection,
        plan: ScenarioPreparationPlan,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
    ) -> "ScenarioCandidateDraft":
        """Replay a stored draft from trusted sources, not from its outer hash."""

        if not isinstance(payload, dict) or set(payload) != _SCENARIO_CANDIDATE_KEYS:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_CANDIDATE_FIELDS_INVALID",
                "stored scenario candidate must use exact fields",
            )
        if (
            payload["schema_version"] != SCENARIO_CANDIDATE_SCHEMA_VERSION
            or payload["model_provenance_status"] != MODEL_PROVENANCE_STATUS
            or payload["review_status"] != REVIEW_STATUS
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_CANDIDATE_POLICY_INVALID",
                "stored scenario candidate violates pending-review policy",
            )
        model_payload = {
            key: payload[key] for key in _SCENARIO_MODEL_OUTPUT_KEYS
        }
        model_payload["schema_version"] = SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION
        draft = cls.from_model_dict(
            model_payload,
            projection,
            plan,
            profile,
            tree,
            model_provider=payload["model_provider"],
            model_capability=payload["model_capability"],
            model_name=payload["model_name"],
            prompt_version=payload["prompt_version"],
        )
        if payload != draft.to_dict():
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_CANDIDATE_SOURCE_MISMATCH",
                "stored scenario candidate does not match trusted sources",
            )
        return draft

    def _payload(self) -> dict[str, Any]:
        return _scenario_candidate_payload(
            model_provider=self.model_provider,
            model_capability=self.model_capability,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
            source_snapshot_hash=self.source_snapshot_hash,
            source_profile_hash=self.source_profile_hash,
            source_plan_hash=self.source_plan_hash,
            source_projection_hash=self.source_projection_hash,
            plan_unit_ref=self.plan_unit_ref,
            planning_mode=self.planning_mode,
            scenario_family=self.scenario_family,
            target_stage=self.target_stage,
            requirement_text=self.requirement_text,
            proposed_parent_ref=self.proposed_parent_ref,
            node_kind_hint=self.node_kind_hint,
            value_type_hint=self.value_type_hint,
            cardinality_hint=self.cardinality_hint,
            supporting_node_refs=self.supporting_node_refs,
            source_signal_refs=self.source_signal_refs,
            requested_aspects=self.requested_aspects,
            rationale=self.rationale,
            uncertainties=self.uncertainties,
            evidence_gaps=self.evidence_gaps,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["draft_hash"] = self.draft_hash
        return payload

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
            "plan_unit_ref": self.plan_unit_ref,
            "scenario_ref": self.scenario_ref,
            "planning_mode": self.planning_mode,
            "scenario_family": self.scenario_family,
            "target_stage": self.target_stage,
            "requirement_text": self.requirement_text,
            "proposed_parent_ref": self.proposed_parent_ref,
            "node_kind_hint": self.node_kind_hint,
            "value_type_hint": self.value_type_hint,
            "cardinality_hint": self.cardinality_hint,
            "supporting_node_refs": list(self.supporting_node_refs),
            "source_signal_refs": list(self.source_signal_refs),
            "requested_aspects": [item.to_dict() for item in self.requested_aspects],
            "rationale": self.rationale,
            "uncertainties": list(self.uncertainties),
            "evidence_gaps": list(self.evidence_gaps),
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationFailure:
    """Stable failure for one attempted plan unit; it contains no model text."""

    plan_unit_ref: str
    error_code: str

    def __post_init__(self) -> None:
        if _PLAN_UNIT_REFERENCE.fullmatch(self.plan_unit_ref) is None:
            raise ValueError("scenario preparation failure unit ref is invalid")
        if (
            not isinstance(self.error_code, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", self.error_code) is None
        ):
            raise ValueError("scenario preparation failure code is invalid")

    def to_dict(self) -> dict[str, str]:
        return {
            "plan_unit_ref": self.plan_unit_ref,
            "error_code": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationNotExecuted:
    """One planned unit intentionally left unattempted for a stable reason."""

    plan_unit_ref: str
    reason_code: str

    def __post_init__(self) -> None:
        if _PLAN_UNIT_REFERENCE.fullmatch(self.plan_unit_ref) is None:
            raise ValueError("not-executed scenario unit ref is invalid")
        if (
            not isinstance(self.reason_code, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", self.reason_code) is None
        ):
            raise ValueError("not-executed scenario reason code is invalid")

    def to_dict(self) -> dict[str, str]:
        return {
            "plan_unit_ref": self.plan_unit_ref,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationBatchCandidate:
    """A run-scoped reference wrapping one locally scoped S001 draft."""

    candidate_ref: str
    plan_unit_ref: str
    source_draft_hash: str
    draft: ScenarioCandidateDraft

    def __post_init__(self) -> None:
        if _RUN_CANDIDATE_REFERENCE.fullmatch(self.candidate_ref) is None:
            raise ValueError("run-level scenario candidate ref is invalid")
        if _PLAN_UNIT_REFERENCE.fullmatch(self.plan_unit_ref) is None:
            raise ValueError("batch candidate plan unit ref is invalid")
        if not isinstance(self.draft, ScenarioCandidateDraft):
            raise ValueError("batch candidate draft is invalid")
        if (
            self.source_draft_hash != self.draft.draft_hash
            or self.plan_unit_ref != self.draft.plan_unit_ref
        ):
            raise ValueError("batch candidate source binding is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ref": self.candidate_ref,
            "plan_unit_ref": self.plan_unit_ref,
            "local_scenario_ref": self.draft.scenario_ref,
            "source_draft_hash": self.source_draft_hash,
            "draft": self.draft.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationBranchCoverage:
    """Branch-local preparation outcomes; lists may overlap after mixed outcomes."""

    candidate_ready_branch_node_ids: tuple[str, ...]
    failed_branch_node_ids: tuple[str, ...]
    not_executed_branch_node_ids: tuple[str, ...]
    omitted_budget_branch_node_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_ready_branch_node_ids",
            "failed_branch_node_ids",
            "not_executed_branch_node_ids",
            "omitted_budget_branch_node_ids",
        ):
            _validate_internal_id_tuple(
                getattr(self, field_name),
                field_name,
                require_non_empty=False,
            )
        omitted = set(self.omitted_budget_branch_node_ids)
        if omitted & (
            set(self.candidate_ready_branch_node_ids)
            | set(self.failed_branch_node_ids)
            | set(self.not_executed_branch_node_ids)
        ):
            raise ValueError("omitted branches cannot have planned outcomes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ready_branch_node_ids": list(
                self.candidate_ready_branch_node_ids
            ),
            "failed_branch_node_ids": list(self.failed_branch_node_ids),
            "not_executed_branch_node_ids": list(
                self.not_executed_branch_node_ids
            ),
            "omitted_budget_branch_node_ids": list(
                self.omitted_budget_branch_node_ids
            ),
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationStageCoverage:
    """Preparation counts for one target stage; execution remains NOT_RUN."""

    planned_unit_count: int
    candidate_ready_unit_count: int
    failed_unit_count: int
    not_executed_unit_count: int
    validation_status: str = SCENARIO_STAGE_NOT_RUN

    def __post_init__(self) -> None:
        counts = (
            self.planned_unit_count,
            self.candidate_ready_unit_count,
            self.failed_unit_count,
            self.not_executed_unit_count,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in counts
        ) or self.planned_unit_count != sum(counts[1:]):
            raise ValueError("scenario target-stage coverage counts are invalid")
        if self.validation_status != SCENARIO_STAGE_NOT_RUN:
            raise ValueError("scenario preparation cannot mark a stage as run")

    def to_dict(self) -> dict[str, Any]:
        return {
            "planned_unit_count": self.planned_unit_count,
            "candidate_ready_unit_count": self.candidate_ready_unit_count,
            "failed_unit_count": self.failed_unit_count,
            "not_executed_unit_count": self.not_executed_unit_count,
            "validation_status": self.validation_status,
        }


@dataclass(frozen=True, slots=True)
class ScenarioProjectedNodeCoverage:
    """Unique-node union across all successfully prebuilt unit projections."""

    total_node_count: int
    included_node_count: int
    omitted_node_count: int
    coverage_complete: bool

    def __post_init__(self) -> None:
        counts = (
            self.total_node_count,
            self.included_node_count,
            self.omitted_node_count,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in counts
        ) or (
            self.total_node_count < 1
            or self.included_node_count + self.omitted_node_count
            != self.total_node_count
            or not isinstance(self.coverage_complete, bool)
            or self.coverage_complete != (self.omitted_node_count == 0)
        ):
            raise ValueError("projected-node coverage counts are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_node_count": self.total_node_count,
            "included_node_count": self.included_node_count,
            "omitted_node_count": self.omitted_node_count,
            "coverage_complete": self.coverage_complete,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPreparationBatch:
    """Deterministic run aggregate; partial candidates remain reviewable."""

    preparation_source_status: str
    source_snapshot_hash: str
    source_profile_hash: str
    source_plan_hash: str
    status: str
    planned_unit_count: int
    attempted_unit_count: int
    completed_unit_count: int
    failed_unit_count: int
    not_executed_unit_count: int
    omitted_target_count: int
    candidates: tuple[ScenarioPreparationBatchCandidate, ...]
    failures: tuple[ScenarioPreparationFailure, ...]
    not_executed: tuple[ScenarioPreparationNotExecuted, ...]
    omitted_family_refs: tuple[str, ...]
    omitted_branch_node_ids: tuple[str, ...]
    family_outcomes: Mapping[str, str]
    branch_coverage: ScenarioPreparationBranchCoverage
    target_stage_coverage: Mapping[str, ScenarioPreparationStageCoverage]
    projected_node_coverage: ScenarioProjectedNodeCoverage
    batch_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "family_outcomes",
            MappingProxyType(dict(self.family_outcomes)),
        )
        object.__setattr__(
            self,
            "target_stage_coverage",
            MappingProxyType(dict(self.target_stage_coverage)),
        )
        if self.preparation_source_status not in PREPARATION_SOURCE_STATUSES:
            raise ValueError("scenario preparation source status is unsupported")
        for digest in (
            self.source_snapshot_hash,
            self.source_profile_hash,
            self.source_plan_hash,
            self.batch_hash,
        ):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("scenario batch hashes must be SHA-256")
        if self.status not in BATCH_STATUSES:
            raise ValueError("scenario batch status is unsupported")
        counts = (
            self.planned_unit_count,
            self.attempted_unit_count,
            self.completed_unit_count,
            self.failed_unit_count,
            self.not_executed_unit_count,
            self.omitted_target_count,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for value in counts
        ) or (
            self.completed_unit_count != len(self.candidates)
            or self.failed_unit_count != len(self.failures)
            or self.not_executed_unit_count != len(self.not_executed)
            or self.attempted_unit_count
            != self.completed_unit_count + self.failed_unit_count
            or self.planned_unit_count
            != self.attempted_unit_count + self.not_executed_unit_count
            or self.planned_unit_count < 1
            or self.planned_unit_count > MAX_PLAN_UNITS
        ):
            raise ValueError("scenario batch counts are invalid")
        if (
            not isinstance(self.candidates, tuple)
            or any(
                not isinstance(item, ScenarioPreparationBatchCandidate)
                for item in self.candidates
            )
            or tuple(item.candidate_ref for item in self.candidates)
            != tuple(
                f"C{index:03d}"
                for index in range(1, len(self.candidates) + 1)
            )
            or len({item.plan_unit_ref for item in self.candidates})
            != len(self.candidates)
        ):
            raise ValueError("scenario batch candidates are invalid")
        if (
            not isinstance(self.failures, tuple)
            or any(
                not isinstance(item, ScenarioPreparationFailure)
                for item in self.failures
            )
            or tuple(item.plan_unit_ref for item in self.failures)
            != tuple(sorted(item.plan_unit_ref for item in self.failures))
            or len({item.plan_unit_ref for item in self.failures})
            != len(self.failures)
        ):
            raise ValueError("scenario batch failures are invalid")
        if (
            not isinstance(self.not_executed, tuple)
            or any(
                not isinstance(item, ScenarioPreparationNotExecuted)
                for item in self.not_executed
            )
            or tuple(item.plan_unit_ref for item in self.not_executed)
            != tuple(sorted(item.plan_unit_ref for item in self.not_executed))
            or len({item.plan_unit_ref for item in self.not_executed})
            != len(self.not_executed)
        ):
            raise ValueError("not-executed scenario units are invalid")
        completed_refs = {item.plan_unit_ref for item in self.candidates}
        failed_refs = {item.plan_unit_ref for item in self.failures}
        not_executed_refs = {item.plan_unit_ref for item in self.not_executed}
        if (
            completed_refs & failed_refs
            or completed_refs & not_executed_refs
            or failed_refs & not_executed_refs
            or len(completed_refs | failed_refs | not_executed_refs)
            != self.planned_unit_count
        ):
            raise ValueError("scenario batch unit outcomes are not a partition")
        _validate_enum_tuple(
            self.omitted_family_refs,
            "omitted_family_refs",
            SCENARIO_FAMILIES,
        )
        _validate_internal_id_tuple(
            self.omitted_branch_node_ids,
            "omitted_branch_node_ids",
            require_non_empty=False,
        )
        if self.omitted_target_count != len(self.omitted_family_refs) + len(
            self.omitted_branch_node_ids
        ):
            raise ValueError("scenario batch omitted count is invalid")
        if (
            not isinstance(self.family_outcomes, MappingProxyType)
            or tuple(self.family_outcomes) != SCENARIO_FAMILY_ORDER
            or any(
                value not in FAMILY_PREPARATION_OUTCOMES
                for value in self.family_outcomes.values()
            )
            or self.omitted_family_refs
            != tuple(
                family
                for family in SCENARIO_FAMILY_ORDER
                if self.family_outcomes[family] == "OMITTED_BUDGET"
            )
        ):
            raise ValueError("scenario family coverage is invalid")
        if (
            not isinstance(
                self.branch_coverage,
                ScenarioPreparationBranchCoverage,
            )
            or self.omitted_branch_node_ids
            != self.branch_coverage.omitted_budget_branch_node_ids
        ):
            raise ValueError("scenario branch coverage is invalid")
        if (
            not isinstance(self.target_stage_coverage, MappingProxyType)
            or tuple(self.target_stage_coverage) != TARGET_STAGE_ORDER
            or any(
                not isinstance(item, ScenarioPreparationStageCoverage)
                for item in self.target_stage_coverage.values()
            )
            or sum(
                item.planned_unit_count
                for item in self.target_stage_coverage.values()
            )
            != self.planned_unit_count
            or sum(
                item.candidate_ready_unit_count
                for item in self.target_stage_coverage.values()
            )
            != self.completed_unit_count
            or sum(
                item.failed_unit_count
                for item in self.target_stage_coverage.values()
            )
            != self.failed_unit_count
            or sum(
                item.not_executed_unit_count
                for item in self.target_stage_coverage.values()
            )
            != self.not_executed_unit_count
        ):
            raise ValueError("scenario target-stage coverage is invalid")
        if not isinstance(
            self.projected_node_coverage,
            ScenarioProjectedNodeCoverage,
        ):
            raise ValueError("scenario projected-node coverage is invalid")
        expected_status = (
            "FAILED"
            if not self.candidates
            and self.failed_unit_count == self.planned_unit_count
            else (
                "PARTIAL"
                if self.failures
                or self.not_executed
                or self.omitted_target_count
                else "SUCCESS"
            )
        )
        if self.status != expected_status:
            raise ValueError("scenario batch status disagrees with its evidence")
        if self.batch_hash != canonical_digest(self._payload()):
            raise ValueError("scenario preparation batch hash is invalid")

    @property
    def review_status(self) -> str:
        return REVIEW_STATUS

    @property
    def semantic_approval(self) -> bool:
        return False

    @property
    def gold_eligible(self) -> bool:
        return False

    @property
    def patch_eligible(self) -> bool:
        return False

    @property
    def reviewable_candidate_count(self) -> int:
        return len(self.candidates)

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        plan: ScenarioPreparationPlan,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
    ) -> "ScenarioPreparationBatch":
        """Rebuild a stored batch from every trusted deterministic projection."""

        verify_scenario_preparation_plan_against_sources(plan, profile, tree)
        if not isinstance(payload, dict) or set(payload) != _SCENARIO_BATCH_KEYS:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_BATCH_FIELDS_INVALID",
                "stored scenario batch must use exact fields",
            )
        if payload["schema_version"] != SCENARIO_BATCH_SCHEMA_VERSION:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_BATCH_VERSION_INVALID",
                "stored scenario batch schema is unsupported",
            )
        if (
            payload["review_status"] != REVIEW_STATUS
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_BATCH_POLICY_INVALID",
                "stored scenario batch violates pending-review policy",
            )
        projections: list[ScenarioPreparationProjection] = []
        projection_failure_codes: dict[str, str] = {}
        for unit in plan.units:
            try:
                projection = build_scenario_preparation_projection(
                    tree,
                    profile,
                    plan,
                    unit.plan_unit_ref,
                )
            except TreeUnderstandingError as exc:
                if exc.code not in SCENARIO_PROJECTION_UNIT_FAILURE_CODES:
                    raise
                projection_failure_codes[unit.plan_unit_ref] = exc.code
            else:
                projections.append(projection)
        projection_items = tuple(projections)
        projection_by_ref = {
            projection.plan_unit_ref: projection
            for projection in projection_items
        }
        try:
            candidate_drafts: list[ScenarioCandidateDraft] = []
            for item in payload["candidates"]:
                if (
                    not isinstance(item, dict)
                    or set(item) != _SCENARIO_BATCH_CANDIDATE_KEYS
                    or item["plan_unit_ref"] not in projection_by_ref
                ):
                    raise ValueError("stored batch candidate wrapper is invalid")
                candidate_drafts.append(
                    ScenarioCandidateDraft.from_dict(
                        item["draft"],
                        projection_by_ref[item["plan_unit_ref"]],
                        plan,
                        profile,
                        tree,
                    )
                )
            failure_items = tuple(
                ScenarioPreparationFailure(**item)
                for item in payload["failures"]
                if isinstance(item, dict)
                and set(item) == _SCENARIO_FAILURE_KEYS
            )
            not_executed_items = tuple(
                ScenarioPreparationNotExecuted(**item)
                for item in payload["not_executed"]
                if isinstance(item, dict)
                and set(item) == _SCENARIO_NOT_EXECUTED_KEYS
            )
            if (
                len(failure_items) != len(payload["failures"])
                or len(not_executed_items) != len(payload["not_executed"])
            ):
                raise ValueError("stored batch outcome wrapper is invalid")
            stored_failure_codes = {
                item.plan_unit_ref: item.error_code
                for item in failure_items
            }
            if any(
                stored_failure_codes.get(plan_unit_ref) != error_code
                for plan_unit_ref, error_code
                in projection_failure_codes.items()
            ):
                raise TreeUnderstandingError(
                    "SCENARIO_PREPARATION_BATCH_PROJECTION_SOURCE_MISMATCH",
                    "stored projection failure does not match trusted replay",
                )
            expected = build_scenario_preparation_batch(
                plan,
                candidate_drafts,
                failure_items,
                not_executed_items,
                projections=projection_items,
                source_node_count=profile.node_count,
                preparation_source_status=payload[
                    "preparation_source_status"
                ],
            )
        except TreeUnderstandingError:
            raise
        except (KeyError, TypeError, ValueError):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_BATCH_VALUE_INVALID",
                "stored scenario batch failed local validation",
            ) from None
        if payload != expected.to_dict():
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_BATCH_SOURCE_MISMATCH",
                "stored scenario batch does not match trusted sources",
            )
        return expected

    def _payload(self) -> dict[str, Any]:
        return _scenario_batch_payload(
            preparation_source_status=self.preparation_source_status,
            source_snapshot_hash=self.source_snapshot_hash,
            source_profile_hash=self.source_profile_hash,
            source_plan_hash=self.source_plan_hash,
            status=self.status,
            planned_unit_count=self.planned_unit_count,
            attempted_unit_count=self.attempted_unit_count,
            completed_unit_count=self.completed_unit_count,
            failed_unit_count=self.failed_unit_count,
            not_executed_unit_count=self.not_executed_unit_count,
            omitted_target_count=self.omitted_target_count,
            candidates=self.candidates,
            failures=self.failures,
            not_executed=self.not_executed,
            omitted_family_refs=self.omitted_family_refs,
            omitted_branch_node_ids=self.omitted_branch_node_ids,
            family_outcomes=self.family_outcomes,
            branch_coverage=self.branch_coverage,
            target_stage_coverage=self.target_stage_coverage,
            projected_node_coverage=self.projected_node_coverage,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["batch_hash"] = self.batch_hash
        return payload


def build_scenario_preparation_batch(
    plan: ScenarioPreparationPlan,
    candidates: Iterable[ScenarioCandidateDraft],
    failures: Iterable[ScenarioPreparationFailure],
    not_executed: Iterable[ScenarioPreparationNotExecuted] = (),
    *,
    projections: Iterable[ScenarioPreparationProjection],
    source_node_count: int,
    preparation_source_status: str = "UNVERIFIED_MODEL_GENERATION",
) -> ScenarioPreparationBatch:
    """Aggregate outcomes and four non-interchangeable coverage dimensions."""

    if not isinstance(plan, ScenarioPreparationPlan):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_SOURCE_INVALID",
            "batch requires a trusted typed plan",
        )
    if preparation_source_status not in PREPARATION_SOURCE_STATUSES:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_SOURCE_STATUS_INVALID",
            "batch preparation source status is unsupported",
        )
    if (
        not isinstance(source_node_count, int)
        or isinstance(source_node_count, bool)
        or source_node_count < 1
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_COVERAGE_INVALID",
            "batch source node count is invalid",
        )
    candidate_items = tuple(candidates)
    failure_items = tuple(failures)
    not_executed_items = tuple(not_executed)
    projection_items = tuple(projections)
    if any(not isinstance(item, ScenarioCandidateDraft) for item in candidate_items):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_CANDIDATE_INVALID",
            "batch candidates must be locally validated drafts",
        )
    if any(not isinstance(item, ScenarioPreparationFailure) for item in failure_items):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_FAILURE_INVALID",
            "batch failures must be typed stable records",
        )
    if any(
        not isinstance(item, ScenarioPreparationNotExecuted)
        for item in not_executed_items
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_NOT_EXECUTED_INVALID",
            "not-executed units must be typed stable records",
        )
    if any(
        not isinstance(item, ScenarioPreparationProjection)
        for item in projection_items
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_PROJECTION_SOURCE_MISMATCH",
            "batch projections must be trusted typed artifacts",
        )
    plan_rank = {ref: index for index, ref in enumerate(plan.plan_unit_refs)}
    if any(
        item.plan_unit_ref not in plan_rank
        or item.source_snapshot_hash != plan.source_snapshot_hash
        or item.source_profile_hash != plan.source_profile_hash
        or item.source_plan_hash != plan.plan_hash
        for item in candidate_items
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_CANDIDATE_SOURCE_MISMATCH",
            "candidate does not belong to the trusted plan",
        )
    if any(item.plan_unit_ref not in plan_rank for item in failure_items):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_FAILURE_INVALID",
            "failure references a unit outside the trusted plan",
        )
    projection_refs = [item.plan_unit_ref for item in projection_items]
    if (
        len(projection_refs) != len(set(projection_refs))
        or any(
            projection.plan_unit_ref not in plan_rank
            or projection.source_snapshot_hash != plan.source_snapshot_hash
            or projection.source_profile_hash != plan.source_profile_hash
            or projection.source_plan_hash != plan.plan_hash
            or projection.total_node_count != source_node_count
            for projection in projection_items
        )
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_PROJECTION_SOURCE_MISMATCH",
            "batch projection does not belong to the trusted plan",
        )
    candidate_refs = [item.plan_unit_ref for item in candidate_items]
    failure_refs = [item.plan_unit_ref for item in failure_items]
    not_executed_refs = [item.plan_unit_ref for item in not_executed_items]
    if (
        len(candidate_refs) != len(set(candidate_refs))
        or len(failure_refs) != len(set(failure_refs))
        or len(not_executed_refs) != len(set(not_executed_refs))
        or set(candidate_refs) & set(failure_refs)
        or set(candidate_refs) & set(not_executed_refs)
        or set(failure_refs) & set(not_executed_refs)
        or set(candidate_refs) | set(failure_refs) | set(not_executed_refs)
        != set(plan.plan_unit_refs)
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_PARTITION_INVALID",
            "every planned unit must be success, failure, or not-executed",
        )
    preprojection_failure_refs = {
        item.plan_unit_ref
        for item in failure_items
        if item.error_code in SCENARIO_PROJECTION_UNIT_FAILURE_CODES
    }
    expected_projection_refs = set(plan.plan_unit_refs) - preprojection_failure_refs
    if set(projection_refs) != expected_projection_refs:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_PROJECTION_PARTITION_INVALID",
            "all and only successfully prebuilt unit projections are required",
        )
    projection_by_ref = {
        projection.plan_unit_ref: projection for projection in projection_items
    }
    if any(
        item.source_projection_hash
        != projection_by_ref[item.plan_unit_ref].projection_hash
        for item in candidate_items
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_CANDIDATE_SOURCE_MISMATCH",
            "candidate does not bind its trusted unit projection",
        )
    ordered_drafts = tuple(
        sorted(candidate_items, key=lambda item: plan_rank[item.plan_unit_ref])
    )
    wrapped_candidates = tuple(
        ScenarioPreparationBatchCandidate(
            candidate_ref=f"C{index:03d}",
            plan_unit_ref=draft.plan_unit_ref,
            source_draft_hash=draft.draft_hash,
            draft=draft,
        )
        for index, draft in enumerate(ordered_drafts, start=1)
    )
    ordered_failures = tuple(
        sorted(failure_items, key=lambda item: plan_rank[item.plan_unit_ref])
    )
    ordered_not_executed = tuple(
        sorted(
            not_executed_items,
            key=lambda item: plan_rank[item.plan_unit_ref],
        )
    )
    omitted_families = tuple(
        family
        for family in SCENARIO_FAMILY_ORDER
        if plan.family_statuses[family] == "OMITTED_BUDGET"
    )
    omitted_target_count = len(omitted_families) + len(
        plan.omitted_branch_node_ids
    )
    outcome_by_ref = {
        **{item.plan_unit_ref: "CANDIDATE_READY" for item in ordered_drafts},
        **{item.plan_unit_ref: "FAILED" for item in ordered_failures},
        **{
            item.plan_unit_ref: "NOT_EXECUTED"
            for item in ordered_not_executed
        },
    }
    family_outcomes = _build_family_outcomes(plan, outcome_by_ref)
    branch_coverage = _build_branch_coverage(plan, outcome_by_ref)
    target_stage_coverage = _build_target_stage_coverage(
        plan,
        outcome_by_ref,
    )
    projected_node_ids = {
        node_id
        for projection in projection_items
        for node_id in projection.reference_to_node_id.values()
    }
    if len(projected_node_ids) > source_node_count:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_COVERAGE_INVALID",
            "projected unique-node coverage exceeds the trusted source count",
        )
    projected_node_coverage = ScenarioProjectedNodeCoverage(
        total_node_count=source_node_count,
        included_node_count=len(projected_node_ids),
        omitted_node_count=source_node_count - len(projected_node_ids),
        coverage_complete=len(projected_node_ids) == source_node_count,
    )
    status = (
        "FAILED"
        if not wrapped_candidates and len(ordered_failures) == len(plan.units)
        else (
            "PARTIAL"
            if ordered_failures or ordered_not_executed or omitted_target_count
            else "SUCCESS"
        )
    )
    payload = _scenario_batch_payload(
        preparation_source_status=preparation_source_status,
        source_snapshot_hash=plan.source_snapshot_hash,
        source_profile_hash=plan.source_profile_hash,
        source_plan_hash=plan.plan_hash,
        status=status,
        planned_unit_count=len(plan.units),
        attempted_unit_count=len(wrapped_candidates) + len(ordered_failures),
        completed_unit_count=len(wrapped_candidates),
        failed_unit_count=len(ordered_failures),
        not_executed_unit_count=len(ordered_not_executed),
        omitted_target_count=omitted_target_count,
        candidates=wrapped_candidates,
        failures=ordered_failures,
        not_executed=ordered_not_executed,
        omitted_family_refs=omitted_families,
        omitted_branch_node_ids=plan.omitted_branch_node_ids,
        family_outcomes=family_outcomes,
        branch_coverage=branch_coverage,
        target_stage_coverage=target_stage_coverage,
        projected_node_coverage=projected_node_coverage,
    )
    return ScenarioPreparationBatch(
        preparation_source_status=preparation_source_status,
        source_snapshot_hash=plan.source_snapshot_hash,
        source_profile_hash=plan.source_profile_hash,
        source_plan_hash=plan.plan_hash,
        status=status,
        planned_unit_count=len(plan.units),
        attempted_unit_count=len(wrapped_candidates) + len(ordered_failures),
        completed_unit_count=len(wrapped_candidates),
        failed_unit_count=len(ordered_failures),
        not_executed_unit_count=len(ordered_not_executed),
        omitted_target_count=omitted_target_count,
        candidates=wrapped_candidates,
        failures=ordered_failures,
        not_executed=ordered_not_executed,
        omitted_family_refs=omitted_families,
        omitted_branch_node_ids=plan.omitted_branch_node_ids,
        family_outcomes=family_outcomes,
        branch_coverage=branch_coverage,
        target_stage_coverage=target_stage_coverage,
        projected_node_coverage=projected_node_coverage,
        batch_hash=canonical_digest(payload),
    )


def _build_family_outcomes(
    plan: ScenarioPreparationPlan,
    outcome_by_ref: Mapping[str, str],
) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for family in SCENARIO_FAMILY_ORDER:
        plan_status = plan.family_statuses[family]
        if plan_status in {"NOT_APPLICABLE", "OMITTED_BUDGET"}:
            outcomes[family] = plan_status
            continue
        risk_units = tuple(
            unit
            for unit in plan.units
            if unit.unit_role == "RISK_CHALLENGE"
            and unit.scenario_family == family
        )
        if len(risk_units) != 1 or risk_units[0].plan_unit_ref not in outcome_by_ref:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_BATCH_FAMILY_COVERAGE_INVALID",
                "planned scenario family lacks one exact risk-unit outcome",
            )
        outcomes[family] = outcome_by_ref[risk_units[0].plan_unit_ref]
    return outcomes


def _build_branch_coverage(
    plan: ScenarioPreparationPlan,
    outcome_by_ref: Mapping[str, str],
) -> ScenarioPreparationBranchCoverage:
    branches_by_outcome: dict[str, set[str]] = {
        "CANDIDATE_READY": set(),
        "FAILED": set(),
        "NOT_EXECUTED": set(),
    }
    for unit in plan.units:
        if unit.planning_mode != "BRANCH_LOCAL":
            continue
        outcome = outcome_by_ref[unit.plan_unit_ref]
        branches_by_outcome[outcome].update(unit.allowed_branch_node_ids)
    return ScenarioPreparationBranchCoverage(
        candidate_ready_branch_node_ids=tuple(
            sorted(branches_by_outcome["CANDIDATE_READY"])
        ),
        failed_branch_node_ids=tuple(sorted(branches_by_outcome["FAILED"])),
        not_executed_branch_node_ids=tuple(
            sorted(branches_by_outcome["NOT_EXECUTED"])
        ),
        omitted_budget_branch_node_ids=plan.omitted_branch_node_ids,
    )


def _build_target_stage_coverage(
    plan: ScenarioPreparationPlan,
    outcome_by_ref: Mapping[str, str],
) -> dict[str, ScenarioPreparationStageCoverage]:
    result: dict[str, ScenarioPreparationStageCoverage] = {}
    for stage in TARGET_STAGE_ORDER:
        stage_outcomes = tuple(
            outcome_by_ref[unit.plan_unit_ref]
            for unit in plan.units
            if unit.target_stage == stage
        )
        result[stage] = ScenarioPreparationStageCoverage(
            planned_unit_count=len(stage_outcomes),
            candidate_ready_unit_count=stage_outcomes.count(
                "CANDIDATE_READY"
            ),
            failed_unit_count=stage_outcomes.count("FAILED"),
            not_executed_unit_count=stage_outcomes.count("NOT_EXECUTED"),
        )
    return result


def verify_scenario_preparation_batch_against_sources(
    batch: ScenarioPreparationBatch,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    """Replay a batch, including coverage, from every successful projection."""

    if not isinstance(batch, ScenarioPreparationBatch):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_SOURCE_MISMATCH",
            "scenario batch is not a trusted typed artifact",
        )
    expected = ScenarioPreparationBatch.from_dict(
        batch.to_dict(),
        plan,
        profile,
        tree,
    )
    if batch != expected:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_BATCH_SOURCE_MISMATCH",
            "scenario batch does not match trusted source replay",
        )


def build_tree_diagnostic_profile(tree: CanonicalTree) -> TreeDiagnosticProfile:
    """Scan a complete canonical tree without model or IO side effects."""

    nodes_by_id, depth_by_id = _validate_and_index_tree(tree)
    branches = _build_branch_profiles(tree, nodes_by_id, depth_by_id)
    findings = _build_findings(nodes_by_id)
    kind_counts = _counts(node.kind for node in nodes_by_id.values())
    value_type_counts = _counts(
        (
            node.value_contract.value_type
            if node.value_contract is not None
            else _NONE
        )
        for node in nodes_by_id.values()
    )
    cardinality_counts = _counts(
        (
            node.value_contract.cardinality
            if node.value_contract is not None
            else _NONE
        )
        for node in nodes_by_id.values()
    )
    depth_counts = _counts(str(depth) for depth in depth_by_id.values())
    payload = _profile_payload(
        schema_version=SCHEMA_VERSION,
        algorithm_version=ALGORITHM_VERSION,
        source_snapshot_hash=tree.snapshot_hash,
        source_tree_id=tree.tree_id,
        source_tree_version=tree.tree_version,
        node_count=len(nodes_by_id),
        root_count=len(tree.root_node_ids),
        max_depth=max(depth_by_id.values()),
        kind_counts=kind_counts,
        value_type_counts=value_type_counts,
        cardinality_counts=cardinality_counts,
        depth_counts=depth_counts,
        top_level_branches=branches,
        findings=findings,
    )
    return TreeDiagnosticProfile(
        schema_version=SCHEMA_VERSION,
        algorithm_version=ALGORITHM_VERSION,
        source_snapshot_hash=tree.snapshot_hash,
        source_tree_id=tree.tree_id,
        source_tree_version=tree.tree_version,
        node_count=len(nodes_by_id),
        root_count=len(tree.root_node_ids),
        max_depth=max(depth_by_id.values()),
        kind_counts=kind_counts,
        value_type_counts=value_type_counts,
        cardinality_counts=cardinality_counts,
        depth_counts=depth_counts,
        top_level_branches=branches,
        findings=findings,
        profile_hash=canonical_digest(payload),
    )


def verify_tree_diagnostic_profile_against_tree(
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    """Reject self-consistent profiles that do not match the trusted tree."""

    expected = build_tree_diagnostic_profile(tree)
    if profile.to_dict() != expected.to_dict():
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_PROFILE_SOURCE_MISMATCH",
            "tree diagnostic profile does not match the trusted source tree",
        )


def build_scenario_preparation_plan(
    tree: CanonicalTree,
    profile: TreeDiagnosticProfile,
    *,
    max_plan_units: int = DEFAULT_MAX_PLAN_UNITS,
    node_limit: int = DEFAULT_SCENARIO_MODEL_NODES,
    new_node_placement_seed: NewNodePlacementSeed | None = None,
) -> ScenarioPreparationPlan:
    """Build a sparse risk-first plan without asking a model to choose coverage."""

    verify_tree_diagnostic_profile_against_tree(profile, tree)
    if (
        not isinstance(max_plan_units, int)
        or isinstance(max_plan_units, bool)
        or max_plan_units < 1
        or max_plan_units > MAX_PLAN_UNITS
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PLAN_UNIT_LIMIT_INVALID",
            "max_plan_units is outside its fixed bound",
        )
    if (
        not isinstance(node_limit, int)
        or isinstance(node_limit, bool)
        or node_limit < 1
        or node_limit > MAX_SCENARIO_MODEL_NODES
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PROJECTION_NODE_LIMIT_INVALID",
            "scenario projection node_limit is outside its fixed bound",
        )
    if new_node_placement_seed is not None and not isinstance(
        new_node_placement_seed,
        NewNodePlacementSeed,
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_NEW_NODE_SEED_INVALID",
            "new-node placement requires a trusted typed seed",
        )

    nodes_by_id, depth_by_id = _validate_and_index_tree(tree)
    branch_by_node_id = _build_top_branch_map(profile, nodes_by_id)
    branch_profiles = tuple(profile.top_level_branches)
    if new_node_placement_seed is not None:
        parent_id = new_node_placement_seed.parent_node_id
        existing_names = {
            _normalize_name(node.name) for node in nodes_by_id.values()
        }
        if (
            parent_id not in nodes_by_id
            or branch_by_node_id.get(parent_id) is None
            or _normalize_name(new_node_placement_seed.proposed_name)
            in existing_names
        ):
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_NEW_NODE_SEED_INVALID",
                "new-node seed must name an absent node beneath an existing branch",
            )

    representative_branches = _select_representative_branches(
        branch_profiles,
        len(branch_profiles),
    )
    risk_specs: dict[str, dict[str, Any] | None] = {
        family: None for family in SCENARIO_FAMILY_ORDER
    }

    clear_branch = representative_branches[0]
    clear_anchor = _select_branch_anchor(
        clear_branch.branch_node_id,
        nodes_by_id,
        depth_by_id,
        branch_by_node_id,
    )
    risk_specs["CLEAR_EXISTING_REUSE"] = _scenario_unit_spec(
        unit_role="RISK_CHALLENGE",
        planning_mode="BRANCH_LOCAL",
        scenario_family="CLEAR_EXISTING_REUSE",
        target_stage="RETRIEVAL",
        primary_anchor_node_id=clear_anchor,
        anchor_node_ids=(clear_anchor,),
        allowed_branch_node_ids=(clear_branch.branch_node_id,),
        node_limit=node_limit,
    )

    if new_node_placement_seed is not None:
        seed_branch_id = branch_by_node_id[new_node_placement_seed.parent_node_id]
        if seed_branch_id is None:  # guarded above; keeps the type narrow
            raise AssertionError("validated new-node seed lost its branch")
        value_policy = (
            "SEED_DEFINED"
            if new_node_placement_seed.value_type_hint is not None
            else "ABSENT"
        )
        cardinality_policy = (
            "SEED_DEFINED"
            if new_node_placement_seed.cardinality_hint is not None
            else "ABSENT"
        )
        risk_specs["NEW_NODE_PLACEMENT"] = _scenario_unit_spec(
            unit_role="RISK_CHALLENGE",
            planning_mode="BRANCH_LOCAL",
            scenario_family="NEW_NODE_PLACEMENT",
            target_stage="RECOMMENDATION",
            primary_anchor_node_id=new_node_placement_seed.parent_node_id,
            anchor_node_ids=(new_node_placement_seed.parent_node_id,),
            allowed_branch_node_ids=(seed_branch_id,),
            parent_hint_policy="CORRECT",
            proposed_parent_node_id=new_node_placement_seed.parent_node_id,
            node_kind_hint_policy="SEED_DEFINED",
            node_kind_hint=new_node_placement_seed.node_kind_hint,
            value_type_hint_policy=value_policy,
            value_type_hint=new_node_placement_seed.value_type_hint,
            cardinality_hint_policy=cardinality_policy,
            cardinality_hint=new_node_placement_seed.cardinality_hint,
            node_limit=node_limit,
        )

    homonym = _select_name_reuse_pair(
        profile,
        nodes_by_id,
        branch_by_node_id,
    )
    if homonym is not None:
        finding, anchors = homonym
        allowed = _branches_for_anchors(anchors, branch_by_node_id)
        risk_specs["HOMONYM_CLARIFICATION"] = _scenario_unit_spec(
            unit_role="RISK_CHALLENGE",
            planning_mode="CONTRAST",
            scenario_family="HOMONYM_CLARIFICATION",
            target_stage="INTENT",
            primary_anchor_node_id=anchors[0],
            anchor_node_ids=anchors,
            allowed_branch_node_ids=allowed,
            finding_code=finding.code,
            node_limit=node_limit,
        )

    if len(representative_branches) >= 2:
        target_branch, conflicting_branch = representative_branches[:2]
        target_anchor = _select_branch_anchor(
            target_branch.branch_node_id,
            nodes_by_id,
            depth_by_id,
            branch_by_node_id,
        )
        conflicting_parent = conflicting_branch.branch_node_id
        risk_specs["WRONG_PARENT_OR_CROSS_BRANCH"] = _scenario_unit_spec(
            unit_role="RISK_CHALLENGE",
            planning_mode="CONTRAST",
            scenario_family="WRONG_PARENT_OR_CROSS_BRANCH",
            target_stage="RECOMMENDATION",
            primary_anchor_node_id=target_anchor,
            anchor_node_ids=(target_anchor, conflicting_parent),
            allowed_branch_node_ids=(
                target_branch.branch_node_id,
                conflicting_branch.branch_node_id,
            ),
            parent_hint_policy="INTENTIONALLY_CONFLICTING",
            proposed_parent_node_id=conflicting_parent,
            node_limit=node_limit,
        )

    kind_branch = representative_branches[0]
    kind_anchor = _select_branch_anchor(
        kind_branch.branch_node_id,
        nodes_by_id,
        depth_by_id,
        branch_by_node_id,
    )
    kind_hint = (
        "CONCEPT" if nodes_by_id[kind_anchor].kind == "PROPERTY" else "PROPERTY"
    )
    risk_specs["KIND_CONFLICT"] = _scenario_unit_spec(
        unit_role="RISK_CHALLENGE",
        planning_mode="BRANCH_LOCAL",
        scenario_family="KIND_CONFLICT",
        target_stage="RECOMMENDATION",
        primary_anchor_node_id=kind_anchor,
        anchor_node_ids=(kind_anchor,),
        allowed_branch_node_ids=(kind_branch.branch_node_id,),
        node_kind_hint_policy="INTENTIONALLY_CONFLICTING",
        node_kind_hint=kind_hint,
        node_limit=node_limit,
    )

    cardinality_anchor = _select_cardinality_anchor(
        representative_branches,
        nodes_by_id,
        depth_by_id,
        branch_by_node_id,
    )
    if cardinality_anchor is not None:
        cardinality_node = nodes_by_id[cardinality_anchor]
        contract = cardinality_node.value_contract
        if contract is None:
            raise AssertionError("cardinality anchor lost its value contract")
        cardinality_branch_id = branch_by_node_id[cardinality_anchor]
        if cardinality_branch_id is None:
            raise AssertionError("cardinality anchor lost its branch")
        risk_specs["CARDINALITY_CONFLICT"] = _scenario_unit_spec(
            unit_role="RISK_CHALLENGE",
            planning_mode="BRANCH_LOCAL",
            scenario_family="CARDINALITY_CONFLICT",
            target_stage="RECOMMENDATION",
            primary_anchor_node_id=cardinality_anchor,
            anchor_node_ids=(cardinality_anchor,),
            allowed_branch_node_ids=(cardinality_branch_id,),
            cardinality_hint_policy="INTENTIONALLY_CONFLICTING",
            cardinality_hint=(
                "MULTIPLE" if contract.cardinality == "SINGLE" else "SINGLE"
            ),
            node_limit=node_limit,
        )

    evidence_branch = representative_branches[0]
    evidence_anchor = _select_branch_anchor(
        evidence_branch.branch_node_id,
        nodes_by_id,
        depth_by_id,
        branch_by_node_id,
    )
    risk_specs["INSUFFICIENT_EVIDENCE"] = _scenario_unit_spec(
        unit_role="RISK_CHALLENGE",
        planning_mode="AMBIGUITY",
        scenario_family="INSUFFICIENT_EVIDENCE",
        target_stage="INTENT",
        primary_anchor_node_id=evidence_anchor,
        anchor_node_ids=(evidence_anchor,),
        allowed_branch_node_ids=(evidence_branch.branch_node_id,),
        node_limit=node_limit,
    )

    if len(representative_branches) >= 2:
        combination_branches = representative_branches[:3]
        combination_anchors = tuple(
            branch.branch_node_id for branch in combination_branches
        )
        risk_specs["UNBOUNDED_COMBINATION"] = _scenario_unit_spec(
            unit_role="RISK_CHALLENGE",
            planning_mode="AMBIGUITY",
            scenario_family="UNBOUNDED_COMBINATION",
            target_stage="INTENT",
            primary_anchor_node_id=combination_anchors[0],
            anchor_node_ids=combination_anchors,
            allowed_branch_node_ids=combination_anchors,
            node_limit=node_limit,
        )

    selected_specs: list[dict[str, Any]] = []
    family_statuses: dict[str, str] = {}
    for family in SCENARIO_FAMILY_ORDER:
        spec = risk_specs[family]
        if spec is None:
            family_statuses[family] = "NOT_APPLICABLE"
        elif len(selected_specs) < max_plan_units:
            selected_specs.append(spec)
            family_statuses[family] = "PLANNED"
        else:
            family_statuses[family] = "OMITTED_BUDGET"

    covered_branches = {
        spec["allowed_branch_node_ids"][0]
        for spec in selected_specs
        if spec["planning_mode"] == "BRANCH_LOCAL"
    }
    branch_slots = max_plan_units - len(selected_specs)
    uncovered_profiles = tuple(
        branch
        for branch in branch_profiles
        if branch.branch_node_id not in covered_branches
    )
    selected_for_coverage = _select_representative_branches(
        uncovered_profiles,
        branch_slots,
    )
    for branch in selected_for_coverage:
        anchor = _select_branch_anchor(
            branch.branch_node_id,
            nodes_by_id,
            depth_by_id,
            branch_by_node_id,
        )
        selected_specs.append(
            _scenario_unit_spec(
                unit_role="BRANCH_COVERAGE",
                planning_mode="BRANCH_LOCAL",
                scenario_family="CLEAR_EXISTING_REUSE",
                target_stage="RETRIEVAL",
                primary_anchor_node_id=anchor,
                anchor_node_ids=(anchor,),
                allowed_branch_node_ids=(branch.branch_node_id,),
                node_limit=node_limit,
            )
        )
        covered_branches.add(branch.branch_node_id)

    units = tuple(
        ScenarioPlanUnit(plan_unit_ref=f"U{index:03d}", **spec)
        for index, spec in enumerate(selected_specs, start=1)
    )
    all_branch_ids = {branch.branch_node_id for branch in branch_profiles}
    covered_branch_ids = tuple(sorted(covered_branches))
    omitted_branch_ids = tuple(sorted(all_branch_ids - covered_branches))
    payload = _scenario_plan_payload(
        source_snapshot_hash=tree.snapshot_hash,
        source_profile_hash=profile.profile_hash,
        max_plan_units=max_plan_units,
        node_limit=node_limit,
        new_node_placement_seed=new_node_placement_seed,
        family_statuses=family_statuses,
        units=units,
        covered_branch_node_ids=covered_branch_ids,
        omitted_branch_node_ids=omitted_branch_ids,
    )
    return ScenarioPreparationPlan(
        schema_version=SCENARIO_PLAN_SCHEMA_VERSION,
        algorithm_version=SCENARIO_PLAN_ALGORITHM_VERSION,
        source_snapshot_hash=tree.snapshot_hash,
        source_profile_hash=profile.profile_hash,
        max_plan_units=max_plan_units,
        node_limit=node_limit,
        new_node_placement_seed=new_node_placement_seed,
        family_statuses=family_statuses,
        units=units,
        covered_branch_node_ids=covered_branch_ids,
        omitted_branch_node_ids=omitted_branch_ids,
        plan_hash=canonical_digest(payload),
    )


def verify_scenario_preparation_plan_against_sources(
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    """Replay a plan from trusted sources, including its explicit seed overlay."""

    if not isinstance(plan, ScenarioPreparationPlan):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PLAN_SOURCE_MISMATCH",
            "scenario plan is not a trusted typed artifact",
        )
    expected = build_scenario_preparation_plan(
        tree,
        profile,
        max_plan_units=plan.max_plan_units,
        node_limit=plan.node_limit,
        new_node_placement_seed=plan.new_node_placement_seed,
    )
    if plan != expected:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PLAN_SOURCE_MISMATCH",
            "scenario plan does not match trusted sources",
        )


def build_scenario_preparation_projection(
    tree: CanonicalTree,
    profile: TreeDiagnosticProfile,
    plan: ScenarioPreparationPlan,
    plan_unit_ref: str,
) -> ScenarioPreparationProjection:
    """Build one bounded ref scope for exactly one deterministic plan unit."""

    verify_scenario_preparation_plan_against_sources(plan, profile, tree)
    if not isinstance(plan_unit_ref, str) or plan_unit_ref not in plan.plan_unit_refs:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PLAN_UNIT_REF_INVALID",
            "plan unit ref is not in the trusted plan",
        )
    unit = next(item for item in plan.units if item.plan_unit_ref == plan_unit_ref)
    nodes_by_id, depth_by_id = _validate_and_index_tree(tree)
    branch_by_node_id = _build_top_branch_map(profile, nodes_by_id)
    selected_node_ids: set[str] = set()

    def include_with_ancestors(node_id: str, *, required: bool) -> None:
        chain: list[str] = []
        current_id: str | None = node_id
        while current_id is not None and current_id not in selected_node_ids:
            chain.append(current_id)
            current_id = nodes_by_id[current_id].parent_node_id
        additions = tuple(reversed(chain))
        if len(selected_node_ids) + len(additions) <= unit.node_limit:
            selected_node_ids.update(additions)
        elif required:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_PROJECTION_REQUIRED_SCOPE_TOO_LARGE",
                "required scenario anchors exceed the per-unit node limit",
            )

    for node_id in unit.anchor_node_ids:
        include_with_ancestors(node_id, required=True)
    for branch_id in unit.allowed_branch_node_ids:
        include_with_ancestors(branch_id, required=True)
    for node_id in sorted(
        (
            node_id
            for node_id, branch_id in branch_by_node_id.items()
            if branch_id in unit.allowed_branch_node_ids
        ),
        key=lambda node_id: (
            0 if node_id in unit.anchor_node_ids else 1,
            depth_by_id[node_id],
            node_id,
        ),
    ):
        include_with_ancestors(node_id, required=False)

    ordered_node_ids = tuple(
        sorted(selected_node_ids, key=lambda node_id: (depth_by_id[node_id], node_id))
    )
    ref_by_node_id = {
        node_id: f"N{index:03d}"
        for index, node_id in enumerate(ordered_node_ids, start=1)
    }
    node_views = tuple(
        TreeUnderstandingNodeView(
            node_ref=ref_by_node_id[node_id],
            parent_ref=(
                ref_by_node_id.get(nodes_by_id[node_id].parent_node_id)
                if nodes_by_id[node_id].parent_node_id is not None
                else None
            ),
            depth=depth_by_id[node_id],
            name=nodes_by_id[node_id].name,
            kind=nodes_by_id[node_id].kind,
            value_type=(
                nodes_by_id[node_id].value_contract.value_type
                if nodes_by_id[node_id].value_contract is not None
                else None
            ),
            cardinality=(
                nodes_by_id[node_id].value_contract.cardinality
                if nodes_by_id[node_id].value_contract is not None
                else None
            ),
            direct_child_count=len(nodes_by_id[node_id].child_node_ids),
            included_child_refs=tuple(
                sorted(
                    ref_by_node_id[child_id]
                    for child_id in nodes_by_id[node_id].child_node_ids
                    if child_id in ref_by_node_id
                )
            ),
        )
        for node_id in ordered_node_ids
    )
    anchor_refs = tuple(
        sorted(ref_by_node_id[node_id] for node_id in unit.anchor_node_ids)
    )
    evidence_refs = tuple(
        sorted(
            ref_by_node_id[node_id]
            for node_id in ordered_node_ids
            if branch_by_node_id[node_id] in unit.allowed_branch_node_ids
        )
    )
    signal: ScenarioPreparationSignalView | None = None
    if unit.finding_code is not None:
        matching_findings = tuple(
            finding
            for finding in profile.findings
            if finding.code == unit.finding_code
            and set(unit.anchor_node_ids).issubset(finding.node_ids)
        )
        if len(matching_findings) != 1:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_PLAN_SOURCE_MISMATCH",
                "planned finding anchor no longer matches the trusted profile",
            )
        finding = matching_findings[0]
        signal = ScenarioPreparationSignalView(
            signal_ref="D001",
            code=finding.code,
            node_refs=anchor_refs,
            source_occurrence_count=finding.occurrence_count,
        )
    proposed_new_node_name = (
        plan.new_node_placement_seed.proposed_name
        if unit.scenario_family == "NEW_NODE_PLACEMENT"
        and plan.new_node_placement_seed is not None
        else None
    )
    model_payload = _scenario_model_input_payload(
        plan_unit_ref=unit.plan_unit_ref,
        unit_role=unit.unit_role,
        planning_mode=unit.planning_mode,
        scenario_family=unit.scenario_family,
        target_stage=unit.target_stage,
        parent_hint_policy=unit.parent_hint_policy,
        node_kind_hint_policy=unit.node_kind_hint_policy,
        value_type_hint_policy=unit.value_type_hint_policy,
        cardinality_hint_policy=unit.cardinality_hint_policy,
        proposed_new_node_name=proposed_new_node_name,
        node_kind_hint=unit.node_kind_hint,
        value_type_hint=unit.value_type_hint,
        cardinality_hint=unit.cardinality_hint,
        total_node_count=profile.node_count,
        root_count=profile.root_count,
        top_level_branch_count=len(profile.top_level_branches),
        included_node_count=len(node_views),
        omitted_node_count=profile.node_count - len(node_views),
        allowed_branch_count=len(unit.allowed_branch_node_ids),
        nodes=node_views,
        signal=signal,
        primary_anchor_ref=ref_by_node_id[unit.primary_anchor_node_id],
        anchor_refs=anchor_refs,
        evidence_node_refs=evidence_refs,
        proposed_parent_ref=(
            ref_by_node_id[unit.proposed_parent_node_id]
            if unit.proposed_parent_node_id is not None
            else None
        ),
    )
    if _serialized_char_count(model_payload) > MAX_SCENARIO_MODEL_INPUT_CHARS:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PROJECTION_TOO_LARGE",
            "scenario projection exceeds its fixed character budget",
        )
    return ScenarioPreparationProjection(
        source_snapshot_hash=tree.snapshot_hash,
        source_profile_hash=profile.profile_hash,
        source_plan_hash=plan.plan_hash,
        plan_unit_ref=unit.plan_unit_ref,
        unit_role=unit.unit_role,
        planning_mode=unit.planning_mode,
        scenario_family=unit.scenario_family,
        target_stage=unit.target_stage,
        parent_hint_policy=unit.parent_hint_policy,
        node_kind_hint_policy=unit.node_kind_hint_policy,
        value_type_hint_policy=unit.value_type_hint_policy,
        cardinality_hint_policy=unit.cardinality_hint_policy,
        proposed_new_node_name=proposed_new_node_name,
        node_kind_hint=unit.node_kind_hint,
        value_type_hint=unit.value_type_hint,
        cardinality_hint=unit.cardinality_hint,
        node_limit=unit.node_limit,
        total_node_count=profile.node_count,
        root_count=profile.root_count,
        top_level_branch_count=len(profile.top_level_branches),
        included_node_count=len(node_views),
        omitted_node_count=profile.node_count - len(node_views),
        allowed_branch_count=len(unit.allowed_branch_node_ids),
        nodes=node_views,
        signal=signal,
        primary_anchor_ref=ref_by_node_id[unit.primary_anchor_node_id],
        anchor_refs=anchor_refs,
        evidence_node_refs=evidence_refs,
        proposed_parent_ref=(
            ref_by_node_id[unit.proposed_parent_node_id]
            if unit.proposed_parent_node_id is not None
            else None
        ),
        reference_to_node_id={ref: node_id for node_id, ref in ref_by_node_id.items()},
        reference_to_branch_node_id={
            ref_by_node_id[node_id]: branch_by_node_id[node_id]
            for node_id in ordered_node_ids
        },
        projection_hash=canonical_digest(model_payload),
    )


def verify_scenario_preparation_projection_against_sources(
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    """Replay one projection from the trusted plan/profile/tree chain."""

    if not isinstance(projection, ScenarioPreparationProjection):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PROJECTION_SOURCE_MISMATCH",
            "scenario projection is not a trusted typed artifact",
        )
    expected = build_scenario_preparation_projection(
        tree,
        profile,
        plan,
        projection.plan_unit_ref,
    )
    if projection != expected:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PROJECTION_SOURCE_MISMATCH",
            "scenario projection does not match trusted sources",
        )


def build_tree_understanding_projection(
    tree: CanonicalTree,
    profile: TreeDiagnosticProfile,
    *,
    node_limit: int = DEFAULT_MAX_MODEL_NODES,
    finding_limit: int = DEFAULT_MAX_MODEL_FINDINGS,
) -> TreeUnderstandingProjection:
    """Build one bounded, source-bound Qwen view from trusted full-tree facts."""

    verify_tree_diagnostic_profile_against_tree(profile, tree)
    if (
        not isinstance(node_limit, int)
        or isinstance(node_limit, bool)
        or node_limit < 1
        or node_limit > MAX_MODEL_NODES
    ):
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_PROJECTION_NODE_LIMIT_INVALID",
            "tree understanding node_limit is outside its fixed bound",
        )
    if (
        not isinstance(finding_limit, int)
        or isinstance(finding_limit, bool)
        or finding_limit < 0
        or finding_limit > MAX_MODEL_FINDINGS
    ):
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_PROJECTION_FINDING_LIMIT_INVALID",
            "tree understanding finding_limit is outside its fixed bound",
        )
    nodes_by_id, depth_by_id = _validate_and_index_tree(tree)
    selected_node_ids: set[str] = set()

    def include_with_ancestors(node_id: str) -> None:
        chain: list[str] = []
        current_id: str | None = node_id
        while current_id is not None and current_id not in selected_node_ids:
            chain.append(current_id)
            current_id = nodes_by_id[current_id].parent_node_id
        additions = tuple(reversed(chain))
        if len(selected_node_ids) + len(additions) <= node_limit:
            selected_node_ids.update(additions)

    for root_id in sorted(tree.root_node_ids):
        include_with_ancestors(root_id)
    for finding in profile.findings[:finding_limit]:
        for node_id in finding.node_ids:
            include_with_ancestors(node_id)
    for branch in profile.top_level_branches:
        include_with_ancestors(branch.branch_node_id)
    for node_id in sorted(
        nodes_by_id,
        key=lambda item: (depth_by_id[item], item),
    ):
        include_with_ancestors(node_id)

    ordered_node_ids = tuple(
        sorted(
            selected_node_ids,
            key=lambda item: (depth_by_id[item], item),
        )
    )
    ref_by_node_id = {
        node_id: f"N{index:03d}"
        for index, node_id in enumerate(ordered_node_ids, start=1)
    }
    node_views = tuple(
        TreeUnderstandingNodeView(
            node_ref=ref_by_node_id[node_id],
            parent_ref=(
                ref_by_node_id.get(nodes_by_id[node_id].parent_node_id)
                if nodes_by_id[node_id].parent_node_id is not None
                else None
            ),
            depth=depth_by_id[node_id],
            name=nodes_by_id[node_id].name,
            kind=nodes_by_id[node_id].kind,
            value_type=(
                nodes_by_id[node_id].value_contract.value_type
                if nodes_by_id[node_id].value_contract is not None
                else None
            ),
            cardinality=(
                nodes_by_id[node_id].value_contract.cardinality
                if nodes_by_id[node_id].value_contract is not None
                else None
            ),
            direct_child_count=len(nodes_by_id[node_id].child_node_ids),
            included_child_refs=tuple(
                sorted(
                    ref_by_node_id[child_id]
                    for child_id in nodes_by_id[node_id].child_node_ids
                    if child_id in ref_by_node_id
                )
            ),
        )
        for node_id in ordered_node_ids
    )
    projected_findings = tuple(
        finding
        for finding in profile.findings
        if set(finding.node_ids).issubset(selected_node_ids)
    )[:finding_limit]
    finding_views = tuple(
        TreeUnderstandingFindingView(
            finding_ref=f"D{index:03d}",
            code=finding.code,
            node_refs=tuple(
                sorted(ref_by_node_id[node_id] for node_id in finding.node_ids)
            ),
            occurrence_count=finding.occurrence_count,
        )
        for index, finding in enumerate(projected_findings, start=1)
    )
    included_node_count = len(node_views)
    included_finding_count = len(finding_views)
    omitted_node_count = profile.node_count - included_node_count
    omitted_finding_count = len(profile.findings) - included_finding_count
    coverage_complete = (
        omitted_node_count == 0 and omitted_finding_count == 0
    )
    model_payload = _tree_understanding_model_payload(
        total_node_count=profile.node_count,
        root_count=profile.root_count,
        max_depth=profile.max_depth,
        included_node_count=included_node_count,
        omitted_node_count=omitted_node_count,
        total_finding_count=len(profile.findings),
        included_finding_count=included_finding_count,
        omitted_finding_count=omitted_finding_count,
        coverage_complete=coverage_complete,
        nodes=node_views,
        findings=finding_views,
    )
    if _serialized_char_count(model_payload) > MAX_MODEL_INPUT_CHARS:
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_PROJECTION_TOO_LARGE",
            "tree understanding projection exceeds its context budget",
        )
    return TreeUnderstandingProjection(
        source_snapshot_hash=tree.snapshot_hash,
        source_profile_hash=profile.profile_hash,
        node_limit=node_limit,
        finding_limit=finding_limit,
        total_node_count=profile.node_count,
        root_count=profile.root_count,
        max_depth=profile.max_depth,
        included_node_count=included_node_count,
        omitted_node_count=omitted_node_count,
        total_finding_count=len(profile.findings),
        included_finding_count=included_finding_count,
        omitted_finding_count=omitted_finding_count,
        coverage_complete=coverage_complete,
        nodes=node_views,
        findings=finding_views,
        reference_to_node_id={
            ref: node_id for node_id, ref in ref_by_node_id.items()
        },
        projection_hash=canonical_digest(model_payload),
    )


def verify_tree_understanding_projection_against_sources(
    projection: TreeUnderstandingProjection,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    """Reject a self-consistent projection that differs from trusted sources."""

    if not isinstance(projection, TreeUnderstandingProjection):
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_PROJECTION_SOURCE_MISMATCH",
            "tree understanding projection is not a trusted typed artifact",
        )
    expected = build_tree_understanding_projection(
        tree,
        profile,
        node_limit=projection.node_limit,
        finding_limit=projection.finding_limit,
    )
    if projection != expected:
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_PROJECTION_SOURCE_MISMATCH",
            "tree understanding projection does not match trusted sources",
        )


def _validate_and_index_tree(
    tree: CanonicalTree,
) -> tuple[dict[str, CanonicalNode], dict[str, int]]:
    if (
        not isinstance(tree, CanonicalTree)
        or tree.schema_version != SUPPORTED_TREE_SCHEMA_VERSION
    ):
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_TREE_SCHEMA_UNSUPPORTED",
            "tree diagnostic input must use the supported canonical schema",
        )
    nodes_by_id = {node.node_id: node for node in tree.nodes}
    root_ids = tuple(sorted(tree.root_node_ids))
    if (
        not nodes_by_id
        or not root_ids
        or len(nodes_by_id) != len(tree.nodes)
        or len(root_ids) != len(set(root_ids))
        or any(root_id not in nodes_by_id for root_id in root_ids)
    ):
        raise _relation_error()
    root_id_set = set(root_ids)
    for node_id, node in nodes_by_id.items():
        if (
            not node_id
            or len(node.child_node_ids) != len(set(node.child_node_ids))
            or any(child_id not in nodes_by_id for child_id in node.child_node_ids)
        ):
            raise _relation_error()
        if node_id in root_id_set:
            if node.parent_node_id is not None:
                raise _relation_error()
        elif (
            node.parent_node_id not in nodes_by_id
            or node_id
            not in nodes_by_id[node.parent_node_id].child_node_ids
        ):
            raise _relation_error()
        for child_id in node.child_node_ids:
            if nodes_by_id[child_id].parent_node_id != node_id:
                raise _relation_error()

    depth_by_id: dict[str, int] = {}
    pending = [(root_id, 0) for root_id in reversed(root_ids)]
    while pending:
        node_id, depth = pending.pop()
        if node_id in depth_by_id:
            raise _relation_error()
        depth_by_id[node_id] = depth
        pending.extend(
            (child_id, depth + 1)
            for child_id in reversed(
                tuple(sorted(nodes_by_id[node_id].child_node_ids))
            )
        )
    if len(depth_by_id) != len(nodes_by_id):
        raise _relation_error()
    return nodes_by_id, depth_by_id


def _build_branch_profiles(
    tree: CanonicalTree,
    nodes_by_id: Mapping[str, CanonicalNode],
    depth_by_id: Mapping[str, int],
) -> tuple[TopLevelBranchProfile, ...]:
    profiles: list[TopLevelBranchProfile] = []
    for root_id in sorted(tree.root_node_ids):
        root = nodes_by_id[root_id]
        branch_ids = tuple(sorted(root.child_node_ids)) or (root_id,)
        for branch_id in branch_ids:
            branch_depth = depth_by_id[branch_id]
            subtree_ids: list[str] = []
            pending = [branch_id]
            while pending:
                node_id = pending.pop()
                subtree_ids.append(node_id)
                pending.extend(
                    reversed(tuple(sorted(nodes_by_id[node_id].child_node_ids)))
                )
            profiles.append(
                TopLevelBranchProfile(
                    root_node_id=root_id,
                    branch_node_id=branch_id,
                    node_count=len(subtree_ids),
                    max_relative_depth=max(
                        depth_by_id[node_id] - branch_depth
                        for node_id in subtree_ids
                    ),
                    max_direct_child_count=max(
                        len(nodes_by_id[node_id].child_node_ids)
                        for node_id in subtree_ids
                    ),
                )
            )
    return tuple(
        sorted(
            profiles,
            key=lambda item: (item.root_node_id, item.branch_node_id),
        )
    )


def _build_findings(
    nodes_by_id: Mapping[str, CanonicalNode],
) -> tuple[TreeDiagnosticFinding, ...]:
    findings: list[TreeDiagnosticFinding] = []
    nodes_by_name: dict[str, list[CanonicalNode]] = defaultdict(list)
    for node in nodes_by_id.values():
        nodes_by_name[_normalize_name(node.name)].append(node)

    for normalized_name in sorted(nodes_by_name):
        nodes = tuple(
            sorted(nodes_by_name[normalized_name], key=lambda item: item.node_id)
        )
        node_ids = tuple(node.node_id for node in nodes)
        if (
            len(nodes) >= 2
            and len({node.parent_node_id for node in nodes}) >= 2
        ):
            findings.append(
                TreeDiagnosticFinding(
                    code="NAME_REUSED_ACROSS_PATHS",
                    node_ids=node_ids,
                    occurrence_count=len(node_ids),
                )
            )
        if len({_node_contract(node) for node in nodes}) >= 2:
            findings.append(
                TreeDiagnosticFinding(
                    code="NAME_CONTRACT_CONFLICT",
                    node_ids=node_ids,
                    occurrence_count=len(node_ids),
                )
            )

    parents_by_child_vector: dict[
        tuple[tuple[str, str, str, str], ...],
        list[str],
    ] = defaultdict(list)
    for node in nodes_by_id.values():
        if not node.child_node_ids:
            continue
        vector = tuple(
            sorted(
                (
                    _normalize_name(child.name),
                    child.kind,
                    (
                        child.value_contract.value_type
                        if child.value_contract is not None
                        else _NONE
                    ),
                    (
                        child.value_contract.cardinality
                        if child.value_contract is not None
                        else _NONE
                    ),
                )
                for child_id in node.child_node_ids
                for child in (nodes_by_id[child_id],)
            )
        )
        parents_by_child_vector[vector].append(node.node_id)
    for vector in sorted(parents_by_child_vector):
        parent_ids = tuple(sorted(parents_by_child_vector[vector]))
        if len(parent_ids) >= 2:
            findings.append(
                TreeDiagnosticFinding(
                    code="CHILD_CONTRACT_VECTOR_REUSED",
                    node_ids=parent_ids,
                    occurrence_count=len(parent_ids),
                )
            )
    return tuple(sorted(findings, key=_finding_sort_key))


def _profile_payload(
    *,
    schema_version: str,
    algorithm_version: str,
    source_snapshot_hash: str,
    source_tree_id: str,
    source_tree_version: str,
    node_count: int,
    root_count: int,
    max_depth: int,
    kind_counts: Mapping[str, int],
    value_type_counts: Mapping[str, int],
    cardinality_counts: Mapping[str, int],
    depth_counts: Mapping[str, int],
    top_level_branches: tuple[TopLevelBranchProfile, ...],
    findings: tuple[TreeDiagnosticFinding, ...],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "algorithm_version": algorithm_version,
        "source_snapshot_hash": source_snapshot_hash,
        "source_tree_id": source_tree_id,
        "source_tree_version": source_tree_version,
        "node_count": node_count,
        "root_count": root_count,
        "max_depth": max_depth,
        "kind_counts": dict(sorted(thaw_json(kind_counts).items())),
        "value_type_counts": dict(
            sorted(thaw_json(value_type_counts).items())
        ),
        "cardinality_counts": dict(
            sorted(thaw_json(cardinality_counts).items())
        ),
        "depth_counts": dict(
            sorted(
                thaw_json(depth_counts).items(),
                key=lambda item: int(item[0]),
            )
        ),
        "top_level_branches": [
            branch.to_dict() for branch in top_level_branches
        ],
        "findings": [finding.to_dict() for finding in findings],
    }


def _counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _validate_count_map(counts: Mapping[str, int], name: str) -> None:
    if (
        not isinstance(counts, Mapping)
        or not counts
        or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            for key, value in counts.items()
        )
    ):
        raise ValueError(f"tree diagnostic {name} is invalid")


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _node_contract(node: CanonicalNode) -> tuple[str, str, str]:
    return (
        node.kind,
        node.value_contract.value_type if node.value_contract is not None else _NONE,
        (
            node.value_contract.cardinality
            if node.value_contract is not None
            else _NONE
        ),
    )


def _finding_sort_key(
    finding: TreeDiagnosticFinding,
) -> tuple[int, tuple[str, ...]]:
    return (_FINDING_CODE_RANK[finding.code], finding.node_ids)


def _validate_internal_id_tuple(
    value: Any,
    field_name: str,
    *,
    require_non_empty: bool = True,
) -> None:
    if (
        not isinstance(value, tuple)
        or (require_non_empty and not value)
        or value != tuple(sorted(value))
        or len(value) != len(set(value))
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError(f"{field_name} must be sorted unique internal refs")


def _validate_enum_tuple(
    value: Any,
    field_name: str,
    allowed: set[str],
) -> None:
    if (
        not isinstance(value, tuple)
        or value != tuple(
            item for item in SCENARIO_FAMILY_ORDER if item in set(value)
        )
        or len(value) != len(set(value))
        or any(item not in allowed for item in value)
    ):
        raise ValueError(f"{field_name} must be ordered unique enum values")


def _validate_planned_hint(
    policy: str,
    value: str | None,
    field_name: str,
    allowed_values: set[str] | None,
) -> None:
    if policy not in REQUEST_HINT_POLICIES:
        raise ValueError(f"{field_name} policy is unsupported")
    if policy == "ABSENT":
        if value is not None:
            raise ValueError(f"{field_name} must be absent under ABSENT policy")
        return
    _required_text(value, field_name)
    if allowed_values is not None and value not in allowed_values:
        raise ValueError(f"{field_name} value is unsupported")


def _scenario_unit_spec(
    *,
    unit_role: str,
    planning_mode: str,
    scenario_family: str,
    target_stage: str,
    primary_anchor_node_id: str,
    anchor_node_ids: Iterable[str],
    allowed_branch_node_ids: Iterable[str],
    node_limit: int,
    finding_code: str | None = None,
    parent_hint_policy: str = "ABSENT",
    proposed_parent_node_id: str | None = None,
    node_kind_hint_policy: str = "ABSENT",
    node_kind_hint: str | None = None,
    value_type_hint_policy: str = "ABSENT",
    value_type_hint: str | None = None,
    cardinality_hint_policy: str = "ABSENT",
    cardinality_hint: str | None = None,
) -> dict[str, Any]:
    return {
        "unit_role": unit_role,
        "planning_mode": planning_mode,
        "scenario_family": scenario_family,
        "target_stage": target_stage,
        "primary_anchor_node_id": primary_anchor_node_id,
        "anchor_node_ids": tuple(sorted(set(anchor_node_ids))),
        "allowed_branch_node_ids": tuple(
            sorted(set(allowed_branch_node_ids))
        ),
        "finding_code": finding_code,
        "parent_hint_policy": parent_hint_policy,
        "proposed_parent_node_id": proposed_parent_node_id,
        "node_kind_hint_policy": node_kind_hint_policy,
        "node_kind_hint": node_kind_hint,
        "value_type_hint_policy": value_type_hint_policy,
        "value_type_hint": value_type_hint,
        "cardinality_hint_policy": cardinality_hint_policy,
        "cardinality_hint": cardinality_hint,
        "node_limit": node_limit,
    }


def _scenario_plan_payload(
    *,
    source_snapshot_hash: str,
    source_profile_hash: str,
    max_plan_units: int,
    node_limit: int,
    new_node_placement_seed: NewNodePlacementSeed | None,
    family_statuses: Mapping[str, str],
    units: tuple[ScenarioPlanUnit, ...],
    covered_branch_node_ids: tuple[str, ...],
    omitted_branch_node_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SCENARIO_PLAN_SCHEMA_VERSION,
        "algorithm_version": SCENARIO_PLAN_ALGORITHM_VERSION,
        "source_snapshot_hash": source_snapshot_hash,
        "source_profile_hash": source_profile_hash,
        "max_plan_units": max_plan_units,
        "node_limit": node_limit,
        "new_node_placement_seed": (
            new_node_placement_seed.to_dict()
            if new_node_placement_seed is not None
            else None
        ),
        "family_statuses": {
            family: family_statuses[family]
            for family in SCENARIO_FAMILY_ORDER
        },
        "units": [unit.to_dict() for unit in units],
        "covered_branch_node_ids": list(covered_branch_node_ids),
        "omitted_branch_node_ids": list(omitted_branch_node_ids),
    }


def _build_top_branch_map(
    profile: TreeDiagnosticProfile,
    nodes_by_id: Mapping[str, CanonicalNode],
) -> dict[str, str | None]:
    result: dict[str, str | None] = {node_id: None for node_id in nodes_by_id}
    for branch in profile.top_level_branches:
        pending = [branch.branch_node_id]
        while pending:
            node_id = pending.pop()
            previous = result[node_id]
            if previous is not None and previous != branch.branch_node_id:
                raise _relation_error()
            result[node_id] = branch.branch_node_id
            pending.extend(nodes_by_id[node_id].child_node_ids)
    return result


def _select_branch_anchor(
    branch_node_id: str,
    nodes_by_id: Mapping[str, CanonicalNode],
    depth_by_id: Mapping[str, int],
    branch_by_node_id: Mapping[str, str | None],
) -> str:
    candidates = tuple(
        node_id
        for node_id, assigned_branch_id in branch_by_node_id.items()
        if assigned_branch_id == branch_node_id
    )
    if not candidates:
        raise _relation_error()
    return min(
        candidates,
        key=lambda node_id: (
            0 if nodes_by_id[node_id].kind == "PROPERTY" else 1,
            -depth_by_id[node_id],
            -len(nodes_by_id[node_id].child_node_ids),
            node_id,
        ),
    )


def _select_cardinality_anchor(
    representative_branches: tuple[TopLevelBranchProfile, ...],
    nodes_by_id: Mapping[str, CanonicalNode],
    depth_by_id: Mapping[str, int],
    branch_by_node_id: Mapping[str, str | None],
) -> str | None:
    branch_rank = {
        branch.branch_node_id: index
        for index, branch in enumerate(representative_branches)
    }
    candidates = tuple(
        node_id
        for node_id, node in nodes_by_id.items()
        if node.value_contract is not None
        and node.value_contract.cardinality in {"SINGLE", "MULTIPLE"}
        and branch_by_node_id[node_id] is not None
    )
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda node_id: (
            branch_rank[branch_by_node_id[node_id]],  # type: ignore[index]
            -depth_by_id[node_id],
            node_id,
        ),
    )


def _select_representative_branches(
    branches: tuple[TopLevelBranchProfile, ...],
    limit: int,
) -> tuple[TopLevelBranchProfile, ...]:
    if limit <= 0 or not branches:
        return ()
    limit = min(limit, len(branches))
    by_id = {branch.branch_node_id: branch for branch in branches}
    selected_ids: list[str] = []

    for metric in (
        "node_count",
        "max_relative_depth",
        "max_direct_child_count",
    ):
        candidate = min(
            branches,
            key=lambda branch: (
                -getattr(branch, metric),
                branch.root_node_id,
                branch.branch_node_id,
            ),
        )
        if candidate.branch_node_id not in selected_ids:
            selected_ids.append(candidate.branch_node_id)
        if len(selected_ids) == limit:
            return tuple(by_id[item] for item in selected_ids)

    dimensions = (
        "node_count",
        "max_relative_depth",
        "max_direct_child_count",
    )
    minima = {
        dimension: min(getattr(branch, dimension) for branch in branches)
        for dimension in dimensions
    }
    maxima = {
        dimension: max(getattr(branch, dimension) for branch in branches)
        for dimension in dimensions
    }

    def vector(
        branch: TopLevelBranchProfile,
    ) -> tuple[Fraction, Fraction, Fraction]:
        values: list[Fraction] = []
        for dimension in dimensions:
            low = minima[dimension]
            high = maxima[dimension]
            values.append(
                Fraction(0, 1)
                if high == low
                else Fraction(
                    getattr(branch, dimension) - low,
                    high - low,
                )
            )
        return (values[0], values[1], values[2])

    vectors = {branch.branch_node_id: vector(branch) for branch in branches}
    while len(selected_ids) < limit:
        remaining = tuple(
            branch
            for branch in branches
            if branch.branch_node_id not in selected_ids
        )

        def diversity(branch: TopLevelBranchProfile) -> Fraction:
            current = vectors[branch.branch_node_id]
            return min(
                sum((left - right) ** 2 for left, right in zip(current, vectors[item]))
                for item in selected_ids
            )

        candidate = min(
            remaining,
            key=lambda branch: (
                -diversity(branch),
                branch.root_node_id,
                branch.branch_node_id,
            ),
        )
        selected_ids.append(candidate.branch_node_id)
    return tuple(by_id[item] for item in selected_ids)


def _select_name_reuse_pair(
    profile: TreeDiagnosticProfile,
    nodes_by_id: Mapping[str, CanonicalNode],
    branch_by_node_id: Mapping[str, str | None],
) -> tuple[TreeDiagnosticFinding, tuple[str, str]] | None:
    for finding in profile.findings:
        if finding.code != "NAME_REUSED_ACROSS_PATHS":
            continue
        for index, left_id in enumerate(finding.node_ids):
            for right_id in finding.node_ids[index + 1 :]:
                if (
                    nodes_by_id[left_id].parent_node_id
                    != nodes_by_id[right_id].parent_node_id
                    and branch_by_node_id[left_id] is not None
                    and branch_by_node_id[right_id] is not None
                ):
                    return finding, (left_id, right_id)
    return None


def _branches_for_anchors(
    anchor_node_ids: Iterable[str],
    branch_by_node_id: Mapping[str, str | None],
) -> tuple[str, ...]:
    branches = {
        branch_by_node_id[node_id]
        for node_id in anchor_node_ids
        if branch_by_node_id[node_id] is not None
    }
    if not branches or len(branches) > 3:
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_PLAN_SCOPE_INVALID",
            "scenario anchors do not form a bounded branch scope",
        )
    return tuple(sorted(branches))  # type: ignore[arg-type]


def _scenario_model_input_payload(
    *,
    plan_unit_ref: str,
    unit_role: str,
    planning_mode: str,
    scenario_family: str,
    target_stage: str,
    parent_hint_policy: str,
    node_kind_hint_policy: str,
    value_type_hint_policy: str,
    cardinality_hint_policy: str,
    proposed_new_node_name: str | None,
    node_kind_hint: str | None,
    value_type_hint: str | None,
    cardinality_hint: str | None,
    total_node_count: int,
    root_count: int,
    top_level_branch_count: int,
    included_node_count: int,
    omitted_node_count: int,
    allowed_branch_count: int,
    nodes: tuple[TreeUnderstandingNodeView, ...],
    signal: ScenarioPreparationSignalView | None,
    primary_anchor_ref: str,
    anchor_refs: tuple[str, ...],
    evidence_node_refs: tuple[str, ...],
    proposed_parent_ref: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCENARIO_MODEL_INPUT_SCHEMA_VERSION,
        "projection_version": SCENARIO_PROJECTION_VERSION,
        "task_type": SCENARIO_TASK_TYPE,
        "assignment": {
            "plan_unit_ref": plan_unit_ref,
            "unit_role": unit_role,
            "planning_mode": planning_mode,
            "scenario_family": scenario_family,
            "target_stage": target_stage,
            "primary_anchor_ref": primary_anchor_ref,
            "anchor_refs": list(anchor_refs),
            "evidence_node_refs": list(evidence_node_refs),
            "proposed_new_node_name": proposed_new_node_name,
            "parent_hint_policy": parent_hint_policy,
            "proposed_parent_ref": proposed_parent_ref,
            "node_kind_hint_policy": node_kind_hint_policy,
            "node_kind_hint": node_kind_hint,
            "value_type_hint_policy": value_type_hint_policy,
            "value_type_hint": value_type_hint,
            "cardinality_hint_policy": cardinality_hint_policy,
            "cardinality_hint": cardinality_hint,
        },
        "tree_shape": {
            "node_count": total_node_count,
            "root_count": root_count,
            "top_level_branch_count": top_level_branch_count,
        },
        "coverage": {
            "total_node_count": total_node_count,
            "included_node_count": included_node_count,
            "omitted_node_count": omitted_node_count,
            "allowed_branch_count": allowed_branch_count,
            "coverage_complete": omitted_node_count == 0,
        },
        "nodes": [node.to_dict() for node in nodes],
        "signals": [signal.to_dict()] if signal is not None else [],
    }


def _verify_scenario_model_echo(
    payload: Mapping[str, Any],
    projection: ScenarioPreparationProjection,
) -> None:
    expected = {
        "plan_unit_ref": projection.plan_unit_ref,
        "scenario_ref": "S001",
        "planning_mode": projection.planning_mode,
        "scenario_family": projection.scenario_family,
        "target_stage": projection.target_stage,
    }
    if any(payload[field] != value for field, value in expected.items()):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_MODEL_PLAN_ECHO_INVALID",
            "scenario model output changed a deterministic plan field",
        )


def _parse_optional_projection_ref(
    value: Any,
    projection: ScenarioPreparationProjection,
    code: str,
) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or _NODE_REFERENCE.fullmatch(value) is None
        or value not in projection.evidence_node_refs
    ):
        raise TreeUnderstandingError(code, "projection ref is not allowlisted")
    return value


def _parse_optional_enum(
    value: Any,
    allowed: set[str],
    code: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in allowed:
        raise TreeUnderstandingError(code, "optional enum is not allowlisted")
    return value


def _parse_optional_text(
    value: Any,
    field_name: str,
    *,
    code: str = "TREE_UNDERSTANDING_MODEL_TEXT_INVALID",
) -> str | None:
    if value is None:
        return None
    return _parse_required_text(value, field_name, code=code)


def _parse_requested_aspects(
    value: Any,
    *,
    allowed_refs: set[str],
    planning_mode: str,
) -> tuple[ScenarioRequestedAspect, ...]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 3
        or (planning_mode == "BRANCH_LOCAL" and len(value) != 1)
    ):
        raise TreeUnderstandingError(
            "SCENARIO_PREPARATION_MODEL_ASPECTS_INVALID",
            "requested_aspects violates the bounded primary-request policy",
        )
    aspects: list[ScenarioRequestedAspect] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != _SCENARIO_REQUESTED_ASPECT_KEYS:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_ASPECTS_INVALID",
                "requested aspect must use exact fields",
            )
        aspect = _parse_required_text(
            item["aspect"],
            "aspect",
            code="SCENARIO_PREPARATION_MODEL_TEXT_INVALID",
        )
        if aspect in seen:
            raise TreeUnderstandingError(
                "SCENARIO_PREPARATION_MODEL_ASPECTS_INVALID",
                "requested aspects must be unique",
            )
        seen.add(aspect)
        refs = _parse_projection_refs(
            item["supporting_node_refs"],
            allowed_refs=allowed_refs,
            pattern=_NODE_REFERENCE,
            code="SCENARIO_PREPARATION_MODEL_ASPECT_EVIDENCE_INVALID",
            field_name="supporting_node_refs",
            require_non_empty=True,
        )
        aspects.append(
            ScenarioRequestedAspect(
                aspect=aspect,
                supporting_node_refs=refs,
            )
        )
    return tuple(aspects)


def _scenario_candidate_text_policy_invalid(
    requirement_text: str,
    requested_aspects: tuple[ScenarioRequestedAspect, ...],
    rationale: str,
    uncertainties: tuple[str, ...],
    evidence_gaps: tuple[str, ...],
) -> bool:
    natural_texts = (
        requirement_text,
        *(item.aspect for item in requested_aspects),
        rationale,
        *uncertainties,
        *evidence_gaps,
    )
    return any(
        sentinel in text
        for sentinel in SCENARIO_MODEL_TEXT_SENTINELS
        for text in natural_texts
    ) or any(
        _TEMPORARY_PROJECTION_REFERENCE_IN_TEXT.search(text) is not None
        for text in natural_texts
    )


def _scenario_candidate_family_policy_invalid(
    scenario_family: str,
    uncertainties: tuple[str, ...],
    evidence_gaps: tuple[str, ...],
) -> bool:
    if scenario_family in {
        "HOMONYM_CLARIFICATION",
        "UNBOUNDED_COMBINATION",
    }:
        return not uncertainties
    if scenario_family == "INSUFFICIENT_EVIDENCE":
        return not evidence_gaps
    return False


def _scenario_candidate_payload(
    *,
    model_provider: str,
    model_capability: str,
    model_name: str,
    prompt_version: str,
    source_snapshot_hash: str,
    source_profile_hash: str,
    source_plan_hash: str,
    source_projection_hash: str,
    plan_unit_ref: str,
    planning_mode: str,
    scenario_family: str,
    target_stage: str,
    requirement_text: str,
    proposed_parent_ref: str | None,
    node_kind_hint: str | None,
    value_type_hint: str | None,
    cardinality_hint: str | None,
    supporting_node_refs: tuple[str, ...],
    source_signal_refs: tuple[str, ...],
    requested_aspects: tuple[ScenarioRequestedAspect, ...],
    rationale: str,
    uncertainties: tuple[str, ...],
    evidence_gaps: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SCENARIO_CANDIDATE_SCHEMA_VERSION,
        "model_provider": model_provider,
        "model_capability": model_capability,
        "model_name": model_name,
        "prompt_version": prompt_version,
        "model_provenance_status": MODEL_PROVENANCE_STATUS,
        "review_status": REVIEW_STATUS,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "source_snapshot_hash": source_snapshot_hash,
        "source_profile_hash": source_profile_hash,
        "source_plan_hash": source_plan_hash,
        "source_projection_hash": source_projection_hash,
        "plan_unit_ref": plan_unit_ref,
        "scenario_ref": "S001",
        "planning_mode": planning_mode,
        "scenario_family": scenario_family,
        "target_stage": target_stage,
        "requirement_text": requirement_text,
        "proposed_parent_ref": proposed_parent_ref,
        "node_kind_hint": node_kind_hint,
        "value_type_hint": value_type_hint,
        "cardinality_hint": cardinality_hint,
        "supporting_node_refs": list(supporting_node_refs),
        "source_signal_refs": list(source_signal_refs),
        "requested_aspects": [item.to_dict() for item in requested_aspects],
        "rationale": rationale,
        "uncertainties": list(uncertainties),
        "evidence_gaps": list(evidence_gaps),
    }


def _scenario_batch_payload(
    *,
    preparation_source_status: str,
    source_snapshot_hash: str,
    source_profile_hash: str,
    source_plan_hash: str,
    status: str,
    planned_unit_count: int,
    attempted_unit_count: int,
    completed_unit_count: int,
    failed_unit_count: int,
    not_executed_unit_count: int,
    omitted_target_count: int,
    candidates: tuple[ScenarioPreparationBatchCandidate, ...],
    failures: tuple[ScenarioPreparationFailure, ...],
    not_executed: tuple[ScenarioPreparationNotExecuted, ...],
    omitted_family_refs: tuple[str, ...],
    omitted_branch_node_ids: tuple[str, ...],
    family_outcomes: Mapping[str, str],
    branch_coverage: ScenarioPreparationBranchCoverage,
    target_stage_coverage: Mapping[str, ScenarioPreparationStageCoverage],
    projected_node_coverage: ScenarioProjectedNodeCoverage,
) -> dict[str, Any]:
    return {
        "schema_version": SCENARIO_BATCH_SCHEMA_VERSION,
        "preparation_source_status": preparation_source_status,
        "review_status": REVIEW_STATUS,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "source_snapshot_hash": source_snapshot_hash,
        "source_profile_hash": source_profile_hash,
        "source_plan_hash": source_plan_hash,
        "status": status,
        "planned_unit_count": planned_unit_count,
        "attempted_unit_count": attempted_unit_count,
        "completed_unit_count": completed_unit_count,
        "failed_unit_count": failed_unit_count,
        "not_executed_unit_count": not_executed_unit_count,
        "omitted_target_count": omitted_target_count,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "failures": [failure.to_dict() for failure in failures],
        "not_executed": [item.to_dict() for item in not_executed],
        "omitted_family_refs": list(omitted_family_refs),
        "omitted_branch_node_ids": list(omitted_branch_node_ids),
        "family_outcomes": {
            family: family_outcomes[family]
            for family in SCENARIO_FAMILY_ORDER
        },
        "branch_coverage": branch_coverage.to_dict(),
        "target_stage_coverage": {
            stage: target_stage_coverage[stage].to_dict()
            for stage in TARGET_STAGE_ORDER
        },
        "projected_node_coverage": projected_node_coverage.to_dict(),
    }


def _tree_understanding_model_payload(
    *,
    total_node_count: int,
    root_count: int,
    max_depth: int,
    included_node_count: int,
    omitted_node_count: int,
    total_finding_count: int,
    included_finding_count: int,
    omitted_finding_count: int,
    coverage_complete: bool,
    nodes: tuple[TreeUnderstandingNodeView, ...],
    findings: tuple[TreeUnderstandingFindingView, ...],
) -> dict[str, Any]:
    return {
        "schema_version": MODEL_INPUT_SCHEMA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "task_type": TASK_TYPE,
        "tree_shape": {
            "node_count": total_node_count,
            "root_count": root_count,
            "max_depth": max_depth,
        },
        "coverage": {
            "total_node_count": total_node_count,
            "included_node_count": included_node_count,
            "omitted_node_count": omitted_node_count,
            "total_finding_count": total_finding_count,
            "included_finding_count": included_finding_count,
            "omitted_finding_count": omitted_finding_count,
            "coverage_complete": coverage_complete,
        },
        "nodes": [item.to_dict() for item in nodes],
        "findings": [item.to_dict() for item in findings],
    }


def _parse_finding_assessments(
    value: Any,
    projection: TreeUnderstandingProjection,
) -> tuple[TreeUnderstandingFindingAssessment, ...]:
    if not isinstance(value, list) or len(value) > MAX_MODEL_FINDINGS:
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_MODEL_FINDING_ASSESSMENTS_INVALID",
            "finding assessments must be a bounded array",
        )
    assessments: list[TreeUnderstandingFindingAssessment] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _FINDING_ASSESSMENT_KEYS:
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_FINDING_ASSESSMENTS_INVALID",
                "finding assessments must use exact fields",
            )
        finding_ref = item["finding_ref"]
        if (
            not isinstance(finding_ref, str)
            or finding_ref not in projection.finding_refs
        ):
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_FINDING_REF_INVALID",
                "finding assessment reference is not in the projection",
            )
        assessments.append(
            TreeUnderstandingFindingAssessment(
                finding_ref=finding_ref,
                disposition=_parse_enum(
                    item["disposition"],
                    FINDING_DISPOSITIONS,
                    "TREE_UNDERSTANDING_MODEL_FINDING_DISPOSITION_INVALID",
                ),
                reason=_parse_required_text(item["reason"], "reason"),
            )
        )
    if tuple(item.finding_ref for item in assessments) != projection.finding_refs:
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_MODEL_FINDING_COVERAGE_INVALID",
            "finding assessments must cover projection findings in order",
        )
    return tuple(assessments)


def _parse_virtual_scenarios(
    value: Any,
    projection: TreeUnderstandingProjection,
) -> tuple[VirtualValidationScenario, ...]:
    if not isinstance(value, list) or len(value) > MAX_VIRTUAL_SCENARIOS:
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_MODEL_SCENARIOS_INVALID",
            "virtual scenarios must be a bounded array",
        )
    scenarios: list[VirtualValidationScenario] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _SCENARIO_KEYS:
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_SCENARIOS_INVALID",
                "virtual scenarios must use exact fields",
            )
        scenario_ref = item["scenario_ref"]
        if (
            not isinstance(scenario_ref, str)
            or _SCENARIO_REFERENCE.fullmatch(scenario_ref) is None
        ):
            raise TreeUnderstandingError(
                "TREE_UNDERSTANDING_MODEL_SCENARIO_REF_INVALID",
                "virtual scenario reference is invalid",
            )
        supporting_node_refs = _parse_projection_refs(
            item["supporting_node_refs"],
            allowed_refs=set(projection.node_refs),
            pattern=_NODE_REFERENCE,
            code="TREE_UNDERSTANDING_MODEL_NODE_REF_INVALID",
            field_name="supporting_node_refs",
            require_non_empty=True,
        )
        source_finding_refs = _parse_projection_refs(
            item["source_finding_refs"],
            allowed_refs=set(projection.finding_refs),
            pattern=_FINDING_REFERENCE,
            code="TREE_UNDERSTANDING_MODEL_FINDING_REF_INVALID",
            field_name="source_finding_refs",
            require_non_empty=False,
        )
        scenarios.append(
            VirtualValidationScenario(
                scenario_ref=scenario_ref,
                title=_parse_required_text(item["title"], "title"),
                natural_language_request=_parse_required_text(
                    item["natural_language_request"],
                    "natural_language_request",
                ),
                validation_goal=_parse_enum(
                    item["validation_goal"],
                    VALIDATION_GOALS,
                    "TREE_UNDERSTANDING_MODEL_VALIDATION_GOAL_INVALID",
                ),
                supporting_node_refs=supporting_node_refs,
                source_finding_refs=source_finding_refs,
                rationale=_parse_required_text(
                    item["rationale"],
                    "rationale",
                ),
            )
        )
    expected_refs = tuple(
        f"S{index:03d}" for index in range(1, len(scenarios) + 1)
    )
    if tuple(item.scenario_ref for item in scenarios) != expected_refs:
        raise TreeUnderstandingError(
            "TREE_UNDERSTANDING_MODEL_SCENARIO_ORDER_INVALID",
            "virtual scenario refs must be contiguous and ordered",
        )
    return tuple(scenarios)


def _parse_projection_refs(
    value: Any,
    *,
    allowed_refs: set[str],
    pattern: re.Pattern[str],
    code: str,
    field_name: str,
    require_non_empty: bool,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > MAX_MODEL_NODES
        or (require_non_empty and not value)
        or any(
            not isinstance(item, str)
            or pattern.fullmatch(item) is None
            or item not in allowed_refs
            for item in value
        )
        or len(value) != len(set(value))
    ):
        raise TreeUnderstandingError(
            code,
            f"{field_name} must use unique allowlisted projection refs",
        )
    return tuple(sorted(value))


def _parse_enum(value: Any, allowed: set[str], code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise TreeUnderstandingError(code, "value is not allowlisted")
    return value


def _parse_required_text(
    value: Any,
    field_name: str,
    *,
    code: str = "TREE_UNDERSTANDING_MODEL_TEXT_INVALID",
) -> str:
    try:
        return _required_text(value, field_name).strip()
    except ValueError:
        raise TreeUnderstandingError(
            code,
            f"{field_name} must be bounded printable text",
        ) from None


def _parse_text_tuple(
    value: Any,
    field_name: str,
    *,
    code: str = "TREE_UNDERSTANDING_MODEL_TEXT_LIST_INVALID",
    item_code: str = "TREE_UNDERSTANDING_MODEL_TEXT_INVALID",
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > _MAX_LIST_ITEMS:
        raise TreeUnderstandingError(
            code,
            f"{field_name} must be a bounded unique text array",
        )
    parsed: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _parse_required_text(item, field_name, code=item_code)
        if text in seen:
            raise TreeUnderstandingError(
                code,
                f"{field_name} must be a bounded unique text array",
            )
        seen.add(text)
        parsed.append(text)
    return tuple(parsed)


def _required_text(
    value: Any,
    field_name: str,
    *,
    max_chars: int = _MAX_TEXT_CHARS,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > max_chars
        or _CONTROL_CHARACTER.search(value) is not None
        or _SURROGATE_CHARACTER.search(value) is not None
    ):
        raise ValueError(f"{field_name} must be bounded printable text")
    return value


def _validate_text_tuple(value: Any, field_name: str) -> None:
    if not isinstance(value, tuple) or len(value) > _MAX_LIST_ITEMS:
        raise ValueError(f"{field_name} must be an immutable unique tuple")
    seen: set[str] = set()
    for item in value:
        _required_text(item, field_name)
        if item in seen:
            raise ValueError(f"{field_name} must be an immutable unique tuple")
        seen.add(item)


def _validate_ref_tuple(
    value: Any,
    pattern: re.Pattern[str],
    field_name: str,
    *,
    require_non_empty: bool,
) -> None:
    if (
        not isinstance(value, tuple)
        or (require_non_empty and not value)
        or value != tuple(sorted(value))
        or len(value) != len(set(value))
        or any(
            not isinstance(item, str) or pattern.fullmatch(item) is None
            for item in value
        )
    ):
        raise ValueError(f"{field_name} must be sorted unique refs")


def _validate_generation_policy(
    generation_status: str,
    scenarios: tuple[VirtualValidationScenario, ...],
    uncertainties: tuple[str, ...],
    evidence_gaps: tuple[str, ...],
) -> None:
    if generation_status == "SCENARIOS_PROPOSED":
        if not scenarios:
            raise ValueError("proposed generation requires scenarios")
        return
    if scenarios:
        raise ValueError("non-proposed generation cannot contain scenarios")
    if generation_status == "NEED_EVIDENCE" and not evidence_gaps:
        raise ValueError("evidence status requires evidence gaps")
    if generation_status == "ABSTAIN" and not (
        uncertainties or evidence_gaps
    ):
        raise ValueError("abstain requires an uncertainty or evidence gap")


def _serialized_char_count(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _relation_error() -> TreeUnderstandingError:
    return TreeUnderstandingError(
        "TREE_UNDERSTANDING_TREE_RELATION_INVALID",
        "canonical tree relations are incomplete or inconsistent",
    )


__all__ = [
    "AGGREGATE_REPORT_VERSION",
    "ALGORITHM_VERSION",
    "BATCH_STATUSES",
    "DEFAULT_MAX_PLAN_UNITS",
    "DEFAULT_MAX_MODEL_FINDINGS",
    "DEFAULT_MAX_MODEL_NODES",
    "DEFAULT_SCENARIO_MODEL_NODES",
    "DRAFT_SCHEMA_VERSION",
    "FAMILY_PLAN_STATUSES",
    "FAMILY_PREPARATION_OUTCOMES",
    "FINDING_DISPOSITIONS",
    "FINDING_CODE_ORDER",
    "GENERATION_STATUSES",
    "MAX_PLAN_UNITS",
    "MAX_MODEL_FINDINGS",
    "MAX_MODEL_INPUT_CHARS",
    "MAX_MODEL_NODES",
    "MAX_SCENARIO_MODEL_INPUT_CHARS",
    "MAX_SCENARIO_MODEL_NODES",
    "MAX_VIRTUAL_SCENARIOS",
    "MODEL_INPUT_SCHEMA_VERSION",
    "MODEL_OUTPUT_SCHEMA_VERSION",
    "MODEL_PROVENANCE_STATUS",
    "NewNodePlacementSeed",
    "PARENT_HINT_POLICIES",
    "PLANNING_MODES",
    "PLAN_UNIT_ROLES",
    "PREPARATION_SOURCE_STATUSES",
    "PROJECTION_VERSION",
    "REVIEW_STATUS",
    "REQUEST_HINT_POLICIES",
    "SCENARIO_BATCH_SCHEMA_VERSION",
    "SCENARIO_CANDIDATE_SCHEMA_VERSION",
    "SCENARIO_EVIDENCE_GAP_TEMPLATE_SENTINEL",
    "SCENARIO_FAMILIES",
    "SCENARIO_FAMILY_ORDER",
    "SCENARIO_MODEL_INPUT_SCHEMA_VERSION",
    "SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION",
    "SCENARIO_MODEL_TEXT_SENTINELS",
    "SCENARIO_PLAN_ALGORITHM_VERSION",
    "SCENARIO_PLAN_SCHEMA_VERSION",
    "SCENARIO_PROJECTION_VERSION",
    "SCENARIO_PROJECTION_UNIT_FAILURE_CODES",
    "SCENARIO_REQUIREMENT_TEMPLATE_SENTINEL",
    "SCENARIO_ASPECT_TEMPLATE_SENTINEL",
    "SCENARIO_RATIONALE_TEMPLATE_SENTINEL",
    "SCENARIO_STAGE_NOT_RUN",
    "SCENARIO_TASK_TYPE",
    "SCHEMA_VERSION",
    "ScenarioCandidateDraft",
    "ScenarioPlanUnit",
    "ScenarioPreparationBatch",
    "ScenarioPreparationBatchCandidate",
    "ScenarioPreparationBranchCoverage",
    "ScenarioPreparationFailure",
    "ScenarioPreparationNotExecuted",
    "ScenarioPreparationPlan",
    "ScenarioPreparationProjection",
    "ScenarioPreparationSignalView",
    "ScenarioPreparationStageCoverage",
    "ScenarioProjectedNodeCoverage",
    "ScenarioRequestedAspect",
    "TASK_TYPE",
    "TARGET_STAGES",
    "TARGET_STAGE_ORDER",
    "TopLevelBranchProfile",
    "TreeDiagnosticFinding",
    "TreeDiagnosticProfile",
    "TreeUnderstandingDraft",
    "TreeUnderstandingError",
    "TreeUnderstandingFindingAssessment",
    "TreeUnderstandingFindingView",
    "TreeUnderstandingNodeView",
    "TreeUnderstandingProjection",
    "VALIDATION_GOALS",
    "VirtualValidationScenario",
    "build_scenario_preparation_batch",
    "build_scenario_preparation_plan",
    "build_scenario_preparation_projection",
    "build_tree_diagnostic_profile",
    "build_tree_understanding_projection",
    "verify_scenario_preparation_batch_against_sources",
    "verify_scenario_preparation_plan_against_sources",
    "verify_scenario_preparation_projection_against_sources",
    "verify_tree_diagnostic_profile_against_tree",
    "verify_tree_understanding_projection_against_sources",
]
