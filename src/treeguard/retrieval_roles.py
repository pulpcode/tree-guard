"""Source-bound role evidence for the Retrieval R1 calibration upper bound."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from treeguard.change_intent import IntentConfirmation, IntentRequest
from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree
from treeguard.retrieval import CandidateRetrievalError
from treeguard.retrieval_query import (
    build_decoupled_candidate_set,
    build_retrieval_query,
)


EVIDENCE_SCHEMA_VERSION = "retrieval-role-evidence.v1"
MODEL_OUTPUT_SCHEMA_VERSION = "retrieval-role-model-output.v1"
RESULT_SCHEMA_VERSION = "role-candidate-set.v1"
ALGORITHM_VERSION = "treeguard.decoupled-role-evidence-retrieval.v1"
RETRIEVAL_SEMANTICS = "DECOUPLED_REQUIREMENT_ROLE_EVIDENCE"
PROVENANCE = "CODEX_SILVER_CALIBRATION"
MODEL_PROVENANCE = "UNVERIFIED_MODEL_CALIBRATION"
DEFAULT_MAX_CANDIDATES = 20
ROLE_ORDER = {"TARGET": 0, "SCOPE": 1, "EXCLUSION": 2}
_TARGET_NAME_WEIGHT = 30_000_000
_TARGET_PATH_WEIGHT = 15_000_000
_SCOPE_NAME_WEIGHT = 2_000_000
_SCOPE_PATH_WEIGHT = 5_000_000
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_WHITESPACE = re.compile(r"\s+")
_MODEL_OUTPUT_KEYS = {"schema_version", "spans"}
_MODEL_SPAN_KEYS = {"role", "text"}
_EVIDENCE_KEYS = {
    "schema_version",
    "provenance",
    "calibration_only",
    "gold_eligible",
    "gate_eligible",
    "production_qualification",
    "source_request_hash",
    "spans",
    "evidence_hash",
}
_EVIDENCE_SPAN_KEYS = {"role", "text", "start", "end"}


@dataclass(frozen=True, slots=True)
class RetrievalRoleSpan:
    role: str
    text: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.role not in ROLE_ORDER:
            raise ValueError("retrieval role span has an unsupported role")
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("retrieval role span text must be non-empty")
        if (
            not isinstance(self.start, int)
            or isinstance(self.start, bool)
            or not isinstance(self.end, int)
            or isinstance(self.end, bool)
            or self.start < 0
            or self.end <= self.start
            or self.end - self.start != len(self.text)
        ):
            raise ValueError("retrieval role span range is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "text": self.text,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True, slots=True)
class RetrievalRoleEvidence:
    provenance: str
    source_request_hash: str
    spans: tuple[RetrievalRoleSpan, ...]
    evidence_hash: str

    def __post_init__(self) -> None:
        if self.provenance not in {PROVENANCE, MODEL_PROVENANCE}:
            raise ValueError("retrieval role evidence provenance is invalid")
        for digest in (self.source_request_hash, self.evidence_hash):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("retrieval role evidence hashes must be SHA-256")
        if (
            not isinstance(self.spans, tuple)
            or not self.spans
            or len(self.spans) > 8
            or any(not isinstance(span, RetrievalRoleSpan) for span in self.spans)
        ):
            raise ValueError("retrieval role evidence spans are invalid")
        keys = tuple(_span_key(span) for span in self.spans)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("retrieval role evidence spans are not canonical")
        if not any(span.role == "TARGET" for span in self.spans):
            raise ValueError("retrieval role evidence requires a TARGET span")
        if self.evidence_hash != canonical_digest(self._payload()):
            raise ValueError("retrieval role evidence hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "provenance": self.provenance,
            "calibration_only": True,
            "gold_eligible": False,
            "gate_eligible": False,
            "production_qualification": False,
            "source_request_hash": self.source_request_hash,
            "spans": [span.to_dict() for span in self.spans],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["evidence_hash"] = self.evidence_hash
        return payload

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_OUTPUT_SCHEMA_VERSION,
            "spans": [
                {"role": span.role, "text": span.text}
                for span in self.spans
            ],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Any,
        request: IntentRequest,
    ) -> "RetrievalRoleEvidence":
        if not isinstance(payload, dict) or set(payload) != _EVIDENCE_KEYS:
            raise CandidateRetrievalError(
                "ROLE_EVIDENCE_FIELDS_INVALID",
                "stored role evidence must use the exact contract fields",
            )
        if (
            payload["schema_version"] != EVIDENCE_SCHEMA_VERSION
            or payload["provenance"] not in {PROVENANCE, MODEL_PROVENANCE}
            or payload["calibration_only"] is not True
            or payload["gold_eligible"] is not False
            or payload["gate_eligible"] is not False
            or payload["production_qualification"] is not False
            or not isinstance(payload["spans"], list)
        ):
            raise CandidateRetrievalError(
                "ROLE_EVIDENCE_POLICY_INVALID",
                "stored role evidence violates its fixed policy",
            )
        try:
            spans = tuple(
                RetrievalRoleSpan(
                    role=item["role"],
                    text=item["text"],
                    start=item["start"],
                    end=item["end"],
                )
                for item in payload["spans"]
                if isinstance(item, dict)
                and set(item) == _EVIDENCE_SPAN_KEYS
            )
            if len(spans) != len(payload["spans"]):
                raise ValueError
            evidence = cls(
                provenance=payload["provenance"],
                source_request_hash=payload["source_request_hash"],
                spans=spans,
                evidence_hash=payload["evidence_hash"],
            )
            verify_retrieval_role_evidence(evidence, request)
            return evidence
        except (KeyError, TypeError, ValueError):
            raise CandidateRetrievalError(
                "ROLE_EVIDENCE_INVALID",
                "stored role evidence failed local validation",
            ) from None


@dataclass(frozen=True, slots=True)
class RoleCandidateScore:
    base_total: int
    target_name_matches: int
    target_path_matches: int
    scope_name_matches: int
    scope_path_matches: int
    total: int

    def __post_init__(self) -> None:
        components = (
            self.base_total,
            self.target_name_matches,
            self.target_path_matches,
            self.scope_name_matches,
            self.scope_path_matches,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in components
        ):
            raise ValueError("role candidate score components are invalid")
        expected = (
            self.base_total
            + self.target_name_matches * _TARGET_NAME_WEIGHT
            + self.target_path_matches * _TARGET_PATH_WEIGHT
            + self.scope_name_matches * _SCOPE_NAME_WEIGHT
            + self.scope_path_matches * _SCOPE_PATH_WEIGHT
        )
        if not isinstance(self.total, int) or isinstance(self.total, bool):
            raise ValueError("role candidate score total must be an integer")
        if self.total != expected:
            raise ValueError("role candidate score total does not match components")

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_total": self.base_total,
            "target_name_matches": self.target_name_matches,
            "target_path_matches": self.target_path_matches,
            "scope_name_matches": self.scope_name_matches,
            "scope_path_matches": self.scope_path_matches,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class RoleCandidate:
    rank: int
    node_id: str
    score: RoleCandidateScore

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rank, int)
            or isinstance(self.rank, bool)
            or self.rank < 1
            or not isinstance(self.node_id, str)
            or not self.node_id
            or not isinstance(self.score, RoleCandidateScore)
        ):
            raise ValueError("role candidate is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class RoleCandidateSet:
    source_evidence_hash: str
    source_query_hash: str
    source_snapshot_hash: str
    status: str
    max_candidates: int
    candidates: tuple[RoleCandidate, ...]
    candidate_set_hash: str

    def __post_init__(self) -> None:
        for digest in (
            self.source_evidence_hash,
            self.source_query_hash,
            self.source_snapshot_hash,
            self.candidate_set_hash,
        ):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("role candidate hashes must be SHA-256")
        if self.status not in {
            "CANDIDATES_READY",
            "NO_CANDIDATES",
            "INSUFFICIENT_SIGNAL",
        }:
            raise ValueError("role candidate status is invalid")
        if (
            not isinstance(self.max_candidates, int)
            or isinstance(self.max_candidates, bool)
            or self.max_candidates < 1
            or self.max_candidates > 100
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > self.max_candidates
            or any(not isinstance(item, RoleCandidate) for item in self.candidates)
        ):
            raise ValueError("role candidate collection is invalid")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("role candidate ranks are not canonical")
        order = tuple((-item.score.total, item.node_id) for item in self.candidates)
        if order != tuple(sorted(order)):
            raise ValueError("role candidates are not canonically ordered")
        if self.status == "CANDIDATES_READY" and not self.candidates:
            raise ValueError("ready role result requires candidates")
        if self.status != "CANDIDATES_READY" and self.candidates:
            raise ValueError("non-ready role result cannot contain candidates")
        if self.candidate_set_hash != canonical_digest(self._payload()):
            raise ValueError("role candidate hash does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "source_evidence_hash": self.source_evidence_hash,
            "source_query_hash": self.source_query_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "status": self.status,
            "embedding_used": False,
            "allows_addition": False,
            "max_candidates": self.max_candidates,
            "candidates": [item.to_dict() for item in self.candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["candidate_set_hash"] = self.candidate_set_hash
        return payload

    def aggregate_report(self) -> dict[str, Any]:
        return {
            "report_version": "role-retrieval-aggregate.v1",
            "valid": True,
            "status": self.status,
            "retrieval_semantics": RETRIEVAL_SEMANTICS,
            "embedding_used": False,
            "allows_addition": False,
            "candidate_count": len(self.candidates),
        }


def build_retrieval_role_evidence(
    request: IntentRequest,
    annotations: tuple[tuple[str, str], ...],
) -> RetrievalRoleEvidence:
    if not isinstance(request, IntentRequest):
        raise CandidateRetrievalError(
            "ROLE_EVIDENCE_REQUEST_INVALID",
            "role evidence requires an IntentRequest",
        )
    if (
        not isinstance(annotations, tuple)
        or not annotations
        or len(annotations) > 8
    ):
        raise CandidateRetrievalError(
            "ROLE_EVIDENCE_ANNOTATIONS_INVALID",
            "role evidence annotations are invalid",
        )
    spans = []
    has_target = False
    for annotation in annotations:
        if (
            not isinstance(annotation, tuple)
            or len(annotation) != 2
            or annotation[0] not in ROLE_ORDER
            or not isinstance(annotation[1], str)
            or not annotation[1]
        ):
            raise CandidateRetrievalError(
                "ROLE_EVIDENCE_ANNOTATIONS_INVALID",
                "role evidence annotation shape is invalid",
            )
        role, text = annotation
        has_target = has_target or role == "TARGET"
        start = request.requirement_text.find(text)
        if start < 0:
            raise CandidateRetrievalError(
                "ROLE_EVIDENCE_SPAN_NOT_FOUND",
                "role evidence text is absent from the request",
            )
        if request.requirement_text.find(text, start + 1) >= 0:
            raise CandidateRetrievalError(
                "ROLE_EVIDENCE_SPAN_AMBIGUOUS",
                "role evidence text occurs more than once",
            )
        spans.append(RetrievalRoleSpan(role, text, start, start + len(text)))
    if not has_target:
        raise CandidateRetrievalError(
            "ROLE_EVIDENCE_TARGET_MISSING",
            "role evidence requires a TARGET annotation",
        )
    ranges = tuple((span.start, span.end) for span in spans)
    if len(set(ranges)) != len(ranges):
        raise CandidateRetrievalError(
            "ROLE_EVIDENCE_ANNOTATIONS_DUPLICATE",
            "role evidence annotations contain a duplicate source span",
        )
    spans.sort(key=_span_key)
    return _build_evidence(request, spans, PROVENANCE)


def _build_evidence(
    request: IntentRequest,
    spans: list[RetrievalRoleSpan],
    provenance: str,
) -> RetrievalRoleEvidence:
    payload = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "provenance": provenance,
        "calibration_only": True,
        "gold_eligible": False,
        "gate_eligible": False,
        "production_qualification": False,
        "source_request_hash": request.request_hash,
        "spans": [span.to_dict() for span in spans],
    }
    return RetrievalRoleEvidence(
        provenance=provenance,
        source_request_hash=request.request_hash,
        spans=tuple(spans),
        evidence_hash=canonical_digest(payload),
    )


def build_model_retrieval_role_evidence(
    payload: Any,
    request: IntentRequest,
) -> RetrievalRoleEvidence:
    if not isinstance(payload, dict) or set(payload) != _MODEL_OUTPUT_KEYS:
        raise CandidateRetrievalError(
            "ROLE_MODEL_FIELDS_INVALID",
            "role model output must use the exact contract fields",
        )
    if payload["schema_version"] != MODEL_OUTPUT_SCHEMA_VERSION:
        raise CandidateRetrievalError(
            "ROLE_MODEL_VERSION_INVALID",
            "role model output schema version is unsupported",
        )
    raw_spans = payload["spans"]
    if (
        not isinstance(raw_spans, list)
        or not raw_spans
        or len(raw_spans) > 8
    ):
        raise CandidateRetrievalError(
            "ROLE_MODEL_SPANS_INVALID",
            "role model output spans are invalid",
        )
    annotations = []
    for raw_span in raw_spans:
        if not isinstance(raw_span, dict) or set(raw_span) != _MODEL_SPAN_KEYS:
            raise CandidateRetrievalError(
                "ROLE_MODEL_SPANS_INVALID",
                "role model output span fields are invalid",
            )
        role = raw_span["role"]
        text = raw_span["text"]
        if role not in ROLE_ORDER:
            raise CandidateRetrievalError(
                "ROLE_MODEL_ROLE_INVALID",
                "role model output contains an unsupported role",
            )
        if not isinstance(text, str) or not text:
            raise CandidateRetrievalError(
                "ROLE_MODEL_SPANS_INVALID",
                "role model output span text is invalid",
            )
        annotations.append((role, text))
    try:
        evidence = build_retrieval_role_evidence(request, tuple(annotations))
    except CandidateRetrievalError as exc:
        code = {
            "ROLE_EVIDENCE_TARGET_MISSING": "ROLE_MODEL_TARGET_MISSING",
            "ROLE_EVIDENCE_SPAN_NOT_FOUND": "ROLE_MODEL_SPAN_NOT_FOUND",
            "ROLE_EVIDENCE_SPAN_AMBIGUOUS": "ROLE_MODEL_SPAN_AMBIGUOUS",
            "ROLE_EVIDENCE_ANNOTATIONS_DUPLICATE": "ROLE_MODEL_SPANS_DUPLICATE",
        }.get(exc.code, "ROLE_MODEL_SPANS_INVALID")
        raise CandidateRetrievalError(
            code,
            "role model output did not bind valid source spans",
        ) from None
    return _build_evidence(request, list(evidence.spans), MODEL_PROVENANCE)


def build_role_candidate_set(
    evidence: RetrievalRoleEvidence,
    request: IntentRequest,
    confirmation: IntentConfirmation,
    tree: CanonicalTree,
    *,
    include_model_expansion: bool = True,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> RoleCandidateSet:
    verify_retrieval_role_evidence(evidence, request)
    if (
        not isinstance(max_candidates, int)
        or isinstance(max_candidates, bool)
        or max_candidates < 1
        or max_candidates > 100
    ):
        raise CandidateRetrievalError(
            "CANDIDATE_LIMIT_INVALID",
            "max_candidates must be between one and one hundred",
        )
    query = build_retrieval_query(
        request,
        confirmation,
        tree,
        include_model_expansion=include_model_expansion,
    )
    base = build_decoupled_candidate_set(query, tree, max_candidates=100)
    if base.status != "CANDIDATES_READY":
        return _candidate_set(
            evidence,
            query.query_hash,
            tree,
            base.status,
            max_candidates,
            (),
        )
    phrases = {
        role: {
            _normalize_text(span.text)
            for span in evidence.spans
            if span.role == role
        }
        for role in ROLE_ORDER
    }
    node_by_id = {node.node_id: node for node in tree.nodes}
    scored = []
    for candidate in base.candidates:
        node = node_by_id[candidate.node_id]
        name_text = _normalize_text(" ".join((node.name, node.label)))
        path_text = _normalize_text(" ".join(node.path_labels))
        if _match_count(phrases["EXCLUSION"], name_text) or _match_count(
            phrases["EXCLUSION"], path_text
        ):
            continue
        target_name = _match_count(phrases["TARGET"], name_text)
        target_path = _match_count(phrases["TARGET"], path_text)
        if target_name + target_path == 0:
            continue
        scope_name = _match_count(phrases["SCOPE"], name_text)
        scope_path = _match_count(phrases["SCOPE"], path_text)
        total = (
            candidate.score.total
            + target_name * _TARGET_NAME_WEIGHT
            + target_path * _TARGET_PATH_WEIGHT
            + scope_name * _SCOPE_NAME_WEIGHT
            + scope_path * _SCOPE_PATH_WEIGHT
        )
        score = RoleCandidateScore(
            base_total=candidate.score.total,
            target_name_matches=target_name,
            target_path_matches=target_path,
            scope_name_matches=scope_name,
            scope_path_matches=scope_path,
            total=total,
        )
        scored.append((-total, candidate.node_id, score))
    scored.sort(key=lambda item: (item[0], item[1]))
    candidates = tuple(
        RoleCandidate(rank, node_id, score)
        for rank, (_, node_id, score) in enumerate(scored[:max_candidates], start=1)
    )
    return _candidate_set(
        evidence,
        query.query_hash,
        tree,
        "CANDIDATES_READY" if candidates else "NO_CANDIDATES",
        max_candidates,
        candidates,
    )


def verify_retrieval_role_evidence(
    evidence: RetrievalRoleEvidence,
    request: IntentRequest,
) -> None:
    if not isinstance(evidence, RetrievalRoleEvidence) or not isinstance(
        request, IntentRequest
    ):
        raise CandidateRetrievalError(
            "ROLE_EVIDENCE_SOURCE_INVALID",
            "role evidence sources are invalid",
        )
    if evidence.source_request_hash != request.request_hash:
        raise CandidateRetrievalError(
            "ROLE_EVIDENCE_SOURCE_MISMATCH",
            "role evidence does not bind the current request",
        )
    if any(
        request.requirement_text[span.start : span.end] != span.text
        for span in evidence.spans
    ):
        raise CandidateRetrievalError(
            "ROLE_EVIDENCE_SPAN_MISMATCH",
            "role evidence span does not match the request",
        )


def _span_key(span: RetrievalRoleSpan) -> tuple[int, int, int, str]:
    return span.start, span.end, ROLE_ORDER[span.role], span.text


def _normalize_text(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _match_count(phrases: set[str], document_text: str) -> int:
    return sum(phrase in document_text for phrase in phrases)


def _candidate_set(
    evidence: RetrievalRoleEvidence,
    query_hash: str,
    tree: CanonicalTree,
    status: str,
    max_candidates: int,
    candidates: tuple[RoleCandidate, ...],
) -> RoleCandidateSet:
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "retrieval_semantics": RETRIEVAL_SEMANTICS,
        "source_evidence_hash": evidence.evidence_hash,
        "source_query_hash": query_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "status": status,
        "embedding_used": False,
        "allows_addition": False,
        "max_candidates": max_candidates,
        "candidates": [item.to_dict() for item in candidates],
    }
    return RoleCandidateSet(
        source_evidence_hash=evidence.evidence_hash,
        source_query_hash=query_hash,
        source_snapshot_hash=tree.snapshot_hash,
        status=status,
        max_candidates=max_candidates,
        candidates=candidates,
        candidate_set_hash=canonical_digest(payload),
    )


__all__ = [
    "ALGORITHM_VERSION",
    "MODEL_OUTPUT_SCHEMA_VERSION",
    "MODEL_PROVENANCE",
    "PROVENANCE",
    "ROLE_ORDER",
    "RetrievalRoleEvidence",
    "RetrievalRoleSpan",
    "RoleCandidate",
    "RoleCandidateScore",
    "RoleCandidateSet",
    "build_retrieval_role_evidence",
    "build_model_retrieval_role_evidence",
    "build_role_candidate_set",
    "verify_retrieval_role_evidence",
]
