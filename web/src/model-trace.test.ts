import { describe, expect, it } from "vitest";

import { formatModelUsage, modelTraceStageLabel } from "./model-trace";

describe("model trace presentation", () => {
  it("uses explicit Chinese labels for every model stage", () => {
    expect(modelTraceStageLabel("INTENT_DRAFT")).toBe("初始意图整理");
    expect(modelTraceStageLabel("INTENT_CLARIFICATION")).toBe("单轮意图澄清");
    expect(modelTraceStageLabel("SEMANTIC_RECOMMENDATION")).toBe(
      "候选语义建议",
    );
  });

  it("formats only token usage returned by the provider", () => {
    expect(
      formatModelUsage({
        prompt_tokens: 20,
        completion_tokens: 10,
        total_tokens: 30,
      }),
    ).toBe("输入 20 / 输出 10 / 合计 30");
    expect(formatModelUsage(null)).toBe("模型未返回 token 用量");
  });
});
