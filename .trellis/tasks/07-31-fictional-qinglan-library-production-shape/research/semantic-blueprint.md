# Semantic Blueprint：青岚生产形状集（草案）

## 整树语义主体

- `tree_subject_scope=RESOURCE_SINGLETON`：整棵树描述一个完全虚构的青岚图书馆
  资源，不描述图书馆集合。
- 只允许一个 `SINGLETON_SECTION` 承载资源级标量。
- 组织分支使用 `ORGANIZATIONAL_CONCEPT`，不得直接承载成员级标量。
- 可重复对象必须使用 `PROPERTY + value_type=class + cardinality=MULTIPLE`。
- 单一嵌套记录使用 `PROPERTY + value_type=class + cardinality=SINGLE`。
- 标量字段必须属于 class 记录或唯一单例章节；集合级属性必须显式标为
  `COLLECTION_AGGREGATE` 并使用聚合语义名称。

## 一级分支草案

为支持声明的跨规模锚点，保留同一完全虚构数据线的六个一级分支合同：

1. 馆藏资源
2. 服务空间
3. 读者服务
4. 公共活动
5. 本馆基本信息
6. 运营与可达保障

它们只作为已声明的青岚 synthetic lineage 使用，不来自消防数据或真实资料
harvest。一级分支以下除锚点闭包外全部按本 Blueprint 新建。

## 节点族与规模

| family | 数量 | 作用 |
|---|---:|---|
| curated_core | 40 | 根、一级结构、值所有者锚点和少量配对重放节点 |
| approved_blueprint_background | 1,561 | 由逐 subject 显式允许表生成的正常背景 |
| stress_only_filler | 400 | 排序、候选上限和宽深形状压力，不可作为语义目标 |
| 合计 | 2,001 | 固定目标 |

建议深度分布：

| 深度 | 节点数 |
|---:|---:|
| 0 | 1 |
| 1 | 6 |
| 2 | 44 |
| 3 | 270 |
| 4 | 760 |
| 5 | 700 |
| 6 | 220 |

最大深度为 6；异常深层路径必须由单独 family 解释，不通过连续包裹制造深度。

## 值所有者合同

每个 `PROPERTY(value_type=class)` 在生成前冻结的 record blueprint 中写入：

```yaml
node_id: <稳定虚构 ID>
represents: <每一条该记录具体描述的对象/事件/规则>
parent_relation: <该记录与父记录或组织分支的关系>
entity_scope: ROOT_ENTITY | COLLECTION_ITEM | COLLECTION_AGGREGATE
cardinality: SINGLE | MULTIPLE
semantic_target_eligible: true | false
```

每个标量字段在独立 `allowed_facets_by_subject` 中声明父 record、字段名、值类型和
基数。生成器只消费已冻结的 record blueprint 与允许表，不能从 `_NODES`、树、
fixture 或输出反推允许表。

作用域沿祖先链继承：重复记录内的 `class/SINGLE` 只是该重复成员的单一组成部分，
其自身及后代仍是 `COLLECTION_ITEM`，不得提升为 `ROOT_ENTITY`。

L1 必须拒绝：

- `DATASET_ATTRIBUTE_OWNER_AMBIGUOUS`
- `DATASET_ITEM_ATTRIBUTE_ON_COLLECTION`
- `DATASET_VALUE_OWNER_INVALID`
- `DATASET_UNDECLARED_ANCHOR_COPY`
- `DATASET_RECORD_REFERENT_MISSING`
- `DATASET_PARENT_RELATION_UNDECLARED`
- `DATASET_SCOPE_ANCESTRY_CONFLICT`
- `DATASET_ALLOWLIST_DERIVED_FROM_OUTPUT`

## 允许组合

- 生成前独立物化完整 `allowed_facets_by_subject`；按记录形状允许 1–5 个标量
  facet，嵌套 class 记录不计入标量 facet 数。
- 允许表以 subject 为键，不能从两个独立列表运行全局 `product()`，也不能由
  成品树反向收集。
- 相同 facet vector 最多用于三个经解释的 subject；超过即进入重复结构 finding。
- 唯一允许的重复 child vector 是 `qs-s029` 与 `qs-s032`，用于保持
  `QP-C02` 的同名异义对照；该例外必须精确 allowlist，不能扩展到其他节点。
- stress-only family 使用独立允许表，且所有节点
  `semantic_target_eligible=false`。
- 固定 seed 只在允许表内部选择 pairwise 组合，不创造新组合。
- 217 个正常背景记录名称在生成前逐分组绑定，不再从 branch-wide 名称池抽样。
- 正常背景的非目标字段使用逐分组绑定的通用治理 profile，并在每个已绑定
  profile 内做固定组合抽样；它只提供 production-shape 背景，不承担领域 Gold
  或语义目标。

## 跨规模锚点

锚点合同投影固定包含：

```text
node_id
parent_node_id
path_labels
kind
name
value_type
cardinality
constraints
```

`child_node_ids` 和 sibling `order` 不属于锚点投影，因为大树增加背景节点后它们
可能合理变化。测试不得把“祖先新增子节点”误报为锚点语义变化。

- 从已修正的 312 节点中选择 24 个依赖闭合节点作为锚点。
- 只允许这 24 个节点保持锚点投影字段一致。
- 其余 1,977 个节点必须使用本 Blueprint 新定义的 family、ID、名称和路径。
- 配对重放只覆盖 4 条场景；结论不得扩展到非锚点或整棵树。

锚点依赖包含：六个一级分支骨架、四条重放场景的目标或竞争节点、其祖先，以及
解释目标所需的有限同级上下文。生成器必须以显式 allowlist 固定这 24 个节点。

## 构建政策

```yaml
global_cartesian_product: false
numbered_sibling_names: false
template_word_substitution: false
undeclared_medium_tree_copy: false
stress_filler_targetable: false
scalar_field_requires_declared_owner: true
record_requires_declared_referent: true
parent_relation_required: true
scope_inherits_repeated_ancestor: true
allowlist_derived_from_output: false
exact_replay_anchor_allowlist_required: true
```

## run-003 冻结顺序

```text
record blueprints + allowed_facets_by_subject
→ 分别计算 canonical digest
→ 生成 2,001 节点候选
→ L1 从候选独立复算父链、作用域和允许组合
→ Codex 逐 record-referent cluster 预审
→ 单人人工审核
```

审核页面必须直接展示：

- “每一条该记录描述：___”
- “与父记录的关系：___”
- “从祖先链继承的作用域：___”

`run-002` 因缺少上述合同而停线；其节点、报告和界面不得作为 `run-003` 的通过
证据。
