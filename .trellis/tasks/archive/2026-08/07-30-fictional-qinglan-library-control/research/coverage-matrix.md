# Coverage Matrix：青岚社区图书馆

规划类别只描述可观察行为，不创建新的运行时枚举或语义 Gold。

| Ref | 单一主要风险 | Challenge tags | 预期可观察类别 |
|---|---|---|---|
| QL-C01 | 清晰需求 | `clear_intent`, `category_scope` | 稳定候选 |
| QL-C02 | 同名异义 | `homonym`, `type_signal` | 区分上下文或追问 |
| QL-C03 | 跨分支归属冲突 | `cross_branch` | 不仅凭词面接受父节点 |
| QL-C04 | 节点类型冲突 | `kind_conflict` | 暴露冲突 |
| QL-C05 | 基数冲突 | `cardinality_conflict` | 暴露冲突 |
| QL-C06 | 错误父节点提示 | `wrong_parent_hint` | 不盲从提示 |
| QL-C07 | 近名 hard-negative | `near_name_negative` | 排除近名错误候选 |
| QL-C08 | 证据不足 | `insufficient_evidence`, `judgment_requires_evidence` | 需要证据 |
| QL-C09 | 应当追问 | `clarification_required` | 需要澄清 |
| QL-C10 | 应当拒答 | `refusal`, `cartesian_request` | 拒绝无界全组合造树 |
| QL-C11 | 结构异常判断 | `near_duplicate_subtree`, `unusual_depth` | 不武断判定重复 |
| QL-C12 | 重放基线锚点 | `small_tree_replay_baseline` | 稳定候选 |

每个 coverage cell 为：

```text
DOMAIN_CONTROL
+ challenge_tags
+ SMALL_40_60
+ expected_observable_category
```

QL-C12 当前只建立小型候选基线，不单独宣称跨规模稳定。只有未来数据任务在独立
批准的中型树上配对重放后，才允许报告规模变化下的结果。

## Pairwise 选择约束

- 不展开领域 × 规模 × 风险 × 故障 × 模型 × Prompt。
- 每个场景只有一个主要风险，可携带相关标签。
- 类型、基数、父节点和词面干扰按 pairwise 选择，不覆盖所有组合。
- transport 和模型非法输出故障不进入本数据集。

## 人工审阅选择

- 12 个场景全部单人筛查。
- 固定 seed `20260730` 抽取 4 个随机复核样本。
- QL-C01、QL-C08、QL-C10、QL-C12 由同一审核人在完成其余场景后进行重点复查；
  当前不要求双人复核。
