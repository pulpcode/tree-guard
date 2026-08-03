"""Source-bound M4 capability validation without creating semantic Gold.

The M3 scenario contracts remain unchanged.  This module adds an independent
overlay that freezes a complete, human-reviewed validation Oracle, executes the
existing intent/retrieval/recommendation boundaries, and emits an aggregate-only
go/no-go report for controlled Shadow validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from treeguard.change_intent import (
    REQUEST_SCHEMA_VERSION,
    ChangeIntentDraft,
    IntentRequest,
    IntentReviewAction,
    IntentValidationError,
    apply_intent_review,
    verify_intent_draft_against_sources,
)
from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree
from treeguard.retrieval import (
    CandidateRetrievalError,
    CandidateSet,
    build_candidate_set,
)
from treeguard.scenario_validation import (
    ReviewedValidationScenario,
    ScenarioReviewAction,
    ScenarioValidationError,
    verify_reviewed_validation_scenario_against_sources,
)
from treeguard.semantic_recommendation import (
    CANDIDATE_RELATIONS,
    RECOMMENDED_ACTIONS,
    SemanticRecommendationDraft,
    SemanticRecommendationError,
)
from treeguard.tree_understanding import (
    ScenarioPreparationBatch,
    ScenarioPreparationBatchCandidate,
    ScenarioPreparationPlan,
    ScenarioPreparationProjection,
    TreeDiagnosticProfile,
)


CAPABILITY_OVERLAY_SCHEMA_VERSION = "scenario-capability-overlay.v1"
CAPABILITY_SILVER_AUTHORIZATION_SCHEMA_VERSION = (
    "scenario-capability-silver-authorization.v1"
)
CAPABILITY_RUN_SCHEMA_VERSION = "scenario-capability-run.v1"
CAPABILITY_REPORT_SCHEMA_VERSION = "scenario-capability-report.v1"
CAPABILITY_ORACLE_REQUEST_POLICY_VERSION = (
    "treeguard.capability-oracle-request-policy.v1"
)

SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
IDENTITY_STATUS = "UNVERIFIED_FILE_ASSERTION"
OVERLAY_REVIEW_STATUSES = {"ACCEPTED", "REVISED_ACCEPTED"}
SILVER_AUTHORIZATION_STATUS = "SILVER_ACCEPTED"
SILVER_ASSESSMENT_AUTHORITY = "CODEX_ASSISTED"
EXPECTED_ROUTES = {"PROCEED", "CLARIFY"}
STAGE_STATUSES = {"MATCH", "MISMATCH", "NOT_RUN", "RUN_FAILED"}
STAGE_REASON_CODES = {
    "INTENT_ORACLE_MATCH",
    "INTENT_ORACLE_MISMATCH",
    "INTENT_PROVIDER_FAILED",
    "RETRIEVAL_ORACLE_MATCH",
    "RETRIEVAL_ORACLE_MISMATCH",
    "RETRIEVAL_RUN_FAILED",
    "RECOMMENDATION_ORACLE_MATCH",
    "RECOMMENDATION_ORACLE_MISMATCH",
    "RECOMMENDATION_PROVIDER_FAILED",
    "EXPECTED_CLARIFICATION_SHORT_CIRCUIT",
    "UPSTREAM_INTENT_MISMATCH",
    "UPSTREAM_INTENT_RUN_FAILED",
    "UPSTREAM_RETRIEVAL_MISMATCH",
    "UPSTREAM_RETRIEVAL_RUN_FAILED",
}
PUBLIC_HARD_FAILURE_CODES = {
    "CONTRACT_INTEGRITY_FAILURE",
    "DATA_BOUNDARY_FAILURE",
    "RESULT_ACCOUNTING_FAILURE",
    "SOURCE_BINDING_FAILURE",
}
FIELD_POLICIES = {"EMPTY", "EXACT_ONE_OF", "NON_EMPTY", "NOT_COMPARED"}
LIST_INTENT_FIELD_NAMES = {
    "assumptions",
    "confirmed_facts",
    "evidence_gaps",
}
UNBOUND_V1_INTENT_FIELD_NAMES = {
    "subject",
    "role",
    "scenario",
    "lifecycle",
    "ownership",
} | LIST_INTENT_FIELD_NAMES
STRUCTURED_REQUEST_INTENT_FIELDS = {
    "node_kind": "node_kind_hint",
    "value_type": "value_type_hint",
    "cardinality": "cardinality_hint",
}
INTENT_FIELD_NAMES = {
    "subject",
    "role",
    "scenario",
    "lifecycle",
    "ownership",
    "node_kind",
    "value_type",
    "cardinality",
    "clarification_question",
} | LIST_INTENT_FIELD_NAMES
RETRIEVAL_STATUSES = {
    "CANDIDATES_READY",
    "NO_CANDIDATES",
    "INSUFFICIENT_SIGNAL",
}
CLARIFICATION_COVERAGE_STATUSES = {
    "COVERED",
    "NOT_APPLICABLE_WITH_BACKFILL",
    "MISSING",
}
GATE_STATUSES = {"PASS", "FAIL"}
DECISIONS = {"GO_SHADOW", "NO_GO"}

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_PROFILE_REFERENCE = re.compile(r"^P(?:00[1-9]|0[1-9][0-9])$")
_PLAN_UNIT_REFERENCE = re.compile(r"^U(?:00[1-9]|0[12][0-9]|03[0-2])$")
_CANDIDATE_REFERENCE = re.compile(r"^C(?:00[1-9]|0[12][0-9]|03[0-2])$")
_FIXED_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)

_OVERLAY_KEYS = {
    "schema_version",
    "status",
    "identity_status",
    "source_class",
    "fictional",
    "derived_from_real",
    "semantic_approval",
    "gold_eligible",
    "patch_eligible",
    "source_reviewed_hash",
    "source_snapshot_hash",
    "source_plan_hash",
    "source_reviewed_content_hash",
    "reviewer_ref",
    "recorded_at",
    "review_round",
    "oracle",
    "overlay_hash",
}
_SILVER_AUTHORIZATION_KEYS = {
    "schema_version",
    "status",
    "quality_tier",
    "assessment_authority",
    "identity_status",
    "source_class",
    "fictional",
    "derived_from_real",
    "semantic_approval",
    "gold_eligible",
    "gate_eligible",
    "patch_eligible",
    "execution_scope",
    "source_reviewed_hash",
    "source_snapshot_hash",
    "source_plan_hash",
    "source_reviewed_content_hash",
    "assessor_ref",
    "recorded_at",
    "oracle",
    "authorization_hash",
}
_ORACLE_KEYS = {
    "expected_route",
    "acceptable_intent_profiles",
    "retrieval",
    "recommendation",
}
_PROFILE_KEYS = {"profile_ref", "field_expectations"}
_FIELD_EXPECTATION_KEYS = {
    "field_name",
    "policy",
    "acceptable_values",
}
_RETRIEVAL_ORACLE_KEYS = {
    "applicable",
    "allowed_statuses",
    "acceptable_node_ids",
    "top_k",
}
_RECOMMENDATION_ORACLE_KEYS = {"applicable", "acceptable_outcomes"}
_RECOMMENDATION_OUTCOME_KEYS = {"action", "target_node_id", "relation"}
_STAGE_RESULT_KEYS = {"applicable", "status", "reason_code"}
_RUN_KEYS = {
    "schema_version",
    "source_overlay_hash",
    "source_reviewed_hash",
    "source_snapshot_hash",
    "source_request_hash",
    "source_intent_draft_hash",
    "source_candidate_set_hash",
    "source_recommendation_draft_hash",
    "plan_unit_ref",
    "candidate_ref",
    "expected_route",
    "intent",
    "retrieval",
    "recommendation",
    "full_path_status",
    "run_hash",
}


class ScenarioCapabilityError(RuntimeError):
    """A capability validation artifact failed a stable local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class IntentCapabilityProvider(Protocol):
    def draft(
        self,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> ChangeIntentDraft: ...


class SemanticCapabilityProvider(Protocol):
    def recommend(
        self,
        confirmation: Any,
        candidate_set: CandidateSet,
        tree: CanonicalTree,
    ) -> SemanticRecommendationDraft: ...


@dataclass(frozen=True, slots=True)
class IntentFieldExpectation:
    """One deterministic scalar-field rule inside an acceptable intent profile."""

    field_name: str
    policy: str
    acceptable_values: tuple[str | None, ...]

    def __post_init__(self) -> None:
        if self.field_name not in INTENT_FIELD_NAMES:
            raise ValueError("unsupported intent Oracle field")
        if self.policy not in FIELD_POLICIES:
            raise ValueError("unsupported intent Oracle field policy")
        if (
            not isinstance(self.acceptable_values, tuple)
            or len(self.acceptable_values) > 32
            or any(
                value is not None
                and (not isinstance(value, str) or not value or len(value) > 1_000)
                for value in self.acceptable_values
            )
        ):
            raise ValueError("intent Oracle acceptable values are invalid")
        if len(self.acceptable_values) != len(set(self.acceptable_values)):
            raise ValueError("intent Oracle acceptable values must be unique")
        if self.acceptable_values != tuple(
            sorted(self.acceptable_values, key=_optional_text_sort_key)
        ):
            raise ValueError("intent Oracle acceptable values must be ordered")
        if self.policy == "EXACT_ONE_OF" and not self.acceptable_values:
            raise ValueError("EXACT_ONE_OF requires acceptable values")
        if self.policy != "EXACT_ONE_OF" and self.acceptable_values:
            raise ValueError("only EXACT_ONE_OF may contain acceptable values")
        if (
            self.field_name in LIST_INTENT_FIELD_NAMES
            and self.policy == "EXACT_ONE_OF"
        ):
            raise ValueError("list intent fields do not support scalar equality")
        if (
            self.field_name not in LIST_INTENT_FIELD_NAMES
            and self.policy == "EMPTY"
        ):
            raise ValueError("EMPTY is reserved for list intent fields")

    @classmethod
    def from_dict(cls, payload: Any) -> "IntentFieldExpectation":
        if not isinstance(payload, dict) or set(payload) != _FIELD_EXPECTATION_KEYS:
            raise ValueError("intent field expectation must use exact fields")
        if not isinstance(payload["acceptable_values"], list):
            raise ValueError("intent field acceptable_values must be an array")
        return cls(
            field_name=payload["field_name"],
            policy=payload["policy"],
            acceptable_values=tuple(payload["acceptable_values"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "policy": self.policy,
            "acceptable_values": list(self.acceptable_values),
        }


@dataclass(frozen=True, slots=True)
class IntentOracleProfile:
    """One complete acceptable intent interpretation."""

    profile_ref: str
    field_expectations: tuple[IntentFieldExpectation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profile_ref, str) or _PROFILE_REFERENCE.fullmatch(
            self.profile_ref
        ) is None:
            raise ValueError("intent Oracle profile_ref is invalid")
        if (
            not isinstance(self.field_expectations, tuple)
            or not self.field_expectations
            or len(self.field_expectations) > len(INTENT_FIELD_NAMES)
            or any(
                not isinstance(item, IntentFieldExpectation)
                for item in self.field_expectations
            )
        ):
            raise ValueError("intent Oracle field expectations are invalid")
        names = tuple(item.field_name for item in self.field_expectations)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("intent Oracle fields must be unique and ordered")

    @classmethod
    def from_dict(cls, payload: Any) -> "IntentOracleProfile":
        if not isinstance(payload, dict) or set(payload) != _PROFILE_KEYS:
            raise ValueError("intent Oracle profile must use exact fields")
        if not isinstance(payload["field_expectations"], list):
            raise ValueError("intent Oracle field_expectations must be an array")
        return cls(
            profile_ref=payload["profile_ref"],
            field_expectations=tuple(
                IntentFieldExpectation.from_dict(item)
                for item in payload["field_expectations"]
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_ref": self.profile_ref,
            "field_expectations": [
                item.to_dict() for item in self.field_expectations
            ],
        }


@dataclass(frozen=True, slots=True)
class RetrievalOracle:
    """Expected deterministic retrieval status and stable Hit@K targets."""

    applicable: bool
    allowed_statuses: tuple[str, ...]
    acceptable_node_ids: tuple[str, ...]
    top_k: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.applicable, bool):
            raise ValueError("retrieval Oracle applicability must be boolean")
        if (
            not isinstance(self.allowed_statuses, tuple)
            or any(item not in RETRIEVAL_STATUSES for item in self.allowed_statuses)
            or self.allowed_statuses != tuple(sorted(set(self.allowed_statuses)))
        ):
            raise ValueError("retrieval Oracle statuses must be unique and ordered")
        _validate_node_id_tuple(self.acceptable_node_ids)
        if not self.applicable:
            if self.allowed_statuses or self.acceptable_node_ids or self.top_k is not None:
                raise ValueError("non-applicable retrieval Oracle must be empty")
            return
        if not self.allowed_statuses:
            raise ValueError("applicable retrieval Oracle requires statuses")
        if (
            not isinstance(self.top_k, int)
            or isinstance(self.top_k, bool)
            or self.top_k < 1
            or self.top_k > 20
        ):
            raise ValueError("retrieval Oracle top_k must be between 1 and 20")
        if self.acceptable_node_ids:
            if self.allowed_statuses != ("CANDIDATES_READY",):
                raise ValueError("targeted retrieval Oracle must require ready candidates")
        elif any(status == "CANDIDATES_READY" for status in self.allowed_statuses):
            raise ValueError("empty-target retrieval Oracle cannot accept ready candidates")

    @classmethod
    def from_dict(cls, payload: Any) -> "RetrievalOracle":
        if not isinstance(payload, dict) or set(payload) != _RETRIEVAL_ORACLE_KEYS:
            raise ValueError("retrieval Oracle must use exact fields")
        if not isinstance(payload["allowed_statuses"], list) or not isinstance(
            payload["acceptable_node_ids"], list
        ):
            raise ValueError("retrieval Oracle collections must be arrays")
        return cls(
            applicable=payload["applicable"],
            allowed_statuses=tuple(payload["allowed_statuses"]),
            acceptable_node_ids=tuple(payload["acceptable_node_ids"]),
            top_k=payload["top_k"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "allowed_statuses": list(self.allowed_statuses),
            "acceptable_node_ids": list(self.acceptable_node_ids),
            "top_k": self.top_k,
        }


@dataclass(frozen=True, slots=True)
class RecommendationOracleOutcome:
    """One acceptable action-target-relation outcome as a joint tuple."""

    action: str
    target_node_id: str | None
    relation: str | None

    def __post_init__(self) -> None:
        if self.action not in RECOMMENDED_ACTIONS:
            raise ValueError("recommendation Oracle action is unsupported")
        _validate_optional_node_id(self.target_node_id)
        if self.relation is not None and self.relation not in CANDIDATE_RELATIONS:
            raise ValueError("recommendation Oracle relation is unsupported")
        if (self.target_node_id is None) != (self.relation is None):
            raise ValueError("recommendation Oracle target and relation must align")
        positive = {
            "USE_EXISTING_NODE": "SEMANTICALLY_EQUIVALENT",
            "ADD_NODE_FROM_CONTRACT": "REUSES_CONTRACT",
            "ADD_CONTEXT_FIELD": "CONTEXTUALLY_RELATED",
        }
        required_relation = positive.get(self.action)
        if required_relation is not None and (
            self.target_node_id is None or self.relation != required_relation
        ):
            raise ValueError("positive recommendation Oracle outcome is incomplete")
        if required_relation is None and self.target_node_id is not None:
            raise ValueError("non-positive recommendation Oracle cannot target a node")

    @classmethod
    def from_dict(cls, payload: Any) -> "RecommendationOracleOutcome":
        if not isinstance(payload, dict) or set(payload) != _RECOMMENDATION_OUTCOME_KEYS:
            raise ValueError("recommendation Oracle outcome must use exact fields")
        return cls(
            action=payload["action"],
            target_node_id=payload["target_node_id"],
            relation=payload["relation"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target_node_id": self.target_node_id,
            "relation": self.relation,
        }


@dataclass(frozen=True, slots=True)
class RecommendationOracle:
    applicable: bool
    acceptable_outcomes: tuple[RecommendationOracleOutcome, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.applicable, bool):
            raise ValueError("recommendation Oracle applicability must be boolean")
        if (
            not isinstance(self.acceptable_outcomes, tuple)
            or any(
                not isinstance(item, RecommendationOracleOutcome)
                for item in self.acceptable_outcomes
            )
            or len(self.acceptable_outcomes) > 32
        ):
            raise ValueError("recommendation Oracle outcomes are invalid")
        serialized = tuple(_outcome_sort_key(item) for item in self.acceptable_outcomes)
        if serialized != tuple(sorted(set(serialized))):
            raise ValueError("recommendation Oracle outcomes must be unique and ordered")
        if self.applicable != bool(self.acceptable_outcomes):
            raise ValueError("recommendation Oracle applicability is inconsistent")

    @classmethod
    def from_dict(cls, payload: Any) -> "RecommendationOracle":
        if not isinstance(payload, dict) or set(payload) != _RECOMMENDATION_ORACLE_KEYS:
            raise ValueError("recommendation Oracle must use exact fields")
        if not isinstance(payload["acceptable_outcomes"], list):
            raise ValueError("recommendation Oracle outcomes must be an array")
        return cls(
            applicable=payload["applicable"],
            acceptable_outcomes=tuple(
                RecommendationOracleOutcome.from_dict(item)
                for item in payload["acceptable_outcomes"]
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "acceptable_outcomes": [
                item.to_dict() for item in self.acceptable_outcomes
            ],
        }


@dataclass(frozen=True, slots=True)
class CapabilityOracle:
    expected_route: str
    acceptable_intent_profiles: tuple[IntentOracleProfile, ...]
    retrieval: RetrievalOracle
    recommendation: RecommendationOracle

    def __post_init__(self) -> None:
        if self.expected_route not in EXPECTED_ROUTES:
            raise ValueError("capability Oracle route is unsupported")
        if (
            not isinstance(self.acceptable_intent_profiles, tuple)
            or not self.acceptable_intent_profiles
            or len(self.acceptable_intent_profiles) > 8
            or any(
                not isinstance(item, IntentOracleProfile)
                for item in self.acceptable_intent_profiles
            )
        ):
            raise ValueError("capability Oracle intent profiles are invalid")
        refs = tuple(item.profile_ref for item in self.acceptable_intent_profiles)
        if refs != tuple(sorted(set(refs))):
            raise ValueError("capability Oracle profiles must be unique and ordered")
        if not isinstance(self.retrieval, RetrievalOracle) or not isinstance(
            self.recommendation, RecommendationOracle
        ):
            raise ValueError("capability Oracle stage contracts are invalid")
        expected_applicable = self.expected_route == "PROCEED"
        if (
            self.retrieval.applicable != expected_applicable
            or self.recommendation.applicable != expected_applicable
        ):
            raise ValueError("capability Oracle route and stage applicability disagree")

    @classmethod
    def from_dict(cls, payload: Any) -> "CapabilityOracle":
        if not isinstance(payload, dict) or set(payload) != _ORACLE_KEYS:
            raise ValueError("capability Oracle must use exact fields")
        if not isinstance(payload["acceptable_intent_profiles"], list):
            raise ValueError("capability Oracle profiles must be an array")
        return cls(
            expected_route=payload["expected_route"],
            acceptable_intent_profiles=tuple(
                IntentOracleProfile.from_dict(item)
                for item in payload["acceptable_intent_profiles"]
            ),
            retrieval=RetrievalOracle.from_dict(payload["retrieval"]),
            recommendation=RecommendationOracle.from_dict(
                payload["recommendation"]
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_route": self.expected_route,
            "acceptable_intent_profiles": [
                item.to_dict() for item in self.acceptable_intent_profiles
            ],
            "retrieval": self.retrieval.to_dict(),
            "recommendation": self.recommendation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ScenarioCapabilityOverlay:
    """Human-frozen full capability Oracle bound to one M3 reviewed scenario."""

    status: str
    source_reviewed_hash: str
    source_snapshot_hash: str
    source_plan_hash: str
    source_reviewed_content_hash: str
    reviewer_ref: str
    recorded_at: str
    review_round: int
    oracle: CapabilityOracle
    overlay_hash: str

    def __post_init__(self) -> None:
        if self.status not in OVERLAY_REVIEW_STATUSES:
            raise ValueError("capability overlay status is unsupported")
        for field_name in (
            "source_reviewed_hash",
            "source_snapshot_hash",
            "source_plan_hash",
            "source_reviewed_content_hash",
            "overlay_hash",
        ):
            _validate_digest(getattr(self, field_name), field_name)
        _validate_reference(self.reviewer_ref, "reviewer_ref")
        _validate_timestamp(self.recorded_at)
        if (
            not isinstance(self.review_round, int)
            or isinstance(self.review_round, bool)
            or self.review_round < 1
            or self.review_round > 2
        ):
            raise ValueError("capability overlay review_round must be one or two")
        if not isinstance(self.oracle, CapabilityOracle):
            raise ValueError("capability overlay requires a complete Oracle")
        if self.overlay_hash != canonical_digest(self._payload()):
            raise ValueError("capability overlay hash does not match its payload")

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
        reviewed: ReviewedValidationScenario,
        plan: ScenarioPreparationPlan,
        tree: CanonicalTree,
    ) -> "ScenarioCapabilityOverlay":
        if not isinstance(payload, dict) or set(payload) != _OVERLAY_KEYS:
            raise ScenarioCapabilityError(
                "CAPABILITY_OVERLAY_FIELDS_INVALID",
                "capability overlay must use the exact contract fields",
            )
        if payload["schema_version"] != CAPABILITY_OVERLAY_SCHEMA_VERSION:
            raise ScenarioCapabilityError(
                "CAPABILITY_OVERLAY_VERSION_INVALID",
                "capability overlay schema is unsupported",
            )
        if (
            payload["identity_status"] != IDENTITY_STATUS
            or payload["source_class"] != SOURCE_CLASS
            or payload["fictional"] is not True
            or payload["derived_from_real"] is not False
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise ScenarioCapabilityError(
                "CAPABILITY_OVERLAY_POLICY_INVALID",
                "capability overlay violates its fixed non-production policy",
            )
        try:
            overlay = cls(
                status=payload["status"],
                source_reviewed_hash=payload["source_reviewed_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                source_plan_hash=payload["source_plan_hash"],
                source_reviewed_content_hash=payload[
                    "source_reviewed_content_hash"
                ],
                reviewer_ref=payload["reviewer_ref"],
                recorded_at=payload["recorded_at"],
                review_round=payload["review_round"],
                oracle=CapabilityOracle.from_dict(payload["oracle"]),
                overlay_hash=payload["overlay_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise ScenarioCapabilityError(
                "CAPABILITY_OVERLAY_VALUE_INVALID",
                "capability overlay failed local validation",
            ) from None
        verify_capability_overlay_against_sources(overlay, reviewed, plan, tree)
        return overlay

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": CAPABILITY_OVERLAY_SCHEMA_VERSION,
            "status": self.status,
            "identity_status": IDENTITY_STATUS,
            "source_class": SOURCE_CLASS,
            "fictional": True,
            "derived_from_real": False,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "source_reviewed_hash": self.source_reviewed_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_plan_hash": self.source_plan_hash,
            "source_reviewed_content_hash": self.source_reviewed_content_hash,
            "reviewer_ref": self.reviewer_ref,
            "recorded_at": self.recorded_at,
            "review_round": self.review_round,
            "oracle": self.oracle.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["overlay_hash"] = self.overlay_hash
        return payload


@dataclass(frozen=True, slots=True)
class ScenarioCapabilitySilverAuthorization:
    """Non-authoritative Codex-assisted authorization for calibration only."""

    source_reviewed_hash: str
    source_snapshot_hash: str
    source_plan_hash: str
    source_reviewed_content_hash: str
    assessor_ref: str
    recorded_at: str
    oracle: CapabilityOracle
    authorization_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_reviewed_hash",
            "source_snapshot_hash",
            "source_plan_hash",
            "source_reviewed_content_hash",
            "authorization_hash",
        ):
            _validate_digest(getattr(self, field_name), field_name)
        _validate_reference(self.assessor_ref, "assessor_ref")
        _validate_timestamp(self.recorded_at)
        if not isinstance(self.oracle, CapabilityOracle):
            raise ValueError("silver authorization requires a complete Oracle")
        if self.authorization_hash != canonical_digest(self._payload()):
            raise ValueError("silver authorization hash does not match its payload")

    @property
    def overlay_hash(self) -> str:
        """Expose the existing run binding name without changing run v1 bytes."""

        return self.authorization_hash

    @property
    def gold_eligible(self) -> bool:
        return False

    @property
    def gate_eligible(self) -> bool:
        return False

    @property
    def patch_eligible(self) -> bool:
        return False

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        reviewed: ReviewedValidationScenario,
        plan: ScenarioPreparationPlan,
        tree: CanonicalTree,
    ) -> "ScenarioCapabilitySilverAuthorization":
        if not isinstance(payload, dict) or set(payload) != _SILVER_AUTHORIZATION_KEYS:
            raise ScenarioCapabilityError(
                "CAPABILITY_SILVER_AUTHORIZATION_FIELDS_INVALID",
                "silver authorization must use the exact contract fields",
            )
        if payload["schema_version"] != CAPABILITY_SILVER_AUTHORIZATION_SCHEMA_VERSION:
            raise ScenarioCapabilityError(
                "CAPABILITY_SILVER_AUTHORIZATION_VERSION_INVALID",
                "silver authorization schema is unsupported",
            )
        if (
            payload["status"] != SILVER_AUTHORIZATION_STATUS
            or payload["quality_tier"] != "SILVER"
            or payload["assessment_authority"] != SILVER_ASSESSMENT_AUTHORITY
            or payload["identity_status"] != IDENTITY_STATUS
            or payload["source_class"] != SOURCE_CLASS
            or payload["fictional"] is not True
            or payload["derived_from_real"] is not False
            or payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["gate_eligible"] is not False
            or payload["patch_eligible"] is not False
            or payload["execution_scope"] != "CALIBRATION_ONLY"
        ):
            raise ScenarioCapabilityError(
                "CAPABILITY_SILVER_AUTHORIZATION_POLICY_INVALID",
                "silver authorization violates its fixed calibration policy",
            )
        try:
            authorization = cls(
                source_reviewed_hash=payload["source_reviewed_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                source_plan_hash=payload["source_plan_hash"],
                source_reviewed_content_hash=payload[
                    "source_reviewed_content_hash"
                ],
                assessor_ref=payload["assessor_ref"],
                recorded_at=payload["recorded_at"],
                oracle=CapabilityOracle.from_dict(payload["oracle"]),
                authorization_hash=payload["authorization_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise ScenarioCapabilityError(
                "CAPABILITY_SILVER_AUTHORIZATION_VALUE_INVALID",
                "silver authorization failed local validation",
            ) from None
        verify_silver_authorization_for_execution(
            authorization,
            reviewed,
            plan,
            tree,
        )
        return authorization

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": CAPABILITY_SILVER_AUTHORIZATION_SCHEMA_VERSION,
            "status": SILVER_AUTHORIZATION_STATUS,
            "quality_tier": "SILVER",
            "assessment_authority": SILVER_ASSESSMENT_AUTHORITY,
            "identity_status": IDENTITY_STATUS,
            "source_class": SOURCE_CLASS,
            "fictional": True,
            "derived_from_real": False,
            "semantic_approval": False,
            "gold_eligible": False,
            "gate_eligible": False,
            "patch_eligible": False,
            "execution_scope": "CALIBRATION_ONLY",
            "source_reviewed_hash": self.source_reviewed_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "source_plan_hash": self.source_plan_hash,
            "source_reviewed_content_hash": self.source_reviewed_content_hash,
            "assessor_ref": self.assessor_ref,
            "recorded_at": self.recorded_at,
            "oracle": self.oracle.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["authorization_hash"] = self.authorization_hash
        return payload


def freeze_silver_capability_authorization(
    reviewed: ReviewedValidationScenario,
    plan: ScenarioPreparationPlan,
    tree: CanonicalTree,
    *,
    assessor_ref: str,
    recorded_at: str,
    oracle: CapabilityOracle,
) -> ScenarioCapabilitySilverAuthorization:
    """Freeze a Codex-assisted Silver decision for calibration execution only."""

    if not isinstance(reviewed, ReviewedValidationScenario):
        raise ScenarioCapabilityError(
            "CAPABILITY_REVIEWED_SCENARIO_REQUIRED",
            "a reviewed validation scenario is required",
        )
    if not isinstance(plan, ScenarioPreparationPlan) or not isinstance(
        tree, CanonicalTree
    ):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_SOURCE_INVALID",
            "a typed plan and resource tree are required",
        )
    if not isinstance(oracle, CapabilityOracle):
        raise ScenarioCapabilityError(
            "CAPABILITY_ORACLE_REQUIRED",
            "a complete typed capability Oracle is required",
        )
    try:
        _validate_oracle_node_sources(oracle, tree)
        source_content_hash = _reviewed_content_digest(reviewed, oracle)
        payload = {
            "schema_version": CAPABILITY_SILVER_AUTHORIZATION_SCHEMA_VERSION,
            "status": SILVER_AUTHORIZATION_STATUS,
            "quality_tier": "SILVER",
            "assessment_authority": SILVER_ASSESSMENT_AUTHORITY,
            "identity_status": IDENTITY_STATUS,
            "source_class": SOURCE_CLASS,
            "fictional": True,
            "derived_from_real": False,
            "semantic_approval": False,
            "gold_eligible": False,
            "gate_eligible": False,
            "patch_eligible": False,
            "execution_scope": "CALIBRATION_ONLY",
            "source_reviewed_hash": reviewed.reviewed_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "source_plan_hash": plan.plan_hash,
            "source_reviewed_content_hash": source_content_hash,
            "assessor_ref": assessor_ref,
            "recorded_at": recorded_at,
            "oracle": oracle.to_dict(),
        }
        authorization = ScenarioCapabilitySilverAuthorization(
            source_reviewed_hash=reviewed.reviewed_hash,
            source_snapshot_hash=tree.snapshot_hash,
            source_plan_hash=plan.plan_hash,
            source_reviewed_content_hash=source_content_hash,
            assessor_ref=assessor_ref,
            recorded_at=recorded_at,
            oracle=oracle,
            authorization_hash=canonical_digest(payload),
        )
    except (TypeError, ValueError):
        raise ScenarioCapabilityError(
            "CAPABILITY_SILVER_AUTHORIZATION_VALUE_INVALID",
            "silver authorization failed local validation",
        ) from None
    verify_silver_authorization_for_execution(
        authorization,
        reviewed,
        plan,
        tree,
    )
    return authorization


def freeze_capability_overlay(
    reviewed: ReviewedValidationScenario,
    plan: ScenarioPreparationPlan,
    tree: CanonicalTree,
    *,
    review_status: str,
    reviewer_ref: str,
    recorded_at: str,
    review_round: int,
    oracle: CapabilityOracle,
) -> ScenarioCapabilityOverlay:
    """Freeze a trusted human decision without upgrading it to Gold or Patch."""

    if not isinstance(reviewed, ReviewedValidationScenario):
        raise ScenarioCapabilityError(
            "CAPABILITY_REVIEWED_SCENARIO_REQUIRED",
            "a reviewed validation scenario is required",
        )
    if not isinstance(plan, ScenarioPreparationPlan) or not isinstance(
        tree, CanonicalTree
    ):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_SOURCE_INVALID",
            "a typed plan and resource tree are required",
        )
    if not isinstance(oracle, CapabilityOracle):
        raise ScenarioCapabilityError(
            "CAPABILITY_ORACLE_REQUIRED",
            "a complete typed capability Oracle is required",
        )
    try:
        _validate_oracle_node_sources(oracle, tree)
    except ValueError:
        raise ScenarioCapabilityError(
            "CAPABILITY_ORACLE_SOURCE_MISMATCH",
            "capability Oracle targets do not exist in the bound tree",
        ) from None
    try:
        source_content_hash = _reviewed_content_digest(reviewed, oracle)
        payload = {
            "schema_version": CAPABILITY_OVERLAY_SCHEMA_VERSION,
            "status": review_status,
            "identity_status": IDENTITY_STATUS,
            "source_class": SOURCE_CLASS,
            "fictional": True,
            "derived_from_real": False,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "source_reviewed_hash": reviewed.reviewed_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "source_plan_hash": plan.plan_hash,
            "source_reviewed_content_hash": source_content_hash,
            "reviewer_ref": reviewer_ref,
            "recorded_at": recorded_at,
            "review_round": review_round,
            "oracle": oracle.to_dict(),
        }
        overlay = ScenarioCapabilityOverlay(
            status=review_status,
            source_reviewed_hash=reviewed.reviewed_hash,
            source_snapshot_hash=tree.snapshot_hash,
            source_plan_hash=plan.plan_hash,
            source_reviewed_content_hash=source_content_hash,
            reviewer_ref=reviewer_ref,
            recorded_at=recorded_at,
            review_round=review_round,
            oracle=oracle,
            overlay_hash=canonical_digest(payload),
        )
    except (TypeError, ValueError):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_VALUE_INVALID",
            "capability overlay failed local validation",
        ) from None
    verify_capability_overlay_for_execution(overlay, reviewed, plan, tree)
    return overlay


def verify_capability_overlay_against_sources(
    overlay: ScenarioCapabilityOverlay,
    reviewed: ReviewedValidationScenario,
    plan: ScenarioPreparationPlan,
    tree: CanonicalTree,
) -> None:
    if not isinstance(overlay, ScenarioCapabilityOverlay):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_REQUIRED",
            "a frozen capability overlay is required",
        )
    if (
        not isinstance(reviewed, ReviewedValidationScenario)
        or not isinstance(plan, ScenarioPreparationPlan)
        or not isinstance(tree, CanonicalTree)
    ):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_SOURCE_INVALID",
            "capability overlay sources must use trusted typed contracts",
        )
    expected_bindings = (
        (overlay.source_reviewed_hash, reviewed.reviewed_hash),
        (overlay.source_snapshot_hash, tree.snapshot_hash),
        (overlay.source_plan_hash, plan.plan_hash),
        (reviewed.source_snapshot_hash, tree.snapshot_hash),
        (reviewed.source_plan_hash, plan.plan_hash),
        (plan.source_snapshot_hash, tree.snapshot_hash),
        (
            overlay.source_reviewed_content_hash,
            _reviewed_content_digest(reviewed, overlay.oracle),
        ),
    )
    if any(expected != actual for expected, actual in expected_bindings):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_SOURCE_MISMATCH",
            "capability overlay does not match the reviewed bytes, plan, and tree",
        )
    expected_draft_status = (
        "READY_FOR_HUMAN_REVIEW"
        if overlay.oracle.expected_route == "PROCEED"
        else "NEEDS_CLARIFICATION"
    )
    if reviewed.oracle.draft_status != expected_draft_status:
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_OBSERVABLE_ORACLE_MISMATCH",
            "capability route contradicts the reviewed observable Oracle",
        )
    try:
        _validate_oracle_node_sources(overlay.oracle, tree)
    except ValueError:
        raise ScenarioCapabilityError(
            "CAPABILITY_ORACLE_SOURCE_MISMATCH",
            "capability Oracle targets do not exist in the bound tree",
        ) from None


def verify_capability_overlay_for_execution(
    overlay: ScenarioCapabilityOverlay,
    reviewed: ReviewedValidationScenario,
    plan: ScenarioPreparationPlan,
    tree: CanonicalTree,
) -> None:
    """Verify source bindings and that the v1 Oracle is request-observable."""

    verify_capability_overlay_against_sources(overlay, reviewed, plan, tree)
    verify_capability_oracle_against_reviewed_request(
        overlay.oracle,
        reviewed,
        tree,
    )


def verify_silver_authorization_for_execution(
    authorization: ScenarioCapabilitySilverAuthorization,
    reviewed: ReviewedValidationScenario,
    plan: ScenarioPreparationPlan,
    tree: CanonicalTree,
) -> None:
    """Verify a non-gating Silver authorization and all source bindings."""

    if not isinstance(authorization, ScenarioCapabilitySilverAuthorization):
        raise ScenarioCapabilityError(
            "CAPABILITY_SILVER_AUTHORIZATION_REQUIRED",
            "a Silver calibration authorization is required",
        )
    if (
        not isinstance(reviewed, ReviewedValidationScenario)
        or not isinstance(plan, ScenarioPreparationPlan)
        or not isinstance(tree, CanonicalTree)
    ):
        raise ScenarioCapabilityError(
            "CAPABILITY_SILVER_AUTHORIZATION_SOURCE_INVALID",
            "Silver authorization sources must use trusted typed contracts",
        )
    expected_bindings = (
        (authorization.source_reviewed_hash, reviewed.reviewed_hash),
        (authorization.source_snapshot_hash, tree.snapshot_hash),
        (authorization.source_plan_hash, plan.plan_hash),
        (reviewed.source_snapshot_hash, tree.snapshot_hash),
        (reviewed.source_plan_hash, plan.plan_hash),
        (plan.source_snapshot_hash, tree.snapshot_hash),
        (
            authorization.source_reviewed_content_hash,
            _reviewed_content_digest(reviewed, authorization.oracle),
        ),
    )
    if any(expected != actual for expected, actual in expected_bindings):
        raise ScenarioCapabilityError(
            "CAPABILITY_SILVER_AUTHORIZATION_SOURCE_MISMATCH",
            "Silver authorization does not match the reviewed bytes, plan, and tree",
        )
    expected_draft_status = (
        "READY_FOR_HUMAN_REVIEW"
        if authorization.oracle.expected_route == "PROCEED"
        else "NEEDS_CLARIFICATION"
    )
    if reviewed.oracle.draft_status != expected_draft_status:
        raise ScenarioCapabilityError(
            "CAPABILITY_SILVER_AUTHORIZATION_OBSERVABLE_ORACLE_MISMATCH",
            "Silver route contradicts the reviewed observable Oracle",
        )
    try:
        _validate_oracle_node_sources(authorization.oracle, tree)
    except ValueError:
        raise ScenarioCapabilityError(
            "CAPABILITY_ORACLE_SOURCE_MISMATCH",
            "capability Oracle targets do not exist in the bound tree",
        ) from None
    verify_capability_oracle_against_reviewed_request(
        authorization.oracle,
        reviewed,
        tree,
    )


def verify_capability_oracle_against_reviewed_request(
    oracle: CapabilityOracle,
    reviewed: ReviewedValidationScenario,
    tree: CanonicalTree,
) -> None:
    """Preflight one proposed Oracle without pretending it was human-frozen."""

    if not isinstance(oracle, CapabilityOracle):
        raise ScenarioCapabilityError(
            "CAPABILITY_ORACLE_REQUIRED",
            "a complete typed capability Oracle is required",
        )
    if not isinstance(reviewed, ReviewedValidationScenario) or not isinstance(
        tree, CanonicalTree
    ):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_SOURCE_INVALID",
            "capability Oracle sources must use trusted typed contracts",
        )
    request = _intent_request(reviewed, tree)
    try:
        _validate_oracle_request_support(oracle, request)
    except ValueError:
        raise ScenarioCapabilityError(
            "CAPABILITY_ORACLE_REQUEST_MISMATCH",
            "capability intent Oracle is not supported by the frozen request",
        ) from None


@dataclass(frozen=True, slots=True)
class CapabilityStageResult:
    applicable: bool
    status: str
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.applicable, bool):
            raise ValueError("capability stage applicability must be boolean")
        if self.status not in STAGE_STATUSES:
            raise ValueError("capability stage status is unsupported")
        if self.reason_code not in STAGE_REASON_CODES:
            raise ValueError("capability stage reason_code is unsupported")
        if not self.applicable and self.status != "NOT_RUN":
            raise ValueError("non-applicable stage must be NOT_RUN")

    @classmethod
    def from_dict(cls, payload: Any) -> "CapabilityStageResult":
        if not isinstance(payload, dict) or set(payload) != _STAGE_RESULT_KEYS:
            raise ValueError("capability stage result must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "status": self.status,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class ScenarioCapabilityRun:
    """Private source-bound evidence for one staged capability execution."""

    source_overlay_hash: str
    source_reviewed_hash: str
    source_snapshot_hash: str
    source_request_hash: str
    source_intent_draft_hash: str | None
    source_candidate_set_hash: str | None
    source_recommendation_draft_hash: str | None
    plan_unit_ref: str
    candidate_ref: str
    expected_route: str
    intent: CapabilityStageResult
    retrieval: CapabilityStageResult
    recommendation: CapabilityStageResult
    full_path_status: str
    run_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_overlay_hash",
            "source_reviewed_hash",
            "source_snapshot_hash",
            "source_request_hash",
            "run_hash",
        ):
            _validate_digest(getattr(self, field_name), field_name)
        for field_name in (
            "source_intent_draft_hash",
            "source_candidate_set_hash",
            "source_recommendation_draft_hash",
        ):
            _validate_optional_digest(getattr(self, field_name), field_name)
        if _PLAN_UNIT_REFERENCE.fullmatch(self.plan_unit_ref) is None:
            raise ValueError("capability run plan_unit_ref is invalid")
        if _CANDIDATE_REFERENCE.fullmatch(self.candidate_ref) is None:
            raise ValueError("capability run candidate_ref is invalid")
        if self.expected_route not in EXPECTED_ROUTES:
            raise ValueError("capability run expected route is unsupported")
        for item in (self.intent, self.retrieval, self.recommendation):
            if not isinstance(item, CapabilityStageResult):
                raise ValueError("capability run stage result is invalid")
        _validate_run_stage_flow(self)
        _validate_run_source_hashes(self)
        _validate_run_reason_codes(self)
        expected_full_path = _full_path_status(
            self.expected_route,
            self.intent,
            self.retrieval,
            self.recommendation,
        )
        if self.full_path_status != expected_full_path:
            raise ValueError("capability run full path status is inconsistent")
        if self.run_hash != canonical_digest(self._payload()):
            raise ValueError("capability run hash does not match its payload")

    @classmethod
    def create(
        cls,
        *,
        source_overlay_hash: str,
        source_reviewed_hash: str,
        source_snapshot_hash: str,
        source_request_hash: str,
        source_intent_draft_hash: str | None,
        source_candidate_set_hash: str | None,
        source_recommendation_draft_hash: str | None,
        plan_unit_ref: str,
        candidate_ref: str,
        expected_route: str,
        intent: CapabilityStageResult,
        retrieval: CapabilityStageResult,
        recommendation: CapabilityStageResult,
    ) -> "ScenarioCapabilityRun":
        full_path_status = _full_path_status(
            expected_route,
            intent,
            retrieval,
            recommendation,
        )
        payload = _run_payload(
            source_overlay_hash=source_overlay_hash,
            source_reviewed_hash=source_reviewed_hash,
            source_snapshot_hash=source_snapshot_hash,
            source_request_hash=source_request_hash,
            source_intent_draft_hash=source_intent_draft_hash,
            source_candidate_set_hash=source_candidate_set_hash,
            source_recommendation_draft_hash=source_recommendation_draft_hash,
            plan_unit_ref=plan_unit_ref,
            candidate_ref=candidate_ref,
            expected_route=expected_route,
            intent=intent,
            retrieval=retrieval,
            recommendation=recommendation,
            full_path_status=full_path_status,
        )
        return cls(
            source_overlay_hash=source_overlay_hash,
            source_reviewed_hash=source_reviewed_hash,
            source_snapshot_hash=source_snapshot_hash,
            source_request_hash=source_request_hash,
            source_intent_draft_hash=source_intent_draft_hash,
            source_candidate_set_hash=source_candidate_set_hash,
            source_recommendation_draft_hash=source_recommendation_draft_hash,
            plan_unit_ref=plan_unit_ref,
            candidate_ref=candidate_ref,
            expected_route=expected_route,
            intent=intent,
            retrieval=retrieval,
            recommendation=recommendation,
            full_path_status=full_path_status,
            run_hash=canonical_digest(payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        overlay: ScenarioCapabilityOverlay,
        reviewed: ReviewedValidationScenario,
        action: ScenarioReviewAction,
        batch: ScenarioPreparationBatch,
        batch_candidate: ScenarioPreparationBatchCandidate,
        projection: ScenarioPreparationProjection,
        plan: ScenarioPreparationPlan,
        profile: TreeDiagnosticProfile,
        tree: CanonicalTree,
    ) -> "ScenarioCapabilityRun":
        if not isinstance(payload, dict) or set(payload) != _RUN_KEYS:
            raise ScenarioCapabilityError(
                "CAPABILITY_RUN_FIELDS_INVALID",
                "capability run must use the exact contract fields",
            )
        if payload["schema_version"] != CAPABILITY_RUN_SCHEMA_VERSION:
            raise ScenarioCapabilityError(
                "CAPABILITY_RUN_VERSION_INVALID",
                "capability run schema is unsupported",
            )
        try:
            run = cls(
                source_overlay_hash=payload["source_overlay_hash"],
                source_reviewed_hash=payload["source_reviewed_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                source_request_hash=payload["source_request_hash"],
                source_intent_draft_hash=payload["source_intent_draft_hash"],
                source_candidate_set_hash=payload["source_candidate_set_hash"],
                source_recommendation_draft_hash=payload[
                    "source_recommendation_draft_hash"
                ],
                plan_unit_ref=payload["plan_unit_ref"],
                candidate_ref=payload["candidate_ref"],
                expected_route=payload["expected_route"],
                intent=CapabilityStageResult.from_dict(payload["intent"]),
                retrieval=CapabilityStageResult.from_dict(payload["retrieval"]),
                recommendation=CapabilityStageResult.from_dict(
                    payload["recommendation"]
                ),
                full_path_status=payload["full_path_status"],
                run_hash=payload["run_hash"],
            )
        except (KeyError, TypeError, ValueError):
            raise ScenarioCapabilityError(
                "CAPABILITY_RUN_VALUE_INVALID",
                "capability run failed local validation",
            ) from None
        try:
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
        except (ScenarioValidationError, TypeError, ValueError):
            raise ScenarioCapabilityError(
                "CAPABILITY_RUN_REVIEWED_SOURCE_MISMATCH",
                "capability run reviewed source replay failed",
            ) from None
        verify_capability_overlay_for_execution(overlay, reviewed, plan, tree)
        request = _intent_request(reviewed, tree)
        if (
            run.source_overlay_hash != overlay.overlay_hash
            or run.source_reviewed_hash != reviewed.reviewed_hash
            or run.source_snapshot_hash != tree.snapshot_hash
            or run.source_request_hash != request.request_hash
            or run.plan_unit_ref != reviewed.plan_unit_ref
            or run.candidate_ref != reviewed.candidate_ref
            or run.expected_route != overlay.oracle.expected_route
        ):
            raise ScenarioCapabilityError(
                "CAPABILITY_RUN_SOURCE_MISMATCH",
                "capability run does not match its trusted source artifacts",
            )
        return run

    def _payload(self) -> dict[str, Any]:
        return _run_payload(
            source_overlay_hash=self.source_overlay_hash,
            source_reviewed_hash=self.source_reviewed_hash,
            source_snapshot_hash=self.source_snapshot_hash,
            source_request_hash=self.source_request_hash,
            source_intent_draft_hash=self.source_intent_draft_hash,
            source_candidate_set_hash=self.source_candidate_set_hash,
            source_recommendation_draft_hash=self.source_recommendation_draft_hash,
            plan_unit_ref=self.plan_unit_ref,
            candidate_ref=self.candidate_ref,
            expected_route=self.expected_route,
            intent=self.intent,
            retrieval=self.retrieval,
            recommendation=self.recommendation,
            full_path_status=self.full_path_status,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["run_hash"] = self.run_hash
        return payload


def run_reviewed_capability_scenario(
    overlay: ScenarioCapabilityOverlay,
    reviewed: ReviewedValidationScenario,
    action: ScenarioReviewAction,
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
    intent_provider: IntentCapabilityProvider,
    semantic_provider: SemanticCapabilityProvider,
) -> ScenarioCapabilityRun:
    """Execute one human-frozen capability scenario."""

    if not isinstance(overlay, ScenarioCapabilityOverlay):
        raise ScenarioCapabilityError(
            "CAPABILITY_OVERLAY_REQUIRED",
            "a human-frozen capability overlay is required",
        )
    return _run_capability_scenario(
        overlay,
        reviewed,
        action,
        batch,
        batch_candidate,
        projection,
        plan,
        profile,
        tree,
        intent_provider,
        semantic_provider,
    )


def run_silver_capability_scenario(
    authorization: ScenarioCapabilitySilverAuthorization,
    reviewed: ReviewedValidationScenario,
    action: ScenarioReviewAction,
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
    intent_provider: IntentCapabilityProvider,
    semantic_provider: SemanticCapabilityProvider,
) -> ScenarioCapabilityRun:
    """Execute one Codex-assisted Silver scenario for calibration only."""

    if not isinstance(authorization, ScenarioCapabilitySilverAuthorization):
        raise ScenarioCapabilityError(
            "CAPABILITY_SILVER_AUTHORIZATION_REQUIRED",
            "a Silver calibration authorization is required",
        )
    return _run_capability_scenario(
        authorization,
        reviewed,
        action,
        batch,
        batch_candidate,
        projection,
        plan,
        profile,
        tree,
        intent_provider,
        semantic_provider,
    )


def _run_capability_scenario(
    overlay: ScenarioCapabilityOverlay | ScenarioCapabilitySilverAuthorization,
    reviewed: ReviewedValidationScenario,
    action: ScenarioReviewAction,
    batch: ScenarioPreparationBatch,
    batch_candidate: ScenarioPreparationBatchCandidate,
    projection: ScenarioPreparationProjection,
    plan: ScenarioPreparationPlan,
    profile: TreeDiagnosticProfile,
    tree: CanonicalTree,
    intent_provider: IntentCapabilityProvider,
    semantic_provider: SemanticCapabilityProvider,
) -> ScenarioCapabilityRun:
    """Execute intent, deterministic retrieval, and recommendation with short-circuiting."""

    try:
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
    except (ScenarioValidationError, TypeError, ValueError):
        raise ScenarioCapabilityError(
            "CAPABILITY_REVIEWED_SOURCE_MISMATCH",
            "reviewed scenario failed trusted source replay",
        ) from None
    if isinstance(overlay, ScenarioCapabilityOverlay):
        verify_capability_overlay_for_execution(overlay, reviewed, plan, tree)
    else:
        verify_silver_authorization_for_execution(overlay, reviewed, plan, tree)
    request = _intent_request(reviewed, tree)

    try:
        draft = intent_provider.draft(request, tree)
    except (IntentValidationError, RuntimeError):
        return _short_circuit_run(
            overlay,
            reviewed,
            tree,
            request,
            intent=CapabilityStageResult(True, "RUN_FAILED", "INTENT_PROVIDER_FAILED"),
            intent_draft_hash=None,
            candidate_set_hash=None,
        )
    if not isinstance(draft, ChangeIntentDraft):
        return _short_circuit_run(
            overlay,
            reviewed,
            tree,
            request,
            intent=CapabilityStageResult(True, "RUN_FAILED", "INTENT_PROVIDER_FAILED"),
            intent_draft_hash=None,
            candidate_set_hash=None,
        )
    try:
        verify_intent_draft_against_sources(draft, request, tree)
    except IntentValidationError:
        return _short_circuit_run(
            overlay,
            reviewed,
            tree,
            request,
            intent=CapabilityStageResult(True, "RUN_FAILED", "INTENT_PROVIDER_FAILED"),
            intent_draft_hash=draft.draft_hash,
            candidate_set_hash=None,
        )

    intent_matches = _intent_matches(draft, overlay.oracle)
    intent_result = CapabilityStageResult(
        True,
        "MATCH" if intent_matches else "MISMATCH",
        "INTENT_ORACLE_MATCH" if intent_matches else "INTENT_ORACLE_MISMATCH",
    )
    if not intent_matches:
        return _short_circuit_run(
            overlay,
            reviewed,
            tree,
            request,
            intent=intent_result,
            intent_draft_hash=draft.draft_hash,
            candidate_set_hash=None,
        )
    if overlay.oracle.expected_route == "CLARIFY":
        not_applicable = CapabilityStageResult(
            False,
            "NOT_RUN",
            "EXPECTED_CLARIFICATION_SHORT_CIRCUIT",
        )
        return ScenarioCapabilityRun.create(
            source_overlay_hash=overlay.overlay_hash,
            source_reviewed_hash=reviewed.reviewed_hash,
            source_snapshot_hash=tree.snapshot_hash,
            source_request_hash=request.request_hash,
            source_intent_draft_hash=draft.draft_hash,
            source_candidate_set_hash=None,
            source_recommendation_draft_hash=None,
            plan_unit_ref=reviewed.plan_unit_ref,
            candidate_ref=reviewed.candidate_ref,
            expected_route=overlay.oracle.expected_route,
            intent=intent_result,
            retrieval=not_applicable,
            recommendation=not_applicable,
        )

    try:
        confirmation = apply_intent_review(
            request,
            draft,
            IntentReviewAction(
                expected_draft_hash=draft.draft_hash,
                decision="CONFIRM_FOR_RETRIEVAL",
                reviewer_ref="m4-validation-harness",
                recorded_at=reviewed.recorded_at,
                confirmed_intent=draft.intent,
            ),
            tree,
        )
        candidate_set = build_candidate_set(confirmation, tree)
    except (IntentValidationError, CandidateRetrievalError):
        return ScenarioCapabilityRun.create(
            source_overlay_hash=overlay.overlay_hash,
            source_reviewed_hash=reviewed.reviewed_hash,
            source_snapshot_hash=tree.snapshot_hash,
            source_request_hash=request.request_hash,
            source_intent_draft_hash=draft.draft_hash,
            source_candidate_set_hash=None,
            source_recommendation_draft_hash=None,
            plan_unit_ref=reviewed.plan_unit_ref,
            candidate_ref=reviewed.candidate_ref,
            expected_route=overlay.oracle.expected_route,
            intent=intent_result,
            retrieval=CapabilityStageResult(
                True, "RUN_FAILED", "RETRIEVAL_RUN_FAILED"
            ),
            recommendation=CapabilityStageResult(
                True, "NOT_RUN", "UPSTREAM_RETRIEVAL_RUN_FAILED"
            ),
        )

    retrieval_matches = _retrieval_matches(candidate_set, overlay.oracle.retrieval)
    retrieval_result = CapabilityStageResult(
        True,
        "MATCH" if retrieval_matches else "MISMATCH",
        (
            "RETRIEVAL_ORACLE_MATCH"
            if retrieval_matches
            else "RETRIEVAL_ORACLE_MISMATCH"
        ),
    )
    if not retrieval_matches:
        return ScenarioCapabilityRun.create(
            source_overlay_hash=overlay.overlay_hash,
            source_reviewed_hash=reviewed.reviewed_hash,
            source_snapshot_hash=tree.snapshot_hash,
            source_request_hash=request.request_hash,
            source_intent_draft_hash=draft.draft_hash,
            source_candidate_set_hash=candidate_set.candidate_set_hash,
            source_recommendation_draft_hash=None,
            plan_unit_ref=reviewed.plan_unit_ref,
            candidate_ref=reviewed.candidate_ref,
            expected_route=overlay.oracle.expected_route,
            intent=intent_result,
            retrieval=retrieval_result,
            recommendation=CapabilityStageResult(
                True, "NOT_RUN", "UPSTREAM_RETRIEVAL_MISMATCH"
            ),
        )

    try:
        recommendation = semantic_provider.recommend(
            confirmation,
            candidate_set,
            tree,
        )
    except (SemanticRecommendationError, RuntimeError):
        return ScenarioCapabilityRun.create(
            source_overlay_hash=overlay.overlay_hash,
            source_reviewed_hash=reviewed.reviewed_hash,
            source_snapshot_hash=tree.snapshot_hash,
            source_request_hash=request.request_hash,
            source_intent_draft_hash=draft.draft_hash,
            source_candidate_set_hash=candidate_set.candidate_set_hash,
            source_recommendation_draft_hash=None,
            plan_unit_ref=reviewed.plan_unit_ref,
            candidate_ref=reviewed.candidate_ref,
            expected_route=overlay.oracle.expected_route,
            intent=intent_result,
            retrieval=retrieval_result,
            recommendation=CapabilityStageResult(
                True, "RUN_FAILED", "RECOMMENDATION_PROVIDER_FAILED"
            ),
        )
    if not isinstance(recommendation, SemanticRecommendationDraft):
        recommendation_result = CapabilityStageResult(
            True, "RUN_FAILED", "RECOMMENDATION_PROVIDER_FAILED"
        )
        recommendation_hash = None
    else:
        try:
            SemanticRecommendationDraft.from_dict(
                recommendation.to_dict(),
                confirmation,
                candidate_set,
                tree,
            )
            recommendation_matches = _recommendation_matches(
                recommendation,
                candidate_set,
                overlay.oracle.recommendation,
            )
            recommendation_result = CapabilityStageResult(
                True,
                "MATCH" if recommendation_matches else "MISMATCH",
                (
                    "RECOMMENDATION_ORACLE_MATCH"
                    if recommendation_matches
                    else "RECOMMENDATION_ORACLE_MISMATCH"
                ),
            )
            recommendation_hash = recommendation.draft_hash
        except SemanticRecommendationError:
            recommendation_result = CapabilityStageResult(
                True, "RUN_FAILED", "RECOMMENDATION_PROVIDER_FAILED"
            )
            recommendation_hash = recommendation.draft_hash
    return ScenarioCapabilityRun.create(
        source_overlay_hash=overlay.overlay_hash,
        source_reviewed_hash=reviewed.reviewed_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_request_hash=request.request_hash,
        source_intent_draft_hash=draft.draft_hash,
        source_candidate_set_hash=candidate_set.candidate_set_hash,
        source_recommendation_draft_hash=recommendation_hash,
        plan_unit_ref=reviewed.plan_unit_ref,
        candidate_ref=reviewed.candidate_ref,
        expected_route=overlay.oracle.expected_route,
        intent=intent_result,
        retrieval=retrieval_result,
        recommendation=recommendation_result,
    )


@dataclass(frozen=True, slots=True)
class ScenarioPreparationMetrics:
    planned_unit_count: int
    accounted_unit_count: int
    accepted_count: int
    revised_accepted_count: int
    rejected_count: int
    generation_failure_count: int
    blocking_finding_count: int
    review_minutes: int

    def __post_init__(self) -> None:
        for field_name in (
            "planned_unit_count",
            "accounted_unit_count",
            "accepted_count",
            "revised_accepted_count",
            "rejected_count",
            "generation_failure_count",
            "blocking_finding_count",
            "review_minutes",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("scenario preparation metrics must be non-negative")
        if self.planned_unit_count < 1 or self.accounted_unit_count > self.planned_unit_count:
            raise ValueError("scenario preparation plan accounting is invalid")
        if (
            self.accepted_count
            + self.revised_accepted_count
            + self.rejected_count
            + self.generation_failure_count
            != self.accounted_unit_count
        ):
            raise ValueError("scenario preparation outcome counts do not reconcile")

    @classmethod
    def from_dict(cls, payload: Any) -> "ScenarioPreparationMetrics":
        keys = {
            "planned_unit_count",
            "accounted_unit_count",
            "accepted_count",
            "revised_accepted_count",
            "rejected_count",
            "generation_failure_count",
            "blocking_finding_count",
            "review_minutes",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("scenario preparation metrics must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "planned_unit_count": self.planned_unit_count,
            "accounted_unit_count": self.accounted_unit_count,
            "accepted_count": self.accepted_count,
            "revised_accepted_count": self.revised_accepted_count,
            "rejected_count": self.rejected_count,
            "generation_failure_count": self.generation_failure_count,
            "blocking_finding_count": self.blocking_finding_count,
            "review_minutes": self.review_minutes,
        }


@dataclass(frozen=True, slots=True)
class CandidatePreparationGate:
    source_metrics: ScenarioPreparationMetrics
    status: str
    failure_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_metrics, ScenarioPreparationMetrics):
            raise ValueError("candidate preparation gate metrics are invalid")
        _validate_gate_status(self.status, self.failure_codes)
        if self.failure_codes != _candidate_failure_codes(self.source_metrics):
            raise ValueError("candidate preparation gate result is inconsistent")

    @classmethod
    def from_dict(cls, payload: Any) -> "CandidatePreparationGate":
        metric_keys = set(ScenarioPreparationMetrics(
            1, 0, 0, 0, 0, 0, 0, 0
        ).to_dict())
        keys = metric_keys | {"status", "failure_codes"}
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("candidate preparation gate must use exact fields")
        metrics = ScenarioPreparationMetrics.from_dict(
            {key: payload[key] for key in metric_keys}
        )
        if not isinstance(payload["failure_codes"], list):
            raise ValueError("candidate preparation failure_codes must be an array")
        return cls(metrics, payload["status"], tuple(payload["failure_codes"]))

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.source_metrics.to_dict(),
            "status": self.status,
            "failure_codes": list(self.failure_codes),
        }


@dataclass(frozen=True, slots=True)
class CapabilityStageAggregate:
    applicable_count: int
    match_count: int
    mismatch_count: int
    not_run_count: int
    run_failed_count: int

    def __post_init__(self) -> None:
        for value in (
            self.applicable_count,
            self.match_count,
            self.mismatch_count,
            self.not_run_count,
            self.run_failed_count,
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("capability stage aggregate counts are invalid")
        if (
            self.match_count
            + self.mismatch_count
            + self.not_run_count
            + self.run_failed_count
            != self.applicable_count
        ):
            raise ValueError("capability stage aggregate does not reconcile")

    @classmethod
    def from_dict(cls, payload: Any) -> "CapabilityStageAggregate":
        keys = {
            "applicable_count",
            "match_count",
            "mismatch_count",
            "not_run_count",
            "run_failed_count",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("capability stage aggregate must use exact fields")
        return cls(**payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "applicable_count": self.applicable_count,
            "match_count": self.match_count,
            "mismatch_count": self.mismatch_count,
            "not_run_count": self.not_run_count,
            "run_failed_count": self.run_failed_count,
        }


@dataclass(frozen=True, slots=True)
class CapabilityExecutionGate:
    selected_scenario_count: int
    proceed_route_count: int
    clarify_route_count: int
    clarification_coverage_status: str
    full_path_match_count: int
    full_path_mismatch_count: int
    full_path_run_failed_count: int
    intent: CapabilityStageAggregate
    retrieval: CapabilityStageAggregate
    recommendation: CapabilityStageAggregate
    status: str
    failure_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "selected_scenario_count",
            "proceed_route_count",
            "clarify_route_count",
            "full_path_match_count",
            "full_path_mismatch_count",
            "full_path_run_failed_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("capability execution counts are invalid")
        if self.selected_scenario_count > 8:
            raise ValueError("capability execution may select at most eight scenarios")
        if self.proceed_route_count + self.clarify_route_count != self.selected_scenario_count:
            raise ValueError("capability route counts do not reconcile")
        if (
            self.full_path_match_count
            + self.full_path_mismatch_count
            + self.full_path_run_failed_count
            != self.selected_scenario_count
        ):
            raise ValueError("capability full-path counts do not reconcile")
        if self.clarification_coverage_status not in CLARIFICATION_COVERAGE_STATUSES:
            raise ValueError("clarification coverage status is unsupported")
        for aggregate in (self.intent, self.retrieval, self.recommendation):
            if not isinstance(aggregate, CapabilityStageAggregate):
                raise ValueError("capability execution aggregate is invalid")
            if aggregate.applicable_count > self.selected_scenario_count:
                raise ValueError("stage denominator exceeds selected scenarios")
        _validate_gate_status(self.status, self.failure_codes)
        if self.failure_codes != _execution_failure_codes(
            selected_scenario_count=self.selected_scenario_count,
            proceed_route_count=self.proceed_route_count,
            clarify_route_count=self.clarify_route_count,
            clarification_coverage_status=self.clarification_coverage_status,
            full_path_match_count=self.full_path_match_count,
            intent=self.intent,
            retrieval=self.retrieval,
            recommendation=self.recommendation,
        ):
            raise ValueError("capability execution gate result is inconsistent")

    @classmethod
    def from_dict(cls, payload: Any) -> "CapabilityExecutionGate":
        keys = {
            "selected_scenario_count",
            "proceed_route_count",
            "clarify_route_count",
            "clarification_coverage_status",
            "full_path_match_count",
            "full_path_mismatch_count",
            "full_path_run_failed_count",
            "intent",
            "retrieval",
            "recommendation",
            "status",
            "failure_codes",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ValueError("capability execution gate must use exact fields")
        if not isinstance(payload["failure_codes"], list):
            raise ValueError("capability execution failure_codes must be an array")
        return cls(
            selected_scenario_count=payload["selected_scenario_count"],
            proceed_route_count=payload["proceed_route_count"],
            clarify_route_count=payload["clarify_route_count"],
            clarification_coverage_status=payload[
                "clarification_coverage_status"
            ],
            full_path_match_count=payload["full_path_match_count"],
            full_path_mismatch_count=payload["full_path_mismatch_count"],
            full_path_run_failed_count=payload["full_path_run_failed_count"],
            intent=CapabilityStageAggregate.from_dict(payload["intent"]),
            retrieval=CapabilityStageAggregate.from_dict(payload["retrieval"]),
            recommendation=CapabilityStageAggregate.from_dict(
                payload["recommendation"]
            ),
            status=payload["status"],
            failure_codes=tuple(payload["failure_codes"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_scenario_count": self.selected_scenario_count,
            "proceed_route_count": self.proceed_route_count,
            "clarify_route_count": self.clarify_route_count,
            "clarification_coverage_status": self.clarification_coverage_status,
            "full_path_match_count": self.full_path_match_count,
            "full_path_mismatch_count": self.full_path_mismatch_count,
            "full_path_run_failed_count": self.full_path_run_failed_count,
            "intent": self.intent.to_dict(),
            "retrieval": self.retrieval.to_dict(),
            "recommendation": self.recommendation.to_dict(),
            "status": self.status,
            "failure_codes": list(self.failure_codes),
        }


@dataclass(frozen=True, slots=True)
class CapabilityGateReport:
    candidate_preparation: CandidatePreparationGate
    execution: CapabilityExecutionGate
    hard_failure_codes: tuple[str, ...]
    decision: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_preparation, CandidatePreparationGate):
            raise ValueError("capability report candidate gate is invalid")
        if not isinstance(self.execution, CapabilityExecutionGate):
            raise ValueError("capability report execution gate is invalid")
        _validate_code_tuple(
            self.hard_failure_codes,
            allowed=PUBLIC_HARD_FAILURE_CODES,
        )
        if self.decision not in DECISIONS:
            raise ValueError("capability report decision is unsupported")
        expected = (
            "GO_SHADOW"
            if not self.hard_failure_codes
            and self.candidate_preparation.status == "PASS"
            and self.execution.status == "PASS"
            else "NO_GO"
        )
        if self.decision != expected:
            raise ValueError("capability report decision is inconsistent")

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
    def from_dict(cls, payload: Any) -> "CapabilityGateReport":
        keys = {
            "schema_version",
            "semantic_approval",
            "gold_eligible",
            "patch_eligible",
            "candidate_preparation",
            "execution",
            "hard_failure_codes",
            "decision",
        }
        if not isinstance(payload, dict) or set(payload) != keys:
            raise ScenarioCapabilityError(
                "CAPABILITY_REPORT_FIELDS_INVALID",
                "capability report must use exact fields",
            )
        if payload["schema_version"] != CAPABILITY_REPORT_SCHEMA_VERSION:
            raise ScenarioCapabilityError(
                "CAPABILITY_REPORT_VERSION_INVALID",
                "capability report schema is unsupported",
            )
        if (
            payload["semantic_approval"] is not False
            or payload["gold_eligible"] is not False
            or payload["patch_eligible"] is not False
            or not isinstance(payload["hard_failure_codes"], list)
        ):
            raise ScenarioCapabilityError(
                "CAPABILITY_REPORT_POLICY_INVALID",
                "capability report violates its aggregate-only policy",
            )
        try:
            report = cls(
                candidate_preparation=CandidatePreparationGate.from_dict(
                    payload["candidate_preparation"]
                ),
                execution=CapabilityExecutionGate.from_dict(payload["execution"]),
                hard_failure_codes=tuple(payload["hard_failure_codes"]),
                decision=payload["decision"],
            )
        except (TypeError, ValueError):
            raise ScenarioCapabilityError(
                "CAPABILITY_REPORT_VALUE_INVALID",
                "capability report failed local validation",
            ) from None
        return report

    def to_dict(self) -> dict[str, Any]:
        """Return the allowlisted public report; never include private run evidence."""

        return {
            "schema_version": CAPABILITY_REPORT_SCHEMA_VERSION,
            "semantic_approval": False,
            "gold_eligible": False,
            "patch_eligible": False,
            "candidate_preparation": self.candidate_preparation.to_dict(),
            "execution": self.execution.to_dict(),
            "hard_failure_codes": list(self.hard_failure_codes),
            "decision": self.decision,
        }


def build_capability_gate_report(
    preparation: ScenarioPreparationMetrics,
    runs: tuple[ScenarioCapabilityRun, ...],
    *,
    clarification_coverage_status: str,
    hard_failure_codes: tuple[str, ...],
) -> CapabilityGateReport:
    """Combine independent candidate-quality and staged-execution gates."""

    if not isinstance(preparation, ScenarioPreparationMetrics):
        raise ScenarioCapabilityError(
            "CAPABILITY_PREPARATION_METRICS_INVALID",
            "typed scenario preparation metrics are required",
        )
    if (
        not isinstance(runs, tuple)
        or len(runs) > 8
        or any(not isinstance(run, ScenarioCapabilityRun) for run in runs)
    ):
        raise ScenarioCapabilityError(
            "CAPABILITY_RUN_SET_INVALID",
            "capability report requires at most eight typed runs",
        )
    overlay_hashes = tuple(run.source_overlay_hash for run in runs)
    if len(overlay_hashes) != len(set(overlay_hashes)):
        raise ScenarioCapabilityError(
            "CAPABILITY_RUN_SET_DUPLICATE",
            "capability report cannot count the same overlay more than once",
        )
    if clarification_coverage_status not in CLARIFICATION_COVERAGE_STATUSES:
        raise ScenarioCapabilityError(
            "CAPABILITY_CLARIFICATION_COVERAGE_INVALID",
            "clarification coverage status is unsupported",
        )
    try:
        _validate_code_tuple(
            hard_failure_codes,
            allowed=PUBLIC_HARD_FAILURE_CODES,
        )
    except ValueError:
        raise ScenarioCapabilityError(
            "CAPABILITY_HARD_FAILURE_CODES_INVALID",
            "hard failure codes must be unique ordered fixed codes",
        ) from None

    candidate_gate = _candidate_preparation_gate(preparation)
    execution_gate = _capability_execution_gate(
        runs,
        clarification_coverage_status,
    )
    decision = (
        "GO_SHADOW"
        if not hard_failure_codes
        and candidate_gate.status == "PASS"
        and execution_gate.status == "PASS"
        else "NO_GO"
    )
    return CapabilityGateReport(
        candidate_preparation=candidate_gate,
        execution=execution_gate,
        hard_failure_codes=hard_failure_codes,
        decision=decision,
    )


def _candidate_preparation_gate(
    metrics: ScenarioPreparationMetrics,
) -> CandidatePreparationGate:
    codes = _candidate_failure_codes(metrics)
    return CandidatePreparationGate(
        source_metrics=metrics,
        status="PASS" if not codes else "FAIL",
        failure_codes=codes,
    )


def _candidate_failure_codes(
    metrics: ScenarioPreparationMetrics,
) -> tuple[str, ...]:
    failures: list[str] = []
    if metrics.accounted_unit_count != metrics.planned_unit_count:
        failures.append("CANDIDATE_PLAN_NOT_FULLY_ACCOUNTED")
    if metrics.accepted_count + metrics.revised_accepted_count < 8:
        failures.append("CANDIDATE_EXECUTABLE_BELOW_MINIMUM")
    if metrics.accepted_count < 4:
        failures.append("CANDIDATE_DIRECT_ACCEPTED_BELOW_MINIMUM")
    if metrics.rejected_count + metrics.generation_failure_count > 3:
        failures.append("CANDIDATE_UNUSABLE_ABOVE_MAXIMUM")
    if metrics.blocking_finding_count:
        failures.append("CANDIDATE_BLOCKING_FINDING_PRESENT")
    if metrics.review_minutes > 150:
        failures.append("CANDIDATE_REVIEW_BUDGET_EXCEEDED")
    return tuple(sorted(failures))


def _capability_execution_gate(
    runs: tuple[ScenarioCapabilityRun, ...],
    clarification_coverage_status: str,
) -> CapabilityExecutionGate:
    proceed_count = sum(run.expected_route == "PROCEED" for run in runs)
    clarify_count = len(runs) - proceed_count
    path_match_count = sum(run.full_path_status == "MATCH" for run in runs)
    path_mismatch_count = sum(run.full_path_status == "MISMATCH" for run in runs)
    path_run_failed_count = sum(run.full_path_status == "RUN_FAILED" for run in runs)
    intent = _stage_aggregate(tuple(run.intent for run in runs))
    retrieval = _stage_aggregate(tuple(run.retrieval for run in runs))
    recommendation = _stage_aggregate(tuple(run.recommendation for run in runs))

    codes = _execution_failure_codes(
        selected_scenario_count=len(runs),
        proceed_route_count=proceed_count,
        clarify_route_count=clarify_count,
        clarification_coverage_status=clarification_coverage_status,
        full_path_match_count=path_match_count,
        intent=intent,
        retrieval=retrieval,
        recommendation=recommendation,
    )
    return CapabilityExecutionGate(
        selected_scenario_count=len(runs),
        proceed_route_count=proceed_count,
        clarify_route_count=clarify_count,
        clarification_coverage_status=clarification_coverage_status,
        full_path_match_count=path_match_count,
        full_path_mismatch_count=path_mismatch_count,
        full_path_run_failed_count=path_run_failed_count,
        intent=intent,
        retrieval=retrieval,
        recommendation=recommendation,
        status="PASS" if not codes else "FAIL",
        failure_codes=codes,
    )


def _execution_failure_codes(
    *,
    selected_scenario_count: int,
    proceed_route_count: int,
    clarify_route_count: int,
    clarification_coverage_status: str,
    full_path_match_count: int,
    intent: CapabilityStageAggregate,
    retrieval: CapabilityStageAggregate,
    recommendation: CapabilityStageAggregate,
) -> tuple[str, ...]:
    failures: list[str] = []
    if selected_scenario_count != 8:
        failures.append("EXECUTION_SCENARIO_COUNT_INVALID")
    if clarification_coverage_status == "COVERED":
        if clarify_route_count != 1 or proceed_route_count != 7:
            failures.append("EXECUTION_CLARIFICATION_COMPOSITION_INVALID")
    elif clarification_coverage_status == "NOT_APPLICABLE_WITH_BACKFILL":
        if clarify_route_count != 0 or proceed_route_count != 8:
            failures.append("EXECUTION_BACKFILL_COMPOSITION_INVALID")
    else:
        failures.append("EXECUTION_CLARIFICATION_COVERAGE_MISSING")
    if full_path_match_count < 6:
        failures.append("EXECUTION_FULL_PATH_MATCH_BELOW_MINIMUM")
    for stage_name, aggregate in (
        ("INTENT", intent),
        ("RETRIEVAL", retrieval),
        ("RECOMMENDATION", recommendation),
    ):
        if aggregate.mismatch_count + aggregate.run_failed_count > 1:
            failures.append(f"EXECUTION_{stage_name}_FAILURE_BUDGET_EXCEEDED")
    return tuple(sorted(failures))


def _stage_aggregate(
    results: tuple[CapabilityStageResult, ...],
) -> CapabilityStageAggregate:
    applicable = tuple(result for result in results if result.applicable)
    return CapabilityStageAggregate(
        applicable_count=len(applicable),
        match_count=sum(result.status == "MATCH" for result in applicable),
        mismatch_count=sum(result.status == "MISMATCH" for result in applicable),
        not_run_count=sum(result.status == "NOT_RUN" for result in applicable),
        run_failed_count=sum(result.status == "RUN_FAILED" for result in applicable),
    )


def _short_circuit_run(
    overlay: ScenarioCapabilityOverlay | ScenarioCapabilitySilverAuthorization,
    reviewed: ReviewedValidationScenario,
    tree: CanonicalTree,
    request: IntentRequest,
    *,
    intent: CapabilityStageResult,
    intent_draft_hash: str | None,
    candidate_set_hash: str | None,
) -> ScenarioCapabilityRun:
    suffix = "RUN_FAILED" if intent.status == "RUN_FAILED" else "MISMATCH"
    applicable = overlay.oracle.expected_route == "PROCEED"
    downstream = CapabilityStageResult(
        applicable,
        "NOT_RUN",
        f"UPSTREAM_INTENT_{suffix}",
    )
    return ScenarioCapabilityRun.create(
        source_overlay_hash=overlay.overlay_hash,
        source_reviewed_hash=reviewed.reviewed_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_request_hash=request.request_hash,
        source_intent_draft_hash=intent_draft_hash,
        source_candidate_set_hash=candidate_set_hash,
        source_recommendation_draft_hash=None,
        plan_unit_ref=reviewed.plan_unit_ref,
        candidate_ref=reviewed.candidate_ref,
        expected_route=overlay.oracle.expected_route,
        intent=intent,
        retrieval=downstream,
        recommendation=downstream,
    )


def _intent_request(
    reviewed: ReviewedValidationScenario,
    tree: CanonicalTree,
) -> IntentRequest:
    try:
        return IntentRequest.from_dict(
            {
                "schema_version": REQUEST_SCHEMA_VERSION,
                "requirement_text": reviewed.request.requirement_text,
                "proposed_parent_node_id": reviewed.request.proposed_parent_node_id,
                "node_kind_hint": reviewed.request.node_kind_hint,
                "value_type_hint": reviewed.request.value_type_hint,
                "cardinality_hint": reviewed.request.cardinality_hint,
            },
            tree,
        )
    except IntentValidationError:
        raise ScenarioCapabilityError(
            "CAPABILITY_REVIEWED_REQUEST_INVALID",
            "reviewed scenario request is invalid for the bound tree",
        ) from None


def _intent_matches(draft: ChangeIntentDraft, oracle: CapabilityOracle) -> bool:
    actual_route = (
        "CLARIFY"
        if draft.review_status == "NEEDS_CLARIFICATION"
        else "PROCEED"
    )
    if actual_route != oracle.expected_route:
        return False
    return any(
        _intent_profile_matches(draft, profile)
        for profile in oracle.acceptable_intent_profiles
    )


def _validate_oracle_request_support(
    oracle: CapabilityOracle,
    request: IntentRequest,
) -> None:
    """Reject v1 expectations whose evidence cannot be replayed deterministically."""

    for profile in oracle.acceptable_intent_profiles:
        if tuple(
            expectation.field_name
            for expectation in profile.field_expectations
        ) != tuple(sorted(INTENT_FIELD_NAMES)):
            raise ValueError("v1 intent profiles must explicitly cover every field")
        has_discriminating_expectation = False
        for expectation in profile.field_expectations:
            field_name = expectation.field_name
            if field_name in UNBOUND_V1_INTENT_FIELD_NAMES:
                if expectation.policy != "NOT_COMPARED":
                    raise ValueError("free-text intent fields need v2 support binding")
                continue

            request_field = STRUCTURED_REQUEST_INTENT_FIELDS.get(field_name)
            if request_field is not None:
                expected_value = getattr(request, request_field)
                if expected_value is None or expected_value == "UNKNOWN":
                    if expectation.policy != "NOT_COMPARED":
                        raise ValueError(
                            "missing hints cannot support exact expectations"
                        )
                    continue
                if (
                    expectation.policy != "EXACT_ONE_OF"
                    or expectation.acceptable_values != (expected_value,)
                ):
                    raise ValueError(
                        "explicit hints require exact singleton expectations"
                    )
                has_discriminating_expectation = True
                continue

            if field_name != "clarification_question":
                raise ValueError("intent expectation has no v1 request support rule")
            if oracle.expected_route == "CLARIFY":
                if expectation.policy != "NON_EMPTY":
                    raise ValueError(
                        "CLARIFY requires a non-empty clarification question"
                    )
                has_discriminating_expectation = True
                continue
            if expectation.policy == "NOT_COMPARED":
                continue
            if oracle.expected_route == "PROCEED":
                if (
                    expectation.policy != "EXACT_ONE_OF"
                    or expectation.acceptable_values != (None,)
                ):
                    raise ValueError("PROCEED cannot require a clarification question")
        if not has_discriminating_expectation:
            raise ValueError("intent profile has no request-supported comparison")


def _intent_profile_matches(
    draft: ChangeIntentDraft,
    profile: IntentOracleProfile,
) -> bool:
    for expectation in profile.field_expectations:
        value = getattr(draft.intent, expectation.field_name)
        if expectation.policy == "NOT_COMPARED":
            continue
        if expectation.policy == "NON_EMPTY":
            if isinstance(value, str):
                if not value.strip():
                    return False
            elif not isinstance(value, tuple) or not value:
                return False
            continue
        if expectation.policy == "EMPTY":
            if not isinstance(value, tuple) or value:
                return False
            continue
        if value not in expectation.acceptable_values:
            return False
    return True


def _retrieval_matches(
    candidate_set: CandidateSet,
    oracle: RetrievalOracle,
) -> bool:
    return retrieval_matches_oracle(candidate_set, oracle)


def retrieval_matches_oracle(
    candidate_set: CandidateSet,
    oracle: RetrievalOracle,
) -> bool:
    """Evaluate the strict v1 Hit@K retrieval contract."""

    if not isinstance(candidate_set, CandidateSet) or not isinstance(
        oracle, RetrievalOracle
    ):
        raise TypeError("retrieval evaluation requires trusted contract objects")
    if candidate_set.status not in oracle.allowed_statuses:
        return False
    if not oracle.acceptable_node_ids:
        return True
    return any(
        candidate.rank <= oracle.top_k
        and candidate.node_id in oracle.acceptable_node_ids
        for candidate in candidate_set.candidates
    )


def _recommendation_matches(
    draft: SemanticRecommendationDraft,
    candidate_set: CandidateSet,
    oracle: RecommendationOracle,
) -> bool:
    return recommendation_matches_oracle(draft, candidate_set, oracle)


def recommendation_outcome_from_draft(
    draft: SemanticRecommendationDraft,
    candidate_set: CandidateSet,
) -> RecommendationOracleOutcome:
    """Resolve a run-scoped recommendation back to one stable joint outcome."""

    if not isinstance(draft, SemanticRecommendationDraft) or not isinstance(
        candidate_set, CandidateSet
    ):
        raise TypeError("recommendation evaluation requires trusted contract objects")
    candidate_by_ref = {
        f"C{candidate.rank:03d}": candidate
        for candidate in candidate_set.candidates[:8]
    }
    relation_by_ref = {
        assessment.candidate_ref: assessment.relation
        for assessment in draft.candidate_assessments
    }
    selected_ref = draft.selected_candidate_ref
    target_node_id = (
        candidate_by_ref[selected_ref].node_id
        if selected_ref is not None and selected_ref in candidate_by_ref
        else None
    )
    relation = relation_by_ref.get(selected_ref) if selected_ref is not None else None
    return RecommendationOracleOutcome(
        action=draft.recommended_action,
        target_node_id=target_node_id,
        relation=relation,
    )


def recommendation_matches_oracle(
    draft: SemanticRecommendationDraft,
    candidate_set: CandidateSet,
    oracle: RecommendationOracle,
) -> bool:
    """Evaluate the strict v1 joint recommendation contract."""

    if not isinstance(oracle, RecommendationOracle):
        raise TypeError("recommendation evaluation requires a trusted Oracle")
    actual = recommendation_outcome_from_draft(draft, candidate_set)
    return actual in oracle.acceptable_outcomes


def _validate_run_stage_flow(run: ScenarioCapabilityRun) -> None:
    if not run.intent.applicable or run.intent.status == "NOT_RUN":
        raise ValueError("intent stage must always be applicable and executed")
    proceed = run.expected_route == "PROCEED"
    if run.retrieval.applicable != proceed or run.recommendation.applicable != proceed:
        raise ValueError("run stage applicability disagrees with expected route")
    if not proceed:
        if (
            run.intent.status != "MATCH"
            and run.retrieval.reason_code
            == "EXPECTED_CLARIFICATION_SHORT_CIRCUIT"
        ):
            raise ValueError("clarification short-circuit requires an intent match")
        return
    if run.intent.status != "MATCH":
        if run.retrieval.status != "NOT_RUN" or run.recommendation.status != "NOT_RUN":
            raise ValueError("intent failure must short-circuit later stages")
        return
    if run.retrieval.status == "NOT_RUN":
        raise ValueError("retrieval cannot be skipped after an intent match")
    if run.retrieval.status != "MATCH" and run.recommendation.status != "NOT_RUN":
        raise ValueError("retrieval failure must short-circuit recommendation")
    if run.retrieval.status == "MATCH" and run.recommendation.status == "NOT_RUN":
        raise ValueError("recommendation cannot be skipped after retrieval match")


def _validate_run_source_hashes(run: ScenarioCapabilityRun) -> None:
    if run.intent.status in {"MATCH", "MISMATCH"} and (
        run.source_intent_draft_hash is None
    ):
        raise ValueError("executed intent result requires a draft hash")
    if run.retrieval.status in {"MATCH", "MISMATCH"} and (
        run.source_candidate_set_hash is None
    ):
        raise ValueError("executed retrieval result requires a candidate-set hash")
    if run.recommendation.status in {"MATCH", "MISMATCH"} and (
        run.source_recommendation_draft_hash is None
    ):
        raise ValueError("executed recommendation result requires a draft hash")


def _validate_run_reason_codes(run: ScenarioCapabilityRun) -> None:
    intent_reasons = {
        "MATCH": "INTENT_ORACLE_MATCH",
        "MISMATCH": "INTENT_ORACLE_MISMATCH",
        "RUN_FAILED": "INTENT_PROVIDER_FAILED",
    }
    if run.intent.reason_code != intent_reasons[run.intent.status]:
        raise ValueError("intent reason code is inconsistent")
    if run.expected_route == "CLARIFY":
        for stage in (run.retrieval, run.recommendation):
            expected = (
                "EXPECTED_CLARIFICATION_SHORT_CIRCUIT"
                if run.intent.status == "MATCH"
                else f"UPSTREAM_INTENT_{run.intent.status}"
            )
            if stage.reason_code != expected:
                raise ValueError("clarification short-circuit reason is inconsistent")
        return
    if run.intent.status != "MATCH":
        expected = f"UPSTREAM_INTENT_{run.intent.status}"
        if (
            run.retrieval.reason_code != expected
            or run.recommendation.reason_code != expected
        ):
            raise ValueError("intent short-circuit reason is inconsistent")
        return
    retrieval_reasons = {
        "MATCH": "RETRIEVAL_ORACLE_MATCH",
        "MISMATCH": "RETRIEVAL_ORACLE_MISMATCH",
        "RUN_FAILED": "RETRIEVAL_RUN_FAILED",
    }
    if run.retrieval.reason_code != retrieval_reasons[run.retrieval.status]:
        raise ValueError("retrieval reason code is inconsistent")
    if run.retrieval.status != "MATCH":
        if run.recommendation.reason_code != (
            f"UPSTREAM_RETRIEVAL_{run.retrieval.status}"
        ):
            raise ValueError("retrieval short-circuit reason is inconsistent")
        return
    recommendation_reasons = {
        "MATCH": "RECOMMENDATION_ORACLE_MATCH",
        "MISMATCH": "RECOMMENDATION_ORACLE_MISMATCH",
        "RUN_FAILED": "RECOMMENDATION_PROVIDER_FAILED",
    }
    if (
        run.recommendation.reason_code
        != recommendation_reasons[run.recommendation.status]
    ):
        raise ValueError("recommendation reason code is inconsistent")


def _full_path_status(
    expected_route: str,
    intent: CapabilityStageResult,
    retrieval: CapabilityStageResult,
    recommendation: CapabilityStageResult,
) -> str:
    applicable = (
        (intent,)
        if expected_route == "CLARIFY"
        else (intent, retrieval, recommendation)
    )
    if any(result.status == "RUN_FAILED" for result in applicable):
        return "RUN_FAILED"
    if any(result.status != "MATCH" for result in applicable):
        return "MISMATCH"
    return "MATCH"


def _run_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CAPABILITY_RUN_SCHEMA_VERSION,
        "source_overlay_hash": values["source_overlay_hash"],
        "source_reviewed_hash": values["source_reviewed_hash"],
        "source_snapshot_hash": values["source_snapshot_hash"],
        "source_request_hash": values["source_request_hash"],
        "source_intent_draft_hash": values["source_intent_draft_hash"],
        "source_candidate_set_hash": values["source_candidate_set_hash"],
        "source_recommendation_draft_hash": values[
            "source_recommendation_draft_hash"
        ],
        "plan_unit_ref": values["plan_unit_ref"],
        "candidate_ref": values["candidate_ref"],
        "expected_route": values["expected_route"],
        "intent": values["intent"].to_dict(),
        "retrieval": values["retrieval"].to_dict(),
        "recommendation": values["recommendation"].to_dict(),
        "full_path_status": values["full_path_status"],
    }


def _reviewed_content_digest(
    reviewed: ReviewedValidationScenario,
    oracle: CapabilityOracle,
) -> str:
    return canonical_digest(
        {
            "source_reviewed_hash": reviewed.reviewed_hash,
            "request": {
                "requirement_text": reviewed.request.requirement_text,
                "proposed_parent_node_id": reviewed.request.proposed_parent_node_id,
                "node_kind_hint": reviewed.request.node_kind_hint,
                "value_type_hint": reviewed.request.value_type_hint,
                "cardinality_hint": reviewed.request.cardinality_hint,
            },
            "capability_oracle": oracle.to_dict(),
        }
    )


def _validate_oracle_node_sources(
    oracle: CapabilityOracle,
    tree: CanonicalTree,
) -> None:
    node_ids = {node.node_id for node in tree.nodes}
    oracle_ids = set(oracle.retrieval.acceptable_node_ids)
    oracle_ids.update(
        outcome.target_node_id
        for outcome in oracle.recommendation.acceptable_outcomes
        if outcome.target_node_id is not None
    )
    if not oracle_ids.issubset(node_ids):
        raise ValueError("capability Oracle references nodes outside the bound tree")


def _validate_gate_status(status: str, failure_codes: tuple[str, ...]) -> None:
    if status not in GATE_STATUSES:
        raise ValueError("gate status is unsupported")
    _validate_code_tuple(failure_codes)
    if (status == "PASS") != (not failure_codes):
        raise ValueError("gate status and failure codes are inconsistent")


def _validate_code_tuple(
    values: tuple[str, ...],
    *,
    allowed: set[str] | None = None,
) -> None:
    if (
        not isinstance(values, tuple)
        or values != tuple(sorted(set(values)))
        or any(
            not isinstance(value, str) or _FIXED_CODE.fullmatch(value) is None
            for value in values
        )
    ):
        raise ValueError("fixed codes must be unique and ordered")
    if allowed is not None and any(value not in allowed for value in values):
        raise ValueError("fixed code is outside the public allowlist")


def _validate_node_id_tuple(values: tuple[str, ...]) -> None:
    if (
        not isinstance(values, tuple)
        or len(values) > 64
        or values != tuple(sorted(set(values)))
    ):
        raise ValueError("acceptable node IDs must be unique and ordered")
    for value in values:
        _validate_optional_node_id(value)


def _validate_optional_node_id(value: str | None) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError("stable node ID is invalid")


def _outcome_sort_key(outcome: RecommendationOracleOutcome) -> tuple[str, str, str]:
    return (
        outcome.action,
        outcome.target_node_id or "",
        outcome.relation or "",
    )


def _optional_text_sort_key(value: str | None) -> tuple[int, str]:
    return (0, "") if value is None else (1, value)


def _validate_digest(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a SHA-256 digest")


def _validate_optional_digest(value: Any, field_name: str) -> None:
    if value is not None:
        _validate_digest(value, field_name)


def _validate_reference(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _REFERENCE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an opaque identifier")


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ValueError("recorded_at must use strict RFC3339")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at must include a timezone")


__all__ = [
    "CAPABILITY_ORACLE_REQUEST_POLICY_VERSION",
    "CAPABILITY_OVERLAY_SCHEMA_VERSION",
    "CAPABILITY_SILVER_AUTHORIZATION_SCHEMA_VERSION",
    "CAPABILITY_REPORT_SCHEMA_VERSION",
    "CAPABILITY_RUN_SCHEMA_VERSION",
    "CLARIFICATION_COVERAGE_STATUSES",
    "CapabilityGateReport",
    "CapabilityOracle",
    "CapabilityStageAggregate",
    "CapabilityStageResult",
    "CandidatePreparationGate",
    "IntentFieldExpectation",
    "IntentOracleProfile",
    "OVERLAY_REVIEW_STATUSES",
    "PUBLIC_HARD_FAILURE_CODES",
    "RecommendationOracle",
    "RecommendationOracleOutcome",
    "RetrievalOracle",
    "ScenarioCapabilityError",
    "ScenarioCapabilityOverlay",
    "ScenarioCapabilitySilverAuthorization",
    "ScenarioCapabilityRun",
    "ScenarioPreparationMetrics",
    "STAGE_REASON_CODES",
    "build_capability_gate_report",
    "freeze_capability_overlay",
    "freeze_silver_capability_authorization",
    "recommendation_matches_oracle",
    "recommendation_outcome_from_draft",
    "retrieval_matches_oracle",
    "run_reviewed_capability_scenario",
    "run_silver_capability_scenario",
    "verify_capability_oracle_against_reviewed_request",
    "verify_capability_overlay_against_sources",
    "verify_capability_overlay_for_execution",
    "verify_silver_authorization_for_execution",
]
