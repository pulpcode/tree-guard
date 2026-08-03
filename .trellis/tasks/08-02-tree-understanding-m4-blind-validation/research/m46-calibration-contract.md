# M4.6 Silver 评分合同校准

## 目标

在已经揭盲的 M4.5 Silver 上区分“模型能力不足”和“v1 评分语义过窄”。本轮只校准
评测合同，不修改 Intent/Semantic Prompt，不恢复 holdout 或门禁资格，也不把离线
重评分解释为模型能力提升。

## 预注册假设

1. 正向复用场景需要验证指定目标是否进入 Top-K，继续使用 `TARGET_HIT`。
2. hard negative、类型/基数冲突和显式新增场景的召回职责是提供有界对照证据，不存在
   唯一正确目标，使用 `BOUNDED_EVIDENCE`；不得把运行前任意冻结的 Top-1 当 Gold。
3. 无候选才是任务实质要求时使用 `EMPTY_RESULT`；本批没有该类执行项，但合同必须
   提供确定性表示。
4. Semantic 首先按原 Oracle 的完整 action-target-relation 联合结果判断
   `PREFERRED_MATCH`。`NEED_CLARIFICATION`、`NEED_EVIDENCE`、`ABSTAIN` 是固定的
   无目标安全退让动作；非首选时记为 `SAFE_ALTERNATIVE`。其余非首选正向动作记为
   `UNSAFE_MISMATCH`，不能因“没有直接复用”自动算正确。
5. 原 v1 召回短路导致 Semantic 没有执行时，只能记录覆盖缺口；不得从缺失输出推断
   Semantic 正确，也不得重写原 run。

## 场景族政策

- `TARGET_HIT`：`UNIQUE_REUSE`、`MULTI_ACCEPTABLE`、`TOP_K_BOUNDARY`、
  `CROSS_BRANCH_CONFLICT`。
- `BOUNDED_EVIDENCE`：`HARD_NEGATIVE`、`KIND_CONFLICT`、
  `CARDINALITY_CONFLICT`、`EXPLICIT_NULL_NEW`。
- `CLARIFY_*` 不进入召回/Semantic 校准分母，继续使用原 Intent 澄清混淆矩阵。

该映射按场景族冻结，不读取单条模型动作后增加例外。

## 防过拟合约束

- 原 M4.5 run、严格聚合和模型输出字节保持不变；新结果与旧结果并列，不覆盖基线。
- calibration policy 独立绑定原 overlay 与原 Oracle digest，固定
  `CODEX_ASSISTED / SILVER / CALIBRATION_ONLY / gate_eligible=false`。
- 本轮先完成离线 A/B。只有新增可达 Semantic 覆盖确实缺失时，才讨论同一冻结模型
  配置下的补跑；补跑也只能更新校准证据。
- 任何 Prompt、模型、温度、召回算法或 family 映射变化都进入新的校准版本；不得在
  同一报告中混合。

## 输出

公开 A/B 仅报告固定状态与聚合计数：原严格召回、校准召回、Semantic 首选/安全/
不安全/未观测、因旧短路新增可达但未执行的数量，以及完整路径是否具备重评覆盖。
不输出请求、节点、Oracle、Prompt、模型文本、trace 或来源 hash。
