from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from treeguard.adapter import adapt_tree_document
from treeguard.ai_review import BailianConfig, build_retrieval_role_request_body
from treeguard.change_intent import IntentContent, IntentRequest


REPOSITORY = Path(__file__).resolve().parents[1]


def load_local(name: str, relative: str):
    location = REPOSITORY / relative
    spec = importlib.util.spec_from_file_location(name, location)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_local(
    "fire_r2_sealed_confirmation_runner_test",
    "scripts/run_fire_r2_sealed_confirmation.py",
)
GENERATOR = load_local(
    "fire_r2_sealed_confirmation_generator_runner_test",
    "scripts/generate_fire_r2_sealed_confirmation_cleanroom_2.py",
)


class FireR2SealedConfirmationRunnerTest(unittest.TestCase):
    def _tree(self):
        imported = adapt_tree_document(
            GENERATOR.build_tree(),
            source_hint="fire-r2-sealed-runner-test",
        )
        self.assertIsNotNone(imported.tree)
        self.assertEqual(imported.issues, ())
        return imported.tree

    def _config(self) -> BailianConfig:
        return BailianConfig(
            api_key="test-key",
            model=RUNNER.MODEL_ID,
            max_attempts=2,
            max_transport_retries=0,
        )

    def test_frozen_runner_constants_match_execution_contract(self) -> None:
        self.assertEqual(RUNNER.ROUND_COUNT, 2)
        self.assertEqual(RUNNER.SCENARIO_COUNT, 28)
        self.assertEqual(RUNNER.MAXIMUM_ACTUAL_CALL_COUNT, 112)
        self.assertEqual(
            RUNNER.VIEW_ORDER,
            (
                "V_CANONICAL",
                "V_FREE_TEXT_DROPPED",
                "V_PARENT_ABSENT",
                "V_PARENT_WRONG_BRANCH",
                "V_REQUIREMENT_ONLY",
            ),
        )

    def test_planned_provider_allows_only_frozen_bodies_and_counts_attempts(self) -> None:
        tree = self._tree()
        request = IntentRequest(
            requirement_text="虚构目标字段",
            proposed_parent_node_id=None,
            node_kind_hint="PROPERTY",
            value_type_hint="TEXT",
            cardinality_hint="SINGLE",
        )
        response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "schema_version": "retrieval-role-model-output.v1",
                                "spans": [{"role": "TARGET", "text": "虚构目标字段"}],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        provider = RUNNER.PlannedRoleProvider(
            self._config(),
            RUNNER._request_allowlist(request, RUNNER.MODEL_ID),
            frozenset(node.node_id for node in tree.nodes),
            transport=lambda body: response,
        )
        evidence = provider.extract_roles(request)
        self.assertEqual(evidence.to_model_dict()["spans"][0]["role"], "TARGET")
        self.assertEqual(len(provider.records), 1)

        unplanned = build_retrieval_role_request_body(request, RUNNER.MODEL_ID)
        unplanned["temperature"] = 1
        with self.assertRaisesRegex(RUNNER.SealedRunnerError, "R2_SEALED_UNPLANNED_REQUEST_BODY"):
            provider._post_json(unplanned)

    def test_planned_provider_rejects_stable_identifier_leak(self) -> None:
        request = IntentRequest(
            requirement_text="虚构目标字段",
            proposed_parent_node_id=None,
            node_kind_hint="PROPERTY",
            value_type_hint="TEXT",
            cardinality_hint="SINGLE",
        )
        body = build_retrieval_role_request_body(request, RUNNER.MODEL_ID)
        provider = RUNNER.PlannedRoleProvider(
            self._config(),
            frozenset({RUNNER.hashlib.sha256(RUNNER._wire_bytes(body)).hexdigest()}),
            frozenset({"虚构目标字段"}),
            transport=lambda value: {},
        )
        with self.assertRaisesRegex(RUNNER.SealedRunnerError, "R2_SEALED_MODEL_INPUT_LEAK"):
            provider._post_json(body)

    def test_confirmation_is_bound_to_request_view_and_tree(self) -> None:
        tree = self._tree()
        request = IntentRequest(
            requirement_text="虚构目标字段",
            proposed_parent_node_id=None,
            node_kind_hint="PROPERTY",
            value_type_hint="TEXT",
            cardinality_hint="SINGLE",
        )
        seed = IntentContent(
            subject=None,
            role=None,
            scenario=None,
            lifecycle=None,
            ownership="LONG_LIVED_SUBJECT_PROPERTY",
            node_kind="PROPERTY",
            value_type="TEXT",
            cardinality="SINGLE",
            confirmed_facts=(),
            assumptions=(),
            evidence_gaps=(),
            clarification_question=None,
        )
        first = RUNNER._confirmation(request, seed, tree, "V_REQUIREMENT_ONLY")
        second = RUNNER._confirmation(request, seed, tree, "V_REQUIREMENT_ONLY")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.source_request_hash, request.request_hash)
        self.assertEqual(first.source_snapshot_hash, tree.snapshot_hash)

    def test_aggregate_and_gate_use_fixed_denominators(self) -> None:
        observations = []
        for index in range(24):
            observations.append(
                {
                    "primary_category": "NON_LITERAL" if index < 4 else "LEXICAL_BASELINE",
                    "positive": True,
                    "rank": 1 if index < 22 else 9,
                    "empty_match": False,
                    "hard_negative": index < 4,
                    "hard_negative_safe": index < 4,
                    "replay_match": True,
                    "status": "CANDIDATES_READY",
                }
            )
        observations.extend(
            {
                "primary_category": "EXPLICIT_EMPTY",
                "positive": False,
                "rank": None,
                "empty_match": True,
                "hard_negative": False,
                "hard_negative_safe": False,
                "replay_match": True,
                "status": "NO_CANDIDATES",
            }
            for _ in range(4)
        )
        metric = RUNNER._aggregate(observations)
        self.assertEqual(metric["recall_at_8"], 22)
        self.assertEqual(metric["recall_at_20"], 24)
        self.assertEqual(metric["empty_status_match_count"], 4)
        self.assertEqual(metric["hard_negative_top8_safe_count"], 4)
        self.assertEqual(metric["non_literal_recall_at_20"], 4)
        report = {
            "contract_success_count": 28,
            "transport_failure_count": 0,
            "actual_call_count": 28,
            "views": {"R2": {view: dict(metric) for view in RUNNER.VIEW_ORDER}},
        }
        self.assertEqual(RUNNER._round_failure_codes(report), [])
        report["views"]["R2"]["V_PARENT_WRONG_BRANCH"]["recall_at_20"] = 21
        self.assertIn("R2_SEALED_WRONG_PARENT_BELOW_MINIMUM", RUNNER._round_failure_codes(report))

    def test_empty_partial_round_fails_without_division_error(self) -> None:
        report, private_report = RUNNER.run_round(
            1,
            [],
            self._tree(),
            self._config(),
            transport=lambda body: {},
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["failure_codes"], ["R2_SEALED_ROLE_CONTRACT_FAILURE"])
        self.assertEqual(private_report["units"], [])

    def test_single_synthetic_unit_runs_both_algorithms_across_five_views(self) -> None:
        tree = self._tree()
        nodes = {node.node_id: node for node in tree.nodes}
        root = next(node for node in tree.nodes if node.parent_node_id is None)
        branches = tuple(node for node in tree.nodes if node.parent_node_id == root.node_id)
        target = next(
            node
            for node in tree.nodes
            if node.kind == "PROPERTY"
            and node.parent_node_id is not None
            and node.value_contract is not None
        )
        proposed = nodes[target.parent_node_id]

        def top_branch(node):
            current = node
            while current.parent_node_id != root.node_id:
                current = nodes[current.parent_node_id]
            return current

        proposed_branch = top_branch(proposed)
        wrong = next(branch for branch in branches if branch.node_id != proposed_branch.node_id)
        contract = target.value_contract
        assert contract is not None
        request_text = target.name
        brief = "完全虚构的 runner 聚焦场景"
        unit = {
            "candidate": {
                "candidate_id": "synthetic-unit",
                "request_text": request_text,
                "scenario_brief": brief,
            },
            "oracle": {
                "acceptable_node_ids": [target.node_id],
                "excluded_node_ids": [],
                "primary_category": "LEXICAL_BASELINE",
            },
            "execution": {
                "candidate_id": "synthetic-unit",
                "cardinality_hint": contract.cardinality,
                "node_kind_hint": target.kind,
                "proposed_parent_node_id": proposed.node_id,
                "retrieval_seed": {
                    "assumptions": [],
                    "cardinality": contract.cardinality,
                    "clarification_question": None,
                    "confirmed_facts": [request_text],
                    "evidence_gaps": [],
                    "lifecycle": None,
                    "node_kind": target.kind,
                    "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
                    "role": None,
                    "scenario": None,
                    "subject": proposed.name,
                    "value_type": contract.value_type,
                },
                "value_type_hint": contract.value_type,
                "wrong_branch_parent_node_id": wrong.node_id,
            },
        }

        def extract(provider, request):
            provider.records.append({"request": {}, "response": {}})
            return RUNNER.build_model_retrieval_role_evidence(
                {
                    "schema_version": "retrieval-role-model-output.v1",
                    "spans": [{"role": "TARGET", "text": request.requirement_text}],
                },
                request,
            )

        with mock.patch.object(RUNNER.PlannedRoleProvider, "extract_roles", extract):
            report, private_report = RUNNER.run_round(
                1,
                [unit],
                tree,
                self._config(),
            )
        self.assertEqual(report["contract_success_count"], 1)
        self.assertEqual(report["actual_call_count"], 1)
        self.assertEqual(set(report["views"]), {"R1", "R2"})
        self.assertTrue(
            all(set(report["views"][algorithm]) == set(RUNNER.VIEW_ORDER) for algorithm in RUNNER.ALGORITHMS)
        )
        self.assertEqual(private_report["units"][0]["status"], "COMPLETED")

    def test_runtime_binding_rejects_wrong_runner_head_before_private_read(self) -> None:
        completed = mock.Mock(stdout="f" * 40 + "\n", returncode=0)
        with mock.patch.object(RUNNER, "_git", return_value=completed), mock.patch.object(
            RUNNER.data_preflight,
            "validate_private",
        ) as private_validation:
            with self.assertRaisesRegex(RUNNER.SealedRunnerError, "R2_SEALED_RUNNER_HEAD_MISMATCH"):
                RUNNER.validate_runtime_binding(
                    REPOSITORY,
                    Path("/private/not-read"),
                    Path("/private/not-read/binding.json"),
                    "a" * 40,
                    "b" * 40,
                )
        private_validation.assert_not_called()

    def test_cli_requires_an_explicit_execution_mode(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                RUNNER.main(
                    [
                        "--private-root",
                        "/private/not-read",
                        "--execution-binding",
                        "/private/not-read/binding.json",
                        "--data-commit",
                        "a" * 40,
                        "--runner-commit",
                        "b" * 40,
                    ]
                )
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.getvalue(), "")

    def test_preflight_mode_never_requires_output_or_calls_model(self) -> None:
        output = io.StringIO()
        with mock.patch.object(RUNNER, "validate_runtime_binding", return_value=(self._tree(), {})), contextlib.redirect_stdout(output):
            exit_code = RUNNER.main(
                [
                    "--private-root",
                    "/private/not-read",
                    "--execution-binding",
                    "/private/not-read/binding.json",
                    "--data-commit",
                    "a" * 40,
                    "--runner-commit",
                    "b" * 40,
                    "--preflight-only",
                ]
            )
        self.assertEqual(exit_code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "PREFLIGHT_READY")
        self.assertIs(report["llm_called"], False)


if __name__ == "__main__":
    unittest.main()
