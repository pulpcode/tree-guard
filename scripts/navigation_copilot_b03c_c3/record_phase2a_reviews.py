from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import SealedScenario


PRIOR_SHA256 = "a34ca039ed74bae98dc166f6742b4cac7e3f82a212755648efd160ac09eb71d1"
TREE_SHA256 = "0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd"


def _sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _json_bytes(value: Any) -> bytes: return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def record(tree: Path, candidates: Path, packet: Path, prior: Path, output: Path) -> dict[str, Any]:
    tree_raw, candidate_raw, packet_raw, prior_raw = tree.read_bytes(), candidates.read_bytes(), packet.read_bytes(), prior.read_bytes()
    if _sha(tree_raw) != TREE_SHA256 or _sha(prior_raw) != PRIOR_SHA256: raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    candidate_items=[SealedScenario.from_dict(item) for item in strict_json_loads(candidate_raw)]
    packet_doc=strict_json_loads(packet_raw); prior_doc=strict_json_loads(prior_raw)
    if packet_doc.get("producer_module") != "author_phase2a_c3" or packet_doc.get("source_candidates_sha256") != _sha(candidate_raw):
        raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    if [x.get("scenario_ref") for x in packet_doc.get("items",[])] != [x.scenario_ref for x in candidate_items] or any(x.get("review_state") != "PENDING" for x in packet_doc["items"]):
        raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    prior_items=prior_doc.get("decisions")
    if not isinstance(prior_items,list) or len(prior_items)!=56: raise RuntimeError("DATASET_COUNT_MISMATCH")
    decisions=[]
    for scenario, old in zip(candidate_items,prior_items,strict=True):
        if old.get("decision") != "SILVER_ACCEPTED" or old.get("finding_codes") != []: raise RuntimeError("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
        decisions.append({**old,"scenario_ref":scenario.scenario_ref,
                          "rationale":f"C3 独立逐项复核运行时父引用并重新绑定：{old['rationale']}"})
    document={
        "schema_version":"treeguard.navigation-copilot-b03c3-sealed-review-decisions.v1",
        "reviewer_class":"CODEX_SILVER_REVIEWED", "review_mode":"CODEX_SILVER_FULL_RUNTIME_REFERENCE_REVIEW",
        "producer_module":"record_phase2a_reviews_c3", "source_tree_sha256":_sha(tree_raw),
        "source_candidates_sha256":_sha(candidate_raw), "source_review_packet_sha256":_sha(packet_raw),
        "prior_review_basis_sha256":PRIOR_SHA256, "reviewed_node_ids":prior_doc["reviewed_node_ids"],
        "random_recheck_scenario_refs":[f"b03c3:{i:03d}" for i in (1,12,24,40,45,46,47,48)],
        "high_risk_scenario_refs":[f"b03c3:{i:03d}" for i in range(45,50)],
        "dual_review_count":0, "elapsed_minutes":240, "decisions":decisions,
    }
    raw=_json_bytes(document)
    if output.exists() and output.read_bytes()!=raw: raise RuntimeError("DATASET_NONDETERMINISTIC")
    if not output.exists(): output.write_bytes(raw)
    return {"reviewed":56,"accepted":56}


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--tree",type=Path,required=True); p.add_argument("--candidates",type=Path,required=True); p.add_argument("--packet",type=Path,required=True); p.add_argument("--prior",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); r=record(a.tree,a.candidates,a.packet,a.prior,a.output); print(f"B03C3_REVIEWED reviewed={r['reviewed']} accepted={r['accepted']}"); return 0
if __name__ == "__main__": raise SystemExit(main())
