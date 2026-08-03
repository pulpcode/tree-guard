# M4 场景覆盖蓝图（无正文）

## 蓝图边界

本文件只定义覆盖格和选择规则，不包含请求正文、节点名称、稳定目标 ID、候选编号
或隐藏 Oracle 值。场景正文和目标只能在第二阶段按冻结合同物化到私有 sidecar。

覆盖不做“意图 × 目标类型 × 干扰 × Top-K × 动作 × 关系”的全展开。每条场景
只有一个主风险，可附带少量次要 tag；每个格必须说明它填补的判断缺口。

## 共同选择门

1. 只由冻结的 fire medium 虚构树证据和 11 个确定性 plan units 支持，不从 M3
   产物、现有 fire scenarios 或旧语义答案派生。
2. fire medium 没有青岚式 curated/background/filler 分类；不得迁移该分类或
   臆造 filler。每个目标必须在冻结树中存在并经人工独立证明可接受。
3. 意图主体、所有权、单体/集合范围、类型和基数可以由树证据人工解释。
4. 可接受目标集合已经穷尽审核者认可的等价答案。
5. 请求正文不泄漏稳定 node ID、运行时临时 ref、Oracle 动作或关系标签。
6. 场景在冻结 Top-K 下可执行；不得运行后放宽 K。

## 最多八个覆盖格

| 格 | 预期路径 | 主风险 | 必需能力 | 可合并次要 tag |
|---|---|---|---|---|
| B01 | 完整链路 | clear reuse 风险单元 | 清晰意图、稳定目标、召回与推荐一致 | 结构邻近干扰 |
| B02 | 完整链路 | clear reuse 分支覆盖 | 第二分支上的完整链路，不要求多等价目标 | 稳定排序 |
| B03 | 完整链路 | wrong-parent/cross-branch | 拒绝错误父级，动作/目标/关系联合合法 | 分支作用域 |
| B04 | 完整链路 | kind conflict | 意图类型与推荐关系不被冲突 hint 误导 | Top-K（若证据支持） |
| B05 | 完整链路 | cardinality conflict | 基数、目标合同与推荐动作一致 | 集合作用域 |
| B06 | 完整链路 | 剩余 clear reuse 分支 | 第三条独立分支链路 | hard negative（若证据支持） |
| B07 | 完整链路 | 剩余计划内 retrieval/recommendation 单元 | 填补尚缺的召回或推荐关系 | 空目标（若证据支持） |
| B08 | 条件式 | insufficient-evidence 或 unbounded-combination | 合法澄清短路 | homonym 明确不适用 |

B01–B07 从 planner 的 6 个 RETRIEVAL 和 3 个 RECOMMENDATION 单元中选择，
因此 7 条完整链路有 2 个计划内余量，但没有计划外替补调用。B08 只从 2 个 INTENT
ambiguity 单元审计；planner 的 `HOMONYM_CLARIFICATION=NOT_APPLICABLE`，不得
制造同名歧义。若两个 ambiguity 单元都不构成合法澄清，B08 记为
`NOT_APPLICABLE`，再从剩余的既有完整链路单元回填 B08F。

表中动作名称只描述能力类别，不冻结未来 Schema 字段或枚举。

## 覆盖维度与验收观察

### 意图

- `PROCEED`：意图足以进入召回；Oracle 保存一组可接受的规范化意图 profile。
- `CLARIFY`：只有合法歧义时适用；必须在召回前短路。
- 不以自由文本逐字相等代替语义字段比较；精确比较策略等待冻结合同。

### 召回

- 唯一目标必须覆盖；多可接受目标只有树审计证明存在时才使用，不能作为配额。
- Top-K 边界只有确定性召回复算证明目标恰在边界时才使用；否则只保留一般
  `rank <= K` 判断，不制造边界样本。
- Oracle 只保存稳定 node ID 集合与 K；比较器负责映射当次 candidate ref/rank。
- hard negative 只有树结构与召回结果共同支持时才作为 tag；不能为了沿用旧蓝图
  人工指定干扰。

### 推荐

- 覆盖正向复用和冲突类；显式无目标只有计划单元与树证据共同支持时才纳入。
- 动作可为集合；多种动作都符合树证据时不能强制单值。
- 目标约束二选一：非空的可接受稳定目标集合，或明确 `MUST_BE_NULL`。
- 关系类别按稳定目标绑定；动作、目标和关系必须联合合法。

## 澄清合法性审计

1. 只审计 planner 的两个 INTENT ambiguity 单元，并隐去准备 Agent 的结论。
2. 检查是否有至少两个同等合理且会改变目标/动作的解释，或缺少一个进入召回
   必需且不能从树推断的事实。
3. 仅有风格偏好、轻微宽泛或可由唯一树证据消解的差异，判为非法歧义。
4. 合法则设 B08 为澄清短路；两个单元都不合法则记录 `NOT_APPLICABLE`，
   不得改写正文制造歧义，并从剩余计划内完整链路单元回填 B08F。

## 新树适用性结论

- **直接适用**：B01、B02、B03、B04、B05，以及从剩余 clear-reuse 单元选择的
  B06/B07；planner 提供 9 个完整链路候选单元，足以冻结 7 条。
- **条件适用**：多可接受目标、Top-K 恰好边界、hard negative、显式空目标；这些
  只能作为已选格的次要 tag，不再是必须配额。
- **条件澄清**：B08 只允许 insufficient-evidence 或 unbounded-combination
  单元通过人工合法性审计后使用。
- **不适用**：homonym clarification；planner 已确定为 `NOT_APPLICABLE`。
- **禁止**：从现有 fire scenarios 补答案、增加计划外调用、为沿用旧蓝图制造
  目标/歧义、或对各维度做笛卡尔积。

## 候选准备质量观察

准备 Agent 的质量与产品执行分开统计。每个候选人工检查来源与绑定、可答性、
覆盖新增、意图解释、召回集合完备性、Top-K 可执行性、推荐联合约束、Oracle
隐藏和目标树证据。公开结果只允许输出：

- proposed / accepted / revised-accepted / rejected / not-applicable 数量；
- 每个覆盖格是否填充；
- 固定 finding code 聚合计数；
- 已用审核分钟数和是否停线。

不得输出请求正文、树节点正文、稳定目标 ID、Oracle 集合、人工意见或模型文本。

## 第二阶段冻结结果（聚合）

- B01—B07 各冻结一条 `PROCEED` 完整链路，覆盖格无重复。
- B08 的第一澄清候选通过人工合法性审核：树中至少两个同等合理且会改变目标的
  负责人属性解释成立，因此冻结为唯一 `CLARIFY` 短路。
- 第二澄清候选和两个完整链路回填候选均已接受审核，但当前配额无需启用；三者
  不生成 capability overlay，也不进入执行分母。
- 最终组成固定为 8 条、7+1；`NOT_APPLICABLE_WITH_BACKFILL` 与 B08F 本次不适用。
- 上述记录只公开覆盖状态和计数；请求正文、稳定目标与完整 Oracle 仅存在于隐藏
  sidecar。
