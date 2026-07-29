# TreeGuard 六周实施路线

状态：建议执行计划
目标出口：内网文件型 Shadow MVP

## 1. 总体策略

- 外网完成通用 Core、合同、虚构 fixtures、测试和离线交付包；
- 外部源码经人工安全审查后单向导入内网；
- 内网人员实现薄 File Adapter 和 Qwen Provider 配置；
- 专家数据准备从第一周并行开始；
- 第六周只决定是否继续 Shadow 或进入待审批 Patch 试点，不接生产写接口。

## 2. 第 1 周：合同与离线基线

工作：

- 固化以下版本化 JSON Schema：
  - `TreeSnapshot`；
  - `ChangeIntent`；
  - `SemanticOverlay`；
  - `DeliberationRecord`；
  - `SchemaPatch`；
  - `WorkflowTrace`；
  - `UsageManifest`；
  - `ConformanceReport`。
- 建立完全虚构的领域 fixtures；
- 实现文件导入、基本结构校验和稳定哈希；
- 建立 Trace 事件模型；
- 完成威胁模型和跨网材料白名单；
- 盘点内网 Python、CUDA、Qwen API 和依赖安装条件；
- 启动真实试点子树和专家评测案例准备。

验收：

- 契约通过内网人工确认；
- 通用 Core 可在无网络环境启动；
- 虚构快照可以完成导入和结构校验；
- 运行时没有非授权外联；
- 明确内部 File Adapter 的责任边界。

## 3. 第 2 周：历史、血缘与检索基线

工作：

- 导入至少两个历史版本；
- 基于 `node_id` 重建新增、修改、删除和疑似移动；
- 形成确定性的结构候选簇和信息观察，并由专家合并或拆分；
- 实现名称、路径、结构和向量索引；
- 建立 BM25 + 向量 + 结构特征的混合召回；
- 实现 Overlay 基本状态机；
- 实现确定性 Trace 回放；
- 生成依赖锁、wheelhouse、SBOM 和 Transfer Manifest。

验收：

- 内网能够导入真实当前树和至少两个历史版本；
- 能输出结构化 Diff、结构候选簇、安全门状态和信息观察；
- 能在整棵树上返回 Top-20 候选；
- 核实“节点更换父节点后 `node_id` 是否稳定”；
- 所有跨网诊断只输出白名单格式。

## 4. 第 3 周：意图编译与选择性决策

工作：

- 实现 Qwen Provider；
- 实现自然语言到 `ChangeIntent`；
- 实现用户确认和修订；
- 实现局部精排；
- 实现候选语义比较；
- 支持：
  - `USE_EXISTING_NODE`；
  - `ADD_NODE_FROM_CONTRACT`；
  - `ADD_CONTEXT_FIELD`；
  - `NEED_CLARIFICATION`；
  - `NEED_EVIDENCE`；
  - `ABSTAIN`。
- 实现非法 JSON、未知节点、超时和版本漂移门禁。

当前已完成文件型纵切：`IntentRequest → ChangeIntentDraft →
IntentConfirmation → CandidateSet → SemanticRecommendationDraft →
RecommendationRecord`。它支持百炼或私有模型输出文件、显式人工确认、可信来源
回放、无 embedding 的全树词法/结构 Top-20 基线，以及固定 Top-8 候选的逐项语义
比较和单一选择性动作。本地政策约束动作与候选关系一致，零候选或证据不足不能产生
正向建议；专家可以确认、按相同政策修订或拒绝。

当前人工建议记录只作 `OPERATIONAL_FEEDBACK_ONLY`，不构成语义审批、Gold 或 Patch
资格。内网 Qwen HTTP 直连、embedding/混合召回、学习型 reranker、
`ADD_ALIAS_OVERLAY` 和正式效果评测仍待后续实现。

验收：

- 内网 Qwen 可以稳定调用；
- 在线最多两次顺序模型调用；
- 所有模型输出通过 JSON Schema；
- 模型编造 ID、越权动作或格式异常全部 fail-closed；
- 任何异常都不会产生正式写操作。

## 5. 第 4 周：Overlay、专家讨论与 Patch

工作：

- 选定一棵消防试点子树；
- AI 起草公共语义合同和成员差异；
- 专家分组审批 Overlay；
- 实现 `DeliberationRecord` 页面和版本历史；
- 实现声明式 Patch 编译；
- 实现结构校验、前置条件和 Dry Run；
- 完成开发集并独立裁决至少 30 条最终冻结案例。

当前已完成其中一个独立的 clean-room 纵切：`ExpertReviewSession v1` 支持专家自由
文本、一次受约束 AI 整理、专家暂定状态、最终裁决、来源绑定哈希链、单动作文件
追加、精确外发请求审批清单和离线回放。它尚不包含认证身份、权威 HEAD、Overlay
页面、结构审批或 Patch，因此即使专家语义状态为 `APPROVED`，仍保持
`patch_eligible=false`、`gold_eligible=false`。文件分支在接入受控仓库前只能视为
可回放制品，不能视为权威记录。

验收：

- 只有 `EXPERT_APPROVED` Overlay 可用于正式建议；
- 不确定案例可以停留在 `NEED_EVIDENCE`；
- Patch 展开为当前树能够表达的普通节点；
- 删除、移动、合并、改类型和改基数无法进入执行动作；
- 冻结案例不受 AI 建议锚定。

## 6. 第 5 周：影响分析与真实 Shadow

工作：

- 实现文件型邮件 Usage Manifest；
- 建立 `node_id → 邮件模板` 反向索引；
- 在 Patch 预览中展示已知影响、同步时间和未知范围；
- 完成独立 Shadow 工作台；
- AI 建议先冻结，人工决定后再揭示；
- 收集人工决策时间和修订记录；
- 对所有建议执行完整回放。

验收：

- 基础版本、Overlay、索引或 Usage Manifest 过期时自动阻断；
- 影响页面不把未知消费者显示成“无影响”；
- Patch 仍然只以文件形式存在；
- 每个案例能够定位召回、排序、决策、门禁或人工修订错误。

## 7. 第 6 周：评测、安全与交付

工作：

- 对冻结集执行一次正式评测；
- 报告 Recall、Precision、Coverage、Abstention 和专家时间；
- 报告 Qwen 延迟、超时和结构化失败；
- 执行红队测试：
  - Prompt 注入；
  - 脏数据；
  - 编造 ID；
  - 索引过期；
  - 模型超时；
  - 重复提交；
  - 版本并发变化；
  - Usage Manifest 不完整。
- 完成离线包、SBOM、操作手册、演示脚本和 Go/No-Go 报告。

验收：

- 安全硬门槛全部通过；
- 指标给出样本分子、分母和置信区间；
- 可以在虚构案例上完成公开面试演示；
- 真实指标只以经过审批的聚合结果展示；
- 质量不达标时继续 Shadow，不接写接口。

## 8. 六周必须砍掉的范围

- Spring Boot 正式写集成；
- 生产编辑器内嵌；
- 全量治理所有 2,000+ 节点；
- 运行时继承或多父节点；
- Elasticsearch、图数据库、Kafka 和微服务化；
- 在线 Proposer/Critic 多轮辩论；
- 模型微调；
- 实时邮件同步；
- 删除、移动、合并、改类型和改基数；
- 原始 VALUE 访问；
- 从粗糙历史自动恢复“正确业务意图”；
- 使用 AI 合成数据宣称业务准确率。

## 9. 交付物清单

外网通用交付：

- TreeGuard Core 源码；
- 版本化 contracts；
- File/Mock Adapter；
- 虚构 fixtures；
- 单元、契约、回放和评测测试；
- Conformance CLI；
- 离线依赖包；
- SBOM 和许可证清单；
- Transfer Manifest；
- 安全说明和部署手册。

内网形成：

- 真实 File Adapter；
- Qwen Provider 配置；
- 试点树索引；
- 已审批 Semantic Overlay；
- 专家讨论记录；
- 至少 30 条冻结 Gold；
- 邮件 Usage Manifest；
- Shadow Trace；
- Patch 文件和正式评测报告。

## 10. MVP 后的决策

满足安全硬门槛和质量目标后，下一阶段优先级：

1. 接入 Spring Boot 只读 API；
2. 建立稳定的邮件 Usage Manifest 生成机制；
3. 支持待审批 Patch 的服务端验证；
4. 扩大试点子树；
5. 积累至少 300 条专家批准案例；
6. 根据稳定错误模式决定是否微调 embedding、reranker 或动作分类器；
7. 最后再评估受控发布和对自然文本抽取的反哺。
