import type { NavigationCopilotCandidate, NavigationCopilotCase } from "./api";

export const SHADOW_REJECTION_OPTIONS = [
  { disposition: "PRESENT_NOT_FOUND", label: "树中有目标，但未找到" },
  { disposition: "ABSENT", label: "树中没有对应节点" },
  { disposition: "UNKNOWN", label: "暂时无法判断" },
] as const;

export function canUseOutsideCandidate(
  selectedNodeRef: string | undefined,
  candidates: NavigationCopilotCandidate[],
): boolean {
  return Boolean(
    selectedNodeRef &&
      !candidates.some((candidate) => candidate.node_ref === selectedNodeRef),
  );
}

export function copilotStatusMessage(value: NavigationCopilotCase): string {
  const highlighted = value.candidates.find(
    (candidate) => candidate.candidate_ref === value.highlighted_candidate_ref,
  );
  if (highlighted) {
    return `AI 建议优先查看“${highlighted.name}”，仍需你确认。`;
  }
  if (value.candidate_status === "NEED_EVIDENCE") {
    return "当前证据不足，没有自动选中节点。";
  }
  if (value.candidate_status === "AMBIGUOUS") {
    return "存在多个可能节点，没有自动选中节点。";
  }
  if (value.candidate_status === "NONE") {
    return "没有找到可用候选，请调整描述或手动浏览。";
  }
  return "当前没有自动选中节点。";
}
