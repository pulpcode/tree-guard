"""Aggregate-only M4.5 sealed repeatability validation.

The existing M4 v1 eight-scenario gate remains unchanged.  This module consumes
three source-bound rounds of existing ``ScenarioCapabilityRun`` objects and
publishes only fixed counts and gate codes for the 24-scenario sealed protocol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from treeguard.scenario_capability_validation import (
    PUBLIC_HARD_FAILURE_CODES,
    CapabilityStageAggregate,
    ScenarioCapabilityError,
    ScenarioCapabilityRun,
)


SEALED_REPEATABILITY_REPORT_SCHEMA_VERSION = "scenario-repeatability-report.v1"
SEALED_REPEATABILITY_POLICY_VERSION = "treeguard.m45-sealed-repeatability-gate.v1"

SEALED_ROUND_COUNT = 3
SEALED_SCENARIO_COUNT = 24
SEALED_PROCEED_COUNT = 18
SEALED_CLARIFY_COUNT = 6
SEALED_OBSERVATION_COUNT = SEALED_ROUND_COUNT * SEALED_SCENARIO_COUNT
SEALED_MINIMUM_ROUND_MATCHES = 18
SEALED_MINIMUM_STABLE_MATCHES = 18
SEALED_CONTRACT_PERCENT = 98
SEALED_MAX_CANDIDATES = 30
SEALED_REVIEW_MINUTES = 180

DECISIONS = {"GO_SHADOW", "NO_GO"}
_FIXED_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _code_tuple(value: Any, *, allowed: set[str] | None = None) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError("code collection must be a tuple")
    if value != tuple(sorted(set(value))):
        raise ValueError("codes must be unique and ordered")
    if any(not isinstance(code, str) or _FIXED_CODE.fullmatch(code) is None for code in value):
        raise ValueError("codes must use the fixed code shape")
    if allowed is not None and any(code not in allowed for code in value):
        raise ValueError("code is outside the allowed set")
    return value


@dataclass(frozen=True, slots=True)
class SealedPreparationMetrics:
    candidate_count: int
    reviewed_count: int
    execution_count: int
    accepted_count: int
    revised_accepted_count: int
    rejected_count: int
    blocking_finding_count: int
    review_minutes: int

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_count",
            "reviewed_count",
            "execution_count",
            "accepted_count",
            "revised_accepted_count",
            "rejected_count",
            "blocking_finding_count",
            "review_minutes",
        ):
            _non_negative_int(getattr(self, field_name), field_name)
        if self.reviewed_count > self.candidate_count:
            raise ValueError("reviewed candidates exceed prepared candidates")
        if self.accepted_count + self.revised_accepted_count + self.rejected_count != self.reviewed_count:
            raise ValueError("review outcomes do not reconcile")
        if self.execution_count > self.accepted_count + self.revised_accepted_count:
            raise ValueError("execution count exceeds accepted candidates")

    @classmethod
    def from_dict(cls, payload: Any) -> "SealedPreparationMetrics":
        keys = {
            "candidate_count",
            "reviewed_count",
            "execution_count",
            "accepted_count",
            "revised_accepted_count",
            "rejected_count",
            "blocking_finding_count",
            "review_minutes",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("sealed preparation metrics must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "candidate_count": self.candidate_count,
            "reviewed_count": self.reviewed_count,
            "execution_count": self.execution_count,
            "accepted_count": self.accepted_count,
            "revised_accepted_count": self.revised_accepted_count,
            "rejected_count": self.rejected_count,
            "blocking_finding_count": self.blocking_finding_count,
            "review_minutes": self.review_minutes,
        }


@dataclass(frozen=True, slots=True)
class ContractComplianceMetrics:
    unit_count: int
    first_pass_valid_count: int
    final_valid_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "unit_count",
            "first_pass_valid_count",
            "final_valid_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name)
        if self.first_pass_valid_count > self.final_valid_count or self.final_valid_count > self.unit_count:
            raise ValueError("contract compliance counts do not reconcile")

    @classmethod
    def from_dict(cls, payload: Any) -> "ContractComplianceMetrics":
        keys = {"unit_count", "first_pass_valid_count", "final_valid_count"}
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("contract compliance metrics must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "unit_count": self.unit_count,
            "first_pass_valid_count": self.first_pass_valid_count,
            "final_valid_count": self.final_valid_count,
        }


@dataclass(frozen=True, slots=True)
class ClarificationConfusionMatrix:
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    true_negative_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "true_positive_count",
            "false_positive_count",
            "false_negative_count",
            "true_negative_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name)
        if self.true_positive_count + self.false_negative_count != SEALED_CLARIFY_COUNT * SEALED_ROUND_COUNT:
            raise ValueError("clarification positive denominator is invalid")
        if self.false_positive_count + self.true_negative_count != SEALED_PROCEED_COUNT * SEALED_ROUND_COUNT:
            raise ValueError("clarification negative denominator is invalid")

    @classmethod
    def from_dict(cls, payload: Any) -> "ClarificationConfusionMatrix":
        keys = {
            "true_positive_count",
            "false_positive_count",
            "false_negative_count",
            "true_negative_count",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("clarification metrics must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "true_positive_count": self.true_positive_count,
            "false_positive_count": self.false_positive_count,
            "false_negative_count": self.false_negative_count,
            "true_negative_count": self.true_negative_count,
        }


@dataclass(frozen=True, slots=True)
class SealedRoundAggregate:
    round_index: int
    proceed_route_count: int
    clarify_route_count: int
    full_path_match_count: int
    full_path_mismatch_count: int
    full_path_run_failed_count: int
    intent: CapabilityStageAggregate
    retrieval: CapabilityStageAggregate
    recommendation: CapabilityStageAggregate

    def __post_init__(self) -> None:
        if self.round_index not in (1, 2, 3):
            raise ValueError("sealed round index is invalid")
        for field_name in (
            "proceed_route_count",
            "clarify_route_count",
            "full_path_match_count",
            "full_path_mismatch_count",
            "full_path_run_failed_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name)
        if self.proceed_route_count + self.clarify_route_count != SEALED_SCENARIO_COUNT:
            raise ValueError("sealed round route counts do not reconcile")
        if self.full_path_match_count + self.full_path_mismatch_count + self.full_path_run_failed_count != SEALED_SCENARIO_COUNT:
            raise ValueError("sealed round full path counts do not reconcile")
        for aggregate in (self.intent, self.retrieval, self.recommendation):
            if not isinstance(aggregate, CapabilityStageAggregate):
                raise ValueError("sealed round stage aggregate is invalid")
            if aggregate.applicable_count > SEALED_SCENARIO_COUNT:
                raise ValueError("sealed round stage denominator is invalid")

    @classmethod
    def from_dict(cls, payload: Any) -> "SealedRoundAggregate":
        keys = {
            "round_index",
            "proceed_route_count",
            "clarify_route_count",
            "full_path_match_count",
            "full_path_mismatch_count",
            "full_path_run_failed_count",
            "intent",
            "retrieval",
            "recommendation",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("sealed round aggregate must use exact fields")
        return cls(
            round_index=payload["round_index"],
            proceed_route_count=payload["proceed_route_count"],
            clarify_route_count=payload["clarify_route_count"],
            full_path_match_count=payload["full_path_match_count"],
            full_path_mismatch_count=payload["full_path_mismatch_count"],
            full_path_run_failed_count=payload["full_path_run_failed_count"],
            intent=CapabilityStageAggregate.from_dict(payload["intent"]),
            retrieval=CapabilityStageAggregate.from_dict(payload["retrieval"]),
            recommendation=CapabilityStageAggregate.from_dict(payload["recommendation"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "proceed_route_count": self.proceed_route_count,
            "clarify_route_count": self.clarify_route_count,
            "full_path_match_count": self.full_path_match_count,
            "full_path_mismatch_count": self.full_path_mismatch_count,
            "full_path_run_failed_count": self.full_path_run_failed_count,
            "intent": self.intent.to_dict(),
            "retrieval": self.retrieval.to_dict(),
            "recommendation": self.recommendation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SealedRepeatabilityReport:
    preparation: SealedPreparationMetrics
    rounds: tuple[SealedRoundAggregate, ...]
    stable_full_path_match_count: int
    executed_retrieval_count: int
    retrieval_match_count: int
    intent_contract: ContractComplianceMetrics
    semantic_contract: ContractComplianceMetrics
    clarification: ClarificationConfusionMatrix
    unsafe_reuse_count: int
    hard_failure_codes: tuple[str, ...]
    failure_codes: tuple[str, ...]
    decision: str

    def __post_init__(self) -> None:
        if not isinstance(self.preparation, SealedPreparationMetrics):
            raise ValueError("sealed report preparation metrics are invalid")
        if (
            not isinstance(self.rounds, tuple)
            or len(self.rounds) != SEALED_ROUND_COUNT
            or any(not isinstance(item, SealedRoundAggregate) for item in self.rounds)
            or tuple(item.round_index for item in self.rounds) != (1, 2, 3)
        ):
            raise ValueError("sealed report rounds are invalid")
        for field_name in (
            "stable_full_path_match_count",
            "executed_retrieval_count",
            "retrieval_match_count",
            "unsafe_reuse_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name)
        if self.stable_full_path_match_count > SEALED_SCENARIO_COUNT:
            raise ValueError("stable match count exceeds scenario count")
        executed_retrieval = sum(
            item.retrieval.match_count + item.retrieval.mismatch_count + item.retrieval.run_failed_count
            for item in self.rounds
        )
        retrieval_matches = sum(item.retrieval.match_count for item in self.rounds)
        executed_semantic = sum(
            item.recommendation.match_count
            + item.recommendation.mismatch_count
            + item.recommendation.run_failed_count
            for item in self.rounds
        )
        if self.executed_retrieval_count != executed_retrieval or self.retrieval_match_count != retrieval_matches:
            raise ValueError("sealed report retrieval counts are inconsistent")
        if not isinstance(self.intent_contract, ContractComplianceMetrics) or not isinstance(self.semantic_contract, ContractComplianceMetrics):
            raise ValueError("sealed report contract metrics are invalid")
        if self.intent_contract.unit_count != SEALED_OBSERVATION_COUNT:
            raise ValueError("intent contract denominator must cover all observations")
        if self.semantic_contract.unit_count != executed_semantic:
            raise ValueError("semantic contract denominator must match executed recommendations")
        if not isinstance(self.clarification, ClarificationConfusionMatrix):
            raise ValueError("sealed report clarification metrics are invalid")
        _code_tuple(self.hard_failure_codes, allowed=PUBLIC_HARD_FAILURE_CODES)
        _code_tuple(self.failure_codes)
        expected_failures = _sealed_failure_codes(
            preparation=self.preparation,
            rounds=self.rounds,
            stable_full_path_match_count=self.stable_full_path_match_count,
            executed_retrieval_count=self.executed_retrieval_count,
            retrieval_match_count=self.retrieval_match_count,
            intent_contract=self.intent_contract,
            semantic_contract=self.semantic_contract,
            unsafe_reuse_count=self.unsafe_reuse_count,
        )
        if self.failure_codes != expected_failures:
            raise ValueError("sealed report failure codes are inconsistent")
        if self.decision not in DECISIONS:
            raise ValueError("sealed report decision is unsupported")
        expected_decision = "GO_SHADOW" if not self.hard_failure_codes and not self.failure_codes else "NO_GO"
        if self.decision != expected_decision:
            raise ValueError("sealed report decision is inconsistent")

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
    def from_dict(cls, payload: Any) -> "SealedRepeatabilityReport":
        keys = {
            "schema_version",
            "policy_version",
            "semantic_approval",
            "gold_eligible",
            "patch_eligible",
            "preparation",
            "round_count",
            "selected_scenario_count",
            "proceed_route_count",
            "clarify_route_count",
            "rounds",
            "stable_full_path_match_count",
            "executed_retrieval_count",
            "retrieval_match_count",
            "intent_contract",
            "semantic_contract",
            "clarification",
            "unsafe_reuse_count",
            "hard_failure_codes",
            "failure_codes",
            "decision",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ScenarioCapabilityError("SEALED_REPORT_FIELDS_INVALID", "sealed report must use exact fields")
        if payload["schema_version"] != SEALED_REPEATABILITY_REPORT_SCHEMA_VERSION or payload["policy_version"] != SEALED_REPEATABILITY_POLICY_VERSION:
            raise ScenarioCapabilityError("SEALED_REPORT_VERSION_INVALID", "sealed report version is unsupported")
        if (
            payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
            or payload["round_count"] != SEALED_ROUND_COUNT
            or payload["selected_scenario_count"] != SEALED_SCENARIO_COUNT
            or payload["proceed_route_count"] != SEALED_PROCEED_COUNT
            or payload["clarify_route_count"] != SEALED_CLARIFY_COUNT
            or not isinstance(payload["rounds"], list)
            or not isinstance(payload["hard_failure_codes"], list)
            or not isinstance(payload["failure_codes"], list)
        ):
            raise ScenarioCapabilityError("SEALED_REPORT_POLICY_INVALID", "sealed report violates fixed policy")
        try:
            return cls(
                preparation=SealedPreparationMetrics.from_dict(payload["preparation"]),
                rounds=tuple(SealedRoundAggregate.from_dict(item) for item in payload["rounds"]),
                stable_full_path_match_count=payload["stable_full_path_match_count"],
                executed_retrieval_count=payload["executed_retrieval_count"],
                retrieval_match_count=payload["retrieval_match_count"],
                intent_contract=ContractComplianceMetrics.from_dict(payload["intent_contract"]),
                semantic_contract=ContractComplianceMetrics.from_dict(payload["semantic_contract"]),
                clarification=ClarificationConfusionMatrix.from_dict(payload["clarification"]),
                unsafe_reuse_count=payload["unsafe_reuse_count"],
                hard_failure_codes=tuple(payload["hard_failure_codes"]),
                failure_codes=tuple(payload["failure_codes"]),
                decision=payload["decision"],
            )
        except (TypeError, ValueError):
            raise ScenarioCapabilityError("SEALED_REPORT_VALUE_INVALID", "sealed report failed local validation") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SEALED_REPEATABILITY_REPORT_SCHEMA_VERSION,
            "policy_version": SEALED_REPEATABILITY_POLICY_VERSION,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "preparation": self.preparation.to_dict(),
            "round_count": SEALED_ROUND_COUNT,
            "selected_scenario_count": SEALED_SCENARIO_COUNT,
            "proceed_route_count": SEALED_PROCEED_COUNT,
            "clarify_route_count": SEALED_CLARIFY_COUNT,
            "rounds": [item.to_dict() for item in self.rounds],
            "stable_full_path_match_count": self.stable_full_path_match_count,
            "executed_retrieval_count": self.executed_retrieval_count,
            "retrieval_match_count": self.retrieval_match_count,
            "intent_contract": self.intent_contract.to_dict(),
            "semantic_contract": self.semantic_contract.to_dict(),
            "clarification": self.clarification.to_dict(),
            "unsafe_reuse_count": self.unsafe_reuse_count,
            "hard_failure_codes": list(self.hard_failure_codes),
            "failure_codes": list(self.failure_codes),
            "decision": self.decision,
        }


def build_sealed_repeatability_report(
    preparation: SealedPreparationMetrics,
    run_rounds: tuple[tuple[ScenarioCapabilityRun, ...], ...],
    *,
    intent_contract: ContractComplianceMetrics,
    semantic_contract: ContractComplianceMetrics,
    clarification: ClarificationConfusionMatrix,
    unsafe_reuse_count: int,
    hard_failure_codes: tuple[str, ...],
) -> SealedRepeatabilityReport:
    """Build the aggregate-only report from three source-bound run rounds."""

    if not isinstance(preparation, SealedPreparationMetrics):
        raise ScenarioCapabilityError("SEALED_PREPARATION_METRICS_INVALID", "typed preparation metrics are required")
    if (
        not isinstance(run_rounds, tuple)
        or len(run_rounds) != SEALED_ROUND_COUNT
        or any(not isinstance(round_runs, tuple) or len(round_runs) != SEALED_SCENARIO_COUNT for round_runs in run_rounds)
        or any(not isinstance(run, ScenarioCapabilityRun) for round_runs in run_rounds for run in round_runs)
    ):
        raise ScenarioCapabilityError("SEALED_RUN_SET_INVALID", "sealed execution requires three rounds of 24 typed runs")
    try:
        _non_negative_int(unsafe_reuse_count, "unsafe_reuse_count")
        _code_tuple(hard_failure_codes, allowed=PUBLIC_HARD_FAILURE_CODES)
    except ValueError:
        raise ScenarioCapabilityError("SEALED_REPORT_INPUT_INVALID", "sealed report input violates fixed policy") from None

    identity_by_overlay: dict[str, tuple[str, ...]] | None = None
    normalized_rounds: list[tuple[ScenarioCapabilityRun, ...]] = []
    for round_runs in run_rounds:
        ordered = tuple(sorted(round_runs, key=lambda run: run.source_overlay_hash))
        overlay_hashes = tuple(run.source_overlay_hash for run in ordered)
        if len(overlay_hashes) != len(set(overlay_hashes)):
            raise ScenarioCapabilityError("SEALED_RUN_SET_DUPLICATE", "a round cannot contain the same overlay twice")
        current_identities = {
            run.source_overlay_hash: (
                run.source_reviewed_hash,
                run.source_snapshot_hash,
                run.source_request_hash,
                run.plan_unit_ref,
                run.candidate_ref,
                run.expected_route,
            )
            for run in ordered
        }
        if identity_by_overlay is None:
            identity_by_overlay = current_identities
        elif current_identities != identity_by_overlay:
            raise ScenarioCapabilityError(
                "SEALED_RUN_SET_SOURCE_MISMATCH",
                "rounds must contain the same source-bound scenario identities",
            )
        normalized_rounds.append(ordered)

    round_aggregates = tuple(
        _round_aggregate(index, runs)
        for index, runs in enumerate(normalized_rounds, start=1)
    )
    stable_matches = sum(
        all(round_runs[index].full_path_status == "MATCH" for round_runs in normalized_rounds)
        for index in range(SEALED_SCENARIO_COUNT)
    )
    executed_retrieval = sum(
        aggregate.retrieval.match_count + aggregate.retrieval.mismatch_count + aggregate.retrieval.run_failed_count
        for aggregate in round_aggregates
    )
    retrieval_matches = sum(aggregate.retrieval.match_count for aggregate in round_aggregates)
    failure_codes = _sealed_failure_codes(
        preparation=preparation,
        rounds=round_aggregates,
        stable_full_path_match_count=stable_matches,
        executed_retrieval_count=executed_retrieval,
        retrieval_match_count=retrieval_matches,
        intent_contract=intent_contract,
        semantic_contract=semantic_contract,
        unsafe_reuse_count=unsafe_reuse_count,
    )
    decision = "GO_SHADOW" if not hard_failure_codes and not failure_codes else "NO_GO"
    try:
        return SealedRepeatabilityReport(
            preparation=preparation,
            rounds=round_aggregates,
            stable_full_path_match_count=stable_matches,
            executed_retrieval_count=executed_retrieval,
            retrieval_match_count=retrieval_matches,
            intent_contract=intent_contract,
            semantic_contract=semantic_contract,
            clarification=clarification,
            unsafe_reuse_count=unsafe_reuse_count,
            hard_failure_codes=hard_failure_codes,
            failure_codes=failure_codes,
            decision=decision,
        )
    except (TypeError, ValueError):
        raise ScenarioCapabilityError("SEALED_REPORT_INPUT_INVALID", "sealed report inputs are inconsistent") from None


def _stage_aggregate(runs: tuple[ScenarioCapabilityRun, ...], field_name: str) -> CapabilityStageAggregate:
    results = tuple(getattr(run, field_name) for run in runs)
    applicable = tuple(result for result in results if result.applicable)
    return CapabilityStageAggregate(
        applicable_count=len(applicable),
        match_count=sum(result.status == "MATCH" for result in applicable),
        mismatch_count=sum(result.status == "MISMATCH" for result in applicable),
        not_run_count=sum(result.status == "NOT_RUN" for result in applicable),
        run_failed_count=sum(result.status == "RUN_FAILED" for result in applicable),
    )


def _round_aggregate(round_index: int, runs: tuple[ScenarioCapabilityRun, ...]) -> SealedRoundAggregate:
    return SealedRoundAggregate(
        round_index=round_index,
        proceed_route_count=sum(run.expected_route == "PROCEED" for run in runs),
        clarify_route_count=sum(run.expected_route == "CLARIFY" for run in runs),
        full_path_match_count=sum(run.full_path_status == "MATCH" for run in runs),
        full_path_mismatch_count=sum(run.full_path_status == "MISMATCH" for run in runs),
        full_path_run_failed_count=sum(run.full_path_status == "RUN_FAILED" for run in runs),
        intent=_stage_aggregate(runs, "intent"),
        retrieval=_stage_aggregate(runs, "retrieval"),
        recommendation=_stage_aggregate(runs, "recommendation"),
    )


def _contract_rate_passes(metrics: ContractComplianceMetrics) -> bool:
    return metrics.unit_count > 0 and metrics.final_valid_count * 100 >= metrics.unit_count * SEALED_CONTRACT_PERCENT


def _sealed_failure_codes(
    *,
    preparation: SealedPreparationMetrics,
    rounds: tuple[SealedRoundAggregate, ...],
    stable_full_path_match_count: int,
    executed_retrieval_count: int,
    retrieval_match_count: int,
    intent_contract: ContractComplianceMetrics,
    semantic_contract: ContractComplianceMetrics,
    unsafe_reuse_count: int,
) -> tuple[str, ...]:
    failures: list[str] = []
    if not (SEALED_SCENARIO_COUNT <= preparation.candidate_count <= SEALED_MAX_CANDIDATES):
        failures.append("SEALED_CANDIDATE_COUNT_INVALID")
    if preparation.execution_count != SEALED_SCENARIO_COUNT or preparation.accepted_count + preparation.revised_accepted_count < SEALED_SCENARIO_COUNT:
        failures.append("SEALED_EXECUTION_SET_INVALID")
    if preparation.blocking_finding_count:
        failures.append("SEALED_BLOCKING_FINDING_PRESENT")
    if preparation.review_minutes > SEALED_REVIEW_MINUTES:
        failures.append("SEALED_REVIEW_BUDGET_EXCEEDED")
    if any(round_item.proceed_route_count != SEALED_PROCEED_COUNT or round_item.clarify_route_count != SEALED_CLARIFY_COUNT for round_item in rounds):
        failures.append("SEALED_ROUTE_COMPOSITION_INVALID")
    if any(round_item.full_path_match_count < SEALED_MINIMUM_ROUND_MATCHES for round_item in rounds):
        failures.append("SEALED_ROUND_MATCH_BELOW_MINIMUM")
    if stable_full_path_match_count < SEALED_MINIMUM_STABLE_MATCHES:
        failures.append("SEALED_STABLE_MATCH_BELOW_MINIMUM")
    if not _contract_rate_passes(intent_contract):
        failures.append("SEALED_INTENT_CONTRACT_BELOW_MINIMUM")
    if not _contract_rate_passes(semantic_contract):
        failures.append("SEALED_SEMANTIC_CONTRACT_BELOW_MINIMUM")
    if executed_retrieval_count == 0 or retrieval_match_count != executed_retrieval_count:
        failures.append("SEALED_RETRIEVAL_NOT_PERFECT")
    if unsafe_reuse_count:
        failures.append("SEALED_UNSAFE_REUSE_PRESENT")
    return tuple(sorted(failures))


__all__ = [
    "SEALED_REPEATABILITY_POLICY_VERSION",
    "SEALED_REPEATABILITY_REPORT_SCHEMA_VERSION",
    "ClarificationConfusionMatrix",
    "ContractComplianceMetrics",
    "SealedPreparationMetrics",
    "SealedRepeatabilityReport",
    "SealedRoundAggregate",
    "build_sealed_repeatability_report",
]
