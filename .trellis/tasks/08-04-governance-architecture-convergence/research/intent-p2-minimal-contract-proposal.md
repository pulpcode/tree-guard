# Intent P2：最小合同候选

## 结论候选

下一版本不应继续把12个语义字段都称为“Intent”。建议把自然语言理解结果拆成两个可
独立验证的产品：

1. `RetrievalRoleEvidence`：绑定原始需求字节的 `TARGET / SCOPE / EXCLUSION` spans，
   为召回提供可回放语义证据；
2. `StructuralIntent`：只保留 `node_kind`、`value_type`、`cardinality` 和一个可空的
   `clarification_question`，为结构过滤与是否短路提供最小机器合同。

原始 `requirement_text` 继续是权威来源；`proposed_parent_node_id` 和显式 hints 仍属于
请求上下文，不进入模型自由文本 Intent。

## 仓库证据

当前 `IntentContent` 有12个字段。M4.9 的30个 Silver Oracle 对字段的实际政策为：

- `node_kind`：30/30 `EXACT_ONE_OF`；
- `cardinality`：30/30 `EXACT_ONE_OF`；
- `value_type`：19个 `EXACT_ONE_OF`、11个无显式值时 `NOT_COMPARED`；
- `clarification_question`：22个明确为空、8个要求非空；
- `subject`、`role`、`scenario`、`lifecycle`、`ownership`、`confirmed_facts`、
  `assumptions`、`evidence_gaps`：30/30 全部 `NOT_COMPARED`。

同时，D1 已冻结原始需求为主查询，D2 已用 source-bound 角色证据替代自由文本摘要，
P1 又表明动作应交给本地 Policy。因此继续要求模型稳定生成上述8个未验收字段，只会
增加合同负担和错误面，且没有当前可证明的下游职责。

## 候选 v2 模型输出

```json
{
  "schema_version": "change-understanding-model-output.v2",
  "node_kind": "PROPERTY",
  "value_type": null,
  "cardinality": "SINGLE",
  "clarification_question": null,
  "spans": [
    {"role": "TARGET", "text": "虚构字段"}
  ]
}
```

模型可以在一次调用中同时给出结构解释与角色 spans，但本地必须分别构造和验证
`StructuralIntent` 与 `RetrievalRoleEvidence`；任一部分非法时不得把另一部分悄悄补成
合法合同。模型不计算字符位置，本地复用现有 role evidence 校验，根据原文唯一匹配
生成 `start/end`。`clarification_question != null` 时本地派生
`NEEDS_CLARIFICATION`，否则派生 `READY_FOR_HUMAN_REVIEW`，不再让模型重复输出状态字段。

## 明确移出的字段

- `subject`：由 `TARGET` source span 承担检索证据；
- `role`、`scenario`、`lifecycle`、`ownership`：当前无 Oracle、无确定性消费者；未来若
  有独立业务动作需要，应以新的有证据字段加入，而不是恢复一组自由摘要；
- `confirmed_facts`：由 source-bound role evidence 替代；
- `assumptions`：不得进入主召回，可作为非持久化解释文本；
- `evidence_gaps`：由 Semantic 候选证据充分性和本地 Policy 状态承担；
- 动作与 selected candidate：按 P1/D3 交给本地 Policy。

解释文本若产品需要，可由 UI 或独立的非权威说明投影生成，但不进入结构合同、召回、
哈希决策域或动作授权。

## 兼容与实施边界

- 现有 v1 工件、Schema、回放与 CLI 保持可读，不原地改变 v1 语义；
- 新增 v2 合同、类型和 Provider 路径，先做离线迁移测试，不切换默认入口；
- v1→v2 兼容桥只投影上述4个字段，并从原始请求重新验证 role evidence，不能信任 v1
  `subject/confirmed_facts` 合成 spans；
- 人工确认仍只授权 Retrieval，不构成语义批准、Gold 或 Patch 资格；
- 在未见数据上至少验证结构字段、澄清路由、角色抽取和合同首轮通过率后，才考虑替换
  v1 产品入口。

## 建议下一实现切片

若接受本候选与 D3，先做一个不接生产入口的 v2 纵切：

1. 新增 `StructuralIntent v2` 与组合模型输出 Schema；
2. 复用现有 `RetrievalRoleEvidence` 的 source-bound 校验，不复制 span 逻辑；
3. 新增 relation-only Semantic 输出与 `DeterministicRecommendationPolicy v2`；
4. 建立 v1/v2 离线迁移和篡改测试；
5. 默认治理 CLI 仍走 v1，待独立确认后再切换。
