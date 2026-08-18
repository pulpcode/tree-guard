from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import SealedScenario


DATASET_REF = "navigation-copilot-sealed-v3c-b03-maker-lab-c"
BATCH_REF = "NAVCOP_SEALED_V3C_B03_20260817_C2"
FUNCTION_COMMIT = "40098afe985dfc81183c928a473a2e8a3c2176dc"
SOURCE_DATA_COMMIT = "70675601e3d53649bee440935199f4cf9fbf3ff0"
SOURCE_BLUEPRINT_SHA256 = "72d8778d26ec2c2317d14c38a1843f014651e0cbd10aa0d0bc4ded729b01792d"
SOURCE_TREE_SHA256 = "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd"
SOURCE_CANDIDATES_SHA256 = "122fd83fab7856b37928288c7f086a6350812946dd05540d9c8ea9fafb7e8dda"
BLUEPRINT_SCHEMA = "treeguard.navigation-copilot-b03c2-blueprint.v1"
PACKET_SCHEMA = "treeguard.navigation-copilot-b03c2-sealed-review-packet.v1"
SELECTION_ALGORITHM = "treeguard.navigation-copilot-b03c2-slot-selection.v1"
SELECTION_SEED = 2026081791

CANDIDATE_QUOTAS = {
    "LITERAL_UNIQUE": 11,
    "NONLITERAL_UNIQUE": 12,
    "STRUCTURAL_INTERFERENCE": 10,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 7,
    "WEAK_EVIDENCE": 5,
    "TARGET_ABSENT": 7,
}
WEAK_REWRITES = {
    "b03c:045": "三维打印台预约不太合适，帮我调整一下",
    "b03c:046": "激光切割机维护有问题，帮我改一下",
    "b03c:047": "涂料登记需要处理一下",
    "b03c:048": "样件保留期限不太合适，帮我处理一下",
    "b03c:049": "交接未结事项需要调整一下",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_exact(path: Path, content: bytes) -> None:
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError("DATASET_NONDETERMINISTIC")
    if not path.exists():
        path.write_bytes(content)


def _read_source(source_dir: Path) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    blueprint_bytes = (source_dir / "blueprint.v1.json").read_bytes()
    tree_bytes = (source_dir / "tree.json").read_bytes()
    candidate_bytes = (source_dir / "candidate-scenarios.v2.json").read_bytes()
    if (
        _sha256(blueprint_bytes) != SOURCE_BLUEPRINT_SHA256
        or _sha256(tree_bytes) != SOURCE_TREE_SHA256
        or _sha256(candidate_bytes) != SOURCE_CANDIDATES_SHA256
    ):
        raise RuntimeError("DATASET_C1_SOURCE_DRIFT")
    blueprint = strict_json_loads(blueprint_bytes)
    candidates = strict_json_loads(candidate_bytes)
    if not isinstance(blueprint, dict) or not isinstance(candidates, list):
        raise RuntimeError("DATASET_REFERENCE_INVALID")
    return blueprint, tree_bytes, candidates


def _build_candidates(source_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for position, payload in enumerate(source_candidates, 1):
        source = SealedScenario.from_dict(payload)
        expected_source_ref = f"b03c:{position:03d}"
        if source.scenario_ref != expected_source_ref:
            raise RuntimeError("DATASET_REFERENCE_INVALID")
        values = {
            "scenario_ref": f"b03c2:{position:03d}",
            "tree_digest": source.tree_digest,
            "category": source.category,
            "requirement_text": WEAK_REWRITES.get(source.scenario_ref, source.requirement_text),
            "proposed_parent_ref": source.proposed_parent_ref,
            "node_kind_hint": source.node_kind_hint,
            "value_type_hint": source.value_type_hint,
            "cardinality_hint": source.cardinality_hint,
            "frozen_clarification_answer": source.frozen_clarification_answer,
            "wrong_context_challenge": source.wrong_context_challenge,
            "repeat_challenge": source.repeat_challenge,
        }
        result.append(SealedScenario.create(**values).to_dict())
    if len(result) != 56 or Counter(item["category"] for item in result) != Counter(CANDIDATE_QUOTAS):
        raise RuntimeError("DATASET_COUNT_MISMATCH")
    return result


def materialize(source_dir: Path, output_dir: Path) -> dict[str, str]:
    if source_dir.resolve() == output_dir.resolve():
        raise RuntimeError("DATASET_C1_SOURCE_DRIFT")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.glob("*oracle*")) or any(output_dir.glob("*manifest*")):
        raise RuntimeError("DATASET_ORACLE_OVERCLAIM")
    source_blueprint, tree_bytes, source_candidates = _read_source(source_dir)
    candidates = _build_candidates(source_candidates)
    candidate_bytes = _json_bytes(candidates)
    blueprint = {
        **source_blueprint,
        "schema_version": BLUEPRINT_SCHEMA,
        "batch_ref": BATCH_REF,
        "selection_seed": SELECTION_SEED,
        "selection_algorithm": SELECTION_ALGORITHM,
        "function_commit": FUNCTION_COMMIT,
        "source_data_commit": SOURCE_DATA_COMMIT,
        "source_tree_sha256": SOURCE_TREE_SHA256,
        "c1_disposition": "REJECTED_PREEXECUTION_ORACLE_CONTRACT_MISMATCH",
    }
    blueprint_bytes = _json_bytes(blueprint)
    packet = {
        "schema_version": PACKET_SCHEMA,
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "source_tree_sha256": _sha256(tree_bytes),
        "source_candidates_sha256": _sha256(candidate_bytes),
        "producer_module": "author_sealed_data_c2",
        "items": [
            {"scenario_ref": item["scenario_ref"], "review_state": "PENDING"}
            for item in candidates
        ],
    }
    contents = {
        "blueprint.v1.json": blueprint_bytes,
        "tree.json": tree_bytes,
        "candidate-scenarios.v2.json": candidate_bytes,
        "review-packet.v1.json": _json_bytes(packet),
    }
    for name, content in contents.items():
        _write_exact(output_dir / name, content)
    return {name: _sha256(content) for name, content in contents.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.source_dir, args.output_dir)
    print("B03C2_PHASE2A_AUTHORED nodes=736 candidates=56 oracle=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
