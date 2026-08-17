import hashlib
import json
import shutil
import stat
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.navigation_copilot_v3c_b02 import pipeline
from treeguard.adapter import load_tree_export
from treeguard.navigation_copilot_sealed_validation import (
    SealedCaseOracle,
    SealedScenario,
    TerminalExpectation,
    validate_sealed_plan,
)
from treeguard.workbench import build_tree_reference_index


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fictional" / "navigation_copilot_sealed_v3c_b02"


def load_json(relative: str):
    return json.loads((FIXTURE / relative).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NavigationCopilotV3CB02DataTests(unittest.TestCase):
    def test_frozen_identity_and_closed_migration_ledger(self):
        catalog = load_json("catalog.json")
        self.assertEqual(catalog["batch_ref"], pipeline.BATCH_REF)
        self.assertEqual(catalog["namespace"], str(pipeline.NAMESPACE))
        self.assertEqual(catalog["seed"], pipeline.SEED)
        self.assertEqual(catalog["stable_id_algorithm_version"], pipeline.STABLE_ID_VERSION)
        self.assertEqual(catalog["schema_version"], pipeline.CATALOG_SCHEMA_VERSION)
        self.assertEqual(catalog["root_blueprint_file"], "blueprints/root.json")

        ledger = load_json("migration-ledger.json")
        self.assertEqual(set(ledger["source_allowlist"]), set(pipeline.SOURCE_ALLOWLIST))
        self.assertEqual(len(ledger["blueprint_files"]), 9)
        for item in ledger["blueprint_files"]:
            self.assertTrue(item["byte_equal"])
            self.assertEqual(item["source_sha256"], item["target_sha256"])
            self.assertEqual(
                item["target_sha256"], sha256(FIXTURE / item["relative_path"])
            )
        self.assertEqual(len(ledger["blueprint_review_payloads"]), 91)
        self.assertTrue(all(item["semantic_payload_equal"] for item in ledger["blueprint_review_payloads"]))
        self.assertEqual(len(ledger["candidate_payloads"]), 56)
        self.assertTrue(all(item["semantic_payload_equal"] for item in ledger["candidate_payloads"]))
        self.assertEqual(len(ledger["oracle_payloads"]), 51)
        self.assertTrue(all(item["semantic_payload_equal"] for item in ledger["oracle_payloads"]))
        self.assertFalse(ledger["weak_oracle_source_semantic_payload_reused"])
        self.assertTrue(ledger["scenario_freeze_preceded_oracle_migration"])

    def test_explicit_blueprints_have_one_root_and_pass_exact_dual_gates(self):
        nodes = pipeline.load_blueprints(FIXTURE)
        self.assertEqual(len(nodes), 700)
        roots = [item for item in nodes if item["parent_ref"] is None or item["parent_role"] is None]
        self.assertEqual([item["blueprint_ref"] for item in roots], ["root"])
        report = pipeline.signature_report(nodes)
        self.assertEqual(report["semantic"]["eligible_instance_count"], 91)
        self.assertLessEqual(report["semantic"]["max_repeat_group"], 3)
        self.assertLessEqual(report["semantic"]["repeated_instance_ratio_bps"], 2_000)
        self.assertLessEqual(report["skeleton"]["max_repeat_group"], 4)
        self.assertLessEqual(report["skeleton"]["repeated_instance_ratio_bps"], 4_000)
        reviews = load_json("reviews/blueprint-silver-review.json")["reviews"]
        self.assertEqual(
            {item["blueprint_ref"] for item in reviews},
            set(report["eligible_blueprint_refs"]),
        )

    def test_signature_negative_cases_block_field_rotation_evasions(self):
        nodes = (
            {
                "blueprint_ref": "root", "parent_ref": None, "parent_role": None,
                "label": "根", "name": "根", "kind": "concept", "value_type": None,
                "cardinality": None, "child_refs": ["leaf"], "semantic_note": "根。",
            },
            {
                "blueprint_ref": "leaf", "parent_ref": "root", "parent_role": "状态",
                "label": "叶", "name": "叶", "kind": "property", "value_type": "boolean",
                "cardinality": "SINGLE", "child_refs": [], "semantic_note": "叶。",
            },
        )
        by_ref = {item["blueprint_ref"]: dict(item) for item in nodes}
        semantic = pipeline._semantic_signature("root", by_ref, {})
        skeleton = pipeline._skeleton_signature("root", by_ref, {})

        renamed = {key: dict(value) for key, value in by_ref.items()}
        renamed["root"]["name"] = "另一个名称"
        renamed["root"]["label"] = "另一个标签"
        self.assertEqual(semantic, pipeline._semantic_signature("root", renamed, {}))
        self.assertEqual(skeleton, pipeline._skeleton_signature("root", renamed, {}))

        for field, value in (
            ("parent_role", "可见性"),
            ("value_type", "integer"),
            ("cardinality", "MULTIPLE"),
        ):
            rotated = {key: dict(item) for key, item in by_ref.items()}
            rotated["leaf"][field] = value
            self.assertNotEqual(
                semantic, pipeline._semantic_signature("root", rotated, {}), field
            )
            self.assertEqual(
                skeleton, pipeline._skeleton_signature("root", rotated, {}), field
            )

    def test_generator_contains_no_semantic_rotation_mechanism(self):
        source = Path(pipeline.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "itertools.product", "itertools.cycle", "cycle(", "rotate(",
            "execution_categories =", "semantic_templates", "topology_templates",
        ):
            self.assertNotIn(forbidden, source)
        self.assertEqual(
            set(pipeline.BLUEPRINT_FIELDS),
            {
                "blueprint_ref", "parent_ref", "parent_role", "label", "name",
                "kind", "value_type", "cardinality", "child_refs", "semantic_note",
            },
        )

    def test_candidate_preregistration_review_and_freeze_quotas(self):
        bindings = load_json("authoring/candidate-bindings.json")["bindings"]
        candidates = load_json("authoring/candidates.json")["candidates"]
        reviews = load_json("reviews/candidate-silver-review.json")["reviews"]
        self.assertEqual((len(bindings), len(candidates), len(reviews)), (56, 56, 56))
        self.assertEqual(len({item["scenario_ref"] for item in bindings}), 56)
        self.assertEqual(len({item["review"]["assessment"] for item in bindings}), 56)
        clarification_bindings = [
            item for item in bindings if item["source_category"] == "CLARIFICATION"
        ]
        self.assertEqual(len(clarification_bindings), 7)
        self.assertTrue(
            all(item["frozen_clarification_answer"] for item in clarification_bindings)
        )
        self.assertTrue(
            all(
                "frozen_clarification_answer" not in item
                for item in bindings
                if item["source_category"] != "CLARIFICATION"
            )
        )
        self.assertEqual(
            Counter(item["selection_disposition"] for item in reviews),
            Counter({"FROZEN_ACCEPTED": 48, "RESERVE_ACCEPTED": 7, "REJECTED": 1}),
        )
        self.assertEqual(sum(item["context_pressure"] for item in candidates), 8)
        self.assertEqual(sum(item["repeat_challenge"] for item in candidates), 16)
        for item in bindings:
            serialized = json.dumps(item, ensure_ascii=False)
            for forbidden in ("acceptable_node_ids", "expected_route", "target_status", "terminal"):
                self.assertNotIn(forbidden, serialized)

    def test_five_weak_reviews_are_new_and_four_frozen_oracles_are_exact(self):
        weak_reviews = load_json("authoring/weak-evidence-oracle-reviews.json")["reviews"]
        self.assertEqual(len(weak_reviews), 5)
        for item in weak_reviews:
            self.assertEqual(item["review_status"], "CODEX_SILVER_REVIEWED")
            self.assertGreaterEqual(len(item["competitor_blueprint_refs"]), 2)
            self.assertNotIn(item["hidden_target_blueprint_ref"], item["competitor_blueprint_refs"])
            self.assertEqual(len(set(item["competitor_blueprint_refs"])), len(item["competitor_blueprint_refs"]))

        oracles = [SealedCaseOracle.from_dict(item) for item in load_json("frozen/hidden-oracle.json")]
        weak = [item for item in oracles if item.category == "WEAK_EVIDENCE"]
        self.assertEqual(len(weak), 4)
        terminal = (TerminalExpectation("EXIT", None, "PRESENT_NOT_FOUND"),)
        for item in weak:
            self.assertEqual(item.expected_route, "LIMIT")
            self.assertEqual(item.acceptable_policy_statuses, ("NEED_EVIDENCE",))
            self.assertEqual(item.acceptable_terminals, terminal)

    def test_public_scenarios_use_reference_index_and_exclude_oracle_fields(self):
        result = load_tree_export(FIXTURE / "frozen" / "tree.json")
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.tree)
        references = build_tree_reference_index(result.tree)
        candidates = {item["scenario_ref"]: item for item in load_json("authoring/candidates.json")["candidates"]}
        scenarios = [SealedScenario.from_dict(item) for item in load_json("frozen/scenarios.json")]
        self.assertEqual(len(scenarios), 48)
        pressured = [item for item in scenarios if item.wrong_context_challenge]
        self.assertEqual(len(pressured), 8)
        for scenario in pressured:
            blueprint_ref = candidates[scenario.scenario_ref]["wrong_parent_blueprint_ref"]
            node_id = pipeline.stable_node_id(blueprint_ref)
            self.assertEqual(scenario.proposed_parent_ref, references.ref_by_node_id[node_id])
            self.assertRegex(scenario.proposed_parent_ref, r"^N\d{6}$")
        public_bytes = json.dumps([item.to_dict() for item in scenarios], ensure_ascii=False)
        for forbidden in ("acceptable_node_ids", "target_status", "expected_route", "oracle_hash"):
            self.assertNotIn(forbidden, public_bytes)
        freeze = load_json("frozen/scenario-freeze.json")
        self.assertFalse(freeze["oracle_read_or_used"])
        self.assertEqual(freeze["scenario_bytes_sha256"], sha256(FIXTURE / "frozen" / "scenarios.json"))

    def test_all_public_contracts_and_complete_sealed_plan_are_compatible(self):
        scenarios = tuple(SealedScenario.from_dict(item) for item in load_json("frozen/scenarios.json"))
        oracles = tuple(SealedCaseOracle.from_dict(item) for item in load_json("frozen/hidden-oracle.json"))
        self.assertEqual(len(scenarios), 48)
        self.assertEqual(len(oracles), 48)
        self.assertEqual(sum(item.target_status == "TARGET_PRESENT" for item in oracles), 42)
        manifest = pipeline._compatibility_manifest(
            scenarios,
            FIXTURE / "frozen" / "hidden-oracle.json",
            FIXTURE / "frozen" / "tree.json",
            FIXTURE / "frozen" / "scenarios.json",
        )
        validate_sealed_plan(manifest, scenarios, oracles)

        authoring_only = set(pipeline.AUTHORING_CATEGORY_ORDER) - {
            "LITERAL_UNIQUE", "CLARIFICATION", "WEAK_EVIDENCE"
        }
        public_bytes = json.dumps(
            [item.to_dict() for item in scenarios] + [item.to_dict() for item in oracles],
            ensure_ascii=False,
        )
        for forbidden in (*authoring_only, "blueprint_ref"):
            self.assertNotIn(forbidden, public_bytes)
        for oracle in oracles:
            self.assertFalse(set(oracle.acceptable_node_ids) & set(oracle.forbidden_node_ids))
            if oracle.target_status == "TARGET_ABSENT":
                self.assertEqual(oracle.acceptable_node_ids, ())
                self.assertEqual(oracle.forbidden_node_ids, ())

    def test_clarification_and_weak_authoring_have_real_competition(self):
        candidates = {item["scenario_ref"]: item for item in load_json("authoring/candidates.json")["candidates"]}
        authoring = load_json("authoring/oracle.json")["oracles"]
        clarification = [item for item in authoring if candidates[item["scenario_ref"]]["authoring_category"] == "CLARIFICATION"]
        self.assertEqual(len(clarification), 7)
        for item in clarification:
            self.assertEqual(len(item["acceptable_target_blueprint_refs"]), 1)
            self.assertGreaterEqual(len(item["clarification_comparison_blueprint_refs"]), 1)
            self.assertTrue(candidates[item["scenario_ref"]]["frozen_clarification_answer"])
        weak = [item for item in authoring if candidates[item["scenario_ref"]]["authoring_category"] == "WEAK_EVIDENCE"]
        self.assertEqual(len(weak), 5)
        for item in weak:
            self.assertEqual(len(item["acceptable_target_blueprint_refs"]), 1)
            self.assertGreaterEqual(len(item["distractor_blueprint_refs"]), 2)
            self.assertIn(item["weak_evidence_reason"], {"INSUFFICIENT_DISCRIMINATOR", "UNBOUNDED_SCOPE"})

    def test_tree_storage_reorder_and_repeat_freeze_are_deterministic(self):
        original = load_json("frozen/tree.json")

        def reverse_subnodes(node):
            copied = dict(node)
            copied["subnodes"] = {
                label: reverse_subnodes(child)
                for label, child in reversed(list(node["subnodes"].items()))
            }
            return copied

        reordered = dict(original)
        reordered["map_topology"] = {
            label: reverse_subnodes(node)
            for label, node in reversed(list(original["map_topology"].items()))
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reordered-tree.json"
            path.write_text(json.dumps(reordered, ensure_ascii=False), encoding="utf-8")
            first = load_tree_export(FIXTURE / "frozen" / "tree.json")
            second = load_tree_export(path)
            self.assertTrue(first.is_valid and second.is_valid)
            self.assertEqual(first.tree.snapshot_hash, second.tree.snapshot_hash)

            replay = Path(directory) / "fixture"
            shutil.copytree(FIXTURE, replay)
            tracked = (
                "frozen/tree.json", "frozen/scenarios.json", "frozen/hidden-oracle.json",
                "frozen/preflight.json", "frozen/data-manifest.json",
            )
            before = {name: sha256(replay / name) for name in tracked}
            pipeline.build_tree(replay)
            pipeline.freeze_scenarios(replay)
            pipeline.freeze_oracles(replay)
            pipeline.finalize(replay)
            after = {name: sha256(replay / name) for name in tracked}
            self.assertEqual(before, after)

    def test_tamper_and_boundary_canaries_fail_closed(self):
        with self.assertRaises(pipeline.DataBuildError):
            pipeline._allowed_source(FIXTURE, "frozen/scenarios.json")

        original_bindings = load_json("authoring/candidate-bindings.json")
        review_tampers = (
            ("accepted_fail", "v3c-b02-lit-01", {0: "FAIL"}, []),
            ("rejected_without_fail", "v3c-b02-lit-12", {0: "PASS"}, ["REQUEST_REDUNDANT_WORDING"]),
            ("rejected_without_finding", "v3c-b02-lit-12", {}, []),
            ("clarification_fail", "v3c-b02-cla-01", {5: "FAIL"}, []),
            ("clarification_not_applicable", "v3c-b02-cla-01", {5: "NOT_APPLICABLE"}, []),
            ("weak_not_applicable", "v3c-b02-wek-01", {6: "NOT_APPLICABLE"}, []),
            ("empty_finding_code", "v3c-b02-lit-12", {}, [""]),
            ("duplicate_finding_code", "v3c-b02-lit-12", {}, ["DUPLICATE", "DUPLICATE"]),
            ("non_string_finding_code", "v3c-b02-lit-12", {}, [1]),
        )
        for name, scenario_ref, rubric_updates, finding_codes in review_tampers:
            with self.subTest(review_tamper=name), tempfile.TemporaryDirectory() as directory:
                payload = json.loads(json.dumps(original_bindings, ensure_ascii=False))
                binding = next(
                    item for item in payload["bindings"]
                    if item["scenario_ref"] == scenario_ref
                )
                for index, value in rubric_updates.items():
                    binding["review"]["rubric"][index] = value
                binding["review"]["finding_codes"] = finding_codes
                fixture = Path(directory)
                destination = fixture / "authoring" / "candidate-bindings.json"
                destination.parent.mkdir(parents=True)
                destination.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                with self.assertRaises(pipeline.DataBuildError):
                    pipeline._load_bindings(fixture)

        scenario = load_json("frozen/scenarios.json")[0]
        with self.assertRaises(Exception):
            SealedScenario.from_dict({**scenario, "target_status": "TARGET_PRESENT"})
        bool_tamper = dict(scenario)
        bool_tamper["repeat_challenge"] = 1
        with self.assertRaises(Exception):
            SealedScenario.from_dict(bool_tamper)

        with tempfile.TemporaryDirectory() as directory:
            replay = Path(directory) / "fixture"
            shutil.copytree(FIXTURE, replay)
            forbidden = replay / "frozen" / "execution-manifest.json"
            forbidden.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(pipeline.DataBuildError):
                pipeline.verify_repository_modes(ROOT, replay)
            forbidden.unlink()
            executable = replay / "catalog.json"
            executable.chmod(0o755)
            with self.assertRaises(pipeline.DataBuildError):
                pipeline.verify_repository_modes(ROOT, replay)

        source_text = Path(pipeline.__file__).read_text(encoding="utf-8")
        self.assertNotIn('source.get("clarification_answer")', source_text)
        self.assertNotIn('source["clarification_answer"]', source_text)
        candidates = load_json("authoring/candidates.json")["candidates"]

        def freeze_with_source_answer(directory: Path, answer_mode: str) -> bytes:
            source = directory / "source"
            target = directory / "target"
            for relative in pipeline.SOURCE_BLUEPRINT_PATHS:
                destination = source / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(FIXTURE / relative, destination)
            review_destination = source / pipeline.SOURCE_BLUEPRINT_REVIEW
            review_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                FIXTURE / "reviews" / "blueprint-silver-review.json",
                review_destination,
            )
            source_rows = []
            for item in candidates:
                row = {
                    "category": item["authoring_category"],
                    "ordinal": item["ordinal"],
                    "scenario_ref": f"source-{item['scenario_ref']}",
                    "request": item["requirement_text"],
                    "non_literal_subtype": item["non_literal_subtype"],
                    "context_pressure": item["context_pressure"],
                    "repeatability_subset": item["repeat_challenge"],
                }
                if item["authoring_category"] == "CLARIFICATION" and answer_mode == "tampered":
                    row["clarification_answer"] = "禁止读取的篡改源答案"
                source_rows.append(row)
            candidate_destination = source / pipeline.SOURCE_CANDIDATES
            candidate_destination.parent.mkdir(parents=True, exist_ok=True)
            candidate_destination.write_text(
                json.dumps({"candidates": source_rows}, ensure_ascii=False),
                encoding="utf-8",
            )
            binding_destination = target / "authoring" / "candidate-bindings.json"
            binding_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                FIXTURE / "authoring" / "candidate-bindings.json",
                binding_destination,
            )
            pipeline.migrate_scenario_sources(source, target)
            pipeline.build_tree(target)
            pipeline.freeze_scenarios(target)
            return (target / "frozen" / "scenarios.json").read_bytes()

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            missing = freeze_with_source_answer(base / "missing", "missing")
            tampered = freeze_with_source_answer(base / "tampered", "tampered")
            self.assertEqual(missing, tampered)
            self.assertEqual(missing, (FIXTURE / "frozen" / "scenarios.json").read_bytes())

    def test_new_checkout_replays_without_private_file_modes_or_execution_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            replay = Path(directory) / "fixture"
            shutil.copytree(FIXTURE, replay)
            result = load_tree_export(replay / "frozen" / "tree.json")
            self.assertTrue(result.is_valid)
            scenarios = tuple(
                SealedScenario.from_dict(item)
                for item in json.loads((replay / "frozen" / "scenarios.json").read_text(encoding="utf-8"))
            )
            oracles = tuple(
                SealedCaseOracle.from_dict(item)
                for item in json.loads((replay / "frozen" / "hidden-oracle.json").read_text(encoding="utf-8"))
            )
            validate_sealed_plan(
                pipeline._compatibility_manifest(
                    scenarios,
                    replay / "frozen" / "hidden-oracle.json",
                    replay / "frozen" / "tree.json",
                    replay / "frozen" / "scenarios.json",
                ),
                scenarios,
                oracles,
            )
            self.assertFalse((replay / "frozen" / "execution-manifest.json").exists())
            for path in replay.rglob("*"):
                if path.is_file():
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o111, 0)

    def test_data_manifest_is_precommit_only_and_self_consistent(self):
        manifest = load_json("frozen/data-manifest.json")
        self.assertIsNone(manifest["data_commit"])
        self.assertFalse(manifest["execution_manifest_present"])
        self.assertFalse((FIXTURE / "frozen" / "execution-manifest.json").exists())
        expected = {
            path.relative_to(FIXTURE).as_posix()
            for path in FIXTURE.rglob("*.json")
            if path != FIXTURE / "frozen" / "data-manifest.json"
        }
        self.assertEqual(set(manifest["artifact_sha256"]), expected)
        for relative, digest in manifest["artifact_sha256"].items():
            self.assertEqual(sha256(FIXTURE / relative), digest)


if __name__ == "__main__":
    unittest.main()
