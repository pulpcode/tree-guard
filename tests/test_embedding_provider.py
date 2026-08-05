from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from treeguard.adapter import load_tree_export
from treeguard.ai_review import BailianConfig
from treeguard.embedding_provider import (
    BailianHybridEmbeddingProvider,
    EmbeddingProviderError,
    build_hybrid_index_with_provider,
    embed_hybrid_documents,
)
from treeguard.retrieval_hybrid import (
    EMBEDDING_DIMENSIONS,
    MODEL_ID,
    build_hybrid_node_documents,
)


ROOT = Path(__file__).resolve().parents[1]
TREE_FIXTURE = ROOT / "tests/fixtures/fictional/fire_m5_assisted_shadow/tree.json"


def _unit(axis: int) -> list[float]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    values[axis] = 1.0
    return values


def _response(count: int) -> dict[str, Any]:
    return {
        "data": [
            {"embedding": _unit(index % 2), "index": index, "object": "embedding"}
            for index in range(count)
        ],
        "id": "fictional-response",
        "model": MODEL_ID,
        "object": "list",
        "usage": {"prompt_tokens": count, "total_tokens": count},
    }


class RecordingEmbeddingProvider(BailianHybridEmbeddingProvider):
    def __init__(self, responses: list[Any]) -> None:
        super().__init__(BailianConfig(api_key="fictional-key", model=MODEL_ID))
        self.responses = responses
        self.bodies: list[dict[str, Any]] = []

    def _post_json(self, body: dict[str, Any]) -> Any:
        self.bodies.append(copy.deepcopy(body))
        return self.responses.pop(0)


class FakeLocalCompatibleProvider:
    model_id = MODEL_ID
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def embed_batch(
        self,
        texts: tuple[str, ...],
        *,
        external_data_approved: bool = False,
    ) -> tuple[tuple[float, ...], ...]:
        self.batch_sizes.append(len(texts))
        return tuple(tuple(_unit(0)) for _ in texts)


class WrongProfileProvider(FakeLocalCompatibleProvider):
    model_id = "local-model"


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self, maximum: int) -> bytes:
        return self.raw[:maximum]


class CapturingOpener:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[Any, float]] = []

    def open(self, request: Any, *, timeout: float):
        self.calls.append((request, timeout))
        return FakeHTTPResponse(self.payload)


class EmbeddingProviderTests(unittest.TestCase):
    def test_bailian_request_is_fixed_and_response_order_is_preserved(self) -> None:
        provider = RecordingEmbeddingProvider([_response(2)])

        result = provider.embed_batch(
            ("节点文档一", "节点文档二"),
            external_data_approved=True,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], 1.0)
        self.assertEqual(result[1][1], 1.0)
        self.assertEqual(
            provider.bodies,
            [
                {
                    "model": MODEL_ID,
                    "input": ["节点文档一", "节点文档二"],
                    "dimensions": EMBEDDING_DIMENSIONS,
                    "encoding_format": "float",
                }
            ],
        )

    def test_http_transport_uses_exact_endpoint_header_and_one_wire_call(self) -> None:
        provider = BailianHybridEmbeddingProvider(
            BailianConfig(api_key="fictional-key", model=MODEL_ID, timeout_seconds=12)
        )
        opener = CapturingOpener(_response(1))
        provider._opener = opener

        provider.embed_batch(("虚构文本",), external_data_approved=True)

        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(provider.wire_attempt_count, 1)
        request, timeout = opener.calls[0]
        self.assertEqual(
            request.full_url,
            "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer fictional-key")
        self.assertEqual(timeout, 12.0)
        self.assertEqual(
            json.loads(request.data),
            {
                "model": MODEL_ID,
                "input": ["虚构文本"],
                "dimensions": EMBEDDING_DIMENSIONS,
                "encoding_format": "float",
            },
        )

    def test_approval_and_input_fail_before_transport(self) -> None:
        provider = RecordingEmbeddingProvider([_response(1)])
        with self.assertRaises(EmbeddingProviderError) as caught:
            provider.embed_batch(("虚构文本",))
        self.assertEqual(caught.exception.code, "EXTERNAL_DATA_APPROVAL_REQUIRED")
        self.assertEqual(provider.bodies, [])
        self.assertEqual(provider.wire_attempt_count, 0)

        invalid_batches = ((), tuple("x" for _ in range(11)), ("",), ("x\x00y",))
        for batch in invalid_batches:
            with self.subTest(size=len(batch)):
                with self.assertRaises(EmbeddingProviderError) as caught:
                    provider.embed_batch(batch, external_data_approved=True)
                self.assertEqual(caught.exception.code, "BAILIAN_EMBEDDING_INPUT_INVALID")
        self.assertEqual(provider.bodies, [])

    def test_response_contract_rejects_shape_order_and_vector_failures(self) -> None:
        cases = []
        extra = _response(1)
        extra["unexpected"] = True
        cases.append(extra)
        wrong_model = _response(1)
        wrong_model["model"] = "other-model"
        cases.append(wrong_model)
        wrong_index = _response(1)
        wrong_index["data"][0]["index"] = 1
        cases.append(wrong_index)
        wrong_dimension = _response(1)
        wrong_dimension["data"][0]["embedding"] = [1.0]
        cases.append(wrong_dimension)
        bool_usage = _response(1)
        bool_usage["usage"]["prompt_tokens"] = True
        cases.append(bool_usage)

        for payload in cases:
            with self.subTest(keys=sorted(payload)):
                provider = RecordingEmbeddingProvider([payload])
                with self.assertRaises(EmbeddingProviderError) as caught:
                    provider.embed_batch(("虚构文本",), external_data_approved=True)
                self.assertEqual(caught.exception.code, "BAILIAN_EMBEDDING_RESPONSE_INVALID")
                self.assertEqual(len(provider.bodies), 1)
                self.assertNotIn("虚构文本", str(caught.exception))
                self.assertNotIn("fictional-response", str(caught.exception))

    def test_document_embedding_uses_stable_batches_of_ten(self) -> None:
        imported = load_tree_export(TREE_FIXTURE)
        assert imported.tree is not None
        documents = build_hybrid_node_documents(imported.tree)[:21]
        provider = FakeLocalCompatibleProvider()

        vectors = embed_hybrid_documents(
            provider,
            documents,
            external_data_approved=True,
        )

        self.assertEqual(provider.batch_sizes, [10, 10, 1])
        self.assertEqual(len(vectors), 21)
        self.assertTrue(all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors))

    def test_provider_builds_an_index_bound_to_the_tree(self) -> None:
        imported = load_tree_export(ROOT / "tests/fixtures/fictional/tree_export.json")
        assert imported.tree is not None
        provider = FakeLocalCompatibleProvider()

        index = build_hybrid_index_with_provider(
            provider,
            imported.tree,
            external_data_approved=True,
        )

        self.assertEqual(index.source_snapshot_hash, imported.tree.snapshot_hash)
        self.assertEqual(len(index.entries), len(build_hybrid_node_documents(imported.tree)))

    def test_bailian_provider_rejects_a_non_h1_model(self) -> None:
        with self.assertRaises(EmbeddingProviderError) as caught:
            BailianHybridEmbeddingProvider(
                BailianConfig(api_key="fictional-key", model="text-embedding-v3")
            )
        self.assertEqual(caught.exception.code, "BAILIAN_EMBEDDING_CONFIG_INVALID")

    def test_wrong_provider_profile_is_rejected_before_embedding(self) -> None:
        imported = load_tree_export(ROOT / "tests/fixtures/fictional/tree_export.json")
        assert imported.tree is not None
        with self.assertRaises(EmbeddingProviderError) as caught:
            build_hybrid_index_with_provider(
                WrongProfileProvider(),
                imported.tree,
                external_data_approved=True,
            )
        self.assertEqual(caught.exception.code, "HYBRID_EMBEDDING_PROVIDER_INVALID")


if __name__ == "__main__":
    unittest.main()
