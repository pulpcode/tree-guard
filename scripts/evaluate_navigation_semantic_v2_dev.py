#!/usr/bin/env python3
"""Evaluate Navigation Semantic v2 on an existing clean-room development set."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from treeguard import adapt_tree_document  # noqa: E402
from treeguard.ai_review import (  # noqa: E402
    BailianConfig,
    BailianNavigationSemanticProviderV2,
    BailianProviderError,
)
from treeguard.change_intent import IntentRequest  # noqa: E402
from treeguard.change_understanding_v2 import ChangeUnderstandingV2  # noqa: E402
from treeguard.fictional_fire_data import (  # noqa: E402
    build_fictional_fire_manifest,
    build_fictional_fire_scenarios,
    build_fictional_fire_tree,
)
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.models import CanonicalTree  # noqa: E402
from treeguard.navigation_copilot import (  # noqa: E402
    NavigationCandidateSet,
    NavigationCopilotError,
    NavigationInterpretation,
    NavigationSemanticDraftV2,
    NavigationSemanticProjectionV2,
    apply_navigation_policy_v2,
    build_navigation_candidate_set,
    build_navigation_semantic_projection_v2,
)


DATA_ROOT = ROOT / "tests" / "fixtures" / "fictional" / "fire_validation"
REPORT_VERSION = "treeguard.navigation-semantic-v2-dev-evaluation.v1"
DATASET_ID = "fictional-fire-governance-validation"


class SemanticV2Provider(Protocol):
    def compare(
        self,
        projection: NavigationSemanticProjectionV2,
        tree: CanonicalTree,
    ) -> NavigationSemanticDraftV2: ...


@dataclass(frozen=True, slots=True)
class DevelopmentUnit:
    interpretation: NavigationInterpretation
    candidate_set: NavigationCandidateSet
    projection: NavigationSemanticProjectionV2
    expected_candidate_ref: str | None


def build_development_units() -> tuple[CanonicalTree, tuple[DevelopmentUnit, ...]]:
    manifest = _read_fixture_json(DATA_ROOT / "manifest.json")
    tree_document = _read_fixture_json(DATA_ROOT / "tree-medium.json")
    scenarios = _read_fixture_json(DATA_ROOT / "scenarios-medium.json")
    if (
        manifest != build_fictional_fire_manifest()
        or tree_document != build_fictional_fire_tree("medium")
        or scenarios != build_fictional_fire_scenarios("medium")
    ):
        raise ValueError(
            "development dataset does not replay the repository clean-room generator"
        )
    if (
        manifest.get("dataset_id") != DATASET_ID
        or manifest.get("fictional") is not True
        or manifest.get("gold_eligible") is not False
        or manifest.get("patch_eligible") is not False
        or manifest.get("source_policy") != "PUBLIC_CATEGORY_CLEAN_ROOM"
    ):
        raise ValueError("development dataset source contract is invalid")
    loaded = adapt_tree_document(tree_document)
    if not loaded.is_valid or loaded.tree is None:
        raise ValueError("development tree is invalid")
    tree = loaded.tree
    if (
        scenarios.get("dataset_id") != DATASET_ID
        or scenarios.get("fictional") is not True
        or scenarios.get("gold_eligible") is not False
        or scenarios.get("benchmark_role") != "semantic_interference"
    ):
        raise ValueError("development scenarios source contract is invalid")

    units = []
    for item in scenarios.get("items", []):
        target_node_id = item.get("oracle", {}).get("required_first_candidate_id")
        if item.get("flow") != "DIRECT" or not isinstance(target_node_id, str):
            continue
        request = IntentRequest.from_dict(item.get("request"), tree)
        prepared = item.get("initial_model_output")
        if not isinstance(prepared, dict):
            raise ValueError("development understanding bridge is missing")
        subject = prepared.get("subject")
        if (
            not isinstance(subject, str)
            or request.requirement_text.count(subject) != 1
        ):
            raise ValueError("development subject is not source-bound")
        understanding = ChangeUnderstandingV2.from_model_dict(
            {
                "schema_version": "change-understanding-model-output.v2",
                "node_kind": prepared.get("node_kind"),
                "value_type": prepared.get("value_type"),
                "cardinality": prepared.get("cardinality"),
                "clarification_question": None,
                "spans": [{"role": "TARGET", "text": subject}],
            },
            request,
            tree,
            model_provider="DETERMINISTIC_DEV_BRIDGE",
            model_capability="SOURCE_BOUND_FIXTURE",
            model_name="fire-validation-v1-bridge",
            prompt_version="treeguard.navigation-semantic-v2-dev-bridge.v1",
        )
        interpretation = NavigationInterpretation.valid(
            understanding, request, tree
        )
        candidate_set = build_navigation_candidate_set(
            request, interpretation, tree
        )
        projection = build_navigation_semantic_projection_v2(
            request, interpretation, candidate_set, tree
        )
        expected_candidate_ref = next(
            (
                view.candidate_ref
                for view, candidate in zip(
                    projection.candidates,
                    candidate_set.candidates[: len(projection.candidates)],
                )
                if candidate.node_id == target_node_id
            ),
            None,
        )
        if target_node_id in json.dumps(
            projection.to_model_dict(),
            ensure_ascii=False,
            sort_keys=True,
        ):
            raise ValueError("development Oracle leaked into model input")
        units.append(
            DevelopmentUnit(
                interpretation=interpretation,
                candidate_set=candidate_set,
                projection=projection,
                expected_candidate_ref=expected_candidate_ref,
            )
        )
    if not units:
        raise ValueError("development evaluation has no eligible units")
    return tree, tuple(units)


def evaluate_development_units(
    provider: SemanticV2Provider,
) -> dict[str, Any]:
    tree, units = build_development_units()
    policy_status_counts: Counter[str] = Counter()
    relation_counts: Counter[str] = Counter()
    failure_code_counts: Counter[str] = Counter()
    retrieval_eligible = 0
    model_valid = 0
    correct_highlight = 0
    incorrect_highlight = 0
    safe_nonhighlight = 0
    provider_failures = 0

    for unit in units:
        if unit.expected_candidate_ref is None:
            continue
        retrieval_eligible += 1
        try:
            draft = provider.compare(unit.projection, tree)
            decision = apply_navigation_policy_v2(
                unit.interpretation,
                unit.candidate_set,
                unit.projection,
                draft,
                semantic_status="SUCCEEDED",
            )
        except (BailianProviderError, NavigationCopilotError) as exc:
            provider_failures += 1
            failure_code_counts[getattr(exc, "code", "MODEL_OR_CONTRACT_FAILED")] += 1
            continue
        model_valid += 1
        policy_status_counts[decision.status] += 1
        relation_counts.update(
            item.relation for item in draft.candidate_assessments
        )
        if decision.highlighted_candidate_ref == unit.expected_candidate_ref:
            correct_highlight += 1
        elif decision.highlighted_candidate_ref is None:
            safe_nonhighlight += 1
        else:
            incorrect_highlight += 1

    return {
        "report_version": REPORT_VERSION,
        "status": "DEVELOPMENT_SMOKE_COMPLETE",
        "dataset_role": "NON_SEALED_CLEANROOM_SILVER",
        "qualification_eligible": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "planned_unit_count": len(units),
        "retrieval_eligible_count": retrieval_eligible,
        "model_valid_count": model_valid,
        "provider_failure_count": provider_failures,
        "failure_code_counts": dict(sorted(failure_code_counts.items())),
        "correct_highlight_count": correct_highlight,
        "incorrect_highlight_count": incorrect_highlight,
        "safe_nonhighlight_count": safe_nonhighlight,
        "policy_status_counts": dict(sorted(policy_status_counts.items())),
        "relation_counts": dict(sorted(relation_counts.items())),
    }


def _read_fixture_json(path: Path) -> dict[str, Any]:
    payload = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("development fixture must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if not args.live:
        print(
            json.dumps(
                {
                    "report_version": REPORT_VERSION,
                    "status": "LIVE_MODE_REQUIRED",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    try:
        provider = BailianNavigationSemanticProviderV2(BailianConfig.from_env())
        report = evaluate_development_units(provider)
    except (BailianProviderError, OSError, TypeError, ValueError) as exc:
        code = getattr(exc, "code", "DEVELOPMENT_EVALUATION_FAILED")
        print(
            json.dumps(
                {"report_version": REPORT_VERSION, "status": code},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 3 if report["provider_failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
