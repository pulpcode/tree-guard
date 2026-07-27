# 实际信息树源格式分析

- 状态：已通过两份本地树样本和一份接口说明材料验证
- 安全：本文只记录结构规律，不记录真实名称、ID、地址、路径或实例值

## 1. 输入材料关系

本地材料包含：

- 同一业务版本的两个保存修订，其中一份不带 VALUE，另一份带部分 VALUE；
- 一份“curl 请求行 + JSON 响应”的接口说明材料。

两个修订的 `map_id/version/id` 相同，`concurrent_version` 不同，且均为 `resource`。接口响应的 `data` 与带值修订内容一致。接口说明材料不是严格 JSON，且请求行包含内网连接信息，因此整个 `tree-schema/` 目录保持本地忽略状态，不进入 Git。

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
- `class` 可以递归包含 `class`；
- 复合属性的直接子节点只能是 PROPERTY；
- 没有已知的业务最大深度，实际经验通常少于 10 层；解析器不能写死业务层数，当前 128 层只是防御性技术上限。

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
- 只记录 `has_value_envelope`；
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

`metadata.id` 与 `map_id` 不同。已经确认的 CanonicalTree 映射是：

```text
tree_id             <- map_id
version_record_id   <- id
tree_version        <- version
source_revision     <- concurrent_version
source_map_type     <- map_type
```

身份和修订语义：

- `map_id` 是跨业务版本稳定的树身份；
- `version` 是业务版本；
- `id` 对应 `map_id + version` 的版本记录，同一 `map_id` 的不同业务版本使用不同 `id`；
- `concurrent_version` 是业务版本内的保存修订号，修改保存后递增；拿到的两个样本不保证是连续保存；
- `map_type=resource` 表示信息树 Schema，`map_type=instance` 表示实例化后的信息树数据；二者拓扑结构相同，不能依据 VALUE 是否存在推断 `map_type`。

历史快照的稳定引用使用 `tree_id + tree_version + source_revision`，并携带 `version_record_id` 做一致性校验。

## 5. CanonicalTree v1

源树在导入后扁平化：

- `node_id` 作为节点主键；
- `parent_node_id` 和 `child_node_ids` 保留拓扑；
- `label`、`name`、计算路径和源 route 分别保存；
- `is_list` 转换为 `SINGLE/MULTIPLE`；
- 显式保留 `source_map_type`，`is_resource_map` 只是由它计算出的事实，不代表已经通过全部 Patch 门禁；
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

Patch 前置条件至少携带 `source_map_type + tree_id + tree_version + version_record_id + source_revision + snapshot_hash`。即使两次保存的 Schema 哈希相同，revision 变化也必须由 Patch 编译器重新检查，不能只信任序列化的 `is_resource_map`。

## 7. 本地 Conformance 结果

聚合验证结果：

| 材料 | 节点数 | VALUE 外层数 | ERROR | WARNING |
|---|---:|---:|---:|---:|
| 无值树 | 20 | 0 | 0 | 1 |
| 带值树 | 20 | 10 | 0 | 0 |
| 接口响应 | 20 | 10 | 0 | 0 |

唯一警告是无值修订中一个节点缺少有效 `node_order`。两份树的节点 ID 集合、`map_id/version/id` 均一致，`source_revision` 相差 4，不能据此假设中间没有其他保存。

确定性 Snapshot Diff 的聚合结果是：

- 新增 0、删除 0、修改 2；
- 两个修改都只有 `ORDER_OBSERVED_CHANGED`；
- 没有名称、label、类型、基数、约束或父子关系变化。

因此这两个样本能验证“保存修订 Diff”和 VALUE 排除边界，但在 `node_order` 规则确认前，不能把这两条顺序变化当作语义 Gold。

## 8. 仍需确认

1. `is_list` 在 `false/true` 间切换后，`node_id` 是否保持不变，以及已有 VALUE 如何迁移；
2. `class + is_list=true` 是否可以在另一个 class/class-list 内继续嵌套；
3. “改类型后 node_id 不变”是否同时覆盖 `node_type` 与 `value_type`；
4. `node_order` 是否必填、同级唯一、连续，以及插入节点时是否重排兄弟节点；
5. 修改 `node_label` 时，系统是否同步修改动态容器键、当前 route 和所有后代 route；
6. `concurrent_version` 是否对只改 VALUE、备注或审计字段的保存也递增；
7. 是否有 Schema-only 接口或 `exclude_values` 参数；
8. 读取复合 VALUE 时，是否以内层 `node_id` 作为最终绑定依据。

进入历史 Diff 前还需要：

- 版本列表或版本元数据接口；
- 按 `map_id + version` 获取 Schema-only 全树的接口或参数；
- 新增或修改节点的校验 DTO；
- 完整 `node_type/value_type/approve_status` 枚举；
- 使用完全虚构内容的错误响应样例。
