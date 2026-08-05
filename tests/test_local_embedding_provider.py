from __future__ import annotations

import unittest
from pathlib import Path

from treeguard.adapter import load_tree_export
from treeguard.local_embedding_provider import (
    LocalBgeH2EmbeddingProvider,
    LocalEmbeddingProviderError,
    build_h2_index_with_provider,
    build_h2_query_embedding_with_provider,
    embed_h2_documents,
    verify_local_h2_snapshot,
)
from treeguard.retrieval_hybrid import (
    EMBEDDING_DIMENSIONS,
    HybridRetrievalError,
    build_hybrid_node_documents,
)
from treeguard.retrieval_hybrid_h2 import (
    MODEL_ID,
    MODEL_REVISION,
    QUERY_INSTRUCTION,
    H2EmbeddingProfile,
)


ROOT = Path(__file__).resolve().parents[1]
TREE_FIXTURE = ROOT / "tests/fixtures/fictional/tree_export.json"


def _unit(axis: int = 0) -> tuple[float, ...]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    values[axis] = 1.0
    return tuple(values)


class RecordingBackend:
    def __init__(self) -> None:
        self.batches: list[tuple[str, ...]] = []

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.batches.append(texts)
        return tuple(_unit(index % 2) for index, _ in enumerate(texts))


class InvalidBackend:
    def embed(self, texts: tuple[str, ...]):
        return ((1.0,),) * len(texts)


class LocalEmbeddingProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        imported = load_tree_export(TREE_FIXTURE)
        assert imported.tree is not None
        cls.tree = imported.tree
        cls.documents = build_hybrid_node_documents(cls.tree)

    def test_profile_freezes_model_revision_runtime_and_batch(self) -> None:
        profile = H2EmbeddingProfile.build(
            artifact_manifest_hash="a" * 64,
            batch_size=16,
        )

        self.assertEqual(profile.to_dict()["model_id"], MODEL_ID)
        self.assertEqual(profile.to_dict()["model_revision"], MODEL_REVISION)
        self.assertEqual(profile.to_dict()["device"], "cpu")
        self.assertEqual(profile.to_dict()["batch_size"], 16)
        self.assertEqual(H2EmbeddingProfile.from_dict(profile.to_dict()), profile)

        tampered = profile.to_dict()
        tampered["query_instruction"] = "different"
        with self.assertRaises(HybridRetrievalError):
            H2EmbeddingProfile.from_dict(tampered)

    def test_documents_batch_stably_and_query_instruction_is_query_only(self) -> None:
        backend = RecordingBackend()
        profile = H2EmbeddingProfile.build(
            artifact_manifest_hash="b" * 64,
            batch_size=16,
        )
        provider = LocalBgeH2EmbeddingProvider(profile, backend)

        documents = (self.documents * 3)[:17]
        vectors = embed_h2_documents(provider, documents)
        provider.embed_query_batch(("fictional query",))

        self.assertEqual([len(batch) for batch in backend.batches], [16, 1, 1])
        self.assertEqual(len(vectors), 17)
        self.assertFalse(backend.batches[0][0].startswith(QUERY_INSTRUCTION))
        self.assertEqual(
            backend.batches[-1],
            (QUERY_INSTRUCTION + "fictional query",),
        )

    def test_provider_builds_profile_bound_index_and_query_embedding(self) -> None:
        backend = RecordingBackend()
        profile = H2EmbeddingProfile.build(
            artifact_manifest_hash="c" * 64,
            batch_size=16,
        )
        provider = LocalBgeH2EmbeddingProvider(profile, backend)

        index = build_h2_index_with_provider(provider, self.tree)
        query_embedding = build_h2_query_embedding_with_provider(
            provider,
            _query_document(self.documents[0].document_hash),
        )

        self.assertEqual(index.source_profile_hash, profile.profile_hash)
        self.assertEqual(query_embedding.source_profile_hash, profile.profile_hash)
        self.assertEqual(len(index.entries), len(self.documents))

    def test_input_output_and_snapshot_fail_closed(self) -> None:
        profile = H2EmbeddingProfile.build(
            artifact_manifest_hash="d" * 64,
            batch_size=16,
        )
        provider = LocalBgeH2EmbeddingProvider(profile, InvalidBackend())
        with self.assertRaises(LocalEmbeddingProviderError) as captured:
            provider.embed_document_batch(("fictional",))
        self.assertEqual(captured.exception.code, "H2_LOCAL_OUTPUT_INVALID")

        with self.assertRaises(LocalEmbeddingProviderError) as captured:
            provider.embed_document_batch(tuple("x" for _ in range(17)))
        self.assertEqual(captured.exception.code, "H2_LOCAL_INPUT_INVALID")

        with self.assertRaises(LocalEmbeddingProviderError) as captured:
            verify_local_h2_snapshot(ROOT / "missing-model")
        self.assertEqual(captured.exception.code, "H2_LOCAL_SNAPSHOT_INVALID")


def _query_document(source_hash: str):
    from treeguard.hashing import canonical_digest
    from treeguard.retrieval_hybrid import HybridQueryDocument

    payload = {
        "schema_version": "treeguard.hybrid-query-document.h1.v1",
        "source_evidence_hash": "1" * 64,
        "source_query_hash": "2" * 64,
        "text": "fictional query",
        "anchor_terms": ["fictional"],
    }
    return HybridQueryDocument(
        "1" * 64,
        "2" * 64,
        "fictional query",
        ("fictional",),
        canonical_digest(payload),
    )


if __name__ == "__main__":
    unittest.main()
