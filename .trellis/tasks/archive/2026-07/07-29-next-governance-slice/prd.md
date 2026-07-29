# 候选语义比较与选择性建议

## Goal

在已有“确认意图 → 确定性全树候选”之后，增加一个不具备审批或 Patch 权限的
候选语义比较纵切：AI 对有限候选解释可复用性、上下文差异和证据缺口，输出可拒答
的结构化建议，再由人工决定是否接受、修订或继续调查。

## What I already know

* 已实现 `IntentConfirmation → CandidateSet`，默认返回可解释的全树 Top-20，
  `allows_addition=false`。
* 已有严格模型输出校验、百炼 OpenAI-compatible Provider、私有文件 IO 和来源
  哈希回放模式。
* 已有专家自由文本、AI 整理、状态裁决和事件回放合同，可复用“AI 不改变权威
  状态”的设计原则。
* 当前没有候选语义比较、选择性动作、Semantic Overlay、Schema Patch、内网
  Qwen 直连或 embedding。
* 当前没有足够的真实冻结 Gold，不能用虚构样例证明真实领域准确率。

## Assumptions (temporary)

* 第一版继续允许离线模型输出文件和获批百炼冒烟；内网 Qwen 直连保持独立适配点。
* 本纵切只输出建议和证据，不产生 Overlay、Patch 或生产写入资格。
* 专家无法对约 2,000 个节点做穷举盲标；MVP 不把有界候选池标注伪装成完整
  全树 Gold 或真实 Recall。
* `OperationalReviewRecord`、`PoolJudgmentCase`、`PartialGoldCase` 和
  `ExhaustiveGoldCase` 只是当前讨论使用的暂定分层与命名，不是已批准的评测数据
  合同；其边界、晋升条件和是否需要四层都有待后续专项推敲。

## Deferred Evaluation Questions

以下问题明确延后到独立评测专项，不阻塞本任务实施，也不构成本任务合同：

* 是否采用“多通道候选池 + 专家部分裁决”的评测基线。
* 候选评测的主指标、分母、样本分层和版本准入阈值。
* 暂定的四层评测数据分级是否必要、命名是否合适，以及从运行反馈晋升为 Gold
  所需的复核、证据和裁决条件。

## Requirements (evolving)

* 输入必须绑定人工确认意图、候选集和同一基础快照。
* 投影给模型的候选必须有界，使用临时引用，并排除稳定 ID、VALUE 和未知字段。
* 模型必须逐候选区分可能复用、上下文不同、明显不等价或证据不足。
* 每个草稿只包含一个 `recommended_action`；候选逐项判断、选中候选、不确定性和
  至多一个关键追问作为其解释依据，不输出并列动作方案。
* 候选关系固定为 `SEMANTICALLY_EQUIVALENT`、`REUSES_CONTRACT`、
  `CONTEXTUALLY_RELATED`、`NOT_EQUIVALENT` 或 `NEED_EVIDENCE`。
* 模型建议动作固定为 `USE_EXISTING_NODE`、`ADD_NODE_FROM_CONTRACT`、
  `ADD_CONTEXT_FIELD`、`NEED_CLARIFICATION`、`NEED_EVIDENCE` 或 `ABSTAIN`。
* 本地代码负责精确字段、引用、来源、版本和跨字段策略校验。
* 建设人员必须能确认、修订或拒绝建议，并通过独立 action 绑定实际查看的草稿。
* 确认结果必须形成可回放的 `RecommendationRecord`，但不构成专家语义审批。
* 任何建议固定为非审批、非 Patch、非生产写入。
* `NO_CANDIDATES`、`INSUFFICIENT_SIGNAL` 或候选全部证据不足时，不得自动产生
  `ADD_NODE_FROM_CONTRACT` 或 `ADD_CONTEXT_FIELD`。
* 第一版模型比较使用现有确定性排序的 Top-8；完整 Top-20 候选集仍作为来源冻结，
  不再增加一个模型精排调用。
* `USE_EXISTING_NODE` 必须绑定一个语义等价候选；`ADD_NODE_FROM_CONTRACT`
  必须绑定一个可复用合同候选；`ADD_CONTEXT_FIELD` 必须至少有上下文相关候选和
  足够的场景证据。Shadow MVP 暂以已确认意图同时包含 `scenario` 和至少一条
  `confirmed_fact` 作为确定性最低门槛，后续可根据内网验证单独调整。
* `NEED_CLARIFICATION` 必须包含一个追问；`NEED_EVIDENCE` 必须列出证据缺口；
  `ABSTAIN` 不得伪装成正向建议。
* `RecommendationRecord` 只是运行旁路记录，不能未经未来评测专项定义的独立
  复核流程就自动作为 Gold 或效果证明。

## Acceptance Criteria (evolving)

* [x] 完全虚构案例可从冻结 `CandidateSet` 生成结构化语义比较草稿。
* [x] 模型引用未知候选、越权审批、生成 Patch 或输出非法结构时 fail-closed。
* [x] 草稿绑定意图确认、候选集、快照、Prompt 和模型来源。
* [x] 快照或候选变化后，旧草稿无法作为当前建议重放。
* [x] 人工 action 绑定草稿哈希；确认、修订和拒绝均可从可信来源重放。
* [x] 无候选、证据不足和模型拒答不会产生新增许可。
* [x] 正向建议违反候选关系或必要证据条件时由本地跨字段校验拒绝。
* [x] 同一草稿不能携带多个主建议，且选中候选必须来自本次 Top-8 投影。
* [x] 完整工件保持私有，stdout 只输出固定状态和聚合计数。

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* `uv sync --frozen`、已配置的 `unittest` 和 `git diff --check` 通过
* 未配置的 lint、typecheck 和 coverage 不宣称已通过
* 行为变化同步更新文档和适用 Trellis 规范
* 明确 rollout、rollback 和内网核验项

## Out of Scope (explicit)

* embedding、向量数据库和混合召回
* Semantic Overlay、Schema Patch、Dry Run 和生产写入
* Spring Boot/MongoDB、Web UI 和身份认证
* Gold/评测数据稳定 Schema、标注平台、效果评测器和真实数据集导入
* `ActionableHit@K`、`PoolRecall@K`、MRR 等指标定义、样本门槛和发布阈值
* 使用虚构或 AI 合成案例宣称真实业务准确率

## Research References

* [`research/next-vertical-slice.md`](research/next-vertical-slice.md) — 比较四个可行
  下一步并推荐先完成候选语义比较。
* [`research/retrieval-evaluation.md`](research/retrieval-evaluation.md) — 依据公开
  检索评测与统计方法，定义候选池、样本量、标注可靠性和模拟评测边界。

## Feasible Approaches

### A. 候选语义比较与选择性建议（推荐）

复用当前意图、候选集、Provider 和严格合同，形成
`CandidateSet → SemanticRecommendationDraft`。新增业务价值最直接，且可继续保持
无生产写权限。

### B. 先接入内网 Qwen Provider

补齐部署适配，但单独完成后不会增加新的业务判断能力；真实端点与模型行为也只能
在内网验证。

### C. 先增加 embedding 或混合召回

可能改善字面不同但语义相同的召回，但当前缺少冻结 Gold 和分层漏召回证据，容易
先增加部署复杂度却无法判断收益。

### D. 先接 Spring Boot/MongoDB 或 Web UI

能改善使用方式，但会提前扩大生产边界；当前语义决策链仍停在候选列表，不适合作为
下一纵切。

## Decision (ADR-lite)

**Context**：当前实现已经能生成确定性候选，但候选列表本身不能回答复用、上下文
差异或证据不足，单独建设 Provider、embedding 或 UI 都不会补齐这个断点。

**Decision**：下一纵切采用“候选语义比较 + 选择性建议 + 人工确认记录”。AI 结果
始终是草稿，人工 action 绑定实际草稿并生成可回放记录；本任务不生成 Overlay、
Patch 或生产写入资格。

第一版采用完整但不可执行的建议动作集合，包括复用、按已有合同新增物理节点、
稳定场景字段扩展、追问、补证和拒答。零候选或证据不足不能自动推出新增建议。

模型输出采用“一个主建议 + 候选逐项判断”，不返回多个并列动作。人工可以确认、
修订或拒绝这个唯一主建议，修订内容仍须通过相同跨字段政策。

**Consequences**：形成更完整的人机协作展示链路，并能把召回错误与语义决策错误
的运行证据保留下来；如何把这些证据晋升为评测数据由后续专项决定。内网 Qwen
直连和混合召回仍需后续独立验证。

## Implementation Plan

1. 增加候选语义判断、唯一主建议和人工 action 的结构化合同与本地跨字段策略。
2. 增加 Top-8 最小模型投影、AI 草稿生成、严格解析和 fail-closed 错误处理。
3. 增加专家确认、修订、拒绝以及来源哈希绑定的 `RecommendationRecord` 回放。
4. 接入现有 CLI，补充完全虚构的单元/集成测试和必要文档。

## Technical Notes

* 主要复用：`change_intent.py`、`retrieval.py`、`ai_review.py`、
  `private_io.py` 和 `governance_cli.py`。
* 可参考：`evidence.py` 的有界临时引用、`expert_review.py` 的 AI 非权威状态和
  可信来源回放。
* 实施上下文：`directory-structure.md`、`development-data-boundary.md`、
  `contracts-and-determinism.md`、`persistence-and-integration.md`、
  `error-handling.md`、`cli-output-and-diagnostics.md`、
  `governance-intake-and-retrieval.md`、`quality-guidelines.md`，以及代码复用、
  跨层边界和 Codex 协作指南。
* 相关设计：`docs/product-spec.md` 的语义动作模型、`docs/architecture.md`
  的局部精排和分层评测、`docs/roadmap.md` 第 3 周。

## Rollout / Rollback / Internal Verification

* Rollout：先在外网完全虚构样例和内网私有模型输出文件上执行
  `recommend → review-recommendation → replay-recommendation`；确认合同回放和
  stdout 边界后，再在受保护环境接入内网 Qwen。外部百炼仍只用于完全虚构或最终
  外发字节已获批准的材料。
* Rollback：停止调用三个新增子命令并回退本功能代码版本即可；本纵切只生成
  不可执行 sidecar，没有生产数据库、信息树或业务版本状态需要回滚。已生成的私有
  工件按内网保留策略处理，不由外网代码自动删除。
* 内网待核验：Qwen OpenAI-compatible JSON Object 行为、48,000 字符预算下的
  实际上下文/延迟、非法输出重试表现，以及真实试点中六类动作的可用性。上述结果
  不影响外网工程合同通过，但未核验前不能宣称领域效果。

## Verification Evidence

2026-07-29 已执行：

* `python3 ./.trellis/scripts/task.py validate next-governance-slice`：通过；
* `UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen`：通过；
* `UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen python -B -m unittest discover -s tests -v`：
  144 项通过；
* `git diff --check`：通过；
* 六个新增 JSON Schema 均可由标准库 `json.tool` 解析。

当前未配置 formatter、linter、type checker、coverage 和第三方 JSON Schema
validator，因此不声明这些检查已通过。
