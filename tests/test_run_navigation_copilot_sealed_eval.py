from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import httpx

from scripts.run_navigation_copilot_sealed_eval import (
    FrozenTreeRepository,
    _preflight_output_paths,
    _read_private_raw_json,
    _read_public_json,
    build_r0_candidate_node_ids,
    execute_case_via_workbench_api,
)
from treeguard import load_tree_export
from treeguard.ai_review import BailianProviderError
from treeguard.change_understanding_v2 import ChangeUnderstandingV2
from treeguard.navigation_copilot import NavigationSemanticDraft
from treeguard.navigation_copilot_sealed_validation import (
    SealedCaseOracle,
    SealedScenario,
    StructuralProfile,
    TerminalExpectation,
    score_sealed_case,
)
from treeguard.web import create_app
from treeguard.workbench import WorkbenchService
from treeguard.workbench_navigation_copilot import WorkbenchNavigationCopilotService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


class InlineExecutor:
    def submit(self, function):
        function()
        return None


class UnderstandingProvider:
    def __init__(self, *, clarify=False, fail=False):
        self.clarify = clarify
        self.fail = fail
        self.calls = 0

    def understand(
        self,
        request,
        tree,
        *,
        clarification_question=None,
        clarification_answer=None,
    ):
        self.calls += 1
        if self.fail:
            raise BailianProviderError("BAILIAN_TIMEOUT", "fictional timeout")
        question = (
            "是定位标签字段吗？"
            if self.clarify and clarification_question is None
            else None
        )
        return ChangeUnderstandingV2.from_model_dict(
            {
                "schema_version": "change-understanding-model-output.v2",
                "node_kind": "PROPERTY",
                "value_type": "string",
                "cardinality": "MULTIPLE",
                "clarification_question": question,
                "spans": [{"role": "TARGET", "text": "Tags"}],
            },
            request,
            tree,
            model_provider="MOCK",
            model_capability="JSON_OBJECT",
            model_name="sealed-fixture",
            prompt_version="sealed-fixture.v1",
        )


class SemanticProvider:
    def __init__(self, *, fail_hard=False, no_equivalent=False):
        self.fail_hard = fail_hard
        self.no_equivalent = no_equivalent
        self.calls = 0

    def compare(self, projection, tree):
        self.calls += 1
        if self.fail_hard:
            raise RuntimeError("fictional contract failure")
        return NavigationSemanticDraft.from_model_dict(
            {
                "schema_version": "navigation-copilot-semantic-output.v1",
                "candidate_assessments": [
                    {
                        "candidate_ref": item.candidate_ref,
                        "relation": (
                            "SEMANTICALLY_EQUIVALENT"
                            if item.label == "TAGS" and not self.no_equivalent
                            else "NOT_EQUIVALENT"
                        ),
                        "reason": "Fictional sealed runner test.",
                    }
                    for item in projection.candidates
                ],
            },
            projection,
            tree,
            model_provider="MOCK",
            model_name="sealed-fixture",
            prompt_version="sealed-fixture.v1",
        )


class ProviderFactory:
    def __init__(
        self,
        *,
        clarify=False,
        fail=False,
        semantic_fail_hard=False,
        no_equivalent=False,
    ):
        self.understanding = UnderstandingProvider(clarify=clarify, fail=fail)
        self.semantic = SemanticProvider(
            fail_hard=semantic_fail_hard,
            no_equivalent=no_equivalent,
        )

    def understanding_provider(self, mode, trace_sink=None):
        return self.understanding

    def semantic_provider(self, mode, trace_sink=None):
        return self.semantic


def _scenario(tree, *, clarify=False, category=None, parent_ref="N000002"):
    resolved_category = category or ("CLARIFICATION" if clarify else "LITERAL_UNIQUE")
    return SealedScenario.create(
        scenario_ref="SEALED001",
        tree_digest=tree.snapshot_hash,
        category=resolved_category,
        requirement_text="Find Tags under Catalog.",
        proposed_parent_ref=parent_ref,
        node_kind_hint="PROPERTY",
        value_type_hint="string",
        cardinality_hint="MULTIPLE",
        frozen_clarification_answer="是，定位标签字段。" if clarify else None,
        wrong_context_challenge=False,
        repeat_challenge=clarify,
    )


def _oracle(tree, scenario, *, clarify=False, targets=("node-004",)):
    absent = not targets
    terminals = (
        (TerminalExpectation("REJECT_ALL", None, "ABSENT"),)
        if absent
        else tuple(
            terminal
            for target in targets
            for terminal in (
                TerminalExpectation("SELECT_CANDIDATE", target, "FOUND_TOP8"),
                TerminalExpectation("SELECT_OUTSIDE_CANDIDATE", target, "FOUND_OUTSIDE"),
            )
        )
    )
    return SealedCaseOracle.create(
        scenario_ref=scenario.scenario_ref,
        tree_digest=tree.snapshot_hash,
        request_digest=scenario.request_digest,
        category=scenario.category,
        expected_route=(
            "CLARIFY"
            if clarify
            else ("LIMIT" if scenario.category == "WEAK_EVIDENCE" else "PROCEED")
        ),
        acceptable_profiles=(StructuralProfile("PROPERTY", "string", "MULTIPLE"),),
        target_status="TARGET_ABSENT" if absent else "TARGET_PRESENT",
        acceptable_node_ids=targets,
        forbidden_node_ids=() if absent else ("node-007",),
        clarification_policy=(
            "CLARIFICATION_REQUIRED" if clarify else "NOT_APPLICABLE"
        ),
        frozen_clarification_answer=scenario.frozen_clarification_answer,
        acceptable_policy_statuses=(
            ("NONE", "NEED_EVIDENCE", "CANDIDATES_AVAILABLE")
            if absent
            else (
                ("NEED_EVIDENCE",)
                if clarify or scenario.category == "WEAK_EVIDENCE"
                else ("CANDIDATES_AVAILABLE",)
            )
        ),
        acceptable_terminals=terminals,
        wrong_context_challenge=False,
        review_status="CODEX_SILVER_REVIEWED",
        reviewed_bytes_digest="7" * 64,
        execution_eligible=True,
    )


class SealedRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def _run(
        self,
        *,
        clarify=False,
        category=None,
        parent_ref="N000002",
        targets=("node-004",),
        fail=False,
        semantic_fail_hard=False,
        no_equivalent=False,
    ):
        result = load_tree_export(FIXTURE)
        self.assertTrue(result.is_valid)
        tree = result.tree
        assert tree is not None
        scenario = _scenario(
            tree,
            clarify=clarify,
            category=category,
            parent_ref=parent_ref,
        )
        oracle = _oracle(tree, scenario, clarify=clarify, targets=targets)
        factory = ProviderFactory(
            clarify=clarify,
            fail=fail,
            semantic_fail_hard=semantic_fail_hard,
            no_equivalent=no_equivalent,
        )
        with tempfile.TemporaryDirectory() as temporary:
            sidecars = Path(temporary) / "sidecars"
            repository = FrozenTreeRepository(result)
            identifiers = iter(("001", "002", "003", "004"))
            service = WorkbenchNavigationCopilotService(
                repository=repository,
                sidecar_root=sidecars,
                provider_factory=factory,
                diagnostics_enabled=True,
                executor=InlineExecutor(),
                id_factory=lambda: next(identifiers),
            )
            app = create_app(
                WorkbenchService(repository),
                navigation_copilot_service=service,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://sealed-test.invalid",
            ) as client:
                trace = await execute_case_via_workbench_api(
                    client,
                    scenario=scenario,
                    oracle=oracle,
                    tree=tree,
                    sidecar_root=sidecars,
                    round_index=1,
                )
        return tree, scenario, oracle, factory, trace

    async def test_clear_case_uses_real_http_api_and_keeps_r0_model_free(self):
        tree, scenario, oracle, factory, trace = await self._run()
        self.assertEqual(factory.understanding.calls, 1)
        self.assertEqual(factory.semantic.calls, 1)
        self.assertIn("node-004", build_r0_candidate_node_ids(scenario, tree))
        self.assertIn("node-004", trace.c1_candidate_node_ids[:8])
        self.assertEqual(trace.observed_route, "PROCEED")
        self.assertEqual(trace.outcome.target_node_id, "node-004")
        self.assertTrue(trace.sidecar_complete)
        self.assertTrue(score_sealed_case(oracle, trace).joint_match)

    async def test_clarification_uses_second_understanding_and_skips_semantic(self):
        _, _, oracle, factory, trace = await self._run(clarify=True)
        self.assertEqual(factory.understanding.calls, 2)
        self.assertEqual(factory.semantic.calls, 0)
        self.assertEqual(trace.logical_model_stage_count, 2)
        self.assertEqual(trace.observed_route, "CLARIFY")
        self.assertEqual(trace.policy_status, "NEED_EVIDENCE")
        self.assertTrue(trace.sidecar_complete)
        self.assertTrue(score_sealed_case(oracle, trace).joint_match)

    async def test_candidate_outside_correction_uses_oracle_only_after_candidates(self):
        _, _, _, _, trace = await self._run(
            category="STRUCTURAL_INTERFERENCE",
            targets=("node-001",),
        )
        self.assertNotIn("node-001", trace.c1_candidate_node_ids[:8])
        self.assertEqual(trace.outcome.action, "SELECT_OUTSIDE_CANDIDATE")
        self.assertEqual(trace.outcome.target_node_id, "node-001")

    async def test_absent_target_rejects_even_when_semantic_highlights_a_candidate(self):
        _, _, oracle, _, trace = await self._run(
            category="TARGET_ABSENT",
            targets=(),
        )
        self.assertEqual(trace.outcome.action, "REJECT_ALL")
        observation = score_sealed_case(oracle, trace)
        self.assertTrue(observation.absent_confident_error)
        self.assertEqual(observation.first_failure_stage, "SEMANTIC")

    async def test_wrong_context_remains_soft_and_does_not_break_api_contract(self):
        _, _, _, _, trace = await self._run(parent_ref="N000005")
        self.assertEqual(trace.run_status, "COMPLETE")
        self.assertLessEqual(trace.logical_model_stage_count, 2)

    async def test_multiple_acceptable_targets_choose_the_highest_visible_target(self):
        _, _, oracle, _, trace = await self._run(
            category="MULTI_ACCEPTABLE",
            targets=("node-003", "node-004"),
        )
        self.assertEqual(trace.outcome.action, "SELECT_CANDIDATE")
        self.assertEqual(trace.outcome.target_node_id, "node-004")
        self.assertTrue(score_sealed_case(oracle, trace).joint_match)

    async def test_weak_evidence_keeps_target_visible_but_policy_bounded(self):
        _, _, oracle, _, trace = await self._run(
            category="WEAK_EVIDENCE",
            no_equivalent=True,
        )
        self.assertIn("node-004", trace.c1_candidate_node_ids[:8])
        self.assertEqual(trace.policy_status, "NEED_EVIDENCE")
        self.assertTrue(score_sealed_case(oracle, trace).joint_match)

    async def test_model_failure_is_product_degradation_not_runner_fallback(self):
        _, _, _, factory, trace = await self._run(fail=True)
        self.assertEqual(factory.understanding.calls, 1)
        self.assertEqual(trace.provider_mode, "BAILIAN_LIVE")
        self.assertEqual(trace.interpretation_status, "MODEL_DEGRADED")
        self.assertEqual(trace.run_status, "COMPLETE")

    async def test_unhandled_product_contract_failure_remains_a_scored_case(self):
        _, _, oracle, _, trace = await self._run(semantic_fail_hard=True)
        self.assertEqual(trace.run_status, "CONTRACT_FAILED")
        self.assertEqual(trace.failure_code, "COPILOT_OPERATION_FAILED")
        observation = score_sealed_case(oracle, trace)
        self.assertEqual(observation.first_failure_stage, "SEMANTIC")
        self.assertFalse(observation.joint_match)


class SealedRunnerIOTests(unittest.TestCase):
    def test_private_input_rejects_public_permissions_symlink_and_fifo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text('{"safe":true}\n', encoding="utf-8")
            source.chmod(0o600)
            raw, payload = _read_private_raw_json(source, max_bytes=1_000)
            self.assertEqual(payload, {"safe": True})
            self.assertEqual(json.loads(raw), payload)

            source.chmod(0o644)
            with self.assertRaises(OSError):
                _read_private_raw_json(source, max_bytes=1_000)
            source.chmod(0o600)

            link = root / "link.json"
            link.symlink_to(source)
            with self.assertRaises(OSError):
                _read_private_raw_json(link, max_bytes=1_000)

            fifo = root / "input.fifo"
            os.mkfifo(fifo, 0o600)
            with self.assertRaises(OSError):
                _read_private_raw_json(fifo, max_bytes=1_000)

    def test_public_input_rejects_final_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text("[]\n", encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(source)
            with self.assertRaises(OSError):
                _read_public_json(link, max_bytes=1_000)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"item":1,"item":2}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                _read_public_json(duplicate, max_bytes=1_000)

    def test_output_preflight_is_private_distinct_and_non_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            sidecars = root / "sidecars"
            output = root / "results"
            _preflight_output_paths(sidecars, output)
            self.assertEqual(sidecars.stat().st_mode & 0o777, 0o700)
            output.mkdir(mode=0o700)
            with self.assertRaises(OSError):
                _preflight_output_paths(sidecars, output)
            with self.assertRaises(ValueError):
                _preflight_output_paths(sidecars, sidecars)


if __name__ == "__main__":
    unittest.main()
