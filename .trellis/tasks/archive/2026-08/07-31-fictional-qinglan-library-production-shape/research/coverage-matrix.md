# Coverage Matrix：青岚生产形状集（草案）

本批只安排 8 条场景，不展开“领域 × 规模 × 风险 × 故障 × 模型”全组合。每条
场景只有一个主要风险，其他标签仅用于聚类。

| cell | 主要风险 | 次要标签 | 预期可观察类别 | 锚点依赖 |
|---|---|---|---|---|
| QP-C01 | CLEAR_INTENT | replay-of-QS-C01, direct-match | 可直接判断 | 是 |
| QP-C02 | HOMONYM | replay-of-QS-C02, hard-negative | 存在多解 | 是 |
| QP-C03 | INSUFFICIENT_EVIDENCE | replay-of-QS-C08, bounded-candidates | 证据不足 | 是 |
| QP-C04 | WRONG_PARENT_HINT | replay-of-QS-C06, branch-conflict | 应当追问 | 是 |
| QP-C05 | NEAR_NAME_HARD_NEGATIVE | candidate-limit, stress-neighbor | 不得误选近名 | 否 |
| QP-C06 | INSTANCE_SCOPE_CONFLICT | value-owner, collection-item | 应当拒绝错误归属 | 否 |
| QP-C07 | REORDER_STABILITY | deterministic-replay | 重排前后结果一致 | 否 |
| QP-C08 | LARGE_TREE_NO_SIGNAL | stress-only, oracle-boundary | 无效果证据时不得下最优结论 | 否 |

## Pairwise 选择

- 四条锚点场景分别覆盖直接回答、多解、证据不足和错误父节点。
- 四条形状场景分别覆盖候选上限、实体作用域、重排和 filler 隔离。
- transport、模型非法 JSON 和 Prompt 变体继续由既有小型合同测试承担，不在
  2,001 节点档重复展开。

## 审核选择

- Codex 预审 8/8。
- 人工审核 8/8。
- 固定 seed 自检 3 条，并复查 4 条高风险场景。
- `dual_review_limit=0`，不产生双审声明。
- 除场景审核外，Codex 必须预审每个 record-referent cluster 至少一个代表；人工
  页面应能直接判断“该记录描述谁”以及其父子关系。
