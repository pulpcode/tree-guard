from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from treeguard.adapter import load_tree_export
from treeguard.hybrid_index_io import (
    read_private_hybrid_embedding_index,
    write_private_hybrid_embedding_index,
)
from treeguard.private_io import write_private_json
from treeguard.retrieval_hybrid import (
    EMBEDDING_DIMENSIONS,
    MAX_INDEX_ENTRIES,
    HybridEmbeddingIndex,
    HybridRetrievalError,
    build_hybrid_embedding_index,
    build_hybrid_node_documents,
)


ROOT = Path(__file__).resolve().parents[1]
TREE_FIXTURE = ROOT / "tests/fixtures/fictional/tree_export.json"
SCHEMA = ROOT / "contracts/hybrid-embedding-index.h1.v1.schema.json"


def _unit() -> tuple[float, ...]:
    return (1.0,) + (0.0,) * (EMBEDDING_DIMENSIONS - 1)


class HybridIndexIOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        imported = load_tree_export(TREE_FIXTURE)
        assert imported.tree is not None
        cls.tree = imported.tree
        cls.documents = build_hybrid_node_documents(cls.tree)
        cls.index = build_hybrid_embedding_index(
            cls.tree,
            cls.documents,
            {document.node_id: _unit() for document in cls.documents},
        )

    def test_schema_matches_the_persisted_index_field_sets(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        payload = self.index.to_dict()
        self.assertEqual(set(schema["required"]), set(payload))
        self.assertEqual(
            set(schema["$defs"]["entry"]["required"]),
            set(payload["entries"][0]),
        )
        self.assertEqual(schema["properties"]["entries"]["maxItems"], MAX_INDEX_ENTRIES)

    def test_private_round_trip_is_0600_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            self.assertTrue(write_private_hybrid_embedding_index(path, self.index))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(read_private_hybrid_embedding_index(path, self.tree), self.index)
            self.assertFalse(write_private_hybrid_embedding_index(path, self.index))

    def test_tamper_public_permissions_and_stale_tree_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tampered = root / "tampered.json"
            payload = self.index.to_dict()
            payload["index_hash"] = "0" * 64
            self.assertTrue(write_private_json(tampered, payload))
            with self.assertRaises(HybridRetrievalError) as caught:
                read_private_hybrid_embedding_index(tampered, self.tree)
            self.assertEqual(caught.exception.code, "HYBRID_INDEX_ARTIFACT_INVALID")

            public = root / "public.json"
            self.assertTrue(write_private_hybrid_embedding_index(public, self.index))
            public.chmod(0o644)
            with self.assertRaises(OSError):
                read_private_hybrid_embedding_index(public, self.tree)

            stale = root / "stale.json"
            self.assertTrue(write_private_hybrid_embedding_index(stale, self.index))
            stale_tree = replace(self.tree, snapshot_hash="0" * 64)
            with self.assertRaises(HybridRetrievalError) as caught:
                read_private_hybrid_embedding_index(stale, stale_tree)
            self.assertEqual(caught.exception.code, "HYBRID_INDEX_STALE")

    def test_from_dict_rejects_extra_fields_and_bool_dimensions(self) -> None:
        extra = self.index.to_dict()
        extra["unexpected"] = True
        invalid_dimension = self.index.to_dict()
        invalid_dimension["dimensions"] = True
        invalid_vector = self.index.to_dict()
        invalid_vector["entries"][0]["values"] = [1.0]
        for payload in (extra, invalid_dimension, invalid_vector):
            with self.subTest(keys=sorted(payload)):
                with self.assertRaises(HybridRetrievalError) as caught:
                    HybridEmbeddingIndex.from_dict(payload)
                self.assertEqual(caught.exception.code, "HYBRID_INDEX_ARTIFACT_INVALID")


if __name__ == "__main__":
    unittest.main()
