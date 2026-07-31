# Coverage Matrix：青岚中型语义挑战集

## 组合方法

每条场景只有一个 `primary_risk`，可携带多个相关 challenge tags。20 条场景以
pairwise/coverage cell 选择分支、节点合同和预期状态，不展开
“领域 × 规模 × 风险 × 模型 × Prompt”。

```text
coverage_cell =
  SEMANTIC_CHALLENGE
  + primary_risk
  + branch_context
  + contract_signal
  + expected_observable_category
```

## 计划场景

| Ref | Primary risk | Branch context | Expected observable category | 说明 |
|---|---|---|---|---|
| QS-C01 | CLEAR_INTENT | 馆藏资源 | STABLE_CANDIDATE | 清晰且可直接判断 |
| QS-C02 | HOMONYM | 读者服务/公共活动 | NEED_CLARIFICATION | 同名字段跨分支 |
| QS-C03 | CROSS_BRANCH | 服务/活动 | CONFLICT_VISIBLE | 归属提示跨分支 |
| QS-C04 | KIND_CONFLICT | 空间 | CONFLICT_VISIBLE | 不给父节点提示，只探测概念与属性类型冲突 |
| QS-C05 | CARDINALITY_CONFLICT | 活动 | CONFLICT_VISIBLE | 明示把既有 string/MULTIPLE 改为 string/SINGLE |
| QS-C06 | WRONG_PARENT_HINT | 馆藏资源/服务空间 | CONFLICT_VISIBLE | 错误父节点提示 |
| QS-C07 | NEAR_NAME_HARD_NEGATIVE | 服务 | STABLE_CANDIDATE | 近名但不同目标 |
| QS-C08 | INSUFFICIENT_EVIDENCE | 馆藏资源 | NEED_EVIDENCE | 缺少判断证据 |
| QS-C09 | CLARIFICATION_REQUIRED | 活动 | NEED_CLARIFICATION | 目标粒度不清 |
| QS-C10 | REFUSAL | 全树 | REFUSE_UNBOUNDED_COMBINATION | 拒绝无界批量请求并引导提交有界 subject/facet 清单 |
| QS-C11 | DUPLICATE_SUBSTRUCTURE | 空间/服务 | NEED_EVIDENCE | 重复结构只作疑点 |
| QS-C12 | UNUSUAL_DEPTH | 运营保障 | NEED_EVIDENCE | 提示根节点与移动要求一致，只探测异常层级证据 |
| QS-C13 | CARTESIAN_DENSITY | 全树 | REFUSE_UNBOUNDED_COMBINATION | 疑似全属性铺设 |
| QS-C14 | INSTANCE_FIELD_SCOPE_CLEAR | 数字资料 | STABLE_CANDIDATE | 单条音频记录字段 |
| QS-C15 | COLLECTION_AGGREGATE_SCOPE | 数字资料 | NEED_CLARIFICATION | 集合汇总与实例字段分离 |
| QS-C16 | POLICY_INSTANCE_SEPARATION | 馆藏资源 | CONFLICT_VISIBLE | 类别政策不得复制进每条实例 |
| QS-C17 | SINGLETON_POLICY_SCOPE | 馆藏资源 | STABLE_CANDIDATE | 单例政策字段作用域 |
| QS-C18 | ANCESTOR_SCOPE | 馆藏资源/读者服务 | NEED_CLARIFICATION | 类级与对象级范围 |
| QS-C19 | CONFLICTING_HINTS | 服务空间 | CONFLICT_VISIBLE | 文本与类型提示冲突 |
| QS-C20 | GRANULARITY_AMBIGUITY | 公共活动/读者服务 | NEED_CLARIFICATION | 父节点粒度多解 |

## 覆盖约束

- 20 个 primary risk 不重复。
- QS-C14—C17 专门覆盖整改后的实例边界；不再使用 replay anchor。
- 每个一级分支至少被一个场景覆盖。
- 只有 QS-C01、C07 可声明稳定候选；其他项不把 challenge tag 升级为精确
  候选或推荐 Gold。
- 所有场景先通过 Schema、引用、确定性、去重、coverage 聚类、数据边界、
  独立性和 oracle 越权检查。

## 人工审核选择

- 全部 20 条由 Codex 预审和用户人工筛查。
- 场景审核之外，审核者必须单独确认“本馆基本信息”为资源单例章节，三个空间
  对象为可重复 class 记录；该决定写入审核导出。
- 固定 seed 随机 self-recheck 5 条。
- 高风险 self-recheck 5 条：拒答、证据不足、异常结构和实例边界。
- 无双人复核；任何不确定案例保持非 Gold 并可直接拒绝晋升。
