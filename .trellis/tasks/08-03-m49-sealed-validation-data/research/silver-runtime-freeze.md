# M4.9 Silver 运行配置冻结

## 结论

M4.9 Codex-assisted Silver 复用 M4.7 的百炼模型、官方默认 OpenAI-compatible
endpoint 和确定性生成选项，只对 Semantic 显式启用 M4.8 的一次连接恢复。不修改
Intent v4、Semantic v4 Prompt、确定性召回、比较器或评分阈值。

## 精确配置

| 项 | 冻结值 |
|---|---|
| Provider | `BAILIAN_OPENAI_COMPATIBLE` |
| model | `qwen3.6-35b-a3b` |
| base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| request endpoint | `/chat/completions` |
| response mode | `response_format={"type":"json_object"}` |
| thinking | `enable_thinking=false` |
| temperature | `0` |
| stream | `false` |
| timeout | `90.0` 秒/实际 wire request |
| `top_p` | 不发送 |
| `max_tokens` | 不发送 |
| model seed | 不发送；三轮用于直接观察剩余波动 |
| Intent Prompt | `treeguard.change-intent.zh.v4` |
| Semantic Prompt | `treeguard.semantic-recommendation.zh.v4` |
| retrieval | `treeguard.lexical-structural-retrieval.v1` |

API Key 只在运行时从既有环境加载并进入 Authorization header，不进入 manifest、
请求计划、trace、Trellis 或 Git。本冻结不读取 `.env`，也不证明运行时凭据当前可用。

## 重试与调用上限

### Intent

- `max_attempts=2`：首次模型内容/合同失败后最多一次完整合同重试；
- 当前 Intent Provider 不消费 `max_transport_retries`，连接失败直接记录为 run failure；
- 每个场景每轮最多 2 次 Intent wire request。

### Semantic

- `max_attempts=2`：首次本地 Semantic 合同失败后最多一次完整合同重试；
- `max_transport_retries=1`：全局最多恢复一次 `*_CONNECTION_FAILED`；
- 连接恢复不消费合同重试，且必须重发同一逻辑尝试的逐字节相同 request body；
- HTTP、编码、非 JSON、响应超限和本地合同错误不得消费连接恢复；
- 每个实际 wire request 独立 trace 和记账；每个 Semantic 单元最多 3 次 wire request。

## 三轮预算

正式集为 24 条、三轮，其中 18 条 `PROCEED`、6 条 `CLARIFY`：

| 阶段 | 首发理论数 | 硬上限 |
|---|---:|---:|
| Intent | 72 | 144 |
| Semantic | 54 | 162 |
| 合计 | 126 | 306 |

Semantic 数量是假设 18 条 `PROCEED` 每轮都通过上游并进入推荐的上限。实际 Intent
失败、澄清或召回短路会降低 Semantic 调用数，但不得把未调用单元记作 Semantic
合同失败。执行前必须根据冻结的 24 条和可能重试正文建立精确请求计划，并把硬上限
写入私有运行 manifest；超限立即停线。

## 精确请求计划的分阶段冻结

`IntentRequest.to_model_dict()` 可在模型调用前由 24 条正式场景和冻结树确定性重建，
因此三轮 72 个 Intent 单元的首发正文及所有可能合同重试正文先完整冻结。相同场景在
三轮中必须使用逐字节相同正文；三轮是重复性观测，不是 Prompt 变体实验。

Semantic 正文不能在此时真实构造：它依赖模型实际返回且通过本地合同的 Intent、
本地阶段比较和确定性 Top-K 候选集。预先用隐藏 Oracle、人工答案或理想 Intent 生成
Semantic 正文会污染盲测。故运行采用两个串行私有计划：

1. 冻结并获准执行 72 个 Intent 观测；
2. 冻结 Intent 私有结果，可信回放上游，只为实际可达单元生成精确 Semantic 正文；
3. 第二份计划校验通过后才允许 Semantic 外发。

这仍受本节 144/162/306 的硬上限约束。任一实际 wire body 未命中当阶段冻结计划，
都必须在 transport 前失败。

## Silver 决定合同

- `quality_tier=CODEX_ASSISTED_SILVER`；
- `gate_eligible=false`、`gold_eligible=false`、`patch_eligible=false`；
- 最终决定只允许 `PROMISING`、`NOT_PROMISING`、`INCONCLUSIVE`；
- 可计算正式重复性合同的同构指标，但不得将结果序列化为正式 `GO_SHADOW`；
- 数据揭盲后永久降级为回归/校准资产。

## 变更失效规则

数据生成或运行后，以下任一变化都会使当前冻结失效：模型、base URL/endpoint、
Prompt 版本、temperature、thinking、response mode、timeout、合同尝试、连接恢复、
召回 K/算法、比较器、Oracle 或门槛。不得在同一数据上修改后重新声称泛化验证。

## 仓库依据与限制

日期：2026-08-04。只读取当前外网仓库已提交代码和聚合研究，不读取 `.env`、私有
请求/响应或隐藏 Oracle，不调用 Web、LLM 或其他网络服务。

依据：

- `src/treeguard/ai_review.py`：Provider 默认值、请求选项和 M4.8 Semantic 恢复合同；
- `scripts/run_m47_semantic_policy_calibration.py`：M4.7 实际模型、endpoint、timeout
  和合同尝试配置；
- `scripts/run_m47_failure_repeat_diagnostic.py`：重复实验沿用配置；
- `.trellis/tasks/08-02-tree-understanding-m4-blind-validation/research/`
  `m48-provider-reliability-contract.md`：M4.8 聚合合同。
