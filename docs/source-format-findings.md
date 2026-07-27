# 实际信息树源格式分析

- 状态：已通过两份本地树样本和一份接口说明材料验证
- 安全：本文只记录结构规律，不记录真实名称、ID、地址、路径或实例值

## 1. 输入材料关系

本地材料包含：

- 一份不带实例值的树；
- 一份带部分实例值的树；
- 一份“curl 请求行 + JSON 响应”的接口说明材料。

接口响应的 `data` 与带值树内容一致。接口说明材料不是严格 JSON，且请求行包含内网连接信息，因此整个 `tree-schema/` 目录保持本地忽略状态，不进入 Git。

## 2. 实际递归语法

```text
Document
├── metadata
└── map_topology
    └── <root-node-label>: NodeEnvelope

NodeEnvelope
├── metadata: NodeMetadata
├── subnodes?: {
│     <child-node-label>: NodeEnvelope
│   }
└── value?: ValueEnvelope
```

已验证：

- `map_topology` 和 `subnodes` 是动态键对象，不是数组；
- 动态键与节点 `node_label` 一致；
- 非根节点的 `parent_node_id` 与实际容器父节点一致；
- 路径使用 `父路径 + "/-/" + node_label`；
- `node_label` 与 `node_name` 是两个不同字段，必须分别保留；
- 拓扑节点类型观察到 `concept` 和 `property`；
- `property` 使用 `is_list` 表达单值或列表；
- `value_type=class` 的属性使用同一个 `subnodes` 结构包含子属性；
- 解析器不能写死复合属性层数。

当前观察到的 `value_type`：

```text
string
integer
float
boolean
class
space_code
time_code
entity_code
```

这只是观察集合，不是完整枚举。未知值类型被保留并产生警告，不会静默改写。

## 3. VALUE 的实际表示

VALUE 不是 `node_type=value` 的拓扑节点，而是 PROPERTY 旁边的可选 `value` 对象。

观察到：

- 基础单值：`simple_value`；
- 基础列表：`simple_values`；
- 时间单值：`date_time_value`；
- 复合单值：`complex_value`；
- 复合列表：`complex_values`；
- 列表使用动态索引键对象，而不是 JSON 数组；
- 复合值内部的动态键对应子属性 `node_name`；
- 内部 `value.metadata.node_id` 可绑定回 Schema 属性。

第一阶段策略：

- 只校验 VALUE 外层绑定元数据；
- 只记录 `has_instance_value`；
- 不把实例载荷保存进 CanonicalTree；
- 不把 VALUE 放进 Schema 哈希、检索、Prompt 或 Trace；
- VALUE 缺失不影响 Schema 导入。

## 4. API 映射

观察到的常用接口是无请求体的 GET，按资源标识和版本读取完整嵌套树，没有分页字段。

安全抽象后的映射：

```text
query.resource_id  → response.data.metadata.map_id
query.version      → response.data.metadata.version
response.data      → Direct Tree Export
```

响应信封：

```text
status: integer
message: string
data:
  metadata
  map_topology
```

`metadata.id` 与 `map_id` 不同。当前 CanonicalTree 暂按以下方式映射：

```text
tree_id             <- map_id
version_record_id   <- id
tree_version        <- version
source_revision     <- concurrent_version
```

这些字段的业务定义仍需内网正式确认。

## 5. CanonicalTree v1

源树在导入后扁平化：

- `node_id` 作为节点主键；
- `parent_node_id` 和 `child_node_ids` 保留拓扑；
- `label`、`name`、计算路径和源 route 分别保存；
- `is_list` 转换为 `SINGLE/MULTIPLE`；
- 约束、placeholder、extension 和未知节点元数据字段显式保留；
- 未分类的 NodeEnvelope 外层字段拒绝导入，防止未来 VALUE 形态误入治理快照；
- 未知源节点类型映射为 `UNSUPPORTED` 并产生警告；
- `UNSUPPORTED` 节点未来不得进入 Patch 生成。

完整合同见 `contracts/tree-snapshot.v1.schema.json`。

## 6. 哈希边界

`node_hash/snapshot_hash` 包含：

- 节点身份；
- 父子关系；
- label、name 和计算路径；
- 顺序；
- 节点类型、数据类型和基数；
- 约束、placeholder、remark 和 extension；
- 未知的非审计、非 VALUE 字段。

明确排除：

- 实例 VALUE；
- 创建人、创建时间、修改人和修改时间；
- API `status/message`；
- `concurrent_version`。

Patch 前置条件应分别携带 `tree_version + source_revision + snapshot_hash`。是否允许实例值写入导致的 revision 变化使 Patch 过期，需要根据 `concurrent_version` 的正式语义再决定。

## 7. 本地 Conformance 结果

聚合验证结果：

| 材料 | 节点数 | VALUE 外层数 | ERROR | WARNING |
|---|---:|---:|---:|---:|
| 无值树 | 20 | 0 | 0 | 1 |
| 带值树 | 20 | 10 | 0 | 0 |
| 接口响应 | 20 | 10 | 0 | 0 |

唯一警告是无值树中一个节点缺少有效 `node_order`。两份树的节点 ID 集合一致、业务 `version` 一致，但 `source_revision` 和规范化 Schema 哈希不同；哈希差异来自 Schema 顺序字段，而不是 VALUE 或审计时间。

## 8. 需要用户确认

P0：

1. 两份树是同一草稿填写实例值前后的快照，还是两个历史版本；
2. `map_id/id/version/concurrent_version` 的正式定义；
3. `concurrent_version` 是否用于乐观锁，哪些操作会使它增加；
4. 是否有 Schema-only 接口或 `exclude_values` 参数；
5. 改名、改类型、改基数、换父节点后 `node_id` 是否稳定；
6. `class` 是否允许递归包含 `class`，是否有最大深度，复合属性下是否只允许属性；
7. `node_label` 的唯一范围、可修改性，以及 route 是否完全派生；
8. 读取复合 VALUE 时，是否以内层 `node_id` 作为最终绑定依据。

进入历史 Diff 前还需要：

- 版本列表或版本元数据接口；
- 按 `map_id + version` 获取 Schema-only 全树的接口或参数；
- 完整 `node_type/value_type/approve_status` 枚举；
- 使用完全虚构内容的错误响应样例。
