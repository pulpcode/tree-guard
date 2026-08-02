# 信息树理解与验证场景准备

本规范记录当前已实现的 M0–M3 合同及百炼虚构数据验证通道。它是只读 Shadow
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
- 虚拟验证场景的状态、引用、数量或人工审核政策。

确定性全树扫描与不可信模型边界必须分离。真实树投影只允许发送给受保护环境
内的 Qwen；百炼只允许接收完全虚构数据，或另行完成最终字节与用途审批的投影。
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
发起网络。请求复用同一投影、Prompt、模型输出合同和本地来源绑定，沿用百炼
官方 HTTPS host、Authorization header、禁 proxy/redirect、有界响应、严格
JSON、`enable_thinking=false`、`temperature=0` 与最多两次尝试。

该门禁只证明调用方显式批准当前外发用途，不把投影自动变成脱敏数据。外网开发
仅使用独立构造的完全虚构树；真实树、真实节点名称、专家文本或生产模型流量
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
| 百炼缺少显式外发批准 | `EXTERNAL_DATA_APPROVAL_REQUIRED`，网络前失败 |
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

## 5. Good / Base / Bad Cases

- Good：完整或明确截断的虚构树投影产生待人工审核场景；引用全部可回映，草案
  保持非 Gold、非 Patch。
- Base：证据不足时返回 `NEED_EVIDENCE`、零场景和至少一个 evidence gap。
- Bad：直接发送 profile `to_dict()`、隐藏遗漏节点、把场景当 oracle、让外部百炼
  调用真实节点 name、或把模型输出直接注册进验证数据集。

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
`BailianTreeUnderstandingProvider` 并传入 `external_data_approved=True`；这不
授权真实树外发。

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
