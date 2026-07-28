"""Deterministic review evidence over one ordered business-version pair."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from treeguard.diff import CHANGE_TYPE_ORDER, SnapshotRef, diff_snapshots
from treeguard.hashing import canonical_digest
from treeguard.history import (
    POLICY_VERSION,
    REASON_CODE_ORDER,
    HistorySummary,
    InformationalObservation,
    ReviewCase,
    _allowlisted_counts,
    _GATE_ORDER,
    _mine_review_artifacts,
    _observation_payload,
    _review_case_payload,
    _RISK_ORDER,
    _validate_digest,
    _validate_summary_against_run,
)
from treeguard.models import CanonicalTree


SCHEMA_VERSION = "business-version-review.v1"
ALGORITHM_VERSION = "treeguard.business-version-review.v1"
COMPARISON_SEMANTICS = "ENDPOINT_NET_CHANGE"
VERSION_ORDER_BASIS = "UNVERIFIED_EXPLICIT_SEQUENCE"


class BusinessVersionReviewError(ValueError):
    """The supplied snapshots cannot safely become a business-version review."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class VersionOrder:
    basis: str
    base_position: int
    target_position: int

    def __post_init__(self) -> None:
        positions = (self.base_position, self.target_position)
        if self.basis != VERSION_ORDER_BASIS:
            raise ValueError("unsupported business-version order basis")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in positions
        ):
            raise ValueError("business-version positions must be non-negative integers")
        if self.target_position != self.base_position + 1:
            raise ValueError("business-version positions must be adjacent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "base_position": self.base_position,
            "target_position": self.target_position,
        }


@dataclass(frozen=True, slots=True)
class BusinessVersionReviewRun:
    schema_version: str
    algorithm_version: str
    policy_version: str
    knowledge_status: str
    source_diff_hash: str
    scope: str
    base: SnapshotRef
    target: SnapshotRef
    comparison_semantics: str
    version_order: VersionOrder
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
            raise ValueError("business-version artifacts must be immutable tuples")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported BusinessVersionReview schema_version")
        if self.algorithm_version != ALGORITHM_VERSION:
            raise ValueError("unsupported BusinessVersionReview algorithm_version")
        if self.policy_version != POLICY_VERSION:
            raise ValueError("unsupported review evidence policy_version")
        if self.knowledge_status != "EVIDENCE_ONLY":
            raise ValueError("business-version review cannot claim Gold knowledge")
        _validate_digest(self.source_diff_hash, "source_diff_hash")
        if self.scope != "BUSINESS_VERSION":
            raise ValueError("business-version review scope must be BUSINESS_VERSION")
        if self.comparison_semantics != COMPARISON_SEMANTICS:
            raise ValueError("unsupported business-version comparison semantics")
        if not isinstance(self.version_order, VersionOrder):
            raise ValueError("business-version review requires VersionOrder")
        if self.reconstructs_historical_operations is not False:
            raise ValueError("business-version review cannot claim operation reconstruction")
        if (
            self.base.source_map_type != "resource"
            or self.target.source_map_type != "resource"
        ):
            raise ValueError("business-version snapshot refs must be resource")
        if self.base.tree_id != self.target.tree_id:
            raise ValueError("business-version snapshot refs must share tree identity")
        if self.base.tree_version == self.target.tree_version:
            raise ValueError("business-version snapshot refs must use different versions")
        if self.base.version_record_id == self.target.version_record_id:
            raise ValueError(
                "business-version snapshot refs must use different record identities"
            )
        if any(
            "INTERMEDIATE_REVISIONS_UNOBSERVED" in item.reason_codes
            for item in self.review_cases
        ):
            raise ValueError("save-revision gap reasons cannot enter business review")

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
            expected_id = canonical_digest(
                _review_case_payload(
                    source_diff_hash=self.source_diff_hash,
                    context_node_ids=item.context_node_ids,
                    risk_level=item.risk_level,
                    gate_status=item.gate_status,
                    reason_codes=item.reason_codes,
                    node_evidence=item.node_evidence,
                )
            )
            if item.case_id != expected_id:
                raise ValueError("review case_id does not match its source diff")
        for item in self.informational_observations:
            expected_id = canonical_digest(
                _observation_payload(
                    basis=item.basis,
                    node_ids=item.node_ids,
                    context_node_ids=item.context_node_ids,
                    change_types=item.change_types,
                    source_diff_hash=self.source_diff_hash,
                )
            )
            if item.observation_id != expected_id:
                raise ValueError("observation_id does not match its source diff")
        _validate_summary_against_run(
            self.summary,
            self.review_cases,
            self.informational_observations,
        )
        payload = self.to_dict()
        supplied_hash = payload.pop("run_hash")
        _validate_digest(supplied_hash, "run_hash")
        if supplied_hash != canonical_digest(payload):
            raise ValueError("BusinessVersionReview run_hash does not match its payload")

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
            "comparison_semantics": self.comparison_semantics,
            "version_order": self.version_order.to_dict(),
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
        return {
            "report_version": "business-version-review-aggregate.v1",
            "knowledge_status": self.knowledge_status,
            "comparison_semantics": self.comparison_semantics,
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


def mine_business_version_pair(
    before: CanonicalTree,
    after: CanonicalTree,
    *,
    base_position: int,
    target_position: int,
) -> BusinessVersionReviewRun:
    """Build review evidence from one explicitly ordered business-version pair."""

    version_order = VersionOrder(
        basis=VERSION_ORDER_BASIS,
        base_position=base_position,
        target_position=target_position,
    )
    tree_diff = diff_snapshots(before, after)
    if before.source_map_type != "resource" or after.source_map_type != "resource":
        raise BusinessVersionReviewError(
            "BUSINESS_REVIEW_SOURCE_NOT_RESOURCE",
            "business-version review accepts resource snapshots only",
        )
    if tree_diff.scope != "BUSINESS_VERSION":
        raise BusinessVersionReviewError(
            "BUSINESS_REVIEW_SCOPE_NOT_VERSION",
            "business-version review requires two different business versions",
        )
    if tree_diff.warnings:
        raise BusinessVersionReviewError(
            "BUSINESS_REVIEW_DIFF_WARNING",
            "business-version review refuses a TreeDiff containing warnings",
        )

    review_cases, informational_observations, summary = _mine_review_artifacts(
        before,
        after,
        tree_diff,
        interval_completeness="BUSINESS_VERSION_ENDPOINTS",
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
        "comparison_semantics": COMPARISON_SEMANTICS,
        "version_order": version_order.to_dict(),
        "reconstructs_historical_operations": False,
        "review_cases": [item.to_dict() for item in review_cases],
        "informational_observations": [
            item.to_dict() for item in informational_observations
        ],
        "summary": summary.to_dict(),
    }
    return BusinessVersionReviewRun(
        schema_version=SCHEMA_VERSION,
        algorithm_version=ALGORITHM_VERSION,
        policy_version=POLICY_VERSION,
        knowledge_status="EVIDENCE_ONLY",
        source_diff_hash=tree_diff.diff_hash,
        scope=tree_diff.scope,
        base=tree_diff.base,
        target=tree_diff.target,
        comparison_semantics=COMPARISON_SEMANTICS,
        version_order=version_order,
        reconstructs_historical_operations=False,
        review_cases=review_cases,
        informational_observations=informational_observations,
        summary=summary,
        run_hash=canonical_digest(payload),
    )


def verify_business_version_review_against_snapshots(
    run: BusinessVersionReviewRun,
    before: CanonicalTree,
    after: CanonicalTree,
) -> None:
    expected = mine_business_version_pair(
        before,
        after,
        base_position=run.version_order.base_position,
        target_position=run.version_order.target_position,
    )
    if run.to_dict() != expected.to_dict():
        raise BusinessVersionReviewError(
            "BUSINESS_REVIEW_SOURCE_MISMATCH",
            "business-version review does not match trusted-snapshot replay",
        )


__all__ = [
    "ALGORITHM_VERSION",
    "BusinessVersionReviewError",
    "BusinessVersionReviewRun",
    "COMPARISON_SEMANTICS",
    "SCHEMA_VERSION",
    "VERSION_ORDER_BASIS",
    "VersionOrder",
    "mine_business_version_pair",
    "verify_business_version_review_against_snapshots",
]
