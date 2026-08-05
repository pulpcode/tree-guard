from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from treeguard.navigation_shadow_run import (
    NavigationShadowQualification,
    NavigationShadowRunError,
    NavigationShadowRunManifest,
    NavigationShadowThresholds,
    aggregate_shadow_qualifications,
    build_shadow_qualification,
)


ROOT = Path(__file__).resolve().parents[1]


def _assert_contract_fields(testcase, name, payload):
    schema = json.loads(
        (ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    testcase.assertEqual(set(schema["required"]), set(payload))


def _manifest() -> NavigationShadowRunManifest:
    return NavigationShadowRunManifest.create(
        run_ref="SR0001",
        contract_commit="0" * 40,
        provider_mode="QWEN_LIVE",
        participant_refs=("P01", "P02", "P03"),
    )


def _qualification(
    manifest: NavigationShadowRunManifest,
    index: int,
    *,
    action: str = "SELECT_CANDIDATE",
    rejection_disposition: str | None = None,
    confident: bool = True,
) -> NavigationShadowQualification:
    decision_hash = f"{index + 1:064x}"
    outcome_hash = f"{index + 101:064x}"
    return build_shadow_qualification(
        manifest,
        f"P{index % 3 + 1:02d}",
        SimpleNamespace(
            decision_hash=decision_hash,
            status="CANDIDATES_AVAILABLE" if confident else "NEED_EVIDENCE",
        ),
        SimpleNamespace(
            source_decision_hash=decision_hash,
            action=action,
            outcome_hash=outcome_hash,
            duration_ms=60_000 + index,
        ),
        rejection_disposition=rejection_disposition,
        clarification_used=False,
        model_degraded=False,
    )


class NavigationShadowRunTests(unittest.TestCase):
    def test_manifest_round_trip_freezes_d10_thresholds(self):
        manifest = _manifest()
        self.assertEqual(
            NavigationShadowRunManifest.from_dict(manifest.to_dict()),
            manifest,
        )
        self.assertEqual(manifest.thresholds.min_valid_case_count, 30)
        self.assertEqual(manifest.thresholds.min_participant_count, 3)
        self.assertFalse(manifest.to_dict()["production_write_enabled"])
        _assert_contract_fields(
            self,
            "navigation-copilot-shadow-run.v1",
            manifest.to_dict(),
        )

    def test_manifest_rejects_tamper_bool_and_insufficient_quota(self):
        manifest = _manifest()
        tampered = manifest.to_dict()
        tampered["planned_case_count"] = 31
        with self.assertRaises(NavigationShadowRunError) as caught:
            NavigationShadowRunManifest.from_dict(tampered)
        self.assertEqual(caught.exception.code, "SHADOW_RUN_MANIFEST_INVALID")
        with self.assertRaises(ValueError):
            NavigationShadowThresholds(min_valid_case_count=True)
        with self.assertRaises(ValueError):
            NavigationShadowThresholds(min_top8_coverage_bps=7_999)
        with self.assertRaises(ValueError):
            NavigationShadowRunManifest.create(
                run_ref="SR0002",
                contract_commit="0" * 40,
                provider_mode="QWEN_LIVE",
                participant_refs=("P01", "P02", "P03"),
                planned_case_count=29,
            )

    def test_rejected_case_requires_explicit_target_disposition(self):
        with self.assertRaises(NavigationShadowRunError) as caught:
            _qualification(_manifest(), 0, action="REJECT_ALL")
        self.assertEqual(
            caught.exception.code,
            "SHADOW_TARGET_DISPOSITION_REQUIRED",
        )
        record = _qualification(
            _manifest(),
            0,
            action="REJECT_ALL",
            rejection_disposition="PRESENT_NOT_FOUND",
            confident=False,
        )
        self.assertEqual(record.target_disposition, "PRESENT_NOT_FOUND")
        self.assertEqual(
            NavigationShadowQualification.from_dict(
                record.to_dict(), _manifest()
            ),
            record,
        )
        _assert_contract_fields(
            self,
            "navigation-copilot-shadow-qualification.v1",
            record.to_dict(),
        )

    def test_aggregate_uses_real_target_present_denominator(self):
        manifest = _manifest()
        records = []
        for index in range(24):
            records.append(_qualification(manifest, index))
        for index in range(24, 27):
            records.append(
                _qualification(
                    manifest,
                    index,
                    action="SELECT_OUTSIDE_CANDIDATE",
                    confident=False,
                )
            )
        records.append(
            _qualification(
                manifest,
                27,
                action="REJECT_ALL",
                rejection_disposition="PRESENT_NOT_FOUND",
                confident=False,
            )
        )
        for index in range(28, 30):
            records.append(
                _qualification(
                    manifest,
                    index,
                    action="REJECT_ALL",
                    rejection_disposition="ABSENT",
                    confident=False,
                )
            )
        aggregate = aggregate_shadow_qualifications(manifest, tuple(records))
        self.assertEqual(aggregate["decision"], "EXPANSION_ELIGIBLE")
        self.assertEqual(aggregate["valid_case_count"], 30)
        self.assertEqual(aggregate["participant_count"], 3)
        self.assertEqual(aggregate["target_present_case_count"], 28)
        self.assertEqual(aggregate["top8_direct_selection_count"], 24)
        self.assertEqual(aggregate["completed_navigation_count"], 27)
        self.assertEqual(aggregate["top8_coverage_rate_bps"], 8571)
        self.assertEqual(aggregate["navigation_completion_rate_bps"], 9642)
        _assert_contract_fields(
            self,
            "navigation-copilot-shadow-qualification-aggregate.v1",
            aggregate,
        )

    def test_aggregate_excludes_unknown_and_rejects_duplicate_outcome(self):
        manifest = _manifest()
        unknown = _qualification(
            manifest,
            0,
            action="REJECT_ALL",
            rejection_disposition="UNKNOWN",
            confident=False,
        )
        aggregate = aggregate_shadow_qualifications(manifest, (unknown,))
        self.assertEqual(aggregate["decision"], "COLLECTING")
        self.assertEqual(aggregate["valid_case_count"], 0)
        self.assertEqual(aggregate["unknown_case_count"], 1)
        with self.assertRaises(NavigationShadowRunError) as caught:
            aggregate_shadow_qualifications(manifest, (unknown, unknown))
        self.assertEqual(caught.exception.code, "SHADOW_AGGREGATE_SOURCE_MISMATCH")

        too_many = tuple(
            _qualification(manifest, index, confident=False)
            for index in range(31)
        )
        with self.assertRaises(NavigationShadowRunError) as caught:
            aggregate_shadow_qualifications(manifest, too_many)
        self.assertEqual(caught.exception.code, "SHADOW_AGGREGATE_PLAN_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
