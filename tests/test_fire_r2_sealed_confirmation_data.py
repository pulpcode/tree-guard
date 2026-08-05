from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from treeguard.adapter import adapt_tree_document


REPOSITORY = Path(__file__).resolve().parents[1]


def load_local(name: str, relative: str):
    location = REPOSITORY / relative
    spec = importlib.util.spec_from_file_location(name, location)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_local(
    "fire_r2_cleanroom_two_generator_test",
    "scripts/generate_fire_r2_sealed_confirmation_cleanroom_2.py",
)
PREFLIGHT = load_local(
    "fire_r2_cleanroom_two_preflight_test",
    "scripts/preflight_fire_r2_sealed_confirmation_cleanroom_2.py",
)


class FireR2SealedConfirmationDataTest(unittest.TestCase):
    def _execution_binding(self) -> dict[str, object]:
        return PREFLIGHT.expected_execution_binding()

    def _execution_binding_raw(self) -> bytes:
        return PREFLIGHT._private_json_bytes(self._execution_binding())

    def _freeze_fixture(
        self,
        temporary: str,
        *,
        data_commit: str = "a" * 40,
    ) -> tuple[Path, Path, tuple[str, ...], dict[str, object]]:
        base = Path(temporary)
        repo = base / "repo"
        repo.mkdir(mode=0o700)
        public_paths = (
            ".trellis/tasks/08-04-r2-sealed-confirmation-cleanroom-2/prd.md",
            "scripts/preflight_fire_r2_sealed_confirmation_cleanroom_2.py",
        )
        for index, relative in enumerate(public_paths, start=1):
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"public-freeze-canary-{index}\n".encode("utf-8"))
            os.chmod(path, 0o644)
        root = base / "private"
        root.mkdir(mode=0o700)
        for index, filename in enumerate(PREFLIGHT.LEDGER_PRIVATE_FILES, start=1):
            path = root / filename
            path.write_bytes((json.dumps({"private_canary": index}) + "\n").encode("utf-8"))
            os.chmod(path, 0o600)
        ledger = PREFLIGHT.build_binding_ledger(
            repo,
            root,
            data_commit,
            public_paths,
            self._execution_binding(),
            self._execution_binding_raw(),
        )
        return repo, root, public_paths, ledger

    def _execution_input_fixture(
        self,
        temporary: str,
    ) -> tuple[Path, dict[str, object], dict[str, object], dict[str, object]]:
        imported = adapt_tree_document(
            GENERATOR.build_tree(),
            source_hint="fire-r2-cleanroom-two-execution-input-test",
        )
        self.assertIsNotNone(imported.tree)
        tree = imported.tree
        assert tree is not None
        root_node = next(node for node in tree.nodes if node.parent_node_id is None)
        top_branches = tuple(
            node for node in tree.nodes if node.parent_node_id == root_node.node_id
        )
        self.assertGreaterEqual(len(top_branches), 2)
        proposed = top_branches[0]
        wrong = top_branches[1]
        contract = next(
            node.value_contract
            for node in tree.nodes
            if node.value_contract is not None
        )
        candidates = []
        entries = []
        for candidate_id in PREFLIGHT.FROZEN_IDS:
            request = f"synthetic locked request {candidate_id}"
            brief = f"synthetic scenario brief {candidate_id}"
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "request_text": request,
                    "scenario_brief": brief,
                }
            )
            entries.append(
                {
                    "candidate_id": candidate_id,
                    "cardinality_hint": contract.cardinality,
                    "node_kind_hint": "PROPERTY",
                    "proposed_parent_node_id": proposed.node_id,
                    "retrieval_seed": {
                        "assumptions": [PREFLIGHT.EXECUTION_ASSUMPTION],
                        "cardinality": contract.cardinality,
                        "clarification_question": None,
                        "confirmed_facts": [request, brief],
                        "evidence_gaps": [PREFLIGHT.EXECUTION_GAP],
                        "lifecycle": PREFLIGHT.EXECUTION_LIFECYCLE,
                        "node_kind": "PROPERTY",
                        "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
                        "role": PREFLIGHT.EXECUTION_ROLE,
                        "scenario": brief,
                        "subject": proposed.name,
                        "value_type": contract.value_type,
                    },
                    "value_type_hint": contract.value_type,
                    "wrong_branch_parent_node_id": wrong.node_id,
                }
            )
        document = {
            "dataset_id": PREFLIGHT.DATASET,
            "entries": entries,
            "entry_count": 28,
            "schema_version": PREFLIGHT.EXECUTION_INPUT_SCHEMA,
            "source_stage": "FROZEN_SELECTION",
            "stage": "EXECUTION_INPUT_LOCKED",
            "view_names": list(PREFLIGHT.FIVE_VIEW_NAMES),
        }
        root = Path(temporary) / "execution-private"
        root.mkdir(mode=0o700)
        path = root / PREFLIGHT.EXECUTION_INPUT_FILE
        path.write_bytes(PREFLIGHT._private_json_bytes(document))
        os.chmod(path, 0o600)
        locked = {"candidates": candidates}
        frozen = {"selected_candidate_ids": list(PREFLIGHT.FROZEN_IDS)}
        return root, locked, frozen, document

    def test_tree_is_deterministic_521_node_resource_without_value(self) -> None:
        first = GENERATOR.build_tree()
        second = GENERATOR.build_tree()
        self.assertEqual(GENERATOR._json_bytes(first), GENERATOR._json_bytes(second))
        self.assertFalse(PREFLIGHT.contains_exact_key(first, "value"))
        imported = adapt_tree_document(first, source_hint="fire-r2-cleanroom-two-test")
        self.assertIsNotNone(imported.tree)
        self.assertEqual(imported.issues, ())
        self.assertEqual(imported.observed_node_count, 521)
        self.assertEqual(imported.observed_value_count, 0)

    def test_public_files_are_exact_generator_outputs(self) -> None:
        self.assertEqual(
            (REPOSITORY / GENERATOR.TREE_FILE).read_bytes(),
            GENERATOR._json_bytes(GENERATOR.build_tree()),
        )
        self.assertEqual(
            (REPOSITORY / GENERATOR.MANIFEST_FILE).read_bytes(),
            GENERATOR._json_bytes(GENERATOR.build_manifest()),
        )

    def test_manifest_is_cleanroom_non_gold_and_has_no_self_commit(self) -> None:
        manifest = GENERATOR.build_manifest()
        self.assertEqual(manifest["source_class"], "CLEANROOM_SYNTHETIC")
        self.assertIs(manifest["fictional"], True)
        self.assertIs(manifest["derived_from_real"], False)
        self.assertIs(manifest["gold_eligible"], False)
        self.assertIs(manifest["patch_eligible"], False)
        self.assertIs(manifest["model_execution_allowed"], False)
        self.assertIs(manifest["network_execution_allowed"], False)
        self.assertEqual(
            manifest["function_baseline_commit"],
            "03faee0a7a33e0ee413a4d91b70e8f577085751f",
        )
        self.assertEqual(manifest["data_commit_binding"], "PRIVATE_FREEZE_LEDGER")
        self.assertNotIn("data_commit", manifest)

    def test_public_preflight_accepts_only_new_generated_tree(self) -> None:
        identifiers = PREFLIGHT.validate_public(REPOSITORY)
        self.assertEqual(len(identifiers), 521)

    def test_execution_input_preflight_marks_five_views_executable_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, locked, frozen, document = self._execution_input_fixture(temporary)
            summary = PREFLIGHT.validate_execution_input(
                REPOSITORY,
                root,
                locked,
                frozen,
            )
            self.assertEqual(
                summary,
                {
                    "execution_input_count": 28,
                    "five_view_count": 5,
                    "five_view_unit_count": 140,
                },
            )
            imported = adapt_tree_document(
                GENERATOR.build_tree(),
                source_hint="fire-r2-cleanroom-two-view-contract-test",
            )
            self.assertIsNotNone(imported.tree)
            assert imported.tree is not None
            views = PREFLIGHT.build_execution_views(
                document["entries"][0],
                locked["candidates"][0],
                imported.tree,
            )
            self.assertEqual(tuple(item[0] for item in views), PREFLIGHT.FIVE_VIEW_NAMES)
            by_name = {item[0]: item for item in views}
            self.assertEqual(
                by_name["V_CANONICAL"][1].proposed_parent_node_id,
                document["entries"][0]["proposed_parent_node_id"],
            )
            self.assertIsNone(by_name["V_PARENT_ABSENT"][1].proposed_parent_node_id)
            self.assertEqual(
                by_name["V_PARENT_WRONG_BRANCH"][1].proposed_parent_node_id,
                document["entries"][0]["wrong_branch_parent_node_id"],
            )
            self.assertIsNone(by_name["V_FREE_TEXT_DROPPED"][2].subject)
            self.assertTrue(by_name["V_FREE_TEXT_DROPPED"][3])
            self.assertIsNone(by_name["V_REQUIREMENT_ONLY"][2].subject)
            self.assertFalse(by_name["V_REQUIREMENT_ONLY"][3])

    def test_execution_input_rejects_fields_enums_bool_and_same_branch_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, locked, frozen, original = self._execution_input_fixture(temporary)
            path = root / PREFLIGHT.EXECUTION_INPUT_FILE
            mutations = {
                "extra_field": lambda value: value.update({"unexpected": True}),
                "bool_count": lambda value: value.update({"entry_count": True}),
                "view_contract": lambda value: value.update(
                    {"view_names": list(reversed(PREFLIGHT.FIVE_VIEW_NAMES))}
                ),
                "node_kind": lambda value: value["entries"][0].update(
                    {"node_kind_hint": "UNKNOWN"}
                ),
                "cardinality": lambda value: value["entries"][0].update(
                    {"cardinality_hint": "UNKNOWN"}
                ),
                "same_branch": lambda value: value["entries"][0].update(
                    {
                        "wrong_branch_parent_node_id": value["entries"][0][
                            "proposed_parent_node_id"
                        ]
                    }
                ),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    changed = json.loads(json.dumps(original, ensure_ascii=False))
                    mutate(changed)
                    path.write_bytes(PREFLIGHT._private_json_bytes(changed))
                    os.chmod(path, 0o600)
                    with self.assertRaises(PREFLIGHT.GateError):
                        PREFLIGHT.validate_execution_input(
                            REPOSITORY,
                            root,
                            locked,
                            frozen,
                        )

    def test_data_commit_changes_are_addition_only_and_allowlisted(self) -> None:
        PREFLIGHT.validate_commit_rows(
            [
                ("A", "scripts/generate_fire_r2_sealed_confirmation_cleanroom_2.py"),
                ("A", "tests/test_fire_r2_sealed_confirmation_data.py"),
                ("A", ".trellis/tasks/08-04-r2-sealed-confirmation-cleanroom-2/prd.md"),
            ]
        )
        with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_NON_ADDITION"):
            PREFLIGHT.validate_commit_rows(
                [("M", "scripts/generate_fire_r2_sealed_confirmation_cleanroom_2.py")]
            )
        with self.assertRaisesRegex(
            PREFLIGHT.GateError,
            "FIRE_R2_C2_FUNCTION_DIFF_FORBIDDEN",
        ):
            PREFLIGHT.validate_commit_rows([("A", "src/treeguard/retrieval.py")])

    def test_private_root_requires_absolute_owner_only_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private_root = Path(temporary) / "bundle"
            private_root.mkdir(mode=0o700)
            PREFLIGHT.validate_private_root(private_root)
            os.chmod(private_root, 0o750)
            with self.assertRaisesRegex(
                PREFLIGHT.GateError,
                "FIRE_R2_C2_PRIVATE_ROOT_MODE_INVALID",
            ):
                PREFLIGHT.validate_private_root(private_root)

    def test_prepare_git_gate_is_hermetic_and_fail_closed(self) -> None:
        allowed_change = " M tests/test_fire_r2_sealed_confirmation_data.py\n"
        valid_results = (
            mock.Mock(stdout=f"{PREFLIGHT.PREVIOUS_DATA_COMMIT}\n"),
            mock.Mock(stdout=""),
            mock.Mock(stdout=allowed_change),
        )
        with mock.patch.object(PREFLIGHT, "git", side_effect=valid_results):
            PREFLIGHT.validate_prepare_git(Path("/isolated-repository"))

        invalid_states = (
            (
                (mock.Mock(stdout=f"{'f' * 40}\n"),),
                "FIRE_R2_C2_HEAD_INVALID",
            ),
            (
                (
                    mock.Mock(stdout=f"{PREFLIGHT.PREVIOUS_DATA_COMMIT}\n"),
                    mock.Mock(stdout="staged-file\n"),
                ),
                "FIRE_R2_C2_INDEX_NOT_CLEAN",
            ),
            (
                (
                    mock.Mock(stdout=f"{PREFLIGHT.PREVIOUS_DATA_COMMIT}\n"),
                    mock.Mock(stdout=""),
                    mock.Mock(stdout="M  scripts/preflight_fire_r2_sealed_confirmation_cleanroom_2.py\n"),
                ),
                "FIRE_R2_C2_TRACKED_CHANGE_FORBIDDEN",
            ),
            (
                (
                    mock.Mock(stdout=f"{PREFLIGHT.PREVIOUS_DATA_COMMIT}\n"),
                    mock.Mock(stdout=""),
                    mock.Mock(stdout="?? src/treeguard/retrieval.py\n"),
                ),
                "FIRE_R2_C2_FUNCTION_DIFF_FORBIDDEN",
            ),
        )
        for results, error_code in invalid_states:
            with self.subTest(error_code=error_code):
                with mock.patch.object(PREFLIGHT, "git", side_effect=results):
                    with self.assertRaisesRegex(PREFLIGHT.GateError, error_code):
                        PREFLIGHT.validate_prepare_git(Path("/isolated-repository"))

    def test_finalization_primitive_publishes_and_verifies_exact_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, root, _, ledger = self._freeze_fixture(temporary)
            self.assertEqual(ledger["execution_binding"], self._execution_binding())
            self.assertEqual(
                ledger["execution_binding_file"],
                {
                    "byte_length": len(self._execution_binding_raw()),
                    "logical_name": PREFLIGHT.EXECUTION_LOGICAL_NAME,
                    "sha256": PREFLIGHT._sha256(self._execution_binding_raw()),
                },
            )
            self.assertEqual(
                tuple(item["path"] for item in ledger["private_files"]),
                PREFLIGHT.LEDGER_PRIVATE_FILES,
            )
            execution_record = ledger["private_files"][-1]
            self.assertEqual(execution_record["path"], PREFLIGHT.EXECUTION_INPUT_FILE)
            self.assertGreater(execution_record["byte_length"], 0)
            self.assertEqual(len(execution_record["sha256"]), 64)
            PREFLIGHT.publish_final_freeze(root, ledger)
            PREFLIGHT.verify_final_freeze(root, ledger)
            final = root / PREFLIGHT.FINAL_FREEZE_DIRECTORY
            self.assertEqual(final.stat().st_mode & 0o777, 0o700)
            self.assertEqual(tuple(sorted(path.name for path in final.iterdir())), PREFLIGHT.FINAL_FREEZE_FILES)
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in final.iterdir()))

    def test_finalization_primitive_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, root, _, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            before = tuple((root / PREFLIGHT.FINAL_FREEZE_DIRECTORY / name).read_bytes() for name in PREFLIGHT.FINAL_FREEZE_FILES)
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_FINAL_DIRECTORY_EXISTS"):
                PREFLIGHT.publish_final_freeze(root, ledger)
            after = tuple((root / PREFLIGHT.FINAL_FREEZE_DIRECTORY / name).read_bytes() for name in PREFLIGHT.FINAL_FREEZE_FILES)
            self.assertEqual(after, before)

    def test_verify_frozen_rejects_private_source_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, root, public_paths, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            source = root / PREFLIGHT.PRIVATE_FILES[0]
            source.write_bytes(b'{"private_canary":"tampered"}\n')
            os.chmod(source, 0o600)
            changed = PREFLIGHT.build_binding_ledger(
                repo,
                root,
                "a" * 40,
                public_paths,
                self._execution_binding(),
                self._execution_binding_raw(),
            )
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_LEDGER_BINDING_INVALID"):
                PREFLIGHT.verify_final_freeze(root, changed)

    def test_verify_frozen_rejects_wrong_data_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, root, public_paths, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            wrong = PREFLIGHT.build_binding_ledger(
                repo,
                root,
                "b" * 40,
                public_paths,
                self._execution_binding(),
                self._execution_binding_raw(),
            )
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_LEDGER_BINDING_INVALID"):
                PREFLIGHT.verify_final_freeze(root, wrong)

    def test_verify_frozen_rejects_symlink_and_public_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, root, _, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            final = root / PREFLIGHT.FINAL_FREEZE_DIRECTORY
            ledger_path = final / PREFLIGHT.FINAL_FREEZE_FILES[0]
            target = root / "symlink-target.json"
            target.write_bytes(ledger_path.read_bytes())
            os.chmod(target, 0o600)
            ledger_path.unlink()
            ledger_path.symlink_to(target)
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_BOUND_FILE_INVALID"):
                PREFLIGHT.verify_final_freeze(root, ledger)
        with tempfile.TemporaryDirectory() as temporary:
            _, root, _, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            receipt = root / PREFLIGHT.FINAL_FREEZE_DIRECTORY / PREFLIGHT.FINAL_FREEZE_FILES[1]
            os.chmod(receipt, 0o644)
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_BOUND_PRIVATE_MODE_INVALID"):
                PREFLIGHT.verify_final_freeze(root, ledger)

    def test_finalization_failure_leaves_no_final_or_temporary_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, root, _, ledger = self._freeze_fixture(temporary)
            with mock.patch.object(
                PREFLIGHT,
                "_atomic_rename_noreplace",
                side_effect=PREFLIGHT.GateError("FIRE_R2_C2_FINAL_RENAME_FAILED"),
            ):
                with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_FINAL_RENAME_FAILED"):
                    PREFLIGHT.publish_final_freeze(root, ledger)
            self.assertFalse((root / PREFLIGHT.FINAL_FREEZE_DIRECTORY).exists())
            self.assertFalse(any(path.name.startswith(f".{PREFLIGHT.FINAL_FREEZE_DIRECTORY}.") for path in root.iterdir()))

    def test_verify_frozen_rejects_receipt_digest_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, root, _, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            receipt_path = root / PREFLIGHT.FINAL_FREEZE_DIRECTORY / PREFLIGHT.FINAL_FREEZE_FILES[1]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["ledger_sha256"] = "0" * 64
            receipt_path.write_bytes(PREFLIGHT._private_json_bytes(receipt))
            os.chmod(receipt_path, 0o600)
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_RECEIPT_BINDING_INVALID"):
                PREFLIGHT.verify_final_freeze(root, ledger)

    def test_execution_binding_rejects_every_frozen_value_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution.json"
            expected = self._execution_binding()
            expected_raw = PREFLIGHT._private_json_bytes(expected)
            path.write_bytes(expected_raw)
            os.chmod(path, 0o600)
            self.assertEqual(PREFLIGHT.load_execution_binding(path), (expected, expected_raw))
            mutations = {
                "schema_version": "treeguard.fire-r2-c2-execution-binding.v2",
                "model_id": "changed-model",
                "prompt_version": "treeguard.retrieval-role-extraction.zh.v3",
                "role_contract_version": "retrieval-role-model-output.v2",
                "r1_strategy_id": "changed-r1",
                "r2_strategy_id": "changed-r2",
                "temperature": 1,
                "enable_thinking": True,
                "candidate_limit": 21,
                "gate_k_values": [20, 8],
                "round_count": 3,
                "scenario_count": 29,
                "max_attempts_per_unit": 3,
                "maximum_actual_call_count": 113,
            }
            for field, changed_value in mutations.items():
                with self.subTest(field=field):
                    payload = self._execution_binding()
                    payload[field] = changed_value
                    path.write_bytes(PREFLIGHT._private_json_bytes(payload))
                    with self.assertRaisesRegex(
                        PREFLIGHT.GateError,
                        "FIRE_R2_C2_EXECUTION_BINDING_VALUE_INVALID",
                    ):
                        PREFLIGHT.load_execution_binding(path)
            for field in ("model_id", "temperature"):
                with self.subTest(field_set=field):
                    payload = self._execution_binding()
                    del payload[field]
                    path.write_bytes(PREFLIGHT._private_json_bytes(payload))
                    with self.assertRaisesRegex(
                        PREFLIGHT.GateError,
                        "FIRE_R2_C2_EXECUTION_BINDING_FIELDS_INVALID",
                    ):
                        PREFLIGHT.load_execution_binding(path)

    def test_execution_binding_rejects_bool_as_int(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution.json"
            os.chmod(temporary, 0o700)
            integer_fields = (
                "temperature",
                "candidate_limit",
                "round_count",
                "scenario_count",
                "max_attempts_per_unit",
                "maximum_actual_call_count",
            )
            for field in integer_fields:
                with self.subTest(field=field):
                    payload = self._execution_binding()
                    payload[field] = False if field == "temperature" else True
                    path.write_bytes(PREFLIGHT._private_json_bytes(payload))
                    os.chmod(path, 0o600)
                    with self.assertRaisesRegex(
                        PREFLIGHT.GateError,
                        "FIRE_R2_C2_EXECUTION_BINDING_TYPE_INVALID",
                    ):
                        PREFLIGHT.load_execution_binding(path)
            payload = self._execution_binding()
            payload["gate_k_values"] = [True, 20]
            path.write_bytes(PREFLIGHT._private_json_bytes(payload))
            with self.assertRaisesRegex(
                PREFLIGHT.GateError,
                "FIRE_R2_C2_EXECUTION_BINDING_TYPE_INVALID",
            ):
                PREFLIGHT.load_execution_binding(path)

    def test_verify_frozen_rejects_execution_binding_reformat(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, root, public_paths, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            execution_path = Path(temporary) / "execution.json"
            reformatted = json.dumps(
                self._execution_binding(),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self.assertNotEqual(reformatted, self._execution_binding_raw())
            execution_path.write_bytes(reformatted)
            os.chmod(execution_path, 0o600)
            binding, raw = PREFLIGHT.load_execution_binding(execution_path)
            changed = PREFLIGHT.build_binding_ledger(
                repo,
                root,
                "a" * 40,
                public_paths,
                binding,
                raw,
            )
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_LEDGER_BINDING_INVALID"):
                PREFLIGHT.verify_final_freeze(root, changed)

    def test_verify_frozen_rejects_frozen_public_file_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, root, public_paths, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            public_path = repo / public_paths[0]
            public_path.write_bytes(public_path.read_bytes() + b"changed\n")
            os.chmod(public_path, 0o644)
            changed = PREFLIGHT.build_binding_ledger(
                repo,
                root,
                "a" * 40,
                public_paths,
                self._execution_binding(),
                self._execution_binding_raw(),
            )
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_LEDGER_BINDING_INVALID"):
                PREFLIGHT.verify_final_freeze(root, changed)

    def test_verify_frozen_rejects_execution_input_sidecar_reformat(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, root, public_paths, ledger = self._freeze_fixture(temporary)
            PREFLIGHT.publish_final_freeze(root, ledger)
            sidecar_path = root / PREFLIGHT.EXECUTION_INPUT_FILE
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            reformatted = json.dumps(
                sidecar,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            self.assertNotEqual(reformatted, sidecar_path.read_bytes())
            sidecar_path.write_bytes(reformatted)
            os.chmod(sidecar_path, 0o600)
            changed = PREFLIGHT.build_binding_ledger(
                repo,
                root,
                "a" * 40,
                public_paths,
                self._execution_binding(),
                self._execution_binding_raw(),
            )
            with self.assertRaisesRegex(PREFLIGHT.GateError, "FIRE_R2_C2_LEDGER_BINDING_INVALID"):
                PREFLIGHT.verify_final_freeze(root, changed)

    def test_finalize_and_verify_stdout_are_aggregate_only(self) -> None:
        sensitive_canaries = (
            "/private/secret/path",
            "0123456789abcdef" * 4,
            "sealed request canary",
            "node-canary",
            "oracle-canary",
        )
        execution = self._execution_binding()
        ledger = {"data_commit": "a" * 40}
        for mode, expected in (
            ("finalize", '{"status":"FINAL_FREEZE_CREATED"}\n'),
            ("verify-frozen", '{"status":"FINAL_FREEZE_VALID"}\n'),
        ):
            output = io.StringIO()
            arguments = [
                "preflight",
                "--mode",
                mode,
                "--private-root",
                sensitive_canaries[0],
                "--data-commit",
                "a" * 40,
                "--execution-binding",
                "/private/execution.json",
            ]
            with (
                mock.patch.object(sys, "argv", arguments),
                mock.patch.object(PREFLIGHT, "validate_commit_binding", return_value=("public",)),
                mock.patch.object(PREFLIGHT, "validate_public", return_value=set()),
                mock.patch.object(PREFLIGHT, "validate_private", return_value={}),
                mock.patch.object(
                    PREFLIGHT,
                    "load_execution_binding",
                    return_value=(execution, self._execution_binding_raw()),
                ),
                mock.patch.object(PREFLIGHT, "build_binding_ledger", return_value=ledger),
                mock.patch.object(PREFLIGHT, "publish_final_freeze"),
                mock.patch.object(PREFLIGHT, "verify_final_freeze"),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(PREFLIGHT.main(), 0)
            self.assertEqual(output.getvalue(), expected)
            for canary in sensitive_canaries:
                self.assertNotIn(canary, output.getvalue())


if __name__ == "__main__":
    unittest.main()
