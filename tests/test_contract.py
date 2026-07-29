from __future__ import annotations

import json
import unittest
from pathlib import Path

from treeguard import load_tree_export


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_all_contracts_parse_and_declare_draft_2020_12(self) -> None:
        contract_paths = sorted((PROJECT_ROOT / "contracts").glob("*.schema.json"))
        self.assertGreaterEqual(len(contract_paths), 1)
        for schema_path in contract_paths:
            with self.subTest(contract=schema_path.name):
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )

    def test_contract_is_valid_json_and_matches_serialized_field_set(self) -> None:
        schema_path = PROJECT_ROOT / "contracts" / "tree-snapshot.v1.schema.json"
        fixture_path = (
            PROJECT_ROOT / "tests" / "fixtures" / "fictional" / "tree_export.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        result = load_tree_export(fixture_path)
        assert result.tree is not None
        snapshot = result.tree.to_dict()

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(set(schema["required"]), set(snapshot))
        self.assertEqual(
            set(schema["$defs"]["node"]["required"]),
            set(snapshot["nodes"][0]),
        )


if __name__ == "__main__":
    unittest.main()
