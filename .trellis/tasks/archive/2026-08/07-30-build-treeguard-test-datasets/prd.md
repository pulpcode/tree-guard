# 构建多测试数据集 Skill

## 背景

TreeGuard 已有完全虚构、可确定性重建的消防验证数据，但缺少一套可重复的项目工作流，用于按不同验证目的构建、检查和晋升多个测试数据集。`schema-flow` 的 `build-test-sample` Skill 提供了可借鉴的分阶段编排、确定性门禁、独立 Critic 和人工晋升机制；其真实来源采集、字段/值提取、模型生成 Gold 等业务流程不符合本项目的数据边界，不能照搬。

## 目标

1. 新增项目级 Skill，指导构建多个用途明确、完全虚构的 TreeGuard 验证数据集。
2. 建立数据集角色、来源分类、阶段工件、机器门禁、只读 Critic、有限人工审核和晋升合同。
3. 明确阻止笛卡尔积造树、模型自证 Gold、真实/受保护信息进入外网工件。
4. 把人工审核控制在可失败、可停线的小批次内，不把 300–500 个节点全量人工审核作为首个里程碑。
5. 在语义蓝图中显式区分单一对象、重复成员和集合聚合属性，阻止成员级属性直接挂在集合概念下。

## 非目标

- 本任务不生成或晋升新的正式测试数据集。
- 本任务不修改现有消防生成器、Provider、Workbench 或生产信息树。
- 本任务不替代后续开发 Plan，也不启动功能实现或并行数据准备。
- 数据准备将在用户敲定 Plan、开始开发并另开对话/worktree 后独立进行。
- 本任务不调用外部模型、Web、MCP 或受保护环境。
- 本任务不创建真实领域 Gold，不保存模型原始请求、响应或 trace。
- 本任务不自动提交、发布或合并任何数据集。

## 数据边界

- 仅允许 `CLEANROOM_SYNTHETIC`、获批准的公开技术合同形状、固定错误码和聚合统计。
- 禁止真实信息树、真实字段名、`VALUE`、专家文本、真实关系/层级、内部标识、凭据、内部路径和网络拓扑。
- 改名、遮罩、稳定化名、删除 `VALUE` 均不构成充分脱敏。
- AI 只可生成或评审完全虚构候选；所有 AI 候选固定 `gold_eligible=false`。
- 外部模型的原始请求、响应、reasoning 和 trace 不得落库；只可保留允许列表化的非权威 sidecar。

## 数据集角色

- `PRECISION_CONTRACT`：小型、确定性、可全量人工复核的核心合同集。
- `SEMANTIC_CHALLENGE`：覆盖歧义、证据不足、冲突和拒答等语义挑战的候选集。
- `PRODUCTION_SHAPE`：复现生产常见规模和形状但不复现生产语义的数据集。
- `SCALE_STRESS`：只验证规模、重排、时延和有界候选，不承担语义 Gold。
- `DOMAIN_CONTROL`：小型第二虚构领域，用于识别领域过拟合。

## 期望工作流

1. **Dataset Charter**：声明角色、规模、挑战标签、固定 seed、允许来源、人工预算和停止条件。
2. **Semantic Blueprint**：声明策划语义核心、属性所有者及单体/成员/集合范围、允许的 subject/facet 兼容关系、背景/压力节点策略；禁止把成员级属性直接挂在集合概念下，也禁止全局维度笛卡尔积。
3. **Deterministic Build**：由现有或后续专用生成器在 staging 中生成树、场景和 manifest。
4. **L1 Machine Gate**：检查适配、节点/场景数、确定性、引用一致性、泄漏 canary、兼容允许表、组合密度和角色约束。
5. **L2 Read-only Critic**：只报告结构自然度、场景可答性和证据锚定问题，不修改工件、不授予 Gold。
6. **L3 Budgeted Human Gate**：复核所有高风险项、每个新风险簇代表样本和固定随机样本；仅计划晋升的少量合同项进入双人复核。
7. **Promotion**：人工批准后才可晋升正式 fictional fixture；晋升后重跑完整测试。

## 人工审核预算

- 每批候选上限默认 25 个场景；首个证明批次应更小。
- 所有候选先完成机器检查、去重和覆盖聚类。
- 人工复核全部高风险项、每个新风险簇至少一个代表，以及默认 5 个随机样本。
- 仅在确有第二审核者时，每批最多 3–5 个计划成为确定性合同 oracle 的案例进入
  双人复核；只有一名审核者时预算必须为 0，且不得由同一人或同一模型模拟双审。
- 若发现任一严重数据边界/安全错误，或随机样本出现两个及以上实质语义错误，应停止该批次并修复蓝图或生成器，而不是继续人工清洗。
- `300–500` 个节点全量人工审核只能作为后续可选活动，不是首个 Skill 或数据集里程碑。

## 交付物

- `.agents/skills/build-treeguard-test-datasets/SKILL.md`
- `.agents/skills/build-treeguard-test-datasets/agents/openai.yaml`
- `.agents/skills/build-treeguard-test-datasets/references/pipeline-contract.md`

## 验收标准

- Skill 能明确区分五类数据集角色及其允许用途。
- Skill 明确使用 clean-room fictional 数据，阻止真实派生、联网 harvest 和 AI 自证 Gold。
- 每个阶段都有输入、输出、门禁、失败回退和最大修复轮次。
- 审核预算、随机抽检、可选双人复核和停线条件可执行；缺少第二审核者不会阻断
  单人审核流程，也不会被错误记录为双审。
- Skill 默认停在规划阶段；只有用户批准开发 Plan 并明确开始实施后才允许造数据。
- Skill 说明后续功能与数据 worktree 的基线、文件所有权、共享合同和合并顺序。
- 文档明确使用兼容允许表、覆盖矩阵/pairwise 选择和挑战标签，禁止全维度笛卡尔积。
- 文档明确 `CONCEPT` 能否带属性取决于其语义主体；重复对象的成员属性使用 `PROPERTY + value_type=class + cardinality=MULTIPLE` 容器，集合级属性必须显式表达聚合语义。
- `agents/openai.yaml` 可触发该 Skill，默认提示包含 `$build-treeguard-test-datasets`。
- 通过 Skill 结构校验、Trellis 测试和 `git diff --check`。

## 首个后续切片

Skill 验收后，另起实现任务构建约 31–50 节点、8 个场景的 `DOMAIN_CONTROL` 或小型语义证明集；只有确定性合同场景带 oracle，AI 生成内容保持 `AI_SYNTHETIC`。
