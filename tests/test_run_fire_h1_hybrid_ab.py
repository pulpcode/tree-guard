from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_fire_h1_hybrid_ab as runner
from treeguard.ai_review import BailianConfig
from treeguard.embedding_provider import (
    BailianHybridEmbeddingProvider,
    EmbeddingProviderError,
    build_hybrid_index_with_provider,
)
from treeguard.hybrid_index_io import write_private_hybrid_embedding_index
from treeguard.retrieval_hybrid import (
    EMBEDDING_DIMENSIONS,
    MODEL_ID,
    build_hybrid_node_documents,
    build_hybrid_query_document,
)


def _unit(axis: int) -> tuple[float, ...]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    values[axis] = 1.0
    return tuple(values)


class SemanticFixtureProvider:
    """Deterministic test double proving orchestration, not model quality."""

    model_id = MODEL_ID
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self, vectors_by_text: dict[str, tuple[float, ...]]) -> None:
        self.vectors_by_text = vectors_by_text
        self.calls: list[tuple[str, ...]] = []

    def embed_batch(
        self,
        texts: tuple[str, ...],
        *,
        external_data_approved: bool = False,
    ) -> tuple[tuple[float, ...], ...]:
        if external_data_approved is not True:
            raise AssertionError("the runner must preserve the approval boundary")
        self.calls.append(texts)
        return tuple(self.vectors_by_text[text] for text in texts)


class FireH1HybridABRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = runner.load_h1_sources()
        cls.documents = build_hybrid_node_documents(cls.sources.tree)

    def _semantic_provider(self) -> SemanticFixtureProvider:
        oracle = self.sources.oracle_by_ref
        target_ids = [
            entry["acceptable_node_ids"][0]
            for entry in oracle.values()
            if entry["acceptable_node_ids"]
        ]
        axis_by_target = {
            node_id: axis for axis, node_id in enumerate(target_ids)
        }
        vectors = {
            document.to_model_text(): _unit(axis_by_target.get(document.node_id, 511))
            for document in self.documents
        }
        for scenario in self.sources.scenarios:
            evidence, request, confirmation = runner.build_h1_case_sources(
                scenario, self.sources.tree
            )
            query = build_hybrid_query_document(
                evidence, request, confirmation, self.sources.tree
            )
            accepted = oracle[scenario["scenario_ref"]]["acceptable_node_ids"]
            vectors[query.to_model_text()] = (
                _unit(axis_by_target[accepted[0]]) if accepted else _unit(510)
            )
        return SemanticFixtureProvider(vectors)

    def test_preflight_replays_the_frozen_a_baseline_without_a_model(self) -> None:
        report = runner.preflight_h1_ab(self.sources)

        self.assertEqual(report["status"], "PREFLIGHT_READY")
        self.assertIs(report["model_called"], False)
        self.assertEqual(report["scenario_count"], 24)
        self.assertEqual(report["node_count"], 1357)
        self.assertEqual(report["planned_index_call_count"], 136)
        self.assertEqual(report["planned_query_call_count"], 20)
        self.assertEqual(report["baseline"]["recall_at_8"], 14)
        self.assertEqual(report["baseline"]["recall_at_20"], 14)
        self.assertEqual(report["baseline"]["non_literal_recall_at_20"], 6)
        self.assertEqual(report["baseline"]["hard_negative_safe_at_8"], 4)
        self.assertEqual(report["baseline"]["empty_status_match_count"], 4)
        self.assertEqual(report["baseline"]["replay_match_count"], 24)

    def test_controlled_semantic_vectors_drive_a_passing_end_to_end_run(self) -> None:
        provider = self._semantic_provider()
        index = build_hybrid_index_with_provider(
            provider,
            self.sources.tree,
            external_data_approved=True,
        )

        public, private = runner.run_h1_ab(self.sources, index, provider)

        self.assertEqual(public["status"], "PASS")
        self.assertEqual(public["decision"], "H1_DEVELOPMENT_CANDIDATE")
        self.assertEqual(public["failure_codes"], [])
        self.assertEqual(public["lexical"]["recall_at_20"], 14)
        self.assertEqual(public["hybrid"]["recall_at_20"], 16)
        self.assertEqual(public["hybrid"]["non_literal_recall_at_20"], 8)
        self.assertEqual(public["hybrid"]["hard_negative_safe_at_8"], 4)
        self.assertEqual(public["hybrid"]["empty_status_match_count"], 4)
        self.assertEqual(public["hybrid"]["replay_match_count"], 24)
        self.assertEqual(len(private["cases"]), 24)
        self.assertEqual([len(batch) for batch in provider.calls[:136]], [10] * 135 + [7])
        self.assertEqual(len(provider.calls), 156)

        public_text = json.dumps(public, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("H1S", public_text)
        self.assertNotIn("M5N", public_text)
        self.assertNotIn("acceptable_node_ids", public_text)
        model_text = "\n".join(text for batch in provider.calls for text in batch)
        self.assertNotIn("M5N", model_text)
        self.assertNotIn("acceptable_node_ids", model_text)

    def test_gate_failures_are_fixed_and_cover_semantic_regressions(self) -> None:
        lexical = {
            "recall_at_8": 14,
            "recall_at_20": 14,
            "non_literal_recall_at_20": 6,
            "lexical_baseline_recall_at_8": 4,
            "hard_negative_safe_at_8": 4,
            "empty_status_match_count": 4,
            "replay_match_count": 24,
        }
        hybrid = {
            "recall_at_8": 13,
            "recall_at_20": 14,
            "non_literal_recall_at_20": 6,
            "lexical_baseline_recall_at_8": 2,
            "hard_negative_safe_at_8": 3,
            "empty_status_match_count": 3,
            "replay_match_count": 23,
        }

        self.assertEqual(
            runner._gate_failures(lexical, hybrid),
            [
                "H1_RECALL_AT_20_GATE_FAILED",
                "H1_NON_LITERAL_GATE_FAILED",
                "H1_RECALL_AT_8_REGRESSION",
                "H1_HARD_NEGATIVE_REGRESSION",
                "H1_EMPTY_STATUS_REGRESSION",
                "H1_LEXICAL_BASELINE_REGRESSION",
                "H1_REPLAY_MISMATCH",
            ],
        )

    def test_cli_preflight_never_loads_provider_configuration(self) -> None:
        output = io.StringIO()
        with patch.object(
            runner.BailianHybridEmbeddingProvider,
            "from_env",
            side_effect=AssertionError("preflight touched environment"),
        ), contextlib.redirect_stdout(output):
            exit_code = runner.main(["--preflight-only"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "PREFLIGHT_READY")
        self.assertIs(payload["model_called"], False)

    def test_cli_rejects_preflight_outputs_before_loading_provider(self) -> None:
        output = io.StringIO()
        with patch.object(
            runner.BailianHybridEmbeddingProvider,
            "from_env",
            side_effect=AssertionError("invalid preflight touched environment"),
        ), contextlib.redirect_stdout(output):
            exit_code = runner.main(
                ["--preflight-only", "--internal-output", "/private/tmp/unused.json"]
            )

        self.assertEqual(exit_code, 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error_code"], "H1_PREFLIGHT_OUTPUT_FORBIDDEN")
        self.assertIs(payload["model_called"], False)

    def test_source_preflight_rejects_an_adjacent_tree_with_changed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fire_h1_hybrid_calibration"
            source = root / "fire_m5_assisted_shadow"
            shutil.copytree(runner.FIXTURE_DIR, fixture)
            source.mkdir()
            source_path = (
                runner.FIXTURE_DIR / "../fire_m5_assisted_shadow/tree.json"
            ).resolve()
            changed = bytearray(source_path.read_bytes())
            changed[-2] = ord(" ")
            (source / "tree.json").write_bytes(changed)

            with self.assertRaises(runner.H1RunnerError) as caught:
                runner.load_h1_sources(fixture)

        self.assertEqual(caught.exception.code, "H1_SOURCE_PREFLIGHT_FAILED")

    def test_live_rejects_one_path_for_index_and_result_before_provider(self) -> None:
        output = io.StringIO()
        with patch.object(
            runner.BailianHybridEmbeddingProvider,
            "from_env",
            side_effect=AssertionError("path collision touched environment"),
        ), contextlib.redirect_stdout(output):
            exit_code = runner.main(
                [
                    "--live",
                    "--index-output",
                    "/private/tmp/h1-path-collision.json",
                    "--internal-output",
                    "/private/tmp/./h1-path-collision.json",
                ]
            )

        self.assertEqual(exit_code, 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error_code"], "H1_LIVE_PATHS_INVALID")
        self.assertIs(payload["model_called"], False)

    def test_cli_classifies_embedding_failure_by_actual_wire_attempt(self) -> None:
        for attempts, expected_exit in ((0, 2), (1, 3)):
            with self.subTest(wire_attempt_count=attempts), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                provider = BailianHybridEmbeddingProvider(
                    BailianConfig(api_key="fictional-key", model=MODEL_ID)
                )
                provider.wire_attempt_count = attempts
                output = io.StringIO()
                with patch.object(
                    runner.BailianHybridEmbeddingProvider,
                    "from_env",
                    return_value=provider,
                ), patch.object(
                    runner,
                    "build_hybrid_index_with_provider",
                    side_effect=EmbeddingProviderError("H1_FAKE_EMBEDDING_FAILURE"),
                ), contextlib.redirect_stdout(output):
                    exit_code = runner.main(
                        [
                            "--live",
                            "--index-output",
                            str(root / "index.json"),
                            "--internal-output",
                            str(root / "result.json"),
                        ]
                    )

                self.assertEqual(exit_code, expected_exit)
                payload = json.loads(output.getvalue())
                self.assertEqual(payload["error_code"], "H1_FAKE_EMBEDDING_FAILURE")
                self.assertIs(payload["model_called"], bool(attempts))
                self.assertFalse((root / "index.json").exists())
                self.assertFalse((root / "result.json").exists())

    def test_cli_reuses_private_index_and_embeds_only_queries(self) -> None:
        provider = self._semantic_provider()
        index = build_hybrid_index_with_provider(
            provider,
            self.sources.tree,
            external_data_approved=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path = root / "index.json"
            result_path = root / "result.json"
            self.assertTrue(write_private_hybrid_embedding_index(index_path, index))
            provider.calls.clear()
            output = io.StringIO()

            with patch.object(
                runner.BailianHybridEmbeddingProvider,
                "from_env",
                return_value=provider,
            ), contextlib.redirect_stdout(output):
                exit_code = runner.main(
                    [
                        "--live",
                        "--index-input",
                        str(index_path),
                        "--internal-output",
                        str(result_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "PASS")
            self.assertEqual(len(provider.calls), 20)
            self.assertTrue(all(len(batch) == 1 for batch in provider.calls))
            node_texts = {document.to_model_text() for document in self.documents}
            self.assertTrue(
                all(text not in node_texts for batch in provider.calls for text in batch)
            )
            self.assertEqual(result_path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
