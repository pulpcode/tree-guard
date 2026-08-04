# Retrieval A/B 预注册合同（草案）

## 目的与限制

本合同只用于已暴露的 M5 clean-room 虚构数据上的开发期方案选择。它不产生生产资格，
不替代新的未见确认集，也不允许在看到候选结果后修改分母或门槛。

本轮不调用 LLM。A/B 只比较检索查询边界与确定性召回，避免把模型波动、Prompt 变化、
Semantic 动作选择同时混入同一个实验。

## 冻结数据与分母

数据绑定到已提交的 `fire_m5_assisted_shadow` fixture 及其 manifest/digest。只使用 24 条
`EXECUTION`：18 条 `PROCEED`、6 条 `CLARIFY`。

Retrieval 分母进一步拆分：

- `R_TARGET=16`：存在至少一个可接受稳定目标的 `PROCEED`；
- `R_EMPTY=2`：Oracle 明确要求无候选/证据不足的 `PROCEED`；
- `R_CLARIFY=6`：应在 Intent 阶段短路，不进入 Retrieval 指标分母。

禁止把 `R_EMPTY` 当作 Recall miss，也禁止把 `R_CLARIFY` 加入召回分母冲淡结果。

## 已冻结基线事实

用 Oracle retrieval seed 重放当前 `treeguard.lexical-structural-retrieval.v1`：

- `R_TARGET` Recall@8 = 16/16；
- `R_TARGET` Recall@20 = 16/16；
- `R_TARGET` MRR = 1.0；
- `R_EMPTY` 正确空结果 = 2/2。

因此“理想 Intent → 当前召回”已经没有提升空间，不能作为选择新检索算法的主实验。
M5 实际三轮 `38/46` 是模型实际 Intent 进入召回后的端到端观测；原始草稿未进入仓库，
本任务不会用新的生成结果冒充逐字复现。

## 已定位的合同错位

18 条 `PROCEED` 的 Intent Oracle 中：

- subject、role、scenario、lifecycle、confirmed_facts、assumptions 均为 18/18
  `NOT_COMPARED`；
- 当前召回却把这些字段中的大部分作为主要 query terms；
- requirement text 当前不进入召回。

所以一个 Intent 可以被判为 `MATCH`，同时携带完全不同的召回文本。该现象必须归类为
`INTENT_RETRIEVAL_INTERFACE_GAP`，不能简单归因于小模型“不理解树”。

## 待比较方案

### A：现有基线

只使用模型 Intent 的自由文本与结构字段；原始 requirement text 不进入召回。

### B：解耦查询（推荐）

- 始终使用原始 requirement text 作为受信任查询来源；
- 只接收通过本地枚举/来源校验的 Intent 结构约束；
- subject、confirmed facts 可作为低权重模型扩展并可单独关闭；
- assumptions、evidence gaps、clarification question 不进入主查询；
- proposed parent 只作为可选软 boost，不是硬检索范围。

首轮 B 使用无外部依赖的确定性加权词法/整数 IDF 风格方案，不引入 embedding。
该选择避免浮点分数进入持久化哈希，并保留逐项可解释性；若未达到冻结门槛，再单独
评估 BM25、embedding 或混合检索，不在同一切片叠加多种算法。

### C：模型改写优先、原文回退

模型自由文本仍为主查询，只有无候选时才使用 requirement text 重试。它保留更多模型
语义改写能力，但一次查询的失败来源更难解释，并可能造成排序在两套策略之间跳变。

## 固定查询视图

每条 `PROCEED` 必须在下列确定性视图上运行；同一视图对 A/B 使用相同树、目标集合和
Top-K：

1. `V_CANONICAL`：冻结 retrieval seed，用于无回归检查；
2. `V_FREE_TEXT_DROPPED`：清空所有未被 Intent Oracle 比较的模型自由文本，模拟合法但
   语义信号缺失的 Intent；
3. `V_PARENT_ABSENT`：去掉 proposed parent，验证纯对话入口；
4. `V_PARENT_WRONG_BRANCH`：使用固定规则选择另一个顶层分支的父节点，验证错误点击不会
   成为硬前提；
5. `V_REQUIREMENT_ONLY`：只保留原始 requirement text 与请求中可校验的结构 hint。

错误父节点的构造规则必须在 harness 中确定性实现并绑定版本；不得人工挑选“容易”或
“困难”的错误分支。

## 指标与门槛

### 主指标

- B 在 `V_REQUIREMENT_ONLY` 的 `R_TARGET` Recall@8 必须达到 16/16；
- B 在 `V_FREE_TEXT_DROPPED` 的 `R_TARGET` Recall@8 必须达到 16/16；
- B 在上述两个视图的 MRR 均不得低于 0.90；
- B 在 `V_CANONICAL` 不得使任何当前 rank-1 目标跌出 Top-8。

### 安全与鲁棒性

- 所有视图中 `R_EMPTY` 的 Oracle 状态匹配必须为 2/2；
- `V_PARENT_ABSENT` 的 `R_TARGET` Recall@8 至少 15/16；
- `V_PARENT_WRONG_BRANCH` 不允许正确目标因 parent 被硬过滤；Recall@20 至少 15/16；
- 相同输入重复运行三次，候选 node ID、分数、排序和摘要 hash 必须逐字节一致；
- A/B 均只报告固定错误码与聚合指标，原始模型内容不进入仓库。

### 失败归因

每个单元只能记入一个主失败阶段：

- `QUERY_SIGNAL_MISSING`：冻结 query representation 没有可用词项；
- `RETRIEVAL_TARGET_ABSENT`：目标未进入 Top-20；
- `RETRIEVAL_RANK_BELOW_K`：目标进入 Top-20 但未进入 Top-8；
- `RETRIEVAL_FALSE_POSITIVE_ON_EMPTY`：应为空时返回候选；
- `CONTEXT_POISONING`：错误 parent 使原可召回目标跌出 Top-20；
- `CONTRACT_OR_REPLAY_FAILURE`：Schema、digest 或确定性回放失败。

Semantic 不在本实验中运行，其错误不得混入上述 code。

## 决策规则

- B 全部通过：冻结 B 的查询边界和检索表示，进入 Semantic/Policy 职责收缩实验；
- B 仅在同义/跨层表达视图失败：保持查询解耦，下一任务才评估 embedding/混合检索；
- B 出现 `R_EMPTY` 或错误 parent 安全退化：不晋升，先修查询/结构约束边界；
- A 与 B 都无法通过 requirement-only：说明当前测试数据或节点表示不足，停止调权重，
  先审核表示与 Oracle；
- 任何门槛都不得在首次 B 结果产生后下调。

## 后续未见确认

只有 B 和后续职责收缩方案均冻结后，才准备新的未见确认集。确认集只运行一次；失败后
回到下一版本开发集，不在同一未见集上继续调权重或 Prompt。
