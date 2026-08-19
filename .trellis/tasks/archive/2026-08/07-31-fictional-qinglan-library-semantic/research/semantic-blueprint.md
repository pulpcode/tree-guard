# Semantic Blueprint：青岚中型语义挑战集

## 设计原则

- 从本任务独立 Blueprint 生成，不读取旧消防语义内容。
- 24 个小型青岚节点只作为 lineage references 披露，不承担精确 replay。
- 所有背景 property placement 必须逐 subject 出现在
  `allowed_facets_by_subject`；禁止全局 `product()`。
- 节点名称自然可读，不使用编号兄弟、稳定化名或模板占位符。
- 每个 curated cluster 必须对应至少一个 coverage cell。

## 精确规模分解

| 家族 | 数量 | 用途 |
|---|---:|---|
| `curated_core` | 72 | challenge anchors、lineage references、人工重点审核 |
| `blueprint_background` | 180 | 提供自然上下文和 hard-negative 密度，不承担 Gold |
| `stress_only_filler` | 60 | 排序、遍历和规模压力，不可作为语义目标 |
| 合计 | 312 | 中型语义挑战树 |

结构计数计划：

```text
1 root
+ 5 first-level domain branches
+ 1 resource-singleton basic-information section
+ 13 organizational CONCEPT containers
+ 52 class PROPERTY subjects
+ 240 scalar properties
= 312 nodes
```

节点族计数与结构计数是两个正交视图；生成器必须同时精确满足。

## 一级分支

推荐使用五个自然领域分支，并在根节点下并列一个资源单例章节：

1. 馆藏资源（lineage reference）
2. 服务空间（lineage reference）
3. 读者服务（lineage reference）
4. 公共活动（lineage reference）
5. 运营与可达保障
6. 本馆基本信息（`SINGLETON_SECTION`，不属于领域分类）

第五个领域分支用于增加与小型树不同的结构风格。“本馆基本信息”只表示当前
这一个虚构馆舍的唯一元数据章节，可直接承载“馆舍名称”等资源级字段；它不表示
一类可重复业务对象。本批不声明跨规模 replay。

## Structural Groups

13 个组织结构容器按领域分支分配，每组包含 2–4 个记录/政策对象。另有 1 个
根级 `SINGLETON_SECTION`。CONCEPT 必须进一步声明为
`ORGANIZATIONAL_CONCEPT` 或 `SINGLETON_SECTION`；后者表示当前整棵资源内
唯一的章节，可以拥有资源级标量字段。组名和对象名在生成前以显式表冻结，不从
真实资料或文章 harvest。

- 馆藏资源：4 组
- 服务空间：0 个单例空间组；静音阅览区、小组研讨室和多用途活动厅均为可重复
  class 记录
- 读者服务：3 组
- 公共活动：3 组
- 运营与可达保障：3 组

## Value Owner / Instance Boundary

- `CONCEPT/ORGANIZATIONAL_CONCEPT` 只表达组织分类，不直接拥有标量
  PROPERTY。
- `CONCEPT/SINGLETON_SECTION` 表示当前资源中的唯一章节，可以直接拥有标量
  PROPERTY；这些字段的 owner scope 固定为 `PARENT_SINGLETON_SECTION`。
- 本批唯一的 `SINGLETON_SECTION` 是根级“本馆基本信息”；其“馆舍名称”描述
  当前这一个虚构馆舍，不描述馆舍集合。
- 可重复条目使用 `PROPERTY(value_type=class, is_list=true)`；例如“音频读物”
  表示音频读物记录集合，“音频时长”属于其中一条记录。
- 静音阅览区、小组研讨室和多用途活动厅同样是可重复 class 记录；其开放时间、
  容量和嵌套区域字段属于各自记录，不表示全部同类空间的汇总值。
- 单例政策或配置使用 `PROPERTY(value_type=class, is_list=false)`；例如
  “纸本文献流通政策”拥有类别级“默认外借许可”，不把该默认值误写为某一册
  文献的当前状态。
- 标量 PROPERTY 必须直接挂在 class PROPERTY 或已声明的 SINGLETON_SECTION
  下，并分别声明 `PARENT_CLASS_RECORD` 或 `PARENT_SINGLETON_SECTION`。
- class PROPERTY 必须声明 `value_owner_scope=REPEATED_RECORD` 或
  `SINGLETON_RECORD`，且与 is_list 一致。
- 集合汇总不是实例字段；没有独立汇总对象和证据时，场景必须追问或拒绝静默落树。

## Subject / Facet Compatibility

- 52 个 class PROPERTY subject；其中 50 个显式分配背景字段，另外 2 个空间记录
  只承载已冻结的 curated 字段和嵌套记录。
- property placement 总数精确为 240。
- 至少 70% 的 child name vector 唯一。
- 有意重复的 type/cardinality vector 仅限 3 个已声明 challenge cluster；
  每个 cluster 使用不同节点名并有单独场景说明。
- 同名 property 最多跨 3 个路径复用，用于 homonym/hard-negative；不得形成
  全局公共字段模板。
- 每个 subject 的允许表记录：
  `facet_ref + name + value_type + cardinality + purpose_cluster`。

## Depth Distribution

- 最小深度：0
- 常规最大深度：5
- 两条 curated unusual-depth 路径：深度 6 和 7
- stress-only filler 只分布在深度 3–5
- unusual-depth 节点必须有场景目的，不能由生成器偶然产生。

## Node Contract Plan

- organizational/singleton `CONCEPT`、class `PROPERTY` 与标量
  `PROPERTY` 均出现。
- class 使用 Adapter 已接受的 `value_type=class`；标量 value type 只使用
  Adapter 已接受的完全虚构合同类型。
- SINGLE/MULTIPLE 组合由 subject 允许表显式指定。
- 不包含 `VALUE`、真实示例值、constraints 业务文本或模型生成 oracle。

## Clean-room Lineage References

保留 24 个已声明 clean-room lineage reference ID 以披露来源关系，但允许根据
本 Blueprint 修改节点类型、名称、父子关系和基数。它们不再计为 exact replay
anchors，也不支持小/中树稳定性结论。

## Stress-only Filler

- 60 个 filler 从预先冻结的显式名称表构造。
- 不使用“字段 1/字段 2”、编号后缀或 subject/facet 笛卡尔积。
- 不进入 scenario target、oracle、语义准确率或人工逐项语义结论。
- L1 必须证明全部 filler 不可被场景引用。

## Determinism

- 固定 seed `20260731` 只用于受控抽样与顺序打散。
- 节点身份、父子关系和允许表来自冻结常量表。
- 输出按显式顺序构建，再以规范 JSON 序列化。
- 同一输入连续重建必须逐字节相同。
