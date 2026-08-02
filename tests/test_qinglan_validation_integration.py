from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import treeguard.qinglan_validation_dataset as qinglan_runtime
from treeguard.adapter import adapt_tree_document
from treeguard.ai_review import (
    LoopbackSimulatorIntentDraftProvider,
    LoopbackSimulatorSemanticRecommendationProvider,
)
from treeguard.fictional_qinglan_library_data import (
    build_qinglan_library_manifest,
    build_qinglan_library_scenarios,
    build_qinglan_library_tree,
)
from treeguard.fictional_qinglan_library_semantic_data import (
    build_qinglan_library_semantic_manifest,
    build_qinglan_library_semantic_scenarios,
    build_qinglan_library_semantic_tree,
)
from treeguard.fire_validation_dataset import (
    FictionalFireValidationDataset,
)
from treeguard.qinglan_validation_dataset import (
    FictionalQinglanRepositoryOverlay,
    FictionalQinglanSemanticValidationDataset,
    FictionalQinglanValidationDataset,
    QINGLAN_CATEGORY_ID,
    QINGLAN_DATASET_REF,
    QINGLAN_RESOURCE_ID,
    QINGLAN_SEMANTIC_DATASET_REF,
    QINGLAN_SEMANTIC_RESOURCE_ID,
    QINGLAN_SEMANTIC_VARIANT_REF,
    QINGLAN_SEMANTIC_VERSION,
    QINGLAN_SEMANTIC_VERSION_RECORD_ID,
    QINGLAN_VARIANT_REF,
    QINGLAN_VERSION,
    QINGLAN_VERSION_RECORD_ID,
)
from treeguard.repository_client import (
    CategoryRef,
    RepositoryClientError,
    ResourceHead,
    VersionRef,
)
from treeguard.simulator import (
    SIMULATOR_BEARER_TOKEN,
    ContractSimulator,
)
from treeguard.tree_understanding import (
    build_tree_diagnostic_profile,
    build_tree_understanding_projection,
)
from treeguard.web import _services_from_environment
from treeguard.workbench_governance import (
    DefaultProviderFactory,
    WorkbenchGovernanceService,
)
from treeguard.workbench_validation import ValidationWorkbenchService


class InlineExecutor:
    def submit(self, function: Any) -> None:
        function()


def _pure_model_post(simulator: ContractSimulator):
    def post(provider: Any, body: dict[str, Any]) -> Any:
        response = simulator.handle(
            method="POST",
            target="/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SIMULATOR_BEARER_TOKEN}",
                "Content-Type": "application/json",
            },
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        )
        if response.status_code != 200:
            raise AssertionError(
                f"unexpected simulator status {response.status_code}"
            )
        return json.loads(response.body)

    return post


@dataclass
class DelegateRepository:
    fetch_calls: list[tuple[str, str | None, str | None]] = field(
        default_factory=list
    )

    def list_categories(self) -> tuple[CategoryRef, ...]:
        return (
            CategoryRef(
                category_id="existing-category",
                parent_id=None,
                name="现有分类",
                order=3,
            ),
        )

    def list_resources(
        self,
        category_id: str,
    ) -> tuple[ResourceHead, ...]:
        return (
            ResourceHead(
                resource_id="existing-resource",
                category_id=category_id,
                name="现有资源",
                head_version="EX-1",
                head_version_record_id="existing-record",
            ),
        )

    def list_versions(
        self,
        resource_id: str,
    ) -> tuple[VersionRef, ...]:
        return (
            VersionRef(
                position=0,
                version="EX-1",
                version_record_id="existing-record",
                description=None,
                is_head=True,
            ),
        )

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ):
        self.fetch_calls.append(
            (resource_id, version, version_record_id)
        )
        return adapt_tree_document(build_qinglan_library_tree())


@dataclass
class ScenarioGovernanceStub:
    expected_by_requirement: dict[str, str]
    create_calls: list[dict[str, Any]] = field(default_factory=list)
    case_status_by_ref: dict[str, str] = field(default_factory=dict)

    def create_case(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(kwargs)
        case_ref = f"CASE_{len(self.create_calls):03d}"
        self.case_status_by_ref[case_ref] = self.expected_by_requirement[
            kwargs["requirement_text"]
        ]
        return {
            "schema_version": "workbench-operation-view.v1",
            "operation_ref": f"OP_{len(self.create_calls):03d}",
            "case_ref": case_ref,
            "kind": "DRAFT_INTENT",
            "status": "SUCCEEDED",
            "error_code": None,
            "case_status": "COMPLETED",
        }

    def case_view(self, case_ref: str) -> dict[str, Any]:
        return {
            "status": "COMPLETED",
            "intent": {
                "review_status": self.case_status_by_ref[case_ref],
            },
            "candidates": None,
            "record": None,
        }


class QinglanProviderTests(unittest.TestCase):
    def test_provider_rebuilds_approved_manifest_and_intent_only_oracles(
        self,
    ) -> None:
        source_manifest = build_qinglan_library_manifest()
        source_scenarios = build_qinglan_library_scenarios()
        provider = FictionalQinglanValidationDataset()
        manifest = provider.manifest()
        scenarios = provider.scenarios(QINGLAN_VARIANT_REF)

        self.assertEqual(provider.dataset_ref, source_manifest["dataset_ref"])
        self.assertEqual(manifest.dataset_ref, QINGLAN_DATASET_REF)
        self.assertEqual(len(manifest.variants), 1)
        variant = manifest.variants[0]
        self.assertEqual(variant.variant_ref, "small")
        self.assertEqual(variant.node_count, 48)
        self.assertEqual(variant.scenario_count, 12)
        self.assertEqual(
            manifest.limitations[: len(source_manifest["limitations"])],
            tuple(source_manifest["limitations"]),
        )
        self.assertIn("只比较意图阶段", manifest.limitations[-1])
        self.assertEqual(
            [item.scenario_ref for item in scenarios],
            [item["scenario_ref"] for item in source_scenarios],
        )
        self.assertEqual(
            sum(
                item.oracle.draft_status == "NEEDS_CLARIFICATION"
                for item in scenarios
            ),
            2,
        )
        self.assertEqual(
            sum(
                item.oracle.draft_status
                == "READY_FOR_HUMAN_REVIEW"
                for item in scenarios
            ),
            10,
        )
        for item in scenarios:
            self.assertIsNone(item.oracle.clarification_status)
            self.assertIsNone(item.oracle.candidate_status)
            self.assertIsNone(item.oracle.recommendation_status)
            self.assertEqual(item.flow, "INTENT_ONLY")
        self.assertEqual(provider.scenarios("unknown"), ())

    def test_semantic_provider_rebuilds_medium_intent_only_batch(
        self,
    ) -> None:
        source_manifest = build_qinglan_library_semantic_manifest()
        source_scenarios = build_qinglan_library_semantic_scenarios()
        provider = FictionalQinglanSemanticValidationDataset()
        manifest = provider.manifest()
        scenarios = provider.scenarios(QINGLAN_SEMANTIC_VARIANT_REF)

        self.assertEqual(provider.dataset_ref, source_manifest["dataset_ref"])
        self.assertEqual(
            manifest.dataset_ref,
            QINGLAN_SEMANTIC_DATASET_REF,
        )
        self.assertEqual(len(manifest.variants), 1)
        variant = manifest.variants[0]
        self.assertEqual(variant.variant_ref, "medium")
        self.assertEqual(variant.node_count, 312)
        self.assertEqual(variant.scenario_count, 20)
        self.assertEqual(
            manifest.limitations[: len(source_manifest["limitations"])],
            tuple(source_manifest["limitations"]),
        )
        self.assertIn("只比较意图阶段", manifest.limitations[-1])
        self.assertEqual(
            [item.scenario_ref for item in scenarios],
            [item["scenario_ref"] for item in source_scenarios],
        )
        for source, scenario in zip(source_scenarios, scenarios):
            category = source["proposed_observable_state"]["category"]
            expected_status = (
                "NEEDS_CLARIFICATION"
                if category == "NEED_CLARIFICATION"
                else "READY_FOR_HUMAN_REVIEW"
            )
            self.assertEqual(
                scenario.oracle.draft_status,
                expected_status,
            )
            self.assertIsNone(scenario.oracle.clarification_status)
            self.assertIsNone(scenario.oracle.candidate_status)
            self.assertIsNone(scenario.oracle.recommendation_status)
            self.assertEqual(scenario.flow, "INTENT_ONLY")
        self.assertEqual(provider.scenarios("unknown"), ())


class QinglanRepositoryOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.delegate = DelegateRepository()
        self.overlay = FictionalQinglanRepositoryOverlay(self.delegate)

    def test_overlay_exposes_qinglan_and_delegates_other_resources(
        self,
    ) -> None:
        categories = self.overlay.list_categories()
        self.assertEqual(
            [item.category_id for item in categories],
            ["existing-category", QINGLAN_CATEGORY_ID],
        )
        self.assertEqual(categories[-1].order, 4)

        resources = self.overlay.list_resources(QINGLAN_CATEGORY_ID)
        self.assertEqual(
            [item.resource_id for item in resources],
            [QINGLAN_RESOURCE_ID, QINGLAN_SEMANTIC_RESOURCE_ID],
        )
        self.assertEqual(resources[0].head_version, QINGLAN_VERSION)
        versions = self.overlay.list_versions(QINGLAN_RESOURCE_ID)
        self.assertEqual(versions[0].version, QINGLAN_VERSION)
        self.assertEqual(
            versions[0].version_record_id,
            QINGLAN_VERSION_RECORD_ID,
        )

        by_version = self.overlay.fetch_tree(
            QINGLAN_RESOURCE_ID,
            version=QINGLAN_VERSION,
        )
        by_record = self.overlay.fetch_tree(
            QINGLAN_RESOURCE_ID,
            version_record_id=QINGLAN_VERSION_RECORD_ID,
        )
        self.assertTrue(by_version.is_valid)
        self.assertEqual(by_version.observed_node_count, 48)
        self.assertEqual(by_record.tree, by_version.tree)

        semantic_versions = self.overlay.list_versions(
            QINGLAN_SEMANTIC_RESOURCE_ID
        )
        self.assertEqual(
            semantic_versions[0].version,
            QINGLAN_SEMANTIC_VERSION,
        )
        semantic_by_version = self.overlay.fetch_tree(
            QINGLAN_SEMANTIC_RESOURCE_ID,
            version=QINGLAN_SEMANTIC_VERSION,
        )
        semantic_by_record = self.overlay.fetch_tree(
            QINGLAN_SEMANTIC_RESOURCE_ID,
            version_record_id=QINGLAN_SEMANTIC_VERSION_RECORD_ID,
        )
        self.assertTrue(semantic_by_version.is_valid)
        self.assertEqual(semantic_by_version.observed_node_count, 312)
        self.assertEqual(
            semantic_by_record.tree,
            semantic_by_version.tree,
        )

        delegated_resources = self.overlay.list_resources(
            "existing-category"
        )
        delegated_versions = self.overlay.list_versions(
            "existing-resource"
        )
        delegated_tree = self.overlay.fetch_tree(
            "existing-resource",
            version="EX-1",
        )
        self.assertEqual(
            delegated_resources[0].resource_id,
            "existing-resource",
        )
        self.assertEqual(delegated_versions[0].version, "EX-1")
        self.assertTrue(delegated_tree.is_valid)
        self.assertEqual(
            self.delegate.fetch_calls,
            [("existing-resource", "EX-1", None)],
        )

    def test_overlay_rejects_invalid_selectors_and_category_collision(
        self,
    ) -> None:
        resources = (
            (
                QINGLAN_RESOURCE_ID,
                QINGLAN_VERSION,
                QINGLAN_VERSION_RECORD_ID,
            ),
            (
                QINGLAN_SEMANTIC_RESOURCE_ID,
                QINGLAN_SEMANTIC_VERSION,
                QINGLAN_SEMANTIC_VERSION_RECORD_ID,
            ),
        )
        for resource_id, version, version_record_id in resources:
            invalid_selectors = (
                {},
                {
                    "version": version,
                    "version_record_id": version_record_id,
                },
                {"version": "unknown"},
                {"version_record_id": "unknown"},
            )
            for selector in invalid_selectors:
                with (
                    self.subTest(
                        resource_id=resource_id,
                        selector=selector,
                    ),
                    self.assertRaises(RepositoryClientError) as caught,
                ):
                    self.overlay.fetch_tree(
                        resource_id,
                        **selector,
                    )
                self.assertEqual(
                    caught.exception.code,
                    "REPOSITORY_QINGLAN_SELECTOR_INVALID",
                )

        class CollisionRepository(DelegateRepository):
            def list_categories(self) -> tuple[CategoryRef, ...]:
                return (
                    CategoryRef(
                        category_id=QINGLAN_CATEGORY_ID,
                        parent_id=None,
                        name="冲突分类",
                        order=0,
                    ),
                )

        with self.assertRaises(RepositoryClientError) as caught:
            FictionalQinglanRepositoryOverlay(
                CollisionRepository()
            ).list_categories()
        self.assertEqual(
            caught.exception.code,
            "REPOSITORY_QINGLAN_OVERLAY_CONFLICT",
        )

    def test_overlay_rejects_a_tree_that_fails_canonical_adaptation(
        self,
    ) -> None:
        with (
            patch.object(
                qinglan_runtime,
                "build_qinglan_library_tree",
                return_value={},
            ),
            self.assertRaises(RepositoryClientError) as caught,
        ):
            self.overlay.fetch_tree(
                QINGLAN_RESOURCE_ID,
                version=QINGLAN_VERSION,
            )

        self.assertEqual(
            caught.exception.code,
            "REPOSITORY_QINGLAN_TREE_INVALID",
        )


class QinglanValidationServiceTests(unittest.TestCase):
    def test_all_scenarios_project_parent_refs_and_bind_runs(self) -> None:
        providers = (
            FictionalQinglanValidationDataset(),
            FictionalQinglanSemanticValidationDataset(),
        )
        batches = (
            (
                providers[0],
                QINGLAN_DATASET_REF,
                QINGLAN_VARIANT_REF,
            ),
            (
                providers[1],
                QINGLAN_SEMANTIC_DATASET_REF,
                QINGLAN_SEMANTIC_VARIANT_REF,
            ),
        )
        scenarios = tuple(
            scenario
            for provider, _, variant_ref in batches
            for scenario in provider.scenarios(variant_ref)
        )
        expected_by_requirement = {
            item.request.requirement_text: item.oracle.draft_status
            for item in scenarios
        }
        governance = ScenarioGovernanceStub(expected_by_requirement)
        service = ValidationWorkbenchService(
            repository=FictionalQinglanRepositoryOverlay(
                DelegateRepository()
            ),
            governance=governance,
            providers=providers,
        )

        for provider, dataset_ref, variant_ref in batches:
            public_scenarios = service.scenarios(
                dataset_ref,
                variant_ref,
            )
            encoded = json.dumps(public_scenarios, ensure_ascii=False)
            self.assertNotIn("ql-", encoded)
            self.assertNotIn("qs-", encoded)
            self.assertEqual(
                len(public_scenarios["items"]),
                provider.manifest().variants[0].scenario_count,
            )

            for scenario in provider.scenarios(variant_ref):
                with self.subTest(
                    dataset_ref=dataset_ref,
                    scenario_ref=scenario.scenario_ref,
                ):
                    operation = service.create_run(
                        dataset_ref=dataset_ref,
                        variant_ref=variant_ref,
                        scenario_ref=scenario.scenario_ref,
                        model_mode="SIMULATOR_LIVE",
                        external_data_approved=False,
                    )
                    comparison = service.comparison(
                        operation["case_ref"]
                    )
                    self.assertEqual(comparison["status"], "MATCH")
                    self.assertEqual(
                        [
                            item["metric"]
                            for item in comparison["items"]
                        ],
                        ["intent_review_status"],
                    )
                    self.assertFalse(comparison["gold_eligible"])

        self.assertEqual(len(governance.create_calls), 32)
        for source, call in zip(scenarios, governance.create_calls):
            if source.request.proposed_parent_node_id is None:
                self.assertIsNone(call["proposed_parent_ref"])
            else:
                self.assertRegex(
                    call["proposed_parent_ref"],
                    r"^N[0-9]{6}$",
                )

    def test_one_stable_scenario_runs_through_real_governance(
        self,
    ) -> None:
        repository = FictionalQinglanRepositoryOverlay(
            DelegateRepository()
        )
        simulator = ContractSimulator()
        post = _pure_model_post(simulator)
        identifiers = iter(
            ("qinglan-case", "draft", "intent", "recommendation")
        )
        provider = FictionalQinglanValidationDataset()
        with tempfile.TemporaryDirectory() as directory:
            governance = WorkbenchGovernanceService(
                repository=repository,
                sidecar_root=Path(directory) / "sidecars",
                provider_factory=DefaultProviderFactory(
                    simulator_base_url="http://127.0.0.1:8765/v1"
                ),
                executor=InlineExecutor(),
                id_factory=lambda: next(identifiers),
                now_factory=lambda: "2035-01-02T03:04:05Z",
            )
            validation = ValidationWorkbenchService(
                repository=repository,
                governance=governance,
                providers=(provider,),
            )
            with patch.object(
                LoopbackSimulatorIntentDraftProvider,
                "_post_json",
                new=post,
            ), patch.object(
                LoopbackSimulatorSemanticRecommendationProvider,
                "_post_json",
                new=post,
            ):
                created = validation.create_run(
                    dataset_ref=QINGLAN_DATASET_REF,
                    variant_ref=QINGLAN_VARIANT_REF,
                    scenario_ref="QL-C01",
                    model_mode="SIMULATOR_LIVE",
                    external_data_approved=False,
                )
                governance.review_intent(
                    created["case_ref"],
                    decision="CONFIRM",
                )
                governance.review_recommendation(
                    created["case_ref"],
                    decision="CONFIRM",
                    reviewer_reasoning=None,
                )
                comparison = validation.comparison(created["case_ref"])
                case = governance.case_view(created["case_ref"])

        self.assertEqual(case["status"], "COMPLETED")
        self.assertEqual(comparison["status"], "MATCH")
        self.assertFalse(case["record"]["semantic_approval"])
        self.assertFalse(case["record"]["gold_eligible"])
        self.assertFalse(case["record"]["patch_eligible"])


class QinglanTreeUnderstandingTests(unittest.TestCase):
    def test_profile_and_projection_cover_all_48_nodes(self) -> None:
        result = adapt_tree_document(build_qinglan_library_tree())
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.tree)
        tree = result.tree
        assert tree is not None

        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)

        self.assertEqual(profile.node_count, 48)
        self.assertEqual(projection.total_node_count, 48)
        self.assertEqual(projection.included_node_count, 48)
        self.assertEqual(projection.omitted_node_count, 0)
        self.assertTrue(projection.coverage_complete)
        self.assertNotIn(
            "ql-",
            json.dumps(projection.to_model_dict(), ensure_ascii=False),
        )

    def test_medium_profile_uses_bounded_projection(self) -> None:
        result = adapt_tree_document(
            build_qinglan_library_semantic_tree()
        )
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.tree)
        tree = result.tree
        assert tree is not None

        profile = build_tree_diagnostic_profile(tree)
        projection = build_tree_understanding_projection(tree, profile)

        self.assertEqual(profile.node_count, 312)
        self.assertEqual(projection.total_node_count, 312)
        self.assertEqual(projection.included_node_count, 64)
        self.assertEqual(projection.omitted_node_count, 248)
        self.assertFalse(projection.coverage_complete)
        self.assertNotIn(
            "qs-",
            json.dumps(projection.to_model_dict(), ensure_ascii=False),
        )

    def test_simulator_environment_registers_all_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "TREEGUARD_WORKBENCH_REPOSITORY_MODE": "SIMULATOR",
                "TREEGUARD_WORKBENCH_REPOSITORY_URL": (
                    "http://127.0.0.1:8765"
                ),
                "TREEGUARD_WORKBENCH_SIDECAR_DIR": directory,
            },
            clear=True,
        ):
            workbench, governance, validation = (
                _services_from_environment()
            )

        self.assertIsInstance(
            workbench.repository,
            FictionalQinglanRepositoryOverlay,
        )
        self.assertIs(governance.repository, workbench.repository)
        self.assertIs(validation.repository, workbench.repository)
        self.assertEqual(
            [item["dataset_ref"] for item in validation.catalog()["items"]],
            [
                FictionalFireValidationDataset().dataset_ref,
                QINGLAN_DATASET_REF,
                QINGLAN_SEMANTIC_DATASET_REF,
            ],
        )

    def test_internal_environment_does_not_register_qinglan(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "TREEGUARD_WORKBENCH_REPOSITORY_MODE": "INTERNAL",
                "TREEGUARD_WORKBENCH_REPOSITORY_URL": (
                    "http://10.20.30.40:8080"
                ),
                "TREEGUARD_WORKBENCH_SIDECAR_DIR": directory,
            },
            clear=True,
        ):
            workbench, governance, validation = (
                _services_from_environment()
            )

        self.assertNotIsInstance(
            workbench.repository,
            FictionalQinglanRepositoryOverlay,
        )
        self.assertIs(governance.repository, workbench.repository)
        self.assertIs(validation.repository, workbench.repository)
        self.assertEqual(
            [item["dataset_ref"] for item in validation.catalog()["items"]],
            [FictionalFireValidationDataset().dataset_ref],
        )


if __name__ == "__main__":
    unittest.main()
