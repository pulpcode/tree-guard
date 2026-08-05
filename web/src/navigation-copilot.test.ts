import { describe, expect, it } from "vitest";

import type { NavigationCopilotCandidate, NavigationCopilotCase } from "./api";
import { canUseOutsideCandidate, copilotStatusMessage } from "./navigation-copilot";

const candidate: NavigationCopilotCandidate = {
  candidate_ref: "C001",
  rank: 1,
  node_ref: "N000001",
  name: "虚构节点",
  label: "fictional",
  kind: "PROPERTY",
  value_type: "string",
  cardinality: "SINGLE",
  path_names: ["虚构根", "虚构节点"],
  parent_relation: "NONE",
  relation: null,
  reason: null,
};

function caseValue(status: NavigationCopilotCase["candidate_status"]): NavigationCopilotCase {
  return {
    schema_version: "navigation-copilot-case-view.v1",
    case_ref: "NC_fixture",
    status: "AWAITING_OUTCOME",
    model_mode: "SIMULATOR_LIVE",
    model_call_count: 2,
    interpretation: null,
    degradation_codes: [],
    candidate_status: status,
    highlighted_candidate_ref: null,
    candidates: [candidate],
    outcome: null,
    navigation_target_ref: null,
  };
}

describe("navigation Copilot presentation policy", () => {
  it("does not silently preselect weak or ambiguous evidence", () => {
    expect(copilotStatusMessage(caseValue("NEED_EVIDENCE"))).toContain("证据不足");
    expect(copilotStatusMessage(caseValue("AMBIGUOUS"))).toContain("多个可能");
  });

  it("accepts outside correction only for a non-candidate tree node", () => {
    expect(canUseOutsideCandidate("N000001", [candidate])).toBe(false);
    expect(canUseOutsideCandidate("N000002", [candidate])).toBe(true);
    expect(canUseOutsideCandidate(undefined, [candidate])).toBe(false);
  });
});
