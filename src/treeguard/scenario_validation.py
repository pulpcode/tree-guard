"""Explicit review gate and INTENT-only execution for scenario candidates.

This module deliberately stays outside the validation Workbench.  A generated
scenario candidate is not executable until a trusted caller freezes both the
final request and its observable oracle in a source-bound review action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentRequest,
    IntentValidationError,
    REQUEST_SCHEMA_VERSION,
    verify_intent_draft_against_sources,
)
from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree
from treeguard.tree_understanding import (
    SCENARIO_FAMILIES,
    ScenarioCandidateDraft,
    ScenarioPreparationBatch,
    ScenarioPreparationBatchCandidate,
    ScenarioPreparationPlan,
    ScenarioPreparationProjection,
    TreeDiagnosticProfile,
    TreeUnderstandingError,
    verify_scenario_preparation_projection_against_sources,
    verify_scenario_preparation_batch_against_sources,
)
from treeguard.workbench_validation import (
    ValidationScenarioOracle,
    ValidationScenarioRequest,
)


ACTION_SCHEMA_VERSION = "scenario-review-action.v1"
RECORD_SCHEMA_VERSION = "scenario-review-record.v1"
INTENT_RUN_SCHEMA_VERSION = "scenario-review-intent-run.v1"
REVIEW_DECISION = "APPROVE_FOR_VALIDATION"
REVIEW_STATUS = "APPROVED_FOR_VALIDATION"
IDENTITY_STATUS = "UNVERIFIED_FILE_ASSERTION"
NOT_RUN = "NOT_RUN"

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RUN_CANDIDATE_REFERENCE = re.compile(
    r"^C(?:00[1-9]|0[12][0-9]|03[0-2])$"
)
_PLAN_UNIT_REFERENCE = re.compile(
    r"^U(?:00[1-9]|0[12][0-9]|03[0-2])$"
)
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_OBSERVABLE_DRAFT_STATUSES = {
    "READY_FOR_HUMAN_REVIEW",
    "NEEDS_CLARIFICATION",
}

_ACTION_KEYS = {
    "schema_version",
    "identity_status",
    "decision",
    "semantic_approval",
    "gold_eligible",
    "patch_eligible",
    "expected_candidate_hash",
    "expected_batch_hash",
    "expected_candidate_ref",
    "expected_snapshot_hash",
    "expected_profile_hash",
    "expected_plan_hash",
    "expected_projection_hash",
    "reviewer_ref",
    "recorded_at",
    "final_request",
    "observable_oracle",
}
_RECORD_KEYS = {
    "schema_version",
    "status",
    "identity_status",
    "semantic_approval",
    "gold_eligible",
    "patch_eligible",
    "source_candidate_hash",
    "source_batch_hash",
    "candidate_ref",
    "source_snapshot_hash",
    "source_profile_hash",
    "source_plan_hash",
    "source_projection_hash",
    "source_action_hash",
    "plan_unit_ref",
    "scenario_target_stage",
    "scenario_family",
    "reviewer_ref",
    "recorded_at",
    "request",
    "oracle",
    "reviewed_hash",
}


class ScenarioValidationError(RuntimeError):
    """A scenario review or execution artifact failed a stable local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class IntentDraftProvider(Protocol):
    """The only model capability allowed by the first executable slice."""

    def draft(
        self,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> ChangeIntentDraft: ...


@dataclass(frozen=True, slots=True)
class ScenarioReviewAction:
    """Trusted review input that freezes a final request and observable oracle."""

    expected_candidate_hash: str
    expected_batch_hash: str
    expected_candidate_ref: str
    expected_snapshot_hash: str
    expected_profile_hash: str
    expected_plan_hash: str
    expected_projection_hash: str
    decision: str
    reviewer_ref: str
    recorded_at: str
    final_request: ValidationScenarioRequest
    observable_oracle: ValidationScenarioOracle

    def __post_init__(self) -> None:
        for field_name in (
            "expected_candidate_hash",
            "expected_batch_hash",
            "expected_snapshot_hash",
            "expected_profile_hash",
            "expected_plan_hash",
            "expected_projection_hash",
        ):
            _validate_digest(getattr(self, field_name), field_name)
        _validate_pattern(
            self.expected_candidate_ref,
            _RUN_CANDIDATE_REFERENCE,
            "expected_candidate_ref",
        )
        if self.decision != REVIEW_DECISION:
            raise ValueError("unsupported scenario review decision")
        _validate_reference(self.reviewer_ref, "reviewer_ref")
        _validate_timestamp(self.recorded_at)
        if not isinstance(self.final_request, ValidationScenarioRequest):
            raise ValueError("scenario review requires a final request")
        if not isinstance(self.observable_oracle, ValidationScenarioOracle):
            raise ValueError("scenario review requires an observable oracle")
        _validate_first_slice_oracle(self.observable_oracle)

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
    def action_hash(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Any) -> "ScenarioReviewAction":
        if not isinstance(payload, dict) or set(payload) != _ACTION_KEYS:
            raise ScenarioValidationError(
                "SCENARIO_REVIEW_ACTION_FIELDS_INVALID",
                "scenario review action must use the exact contract fields",
            )
        if payload["schema_version"] != ACTION_SCHEMA_VERSION:
            raise ScenarioValidationError(
                "SCENARIO_REVIEW_ACTION_VERSION_INVALID",
                "scenario review action schema is unsupported",
            )
        if (
            payload["identity_status"] != IDENTITY_STATUS
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise ScenarioValidationError(
                "SCENARIO_REVIEW_ACTION_POLICY_INVALID",
                "scenario review action violates its fixed policy",
            )
        try:
            return cls(
                expected_candidate_hash=payload["expected_candidate_hash"],
                expected_batch_hash=payload["expected_batch_hash"],
                expected_candidate_ref=payload["expected_candidate_ref"],
                expected_snapshot_hash=payload["expected_snapshot_hash"],
                expected_profile_hash=payload["expected_profile_hash"],
                expected_plan_hash=payload["expected_plan_hash"],
                expected_projection_hash=payload["expected_projection_hash"],
                decision=payload["decision"],
                reviewer_ref=payload["reviewer_ref"],
                recorded_at=payload["recorded_at"],
                final_request=_request_from_dict(payload["final_request"]),
                observable_oracle=_oracle_from_dict(payload["observable_oracle"]),
            )
        except (KeyError, TypeError, ValueError):
            raise ScenarioValidationError(
                "SCENARIO_REVIEW_ACTION_VALUE_INVALID",
                "scenario review action failed local validation",
            ) from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTION_SCHEMA_VERSION,
            "identity_status": IDENTITY_STATUS,
            "decision": self.decision,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "expected_candidate_hash": self.expected_candidate_hash,
            "expected_batch_hash": self.expected_batch_hash,
            "expected_candidate_ref": self.expected_candidate_ref,
            "expected_snapshot_hash": self.expected_snapshot_hash,
            "expected_profile_hash": self.expected_profile_hash,
            "expected_plan_hash": self.expected_plan_hash,
            "expected_projection_hash": self.expected_projection_hash,
            "reviewer_ref": self.reviewer_ref,
            "recorded_at": self.recorded_at,
            "final_request": _request_to_dict(self.final_request),
            "observable_oracle": _oracle_to_dict(self.observable_oracle),
        }


@dataclass(frozen=True, slots=True)
class ReviewedValidationScenario:
    """One source-bound, in-memory scenario approved only for validation."""

    source_candidate_hash: str
    source_batch_hash: str
    candidate_ref: str
    source_snapshot_hash: str
    source_profile_hash: str
    source_plan_hash: str
    source_projection_hash: str
    source_action_hash: str
    plan_unit_ref: str
    scenario_target_stage: str
    scenario_family: str
    reviewer_ref: str
    recorded_at: str
    request: ValidationScenarioRequest
    oracle: ValidationScenarioOracle
    reviewed_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_candidate_hash",
            "source_batch_hash",
            "source_snapshot_hash",
            "source_profile_hash",
            "source_plan_hash",
            "source_projection_hash",
            "source_action_hash",
            "reviewed_hash",
        ):
            _validate_digest(getattr(self, field_name), field_name)
        _validate_pattern(
            self.candidate_ref,
            _RUN_CANDIDATE_REFERENCE,
            "candidate_ref",
        )
        _validate_pattern(self.plan_unit_ref, _PLAN_UNIT_REFERENCE, "plan_unit_ref")
        if self.scenario_target_stage not in {
            "INTENT",
            "RETRIEVAL",
            "RECOMMENDATION",
        }:
            raise ValueError("scenario review target stage is unsupported")
        if self.scenario_family not in SCENARIO_FAMILIES:
            raise ValueError("scenario review family is unsupported")
        _validate_reference(self.reviewer_ref, "reviewer_ref")
        _validate_timestamp(self.recorded_at)
        if not isinstance(self.request, ValidationScenarioRequest):
            raise ValueError("reviewed scenario request is invalid")
        if not isinstance(self.oracle, ValidationScenarioOracle):
            raise ValueError("reviewed scenario oracle is invalid")
        _validate_first_slice_oracle(self.oracle)
        if self.reviewed_hash != canonical_digest(self._payload()):
            raise ValueError("reviewed scenario hash does not match its payload")

    @property
    def status(self) -> str:
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
    def from_dict(
        cls,
        payload: Any,
        action: ScenarioReviewAction,
        batch: ScenarioPreparationBatch,
        batch_candidate: ScenarioPreparationBatchCandidate,
        projection: ScenarioPreparationProjection,
        plan: ScenarioPreparationPlan,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
    ) -> "ReviewedValidationScenario":
        if not isinstance(payload, dict) or set(payload) != _RECORD_KEYS:
            raise ScenarioValidationError(
                "SCENARIO_REVIEWED_FIELDS_INVALID",
                "reviewed scenario must use the exact contract fields",
            )
        if payload["schema_version"] != RECORD_SCHEMA_VERSION:
            raise ScenarioValidationError(
                "SCENARIO_REVIEWED_VERSION_INVALID",
                "reviewed scenario schema is unsupported",
            )
        if (
            payload["status"] != REVIEW_STATUS
            or payload["identity_status"] != IDENTITY_STATUS
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise ScenarioValidationError(
                "SCENARIO_REVIEWED_POLICY_INVALID",
                "reviewed scenario violates its fixed policy",
            )
        try:
            reviewed = cls(
                source_candidate_hash=payload["source_candidate_hash"],
                source_batch_hash=payload["source_batch_hash"],
                candidate_ref=payload["candidate_ref"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                source_profile_hash=payload["source_profile_hash"],
                source_plan_hash=payload["source_plan_hash"],
                source_projection_hash=payload["source_projection_hash"],
                source_action_hash=payload["source_action_hash"],
                plan_unit_ref=payload["plan_unit_ref"],
                scenario_target_stage=payload["scenario_target_stage"],
                scenario_family=payload["scenario_family"],
                reviewer_ref=payload["reviewer_ref"],
                recorded_at=payload["recorded_at"],
                request=_request_from_dict(payload["request"]),
                oracle=_oracle_from_dict(payload["oracle"]),
                reviewed_hash=payload["reviewed_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise ScenarioValidationError(
                "SCENARIO_REVIEWED_VALUE_INVALID",
                "reviewed scenario failed local validation",
            ) from None
        verify_reviewed_validation_scenario_against_sources(
            reviewed,
            action,
            batch,
            batch_candidate,
            projection,
            plan,
            profile,
            tree,
        )
        return reviewed

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RECORD_SCHEMA_VERSION,
            "status": REVIEW_STATUS,
            "identity_status": IDENTITY_STATUS,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "source_candidate_hash": self.source_candidate_hash,
            "source_batch_hash": self.source_batch_hash,
            "candidate_ref": self.candidate_ref,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_profile_hash": self.source_profile_hash,
            "source_plan_hash": self.source_plan_hash,
            "source_projection_hash": self.source_projection_hash,
            "source_action_hash": self.source_action_hash,
            "plan_unit_ref": self.plan_unit_ref,
            "scenario_target_stage": self.scenario_target_stage,
            "scenario_family": self.scenario_family,
            "reviewer_ref": self.reviewer_ref,
            "recorded_at": self.recorded_at,
            "request": _request_to_dict(self.request),
            "oracle": _oracle_to_dict(self.oracle),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["reviewed_hash"] = self.reviewed_hash
        return payload


@dataclass(frozen=True, slots=True)
class ScenarioIntentRun:
    """Evidence for one reviewed scenario's INTENT-only execution."""

    source_reviewed_hash: str
    source_action_hash: str
    source_candidate_hash: str
    source_batch_hash: str
    source_snapshot_hash: str
    source_request_hash: str
    source_intent_draft_hash: str
    plan_unit_ref: str
    candidate_ref: str
    scenario_target_stage: str
    scenario_family: str
    expected_draft_status: str
    actual_draft_status: str
    intent_validation_status: str
    retrieval_validation_status: str
    recommendation_validation_status: str
    target_validation_status: str
    run_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_reviewed_hash",
            "source_action_hash",
            "source_candidate_hash",
            "source_batch_hash",
            "source_snapshot_hash",
            "source_request_hash",
            "source_intent_draft_hash",
            "run_hash",
        ):
            _validate_digest(getattr(self, field_name), field_name)
        _validate_pattern(self.plan_unit_ref, _PLAN_UNIT_REFERENCE, "plan_unit_ref")
        _validate_pattern(
            self.candidate_ref,
            _RUN_CANDIDATE_REFERENCE,
            "candidate_ref",
        )
        if self.scenario_target_stage not in {
            "INTENT",
            "RETRIEVAL",
            "RECOMMENDATION",
        }:
            raise ValueError("scenario intent run target stage is unsupported")
        if self.scenario_family not in SCENARIO_FAMILIES:
            raise ValueError("scenario intent run family is unsupported")
        if self.expected_draft_status not in _OBSERVABLE_DRAFT_STATUSES:
            raise ValueError("scenario intent run expected status is unsupported")
        if self.actual_draft_status not in _OBSERVABLE_DRAFT_STATUSES:
            raise ValueError("scenario intent run actual status is unsupported")
        if self.intent_validation_status not in {"MATCH", "MISMATCH"}:
            raise ValueError("scenario intent validation status is invalid")
        if (
            self.retrieval_validation_status != NOT_RUN
            or self.recommendation_validation_status != NOT_RUN
        ):
            raise ValueError("later scenario validation stages must not run")
        expected_target_status = (
            self.intent_validation_status
            if self.scenario_target_stage == "INTENT"
            else NOT_RUN
        )
        if self.target_validation_status != expected_target_status:
            raise ValueError("scenario target validation status is inconsistent")
        if self.run_hash != canonical_digest(self._payload()):
            raise ValueError("scenario intent run hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": INTENT_RUN_SCHEMA_VERSION,
            "source_reviewed_hash": self.source_reviewed_hash,
            "source_action_hash": self.source_action_hash,
            "source_candidate_hash": self.source_candidate_hash,
            "source_batch_hash": self.source_batch_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_request_hash": self.source_request_hash,
            "source_intent_draft_hash": self.source_intent_draft_hash,
            "plan_unit_ref": self.plan_unit_ref,
            "candidate_ref": self.candidate_ref,
            "scenario_target_stage": self.scenario_target_stage,
            "scenario_family": self.scenario_family,
            "expected_draft_status": self.expected_draft_status,
            "actual_draft_status": self.actual_draft_status,
            "intent_validation_status": self.intent_validation_status,
            "retrieval_validation_status": self.retrieval_validation_status,
            "recommendation_validation_status": (
                self.recommendation_validation_status
            ),
            "target_validation_status": self.target_validation_status,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["run_hash"] = self.run_hash
        return payload


def apply_scenario_review(
    action: ScenarioReviewAction,
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> ReviewedValidationScenario:
    """Apply one trusted approval after replaying every untrusted source."""

    if not isinstance(action, ScenarioReviewAction):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_ACTION_REQUIRED",
            "a trusted typed scenario review action is required",
        )
    _verify_batch_candidate_against_sources(
        batch,
        batch_candidate,
        projection,
        plan,
        profile,
        tree,
    )
    candidate = batch_candidate.draft
    expected_bindings = {
        "candidate": (action.expected_candidate_hash, candidate.draft_hash),
        "batch": (action.expected_batch_hash, batch.batch_hash),
        "candidate_ref": (
            action.expected_candidate_ref,
            batch_candidate.candidate_ref,
        ),
        "snapshot": (action.expected_snapshot_hash, tree.snapshot_hash),
        "profile": (action.expected_profile_hash, profile.profile_hash),
        "plan": (action.expected_plan_hash, plan.plan_hash),
        "projection": (
            action.expected_projection_hash,
            projection.projection_hash,
        ),
    }
    if any(expected != actual for expected, actual in expected_bindings.values()):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_ACTION_STALE",
            "scenario review action does not bind the current trusted sources",
        )
    _intent_request_from_validation(action.final_request, tree)
    _validate_first_slice_oracle(action.observable_oracle)
    payload = _reviewed_payload(
        action,
        batch,
        batch_candidate,
        projection,
        plan,
        profile,
        tree,
    )
    return ReviewedValidationScenario(
        source_candidate_hash=candidate.draft_hash,
        source_batch_hash=batch.batch_hash,
        candidate_ref=batch_candidate.candidate_ref,
        source_snapshot_hash=tree.snapshot_hash,
        source_profile_hash=profile.profile_hash,
        source_plan_hash=plan.plan_hash,
        source_projection_hash=projection.projection_hash,
        source_action_hash=action.action_hash,
        plan_unit_ref=candidate.plan_unit_ref,
        scenario_target_stage=candidate.target_stage,
        scenario_family=candidate.scenario_family,
        reviewer_ref=action.reviewer_ref,
        recorded_at=action.recorded_at,
        request=action.final_request,
        oracle=action.observable_oracle,
        reviewed_hash=canonical_digest(payload),
    )


def verify_reviewed_validation_scenario_against_sources(
    reviewed: ReviewedValidationScenario,
    action: ScenarioReviewAction,
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    """Replay an approved in-memory scenario from all of its trusted sources."""

    if not isinstance(reviewed, ReviewedValidationScenario):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_REQUIRED",
            "a reviewed validation scenario is required before execution",
        )
    expected = apply_scenario_review(
        action,
        batch,
        batch_candidate,
        projection,
        plan,
        profile,
        tree,
    )
    if reviewed != expected:
        raise ScenarioValidationError(
            "SCENARIO_REVIEWED_SOURCE_MISMATCH",
            "reviewed scenario does not match its trusted source replay",
        )


def run_reviewed_intent_slice(
    reviewed: ReviewedValidationScenario,
    action: ScenarioReviewAction,
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
    provider: IntentDraftProvider,
) -> ScenarioIntentRun:
    """Run exactly one draft call after the explicit review gate succeeds."""

    verify_reviewed_validation_scenario_against_sources(
        reviewed,
        action,
        batch,
        batch_candidate,
        projection,
        plan,
        profile,
        tree,
    )
    request = _intent_request_from_validation(reviewed.request, tree)
    draft = provider.draft(request, tree)
    if not isinstance(draft, ChangeIntentDraft):
        raise ScenarioValidationError(
            "SCENARIO_INTENT_DRAFT_INVALID",
            "intent provider did not return a typed draft",
        )
    try:
        verify_intent_draft_against_sources(draft, request, tree)
    except IntentValidationError:
        raise ScenarioValidationError(
            "SCENARIO_INTENT_DRAFT_SOURCE_MISMATCH",
            "intent draft does not match the reviewed request and snapshot",
        ) from None
    intent_status = (
        "MATCH"
        if draft.review_status == reviewed.oracle.draft_status
        else "MISMATCH"
    )
    target_status = (
        intent_status if reviewed.scenario_target_stage == "INTENT" else NOT_RUN
    )
    payload = _intent_run_payload(
        reviewed,
        request,
        draft,
        intent_status,
        target_status,
    )
    return ScenarioIntentRun(
        source_reviewed_hash=reviewed.reviewed_hash,
        source_action_hash=reviewed.source_action_hash,
        source_candidate_hash=reviewed.source_candidate_hash,
        source_batch_hash=reviewed.source_batch_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_request_hash=request.request_hash,
        source_intent_draft_hash=draft.draft_hash,
        plan_unit_ref=reviewed.plan_unit_ref,
        candidate_ref=reviewed.candidate_ref,
        scenario_target_stage=reviewed.scenario_target_stage,
        scenario_family=reviewed.scenario_family,
        expected_draft_status=reviewed.oracle.draft_status,
        actual_draft_status=draft.review_status,
        intent_validation_status=intent_status,
        retrieval_validation_status=NOT_RUN,
        recommendation_validation_status=NOT_RUN,
        target_validation_status=target_status,
        run_hash=canonical_digest(payload),
    )


def _verify_batch_candidate_against_sources(
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    if not isinstance(batch, ScenarioPreparationBatch) or not isinstance(
        batch_candidate,
        ScenarioPreparationBatchCandidate,
    ):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_BATCH_CANDIDATE_REQUIRED",
            "a typed batch and run-level candidate are required",
        )
    try:
        verify_scenario_preparation_batch_against_sources(
            batch,
            plan,
            profile,
            tree,
        )
    except (TreeUnderstandingError, TypeError, ValueError):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_BATCH_SOURCE_MISMATCH",
            "scenario batch does not match the trusted plan",
        ) from None
    if (
        batch.source_snapshot_hash != tree.snapshot_hash
        or batch.source_profile_hash != profile.profile_hash
        or batch_candidate not in batch.candidates
    ):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_BATCH_SOURCE_MISMATCH",
            "scenario batch or run-level candidate failed source replay",
        )
    _verify_candidate_against_sources(
        batch_candidate.draft,
        projection,
        plan,
        profile,
        tree,
    )


def _verify_candidate_against_sources(
    candidate: ScenarioCandidateDraft,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> None:
    if not isinstance(candidate, ScenarioCandidateDraft):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_CANDIDATE_REQUIRED",
            "a locally validated scenario candidate is required",
        )
    try:
        verify_scenario_preparation_projection_against_sources(
            projection,
            plan,
            profile,
            tree,
        )
        expected = ScenarioCandidateDraft.from_model_dict(
            candidate.to_model_dict(),
            projection,
            plan,
            profile,
            tree,
            model_provider=candidate.model_provider,
            model_capability=candidate.model_capability,
            model_name=candidate.model_name,
            prompt_version=candidate.prompt_version,
        )
    except (TreeUnderstandingError, TypeError, ValueError):
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_CANDIDATE_SOURCE_MISMATCH",
            "scenario candidate does not match the trusted sources",
        ) from None
    if candidate != expected:
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_CANDIDATE_SOURCE_MISMATCH",
            "scenario candidate does not match its deterministic replay",
        )


def _reviewed_payload(
    action: ScenarioReviewAction,
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
) -> dict[str, Any]:
    candidate = batch_candidate.draft
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "status": REVIEW_STATUS,
        "identity_status": IDENTITY_STATUS,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "source_candidate_hash": candidate.draft_hash,
        "source_batch_hash": batch.batch_hash,
        "candidate_ref": batch_candidate.candidate_ref,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_profile_hash": profile.profile_hash,
        "source_plan_hash": plan.plan_hash,
        "source_projection_hash": projection.projection_hash,
        "source_action_hash": action.action_hash,
        "plan_unit_ref": candidate.plan_unit_ref,
        "scenario_target_stage": candidate.target_stage,
        "scenario_family": candidate.scenario_family,
        "reviewer_ref": action.reviewer_ref,
        "recorded_at": action.recorded_at,
        "request": _request_to_dict(action.final_request),
        "oracle": _oracle_to_dict(action.observable_oracle),
    }


def _intent_run_payload(
    reviewed: ReviewedValidationScenario,
    request: IntentRequest,
    draft: ChangeIntentDraft,
    intent_status: str,
    target_status: str,
) -> dict[str, Any]:
    return {
        "schema_version": INTENT_RUN_SCHEMA_VERSION,
        "source_reviewed_hash": reviewed.reviewed_hash,
        "source_action_hash": reviewed.source_action_hash,
        "source_candidate_hash": reviewed.source_candidate_hash,
        "source_batch_hash": reviewed.source_batch_hash,
        "source_snapshot_hash": reviewed.source_snapshot_hash,
        "source_request_hash": request.request_hash,
        "source_intent_draft_hash": draft.draft_hash,
        "plan_unit_ref": reviewed.plan_unit_ref,
        "candidate_ref": reviewed.candidate_ref,
        "scenario_target_stage": reviewed.scenario_target_stage,
        "scenario_family": reviewed.scenario_family,
        "expected_draft_status": reviewed.oracle.draft_status,
        "actual_draft_status": draft.review_status,
        "intent_validation_status": intent_status,
        "retrieval_validation_status": NOT_RUN,
        "recommendation_validation_status": NOT_RUN,
        "target_validation_status": target_status,
    }


def _intent_request_from_validation(
    request: ValidationScenarioRequest,
    tree: CanonicalTree,
) -> IntentRequest:
    try:
        return IntentRequest.from_dict(
            {
                "schema_version": REQUEST_SCHEMA_VERSION,
                **_request_to_dict(request),
            },
            tree,
        )
    except IntentValidationError:
        raise ScenarioValidationError(
            "SCENARIO_REVIEW_REQUEST_INVALID",
            "reviewed request is not valid for the bound source tree",
        ) from None


def _request_to_dict(request: ValidationScenarioRequest) -> dict[str, Any]:
    return {
        "requirement_text": request.requirement_text,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "node_kind_hint": request.node_kind_hint,
        "value_type_hint": request.value_type_hint,
        "cardinality_hint": request.cardinality_hint,
    }


def _request_from_dict(payload: Any) -> ValidationScenarioRequest:
    keys = {
        "requirement_text",
        "proposed_parent_node_id",
        "node_kind_hint",
        "value_type_hint",
        "cardinality_hint",
    }
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ValueError("scenario review request fields are invalid")
    return ValidationScenarioRequest(**payload)


def _oracle_to_dict(oracle: ValidationScenarioOracle) -> dict[str, Any]:
    return {
        "draft_status": oracle.draft_status,
        "clarification_status": oracle.clarification_status,
        "candidate_status": oracle.candidate_status,
        "recommendation_status": oracle.recommendation_status,
    }


def _oracle_from_dict(payload: Any) -> ValidationScenarioOracle:
    keys = {
        "draft_status",
        "clarification_status",
        "candidate_status",
        "recommendation_status",
    }
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ValueError("scenario review oracle fields are invalid")
    return ValidationScenarioOracle(**payload)


def _validate_first_slice_oracle(oracle: ValidationScenarioOracle) -> None:
    if oracle.draft_status not in _OBSERVABLE_DRAFT_STATUSES:
        raise ValueError("scenario oracle draft_status is unsupported")
    if any(
        value is not None
        for value in (
            oracle.clarification_status,
            oracle.candidate_status,
            oracle.recommendation_status,
        )
    ):
        raise ValueError("scenario first-slice oracle cannot expect later stages")


def _validate_digest(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a SHA-256 digest")


def _validate_reference(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _REFERENCE.fullmatch(value) is None:
        raise ValueError(f"{field_name} is invalid")


def _validate_pattern(
    value: Any,
    pattern: re.Pattern[str],
    field_name: str,
) -> None:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{field_name} is invalid")


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ValueError("recorded_at must be strict RFC3339")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at must include a timezone")


__all__ = [
    "ACTION_SCHEMA_VERSION",
    "IDENTITY_STATUS",
    "INTENT_RUN_SCHEMA_VERSION",
    "IntentDraftProvider",
    "NOT_RUN",
    "RECORD_SCHEMA_VERSION",
    "REVIEW_DECISION",
    "REVIEW_STATUS",
    "ReviewedValidationScenario",
    "ScenarioIntentRun",
    "ScenarioReviewAction",
    "ScenarioValidationError",
    "apply_scenario_review",
    "run_reviewed_intent_slice",
    "verify_reviewed_validation_scenario_against_sources",
]
