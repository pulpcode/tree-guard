from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from treeguard import load_tree_export
from treeguard.navigation_copilot_sealed_validation import SealedScenario
from treeguard.workbench import build_tree_reference_index


BATCH_REF = "NAVCOP_SEALED_V3C_B03_20260817_C3"
SOURCE_DATA_COMMIT = "cbb22e8416c10cc8de36d9ed09cc6a821b782a62"
SOURCE_SHA256 = {
    "tree.json": "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd",
    "candidate-scenarios.v2.json": "1437568f07ea6c6a01a4d25a9c103f40718e37b3a505e6404dceaabb71c1c34e",
}


def _sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _json_bytes(value: Any) -> bytes: return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write(path: Path, raw: bytes) -> None:
    if path.exists() and path.read_bytes() != raw: raise RuntimeError("DATASET_NONDETERMINISTIC")
    if not path.exists(): path.write_bytes(raw)


def author(source: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    tree_raw = (source / "tree.json").read_bytes()
    candidates_raw = (source / "candidate-scenarios.v2.json").read_bytes()
    if _sha(tree_raw) != SOURCE_SHA256["tree.json"] or _sha(candidates_raw) != SOURCE_SHA256["candidate-scenarios.v2.json"]:
        raise RuntimeError("DATASET_C2_SOURCE_DRIFT")
    result = load_tree_export(source / "tree.json")
    if not result.is_valid or result.tree is None or result.observed_node_count != 736 or result.observed_value_count != 0:
        raise RuntimeError("DATASET_COUNT_MISMATCH")
    refs = build_tree_reference_index(result.tree)
    old_items = [SealedScenario.from_dict(item) for item in json.loads(candidates_raw)]
    items: list[SealedScenario] = []
    for index, old in enumerate(old_items, 1):
        parent_ref = None
        if old.proposed_parent_ref is not None:
            parent_ref = refs.ref_by_node_id.get(old.proposed_parent_ref)
            if parent_ref is None: raise RuntimeError("DATASET_PARENT_REFERENCE_CONTRACT_MISMATCH")
        items.append(SealedScenario.create(
            scenario_ref=f"b03c3:{index:03d}", tree_digest=old.tree_digest, category=old.category,
            requirement_text=old.requirement_text, proposed_parent_ref=parent_ref,
            node_kind_hint=old.node_kind_hint, value_type_hint=old.value_type_hint,
            cardinality_hint=old.cardinality_hint, frozen_clarification_answer=old.frozen_clarification_answer,
            wrong_context_challenge=old.wrong_context_challenge, repeat_challenge=old.repeat_challenge,
        ))
    candidate_bytes = _json_bytes([item.to_dict() for item in items])
    packet = {
        "schema_version": "treeguard.navigation-copilot-b03c3-review-packet.v1",
        "batch_ref": BATCH_REF, "producer_module": "author_phase2a_c3",
        "source_tree_sha256": _sha(tree_raw), "source_candidates_sha256": _sha(candidate_bytes),
        "items": [{"scenario_ref": item.scenario_ref, "review_state": "PENDING"} for item in items],
    }
    blueprint = {
        "schema_version": "treeguard.navigation-copilot-b03c3-blueprint.v1",
        "dataset_ref": "navigation-copilot-sealed-v3c-b03-maker-lab-c", "batch_ref": BATCH_REF,
        "source_data_commit": SOURCE_DATA_COMMIT, "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True, "derived_from_real": False, "gold_eligible": False, "patch_eligible": False,
        "source_tree_sha256": _sha(tree_raw),
        "c2_disposition": "REJECTED_PREEXECUTION_PARENT_REFERENCE_CONTRACT_MISMATCH",
    }
    outputs = {"blueprint.v1.json": _json_bytes(blueprint), "tree.json": tree_raw,
               "candidate-scenarios.v2.json": candidate_bytes, "review-packet.v1.json": _json_bytes(packet)}
    for name, raw in outputs.items(): _write(output / name, raw)
    return {"candidates": len(items), "runtime_parent_refs": sum(item.proposed_parent_ref is not None for item in items)}


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--source",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); report=author(args.source,args.output)
    print(f"B03C3_AUTHORED candidates={report['candidates']} parent_refs={report['runtime_parent_refs']} review=PENDING")
    return 0
if __name__ == "__main__": raise SystemExit(main())
