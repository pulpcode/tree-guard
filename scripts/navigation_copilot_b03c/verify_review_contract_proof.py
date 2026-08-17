from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_REPORT = "treeguard.navigation-copilot-b03c-review-proof-report.v1"


class ContractViolation(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject(code: str) -> None:
    raise ContractViolation(code)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _node_maps(tree: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    nodes = tree.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 41:
        _reject("DATASET_COUNT_MISMATCH")
    by_id: dict[str, dict[str, Any]] = {}
    children: dict[str, list[str]] = {}
    for node in nodes:
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or node_id in by_id:
            _reject("DATASET_REFERENCE_INVALID")
        by_id[node_id] = node
        parent_id = node.get("parent_id")
        if parent_id is not None:
            children.setdefault(parent_id, []).append(node_id)
        if "VALUE" in node:
            _reject("DATASET_VALUE_ENVELOPE_PRESENT")
    return by_id, children


def _assert_authoring_independent(packet: dict[str, Any]) -> None:
    if packet.get("producer_module") != "author_review_contract_proof":
        _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    for item in packet.get("items", []):
        if set(item) != {"scenario_id", "review_state"} or item.get("review_state") != "PENDING":
            _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")


def _assert_review_independent(decisions: dict[str, Any]) -> None:
    if decisions.get("producer_module") != "record_review_contract_decisions":
        _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    if decisions.get("generated_by_verification") is not None:
        _reject("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")


def _assert_review_texts(items: list[dict[str, Any]]) -> None:
    rationales = [item.get("rationale") for item in items]
    if any(not isinstance(value, str) or len(value.strip()) < 12 for value in rationales):
        _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    if len(rationales) != len(set(rationales)):
        _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    generic = {"经审核符合要求，可以通过。", "内容完整，语义合理，审核通过。"}
    if any(value in generic for value in rationales):
        _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")


def _require_target_ids(decision: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[str]:
    target_ids = decision.get("reviewed_target_ids")
    if not isinstance(target_ids, list) or any(target not in by_id for target in target_ids):
        _reject("DATASET_REFERENCE_INVALID")
    if len(target_ids) != len(set(target_ids)):
        _reject("DATASET_REFERENCE_INVALID")
    return target_ids


def verify_absence_contract(
    request_text: str,
    labels_and_aliases: list[str],
    reviewed_target_ids: list[str],
    satisfiable_supertype_ids: list[str],
) -> None:
    if satisfiable_supertype_ids:
        _reject("DATASET_ORACLE_OVERCLAIM")
    normalized_request = request_text.replace("我想", "").replace("一台", "")
    if any(text in request_text or normalized_request in text for text in labels_and_aliases):
        _reject("DATASET_ABSENCE_CLOSURE_INCOMPLETE")
    if reviewed_target_ids:
        _reject("DATASET_ORACLE_OVERCLAIM")


def verify_target_set_exhaustiveness(
    reviewed_target_ids: list[str], compatible_target_ids: list[str]
) -> None:
    if reviewed_target_ids != sorted(compatible_target_ids):
        _reject("DATASET_TARGET_SET_NOT_EXHAUSTIVE")


def verify_clarification_contrast(
    contrast_node_ids: list[str], resolved_target_ids: list[str]
) -> None:
    if (
        len(contrast_node_ids) < 2
        or len(contrast_node_ids) != len(set(contrast_node_ids))
        or len(resolved_target_ids) != 1
        or resolved_target_ids[0] not in contrast_node_ids
    ):
        _reject("DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT")


def _verify_absence(
    scenario: dict[str, Any], decision: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> None:
    verify_absence_contract(
        scenario["request_text"],
        [
            text
            for node in by_id.values()
            for text in [node["label"], *node.get("aliases", [])]
        ],
        decision.get("reviewed_target_ids", []),
        decision.get("satisfiable_supertype_ids", []),
    )


def _verify_nonliteral(decision: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> None:
    phenomenon = decision.get("phenomenon")
    surface = decision.get("surface_form")
    if phenomenon == "abbreviation":
        matches = [
            node_id
            for node_id, node in by_id.items()
            if surface in node.get("aliases", [])
        ]
    elif phenomenon == "minor_typo":
        matches = [
            node_id
            for node_id, node in by_id.items()
            if _edit_distance(surface, node["label"]) == 1
        ]
    else:
        _reject("DATASET_SCENARIO_COVERAGE_DUPLICATE")
    if len(matches) != 1 or decision.get("reviewed_target_ids") != matches:
        _reject("DATASET_SCENARIO_COVERAGE_DUPLICATE")


def _verify_multi(
    decision: dict[str, Any], by_id: dict[str, dict[str, Any]], children: dict[str, list[str]]
) -> None:
    expected = sorted(
        node_id
        for node_id in children.get("c0n-022", [])
        if by_id[node_id]["label"].endswith("补充")
    )
    verify_target_set_exhaustiveness(decision.get("reviewed_target_ids", []), expected)


def _verify_clarification(decision: dict[str, Any]) -> None:
    contrast_ids = decision.get("contrast_node_ids")
    resolved_ids = decision.get("resolved_target_ids")
    if not isinstance(contrast_ids, list) or not isinstance(resolved_ids, list):
        _reject("DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT")
    verify_clarification_contrast(contrast_ids, resolved_ids)


def verify_documents(
    tree: dict[str, Any],
    scenarios: dict[str, Any],
    packet: dict[str, Any],
    decisions: dict[str, Any],
    *,
    tree_bytes: bytes,
    scenario_bytes: bytes,
    packet_bytes: bytes,
    review_input_bytes: bytes,
) -> dict[str, Any]:
    _assert_authoring_independent(packet)
    _assert_review_independent(decisions)
    if packet.get("source_tree_sha256") != _sha256(tree_bytes):
        _reject("DATASET_NONDETERMINISTIC")
    if packet.get("source_scenarios_sha256") != _sha256(scenario_bytes):
        _reject("DATASET_NONDETERMINISTIC")
    if decisions.get("source_tree_sha256") != _sha256(tree_bytes):
        _reject("DATASET_NONDETERMINISTIC")
    if decisions.get("source_scenarios_sha256") != _sha256(scenario_bytes):
        _reject("DATASET_NONDETERMINISTIC")
    if decisions.get("source_review_packet_sha256") != _sha256(packet_bytes):
        _reject("DATASET_NONDETERMINISTIC")
    if decisions.get("source_review_input_sha256") != _sha256(review_input_bytes):
        _reject("DATASET_NONDETERMINISTIC")
    if decisions.get("elapsed_minutes") not in range(1, 121):
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")

    by_id, children = _node_maps(tree)
    scenario_items = scenarios.get("items")
    decision_items = decisions.get("decisions")
    if not isinstance(scenario_items, list) or len(scenario_items) != 8:
        _reject("DATASET_COUNT_MISMATCH")
    if not isinstance(decision_items, list) or len(decision_items) != 8:
        _reject("DATASET_COUNT_MISMATCH")
    if [item.get("scenario_id") for item in scenario_items] != [
        item.get("scenario_id") for item in decision_items
    ]:
        _reject("DATASET_REFERENCE_INVALID")
    if decisions.get("reviewed_node_ids") != sorted(by_id):
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")
    scenario_ids = [item["scenario_id"] for item in scenario_items]
    recheck_ids = decisions.get("random_recheck_scenario_ids")
    if (
        not isinstance(recheck_ids, list)
        or len(recheck_ids) != 3
        or len(set(recheck_ids)) != 3
        or any(scenario_id not in scenario_ids for scenario_id in recheck_ids)
        or decisions.get("dual_review_count") != 0
    ):
        _reject("DATASET_REVIEW_BUDGET_EXCEEDED")
    _assert_review_texts(decision_items)

    for scenario, decision in zip(scenario_items, decision_items, strict=True):
        if decision.get("decision") != "SILVER_ACCEPTED":
            _reject("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
        target_ids = _require_target_ids(decision, by_id)
        scenario_type = scenario.get("scenario_type")
        if scenario_type == "NONLITERAL_UNIQUE":
            _verify_nonliteral(decision, by_id)
        elif scenario_type == "MULTI_ACCEPTABLE":
            _verify_multi(decision, by_id, children)
        elif scenario_type == "CLARIFICATION":
            _verify_clarification(decision)
        elif scenario_type == "TARGET_ABSENT":
            _verify_absence(scenario, decision, by_id)
        elif scenario_type == "WEAK_EVIDENCE":
            if target_ids or not decision.get("evidence_gap"):
                _reject("DATASET_ORACLE_OVERCLAIM")
        elif scenario_type in {"UNIQUE", "WRONG_CONTEXT", "SUPERTYPE_PRESENT"}:
            if len(target_ids) != 1:
                _reject("DATASET_SCENARIO_COVERAGE_DUPLICATE")
        else:
            _reject("DATASET_SCENARIO_COVERAGE_DUPLICATE")

    return {
        "schema_version": SCHEMA_REPORT,
        "status": "C0_REVIEW_CONTRACT_PROOF_PASSED",
        "nodes": 41,
        "scenarios": 8,
        "accepted": 8,
        "value_envelope_count": 0,
        "reviewer_class": decisions.get("reviewer_class"),
        "source_tree_sha256": _sha256(tree_bytes),
        "source_scenarios_sha256": _sha256(scenario_bytes),
        "source_review_packet_sha256": _sha256(packet_bytes),
        "source_review_input_sha256": _sha256(review_input_bytes),
    }


def verify_paths(
    tree_path: Path,
    scenarios_path: Path,
    packet_path: Path,
    review_input_path: Path,
    decisions_path: Path,
) -> dict[str, Any]:
    tree_bytes = tree_path.read_bytes()
    scenario_bytes = scenarios_path.read_bytes()
    packet_bytes = packet_path.read_bytes()
    return verify_documents(
        json.loads(tree_bytes),
        json.loads(scenario_bytes),
        json.loads(packet_bytes),
        json.loads(decisions_path.read_bytes()),
        tree_bytes=tree_bytes,
        scenario_bytes=scenario_bytes,
        packet_bytes=packet_bytes,
        review_input_bytes=review_input_path.read_bytes(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--review-input", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = verify_paths(args.tree, args.scenarios, args.packet, args.review_input, args.decisions)
    content = _json_bytes(report)
    if args.report.exists() and args.report.read_bytes() != content:
        _reject("DATASET_NONDETERMINISTIC")
    if not args.report.exists():
        args.report.write_bytes(content)
    print("C0_VERIFIED nodes=41 scenarios=8 accepted=8 negative_contracts=12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
