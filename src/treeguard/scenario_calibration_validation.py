"""Non-gating M4.6 scoring calibration over exposed Silver observations.

This module does not mutate or reinterpret the M4 v1 wire contracts.  It binds
an explicit Silver-only scoring policy to one existing capability Oracle and
produces an aggregate comparison without claiming holdout or Gold status.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from treeguard.hashing import canonical_digest
from treeguard.models import freeze_json, thaw_json
from treeguard.retrieval import CandidateSet
from treeguard.scenario_capability_validation import (
    CapabilityOracle,
    ScenarioCapabilityRun,
    recommendation_outcome_from_draft,
    retrieval_matches_oracle,
)
from treeguard.semantic_recommendation import SemanticRecommendationDraft


CALIBRATION_POLICY_SCHEMA_VERSION = "scenario-calibration-policy.v1"
CALIBRATION_POLICY_VERSION = "treeguard.m46-silver-calibration.v1"
CALIBRATION_OBSERVATION_SCHEMA_VERSION = "scenario-calibration-observation.v1"
CALIBRATION_REPORT_SCHEMA_VERSION = "scenario-calibration-comparison-report.v1"

RETRIEVAL_MODES = {"TARGET_HIT", "BOUNDED_EVIDENCE", "EMPTY_RESULT"}
CALIBRATED_RETRIEVAL_STATUSES = {"MATCH", "MISMATCH", "NOT_RUN", "RUN_FAILED"}
SEMANTIC_CALIBRATION_STATUSES = {
    "PREFERRED_MATCH",
    "SAFE_ALTERNATIVE",
    "UNSAFE_MISMATCH",
    "NOT_OBSERVED",
    "RUN_FAILED",
}
SEMANTIC_OBSERVATION_SOURCES = {
    "NONE",
    "ORIGINAL_RUN",
    "SUPPLEMENTAL_CALIBRATION",
}
SAFE_NON_TARGETING_ACTIONS = {
    "ABSTAIN",
    "NEED_CLARIFICATION",
    "NEED_EVIDENCE",
}
SEMANTIC_SAFE_ACTION_POLICY = "treeguard.non-targeting-safe-alternative.v1"

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_OBSERVATION_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_POLICY_KEYS = {
    "schema_version",
    "policy_version",
    "quality_tier",
    "assessment_authority",
    "evaluation_role",
    "gate_eligible",
    "gold_eligible",
    "source_overlay_hash",
    "source_oracle_digest",
    "retrieval_mode",
    "semantic_safe_action_policy",
    "policy_hash",
}
_OBSERVATION_KEYS = {
    "schema_version",
    "observation_ref",
    "source_run_hash",
    "source_policy_hash",
    "strict_full_path_status",
    "strict_retrieval_status",
    "calibrated_retrieval_status",
    "calibrated_retrieval_reason",
    "semantic_status",
    "semantic_observation_source",
    "source_recommendation_draft_hash",
    "newly_semantic_eligible",
    "result_hash",
}
_REPORT_KEYS = {
    "schema_version",
    "policy_version",
    "quality_tier",
    "evaluation_role",
    "gate_eligible",
    "gold_eligible",
    "observation_count",
    "policy_count",
    "strict_full_path_counts",
    "strict_retrieval_counts",
    "calibrated_retrieval_counts",
    "calibrated_retrieval_match_kinds",
    "semantic_counts",
    "semantic_source_counts",
    "newly_semantic_eligible_count",
    "full_path_reassessment_status",
    "report_hash",
}
_FULL_PATH_STATUSES = {"MATCH", "MISMATCH", "RUN_FAILED"}
_RETRIEVAL_REASONS = {
    "CALIBRATION_TARGET_HIT",
    "CALIBRATION_BOUNDED_EVIDENCE_READY",
    "CALIBRATION_EMPTY_RESULT",
    "CALIBRATION_RETRIEVAL_MISMATCH",
    "CALIBRATION_RETRIEVAL_RUN_FAILED",
    "UPSTREAM_INTENT_MISMATCH",
    "UPSTREAM_INTENT_RUN_FAILED",
}
_MATCH_REASONS = {
    "CALIBRATION_TARGET_HIT",
    "CALIBRATION_BOUNDED_EVIDENCE_READY",
    "CALIBRATION_EMPTY_RESULT",
}


def _validate_digest(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a SHA-256 digest")


def _count_map(value: Any, keys: set[str], field_name: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{field_name} must use exact status keys")
    if any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in value.values()
    ):
        raise ValueError(f"{field_name} counts must be non-negative integers")
    return dict(value)


@dataclass(frozen=True, slots=True)
class ScenarioCalibrationPolicy:
    schema_version: str
    policy_version: str
    quality_tier: str
    assessment_authority: str
    evaluation_role: str
    gate_eligible: bool
    gold_eligible: bool
    source_overlay_hash: str
    source_oracle_digest: str
    retrieval_mode: str
    semantic_safe_action_policy: str
    policy_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_POLICY_SCHEMA_VERSION:
            raise ValueError("calibration policy schema version is unsupported")
        if self.policy_version != CALIBRATION_POLICY_VERSION:
            raise ValueError("calibration policy version is unsupported")
        if (
            self.quality_tier != "SILVER"
            or self.assessment_authority != "CODEX_ASSISTED"
            or self.evaluation_role != "CALIBRATION_ONLY"
            or self.gate_eligible is not False
            or self.gold_eligible is not False
        ):
            raise ValueError("calibration policy trust boundary is invalid")
        _validate_digest(self.source_overlay_hash, "source_overlay_hash")
        _validate_digest(self.source_oracle_digest, "source_oracle_digest")
        if self.retrieval_mode not in RETRIEVAL_MODES:
            raise ValueError("calibration retrieval mode is unsupported")
        if self.semantic_safe_action_policy != SEMANTIC_SAFE_ACTION_POLICY:
            raise ValueError("semantic safe-action policy is unsupported")
        _validate_digest(self.policy_hash, "policy_hash")
        if canonical_digest(self._hash_payload()) != self.policy_hash:
            raise ValueError("calibration policy hash is invalid")

    @classmethod
    def create(
        cls,
        *,
        source_overlay_hash: str,
        oracle: CapabilityOracle,
        retrieval_mode: str,
    ) -> "ScenarioCalibrationPolicy":
        if not isinstance(oracle, CapabilityOracle):
            raise TypeError("calibration policy requires a capability Oracle")
        _validate_policy_mode_against_oracle(retrieval_mode, oracle)
        values = {
            "schema_version": CALIBRATION_POLICY_SCHEMA_VERSION,
            "policy_version": CALIBRATION_POLICY_VERSION,
            "quality_tier": "SILVER",
            "assessment_authority": "CODEX_ASSISTED",
            "evaluation_role": "CALIBRATION_ONLY",
            "gate_eligible": False,
            "gold_eligible": False,
            "source_overlay_hash": source_overlay_hash,
            "source_oracle_digest": canonical_digest(oracle.to_dict()),
            "retrieval_mode": retrieval_mode,
            "semantic_safe_action_policy": SEMANTIC_SAFE_ACTION_POLICY,
        }
        return cls(**values, policy_hash=canonical_digest(values))

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        *,
        oracle: CapabilityOracle,
        expected_overlay_hash: str,
    ) -> "ScenarioCalibrationPolicy":
        if not isinstance(payload, dict) or set(payload) != _POLICY_KEYS:
            raise ValueError("calibration policy must use exact fields")
        policy = cls(**payload)
        if policy.source_overlay_hash != expected_overlay_hash:
            raise ValueError("calibration policy overlay source is stale")
        if policy.source_oracle_digest != canonical_digest(oracle.to_dict()):
            raise ValueError("calibration policy Oracle source is stale")
        _validate_policy_mode_against_oracle(policy.retrieval_mode, oracle)
        return policy

    def _hash_payload(self) -> dict[str, Any]:
        return {
            key: getattr(self, key)
            for key in sorted(_POLICY_KEYS - {"policy_hash"})
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._hash_payload(),
            "policy_hash": self.policy_hash,
        }


def _validate_policy_mode_against_oracle(
    retrieval_mode: str,
    oracle: CapabilityOracle,
) -> None:
    if retrieval_mode not in RETRIEVAL_MODES:
        raise ValueError("calibration retrieval mode is unsupported")
    retrieval = oracle.retrieval
    if oracle.expected_route != "PROCEED" or not retrieval.applicable:
        raise ValueError("calibration retrieval policy requires a PROCEED Oracle")
    if retrieval_mode == "TARGET_HIT":
        if (
            not retrieval.acceptable_node_ids
            or retrieval.allowed_statuses != ("CANDIDATES_READY",)
        ):
            raise ValueError("TARGET_HIT requires a targeted ready-candidate Oracle")
    elif retrieval_mode == "BOUNDED_EVIDENCE":
        if "CANDIDATES_READY" not in retrieval.allowed_statuses:
            raise ValueError("BOUNDED_EVIDENCE requires a ready-candidate Oracle")
    elif retrieval.acceptable_node_ids or "CANDIDATES_READY" in retrieval.allowed_statuses:
        raise ValueError("EMPTY_RESULT requires an empty-target Oracle")


@dataclass(frozen=True, slots=True)
class CalibrationObservationResult:
    schema_version: str
    observation_ref: str
    source_run_hash: str
    source_policy_hash: str
    strict_full_path_status: str
    strict_retrieval_status: str
    calibrated_retrieval_status: str
    calibrated_retrieval_reason: str
    semantic_status: str
    semantic_observation_source: str
    source_recommendation_draft_hash: str | None
    newly_semantic_eligible: bool
    result_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_OBSERVATION_SCHEMA_VERSION:
            raise ValueError("calibration observation schema version is unsupported")
        if (
            not isinstance(self.observation_ref, str)
            or _OBSERVATION_REFERENCE.fullmatch(self.observation_ref) is None
        ):
            raise ValueError("calibration observation_ref is invalid")
        _validate_digest(self.source_run_hash, "source_run_hash")
        _validate_digest(self.source_policy_hash, "source_policy_hash")
        if self.strict_full_path_status not in _FULL_PATH_STATUSES:
            raise ValueError("strict full-path status is unsupported")
        if self.strict_retrieval_status not in CALIBRATED_RETRIEVAL_STATUSES:
            raise ValueError("strict retrieval status is unsupported")
        if self.calibrated_retrieval_status not in CALIBRATED_RETRIEVAL_STATUSES:
            raise ValueError("calibrated retrieval status is unsupported")
        if self.calibrated_retrieval_reason not in _RETRIEVAL_REASONS:
            raise ValueError("calibrated retrieval reason is unsupported")
        if (
            self.calibrated_retrieval_status == "MATCH"
        ) != (self.calibrated_retrieval_reason in _MATCH_REASONS):
            raise ValueError("calibrated retrieval status and reason disagree")
        if self.semantic_status not in SEMANTIC_CALIBRATION_STATUSES:
            raise ValueError("semantic calibration status is unsupported")
        if self.semantic_observation_source not in SEMANTIC_OBSERVATION_SOURCES:
            raise ValueError("semantic observation source is unsupported")
        if self.source_recommendation_draft_hash is not None:
            _validate_digest(
                self.source_recommendation_draft_hash,
                "source_recommendation_draft_hash",
            )
        if self.semantic_status == "NOT_OBSERVED" and (
            self.semantic_observation_source != "NONE"
            or self.source_recommendation_draft_hash is not None
        ):
            raise ValueError("unobserved Semantic result cannot claim a source")
        if self.semantic_status in {
            "PREFERRED_MATCH",
            "SAFE_ALTERNATIVE",
            "UNSAFE_MISMATCH",
        } and (
            self.semantic_observation_source == "NONE"
            or self.source_recommendation_draft_hash is None
        ):
            raise ValueError("scored Semantic result requires a bound draft")
        if self.semantic_status == "RUN_FAILED" and (
            self.semantic_observation_source == "NONE"
            or self.source_recommendation_draft_hash is not None
        ):
            raise ValueError("failed Semantic observation must bind an attempt source")
        if not isinstance(self.newly_semantic_eligible, bool):
            raise ValueError("newly_semantic_eligible must be boolean")
        if self.newly_semantic_eligible and (
            self.strict_retrieval_status != "MISMATCH"
            or self.calibrated_retrieval_status != "MATCH"
            or self.semantic_status != "NOT_OBSERVED"
        ):
            raise ValueError("newly eligible Semantic observation is inconsistent")
        _validate_digest(self.result_hash, "result_hash")
        if canonical_digest(self._hash_payload()) != self.result_hash:
            raise ValueError("calibration observation hash is invalid")

    @classmethod
    def create(cls, **values: Any) -> "CalibrationObservationResult":
        payload = {
            "schema_version": CALIBRATION_OBSERVATION_SCHEMA_VERSION,
            **values,
        }
        return cls(**payload, result_hash=canonical_digest(payload))

    @classmethod
    def from_dict(cls, payload: Any) -> "CalibrationObservationResult":
        if not isinstance(payload, dict) or set(payload) != _OBSERVATION_KEYS:
            raise ValueError("calibration observation must use exact fields")
        return cls(**payload)

    def _hash_payload(self) -> dict[str, Any]:
        return {
            key: getattr(self, key)
            for key in sorted(_OBSERVATION_KEYS - {"result_hash"})
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "result_hash": self.result_hash}


def score_calibration_observation(
    run: ScenarioCapabilityRun,
    oracle: CapabilityOracle,
    policy: ScenarioCalibrationPolicy,
    *,
    observation_ref: str,
    candidate_set: CandidateSet | None,
    recommendation_draft: SemanticRecommendationDraft | None,
    semantic_observation_source: str | None = None,
    semantic_provider_failed: bool = False,
) -> CalibrationObservationResult:
    """Score one already-executed Silver observation without changing its run."""

    if not isinstance(run, ScenarioCapabilityRun):
        raise TypeError("calibration scoring requires a capability run")
    if not isinstance(oracle, CapabilityOracle) or not isinstance(
        policy, ScenarioCalibrationPolicy
    ):
        raise TypeError("calibration scoring requires trusted policy objects")
    if run.expected_route != "PROCEED":
        raise ValueError("clarification runs are outside retrieval calibration")
    if run.source_overlay_hash != policy.source_overlay_hash:
        raise ValueError("calibration run does not match the policy overlay")
    if policy.source_oracle_digest != canonical_digest(oracle.to_dict()):
        raise ValueError("calibration policy does not match the Oracle")
    _validate_policy_mode_against_oracle(policy.retrieval_mode, oracle)

    if run.intent.status != "MATCH":
        if candidate_set is not None or recommendation_draft is not None:
            raise ValueError("upstream Intent failure cannot carry downstream artifacts")
        reason = (
            "UPSTREAM_INTENT_RUN_FAILED"
            if run.intent.status == "RUN_FAILED"
            else "UPSTREAM_INTENT_MISMATCH"
        )
        return CalibrationObservationResult.create(
            observation_ref=observation_ref,
            source_run_hash=run.run_hash,
            source_policy_hash=policy.policy_hash,
            strict_full_path_status=run.full_path_status,
            strict_retrieval_status=run.retrieval.status,
            calibrated_retrieval_status="NOT_RUN",
            calibrated_retrieval_reason=reason,
            semantic_status="NOT_OBSERVED",
            semantic_observation_source="NONE",
            source_recommendation_draft_hash=None,
            newly_semantic_eligible=False,
        )

    if run.retrieval.status == "RUN_FAILED":
        if recommendation_draft is not None:
            raise ValueError("retrieval failure cannot carry a recommendation")
        return CalibrationObservationResult.create(
            observation_ref=observation_ref,
            source_run_hash=run.run_hash,
            source_policy_hash=policy.policy_hash,
            strict_full_path_status=run.full_path_status,
            strict_retrieval_status=run.retrieval.status,
            calibrated_retrieval_status="RUN_FAILED",
            calibrated_retrieval_reason="CALIBRATION_RETRIEVAL_RUN_FAILED",
            semantic_status="NOT_OBSERVED",
            semantic_observation_source="NONE",
            source_recommendation_draft_hash=None,
            newly_semantic_eligible=False,
        )

    if not isinstance(candidate_set, CandidateSet):
        raise ValueError("Intent-matched calibration requires the candidate set")
    if run.source_candidate_set_hash != candidate_set.candidate_set_hash:
        raise ValueError("calibration candidate set does not match the source run")

    retrieval_match, retrieval_reason = _score_retrieval(candidate_set, oracle, policy)
    calibrated_retrieval_status = "MATCH" if retrieval_match else "MISMATCH"
    if not retrieval_match:
        if recommendation_draft is not None:
            raise ValueError("calibrated retrieval mismatch cannot score Semantic")
        return CalibrationObservationResult.create(
            observation_ref=observation_ref,
            source_run_hash=run.run_hash,
            source_policy_hash=policy.policy_hash,
            strict_full_path_status=run.full_path_status,
            strict_retrieval_status=run.retrieval.status,
            calibrated_retrieval_status=calibrated_retrieval_status,
            calibrated_retrieval_reason=retrieval_reason,
            semantic_status="NOT_OBSERVED",
            semantic_observation_source="NONE",
            source_recommendation_draft_hash=None,
            newly_semantic_eligible=False,
        )

    newly_eligible = (
        run.retrieval.status == "MISMATCH"
        and run.recommendation.status == "NOT_RUN"
        and recommendation_draft is None
        and not semantic_provider_failed
    )
    if semantic_observation_source is None:
        semantic_observation_source = (
            "ORIGINAL_RUN"
            if recommendation_draft is not None
            or run.recommendation.status == "RUN_FAILED"
            else "NONE"
        )
    if semantic_observation_source not in SEMANTIC_OBSERVATION_SOURCES:
        raise ValueError("semantic observation source is unsupported")
    if semantic_observation_source == "SUPPLEMENTAL_CALIBRATION" and (
        run.retrieval.status != "MISMATCH"
        or run.recommendation.status != "NOT_RUN"
    ):
        raise ValueError("supplemental Semantic is only valid after strict short-circuit")
    if recommendation_draft is None:
        semantic_status = (
            "RUN_FAILED"
            if run.recommendation.status == "RUN_FAILED" or semantic_provider_failed
            else "NOT_OBSERVED"
        )
        if semantic_provider_failed and semantic_observation_source == "NONE":
            raise ValueError("provider failure requires an attempt source")
        recommendation_hash = None
    else:
        if semantic_observation_source == "ORIGINAL_RUN" and (
            run.source_recommendation_draft_hash != recommendation_draft.draft_hash
        ):
            raise ValueError("calibration recommendation does not match the source run")
        if semantic_observation_source == "NONE":
            raise ValueError("scored Semantic recommendation requires a source")
        recommendation_hash = recommendation_draft.draft_hash
        actual = recommendation_outcome_from_draft(
            recommendation_draft,
            candidate_set,
        )
        if actual in oracle.recommendation.acceptable_outcomes:
            semantic_status = "PREFERRED_MATCH"
        elif (
            actual.action in SAFE_NON_TARGETING_ACTIONS
            and actual.target_node_id is None
            and actual.relation is None
        ):
            semantic_status = "SAFE_ALTERNATIVE"
        else:
            semantic_status = "UNSAFE_MISMATCH"

    return CalibrationObservationResult.create(
        observation_ref=observation_ref,
        source_run_hash=run.run_hash,
        source_policy_hash=policy.policy_hash,
        strict_full_path_status=run.full_path_status,
        strict_retrieval_status=run.retrieval.status,
        calibrated_retrieval_status=calibrated_retrieval_status,
        calibrated_retrieval_reason=retrieval_reason,
        semantic_status=semantic_status,
        semantic_observation_source=(
            "NONE" if semantic_status == "NOT_OBSERVED" else semantic_observation_source
        ),
        source_recommendation_draft_hash=recommendation_hash,
        newly_semantic_eligible=newly_eligible,
    )


def _score_retrieval(
    candidate_set: CandidateSet,
    oracle: CapabilityOracle,
    policy: ScenarioCalibrationPolicy,
) -> tuple[bool, str]:
    if policy.retrieval_mode == "TARGET_HIT":
        matched = retrieval_matches_oracle(candidate_set, oracle.retrieval)
        return matched, (
            "CALIBRATION_TARGET_HIT"
            if matched
            else "CALIBRATION_RETRIEVAL_MISMATCH"
        )
    if policy.retrieval_mode == "BOUNDED_EVIDENCE":
        matched = candidate_set.status == "CANDIDATES_READY" and bool(
            candidate_set.candidates
        )
        return matched, (
            "CALIBRATION_BOUNDED_EVIDENCE_READY"
            if matched
            else "CALIBRATION_RETRIEVAL_MISMATCH"
        )
    matched = candidate_set.status in {"NO_CANDIDATES", "INSUFFICIENT_SIGNAL"} and not (
        candidate_set.candidates
    )
    return matched, (
        "CALIBRATION_EMPTY_RESULT"
        if matched
        else "CALIBRATION_RETRIEVAL_MISMATCH"
    )


@dataclass(frozen=True, slots=True)
class CalibrationComparisonReport:
    schema_version: str
    policy_version: str
    quality_tier: str
    evaluation_role: str
    gate_eligible: bool
    gold_eligible: bool
    observation_count: int
    policy_count: int
    strict_full_path_counts: Mapping[str, int]
    strict_retrieval_counts: Mapping[str, int]
    calibrated_retrieval_counts: Mapping[str, int]
    calibrated_retrieval_match_kinds: Mapping[str, int]
    semantic_counts: Mapping[str, int]
    semantic_source_counts: Mapping[str, int]
    newly_semantic_eligible_count: int
    full_path_reassessment_status: str
    report_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_REPORT_SCHEMA_VERSION:
            raise ValueError("calibration report schema version is unsupported")
        if self.policy_version != CALIBRATION_POLICY_VERSION:
            raise ValueError("calibration report policy version is unsupported")
        if (
            self.quality_tier != "SILVER"
            or self.evaluation_role != "CALIBRATION_ONLY"
            or self.gate_eligible is not False
            or self.gold_eligible is not False
        ):
            raise ValueError("calibration report trust boundary is invalid")
        for field_name in ("observation_count", "policy_count", "newly_semantic_eligible_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.policy_count > self.observation_count:
            raise ValueError("calibration policy count exceeds observations")
        strict_full_path = _count_map(
            self.strict_full_path_counts,
            _FULL_PATH_STATUSES,
            "strict_full_path_counts",
        )
        strict_retrieval = _count_map(
            self.strict_retrieval_counts,
            CALIBRATED_RETRIEVAL_STATUSES,
            "strict_retrieval_counts",
        )
        calibrated_retrieval = _count_map(
            self.calibrated_retrieval_counts,
            CALIBRATED_RETRIEVAL_STATUSES,
            "calibrated_retrieval_counts",
        )
        match_kinds = _count_map(
            self.calibrated_retrieval_match_kinds,
            _MATCH_REASONS,
            "calibrated_retrieval_match_kinds",
        )
        semantic = _count_map(
            self.semantic_counts,
            SEMANTIC_CALIBRATION_STATUSES,
            "semantic_counts",
        )
        semantic_sources = _count_map(
            self.semantic_source_counts,
            SEMANTIC_OBSERVATION_SOURCES,
            "semantic_source_counts",
        )
        if any(
            sum(counts.values()) != self.observation_count
            for counts in (
                strict_full_path,
                strict_retrieval,
                calibrated_retrieval,
                semantic,
                semantic_sources,
            )
        ):
            raise ValueError("calibration report denominators do not reconcile")
        if sum(match_kinds.values()) != calibrated_retrieval["MATCH"]:
            raise ValueError("calibrated retrieval match kinds do not reconcile")
        if self.newly_semantic_eligible_count > semantic["NOT_OBSERVED"]:
            raise ValueError("newly eligible count exceeds unobserved Semantic units")
        expected_coverage = (
            "INCOMPLETE_SEMANTIC_COVERAGE"
            if self.newly_semantic_eligible_count
            else "COMPLETE"
        )
        if self.full_path_reassessment_status != expected_coverage:
            raise ValueError("full-path reassessment status is inconsistent")
        _validate_digest(self.report_hash, "report_hash")
        if canonical_digest(self._hash_payload()) != self.report_hash:
            raise ValueError("calibration report hash is invalid")
        for field_name in (
            "strict_full_path_counts",
            "strict_retrieval_counts",
            "calibrated_retrieval_counts",
            "calibrated_retrieval_match_kinds",
            "semantic_counts",
            "semantic_source_counts",
        ):
            object.__setattr__(self, field_name, freeze_json(getattr(self, field_name)))

    @classmethod
    def from_dict(cls, payload: Any) -> "CalibrationComparisonReport":
        if not isinstance(payload, dict) or set(payload) != _REPORT_KEYS:
            raise ValueError("calibration report must use exact fields")
        return cls(**payload)

    def _hash_payload(self) -> dict[str, Any]:
        return {
            key: thaw_json(getattr(self, key))
            for key in sorted(_REPORT_KEYS - {"report_hash"})
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "report_hash": self.report_hash}


def build_calibration_comparison_report(
    observations: tuple[CalibrationObservationResult, ...],
) -> CalibrationComparisonReport:
    if (
        not isinstance(observations, tuple)
        or not observations
        or any(not isinstance(item, CalibrationObservationResult) for item in observations)
    ):
        raise ValueError("calibration observations must be a non-empty tuple")
    if len({item.result_hash for item in observations}) != len(observations):
        raise ValueError("calibration observations must be unique")

    def counts(values: list[str], keys: set[str]) -> dict[str, int]:
        return {key: values.count(key) for key in sorted(keys)}

    strict_full = [item.strict_full_path_status for item in observations]
    strict_retrieval = [item.strict_retrieval_status for item in observations]
    calibrated_retrieval = [item.calibrated_retrieval_status for item in observations]
    semantic = [item.semantic_status for item in observations]
    semantic_sources = [item.semantic_observation_source for item in observations]
    match_reasons = [
        item.calibrated_retrieval_reason
        for item in observations
        if item.calibrated_retrieval_status == "MATCH"
    ]
    values = {
        "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
        "policy_version": CALIBRATION_POLICY_VERSION,
        "quality_tier": "SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gate_eligible": False,
        "gold_eligible": False,
        "observation_count": len(observations),
        "policy_count": len({item.source_policy_hash for item in observations}),
        "strict_full_path_counts": counts(strict_full, _FULL_PATH_STATUSES),
        "strict_retrieval_counts": counts(
            strict_retrieval,
            CALIBRATED_RETRIEVAL_STATUSES,
        ),
        "calibrated_retrieval_counts": counts(
            calibrated_retrieval,
            CALIBRATED_RETRIEVAL_STATUSES,
        ),
        "calibrated_retrieval_match_kinds": counts(match_reasons, _MATCH_REASONS),
        "semantic_counts": counts(semantic, SEMANTIC_CALIBRATION_STATUSES),
        "semantic_source_counts": counts(
            semantic_sources,
            SEMANTIC_OBSERVATION_SOURCES,
        ),
        "newly_semantic_eligible_count": sum(
            item.newly_semantic_eligible for item in observations
        ),
        "full_path_reassessment_status": (
            "INCOMPLETE_SEMANTIC_COVERAGE"
            if any(item.newly_semantic_eligible for item in observations)
            else "COMPLETE"
        ),
    }
    return CalibrationComparisonReport(**values, report_hash=canonical_digest(values))


__all__ = [
    "CALIBRATION_OBSERVATION_SCHEMA_VERSION",
    "CALIBRATION_POLICY_SCHEMA_VERSION",
    "CALIBRATION_POLICY_VERSION",
    "CALIBRATION_REPORT_SCHEMA_VERSION",
    "SEMANTIC_SAFE_ACTION_POLICY",
    "CalibrationComparisonReport",
    "CalibrationObservationResult",
    "ScenarioCalibrationPolicy",
    "build_calibration_comparison_report",
    "score_calibration_observation",
]
