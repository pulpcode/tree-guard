#!/usr/bin/env python3
"""Freeze the private, pre-egress M4.9 Intent request plan.

The first model stage can be reconstructed exactly from the promoted fixture.
Semantic request bodies depend on the untrusted Intent result and deterministic
retrieval, so they are deliberately frozen in a second phase instead of being
guessed from the hidden Oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.promote_fire_m49_sealed_data import (  # noqa: E402
    FIXTURE_DIR,
    PromotionError,
    validate_fixture,
)
from treeguard.adapter import adapt_tree_document  # noqa: E402
from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianIntentDraftProvider,
)
from treeguard.change_intent import IntentRequest  # noqa: E402
from treeguard.hashing import canonical_digest  # noqa: E402
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.private_io import write_private_json  # noqa: E402


PLAN_SCHEMA_VERSION = "fire-m49-sealed-runtime-plan.v1"
ROUND_COUNT = 3
FORMAL_SCENARIO_COUNT = 24
OBSERVATION_COUNT = ROUND_COUNT * FORMAL_SCENARIO_COUNT
INTENT_MAX_ATTEMPTS = 2
SEMANTIC_MAX_ATTEMPTS = 2
SEMANTIC_MAX_TRANSPORT_RETRIES = 1
INTENT_INITIAL_REQUEST_COUNT = OBSERVATION_COUNT
INTENT_MAXIMUM_ACTUAL_REQUEST_COUNT = OBSERVATION_COUNT * INTENT_MAX_ATTEMPTS
SEMANTIC_INITIAL_REQUEST_COUNT_UPPER_BOUND = 54
SEMANTIC_MAXIMUM_ACTUAL_REQUEST_COUNT = 162
TOTAL_MAXIMUM_ACTUAL_REQUEST_COUNT = (
    INTENT_MAXIMUM_ACTUAL_REQUEST_COUNT + SEMANTIC_MAXIMUM_ACTUAL_REQUEST_COUNT
)

# The retry body includes the exact local validation code.  This is an
# experiment contract, not a guess at model output, so the finite set is frozen
# before egress and must match the v4 Intent validator's public error family.
INTENT_RETRY_CODES = (
    "INTENT_MODEL_CONTENT_INVALID",
    "INTENT_MODEL_ASSUMPTIONS_INVALID",
    "INTENT_MODEL_CARDINALITY_INVALID",
    "INTENT_MODEL_CLARIFICATION_QUESTION_INVALID",
    "INTENT_MODEL_CONFIRMED_FACTS_INVALID",
    "INTENT_MODEL_EVIDENCE_GAPS_INVALID",
    "INTENT_MODEL_LIFECYCLE_INVALID",
    "INTENT_MODEL_NODE_KIND_INVALID",
    "INTENT_MODEL_OWNERSHIP_INVALID",
    "INTENT_MODEL_ROLE_INVALID",
    "INTENT_MODEL_SCENARIO_INVALID",
    "INTENT_MODEL_SUBJECT_INVALID",
    "INTENT_MODEL_VALUE_TYPE_INVALID",
    "INTENT_MODEL_FIELDS_INVALID",
    "INTENT_MODEL_INTERNAL_ID_FORBIDDEN",
    "INTENT_MODEL_RESPONSE_INVALID",
    "INTENT_MODEL_VERSION_INVALID",
)

PLAN_KEYS = {
    "schema_version",
    "purpose",
    "dataset_ref",
    "source_class",
    "fictional",
    "derived_from_real",
    "quality_tier",
    "evaluation_role",
    "gold_eligible",
    "gate_eligible",
    "patch_eligible",
    "execution_authorized",
    "contains_oracle",
    "contains_credentials",
    "runtime_registered",
    "experiment_executed",
    "functional_baseline_commit",
    "provider",
    "endpoint",
    "model",
    "response_mode",
    "thinking_enabled",
    "temperature",
    "stream",
    "timeout_seconds",
    "top_p_sent",
    "max_tokens_sent",
    "model_seed_sent",
    "intent_prompt_version",
    "semantic_prompt_version",
    "retrieval_version",
    "round_count",
    "formal_scenario_count",
    "observation_count",
    "intent_initial_request_count",
    "intent_maximum_actual_request_count",
    "intent_possible_request_body_count",
    "semantic_initial_request_count_upper_bound",
    "semantic_maximum_actual_request_count",
    "total_maximum_actual_request_count",
    "intent_retry_policy",
    "semantic_retry_policy",
    "semantic_request_plan_state",
    "semantic_request_plan_gate",
    "source_tree_snapshot_hash",
    "source_candidate_batch_digest",
    "source_silver_review_digest",
    "units",
    "next_gate",
    "plan_digest",
}
UNIT_KEYS = {
    "observation_ref",
    "round_index",
    "scenario_ref",
    "source_candidate_digest",
    "intent_possible_requests",
    "semantic_request_state",
}
REQUEST_KEYS = {
    "attempt",
    "retry_code",
    "stage",
    "wire_body_text",
    "wire_sha256",
}


class M49RuntimePlanError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PlannedIntentContext:
    scenario_ref: str
    source_candidate_digest: str
    request: IntentRequest
    tree: Any


def wire_bytes(body: dict[str, Any]) -> bytes:
    """Match the provider transport's JSON encoding exactly."""

    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _read_canonical_json(path: Path, *, maximum_bytes: int) -> Any:
    try:
        raw = path.read_bytes()
        if len(raw) > maximum_bytes:
            raise ValueError
        value = strict_json_loads(raw.decode("utf-8"))
        expected = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if raw != expected:
            raise ValueError
        return value
    except (OSError, TypeError, UnicodeError, ValueError):
        raise M49RuntimePlanError("M49_RUNTIME_SOURCE_INVALID") from None


def _validated_sources(fixture_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    try:
        report = validate_fixture(fixture_dir)
        if report["status"] != "PASS":
            raise ValueError
    except (KeyError, PromotionError, TypeError, ValueError):
        raise M49RuntimePlanError("M49_RUNTIME_FIXTURE_INVALID") from None

    manifest = _read_canonical_json(
        fixture_dir / "manifest.json", maximum_bytes=1_000_000
    )
    scenario_batch = _read_canonical_json(
        fixture_dir / "scenario-candidates.json", maximum_bytes=3_000_000
    )
    silver_review = _read_canonical_json(
        fixture_dir / "silver-review.json", maximum_bytes=3_000_000
    )
    tree_document = _read_canonical_json(
        fixture_dir / "tree.json", maximum_bytes=20_000_000
    )
    tree_result = adapt_tree_document(tree_document)
    if not tree_result.is_valid or tree_result.tree is None:
        raise M49RuntimePlanError("M49_RUNTIME_TREE_INVALID")

    try:
        review_by_ref = {
            item["scenario_ref"]: item for item in silver_review["items"]
        }
        formal = [
            item for item in scenario_batch["items"] if item["batch"] == "FORMAL"
        ]
        formal.sort(
            key=lambda item: (
                item["scenario_ref"].startswith("C"),
                int(item["scenario_ref"][1:]),
            )
        )
        if (
            manifest["source_class"] != "CLEANROOM_SYNTHETIC"
            or manifest["fictional"] is not True
            or manifest["derived_from_real"] is not False
            or manifest["quality_tier"] != "CODEX_ASSISTED_SILVER"
            or manifest["gate_eligible"] is not False
            or manifest["gold_eligible"] is not False
            or manifest["patch_eligible"] is not False
            or manifest["runtime_registered"] is not False
            or manifest["formal_scenario_count"] != FORMAL_SCENARIO_COUNT
            or silver_review["status"] != "SILVER_ACCEPTED"
            or len(formal) != FORMAL_SCENARIO_COUNT
            or len({item["scenario_ref"] for item in formal}) != len(formal)
            or any(
                review_by_ref[item["scenario_ref"]]["decision"] != "ACCEPTED"
                for item in formal
            )
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise M49RuntimePlanError("M49_RUNTIME_SOURCE_POLICY_INVALID") from None
    return manifest, formal, tree_result.tree


def load_formal_intent_contexts(
    fixture_dir: Path = FIXTURE_DIR,
) -> tuple[PlannedIntentContext, ...]:
    """Rebuild the 24 reviewed request contexts without reading Oracle answers."""

    _, formal, tree = _validated_sources(fixture_dir)
    contexts = []
    for candidate in formal:
        try:
            contexts.append(
                PlannedIntentContext(
                    scenario_ref=candidate["scenario_ref"],
                    source_candidate_digest=candidate["candidate_digest"],
                    request=IntentRequest.from_dict(candidate["request"], tree),
                    tree=tree,
                )
            )
        except (KeyError, TypeError, ValueError):
            raise M49RuntimePlanError(
                "M49_RUNTIME_REQUEST_RECONSTRUCTION_INVALID"
            ) from None
    return tuple(contexts)


def build_plan(fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    manifest, _, _ = _validated_sources(fixture_dir)
    contexts = load_formal_intent_contexts(fixture_dir)
    provider = BailianIntentDraftProvider(
        BailianConfig(
            api_key="NOT_USED_FOR_LOCAL_PLAN",
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            timeout_seconds=90.0,
            max_attempts=INTENT_MAX_ATTEMPTS,
        )
    )
    units: list[dict[str, Any]] = []
    for round_index in range(1, ROUND_COUNT + 1):
        for context in contexts:
            try:
                model_input = context.request.to_model_dict(context.tree)
                variants = ((1, None),) + tuple(
                    (2, code) for code in INTENT_RETRY_CODES
                )
                possible_requests = []
                for attempt, retry_code in variants:
                    body = provider._intent_request_body(
                        model_input,
                        retry_code=retry_code,
                    )
                    encoded = wire_bytes(body)
                    possible_requests.append(
                        {
                            "attempt": attempt,
                            "retry_code": retry_code,
                            "stage": "INTENT_DRAFT",
                            "wire_body_text": encoded.decode("utf-8"),
                            "wire_sha256": hashlib.sha256(encoded).hexdigest(),
                        }
                    )
                units.append(
                    {
                        "observation_ref": (
                            f"R{round_index:02d}:{context.scenario_ref}"
                        ),
                        "round_index": round_index,
                        "scenario_ref": context.scenario_ref,
                        "source_candidate_digest": context.source_candidate_digest,
                        "intent_possible_requests": possible_requests,
                        "semantic_request_state": (
                            "DEFERRED_UNTIL_FROZEN_INTENT_RESULT_AND_RETRIEVAL"
                        ),
                    }
                )
            except (KeyError, TypeError, ValueError):
                raise M49RuntimePlanError(
                    "M49_RUNTIME_REQUEST_RECONSTRUCTION_INVALID"
                ) from None

    possible_body_count = OBSERVATION_COUNT * (1 + len(INTENT_RETRY_CODES))
    if (
        len(units) != OBSERVATION_COUNT
        or len({unit["observation_ref"] for unit in units}) != OBSERVATION_COUNT
        or any(
            len(unit["intent_possible_requests"]) != 1 + len(INTENT_RETRY_CODES)
            for unit in units
        )
        or any(
            len(
                {
                    request["wire_sha256"]
                    for request in unit["intent_possible_requests"]
                }
            )
            != 1 + len(INTENT_RETRY_CODES)
            for unit in units
        )
    ):
        raise M49RuntimePlanError("M49_RUNTIME_REQUEST_ACCOUNTING_INVALID")

    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "purpose": "M49_SEALED_SILVER_CALIBRATION_ONLY",
        "dataset_ref": manifest["dataset_ref"],
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "execution_authorized": False,
        "contains_oracle": False,
        "contains_credentials": False,
        "runtime_registered": False,
        "experiment_executed": False,
        "functional_baseline_commit": manifest["functional_baseline_commit"],
        "provider": "BAILIAN_OPENAI_COMPATIBLE",
        "endpoint": DEFAULT_BASE_URL.rstrip("/") + "/chat/completions",
        "model": DEFAULT_MODEL,
        "response_mode": {"type": "json_object"},
        "thinking_enabled": False,
        "temperature": 0,
        "stream": False,
        "timeout_seconds": 90.0,
        "top_p_sent": False,
        "max_tokens_sent": False,
        "model_seed_sent": False,
        "intent_prompt_version": provider.prompt_version,
        "semantic_prompt_version": "treeguard.semantic-recommendation.zh.v4",
        "retrieval_version": "treeguard.lexical-structural-retrieval.v1",
        "round_count": ROUND_COUNT,
        "formal_scenario_count": FORMAL_SCENARIO_COUNT,
        "observation_count": OBSERVATION_COUNT,
        "intent_initial_request_count": INTENT_INITIAL_REQUEST_COUNT,
        "intent_maximum_actual_request_count": INTENT_MAXIMUM_ACTUAL_REQUEST_COUNT,
        "intent_possible_request_body_count": possible_body_count,
        "semantic_initial_request_count_upper_bound": (
            SEMANTIC_INITIAL_REQUEST_COUNT_UPPER_BOUND
        ),
        "semantic_maximum_actual_request_count": (
            SEMANTIC_MAXIMUM_ACTUAL_REQUEST_COUNT
        ),
        "total_maximum_actual_request_count": TOTAL_MAXIMUM_ACTUAL_REQUEST_COUNT,
        "intent_retry_policy": (
            "AT_MOST_ONE_COMPLETE_RETRY_USING_ACTUAL_LOCAL_ERROR_CODE"
        ),
        "semantic_retry_policy": (
            "TWO_CONTRACT_ATTEMPTS_AND_ONE_CONNECTION_RECOVERY"
        ),
        "semantic_request_plan_state": "NOT_YET_CONSTRUCTIBLE",
        "semantic_request_plan_gate": (
            "FREEZE_EXACT_BODIES_AFTER_INTENT_RESULT_AND_DETERMINISTIC_RETRIEVAL"
        ),
        "source_tree_snapshot_hash": manifest["tree_snapshot_hash"],
        "source_candidate_batch_digest": manifest["candidate_batch_digest"],
        "source_silver_review_digest": manifest["silver_review_digest"],
        "units": units,
        "next_gate": "EXPLICIT_INTENT_EXECUTION_APPROVAL",
    }
    plan["plan_digest"] = canonical_digest(plan)
    validate_plan(plan, fixture_dir=fixture_dir, rebuild=False)
    return plan


def _assert_no_oracle_leak(plan: dict[str, Any], fixture_dir: Path) -> None:
    text = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    forbidden_markers = (
        '"acceptable_node_ids"',
        '"acceptable_outcomes"',
        '"capability_oracle"',
        '"oracle"',
        '"target_node_id"',
        '"expected_route"',
        '"clarification_rubric"',
    )
    if any(marker in text for marker in forbidden_markers):
        raise M49RuntimePlanError("M49_RUNTIME_ORACLE_LEAK")
    oracle = _read_canonical_json(
        fixture_dir / "oracle-sidecar.json", maximum_bytes=5_000_000
    )
    try:
        target_ids = {
            target
            for item in oracle["items"]
            for target in (
                list(item["oracle"]["retrieval"]["acceptable_node_ids"])
                + [
                    outcome["target_node_id"]
                    for outcome in item["oracle"]["recommendation"][
                        "acceptable_outcomes"
                    ]
                    if outcome["target_node_id"] is not None
                ]
            )
        }
    except (KeyError, TypeError):
        raise M49RuntimePlanError("M49_RUNTIME_ORACLE_SOURCE_INVALID") from None
    if any(json.dumps(node_id, ensure_ascii=False) in text for node_id in target_ids):
        raise M49RuntimePlanError("M49_RUNTIME_ORACLE_LEAK")


def validate_plan(
    plan: Any,
    *,
    fixture_dir: Path = FIXTURE_DIR,
    rebuild: bool = True,
) -> dict[str, Any]:
    if not isinstance(plan, dict) or set(plan) != PLAN_KEYS:
        raise M49RuntimePlanError("M49_RUNTIME_PLAN_FIELDS_INVALID")
    fixed_values = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "purpose": "M49_SEALED_SILVER_CALIBRATION_ONLY",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "CODEX_ASSISTED_SILVER",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "execution_authorized": False,
        "contains_oracle": False,
        "contains_credentials": False,
        "runtime_registered": False,
        "experiment_executed": False,
        "provider": "BAILIAN_OPENAI_COMPATIBLE",
        "endpoint": DEFAULT_BASE_URL.rstrip("/") + "/chat/completions",
        "model": DEFAULT_MODEL,
        "response_mode": {"type": "json_object"},
        "thinking_enabled": False,
        "temperature": 0,
        "stream": False,
        "timeout_seconds": 90.0,
        "top_p_sent": False,
        "max_tokens_sent": False,
        "model_seed_sent": False,
        "intent_prompt_version": "treeguard.change-intent.zh.v4",
        "semantic_prompt_version": "treeguard.semantic-recommendation.zh.v4",
        "retrieval_version": "treeguard.lexical-structural-retrieval.v1",
        "intent_retry_policy": (
            "AT_MOST_ONE_COMPLETE_RETRY_USING_ACTUAL_LOCAL_ERROR_CODE"
        ),
        "semantic_retry_policy": (
            "TWO_CONTRACT_ATTEMPTS_AND_ONE_CONNECTION_RECOVERY"
        ),
        "semantic_request_plan_state": "NOT_YET_CONSTRUCTIBLE",
        "semantic_request_plan_gate": (
            "FREEZE_EXACT_BODIES_AFTER_INTENT_RESULT_AND_DETERMINISTIC_RETRIEVAL"
        ),
        "next_gate": "EXPLICIT_INTENT_EXECUTION_APPROVAL",
    }
    if (
        plan["plan_digest"]
        != canonical_digest(
            {key: value for key, value in plan.items() if key != "plan_digest"}
        )
        or any(plan[key] != value for key, value in fixed_values.items())
    ):
        raise M49RuntimePlanError("M49_RUNTIME_PLAN_POLICY_INVALID")
    expected_counts = {
        "round_count": ROUND_COUNT,
        "formal_scenario_count": FORMAL_SCENARIO_COUNT,
        "observation_count": OBSERVATION_COUNT,
        "intent_initial_request_count": INTENT_INITIAL_REQUEST_COUNT,
        "intent_maximum_actual_request_count": INTENT_MAXIMUM_ACTUAL_REQUEST_COUNT,
        "intent_possible_request_body_count": OBSERVATION_COUNT
        * (1 + len(INTENT_RETRY_CODES)),
        "semantic_initial_request_count_upper_bound": (
            SEMANTIC_INITIAL_REQUEST_COUNT_UPPER_BOUND
        ),
        "semantic_maximum_actual_request_count": (
            SEMANTIC_MAXIMUM_ACTUAL_REQUEST_COUNT
        ),
        "total_maximum_actual_request_count": TOTAL_MAXIMUM_ACTUAL_REQUEST_COUNT,
    }
    if any(
        not isinstance(plan[field], int)
        or isinstance(plan[field], bool)
        or plan[field] != value
        for field, value in expected_counts.items()
    ):
        raise M49RuntimePlanError("M49_RUNTIME_PLAN_ACCOUNTING_INVALID")
    units = plan["units"]
    if (
        not isinstance(units, list)
        or len(units) != OBSERVATION_COUNT
        or any(not isinstance(unit, dict) or set(unit) != UNIT_KEYS for unit in units)
    ):
        raise M49RuntimePlanError("M49_RUNTIME_UNIT_FIELDS_INVALID")
    expected_refs = [
        f"R{round_index:02d}:{scenario_ref}"
        for round_index in range(1, ROUND_COUNT + 1)
        for scenario_ref in (
            [f"P{index:02d}" for index in range(1, 19)]
            + [f"C{index:02d}" for index in range(1, 7)]
        )
    ]
    if [unit["observation_ref"] for unit in units] != expected_refs:
        raise M49RuntimePlanError("M49_RUNTIME_UNIT_ORDER_INVALID")
    for unit in units:
        requests = unit["intent_possible_requests"]
        if (
            not isinstance(requests, list)
            or len(requests) != 1 + len(INTENT_RETRY_CODES)
            or any(
                not isinstance(request, dict) or set(request) != REQUEST_KEYS
                for request in requests
            )
        ):
            raise M49RuntimePlanError("M49_RUNTIME_REQUEST_FIELDS_INVALID")
        expected_variants = ((1, None),) + tuple(
            (2, code) for code in INTENT_RETRY_CODES
        )
        if [
            (request["attempt"], request["retry_code"]) for request in requests
        ] != list(expected_variants):
            raise M49RuntimePlanError("M49_RUNTIME_RETRY_PLAN_INVALID")
        if (
            unit["round_index"]
            != int(unit["observation_ref"][1:3])
            or unit["scenario_ref"] != unit["observation_ref"].split(":", 1)[1]
            or unit["semantic_request_state"]
            != "DEFERRED_UNTIL_FROZEN_INTENT_RESULT_AND_RETRIEVAL"
            or not isinstance(unit["source_candidate_digest"], str)
            or len(unit["source_candidate_digest"]) != 64
        ):
            raise M49RuntimePlanError("M49_RUNTIME_UNIT_POLICY_INVALID")
        for request in requests:
            if (
                request["stage"] != "INTENT_DRAFT"
                or not isinstance(request["wire_body_text"], str)
                or not isinstance(request["wire_sha256"], str)
                or len(request["wire_sha256"]) != 64
            ):
                raise M49RuntimePlanError("M49_RUNTIME_REQUEST_POLICY_INVALID")
            try:
                body = strict_json_loads(request["wire_body_text"])
                encoded = wire_bytes(body)
            except (TypeError, UnicodeError, ValueError):
                raise M49RuntimePlanError("M49_RUNTIME_WIRE_BODY_INVALID") from None
            if hashlib.sha256(encoded).hexdigest() != request["wire_sha256"]:
                raise M49RuntimePlanError("M49_RUNTIME_WIRE_DIGEST_INVALID")
    _assert_no_oracle_leak(plan, fixture_dir)
    if rebuild and plan != build_plan(fixture_dir):
        raise M49RuntimePlanError("M49_RUNTIME_PLAN_REPLAY_MISMATCH")
    return {
        "status": "PASS",
        "dataset_ref": plan["dataset_ref"],
        "round_count": plan["round_count"],
        "observation_count": plan["observation_count"],
        "intent_possible_request_body_count": plan[
            "intent_possible_request_body_count"
        ],
        "intent_maximum_actual_request_count": plan[
            "intent_maximum_actual_request_count"
        ],
        "semantic_plan_state": plan["semantic_request_plan_state"],
        "total_maximum_actual_request_count": plan[
            "total_maximum_actual_request_count"
        ],
        "execution_authorized": plan["execution_authorized"],
        "contains_oracle": plan["contains_oracle"],
        "contains_credentials": plan["contains_credentials"],
    }


def write_plan(output: Path, fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    if output.exists():
        raise M49RuntimePlanError("M49_RUNTIME_OUTPUT_EXISTS")
    plan = build_plan(fixture_dir)
    if not write_private_json(output, plan):
        raise M49RuntimePlanError("M49_RUNTIME_OUTPUT_INVALID")
    try:
        if stat.S_IMODE(output.stat().st_mode) != 0o600:
            raise ValueError
        stored = _read_canonical_json(output, maximum_bytes=30_000_000)
        validate_plan(stored, fixture_dir=fixture_dir)
    except (OSError, ValueError, M49RuntimePlanError):
        output.unlink(missing_ok=True)
        raise M49RuntimePlanError("M49_RUNTIME_OUTPUT_INVALID") from None
    return validate_plan(plan, fixture_dir=fixture_dir, rebuild=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = write_plan(args.output, fixture_dir=args.fixture_dir)
    except M49RuntimePlanError as exc:
        print(json.dumps({"code": exc.code, "status": "FAIL"}, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
