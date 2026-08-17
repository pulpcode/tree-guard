from __future__ import annotations

import unittest
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from treeguard import load_tree_export
from treeguard.ai_review import (
    BailianConfig,
    BailianNavigationSemanticProvider,
    BailianNavigationSemanticProviderV2,
    BailianNavigationUnderstandingProvider,
    BailianProviderError,
)
from treeguard.change_intent import IntentRequest
from treeguard.change_understanding_v2 import ChangeUnderstandingV2
from treeguard.hashing import canonical_digest
from treeguard.navigation_copilot import (
    NavigationClarificationAnswer,
    NavigationClarificationRound,
    NavigationCopilotError,
    NavigationInterpretation,
    NavigationPolicyDecisionV2,
    NavigationSemanticDraft,
    NavigationSemanticDraftV2,
    NavigationShadowObservation,
    apply_navigation_policy,
    apply_navigation_policy_v2,
    build_navigation_candidate_set,
    build_navigation_outcome,
    build_navigation_semantic_projection,
    build_navigation_semantic_projection_v2,
    navigation_shadow_aggregate,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


def _assert_contract_fields(testcase, name, payload):
    schema = json.loads(
        (ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    testcase.assertEqual(set(schema["required"]), set(payload))


def _sources(
    *,
    clarification_question=None,
    spans=None,
    node_kind="PROPERTY",
    value_type="string",
    cardinality="MULTIPLE",
    requirement="Find Tags under Catalog, not Profile.",
):
    loaded = load_tree_export(FIXTURE)
    assert loaded.tree is not None
    tree = loaded.tree
    request = IntentRequest.from_dict(
        {
            "schema_version": "intent-request.v1",
            "requirement_text": requirement,
            "proposed_parent_node_id": "node-002",
            "node_kind_hint": node_kind,
            "value_type_hint": value_type,
            "cardinality_hint": cardinality,
        },
        tree,
    )
    understanding = ChangeUnderstandingV2.from_model_dict(
        {
            "schema_version": "change-understanding-model-output.v2",
            "node_kind": node_kind,
            "value_type": value_type,
            "cardinality": cardinality,
            "clarification_question": clarification_question,
            "spans": spans or [{"role": "TARGET", "text": "Tags"}],
        },
        request,
        tree,
        model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
        model_capability="JSON_OBJECT",
        model_name="fixture-model",
        prompt_version="treeguard.change-understanding.zh.v2",
    )
    return tree, request, understanding


def _semantic_payload(projection, *, equivalents=("C001",)):
    return {
        "schema_version": "navigation-copilot-semantic-output.v1",
        "candidate_assessments": [
            {
                "candidate_ref": item.candidate_ref,
                "relation": (
                    "SEMANTICALLY_EQUIVALENT"
                    if item.candidate_ref in equivalents
                    else "NOT_EQUIVALENT"
                ),
                "reason": "Compared only within the fictional projection.",
            }
            for item in projection.candidates
        ],
    }


def _semantic_payload_v2(projection, *, equivalents=("C001",)):
    return {
        **_semantic_payload(projection, equivalents=equivalents),
        "schema_version": "navigation-copilot-semantic-output.v2",
    }


class NavigationCopilotCoreTests(unittest.TestCase):
    def test_semantic_v2_policy_keeps_unique_equivalent_rule_and_all_relations_safe(self):
        tree, request, understanding = _sources(
            node_kind="UNKNOWN",
            value_type=None,
            cardinality="UNKNOWN",
        )
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        projection = build_navigation_semantic_projection_v2(
            request, interpretation, candidates, tree
        )

        unique_draft = NavigationSemanticDraftV2.from_model_dict(
            _semantic_payload_v2(projection),
            projection,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_name="fixture-model",
            prompt_version="fixture-semantic.v2",
        )
        unique = apply_navigation_policy_v2(
            interpretation,
            candidates,
            projection,
            unique_draft,
            semantic_status="SUCCEEDED",
        )
        self.assertEqual(unique.status, "CANDIDATES_AVAILABLE")
        self.assertEqual(unique.highlighted_candidate_ref, "C001")
        _assert_contract_fields(
            self, "navigation-copilot-policy-decision.v2", unique.to_dict()
        )
        self.assertEqual(
            NavigationPolicyDecisionV2.from_dict(
                unique.to_dict(),
                interpretation,
                candidates,
                projection,
                unique_draft,
            ),
            unique,
        )

        multiple_draft = NavigationSemanticDraftV2.from_model_dict(
            _semantic_payload_v2(projection, equivalents=("C001", "C002")),
            projection,
            tree,
            model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
            model_name="fixture-model",
            prompt_version="fixture-semantic.v2",
        )
        multiple = apply_navigation_policy_v2(
            interpretation,
            candidates,
            projection,
            multiple_draft,
            semantic_status="SUCCEEDED",
        )
        self.assertEqual(multiple.status, "AMBIGUOUS")
        self.assertIsNone(multiple.highlighted_candidate_ref)

        for relation in (
            "REUSES_CONTRACT",
            "CONTEXTUALLY_RELATED",
            "NOT_EQUIVALENT",
            "NEED_EVIDENCE",
        ):
            payload = {
                "schema_version": "navigation-copilot-semantic-output.v2",
                "candidate_assessments": [
                    {
                        "candidate_ref": item.candidate_ref,
                        "relation": relation,
                        "reason": "Fictional relation-only policy fixture.",
                    }
                    for item in projection.candidates
                ],
            }
            draft = NavigationSemanticDraftV2.from_model_dict(
                payload,
                projection,
                tree,
                model_provider="UNVERIFIED_MODEL_OUTPUT_FILE",
                model_name="fixture-model",
                prompt_version="fixture-semantic.v2",
            )
            decision = apply_navigation_policy_v2(
                interpretation,
                candidates,
                projection,
                draft,
                semantic_status="SUCCEEDED",
            )
            self.assertEqual(decision.status, "NEED_EVIDENCE")
            self.assertIsNone(decision.highlighted_candidate_ref)

    def test_semantic_v2_restores_authoritative_requirement_without_changing_v1(self):
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        legacy = build_navigation_semantic_projection(
            request, interpretation, candidates, tree
        )
        projection = build_navigation_semantic_projection_v2(
            request, interpretation, candidates, tree
        )

        self.assertNotIn("requirement_text", legacy.to_model_dict())
        self.assertEqual(
            projection.to_model_dict()["requirement_text"],
            request.requirement_text,
        )
        self.assertEqual(projection.candidates, legacy.candidates)
        self.assertNotIn("source_request_hash", projection.to_model_dict())
        self.assertNotIn("node-", json.dumps(projection.to_model_dict()))
        for contract, artifact in (
            ("navigation-copilot-semantic-input.v2", projection.to_model_dict()),
            ("navigation-copilot-semantic-projection.v2", projection.to_dict()),
        ):
            _assert_contract_fields(self, contract, artifact)
        replayed = type(projection).from_dict(
            projection.to_dict(), request, interpretation, candidates, tree
        )
        self.assertEqual(replayed, projection)

        different_tree, different_request, different_understanding = _sources(
            requirement="Find Description under Catalog, not Profile.",
            spans=[{"role": "TARGET", "text": "Description"}],
        )
        different_interpretation = NavigationInterpretation.valid(
            different_understanding, different_request, different_tree
        )
        different_candidates = build_navigation_candidate_set(
            different_request, different_interpretation, different_tree
        )
        with self.assertRaisesRegex(ValueError, "does not replay"):
            type(projection).from_dict(
                projection.to_dict(),
                different_request,
                different_interpretation,
                different_candidates,
                different_tree,
            )

    def test_semantic_v2_rejects_internal_identifier_in_authoritative_requirement(self):
        tree, request, understanding = _sources(
            requirement="Find Catalog at node-004.",
            spans=[{"role": "TARGET", "text": "Catalog"}],
        )
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)

        with self.assertRaises(NavigationCopilotError) as error:
            build_navigation_semantic_projection_v2(
                request, interpretation, candidates, tree
            )
        self.assertEqual(
            error.exception.code,
            "COPILOT_SEMANTIC_V2_INTERNAL_ID_FORBIDDEN",
        )

        safe_tree, safe_request, safe_understanding = _sources()
        safe_interpretation = NavigationInterpretation.valid(
            safe_understanding, safe_request, safe_tree
        )
        safe_candidates = build_navigation_candidate_set(
            safe_request, safe_interpretation, safe_tree
        )
        legacy = build_navigation_semantic_projection(
            safe_request, safe_interpretation, safe_candidates, safe_tree
        )
        leaked_id = safe_tree.nodes[0].node_id
        bad_views = (
            replace(legacy.candidates[0], label=leaked_id),
            *legacy.candidates[1:],
        )
        bad_model_input = legacy.to_model_dict()
        bad_model_input["candidates"][0]["label"] = leaked_id
        bad_legacy = replace(
            legacy,
            candidates=bad_views,
            projection_hash=canonical_digest(bad_model_input),
        )
        with (
            patch(
                "treeguard.navigation_copilot.build_navigation_semantic_projection",
                return_value=bad_legacy,
            ),
            self.assertRaises(NavigationCopilotError) as candidate_error,
        ):
            build_navigation_semantic_projection_v2(
                safe_request,
                safe_interpretation,
                safe_candidates,
                safe_tree,
            )
        self.assertEqual(
            candidate_error.exception.code,
            "COPILOT_SEMANTIC_V2_INTERNAL_ID_FORBIDDEN",
        )

    def test_semantic_v2_rejects_projection_over_context_budget(self):
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        legacy = build_navigation_semantic_projection(
            request, interpretation, candidates, tree
        )

        with (
            patch(
                "treeguard.navigation_copilot.build_navigation_semantic_projection",
                return_value=legacy,
            ),
            patch("treeguard.navigation_copilot.MAX_MODEL_INPUT_CHARS", 1),
            self.assertRaises(NavigationCopilotError) as error,
        ):
            build_navigation_semantic_projection_v2(
                request, interpretation, candidates, tree
            )

        self.assertEqual(
            error.exception.code,
            "COPILOT_SEMANTIC_V2_PROJECTION_TOO_LARGE",
        )

    def test_no_lexical_candidate_is_none_without_addition_permission(self):
        tree, request, understanding = _sources(
            requirement="UnfindableZebraToken",
            spans=[{"role": "TARGET", "text": "UnfindableZebraToken"}],
            node_kind="UNKNOWN",
            value_type=None,
            cardinality="UNKNOWN",
        )
        interpretation = NavigationInterpretation.valid(
            understanding, request, tree
        )
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        decision = apply_navigation_policy(
            interpretation,
            candidates,
            None,
            None,
            semantic_status="NOT_APPLICABLE",
        )

        self.assertEqual(candidates.status, "NO_CANDIDATES")
        self.assertEqual(candidates.candidates, ())
        self.assertFalse(candidates.to_dict()["allows_addition"])
        self.assertEqual(decision.status, "NONE")
        self.assertIsNone(decision.highlighted_candidate_ref)

    def test_raw_request_floor_survives_wrong_role_and_exclusion(self) -> None:
        tree, request, understanding = _sources(
            spans=[
                {"role": "TARGET", "text": "Catalog"},
                {"role": "EXCLUSION", "text": "Tags"},
            ]
        )
        interpretation = NavigationInterpretation.valid(
            understanding, request, tree
        )

        candidates = build_navigation_candidate_set(
            request, interpretation, tree
        )

        self.assertEqual(candidates.status, "CANDIDATES_READY")
        self.assertIn("node-004", {item.node_id for item in candidates.candidates})
        tags = next(
            item for item in candidates.candidates if item.node_id == "node-004"
        )
        self.assertGreater(tags.score.base_total, 0)
        self.assertGreater(tags.score.exclusion_penalty, 0)
        self.assertFalse(candidates.to_dict()["embedding_used"])
        self.assertFalse(candidates.to_dict()["allows_addition"])

    def test_unique_multiple_and_degraded_semantic_states_are_local(self) -> None:
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(
            understanding, request, tree
        )
        candidates = build_navigation_candidate_set(
            request, interpretation, tree
        )
        projection = build_navigation_semantic_projection(
            request, interpretation, candidates, tree
        )
        unique = NavigationSemanticDraft.from_model_dict(
            _semantic_payload(projection),
            projection,
            tree,
            model_provider="fixture",
            model_name="fixture-model",
            prompt_version="treeguard.navigation-copilot.semantic.zh.v1",
        )

        decision = apply_navigation_policy(
            interpretation,
            candidates,
            projection,
            unique,
            semantic_status="SUCCEEDED",
        )
        self.assertEqual(decision.status, "CANDIDATES_AVAILABLE")
        self.assertEqual(decision.highlighted_candidate_ref, "C001")
        self.assertFalse(decision.to_dict()["semantic_approval"])

        ambiguous_tree, ambiguous_request, ambiguous_understanding = _sources(
            node_kind="UNKNOWN",
            value_type=None,
            cardinality="UNKNOWN",
        )
        ambiguous_interpretation = NavigationInterpretation.valid(
            ambiguous_understanding,
            ambiguous_request,
            ambiguous_tree,
        )
        ambiguous_candidates = build_navigation_candidate_set(
            ambiguous_request,
            ambiguous_interpretation,
            ambiguous_tree,
        )
        ambiguous_projection = build_navigation_semantic_projection(
            ambiguous_request,
            ambiguous_interpretation,
            ambiguous_candidates,
            ambiguous_tree,
        )
        multiple_refs = tuple(
            item.candidate_ref for item in ambiguous_projection.candidates[:2]
        )
        multiple = NavigationSemanticDraft.from_model_dict(
            _semantic_payload(ambiguous_projection, equivalents=multiple_refs),
            ambiguous_projection,
            ambiguous_tree,
            model_provider="fixture",
            model_name="fixture-model",
            prompt_version="treeguard.navigation-copilot.semantic.zh.v1",
        )
        ambiguous = apply_navigation_policy(
            ambiguous_interpretation,
            ambiguous_candidates,
            ambiguous_projection,
            multiple,
            semantic_status="SUCCEEDED",
        )
        self.assertEqual(ambiguous.status, "AMBIGUOUS")
        self.assertIsNone(ambiguous.highlighted_candidate_ref)

        degraded = apply_navigation_policy(
            interpretation,
            candidates,
            projection,
            None,
            semantic_status="DEGRADED",
        )
        self.assertEqual(degraded.status, "NEED_EVIDENCE")
        self.assertIsNone(degraded.highlighted_candidate_ref)

    def test_single_clarification_round_binds_answer_and_skips_semantic(self) -> None:
        tree, request, initial_understanding = _sources(
            clarification_question="Should Tags be single or multiple?"
        )
        initial = NavigationInterpretation.valid(
            initial_understanding, request, tree
        )
        answer = NavigationClarificationAnswer.create(
            initial,
            answer_text="Multiple values.",
            recorded_at="2030-01-02T03:04:05Z",
        )
        _, _, revised_understanding = _sources()
        revised = NavigationInterpretation.valid(
            revised_understanding, request, tree
        )
        round_artifact = NavigationClarificationRound.create(
            initial, answer, revised
        )
        candidates = build_navigation_candidate_set(request, revised, tree)
        decision = apply_navigation_policy(
            revised,
            candidates,
            None,
            None,
            semantic_status="SKIPPED_CLARIFICATION_PATH",
        )

        self.assertEqual(
            round_artifact.source_answer_hash,
            answer.answer_hash,
        )
        self.assertEqual(decision.status, "NEED_EVIDENCE")
        self.assertEqual(
            decision.semantic_status,
            "SKIPPED_CLARIFICATION_PATH",
        )
        self.assertEqual(
            NavigationClarificationAnswer.from_dict(answer.to_dict(), initial),
            answer,
        )
        self.assertEqual(
            NavigationClarificationRound.from_dict(
                round_artifact.to_dict(), initial, answer, request, tree
            ),
            round_artifact,
        )
        _assert_contract_fields(
            self,
            "navigation-copilot-clarification-answer.v1",
            answer.to_dict(),
        )
        _assert_contract_fields(
            self,
            "navigation-copilot-clarification-round.v1",
            round_artifact.to_dict(),
        )

    def test_outcomes_distinguish_direct_hit_and_outside_correction(self) -> None:
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(
            understanding, request, tree
        )
        candidates = build_navigation_candidate_set(
            request, interpretation, tree
        )
        projection = build_navigation_semantic_projection(
            request, interpretation, candidates, tree
        )
        semantic = NavigationSemanticDraft.from_model_dict(
            _semantic_payload(projection),
            projection,
            tree,
            model_provider="fixture",
            model_name="fixture-model",
            prompt_version="treeguard.navigation-copilot.semantic.zh.v1",
        )
        decision = apply_navigation_policy(
            interpretation,
            candidates,
            projection,
            semantic,
            semantic_status="SUCCEEDED",
        )
        direct_node = candidates.candidates[0].node_id
        direct = build_navigation_outcome(
            decision,
            candidates,
            tree,
            action="SELECT_CANDIDATE",
            selected_candidate_ref="C001",
            selected_node_id=direct_node,
            duration_ms=1_000,
        )
        candidate_nodes = {item.node_id for item in candidates.candidates[:8]}
        outside_node = next(
            node.node_id for node in tree.nodes if node.node_id not in candidate_nodes
        )
        corrected = build_navigation_outcome(
            decision,
            candidates,
            tree,
            action="SELECT_OUTSIDE_CANDIDATE",
            selected_candidate_ref=None,
            selected_node_id=outside_node,
            duration_ms=2_000,
        )
        aggregate = navigation_shadow_aggregate(
            (
                NavigationShadowObservation(decision, direct, False, False),
                NavigationShadowObservation(decision, corrected, True, True),
            )
        )

        self.assertFalse(direct.candidate_miss)
        self.assertTrue(corrected.candidate_miss)
        self.assertTrue(corrected.user_corrected)
        self.assertEqual(aggregate["completed_navigation_count"], 2)
        self.assertEqual(aggregate["top8_direct_selection_count"], 1)
        self.assertEqual(aggregate["candidate_correction_count"], 1)
        self.assertEqual(aggregate["clarification_case_count"], 1)
        self.assertEqual(aggregate["degraded_case_count"], 1)
        self.assertEqual(aggregate["evidence_covered_case_count"], 2)
        self.assertEqual(aggregate["median_completion_ms"], 1_500)
        self.assertFalse(aggregate["gold_eligible"])
        for contract, artifact in (
            ("navigation-copilot-interpretation.v1", interpretation.to_dict()),
            ("navigation-copilot-candidate-set.v1", candidates.to_dict()),
            ("navigation-copilot-semantic-input.v1", projection.to_model_dict()),
            ("navigation-copilot-semantic-projection.v1", projection.to_dict()),
            ("navigation-copilot-semantic-draft.v1", semantic.to_dict()),
            ("navigation-copilot-policy-decision.v1", decision.to_dict()),
            ("navigation-copilot-outcome.v1", direct.to_dict()),
            ("navigation-copilot-shadow-aggregate.v1", aggregate),
        ):
            _assert_contract_fields(self, contract, artifact)
        replayed_interpretation = NavigationInterpretation.from_dict(
            interpretation.to_dict(), request, tree
        )
        replayed_candidates = type(candidates).from_dict(
            candidates.to_dict(), request, replayed_interpretation, tree
        )
        replayed_projection = type(projection).from_dict(
            projection.to_dict(),
            request,
            replayed_interpretation,
            replayed_candidates,
            tree,
        )
        replayed_semantic = NavigationSemanticDraft.from_dict(
            semantic.to_dict(), replayed_projection, tree
        )
        replayed_decision = type(decision).from_dict(
            decision.to_dict(),
            replayed_interpretation,
            replayed_candidates,
            replayed_projection,
            replayed_semantic,
        )
        self.assertEqual(
            type(direct).from_dict(
                direct.to_dict(), replayed_decision, replayed_candidates, tree
            ),
            direct,
        )
        tampered = direct.to_dict()
        tampered["candidate_miss"] = True
        with self.assertRaisesRegex(ValueError, "does not replay"):
            type(direct).from_dict(
                tampered, replayed_decision, replayed_candidates, tree
            )


class _RecordingUnderstandingProvider(BailianNavigationUnderstandingProvider):
    def __init__(self, responses):
        super().__init__(BailianConfig(api_key="fictional-key"))
        self.responses = iter(responses)
        self.bodies = []

    def _post_json(self, body):
        self.bodies.append(body)
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(next(self.responses))}}]}


class _RecordingSemanticProvider(BailianNavigationSemanticProvider):
    def __init__(self, responses):
        super().__init__(BailianConfig(api_key="fictional-key"))
        self.responses = iter(responses)
        self.bodies = []

    def _post_json(self, body):
        self.bodies.append(body)
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(next(self.responses))}}]}


class _RecordingSemanticProviderV2(BailianNavigationSemanticProviderV2):
    def __init__(self, responses):
        super().__init__(BailianConfig(api_key="fictional-key"))
        self.responses = iter(responses)
        self.bodies = []

    def _post_json(self, body):
        self.bodies.append(body)
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(next(self.responses))}}]}


class NavigationCopilotProviderTests(unittest.TestCase):
    def test_semantic_v2_provider_rejects_stale_projection_before_transport(self):
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        projection = build_navigation_semantic_projection_v2(
            request, interpretation, candidates, tree
        )
        stale = replace(projection, source_snapshot_hash="f" * 64)
        provider = _RecordingSemanticProviderV2(
            (_semantic_payload_v2(projection),)
        )

        with self.assertRaises(NavigationCopilotError) as error:
            provider.compare(stale, tree)

        self.assertEqual(
            error.exception.code,
            "COPILOT_SEMANTIC_V2_SOURCE_MISMATCH",
        )
        self.assertEqual(provider.bodies, [])

    def test_semantic_v2_provider_sends_requirement_and_explicit_relation_rubric(self):
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        projection = build_navigation_semantic_projection_v2(
            request, interpretation, candidates, tree
        )
        valid = _semantic_payload_v2(projection)
        provider = _RecordingSemanticProviderV2((valid,))

        draft = provider.compare(projection, tree)

        self.assertIsInstance(draft, NavigationSemanticDraftV2)
        _assert_contract_fields(
            self, "navigation-copilot-semantic-output.v2", valid
        )
        _assert_contract_fields(
            self, "navigation-copilot-semantic-draft.v2", draft.to_dict()
        )
        user_payload = json.loads(provider.bodies[0]["messages"][1]["content"])
        self.assertEqual(
            user_payload["semantic_input"]["requirement_text"],
            request.requirement_text,
        )
        system_prompt = provider.bodies[0]["messages"][0]["content"]
        for relation in (
            "SEMANTICALLY_EQUIVALENT",
            "REUSES_CONTRACT",
            "CONTEXTUALLY_RELATED",
            "NOT_EQUIVALENT",
            "NEED_EVIDENCE",
        ):
            self.assertIn(relation, system_prompt)
        self.assertEqual(
            NavigationSemanticDraftV2.from_dict(
                draft.to_dict(), projection, tree
            ),
            draft,
        )

    def test_semantic_v2_provider_retries_with_stable_validation_code(self):
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        projection = build_navigation_semantic_projection_v2(
            request, interpretation, candidates, tree
        )
        valid = _semantic_payload_v2(projection)
        invalid = {
            **valid,
            "candidate_assessments": list(reversed(valid["candidate_assessments"])),
        }
        provider = _RecordingSemanticProviderV2((invalid, valid))

        draft = provider.compare(projection, tree)

        self.assertEqual(
            tuple(item.candidate_ref for item in draft.candidate_assessments),
            projection.candidate_refs,
        )
        self.assertEqual(len(provider.bodies), 2)
        retry_payload = json.loads(provider.bodies[1]["messages"][1]["content"])
        self.assertEqual(
            retry_payload["previous_validation_error"],
            "COPILOT_SEMANTIC_CANDIDATE_COVERAGE_INVALID",
        )

        failing_provider = _RecordingSemanticProviderV2((invalid, invalid))
        with self.assertRaises(BailianProviderError) as error:
            failing_provider.compare(projection, tree)
        self.assertEqual(
            error.exception.code,
            "COPILOT_SEMANTIC_CANDIDATE_COVERAGE_INVALID",
        )

    def test_understanding_provider_retries_with_safe_code_and_json_mode(self):
        tree, request, _ = _sources()
        valid = {
            "schema_version": "change-understanding-model-output.v2",
            "node_kind": "PROPERTY",
            "value_type": "string",
            "cardinality": "MULTIPLE",
            "clarification_question": None,
            "spans": [{"role": "TARGET", "text": "Tags"}],
        }
        invalid = {**valid, "spans": []}
        provider = _RecordingUnderstandingProvider((invalid, valid))

        result = provider.understand(request, tree)

        self.assertEqual(result.structural_intent.node_kind, "PROPERTY")
        self.assertEqual(
            result.prompt_version,
            "treeguard.navigation-copilot-understanding.zh.v2",
        )
        self.assertEqual(len(provider.bodies), 2)
        self.assertFalse(provider.bodies[0]["enable_thinking"])
        system_prompt = provider.bodies[0]["messages"][0]["content"]
        self.assertIn("非空的 node_kind_hint", system_prompt)
        self.assertIn("至少两个互斥解释", system_prompt)
        self.assertIn("不得因为候选不确定", system_prompt)
        retry_payload = json.loads(provider.bodies[1]["messages"][1]["content"])
        self.assertEqual(
            retry_payload["previous_validation_error"],
            "UNDERSTANDING_V2_ROLE_MODEL_SPANS_INVALID",
        )
        self.assertNotIn("node-004", provider.bodies[1]["messages"][1]["content"])

    def test_semantic_provider_retries_and_preserves_projection_order(self):
        tree, request, understanding = _sources()
        interpretation = NavigationInterpretation.valid(understanding, request, tree)
        candidates = build_navigation_candidate_set(request, interpretation, tree)
        projection = build_navigation_semantic_projection(request, interpretation, candidates, tree)
        valid = _semantic_payload(projection)
        _assert_contract_fields(
            self, "navigation-copilot-semantic-output.v1", valid
        )
        invalid = {
            "schema_version": "navigation-copilot-semantic-output.v1",
            "candidate_assessments": list(reversed(valid["candidate_assessments"])),
        }
        provider = _RecordingSemanticProvider((invalid, valid))

        draft = provider.compare(projection, tree)

        self.assertEqual(
            tuple(item.candidate_ref for item in draft.candidate_assessments),
            projection.candidate_refs,
        )
        self.assertEqual(len(provider.bodies), 2)
        retry_payload = json.loads(provider.bodies[1]["messages"][1]["content"])
        self.assertEqual(
            retry_payload["previous_validation_error"],
            "COPILOT_SEMANTIC_CANDIDATE_COVERAGE_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
