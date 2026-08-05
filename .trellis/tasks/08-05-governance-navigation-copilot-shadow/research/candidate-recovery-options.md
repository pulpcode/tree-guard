# 候选恢复路线比较

## 结论

第一版推荐采用“原始需求召回底座 + 角色/上下文软重排”，而不是直接晋升 R2 或沿用
v1 `CandidateSet`。这不是宣称词法召回已经足够，而是把它降级为一个永远可见、可回放的
候选恢复底座；角色、页面和选中节点可以帮助排序，但不能把底座中的候选裁掉。

## 仓库事实

- `retrieval_query.build_decoupled_candidate_set()` 已以原始 `requirement_text` 为主信号搜索
  完整 resource 树，并把父节点上下文作为软信号，适合作为宽召回底座。
- `retrieval_roles.build_role_candidate_set()` 和
  `retrieval_role_tolerant.build_role_tolerant_candidate_set()` 虽然先取得宽候选，但都要求
  TARGET 名称或路径相似度非零；因此角色在当前实现中仍是硬门。
- `retrieval.build_candidate_set()` 已接入旧 Workbench 流程，但要求
  `CONFIRMED_FOR_RETRIEVAL`，并依赖自由文本 Intent 字段，不符合清晰请求直接检索和
  单 case 短对话的新边界。
- H1/H2 尚未证明 embedding 路线优于同预算词法基线，本任务也明确不重启 H3。

## 方案 A：原始需求召回底座 + 软重排（推荐）

1. 用原始需求在完整树上取得固定上限的宽候选池；首版可沿用现有确定性词法实现。
2. 角色提议、显式结构提示、页面上下文和选中节点只增加软分或生成差异说明，不执行
   hard filter。
3. 对多路结果按稳定节点身份合并、去重并确定性排序；内部池可以宽于界面上限，最终只把
   最多8项送给 relation-only Semantic 和 Workbench。
4. 候选均不正确时，保留候选外人工纠正，并记为 `CANDIDATE_MISS / USER_CORRECTED`。

优点是与既定架构边界一致，并能把“召回没有覆盖目标”和“Semantic/人工没有选对”分开
统计。限制是它仍只是首版可解释底座，不能凭此获得生产检索资格。

## 方案 B：直接复用 R2

优点是实现改动较小，也保留了角色化解释。主要问题是 TARGET 非零仍是候选资格条件；一旦
模型角色提议错误或用户表达非字面化，正确候选可能在 Semantic 之前被消失。这与“角色
只能软建议”直接冲突，因此不建议作为产品主路径。R2 可以保留为排序特征或对照腿。

## 方案 C：继续使用 v1 `CandidateSet`

优点是已有 Workbench 接口和回归覆盖。问题是它把旧 Intent 确认作为检索前置状态，且
Intent 字段与新四键理解、短对话和 relation-only Semantic 的职责边界不同。继续扩展会把
旧合同和新合同耦合，适合保留兼容，不适合作为新纵切核心。

## 首版不做的事

- 不增加 embedding、向量索引或 H3；
- 不让 LLM 浏览整棵树并直接指定稳定节点；
- 不以 Top-1 自动完成业务绑定；
- 不用候选外人工纠正反向美化 Retrieval 命中率；
- 不承诺同一 case 内多轮自动改写或跨 case 记忆。
