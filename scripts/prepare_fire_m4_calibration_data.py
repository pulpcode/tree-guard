#!/usr/bin/env python3
"""Prepare a private, non-gating M4 calibration candidate package.

The frozen blind fixture is immutable.  This script derives a new candidate
identity, narrows only unsupported v1 intent expectations, and stops at
``PENDING_HUMAN_REVIEW``.  It never freezes or promotes a fixture.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import secrets
import shutil
import stat
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

BLIND_PREFLIGHT_PATH = (
    PROJECT_ROOT / "scripts/preflight_fire_m4_blind_validation_data.py"
)
SOURCE_FIXTURE_DIR = (
    PROJECT_ROOT / "tests/fixtures/fictional/fire_validation_m4_blind"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "artifacts/fictional-validation/fire-m4-calibration-v1"
)
POLICY_SOURCE_PATH = PROJECT_ROOT / "src/treeguard/scenario_capability_validation.py"

DATASET_REF = "fictional-fire-m4-calibration-v1"
RUN_REF = "fire-m4-calibration-v1"
SOURCE_BLIND_MANIFEST_SHA256 = (
    "336289969eb548b6420144ce90e8ec1a3ccc4dee4928590b08d30f6c64471267"
)
SOURCE_BLIND_SIDECAR_SHA256 = (
    "7f467c0e1c0c2fc1a1666aeb95d50975be41f3812c7e77920e005fa88569cce0"
)
SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
UNBOUND_V1_FIELDS = {
    "assumptions",
    "confirmed_facts",
    "evidence_gaps",
    "lifecycle",
    "ownership",
    "role",
    "scenario",
    "subject",
}
STRUCTURED_FIELDS = {
    "cardinality": "cardinality_hint",
    "node_kind": "node_kind_hint",
    "value_type": "value_type_hint",
}
INTENT_FIELDS = {
    "assumptions",
    "cardinality",
    "clarification_question",
    "confirmed_facts",
    "evidence_gaps",
    "lifecycle",
    "node_kind",
    "ownership",
    "role",
    "scenario",
    "subject",
    "value_type",
}
OUTPUT_FILES = {
    "calibration-blueprint.json",
    "critic-report.json",
    "dataset-charter.json",
    "human-review-packet.json",
    "human-review.json",
    "manifest.json",
    "preflight-report.json",
    "promotion-checklist.json",
    "scenario-candidates.json",
}


def _load_blind_preflight():
    spec = importlib.util.spec_from_file_location(
        "treeguard_fire_m4_blind_preflight_for_calibration",
        BLIND_PREFLIGHT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load frozen blind-data preflight")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BLIND_PREFLIGHT = _load_blind_preflight()

from treeguard.hashing import canonical_digest  # noqa: E402
from treeguard.private_io import write_private_json  # noqa: E402
from treeguard.scenario_capability_validation import (  # noqa: E402
    CAPABILITY_ORACLE_REQUEST_POLICY_VERSION,
    CapabilityOracle,
    ScenarioCapabilityOverlay,
    verify_capability_oracle_against_reviewed_request,
)
from treeguard.scenario_validation import (  # noqa: E402
    ReviewedValidationScenario,
    ScenarioReviewAction,
)
from treeguard.tree_understanding import (  # noqa: E402
    ScenarioPreparationBatch,
    ScenarioPreparationBatchCandidate,
    ScenarioPreparationPlan,
    ScenarioPreparationProjection,
    TreeDiagnosticProfile,
    build_scenario_preparation_projection,
)
from treeguard.models import CanonicalTree  # noqa: E402


class M4CalibrationDataError(RuntimeError):
    """One aggregate-safe preparation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CalibrationExecutionContext:
    """One typed source replay paired with its proposed calibration Oracle."""

    scenario_ref: str
    candidate_item_sha256: str
    action: ScenarioReviewAction
    reviewed: ReviewedValidationScenario
    batch: ScenarioPreparationBatch
    batch_candidate: ScenarioPreparationBatchCandidate
    projection: ScenarioPreparationProjection
    plan: ScenarioPreparationPlan
    profile: TreeDiagnosticProfile
    tree: CanonicalTree
    oracle: CapabilityOracle


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _read_canonical(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        if _digest(payload) != expected_sha256:
            raise ValueError
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict) or canonical_json_bytes(value) != payload:
            raise ValueError
        return value
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise M4CalibrationDataError("CALIBRATION_SOURCE_FIXTURE_INVALID") from None


def _policy_source_sha256() -> str:
    try:
        return _digest(POLICY_SOURCE_PATH.read_bytes())
    except OSError:
        raise M4CalibrationDataError("CALIBRATION_CONTRACT_BINDING_INVALID") from None


def _transform_oracle(
    source_oracle: dict[str, Any],
    request: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    proposal = copy.deepcopy(source_oracle)
    changes: list[dict[str, str]] = []
    try:
        profiles = proposal["acceptable_intent_profiles"]
        for profile in profiles:
            profile_ref = profile["profile_ref"]
            source_expectations = {
                expectation["field_name"]: expectation
                for expectation in profile["field_expectations"]
            }
            if len(source_expectations) != len(profile["field_expectations"]):
                raise ValueError
            transformed_expectations = []
            for field_name in sorted(INTENT_FIELDS):
                expectation = source_expectations.get(field_name)
                if expectation is None:
                    if field_name not in UNBOUND_V1_FIELDS:
                        raise ValueError
                    expectation = {
                        "acceptable_values": [],
                        "field_name": field_name,
                        "policy": "NOT_COMPARED",
                    }
                    changes.append(
                        {
                            "field_name": field_name,
                            "from_policy": "MISSING",
                            "operation": "ADD_NOT_COMPARED_EXPECTATION",
                            "profile_ref": profile_ref,
                            "to_policy": "NOT_COMPARED",
                        }
                    )
                must_not_compare = field_name in UNBOUND_V1_FIELDS
                request_field = STRUCTURED_FIELDS.get(field_name)
                if request_field is not None:
                    request_value = request[request_field]
                    must_not_compare = (
                        request_value is None or request_value == "UNKNOWN"
                    )
                previous_policy = expectation["policy"]
                previous_values = expectation["acceptable_values"]
                if must_not_compare and (
                    previous_policy != "NOT_COMPARED" or previous_values
                ):
                    changes.append(
                        {
                            "field_name": field_name,
                            "from_policy": previous_policy,
                            "operation": "SET_TO_NOT_COMPARED",
                            "profile_ref": profile_ref,
                            "to_policy": "NOT_COMPARED",
                        }
                    )
                    expectation["policy"] = "NOT_COMPARED"
                    expectation["acceptable_values"] = []
                transformed_expectations.append(expectation)
            profile["field_expectations"] = transformed_expectations
    except (KeyError, TypeError, ValueError):
        raise M4CalibrationDataError("CALIBRATION_SOURCE_ORACLE_INVALID") from None
    return proposal, changes


def _request_payload(reviewed: ReviewedValidationScenario) -> dict[str, Any]:
    payload = reviewed.to_dict()["request"]
    if not isinstance(payload, dict):
        raise M4CalibrationDataError("CALIBRATION_SOURCE_REPLAY_FAILED")
    return payload


def _field_evidence_bindings(
    oracle: CapabilityOracle,
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for profile in oracle.acceptable_intent_profiles:
        for expectation in profile.field_expectations:
            expectation_payload = expectation.to_dict()
            field_name = expectation.field_name
            if (
                field_name in STRUCTURED_FIELDS
                and expectation.policy != "NOT_COMPARED"
            ):
                source_ref = STRUCTURED_FIELDS[field_name]
                source_value = request[source_ref]
                binding = {
                    "evidence_status": "PROPOSED_BOUND",
                    "relation": "SUPPORTS",
                    "source_kind": "STRUCTURED_REQUEST_FIELD",
                    "source_ref": source_ref,
                    "source_value_sha256": canonical_digest(source_value),
                }
            elif field_name in STRUCTURED_FIELDS:
                source_ref = STRUCTURED_FIELDS[field_name]
                binding = {
                    "evidence_status": "PROPOSED_UNBOUND",
                    "relation": "SUPPORT_NOT_ESTABLISHED",
                    "source_kind": "STRUCTURED_REQUEST_FIELD",
                    "source_ref": source_ref,
                    "source_value_sha256": canonical_digest(
                        request[source_ref]
                    ),
                }
            elif (
                field_name == "clarification_question"
                and expectation.policy != "NOT_COMPARED"
            ):
                binding = {
                    "evidence_status": "PROPOSED_BOUND",
                    "relation": "SUPPORTS",
                    "source_kind": "EXPECTED_ROUTE",
                    "source_ref": "expected_route",
                    "source_value_sha256": canonical_digest(
                        oracle.expected_route
                    ),
                }
            else:
                binding = {
                    "evidence_status": "PROPOSED_UNBOUND",
                    "relation": "SUPPORT_NOT_ESTABLISHED",
                    "source_kind": "NONE",
                    "source_ref": None,
                    "source_value_sha256": None,
                }
            bindings.append(
                {
                    **binding,
                    "expectation_sha256": canonical_digest(
                        expectation_payload
                    ),
                    "field_name": field_name,
                    "profile_ref": profile.profile_ref,
                }
            )
    return bindings


def _build_candidate_material() -> tuple[dict[str, Any], dict[str, Any]]:
    blind_manifest = _read_canonical(
        SOURCE_FIXTURE_DIR / "manifest.json",
        SOURCE_BLIND_MANIFEST_SHA256,
    )
    blind_sidecar = _read_canonical(
        SOURCE_FIXTURE_DIR / "oracle-sidecar.json",
        SOURCE_BLIND_SIDECAR_SHA256,
    )
    if (
        blind_manifest.get("oracle_sidecar_sha256")
        != SOURCE_BLIND_SIDECAR_SHA256
        or blind_manifest.get("dataset_ref") != "fictional-fire-m4-blind-v1"
        or blind_sidecar.get("dataset_ref") != "fictional-fire-m4-blind-v1"
        or blind_manifest.get("lifecycle_status") != "FROZEN"
        or blind_sidecar.get("lifecycle_status") != "FROZEN"
    ):
        raise M4CalibrationDataError("CALIBRATION_SOURCE_FIXTURE_INVALID")

    tree, profile, plan = BLIND_PREFLIGHT.load_bound_tree_profile_and_plan()
    try:
        batch = ScenarioPreparationBatch.from_dict(
            blind_sidecar["scenario_preparation_batch"],
            plan,
            profile,
            tree,
        )
        candidate_by_unit = {
            candidate.plan_unit_ref: candidate for candidate in batch.candidates
        }
    except (KeyError, TypeError, ValueError, RuntimeError):
        raise M4CalibrationDataError("CALIBRATION_SOURCE_REPLAY_FAILED") from None

    candidates: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    changed_expectation_count = 0
    bound_evidence_count = 0
    unbound_evidence_count = 0
    route_counts = {"CLARIFY": 0, "PROCEED": 0}
    for item in blind_sidecar.get("items", []):
        if item.get("execution_eligible") is not True:
            continue
        try:
            plan_unit_ref = item["plan_unit_ref"]
            candidate = candidate_by_unit[plan_unit_ref]
            projection = build_scenario_preparation_projection(
                tree, profile, plan, plan_unit_ref
            )
            action = ScenarioReviewAction.from_dict(item["action"])
            reviewed = ReviewedValidationScenario.from_dict(
                item["reviewed"],
                action,
                batch,
                candidate,
                projection,
                plan,
                profile,
                tree,
            )
            source_overlay = ScenarioCapabilityOverlay.from_dict(
                item["overlay"], reviewed, plan, tree
            )
            request_payload = _request_payload(reviewed)
            proposed_oracle, changes = _transform_oracle(
                source_overlay.oracle.to_dict(),
                request_payload,
            )
            typed_oracle = CapabilityOracle.from_dict(proposed_oracle)
            verify_capability_oracle_against_reviewed_request(
                typed_oracle,
                reviewed,
                tree,
            )
            evidence_bindings = _field_evidence_bindings(
                typed_oracle,
                request_payload,
            )
        except M4CalibrationDataError:
            raise
        except (KeyError, TypeError, ValueError, RuntimeError):
            raise M4CalibrationDataError(
                "CALIBRATION_PROPOSED_ORACLE_INVALID"
            ) from None

        route = typed_oracle.expected_route
        route_counts[route] += 1
        changed_expectation_count += len(changes)
        bound_evidence_count += sum(
            binding["evidence_status"] == "PROPOSED_BOUND"
            for binding in evidence_bindings
        )
        unbound_evidence_count += sum(
            binding["evidence_status"] == "PROPOSED_UNBOUND"
            for binding in evidence_bindings
        )
        if not any(
            binding["evidence_status"] == "PROPOSED_BOUND"
            for binding in evidence_bindings
        ):
            raise M4CalibrationDataError(
                "CALIBRATION_DISCRIMINATING_EVIDENCE_MISSING"
            )
        transformation_diff = {
            "allowed_operations": [
                "ADD_NOT_COMPARED_EXPECTATION",
                "SET_TO_NOT_COMPARED",
            ],
            "changes": changes,
        }
        candidate_payload = {
            "changed_field_names": sorted(
                {change["field_name"] for change in changes}
            ),
            "expected_route": route,
            "field_evidence_bindings": evidence_bindings,
            "field_evidence_bindings_sha256": canonical_digest(
                evidence_bindings
            ),
            "plan_unit_ref": plan_unit_ref,
            "proposed_oracle": typed_oracle.to_dict(),
            "proposed_oracle_sha256": canonical_digest(
                typed_oracle.to_dict()
            ),
            "scenario_ref": item["scenario_ref"],
            "source_action_hash": action.action_hash,
            "source_candidate_digest": item["candidate_digest"],
            "source_overlay_hash": source_overlay.overlay_hash,
            "source_reviewed_content_hash": (
                source_overlay.source_reviewed_content_hash
            ),
            "source_reviewed_hash": reviewed.reviewed_hash,
            "source_validation_request_sha256": canonical_digest(
                request_payload
            ),
            "transformation_diff": transformation_diff,
            "transformation_diff_sha256": canonical_digest(
                transformation_diff
            ),
        }
        candidate_payload["candidate_item_sha256"] = canonical_digest(
            candidate_payload
        )
        candidates.append(candidate_payload)
        review_items.append(
            {
                "changed_expectations": changes,
                "expected_route": route,
                "field_evidence_bindings": evidence_bindings,
                "plan_unit_ref": plan_unit_ref,
                "proposed_intent_profiles": typed_oracle.to_dict()[
                    "acceptable_intent_profiles"
                ],
                "request": request_payload,
                "review_questions": [
                    "STRUCTURED_HINT_EXPECTATIONS_MATCH_REQUEST",
                    "UNBOUND_V1_FIELDS_ARE_NOT_COMPARED",
                    "MISSING_V1_FIELDS_ARE_EXPLICITLY_NOT_COMPARED",
                    "UNKNOWN_OR_NULL_HINTS_ARE_NOT_COMPARED",
                    "CLARIFICATION_POLICY_MATCHES_ROUTE",
                    "UNCHANGED_DOWNSTREAM_ORACLE_REMAINS_ACCEPTABLE",
                ],
                "scenario_ref": item["scenario_ref"],
                "source_overlay_hash": source_overlay.overlay_hash,
                "unchanged_recommendation_oracle_hash": canonical_digest(
                    typed_oracle.to_dict()["recommendation"]
                ),
                "unchanged_retrieval_oracle_hash": canonical_digest(
                    typed_oracle.to_dict()["retrieval"]
                ),
            }
        )

    if (
        len(candidates) != 8
        or route_counts != {"CLARIFY": 1, "PROCEED": 7}
        or changed_expectation_count != 59
        or bound_evidence_count != 29
        or unbound_evidence_count != 67
    ):
        raise M4CalibrationDataError("CALIBRATION_ACCOUNTING_INVALID")

    policy_source_sha256 = _policy_source_sha256()
    common = {
        "dataset_ref": DATASET_REF,
        "derived_from_real": False,
        "evaluation_role": "CALIBRATION",
        "exposure_status": "EXPOSED",
        "fictional": True,
        "gate_eligible": False,
        "gold_eligible": False,
        "intended_use": "CALIBRATION_ONLY",
        "oracle_request_policy_source_sha256": policy_source_sha256,
        "oracle_request_policy_version": CAPABILITY_ORACLE_REQUEST_POLICY_VERSION,
        "patch_eligible": False,
        "run_ref": RUN_REF,
        "source_blind_manifest_sha256": SOURCE_BLIND_MANIFEST_SHA256,
        "source_blind_sidecar_sha256": SOURCE_BLIND_SIDECAR_SHA256,
        "source_candidate_batch_sha256": blind_manifest[
            "source_candidate_batch_sha256"
        ],
        "source_class": SOURCE_CLASS,
        "source_contract_versions": blind_manifest["contract_versions"],
        "source_feature_contract_commit": blind_manifest[
            "feature_contract_commit"
        ],
        "source_review_packet_sha256": blind_manifest[
            "source_review_packet_sha256"
        ],
        "source_scenario_plan_hash": blind_manifest["scenario_plan_hash"],
        "source_tree_fixture_sha256": blind_manifest["tree_fixture_sha256"],
        "source_tree_snapshot_hash": blind_manifest["tree_snapshot_hash"],
    }
    candidate_batch = {
        **common,
        "artifact_lifecycle_status": "MACHINE_VALIDATED",
        "candidate_count": len(candidates),
        "contract_integrity_status": "PASS",
        "execution_eligible": False,
        "items": candidates,
        "primary_role": "SEMANTIC_CHALLENGE",
        "review_status": "PENDING_HUMAN_REVIEW",
        "schema_version": "fire-m4-calibration-candidates.v1",
    }
    review_packet = {
        **common,
        "candidate_batch_sha256": _digest(canonical_json_bytes(candidate_batch)),
        "items": review_items,
        "review_scope": "INTENT_ORACLE_DELTA_AND_UNCHANGED_DOWNSTREAM_CONFIRMATION",
        "schema_version": "fire-m4-calibration-human-review-packet.v1",
    }
    accounting = {
        "candidate_count": len(candidates),
        "changed_expectation_count": changed_expectation_count,
        "bound_evidence_count": bound_evidence_count,
        "clarification_count": route_counts["CLARIFY"],
        "full_chain_count": route_counts["PROCEED"],
        "unbound_evidence_count": unbound_evidence_count,
    }
    return {"candidate_batch": candidate_batch, "review_packet": review_packet}, accounting


def _dataset_charter() -> dict[str, Any]:
    return {
        "dataset_ref": DATASET_REF,
        "derived_from_real": False,
        "evaluation_role": "CALIBRATION",
        "exposure_status": "EXPOSED",
        "fictional": True,
        "gate_eligible": False,
        "gold_eligible": False,
        "non_goals": [
            "NOT_A_GATING_HOLDOUT",
            "NOT_PRODUCTION_ACCURACY_EVIDENCE",
            "NOT_REAL_DOMAIN_GOLD",
            "NOT_AUTHORITY_TO_PATCH_ANY_TREE",
        ],
        "patch_eligible": False,
        "primary_role": "SEMANTIC_CHALLENGE",
        "purpose": "CALIBRATE_M4_V1_REQUEST_OBSERVABLE_INTENT_SCORING",
        "review_budget": {
            "candidate_limit": 8,
            "dual_review_limit": 0,
            "required_review_count": 8,
            "time_limit_minutes": 60,
        },
        "run_ref": RUN_REF,
        "schema_version": "fire-m4-calibration-dataset-charter.v1",
        "source_blind_manifest_sha256": SOURCE_BLIND_MANIFEST_SHA256,
        "source_blind_sidecar_sha256": SOURCE_BLIND_SIDECAR_SHA256,
        "source_class": SOURCE_CLASS,
        "stop_rules": {
            "blocking_boundary_findings": 1,
            "material_review_errors": 1,
            "maximum_revision_rounds": 2,
        },
    }


def _calibration_blueprint() -> dict[str, Any]:
    return {
        "allowed_transformation": {
            "acceptable_values_after": [],
            "field_allowlist": sorted(UNBOUND_V1_FIELDS),
            "conditional_structured_field_allowlist": sorted(
                STRUCTURED_FIELDS
            ),
            "existing_field_name_immutable": True,
            "missing_unbound_field_may_be_added": True,
            "operations": [
                "ADD_NOT_COMPARED_EXPECTATION",
                "SET_TO_NOT_COMPARED",
            ],
            "policy_after": "NOT_COMPARED",
            "result_order": "FIELD_NAME_ASCENDING",
        },
        "dataset_ref": DATASET_REF,
        "forbidden_changes": [
            "REQUEST_BYTES",
            "EXPECTED_ROUTE",
            "RETRIEVAL_ORACLE",
            "RECOMMENDATION_ORACLE",
            "SOURCE_ACTION_OR_REVIEWED_BYTES",
            "STABLE_TARGET_IDENTITIES",
        ],
        "required_evidence": {
            "clarification_question": "EXPECTED_ROUTE",
            "structured_fields": STRUCTURED_FIELDS,
            "unbound_fields": "PROPOSED_UNBOUND_REQUIRES_HUMAN_CONFIRMATION",
        },
        "review_scope": "ALL_EIGHT_MODIFIED_ORACLES",
        "schema_version": "fire-m4-calibration-blueprint.v1",
    }


def build_artifacts() -> dict[str, bytes]:
    charter_bytes = canonical_json_bytes(_dataset_charter())
    blueprint_bytes = canonical_json_bytes(_calibration_blueprint())
    material, accounting = _build_candidate_material()
    material["candidate_batch"].update(
        {
            "calibration_blueprint_sha256": _digest(blueprint_bytes),
            "dataset_charter_sha256": _digest(charter_bytes),
        }
    )
    candidate_bytes = canonical_json_bytes(material["candidate_batch"])
    material["review_packet"].update(
        {
            "calibration_blueprint_sha256": _digest(blueprint_bytes),
            "candidate_batch_sha256": _digest(candidate_bytes),
            "dataset_charter_sha256": _digest(charter_bytes),
        }
    )
    review_packet_bytes = canonical_json_bytes(material["review_packet"])
    critic = {
        "blocking_finding_count": 0,
        "candidate_batch_sha256": _digest(candidate_bytes),
        "critic_authority": "NON_AUTHORITATIVE",
        "dataset_ref": DATASET_REF,
        "finding_counts": {},
        "high_risk_human_review_count": accounting["candidate_count"],
        "review_flags": ["ALL_MODIFIED_ORACLES_REQUIRE_HUMAN_REVIEW"],
        "schema_version": "fire-m4-calibration-critic-report.v1",
        "source_class": "DETERMINISTIC_REPORT",
        "status": "PASS_WITH_REVIEW_REQUIRED",
    }
    critic_bytes = canonical_json_bytes(critic)
    manifest = {
        "artifact_lifecycle_status": "MACHINE_VALIDATED",
        "calibration_blueprint_file": "calibration-blueprint.json",
        "calibration_blueprint_sha256": _digest(blueprint_bytes),
        "candidate_count": accounting["candidate_count"],
        "candidate_file": "scenario-candidates.json",
        "candidate_sha256": _digest(candidate_bytes),
        "dataset_ref": DATASET_REF,
        "derived_from_real": False,
        "dataset_charter_file": "dataset-charter.json",
        "dataset_charter_sha256": _digest(charter_bytes),
        "evaluation_role": "CALIBRATION",
        "contract_integrity_status": "PASS",
        "execution_eligible": False,
        "exposure_status": "EXPOSED",
        "fictional": True,
        "gate_eligible": False,
        "gold_eligible": False,
        "human_review_packet_file": "human-review-packet.json",
        "human_review_packet_sha256": _digest(review_packet_bytes),
        "intended_use": "CALIBRATION_ONLY",
        "limitations": [
            "EXPOSED_NON_BLIND_CALIBRATION_ONLY",
            "NOT_GATING_HOLDOUT",
            "CLEANROOM_SYNTHETIC_NOT_GOLD",
            "NO_PATCH_OR_PRODUCTION_WRITE_AUTHORITY",
        ],
        "critic_report_file": "critic-report.json",
        "critic_report_sha256": _digest(critic_bytes),
        "oracle_request_policy_source_sha256": _policy_source_sha256(),
        "oracle_request_policy_version": CAPABILITY_ORACLE_REQUEST_POLICY_VERSION,
        "patch_eligible": False,
        "primary_role": "SEMANTIC_CHALLENGE",
        "review_status": "PENDING_HUMAN_REVIEW",
        "run_ref": RUN_REF,
        "schema_version": "fire-m4-calibration-candidate-manifest.v1",
        "source_blind_manifest_sha256": SOURCE_BLIND_MANIFEST_SHA256,
        "source_blind_sidecar_sha256": SOURCE_BLIND_SIDECAR_SHA256,
        "source_candidate_batch_sha256": material["candidate_batch"][
            "source_candidate_batch_sha256"
        ],
        "source_class": SOURCE_CLASS,
        "source_contract_versions": material["candidate_batch"][
            "source_contract_versions"
        ],
        "source_feature_contract_commit": material["candidate_batch"][
            "source_feature_contract_commit"
        ],
        "source_review_packet_sha256": material["candidate_batch"][
            "source_review_packet_sha256"
        ],
        "source_scenario_plan_hash": material["candidate_batch"][
            "source_scenario_plan_hash"
        ],
        "source_tree_fixture_sha256": material["candidate_batch"][
            "source_tree_fixture_sha256"
        ],
        "source_tree_snapshot_hash": material["candidate_batch"][
            "source_tree_snapshot_hash"
        ],
    }
    manifest_bytes = canonical_json_bytes(manifest)
    report = {
        **accounting,
        "dataset_ref": DATASET_REF,
        "finding_counts": {},
        "review_status": "PENDING_HUMAN_REVIEW",
        "schema_version": "fire-m4-calibration-preflight-report.v1",
        "source_class": "DETERMINISTIC_REPORT",
        "status": "PASS",
        "checks": [
            "SOURCE_BLIND_BYTES_IMMUTABLE",
            "SOURCE_TREE_PLAN_AND_REVIEW_REPLAY",
            "ORACLE_DELTA_ALLOWLIST",
            "REQUEST_OBSERVABLE_INTENT_POLICY",
            "DOWNSTREAM_ORACLE_UNCHANGED",
            "CANDIDATE_ACCOUNTING",
        ],
    }
    human_review = {
        "accepted_count": 0,
        "candidate_sha256": _digest(candidate_bytes),
        "candidate_schema_version": material["candidate_batch"][
            "schema_version"
        ],
        "dataset_ref": DATASET_REF,
        "decisions": [],
        "elapsed_minutes": None,
        "human_review_packet_sha256": _digest(review_packet_bytes),
        "human_review_packet_schema_version": material["review_packet"][
            "schema_version"
        ],
        "oracle_request_policy_version": CAPABILITY_ORACLE_REQUEST_POLICY_VERSION,
        "rejected_count": 0,
        "review_round": 2,
        "review_status": "PENDING_HUMAN_REVIEW",
        "reviewed_count": 0,
        "reviewer_ref": None,
        "schema_version": "fire-m4-calibration-human-review.v1",
    }
    checklist = {
        "candidate_sha256": _digest(candidate_bytes),
        "human_review_packet_sha256": _digest(review_packet_bytes),
        "checks": {
            "candidate_machine_validated": True,
            "critic_has_no_blocking_finding": True,
            "feature_contract_committed": False,
            "formal_fixture_promoted": False,
            "human_review_complete": False,
            "promotion_explicitly_approved": False,
            "source_blind_fixture_unchanged": True,
        },
        "dataset_ref": DATASET_REF,
        "schema_version": "fire-m4-calibration-promotion-checklist.v1",
        "status": "BLOCKED_PENDING_HUMAN_REVIEW",
    }
    return {
        "calibration-blueprint.json": blueprint_bytes,
        "critic-report.json": critic_bytes,
        "dataset-charter.json": charter_bytes,
        "human-review-packet.json": review_packet_bytes,
        "human-review.json": canonical_json_bytes(human_review),
        "manifest.json": manifest_bytes,
        "preflight-report.json": canonical_json_bytes(report),
        "promotion-checklist.json": canonical_json_bytes(checklist),
        "scenario-candidates.json": candidate_bytes,
    }


def load_calibration_execution_contexts() -> tuple[CalibrationExecutionContext, ...]:
    """Replay all eight candidate sources into typed calibration contexts."""

    artifacts = build_artifacts()
    try:
        candidate_batch = json.loads(
            artifacts["scenario-candidates.json"].decode("utf-8")
        )
        blind_sidecar = _read_canonical(
            SOURCE_FIXTURE_DIR / "oracle-sidecar.json",
            SOURCE_BLIND_SIDECAR_SHA256,
        )
        tree, profile, plan = BLIND_PREFLIGHT.load_bound_tree_profile_and_plan()
        batch = ScenarioPreparationBatch.from_dict(
            blind_sidecar["scenario_preparation_batch"],
            plan,
            profile,
            tree,
        )
        source_items = {
            item["plan_unit_ref"]: item
            for item in blind_sidecar["items"]
            if item["execution_eligible"] is True
        }
        candidate_by_unit = {
            candidate.plan_unit_ref: candidate for candidate in batch.candidates
        }
        contexts: list[CalibrationExecutionContext] = []
        for candidate_item in candidate_batch["items"]:
            plan_unit_ref = candidate_item["plan_unit_ref"]
            source_item = source_items[plan_unit_ref]
            batch_candidate = candidate_by_unit[plan_unit_ref]
            projection = build_scenario_preparation_projection(
                tree,
                profile,
                plan,
                plan_unit_ref,
            )
            action = ScenarioReviewAction.from_dict(source_item["action"])
            reviewed = ReviewedValidationScenario.from_dict(
                source_item["reviewed"],
                action,
                batch,
                batch_candidate,
                projection,
                plan,
                profile,
                tree,
            )
            oracle = CapabilityOracle.from_dict(candidate_item["proposed_oracle"])
            verify_capability_oracle_against_reviewed_request(
                oracle,
                reviewed,
                tree,
            )
            if (
                candidate_item["source_action_hash"] != action.action_hash
                or candidate_item["source_reviewed_hash"] != reviewed.reviewed_hash
                or candidate_item["proposed_oracle_sha256"]
                != canonical_digest(oracle.to_dict())
                or candidate_item["candidate_item_sha256"]
                != canonical_digest(
                    {
                        key: value
                        for key, value in candidate_item.items()
                        if key != "candidate_item_sha256"
                    }
                )
            ):
                raise ValueError
            contexts.append(
                CalibrationExecutionContext(
                    scenario_ref=candidate_item["scenario_ref"],
                    candidate_item_sha256=candidate_item[
                        "candidate_item_sha256"
                    ],
                    action=action,
                    reviewed=reviewed,
                    batch=batch,
                    batch_candidate=batch_candidate,
                    projection=projection,
                    plan=plan,
                    profile=profile,
                    tree=tree,
                    oracle=oracle,
                )
            )
    except M4CalibrationDataError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        raise M4CalibrationDataError(
            "CALIBRATION_EXECUTION_CONTEXT_INVALID"
        ) from None
    if len(contexts) != 8:
        raise M4CalibrationDataError("CALIBRATION_ACCOUNTING_INVALID")
    return tuple(contexts)


def prepare(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    output_path = Path(output_dir)
    artifacts = build_artifacts()
    temporary_path: Path | None = None
    try:
        output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.lstat(output_path)
        except FileNotFoundError:
            pass
        else:
            raise M4CalibrationDataError(
                "CALIBRATION_STAGING_ALREADY_EXISTS"
            )
        temporary_path = output_path.parent / (
            f".{output_path.name}.treeguard-{secrets.token_hex(12)}.tmp"
        )
        temporary_path.mkdir(mode=0o700, exist_ok=False)
        os.chmod(temporary_path, 0o700)
        for name, payload in artifacts.items():
            path = temporary_path / name
            if not write_private_json(
                path,
                json.loads(payload.decode("utf-8")),
            ):
                raise M4CalibrationDataError(
                    "CALIBRATION_STAGING_WRITE_FAILED"
                )
        report = validate_staging(temporary_path)
        try:
            os.lstat(output_path)
        except FileNotFoundError:
            pass
        else:
            raise M4CalibrationDataError(
                "CALIBRATION_STAGING_ALREADY_EXISTS"
            )
        os.rename(temporary_path, output_path)
        temporary_path = None
    except FileExistsError:
        raise M4CalibrationDataError(
            "CALIBRATION_STAGING_ALREADY_EXISTS"
        ) from None
    except M4CalibrationDataError:
        raise
    except OSError:
        raise M4CalibrationDataError("CALIBRATION_STAGING_WRITE_FAILED") from None
    finally:
        if temporary_path is not None:
            try:
                shutil.rmtree(temporary_path)
            except OSError:
                pass
    return report


def validate_staging(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    output_path = Path(output_dir)
    expected = build_artifacts()
    try:
        entries = tuple(output_path.iterdir())
        if (
            {path.name for path in entries} != OUTPUT_FILES
            or any(path.is_symlink() or not path.is_file() for path in entries)
            or stat.S_IMODE(output_path.stat().st_mode) != 0o700
            or any(stat.S_IMODE(path.stat().st_mode) != 0o600 for path in entries)
        ):
            raise M4CalibrationDataError("CALIBRATION_STAGING_FILES_INVALID")
        for name, payload in expected.items():
            if (output_path / name).read_bytes() != payload:
                raise M4CalibrationDataError("CALIBRATION_STAGING_DIGEST_MISMATCH")
        report = json.loads((output_path / "preflight-report.json").read_text())
    except M4CalibrationDataError:
        raise
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise M4CalibrationDataError("CALIBRATION_STAGING_INVALID") from None
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = (
            validate_staging(args.output_dir)
            if args.check
            else prepare(args.output_dir)
        )
    except M4CalibrationDataError as error:
        print(
            json.dumps(
                {
                    "dataset_ref": DATASET_REF,
                    "finding_counts": {error.code: 1},
                    "schema_version": "fire-m4-calibration-preflight-report.v1",
                    "source_class": "DETERMINISTIC_REPORT",
                    "status": "FAIL",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
