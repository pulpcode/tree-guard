# Navigation Copilot b03 clean-room 密封资格数据

## 1. 状态与人工启动门

- Trellis 任务状态保持 `in_progress`，当前明确回到规划门。
- 规划状态：`BATCH_C_REDESIGN_PLANNED_AWAITING_C0_IMPLEMENTATION_APPROVAL`。
- Batch A 工件状态：`REJECTED_PHASE2A_SEMANTIC_DESIGN_INVALID`；不得晋升、修补、
  覆盖、删除或作为 Batch B 输入复用。
- Batch B 工件状态：`REJECTED_PHASE2A_REVIEW_GATE_AND_SEMANTIC_INVALID`；Phase 2B 永久
  关闭，不得补写 Oracle、Silver sidecar、freeze report 或 execution manifest，也不得
  原地替换 final Scenario、目标计划或审核结论后继续。
- Batch B 的现有蓝图、树、56 条候选、48 条最终 Scenario、构建器、测试和 ignored
  staging 全部转为拒绝证据保护集；不得删除、覆盖、移动、改写、导入或作为下一批输入。
- Batch C 的候选 Charter、namespace、seed、文件白名单和阶段门已写入本 Plan，但尚未获得
  实施授权，也尚未创建独立 worktree/执行主体。本轮只冻结两级开发 Plan；创建新 worktree、
  实施 C0、开始完整数据 Phase 2A 或任何数据生成都必须另行取得用户明确批准。

### 1.1 Batch A 拒绝记录

Batch A 已由人工审核拒绝，状态固定为
`REJECTED_PHASE2A_SEMANTIC_DESIGN_INVALID`。以下均为 blocking finding，不能通过
补写 Oracle、修改同批 Scenario、替换同 slot 候选或放宽门禁消除：

| finding code | 范围 | 拒绝理由 |
|---|---:|---|
| `DATASET_ORACLE_OVERCLAIM` | 6 条 `TARGET_ABSENT` | 请求直接声明树中没有目标，把应由树观察得到的答案写进请求。 |
| `DATASET_SCENARIO_COVERAGE_DUPLICATE` | 至少 1 个批次级挑战簇 | abbreviation 与 minor_typo 请求同时给出标准词、全称或纠错说明，未形成真实非字面判断。 |
| `SEMANTIC_HIERARCHY_UNNATURAL` | 至少 1 个批次级层级簇 | 多个语义上应为兄弟的主题被挂成父子关系；Batch A 不再逐项返修。 |
| `DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED` | 56/56 条自述审核记录 | 自然语言门禁依赖与场景同源的 `plain_language_reviewed=true`，不能替代独立检查和逐项审核证据。 |

除 `DATASET_ORACLE_OVERCLAIM=6` 与 `56/56` 条不可信自述记录外，不在本轮重读 Batch A
内容以追补逐项计数；批次级 blocking 已足以拒绝整批。Batch A 既有主要字节摘要仅作为
保留 canary：

- blueprint：`a64cb81e19bd6f3f3c19b36d6e8945c14914a1a9ee33ae61ae121098df73c2dd`
- tree：`7d8a477e7d12a9716d33d3cc2e8eb5e22a0ff72d3a8e490d0a5a022b6ba75dd2`
- 56 条候选集合：`ba8ea773d7923a0f228e9932f42a698b418c7ffe0d2092b2c2fd54e757ca8af5`
- 最终 48 条 Scenario：`752162cbebebd0cd7457b4b9d00c9439bcd4678b538dd9743c8b1b4d34f6f214`

### 1.2 Batch B 拒绝记录

Batch B 已在 Phase 2A 审核门由独立 Codex 审阅拒绝，状态固定为
`REJECTED_PHASE2A_REVIEW_GATE_AND_SEMANTIC_INVALID`。审阅只读取 Batch B 的公开虚构树、
56 条候选、48 条最终 Scenario、Phase 2A 审核工件和构建/测试实现；未创建或读取 Oracle，
未调用模型或产品链路。以下均为 blocking finding：

| finding code | 范围 | 拒绝理由 |
|---|---:|---|
| `DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED` | 56 条 Scenario 与 193 条层级关系 | 所谓人工审核结论与 Scenario 同置于构建器；Scenario 审核只校验预填 `ACCEPT`、字段长度和引用存在，层级 `manual_decision` 由确定性格式检查直接生成，不能证明发生了独立语义判断。 |
| `DATASET_ORACLE_OVERCLAIM` | `MULTI_ACCEPTABLE-02` | “日常检查”计划只绑定两个目标，但完整树中还有多个普通中文上同样合理的检查主题；现有审核没有给出可观察的排除依据，目标集合不具备穷尽性。 |
| `DATASET_SCENARIO_COVERAGE_DUPLICATE` | `CLARIFICATION-03` | “活动登记”在当前树内只有一个主要可操作主题，现有材料没有登记至少两个澄清前仍合理的对照目标，不能证明必须澄清。 |
| `DATASET_ORACLE_OVERCLAIM` | `TARGET_ABSENT` 门禁 | absence 检查只拒绝规范化完整标签精确命中，没有实现 PRD 已冻结的普通中文 alias 闭集、上位主题可满足性或语义覆盖检查；因此不能证明全部空目标均真正缺失。 |

聚焦测试 `5/5`、scenario-only preflight 和摘要重放通过，只证明当前实现检查到的格式、
计数、哈希与门槛一致；不能覆盖上述未实现的语义合同，也不能推翻 blocking finding。
根据“选中项后来失败则整批作废、不得热替换”以及随机复查停线规则，Batch B 不得进入
Phase 2B。

Batch B 主要冻结字节仅作为拒绝保护 canary：

- blueprint：`e66e55afc9a1b4ff39398cd5ba2c4e7bd3801900c1554fe3b688067c5d844645`
- tree：`4e1c45f3ba170d445d68b59d09e62c9ae793a15e4a35be4caecc3e47934203e2`
- 56 条候选集合：`abb0bfd89dd5719f6f43f3f26629528d4c01e9b6a2ae9b70f928a8aa84f7598d`
- 最终 48 条 Scenario：`7129881c8c24611586a5c428d1682ebb7a746a838c0723ea80db479ed4c1cdaf`

### 1.3 下一批必须先冻结的审核合同

下一批不得复制 Batch B 后只改文本。任何新 Charter 获批前，必须先把以下要求写成可执行
合同和负例测试设计：

1. Scenario、层级理由和审核结论必须是三个独立来源。构建器不得内置或生成
   `ACCEPT/REJECT`、`manual_decision` 或人工审核说明；审核文件初始只能是 `PENDING`，
   由读取冻结 Scenario 与树的独立审核步骤逐项写入，之后由 preflight 只读校验并绑定原始
   字节摘要。构建器自己的布尔、枚举或模板文本没有审核权威。
2. Scenario 人工清单必须逐项说明为什么当前证据足以支持其类别。通用套话、只复述类别名、
   只证明引用存在或所有项使用同一理由时，固定返回
   `DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED`。
3. 层级审核必须由独立清单判断父节点普通中文范围是否真实包含每个 child；确定性代码只
   校验闭集、类型、长度和绑定，不得根据这些检查自动写 `manual_decision=ACCEPT`。
4. `TARGET_ABSENT` 必须在 Scenario 编写前冻结普通中文 canonical label、alias、常见简称、
   上下位主题和可满足性闭集。检查同时覆盖规范化精确命中、alias 命中和已有上位主题能否
   合理承接请求；只要现有节点可能满足，就不能标为空目标，必须改为澄清、弱证据或目标
   存在场景。
5. `MULTI_ACCEPTABLE` 必须对全部 targetable curated 节点执行穷尽性候选枚举。人工审核要
   对每个纳入和排除项记录普通中文谓词依据；删除一个应接受目标、加入一个不满足目标或
   新增另一个满足谓词的节点时，负例测试必须失败。
6. `CLARIFICATION` 在冻结回答前必须登记至少两个结构兼容且语义合理的对照目标；冻结回答
   后必须精确收敛到一个目标。初始文本只有一个合理目标、或对照项只靠 ID/随机错误上下文
   形成时，记录 `DATASET_SCENARIO_COVERAGE_DUPLICATE`。
7. 聚焦测试必须增加审核决定篡改、模板化审核文本、错误/多余证据引用、alias 命中、上位
   主题可满足、空目标假阴性、多目标漏项/多项和伪澄清等负例；只断言聚合计数为零不再构成
   充分验收。

下一批必须使用新的 batch、dataset ref、domain、namespace、tree seed、selection seed、
稳定 ID 前缀、scenario 前缀、独立 worktree/执行主体和文件路径。Batch A/B 的任何数据、
构建器、审核文本、目标计划和逐项结果均不得作为模板或输入。

### 1.4 Batch C 两级开发 Plan

Batch C 不再直接生成数百节点正式分母。它先用独立的小型合同证明集验证审核系统能拒绝
伪造通过，再构建正式密封数据。两个阶段共享公开产品合同，但使用不同虚构领域、dataset、
namespace、seed、fixture 和评分用途；C0 的节点、文本、目标和审核结果不得进入 C1。

#### 1.4.1 Git、worktree 与启动门

- 当前 worktree 只保留 Batch A/B 拒绝证据和本 Plan，不承担 Batch C 实施。
- 必须先把本 PRD、task.json 以及经批准的 Batch A/B 保护集作为一个独立数据拒绝提交完成
  审阅；该提交记为 `rejection_contract_commit`。当前未提交 HEAD
  `7d8bd6d06ae1a16c87dcb91cd45f7820173ed6fc` 不能作为 Batch C 实施基线。
- 获得用户新的明确批准后，才从 `rejection_contract_commit` 创建：
  - worktree：`/Users/lau/workspace/tree-flow-navigation-sealed-data-v3c-b03c`
  - branch：`codex/build-navigation-copilot-sealed-data-v3c-b03c`
  - Trellis task：`08-18-navigation-copilot-b03c-cleanroom-sealed-data`
- 新任务第一阶段只能复制本节的合同摘要和公开功能提交引用；不得打开、导入或复制 Batch
  A/B 的树、场景、构建器、审核文件或逐项结果。新执行主体在实施前必须用既有 canary
  做不解析内容的 SHA-256 核对。
- 当前批准门只涵盖 Plan。C0 实施、C1 Phase 2A、C1 Phase 2B、data commit、execution
  manifest、模型运行分别使用独立人工门，前一门通过不自动授权后一门。

#### 1.4.2 C0：审核合同证明集

```yaml
dataset_ref: navigation-copilot-b03c-review-contract-proof
primary_role: PRECISION_CONTRACT
domain_ref: FICTIONAL_SHARED_LAUNDRY_OPERATIONS
purpose: >-
  用一次可在短时间内全量审阅的小型虚构树，证明审核来源隔离、absence 可满足性、
  多目标穷尽性和合法澄清门禁能够拒绝已知伪造通过。
non_goals:
  - 不进入正式 48 条资格分母
  - 不用于 Prompt、模型或召回调参
  - 不创建 Gold、生产结论或 Patch 资格
source_class: CLEANROOM_SYNTHETIC
fictional: true
derived_from_real: false
gold_eligible: false
patch_eligible: false
batch_ref: NAVCOP_B03C_REVIEW_PROOF_20260817_C0
namespace: urn:treeguard:fictional:navigation-copilot:b03c:review-proof:v1
seed: 2026081737
target:
  nodes: 41
  scenarios: 8
  value_envelope_count: 0
review_budget:
  scenario_full_review: 8
  curated_node_full_review: ALL
  random_recheck: 3
  dual_review_limit: 0
  time_limit_minutes: 120
```

C0 的 8 条场景精确覆盖：唯一目标、非字面唯一目标、错误上下文、多可接受目标、合法澄清、
弱证据、真实空目标和“已有上位主题可满足、因此不得判空”的反例，各 1 条。C0 不追求规模、
自然语言多样性或产品效果，只验证审核合同。

C0 必须有三个物理分离且不可逆回写的来源：

1. `authoring`：普通中文树、Scenario 和只含 `PENDING` 的 review packet；不得包含目标答案、
   审核结论、finding 或 Oracle。
2. `review`：独立审核步骤只读取冻结 authoring 字节和完整可见树，逐项填写决定、证据、
   候选对照及固定 finding；不得修改 authoring。
3. `verification`：preflight 只读取并重建前两者，验证原始字节摘要、来源顺序、完整性和
   语义约束；不得生成、补全或改写 review 决定。

构建器、审核器和验证器必须分属三个模块。authoring 模块不得出现
`ACCEPT/REJECT/manual_decision`，审核器不得导入 authoring 私有常量，验证器不得把
字段存在、字数或引用存在自动解释为语义接受。审核工件必须绑定审核者实际读取的 tree 与
Scenario 原始字节 SHA-256；任一字节变化使审核失效并回到 `PENDING`。

C0 至少实现以下 12 个阻塞负例，且每个使用精确固定错误码：

| 负例 | 错误码 |
|---|---|
| authoring 预填 `ACCEPT` 或 finding | `DATASET_REVIEW_SOURCE_NOT_INDEPENDENT` |
| review 与 authoring 同一模块或读取未冻结字节 | `DATASET_REVIEW_SOURCE_NOT_INDEPENDENT` |
| verification 自动生成审核决定 | `DATASET_REVIEW_SOURCE_NOT_INDEPENDENT` |
| 审核文本为跨项通用套话 | `DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED` |
| 审核绑定的 tree/Scenario digest 漂移 | `DATASET_NONDETERMINISTIC` |
| 空目标命中 canonical label 或普通 alias | `DATASET_ABSENCE_CLOSURE_INCOMPLETE` |
| 已有上位主题能够合理承接却仍标为空目标 | `DATASET_ORACLE_OVERCLAIM` |
| abbreviation 展开到零个或多个节点 | `DATASET_SCENARIO_COVERAGE_DUPLICATE` |
| minor typo 存在零个或多个单编辑近邻 | `DATASET_SCENARIO_COVERAGE_DUPLICATE` |
| 多目标漏掉一个满足谓词的兼容节点 | `DATASET_TARGET_SET_NOT_EXHAUSTIVE` |
| 多目标加入一个不满足谓词的节点 | `DATASET_TARGET_SET_NOT_EXHAUSTIVE` |
| 澄清前少于两个合理对照，或回答后不能唯一收敛 | `DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT` |

C0 只有在 8 条正例全部通过、12 个负例全部以预期错误码拒绝、两次逐字节重建一致、审核
预算未超且独立 Codex 人工复查无 blocking finding 时，才可提请 C1 Phase 2A 批准。C0
失败最多修复 2 轮；第三次仍失败则结束 Batch C，不放宽门禁。

#### 1.4.3 C1：正式密封资格数据 Charter

```yaml
dataset_ref: navigation-copilot-sealed-v3c-b03-maker-lab-c
primary_role: SEMANTIC_CHALLENGE
domain_ref: FICTIONAL_MAKER_LAB_OPERATIONS
domain_statement: >-
  从零构造一个完全虚构的小型创作工坊运营图谱，使用普通中文表达项目登记、工位预约、
  工具借还、材料管理、设备维护、样件处理、安全检查和成果交接；不读取、改写或翻译
  Batch A/B、C0 或任何既有 fixture。
purpose: >-
  在未参与 Prompt 校准的新领域和新树上形成 48 条可独立审核的 Navigation Copilot
  密封资格分母。
non_goals:
  - 不证明真实行业或生产准确率
  - 不用于 Prompt、模型、召回或阈值调参
  - 不创建 Gold、生产结论或 Patch 资格
source_class: CLEANROOM_SYNTHETIC
fictional: true
derived_from_real: false
gold_eligible: false
patch_eligible: false
batch_ref: NAVCOP_SEALED_V3C_B03_20260817_C
namespace: urn:treeguard:fictional:navigation-copilot:b03:maker-lab:v1
tree_seed: 2026081743
selection_seed: 2026081789
stable_id_prefix: b03cn-
scenario_prefix: b03c:
target:
  nodes: 736
  top_level_branches: 8
  curated_core: 160
  blueprint_background: 456
  stress_only_filler: 120
  value_envelope_count: 0
  candidate_scenarios: 56
  execution_scenarios: 48
```

八个顶层分支的精确节点/角色配额为：

| 分支 | 总数 | curated | background | filler |
|---|---:|---:|---:|---:|
| 项目登记 | 81 | 18 | 50 | 13 |
| 工位预约 | 87 | 19 | 54 | 14 |
| 工具借还 | 92 | 20 | 57 | 15 |
| 材料管理 | 86 | 19 | 53 | 14 |
| 设备维护 | 96 | 21 | 59 | 16 |
| 样件处理 | 88 | 19 | 55 | 14 |
| 安全检查 | 101 | 22 | 62 | 17 |
| 成果交接 | 104 | 21 | 66 | 17 |
| 全树根 | 1 | 1 | 0 | 0 |
| **合计** | **736** | **160** | **456** | **120** |

C1 沿用公开 Scenario v2 / Oracle v2 / Evaluation Manifest v2 和功能合同提交
`40098afe985dfc81183c928a473a2e8a3c2176dc`，但不得复用 A/B/C0 的数据、场景、审核或
目标。候选/最终类别配额保持 11/12/10/4/7/5/7 与 10/10/8/4/6/4/6，以便与既有资格
聚合分母可比；这只冻结数量，不冻结任何语义内容。

C1 审核预算固定为：160 个 curated 全审、56 条 Scenario 全审、每分支 3 个 background
和 1 个 filler 边界样本共 32 个、最终 48 条 Oracle 全审、固定 seed 随机复查 8 条、
`dual_review_limit=0`、总时限 720 分钟、最多 2 轮修复。任一边界错误、一个 Oracle
越权严重错误、两个实质语义错误、同一错误跨两个覆盖簇、审核模板化或预算超限立即整批
停线。

对 `TARGET_ABSENT`、`MULTI_ACCEPTABLE` 和 `CLARIFICATION`，C1 必须复用 C0 已通过的
审核合同实现，不得在数据构建器中另写简化版本：

- absence closure 在 Scenario 前冻结 canonical/alias/abbreviation/typo/上位主题可满足性；
- 全树先按结构兼容性产生有界候选集合，人工审核所有兼容候选的纳入/排除依据；
- clarification 在回答前至少两个合理对照，回答后恰好一个；
- review packet、review decision 和 verification report 分别绑定并单向流动；
- Oracle 只能在 Phase 2B 创建，且不能回写或影响 Scenario、选择和审核结论。

#### 1.4.4 文件所有权与阶段顺序

C0 获批后，新 worktree 只允许新增：

- `.trellis/tasks/08-18-navigation-copilot-b03c-cleanroom-sealed-data/`
- `scripts/navigation_copilot_b03c/author_review_contract_proof.py`
- `scripts/navigation_copilot_b03c/record_review_contract_decisions.py`
- `scripts/navigation_copilot_b03c/verify_review_contract_proof.py`
- `tests/test_navigation_copilot_b03c_review_contract.py`
- `tests/fixtures/fictional/navigation_copilot_b03c_review_contract_proof/`
- ignored staging `artifacts/fictional-validation/navigation-copilot-b03c-review-proof/`

C0 阶段不得创建 C1 目录或实现 C1 builder。C0 通过并取得新的 C1 Phase 2A 批准后，才
允许新增：

- `scripts/navigation_copilot_b03c/author_sealed_data.py`
- `scripts/navigation_copilot_b03c/record_sealed_reviews.py`
- `scripts/navigation_copilot_b03c/verify_sealed_phase2a.py`
- `tests/test_navigation_copilot_b03c_sealed_data.py`
- `tests/fixtures/fictional/navigation_copilot_sealed_v3c_b03c/` 的 Phase 2A 公开工件
- ignored staging `artifacts/fictional-validation/navigation-copilot-b03c-20260817-c/`

C1 Phase 2A 只生成蓝图、树、56 条候选、独立 review packet/decision、最终 48 条 Scenario
和 scenario-only 报告，随后停止。新的 Phase 2B 批准后才可生成 Oracle、Silver 摘要和
tracked freeze report。data commit、fresh-checkout 私有物化、execution manifest 和产品
实验仍各自需要后续批准。

#### 1.4.5 验收命令规划

C0 实施只允许其三个专属入口、聚焦测试、当前 Trellis validate 和 `git diff --check`；
禁止完整/递归测试、模型、Provider、Retrieval、Semantic、Policy 和产品链路。C1 每一阶段
在获批 PRD 中另行冻结精确命令，不能从 C0 命令自动扩权。

本 Plan 的当前验收只包括：身份、规模、预算、文件所有权、双阶段人工门和失败回退规则
完整；没有创建新 worktree、C0/C1 数据、脚本、测试、Oracle 或执行工件；未 stage、commit、
push 或 merge。下一步必须先由用户批准“提交当前拒绝与 Plan，并创建 Batch C 新 worktree，
只实施 C0”，不能直接批准 C1 Phase 2A。

## 2. Batch B 历史合同（已终止，仅作拒绝证据）

本节至第 13 节保留 Batch B 获批时的 Charter、覆盖、文件和阶段合同，用于解释拒绝
结论及复核原始约束。其中所有“允许新增”“Phase 2A/2B 获批后执行”和晋升描述均已由
第 1.2 节撤销，不能作为当前或下一批的实施授权；冲突时以第 1 节状态和第 1.3 节下一批
前置合同为准。

### 2.1 基线、共享合同与隔离

- 数据 worktree：`/Users/lau/workspace/tree-flow-navigation-sealed-data-v3c-b03`。
- 数据分支：`codex/build-navigation-copilot-sealed-data-v3c-b03`。
- 数据规划基线：`7d8bd6d06ae1a16c87dcb91cd45f7820173ed6fc`。
- 功能合同固定绑定：`40098afe985dfc81183c928a473a2e8a3c2176dc`。
- 公开合同：Navigation Copilot sealed Scenario v2、Oracle v2、Evaluation Manifest
  v2，以及 `src/treeguard/navigation_copilot_sealed_validation.py` 在规划基线上的
  确定性合同。
- b03 数据提交不得生成 execution manifest；未来由功能会话集成已批准的数据提交，
  并把 `function_commit` 固定为上述功能合同提交。
- 禁止读取或执行 b01/b02 的树、蓝图、候选、Scenario、Oracle、Silver、preflight、
  manifest、runner 输出和实验结果；禁止读取 H1/H2、M4/M5、R2、青岚等既有语义
  数据、生成器和逐项结果；禁止读取 `/private/tmp` 既有实验工件；禁止完整或递归测试。
- 任一隔离违规使本 batch、namespace、seed 和执行主体立即作废，不能原地修复。

## 3. Dataset Charter

```yaml
dataset_ref: navigation-copilot-sealed-v3c-b03-civic-atrium-b
primary_role: SEMANTIC_CHALLENGE
purpose: >-
  在从未参与 Prompt v2 校准的全新虚构信息树上，验证公开的 Navigation Copilot
  密封资格确定性合同是否可形成独立、可审、可重建的 48 条执行分母。
non_goals:
  - 不证明真实领域正确性或生产准确率
  - 不创建 Gold，不恢复 b02 资格
  - 不调用模型、产品链路或真实资格实验
  - 不生成 execution manifest
  - 不修改产品源码、Prompt、Provider、Retrieval、Semantic、Policy 或 Workbench
source_class: CLEANROOM_SYNTHETIC
fictional: true
derived_from_real: false
quality_tier: SILVER
assessment_authority: CODEX_ASSISTED
gold_eligible: false
patch_eligible: false
domain_ref: FICTIONAL_CIVIC_ATRIUM_OPERATIONS
domain_statement: >-
  Batch B 从零设计“公共中庭协作图谱”，使用普通中文描述完全虚构的公共服务主题、
  流程、步骤和属性；不取材、不改写、不翻译 Batch A、真实数据或任何既有 fixture。
batch_ref: NAVCOP_SEALED_V3C_B03_20260817_B
namespace: urn:treeguard:fictional:navigation-copilot:b03:civic-atrium:v1
seed: 2026081719
selection_seed: 2026081761
target:
  nodes: 927
  value_envelope_count: 0
  candidate_scenarios: 56
  execution_scenarios: 48
```

限制：本数据只能证明公开测试合同；AI 生成或评审内容始终
`gold_eligible=false`，不能外推到真实领域或生产效果。

## 4. 节点规模、角色与稳定身份

精确节点数固定为 927，任何偏差停线。一个根节点加九个刻意不等宽的顶层分支；
下表数量包含各分支根，不包含全树根：

| 虚构分支族 | 总数 | curated core | approved background | stress-only filler |
|---|---:|---:|---:|---:|
| 访客接待 | 83 | 16 | 54 | 13 |
| 公共阅读 | 96 | 18 | 63 | 15 |
| 社区厨房 | 101 | 20 | 66 | 15 |
| 园艺养护 | 89 | 17 | 58 | 14 |
| 物品寄存 | 107 | 21 | 69 | 17 |
| 排练场地 | 94 | 18 | 61 | 15 |
| 维修工坊 | 116 | 22 | 75 | 19 |
| 安全值守 | 103 | 19 | 67 | 17 |
| 便民借用 | 137 | 24 | 90 | 23 |
| 全树根 | 1 | 1 | 0 | 0 |
| **合计** | **927** | **176** | **603** | **148** |

该表是 Batch B 从零冻结的配额，不是 Batch A 表的改名或逐行映射；节点总数、顶层分支数、
每个分支总数以及总体 curated/background/filler 配额均与 Batch A 不同。任何 Batch B
逻辑节点、父子关系或 family 都不得从 Batch A 复制、变换或重编号得到。

- `curated core` 承担目标、树内干扰项和精确合同锚点；逐项显式蓝图并全部人工审核。
- `approved blueprint background` 只能来自逐项列出的 subject/facet 允许表，不独立承担
  semantic Oracle。
- `stress-only filler` 只制造规模、深度和排序压力，不得成为目标、禁止目标、错误上下文、
  Scenario 证据或 Oracle 依据。
- 蓝图先为每个节点分配不可变 `logical_ref`；禁止从名称、位置、父节点序号或列表顺序
  推导身份。
- 稳定源 ID 规则固定为：
  `b03bn-` + `SHA-256(UTF-8(namespace + "\n" + logical_ref))` 的前 24 个小写十六进制字符。
  不加随机盐，不因重排或插入而改变；完整摘要重复或短 ID 碰撞立即停线。
- `logical_ref` 与稳定源 ID 一经首次冻结不得复用、改名或重新编号。
- Scenario 的 `N000000` 形式引用不是源 ID；它只能由当前产品的公开投影确定性产生并在
  Scenario 冻结前校验，数据脚本不得自创另一套映射。
- 树序列化使用规范排序和现有 `adapt_tree_document()`；相同蓝图、namespace 与 seed
  必须逐字节重建一致。

## 5. Semantic Blueprint 与属性所有权

- 整树 scope 为 `ENTITY_COLLECTION`：九个顶层分支描述虚构协作图谱中的不同对象族。
- 每个 curated 属性必须逐项声明 `attribute_owner_ref` 和以下三者之一：
  `ROOT_ENTITY`、`COLLECTION_ITEM`、`COLLECTION_AGGREGATE`。
- 成员级属性必须经过当前合同的复合列表容器：
  `PROPERTY + value_type=class + cardinality=MULTIPLE`；不得直接挂在集合概念下。
- 集合聚合属性必须显式标为 `COLLECTION_AGGREGATE`，名称和 Scenario 必须可观察到
  “总数、合计或统一规则”的聚合含义。
- 每个 curated 节点、候选目标、干扰项和错误上下文都要有唯一 `purpose_ref`；无法回答
  “该值属于谁、是一份还是每个成员一份”时蓝图失败。
- 每个 curated 节点必须显式声明 `semantic_level`、`entity_scope` 和到父节点的
  `relation_kind`。同一主体范围、同一语义层级且互不包含的主题必须挂在共同父节点下；
  不得为了增加深度把本应为兄弟的主题串成父子链。
- 每个 curated 非叶节点必须提供 `child_membership_rationales`，键集合与其直接子节点
  精确相等；每个值用一句无需世界观说明的普通中文分别回答“为什么这个子节点属于这个
  父节点”。一个理由不得覆盖多个 child，也不得使用“按设计如此”“相关内容”“子项”等
  循环或空泛表述。
- curated 父子关系只允许预注册的层级对：`branch→topic`、`topic→process`、
  `process→step`、主体节点到其属性，以及重复成员容器到成员属性。同级主题默认只能为
  兄弟；确需 `topic→subtopic` 时必须同时给出非空 `scope_delta`，说明子主题比父主题缩小
  的主体或功能范围，否则记录 `SEMANTIC_HIERARCHY_UNNATURAL`。
- 确定性门禁校验 relation matrix、semantic level、scope delta、理由键闭集、理由非空与
  理由重复；逐项人工清单再判断每句理由是否自然成立。机器结构通过不能替代人工语义确认。
- 语义内容由逐节点平铺蓝图明确给出。构建脚本只可校验闭集、分配稳定 ID、调用现有
  Adapter 并规范序列化；不得生成名称、语义、父子关系、Scenario 文本或 Oracle。

## 6. 覆盖蓝图与冻结分母

最终 48 条执行集精确满足：

| 类别 | 数量 |
|---|---:|
| `LITERAL_UNIQUE` | 10 |
| `NONLITERAL_UNIQUE` | 10 |
| `STRUCTURAL_INTERFERENCE` | 8 |
| `MULTI_ACCEPTABLE` | 4 |
| `CLARIFICATION` | 6 |
| `WEAK_EVIDENCE` | 4 |
| `TARGET_ABSENT` | 6 |

同时冻结：

- 目标存在 42，目标不存在 6；错误上下文 8；重复性子集 16。
- 重复性子集从 `NONLITERAL_UNIQUE`、`STRUCTURAL_INTERFERENCE`、
  `CLARIFICATION`、`WEAK_EVIDENCE` 各取 4 条。
- 错误上下文按 `LITERAL_UNIQUE=1`、`NONLITERAL_UNIQUE=2`、
  `STRUCTURAL_INTERFERENCE=4`、`CLARIFICATION=1` 分配；均引用树内存在但语义错误
  的公开父节点，且不与可接受目标重叠。
- 非字面 10 个最终 slot 精确覆盖 synonym、abbreviation、colloquial、minor_typo、
  cross_layer_expression 五类，各 2 条；每条只有一个主要非字面现象。
- 每个 `TARGET_ABSENT` slot 必须预注册一个与九个当前领域之一语义相近、但在完整树中
  确实缺失的普通需求，并注册至少两个同分支 curated 近邻干扰项。近邻必须共享主体、
  功能或属性类型中的至少一项，但不能满足请求；不得用完全无关领域制造显而易见的缺失。
- `TARGET_ABSENT` 请求文本不得出现“树中没有”“不存在”“找不到”“未收录”“缺少该
  目标”等答案提示或语义等价的自证句。缺失结论只能由完整树的可见标签、近邻干扰项和
  确定性 absence 检查得出；请求本身只陈述要完成的普通任务。
- abbreviation 与 minor_typo 的请求不得在同一请求内出现标准词、全称、括号释义、
  “即/也就是/简称/全称/误写/错别字/应为/写成”等纠错或展开说明。abbreviation 必须能
  由普通中文习惯及树内可见完整标签判断；minor_typo 必须由普通中文上下文及树内标签的
  单一近邻判断，不能依赖隐藏词典、Oracle 或世界观说明。
- 56 个候选的类别数量固定为 11/12/10/4/7/5/7，顺序对应上表七类。候选不足、类别
  不符或 slot 无合格项时整批停止，不跨类别借位、不补造。
- 每个 coverage cell 固定为：
  `category + primary_challenge + tree_branch + structural_profile + context_mode +
  expected_observable_state`。候选必须填一个预注册 slot，不能凭 Oracle 或模型结果改格。

## 7. 候选与最终 48 条的确定性选择

1. 先注册 48 个 final slot；其中八个 slot 各允许两个候选，其余 slot 各一个候选，
   因而候选总数精确为 56。
2. 双候选 slot 固定为：`LITERAL_UNIQUE-09`、`NONLITERAL_UNIQUE-01`、
   `NONLITERAL_UNIQUE-06`、`STRUCTURAL_INTERFERENCE-02`、
   `STRUCTURAL_INTERFERENCE-07`、`CLARIFICATION-04`、`WEAK_EVIDENCE-03`、
   `TARGET_ABSENT-05`。
3. `scenario_ref` 在写文本前按 `b03b:<category-code>:<slot:02d>:<variant:a|b>` 冻结。
   单候选 slot 只使用 variant `a`。
4. 56 条 Scenario 必须在任何 Oracle 之前独立显式编写、完成 scenario-only preflight，
   并冻结 `scenario_hash`。
5. 双候选 slot 选择键固定为
   `SHA-256(UTF-8(namespace + "\n" + selection_seed + "\n" + slot_ref + "\n" +
   scenario_ref + "\n" + scenario_hash))`；取小写摘要字典序最小者。单候选 slot 直接入选。
   算法版本固定为 `treeguard.navigation-copilot-b03-b-slot-selection.v1`。
6. 48 条最终输出按 `scenario_ref` 字典序规范排序；重复集合是其中预注册的 16 个 slot，
   同样按 `scenario_ref` 排序。
7. 选择只依赖已冻结 Scenario，不读取 Oracle、Silver 结论或产品结果。选中项后来若失败，
   batch 作废；不得用同 slot 的备用候选热替换。
8. 选择完成即结束 Phase 2A；此时 Oracle 文件、Oracle staging、Oracle 字段和 Silver
   结果必须全部不存在，并停下等待用户审核。
9. 只有新的 Phase 2B 明确批准后，才允许为最终 48 条写隐藏 Oracle。Oracle 不得反向
   改写请求文本、提示字段、frozen clarification answer、自然语言结论或 slot 标签。

## 8. Oracle 与审核设计

- Phase 2A 不得创建、草拟、预填或推导任何 Oracle 内容。
- 所有 Oracle 字段严格符合 v2 Schema 和公开 Python 合同；可接受/禁止节点属于冻结树、
  有序唯一且互不重叠。
- `CLARIFICATION`：`expected_route=CLARIFY`、
  `clarification_policy=CLARIFICATION_REQUIRED`、恰好一个可接受节点、非空冻结回答，
  `acceptable_policy_statuses` 精确为 `[NEED_EVIDENCE]`。
- `WEAK_EVIDENCE`：`expected_route=LIMIT`、目标存在、
  `acceptable_policy_statuses=[NEED_EVIDENCE]`，终态精确可达
  `EXIT / null / PRESENT_NOT_FOUND`。
- `TARGET_ABSENT`：`expected_route=PROCEED`、可接受和禁止节点集合都为空。
- `MULTI_ACCEPTABLE` 至少两个稳定目标；其他目标存在类别恰好一个稳定目标。
- 结构 profile、Policy 和终态只来自当前可观察确定性合同，不按期望模型答案反推。
- 隐藏 Oracle、目标、评分答案、Silver sidecar 不进入模型请求、公开 Scenario、未来
  execution manifest 或生成日志。
- Silver 审核覆盖全部 176 个 curated core、全部 56 个候选 Scenario、最终 48 个 Oracle，
  以及每个顶层分支 3 个 background 与 1 个 filler 边界样本（共 36）。所有可成为目标
  或干扰项的非叶蓝图必须逐项通过；若不在 curated core，自动视为蓝图分类错误并停线。
- 只有一名审核者，`dual_review_limit=0`；不得让同一人或同一模型模拟双审。

## 9. 语义签名、骨架签名和反批量门禁

语义签名固定为以下规范 tuple 的 canonical digest：

```text
(subject_scope, attribute_owner_class, intent_concept, target_role,
 node_kind, value_type, cardinality, tree_branch, lexical_motif,
 ambiguity_mode, evidence_mode, context_mode)
```

- 语义签名用于发现异常集中和重复 coverage，不以“全部唯一”为目标。curated core 与
  Scenario 都必须报告唯一组数、最大组、重复组分布和覆盖率；两个节点或 Scenario 共享
  签名本身不构成失败，只要其自然层级、逐项 purpose 和预注册 coverage cell 均成立。
- 任意候选不得只靠 ID、顺序、编号或同义改写与另一候选区分；相同预注册 coverage cell
  或没有独立挑战目的的重复仍记录 `DATASET_SCENARIO_COVERAGE_DUPLICATE`。签名统计不能
  代替逐项语义审核，也不能驱动节点类型或层级改写。
- 骨架签名有两级：直接 child vector 为
  `(node_kind,value_type,cardinality,ordered(edge_role,child_kind,child_value_type,
  child_cardinality))`；depth-2 signature 再递归加入每个 child 的直接 vector。
- curated 非叶节点中，直接 child vector 的最大重复组不得超过 4，depth-2 signature 的
  最大重复组不得超过 3；全部非 filler 非叶节点中，直接 child vector 的最大重复组不得
  超过 8。
- “重复骨架覆盖率”固定定义为：全部非 filler 非叶节点中，其直接 child vector 所在组
  大小至少为 2 的节点数，除以全部非 filler 非叶节点数。该比率必须 `<=0.40`，preflight
  同时输出精确分子、分母和 basis points；不设最低重复率，也不奖励人为制造唯一骨架。
- 任一直接或 depth-2 骨架签名不得跨超过 3 个顶层分支。九个顶层分支的 depth-2
  signature 多重集合不得完全相同；任意两分支的 Jaccard 相似度必须 `<0.70`。
- 自然父子语义和逐 child 从属理由优先于签名唯一性。禁止仅为降低重复率而改变父节点、
  改变 `node_kind` / `value_type` / `cardinality`，或增加无业务意义的中间层、空属性和
  排序扰动。
- preflight 必须先完成 relation matrix、semantic level、scope delta 和全部逐 child 从属
  理由的确定性校验与逐项审核，再计算语义/骨架重复指标；层级门禁失败时不得用后续较低
  重复率覆盖或抵消。
- 若自然层级与上述骨架门槛冲突，必须回到蓝图重新设计；若证据表明门槛不合理，只能修改
  PRD 并重新申请 Batch B Phase 2A 批准，不能在实施中放宽阈值或扭曲层级以过关。
- 出现编号兄弟、统一服务单元骨架、批量同义改写、重复 child vector 超阈、仅靠
  ID/顺序扰动的“多样性”时停线。

自然语言有效性门禁：

- 全部 56 条候选的 `requirement_text`、结构提示和澄清回答必须使用无需私有世界观、
  私有术语表或任务外说明即可理解的普通中文。一般中文读者只阅读请求和树内普通中文
  标签，就应能理解请求在问什么，以及关键限制条件是什么。
- “棱湾”“折光穹庭”等虚构专名只能标识对象或地点；专名本身不得承担目标与干扰项的
  唯一语义区别。把专名替换为“对象甲”“区域乙”等中性占位符后，普通中文描述的功能、
  属性、动作、层级或范围仍必须足以区分目标、可接受多目标、错误上下文和禁止干扰项。
- 自造简称、暗号、单位、岗位、流程名或世界观规则不得作为判别依据。`abbreviation`
  challenge 只能使用一般读者可理解的通用简称，并允许从树内可见普通中文完整标签取得
  证据；请求自身不得给出标准词或全称。`minor_typo` 只能由普通中文上下文和树内唯一近邻
  标签纠正；请求自身不得解释错字。
- `plain_language_reviewed`、`proper_noun_dependency` 或任何与 Scenario 同源的布尔/枚举
  自述一律视为无权威输入：构建器可以拒绝其存在，或读取后完全忽略；它们不能增加通过
  计数，也不能成为 finding 为零的证据。
- 独立确定性检查必须直接读取 Scenario 文本与树内可见标签，至少执行：中文字符与句式
  下限；未解释虚构专名/占位替换；`TARGET_ABSENT` 答案提示词及语义等价模式拒绝；
  abbreviation/minor_typo 标准词、全称、括号释义和纠错提示模式拒绝；缺失目标对规范化
  全树标签及预注册普通中文 alias 闭集的零命中；每条 absent 的同分支近邻数 `>=2`；
  abbreviation 对树内完整标签有唯一展开，minor_typo 对树内标签有唯一单编辑近邻。检查
  规则、alias 闭集和模式表必须在 Scenario 编写前冻结，不能从请求反向补录。
- Phase 2A 必须生成独立逐项人工审核清单，56 条每条记录：普通中文任务复述、树内可见
  证据引用、专名中性替换后是否仍可判断、是否泄漏答案、挑战是否真实、近邻是否构成干扰、
  `accept/reject` 结论和固定 finding code。清单不得复制场景自述值作为答案；任一字段缺失
  或任一 `reject` 都使整批停止。该清单是人工审核输入，不是 Oracle，也不得包含期望目标
  集或评分答案。
- scenario-only preflight 必须分别报告确定性检查与人工清单完整性；只有两者逐项 56/56
  通过才可报告自然语言门禁通过，且整个过程不得读取 Oracle。
- 固定 blocking finding code 为 `DATASET_REQUEST_PRIVATE_LEXICON_REQUIRED`。任一请求
  只能依靠未解释自造词、私有世界观或虚构专名才能判别时，立即记录该 code 并整批停线；
  不删除单条、不改换备用候选、不在同一 batch 临时补词表或补写解释。
- 固定 blocking finding code `DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED` 用于布尔自述
  被计入审核通过、逐项证据清单不完整或检查实现与 Scenario 共享未经验证的“已通过”来源；
  任一命中整批停线。
- `DATASET_ORACLE_OVERCLAIM` 同时覆盖 `TARGET_ABSENT` 请求泄漏缺失答案；
  `DATASET_SCENARIO_COVERAGE_DUPLICATE` 同时覆盖 abbreviation/minor_typo 因自带展开或
  纠错说明而退化为 literal challenge。

反笛卡尔积门禁：

- 蓝图必须平铺列出 927 个节点；脚本不得对两个或更多独立语义维度使用 `product()`、
  嵌套全展开循环或等价矩阵扩张。
- 每个 background family 必须有显式 `allowed_facets_by_subject` 和逐组合 `purpose_ref`。
- 当 subject 与 facet 各至少 3 个时，若实现了完整 `subjects × facets` 即失败；每个 family
  的实现密度必须 `<= 0.35`。密度只能用于拒绝，不能自动补齐组合。
- 构建前后节点数、family 数和每个允许组合计数必须精确一致；未注册组合、密度跃升或
  生成器推导语义均返回 blocking finding。

规划 finding 至少使用 pipeline contract 中的稳定 code：
`DATASET_CARTESIAN_DENSITY_HIGH`、`DATASET_REPEATED_VECTOR`、
`DATASET_COMBINATION_UNAPPROVED`、`DATASET_ATTRIBUTE_OWNER_AMBIGUOUS`、
`DATASET_ITEM_ATTRIBUTE_ON_COLLECTION`、`DATASET_SCENARIO_COVERAGE_DUPLICATE`、
`DATASET_ORACLE_OVERCLAIM`、`DATASET_REQUEST_PRIVATE_LEXICON_REQUIRED`、
`SEMANTIC_HIERARCHY_UNNATURAL`、`DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED`。

## 10. 人工预算、修复轮次与停线

```yaml
review_budget:
  candidate_limit: 56
  candidate_review_sessions: [20, 20, 16]
  candidate_independent_deterministic_checks: 56
  candidate_manual_semantic_reviews: 56
  curated_core_items: 176
  curated_nonleaf_child_membership_rationales: ALL_DIRECT_CHILD_EDGES
  background_and_filler_samples: 36
  oracle_items: 48
  deterministic_random_recheck: 8
  dual_review_limit: 0
  time_limit_minutes: 720
  max_regeneration_rounds: 3
```

随机复查从已审核项按
`SHA-256(namespace + selection_seed + stable_ref)` 最小的 8 项选择。任一项字节变化使其
后续审核失效。以下任一条件立即整批停线：

- 访问禁读材料、白名单外文件或网络/模型/产品链路；
- 来源分类、927 节点、`VALUE=0`、56/48 数量、类别、42 个目标存在、8 个错误上下文、
  16 个重复 slot 或非字面配额不符；
- 任一 Oracle/目标/review sidecar 泄漏到公开或模型工件；
- 属性所有者不唯一、成员属性越级、笛卡尔积、统一骨架或签名门禁失败；
- curated 父子层级不在允许矩阵、同级主题被串成父子、任一 curated 非叶节点缺少逐 child
  普通中文从属理由，或任一理由不能用一句普通中文自然成立；
- 任一请求需要未解释自造词、私有世界观、隐藏术语表或仅凭虚构专名才能区分目标与干扰项；
- 任一 `TARGET_ABSENT` 请求泄漏缺失答案、目标实际存在、没有至少两个合格树内近邻，或
  使用与当前领域明显无关的请求制造缺失；
- 任一 abbreviation/minor_typo 请求自带标准词、全称、括号释义或纠错说明；任一自然语言
  通过结论仅来自同源布尔自述，或 56 条独立人工清单有缺失/拒绝；
- Scenario 在 Oracle 后编写，或 Oracle 影响 Scenario；
- `CLARIFICATION` / `WEAK_EVIDENCE` Oracle 对当前两调用路径不可达；
- 随机复查出现 2 个实质语义错误、同一错误跨 2 个聚类、任一边界/Oracle 越权严重错误、
  审核不完整或超过 720 分钟；
- 同一阶段修复超过 3 轮、冻结字节漂移，或需要热修已冻结执行分母。

冻结后发现数据错误，本 batch 作废；新一轮必须使用新 batch、namespace、seed 和执行主体。

## 11. Batch A 保护集与 Batch B 文件白名单

本次 Batch A 拒绝/Batch B 回规轮次唯一允许修改：

- `.trellis/tasks/08-17-navigation-copilot-b03-cleanroom-sealed-data/prd.md`

以下 Batch A 路径全部转为拒绝证据保护集；未经用户另行批准不得读取语义内容、删除、覆盖、
改写、移动、导入或作为 Batch B 模板。只允许用既有摘要或流式 SHA-256/existence/stat
做不解析内容的保留 canary；Batch B 构建器和测试不得打开这些路径：

- `tests/navigation_copilot_b03_cleanroom_builder.py`
- `tests/test_navigation_copilot_b03_cleanroom_data.py`
- `tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v1/` 全目录
- 被 Git 忽略的 `artifacts/fictional-validation/navigation-copilot-b03-20260817-a/` 全目录

拒绝保护集保持当前 tracked/untracked/ignored 属性，不因 Git 不追踪而失去保留要求。
本轮只通过既有摘要、精确路径 `git status` 和禁止写 canary 核对隔离；不重新读取 Batch A
逐项内容。未来 Batch B Phase 2A 开始前后都要断言上述四个已知主要 SHA-256 未变化；
无法证明未变化时停线，不得“重建”Batch A 来恢复。

以下是 Batch B 当时的 Phase 2A 文件白名单，现已全部转为拒绝证据保护集：

- `tests/navigation_copilot_b03_cleanroom_batch_b_builder.py`
- `tests/test_navigation_copilot_b03_cleanroom_batch_b_data.py`
- `tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v2/blueprint.v1.json`
- `tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v2/tree.json`
- `tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v2/scenarios.v2.json`
- `tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v2/dataset-classification.v1.json`
- 被 Git 忽略的 `artifacts/fictional-validation/navigation-copilot-b03-20260817-b/`，仅存
  Batch B candidate、scenario-only preflight 聚合、独立确定性检查结果、允许列表 finding、
  逐项人工审核清单和 Phase 2A selection/checklist；不得包含 Oracle、Silver、原始 Prompt、
  模型请求/响应或 trace。

以下是从未获得批准、也不得再为 Batch B 创建的 Phase 2B 路径：

- `tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v2/oracle.v2.json`
- `tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v2/freeze-report.v1.json`
- Batch B ignored staging 中的 Silver 审核工作清单和 promotion checklist。

`dataset-classification.v1.json` 只记录来源、计数、seed、namespace、公开合同版本与摘要；
它不是且不得伪装成 Evaluation Manifest。任何其他 tracked/untracked 路径变化都停线。

`freeze-report.v1.json` 是 `DETERMINISTIC_REPORT`，必须 tracked，不能由 ignored staging
替代。Batch B 使用 `schema_version=navigation-copilot-b03-b-freeze-report.v1`，并至少精确记录：

- blueprint、tree、全部 56 条候选 Scenario 的规范集合、最终 48 条 Scenario、Oracle、
  Silver 审核摘要这六份冻结字节各自的完整文件 SHA-256；摘要按原始 UTF-8 文件字节计算，
  不能只记录内部对象 hash；
- 56 个候选的有序 `scenario_ref + scenario_hash`、48 个最终有序引用及每个双候选 slot
  的两个选择键，使候选集合和选择决定可在不读取 Oracle 的情况下复核；
- `selection_algorithm_version=treeguard.navigation-copilot-b03-b-slot-selection.v1`、namespace、
  selection seed、双候选 slot 清单和规范排序规则；
- 七类候选配额与最终配额、16 个有序重复子集引用、8 个有序错误上下文引用、目标存在/
  不存在计数，以及五类非字面现象各 2 条的最终映射；
- curated 父子理由的计划/实际边数与通过数、层级门禁顺序，以及直接/depth-2 最大重复组、
  重复骨架覆盖率分子/分母/basis points、跨分支最大数和 Jaccard 聚合；
- Scenario v2、Oracle v2、Evaluation Manifest v2、确定性 Python 合同版本、功能合同提交
  和数据规划基线；
- Silver 审核的计划/实际数量、accept/revise/reject 聚合、用时、自然语言门禁通过数、
  finding code 聚合、`dual_review_limit=0`、停线状态和对应审核摘要 SHA-256；不得包含
  自由文本、Oracle 内容、目标 ID、Prompt、模型请求/响应或 trace；
- 报告自身的 canonical SHA-256，且任一所绑定文件字节变化都使报告失效并整批停线。

即使 ignored staging 被清理，tracked freeze report 仍必须保留全部选择输入的引用/hash、
配额、审核聚合和六类字节绑定；ignored staging 不得成为唯一冻结证据。

## 12. 测试与命令白名单

当前回规轮次只允许：

```bash
python3 ./.trellis/scripts/task.py validate 08-17-navigation-copilot-b03-cleanroom-sealed-data
git diff --check
```

可执行只读的 `git status`、`git rev-parse HEAD` 和精确路径 diff 审阅。不得运行任何完整、
递归或会加载禁读材料的测试。

以下命令只记录 Batch B Phase 2A 审核时曾允许的聚焦验证；Batch B 拒绝后不再授权运行，
下一批必须在新 Charter 中重新定义命令白名单：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest tests.test_navigation_copilot_b03_cleanroom_batch_b_data -v
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B tests/navigation_copilot_b03_cleanroom_batch_b_builder.py --preflight
```

若命令入口与实际新脚本不一致，必须先回到规划并获得批准，不能临时扩大白名单。

## 13. Batch B 历史实施顺序与当前规划验收条件

### Batch B Phase 2A（历史，已完成后拒绝）

以下仅记录 Batch B Phase 2A 当时获批后的历史步骤，不得重新执行：

1. 不读取或复用 Batch A，从 Batch B Charter 显式编写逐节点蓝图，构建精确 927 节点树，
   并独立显式编写 56 条 Scenario。
2. 对全部 curated 非叶节点逐项填写每个 child 的普通中文从属理由；完成 relation matrix、
   semantic level、scope delta 与兄弟/父子层级门禁。
3. 断言 Batch B Oracle 文件、Oracle staging、Oracle 字段、Silver 结果和 freeze report
   不存在，并断言 Batch A 保护集未变化。
4. 构建到 Batch B 忽略 staging，运行专属 scenario-only preflight、引用/计数检查、语义
   签名、骨架、反笛卡尔积、TARGET_ABSENT 近邻/答案泄漏门禁、abbreviation/minor_typo
   退化门禁，以及直接读取文本和树标签的独立确定性检查。
5. 完成 56 条逐项人工审核清单；不得从 `plain_language_reviewed` 或其他同源自述导入通过
   结论。确定性检查与清单必须分别 56/56 通过。
6. 按第 7 节只使用已冻结 Scenario 确定性选择 48 条；失败不替换。
7. 核对 tracked 的 blueprint、tree、final Scenario 与 classification 工件，以及 ignored
   staging 中完整候选的聚合摘要；不得创建 Oracle 或完整 freeze report。
8. 立即停止，报告父子理由审核聚合、两级骨架最大重复组、重复骨架覆盖率精确分子/分母、
   跨分支最大数、56 条候选摘要、独立门禁与人工清单 findings、48 条选择、Batch A 保留
   canary 和 Git 状态，等待用户审核。

Phase 2A 完成不授权 Phase 2B，不授权 Oracle、Silver、完整冻结或 data commit。

### Batch B Phase 2B（永久关闭，未获批准）

以下是已撤销的历史 Phase 2B 计划；Batch B 已被拒绝，任何新的用户批准也不能恢复本段：

1. 在不得改动 Phase 2A 已冻结请求字节、slot、自然语言结论和选择结果的前提下，为 final
   48 编写隐藏 Oracle。
2. 执行第 8、10 节规定的 Codex Silver 与人工预算审核；任一修订请求都使当前 batch
   作废，不能回写 Phase 2A 字节继续。
3. 生成 tracked `freeze-report.v1.json`，绑定第 11 节规定的六类 SHA-256、选择算法、
   配额、重复/错误上下文、公开合同版本和审核聚合；重放并验证所有绑定。
4. 运行 b03 专属完整冻结 preflight 和逐字节重建；不生成 execution manifest，不调用
   产品链路或模型。
5. 停在 data-commit 人工审阅门；不得 stage、commit、push 或 merge。

当前拒绝记录与下一批前置合同验收：

- 独立 worktree/分支位于指定基线，HEAD 未移动；
- 当前 Trellis task 存在、session active、`status=in_progress`，并在 PRD 中明确处于
  `BATCH_C_REDESIGN_PLANNED_AWAITING_C0_IMPLEMENTATION_APPROVAL` 规划门；
- Batch A/B 均有最小拒绝理由、状态和主要字节 canary，Batch B Phase 2B 永久关闭；
- Batch C 必须先以 C0 实现独立审核来源、absence 语义覆盖、多目标穷尽性、合法澄清对照
  和篡改负例合同；C0 独立通过后才能申请 C1 Phase 2A 批准；
- 本轮仅 PRD 发生变化；Batch A/B 保护集保持原字节与原 Git 属性，没有创建 Batch C
  蓝图、树、候选、Scenario、Oracle、Silver、freeze report 或模型工件；
- Trellis validate 与 `git diff --check` 通过；Git 未 stage、commit、push 或 merge。
