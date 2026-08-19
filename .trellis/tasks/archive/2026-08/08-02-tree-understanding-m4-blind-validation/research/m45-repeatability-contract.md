# M4.5 24×3 重复性报告合同

## 缺口

`scenario-capability-report.v1` 有意冻结为首轮 8 条门槛：最多 8 个 run、7+1/8+0、
至少 6 条完整路径匹配、每阶段最多 1 条失败。新密封方案要求 24 条场景各执行 3 次，
不能修改 v1 常量或把 72 个观测伪装成 8 个。

## 方案

新增独立 `scenario-repeatability-report.v1`，复用现有单条 overlay/run，不改变 v1：

- 输入精确为 3 个 round，每轮 24 个 run；每轮 overlay 唯一，三轮 overlay 集合与
  expected route 一致；
- 每轮组成固定 18 `PROCEED` + 6 `CLARIFY`；同一 overlay 跨 round 重复是预期，
  round 内重复固定拒绝；
- 公开报告记录每轮端到端与逐阶段聚合、3/3 稳定数、实际执行召回的命中数、Intent/
  Semantic 首发和重试后合同合法计数、澄清混淆矩阵、硬冲突错误复用数；
- 最终合同合法率使用整数交叉乘法判断 98%，不持久化浮点阈值；
- 门槛固定：准备闭包通过、三轮每轮至少 18/24 完整匹配、稳定 3/3 至少 18/24、
  实际执行召回 100%、Intent/Semantic 最终合同合法率至少 98%、硬冲突错误复用为 0、
  四类 hard failure 为 0；
- 澄清 precision/recall 由 TP/FP/FN/TN 公开计数表达，本版只观测不另设阈值；
- 报告不含 overlay hash、request、Oracle、node ID、Prompt、模型文本或 trace。

## 数据与计划关系

24 条场景可以来自多个来源绑定 batch，或同一稀疏计划的多个独立候选批次。每个单条
overlay 仍完整绑定自己的 plan/batch/reviewed bytes；新报告只要求三轮场景集合一致，
不把多个计划伪造成一个 plan，也不改变 planner 的 32 单元硬上限。

## 兼容性

- `scenario-capability-overlay.v1`、`scenario-capability-run.v1`、
  `scenario-capability-report.v1` 不变；
- 新合同使用独立 Schema、Python 类型、严格 parser 与聚焦测试；
- 原 8 条完整 suite 必须逐字节回归通过。
