# M3 现有完全虚构数据集复用研究

## 问题与范围

- 日期：2026-08-02；
- 问题：既有青岚三档完全虚构数据能否作为 M3 信息树测试场景准备 Agent 的主要
  开发与验收基座；
- 范围：只检查本仓库已合并的完全虚构 fixture、聚合清单、覆盖矩阵和人工审核
  状态，不使用外部查询、真实树、模型请求/响应或受保护材料。

## 仓库依据

- `qinglan_library_control`：48 节点、12 个场景、4 个一级分支；
- `qinglan_library_semantic`：312 节点、20 个场景、6 个一级分支；
- `qinglan_library_production_shape`：2,001 节点、8 个场景、6 个一级分支；
- 三档数据都声明完全虚构、非真实数据衍生、`gold_eligible=false`，promotion 记录
  表明候选已完成人工/Codex 辅助审核并冻结，但没有升级为领域 Gold；
- 中型与生产形状数据包含同名、跨分支、错误父节点、kind/cardinality 冲突、证据
  不足、无界组合和跨规模重放等参考场景；
- 现有运行时适配只把建议观察类别投影为意图阶段可观察状态，不证明召回或推荐
  语义正确。

## 可复用边界

1. 三档 `tree.json` 直接作为确定性规划、局部投影、预算和重排测试输入；
2. `scenarios.json`、`coverage-matrix.json` 和 promotion 只作为生成后的隐藏参照，
   不进入真实 LLM 的模型输入，防止答案泄漏；
3. 固定虚构 transport 可以复用参考请求验证解析、归并和失败合同；真实模型实验
   只要求结构/风险/证据等价，不要求逐字复现参考文本；
4. 原始稳定节点 ID 只留在可信本地规划和审核边界，模型视图继续使用临时引用；
5. 参考场景可以支持 7 个 M3 核心风险族；`NEW_NODE_PLACEMENT` 缺少明确对应，
   应在既有树上增加 M3 专用 overlay，不另造平行数据集；
6. 现有 fixture 保持不可改写；M3 新增计划、证据、digest、审核和批次 sidecar/
   overlay 合同。

## 风险族映射

- `CLEAR_INTENT` + `existing_property` → `CLEAR_EXISTING_REUSE`；
- `HOMONYM` → `HOMONYM_CLARIFICATION`；
- `CROSS_BRANCH` / `WRONG_PARENT_HINT` → `WRONG_PARENT_OR_CROSS_BRANCH`；
- `KIND_CONFLICT`、`CARDINALITY_CONFLICT`、`INSUFFICIENT_EVIDENCE` 直接对应；
- `REFUSAL` / `CARTESIAN_DENSITY` → `UNBOUNDED_COMBINATION`；
- `NEW_NODE_PLACEMENT` → 现有覆盖缺口。

## 结论与限制

- M3 不需要重新创建 48/312/2,001 节点树，应以现有青岚三档 fixture 为主要基座；
- 现有人工审核结果是完全虚构回归参照，不是生产领域 Gold 或自动 Oracle；
- 首个 INTENT 切片只能验证意图可观察状态，其他风险场景在 M3 中首先证明 Agent
  能准备有界候选，不能提前声称 MVP 的召回或推荐能力通过；
- 本研究不保存 Prompt、模型文本、请求/响应 envelope、凭据或真实业务材料。

## 实现落点

- 三档回归测试只显式打开各自的 `tree.json`；312 节点计划使用独立目录
  `tests/fixtures/fictional/qinglan_tree_understanding_m3/` 中的 overlay；
- overlay 绑定 312 节点快照，把完全虚构且树中不存在的“无障碍替代文本说明”
  作为 `PROPERTY/string/SINGLE` seed 放在“电子图册”父节点下；它不含自然语言
  request、Oracle、审批或模型输出；
- 生成完成后的隐藏对照固定使用 `QS-C01`、`QS-C02`、`QS-C06`、`QS-C04`、
  `QS-C05`、`QS-C08`、`QS-C10` 映射七个既有风险族；
- 虚构固定 transport replay 只证明计划、投影、模型合同和归并未读取隐藏答案，
  不计为真实模型语义理解证据。
