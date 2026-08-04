# M5 Codex Silver 三轮预实验结果

## 范围

- 日期：2026-08-04。
- 质量等级：`SILVER / CODEX_ASSISTED / CALIBRATION_ONLY`。
- 固定协议：24 条×3 轮，18 `PROCEED` + 6 `CLARIFY`。
- 数据为项目独立编制的 clean-room 虚构消防树；隐藏 Oracle 未进入模型投影。
- 本轮从首次模型调用起永久失去正式未见准入资格，只可用于诊断和回归。

## 聚合结果

| 指标 | 结果 |
|---|---:|
| Intent 实际 wire 请求 | 105 |
| Intent 最终合同合法 | 72/72 |
| Intent 首次合同合法 | 39/72 |
| 正确澄清 | 16/18 |
| 实际执行 Retrieval | 46 |
| Retrieval `MATCH` | 38/46 |
| Semantic 实际 wire 请求 | 44 |
| Semantic 最终合同合法 | 36/38 |
| Semantic 首次合同合法 | 32/38 |
| `PREFERRED_MATCH` | 24 |
| `SAFE_ALTERNATIVE` | 12 |
| `UNSAFE_MISMATCH` | 0 |
| Semantic `RUN_FAILED` | 2 |
| 每轮首选完整路径 | 8 / 8 / 8（分母 18） |
| 每轮安全完整路径 | 16 / 17 / 19（分母 24） |
| 三轮稳定首选 | 5/18 |
| 三轮稳定安全 | 14/24 |

Codex 复核了 12 个不同的安全退让输出，12/12 均有阻塞性交互问题。
共性问题是把临时候选引用、节点 ID 或“候选项”暴露给用户，以及将多个
结构事实合并成一个非原子问题。这些输出没有形成正向误操作，但不适合直接展示给
生产用户。

## 结论

正式 M5 合同决策为 `EVALUATION_PENDING`，因为 Oracle 只是 Codex Silver，不是
`HUMAN_AUTHORIZED`。即使忽略该资格门，当前技术指标也不应进入生产 Shadow：

- 三轮每轮首选 8/18，证明已有重复出现的实质定位能力；
- 稳定首选 5/18，低于冻结底线 6/18；
- Retrieval 只有 38/46，是安全完整路径损失的主要上游来源；
- Semantic 最终合同 36/38，仍有 2 条最终失败；
- 没有 `UNSAFE_MISMATCH`，但安全退让文本需要独立的用户交互收口。

稳定失败 code：

- `ASSISTED_RETRIEVAL_NOT_PERFECT`
- `ASSISTED_ROUND_SAFE_PATH_BELOW_MINIMUM`
- `ASSISTED_SAFE_ALTERNATIVE_BLOCKING_FINDING_PRESENT`
- `ASSISTED_SAFE_ALTERNATIVE_REVIEW_INCOMPLETE`
- `ASSISTED_SEMANTIC_CONTRACT_BELOW_MINIMUM`
- `ASSISTED_STABLE_PREFERRED_PATH_BELOW_MINIMUM`
- `ASSISTED_STABLE_SAFE_PATH_BELOW_MINIMUM`

本记录不包含请求正文、节点、Oracle、Prompt、模型响应、来源 hash、凭据或内部路径。
