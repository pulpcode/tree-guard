from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from treeguard.adapter import adapt_tree_document
from treeguard.ai_review import (
    LoopbackSimulatorIntentDraftProvider,
    LoopbackSimulatorSemanticRecommendationProvider,
)
from treeguard.fictional_fire_data import (
    FIRE_VALIDATION_RESOURCE_IDS,
    FIRE_VALIDATION_TIERS,
    TIER_SPECS,
    build_fictional_fire_tree,
    fire_validation_version,
)
from treeguard.fire_validation_dataset import (
    FictionalFireValidationDataset,
)
from treeguard.repository_client import CategoryRef, ResourceHead, VersionRef
from treeguard.simulator import (
    SIMULATOR_BEARER_TOKEN,
    SIMULATOR_CATEGORY_ID,
    SIMULATOR_HEAD_VERSION,
    SIMULATOR_RESOURCE_ID,
    ContractSimulator,
    build_fictional_tree,
)
from treeguard.web import create_app
from treeguard.workbench import WorkbenchService
from treeguard.workbench_governance import (
    DefaultProviderFactory,
    WorkbenchGovernanceService,
)
from treeguard.workbench_validation import (
    ValidationDatasetManifest,
    ValidationScenario,
    ValidationScenarioOracle,
    ValidationScenarioRequest,
    ValidationVariant,
    ValidationWorkbenchError,
    ValidationWorkbenchService,
)


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
class FireRepository:
    fetch_count: int = 0

    def list_categories(self) -> tuple[CategoryRef, ...]:
        return ()

    def list_resources(self, category_id: str) -> tuple[ResourceHead, ...]:
        return ()

    def list_versions(self, resource_id: str) -> tuple[VersionRef, ...]:
        return ()

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ):
        self.fetch_count += 1
        if (
            resource_id == SIMULATOR_RESOURCE_ID
            and version == SIMULATOR_HEAD_VERSION
        ):
            return adapt_tree_document(
                build_fictional_tree(
                    node_count=20,
                    version=SIMULATOR_HEAD_VERSION,
                )
            )
        tier = next(
            (
                item
                for item in FIRE_VALIDATION_TIERS
                if FIRE_VALIDATION_RESOURCE_IDS[item] == resource_id
            ),
            None,
        )
        if tier is None or version != fire_validation_version(tier):
            raise AssertionError("unexpected fictional repository selector")
        return adapt_tree_document(build_fictional_fire_tree(tier))


@dataclass
class GovernanceStub:
    create_calls: list[dict[str, Any]] = field(default_factory=list)
    case: dict[str, Any] = field(
        default_factory=lambda: {
            "status": "COMPLETED",
            "intent": {"review_status": "READY_FOR_HUMAN_REVIEW"},
            "candidates": {"status": "CANDIDATES_READY"},
            "record": {
                "status": "CONFIRMED",
                "semantic_approval": False,
                "gold_eligible": False,
                "patch_eligible": False,
            },
        }
    )

    def create_case(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(kwargs)
        return {
            "schema_version": "workbench-operation-view.v1",
            "operation_ref": "OP_fictional",
            "case_ref": "CASE_fictional",
            "kind": "DRAFT_INTENT",
            "status": "SUCCEEDED",
            "error_code": None,
            "case_status": "INTENT_REVIEW",
        }

    def case_view(self, case_ref: str) -> dict[str, Any]:
        if case_ref != "CASE_fictional":
            raise AssertionError("unexpected fictional case reference")
        return self.case


class FictionalMuseumValidationDataset:
    """Second domain proves the service depends on a provider contract."""

    @property
    def dataset_ref(self) -> str:
        return "fictional-museum-validation"

    def manifest(self) -> ValidationDatasetManifest:
        return ValidationDatasetManifest(
            dataset_ref=self.dataset_ref,
            title="完全虚构博物馆验证数据",
            limitations=("仅用于跨领域注册合同测试。",),
            variants=(
                ValidationVariant(
                    variant_ref="compact",
                    category_id=SIMULATOR_CATEGORY_ID,
                    resource_id=SIMULATOR_RESOURCE_ID,
                    version=SIMULATOR_HEAD_VERSION,
                    benchmark_role="cross_domain_contract",
                    node_count=20,
                    scenario_count=1,
                ),
            ),
        )

    def scenarios(
        self,
        variant_ref: str,
    ) -> tuple[ValidationScenario, ...]:
        if variant_ref != "compact":
            return ()
        return (
            ValidationScenario(
                scenario_ref="display-field",
                purpose="证明非消防数据集复用同一治理边界",
                flow="clear_intent",
                request=ValidationScenarioRequest(
                    requirement_text="记录完全虚构藏品的陈列说明。",
                    proposed_parent_node_id="fictional-museum-root",
                    node_kind_hint="PROPERTY",
                    value_type_hint="string",
                    cardinality_hint="SINGLE",
                ),
                oracle=ValidationScenarioOracle(
                    draft_status="READY_FOR_HUMAN_REVIEW",
                    clarification_status=None,
                    candidate_status="CANDIDATES_READY",
                    recommendation_status="CONFIRMED",
                ),
            ),
        )


class ValidationWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FireRepository()
        self.governance = GovernanceStub()
        self.service = ValidationWorkbenchService(
            repository=self.repository,
            governance=self.governance,
            providers=(FictionalFireValidationDataset(),),
        )

    def test_catalog_and_scenarios_are_allowlisted(self) -> None:
        catalog = self.service.catalog()
        dataset = catalog["items"][0]
        scenarios = self.service.scenarios(
            dataset["dataset_ref"],
            "small",
        )
        encoded = json.dumps(
            {"catalog": catalog, "scenarios": scenarios},
            ensure_ascii=False,
            sort_keys=True,
        )

        self.assertEqual(
            [item["variant_ref"] for item in dataset["variants"]],
            list(FIRE_VALIDATION_TIERS),
        )
        self.assertEqual(
            [item["node_count"] for item in dataset["variants"]],
            [TIER_SPECS[tier]["node_count"] for tier in FIRE_VALIDATION_TIERS],
        )
        self.assertEqual(len(scenarios["items"]), 8)
        self.assertRegex(
            scenarios["items"][0]["request"]["proposed_parent_ref"],
            r"^N[0-9]{6}$",
        )
        for forbidden in (
            "ffv-",
            "initial_model_output",
            "model_output",
            "required_first_candidate_id",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_second_domain_uses_registration_without_service_changes(
        self,
    ) -> None:
        service = ValidationWorkbenchService(
            repository=self.repository,
            governance=self.governance,
            providers=(
                FictionalFireValidationDataset(),
                FictionalMuseumValidationDataset(),
            ),
        )

        catalog = service.catalog()
        scenarios = service.scenarios(
            "fictional-museum-validation",
            "compact",
        )
        operation = service.create_run(
            dataset_ref="fictional-museum-validation",
            variant_ref="compact",
            scenario_ref="display-field",
            model_mode="SIMULATOR_LIVE",
            external_data_approved=False,
        )
        comparison = service.comparison(operation["case_ref"])

        self.assertEqual(
            [item["dataset_ref"] for item in catalog["items"]],
            [
                FictionalFireValidationDataset().dataset_ref,
                "fictional-museum-validation",
            ],
        )
        self.assertEqual(scenarios["variant_ref"], "compact")
        self.assertEqual(operation["case_ref"], "CASE_fictional")
        self.assertEqual(comparison["status"], "MATCH")
        self.assertEqual(
            comparison["dataset_ref"],
            "fictional-museum-validation",
        )
        self.assertEqual(
            self.governance.create_calls[-1]["resource_id"],
            SIMULATOR_RESOURCE_ID,
        )

    def test_run_uses_trusted_preset_and_comparison_is_non_gold(self) -> None:
        operation = self.service.create_run(
            dataset_ref=FictionalFireValidationDataset().dataset_ref,
            variant_ref="small",
            scenario_ref="clear-intent",
            model_mode="SIMULATOR_LIVE",
            external_data_approved=False,
        )
        comparison = self.service.comparison(operation["case_ref"])

        self.assertEqual(len(self.governance.create_calls), 1)
        call = self.governance.create_calls[0]
        self.assertEqual(
            call["resource_id"],
            FIRE_VALIDATION_RESOURCE_IDS["small"],
        )
        self.assertEqual(
            call["version"],
            fire_validation_version("small"),
        )
        self.assertRegex(call["proposed_parent_ref"], r"^N[0-9]{6}$")
        self.assertEqual(comparison["status"], "MATCH")
        self.assertFalse(comparison["gold_eligible"])
        self.assertTrue(
            all(item["status"] == "MATCH" for item in comparison["items"])
        )

    def test_bailian_approval_fails_before_repository_or_governance(self) -> None:
        with self.assertRaises(ValidationWorkbenchError) as caught:
            self.service.create_run(
                dataset_ref=FictionalFireValidationDataset().dataset_ref,
                variant_ref="small",
                scenario_ref="clear-intent",
                model_mode="BAILIAN_LIVE",
                external_data_approved=False,
            )

        self.assertEqual(
            caught.exception.code,
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertEqual(self.repository.fetch_count, 0)
        self.assertEqual(self.governance.create_calls, [])

    def test_approved_bailian_run_reuses_the_same_governance_boundary(
        self,
    ) -> None:
        self.service.create_run(
            dataset_ref=FictionalFireValidationDataset().dataset_ref,
            variant_ref="small",
            scenario_ref="clear-intent",
            model_mode="BAILIAN_LIVE",
            external_data_approved=True,
        )

        self.assertEqual(len(self.governance.create_calls), 1)
        self.assertEqual(
            self.governance.create_calls[0]["model_mode"],
            "BAILIAN_LIVE",
        )
        self.assertTrue(
            self.governance.create_calls[0]["external_data_approved"]
        )

    def test_comparison_distinguishes_pending_and_terminal_mismatch(
        self,
    ) -> None:
        operation = self.service.create_run(
            dataset_ref=FictionalFireValidationDataset().dataset_ref,
            variant_ref="small",
            scenario_ref="clear-intent",
            model_mode="SIMULATOR_LIVE",
            external_data_approved=False,
        )
        self.governance.case = {
            "status": "INTENT_REVIEW",
            "intent": {"review_status": "READY_FOR_HUMAN_REVIEW"},
            "candidates": None,
            "record": None,
        }

        pending = self.service.comparison(operation["case_ref"])

        self.assertEqual(pending["status"], "IN_PROGRESS")
        self.assertIn(
            "PENDING",
            {item["status"] for item in pending["items"]},
        )

        self.governance.case = {
            "status": "COMPLETED",
            "intent": {"review_status": "READY_FOR_HUMAN_REVIEW"},
            "candidates": {"status": "NO_CANDIDATES"},
            "record": {
                "status": "CONFIRMED",
                "semantic_approval": False,
                "gold_eligible": False,
                "patch_eligible": False,
            },
        }
        mismatch = self.service.comparison(operation["case_ref"])

        self.assertEqual(mismatch["status"], "MISMATCH")
        self.assertIn(
            "MISMATCH",
            {item["status"] for item in mismatch["items"]},
        )

    def test_unknown_variant_and_scenario_fail_with_fixed_codes(self) -> None:
        dataset_ref = FictionalFireValidationDataset().dataset_ref
        with self.assertRaises(ValidationWorkbenchError) as dataset_error:
            self.service.scenarios("unknown", "small")
        with self.assertRaises(ValidationWorkbenchError) as variant_error:
            self.service.scenarios(dataset_ref, "unknown")
        with self.assertRaises(ValidationWorkbenchError) as scenario_error:
            self.service.create_run(
                dataset_ref=dataset_ref,
                variant_ref="small",
                scenario_ref="unknown",
                model_mode="SIMULATOR_LIVE",
                external_data_approved=False,
            )

        self.assertEqual(
            dataset_error.exception.code,
            "VALIDATION_DATASET_NOT_FOUND",
        )
        self.assertEqual(
            variant_error.exception.code,
            "VALIDATION_VARIANT_NOT_FOUND",
        )
        self.assertEqual(
            scenario_error.exception.code,
            "VALIDATION_SCENARIO_NOT_FOUND",
        )


class ValidationAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_run_and_comparison_use_fixed_views(self) -> None:
        repository = FireRepository()
        governance = GovernanceStub()
        validation = ValidationWorkbenchService(
            repository,
            governance,
            (FictionalFireValidationDataset(),),
        )
        app = create_app(
            WorkbenchService(repository),
            governance,
            validation,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            catalog = await client.get("/api/v1/validation/datasets")
            scenarios = await client.get(
                "/api/v1/validation/datasets/"
                f"{FictionalFireValidationDataset().dataset_ref}/scenarios",
                params={"variant_ref": "small"},
            )
            denied = await client.post(
                "/api/v1/validation/runs",
                json={
                    "dataset_ref": (
                        FictionalFireValidationDataset().dataset_ref
                    ),
                    "variant_ref": "small",
                    "scenario_ref": "clear-intent",
                    "model_mode": "BAILIAN_LIVE",
                    "external_data_approved": False,
                },
            )
            created = await client.post(
                "/api/v1/validation/runs",
                json={
                    "dataset_ref": (
                        FictionalFireValidationDataset().dataset_ref
                    ),
                    "variant_ref": "small",
                    "scenario_ref": "clear-intent",
                    "model_mode": "SIMULATOR_LIVE",
                    "external_data_approved": False,
                },
            )
            comparison = await client.get(
                "/api/v1/validation/runs/CASE_fictional/comparison"
            )

        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(scenarios.status_code, 200)
        self.assertEqual(denied.status_code, 422)
        self.assertEqual(
            denied.json()["error_code"],
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
        )
        self.assertEqual(created.status_code, 202)
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(comparison.json()["status"], "MATCH")
        for response in (catalog, scenarios, denied, created, comparison):
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(
                response.headers["x-content-type-options"],
                "nosniff",
            )


class ValidationGovernanceIntegrationTests(unittest.TestCase):
    def test_small_scenario_runs_through_real_governance_services(self) -> None:
        repository = FireRepository()
        simulator = ContractSimulator()
        post = _pure_model_post(simulator)
        identifiers = iter(("case", "draft", "intent", "recommendation"))
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
                repository,
                governance,
                (FictionalFireValidationDataset(),),
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
                    dataset_ref=(
                        FictionalFireValidationDataset().dataset_ref
                    ),
                    variant_ref="small",
                    scenario_ref="clear-intent",
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


if __name__ == "__main__":
    unittest.main()
