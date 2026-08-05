"""Frozen run and qualification contracts for navigation Shadow rollout."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from treeguard.hashing import canonical_digest
from treeguard.navigation_copilot import NavigationOutcome, NavigationPolicyDecision


RUN_SCHEMA_VERSION = "navigation-copilot-shadow-run.v1"
QUALIFICATION_SCHEMA_VERSION = "navigation-copilot-shadow-qualification.v1"
QUALIFICATION_AGGREGATE_VERSION = (
    "navigation-copilot-shadow-qualification-aggregate.v1"
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_RUN_REF = re.compile(r"^SR[0-9]{4,12}$")
_PARTICIPANT_REF = re.compile(r"^P[0-9]{2,4}$")
PROVIDER_MODES = frozenset({"SIMULATOR_LIVE", "BAILIAN_LIVE", "QWEN_LIVE"})
REJECTION_DISPOSITIONS = frozenset(
    {"PRESENT_NOT_FOUND", "ABSENT", "UNKNOWN"}
)
TARGET_PRESENT_DISPOSITIONS = frozenset(
    {"FOUND_TOP8", "FOUND_OUTSIDE", "PRESENT_NOT_FOUND"}
)
ELIGIBLE_DISPOSITIONS = frozenset(
    {"FOUND_TOP8", "FOUND_OUTSIDE", "PRESENT_NOT_FOUND", "ABSENT"}
)


class NavigationShadowRunError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NavigationShadowThresholds:
    min_valid_case_count: int = 30
    min_participant_count: int = 3
    min_safe_rate_bps: int = 10_000
    min_top8_coverage_bps: int = 8_000
    min_navigation_completion_bps: int = 9_000
    max_confident_error_bps: int = 500
    max_median_completion_ms: int = 180_000

    def __post_init__(self) -> None:
        values = tuple(self.to_dict().values())
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in values
        ):
            raise ValueError("navigation Shadow thresholds must be integers")
        if values != (30, 3, 10_000, 8_000, 9_000, 500, 180_000):
            raise ValueError("navigation Shadow D10 thresholds are not frozen")

    def to_dict(self) -> dict[str, int]:
        return {
            "min_valid_case_count": self.min_valid_case_count,
            "min_participant_count": self.min_participant_count,
            "min_safe_rate_bps": self.min_safe_rate_bps,
            "min_top8_coverage_bps": self.min_top8_coverage_bps,
            "min_navigation_completion_bps": self.min_navigation_completion_bps,
            "max_confident_error_bps": self.max_confident_error_bps,
            "max_median_completion_ms": self.max_median_completion_ms,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "NavigationShadowThresholds":
        expected = set(cls().to_dict())
        if not isinstance(payload, dict) or set(payload) != expected:
            raise NavigationShadowRunError(
                "SHADOW_RUN_THRESHOLDS_INVALID",
                "Shadow run thresholds have invalid fields",
            )
        try:
            return cls(**payload)
        except (TypeError, ValueError):
            raise NavigationShadowRunError(
                "SHADOW_RUN_THRESHOLDS_INVALID",
                "Shadow run thresholds are invalid",
            ) from None


@dataclass(frozen=True, slots=True)
class NavigationShadowRunManifest:
    run_ref: str
    contract_commit: str
    provider_mode: str
    participant_refs: tuple[str, ...]
    planned_case_count: int
    thresholds: NavigationShadowThresholds
    run_hash: str

    def __post_init__(self) -> None:
        if _RUN_REF.fullmatch(self.run_ref) is None:
            raise ValueError("navigation Shadow run reference is invalid")
        if _COMMIT.fullmatch(self.contract_commit) is None:
            raise ValueError("navigation Shadow contract commit is invalid")
        if self.provider_mode not in PROVIDER_MODES:
            raise ValueError("navigation Shadow provider mode is invalid")
        if (
            not isinstance(self.participant_refs, tuple)
            or len(self.participant_refs) < 3
            or len(self.participant_refs) > 100
            or tuple(sorted(set(self.participant_refs))) != self.participant_refs
            or any(
                _PARTICIPANT_REF.fullmatch(item) is None
                for item in self.participant_refs
            )
        ):
            raise ValueError("navigation Shadow participant references are invalid")
        if (
            not isinstance(self.planned_case_count, int)
            or isinstance(self.planned_case_count, bool)
            or self.planned_case_count < self.thresholds.min_valid_case_count
            or self.planned_case_count > 1_000
            or len(self.participant_refs) < self.thresholds.min_participant_count
        ):
            raise ValueError("navigation Shadow run quota is invalid")
        if (
            _DIGEST.fullmatch(self.run_hash) is None
            or self.run_hash != canonical_digest(self._payload())
        ):
            raise ValueError("navigation Shadow run hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RUN_SCHEMA_VERSION,
            "record_semantics": "OPERATIONAL_SHADOW_ONLY",
            "contract_commit": self.contract_commit,
            "run_ref": self.run_ref,
            "provider_mode": self.provider_mode,
            "participant_refs": list(self.participant_refs),
            "planned_case_count": self.planned_case_count,
            "thresholds": self.thresholds.to_dict(),
            "production_write_enabled": False,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "run_hash": self.run_hash}

    @classmethod
    def create(
        cls,
        *,
        run_ref: str,
        contract_commit: str,
        provider_mode: str,
        participant_refs: tuple[str, ...],
        planned_case_count: int = 30,
        thresholds: NavigationShadowThresholds | None = None,
    ) -> "NavigationShadowRunManifest":
        resolved = thresholds or NavigationShadowThresholds()
        normalized = tuple(sorted(participant_refs))
        payload = _run_payload(
            run_ref=run_ref,
            contract_commit=contract_commit,
            provider_mode=provider_mode,
            participant_refs=normalized,
            planned_case_count=planned_case_count,
            thresholds=resolved,
        )
        return cls(
            run_ref=run_ref,
            contract_commit=contract_commit,
            provider_mode=provider_mode,
            participant_refs=normalized,
            planned_case_count=planned_case_count,
            thresholds=resolved,
            run_hash=canonical_digest(payload),
        )

    @classmethod
    def from_dict(cls, payload: Any) -> "NavigationShadowRunManifest":
        expected = {
            "schema_version", "record_semantics", "contract_commit", "run_ref",
            "provider_mode", "participant_refs", "planned_case_count", "thresholds",
            "production_write_enabled", "semantic_approval", "gold_eligible",
            "patch_eligible", "run_hash",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise NavigationShadowRunError(
                "SHADOW_RUN_MANIFEST_INVALID",
                "Shadow run manifest has invalid fields",
            )
        if (
            payload.get("schema_version") != RUN_SCHEMA_VERSION
            or payload.get("record_semantics") != "OPERATIONAL_SHADOW_ONLY"
            or payload.get("production_write_enabled") is not False
            or payload.get("semantic_approval") is not False
            or payload.get("gold_eligible") is not False
            or payload.get("patch_eligible") is not False
            or not isinstance(payload.get("participant_refs"), list)
        ):
            raise NavigationShadowRunError(
                "SHADOW_RUN_MANIFEST_INVALID",
                "Shadow run manifest constants are invalid",
            )
        try:
            return cls(
                run_ref=payload["run_ref"],
                contract_commit=payload["contract_commit"],
                provider_mode=payload["provider_mode"],
                participant_refs=tuple(payload["participant_refs"]),
                planned_case_count=payload["planned_case_count"],
                thresholds=NavigationShadowThresholds.from_dict(payload["thresholds"]),
                run_hash=payload["run_hash"],
            )
        except (TypeError, ValueError):
            raise NavigationShadowRunError(
                "SHADOW_RUN_MANIFEST_INVALID",
                "Shadow run manifest failed validation",
            ) from None


def _run_payload(
    *,
    run_ref: str,
    contract_commit: str,
    provider_mode: str,
    participant_refs: tuple[str, ...],
    planned_case_count: int,
    thresholds: NavigationShadowThresholds,
) -> dict[str, Any]:
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "record_semantics": "OPERATIONAL_SHADOW_ONLY",
        "contract_commit": contract_commit,
        "run_ref": run_ref,
        "provider_mode": provider_mode,
        "participant_refs": list(participant_refs),
        "planned_case_count": planned_case_count,
        "thresholds": thresholds.to_dict(),
        "production_write_enabled": False,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class NavigationShadowQualification:
    run_hash: str
    participant_ref: str
    source_outcome_hash: str
    target_disposition: str
    confident: bool
    clarification_used: bool
    model_degraded: bool
    evidence_covered: bool
    duration_ms: int
    qualification_hash: str

    def __post_init__(self) -> None:
        if (
            _DIGEST.fullmatch(self.run_hash) is None
            or _PARTICIPANT_REF.fullmatch(self.participant_ref) is None
            or _DIGEST.fullmatch(self.source_outcome_hash) is None
            or self.target_disposition not in {
                "FOUND_TOP8",
                "FOUND_OUTSIDE",
                "PRESENT_NOT_FOUND",
                "ABSENT",
                "UNKNOWN",
                "EXITED",
            }
            or any(
                not isinstance(value, bool)
                for value in (
                    self.confident,
                    self.clarification_used,
                    self.model_degraded,
                    self.evidence_covered,
                )
            )
            or not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
            or _DIGEST.fullmatch(self.qualification_hash) is None
            or self.qualification_hash != canonical_digest(self._payload())
        ):
            raise ValueError("navigation Shadow qualification is invalid")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUALIFICATION_SCHEMA_VERSION,
            "record_semantics": "OPERATIONAL_SHADOW_ONLY",
            "run_hash": self.run_hash,
            "participant_ref": self.participant_ref,
            "source_outcome_hash": self.source_outcome_hash,
            "target_disposition": self.target_disposition,
            "confident": self.confident,
            "clarification_used": self.clarification_used,
            "model_degraded": self.model_degraded,
            "evidence_covered": self.evidence_covered,
            "duration_ms": self.duration_ms,
            "safe_termination": True,
            "snapshot_bound": True,
            "production_write_occurred": False,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "qualification_hash": self.qualification_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        manifest: NavigationShadowRunManifest,
    ) -> "NavigationShadowQualification":
        expected = set(_qualification_fields()) | {"qualification_hash"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise NavigationShadowRunError(
                "SHADOW_QUALIFICATION_INVALID",
                "Shadow qualification has invalid fields",
            )
        if not (
            payload.get("schema_version") == QUALIFICATION_SCHEMA_VERSION
            and payload.get("record_semantics") == "OPERATIONAL_SHADOW_ONLY"
            and payload.get("safe_termination") is True
            and payload.get("snapshot_bound") is True
            and payload.get("production_write_occurred") is False
            and payload.get("semantic_approval") is False
            and payload.get("gold_eligible") is False
            and payload.get("patch_eligible") is False
        ):
            raise NavigationShadowRunError(
                "SHADOW_QUALIFICATION_INVALID",
                "Shadow qualification constants are invalid",
            )
        try:
            result = cls(
                run_hash=payload["run_hash"],
                participant_ref=payload["participant_ref"],
                source_outcome_hash=payload["source_outcome_hash"],
                target_disposition=payload["target_disposition"],
                confident=payload["confident"],
                clarification_used=payload["clarification_used"],
                model_degraded=payload["model_degraded"],
                evidence_covered=payload["evidence_covered"],
                duration_ms=payload["duration_ms"],
                qualification_hash=payload["qualification_hash"],
            )
        except (TypeError, ValueError):
            raise NavigationShadowRunError(
                "SHADOW_QUALIFICATION_INVALID",
                "Shadow qualification failed validation",
            ) from None
        if (
            result.run_hash != manifest.run_hash
            or result.participant_ref not in manifest.participant_refs
        ):
            raise NavigationShadowRunError(
                "SHADOW_QUALIFICATION_SOURCE_MISMATCH",
                "Shadow qualification does not bind the frozen run",
            )
        return result


def build_shadow_qualification(
    manifest: NavigationShadowRunManifest,
    participant_ref: str,
    decision: NavigationPolicyDecision,
    outcome: NavigationOutcome,
    *,
    rejection_disposition: str | None,
    clarification_used: bool,
    model_degraded: bool,
) -> NavigationShadowQualification:
    if participant_ref not in manifest.participant_refs:
        raise NavigationShadowRunError(
            "SHADOW_PARTICIPANT_NOT_REGISTERED",
            "participant is not registered in the frozen run",
        )
    if outcome.source_decision_hash != decision.decision_hash:
        raise NavigationShadowRunError(
            "SHADOW_QUALIFICATION_SOURCE_MISMATCH",
            "outcome does not bind the decision",
        )
    if outcome.action == "SELECT_CANDIDATE":
        disposition = "FOUND_TOP8"
    elif outcome.action == "SELECT_OUTSIDE_CANDIDATE":
        disposition = "FOUND_OUTSIDE"
    elif outcome.action == "REJECT_ALL":
        if rejection_disposition not in REJECTION_DISPOSITIONS:
            raise NavigationShadowRunError(
                "SHADOW_TARGET_DISPOSITION_REQUIRED",
                "rejected candidates require a target disposition",
            )
        disposition = rejection_disposition
    elif outcome.action == "EXIT":
        if rejection_disposition is not None:
            raise NavigationShadowRunError(
                "SHADOW_TARGET_DISPOSITION_FORBIDDEN",
                "exit cannot carry a target disposition",
            )
        disposition = "EXITED"
    else:
        raise NavigationShadowRunError(
            "SHADOW_OUTCOME_ACTION_INVALID",
            "outcome action is unsupported",
        )
    if outcome.action != "REJECT_ALL" and rejection_disposition is not None:
        raise NavigationShadowRunError(
            "SHADOW_TARGET_DISPOSITION_FORBIDDEN",
            "selected outcomes cannot carry a target disposition",
        )
    payload = _qualification_payload(
        manifest=manifest,
        participant_ref=participant_ref,
        outcome=outcome,
        disposition=disposition,
        confident=decision.status == "CANDIDATES_AVAILABLE",
        clarification_used=clarification_used,
        model_degraded=model_degraded,
        evidence_covered=decision.status != "NONE",
    )
    return NavigationShadowQualification(
        run_hash=manifest.run_hash,
        participant_ref=participant_ref,
        source_outcome_hash=outcome.outcome_hash,
        target_disposition=disposition,
        confident=payload["confident"],
        clarification_used=clarification_used,
        model_degraded=model_degraded,
        evidence_covered=payload["evidence_covered"],
        duration_ms=outcome.duration_ms,
        qualification_hash=canonical_digest(payload),
    )


def _qualification_payload(
    *,
    manifest: NavigationShadowRunManifest,
    participant_ref: str,
    outcome: NavigationOutcome,
    disposition: str,
    confident: bool,
    clarification_used: bool,
    model_degraded: bool,
    evidence_covered: bool,
) -> dict[str, Any]:
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "record_semantics": "OPERATIONAL_SHADOW_ONLY",
        "run_hash": manifest.run_hash,
        "participant_ref": participant_ref,
        "source_outcome_hash": outcome.outcome_hash,
        "target_disposition": disposition,
        "confident": confident,
        "clarification_used": clarification_used,
        "model_degraded": model_degraded,
        "evidence_covered": evidence_covered,
        "duration_ms": outcome.duration_ms,
        "safe_termination": True,
        "snapshot_bound": True,
        "production_write_occurred": False,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }


def _qualification_fields() -> tuple[str, ...]:
    return (
        "schema_version", "record_semantics", "run_hash", "participant_ref",
        "source_outcome_hash", "target_disposition", "confident",
        "clarification_used", "model_degraded", "evidence_covered",
        "duration_ms", "safe_termination", "snapshot_bound",
        "production_write_occurred", "semantic_approval", "gold_eligible",
        "patch_eligible",
    )


def aggregate_shadow_qualifications(
    manifest: NavigationShadowRunManifest,
    records: tuple[NavigationShadowQualification, ...],
) -> dict[str, Any]:
    if not isinstance(records, tuple):
        raise NavigationShadowRunError(
            "SHADOW_AGGREGATE_RECORDS_INVALID",
            "qualification records must be an immutable tuple",
        )
    if len(records) > manifest.planned_case_count:
        raise NavigationShadowRunError(
            "SHADOW_AGGREGATE_PLAN_EXCEEDED",
            "qualification count exceeds the frozen run plan",
        )
    seen_outcomes: set[str] = set()
    for record in records:
        if (
            not isinstance(record, NavigationShadowQualification)
            or record.run_hash != manifest.run_hash
            or record.participant_ref not in manifest.participant_refs
            or record.source_outcome_hash in seen_outcomes
        ):
            raise NavigationShadowRunError(
                "SHADOW_AGGREGATE_SOURCE_MISMATCH",
                "qualification records do not bind the frozen run",
            )
        seen_outcomes.add(record.source_outcome_hash)

    eligible = tuple(
        record
        for record in records
        if record.target_disposition in ELIGIBLE_DISPOSITIONS
    )
    target_present = tuple(
        record
        for record in eligible
        if record.target_disposition in TARGET_PRESENT_DISPOSITIONS
    )
    direct_count = sum(
        record.target_disposition == "FOUND_TOP8" for record in target_present
    )
    completed_count = sum(
        record.target_disposition in {"FOUND_TOP8", "FOUND_OUTSIDE"}
        for record in target_present
    )
    confident = tuple(record for record in eligible if record.confident)
    confident_error_count = sum(
        record.target_disposition != "FOUND_TOP8" for record in confident
    )
    participant_count = len({record.participant_ref for record in eligible})
    top8_rate = _rate_bps(direct_count, len(target_present))
    completion_rate = _rate_bps(completed_count, len(target_present))
    confident_error_rate = _rate_bps(confident_error_count, len(confident))
    safety_rate = 10_000 if eligible else None
    durations = sorted(
        record.duration_ms
        for record in target_present
        if record.target_disposition in {"FOUND_TOP8", "FOUND_OUTSIDE"}
    )
    completion_median = None
    if durations:
        middle = len(durations) // 2
        completion_median = (
            durations[middle]
            if len(durations) % 2
            else (durations[middle - 1] + durations[middle]) // 2
        )
    thresholds = manifest.thresholds
    denominator_ready = (
        len(records) == manifest.planned_case_count
        and len(eligible) >= thresholds.min_valid_case_count
        and participant_count >= thresholds.min_participant_count
    )
    metrics_pass = (
        denominator_ready
        and safety_rate is not None
        and safety_rate >= thresholds.min_safe_rate_bps
        and top8_rate is not None
        and top8_rate >= thresholds.min_top8_coverage_bps
        and completion_rate is not None
        and completion_rate >= thresholds.min_navigation_completion_bps
        and confident_error_rate is not None
        and confident_error_rate <= thresholds.max_confident_error_bps
        and completion_median is not None
        and completion_median <= thresholds.max_median_completion_ms
    )
    return {
        "report_version": QUALIFICATION_AGGREGATE_VERSION,
        "valid": True,
        "decision": (
            "EXPANSION_ELIGIBLE"
            if metrics_pass
            else "HOLD_NOT_QUALIFIED"
            if denominator_ready
            else "COLLECTING"
        ),
        "record_count": len(records),
        "valid_case_count": len(eligible),
        "participant_count": participant_count,
        "target_present_case_count": len(target_present),
        "top8_direct_selection_count": direct_count,
        "completed_navigation_count": completed_count,
        "confident_case_count": len(confident),
        "confident_error_count": confident_error_count,
        "unknown_case_count": sum(
            record.target_disposition == "UNKNOWN" for record in records
        ),
        "exited_case_count": sum(
            record.target_disposition == "EXITED" for record in records
        ),
        "safe_termination_rate_bps": safety_rate,
        "snapshot_binding_rate_bps": safety_rate,
        "zero_production_write_rate_bps": safety_rate,
        "top8_coverage_rate_bps": top8_rate,
        "navigation_completion_rate_bps": completion_rate,
        "confident_error_rate_bps": confident_error_rate,
        "median_completion_ms": completion_median,
        "semantic_approval": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }


def _rate_bps(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    return numerator * 10_000 // denominator


__all__ = [
    "ELIGIBLE_DISPOSITIONS",
    "NavigationShadowQualification",
    "NavigationShadowRunError",
    "NavigationShadowRunManifest",
    "NavigationShadowThresholds",
    "QUALIFICATION_AGGREGATE_VERSION",
    "QUALIFICATION_SCHEMA_VERSION",
    "REJECTION_DISPOSITIONS",
    "RUN_SCHEMA_VERSION",
    "aggregate_shadow_qualifications",
    "build_shadow_qualification",
]
