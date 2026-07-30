import type { GovernanceModelTraceAttempt } from "./api";

export function modelTraceStageLabel(
  stage: GovernanceModelTraceAttempt["stage"],
): string {
  if (stage === "INTENT_DRAFT") {
    return "初始意图整理";
  }
  if (stage === "INTENT_CLARIFICATION") {
    return "单轮意图澄清";
  }
  return "候选语义建议";
}

export function formatModelUsage(
  usage: GovernanceModelTraceAttempt["usage"],
): string {
  if (!usage) {
    return "模型未返回 token 用量";
  }
  const segments = [
    ["输入", usage.prompt_tokens],
    ["输出", usage.completion_tokens],
    ["合计", usage.total_tokens],
  ]
    .filter((item): item is [string, number] => typeof item[1] === "number")
    .map(([label, value]) => `${label} ${value}`);
  return segments.length
    ? segments.join(" / ")
    : "模型未返回 token 用量";
}
