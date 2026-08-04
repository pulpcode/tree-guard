"""In-memory, development-only Retrieval Oracle calibration for exposed M5 data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree


POLICY_VERSION = "treeguard.fire-m5-request-observable-retrieval-oracle.v2"
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TARGET_POLICIES = {
    "SOURCE_ORACLE_RETAINED",
    "REQUEST_OBSERVABLE_CLASS",
    "EXPLICIT_EMPTY",
}


class RetrievalCalibrationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class RetrievalCalibrationItem:
    scenario_ref: str
    target_policy: str
    acceptable_node_ids: tuple[str, ...]
    allowed_statuses: tuple[str, ...]
    top_k: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenario_ref, str)
            or not self.scenario_ref
            or self.target_policy not in _TARGET_POLICIES
            or self.acceptable_node_ids
            != tuple(sorted(set(self.acceptable_node_ids)))
            or any(
                not isinstance(node_id, str) or not node_id
                for node_id in self.acceptable_node_ids
            )
            or self.allowed_statuses != tuple(sorted(set(self.allowed_statuses)))
            or any(
                not isinstance(status, str) or not status
                for status in self.allowed_statuses
            )
            or not isinstance(self.top_k, int)
            or isinstance(self.top_k, bool)
            or self.top_k < 1
            or self.top_k > 20
        ):
            raise ValueError("retrieval calibration item is invalid")
        if self.target_policy == "EXPLICIT_EMPTY" and self.acceptable_node_ids:
            raise ValueError("explicit-empty calibration item cannot contain targets")
        if self.target_policy != "EXPLICIT_EMPTY" and not self.acceptable_node_ids:
            raise ValueError("target-bearing calibration item requires targets")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_ref": self.scenario_ref,
            "target_policy": self.target_policy,
            "acceptable_node_ids": list(self.acceptable_node_ids),
            "allowed_statuses": list(self.allowed_statuses),
            "top_k": self.top_k,
        }


@dataclass(frozen=True, slots=True)
class RetrievalCalibrationOracle:
    source_tree_digest: str
    items: tuple[RetrievalCalibrationItem, ...]
    oracle_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_tree_digest, str)
            or _DIGEST.fullmatch(self.source_tree_digest) is None
            or not isinstance(self.oracle_digest, str)
            or _DIGEST.fullmatch(self.oracle_digest) is None
            or not isinstance(self.items, tuple)
            or not self.items
            or any(
                not isinstance(item, RetrievalCalibrationItem) for item in self.items
            )
        ):
            raise ValueError("retrieval calibration oracle is invalid")
        refs = tuple(item.scenario_ref for item in self.items)
        if refs != tuple(sorted(set(refs))):
            raise ValueError("retrieval calibration items are not canonical")
        if self.oracle_digest != canonical_digest(self._payload()):
            raise ValueError("retrieval calibration digest does not match its payload")

    def _payload(self) -> dict[str, Any]:
        return {
            "policy_version": POLICY_VERSION,
            "source_tree_digest": self.source_tree_digest,
            "calibration_only": True,
            "production_qualification": False,
            "gold_eligible": False,
            "gate_eligible": False,
            "items": [item.to_dict() for item in self.items],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["oracle_digest"] = self.oracle_digest
        return payload

    def aggregate_report(self) -> dict[str, Any]:
        policy_counts: dict[str, int] = {}
        target_counts: dict[str, int] = {}
        for item in self.items:
            policy_counts[item.target_policy] = (
                policy_counts.get(item.target_policy, 0) + 1
            )
            target_counts[item.target_policy] = target_counts.get(
                item.target_policy, 0
            ) + len(item.acceptable_node_ids)
        return {
            "report_version": "fire-m5-retrieval-calibration-oracle.v2",
            "status": "PASS",
            "policy_version": POLICY_VERSION,
            "calibration_only": True,
            "production_qualification": False,
            "gold_eligible": False,
            "gate_eligible": False,
            "item_count": len(self.items),
            "policy_counts": dict(sorted(policy_counts.items())),
            "target_counts": dict(sorted(target_counts.items())),
        }


def build_retrieval_calibration_oracle_v2(
    formal_scenarios: tuple[dict[str, Any], ...],
    oracle_by_ref: dict[str, dict[str, Any]],
    tree: CanonicalTree,
) -> RetrievalCalibrationOracle:
    """Reconcile exposed broad-class requests without mutating the source Oracle."""

    if not isinstance(tree, CanonicalTree) or tree.source_map_type != "resource":
        raise RetrievalCalibrationError("RETRIEVAL_CALIBRATION_SOURCE_INVALID")
    if len(formal_scenarios) != 18:
        raise RetrievalCalibrationError("RETRIEVAL_CALIBRATION_DENOMINATOR_INVALID")
    items = []
    for scenario in sorted(formal_scenarios, key=lambda item: item["scenario_ref"]):
        if scenario.get("expected_route") != "PROCEED":
            raise RetrievalCalibrationError("RETRIEVAL_CALIBRATION_ROUTE_INVALID")
        scenario_ref = scenario["scenario_ref"]
        oracle = oracle_by_ref.get(scenario_ref)
        if oracle is None:
            raise RetrievalCalibrationError("RETRIEVAL_CALIBRATION_ORACLE_MISSING")
        retrieval = oracle["capability_oracle"]["retrieval"]
        original_ids = tuple(sorted(retrieval["acceptable_node_ids"]))
        if scenario["coverage_cell"] == "P04":
            acceptable_ids = _request_observable_class_targets(scenario, tree)
            if not set(original_ids) < set(acceptable_ids):
                raise RetrievalCalibrationError(
                    "RETRIEVAL_CALIBRATION_CLASS_NOT_EXPANDED"
                )
            target_policy = "REQUEST_OBSERVABLE_CLASS"
        elif original_ids:
            acceptable_ids = original_ids
            target_policy = "SOURCE_ORACLE_RETAINED"
        else:
            acceptable_ids = ()
            target_policy = "EXPLICIT_EMPTY"
        items.append(
            RetrievalCalibrationItem(
                scenario_ref=scenario_ref,
                target_policy=target_policy,
                acceptable_node_ids=acceptable_ids,
                allowed_statuses=tuple(sorted(retrieval["allowed_statuses"])),
                top_k=retrieval["top_k"],
            )
        )
    payload = {
        "policy_version": POLICY_VERSION,
        "source_tree_digest": tree.snapshot_hash,
        "calibration_only": True,
        "production_qualification": False,
        "gold_eligible": False,
        "gate_eligible": False,
        "items": [item.to_dict() for item in items],
    }
    return RetrievalCalibrationOracle(
        source_tree_digest=tree.snapshot_hash,
        items=tuple(items),
        oracle_digest=canonical_digest(payload),
    )


def _request_observable_class_targets(
    scenario: dict[str, Any], tree: CanonicalTree
) -> tuple[str, ...]:
    request = scenario["request"]
    requirement_text = request["requirement_text"]
    node_kind = request["node_kind_hint"]
    if (
        not isinstance(requirement_text, str)
        or not requirement_text
        or node_kind == "UNKNOWN"
    ):
        raise RetrievalCalibrationError(
            "RETRIEVAL_CALIBRATION_CLASS_SIGNAL_INVALID"
        )
    eligible_nodes = tuple(
        node
        for node in tree.nodes
        if node.kind == node_kind and node.kind != "UNSUPPORTED"
    )
    fragments = set()
    for run in _CJK_RUN.findall(requirement_text):
        maximum = min(12, len(run))
        for length in range(4, maximum + 1):
            fragments.update(
                run[index : index + length]
                for index in range(len(run) - length + 1)
            )
    candidates = []
    for fragment in fragments:
        matching_ids = tuple(
            sorted(node.node_id for node in eligible_nodes if fragment in node.name)
        )
        if len(matching_ids) >= 2:
            candidates.append((fragment, matching_ids))
    if not candidates:
        raise RetrievalCalibrationError(
            "RETRIEVAL_CALIBRATION_CLASS_SIGNAL_MISSING"
        )
    fragment, matching_ids = min(
        candidates,
        key=lambda item: (-len(item[0]), -len(item[1]), item[0]),
    )
    if len(fragment) < 4:
        raise RetrievalCalibrationError(
            "RETRIEVAL_CALIBRATION_CLASS_SIGNAL_INVALID"
        )
    return matching_ids


__all__ = [
    "POLICY_VERSION",
    "RetrievalCalibrationError",
    "RetrievalCalibrationItem",
    "RetrievalCalibrationOracle",
    "build_retrieval_calibration_oracle_v2",
]
