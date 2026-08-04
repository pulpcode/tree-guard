"""Deterministic admission report for read-only, human-in-the-loop Shadow.

This contract is independent from the strict M4.5 gate and the non-gating M4.6
Silver calibration report.  It consumes only trusted aggregate counts and never
model text, tree identities, requests, or Oracle contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from treeguard.scenario_calibration_validation import SEMANTIC_SAFE_ACTION_POLICY
from treeguard.scenario_capability_validation import (
    PUBLIC_HARD_FAILURE_CODES,
    ScenarioCapabilityError,
)
from treeguard.scenario_repeatability_validation import ContractComplianceMetrics


ASSISTED_SHADOW_REPORT_SCHEMA_VERSION = "scenario-assisted-shadow-report.v1"
ASSISTED_SHADOW_POLICY_VERSION = "treeguard.m5-assisted-shadow-admission.v1"
ASSISTED_SHADOW_OPERATION_MODE = "READ_ONLY_HUMAN_IN_LOOP"

ASSISTED_SHADOW_ROUND_COUNT = 3
ASSISTED_SHADOW_SCENARIO_COUNT = 24
ASSISTED_SHADOW_PROCEED_COUNT = 18
ASSISTED_SHADOW_CLARIFY_COUNT = 6
ASSISTED_SHADOW_OBSERVATION_COUNT = 72
ASSISTED_SHADOW_MAX_SEMANTIC_COUNT = 54
ASSISTED_SHADOW_MINIMUM_ROUND_SAFE_COUNT = 18
ASSISTED_SHADOW_MINIMUM_STABLE_SAFE_COUNT = 18
ASSISTED_SHADOW_MINIMUM_ROUND_PREFERRED_COUNT = 6
ASSISTED_SHADOW_MINIMUM_STABLE_PREFERRED_COUNT = 6
ASSISTED_SHADOW_CONTRACT_PERCENT = 98

ORACLE_REVIEW_AUTHORITIES = {
    "CODEX_ASSISTED",
    "HUMAN_AUTHORIZED",
    "NOT_REVIEWED",
}
SAFE_REVIEW_AUTHORITIES = ORACLE_REVIEW_AUTHORITIES | {"NOT_APPLICABLE"}
ASSISTED_SHADOW_QUALIFICATION_CODES = {
    "ASSISTED_FORMAL_SCENARIO_REVIEW_INCOMPLETE",
    "ASSISTED_ORACLE_NOT_HUMAN_REVIEWED",
    "ASSISTED_POLICY_NOT_FROZEN_BEFORE_EXECUTION",
    "ASSISTED_REQUEST_SET_PREVIOUSLY_EXPOSED",
    "ASSISTED_RUNTIME_CONFIGURATION_NOT_FROZEN",
}
ASSISTED_SHADOW_FAILURE_CODES = {
    "ASSISTED_INTENT_CONTRACT_BELOW_MINIMUM",
    "ASSISTED_RETRIEVAL_NOT_PERFECT",
    "ASSISTED_ROUND_PREFERRED_PATH_BELOW_MINIMUM",
    "ASSISTED_ROUND_SAFE_PATH_BELOW_MINIMUM",
    "ASSISTED_SAFE_ALTERNATIVE_BLOCKING_FINDING_PRESENT",
    "ASSISTED_SAFE_ALTERNATIVE_REVIEW_INCOMPLETE",
    "ASSISTED_SEMANTIC_CONTRACT_BELOW_MINIMUM",
    "ASSISTED_STABLE_SAFE_PATH_BELOW_MINIMUM",
    "ASSISTED_STABLE_PREFERRED_PATH_BELOW_MINIMUM",
    "ASSISTED_STAGE_SHORT_CIRCUIT_VIOLATION",
    "ASSISTED_UNSAFE_MISMATCH_PRESENT",
}

_REPORT_KEYS = {
    "schema_version",
    "policy_version",
    "operation_mode",
    "semantic_safe_action_policy",
    "semantic_approval",
    "gold_eligible",
    "patch_eligible",
    "automatic_action_enabled",
    "human_confirmation_required",
    "evidence",
    "round_count",
    "selected_scenario_count",
    "proceed_route_count",
    "clarify_route_count",
    "rounds",
    "stable_safe_full_path_count",
    "stable_preferred_full_path_count",
    "executed_retrieval_count",
    "retrieval_match_count",
    "semantic_attempted_count",
    "intent_contract",
    "semantic_contract",
    "clarification_match_count",
    "semantic_outcomes",
    "safe_alternative_review",
    "hard_failure_codes",
    "qualification_codes",
    "failure_codes",
    "decision",
}


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _ordered_codes(
    value: Any,
    *,
    allowed: set[str],
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if value != tuple(sorted(set(value))) or any(code not in allowed for code in value):
        raise ValueError(f"{field_name} must contain ordered allowed codes")
    return value


@dataclass(frozen=True, slots=True)
class AssistedShadowEvidenceQualification:
    policy_frozen_before_execution: bool
    requests_unseen_at_first_execution: bool
    oracle_review_authority: str
    reviewed_scenario_count: int
    runtime_configuration_frozen: bool

    def __post_init__(self) -> None:
        for field_name in (
            "policy_frozen_before_execution",
            "requests_unseen_at_first_execution",
            "runtime_configuration_frozen",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")
        if self.oracle_review_authority not in ORACLE_REVIEW_AUTHORITIES:
            raise ValueError("oracle review authority is unsupported")
        _non_negative_int(self.reviewed_scenario_count, "reviewed_scenario_count")
        if self.reviewed_scenario_count > ASSISTED_SHADOW_SCENARIO_COUNT:
            raise ValueError("reviewed scenarios exceed the formal execution set")

    @classmethod
    def from_dict(cls, payload: Any) -> "AssistedShadowEvidenceQualification":
        keys = {
            "policy_frozen_before_execution",
            "requests_unseen_at_first_execution",
            "oracle_review_authority",
            "reviewed_scenario_count",
            "runtime_configuration_frozen",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("evidence qualification must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_frozen_before_execution": self.policy_frozen_before_execution,
            "requests_unseen_at_first_execution": self.requests_unseen_at_first_execution,
            "oracle_review_authority": self.oracle_review_authority,
            "reviewed_scenario_count": self.reviewed_scenario_count,
            "runtime_configuration_frozen": self.runtime_configuration_frozen,
        }


@dataclass(frozen=True, slots=True)
class AssistedShadowRoundMetrics:
    round_index: int
    safe_full_path_count: int
    preferred_full_path_count: int

    def __post_init__(self) -> None:
        _non_negative_int(self.round_index, "round_index")
        _non_negative_int(self.safe_full_path_count, "safe_full_path_count")
        _non_negative_int(self.preferred_full_path_count, "preferred_full_path_count")
        if not 1 <= self.round_index <= ASSISTED_SHADOW_ROUND_COUNT:
            raise ValueError("round index is outside the assisted Shadow protocol")
        if self.safe_full_path_count > ASSISTED_SHADOW_SCENARIO_COUNT:
            raise ValueError("safe full-path count exceeds the round denominator")
        if self.preferred_full_path_count > ASSISTED_SHADOW_PROCEED_COUNT:
            raise ValueError("preferred full-path count exceeds the PROCEED denominator")
        if self.preferred_full_path_count > self.safe_full_path_count:
            raise ValueError("preferred full-path count exceeds the safe count")

    @classmethod
    def from_dict(cls, payload: Any) -> "AssistedShadowRoundMetrics":
        if not isinstance(payload, dict) or set(payload) != {
            "round_index",
            "safe_full_path_count",
            "preferred_full_path_count",
        }:
            raise ValueError("assisted Shadow round must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "round_index": self.round_index,
            "safe_full_path_count": self.safe_full_path_count,
            "preferred_full_path_count": self.preferred_full_path_count,
        }


@dataclass(frozen=True, slots=True)
class SemanticOutcomeMetrics:
    preferred_match_count: int
    safe_alternative_count: int
    unsafe_mismatch_count: int
    run_failed_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "preferred_match_count",
            "safe_alternative_count",
            "unsafe_mismatch_count",
            "run_failed_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name)

    @classmethod
    def from_dict(cls, payload: Any) -> "SemanticOutcomeMetrics":
        keys = {
            "preferred_match_count",
            "safe_alternative_count",
            "unsafe_mismatch_count",
            "run_failed_count",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("semantic outcomes must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "preferred_match_count": self.preferred_match_count,
            "safe_alternative_count": self.safe_alternative_count,
            "unsafe_mismatch_count": self.unsafe_mismatch_count,
            "run_failed_count": self.run_failed_count,
        }


@dataclass(frozen=True, slots=True)
class SafeAlternativeReviewMetrics:
    distinct_output_count: int
    reviewed_output_count: int
    blocking_finding_count: int
    reviewer_authority: str

    def __post_init__(self) -> None:
        for field_name in (
            "distinct_output_count",
            "reviewed_output_count",
            "blocking_finding_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name)
        if self.reviewed_output_count > self.distinct_output_count:
            raise ValueError("reviewed safe alternatives exceed distinct outputs")
        if self.blocking_finding_count > self.reviewed_output_count:
            raise ValueError("blocking findings exceed reviewed safe alternatives")
        if self.reviewer_authority not in SAFE_REVIEW_AUTHORITIES:
            raise ValueError("safe-alternative reviewer authority is unsupported")
        if self.distinct_output_count == 0:
            if (
                self.reviewed_output_count != 0
                or self.blocking_finding_count != 0
                or self.reviewer_authority != "NOT_APPLICABLE"
            ):
                raise ValueError("empty safe-alternative review must be not applicable")
        elif self.reviewer_authority == "NOT_APPLICABLE":
            raise ValueError("non-empty safe alternatives require a reviewer status")

    @classmethod
    def from_dict(cls, payload: Any) -> "SafeAlternativeReviewMetrics":
        keys = {
            "distinct_output_count",
            "reviewed_output_count",
            "blocking_finding_count",
            "reviewer_authority",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("safe-alternative review must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "distinct_output_count": self.distinct_output_count,
            "reviewed_output_count": self.reviewed_output_count,
            "blocking_finding_count": self.blocking_finding_count,
            "reviewer_authority": self.reviewer_authority,
        }


@dataclass(frozen=True, slots=True)
class AssistedShadowAdmissionReport:
    evidence: AssistedShadowEvidenceQualification
    rounds: tuple[AssistedShadowRoundMetrics, ...]
    stable_safe_full_path_count: int
    stable_preferred_full_path_count: int
    executed_retrieval_count: int
    retrieval_match_count: int
    semantic_attempted_count: int
    intent_contract: ContractComplianceMetrics
    semantic_contract: ContractComplianceMetrics
    clarification_match_count: int
    semantic_outcomes: SemanticOutcomeMetrics
    safe_alternative_review: SafeAlternativeReviewMetrics
    hard_failure_codes: tuple[str, ...]
    qualification_codes: tuple[str, ...]
    failure_codes: tuple[str, ...]
    decision: str

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, AssistedShadowEvidenceQualification):
            raise ValueError("assisted Shadow report requires typed evidence")
        if (
            not isinstance(self.rounds, tuple)
            or len(self.rounds) != ASSISTED_SHADOW_ROUND_COUNT
            or any(not isinstance(item, AssistedShadowRoundMetrics) for item in self.rounds)
            or tuple(item.round_index for item in self.rounds) != (1, 2, 3)
        ):
            raise ValueError("assisted Shadow rounds must be the ordered fixed protocol")
        for field_name in (
            "stable_safe_full_path_count",
            "stable_preferred_full_path_count",
            "executed_retrieval_count",
            "retrieval_match_count",
            "semantic_attempted_count",
            "clarification_match_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name)
        if self.stable_safe_full_path_count > min(
            item.safe_full_path_count for item in self.rounds
        ):
            raise ValueError("stable safe count exceeds a round safe count")
        if self.stable_preferred_full_path_count > min(
            item.preferred_full_path_count for item in self.rounds
        ):
            raise ValueError("stable preferred count exceeds a round preferred count")
        if self.stable_preferred_full_path_count > ASSISTED_SHADOW_PROCEED_COUNT:
            raise ValueError("stable preferred count exceeds the PROCEED denominator")
        if self.executed_retrieval_count > ASSISTED_SHADOW_MAX_SEMANTIC_COUNT:
            raise ValueError("executed retrieval count exceeds the fixed protocol")
        if self.retrieval_match_count > self.executed_retrieval_count:
            raise ValueError("retrieval matches exceed executed retrieval")
        if self.semantic_attempted_count > ASSISTED_SHADOW_MAX_SEMANTIC_COUNT:
            raise ValueError("Semantic attempts exceed the fixed protocol")
        if self.clarification_match_count > (
            ASSISTED_SHADOW_CLARIFY_COUNT * ASSISTED_SHADOW_ROUND_COUNT
        ):
            raise ValueError("clarification matches exceed the fixed denominator")
        if not isinstance(self.intent_contract, ContractComplianceMetrics) or not isinstance(
            self.semantic_contract, ContractComplianceMetrics
        ):
            raise ValueError("assisted Shadow report requires typed contract metrics")
        if self.intent_contract.unit_count != ASSISTED_SHADOW_OBSERVATION_COUNT:
            raise ValueError("Intent contract denominator is not the fixed protocol")
        if self.semantic_contract.unit_count != self.retrieval_match_count:
            raise ValueError("Semantic contract denominator must equal retrieval matches")
        if self.semantic_attempted_count < self.semantic_contract.unit_count:
            raise ValueError("Semantic outcomes cannot exceed attempted observations")
        if not isinstance(self.semantic_outcomes, SemanticOutcomeMetrics):
            raise ValueError("assisted Shadow report requires typed Semantic outcomes")
        outcome_total = sum(self.semantic_outcomes.to_dict().values())
        valid_outcomes = outcome_total - self.semantic_outcomes.run_failed_count
        if outcome_total != self.semantic_contract.unit_count:
            raise ValueError("Semantic outcomes do not reconcile with the denominator")
        if valid_outcomes != self.semantic_contract.final_valid_count:
            raise ValueError("Semantic valid outcomes do not reconcile with contract metrics")
        if sum(item.preferred_full_path_count for item in self.rounds) != (
            self.semantic_outcomes.preferred_match_count
        ):
            raise ValueError("preferred full-path counts do not reconcile")
        safe_total = sum(item.safe_full_path_count for item in self.rounds)
        if safe_total != (
            self.clarification_match_count
            + self.semantic_outcomes.preferred_match_count
            + self.semantic_outcomes.safe_alternative_count
        ):
            raise ValueError("safe full-path counts do not reconcile")
        if not isinstance(self.safe_alternative_review, SafeAlternativeReviewMetrics):
            raise ValueError("assisted Shadow report requires typed safe review metrics")
        if (
            self.safe_alternative_review.distinct_output_count
            > self.semantic_outcomes.safe_alternative_count
        ):
            raise ValueError("distinct safe outputs exceed safe observations")
        _ordered_codes(
            self.hard_failure_codes,
            allowed=PUBLIC_HARD_FAILURE_CODES,
            field_name="hard_failure_codes",
        )
        _ordered_codes(
            self.qualification_codes,
            allowed=ASSISTED_SHADOW_QUALIFICATION_CODES,
            field_name="qualification_codes",
        )
        _ordered_codes(
            self.failure_codes,
            allowed=ASSISTED_SHADOW_FAILURE_CODES,
            field_name="failure_codes",
        )
        expected_qualification = _qualification_codes(self.evidence)
        if self.qualification_codes != expected_qualification:
            raise ValueError("assisted Shadow qualification codes are inconsistent")
        expected_failures = _failure_codes(
            rounds=self.rounds,
            stable_safe_full_path_count=self.stable_safe_full_path_count,
            stable_preferred_full_path_count=self.stable_preferred_full_path_count,
            executed_retrieval_count=self.executed_retrieval_count,
            retrieval_match_count=self.retrieval_match_count,
            semantic_attempted_count=self.semantic_attempted_count,
            intent_contract=self.intent_contract,
            semantic_contract=self.semantic_contract,
            semantic_outcomes=self.semantic_outcomes,
            safe_alternative_review=self.safe_alternative_review,
        )
        if self.failure_codes != expected_failures:
            raise ValueError("assisted Shadow failure codes are inconsistent")
        expected_decision = _decision(
            self.hard_failure_codes,
            self.qualification_codes,
            self.failure_codes,
        )
        if self.decision != expected_decision:
            raise ValueError("assisted Shadow decision is inconsistent")

    @classmethod
    def from_dict(cls, payload: Any) -> "AssistedShadowAdmissionReport":
        if not isinstance(payload, dict) or set(payload) != _REPORT_KEYS:
            raise ScenarioCapabilityError(
                "ASSISTED_SHADOW_REPORT_FIELDS_INVALID",
                "assisted Shadow report must use exact fields",
            )
        if (
            payload["schema_version"] != ASSISTED_SHADOW_REPORT_SCHEMA_VERSION
            or payload["policy_version"] != ASSISTED_SHADOW_POLICY_VERSION
        ):
            raise ScenarioCapabilityError(
                "ASSISTED_SHADOW_REPORT_VERSION_INVALID",
                "assisted Shadow report version is unsupported",
            )
        if (
            payload["operation_mode"] != ASSISTED_SHADOW_OPERATION_MODE
            or payload["semantic_safe_action_policy"] != SEMANTIC_SAFE_ACTION_POLICY
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
            or payload["automatic_action_enabled"] is not False
            or payload["human_confirmation_required"] is not True
            or payload["round_count"] != ASSISTED_SHADOW_ROUND_COUNT
            or payload["selected_scenario_count"] != ASSISTED_SHADOW_SCENARIO_COUNT
            or payload["proceed_route_count"] != ASSISTED_SHADOW_PROCEED_COUNT
            or payload["clarify_route_count"] != ASSISTED_SHADOW_CLARIFY_COUNT
            or not isinstance(payload["rounds"], list)
            or not isinstance(payload["hard_failure_codes"], list)
            or not isinstance(payload["qualification_codes"], list)
            or not isinstance(payload["failure_codes"], list)
        ):
            raise ScenarioCapabilityError(
                "ASSISTED_SHADOW_REPORT_POLICY_INVALID",
                "assisted Shadow report violates fixed policy",
            )
        try:
            return cls(
                evidence=AssistedShadowEvidenceQualification.from_dict(payload["evidence"]),
                rounds=tuple(
                    AssistedShadowRoundMetrics.from_dict(item)
                    for item in payload["rounds"]
                ),
                stable_safe_full_path_count=payload["stable_safe_full_path_count"],
                stable_preferred_full_path_count=payload[
                    "stable_preferred_full_path_count"
                ],
                executed_retrieval_count=payload["executed_retrieval_count"],
                retrieval_match_count=payload["retrieval_match_count"],
                semantic_attempted_count=payload["semantic_attempted_count"],
                intent_contract=ContractComplianceMetrics.from_dict(payload["intent_contract"]),
                semantic_contract=ContractComplianceMetrics.from_dict(payload["semantic_contract"]),
                clarification_match_count=payload["clarification_match_count"],
                semantic_outcomes=SemanticOutcomeMetrics.from_dict(payload["semantic_outcomes"]),
                safe_alternative_review=SafeAlternativeReviewMetrics.from_dict(
                    payload["safe_alternative_review"]
                ),
                hard_failure_codes=tuple(payload["hard_failure_codes"]),
                qualification_codes=tuple(payload["qualification_codes"]),
                failure_codes=tuple(payload["failure_codes"]),
                decision=payload["decision"],
            )
        except (TypeError, ValueError):
            raise ScenarioCapabilityError(
                "ASSISTED_SHADOW_REPORT_VALUE_INVALID",
                "assisted Shadow report failed local validation",
            ) from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ASSISTED_SHADOW_REPORT_SCHEMA_VERSION,
            "policy_version": ASSISTED_SHADOW_POLICY_VERSION,
            "operation_mode": ASSISTED_SHADOW_OPERATION_MODE,
            "semantic_safe_action_policy": SEMANTIC_SAFE_ACTION_POLICY,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "automatic_action_enabled": False,
            "human_confirmation_required": True,
            "evidence": self.evidence.to_dict(),
            "round_count": ASSISTED_SHADOW_ROUND_COUNT,
            "selected_scenario_count": ASSISTED_SHADOW_SCENARIO_COUNT,
            "proceed_route_count": ASSISTED_SHADOW_PROCEED_COUNT,
            "clarify_route_count": ASSISTED_SHADOW_CLARIFY_COUNT,
            "rounds": [item.to_dict() for item in self.rounds],
            "stable_safe_full_path_count": self.stable_safe_full_path_count,
            "stable_preferred_full_path_count": self.stable_preferred_full_path_count,
            "executed_retrieval_count": self.executed_retrieval_count,
            "retrieval_match_count": self.retrieval_match_count,
            "semantic_attempted_count": self.semantic_attempted_count,
            "intent_contract": self.intent_contract.to_dict(),
            "semantic_contract": self.semantic_contract.to_dict(),
            "clarification_match_count": self.clarification_match_count,
            "semantic_outcomes": self.semantic_outcomes.to_dict(),
            "safe_alternative_review": self.safe_alternative_review.to_dict(),
            "hard_failure_codes": list(self.hard_failure_codes),
            "qualification_codes": list(self.qualification_codes),
            "failure_codes": list(self.failure_codes),
            "decision": self.decision,
        }


def _contract_rate_passes(metrics: ContractComplianceMetrics) -> bool:
    return (
        metrics.unit_count > 0
        and metrics.final_valid_count * 100
        >= metrics.unit_count * ASSISTED_SHADOW_CONTRACT_PERCENT
    )


def _qualification_codes(
    evidence: AssistedShadowEvidenceQualification,
) -> tuple[str, ...]:
    codes: list[str] = []
    if not evidence.policy_frozen_before_execution:
        codes.append("ASSISTED_POLICY_NOT_FROZEN_BEFORE_EXECUTION")
    if not evidence.requests_unseen_at_first_execution:
        codes.append("ASSISTED_REQUEST_SET_PREVIOUSLY_EXPOSED")
    if evidence.oracle_review_authority != "HUMAN_AUTHORIZED":
        codes.append("ASSISTED_ORACLE_NOT_HUMAN_REVIEWED")
    if evidence.reviewed_scenario_count != ASSISTED_SHADOW_SCENARIO_COUNT:
        codes.append("ASSISTED_FORMAL_SCENARIO_REVIEW_INCOMPLETE")
    if not evidence.runtime_configuration_frozen:
        codes.append("ASSISTED_RUNTIME_CONFIGURATION_NOT_FROZEN")
    return tuple(sorted(codes))


def _failure_codes(
    *,
    rounds: tuple[AssistedShadowRoundMetrics, ...],
    stable_safe_full_path_count: int,
    stable_preferred_full_path_count: int,
    executed_retrieval_count: int,
    retrieval_match_count: int,
    semantic_attempted_count: int,
    intent_contract: ContractComplianceMetrics,
    semantic_contract: ContractComplianceMetrics,
    semantic_outcomes: SemanticOutcomeMetrics,
    safe_alternative_review: SafeAlternativeReviewMetrics,
) -> tuple[str, ...]:
    codes: list[str] = []
    if any(
        item.safe_full_path_count < ASSISTED_SHADOW_MINIMUM_ROUND_SAFE_COUNT
        for item in rounds
    ):
        codes.append("ASSISTED_ROUND_SAFE_PATH_BELOW_MINIMUM")
    if stable_safe_full_path_count < ASSISTED_SHADOW_MINIMUM_STABLE_SAFE_COUNT:
        codes.append("ASSISTED_STABLE_SAFE_PATH_BELOW_MINIMUM")
    if any(
        item.preferred_full_path_count
        < ASSISTED_SHADOW_MINIMUM_ROUND_PREFERRED_COUNT
        for item in rounds
    ):
        codes.append("ASSISTED_ROUND_PREFERRED_PATH_BELOW_MINIMUM")
    if (
        stable_preferred_full_path_count
        < ASSISTED_SHADOW_MINIMUM_STABLE_PREFERRED_COUNT
    ):
        codes.append("ASSISTED_STABLE_PREFERRED_PATH_BELOW_MINIMUM")
    if not _contract_rate_passes(intent_contract):
        codes.append("ASSISTED_INTENT_CONTRACT_BELOW_MINIMUM")
    if not _contract_rate_passes(semantic_contract):
        codes.append("ASSISTED_SEMANTIC_CONTRACT_BELOW_MINIMUM")
    if executed_retrieval_count == 0 or retrieval_match_count != executed_retrieval_count:
        codes.append("ASSISTED_RETRIEVAL_NOT_PERFECT")
    if semantic_attempted_count != retrieval_match_count:
        codes.append("ASSISTED_STAGE_SHORT_CIRCUIT_VIOLATION")
    if semantic_outcomes.unsafe_mismatch_count:
        codes.append("ASSISTED_UNSAFE_MISMATCH_PRESENT")
    if safe_alternative_review.blocking_finding_count:
        codes.append("ASSISTED_SAFE_ALTERNATIVE_BLOCKING_FINDING_PRESENT")
    if semantic_outcomes.safe_alternative_count and (
        safe_alternative_review.reviewed_output_count
        != safe_alternative_review.distinct_output_count
        or safe_alternative_review.reviewer_authority != "HUMAN_AUTHORIZED"
    ):
        codes.append("ASSISTED_SAFE_ALTERNATIVE_REVIEW_INCOMPLETE")
    return tuple(sorted(codes))


def _decision(
    hard_failure_codes: tuple[str, ...],
    qualification_codes: tuple[str, ...],
    failure_codes: tuple[str, ...],
) -> str:
    if hard_failure_codes:
        return "NOT_READY"
    if qualification_codes:
        return "EVALUATION_PENDING"
    if failure_codes:
        return "NOT_READY"
    return "READY_FOR_ASSISTED_SHADOW"


def build_assisted_shadow_admission_report(
    evidence: AssistedShadowEvidenceQualification,
    rounds: tuple[AssistedShadowRoundMetrics, ...],
    *,
    stable_safe_full_path_count: int,
    stable_preferred_full_path_count: int,
    executed_retrieval_count: int,
    retrieval_match_count: int,
    semantic_attempted_count: int,
    intent_contract: ContractComplianceMetrics,
    semantic_contract: ContractComplianceMetrics,
    clarification_match_count: int,
    semantic_outcomes: SemanticOutcomeMetrics,
    safe_alternative_review: SafeAlternativeReviewMetrics,
    hard_failure_codes: tuple[str, ...],
) -> AssistedShadowAdmissionReport:
    """Build an aggregate-only assisted Shadow admission report."""

    try:
        qualification_codes = _qualification_codes(evidence)
        failure_codes = _failure_codes(
            rounds=rounds,
            stable_safe_full_path_count=stable_safe_full_path_count,
            stable_preferred_full_path_count=stable_preferred_full_path_count,
            executed_retrieval_count=executed_retrieval_count,
            retrieval_match_count=retrieval_match_count,
            semantic_attempted_count=semantic_attempted_count,
            intent_contract=intent_contract,
            semantic_contract=semantic_contract,
            semantic_outcomes=semantic_outcomes,
            safe_alternative_review=safe_alternative_review,
        )
        return AssistedShadowAdmissionReport(
            evidence=evidence,
            rounds=rounds,
            stable_safe_full_path_count=stable_safe_full_path_count,
            stable_preferred_full_path_count=stable_preferred_full_path_count,
            executed_retrieval_count=executed_retrieval_count,
            retrieval_match_count=retrieval_match_count,
            semantic_attempted_count=semantic_attempted_count,
            intent_contract=intent_contract,
            semantic_contract=semantic_contract,
            clarification_match_count=clarification_match_count,
            semantic_outcomes=semantic_outcomes,
            safe_alternative_review=safe_alternative_review,
            hard_failure_codes=hard_failure_codes,
            qualification_codes=qualification_codes,
            failure_codes=failure_codes,
            decision=_decision(hard_failure_codes, qualification_codes, failure_codes),
        )
    except (AttributeError, TypeError, ValueError):
        raise ScenarioCapabilityError(
            "ASSISTED_SHADOW_REPORT_INPUT_INVALID",
            "assisted Shadow report inputs are inconsistent",
        ) from None


__all__ = [
    "ASSISTED_SHADOW_POLICY_VERSION",
    "ASSISTED_SHADOW_REPORT_SCHEMA_VERSION",
    "AssistedShadowAdmissionReport",
    "AssistedShadowEvidenceQualification",
    "AssistedShadowRoundMetrics",
    "SafeAlternativeReviewMetrics",
    "SemanticOutcomeMetrics",
    "build_assisted_shadow_admission_report",
]
