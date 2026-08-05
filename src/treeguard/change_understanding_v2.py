"""Minimal structural intent and source-bound role evidence for v2 trials."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import (
    CARDINALITIES,
    MODEL_PROVENANCE_STATUS,
    NODE_KINDS,
    IntentRequest,
)
from treeguard.hashing import canonical_digest
from treeguard.model_safety import contains_internal_identifier
from treeguard.models import CanonicalTree
from treeguard.retrieval import CandidateRetrievalError
from treeguard.retrieval_roles import (
    MODEL_OUTPUT_SCHEMA_VERSION as ROLE_MODEL_OUTPUT_SCHEMA_VERSION,
    RetrievalRoleEvidence,
    build_model_retrieval_role_evidence,
)


MODEL_OUTPUT_SCHEMA_VERSION = "change-understanding-model-output.v2"
STRUCTURAL_INTENT_SCHEMA_VERSION = "structural-intent.v2"
UNDERSTANDING_SCHEMA_VERSION = "change-understanding.v2"
_MODEL_OUTPUT_KEYS = {
    "schema_version",
    "node_kind",
    "value_type",
    "cardinality",
    "clarification_question",
    "spans",
}
_STRUCTURAL_INTENT_KEYS = {
    "schema_version",
    "source_request_hash",
    "node_kind",
    "value_type",
    "cardinality",
    "clarification_question",
    "intent_hash",
}
_UNDERSTANDING_KEYS = {
    "schema_version",
    "model_provider",
    "model_capability",
    "model_name",
    "prompt_version",
    "model_provenance_status",
    "semantic_approval",
    "patch_eligible",
    "source_request_hash",
    "source_snapshot_hash",
    "structural_intent",
    "role_evidence",
    "understanding_hash",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SURROGATE_CHARACTER = re.compile(r"[\ud800-\udfff]")
_MAX_TEXT_CHARS = 1_000


class ChangeUnderstandingV2Error(ValueError):
    """A v2 understanding artifact failed its local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class StructuralIntentV2:
    source_request_hash: str
    node_kind: str
    value_type: str | None
    cardinality: str
    clarification_question: str | None
    intent_hash: str

    def __post_init__(self) -> None:
        _digest(self.source_request_hash, "source_request_hash")
        if self.node_kind not in NODE_KINDS:
            raise ValueError("structural intent node_kind is unsupported")
        _optional_text(self.value_type, "value_type")
        if self.cardinality not in CARDINALITIES:
            raise ValueError("structural intent cardinality is unsupported")
        _optional_text(self.clarification_question, "clarification_question")
        _digest(self.intent_hash, "intent_hash")
        if self.intent_hash != canonical_digest(self._payload()):
            raise ValueError("structural intent hash does not match its payload")

    @property
    def review_status(self) -> str:
        return (
            "NEEDS_CLARIFICATION"
            if self.clarification_question is not None
            else "READY_FOR_HUMAN_REVIEW"
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": STRUCTURAL_INTENT_SCHEMA_VERSION,
            "source_request_hash": self.source_request_hash,
            "node_kind": self.node_kind,
            "value_type": self.value_type,
            "cardinality": self.cardinality,
            "clarification_question": self.clarification_question,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "intent_hash": self.intent_hash}

    @classmethod
    def from_model_values(
        cls,
        *,
        node_kind: Any,
        value_type: Any,
        cardinality: Any,
        clarification_question: Any,
        request: IntentRequest,
    ) -> "StructuralIntentV2":
        if not isinstance(request, IntentRequest):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_SOURCE_INVALID",
                "structural intent requires an IntentRequest",
            )
        parsed_kind = _enum(
            node_kind,
            NODE_KINDS,
            "UNDERSTANDING_V2_NODE_KIND_INVALID",
        )
        parsed_value_type = _parsed_optional_text(
            value_type,
            "UNDERSTANDING_V2_VALUE_TYPE_INVALID",
        )
        parsed_cardinality = _enum(
            cardinality,
            CARDINALITIES,
            "UNDERSTANDING_V2_CARDINALITY_INVALID",
        )
        parsed_question = _parsed_optional_text(
            clarification_question,
            "UNDERSTANDING_V2_CLARIFICATION_INVALID",
        )
        if (
            request.node_kind_hint != "UNKNOWN"
            and parsed_kind != request.node_kind_hint
        ) or (
            request.value_type_hint is not None
            and parsed_value_type != request.value_type_hint
        ) or (
            request.cardinality_hint != "UNKNOWN"
            and parsed_cardinality != request.cardinality_hint
        ):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_HINT_CONFLICT",
                "structural intent conflicts with explicit request hints",
            )
        payload = {
            "schema_version": STRUCTURAL_INTENT_SCHEMA_VERSION,
            "source_request_hash": request.request_hash,
            "node_kind": parsed_kind,
            "value_type": parsed_value_type,
            "cardinality": parsed_cardinality,
            "clarification_question": parsed_question,
        }
        return cls(
            source_request_hash=request.request_hash,
            node_kind=parsed_kind,
            value_type=parsed_value_type,
            cardinality=parsed_cardinality,
            clarification_question=parsed_question,
            intent_hash=canonical_digest(payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
    ) -> "StructuralIntentV2":
        if not isinstance(payload, dict) or set(payload) != _STRUCTURAL_INTENT_KEYS:
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_INTENT_FIELDS_INVALID",
                "stored structural intent must use exact fields",
            )
        if payload["schema_version"] != STRUCTURAL_INTENT_SCHEMA_VERSION:
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_INTENT_VERSION_INVALID",
                "stored structural intent version is unsupported",
            )
        try:
            intent = cls.from_model_values(
                node_kind=payload["node_kind"],
                value_type=payload["value_type"],
                cardinality=payload["cardinality"],
                clarification_question=payload["clarification_question"],
                request=request,
            )
        except (KeyError, TypeError, ValueError):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_INTENT_INVALID",
                "stored structural intent failed local validation",
            ) from None
        if intent.to_dict() != payload:
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_INTENT_SOURCE_MISMATCH",
                "stored structural intent does not bind the current request",
            )
        return intent


@dataclass(frozen=True, slots=True)
class ChangeUnderstandingV2:
    model_provider: str
    model_capability: str
    model_name: str
    prompt_version: str
    source_request_hash: str
    source_snapshot_hash: str
    structural_intent: StructuralIntentV2
    role_evidence: RetrievalRoleEvidence
    understanding_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "model_provider",
            "model_capability",
            "model_name",
            "prompt_version",
        ):
            _required_text(getattr(self, field_name), field_name)
        _digest(self.source_request_hash, "source_request_hash")
        _digest(self.source_snapshot_hash, "source_snapshot_hash")
        if not isinstance(self.structural_intent, StructuralIntentV2):
            raise ValueError("understanding requires StructuralIntentV2")
        if not isinstance(self.role_evidence, RetrievalRoleEvidence):
            raise ValueError("understanding requires RetrievalRoleEvidence")
        if (
            self.structural_intent.source_request_hash
            != self.source_request_hash
            or self.role_evidence.source_request_hash
            != self.source_request_hash
        ):
            raise ValueError("understanding sources do not align")
        _digest(self.understanding_hash, "understanding_hash")
        if self.understanding_hash != canonical_digest(self._payload()):
            raise ValueError("understanding hash does not match its payload")

    @property
    def review_status(self) -> str:
        return self.structural_intent.review_status

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": UNDERSTANDING_SCHEMA_VERSION,
            "model_provider": self.model_provider,
            "model_capability": self.model_capability,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "semantic_approval": False,
            "patch_eligible": False,
            "source_request_hash": self.source_request_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "structural_intent": self.structural_intent.to_dict(),
            "role_evidence": self.role_evidence.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "understanding_hash": self.understanding_hash}

    @classmethod
    def from_model_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        tree: CanonicalTree,
        *,
        model_provider: str,
        model_capability: str,
        model_name: str,
        prompt_version: str,
    ) -> "ChangeUnderstandingV2":
        _validate_sources(request, tree)
        if not isinstance(payload, dict) or set(payload) != _MODEL_OUTPUT_KEYS:
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_MODEL_FIELDS_INVALID",
                "model output must use exact v2 fields",
            )
        if payload["schema_version"] != MODEL_OUTPUT_SCHEMA_VERSION:
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_MODEL_VERSION_INVALID",
                "model output uses an unsupported v2 version",
            )
        intent = StructuralIntentV2.from_model_values(
            node_kind=payload["node_kind"],
            value_type=payload["value_type"],
            cardinality=payload["cardinality"],
            clarification_question=payload["clarification_question"],
            request=request,
        )
        if intent.clarification_question is not None and contains_internal_identifier(
            (intent.clarification_question,),
            (node.node_id for node in tree.nodes),
        ):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_INTERNAL_ID_FORBIDDEN",
                "clarification text must not contain internal identifiers",
            )
        try:
            evidence = build_model_retrieval_role_evidence(
                {
                    "schema_version": ROLE_MODEL_OUTPUT_SCHEMA_VERSION,
                    "spans": payload["spans"],
                },
                request,
            )
        except CandidateRetrievalError as exc:
            raise ChangeUnderstandingV2Error(
                f"UNDERSTANDING_V2_{exc.code}",
                "model role evidence failed source-bound validation",
            ) from None
        metadata = {
            "model_provider": _parsed_required_text(
                model_provider,
                "UNDERSTANDING_V2_MODEL_METADATA_INVALID",
            ),
            "model_capability": _parsed_required_text(
                model_capability,
                "UNDERSTANDING_V2_MODEL_METADATA_INVALID",
            ),
            "model_name": _parsed_required_text(
                model_name,
                "UNDERSTANDING_V2_MODEL_METADATA_INVALID",
            ),
            "prompt_version": _parsed_required_text(
                prompt_version,
                "UNDERSTANDING_V2_MODEL_METADATA_INVALID",
            ),
        }
        artifact_payload = {
            "schema_version": UNDERSTANDING_SCHEMA_VERSION,
            **metadata,
            "model_provenance_status": MODEL_PROVENANCE_STATUS,
            "semantic_approval": False,
            "patch_eligible": False,
            "source_request_hash": request.request_hash,
            "source_snapshot_hash": tree.snapshot_hash,
            "structural_intent": intent.to_dict(),
            "role_evidence": evidence.to_dict(),
        }
        return cls(
            **metadata,
            source_request_hash=request.request_hash,
            source_snapshot_hash=tree.snapshot_hash,
            structural_intent=intent,
            role_evidence=evidence,
            understanding_hash=canonical_digest(artifact_payload),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
        tree: CanonicalTree,
    ) -> "ChangeUnderstandingV2":
        _validate_sources(request, tree)
        if not isinstance(payload, dict) or set(payload) != _UNDERSTANDING_KEYS:
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_FIELDS_INVALID",
                "stored understanding must use exact fields",
            )
        if (
            payload["schema_version"] != UNDERSTANDING_SCHEMA_VERSION
            or payload["model_provenance_status"] != MODEL_PROVENANCE_STATUS
            or payload["semantic_approval"] is not False
            or payload["patch_eligible"] is not False
        ):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_POLICY_INVALID",
                "stored understanding violates its fixed policy",
            )
        intent = StructuralIntentV2.from_dict(
            payload["structural_intent"],
            request,
        )
        if intent.clarification_question is not None and contains_internal_identifier(
            (intent.clarification_question,),
            (node.node_id for node in tree.nodes),
        ):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_INTERNAL_ID_FORBIDDEN",
                "clarification text must not contain internal identifiers",
            )
        try:
            evidence = RetrievalRoleEvidence.from_dict(
                payload["role_evidence"],
                request,
            )
            artifact = cls(
                model_provider=payload["model_provider"],
                model_capability=payload["model_capability"],
                model_name=payload["model_name"],
                prompt_version=payload["prompt_version"],
                source_request_hash=payload["source_request_hash"],
                source_snapshot_hash=payload["source_snapshot_hash"],
                structural_intent=intent,
                role_evidence=evidence,
                understanding_hash=payload["understanding_hash"],
            )
        except (CandidateRetrievalError, KeyError, TypeError, ValueError):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_INVALID",
                "stored understanding failed local validation",
            ) from None
        if (
            artifact.source_request_hash != request.request_hash
            or artifact.source_snapshot_hash != tree.snapshot_hash
        ):
            raise ChangeUnderstandingV2Error(
                "UNDERSTANDING_V2_SOURCE_MISMATCH",
                "stored understanding does not bind trusted sources",
            )
        return artifact


def _validate_sources(request: IntentRequest, tree: CanonicalTree) -> None:
    if (
        not isinstance(request, IntentRequest)
        or not isinstance(tree, CanonicalTree)
        or not tree.is_resource_map
    ):
        raise ChangeUnderstandingV2Error(
            "UNDERSTANDING_V2_SOURCE_INVALID",
            "v2 understanding requires trusted resource sources",
        )


def _enum(value: Any, allowed: set[str], code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ChangeUnderstandingV2Error(code, "value is not allowlisted")
    return value


def _required_text(value: Any, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _MAX_TEXT_CHARS
        or _CONTROL_CHARACTER.search(value) is not None
        or _SURROGATE_CHARACTER.search(value) is not None
    ):
        raise ValueError(f"{field_name} must be bounded printable text")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _parsed_required_text(value: Any, code: str) -> str:
    try:
        return _required_text(value, "model_metadata").strip()
    except ValueError:
        raise ChangeUnderstandingV2Error(
            code,
            "model metadata must be bounded printable text",
        ) from None


def _parsed_optional_text(value: Any, code: str) -> str | None:
    try:
        parsed = _optional_text(value, "model_text")
        return parsed.strip() if parsed is not None else None
    except ValueError:
        raise ChangeUnderstandingV2Error(
            code,
            "model text must be bounded printable text or null",
        ) from None


def _digest(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a SHA-256 digest")


__all__ = [
    "MODEL_OUTPUT_SCHEMA_VERSION",
    "STRUCTURAL_INTENT_SCHEMA_VERSION",
    "UNDERSTANDING_SCHEMA_VERSION",
    "ChangeUnderstandingV2",
    "ChangeUnderstandingV2Error",
    "StructuralIntentV2",
]
