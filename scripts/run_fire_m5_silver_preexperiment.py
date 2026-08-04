#!/usr/bin/env python3
"""Run the non-qualifying M5 Codex Silver pre-experiment.

The runner freezes a private plan before egress, enforces Intent -> Retrieval
-> Semantic short-circuiting, stores validated model drafts only in a private
result, and emits an aggregate-only M5 report.  It never grants admission,
Gold, Patch, or automatic-action authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fire_m5_data_common import preflight_dataset  # noqa: E402
from treeguard.adapter import load_tree_export  # noqa: E402
from treeguard.ai_review import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BailianConfig,
    BailianIntentDraftProvider,
    BailianProviderError,
    BailianSemanticRecommendationV4Provider,
)
from treeguard.change_intent import (  # noqa: E402
    ChangeIntentDraft,
    IntentRequest,
    IntentReviewAction,
    apply_intent_review,
)
from treeguard.hashing import canonical_digest  # noqa: E402
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.private_io import (  # noqa: E402
    preflight_private_output,
    read_private_json,
    write_private_json,
)
from treeguard.retrieval import build_candidate_set  # noqa: E402
from treeguard.scenario_assisted_shadow_validation import (  # noqa: E402
    AssistedShadowEvidenceQualification,
    AssistedShadowRoundMetrics,
    SafeAlternativeReviewMetrics,
    SemanticOutcomeMetrics,
    build_assisted_shadow_admission_report,
)
from treeguard.scenario_capability_validation import (  # noqa: E402
    CapabilityOracle,
    intent_matches_oracle,
    recommendation_matches_oracle,
    recommendation_outcome_from_draft,
    retrieval_matches_oracle,
)
from treeguard.scenario_repeatability_validation import (  # noqa: E402
    ContractComplianceMetrics,
)
from treeguard.semantic_recommendation import (  # noqa: E402
    SemanticRecommendationDraft,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "fictional" / "fire_m5_assisted_shadow"
PLAN_SCHEMA_VERSION = "fire-m5-silver-preexperiment-plan.v1"
RESULT_SCHEMA_VERSION = "fire-m5-silver-preexperiment-results.v1"
DIAGNOSTIC_SCHEMA_VERSION = "treeguard.m5-silver-preexperiment-diagnostic.v1"
ROUND_COUNT = 3
SCENARIO_COUNT = 24
OBSERVATION_COUNT = ROUND_COUNT * SCENARIO_COUNT
REVIEWER_REF = "m5-silver-deterministic-intent-bridge"
RECORDED_AT = "2030-01-02T03:07:00Z"
SAFE_ACTIONS = {"NEED_CLARIFICATION", "NEED_EVIDENCE", "ABSTAIN"}


class M5SilverExperimentError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _wire_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise M5SilverExperimentError("M5_SILVER_SOURCE_INVALID") from None
    return digest.hexdigest()


def _read_canonical_json(path: Path, *, maximum_bytes: int) -> Any:
    try:
        raw = path.read_bytes()
        if len(raw) > maximum_bytes:
            raise ValueError
        payload = strict_json_loads(raw.decode("utf-8"))
        expected = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if raw != expected:
            raise ValueError
        return payload
    except (OSError, TypeError, UnicodeError, ValueError):
        raise M5SilverExperimentError("M5_SILVER_SOURCE_INVALID") from None


def _load_sources(
    fixture_dir: Path = FIXTURE_DIR,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], dict[str, Any], Any]:
    try:
        if preflight_dataset(fixture_dir)["status"] != "PASS":
            raise ValueError
        manifest = _read_canonical_json(
            fixture_dir / "manifest.json", maximum_bytes=1_000_000
        )
        scenarios = _read_canonical_json(
            fixture_dir / "scenario-candidates.json", maximum_bytes=2_000_000
        )
        oracle = _read_canonical_json(
            fixture_dir / "oracle-sidecar.json", maximum_bytes=3_000_000
        )
        silver = _read_canonical_json(
            fixture_dir / "codex-silver-review.json", maximum_bytes=1_000_000
        )
        imported = load_tree_export(fixture_dir / "tree.json")
        if imported.tree is None or not imported.is_valid:
            raise ValueError
        formal = tuple(
            item
            for item in scenarios["candidates"]
            if item["selection_status"] == "EXECUTION"
        )
        silver_by_ref = {
            item["scenario_ref"]: item for item in silver["items"]
        }
        oracle_by_ref = {
            item["scenario_ref"]: item for item in oracle["items"]
        }
        if (
            manifest["source_class"] != "CLEANROOM_SYNTHETIC"
            or manifest["fictional"] is not True
            or manifest["derived_from_real"] is not False
            or manifest["model_exposed"] is not False
            or manifest["execution_count"] != SCENARIO_COUNT
            or silver["quality_tier"] != "SILVER"
            or silver["assessment_authority"] != "CODEX_ASSISTED"
            or silver["execution_eligible"] is not False
            or silver["gold_eligible"] is not False
            or silver["patch_eligible"] is not False
            or len(formal) != SCENARIO_COUNT
            or len({item["scenario_ref"] for item in formal}) != SCENARIO_COUNT
            or any(
                silver_by_ref[item["scenario_ref"]]["status"]
                != "SILVER_ACCEPTED"
                for item in formal
            )
            or set(oracle_by_ref) != {
                item["scenario_ref"] for item in scenarios["candidates"]
            }
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise M5SilverExperimentError("M5_SILVER_SOURCE_POLICY_INVALID") from None
    return manifest, formal, oracle_by_ref, imported.tree


def _intent_request(payload: dict[str, Any]) -> IntentRequest:
    try:
        return IntentRequest(
            requirement_text=payload["requirement_text"],
            proposed_parent_node_id=payload["proposed_parent_node_id"],
            node_kind_hint=payload["node_kind_hint"],
            value_type_hint=payload["value_type_hint"],
            cardinality_hint=payload["cardinality_hint"],
        )
    except (KeyError, TypeError, ValueError):
        raise M5SilverExperimentError("M5_SILVER_REQUEST_INVALID") from None


def build_plan(fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    manifest, formal, _, tree = _load_sources(fixture_dir)
    units: list[dict[str, Any]] = []
    forbidden = _forbidden_model_values(manifest, fixture_dir, tree)
    for round_index in range(1, ROUND_COUNT + 1):
        for scenario in formal:
            request = _intent_request(scenario["request"])
            model_view = json.dumps(
                request.to_model_dict(tree), ensure_ascii=False, sort_keys=True
            )
            if any(value and value in model_view for value in forbidden):
                raise M5SilverExperimentError("M5_SILVER_MODEL_INPUT_LEAK")
            units.append(
                {
                    "observation_ref": f"R{round_index:02d}:{scenario['scenario_ref']}",
                    "round_index": round_index,
                    "scenario_ref": scenario["scenario_ref"],
                    "source_candidate_digest": canonical_digest(scenario),
                    "expected_route": scenario["expected_route"],
                }
            )
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "purpose": "M5_CODEX_SILVER_NON_QUALIFYING_PREEXPERIMENT",
        "dataset_ref": manifest["dataset_ref"],
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "quality_tier": "SILVER",
        "assessment_authority": "CODEX_ASSISTED",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "qualification_forfeited_on_first_call": True,
        "contains_oracle": False,
        "contains_credentials": False,
        "provider": "BAILIAN",
        "endpoint": DEFAULT_BASE_URL.rstrip("/") + "/chat/completions",
        "model": DEFAULT_MODEL,
        "intent_prompt_version": BailianIntentDraftProvider.prompt_version,
        "semantic_prompt_version": (
            BailianSemanticRecommendationV4Provider.prompt_version
        ),
        "temperature": 0,
        "thinking_enabled": False,
        "round_count": ROUND_COUNT,
        "formal_scenario_count": SCENARIO_COUNT,
        "observation_count": OBSERVATION_COUNT,
        "intent_max_attempts": 2,
        "semantic_max_attempts": 2,
        "semantic_max_transport_retries": 1,
        "stage_policy": "INTENT_MATCH_THEN_RETRIEVAL_MATCH_THEN_SEMANTIC",
        "source_tree_sha256": manifest["tree_file_sha256"],
        "source_scenario_sha256": manifest["scenario_file_sha256"],
        "source_oracle_sha256": manifest["oracle_file_sha256"],
        "runner_source_sha256": _sha256_file(Path(__file__)),
        "provider_source_sha256": _sha256_file(ROOT / "src/treeguard/ai_review.py"),
        "intent_source_sha256": _sha256_file(ROOT / "src/treeguard/change_intent.py"),
        "retrieval_source_sha256": _sha256_file(ROOT / "src/treeguard/retrieval.py"),
        "semantic_source_sha256": _sha256_file(
            ROOT / "src/treeguard/semantic_recommendation.py"
        ),
        "oracle_source_sha256": _sha256_file(
            ROOT / "src/treeguard/scenario_capability_validation.py"
        ),
        "units": units,
    }
    plan["plan_digest"] = canonical_digest(plan)
    return plan


def write_plan(path: Path, fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    try:
        preflight_private_output(path)
    except OSError:
        raise M5SilverExperimentError("M5_SILVER_PLAN_OUTPUT_INVALID") from None
    plan = build_plan(fixture_dir)
    if not write_private_json(path, plan):
        raise M5SilverExperimentError("M5_SILVER_PLAN_WRITE_FAILED")
    return plan


def read_plan(
    path: Path,
    expected_sha256: str,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
    try:
        plan = read_private_json(path, max_bytes=5_000_000)
        if (
            stat.S_IMODE(path.stat().st_mode) != 0o600
            or _sha256_file(path) != expected_sha256
            or plan != build_plan(fixture_dir)
        ):
            raise ValueError
    except (OSError, TypeError, UnicodeError, ValueError):
        raise M5SilverExperimentError("M5_SILVER_PLAN_INVALID") from None
    return plan


class _GuardedTransportMixin:
    def _initialize_guard(
        self,
        forbidden_values: frozenset[str],
        audit: list[dict[str, Any]],
        maximum_calls: int,
    ) -> None:
        self._forbidden_values = forbidden_values
        self._audit = audit
        self._maximum_calls = maximum_calls

    def _post_json(self, body: dict[str, Any]) -> Any:
        encoded = _wire_bytes(body)
        text = encoded.decode("utf-8")
        if any(value and value in text for value in self._forbidden_values):
            raise M5SilverExperimentError("M5_SILVER_MODEL_INPUT_LEAK")
        if len(self._audit) >= self._maximum_calls:
            raise M5SilverExperimentError("M5_SILVER_UNIT_CALL_LIMIT_EXCEEDED")
        self._audit.append(
            {
                "attempt": len(self._audit) + 1,
                "wire_sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
        return super()._post_json(body)


class GuardedIntentProvider(_GuardedTransportMixin, BailianIntentDraftProvider):
    def __init__(
        self,
        config: BailianConfig,
        forbidden_values: frozenset[str],
        audit: list[dict[str, Any]],
    ) -> None:
        self.validation_error_codes: list[str] = []
        BailianIntentDraftProvider.__init__(self, config, trace_sink=self._capture_trace)
        self._initialize_guard(forbidden_values, audit, 2)

    def _capture_trace(self, trace: Any) -> None:
        if trace.validation_status == "FAILED" and isinstance(
            trace.validation_error_code, str
        ):
            self.validation_error_codes.append(trace.validation_error_code)


class GuardedSemanticProvider(
    _GuardedTransportMixin, BailianSemanticRecommendationV4Provider
):
    def __init__(
        self,
        config: BailianConfig,
        forbidden_values: frozenset[str],
        audit: list[dict[str, Any]],
    ) -> None:
        self.validation_error_codes: list[str] = []
        BailianSemanticRecommendationV4Provider.__init__(
            self, config, trace_sink=self._capture_trace
        )
        self._initialize_guard(forbidden_values, audit, 3)

    def _capture_trace(self, trace: Any) -> None:
        if trace.validation_status == "FAILED" and isinstance(
            trace.validation_error_code, str
        ):
            self.validation_error_codes.append(trace.validation_error_code)


def _validate_tls_trust() -> None:
    try:
        roots = ssl.create_default_context().get_ca_certs()
    except (OSError, ssl.SSLError):
        raise M5SilverExperimentError("M5_SILVER_TLS_TRUST_UNAVAILABLE") from None
    if not roots:
        raise M5SilverExperimentError("M5_SILVER_TLS_TRUST_UNAVAILABLE")


def _forbidden_model_values(
    manifest: dict[str, Any], fixture_dir: Path, tree: Any
) -> frozenset[str]:
    scenarios = _read_canonical_json(
        fixture_dir / "scenario-candidates.json", maximum_bytes=2_000_000
    )
    oracle = _read_canonical_json(
        fixture_dir / "oracle-sidecar.json", maximum_bytes=3_000_000
    )
    values = {node.node_id for node in tree.nodes}
    values.update(
        {
            manifest["tree_canonical_digest"],
            manifest["tree_file_sha256"],
            manifest["scenario_file_sha256"],
            manifest["oracle_file_sha256"],
            scenarios["candidate_set_digest"],
            oracle["oracle_digest"],
            *(
                item["scenario_ref"]
                for item in scenarios["candidates"]
            ),
        }
    )
    return frozenset(values)


def _safe_semantic_class(
    recommendation: Any,
    candidate_set: Any,
    oracle_item: dict[str, Any],
    oracle: CapabilityOracle,
) -> str:
    if recommendation_matches_oracle(
        recommendation, candidate_set, oracle.recommendation
    ):
        return "PREFERRED_MATCH"
    outcome = recommendation_outcome_from_draft(recommendation, candidate_set)
    allowed = set(oracle_item["safe_alternative"]["allowed_actions"])
    if (
        outcome.action in SAFE_ACTIONS
        and outcome.action in allowed
        and outcome.target_node_id is None
        and outcome.relation is None
    ):
        return "SAFE_ALTERNATIVE"
    return "UNSAFE_MISMATCH"


def execute_plan(
    *,
    plan_file: Path,
    plan_sha256: str,
    private_output: Path,
    exposure_marker: Path,
    fixture_dir: Path = FIXTURE_DIR,
    intent_provider_factory: Callable[..., Any] = GuardedIntentProvider,
    semantic_provider_factory: Callable[..., Any] = GuardedSemanticProvider,
) -> dict[str, Any]:
    plan = read_plan(plan_file, plan_sha256, fixture_dir)
    _validate_tls_trust()
    try:
        preflight_private_output(private_output)
        preflight_private_output(exposure_marker)
        environment = BailianConfig.from_env()
        config = BailianConfig(
            api_key=environment.api_key,
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            timeout_seconds=90.0,
            max_attempts=2,
            max_transport_retries=1,
        )
        manifest, formal, oracle_by_ref, tree = _load_sources(fixture_dir)
    except (BailianProviderError, OSError, TypeError, ValueError):
        raise M5SilverExperimentError("M5_SILVER_EXECUTION_PREFLIGHT_FAILED") from None

    if not write_private_json(
        exposure_marker,
        {
            "schema_version": "fire-m5-silver-exposure-marker.v1",
            "status": "EXPOSURE_STARTED",
            "evaluation_role": "CALIBRATION_ONLY",
            "qualification_forfeited": True,
            "plan_file_sha256": plan_sha256,
            "contains_credentials": False,
        },
    ):
        raise M5SilverExperimentError("M5_SILVER_EXPOSURE_MARKER_WRITE_FAILED")

    scenario_by_ref = {item["scenario_ref"]: item for item in formal}
    forbidden_values = _forbidden_model_values(manifest, fixture_dir, tree)
    results: list[dict[str, Any]] = []
    for unit in plan["units"]:
        scenario = scenario_by_ref[unit["scenario_ref"]]
        oracle_item = oracle_by_ref[unit["scenario_ref"]]
        oracle = CapabilityOracle.from_dict(oracle_item["capability_oracle"])
        request = _intent_request(scenario["request"])
        intent_calls: list[dict[str, Any]] = []
        intent_provider = intent_provider_factory(
            config, forbidden_values, intent_calls
        )
        draft = None
        intent_failure_code = None
        try:
            draft = intent_provider.draft(request, tree)
        except BailianProviderError as exc:
            intent_failure_code = exc.code
        intent_match = draft is not None and intent_matches_oracle(draft, oracle)
        actual_route = None
        if draft is not None:
            actual_route = (
                "CLARIFY"
                if draft.review_status == "NEEDS_CLARIFICATION"
                else "PROCEED"
            )
        retrieval_status = "NOT_RUN"
        semantic_status = "NOT_RUN"
        semantic_class = "NOT_OBSERVED"
        semantic_failure_code = None
        semantic_calls: list[dict[str, Any]] = []
        semantic_validation_codes: list[str] = []
        recommendation = None
        candidate_set = None
        if intent_match and oracle.expected_route == "PROCEED":
            confirmation = apply_intent_review(
                request,
                draft,
                IntentReviewAction(
                    expected_draft_hash=draft.draft_hash,
                    decision="CONFIRM_FOR_RETRIEVAL",
                    reviewer_ref=REVIEWER_REF,
                    recorded_at=RECORDED_AT,
                    confirmed_intent=draft.intent,
                ),
                tree,
            )
            candidate_set = build_candidate_set(confirmation, tree)
            retrieval_match = retrieval_matches_oracle(
                candidate_set, oracle.retrieval
            )
            retrieval_status = "MATCH" if retrieval_match else "MISMATCH"
            if retrieval_match:
                semantic_provider = semantic_provider_factory(
                    config, forbidden_values, semantic_calls
                )
                try:
                    recommendation = semantic_provider.recommend(
                        confirmation, candidate_set, tree
                    )
                except BailianProviderError as exc:
                    semantic_failure_code = exc.code
                semantic_validation_codes = list(
                    getattr(semantic_provider, "validation_error_codes", ())
                )
                if recommendation is None:
                    semantic_status = "RUN_FAILED"
                    semantic_class = "RUN_FAILED"
                else:
                    semantic_status = "DRAFT_READY"
                    semantic_class = _safe_semantic_class(
                        recommendation, candidate_set, oracle_item, oracle
                    )
        results.append(
            {
                "observation_ref": unit["observation_ref"],
                "round_index": unit["round_index"],
                "scenario_ref": unit["scenario_ref"],
                "expected_route": oracle.expected_route,
                "actual_route": actual_route,
                "intent_status": (
                    "MATCH"
                    if intent_match
                    else "RUN_FAILED" if draft is None else "MISMATCH"
                ),
                "intent_failure_code": intent_failure_code,
                "intent_calls": intent_calls,
                "intent_validation_error_codes": list(
                    getattr(intent_provider, "validation_error_codes", ())
                ),
                "retrieval_status": retrieval_status,
                "semantic_status": semantic_status,
                "semantic_class": semantic_class,
                "semantic_failure_code": semantic_failure_code,
                "semantic_calls": semantic_calls,
                "semantic_validation_error_codes": semantic_validation_codes,
                "intent_draft": None if draft is None else draft.to_dict(),
                "semantic_draft": (
                    None if recommendation is None else recommendation.to_dict()
                ),
            }
        )
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "purpose": "M5_CODEX_SILVER_NON_QUALIFYING_PREEXPERIMENT",
        "dataset_ref": plan["dataset_ref"],
        "quality_tier": "SILVER",
        "assessment_authority": "CODEX_ASSISTED",
        "evaluation_role": "CALIBRATION_ONLY",
        "gold_eligible": False,
        "gate_eligible": False,
        "patch_eligible": False,
        "qualification_forfeited": True,
        "contains_credentials": False,
        "plan_file_sha256": plan_sha256,
        "model": DEFAULT_MODEL,
        "observation_count": len(results),
        "results": results,
    }
    if not write_private_json(private_output, payload):
        raise M5SilverExperimentError("M5_SILVER_RESULT_WRITE_FAILED")
    return _aggregate_result(payload, codex_safe_reviewed=False)


def _aggregate_result(
    payload: dict[str, Any], *, codex_safe_reviewed: bool
) -> dict[str, Any]:
    results = payload["results"]
    if len(results) != OBSERVATION_COUNT:
        raise M5SilverExperimentError("M5_SILVER_RESULT_ACCOUNTING_INVALID")
    semantic_results = [
        item for item in results if item["semantic_status"] != "NOT_RUN"
    ]
    retrieval_results = [
        item for item in results if item["retrieval_status"] != "NOT_RUN"
    ]
    semantic_counts = Counter(item["semantic_class"] for item in semantic_results)
    clarification_match_count = sum(
        item["expected_route"] == "CLARIFY" and item["intent_status"] == "MATCH"
        for item in results
    )
    safe_by_ref: dict[str, bool] = {}
    preferred_by_ref: dict[str, bool] = {}
    safe_fingerprints = set()
    for item in results:
        preferred = item["semantic_class"] == "PREFERRED_MATCH"
        safe = (
            preferred
            or item["semantic_class"] == "SAFE_ALTERNATIVE"
            or (
                item["expected_route"] == "CLARIFY"
                and item["intent_status"] == "MATCH"
            )
        )
        preferred_by_ref[item["observation_ref"]] = preferred
        safe_by_ref[item["observation_ref"]] = safe
        if item["semantic_class"] == "SAFE_ALTERNATIVE":
            draft = item["semantic_draft"]
            safe_fingerprints.add(
                canonical_digest(
                    {
                        key: draft[key]
                        for key in (
                            "candidate_assessments",
                            "recommended_action",
                            "selected_candidate_ref",
                            "rationale",
                            "uncertainties",
                            "evidence_gaps",
                            "clarification_question",
                        )
                    }
                )
            )
    rounds = tuple(
        AssistedShadowRoundMetrics(
            round_index=round_index,
            safe_full_path_count=sum(
                matched
                for ref, matched in safe_by_ref.items()
                if ref.startswith(f"R{round_index:02d}:")
            ),
            preferred_full_path_count=sum(
                matched
                for ref, matched in preferred_by_ref.items()
                if ref.startswith(f"R{round_index:02d}:")
            ),
        )
        for round_index in range(1, ROUND_COUNT + 1)
    )
    scenario_refs = {item["scenario_ref"] for item in results}
    stable_safe = sum(
        all(safe_by_ref[f"R{round_index:02d}:{ref}"] for round_index in range(1, 4))
        for ref in scenario_refs
    )
    stable_preferred = sum(
        all(
            preferred_by_ref[f"R{round_index:02d}:{ref}"]
            for round_index in range(1, 4)
        )
        for ref in scenario_refs
    )
    intent_final_valid = sum(item["intent_status"] != "RUN_FAILED" for item in results)
    intent_first_valid = sum(
        item["intent_status"] != "RUN_FAILED"
        and not item["intent_validation_error_codes"]
        for item in results
    )
    semantic_final_valid = sum(
        item["semantic_status"] == "DRAFT_READY" for item in semantic_results
    )
    semantic_first_valid = sum(
        item["semantic_status"] == "DRAFT_READY"
        and not item["semantic_validation_error_codes"]
        for item in semantic_results
    )
    distinct_safe = len(safe_fingerprints)
    report = build_assisted_shadow_admission_report(
        AssistedShadowEvidenceQualification(
            policy_frozen_before_execution=True,
            requests_unseen_at_first_execution=True,
            oracle_review_authority="CODEX_ASSISTED",
            reviewed_scenario_count=SCENARIO_COUNT,
            runtime_configuration_frozen=True,
        ),
        rounds,
        stable_safe_full_path_count=stable_safe,
        stable_preferred_full_path_count=stable_preferred,
        executed_retrieval_count=len(retrieval_results),
        retrieval_match_count=sum(
            item["retrieval_status"] == "MATCH" for item in retrieval_results
        ),
        semantic_attempted_count=len(semantic_results),
        intent_contract=ContractComplianceMetrics(
            OBSERVATION_COUNT, intent_first_valid, intent_final_valid
        ),
        semantic_contract=ContractComplianceMetrics(
            len(semantic_results), semantic_first_valid, semantic_final_valid
        ),
        clarification_match_count=clarification_match_count,
        semantic_outcomes=SemanticOutcomeMetrics(
            preferred_match_count=semantic_counts["PREFERRED_MATCH"],
            safe_alternative_count=semantic_counts["SAFE_ALTERNATIVE"],
            unsafe_mismatch_count=semantic_counts["UNSAFE_MISMATCH"],
            run_failed_count=semantic_counts["RUN_FAILED"],
        ),
        safe_alternative_review=SafeAlternativeReviewMetrics(
            distinct_output_count=distinct_safe,
            reviewed_output_count=distinct_safe if codex_safe_reviewed else 0,
            blocking_finding_count=0,
            reviewer_authority=(
                "CODEX_ASSISTED"
                if codex_safe_reviewed and distinct_safe
                else "NOT_REVIEWED" if distinct_safe else "NOT_APPLICABLE"
            ),
        ),
        hard_failure_codes=(),
    )
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "status": "PASS",
        "evaluation_role": "CALIBRATION_ONLY",
        "qualification_forfeited": True,
        "codex_safe_reviewed": codex_safe_reviewed,
        "intent_actual_request_count": sum(
            len(item["intent_calls"]) for item in results
        ),
        "semantic_actual_request_count": sum(
            len(item["semantic_calls"]) for item in results
        ),
        "report": report.to_dict(),
    }


def score_private_result(
    *,
    result_file: Path,
    result_sha256: str,
    plan_file: Path,
    plan_sha256: str,
    fixture_dir: Path = FIXTURE_DIR,
    codex_safe_reviewed: bool,
) -> dict[str, Any]:
    try:
        payload = read_private_json(result_file, max_bytes=30_000_000)
        if (
            stat.S_IMODE(result_file.stat().st_mode) != 0o600
            or _sha256_file(result_file) != result_sha256
            or payload.get("schema_version") != RESULT_SCHEMA_VERSION
            or payload.get("qualification_forfeited") is not True
            or payload.get("contains_credentials") is not False
            or payload.get("plan_file_sha256") != plan_sha256
        ):
            raise ValueError
        _validate_result_shape(payload)
        plan = read_plan(plan_file, plan_sha256, fixture_dir)
        _replay_result(payload, plan, fixture_dir)
    except (OSError, TypeError, UnicodeError, ValueError):
        raise M5SilverExperimentError("M5_SILVER_RESULT_INVALID") from None
    return _aggregate_result(payload, codex_safe_reviewed=codex_safe_reviewed)


def _replay_result(
    payload: dict[str, Any], plan: dict[str, Any], fixture_dir: Path
) -> None:
    _, formal, oracle_by_ref, tree = _load_sources(fixture_dir)
    scenario_by_ref = {item["scenario_ref"]: item for item in formal}
    if [item["observation_ref"] for item in payload["results"]] != [
        item["observation_ref"] for item in plan["units"]
    ]:
        raise M5SilverExperimentError("M5_SILVER_RESULT_SOURCE_MISMATCH")
    try:
        for item, unit in zip(payload["results"], plan["units"], strict=True):
            if (
                item["round_index"] != unit["round_index"]
                or item["scenario_ref"] != unit["scenario_ref"]
                or item["expected_route"] != unit["expected_route"]
            ):
                raise ValueError
            scenario = scenario_by_ref[item["scenario_ref"]]
            oracle_item = oracle_by_ref[item["scenario_ref"]]
            oracle = CapabilityOracle.from_dict(oracle_item["capability_oracle"])
            request = _intent_request(scenario["request"])
            draft = None
            if item["intent_draft"] is not None:
                draft = ChangeIntentDraft.from_dict(
                    item["intent_draft"], request, tree
                )
            intent_match = draft is not None and intent_matches_oracle(draft, oracle)
            actual_route = None
            if draft is not None:
                actual_route = (
                    "CLARIFY"
                    if draft.review_status == "NEEDS_CLARIFICATION"
                    else "PROCEED"
                )
            expected_intent_status = (
                "MATCH"
                if intent_match
                else "RUN_FAILED" if draft is None else "MISMATCH"
            )
            if (
                item["actual_route"] != actual_route
                or item["intent_status"] != expected_intent_status
            ):
                raise ValueError
            expected_retrieval = "NOT_RUN"
            expected_semantic_status = "NOT_RUN"
            expected_semantic_class = "NOT_OBSERVED"
            if intent_match and oracle.expected_route == "PROCEED":
                confirmation = apply_intent_review(
                    request,
                    draft,
                    IntentReviewAction(
                        expected_draft_hash=draft.draft_hash,
                        decision="CONFIRM_FOR_RETRIEVAL",
                        reviewer_ref=REVIEWER_REF,
                        recorded_at=RECORDED_AT,
                        confirmed_intent=draft.intent,
                    ),
                    tree,
                )
                candidate_set = build_candidate_set(confirmation, tree)
                retrieval_match = retrieval_matches_oracle(
                    candidate_set, oracle.retrieval
                )
                expected_retrieval = "MATCH" if retrieval_match else "MISMATCH"
                if retrieval_match:
                    if item["semantic_draft"] is None:
                        expected_semantic_status = "RUN_FAILED"
                        expected_semantic_class = "RUN_FAILED"
                    else:
                        recommendation = SemanticRecommendationDraft.from_dict(
                            item["semantic_draft"], confirmation, candidate_set, tree
                        )
                        expected_semantic_status = "DRAFT_READY"
                        expected_semantic_class = _safe_semantic_class(
                            recommendation, candidate_set, oracle_item, oracle
                        )
            if (
                item["retrieval_status"] != expected_retrieval
                or item["semantic_status"] != expected_semantic_status
                or item["semantic_class"] != expected_semantic_class
            ):
                raise ValueError
    except (KeyError, TypeError, ValueError):
        raise M5SilverExperimentError("M5_SILVER_RESULT_SOURCE_MISMATCH") from None


def _validate_result_shape(payload: dict[str, Any]) -> None:
    top_keys = {
        "schema_version",
        "purpose",
        "dataset_ref",
        "quality_tier",
        "assessment_authority",
        "evaluation_role",
        "gold_eligible",
        "gate_eligible",
        "patch_eligible",
        "qualification_forfeited",
        "contains_credentials",
        "plan_file_sha256",
        "model",
        "observation_count",
        "results",
    }
    item_keys = {
        "observation_ref",
        "round_index",
        "scenario_ref",
        "expected_route",
        "actual_route",
        "intent_status",
        "intent_failure_code",
        "intent_calls",
        "intent_validation_error_codes",
        "retrieval_status",
        "semantic_status",
        "semantic_class",
        "semantic_failure_code",
        "semantic_calls",
        "semantic_validation_error_codes",
        "intent_draft",
        "semantic_draft",
    }
    results = payload.get("results")
    if (
        set(payload) != top_keys
        or payload.get("purpose")
        != "M5_CODEX_SILVER_NON_QUALIFYING_PREEXPERIMENT"
        or payload.get("quality_tier") != "SILVER"
        or payload.get("assessment_authority") != "CODEX_ASSISTED"
        or payload.get("evaluation_role") != "CALIBRATION_ONLY"
        or any(
            payload.get(field) is not False
            for field in ("gold_eligible", "gate_eligible", "patch_eligible")
        )
        or payload.get("qualification_forfeited") is not True
        or payload.get("contains_credentials") is not False
        or payload.get("model") != DEFAULT_MODEL
        or payload.get("observation_count") != OBSERVATION_COUNT
        or not isinstance(payload.get("plan_file_sha256"), str)
        or len(payload["plan_file_sha256"]) != 64
        or not isinstance(results, list)
        or len(results) != OBSERVATION_COUNT
        or any(not isinstance(item, dict) or set(item) != item_keys for item in results)
    ):
        raise M5SilverExperimentError("M5_SILVER_RESULT_POLICY_INVALID")
    expected_refs = [
        f"R{round_index:02d}:M5S{scenario_index:03d}"
        for round_index in range(1, ROUND_COUNT + 1)
        for scenario_index in range(1, SCENARIO_COUNT + 1)
    ]
    if [item["observation_ref"] for item in results] != expected_refs:
        raise M5SilverExperimentError("M5_SILVER_RESULT_ORDER_INVALID")
    for item in results:
        calls = item["intent_calls"] + item["semantic_calls"]
        if (
            item["round_index"] not in {1, 2, 3}
            or item["expected_route"] not in {"PROCEED", "CLARIFY"}
            or item["actual_route"] not in {None, "PROCEED", "CLARIFY"}
            or item["intent_status"] not in {"MATCH", "MISMATCH", "RUN_FAILED"}
            or item["retrieval_status"] not in {"NOT_RUN", "MATCH", "MISMATCH"}
            or item["semantic_status"] not in {"NOT_RUN", "DRAFT_READY", "RUN_FAILED"}
            or item["semantic_class"]
            not in {
                "NOT_OBSERVED",
                "PREFERRED_MATCH",
                "SAFE_ALTERNATIVE",
                "UNSAFE_MISMATCH",
                "RUN_FAILED",
            }
            or not isinstance(item["intent_validation_error_codes"], list)
            or not isinstance(item["semantic_validation_error_codes"], list)
            or any(not isinstance(code, str) for code in item["intent_validation_error_codes"])
            or any(not isinstance(code, str) for code in item["semantic_validation_error_codes"])
            or any(
                not isinstance(call, dict)
                or set(call) != {"attempt", "wire_sha256"}
                or call["attempt"] < 1
                or not isinstance(call["wire_sha256"], str)
                or len(call["wire_sha256"]) != 64
                for call in calls
            )
            or len(item["intent_calls"]) > 2
            or len(item["semantic_calls"]) > 3
            or (item["intent_draft"] is None) != (item["intent_status"] == "RUN_FAILED")
            or (item["semantic_draft"] is None)
            != (item["semantic_status"] != "DRAFT_READY")
        ):
            raise M5SilverExperimentError("M5_SILVER_RESULT_ITEM_INVALID")
        if item["intent_status"] != "MATCH" and (
            item["retrieval_status"] != "NOT_RUN"
            or item["semantic_status"] != "NOT_RUN"
        ):
            raise M5SilverExperimentError("M5_SILVER_STAGE_SHORT_CIRCUIT_INVALID")
        if item["expected_route"] == "CLARIFY" and item["intent_status"] == "MATCH" and (
            item["retrieval_status"] != "NOT_RUN"
            or item["semantic_status"] != "NOT_RUN"
        ):
            raise M5SilverExperimentError("M5_SILVER_STAGE_SHORT_CIRCUIT_INVALID")
        if item["expected_route"] == "PROCEED" and item["intent_status"] == "MATCH" and (
            item["retrieval_status"] == "NOT_RUN"
        ):
            raise M5SilverExperimentError("M5_SILVER_STAGE_SHORT_CIRCUIT_INVALID")
        if item["retrieval_status"] == "MISMATCH" and item["semantic_status"] != "NOT_RUN":
            raise M5SilverExperimentError("M5_SILVER_STAGE_SHORT_CIRCUIT_INVALID")
        if item["retrieval_status"] == "MATCH" and item["semantic_status"] == "NOT_RUN":
            raise M5SilverExperimentError("M5_SILVER_STAGE_SHORT_CIRCUIT_INVALID")
        if item["semantic_status"] == "NOT_RUN" and item["semantic_class"] != "NOT_OBSERVED":
            raise M5SilverExperimentError("M5_SILVER_RESULT_ITEM_INVALID")
        if item["semantic_status"] == "RUN_FAILED" and item["semantic_class"] != "RUN_FAILED":
            raise M5SilverExperimentError("M5_SILVER_RESULT_ITEM_INVALID")


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--plan-file", type=Path, required=True)
    prepare.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    run = subparsers.add_parser("run")
    run.add_argument("--plan-file", type=Path, required=True)
    run.add_argument("--plan-sha256", required=True)
    run.add_argument("--private-output", type=Path, required=True)
    run.add_argument("--exposure-marker", type=Path, required=True)
    run.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    score = subparsers.add_parser("score")
    score.add_argument("--result-file", type=Path, required=True)
    score.add_argument("--result-sha256", required=True)
    score.add_argument("--plan-file", type=Path, required=True)
    score.add_argument("--plan-sha256", required=True)
    score.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    score.add_argument("--codex-safe-reviewed", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "prepare":
            plan = write_plan(args.plan_file, args.fixture_dir)
            _print(
                {
                    "status": "PASS",
                    "schema_version": plan["schema_version"],
                    "observation_count": plan["observation_count"],
                    "qualification_forfeited_on_first_call": True,
                    "next_gate": "RUN_WITH_EXACT_PLAN_SHA256",
                }
            )
        elif args.command == "run":
            _print(
                execute_plan(
                    plan_file=args.plan_file,
                    plan_sha256=args.plan_sha256,
                    private_output=args.private_output,
                    exposure_marker=args.exposure_marker,
                    fixture_dir=args.fixture_dir,
                )
            )
        else:
            _print(
                score_private_result(
                    result_file=args.result_file,
                    result_sha256=args.result_sha256,
                    plan_file=args.plan_file,
                    plan_sha256=args.plan_sha256,
                    fixture_dir=args.fixture_dir,
                    codex_safe_reviewed=args.codex_safe_reviewed,
                )
            )
    except M5SilverExperimentError as exc:
        _print({"status": "FAIL", "error_code": exc.code})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
