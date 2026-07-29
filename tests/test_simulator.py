import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from treeguard.adapter import adapt_tree_document
from treeguard.ai_review import (
    BailianProviderError,
    LoopbackSimulatorConfig,
    LoopbackSimulatorIntentDraftProvider,
    LoopbackSimulatorSemanticRecommendationProvider,
)
from treeguard.demo_cli import main as demo_main
from treeguard.json_utils import strict_json_loads
from treeguard.repository_client import (
    ProvisionalRepositoryClient,
    RepositoryClientConfig,
    RepositoryClientError,
)
from treeguard.simulator import (
    SIMULATOR_BEARER_TOKEN,
    SIMULATOR_CATEGORY_ID,
    SIMULATOR_RESOURCE_ID,
    ContractSimulator,
    build_fictional_tree,
)
from treeguard.simulator_cli import main as simulator_main


class _MemoryResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class _RouterOpener:
    def __init__(self, simulator: ContractSimulator) -> None:
        self.simulator = simulator

    def open(self, request, timeout: float):
        target = request.full_url.split("127.0.0.1:8765", 1)[1]
        response = self.simulator.handle(
            method=request.get_method(),
            target=target,
            headers=dict(request.header_items()),
            body=request.data or b"",
        )
        if response.status_code >= 400:
            raise AssertionError(
                f"unexpected simulator status {response.status_code}"
            )
        return _MemoryResponse(response.body)


class _StaticOpener:
    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def open(self, request, timeout: float):
        return _MemoryResponse(self.body)


def _repository_client(
    *,
    node_count: int,
) -> ProvisionalRepositoryClient:
    client = ProvisionalRepositoryClient(
        RepositoryClientConfig(base_url="http://127.0.0.1:8765")
    )
    client._opener = _RouterOpener(
        ContractSimulator(node_count=node_count)
    )
    return client


def _pure_model_post(
    simulator: ContractSimulator,
):
    def post(provider, body):
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
        return strict_json_loads(response.body)

    return post


def _chat_body(schema_version: str) -> bytes:
    return json.dumps(
        {
            "model": "treeguard-simulator-model",
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "output_contract": {
                                "schema_version": schema_version
                            }
                        }
                    ),
                }
            ],
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "temperature": 0,
            "stream": False,
        }
    ).encode("utf-8")


class FictionalTreeTests(unittest.TestCase):
    def test_large_tree_is_deterministic_and_adaptable(self) -> None:
        first = build_fictional_tree(node_count=2_005, version="SIM-V2")
        second = build_fictional_tree(node_count=2_005, version="SIM-V2")

        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )
        result = adapt_tree_document(first)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.observed_node_count, 2_005)
        self.assertIsNotNone(result.tree)

    def test_versions_keep_node_identity_but_change_snapshot(self) -> None:
        old = adapt_tree_document(
            build_fictional_tree(node_count=20, version="SIM-V1")
        )
        new = adapt_tree_document(
            build_fictional_tree(node_count=20, version="SIM-V2")
        )
        self.assertIsNotNone(old.tree)
        self.assertIsNotNone(new.tree)
        old_nodes = {node.node_id: node for node in old.tree.nodes}
        new_nodes = {node.node_id: node for node in new.tree.nodes}

        self.assertEqual(set(old_nodes), set(new_nodes))
        self.assertEqual(old_nodes["fictional-height"].name, "展品高度")
        self.assertEqual(new_nodes["fictional-height"].name, "陈列高度")
        self.assertNotEqual(old.tree.snapshot_hash, new.tree.snapshot_hash)


class PureSimulatorTests(unittest.TestCase):
    def test_auth_and_query_fail_closed(self) -> None:
        simulator = ContractSimulator()
        unauthorized = simulator.handle(
            method="GET",
            target="/provisional/v1/categories",
            headers={},
        )
        malformed_query = simulator.handle(
            method="GET",
            target="/provisional/v1/categories?unexpected=true",
            headers={
                "Authorization": f"Bearer {SIMULATOR_BEARER_TOKEN}"
            },
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(malformed_query.status_code, 400)
        self.assertNotIn(b"unexpected=true", malformed_query.body)

    def test_model_fault_scenarios_are_explicit(self) -> None:
        headers = {
            "Authorization": f"Bearer {SIMULATOR_BEARER_TOKEN}",
            "Content-Type": "application/json",
        }
        request = _chat_body("change-intent-model-output.v1")

        invalid = ContractSimulator(
            model_scenario="invalid-json"
        ).handle(
            method="POST",
            target="/v1/chat/completions",
            headers=headers,
            body=request,
        )
        limited = ContractSimulator(model_scenario="http-429").handle(
            method="POST",
            target="/v1/chat/completions",
            headers=headers,
            body=request,
        )
        delayed = ContractSimulator(
            model_scenario="timeout",
            delay_seconds=1.0,
        ).handle(
            method="POST",
            target="/v1/chat/completions",
            headers=headers,
            body=request,
        )

        self.assertEqual(invalid.body, b"{")
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(delayed.delay_seconds, 1.0)
        self.assertLess(
            LoopbackSimulatorConfig(
                api_key=SIMULATOR_BEARER_TOKEN,
                base_url="http://127.0.0.1:8765/v1",
            ).timeout_seconds,
            delayed.delay_seconds,
        )

    def test_clarification_extra_field_and_server_error_are_distinct(self) -> None:
        headers = {
            "Authorization": f"Bearer {SIMULATOR_BEARER_TOKEN}",
            "Content-Type": "application/json",
        }
        request = _chat_body("change-intent-model-output.v1")

        clarification = ContractSimulator(
            model_scenario="clarification"
        ).handle(
            method="POST",
            target="/v1/chat/completions",
            headers=headers,
            body=request,
        )
        extra = ContractSimulator(model_scenario="extra-field").handle(
            method="POST",
            target="/v1/chat/completions",
            headers=headers,
            body=request,
        )
        failed = ContractSimulator(model_scenario="http-500").handle(
            method="POST",
            target="/v1/chat/completions",
            headers=headers,
            body=request,
        )
        clarification_output = json.loads(
            json.loads(clarification.body)["choices"][0]["message"]["content"]
        )
        extra_output = json.loads(
            json.loads(extra.body)["choices"][0]["message"]["content"]
        )

        self.assertIsNotNone(
            clarification_output["clarification_question"]
        )
        self.assertTrue(extra_output["unexpected"])
        self.assertEqual(failed.status_code, 500)

    def test_repository_routes_are_byte_stable(self) -> None:
        simulator = ContractSimulator(node_count=20)
        arguments = {
            "method": "GET",
            "target": "/provisional/v1/categories",
            "headers": {
                "Authorization": f"Bearer {SIMULATOR_BEARER_TOKEN}"
            },
        }

        self.assertEqual(
            simulator.handle(**arguments).body,
            simulator.handle(**arguments).body,
        )


class SimulatorHTTPIntegrationTests(unittest.TestCase):
    def test_four_repository_operations_validate_large_snapshots(self) -> None:
        client = _repository_client(node_count=2_001)
        categories = client.list_categories()
        resources = client.list_resources(SIMULATOR_CATEGORY_ID)
        versions = client.list_versions(SIMULATOR_RESOURCE_ID)
        old = client.fetch_tree(
            SIMULATOR_RESOURCE_ID,
            version=versions[0].version,
        )
        head = client.fetch_tree(
            SIMULATOR_RESOURCE_ID,
            version_record_id=versions[1].version_record_id,
        )

        self.assertEqual(len(categories), 2)
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(versions), 2)
        self.assertEqual(old.observed_node_count, 2_001)
        self.assertEqual(head.observed_node_count, 2_001)

    def test_repository_verification_cli_reports_only_aggregates(self) -> None:
        client = _repository_client(node_count=25)
        with patch(
            "treeguard.simulator_cli.ProvisionalRepositoryClient",
            return_value=client,
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = simulator_main(
                    [
                        "verify-repository",
                        "--base-url",
                        "http://127.0.0.1:8765",
                    ]
                )

        report = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "VERIFIED")
        self.assertEqual(report["snapshot_count"], 2)
        self.assertEqual(report["node_count"], 50)
        self.assertNotIn("items", report)

    def test_unsupported_method_returns_json_error(self) -> None:
        response = ContractSimulator().handle(
            method="PUT",
            target="/provisional/v1/categories",
            headers={
                "Authorization": f"Bearer {SIMULATOR_BEARER_TOKEN}"
            },
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            payload["error_code"],
            "SIMULATOR_METHOD_NOT_ALLOWED",
        )

    def test_simulator_mode_runs_the_full_governance_demo(self) -> None:
        simulator = ContractSimulator()
        post = _pure_model_post(simulator)
        with patch.object(
            LoopbackSimulatorIntentDraftProvider,
            "_post_json",
            new=post,
        ), patch.object(
            LoopbackSimulatorSemanticRecommendationProvider,
            "_post_json",
            new=post,
        ):
            with tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory) / "simulator-demo"
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = demo_main(
                        [
                            "--output-dir",
                            str(output_dir),
                            "--review-decision",
                            "confirm",
                            "--mode",
                            "simulator-live",
                            "--simulator-base-url",
                            "http://127.0.0.1:8765/v1",
                        ]
                    )
                report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["completed"])
        self.assertEqual(report["mode"], "SIMULATOR_LIVE")
        self.assertTrue(report["ai"]["intent_called"])
        self.assertTrue(report["ai"]["semantic_called"])
        self.assertFalse(report["patch_eligible"])
        self.assertFalse(report["gold_eligible"])


class SimulatorClientBoundaryTests(unittest.TestCase):
    def test_model_and_repository_clients_reject_non_loopback_urls(self) -> None:
        with self.assertRaises(BailianProviderError) as model_error:
            LoopbackSimulatorConfig(
                api_key=SIMULATOR_BEARER_TOKEN,
                base_url="https://example.invalid/v1",
            )
        with self.assertRaises(RepositoryClientError) as repository_error:
            RepositoryClientConfig(
                base_url="http://example.invalid:8765"
            )

        self.assertEqual(
            model_error.exception.code,
            "SIMULATOR_MODEL_BASE_URL_INVALID",
        )
        self.assertEqual(
            repository_error.exception.code,
            "REPOSITORY_SIMULATOR_BASE_URL_INVALID",
        )

    def test_repository_token_rejects_header_controls(self) -> None:
        with self.assertRaises(RepositoryClientError) as caught:
            RepositoryClientConfig(
                base_url="http://127.0.0.1:8765",
                token="fictional-token\nInjected: value",
            )

        self.assertEqual(
            caught.exception.code,
            "REPOSITORY_SIMULATOR_TOKEN_INVALID",
        )

    def test_repository_client_rejects_unknown_envelope_fields(self) -> None:
        response = ContractSimulator().handle(
            method="GET",
            target="/provisional/v1/categories",
            headers={
                "Authorization": f"Bearer {SIMULATOR_BEARER_TOKEN}"
            },
        )
        payload = json.loads(response.body)
        payload["data"]["unexpected"] = True
        client = _repository_client(node_count=20)
        client._opener = _StaticOpener(payload)

        with self.assertRaises(RepositoryClientError) as caught:
            client.list_categories()

        self.assertEqual(
            caught.exception.code,
            "REPOSITORY_CATEGORY_ENVELOPE_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
