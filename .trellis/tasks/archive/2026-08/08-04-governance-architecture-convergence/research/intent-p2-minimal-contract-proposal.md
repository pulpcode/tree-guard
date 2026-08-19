# Intent P2：最小合同候选

## 结论候选

下一版本不应继续把12个语义字段都称为“Intent”。建议把自然语言理解结果拆成两个可
独立验证的产品：

1. `RetrievalRoleEvidence`：绑定原始需求字节的 `TARGET / SCOPE / EXCLUSION` spans，
   为召回提供可回放的角色提议；source binding 不证明角色语义正确；
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

同时，D1 已冻结原始需求为主查询，D2 候选让 source-bound 角色提议补充原始需求，并
禁止把另一份自由文本摘要当作主查询真值；P1 又表明动作应交给本地 Policy。因此继续
要求模型稳定生成上述8个未验收字段，只会
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

实现可以选择在一次调用中同时给出结构解释与角色 spans，但本地必须分别构造和验证
`StructuralIntent` 与 `RetrievalRoleEvidence`；任一部分非法时不得把另一部分悄悄补成
合法合同。模型不计算字符位置，本地复用现有 role evidence 校验，根据原文唯一匹配
生成 `start/end`。`clarification_question != null` 时本地派生
`NEEDS_CLARIFICATION`，否则派生 `READY_FOR_HUMAN_REVIEW`，不再让模型重复输出状态字段。

## 明确移出的字段

- `subject`：原始需求继续承担权威检索输入；可选 `TARGET` 提议只作有界软信号；
- `role`、`scenario`、`lifecycle`、`ownership`：当前无 Oracle、无确定性消费者；未来若
  有独立业务动作需要，应以新的有证据字段加入，而不是恢复一组自由摘要；
- `confirmed_facts`：不再作为权威摘要；source-bound 角色提议只作独立、未验证的补充；
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

## 2026-08-05 复核收紧

上述30个 Silver Oracle 的字段消费矩阵支持的是“固定四键构成当前最大机器语义面”，
不支持“四个字段每次都必须由模型一次性生成确定值”。其中 `node_kind` 与 `cardinality` 为30/30
实质比较，`value_type` 只有19条比较，`clarification_question` 为22条空值和8条非空；
其余8个自由文本字段才是30/30全部 `NOT_COMPARED`。四键仍按 Schema 始终序列化，
缺失语义使用 `UNKNOWN` 或 `null`，不强制模型猜出确定值。

下一版本应按字段采用以下来源优先级：

1. 用户在请求中明确提供并经本地合同校验的结构提示；界面随手选中的节点不属于权威
   提示，只可作为低信任软上下文；
2. 能从可信输入由确定性规则直接得到的字段；
3. 下游确实需要且仍缺失时，模型提出的候选值；
4. 证据不足时保留 `UNKNOWN` 或 `null`，不得为了形成完整表面输出而猜测。

`RetrievalRoleEvidence` 的 source binding 只证明指定 `start/end` 切片与原始请求一致
且可回放，不重新证明文本在全文唯一，也不证明 `TARGET / SCOPE / EXCLUSION` 分类在
业务语义上正确。当前构造器另外拒绝不能唯一定位的提议文本。模型输出应保持
`UNVERIFIED_MODEL_CALIBRATION`；Codex/Silver 标注也仍是非 Gold 校准。角色提议不得
单独硬裁剪从原始需求得到的宽候选，不得转化为动作许可。

初次理解阶段的 `clarification_question` 只处理请求文本自身存在、且会改变结构意图的
歧义。只有看到真实候选后才出现的同名、近义或结构冲突，应在候选比较阶段提出澄清。
将四字段和角色 spans 合并在一次调用中只是可选的时延/成本方案；当前隔离 v2 和单元
测试只验证合同、来源与篡改门禁，没有 live v2 A/B、未见数据或生产效果证据。
