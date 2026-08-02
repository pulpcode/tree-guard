from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from treeguard.ai_review import (
    BailianConfig,
    BailianProviderError,
    BailianScenarioPreparationProvider,
    InternalQwenConfig,
    InternalQwenScenarioPreparationProvider,
    SCENARIO_PREPARATION_PROMPT_VERSION,
)
from treeguard.tree_understanding import (
    SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
    NewNodePlacementSeed,
    ScenarioPreparationProjection,
    TreeUnderstandingError,
    build_scenario_preparation_plan,
    build_scenario_preparation_projection,
    build_tree_diagnostic_profile,
)
from tests.test_tree_understanding import (
    _fictional_tree,
    _wide_fictional_tree,
)


REQUIREMENT_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_REQUIREMENT_TEXT__"
)
ASPECT_TEMPLATE_SENTINEL = "__TREEGUARD_MUST_REWRITE_REQUESTED_ASPECT__"
RATIONALE_TEMPLATE_SENTINEL = "__TREEGUARD_MUST_REWRITE_RATIONALE__"
EVIDENCE_GAP_TEMPLATE_SENTINEL = (
    "__TREEGUARD_MUST_REWRITE_EVIDENCE_GAP__"
)


def _model_response(payload: dict[str, object]) -> dict[str, object]:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            }
        ]
    }


def _valid_candidate_output(
    projection: ScenarioPreparationProjection,
    *,
    requirement_text: str = "Reuse the existing imaginary structure for this field.",
) -> dict[str, object]:
    supporting_refs = list(projection.anchor_refs)
    uncertainties = (
        ["The request leaves a bounded structural ambiguity to disclose."]
        if projection.scenario_family
        in {"HOMONYM_CLARIFICATION", "UNBOUNDED_COMBINATION"}
        else []
    )
    evidence_gaps = (
        ["The projected tree does not contain the requested business evidence."]
        if projection.scenario_family == "INSUFFICIENT_EVIDENCE"
        else []
    )
    return {
        "schema_version": SCENARIO_MODEL_OUTPUT_SCHEMA_VERSION,
        "plan_unit_ref": projection.plan_unit_ref,
        "scenario_ref": "S001",
        "planning_mode": projection.planning_mode,
        "scenario_family": projection.scenario_family,
        "target_stage": projection.target_stage,
        "requirement_text": requirement_text,
        "proposed_parent_ref": projection.proposed_parent_ref,
        "node_kind_hint": projection.node_kind_hint,
        "value_type_hint": projection.value_type_hint,
        "cardinality_hint": projection.cardinality_hint,
        "supporting_node_refs": supporting_refs,
        "source_signal_refs": list(projection.signal_refs),
        "requested_aspects": [
            {
                "aspect": "Express one bounded structural change request.",
                "supporting_node_refs": supporting_refs,
            }
        ],
        "rationale": "The projected anchors directly support this request.",
        "uncertainties": uncertainties,
        "evidence_gaps": evidence_gaps,
    }


class ScenarioPreparationProviderTests(unittest.TestCase):
    def _provider(
        self,
        *,
        max_attempts: int = 2,
    ) -> InternalQwenScenarioPreparationProvider:
        return InternalQwenScenarioPreparationProvider(
            InternalQwenConfig(
                base_url="http://10.20.30.40:8000/v1",
                model="fictional-qwen",
                max_attempts=max_attempts,
            )
        )

    def _sources(
        self,
        *,
        max_plan_units: int,
        new_node_placement_seed: NewNodePlacementSeed | None = None,
    ):
        tree = _fictional_tree()
        profile = build_tree_diagnostic_profile(tree)
        plan = build_scenario_preparation_plan(
            tree,
            profile,
            max_plan_units=max_plan_units,
            new_node_placement_seed=new_node_placement_seed,
        )
        projections = {
            unit.plan_unit_ref: build_scenario_preparation_projection(
                tree,
                profile,
                plan,
                unit.plan_unit_ref,
            )
            for unit in plan.units
        }
        return tree, profile, plan, projections

    @staticmethod
    def _request_unit_ref(body: dict[str, object]) -> str:
        messages = body["messages"]
        if not isinstance(messages, list):
            raise AssertionError("messages must be a list")
        message = messages[1]
        if not isinstance(message, dict):
            raise AssertionError("user message must be an object")
        payload = json.loads(message["content"])
        return payload["scenario_projection"]["assignment"]["plan_unit_ref"]

    def test_internal_qwen_uses_only_the_per_unit_model_projection(self) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=1)
        provider = self._provider()
        sent: list[dict[str, object]] = []

        def fake_post(body):
            sent.append(body)
            projection = projections[self._request_unit_ref(body)]
            return _model_response(_valid_candidate_output(projection))

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(len(sent), 1)
        self.assertEqual(batch.completed_unit_count, 1)
        self.assertEqual(batch.failed_unit_count, 0)
        self.assertEqual(batch.candidates[0].candidate_ref, "C001")
        self.assertEqual(
            batch.candidates[0].draft.review_status,
            "PENDING_HUMAN_REVIEW",
        )
        self.assertFalse(batch.candidates[0].draft.gold_eligible)
        self.assertFalse(batch.candidates[0].draft.patch_eligible)
        self.assertEqual(
            batch.candidates[0].draft.prompt_version,
            SCENARIO_PREPARATION_PROMPT_VERSION,
        )
        self.assertEqual(
            sent[0]["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertNotIn("enable_thinking", sent[0])
        self.assertEqual(sent[0]["temperature"], 0)
        self.assertEqual(
            provider._request_headers(),
            {"Content-Type": "application/json"},
        )
        user_payload = json.loads(sent[0]["messages"][1]["content"])
        projection = projections[plan.units[0].plan_unit_ref]
        self.assertEqual(
            user_payload["scenario_projection"],
            projection.to_model_dict(),
        )
        self.assertEqual(
            user_payload["allowed_references"]["supporting_node_refs"],
            list(projection.evidence_node_refs),
        )
        self.assertEqual(
            user_payload["exact_object_template"]["plan_unit_ref"],
            projection.plan_unit_ref,
        )
        encoded_request = json.dumps(sent[0], ensure_ascii=False, sort_keys=True)
        for forbidden in (
            tree.snapshot_hash,
            profile.profile_hash,
            plan.plan_hash,
            projection.projection_hash,
            "lattice-root",
            "alpha-signal",
            "beta-signal",
            "fictional-version-record",
            "scenarios.json",
            "promotion.json",
        ):
            self.assertNotIn(forbidden, encoded_request)
        self.assertEqual(
            SCENARIO_PREPARATION_PROMPT_VERSION,
            "treeguard.scenario-preparation.zh.v3",
        )

    def test_prompt_v3_uses_must_rewrite_template_sentinels(self) -> None:
        seed = NewNodePlacementSeed(
            parent_node_id="alpha-branch",
            proposed_name="Novel imaginary marker",
            node_kind_hint="PROPERTY",
            value_type_hint="string",
            cardinality_hint="SINGLE",
        )
        _, _, plan, projections = self._sources(
            max_plan_units=16,
            new_node_placement_seed=seed,
        )
        provider = self._provider()
        projection = projections[plan.units[0].plan_unit_ref]
        body = provider._scenario_preparation_request_body(  # noqa: SLF001
            projection,
            retry=False,
        )
        user_payload = json.loads(body["messages"][1]["content"])
        template = user_payload["exact_object_template"]

        self.assertEqual(
            template["requirement_text"],
            REQUIREMENT_TEMPLATE_SENTINEL,
        )
        self.assertEqual(
            template["requested_aspects"][0]["aspect"],
            ASPECT_TEMPLATE_SENTINEL,
        )
        self.assertEqual(
            template["rationale"],
            RATIONALE_TEMPLATE_SENTINEL,
        )
        insufficient_unit = next(
            unit
            for unit in plan.units
            if unit.scenario_family == "INSUFFICIENT_EVIDENCE"
        )
        insufficient_body = provider._scenario_preparation_request_body(  # noqa: SLF001
            projections[insufficient_unit.plan_unit_ref],
            retry=False,
        )
        insufficient_payload = json.loads(
            insufficient_body["messages"][1]["content"]
        )
        self.assertEqual(
            insufficient_payload["exact_object_template"]["evidence_gaps"],
            [EVIDENCE_GAP_TEMPLATE_SENTINEL],
        )
        self.assertTrue(
            user_payload["deterministic_policy"][
                "temporary_references_forbidden_in_all_natural_language_fields"
            ]
        )
        system_prompt = body["messages"][0]["content"]
        self.assertIn("SINGLE/MULTIPLE 只表达基数", system_prompt)
        self.assertIn("N/D/S 临时引用只能出现在结构化引用字段", system_prompt)

    def test_prompt_v3_states_semantic_generation_boundaries(self) -> None:
        _, _, plan, projections = self._sources(max_plan_units=1)
        provider = self._provider()
        projection = projections[plan.units[0].plan_unit_ref]
        body = provider._scenario_preparation_request_body(  # noqa: SLF001
            projection,
            retry=False,
        )
        system_prompt = body["messages"][0]["content"]

        for required_policy in (
            "已有节点只代表可复用的结构定义，不代表任何实例值已经存在",
            "不能生成读取、填写或查询实例值的需求",
            "requirement_text 必须采用自然用户视角",
            "UNBOUNDED_COMBINATION 的缩小范围建议只能写入 uncertainties",
            "不能提前写入 requirement_text",
            "INSUFFICIENT_EVIDENCE 的 evidence_gaps 必须具体说明缺少哪类证据或输入",
            "NEW_NODE_PLACEMENT 的自然语言数量表达必须与 cardinality_hint 一致",
        ):
            with self.subTest(required_policy=required_policy):
                self.assertIn(required_policy, system_prompt)

    def test_prompt_v3_has_distinct_non_internal_family_tasks(self) -> None:
        seed = NewNodePlacementSeed(
            parent_node_id="alpha-branch",
            proposed_name="Novel imaginary marker",
            node_kind_hint="PROPERTY",
            value_type_hint="string",
            cardinality_hint="SINGLE",
        )
        _, _, plan, projections = self._sources(
            max_plan_units=16,
            new_node_placement_seed=seed,
        )
        provider = self._provider()
        actual_tasks: dict[str, str] = {}
        for unit in plan.units:
            if unit.unit_role != "RISK_CHALLENGE":
                continue
            projection = projections[unit.plan_unit_ref]
            body = provider._scenario_preparation_request_body(  # noqa: SLF001
                projection,
                retry=False,
            )
            user_payload = json.loads(body["messages"][1]["content"])
            family_task = user_payload.get("family_task")
            self.assertIsInstance(family_task, str)
            if not isinstance(family_task, str):
                raise AssertionError("family_task must be text")
            actual_tasks[unit.scenario_family] = family_task

        self.assertEqual(len(actual_tasks), 8)
        self.assertEqual(
            len(set(actual_tasks.values())),
            len(actual_tasks),
        )
        for family, family_task in actual_tasks.items():
            for forbidden in ("MVP", "主要锚点", "用于验证"):
                with self.subTest(family=family, forbidden=forbidden):
                    self.assertNotIn(forbidden, family_task)
        self.assertIn("结构定义", actual_tasks["CLEAR_EXISTING_REUSE"])
        self.assertIn("基数提示", actual_tasks["NEW_NODE_PLACEMENT"])
        self.assertIn("证据缺口", actual_tasks["INSUFFICIENT_EVIDENCE"])
        self.assertIn("过宽需求", actual_tasks["UNBOUNDED_COMBINATION"])

    def test_invalid_first_output_is_discarded_before_complete_retry(self) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=1)
        provider = self._provider(max_attempts=2)
        sent: list[dict[str, object]] = []

        def fake_post(body):
            sent.append(body)
            projection = projections[self._request_unit_ref(body)]
            payload = _valid_candidate_output(
                projection,
                requirement_text="Use only the complete second candidate.",
            )
            if len(sent) == 1:
                payload.pop("evidence_gaps")
            return _model_response(payload)

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(len(sent), 2)
        self.assertEqual(batch.completed_unit_count, 1)
        self.assertEqual(batch.failed_unit_count, 0)
        self.assertEqual(
            batch.candidates[0].draft.requirement_text,
            "Use only the complete second candidate.",
        )
        retry_prompt = sent[1]["messages"][0]["content"]
        self.assertIn("上一次输出未通过本地合同校验", retry_prompt)

    def test_prompt_v3_text_policy_failure_retries_complete_candidate(
        self,
    ) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=1)
        provider = self._provider(max_attempts=2)
        sent: list[dict[str, object]] = []

        def fake_post(body):
            sent.append(body)
            projection = projections[self._request_unit_ref(body)]
            payload = _valid_candidate_output(
                projection,
                requirement_text="Use only the rewritten second candidate.",
            )
            if len(sent) == 1:
                payload["rationale"] = "The first candidate still exposes N001."
            return _model_response(payload)

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(len(sent), 2)
        self.assertEqual(batch.completed_unit_count, 1)
        self.assertEqual(batch.failed_unit_count, 0)
        self.assertEqual(
            batch.candidates[0].draft.requirement_text,
            "Use only the rewritten second candidate.",
        )

    def test_prompt_v3_family_policy_failure_retries_complete_candidate(
        self,
    ) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=2)
        provider = self._provider(max_attempts=2)
        calls: list[str] = []
        attempts_by_unit: dict[str, int] = {}

        def fake_post(body):
            unit_ref = self._request_unit_ref(body)
            calls.append(unit_ref)
            attempts_by_unit[unit_ref] = attempts_by_unit.get(unit_ref, 0) + 1
            projection = projections[unit_ref]
            payload = _valid_candidate_output(projection)
            if unit_ref == "U002" and attempts_by_unit[unit_ref] == 1:
                payload["uncertainties"] = []
            return _model_response(payload)

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(calls, ["U001", "U002", "U002"])
        self.assertEqual(batch.completed_unit_count, 2)
        self.assertEqual(batch.failed_unit_count, 0)
        second = next(
            item
            for item in batch.candidates
            if item.plan_unit_ref == "U002"
        )
        self.assertTrue(second.draft.uncertainties)

    def test_complete_plan_assigns_distinct_run_refs_to_local_s001_drafts(
        self,
    ) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=16)
        provider = self._provider()

        def fake_post(body):
            projection = projections[self._request_unit_ref(body)]
            return _model_response(_valid_candidate_output(projection))

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(batch.status, "SUCCESS")
        self.assertEqual(batch.completed_unit_count, len(plan.units))
        self.assertEqual(
            tuple(item.candidate_ref for item in batch.candidates),
            tuple(
                f"C{index:03d}"
                for index in range(1, len(plan.units) + 1)
            ),
        )
        self.assertEqual(
            {item.draft.scenario_ref for item in batch.candidates},
            {"S001"},
        )

    def test_transport_failure_is_recorded_and_next_unit_continues(self) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=2)
        provider = self._provider(max_attempts=2)
        calls: list[str] = []

        def fake_post(body):
            unit_ref = self._request_unit_ref(body)
            calls.append(unit_ref)
            if unit_ref == "U002":
                raise BailianProviderError(
                    "QWEN_CONNECTION_FAILED",
                    "fictional transport failure",
                )
            return _model_response(
                _valid_candidate_output(projections[unit_ref])
            )

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(calls, ["U001", "U002"])
        self.assertEqual(batch.status, "PARTIAL")
        self.assertEqual(batch.completed_unit_count, 1)
        self.assertEqual(batch.failed_unit_count, 1)
        self.assertEqual(batch.failures[0].plan_unit_ref, "U002")
        self.assertEqual(batch.failures[0].error_code, "QWEN_CONNECTION_FAILED")

    def test_all_transport_failures_return_failed_batch_without_candidates(
        self,
    ) -> None:
        tree, profile, plan, _ = self._sources(max_plan_units=2)
        provider = self._provider(max_attempts=2)
        calls: list[str] = []

        def fake_post(body):
            calls.append(self._request_unit_ref(body))
            raise BailianProviderError(
                "QWEN_CONNECTION_FAILED",
                "fictional transport failure",
            )

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(calls, ["U001", "U002"])
        self.assertEqual(batch.status, "FAILED")
        self.assertEqual(batch.reviewable_candidate_count, 0)
        self.assertEqual(batch.completed_unit_count, 0)
        self.assertEqual(batch.failed_unit_count, 2)

    def test_contract_failures_respect_two_attempts_per_unit(self) -> None:
        tree, profile, plan, _ = self._sources(max_plan_units=2)
        provider = self._provider(max_attempts=2)
        calls: list[str] = []

        def fake_post(body):
            calls.append(self._request_unit_ref(body))
            return _model_response({"schema_version": "wrong"})

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(tree, profile, plan)

        self.assertEqual(calls, ["U001", "U001", "U002", "U002"])
        self.assertLessEqual(len(calls), len(plan.units) * 2)
        self.assertEqual(batch.status, "FAILED")
        self.assertEqual(batch.failed_unit_count, 2)
        self.assertEqual(
            {failure.error_code for failure in batch.failures},
            {"SCENARIO_PREPARATION_MODEL_FIELDS_INVALID"},
        )

    def test_all_sources_are_replayed_before_any_transport(self) -> None:
        _, profile, plan, _ = self._sources(max_plan_units=2)
        different_tree = _wide_fictional_tree(5)
        provider = self._provider()
        network_called = False

        def fake_post(body):
            nonlocal network_called
            network_called = True
            raise AssertionError("transport must not run for stale sources")

        provider._post_json = fake_post  # type: ignore[method-assign]

        with self.assertRaises(TreeUnderstandingError):
            provider.prepare(different_tree, profile, plan)

        self.assertFalse(network_called)

    def test_projection_unit_failure_is_recorded_before_other_unit_io(
        self,
    ) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=2)
        provider = self._provider()
        network_called = False
        calls: list[str] = []

        def fake_build(tree_arg, profile_arg, plan_arg, unit_ref):
            self.assertFalse(network_called)
            if unit_ref == "U001":
                raise TreeUnderstandingError(
                    "SCENARIO_PREPARATION_PROJECTION_TOO_LARGE",
                    "fictional projection exceeded its budget",
                )
            return projections[unit_ref]

        def fake_post(body):
            nonlocal network_called
            network_called = True
            unit_ref = self._request_unit_ref(body)
            calls.append(unit_ref)
            return _model_response(
                _valid_candidate_output(projections[unit_ref])
            )

        provider._post_json = fake_post  # type: ignore[method-assign]
        with patch(
            "treeguard.ai_review.build_scenario_preparation_projection",
            side_effect=fake_build,
        ):
            batch = provider.prepare(tree, profile, plan)

        self.assertEqual(calls, ["U002"])
        self.assertEqual(batch.completed_unit_count, 1)
        self.assertEqual(batch.failed_unit_count, 1)
        self.assertEqual(batch.failures[0].plan_unit_ref, "U001")
        self.assertEqual(
            batch.failures[0].error_code,
            "SCENARIO_PREPARATION_PROJECTION_TOO_LARGE",
        )

    def test_all_projection_unit_failures_make_zero_transport_calls(
        self,
    ) -> None:
        tree, profile, plan, _ = self._sources(max_plan_units=2)
        provider = self._provider()
        network_called = False

        def fake_post(body):
            nonlocal network_called
            network_called = True
            raise AssertionError("transport must not run without a projection")

        provider._post_json = fake_post  # type: ignore[method-assign]
        with patch(
            "treeguard.ai_review.build_scenario_preparation_projection",
            side_effect=TreeUnderstandingError(
                "SCENARIO_PREPARATION_PROJECTION_REQUIRED_SCOPE_TOO_LARGE",
                "fictional required scope exceeded its budget",
            ),
        ):
            batch = provider.prepare(tree, profile, plan)

        self.assertFalse(network_called)
        self.assertEqual(batch.status, "FAILED")
        self.assertEqual(batch.failed_unit_count, 2)
        self.assertEqual(batch.reviewable_candidate_count, 0)

    def test_bailian_requires_exact_approval_before_transport(self) -> None:
        tree, profile, plan, _ = self._sources(max_plan_units=1)
        provider = BailianScenarioPreparationProvider(
            BailianConfig(
                api_key="fictional-token",
                model="fictional-qwen",
            )
        )
        network_called = False

        def fake_post(body):
            nonlocal network_called
            network_called = True
            raise AssertionError("transport must not run without approval")

        provider._post_json = fake_post  # type: ignore[method-assign]

        with self.assertRaises(BailianProviderError) as captured:
            provider.prepare(tree, profile, plan)

        self.assertEqual(
            captured.exception.code,
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertFalse(network_called)

        with self.assertRaises(BailianProviderError) as captured:
            provider.prepare(
                tree,
                profile,
                plan,
                external_data_approved=1,  # type: ignore[arg-type]
            )

        self.assertEqual(
            captured.exception.code,
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertFalse(network_called)

    def test_bailian_approved_fictional_plan_uses_bailian_transport(self) -> None:
        tree, profile, plan, projections = self._sources(max_plan_units=1)
        provider = BailianScenarioPreparationProvider(
            BailianConfig(
                api_key="fictional-token",
                model="fictional-qwen",
            )
        )
        sent: list[dict[str, object]] = []

        def fake_post(body):
            sent.append(body)
            projection = projections[self._request_unit_ref(body)]
            return _model_response(_valid_candidate_output(projection))

        provider._post_json = fake_post  # type: ignore[method-assign]
        batch = provider.prepare(
            tree,
            profile,
            plan,
            external_data_approved=True,
        )

        self.assertEqual(batch.completed_unit_count, 1)
        self.assertEqual(len(sent), 1)
        self.assertFalse(sent[0]["enable_thinking"])
        self.assertNotIn("chat_template_kwargs", sent[0])
        self.assertEqual(
            provider._request_headers(),
            {
                "Authorization": "Bearer fictional-token",
                "Content-Type": "application/json",
            },
        )


if __name__ == "__main__":
    unittest.main()
