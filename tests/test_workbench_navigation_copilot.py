from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from treeguard import load_tree_export
from treeguard.ai_review import BailianProviderError
from treeguard.change_understanding_v2 import ChangeUnderstandingV2
from treeguard.navigation_copilot import (
    NavigationSemanticDraft,
)
from treeguard.navigation_shadow_run import NavigationShadowRunManifest
from treeguard.private_io import read_private_json, write_private_json
from treeguard.web import create_app
from treeguard.workbench import WorkbenchService, build_tree_reference_index
from treeguard.workbench_navigation_copilot import (
    WorkbenchNavigationCopilotService,
    navigation_copilot_enabled_from_env,
    shadow_run_binding_from_env,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"


class FakeRepository:
    def __init__(self):
        self.result = load_tree_export(FIXTURE)
        self.fetch_count = 0

    def fetch_tree(self, resource_id, *, version):
        self.fetch_count += 1
        return self.result


class InlineExecutor:
    def submit(self, function):
        function()
        return None


class FakeUnderstandingProvider:
    def __init__(self, *, clarification=False, fail=False, always_clarifies=False):
        self.clarification = clarification
        self.fail = fail
        self.always_clarifies = always_clarifies
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
            raise BailianProviderError(
                "QWEN_CONNECTION_FAILED", "fictional failure"
            )
        question = (
            "Should Tags allow multiple values?"
            if self.clarification
            and (clarification_question is None or self.always_clarifies)
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
            model_provider="FAKE",
            model_capability="JSON_OBJECT",
            model_name="fixture-model",
            prompt_version="fixture-understanding.v1",
        )


class FakeSemanticProvider:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = 0

    def compare(self, projection, tree):
        self.calls += 1
        if self.fail:
            raise BailianProviderError(
                "QWEN_CONNECTION_FAILED", "fictional failure"
            )
        return NavigationSemanticDraft.from_model_dict(
            {
                "schema_version": "navigation-copilot-semantic-output.v1",
                "candidate_assessments": [
                    {
                        "candidate_ref": item.candidate_ref,
                        "relation": (
                            "SEMANTICALLY_EQUIVALENT"
                            if item.candidate_ref == "C001"
                            else "NOT_EQUIVALENT"
                        ),
                        "reason": "Compared within a fictional projection.",
                    }
                    for item in projection.candidates
                ],
            },
            projection,
            tree,
            model_provider="FAKE",
            model_name="fixture-model",
            prompt_version="fixture-semantic.v1",
        )


class FakeFactory:
    def __init__(self, understanding=None, semantic=None):
        self.understanding = understanding or FakeUnderstandingProvider()
        self.semantic = semantic or FakeSemanticProvider()

    def understanding_provider(self, mode, trace_sink=None):
        return self.understanding

    def semantic_provider(self, mode, trace_sink=None):
        return self.semantic


def _id_factory():
    values = iter(("001", "002", "003", "004", "005", "006"))
    return lambda: next(values)


def _create(service):
    return service.create_case(
        resource_id="fictional-resource",
        version="V1",
        requirement_text="Find Tags under Catalog.",
        proposed_parent_ref="N000002",
        node_kind_hint="PROPERTY",
        value_type_hint="string",
        cardinality_hint="MULTIPLE",
        model_mode="QWEN_LIVE",
        external_data_approved=False,
    )


class WorkbenchNavigationCopilotTests(unittest.TestCase):
    def test_frozen_shadow_run_requires_disposition_and_publishes_qualification(self):
        manifest = NavigationShadowRunManifest.create(
            run_ref="SR0001",
            contract_commit="0" * 40,
            provider_mode="QWEN_LIVE",
            participant_refs=("P01", "P02", "P03"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            service = WorkbenchNavigationCopilotService(
                repository=FakeRepository(),
                sidecar_root=root,
                provider_factory=FakeFactory(),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
                shadow_run_manifest=manifest,
                participant_ref="P01",
            )
            operation = _create(service)
            case_ref = operation["case_ref"]
            with self.assertRaisesRegex(RuntimeError, "qualification") as caught:
                service.complete(
                    case_ref,
                    action="REJECT_ALL",
                    selected_candidate_ref=None,
                    selected_node_ref=None,
                )
            self.assertEqual(
                caught.exception.code,
                "SHADOW_TARGET_DISPOSITION_REQUIRED",
            )
            self.assertFalse((root / case_ref / "09-outcome.json").exists())

            completed = service.complete(
                case_ref,
                action="REJECT_ALL",
                selected_candidate_ref=None,
                selected_node_ref=None,
                rejection_disposition="ABSENT",
            )
            self.assertEqual(completed["status"], "COMPLETED")
            qualification_path = root / case_ref / "10-shadow-qualification.json"
            qualification = read_private_json(
                qualification_path,
                max_bytes=64 * 1024,
            )
            self.assertEqual(qualification["participant_ref"], "P01")
            self.assertEqual(qualification["target_disposition"], "ABSENT")
            self.assertEqual(stat.S_IMODE(qualification_path.stat().st_mode), 0o600)

    def test_shadow_run_environment_binding_is_private_and_commit_bound(self):
        manifest = NavigationShadowRunManifest.create(
            run_ref="SR0001",
            contract_commit="0" * 40,
            provider_mode="QWEN_LIVE",
            participant_refs=("P01", "P02", "P03"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.json"
            self.assertTrue(write_private_json(path, manifest.to_dict()))
            environment = {
                "TREEGUARD_WORKBENCH_NAVIGATION_COPILOT_RUN_MANIFEST": str(path),
                "TREEGUARD_WORKBENCH_NAVIGATION_COPILOT_PARTICIPANT_REF": "P02",
                "TREEGUARD_WORKBENCH_BUILD_COMMIT": "0" * 40,
            }
            with patch.dict(os.environ, environment, clear=True):
                loaded, participant = shadow_run_binding_from_env()
            self.assertEqual(loaded, manifest)
            self.assertEqual(participant, "P02")
            environment["TREEGUARD_WORKBENCH_BUILD_COMMIT"] = "1" * 40
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RuntimeError, "build") as caught:
                    shadow_run_binding_from_env()
            self.assertEqual(caught.exception.code, "COPILOT_SHADOW_BUILD_MISMATCH")

    def test_bailian_approval_fails_before_tree_read_or_sidecar(self):
        repository = FakeRepository()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            service = WorkbenchNavigationCopilotService(
                repository=repository,
                sidecar_root=root,
                provider_factory=FakeFactory(),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            with self.assertRaisesRegex(RuntimeError, "explicit approval"):
                service.create_case(
                    resource_id="fictional-resource",
                    version="V1",
                    requirement_text="Find Tags.",
                    proposed_parent_ref=None,
                    node_kind_hint="UNKNOWN",
                    value_type_hint=None,
                    cardinality_hint="UNKNOWN",
                    model_mode="BAILIAN_LIVE",
                    external_data_approved=False,
                )

            self.assertEqual(repository.fetch_count, 0)
            self.assertFalse(root.exists())

    def test_clear_path_uses_two_calls_and_completes_with_navigation_ref(self):
        factory = FakeFactory()
        ticks = iter((1_000, 2_000))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sidecars"
            service = WorkbenchNavigationCopilotService(
                repository=FakeRepository(),
                sidecar_root=root,
                provider_factory=factory,
                executor=InlineExecutor(),
                id_factory=_id_factory(),
                clock_ms=lambda: next(ticks),
            )
            operation = _create(service)
            self.assertEqual(operation["status"], "SUCCEEDED")
            case_ref = operation["case_ref"]
            view = service.case_view(case_ref)
            self.assertEqual(view["status"], "AWAITING_OUTCOME")
            self.assertEqual(view["model_call_count"], 2)
            self.assertEqual(view["candidate_status"], "CANDIDATES_AVAILABLE")

            completed = service.complete(
                case_ref,
                action="SELECT_CANDIDATE",
                selected_candidate_ref="C001",
                selected_node_ref=view["candidates"][0]["node_ref"],
            )

            self.assertEqual(completed["status"], "COMPLETED")
            self.assertEqual(
                completed["navigation_target_ref"],
                view["candidates"][0]["node_ref"],
            )
            self.assertFalse(completed["outcome"]["gold_eligible"])
            self.assertEqual(service.aggregate_view()["case_count"], 1)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            for path in (root / case_ref).iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaisesRegex(RuntimeError, "not waiting"):
                service.complete(
                    case_ref,
                    action="SELECT_CANDIDATE",
                    selected_candidate_ref="C001",
                    selected_node_ref=view["candidates"][0]["node_ref"],
                )

    def test_clarification_path_uses_second_call_and_skips_semantic(self):
        understanding = FakeUnderstandingProvider(clarification=True)
        semantic = FakeSemanticProvider()
        factory = FakeFactory(understanding, semantic)
        with tempfile.TemporaryDirectory() as temporary:
            service = WorkbenchNavigationCopilotService(
                repository=FakeRepository(),
                sidecar_root=Path(temporary) / "sidecars",
                provider_factory=factory,
                executor=InlineExecutor(),
                id_factory=_id_factory(),
                recorded_at_factory=lambda: "2030-01-02T03:04:05Z",
            )
            operation = _create(service)
            case_ref = operation["case_ref"]
            self.assertEqual(
                service.case_view(case_ref)["status"],
                "NEEDS_CLARIFICATION",
            )

            clarified = service.clarify(
                case_ref, answer_text="Use multiple values."
            )
            view = service.case_view(case_ref)

            self.assertEqual(clarified["status"], "SUCCEEDED")
            self.assertEqual(view["status"], "AWAITING_OUTCOME")
            self.assertEqual(view["model_call_count"], 2)
            self.assertEqual(view["candidate_status"], "NEED_EVIDENCE")
            self.assertEqual(understanding.calls, 2)
            self.assertEqual(semantic.calls, 0)
            self.assertIsNone(view["highlighted_candidate_ref"])

    def test_unresolved_second_understanding_stops_and_rejects_more_turns(self):
        understanding = FakeUnderstandingProvider(
            clarification=True, always_clarifies=True
        )
        semantic = FakeSemanticProvider()
        with tempfile.TemporaryDirectory() as temporary:
            service = WorkbenchNavigationCopilotService(
                repository=FakeRepository(),
                sidecar_root=Path(temporary) / "sidecars",
                provider_factory=FakeFactory(understanding, semantic),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            case_ref = _create(service)["case_ref"]
            service.clarify(case_ref, answer_text="Still uncertain.")

            self.assertEqual(
                service.case_view(case_ref)["status"],
                "CLARIFICATION_LIMIT_REACHED",
            )
            self.assertEqual(understanding.calls, 2)
            self.assertEqual(semantic.calls, 0)
            with self.assertRaisesRegex(RuntimeError, "not waiting"):
                service.clarify(case_ref, answer_text="Third attempt.")

    def test_model_failures_degrade_without_losing_candidates(self):
        cases = (
            (FakeUnderstandingProvider(fail=True), FakeSemanticProvider()),
            (FakeUnderstandingProvider(), FakeSemanticProvider(fail=True)),
        )
        for understanding, semantic in cases:
            with self.subTest(
                understanding_failure=understanding.fail,
                semantic_failure=semantic.fail,
            ):
                with tempfile.TemporaryDirectory() as temporary:
                    service = WorkbenchNavigationCopilotService(
                        repository=FakeRepository(),
                        sidecar_root=Path(temporary) / "sidecars",
                        provider_factory=FakeFactory(understanding, semantic),
                        executor=InlineExecutor(),
                        id_factory=_id_factory(),
                    )
                    operation = _create(service)
                    view = service.case_view(operation["case_ref"])

                    self.assertEqual(view["status"], "AWAITING_OUTCOME")
                    self.assertTrue(view["candidates"])
                    self.assertIn(
                        "QWEN_CONNECTION_FAILED",
                        view["degradation_codes"],
                    )
                    if semantic.fail:
                        self.assertEqual(
                            view["candidate_status"], "NEED_EVIDENCE"
                        )
                        self.assertIsNone(view["highlighted_candidate_ref"])

    def test_outside_correction_is_not_counted_as_direct_hit(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = FakeRepository()
            service = WorkbenchNavigationCopilotService(
                repository=repository,
                sidecar_root=Path(temporary) / "sidecars",
                provider_factory=FakeFactory(),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            operation = _create(service)
            case_ref = operation["case_ref"]
            view = service.case_view(case_ref)
            candidate_refs = {item["node_ref"] for item in view["candidates"]}
            tree = repository.result.tree
            assert tree is not None
            references = build_tree_reference_index(tree)
            outside_ref = next(
                reference
                for reference in references.node_id_by_ref
                if reference not in candidate_refs
            )

            completed = service.complete(
                case_ref,
                action="SELECT_OUTSIDE_CANDIDATE",
                selected_candidate_ref=None,
                selected_node_ref=outside_ref,
            )

            self.assertTrue(completed["outcome"]["candidate_miss"])
            self.assertTrue(completed["outcome"]["user_corrected"])
            aggregate = service.aggregate_view()
            self.assertEqual(aggregate["top8_direct_selection_count"], 0)
            self.assertEqual(aggregate["candidate_correction_count"], 1)

    def test_feature_flag_defaults_off_and_rejects_unknown_values(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(navigation_copilot_enabled_from_env())
        with patch.dict(
            os.environ,
            {"TREEGUARD_WORKBENCH_NAVIGATION_COPILOT": "1"},
            clear=True,
        ):
            self.assertTrue(navigation_copilot_enabled_from_env())
        with patch.dict(
            os.environ,
            {"TREEGUARD_WORKBENCH_NAVIGATION_COPILOT": "yes"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "zero or one"):
                navigation_copilot_enabled_from_env()


class WorkbenchNavigationCopilotAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_capability_defaults_off_and_enabled_flow_is_bounded(self):
        repository = FakeRepository()
        off_app = create_app(WorkbenchService(repository))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=off_app),
            base_url="http://test",
        ) as client:
            capability = await client.get(
                "/api/v1/navigation-copilot/capability"
            )
        self.assertEqual(capability.status_code, 200)
        self.assertFalse(capability.json()["enabled"])

        with tempfile.TemporaryDirectory() as temporary:
            copilot = WorkbenchNavigationCopilotService(
                repository=repository,
                sidecar_root=Path(temporary) / "sidecars",
                provider_factory=FakeFactory(),
                executor=InlineExecutor(),
                id_factory=_id_factory(),
            )
            app = create_app(
                WorkbenchService(repository),
                navigation_copilot_service=copilot,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                capability = await client.get(
                    "/api/v1/navigation-copilot/capability"
                )
                created = await client.post(
                    "/api/v1/navigation-copilot/cases",
                    json={
                        "resource_id": "fictional-resource",
                        "version": "V1",
                        "requirement_text": "Find Tags under Catalog.",
                        "proposed_parent_ref": "N000002",
                        "node_kind_hint": "PROPERTY",
                        "value_type_hint": "string",
                        "cardinality_hint": "MULTIPLE",
                        "model_mode": "QWEN_LIVE",
                        "external_data_approved": False,
                    },
                )
                operation = created.json()
                case = await client.get(
                    f"/api/v1/navigation-copilot/cases/{operation['case_ref']}"
                )

        self.assertTrue(capability.json()["enabled"])
        self.assertEqual(created.status_code, 202)
        self.assertEqual(case.status_code, 200)
        self.assertLessEqual(len(case.json()["candidates"]), 8)
        self.assertLessEqual(case.json()["model_call_count"], 2)
        self.assertNotIn("node_id", case.text)
        self.assertNotIn("source_snapshot_hash", case.text)


if __name__ == "__main__":
    unittest.main()
