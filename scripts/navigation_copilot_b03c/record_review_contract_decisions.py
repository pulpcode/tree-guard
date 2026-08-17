from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_INPUT = "treeguard.navigation-copilot-b03c-review-input.v1"
SCHEMA_DECISIONS = "treeguard.navigation-copilot-b03c-review-decisions.v1"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def record_decisions(
    tree_path: Path,
    scenarios_path: Path,
    packet_path: Path,
    reviewer_input_path: Path,
    output_path: Path,
) -> None:
    tree_bytes = tree_path.read_bytes()
    scenario_bytes = scenarios_path.read_bytes()
    packet = json.loads(packet_path.read_bytes())
    review_input = json.loads(reviewer_input_path.read_bytes())
    if review_input.get("schema_version") != SCHEMA_INPUT:
        raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    if packet.get("source_tree_sha256") != _sha256(tree_bytes):
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    if packet.get("source_scenarios_sha256") != _sha256(scenario_bytes):
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    expected_source_digests = {
        "source_tree_sha256": _sha256(tree_bytes),
        "source_scenarios_sha256": _sha256(scenario_bytes),
        "source_review_packet_sha256": _sha256(packet_path.read_bytes()),
    }
    if any(review_input.get(key) != value for key, value in expected_source_digests.items()):
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    pending_ids = [item.get("scenario_id") for item in packet.get("items", [])]
    if any(item.get("review_state") != "PENDING" for item in packet.get("items", [])):
        raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    decisions = review_input.get("decisions")
    if not isinstance(decisions, list) or [item.get("scenario_id") for item in decisions] != pending_ids:
        raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    document = {
        "schema_version": SCHEMA_DECISIONS,
        "reviewer_class": "CODEX_SILVER_REVIEWED",
        **expected_source_digests,
        "source_review_input_sha256": _sha256(reviewer_input_path.read_bytes()),
        "producer_module": "record_review_contract_decisions",
        "elapsed_minutes": review_input.get("elapsed_minutes"),
        "reviewed_node_ids": review_input.get("reviewed_node_ids"),
        "random_recheck_scenario_ids": review_input.get("random_recheck_scenario_ids"),
        "dual_review_count": review_input.get("dual_review_count"),
        "decisions": decisions,
    }
    content = _json_bytes(document)
    if output_path.exists() and output_path.read_bytes() != content:
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    if not output_path.exists():
        output_path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--review-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record_decisions(args.tree, args.scenarios, args.packet, args.review_input, args.output)
    print("C0_REVIEW_RECORDED decisions=8 reviewer_class=CODEX_SILVER_REVIEWED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
