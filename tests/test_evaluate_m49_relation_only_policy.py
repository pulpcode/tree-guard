from __future__ import annotations

import importlib.util
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

from treeguard.scenario_capability_validation import RecommendationOracleOutcome
from treeguard.semantic_recommendation import SemanticCandidateAssessment


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/evaluate_m49_relation_only_policy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "treeguard_relation_only_policy_test",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load relation-only policy evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P1 = _load_module()


@dataclass(frozen=True)
class _Candidate:
    candidate_ref: str
    kind: str = "PROPERTY"
    value_type: str | None = "TEXT"
    cardinality: str = "SINGLE"


@dataclass(frozen=True)
class _RankedCandidate:
    rank: int
    node_id: str


@dataclass(frozen=True)
class _Intent:
    node_kind: str = "PROPERTY"
    value_type: str | None = "TEXT"
    cardinality: str = "SINGLE"


@dataclass(frozen=True)
class _Projection:
    intent: _Intent
    candidates: tuple[_Candidate, ...]


@dataclass(frozen=True)
class _CandidateSet:
    candidates: tuple[_RankedCandidate, ...]


@dataclass(frozen=True)
class _Draft:
    candidate_assessments: tuple[SemanticCandidateAssessment, ...]


def _assessment(ref: str, relation: str) -> SemanticCandidateAssessment:
    return SemanticCandidateAssessment(
        candidate_ref=ref,
        relation=relation,
        reason="Synthetic reason.",
    )


class RelationOnlyPolicyTests(unittest.TestCase):
    def test_unique_compatible_equivalent_selects_existing_node(self) -> None:
        projection = _Projection(_Intent(), (_Candidate("C001"),))
        outcome = P1.derive_relation_only_outcome(
            _Draft((_assessment("C001", "SEMANTICALLY_EQUIVALENT"),)),
            _CandidateSet((_RankedCandidate(1, "fictional-node"),)),
            projection,
        )
        self.assertEqual(
            outcome,
            RecommendationOracleOutcome(
                action="USE_EXISTING_NODE",
                target_node_id="fictional-node",
                relation="SEMANTICALLY_EQUIVALENT",
            ),
        )

    def test_contract_conflict_cannot_produce_positive_action(self) -> None:
        projection = _Projection(
            _Intent(),
            (_Candidate("C001", kind="CONCEPT"),),
        )
        outcome = P1.derive_relation_only_outcome(
            _Draft((_assessment("C001", "SEMANTICALLY_EQUIVALENT"),)),
            _CandidateSet((_RankedCandidate(1, "fictional-node"),)),
            projection,
        )
        self.assertEqual(outcome.action, "ABSTAIN")
        self.assertIsNone(outcome.target_node_id)

    def test_multiple_equivalents_require_clarification(self) -> None:
        projection = _Projection(
            _Intent(),
            (_Candidate("C001"), _Candidate("C002")),
        )
        outcome = P1.derive_relation_only_outcome(
            _Draft(
                (
                    _assessment("C001", "SEMANTICALLY_EQUIVALENT"),
                    _assessment("C002", "SEMANTICALLY_EQUIVALENT"),
                )
            ),
            _CandidateSet(
                (
                    _RankedCandidate(1, "fictional-node-1"),
                    _RankedCandidate(2, "fictional-node-2"),
                )
            ),
            projection,
        )
        self.assertEqual(outcome.action, "NEED_CLARIFICATION")
        self.assertIsNone(outcome.target_node_id)

    def test_evidence_gap_precedes_abstain(self) -> None:
        projection = _Projection(_Intent(), (_Candidate("C001"),))
        outcome = P1.derive_relation_only_outcome(
            _Draft((_assessment("C001", "NEED_EVIDENCE"),)),
            _CandidateSet((_RankedCandidate(1, "fictional-node"),)),
            projection,
        )
        self.assertEqual(outcome.action, "NEED_EVIDENCE")

    def test_context_relation_does_not_authorize_addition(self) -> None:
        projection = _Projection(_Intent(), (_Candidate("C001"),))
        outcome = P1.derive_relation_only_outcome(
            _Draft((_assessment("C001", "CONTEXTUALLY_RELATED"),)),
            _CandidateSet((_RankedCandidate(1, "fictional-node"),)),
            projection,
        )
        self.assertEqual(outcome.action, "ABSTAIN")


if __name__ == "__main__":
    unittest.main()
