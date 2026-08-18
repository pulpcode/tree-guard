from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from treeguard import load_tree_export
from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import SealedScenario
from treeguard.workbench import build_tree_reference_index


FINAL_QUOTAS={"LITERAL_UNIQUE":10,"NONLITERAL_UNIQUE":10,"STRUCTURAL_INTERFERENCE":8,"MULTI_ACCEPTABLE":4,"CLARIFICATION":6,"WEAK_EVIDENCE":4,"TARGET_ABSENT":6}

def _sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()
def _json_bytes(v:Any)->bytes:return (json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
def _write(p:Path,raw:bytes)->None:
    if p.exists() and p.read_bytes()!=raw:raise RuntimeError("DATASET_NONDETERMINISTIC")
    if not p.exists():p.write_bytes(raw)

def verify(source:Path,scenarios_output:Path,report_output:Path)->dict[str,Any]:
    if any(source.glob("*oracle*")) or any(source.glob("*manifest*")):raise RuntimeError("DATASET_ORACLE_OVERCLAIM")
    names=("blueprint.v1.json","tree.json","candidate-scenarios.v2.json","review-packet.v1.json","review-decisions.hidden.v1.json")
    raw={n:(source/n).read_bytes() for n in names}
    blueprint=strict_json_loads(raw["blueprint.v1.json"]); packet=strict_json_loads(raw["review-packet.v1.json"]); review=strict_json_loads(raw["review-decisions.hidden.v1.json"])
    if blueprint.get("batch_ref")!="NAVCOP_SEALED_V3C_B03_20260817_C3" or blueprint.get("source_class")!="CLEANROOM_SYNTHETIC" or blueprint.get("gold_eligible") is not False:raise RuntimeError("DATASET_SOURCE_CLASS_INVALID")
    result=load_tree_export(source/"tree.json")
    if not result.is_valid or result.tree is None or (result.observed_node_count,result.observed_value_count)!=(736,0):raise RuntimeError("DATASET_COUNT_MISMATCH")
    refs=build_tree_reference_index(result.tree)
    candidates=[SealedScenario.from_dict(x) for x in strict_json_loads(raw["candidate-scenarios.v2.json"])]
    if len(candidates)!=56 or [x.scenario_ref for x in candidates]!=[f"b03c3:{i:03d}" for i in range(1,57)]:raise RuntimeError("DATASET_COUNT_MISMATCH")
    parents=[x.proposed_parent_ref for x in candidates if x.proposed_parent_ref]
    if len(parents)!=8 or any(x not in refs.node_id_by_ref for x in parents) or any(x.startswith("N500") for x in parents):raise RuntimeError("DATASET_PARENT_REFERENCE_CONTRACT_MISMATCH")
    if packet.get("producer_module")!="author_phase2a_c3" or review.get("producer_module")!="record_phase2a_reviews_c3":raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    if review.get("source_tree_sha256")!=_sha(raw["tree.json"]) or review.get("source_candidates_sha256")!=_sha(raw["candidate-scenarios.v2.json"]) or review.get("source_review_packet_sha256")!=_sha(raw["review-packet.v1.json"]):raise RuntimeError("DATASET_REVIEW_SOURCE_NOT_INDEPENDENT")
    decisions=review.get("decisions")
    if not isinstance(decisions,list) or len(decisions)!=56 or [x.get("scenario_ref") for x in decisions]!=[x.scenario_ref for x in candidates] or any(x.get("decision")!="SILVER_ACCEPTED" or x.get("finding_codes")!=[] for x in decisions):raise RuntimeError("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    node_ids={node.node_id for node in result.tree.nodes}
    rationales=[item.get("rationale") for item in decisions]
    if any(not isinstance(text,str) or len(text)<20 for text in rationales) or len(set(rationales))!=56:raise RuntimeError("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
    for scenario,decision in zip(candidates,decisions,strict=True):
        fields=("reviewed_target_ids","compatible_target_ids","contrast_node_ids","resolved_target_ids","satisfiable_supertype_ids")
        if any(not isinstance(decision.get(name),list) for name in fields):raise RuntimeError("DATASET_REFERENCE_INVALID")
        if any(node_id not in node_ids for name in fields for node_id in decision[name]):raise RuntimeError("DATASET_REFERENCE_INVALID")
        reviewed=decision["reviewed_target_ids"];compatible=decision["compatible_target_ids"]
        if scenario.category=="MULTI_ACCEPTABLE" and (reviewed!=compatible or len(reviewed)<2):raise RuntimeError("DATASET_TARGET_SET_NOT_EXHAUSTIVE")
        if scenario.category=="CLARIFICATION" and (len(decision["resolved_target_ids"])!=1 or len(decision["contrast_node_ids"])<2):raise RuntimeError("DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT")
        if scenario.category=="WEAK_EVIDENCE" and (reviewed!=compatible or len(reviewed)!=1 or not isinstance(decision.get("evidence_gap"),str) or len(decision["evidence_gap"])<20):raise RuntimeError("DATASET_WEAK_EVIDENCE_TARGET_UNBOUND")
        if scenario.category=="TARGET_ABSENT" and any(decision[name] for name in fields):raise RuntimeError("DATASET_ORACLE_OVERCLAIM")
        if scenario.category in {"LITERAL_UNIQUE","NONLITERAL_UNIQUE","STRUCTURAL_INTERFERENCE"} and (reviewed!=compatible or len(reviewed)!=1):raise RuntimeError("DATASET_SCENARIO_COVERAGE_DUPLICATE")
    used:Counter[str]=Counter();selected=[]
    for item in candidates:
        if used[item.category]<FINAL_QUOTAS[item.category]:used[item.category]+=1;selected.append(item)
    if len(selected)!=48 or used!=Counter(FINAL_QUOTAS) or sum(x.category!="TARGET_ABSENT" for x in selected)!=42 or sum(x.wrong_context_challenge for x in selected)!=8 or sum(x.repeat_challenge for x in selected)!=16:raise RuntimeError("DATASET_COUNT_MISMATCH")
    scenario_raw=_json_bytes([x.to_dict() for x in selected])
    report={"schema_version":"treeguard.navigation-copilot-b03c3-phase2a-preflight.v1","status":"C3_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW","batch_ref":blueprint["batch_ref"],"source_class":"CLEANROOM_SYNTHETIC","fictional":True,"derived_from_real":False,"gold_eligible":False,"patch_eligible":False,"nodes":736,"value_envelope_count":0,"candidates":56,"accepted":56,"execution_scenarios":48,"target_present":42,"target_absent":6,"wrong_context":8,"repeat_subset":16,"runtime_parent_refs_valid":8,"stable_ids_used_as_parent_refs":0,"reviewed_scenarios":56,"random_rechecks":8,"dual_reviews":0,"elapsed_minutes":review["elapsed_minutes"],"oracle_status":"ABSENT_PHASE2B_NOT_APPROVED","blueprint_sha256":_sha(raw["blueprint.v1.json"]),"tree_sha256":_sha(raw["tree.json"]),"candidates_sha256":_sha(raw["candidate-scenarios.v2.json"]),"review_packet_sha256":_sha(raw["review-packet.v1.json"]),"review_decisions_sha256":_sha(raw["review-decisions.hidden.v1.json"]),"scenarios_sha256":_sha(scenario_raw),"blocking_finding_codes":[]}
    _write(scenarios_output,scenario_raw);_write(report_output,_json_bytes(report));return report

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--scenarios-output",type=Path,required=True);p.add_argument("--report-output",type=Path,required=True);a=p.parse_args();r=verify(a.source,a.scenarios_output,a.report_output);print(f"B03C3_PHASE2A_VERIFIED scenarios={r['execution_scenarios']} parent_refs=8 oracle=ABSENT");return 0
if __name__=="__main__":raise SystemExit(main())
