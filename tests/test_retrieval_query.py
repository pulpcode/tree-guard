from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard import load_tree_export
from treeguard.change_intent import (
    ChangeIntentDraft,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.retrieval import CandidateRetrievalError
from treeguard.retrieval_anchor import (
    build_anchored_candidate_set,
    build_anchored_retrieval_query,
)
from treeguard.retrieval_phrase import (
    build_phrase_candidate_set,
    build_phrase_retrieval_query,
)
from treeguard.retrieval_query import (
    RETRIEVAL_SEMANTICS,
    build_decoupled_candidate_set,
    build_node_search_documents,
    build_retrieval_query,
)
from treeguard.retrieval_roles import (
    MODEL_PROVENANCE,
    build_model_retrieval_role_evidence,
    build_retrieval_role_evidence,
    build_role_candidate_set,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def _sources(
    *,
    requirement_text: str = "Reuse the existing Display height property.",
    subject: str | None = "Unrelated quasar wording",
    assumptions: tuple[str, ...] = ("Untrusted nebula assumption",),
    proposed_parent_node_id: str | None = "node-003",
):
    imported = load_tree_export(FIXTURE_PATH)
    assert imported.tree is not None
    tree = imported.tree
    request = IntentRequest.from_dict(
        {
            "schema_version": "intent-request.v1",
            "requirement_text": requirement_text,
            "proposed_parent_node_id": proposed_parent_node_id,
            "node_kind_hint": "PROPERTY",
            "value_type_hint": "float",
            "cardinality_hint": "SINGLE",
        },
        tree,
    )
    draft = ChangeIntentDraft.from_model_dict(
        {
            "schema_version": "change-intent-model-output.v1",
            "subject": subject,
            "role": None,
            "scenario": None,
            "lifecycle": None,
            "ownership": "UNKNOWN",
            "node_kind": "PROPERTY",
            "value_type": "float",
            "cardinality": "SINGLE",
            "confirmed_facts": [],
            "assumptions": list(assumptions),
            "evidence_gaps": [],
            "clarification_question": None,
        },
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.change-intent.zh.v4",
    )
    action = IntentReviewAction.from_dict(
        {
            "schema_version": "intent-review-action.v1",
            "expected_draft_hash": draft.draft_hash,
            "decision": "CONFIRM_FOR_RETRIEVAL",
            "reviewer_ref": "fictional-steward",
            "recorded_at": "2030-01-02T03:04:05Z",
            "confirmed_intent": draft.intent.to_dict(),
        }
    )
    return tree, request, apply_intent_review(request, draft, action, tree)


class RetrievalQueryTests(unittest.TestCase):
    def test_requirement_text_is_primary_and_assumptions_are_excluded(self) -> None:
        tree, request, confirmation = _sources()

        query = build_retrieval_query(request, confirmation, tree)
        candidate_set = build_decoupled_candidate_set(query, tree)

        self.assertIn("height", query.requirement_terms)
        self.assertIn("quasar", query.expansion_terms)
        self.assertNotIn("nebula", query.requirement_terms)
        self.assertNotIn("nebula", query.expansion_terms)
        self.assertEqual(candidate_set.candidates[0].node_id, "node-008")
        self.assertEqual(
            candidate_set.to_dict()["retrieval_semantics"],
            RETRIEVAL_SEMANTICS,
        )
        self.assertFalse(candidate_set.to_dict()["embedding_used"])
        self.assertFalse(candidate_set.to_dict()["allows_addition"])

    def test_model_expansion_can_be_disabled_without_losing_request_signal(self) -> None:
        tree, request, confirmation = _sources()

        query = build_retrieval_query(
            request,
            confirmation,
            tree,
            include_model_expansion=False,
        )
        candidate_set = build_decoupled_candidate_set(query, tree)

        self.assertEqual(query.expansion_terms, ())
        self.assertEqual(candidate_set.candidates[0].node_id, "node-008")

    def test_parent_is_a_soft_boost_and_does_not_filter_the_complete_tree(self) -> None:
        tree, request, confirmation = _sources(proposed_parent_node_id="node-003")

        candidate_set = build_decoupled_candidate_set(
            build_retrieval_query(request, confirmation, tree),
            tree,
        )

        self.assertIn("node-008", {item.node_id for item in candidate_set.candidates})

    def test_documents_and_results_are_deterministic_under_node_reordering(self) -> None:
        tree, request, confirmation = _sources()
        reordered = replace(tree, nodes=tuple(reversed(tree.nodes)))
        query = build_retrieval_query(request, confirmation, tree)

        first_documents = build_node_search_documents(tree)
        second_documents = build_node_search_documents(reordered)
        first = build_decoupled_candidate_set(query, tree)
        second = build_decoupled_candidate_set(query, reordered)

        self.assertEqual(first_documents, second_documents)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_no_lexical_signal_fails_safe_without_parent_only_candidates(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text="!!!",
            subject=None,
            assumptions=(),
        )

        query = build_retrieval_query(request, confirmation, tree)
        result = build_decoupled_candidate_set(query, tree)

        self.assertEqual(result.status, "INSUFFICIENT_SIGNAL")
        self.assertEqual(result.candidates, ())
        self.assertFalse(result.to_dict()["allows_addition"])

    def test_stale_query_and_invalid_limit_fail_with_stable_codes(self) -> None:
        tree, request, confirmation = _sources()
        query = build_retrieval_query(request, confirmation, tree)

        with self.assertRaises(CandidateRetrievalError) as context:
            build_decoupled_candidate_set(query, replace(tree, snapshot_hash="0" * 64))
        self.assertEqual(context.exception.code, "CANDIDATE_SOURCE_STALE")

        with self.assertRaises(CandidateRetrievalError) as context:
            build_decoupled_candidate_set(query, tree, max_candidates=True)
        self.assertEqual(context.exception.code, "CANDIDATE_LIMIT_INVALID")

    def test_query_and_result_hash_tampering_is_rejected(self) -> None:
        tree, request, confirmation = _sources()
        query = build_retrieval_query(request, confirmation, tree)
        result = build_decoupled_candidate_set(query, tree)

        with self.assertRaises(ValueError):
            replace(query, query_hash="0" * 64)
        with self.assertRaises(ValueError):
            replace(result, candidate_set_hash="0" * 64)
        with self.assertRaises(ValueError):
            replace(result, candidates=tuple(reversed(result.candidates)))

    def test_aggregate_report_does_not_expose_query_or_node_identifiers(self) -> None:
        tree, request, confirmation = _sources()
        result = build_decoupled_candidate_set(
            build_retrieval_query(request, confirmation, tree),
            tree,
        )

        report = result.aggregate_report()
        encoded = repr(report)
        self.assertNotIn(request.requirement_text, encoded)
        self.assertNotIn("node-008", encoded)
        self.assertNotIn(result.source_query_hash, encoded)
        self.assertNotIn(result.source_snapshot_hash, encoded)


class AnchoredRetrievalTests(unittest.TestCase):
    def test_explicit_positive_and_negative_quotes_rerank_the_target(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text=(
                "复用“Display height”，不要误用“Display title”。"
            ),
            subject=None,
            assumptions=(),
            proposed_parent_node_id=None,
        )

        query = build_anchored_retrieval_query(request, confirmation, tree)
        result = build_anchored_candidate_set(query, tree)

        self.assertIn("height", query.positive_anchor_terms)
        self.assertIn("title", query.excluded_anchor_terms)
        self.assertEqual(result.candidates[0].node_id, "node-008")
        self.assertNotIn(
            "node-003",
            {item.node_id for item in result.candidates},
        )

    def test_unmatched_explicit_identifier_produces_no_candidates(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text=(
                "需要定义“m5voidalpha”，当前树未提供可复用证据。"
            ),
            subject=None,
            assumptions=(),
            proposed_parent_node_id=None,
        )

        query = build_anchored_retrieval_query(request, confirmation, tree)
        result = build_anchored_candidate_set(query, tree)

        self.assertIn("m5voidalpha", query.positive_anchor_terms)
        self.assertEqual(result.status, "NO_CANDIDATES")
        self.assertEqual(result.candidates, ())

    def test_anchored_result_is_deterministic_and_hash_bound(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text="复用“Display height”既有属性。",
            subject=None,
            assumptions=(),
        )
        query = build_anchored_retrieval_query(request, confirmation, tree)

        first = build_anchored_candidate_set(query, tree)
        second = build_anchored_candidate_set(
            query,
            replace(tree, nodes=tuple(reversed(tree.nodes))),
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        with self.assertRaises(ValueError):
            replace(query, query_hash="0" * 64)
        with self.assertRaises(ValueError):
            replace(first, candidate_set_hash="0" * 64)


class PhraseRetrievalTests(unittest.TestCase):
    def test_complete_phrases_do_not_penalize_shared_substrings(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text=(
                "复用“Height”，不要误用“Height title”。"
            ),
            subject=None,
            assumptions=(),
            proposed_parent_node_id=None,
        )

        query = build_phrase_retrieval_query(request, confirmation, tree)
        result = build_phrase_candidate_set(query, tree)

        self.assertEqual(query.positive_phrases, ("height",))
        self.assertEqual(query.excluded_phrases, ("height title",))
        self.assertEqual(result.candidates[0].node_id, "node-008")
        self.assertEqual(
            result.candidates[0].score.excluded_name_matches
            + result.candidates[0].score.excluded_path_matches,
            0,
        )

    def test_unmatched_complete_identifier_produces_no_candidates(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text="需要定义“m5voidalpha”，当前树没有对应证据。",
            subject=None,
            assumptions=(),
            proposed_parent_node_id=None,
        )

        query = build_phrase_retrieval_query(request, confirmation, tree)
        result = build_phrase_candidate_set(query, tree)

        self.assertEqual(query.positive_phrases, ("m5voidalpha",))
        self.assertEqual(result.status, "NO_CANDIDATES")
        self.assertEqual(result.candidates, ())

    def test_phrase_result_is_deterministic_and_hash_bound(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text="复用“Display height”既有属性。",
            subject=None,
            assumptions=(),
        )
        query = build_phrase_retrieval_query(request, confirmation, tree)

        first = build_phrase_candidate_set(query, tree)
        second = build_phrase_candidate_set(
            query,
            replace(tree, nodes=tuple(reversed(tree.nodes))),
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        with self.assertRaises(ValueError):
            replace(query, query_hash="0" * 64)
        with self.assertRaises(ValueError):
            replace(query, positive_phrases=(" Height ",))
        with self.assertRaises(ValueError):
            replace(first, candidate_set_hash="0" * 64)


class RoleRetrievalTests(unittest.TestCase):
    def test_model_output_is_strict_source_bound_and_locally_canonicalized(self) -> None:
        _, request, _ = _sources(
            requirement_text="在 CATALOG 范围复用 Height，排除 Display title。"
        )

        evidence = build_model_retrieval_role_evidence(
            {
                "schema_version": "retrieval-role-model-output.v1",
                "spans": [
                    {"role": "EXCLUSION", "text": "Display title"},
                    {"role": "TARGET", "text": "Height"},
                    {"role": "SCOPE", "text": "CATALOG"},
                ],
            },
            request,
        )

        self.assertEqual(evidence.provenance, MODEL_PROVENANCE)
        self.assertEqual(
            [span.role for span in evidence.spans],
            ["SCOPE", "TARGET", "EXCLUSION"],
        )
        self.assertEqual(
            evidence.to_model_dict(),
            {
                "schema_version": "retrieval-role-model-output.v1",
                "spans": [
                    {"role": "SCOPE", "text": "CATALOG"},
                    {"role": "TARGET", "text": "Height"},
                    {"role": "EXCLUSION", "text": "Display title"},
                ],
            },
        )
        schema = json.loads(
            (
                PROJECT_ROOT
                / "contracts/retrieval-role-model-output.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(set(schema["required"]), set(evidence.to_model_dict()))
        self.assertEqual(
            set(schema["properties"]["spans"]["items"]["required"]),
            set(evidence.to_model_dict()["spans"][0]),
        )

        _, unique_request, _ = _sources(requirement_text="Reuse Height")
        with self.assertRaises(CandidateRetrievalError) as context:
            build_model_retrieval_role_evidence(
                {
                    "schema_version": "retrieval-role-model-output.v1",
                    "spans": [
                        {"role": "TARGET", "text": "Height"},
                        {"role": "TARGET", "text": "Height"},
                    ],
                },
                unique_request,
            )
        self.assertEqual(context.exception.code, "ROLE_MODEL_SPANS_DUPLICATE")

    def test_model_output_failures_use_field_level_safe_codes(self) -> None:
        _, request, _ = _sources(requirement_text="Height and Height")
        invalid_cases = (
            ({"schema_version": "retrieval-role-model-output.v1"}, "ROLE_MODEL_FIELDS_INVALID"),
            (
                {
                    "schema_version": "retrieval-role-model-output.v2",
                    "spans": [{"role": "TARGET", "text": "Height"}],
                },
                "ROLE_MODEL_VERSION_INVALID",
            ),
            (
                {
                    "schema_version": "retrieval-role-model-output.v1",
                    "spans": [{"role": "OTHER", "text": "Height"}],
                },
                "ROLE_MODEL_ROLE_INVALID",
            ),
            (
                {
                    "schema_version": "retrieval-role-model-output.v1",
                    "spans": [{"role": "SCOPE", "text": "Height and"}],
                },
                "ROLE_MODEL_TARGET_MISSING",
            ),
            (
                {
                    "schema_version": "retrieval-role-model-output.v1",
                    "spans": [{"role": "TARGET", "text": "Width"}],
                },
                "ROLE_MODEL_SPAN_NOT_FOUND",
            ),
            (
                {
                    "schema_version": "retrieval-role-model-output.v1",
                    "spans": [{"role": "TARGET", "text": "Height"}],
                },
                "ROLE_MODEL_SPAN_AMBIGUOUS",
            ),
        )
        for payload, expected_code in invalid_cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(CandidateRetrievalError) as context:
                    build_model_retrieval_role_evidence(payload, request)
                self.assertEqual(context.exception.code, expected_code)

    def test_role_evidence_prioritizes_target_and_excludes_negative(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text=(
                "在“CATALOG”范围复用“Height”，排除“Display title”。"
            ),
            subject=None,
            assumptions=(),
            proposed_parent_node_id=None,
        )
        evidence = build_retrieval_role_evidence(
            request,
            (
                ("SCOPE", "CATALOG"),
                ("TARGET", "Height"),
                ("EXCLUSION", "Display title"),
            ),
        )

        result = build_role_candidate_set(
            evidence,
            request,
            confirmation,
            tree,
        )

        self.assertEqual(result.candidates[0].node_id, "node-008")
        self.assertNotIn("node-003", {item.node_id for item in result.candidates})
        self.assertEqual(
            [span.role for span in evidence.spans],
            ["SCOPE", "TARGET", "EXCLUSION"],
        )

    def test_missing_ambiguous_and_targetless_annotations_fail_closed(self) -> None:
        _, request, _ = _sources(requirement_text="Height and Height")

        with self.assertRaises(CandidateRetrievalError) as context:
            build_retrieval_role_evidence(request, (("TARGET", "Width"),))
        self.assertEqual(context.exception.code, "ROLE_EVIDENCE_SPAN_NOT_FOUND")

        with self.assertRaises(CandidateRetrievalError) as context:
            build_retrieval_role_evidence(request, (("TARGET", "Height"),))
        self.assertEqual(context.exception.code, "ROLE_EVIDENCE_SPAN_AMBIGUOUS")

        with self.assertRaises(CandidateRetrievalError) as context:
            build_retrieval_role_evidence(request, (("SCOPE", "Height and"),))
        self.assertEqual(context.exception.code, "ROLE_EVIDENCE_TARGET_MISSING")

    def test_role_evidence_is_source_bound_deterministic_and_private_in_aggregate(self) -> None:
        tree, request, confirmation = _sources(
            requirement_text="复用“Height”属性。",
            subject=None,
            assumptions=(),
        )
        evidence = build_retrieval_role_evidence(
            request,
            (("TARGET", "Height"),),
        )
        first = build_role_candidate_set(evidence, request, confirmation, tree)
        second = build_role_candidate_set(
            evidence,
            request,
            confirmation,
            replace(tree, nodes=tuple(reversed(tree.nodes))),
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        encoded = repr(first.aggregate_report())
        self.assertNotIn("Height", encoded)
        self.assertNotIn("node-008", encoded)
        self.assertNotIn(evidence.evidence_hash, encoded)

        _, other_request, other_confirmation = _sources(
            requirement_text="复用“Width”属性。",
            subject=None,
            assumptions=(),
        )
        with self.assertRaises(CandidateRetrievalError) as context:
            build_role_candidate_set(
                evidence,
                other_request,
                other_confirmation,
                tree,
            )
        self.assertEqual(context.exception.code, "ROLE_EVIDENCE_SOURCE_MISMATCH")

        with self.assertRaises(ValueError):
            replace(evidence, evidence_hash="0" * 64)
        with self.assertRaises(ValueError):
            replace(first, candidate_set_hash="0" * 64)


if __name__ == "__main__":
    unittest.main()
