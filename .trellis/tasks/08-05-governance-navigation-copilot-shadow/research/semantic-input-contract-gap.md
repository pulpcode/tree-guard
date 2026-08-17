# Navigation Semantic 输入合同缺口

## 结论

当前密封资格运行保持正式负结果，不能据此修改分母、重跑同一批次或调宽确定性
Policy。仓库实现检查发现一个先于模型能力判断的合同缺口：Navigation Semantic v1
只接收结构意图与候选视图，没有接收权威的原始 `requirement_text`。因此模型可以比较
候选的结构形状，却没有足够输入判断“候选是否表达用户实际需求”。

这说明当前结果不能单独归因为模型不具备语义理解能力；至少有一部分失败来自模型任务
输入不完整。修复后仍需使用非密封、完全虚构的开发数据重新验证，不能宣称效果已经提升。

## 仓库证据

- `NavigationSemanticProjection.to_model_dict()` 仅输出
  `structural_intent`、`candidate_status` 和 `candidates`。
- `BailianNavigationSemanticProvider` 的 v1 Prompt 要求返回五类关系，但没有给出五类关系
  的判定边界。
- `apply_navigation_policy()` 只在恰有一个结构兼容的
  `SEMANTICALLY_EQUIVALENT` 时突出候选；多个等价候选进入 `AMBIGUOUS`，没有等价候选
  进入 `NEED_EVIDENCE`。
- 既有关系—Policy 开发实验表明，严格的本地 Policy 能减少不安全的直接动作。因此本轮
  不以放宽 Policy 代替输入合同修复。

## 方案比较

### A. 新增 Semantic v2 输入（采用）

新增并行、版本化的 Semantic v2 合同：包含有界的权威原始需求、结构意图和候选视图；
Prompt 明确定义五类关系的互斥判定边界。保留 v1 字节、回放与默认产品路径不变。

优点是修复了任务输入缺失且不改变安全策略；代价是需要新增 Schema、运行时类型、
Provider 和可信来源回放测试。

### B. 放宽 Policy（拒绝）

把 `REUSES_CONTRACT` 或排序第一直接解释为可突出候选。该方案会把模型不确定关系转成
错误自信，违背 D6 和既有 D3，不采用。

### C. 取消 Semantic、完全人工选择（保留为降级）

该方案安全但不能验证自动差异比较是否有产品价值。继续作为 `NEED_EVIDENCE` 的降级
路径，而不是替代主要路线。

## v2 最小边界

- `requirement_text` 必须来自可信 `IntentRequest`，不得来自模型摘要；
- 输入仍只使用 `C001`—`C008` 临时引用，不包含稳定节点 ID、hash、Oracle、动作或审批；
- 五类关系必须在 Prompt 中给出明确边界；不确定或缺证据时返回 `NEED_EVIDENCE`；
- 输出仍逐项、等长、顺序覆盖候选，不允许模型选择动作；
- 确定性 Policy 保持“唯一兼容等价才突出”的规则；
- v1 保持历史回放与默认入口，不做原位升级；
- 首轮只在非密封 clean-room 开发数据验证合同与行为，不运行已揭盲的 48 条资格集。

## 限制

本结论只定位出一个确定的实验设计/实现缺口，不证明修复后模型一定达到资格门槛，也不
证明召回、交互或候选标签已经最优。只有新合同经过独立开发验证并在未来新密封分母上
通过，才能重新申请生产 Shadow 资格。
