# 修正导航密封测评阶段归因

## 目标

在不修改既有密封资格成绩、阈值和 v1 工件语义的前提下，新增一个只读、确定性、
可回放的诊断聚合合同。它把理解合同降级、结构 Profile、产品路线、召回、Semantic、
Policy 和终态分别记账，避免把下游 `NEED_EVIDENCE` 导致的路线变化误归因为
`UNDERSTANDING`。

## 已确认事实

- 既有 `first_failure_stage` 是资格合同 v1 的冻结语义，不能在揭盲后原地改写。
- `clarification_match` 实际比较的是最终产品路线与 Oracle 期望路线；最终路线由
  candidate/Policy 状态共同决定，不是纯 Understanding 输出。
- 现有 observation 已含匿名布尔量和名次，足以生成非互斥诊断计数；无需读取或公开
  请求正文、模型响应、节点、路径或 Oracle 正文。
- 本次正式资格结论保持 `HOLD_MODEL_CONTRACT`，诊断聚合不得改变 qualification。

## 范围

1. 新增版本化 `navigation-copilot-sealed-diagnostic-aggregate.v1` 合同和 JSON Schema。
2. 从受信任的 manifest 与 observation v1 确定性生成诊断聚合。
3. 使用独立、可重叠的计数，至少包含：
   - Understanding 模型降级；
   - Profile 不匹配；
   - 产品路线不匹配；
   - C1 Top-8 召回漏失；
   - Semantic 错误自信或错误高亮；
   - Policy 不匹配；
   - 终态不匹配；
   - 联合匹配和无降级路径。
4. 输出只包含固定版本、来源 manifest hash、聚合计数、诊断用途标志和内容摘要。
5. 增加严格回放、缺失/重复分母、类型、哈希、Schema 字段和敏感字段泄漏测试。

## 非目标

- 不修改 v1 observation、aggregate、`first_failure_stage`、资格阈值或状态优先级。
- 不修改 Prompt、Provider、Retrieval、Semantic、Policy、Workbench API 或 UI。
- 不读取或写入本次密封运行的逐条请求、响应、节点或 Oracle 正文。
- 不在已揭盲的 48 条分母上调参、重跑模型或产生新的资格声明。
- 不把诊断计数宣称为互斥根因，也不产生 Gold、Patch 或生产资格。

## 验收条件

- [x] 既有资格聚合测试保持不变并通过。
- [x] 新诊断聚合按 48 条主轮、唯一 scenario ref 和 manifest 完整分母严格校验。
- [x] 各维度独立计数，可重叠；产品路线不匹配不再命名为 Understanding 错误。
- [x] 诊断输出无 scenario ref、节点 ID、请求、响应、Prompt、Oracle 正文或逐项记录。
- [x] 修改任一计数字段或来源绑定后，严格回放拒绝。
- [x] JSON Schema、Python 字段集、序列化与哈希域一致。
- [x] 聚焦测试、Trellis validate、Python 语法检查和 `git diff --check` 通过。

## 数据边界

仅使用仓库内完全虚构的测试对象和固定聚合计数。完整 observation 仍属于私有输入；
公开诊断聚合采用正向允许列表构造，不持久化任何逐项内容。本任务不调用网络或模型。
