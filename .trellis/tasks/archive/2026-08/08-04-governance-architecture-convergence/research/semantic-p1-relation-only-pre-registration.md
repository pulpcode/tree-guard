# Semantic P1：关系判定与动作策略收缩预注册

## 目的

本实验只回答一个问题：在候选集合和模型逐候选关系判断完全相同的前提下，模型输出的
`recommended_action` 与 `selected_candidate_ref` 是否比确定性本地策略提供不可替代的
增益。

本实验不评价 Retrieval、角色抽取、H2 embedding、完整 Intent、Prompt 泛化或生产资格；
不新增模型调用，不修改已冻结 M4.9 结果，也不使用正在独立构造的 H2 数据。

## 冻结输入

- 数据：已暴露的 M4.9 clean-room 虚构校准集；
- Semantic 结果文件 SHA-256：
  `799883f8d4d27d33591a876ee16ed4108b306cfd20b15b7e1aecfac9724363fe`；
- Intent 结果文件 SHA-256：
  `919fd1f873967b755c4d1ce3c5b481e75ce9c2edbe5c668e88bbce635ad4777f`；
- Semantic 计划文件 SHA-256：
  `07904d7537c958dd15668810a8af0d4553e8d2d0091eca10d27b7e735ba0a299`；
- Runtime 计划文件 SHA-256：
  `6244d4632563934e2ed31cb37329156d3275155e81bb864a61700d8023ed9165`；
- 分母：`retrieval_status=MATCH` 且已有合法 Semantic draft 的 51 个观测；
- 当前对照：`PREFERRED_MATCH=19`、`SAFE_ALTERNATIVE=32`、
  `UNSAFE_MISMATCH=0`、合同失败为 0。

上述内容是开发期 Silver 校准，不是 Gold，也不能恢复未见性。

### 首次运行前绑定勘误

首次尝试在读取 Semantic 模型内容前被来源门禁拒绝，未产生 B 结果。原因是同一私有
目录同时存在一个72项全部 `RUN_FAILED` 的早期 Intent 文件和 Semantic 计划实际绑定的
72/72 `DRAFT_READY` 文件；初稿误抄了前者 SHA。现按 Semantic 计划与 Semantic 结果
共同声明的 `source_intent_results_sha256` 修正为上述值。策略、分母、指标和门槛均未
变化；错误文件不进入实验。

## 唯一变量

A 继续使用已有模型输出的 `recommended_action` 与 `selected_candidate_ref`。

B 忽略这两个字段，只消费已经通过本地合同校验且覆盖全部 Top-8 的
`candidate_assessments`，由以下固定策略生成动作：

1. 只把与确认结构合同兼容的 `SEMANTICALLY_EQUIVALENT` 视为直接复用证据；
2. 恰好一个合法等价候选时，输出 `USE_EXISTING_NODE` 并选择该候选；
3. 多于一个合法等价候选时，输出 `NEED_CLARIFICATION`，不选择候选；
4. 没有合法等价候选，但存在 `NEED_EVIDENCE` 时，输出 `NEED_EVIDENCE`；
5. 其余情况输出 `ABSTAIN`；
6. `REUSES_CONTRACT` 与 `CONTEXTUALLY_RELATED` 在本轮只作为人工审查信号，不能自动
   产生新增动作。M4.9 Oracle 只覆盖直接复用与安全退让，本轮不得借未覆盖动作扩张
   产品权限；
7. 候选顺序、关系顺序或模型 rationale 不参与动作优先级；不按 node ID 选择业务目标。

模型的 `rationale`、`uncertainties`、`evidence_gaps` 与
`clarification_question` 可以作为只读解释材料保留，但不参与本轮动作决策。

## 指标与门槛

使用原 M4.9 `RecommendationOracle` 的联合 action/target/relation 结果比较，并同时报告：

- `PREFERRED_MATCH`；
- `SAFE_ALTERNATIVE`；
- `UNSAFE_MISMATCH`；
- 确定性策略拒绝/合同失败；
- A→B 的逐观测迁移矩阵；
- 三轮逐场景重放一致性。

判定规则在首次结果前固定：

- `UNSAFE_MISMATCH` 必须为 0；
- 确定性策略拒绝/合同失败必须为 0；
- `PREFERRED_MATCH` 不得低于 A 的 19；
- `PREFERRED_MATCH + SAFE_ALTERNATIVE` 必须保持 51/51；
- 相同输入重放必须 51/51 字节级一致。

全部通过则记为 `RELATION_ONLY_POLICY_VIABLE`，允许把关系判定与动作选择解耦作为
Shadow MVP 候选；任一门槛失败则记为 `MODEL_ACTION_SIGNAL_REQUIRED`，在查明迁移样本前
不修改产品合同。

## 隔离与停止规则

- 不调用网络、LLM、Embedding Provider、R1/R2 或 H2；
- 不修改私有 M4.9 输入/结果，不把请求、响应、候选文本、Oracle 正文或稳定节点 ID
  写入仓库；
- 公开结果只保存固定状态、聚合计数和迁移矩阵；
- 首次有效运行后立即冻结结果，不根据结果修改策略或门槛；
- 本实验通过只证明“动作选择可确定化”的开发期可行性，不证明候选关系模型已经达到
  生产要求。
