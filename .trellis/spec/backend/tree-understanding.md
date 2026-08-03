# 信息树理解与验证场景准备

本规范记录当前已实现的 M0–M4 合同及百炼虚构数据验证通道。它是只读 Shadow
能力，不是“模型已理解整树”的证明，也不授予语义审批、Gold、Patch 或生产写入
资格。

## 1. Scope / Trigger

修改以下任一能力时适用：

- `tree_understanding.py` 的全树画像、模型投影、模型输出解析或可信回放；
- `ai_review.py` 的 `InternalQwenTreeUnderstandingProvider` 与
  `BailianTreeUnderstandingProvider`，以及两个 `ScenarioPreparationProvider`；
- `tree-understanding-*.v1.schema.json`、`scenario-preparation-*.v1.schema.json`
  或 `scenario-review-*.v1.schema.json`；
- `scenario_validation.py` 的显式审核与 INTENT-only 执行边界；
- `scenario_capability_validation.py` 的完整能力 Oracle、分阶段执行与 Shadow 门槛；
- 虚拟验证场景的状态、引用、数量或人工审核政策。

确定性全树扫描与不可信模型边界必须分离。真实树投影只允许发送给受保护环境
内的 Qwen；百炼可以直接接收项目自编、可信分类的完全虚构测试数据，无需逐次数据
许可；其他数据仍需另行完成最终字节与用途审批。
增加 Workbench、sidecar、候选持久化或数据集注册需要独立任务。

## 2. Signatures

```python
build_tree_diagnostic_profile(
    tree: CanonicalTree,
) -> TreeDiagnosticProfile

build_tree_understanding_projection(
    tree: CanonicalTree,
    profile: TreeDiagnosticProfile,
    *,
    node_limit: int = 64,
    finding_limit: int = 20,
) -> TreeUnderstandingProjection

InternalQwenTreeUnderstandingProvider.analyze(
    tree: CanonicalTree,
    profile: TreeDiagnosticProfile,
    *,
    node_limit: int = 64,
    finding_limit: int = 20,
) -> TreeUnderstandingDraft

BailianTreeUnderstandingProvider.analyze(
    tree: CanonicalTree,
    profile: TreeDiagnosticProfile,
    *,
    node_limit: int = 64,
    finding_limit: int = 20,
    external_data_approved: bool = False,
) -> TreeUnderstandingDraft

TreeUnderstandingDraft.from_model_dict(
    payload,
    projection,
    profile,
    tree,
    *,
    model_provider,
    model_capability,
    model_name,
    prompt_version,
) -> TreeUnderstandingDraft

build_scenario_preparation_plan(
    tree,
    profile,
    *,
    max_plan_units=16,
    node_limit=48,
    new_node_placement_seed=None,
) -> ScenarioPreparationPlan

build_scenario_preparation_projection(
    tree, profile, plan, plan_unit_ref,
) -> ScenarioPreparationProjection

InternalQwenScenarioPreparationProvider.prepare(
    tree, profile, plan,
) -> ScenarioPreparationBatch

BailianScenarioPreparationProvider.prepare(
    tree, profile, plan, *, external_data_approved=False,
) -> ScenarioPreparationBatch

apply_scenario_review(
    action, batch, batch_candidate, projection, plan, profile, tree,
) -> ReviewedValidationScenario

run_reviewed_intent_slice(
    reviewed, action, batch, batch_candidate,
    projection, plan, profile, tree, provider,
) -> ScenarioIntentRun

freeze_capability_overlay(
    reviewed, plan, tree, *,
    review_status, reviewer_ref, recorded_at, review_round, oracle,
) -> ScenarioCapabilityOverlay

freeze_silver_capability_authorization(
    reviewed, plan, tree, *, assessor_ref, recorded_at, oracle,
) -> ScenarioCapabilitySilverAuthorization

run_reviewed_capability_scenario(
    overlay, reviewed, action, batch, batch_candidate,
    projection, plan, profile, tree, intent_provider, semantic_provider,
) -> ScenarioCapabilityRun

run_silver_capability_scenario(
    authorization, reviewed, action, batch, batch_candidate,
    projection, plan, profile, tree, intent_provider, semantic_provider,
) -> ScenarioCapabilityRun

verify_capability_overlay_for_execution(
    overlay, reviewed, plan, tree,
) -> None

build_capability_gate_report(
    preparation, runs, *,
    clarification_coverage_status, hard_failure_codes,
) -> CapabilityGateReport
```

`from_dict(payload, projection, profile, tree)` 必须从可信来源重建整个草案，不能只
验证外层 digest。

## 3. Contracts

### 确定性画像

- profile Schema：`tree-diagnostic-profile.v1`；
- algorithm：`treeguard.tree-diagnostic-profile.v1`；
- 扫描完整 `CanonicalTree`，不读取 `VALUE`、extension 或 `metadata_extra`；
- finding 只有 `NAME_REUSED_ACROSS_PATHS`、`NAME_CONTRACT_CONFLICT` 和
  `CHILD_CONTRACT_VECTOR_REUSED`，均是候选信号而非业务结论。

### 单次模型投影

- 输入 Schema：`tree-understanding-model-input.v1`；
- projection：`treeguard.tree-understanding-projection.v1`；
- 默认上限为 64 节点 / 20 finding，硬上限为 128 / 50，序列化字符上限
  48,000；
- 节点使用单次作用域 `N001`—`N128`，finding 使用 `D001`—`D050`；
- 节点视图只含 name、kind、value type、cardinality、depth、直接子节点数量和
  已投影父子临时引用；
- 不含稳定 node/tree ID、label、route、path label、hash、`VALUE`、extension
  或未知 metadata；
- `coverage` 精确报告包含和遗漏数量；截断时
  `coverage_complete=false`。

### 模型输出与草案

- 模型输出 Schema：`tree-understanding-model-output.v1`；
- 草案 Schema：`tree-understanding-draft.v1`；
- finding assessment 必须按投影顺序完整覆盖；
- 场景使用连续 `S001`—`S008`，节点/finding 引用必须属于当前投影；
- 场景的支持节点与来源 finding 引用是无优先级集合：parser 在验证引用格式、
  允许列表和唯一性后统一升序，输入数组顺序不进入草案语义或 digest；未知、
  重复、格式错误及空的支持引用仍拒绝；
- `SCENARIOS_PROPOSED` 至少包含一个场景；
- `NEED_EVIDENCE` 和 `ABSTAIN` 不含场景，前者必须列出 evidence gap；
- 草案固定
  `PENDING_HUMAN_REVIEW`、`semantic_approval=false`、
  `gold_eligible=false`、`patch_eligible=false`；
- snapshot/profile/projection/draft digest 都是完整性绑定，不是身份、审批或
  Gold 证明。

### M3 稀疏场景计划

- plan Schema：`scenario-preparation-plan.v1`；algorithm：
  `treeguard.scenario-preparation-plan.v1`；
- 核心风险族固定为 `CLEAR_EXISTING_REUSE`、`NEW_NODE_PLACEMENT`、
  `HOMONYM_CLARIFICATION`、`WRONG_PARENT_OR_CROSS_BRANCH`、
  `KIND_CONFLICT`、`CARDINALITY_CONFLICT`、`INSUFFICIENT_EVIDENCE` 和
  `UNBOUNDED_COMBINATION`，按该顺序最多各规划一个风险单元；
- 默认最多 16 个、硬上限 32 个单元；适用风险单元优先，剩余名额用于一级分支
  覆盖，不做分支 × 风险笛卡尔积；
- 分支超额时依次保留节点数最大、相对深度最大、最大直接子节点数最大的分支并
  去重，再按规范化结构向量差异补足；稳定 ID 只作同分决胜；
- `NEW_NODE_PLACEMENT` 只有显式 `NewNodePlacementSeed` 时适用；父节点必须存在且
  归属一级分支，规范化新名称必须在整树中不存在；
- `BRANCH_LOCAL` 只允许一个一级分支，`CONTRAST` 只允许计划声明的少量上下文，
  `AMBIGUITY` 可缺少父提示或包含有意冲突；
- 节点存储重排不得改变单元、覆盖、临时引用或 digest。

### M3 逐单元投影、候选与批次

- 模型输入/输出 Schema 分别为 `scenario-preparation-model-input.v1` 和
  `scenario-preparation-model-output.v1`；候选/批次分别为
  `scenario-preparation-candidate.v1` 和 `scenario-preparation-batch.v1`；
- 每单元默认最多 48 节点、硬上限 64、序列化最多 48,000 字符；只发送单次
  `N/D/U` 临时引用、允许列表字段、计划锁定值和准确的包含/遗漏计数；
- 模型每单元只返回 `S001`，必须原样回显 planning mode、family、target stage、
  父提示和类型/基数提示；每个 requested aspect 至少绑定一个允许节点引用；
- 场景准备 Prompt v3 为八个风险族提供各自的确定性任务说明；对象模板中的
  requirement/aspect/rationale/evidence gap 使用四个必须改写的固定哨兵，模型
  原样保留任一哨兵时失败关闭；该升级不改变 v1 模型输入/输出 Schema 字段；
- `requirement_text`、`requested_aspects[].aspect`、`rationale`、
  `uncertainties[]`、`evidence_gaps[]` 不得包含独立的单次投影 `N/D/S` 引用；
  结构证据只能通过专用引用字段表达。`HOMONYM_CLARIFICATION`、
  `UNBOUNDED_COMBINATION` 必须至少披露一项 uncertainty，
  `INSUFFICIENT_EVIDENCE` 必须至少披露一项 evidence gap；Prompt 明确结构定义
  不等于实例值、`SINGLE/MULTIPLE` 只表达基数而不推出“必填”；自然用户视角、
  需求—证据等价、具体缺口和基数文字含义仍由人工审核，不能使用中文关键词自动
  裁决；
- 模型不得选择覆盖、Oracle、审批、Gold、Patch 或发布状态；候选固定
  `PENDING_HUMAN_REVIEW`、非 Gold、非 Patch；
- 候选直接构造、模型解析与存储回放统一执行当前文本政策；不得依据候选自带的
  `prompt_version` 放宽旧输出。若未来需要长期回放不满足当前安全政策的历史候选，
  必须升级可信候选合同，不能增加版本字符串绕过；
- 合法无序引用在验证格式、唯一性和允许列表后本地规范排序；模式外、计划外、
  重复、未知或内部稳定 ID 失败关闭；
- 多投影归并给候选分配运行级 `C001`—`C032`，不能把各投影的 `S001` 当作
  跨投影身份；每个计划单元必须恰好归入 success、failure 或 typed
  `NOT_EXECUTED`，后者不能用普通 failure code 冒充；
- 批次固定 `PENDING_HUMAN_REVIEW`、`semantic_approval=false`、非 Gold、非
  Patch，并把四种覆盖保持为不可互换的字段：
  - `family_outcomes` 只取每个风险族唯一 `RISK_CHALLENGE` 单元的
    `CANDIDATE_READY`/`FAILED`/`NOT_EXECUTED`，或计划本身的
    `NOT_APPLICABLE`/`OMITTED_BUDGET`；branch-coverage 单元不能冒充风险族结果；
  - `branch_coverage` 只按 `BRANCH_LOCAL` 单元分别列出候选、失败、未执行和预算
    遗漏的一级分支；同一分支有多个单元且结果不同时，结果列表允许重叠；
  - `target_stage_coverage` 只统计各目标阶段的准备结果；M3 尚未执行这些批次，三个
    阶段的 `validation_status` 都固定为 `NOT_RUN`；
  - `projected_node_coverage` 是全部成功预构建投影中 reverse mapping 的唯一节点
    并集，只报告 total/included/omitted 聚合数，不相加逐单元计数、不输出节点身份，
    也不证明语义理解；
- 批次可信回放必须从 tree/profile/plan 重建所有成功预构建投影，再重建候选、结果
  分区、四种覆盖与 digest；不能只用被审核候选的单个投影伪造整批覆盖；
- 有失败、未执行或预算遗漏时为 `PARTIAL`，成功候选仍可审核；全部单元失败且
  没有成功候选时为
  `FAILED` 且无可审核候选；无失败/遗漏时才为 `SUCCESS`；
- 三档青岚完全虚构 `tree.json` 是主要回归输入。原 scenarios/coverage/promotion
  只在生成完成后作隐藏对照；独立 overlay 只提供不存在节点的 seed，不含需求或
  Oracle；这种确定性 fake-transport 运行必须标记 `FIXTURE_REPLAY`，真实模型生成
  标记 `UNVERIFIED_MODEL_GENERATION`。来源状态只说明产物路径，不是语义能力、
  Gold、审批或发布证明，逐字复现隐藏参照也不得升级该结论。

### M3 显式审核与首个执行切片

- `ScenarioReviewAction` 同时绑定 batch hash、运行级 candidate ref、candidate/
  tree/profile/plan/projection digest，并由可信审核者冻结最终
  `ValidationScenarioRequest` 与可观察 `ValidationScenarioOracle`；
- `PARTIAL` 批次不阻止其中成功候选独立审核；两个局部 `S001` 必须通过不同
  `C` 引用区分；
- 未审核 candidate 不能执行。review/action 的自洽外层 hash 不能替代从可信
  candidate/projection/plan/profile/tree 的完整回放；
- `run_reviewed_intent_slice()` 只调用一次 intent `draft()`，不澄清、不人工确认、
  不召回、不语义推荐；INTENT 记录 `MATCH`/`MISMATCH`，后两阶段始终明确
  `NOT_RUN`；
- candidate 的 target stage 不是 INTENT 时，即使意图状态匹配，
  `target_validation_status` 仍为 `NOT_RUN`；
- 审核、候选和运行工件始终 `semantic_approval=false`、非 Gold、非 Patch；
  M3 不写 Workbench sidecar、不注册 dataset provider。

### M4 完整能力 overlay、执行与门槛

- M4 新增独立 `scenario-capability-overlay.v1`、`scenario-capability-run.v1` 和
  `scenario-capability-report.v1`，不得修改或放宽 M3 action、record、intent-run
  v1；
- overlay 只接受 `ACCEPTED` 或 `REVISED_ACCEPTED`，固定
  `CLEANROOM_SYNTHETIC`、`fictional=true`、`derived_from_real=false`、
  `semantic_approval=false`、非 Gold、非 Patch，并绑定 reviewed hash、树快照、
  计划和“已审核 request + 完整 Oracle”的内容 digest；
- Codex 辅助审核不得伪装成上述人工 overlay。校准执行使用独立
  `scenario-capability-silver-authorization.v1`，固定
  `status=SILVER_ACCEPTED`、`quality_tier=SILVER`、
  `assessment_authority=CODEX_ASSISTED`、`execution_scope=CALIBRATION_ONLY`，
  且 `gold_eligible=false`、`gate_eligible=false`、`patch_eligible=false`；
  Silver 只能授权校准调用和来源绑定结果记录，不能进入正式 M4 门槛分母，实验成功
  也不能自动升级为 Gold；
- `expected_route` 只取 `PROCEED`/`CLARIFY`，且必须与 M3 已冻结的
  `draft_status` 一致；意图 profile 只做确定性字段比较：标量字段可用
  `EXACT_ONE_OF`，标量或 tuple 可用 `NON_EMPTY`，tuple 可用 `EMPTY`，不比较字段
  显式使用 `NOT_COMPARED`，不得加入另一个 LLM judge；
- `CLARIFY` 时召回和推荐均不适用；`PROCEED` 时二者均适用。召回按允许状态和
  稳定 node ID 的 Hit@K 判断；空目标 Oracle 只能接受非 ready 状态；
- 推荐 Oracle 是一个或多个完整的 `action + stable target/null + relation/null`
  联合结果，禁止分别命中三个集合后做笛卡尔拼接；运行级 `C001`—`C008` 必须先
  通过同次 Top-8 候选映射回稳定 node ID；
- 意图 `MISMATCH/RUN_FAILED` 固定短路召回和推荐；召回
  `MISMATCH/RUN_FAILED` 固定短路推荐。级联阶段保持适用分母但记
  `NOT_RUN` 和固定上游 reason，不重复增加语义失败数；
- 私有 run 可以保存来源 hash，但公开 report 只能保存固定政策值、候选审核聚合、
  阶段分母/计数、允许列表 code 和 `GO_SHADOW/NO_GO`，不得包含 request、Oracle、
  稳定目标、hash、Prompt、模型文本或 trace；
- 候选门要求计划完全记账、可执行候选至少 8、直接接受至少 4、reject 加生成失败
  最多 3、blocking finding 为 0、人工审核不超过 150 分钟；执行门要求恰好 8 条、
  至少 6 条完整路径 MATCH、每个适用阶段最多 1 条 MISMATCH/RUN_FAILED，并满足
  7+1 澄清组成或显式 `NOT_APPLICABLE_WITH_BACKFILL` 的 8 条完整链路；
- 只有两个门均 PASS 且 `DATA_BOUNDARY_FAILURE`、`SOURCE_BINDING_FAILURE`、
  `CONTRACT_INTEGRITY_FAILURE`、`RESULT_ACCOUNTING_FAILURE` 均不存在时，才输出
  `GO_SHADOW`；该结论只授权继续受控 Shadow 验证；
- 单 overlay 是功能运行时合同；数据集 manifest、批量 sidecar wrapper、fixture
  SHA、合同提交绑定和数据集 selector 由独立数据任务拥有，但其中每个可执行项必须
  能重建该 overlay，不能在数据分支发明宽松运行时字段。
- request-aware 执行资格政策固定为
  `treeguard.capability-oracle-request-policy.v1`。M4 v1 request 只有
  `node_kind_hint`、`value_type_hint`、`cardinality_hint` 是可逐字段确定性重放的
  Intent 证据：显式且非 `UNKNOWN`/非 `null` 的 hint 必须用 `EXACT_ONE_OF`
  精确接受该值，不得选择性忽略；`UNKNOWN`/`null` 只表示 request 没有提供证据，
  对应 expectation 必须是 `NOT_COMPARED`，不能据此断言模型也应输出未知或空值；
- `clarification_question` 由 route 支持：`PROCEED` 可以 `NOT_COMPARED` 或精确
  接受 `null`，`CLARIFY` 必须 `NON_EMPTY`；route 本身仍先比较，且 `PROCEED`
  的空问题检查不替代至少一个结构化 hint 提供的区分力；
- v1 没有逐字段文本 span 或完整性证明，因此
  `subject/role/scenario/lifecycle/ownership` 和
  `confirmed_facts/assumptions/evidence_gaps` 只能 `NOT_COMPARED`。尤其
  `PROCEED` 只表示没有澄清问题，不保证 assumptions/evidence gaps 为空；
- 每个可执行 profile 必须显式且只覆盖全部 12 个 Intent 字段；`PROCEED` 至少保留
  一个由非空结构化 hint 支持的有区分力比较，`CLARIFY` 可以由非空澄清问题承担
  区分力，禁止退化成只比较 route 或无条件通过；
- `ScenarioCapabilityOverlay.from_dict()` 可以对历史 overlay 做形状和来源重放；
  `freeze_capability_overlay()`、`verify_capability_overlay_for_execution()`、实际运行和
  数据门禁必须另外校验 request support。历史不可回答工件可以保留为诊断，但不能
  调用 Provider 或进入 go/no-go 分母；
- 未来若要比较自由文本字段或断言 list 为空，必须升级 overlay 版本，为每个
  expectation 绑定结构化 request 字段或精确文本 span 与完整性证据；单独增加不可
  重放的 `answerability=true` 不能放宽 v1。

### M4.5 密封重复性报告

- `scenario-capability-report.v1` 保持首轮 8 条、7+1/8+0、6/8 和逐阶段单失败预算
  不变；24×3 验证使用独立 `scenario-repeatability-report.v1` 与
  `treeguard.m45-sealed-repeatability-gate.v1`，不能修改或复用 v1 门槛常量；
- 新报告消费三轮现有 `ScenarioCapabilityRun`：每轮精确 24 条、round 内 overlay
  唯一，三轮 overlay 集合和 expected route 一致；同一 overlay 跨轮重复是重复性
  观测，不是重复记账；
- 每轮组成固定 18 `PROCEED` + 6 `CLARIFY`。公开报告只保存逐轮阶段聚合、每轮完整
  路径计数、3/3 稳定数、实际执行召回命中、Intent/Semantic 合同合法计数、澄清
  TP/FP/FN/TN、硬冲突错误复用数、固定 code 和决定；
- 固定门槛为：Intent/Semantic 重试后最终合同合法率均至少 98%，实际执行的确定性
  召回 100%，每轮完整路径至少 18/24，3/3 稳定场景至少 18/24，硬冲突错误复用为
  0，四类 hard failure 为 0；百分比使用整数交叉乘法判断；
- Semantic 合同分母精确等于三轮中真正执行推荐的单元数；上游短路不伪装成 Semantic
  合同失败。澄清混淆矩阵本版单独观察，不另设通过阈值；
- 多个来源绑定 batch/plan 可以组成 24 条密封执行集，但每条 overlay 仍绑定自己的
  可信 plan/batch/reviewed bytes；报告不把多个 plan 伪造成一个 plan，也不放宽
  planner 的 32 单元上限；
- 报告 parser 只能验证聚合自洽和固定政策，不能从聚合值反推出逐场景交集或权威来源；
  完整执行 harness 必须先可信重放各单条 run，再构建报告。匹配报告不是签名或 Gold。

### 内网 Qwen

只允许 `InternalQwenConfig`。请求沿用现有隔离 transport：禁 proxy/redirect、
响应有界、严格 JSON、JSON-object mode、`temperature=0`、
`chat_template_kwargs.enable_thinking=false`、不发送 Authorization、最多两次
顺序尝试且不自动回退。

M3 在任何网络调用前完整回放 tree/profile/plan，并零网络预构建所有单元投影。
只有 required-scope/character 预算错误可记为单元失败并继续；来源或关系不一致使
整批失败。模型 envelope/content/本地合同失败可进行第二次完整尝试；transport
失败不在该单元内重试，但记录固定错误码并继续其他单元。

### 百炼虚构数据验证

只允许 `BailianConfig`，并且 `external_data_approved` 必须精确为 `True` 才能
发起网络。对于可信的项目自编 clean-room 测试数据，实验 harness 可以直接设置该值，
无需逐次向用户索要数据许可。请求复用同一投影、Prompt、模型输出合同和本地来源
绑定，沿用百炼官方 HTTPS host、Authorization header、禁 proxy/redirect、有界
响应、严格 JSON、`enable_thinking=false`、`temperature=0` 与最多两次尝试。

该门禁只声明调用方已确认输入具备外传资格，不把任意投影自动变成脱敏数据。项目自编
clean-room 测试数据已有常设 LLM 授权；真实树、真实节点名称、专家文本或生产模型流量
不得进入百炼。内网 Qwen 与百炼必须显式选择，禁止自动回退。

任一次模型输出未通过精确字段、引用或跨字段政策时，只能要求模型重新生成一次
完整 JSON；本地不得补入缺失字段、删除额外字段或增加、删除、替换 N/D/S 引用。
合法唯一的集合型引用允许做不改变成员的升序规范化。第二次仍失败则返回最后一个
固定合同错误码，不产生部分草案。

## 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| tree/profile 不一致 | `TREE_UNDERSTANDING_PROFILE_SOURCE_MISMATCH` |
| node/finding limit 非法 | `TREE_UNDERSTANDING_PROJECTION_*_LIMIT_INVALID` |
| 投影超过字符预算 | `TREE_UNDERSTANDING_PROJECTION_TOO_LARGE` |
| 重放投影与可信来源不一致 | `TREE_UNDERSTANDING_PROJECTION_SOURCE_MISMATCH` |
| 模型顶层字段或版本错误 | `TREE_UNDERSTANDING_MODEL_FIELDS_INVALID` / `*_VERSION_INVALID` |
| finding 未按顺序完整覆盖 | `TREE_UNDERSTANDING_MODEL_FINDING_COVERAGE_INVALID` |
| 未知、重复或格式错误的 N/D 引用 | 对应 `TREE_UNDERSTANDING_MODEL_*_REF_INVALID` |
| 合法唯一的场景 N/D 引用未排序 | 本地升序规范化后继续校验 |
| 场景 S 引用不连续或 finding assessment D 引用乱序 | 对应 `*_ORDER_INVALID` / `*_COVERAGE_INVALID` |
| status 与场景/evidence gap 冲突 | `TREE_UNDERSTANDING_MODEL_GENERATION_POLICY_INVALID` |
| 模型文本包含内部 ID | `TREE_UNDERSTANDING_MODEL_INTERNAL_ID_FORBIDDEN` |
| 存储草案重建后不一致 | `TREE_UNDERSTANDING_DRAFT_SOURCE_MISMATCH` |
| Qwen transport 失败 | 既有 `QWEN_*` family，不返回部分草案 |
| 百炼缺少 `external_data_approved=True` 外传资格声明 | `EXTERNAL_DATA_APPROVAL_REQUIRED`，网络前失败 |
| 百炼 transport 失败 | 既有 `BAILIAN_*` family，不返回部分草案 |
| M3 plan/unit/node limit 非法 | `SCENARIO_PREPARATION_*_LIMIT_INVALID` |
| M3 seed 父节点未知或名称已存在 | `SCENARIO_PREPARATION_NEW_NODE_SEED_INVALID` |
| M3 projection 必需作用域/字符超限 | 对应 `SCENARIO_PREPARATION_PROJECTION_*` 单元失败 |
| M3 模型字段、计划回显、引用或 hint 政策错误 | 对应 `SCENARIO_PREPARATION_MODEL_*` 单元失败 |
| M3 保留模板哨兵或把临时引用写入任一自然语言字段 | `SCENARIO_PREPARATION_MODEL_TEXT_POLICY_INVALID` |
| M3 存储候选自称旧 Prompt 但违反当前文本政策 | `SCENARIO_PREPARATION_MODEL_TEXT_POLICY_INVALID`，不按版本降级 |
| M3 风险族缺少最小 uncertainty/evidence gap | `SCENARIO_PREPARATION_MODEL_FAMILY_POLICY_INVALID` |
| M3 success/failure 未精确分区计划 | `SCENARIO_PREPARATION_BATCH_PARTITION_INVALID` |
| 未审核候选直接执行或 action 陈旧 | `SCENARIO_REVIEW_REQUIRED` / `SCENARIO_REVIEW_ACTION_STALE` |
| candidate/projection/plan/tree 来源不匹配 | `SCENARIO_REVIEW_CANDIDATE_SOURCE_MISMATCH` 等来源错误 |
| Intent Provider 返回错误来源草案 | `SCENARIO_INTENT_DRAFT_SOURCE_MISMATCH` |
| M4 overlay 额外字段、版本或固定政策改变 | `CAPABILITY_OVERLAY_*_INVALID` |
| M4 overlay 与 reviewed bytes/tree/plan 不一致 | `CAPABILITY_OVERLAY_SOURCE_MISMATCH` |
| M4 Oracle 稳定目标不在绑定树中 | `CAPABILITY_ORACLE_SOURCE_MISMATCH` |
| M4 route 与 M3 observable Oracle 矛盾 | `CAPABILITY_OVERLAY_OBSERVABLE_ORACLE_MISMATCH` |
| M4 Intent expectation 无冻结 request 支持或与 hint/route 冲突 | `CAPABILITY_ORACLE_REQUEST_MISMATCH`，Provider 零调用 |
| M4 执行前 M3 来源回放失败 | `CAPABILITY_REVIEWED_SOURCE_MISMATCH`，Provider 零调用 |
| M4 Provider/本地输出合同失败 | 对应阶段 `RUN_FAILED`，后续固定 `NOT_RUN` |
| M4 意图或 Hit@K 不符合 Oracle | 对应阶段 `MISMATCH`，后续固定短路 |
| M4 run 存储重放来源不一致 | `CAPABILITY_RUN_SOURCE_MISMATCH` 或 `CAPABILITY_RUN_REVIEWED_SOURCE_MISMATCH` |
| M4 公开 hard failure code 不在四项允许列表 | `CAPABILITY_HARD_FAILURE_CODES_INVALID` |
| M4 任一硬失败、候选门或执行门失败 | `NO_GO` |

## 5. Good / Base / Bad Cases

- Good：完整或明确截断的虚构树投影产生待人工审核场景；引用全部可回映，草案
  保持非 Gold、非 Patch。
- Base：证据不足时返回 `NEED_EVIDENCE`、零场景和至少一个 evidence gap。
- Bad：直接发送 profile `to_dict()`、隐藏遗漏节点、把场景当 oracle、让外部百炼
  调用真实节点 name、或把模型输出直接注册进验证数据集。
- M4 Good：人工冻结完整 Oracle 后，意图、Hit@K 和推荐联合结果均 MATCH，公开
  报告只显示聚合门槛并输出 `GO_SHADOW`。
- M4 Base：合法澄清在意图阶段 MATCH，召回/推荐为不适用的 `NOT_RUN`；或上游
  不匹配导致下游适用但短路，不重复计错。
- M4 Bad：Oracle 保存 `C001`、分别维护 action/target/relation 集合后做组合，或把
  6/8 通过解释为生产准确率/Gold。
- M4 request-policy Good：只比较冻结的类型/基数 hint 和 route；未结构化支持的
  自由文本字段显式 `NOT_COMPARED`，后续召回/推荐仍承担实质定位验收。
- M4 request-policy Base：历史 overlay 形状和来源可重放，但执行资格因固定 request
  policy 失败，保留为诊断而不调用模型。
- M4 request-policy Bad：仅凭 requirement text 非空就要求 role/scenario
  `NON_EMPTY`，或仅凭 `PROCEED` 就要求 assumptions/evidence gaps `EMPTY`。

## 6. Tests Required

- 2,001 节点完成确定性全树扫描，单次投影仍受固定上限约束；
- 节点存储重排不改变 profile、projection、临时引用或 digest；
- Schema 必填字段与 Python 顶层/嵌套字段精确一致；
- 模型视图不存在稳定 ID、hash、label、route、path 或未知字段 canary；
- 未知、重复引用、额外字段、策略冲突和内部 ID fail closed；合法唯一的场景
  引用重排后产生相同规范草案和 digest；
- projection/profile/tree 与草案的重新哈希篡改仍被可信回放拒绝；
- `NEED_EVIDENCE` 零场景合法，避免合同强迫幻觉；
- Qwen 虚构 transport 断言无 Authorization、thinking 关闭、JSON mode、最多
  两次尝试且无真实网络。
- 百炼虚构 transport 断言缺少批准时零网络、token 只进 header、使用顶层
  `enable_thinking=false`，并复用同一严格输出合同。
- 首次输出缺字段、额外字段或错误引用、第二次合法时，只返回第二次完整重建且
  已验证的草案；两次都非法时 fail closed，禁止本地修补第一次输出。
- 自动化 suite 不访问真实网络；手工百炼冒烟只发送完全虚构投影，不持久化请求/
  响应，只输出固定状态与聚合计数。
- 48/312/2,001 节点青岚树直接由各自 `tree.json` 进入计划；生成请求不含场景
  reference/request、旧风险值、覆盖矩阵或 promotion key；
- 八风险族按适用性产生 `PLANNED`/`NOT_APPLICABLE`/`OMITTED_BUDGET`，默认/硬
  预算、结构代表性选择、分支遗漏和节点存储重排均有确定性测试；
- 每单元最多两次调用，重试不会合并两个 candidate；transport、合同和投影预算
  局部失败仍准确形成 partial batch；
- Prompt v3 断言八族任务说明互异、四个模板哨兵必须改写、五类自然语言字段均
  拒绝独立 `N/D/S` 引用而结构化引用保持合法，三类风险的最小披露政策有正反例；
  上述失败仍只触发一次完整重试，不由本地代码修补文本；Prompt 结构—实例边界
  只作生成目标断言，不被报告为自动语义验收；
- 候选直接构造和 `from_dict()` 回放均执行同一文本政策；把 `prompt_version`
  改为 v2 不能放行 rationale、uncertainty 或 evidence gap 中的受禁引用；
- 批次四种覆盖分别验证，节点覆盖使用跨投影唯一并集；完整可信回放拒绝重新哈希
  的覆盖篡改，全部 `NOT_EXECUTED` 为 `PARTIAL` 而不是 `FAILED`；fixture replay
  有独立机器可读来源状态且不被报告为语义评估；
- 两个局部 `S001` 归并为不同运行级 `C` 引用；未审核、陈旧 action、换来源和
  重算外层 hash 在 Provider 调用前失败；
- 已审核 INTENT-only 执行恰好调用一次 draft，后两阶段为显式 `NOT_RUN`，且
  RETRIEVAL/RECOMMENDATION target 不借用 INTENT MATCH 冒充通过。
- M4 三份 Schema 的顶层/嵌套 required 与 serializer 精确一致；overlay 额外字段、
  错树、错计划、错受审字节、route 矛盾和重新哈希篡改均拒绝；
- Silver authorization 的固定来源、质量等级、非 Gold/非门禁政策和来源 digest
  必须逐项重放；篡改 authority、gate/Gold 资格或 Oracle 后重算外层 hash 仍拒绝；
- M4 request policy 覆盖 hint 精确一致/冲突、PROCEED/CLARIFY question、未绑定
  自由文本、list `EMPTY`、多 profile 任一不合法、历史 overlay 可读不可执行，以及
  Intent/Semantic Provider 零调用；
- 完整链路把 `C001` 映射回同次候选集的稳定目标后比较；Hit@K 未命中不调用推荐，
  推荐动作—目标—关系只按冻结联合结果判断；
- 合法澄清、三个阶段 MATCH/MISMATCH/RUN_FAILED、上游短路、运行重放和固定 reason
  code 均有正反例；级联 `NOT_RUN` 不增加下游 mismatch/run-failed；
- 候选门和执行门覆盖阈值等号、低一单位、两次同阶段失败、硬失败、7+1 与 N/A 回填；
  runs 重排不改变公开报告；
- 公开报告使用 request、Oracle、node ID、source hash、Prompt、模型文本和 trace
  canary 做允许列表泄漏测试；M3 v1 序列化与完整原有 suite 保持不变。

## 7. Wrong vs Correct

Wrong：

```python
request_payload = profile.to_dict()
draft = model(request_payload)
validation_dataset.register(draft["virtual_scenarios"])
```

这会发送稳定来源信息、绕过本地引用/来源校验，并把未审模型输出升级为 Gold。

M2 Correct：

```python
projection = build_tree_understanding_projection(tree, profile)
draft = InternalQwenTreeUnderstandingProvider(config).analyze(tree, profile)
assert draft.review_status == "PENDING_HUMAN_REVIEW"
```

外网虚构数据效果冒烟必须显式选择
`BailianTreeUnderstandingProvider` 并传入 `external_data_approved=True`；对项目
自编 clean-room 测试数据可直接传入，无需逐次许可，但这不授权真实树外发。

M3 Correct：

```python
plan = build_scenario_preparation_plan(tree, profile)
batch = InternalQwenScenarioPreparationProvider(config).prepare(
    tree, profile, plan
)
candidate = batch.candidates[0]
reviewed = apply_scenario_review(
    action, batch, candidate, projection, plan, profile, tree
)
run = run_reviewed_intent_slice(
    reviewed, action, batch, candidate,
    projection, plan, profile, tree, intent_provider,
)
assert run.retrieval_validation_status == "NOT_RUN"
assert run.recommendation_validation_status == "NOT_RUN"
```

Workbench sidecar、候选持久化、数据集注册和后续阶段验收仍需独立合同。

M3 replay Wrong：

```python
if payload["prompt_version"].endswith(".v2"):
    skip_current_text_policy(payload)
```

候选自带版本是待验证文本，不能授权安全策略降级。

M3 replay Correct：

```python
draft = ScenarioCandidateDraft.from_dict(
    payload, projection, plan, profile, tree
)
# from_dict 通过当前 from_model_dict 合同重建；旧 Prompt 标记没有绕过权限。
```

M4 Wrong：

```python
if draft.selected_candidate_ref in oracle.acceptable_candidate_refs:
    recommendation_status = "MATCH"
```

`C001` 只在一次 Top-8 投影内有效，不能成为长期 Oracle 身份。

M4 request-policy Wrong：

```python
IntentFieldExpectation("role", "NON_EMPTY", ())
IntentFieldExpectation("evidence_gaps", "EMPTY", ())
```

v1 没有 role 的逐字段输入证据，也没有“请求完整且无证据缺口”的来源绑定；形状合法
不等于 Oracle 可实现。

M4 Correct：

```python
overlay = freeze_capability_overlay(
    reviewed, plan, tree,
    review_status="ACCEPTED",
    reviewer_ref=reviewer_ref,
    recorded_at=recorded_at,
    review_round=1,
    oracle=oracle,
)
run = run_reviewed_capability_scenario(
    overlay, reviewed, action, batch, candidate,
    projection, plan, profile, tree, intent_provider, semantic_provider,
)
report = build_capability_gate_report(
    preparation_metrics, runs,
    clarification_coverage_status="NOT_APPLICABLE_WITH_BACKFILL",
    hard_failure_codes=(),
)
assert report.decision in {"GO_SHADOW", "NO_GO"}
assert report.gold_eligible is False
```

执行前还必须调用 `verify_capability_overlay_for_execution()`；历史 overlay 的
`from_dict()` 成功只表示形状、哈希和来源可重放，不授予门控执行资格。
