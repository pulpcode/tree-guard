# TreeGuard 决策记录

日期：2026-07-27
用途：记录已经接受的关键决策、明确不做的事项和仍需通过内网事实核实的问题。

## 1. 已接受的产品决策

### D-001：主方向选择信息树语义治理

选择“AI 辅助信息树增量建模和变更治理”，不把通用自然文本抽取作为首个亮点项目。

原因：

- 直接命中 2,000+ 节点信息树的真实建设成本；
- 可以利用当前信息树仓库、版本和邮件引用资产；
- 业务结果可由专家裁决，评测边界更清晰；
- 能展示检索、Schema 编译、工作流、回放、安全和人机协作等工程能力；
- 自然文本抽取仍受候选覆盖和路径导航限制，更适合作为后续方向。

### D-002：从一个子树开始治理

- 读取和检索范围：完整信息树；
- Overlay 审批和 Patch 建议范围：试点子树。

### D-003：系统入口是“AI 建模建议 / 新增审查”

MVP 不宣称可以安全修改已有节点。“修改”只允许发生在意图卡、Overlay 草稿和未发布 Patch。

### D-004：专家可以提交思考，而不是强制 N 分类

系统保留专家原文，并整理为事实、假设、分歧、风险和待取证项。只有 `APPROVED` 结论才能进入 Patch。

### D-005：领域专家与信息树建设人员协作审批

- 领域专家负责业务语义；
- 信息树建设人员负责物理结构、类型、基数和 Patch；
- MVP 可以由同一账号操作，但 Trace 分别记录角色。

### D-006：采用选择性自动化

AI 可以追问、要求证据或拒答，不要求覆盖全部案例。优先保证明确建议的准确率。

## 2. 已接受的语义建模决策

### D-007：严格区分物理节点和语义合同

不再使用模糊的 `REUSE`，拆分为：

- `USE_EXISTING_NODE`；
- `ADD_NODE_FROM_CONTRACT`；
- `ADD_CONTEXT_FIELD`；
- `ADD_ALIAS_OVERLAY`。

### D-008：基础树保持单父结构

MVP 不为现有运行时增加继承或多父节点。`SPECIALIZES`、`REUSES_CONTRACT` 等只保存在 Overlay，Patch 必须展开为普通 `CONCEPT/PROPERTY` 节点。

### D-009：人员信息采用核心、参与关系和场景扩展分层

- `PersonCore`；
- `TaskParticipantBase`；
- `<TaskType>ParticipantExtension`。

特殊任务具有相对稳定语义，但可能增加特殊字段，因此优先采用上下文扩展，而不是复制完整人员子树或污染全局人员节点。

### D-010：Semantic Overlay 独立版本化

Overlay 以 `node_id + base_tree_version + base_node_hash` 锚定，状态包括：

- `AI_DRAFT`；
- `EXPERT_APPROVED`；
- `REJECTED`；
- `STALE`。

只有审批后的补充语义可用于正式建议。

## 3. 已接受的技术决策

### D-011：采用可回放的受约束工作流

- 固定步骤；
- 白名单工具；
- 类型化输入输出；
- 最大调用次数和超时；
- 人工门禁；
- append-only Trace；
- 不使用自由行动的通用 Agent。

### D-012：在线最多两次顺序 LLM 调用

1. 自然语言到意图卡；
2. 小候选集合到语义建议。

Patch、Diff、校验和影响分析使用确定性代码。

### D-013：Python AI 治理服务与 Spring Boot 解耦

- Spring Boot 继续作为基础树的事实来源、权限边界和未来发布方；
- Python 负责工作流、检索、Overlay、Trace、评测和模型编排；
- AI 不直接写 MongoDB。

### D-014：先做文件型 Shadow MVP

- 树和历史版本通过文件导入；
- 邮件依赖通过 Usage Manifest 导入；
- TreeGuard 生成 Patch 文件；
- 不实现正式写 API。

### D-015：邮件系统仍是节点使用关系的事实来源

TreeGuard 导入周期性 Usage Manifest，建立只读反向索引。索引过期或覆盖不全时只能声明已知影响，不能宣称“无影响”。

### D-016：2,000 节点规模不引入重型基础设施

MVP 使用轻量 BM25、向量索引和结构特征，不引入 Elasticsearch、图数据库、Kafka 或微服务群。

## 4. 已接受的数据与评测决策

### D-017：历史版本不是 Gold

版本只是修改容器。先拆分不同子树的原子变更簇，再由专家基于变更前快照重新裁决。

### D-018：建立至少 30 条真实冻结案例

AI 建议先生成并隐藏，人工独立决定后再揭示。冻结集不得继续用于调 Prompt、阈值或检索。

### D-019：允许 AI 合成数据，但严格限制用途

合成数据用于契约、边界、压力、开发和 few-shot，不替代真实 Gold，不证明消防业务准确率。

来源标签：

- `REAL_HUMAN_GOLD`；
- `EXPERT_APPROVED_SYNTHETIC`；
- `AI_SYNTHETIC`；
- `DETERMINISTIC_STRESS`。

### D-020：MVP 不微调模型

先积累至少 300 条专家批准案例和稳定错误模式，再判断是否微调 embedding、reranker 或动作分类器。

## 5. 已接受的安全决策

### D-021：外网洁净 Core + 内网薄 Adapter

外网不能获得真实数据和内部代码。通用源码经安全审查单向导入内网，真实运行和验证留在内网。

### D-022：少量外传材料必须分级脱敏

- L0：抽象合同和错误码；
- L1：经审批的随机化结构样例；
- L2：人工改写到无关虚构领域的最小语义复现；
- 不允许传出完整数据、源码、Prompt、Trace 或日志。

### D-023：模型默认不访问原始 VALUE

默认使用 `SCHEMA_ONLY`。更高证据等级需要单独授权，MVP 不开放 `RAW_VALUE`。

### D-024：正式写路径物理缺失

六周 MVP 中不只是“配置上关闭写入”，而是不提供 Spring Boot/MongoDB 正式写连接器。

### D-025：Canonical Tree 默认采用 `SCHEMA_ONLY`

实际导出格式中的 VALUE 是属性节点旁边的实例对象，不是独立拓扑节点。File Adapter 只记录属性是否携带实例值，不保存、不输出、不哈希实例载荷。

### D-026：真实源文件不得进入通用 Git 仓库

本地 `tree-schema/` 仅用于只读格式验证，已整体加入 `.gitignore`。仓库测试只能使用完全虚构的 fixtures。

### D-027：版本身份分为业务版本和保存修订

- `tree_id <- map_id`，跨业务版本稳定；
- `tree_version <- version`，表示业务版本；
- `version_record_id <- id`，对应 `map_id + version` 的版本记录；
- `source_revision <- concurrent_version`，表示业务版本内递增的保存修订。

历史快照使用 `tree_id + tree_version + source_revision` 定位。Patch 前置条件还必须携带 `version_record_id + snapshot_hash`，不能解析业务版本字符串猜测先后。

### D-028：resource/instance 与 VALUE 存在性解耦

`map_type=resource` 和 `map_type=instance` 使用相同的树结构，resource 也可能携带 VALUE。CanonicalTree 显式保留 `source_map_type`，只记录 `has_value_envelope`，不能通过 VALUE 是否存在推断树类型。instance 可以做只读 Schema 投影，但不得进入治理 Patch。

### D-029：跨修订节点匹配只使用 node_id

已确认改名和更换父节点不会改变 `node_id`；用户所称的“改类型”也保持 node_id，但它是否同时覆盖 `node_type` 与 `value_type` 仍待核实。`node_label` 同级唯一但可修改，`node_label_route` 完全派生。因此 Diff 只能使用 `node_id` 匹配；label、route 和计算路径不得作为身份。

### D-030：复合属性允许递归，但子节点类型受限

`value_type=class` 可以递归包含 class，没有已知业务最大深度，实际通常少于 10 层。复合属性的直接子节点只能是 PROPERTY。实现中的 128 层限制是技术安全上限，不是业务规则。

### D-031：历史 Diff 使用确定性字段比较

历史 Diff 不交给 LLM。它按稳定 `node_id` 识别新增、删除、移动、改名、类型、基数和其他字段变化，并排除 VALUE、审计字段及派生 route/path/child 列表，避免祖先移动或改名造成整棵后代误报。

通用查看允许反向比较并给出 `SOURCE_REVISION_DECREASED` 警告；历史分簇、样本构建和 Gold 流水线必须把该警告作为硬门，不能把逆向 Diff 学成真实演进操作。完整 TreeDiff 含字段前后值，只能留在内网，跨网只允许聚合码和计数。

## 6. 仍需内网核实的事实

以下问题不能由外网假设替代：

1. 历史版本能否稳定导出完整快照，而不是只导出当前树；
2. 节点新增或修改校验 DTO，以及完整节点类型、值类型、基数和顺序规则；
3. `is_list` 切换后 node_id 是否稳定，以及已有 VALUE 的迁移语义；
4. `class + is_list=true` 能否在另一复合属性中继续嵌套；
5. “改类型保持 node_id”是否同时覆盖 `node_type` 和 `value_type`；
6. 是否存在节点 ID 被重建或复制的历史情况；
7. 修改 label 时，动态键和全部派生 route 是否由系统同步更新；
8. `concurrent_version` 是否对只改 VALUE、备注或审计字段的保存也递增；
9. 是否存在 Schema-only 接口或排除 VALUE 的查询参数；
10. 邮件模板中的节点引用是否全部为稳定 `node_id`；
11. Usage Manifest 能否包含模板版本、状态和最后更新时间；
12. 当前 Qwen 的接口协议、最大上下文、并发、超时和结构化输出能力；
13. 首个试点消防子树的具体范围；
14. 30 条冻结案例需要多少专家工时；
15. 内网允许使用的 Python、向量库、MongoDB 和前端依赖版本；
16. 内网离线依赖扫描和许可证审批流程；
17. Trace 的权限、加密和保留期限。


## 7. 暂缓事项

- 生产编辑器内嵌；
- Spring Boot 写接口；
- 删除、移动、合并和迁移自动化；
- 全量 2,000+ 节点治理；
- 实时邮件事件；
- 多消费者依赖图；
- 通用自然文本抽取；
- 模型微调；
- 在线多 Agent 辩论；
- 运行时继承、多父节点和图数据库。

## 8. 决策变更规则

修改以上基线时，应记录：

- 被修改的决策编号；
- 新事实或评测证据；
- 对合同、数据、评测和安全边界的影响；
- 是否需要重新冻结 Gold 或重做 Shadow；
- 审批人和生效版本。

这样可以避免后续实现仅凭口头讨论偏离最初目标。
