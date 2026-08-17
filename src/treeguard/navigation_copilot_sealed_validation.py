"""Deterministic contracts and scoring for sealed Navigation Copilot evaluation.

This module is deliberately independent from the operational Shadow aggregate.
It consumes source-bound observations produced after the product sidecars exist;
it never calls a model, reads files, or reimplements the product pipeline.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from treeguard.hashing import canonical_digest


MANIFEST_SCHEMA_VERSION = "navigation-copilot-sealed-evaluation-manifest.v2"
SCENARIO_SCHEMA_VERSION = "navigation-copilot-sealed-scenario.v2"
ORACLE_SCHEMA_VERSION = "navigation-copilot-sealed-oracle.v2"
TRACE_SCHEMA_VERSION = "navigation-copilot-sealed-trace.v2"
OBSERVATION_SCHEMA_VERSION = "navigation-copilot-sealed-observation.v2"
AGGREGATE_SCHEMA_VERSION = "navigation-copilot-sealed-aggregate.v2"
DIAGNOSTIC_AGGREGATE_SCHEMA_VERSION = (
    "navigation-copilot-sealed-diagnostic-aggregate.v2"
)
THRESHOLD_POLICY_VERSION = "treeguard.navigation-copilot-sealed-gate.v1"

MAIN_CASE_COUNT = 48
TARGET_PRESENT_COUNT = 42
REPEAT_FAMILY_COUNT = 16
WRONG_CONTEXT_COUNT = 8
LOGICAL_CASE_LIMIT = 80
LOGICAL_MODEL_STAGE_LIMIT = 160
PER_CASE_MODEL_STAGE_LIMIT = 2

PROVIDER_MODE = "BAILIAN_LIVE"
EXPECTED_ROUTES = frozenset({"PROCEED", "CLARIFY", "LIMIT"})
TARGET_STATUSES = frozenset({"TARGET_PRESENT", "TARGET_ABSENT"})
CLARIFICATION_POLICIES = frozenset(
    {"CLARIFICATION_REQUIRED", "NOT_APPLICABLE"}
)
POLICY_STATUSES = frozenset(
    {"CANDIDATES_AVAILABLE", "AMBIGUOUS", "NONE", "NEED_EVIDENCE"}
)
OUTCOME_ACTIONS = frozenset(
    {"SELECT_CANDIDATE", "SELECT_OUTSIDE_CANDIDATE", "REJECT_ALL", "EXIT"}
)
TARGET_DISPOSITIONS = frozenset(
    {"FOUND_TOP8", "FOUND_OUTSIDE", "PRESENT_NOT_FOUND", "ABSENT"}
)
STAGES = frozenset(
    {
        "NONE",
        "UNDERSTANDING",
        "RETRIEVAL",
        "SEMANTIC",
        "POLICY",
        "END_TO_END",
        "REPEATABILITY",
    }
)
RUN_STATUSES = frozenset(
    {"COMPLETE", "UNRUN", "PROVIDER_FAILED", "CONTRACT_FAILED"}
)
QUALIFICATION_STATUSES = frozenset(
    {
        "READY_FOR_PROTECTED_SHADOW",
        "HOLD_RETRIEVAL",
        "HOLD_SEMANTIC_POLICY",
        "HOLD_MODEL_CONTRACT",
        "DATA_OR_RUN_INVALID",
        "INCONCLUSIVE",
    }
)
CATEGORIES = frozenset(
    {
        "LITERAL_UNIQUE",
        "NONLITERAL_UNIQUE",
        "STRUCTURAL_INTERFERENCE",
        "MULTI_ACCEPTABLE",
        "CLARIFICATION",
        "WEAK_EVIDENCE",
        "TARGET_ABSENT",
    }
)
CATEGORY_QUOTAS = {
    "LITERAL_UNIQUE": 10,
    "NONLITERAL_UNIQUE": 10,
    "STRUCTURAL_INTERFERENCE": 8,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 6,
    "WEAK_EVIDENCE": 4,
    "TARGET_ABSENT": 6,
}

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")


class SealedEvaluationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a SHA-256 digest")
    return value


def _text(value: Any, name: str, *, maximum: int = 1_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be bounded non-empty text")
    return value


def _ordered_strings(
    value: Any,
    name: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item for item in value)
        or value != tuple(sorted(set(value)))
    ):
        raise ValueError(f"{name} must be an ordered unique tuple")
    return value


def _creation_digest(cls: type[Any], values: dict[str, Any]) -> str:
    """Hash a fully specified creation payload before final validation."""

    draft = object.__new__(cls)
    for name, value in values.items():
        object.__setattr__(draft, name, value)
    return canonical_digest(draft._payload())


@dataclass(frozen=True, slots=True)
class SealedEvaluationThresholds:
    min_top40_hits: int = 38
    min_top8_hits: int = 36
    min_nonliteral_top8_hits: int = 8
    min_interference_top8_hits: int = 6
    min_clarification_top8_hits: int = 5
    min_required_clarification_match_count: int = 5
    min_wrong_context_top8_hits: int = 7
    max_absent_confident_errors: int = 0
    min_highlight_precision_numerator_bps: int = 9_500
    min_correct_highlight_count: int = 21
    min_no_degradation_count: int = 44
    min_joint_match_count: int = 41
    max_needless_clarification_count: int = 4
    max_c1_top8_loss_from_r0: int = 1
    min_repeat_stable_count: int = 14

    def __post_init__(self) -> None:
        values = tuple(self.to_dict().values())
        if any(not isinstance(v, int) or isinstance(v, bool) for v in values):
            raise ValueError("sealed thresholds must be integers")
        if values != (38, 36, 8, 6, 5, 5, 7, 0, 9_500, 21, 44, 41, 4, 1, 14):
            raise ValueError("sealed evaluation thresholds are not frozen")

    def to_dict(self) -> dict[str, int]:
        return {
            "min_top40_hits": self.min_top40_hits,
            "min_top8_hits": self.min_top8_hits,
            "min_nonliteral_top8_hits": self.min_nonliteral_top8_hits,
            "min_interference_top8_hits": self.min_interference_top8_hits,
            "min_clarification_top8_hits": self.min_clarification_top8_hits,
            "min_required_clarification_match_count": self.min_required_clarification_match_count,
            "min_wrong_context_top8_hits": self.min_wrong_context_top8_hits,
            "max_absent_confident_errors": self.max_absent_confident_errors,
            "min_highlight_precision_numerator_bps": self.min_highlight_precision_numerator_bps,
            "min_correct_highlight_count": self.min_correct_highlight_count,
            "min_no_degradation_count": self.min_no_degradation_count,
            "min_joint_match_count": self.min_joint_match_count,
            "max_needless_clarification_count": self.max_needless_clarification_count,
            "max_c1_top8_loss_from_r0": self.max_c1_top8_loss_from_r0,
            "min_repeat_stable_count": self.min_repeat_stable_count,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "SealedEvaluationThresholds":
        if not isinstance(payload, dict) or set(payload) != set(cls().to_dict()):
            raise SealedEvaluationError(
                "SEALED_THRESHOLDS_INVALID", "thresholds must use exact fields"
            )
        try:
            return cls(**payload)
        except (TypeError, ValueError):
            raise SealedEvaluationError(
                "SEALED_THRESHOLDS_INVALID", "thresholds violate the frozen gate"
            ) from None


@dataclass(frozen=True, slots=True)
class SealedEvaluationManifest:
    function_commit: str
    data_commit: str
    tree_sha256: str
    scenarios_sha256: str
    oracle_sha256: str
    model_name: str
    understanding_prompt_version: str
    clarification_prompt_version: str
    semantic_prompt_version: str
    endpoint_class: str
    scenario_refs: tuple[str, ...]
    repeat_scenario_refs: tuple[str, ...]
    wire_attempt_limit: int
    thresholds: SealedEvaluationThresholds
    manifest_hash: str

    def __post_init__(self) -> None:
        if _COMMIT.fullmatch(self.function_commit) is None or _COMMIT.fullmatch(
            self.data_commit
        ) is None:
            raise ValueError("sealed evaluation commits are invalid")
        for name in ("tree_sha256", "scenarios_sha256", "oracle_sha256"):
            _digest(getattr(self, name), name)
        for name in (
            "model_name",
            "understanding_prompt_version",
            "clarification_prompt_version",
            "semantic_prompt_version",
        ):
            _text(getattr(self, name), name)
        if self.endpoint_class != "OFFICIAL_BAILIAN_COMPATIBLE":
            raise ValueError("sealed endpoint class is not frozen")
        _ordered_strings(self.scenario_refs, "scenario_refs", allow_empty=False)
        _ordered_strings(
            self.repeat_scenario_refs, "repeat_scenario_refs", allow_empty=False
        )
        if len(self.scenario_refs) != MAIN_CASE_COUNT:
            raise ValueError("sealed evaluation requires exactly 48 scenarios")
        if len(self.repeat_scenario_refs) != REPEAT_FAMILY_COUNT or not set(
            self.repeat_scenario_refs
        ).issubset(self.scenario_refs):
            raise ValueError("sealed repeat subset is invalid")
        if (
            not isinstance(self.wire_attempt_limit, int)
            or isinstance(self.wire_attempt_limit, bool)
            or not LOGICAL_MODEL_STAGE_LIMIT
            <= self.wire_attempt_limit
            <= LOGICAL_MODEL_STAGE_LIMIT * 2
        ):
            raise ValueError("wire attempt limit is outside the frozen bound")
        if not isinstance(self.thresholds, SealedEvaluationThresholds):
            raise ValueError("sealed thresholds are invalid")
        _digest(self.manifest_hash, "manifest_hash")
        if self.manifest_hash != canonical_digest(self._payload()):
            raise ValueError("sealed manifest hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "threshold_policy_version": THRESHOLD_POLICY_VERSION,
            "evaluation_role": "SEALED_FICTIONAL_QUALIFICATION",
            "function_commit": self.function_commit,
            "data_commit": self.data_commit,
            "tree_sha256": self.tree_sha256,
            "scenarios_sha256": self.scenarios_sha256,
            "oracle_sha256": self.oracle_sha256,
            "provider_mode": PROVIDER_MODE,
            "model_name": self.model_name,
            "understanding_prompt_version": self.understanding_prompt_version,
            "clarification_prompt_version": self.clarification_prompt_version,
            "semantic_prompt_version": self.semantic_prompt_version,
            "endpoint_class": self.endpoint_class,
            "scenario_refs": list(self.scenario_refs),
            "repeat_scenario_refs": list(self.repeat_scenario_refs),
            "main_case_count": MAIN_CASE_COUNT,
            "target_present_count": TARGET_PRESENT_COUNT,
            "wrong_context_count": WRONG_CONTEXT_COUNT,
            "logical_case_limit": LOGICAL_CASE_LIMIT,
            "logical_model_stage_limit": LOGICAL_MODEL_STAGE_LIMIT,
            "per_case_model_stage_limit": PER_CASE_MODEL_STAGE_LIMIT,
            "wire_attempt_limit": self.wire_attempt_limit,
            "thresholds": self.thresholds.to_dict(),
            "production_write_enabled": False,
            "gold_eligible": False,
            "patch_eligible": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "manifest_hash": self.manifest_hash}

    @classmethod
    def create(cls, **values: Any) -> "SealedEvaluationManifest":
        normalized = {
            **values,
            "scenario_refs": tuple(sorted(values["scenario_refs"])),
            "repeat_scenario_refs": tuple(sorted(values["repeat_scenario_refs"])),
            "thresholds": values.get("thresholds") or SealedEvaluationThresholds(),
        }
        return cls(**normalized, manifest_hash=_creation_digest(cls, normalized))

    @classmethod
    def from_dict(cls, payload: Any) -> "SealedEvaluationManifest":
        expected = set(cls._payload_keys()) | {"manifest_hash"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise SealedEvaluationError(
                "SEALED_MANIFEST_FIELDS_INVALID", "manifest must use exact fields"
            )
        constants = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "threshold_policy_version": THRESHOLD_POLICY_VERSION,
            "evaluation_role": "SEALED_FICTIONAL_QUALIFICATION",
            "provider_mode": PROVIDER_MODE,
            "main_case_count": MAIN_CASE_COUNT,
            "target_present_count": TARGET_PRESENT_COUNT,
            "wrong_context_count": WRONG_CONTEXT_COUNT,
            "logical_case_limit": LOGICAL_CASE_LIMIT,
            "logical_model_stage_limit": LOGICAL_MODEL_STAGE_LIMIT,
            "per_case_model_stage_limit": PER_CASE_MODEL_STAGE_LIMIT,
            "production_write_enabled": False,
            "gold_eligible": False,
            "patch_eligible": False,
        }
        if any(payload.get(key) != value for key, value in constants.items()):
            raise SealedEvaluationError(
                "SEALED_MANIFEST_CONSTANT_INVALID", "manifest constants changed"
            )
        if not isinstance(payload["scenario_refs"], list) or not isinstance(
            payload["repeat_scenario_refs"], list
        ):
            raise SealedEvaluationError(
                "SEALED_MANIFEST_FIELDS_INVALID", "manifest refs must be arrays"
            )
        try:
            return cls(
                function_commit=payload["function_commit"],
                data_commit=payload["data_commit"],
                tree_sha256=payload["tree_sha256"],
                scenarios_sha256=payload["scenarios_sha256"],
                oracle_sha256=payload["oracle_sha256"],
                model_name=payload["model_name"],
                understanding_prompt_version=payload["understanding_prompt_version"],
                clarification_prompt_version=payload["clarification_prompt_version"],
                semantic_prompt_version=payload["semantic_prompt_version"],
                endpoint_class=payload["endpoint_class"],
                scenario_refs=tuple(payload["scenario_refs"]),
                repeat_scenario_refs=tuple(payload["repeat_scenario_refs"]),
                wire_attempt_limit=payload["wire_attempt_limit"],
                thresholds=SealedEvaluationThresholds.from_dict(payload["thresholds"]),
                manifest_hash=payload["manifest_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise SealedEvaluationError(
                "SEALED_MANIFEST_INVALID", "manifest failed strict validation"
            ) from None

    @staticmethod
    def _payload_keys() -> tuple[str, ...]:
        return (
            "schema_version", "threshold_policy_version", "evaluation_role",
            "function_commit", "data_commit", "tree_sha256", "scenarios_sha256",
            "oracle_sha256", "provider_mode", "model_name",
            "understanding_prompt_version", "clarification_prompt_version",
            "semantic_prompt_version", "endpoint_class", "scenario_refs",
            "repeat_scenario_refs",
            "main_case_count", "target_present_count", "wrong_context_count",
            "logical_case_limit",
            "logical_model_stage_limit", "per_case_model_stage_limit",
            "wire_attempt_limit", "thresholds", "production_write_enabled",
            "gold_eligible", "patch_eligible",
        )


@dataclass(frozen=True, slots=True)
class StructuralProfile:
    node_kind: str
    value_type: str | None
    cardinality: str

    def __post_init__(self) -> None:
        if self.node_kind not in {"CONCEPT", "PROPERTY", "UNKNOWN"}:
            raise ValueError("profile node kind is invalid")
        if self.value_type is not None:
            _text(self.value_type, "profile value_type")
        if self.cardinality not in {"SINGLE", "MULTIPLE", "UNKNOWN"}:
            raise ValueError("profile cardinality is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_kind": self.node_kind,
            "value_type": self.value_type,
            "cardinality": self.cardinality,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "StructuralProfile":
        if not isinstance(payload, dict) or set(payload) != {
            "node_kind", "value_type", "cardinality"
        }:
            raise ValueError("structural profile must use exact fields")
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class SealedScenario:
    scenario_ref: str
    tree_digest: str
    category: str
    requirement_text: str
    proposed_parent_ref: str | None
    node_kind_hint: str
    value_type_hint: str | None
    cardinality_hint: str
    frozen_clarification_answer: str | None
    wrong_context_challenge: bool
    repeat_challenge: bool
    request_digest: str
    scenario_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_ref, str) or _REF.fullmatch(self.scenario_ref) is None:
            raise ValueError("scenario reference is invalid")
        _digest(self.tree_digest, "tree_digest")
        _text(self.requirement_text, "requirement_text", maximum=8_000)
        if self.category not in CATEGORIES:
            raise ValueError("scenario category is invalid")
        if self.proposed_parent_ref is not None and (
            not isinstance(self.proposed_parent_ref, str)
            or re.fullmatch(r"^N[0-9]{6}$", self.proposed_parent_ref) is None
        ):
            raise ValueError("scenario parent reference is invalid")
        if self.node_kind_hint not in {"CONCEPT", "PROPERTY", "UNKNOWN"}:
            raise ValueError("scenario node-kind hint is invalid")
        if self.value_type_hint is not None:
            _text(self.value_type_hint, "value_type_hint")
        if self.cardinality_hint not in {"SINGLE", "MULTIPLE", "UNKNOWN"}:
            raise ValueError("scenario cardinality hint is invalid")
        if self.category == "CLARIFICATION":
            _text(
                self.frozen_clarification_answer,
                "frozen_clarification_answer",
                maximum=4_000,
            )
        elif self.frozen_clarification_answer is not None:
            raise ValueError("non-clarification scenario cannot carry an answer")
        if not isinstance(self.wrong_context_challenge, bool) or not isinstance(
            self.repeat_challenge, bool
        ):
            raise ValueError("scenario challenge flags must be booleans")
        if self.wrong_context_challenge and self.proposed_parent_ref is None:
            raise ValueError("wrong-context challenge requires a parent reference")
        _digest(self.request_digest, "request_digest")
        if self.request_digest != canonical_digest(self.model_request_dict()):
            raise ValueError("scenario request digest does not match")
        _digest(self.scenario_hash, "scenario_hash")
        if self.scenario_hash != canonical_digest(self._payload()):
            raise ValueError("scenario hash does not match")

    def model_request_dict(self) -> dict[str, Any]:
        """Return the only scenario fields allowed to enter the Workbench API."""

        return {
            "requirement_text": self.requirement_text,
            "proposed_parent_ref": self.proposed_parent_ref,
            "node_kind_hint": self.node_kind_hint,
            "value_type_hint": self.value_type_hint,
            "cardinality_hint": self.cardinality_hint,
        }

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCENARIO_SCHEMA_VERSION,
            "scenario_ref": self.scenario_ref,
            "tree_digest": self.tree_digest,
            "category": self.category,
            **self.model_request_dict(),
            "frozen_clarification_answer": self.frozen_clarification_answer,
            "wrong_context_challenge": self.wrong_context_challenge,
            "repeat_challenge": self.repeat_challenge,
            "request_digest": self.request_digest,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "scenario_hash": self.scenario_hash}

    @classmethod
    def create(cls, **values: Any) -> "SealedScenario":
        request_payload = {
            key: values[key]
            for key in (
                "requirement_text", "proposed_parent_ref", "node_kind_hint",
                "value_type_hint", "cardinality_hint",
            )
        }
        normalized = {**values, "request_digest": canonical_digest(request_payload)}
        return cls(**normalized, scenario_hash=_creation_digest(cls, normalized))

    @classmethod
    def from_dict(cls, payload: Any) -> "SealedScenario":
        expected = {
            "schema_version", "scenario_ref", "tree_digest", "category",
            "requirement_text", "proposed_parent_ref", "node_kind_hint",
            "value_type_hint", "cardinality_hint", "frozen_clarification_answer",
            "wrong_context_challenge", "repeat_challenge", "request_digest",
            "scenario_hash",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != expected
            or payload.get("schema_version") != SCENARIO_SCHEMA_VERSION
        ):
            raise SealedEvaluationError(
                "SEALED_SCENARIO_FIELDS_INVALID", "scenario must use exact fields"
            )
        try:
            return cls(
                scenario_ref=payload["scenario_ref"],
                tree_digest=payload["tree_digest"],
                category=payload["category"],
                requirement_text=payload["requirement_text"],
                proposed_parent_ref=payload["proposed_parent_ref"],
                node_kind_hint=payload["node_kind_hint"],
                value_type_hint=payload["value_type_hint"],
                cardinality_hint=payload["cardinality_hint"],
                frozen_clarification_answer=payload["frozen_clarification_answer"],
                wrong_context_challenge=payload["wrong_context_challenge"],
                repeat_challenge=payload["repeat_challenge"],
                request_digest=payload["request_digest"],
                scenario_hash=payload["scenario_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise SealedEvaluationError(
                "SEALED_SCENARIO_INVALID", "scenario failed strict validation"
            ) from None


@dataclass(frozen=True, slots=True)
class TerminalExpectation:
    action: str
    target_node_id: str | None
    target_disposition: str

    def __post_init__(self) -> None:
        if self.action not in OUTCOME_ACTIONS or self.target_disposition not in TARGET_DISPOSITIONS:
            raise ValueError("terminal expectation enum is invalid")
        if self.target_node_id is not None:
            _text(self.target_node_id, "terminal target", maximum=512)
        selected = self.action in {"SELECT_CANDIDATE", "SELECT_OUTSIDE_CANDIDATE"}
        if selected != (self.target_node_id is not None):
            raise ValueError("terminal target and action disagree")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target_node_id": self.target_node_id,
            "target_disposition": self.target_disposition,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "TerminalExpectation":
        if not isinstance(payload, dict) or set(payload) != {
            "action", "target_node_id", "target_disposition"
        }:
            raise ValueError("terminal expectation must use exact fields")
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class SealedCaseOracle:
    scenario_ref: str
    tree_digest: str
    request_digest: str
    category: str
    expected_route: str
    acceptable_profiles: tuple[StructuralProfile, ...]
    target_status: str
    acceptable_node_ids: tuple[str, ...]
    forbidden_node_ids: tuple[str, ...]
    clarification_policy: str
    frozen_clarification_answer: str | None
    acceptable_policy_statuses: tuple[str, ...]
    acceptable_terminals: tuple[TerminalExpectation, ...]
    wrong_context_challenge: bool
    review_status: str
    reviewed_bytes_digest: str
    execution_eligible: bool
    oracle_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_ref, str) or _REF.fullmatch(self.scenario_ref) is None:
            raise ValueError("scenario reference is invalid")
        _digest(self.tree_digest, "tree_digest")
        _digest(self.request_digest, "request_digest")
        if self.category not in CATEGORIES or self.expected_route not in EXPECTED_ROUTES:
            raise ValueError("Oracle category or route is invalid")
        if not isinstance(self.acceptable_profiles, tuple) or any(
            not isinstance(item, StructuralProfile) for item in self.acceptable_profiles
        ):
            raise ValueError("Oracle profiles are invalid")
        profile_keys = tuple(canonical_digest(item.to_dict()) for item in self.acceptable_profiles)
        if profile_keys != tuple(sorted(set(profile_keys))):
            raise ValueError("Oracle profiles must be unique and ordered")
        if self.target_status not in TARGET_STATUSES:
            raise ValueError("Oracle target status is invalid")
        _ordered_strings(self.acceptable_node_ids, "acceptable_node_ids")
        _ordered_strings(self.forbidden_node_ids, "forbidden_node_ids")
        if set(self.acceptable_node_ids) & set(self.forbidden_node_ids):
            raise ValueError("acceptable and forbidden targets overlap")
        if (self.target_status == "TARGET_PRESENT") != bool(self.acceptable_node_ids):
            raise ValueError("target status and acceptable targets disagree")
        expected_target_status = (
            "TARGET_ABSENT" if self.category == "TARGET_ABSENT" else "TARGET_PRESENT"
        )
        if self.target_status != expected_target_status:
            raise ValueError("Oracle category and target status disagree")
        expected_route = (
            "CLARIFY"
            if self.category == "CLARIFICATION"
            else ("LIMIT" if self.category == "WEAK_EVIDENCE" else "PROCEED")
        )
        if self.expected_route != expected_route:
            raise ValueError("Oracle category and route disagree")
        if self.category == "MULTI_ACCEPTABLE":
            if len(self.acceptable_node_ids) < 2:
                raise ValueError("multi-acceptable Oracle requires multiple targets")
        elif self.target_status == "TARGET_PRESENT" and len(self.acceptable_node_ids) != 1:
            raise ValueError("non-multi Oracle requires exactly one target")
        if self.target_status == "TARGET_ABSENT" and self.forbidden_node_ids:
            raise ValueError("absent-target Oracle cannot name structural distractors")
        if self.clarification_policy not in CLARIFICATION_POLICIES:
            raise ValueError("clarification policy is invalid")
        if self.clarification_policy == "CLARIFICATION_REQUIRED":
            _text(self.frozen_clarification_answer, "clarification answer", maximum=4_000)
            if self.expected_route != "CLARIFY":
                raise ValueError("required clarification must expect CLARIFY")
        elif self.frozen_clarification_answer is not None:
            raise ValueError("non-clarification Oracle cannot carry an answer")
        _ordered_strings(
            self.acceptable_policy_statuses,
            "acceptable_policy_statuses",
            allow_empty=False,
        )
        if any(item not in POLICY_STATUSES for item in self.acceptable_policy_statuses):
            raise ValueError("Oracle policy status is unsupported")
        if not isinstance(self.acceptable_terminals, tuple) or not self.acceptable_terminals:
            raise ValueError("Oracle requires terminal expectations")
        terminal_keys = tuple(canonical_digest(item.to_dict()) for item in self.acceptable_terminals)
        if terminal_keys != tuple(sorted(set(terminal_keys))):
            raise ValueError("Oracle terminals must be unique and ordered")
        if self.target_status == "TARGET_PRESENT":
            if self.category == "WEAK_EVIDENCE":
                if (
                    self.expected_route != "LIMIT"
                    or self.acceptable_policy_statuses != ("NEED_EVIDENCE",)
                    or any(
                        item.action != "EXIT"
                        or item.target_node_id is not None
                        or item.target_disposition != "PRESENT_NOT_FOUND"
                        for item in self.acceptable_terminals
                    )
                ):
                    raise ValueError("weak-evidence terminal is inconsistent")
            elif any(
                item.action not in {"SELECT_CANDIDATE", "SELECT_OUTSIDE_CANDIDATE"}
                or item.target_node_id not in self.acceptable_node_ids
                or item.target_disposition not in {"FOUND_TOP8", "FOUND_OUTSIDE"}
                for item in self.acceptable_terminals
            ):
                raise ValueError("present-target terminal is inconsistent")
        elif any(
            item.action not in {"REJECT_ALL", "EXIT"}
            or item.target_node_id is not None
            or item.target_disposition != "ABSENT"
            for item in self.acceptable_terminals
        ):
            raise ValueError("absent-target terminal is inconsistent")
        if not isinstance(self.wrong_context_challenge, bool):
            raise ValueError("wrong-context flag must be boolean")
        if (
            self.review_status != "CODEX_SILVER_REVIEWED"
            or self.execution_eligible is not True
        ):
            raise ValueError("Oracle is not Silver execution eligible")
        _digest(self.reviewed_bytes_digest, "reviewed_bytes_digest")
        _digest(self.oracle_hash, "oracle_hash")
        if self.oracle_hash != canonical_digest(self._payload()):
            raise ValueError("Oracle hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": ORACLE_SCHEMA_VERSION,
            "quality_tier": "SILVER",
            "assessment_authority": "CODEX_ASSISTED",
            "gold_eligible": False,
            "patch_eligible": False,
            "scenario_ref": self.scenario_ref,
            "tree_digest": self.tree_digest,
            "request_digest": self.request_digest,
            "category": self.category,
            "expected_route": self.expected_route,
            "acceptable_profiles": [item.to_dict() for item in self.acceptable_profiles],
            "target_status": self.target_status,
            "acceptable_node_ids": list(self.acceptable_node_ids),
            "forbidden_node_ids": list(self.forbidden_node_ids),
            "clarification_policy": self.clarification_policy,
            "frozen_clarification_answer": self.frozen_clarification_answer,
            "acceptable_policy_statuses": list(self.acceptable_policy_statuses),
            "acceptable_terminals": [item.to_dict() for item in self.acceptable_terminals],
            "wrong_context_challenge": self.wrong_context_challenge,
            "review_status": self.review_status,
            "reviewed_bytes_digest": self.reviewed_bytes_digest,
            "execution_eligible": self.execution_eligible,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "oracle_hash": self.oracle_hash}

    @classmethod
    def create(cls, **values: Any) -> "SealedCaseOracle":
        normalized = {
            **values,
            "acceptable_profiles": tuple(
                sorted(values.get("acceptable_profiles", ()), key=lambda x: canonical_digest(x.to_dict()))
            ),
            "acceptable_node_ids": tuple(sorted(values.get("acceptable_node_ids", ()))),
            "forbidden_node_ids": tuple(sorted(values.get("forbidden_node_ids", ()))),
            "acceptable_policy_statuses": tuple(sorted(values["acceptable_policy_statuses"])),
            "acceptable_terminals": tuple(
                sorted(values["acceptable_terminals"], key=lambda x: canonical_digest(x.to_dict()))
            ),
        }
        return cls(**normalized, oracle_hash=_creation_digest(cls, normalized))

    @classmethod
    def from_dict(cls, payload: Any) -> "SealedCaseOracle":
        constants = {
            "schema_version": ORACLE_SCHEMA_VERSION,
            "quality_tier": "SILVER",
            "assessment_authority": "CODEX_ASSISTED",
            "gold_eligible": False,
            "patch_eligible": False,
        }
        fields = {
            "scenario_ref", "tree_digest", "request_digest", "category",
            "expected_route", "acceptable_profiles", "target_status",
            "acceptable_node_ids", "forbidden_node_ids", "clarification_policy",
            "frozen_clarification_answer", "acceptable_policy_statuses",
            "acceptable_terminals", "wrong_context_challenge", "review_status",
            "reviewed_bytes_digest", "execution_eligible", "oracle_hash",
        }
        if not isinstance(payload, dict) or set(payload) != set(constants) | fields:
            raise SealedEvaluationError(
                "SEALED_ORACLE_FIELDS_INVALID", "Oracle must use exact fields"
            )
        if any(payload.get(key) != value for key, value in constants.items()):
            raise SealedEvaluationError(
                "SEALED_ORACLE_TRUST_INVALID", "Oracle trust constants changed"
            )
        for name in (
            "acceptable_profiles", "acceptable_node_ids", "forbidden_node_ids",
            "acceptable_policy_statuses", "acceptable_terminals",
        ):
            if not isinstance(payload[name], list):
                raise SealedEvaluationError(
                    "SEALED_ORACLE_FIELDS_INVALID", "Oracle collections must be arrays"
                )
        try:
            return cls(
                scenario_ref=payload["scenario_ref"],
                tree_digest=payload["tree_digest"],
                request_digest=payload["request_digest"],
                category=payload["category"],
                expected_route=payload["expected_route"],
                acceptable_profiles=tuple(
                    StructuralProfile.from_dict(item) for item in payload["acceptable_profiles"]
                ),
                target_status=payload["target_status"],
                acceptable_node_ids=tuple(payload["acceptable_node_ids"]),
                forbidden_node_ids=tuple(payload["forbidden_node_ids"]),
                clarification_policy=payload["clarification_policy"],
                frozen_clarification_answer=payload["frozen_clarification_answer"],
                acceptable_policy_statuses=tuple(payload["acceptable_policy_statuses"]),
                acceptable_terminals=tuple(
                    TerminalExpectation.from_dict(item) for item in payload["acceptable_terminals"]
                ),
                wrong_context_challenge=payload["wrong_context_challenge"],
                review_status=payload["review_status"],
                reviewed_bytes_digest=payload["reviewed_bytes_digest"],
                execution_eligible=payload["execution_eligible"],
                oracle_hash=payload["oracle_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise SealedEvaluationError(
                "SEALED_ORACLE_INVALID", "Oracle failed strict validation"
            ) from None


def validate_sealed_plan(
    manifest: SealedEvaluationManifest,
    scenarios: tuple[SealedScenario, ...],
    oracles: tuple[SealedCaseOracle, ...],
) -> None:
    """Validate the frozen cross-file denominator before any product execution."""

    if (
        not isinstance(manifest, SealedEvaluationManifest)
        or not isinstance(scenarios, tuple)
        or not isinstance(oracles, tuple)
        or any(not isinstance(item, SealedScenario) for item in scenarios)
        or any(not isinstance(item, SealedCaseOracle) for item in oracles)
    ):
        raise SealedEvaluationError(
            "SEALED_PLAN_FIELDS_INVALID", "sealed plan requires trusted contracts"
        )
    scenario_refs = tuple(item.scenario_ref for item in scenarios)
    oracle_refs = tuple(item.scenario_ref for item in oracles)
    if (
        scenario_refs != manifest.scenario_refs
        or oracle_refs != manifest.scenario_refs
        or len(set(scenario_refs)) != len(scenario_refs)
    ):
        raise SealedEvaluationError(
            "SEALED_PLAN_REFERENCE_INVALID", "sealed plan references do not align"
        )
    oracle_by_ref = {item.scenario_ref: item for item in oracles}
    for scenario in scenarios:
        oracle = oracle_by_ref[scenario.scenario_ref]
        if (
            oracle.tree_digest != scenario.tree_digest
            or oracle.request_digest != scenario.request_digest
            or oracle.category != scenario.category
            or oracle.wrong_context_challenge != scenario.wrong_context_challenge
            or oracle.frozen_clarification_answer
            != scenario.frozen_clarification_answer
            or (scenario.scenario_ref in manifest.repeat_scenario_refs)
            != scenario.repeat_challenge
        ):
            raise SealedEvaluationError(
                "SEALED_PLAN_SOURCE_INVALID", "sealed scenario and Oracle do not align"
            )
    category_counts = Counter(item.category for item in scenarios)
    target_present_count = sum(
        item.target_status == "TARGET_PRESENT" for item in oracles
    )
    wrong_context_count = sum(
        scenario.wrong_context_challenge
        and oracle_by_ref[scenario.scenario_ref].target_status == "TARGET_PRESENT"
        for scenario in scenarios
    )
    repeat_categories = Counter(
        scenario.category
        for scenario in scenarios
        if scenario.scenario_ref in manifest.repeat_scenario_refs
    )
    if (
        category_counts != Counter(CATEGORY_QUOTAS)
        or target_present_count != TARGET_PRESENT_COUNT
        or wrong_context_count != WRONG_CONTEXT_COUNT
        or repeat_categories
        != Counter(
            {
                "NONLITERAL_UNIQUE": 4,
                "STRUCTURAL_INTERFERENCE": 4,
                "CLARIFICATION": 4,
                "WEAK_EVIDENCE": 4,
            }
        )
    ):
        raise SealedEvaluationError(
            "SEALED_PLAN_QUOTA_INVALID", "sealed plan denominator is not frozen"
        )


@dataclass(frozen=True, slots=True)
class SealedCaseTrace:
    scenario_ref: str
    round_index: int
    tree_digest: str
    request_digest: str
    provider_mode: str
    run_status: str
    failure_code: str | None
    failure_stage: str | None
    logical_model_stage_count: int
    wire_attempt_count: int
    sidecar_complete: bool
    interpretation_status: str | None
    observed_route: str | None
    observed_profile: StructuralProfile | None
    r0_candidate_node_ids: tuple[str, ...]
    c1_candidate_node_ids: tuple[str, ...]
    policy_status: str | None
    semantic_status: str | None
    highlighted_node_id: str | None
    outcome: TerminalExpectation | None
    trace_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_ref, str) or _REF.fullmatch(self.scenario_ref) is None:
            raise ValueError("trace scenario reference is invalid")
        if self.round_index not in (1, 2, 3):
            raise ValueError("trace round index is invalid")
        _digest(self.tree_digest, "tree_digest")
        _digest(self.request_digest, "request_digest")
        if self.provider_mode != PROVIDER_MODE or self.run_status not in RUN_STATUSES:
            raise ValueError("trace provider or run status is invalid")
        if self.failure_code is not None and (
            not isinstance(self.failure_code, str) or _CODE.fullmatch(self.failure_code) is None
        ):
            raise ValueError("trace failure code is invalid")
        if self.failure_stage not in (STAGES - {"NONE", "REPEATABILITY"}) | {None}:
            raise ValueError("trace failure stage is invalid")
        _integer(self.logical_model_stage_count, "logical_model_stage_count")
        _integer(self.wire_attempt_count, "wire_attempt_count")
        if self.logical_model_stage_count > PER_CASE_MODEL_STAGE_LIMIT:
            raise ValueError("trace exceeds per-case model stage limit")
        if self.wire_attempt_count > self.logical_model_stage_count * 2:
            raise ValueError("trace exceeds per-stage wire attempt limit")
        if not isinstance(self.sidecar_complete, bool):
            raise ValueError("sidecar completeness must be boolean")
        if self.interpretation_status not in {None, "MODEL_VALID", "MODEL_DEGRADED"}:
            raise ValueError("trace interpretation status is invalid")
        if self.observed_route not in EXPECTED_ROUTES | {None}:
            raise ValueError("trace route is invalid")
        if self.observed_profile is not None and not isinstance(
            self.observed_profile, StructuralProfile
        ):
            raise ValueError("trace profile is invalid")
        for name, values, limit in (
            ("r0_candidate_node_ids", self.r0_candidate_node_ids, 40),
            ("c1_candidate_node_ids", self.c1_candidate_node_ids, 40),
        ):
            if (
                not isinstance(values, tuple)
                or len(values) > limit
                or len(set(values)) != len(values)
                or any(not isinstance(item, str) or not item for item in values)
            ):
                raise ValueError(f"{name} is invalid")
        if self.policy_status not in POLICY_STATUSES | {None}:
            raise ValueError("trace policy status is invalid")
        if self.semantic_status not in {
            None,
            "SUCCEEDED",
            "SKIPPED_CLARIFICATION_PATH",
            "DEGRADED",
            "NOT_APPLICABLE",
        }:
            raise ValueError("trace semantic status is invalid")
        if self.highlighted_node_id is not None:
            _text(self.highlighted_node_id, "highlighted_node_id", maximum=512)
        if self.outcome is not None and not isinstance(self.outcome, TerminalExpectation):
            raise ValueError("trace outcome is invalid")
        complete_fields = (
            self.interpretation_status is not None
            and self.observed_route is not None
            and self.policy_status is not None
            and self.semantic_status is not None
            and self.outcome is not None
            and self.sidecar_complete
        )
        if self.run_status == "COMPLETE":
            if (
                self.failure_code is not None
                or self.failure_stage is not None
                or not complete_fields
            ):
                raise ValueError("complete trace is missing product artifacts")
        elif self.failure_code is None or self.failure_stage is None or complete_fields:
            raise ValueError("failed/unrun trace is inconsistent")
        _digest(self.trace_hash, "trace_hash")
        if self.trace_hash != canonical_digest(self._payload()):
            raise ValueError("trace hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "scenario_ref": self.scenario_ref,
            "round_index": self.round_index,
            "tree_digest": self.tree_digest,
            "request_digest": self.request_digest,
            "provider_mode": self.provider_mode,
            "run_status": self.run_status,
            "failure_code": self.failure_code,
            "failure_stage": self.failure_stage,
            "logical_model_stage_count": self.logical_model_stage_count,
            "wire_attempt_count": self.wire_attempt_count,
            "sidecar_complete": self.sidecar_complete,
            "interpretation_status": self.interpretation_status,
            "observed_route": self.observed_route,
            "observed_profile": self.observed_profile.to_dict() if self.observed_profile else None,
            "r0_candidate_node_ids": list(self.r0_candidate_node_ids),
            "c1_candidate_node_ids": list(self.c1_candidate_node_ids),
            "policy_status": self.policy_status,
            "semantic_status": self.semantic_status,
            "highlighted_node_id": self.highlighted_node_id,
            "outcome": self.outcome.to_dict() if self.outcome else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "trace_hash": self.trace_hash}

    @classmethod
    def create(cls, **values: Any) -> "SealedCaseTrace":
        return cls(**values, trace_hash=_creation_digest(cls, values))

    @classmethod
    def from_dict(cls, payload: Any) -> "SealedCaseTrace":
        expected = {
            "schema_version", "scenario_ref", "round_index", "tree_digest",
            "request_digest", "provider_mode", "run_status", "failure_code",
            "failure_stage",
            "logical_model_stage_count", "wire_attempt_count", "sidecar_complete",
            "interpretation_status", "observed_route", "observed_profile",
            "r0_candidate_node_ids", "c1_candidate_node_ids", "policy_status",
            "semantic_status", "highlighted_node_id", "outcome", "trace_hash",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != expected
            or payload.get("schema_version") != TRACE_SCHEMA_VERSION
            or not isinstance(payload.get("r0_candidate_node_ids"), list)
            or not isinstance(payload.get("c1_candidate_node_ids"), list)
        ):
            raise SealedEvaluationError(
                "SEALED_TRACE_FIELDS_INVALID", "trace must use exact fields"
            )
        try:
            return cls(
                scenario_ref=payload["scenario_ref"],
                round_index=payload["round_index"],
                tree_digest=payload["tree_digest"],
                request_digest=payload["request_digest"],
                provider_mode=payload["provider_mode"],
                run_status=payload["run_status"],
                failure_code=payload["failure_code"],
                failure_stage=payload["failure_stage"],
                logical_model_stage_count=payload["logical_model_stage_count"],
                wire_attempt_count=payload["wire_attempt_count"],
                sidecar_complete=payload["sidecar_complete"],
                interpretation_status=payload["interpretation_status"],
                observed_route=payload["observed_route"],
                observed_profile=(
                    StructuralProfile.from_dict(payload["observed_profile"])
                    if payload["observed_profile"] is not None
                    else None
                ),
                r0_candidate_node_ids=tuple(payload["r0_candidate_node_ids"]),
                c1_candidate_node_ids=tuple(payload["c1_candidate_node_ids"]),
                policy_status=payload["policy_status"],
                semantic_status=payload["semantic_status"],
                highlighted_node_id=payload["highlighted_node_id"],
                outcome=(
                    TerminalExpectation.from_dict(payload["outcome"])
                    if payload["outcome"] is not None
                    else None
                ),
                trace_hash=payload["trace_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise SealedEvaluationError(
                "SEALED_TRACE_INVALID", "trace failed strict validation"
            ) from None


@dataclass(frozen=True, slots=True)
class SealedCaseObservation:
    scenario_ref: str
    round_index: int
    source_oracle_hash: str
    source_trace_hash: str
    category: str
    wrong_context_challenge: bool
    target_present: bool
    r0_rank: int | None
    c1_rank: int | None
    observed_policy_status: str | None
    profile_match: bool
    clarification_match: bool
    understanding_model_degraded: bool
    semantic_model_degraded: bool
    model_degraded: bool
    highlighted: bool
    highlighted_correct: bool
    absent_confident_error: bool
    policy_match: bool
    terminal_match: bool
    joint_match: bool
    no_degradation_path: bool
    first_failure_stage: str
    finding_codes: tuple[str, ...]
    observation_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_ref, str) or _REF.fullmatch(self.scenario_ref) is None:
            raise ValueError("observation scenario ref is invalid")
        if self.round_index not in (1, 2, 3):
            raise ValueError("observation round index is invalid")
        _digest(self.source_oracle_hash, "source_oracle_hash")
        _digest(self.source_trace_hash, "source_trace_hash")
        if self.category not in CATEGORIES:
            raise ValueError("observation category is invalid")
        if self.observed_policy_status not in POLICY_STATUSES | {None}:
            raise ValueError("observation policy status is invalid")
        for rank in (self.r0_rank, self.c1_rank):
            if rank is not None and (
                not isinstance(rank, int) or isinstance(rank, bool) or not 1 <= rank <= 40
            ):
                raise ValueError("observation candidate rank is invalid")
        for name in (
            "wrong_context_challenge", "target_present", "profile_match",
            "clarification_match", "understanding_model_degraded",
            "semantic_model_degraded", "model_degraded",
            "highlighted", "highlighted_correct", "absent_confident_error",
            "policy_match", "terminal_match", "joint_match", "no_degradation_path",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        if not self.target_present and (self.r0_rank is not None or self.c1_rank is not None):
            raise ValueError("absent target cannot have a retrieval rank")
        if self.highlighted_correct and not self.highlighted:
            raise ValueError("correct highlight requires a highlight")
        if self.model_degraded != (
            self.understanding_model_degraded or self.semantic_model_degraded
        ):
            raise ValueError("combined model degradation does not match its stages")
        if self.first_failure_stage not in STAGES:
            raise ValueError("observation failure stage is invalid")
        _ordered_strings(self.finding_codes, "finding_codes")
        if any(_CODE.fullmatch(code) is None for code in self.finding_codes):
            raise ValueError("observation finding code is invalid")
        _digest(self.observation_hash, "observation_hash")
        if self.observation_hash != canonical_digest(self._payload()):
            raise ValueError("observation hash does not match")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "scenario_ref": self.scenario_ref,
            "round_index": self.round_index,
            "source_oracle_hash": self.source_oracle_hash,
            "source_trace_hash": self.source_trace_hash,
            "category": self.category,
            "wrong_context_challenge": self.wrong_context_challenge,
            "target_present": self.target_present,
            "r0_rank": self.r0_rank,
            "c1_rank": self.c1_rank,
            "observed_policy_status": self.observed_policy_status,
            "profile_match": self.profile_match,
            "clarification_match": self.clarification_match,
            "understanding_model_degraded": self.understanding_model_degraded,
            "semantic_model_degraded": self.semantic_model_degraded,
            "model_degraded": self.model_degraded,
            "highlighted": self.highlighted,
            "highlighted_correct": self.highlighted_correct,
            "absent_confident_error": self.absent_confident_error,
            "policy_match": self.policy_match,
            "terminal_match": self.terminal_match,
            "joint_match": self.joint_match,
            "no_degradation_path": self.no_degradation_path,
            "first_failure_stage": self.first_failure_stage,
            "finding_codes": list(self.finding_codes),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "observation_hash": self.observation_hash}

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        *,
        oracle: SealedCaseOracle,
        trace: SealedCaseTrace,
    ) -> "SealedCaseObservation":
        expected = score_sealed_case(oracle, trace)
        if not isinstance(payload, dict) or expected.to_dict() != payload:
            raise SealedEvaluationError(
                "SEALED_OBSERVATION_REPLAY_MISMATCH",
                "observation does not replay trusted Oracle and trace",
            )
        return expected


def _rank(candidates: tuple[str, ...], acceptable: tuple[str, ...]) -> int | None:
    accepted = set(acceptable)
    return next(
        (index for index, node_id in enumerate(candidates, start=1) if node_id in accepted),
        None,
    )


def score_sealed_case(
    oracle: SealedCaseOracle,
    trace: SealedCaseTrace,
) -> SealedCaseObservation:
    if not isinstance(oracle, SealedCaseOracle) or not isinstance(trace, SealedCaseTrace):
        raise TypeError("sealed scoring requires trusted Oracle and trace contracts")
    if (
        oracle.scenario_ref != trace.scenario_ref
        or oracle.tree_digest != trace.tree_digest
        or oracle.request_digest != trace.request_digest
    ):
        raise SealedEvaluationError(
            "SEALED_SCORING_SOURCE_MISMATCH", "Oracle and trace sources do not align"
        )
    target_present = oracle.target_status == "TARGET_PRESENT"
    r0_rank = _rank(trace.r0_candidate_node_ids, oracle.acceptable_node_ids) if target_present else None
    c1_rank = _rank(trace.c1_candidate_node_ids, oracle.acceptable_node_ids) if target_present else None
    profile_match = not oracle.acceptable_profiles or trace.observed_profile in oracle.acceptable_profiles
    clarification_match = trace.observed_route == oracle.expected_route
    highlighted = trace.highlighted_node_id is not None
    highlighted_correct = highlighted and trace.highlighted_node_id in oracle.acceptable_node_ids
    absent_confident_error = not target_present and (
        highlighted or trace.policy_status == "CANDIDATES_AVAILABLE"
    )
    policy_match = trace.policy_status in oracle.acceptable_policy_statuses
    terminal_match = trace.outcome in oracle.acceptable_terminals
    understanding_model_degraded = trace.interpretation_status == "MODEL_DEGRADED"
    semantic_model_degraded = trace.semantic_status == "DEGRADED"
    model_degraded = understanding_model_degraded or semantic_model_degraded
    complete = trace.run_status == "COMPLETE"
    joint_match = complete and clarification_match and policy_match and terminal_match
    no_degradation_path = complete and not model_degraded

    findings: list[str] = []
    if not complete:
        findings.append(f"SEALED_{trace.run_status}")
        first_stage = trace.failure_stage or "UNDERSTANDING"
    elif not clarification_match or not profile_match:
        findings.append("SEALED_UNDERSTANDING_MISMATCH")
        first_stage = "UNDERSTANDING"
    elif target_present and (c1_rank is None or c1_rank > 8):
        findings.append("SEALED_C1_TOP8_MISS")
        first_stage = "RETRIEVAL"
    elif absent_confident_error or (highlighted and not highlighted_correct):
        findings.append("SEALED_SEMANTIC_MISMATCH")
        first_stage = "SEMANTIC"
    elif not policy_match:
        findings.append("SEALED_POLICY_MISMATCH")
        first_stage = "POLICY"
    elif not terminal_match:
        findings.append("SEALED_TERMINAL_MISMATCH")
        first_stage = "END_TO_END"
    else:
        first_stage = "NONE"
    if target_present and r0_rank is not None and r0_rank <= 8 and (c1_rank is None or c1_rank > 8):
        findings.append("SEALED_C1_HARMED_TOP8")
    if target_present and (r0_rank is None or r0_rank > 8) and c1_rank is not None and c1_rank <= 8:
        findings.append("SEALED_C1_HELPED_TOP8")
    values = {
        "scenario_ref": oracle.scenario_ref,
        "round_index": trace.round_index,
        "source_oracle_hash": oracle.oracle_hash,
        "source_trace_hash": trace.trace_hash,
        "category": oracle.category,
        "wrong_context_challenge": oracle.wrong_context_challenge,
        "target_present": target_present,
        "r0_rank": r0_rank,
        "c1_rank": c1_rank,
        "observed_policy_status": trace.policy_status,
        "profile_match": profile_match,
        "clarification_match": clarification_match,
        "understanding_model_degraded": understanding_model_degraded,
        "semantic_model_degraded": semantic_model_degraded,
        "model_degraded": model_degraded,
        "highlighted": highlighted,
        "highlighted_correct": highlighted_correct,
        "absent_confident_error": absent_confident_error,
        "policy_match": policy_match,
        "terminal_match": terminal_match,
        "joint_match": joint_match,
        "no_degradation_path": no_degradation_path,
        "first_failure_stage": first_stage,
        "finding_codes": tuple(sorted(set(findings))),
    }
    return SealedCaseObservation(
        **values,
        observation_hash=_creation_digest(SealedCaseObservation, values),
    )


def public_sealed_aggregate(
    manifest: SealedEvaluationManifest,
    observations: tuple[SealedCaseObservation, ...],
    *,
    run_integrity_valid: bool,
) -> dict[str, Any]:
    """Aggregate private observations into the fixed public allowlist."""

    if not isinstance(manifest, SealedEvaluationManifest):
        raise TypeError("sealed aggregate requires a trusted manifest")
    if not isinstance(observations, tuple) or any(
        not isinstance(item, SealedCaseObservation) for item in observations
    ):
        raise SealedEvaluationError(
            "SEALED_OBSERVATIONS_INVALID", "observations must be an immutable tuple"
        )
    if not isinstance(run_integrity_valid, bool):
        raise ValueError("run_integrity_valid must be boolean")
    keys = tuple((item.scenario_ref, item.round_index) for item in observations)
    if len(set(keys)) != len(keys):
        raise SealedEvaluationError(
            "SEALED_OBSERVATION_DUPLICATE", "scenario rounds must be unique"
        )
    primary = {item.scenario_ref: item for item in observations if item.round_index == 1}
    repeats = {
        ref: tuple(
            sorted(
                (item for item in observations if item.scenario_ref == ref),
                key=lambda item: item.round_index,
            )
        )
        for ref in manifest.repeat_scenario_refs
    }
    complete_denominator = set(primary) == set(manifest.scenario_refs)
    repeat_denominator = all(
        tuple(item.round_index for item in items) == (1, 2, 3)
        for items in repeats.values()
    )
    ordered = tuple(primary[ref] for ref in manifest.scenario_refs if ref in primary)
    target = tuple(item for item in ordered if item.target_present)
    absent = tuple(item for item in ordered if not item.target_present)
    category_counts = {
        category: sum(item.category == category for item in ordered)
        for category in sorted(CATEGORIES)
    }
    data_valid = (
        complete_denominator
        and repeat_denominator
        and len(target) == TARGET_PRESENT_COUNT
        and category_counts == dict(sorted(CATEGORY_QUOTAS.items()))
        and sum(item.wrong_context_challenge for item in target) == 8
        and all(
            sum(
                primary[ref].category == category
                for ref in manifest.repeat_scenario_refs
            ) == 4
            for category in (
                "NONLITERAL_UNIQUE",
                "STRUCTURAL_INTERFERENCE",
                "CLARIFICATION",
                "WEAK_EVIDENCE",
            )
        )
        and run_integrity_valid
    )
    r0_top40 = sum(item.r0_rank is not None and item.r0_rank <= 40 for item in target)
    r0_top8 = sum(item.r0_rank is not None and item.r0_rank <= 8 for item in target)
    c1_top8 = sum(item.c1_rank is not None and item.c1_rank <= 8 for item in target)
    c1_top40 = sum(item.c1_rank is not None and item.c1_rank <= 40 for item in target)
    helped = sum("SEALED_C1_HELPED_TOP8" in item.finding_codes for item in target)
    harmed = sum("SEALED_C1_HARMED_TOP8" in item.finding_codes for item in target)
    highlighted = tuple(item for item in ordered if item.highlighted)
    correct_highlights = sum(item.highlighted_correct for item in highlighted)
    highlight_precision_bps = (
        correct_highlights * 10_000 // len(highlighted) if highlighted else 0
    )
    r0_mrr_units = sum(
        840 // item.r0_rank
        for item in target
        if item.r0_rank is not None and item.r0_rank <= 8
    )
    c1_mrr_units = sum(
        840 // item.c1_rank
        for item in target
        if item.c1_rank is not None and item.c1_rank <= 8
    )
    repeat_stable = 0
    for items in repeats.values():
        signatures = [
            (
                item.c1_rank is not None and item.c1_rank <= 8,
                item.observed_policy_status,
            )
            for item in items
        ]
        repeat_stable += any(signatures.count(value) >= 2 for value in set(signatures))
    thresholds = manifest.thresholds
    retrieval_pass = (
        c1_top40 >= thresholds.min_top40_hits
        and c1_top8 >= thresholds.min_top8_hits
        and sum(
            item.c1_rank is not None and item.c1_rank <= 8
            for item in target if item.category == "NONLITERAL_UNIQUE"
        ) >= thresholds.min_nonliteral_top8_hits
        and sum(
            item.c1_rank is not None and item.c1_rank <= 8
            for item in target if item.category == "STRUCTURAL_INTERFERENCE"
        ) >= thresholds.min_interference_top8_hits
        and sum(
            item.c1_rank is not None and item.c1_rank <= 8
            for item in target if item.category == "CLARIFICATION"
        ) >= thresholds.min_clarification_top8_hits
        and sum(
            item.c1_rank is not None and item.c1_rank <= 8
            for item in target if item.wrong_context_challenge
        ) >= thresholds.min_wrong_context_top8_hits
        and r0_top8 - c1_top8 <= thresholds.max_c1_top8_loss_from_r0
    )
    semantic_policy_pass = (
        sum(item.absent_confident_error for item in absent)
        <= thresholds.max_absent_confident_errors
        and highlight_precision_bps
        >= thresholds.min_highlight_precision_numerator_bps
        and correct_highlights >= thresholds.min_correct_highlight_count
        and sum(item.joint_match for item in ordered)
        >= thresholds.min_joint_match_count
        and sum(
            item.clarification_match
            for item in ordered if item.category == "CLARIFICATION"
        ) >= thresholds.min_required_clarification_match_count
        and repeat_stable >= thresholds.min_repeat_stable_count
    )
    model_contract_pass = (
        sum(item.no_degradation_path for item in ordered)
        >= thresholds.min_no_degradation_count
        and sum(
            item.category != "CLARIFICATION" and not item.clarification_match
            for item in ordered
        ) <= thresholds.max_needless_clarification_count
    )
    if not complete_denominator or not repeat_denominator:
        qualification = "INCONCLUSIVE"
    elif not data_valid:
        qualification = "DATA_OR_RUN_INVALID"
    elif not model_contract_pass:
        qualification = "HOLD_MODEL_CONTRACT"
    elif not retrieval_pass:
        qualification = "HOLD_RETRIEVAL"
    elif not semantic_policy_pass:
        qualification = "HOLD_SEMANTIC_POLICY"
    else:
        qualification = "READY_FOR_PROTECTED_SHADOW"
    if qualification not in QUALIFICATION_STATUSES:
        raise AssertionError("sealed qualification status is unsupported")
    stage_counts = {
        stage: sum(item.first_failure_stage == stage for item in ordered)
        for stage in sorted(STAGES)
    }
    stage_counts["REPEATABILITY"] = REPEAT_FAMILY_COUNT - repeat_stable
    payload = {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "threshold_policy_version": THRESHOLD_POLICY_VERSION,
        "source_manifest_hash": manifest.manifest_hash,
        "qualification_status": qualification,
        "main_case_count": len(ordered),
        "target_present_count": len(target),
        "category_counts": category_counts,
        "r0_top40_hit_count": r0_top40,
        "r0_top8_hit_count": r0_top8,
        "r0_mrr_at8_bps": r0_mrr_units * 10_000 // (TARGET_PRESENT_COUNT * 840),
        "c1_top40_hit_count": c1_top40,
        "c1_top8_hit_count": c1_top8,
        "c1_mrr_at8_bps": c1_mrr_units * 10_000 // (TARGET_PRESENT_COUNT * 840),
        "c1_helped_top8_count": helped,
        "c1_harmed_top8_count": harmed,
        "highlighted_count": len(highlighted),
        "correct_highlight_count": correct_highlights,
        "highlight_precision_bps": highlight_precision_bps,
        "absent_confident_error_count": sum(item.absent_confident_error for item in absent),
        "no_degradation_count": sum(item.no_degradation_path for item in ordered),
        "joint_match_count": sum(item.joint_match for item in ordered),
        "repeat_family_count": len(repeats),
        "repeat_stable_count": repeat_stable,
        "first_failure_stage_counts": stage_counts,
        "production_write_enabled": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }
    return {**payload, "aggregate_hash": canonical_digest(payload)}


def replay_public_sealed_aggregate(
    payload: Any,
    manifest: SealedEvaluationManifest,
    observations: tuple[SealedCaseObservation, ...],
    *,
    run_integrity_valid: bool,
) -> dict[str, Any]:
    """Strictly reconstruct an aggregate from its trusted private sources."""

    expected = public_sealed_aggregate(
        manifest,
        observations,
        run_integrity_valid=run_integrity_valid,
    )
    if not isinstance(payload, dict) or payload != expected:
        raise SealedEvaluationError(
            "SEALED_AGGREGATE_REPLAY_MISMATCH",
            "aggregate does not replay trusted observations",
        )
    return expected


def public_sealed_diagnostic_aggregate(
    manifest: SealedEvaluationManifest,
    observations: tuple[SealedCaseObservation, ...],
) -> dict[str, Any]:
    """Build independent diagnostic counts without changing qualification v1."""

    if not isinstance(manifest, SealedEvaluationManifest):
        raise TypeError("sealed diagnostic aggregate requires a trusted manifest")
    if not isinstance(observations, tuple) or any(
        not isinstance(item, SealedCaseObservation) for item in observations
    ):
        raise SealedEvaluationError(
            "SEALED_DIAGNOSTIC_OBSERVATIONS_INVALID",
            "diagnostic observations must be an immutable tuple",
        )
    keys = tuple((item.scenario_ref, item.round_index) for item in observations)
    if len(set(keys)) != len(keys):
        raise SealedEvaluationError(
            "SEALED_DIAGNOSTIC_DENOMINATOR_INVALID",
            "diagnostic scenario rounds must be unique",
        )
    scenario_refs = set(manifest.scenario_refs)
    repeat_refs = set(manifest.repeat_scenario_refs)
    if any(
        item.scenario_ref not in scenario_refs
        or (item.round_index != 1 and item.scenario_ref not in repeat_refs)
        for item in observations
    ):
        raise SealedEvaluationError(
            "SEALED_DIAGNOSTIC_DENOMINATOR_INVALID",
            "diagnostic observations are outside the frozen manifest",
        )
    primary = {item.scenario_ref: item for item in observations if item.round_index == 1}
    if set(primary) != scenario_refs:
        raise SealedEvaluationError(
            "SEALED_DIAGNOSTIC_DENOMINATOR_INVALID",
            "diagnostic aggregate requires the complete main denominator",
        )
    ordered = tuple(primary[ref] for ref in manifest.scenario_refs)
    payload = {
        "schema_version": DIAGNOSTIC_AGGREGATE_SCHEMA_VERSION,
        "source_manifest_hash": manifest.manifest_hash,
        "source_observation_schema_version": OBSERVATION_SCHEMA_VERSION,
        "main_case_count": len(ordered),
        "understanding_model_degraded_count": sum(
            item.understanding_model_degraded for item in ordered
        ),
        "semantic_model_degraded_count": sum(
            item.semantic_model_degraded for item in ordered
        ),
        "understanding_profile_mismatch_count": sum(
            not item.profile_match for item in ordered
        ),
        "product_route_mismatch_count": sum(
            not item.clarification_match for item in ordered
        ),
        "retrieval_top8_miss_count": sum(
            item.target_present and (item.c1_rank is None or item.c1_rank > 8)
            for item in ordered
        ),
        "semantic_mismatch_count": sum(
            item.absent_confident_error
            or (item.highlighted and not item.highlighted_correct)
            for item in ordered
        ),
        "policy_mismatch_count": sum(not item.policy_match for item in ordered),
        "terminal_mismatch_count": sum(
            not item.terminal_match for item in ordered
        ),
        "joint_match_count": sum(item.joint_match for item in ordered),
        "no_degradation_path_count": sum(
            item.no_degradation_path for item in ordered
        ),
        "counts_are_independent": True,
        "diagnostic_only": True,
        "qualification_effect": False,
        "production_write_enabled": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }
    return {**payload, "diagnostic_aggregate_hash": canonical_digest(payload)}


def replay_public_sealed_diagnostic_aggregate(
    payload: Any,
    manifest: SealedEvaluationManifest,
    observations: tuple[SealedCaseObservation, ...],
) -> dict[str, Any]:
    """Strictly replay a diagnostic aggregate from trusted observations."""

    expected = public_sealed_diagnostic_aggregate(manifest, observations)
    if not isinstance(payload, dict) or payload != expected:
        raise SealedEvaluationError(
            "SEALED_DIAGNOSTIC_AGGREGATE_REPLAY_MISMATCH",
            "diagnostic aggregate does not replay trusted observations",
        )
    return expected


__all__ = [
    "AGGREGATE_SCHEMA_VERSION",
    "DIAGNOSTIC_AGGREGATE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "OBSERVATION_SCHEMA_VERSION",
    "ORACLE_SCHEMA_VERSION",
    "SealedCaseObservation",
    "SealedCaseOracle",
    "SealedCaseTrace",
    "SealedEvaluationError",
    "SealedEvaluationManifest",
    "SealedEvaluationThresholds",
    "SealedScenario",
    "StructuralProfile",
    "TerminalExpectation",
    "validate_sealed_plan",
    "public_sealed_aggregate",
    "public_sealed_diagnostic_aggregate",
    "replay_public_sealed_aggregate",
    "replay_public_sealed_diagnostic_aggregate",
    "score_sealed_case",
]
