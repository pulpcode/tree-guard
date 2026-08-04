from __future__ import annotations

import unittest

from scripts.rescore_fire_m49_semantic_phase import score_semantic_item


class FireM49SemanticRescoreTests(unittest.TestCase):
    @staticmethod
    def _item(
        *,
        retrieval: str = "MATCH",
        recommendation: str = "MISMATCH",
        action: str | None = "NEED_CLARIFICATION",
    ) -> dict[str, object]:
        return {
            "retrieval_status": retrieval,
            "recommendation_status": recommendation,
            "draft": None if action is None else {"recommended_action": action},
        }

    def test_retrieval_mismatch_short_circuits_semantic_scoring(self) -> None:
        self.assertEqual(
            ("UPSTREAM_SHORT_CIRCUIT", False, False),
            score_semantic_item(self._item(retrieval="MISMATCH")),
        )

    def test_preferred_match_is_strict_and_safe(self) -> None:
        self.assertEqual(
            ("PREFERRED_MATCH", True, True),
            score_semantic_item(
                self._item(
                    recommendation="MATCH", action="USE_EXISTING_NODE"
                )
            ),
        )

    def test_non_positive_fallback_is_safe_but_not_preferred(self) -> None:
        for action in ("NEED_CLARIFICATION", "NEED_EVIDENCE", "ABSTAIN"):
            with self.subTest(action=action):
                self.assertEqual(
                    ("SAFE_ALTERNATIVE", False, True),
                    score_semantic_item(self._item(action=action)),
                )

    def test_wrong_positive_action_is_unsafe(self) -> None:
        self.assertEqual(
            ("UNSAFE_MISMATCH", False, False),
            score_semantic_item(self._item(action="USE_EXISTING_NODE")),
        )

    def test_contract_failure_is_not_reclassified_as_safe(self) -> None:
        self.assertEqual(
            ("RUN_FAILED", False, False),
            score_semantic_item(
                self._item(recommendation="RUN_FAILED", action=None)
            ),
        )


if __name__ == "__main__":
    unittest.main()
