# Navigation Copilot b03c C0 审核合同证明

## 状态

`C2_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW`

用户已批准并完成 C1 Phase 2A。C0 中与洗衣房节点绑定的 absence、多目标穷尽性和澄清
收敛规则已提炼为参数化公共验证函数；C0 六份工件字节和既有结论保持不变。

## 目标

在完全虚构的共享洗衣房领域，用 41 节点、8 条场景证明三段式审核合同能够拒绝伪造通过：

1. authoring 只生成树、场景和 `PENDING` 审核包；
2. review 独立记录逐项审核决定，且绑定实际读取的冻结字节；
3. verification 只验证来源、摘要、完整性和语义约束，不补写审核结论。

基线拒绝合同提交为 `95678fe2a50f0eafc481ed1a5a2ab6d0125573af`。本任务只实施 C0，
不创建 C1 数据、模型调用、产品链路或正式资格分母。

## 数据边界

- `source_class=CLEANROOM_SYNTHETIC`
- `fictional=true`
- `derived_from_real=false`
- `gold_eligible=false`
- `patch_eligible=false`
- `VALUE` envelope 必须为 0。

## 固定身份

- dataset：`navigation-copilot-b03c-review-contract-proof`
- batch：`NAVCOP_B03C_REVIEW_PROOF_20260817_C0`
- domain：`FICTIONAL_SHARED_LAUNDRY_OPERATIONS`
- namespace：`urn:treeguard:fictional:navigation-copilot:b03c:review-proof:v1`
- seed：`2026081737`
- 规模：41 节点、8 场景。

## 覆盖与门禁

8 条正例分别覆盖唯一目标、非字面唯一目标、错误上下文、多可接受目标、合法澄清、弱证据、
真实空目标和上位主题可承接。后者必须被正确记录为非空目标；把它篡改为空目标属于负例。

必须实现并测试原规划中的 12 个阻塞负例，使用固定错误码：

- `DATASET_REVIEW_SOURCE_NOT_INDEPENDENT`
- `DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED`
- `DATASET_NONDETERMINISTIC`
- `DATASET_ABSENCE_CLOSURE_INCOMPLETE`
- `DATASET_ORACLE_OVERCLAIM`
- `DATASET_SCENARIO_COVERAGE_DUPLICATE`
- `DATASET_TARGET_SET_NOT_EXHAUSTIVE`
- `DATASET_CLARIFICATION_CONTRAST_INSUFFICIENT`

## 文件范围

只允许新增当前任务目录、三个 `scripts/navigation_copilot_b03c/` 专属模块、一个聚焦测试和
`tests/fixtures/fictional/navigation_copilot_b03c_review_contract_proof/`。不得修改 Batch A/B，
不得创建 C1 路径。

## 验收

- 41 节点、8 场景、0 `VALUE`；
- 8/8 正例通过；
- 12/12 负例以精确错误码拒绝；
- 两次 authoring 重建逐字节一致；
- 审核绑定 tree/scenario 原始字节 SHA-256；
- 只运行三个专属入口、聚焦测试、当前 Trellis validate 与 `git diff --check`；
- 不运行完整测试、模型、Provider、Retrieval、Semantic、Policy 或产品链路；
- 不 stage、commit、push 或 merge，除非再次获得明确批准。

## 实施结果

- authoring：41 节点、8 场景、全部 `PENDING`，两次重建逐字节一致；
- Codex Silver：8/8 接受，41/41 节点完成审核，固定 3 条复核，双审 0，记录耗时 20 分钟；
- verification：8/8 正例通过，12/12 篡改负例按预期固定错误码拒绝；
- `tree.v1.json` SHA-256：`dc256ad590159e23564f9166fae46f1053757a00fdf2d5751fc1d7ab67fef12d`；
- `scenarios.v1.json` SHA-256：`7d3f502f08f115c0cf41fa7460766a46564b925b2eaf6fa9aeb3ec041c4cc75d`；
- `review-packet.v1.json` SHA-256：`9cd5904eb6f451599cf13344e9f6796e0548c67f84d78892cf482aad40a51f06`；
- `review-input.silver.v1.json` SHA-256：`c906112c70691e0347b058aaa591b34740d5c38cbe528370cc99272f344d8b93`；
- `review-decisions.v1.json` SHA-256：`a984c55f535bd523df1544d82b9385af985ed96de4b6c397fea407bad5c161fe`；
- `verification-report.v1.json` SHA-256：`7b579252b8ce74851974452f77078e54b7c7c7489bbcad3179ca64ea0610cab5`。

C0 只证明审核合同能够识别已知伪造通过，不证明产品模型、召回或端到端效果；其结论仅作为
C1 Phase 2A 的审核合同前置条件。

## C1 Phase 2A

### 合同调整

公开 `navigation-copilot-sealed-scenario.v2` 要求 `proposed_parent_ref` 使用 `N######`。
因此原规划中的 `b03cn-` 仅保留为 blueprint 语义引用前缀，树稳定节点身份冻结为
`N500001`—`N500736`，避免再次形成执行合同不兼容批次。

### 数据身份与范围

- dataset：`navigation-copilot-sealed-v3c-b03-maker-lab-c`
- batch：`NAVCOP_SEALED_V3C_B03_20260817_C`
- domain：`FICTIONAL_MAKER_LAB_OPERATIONS`
- function commit：`40098afe985dfc81183c928a473a2e8a3c2176dc`
- 角色：`SEMANTIC_CHALLENGE`
- 节点：736，含 curated 160、background 456、filler 120；`VALUE=0`
- 候选：56；Codex Silver 接受 56；确定性冻结 48
- 最终类别：`10/10/8/4/6/4/6`
- 目标存在/空目标：42/6；错误上下文：8；重复子集：16
- 审核：160 个 curated 全审，加每分支 3 background 和 1 filler，共 192 节点；
  56 条 Scenario 全审、固定复核 8、双审 0、记录耗时 180 分钟。

### 三段来源与复用

1. `author_sealed_data.py` 只产生 blueprint、树、56 条候选和全 `PENDING` review packet；
2. `record_sealed_reviews.py` 不导入 authoring 模块，以固定原始字节 SHA-256 记录 Silver；
3. `verify_sealed_phase2a.py` 不导入 review 模块，复用 C0 参数化 absence、多目标和澄清门禁，
   只产生 48 条 Scenario 与聚合 preflight。

Phase 2A 没有生成 Oracle、execution manifest、模型请求、模型响应或产品结果。隐藏审核决定
不得进入后续被测模型输入。

### 工件摘要

- `blueprint.v1.json`：`72d8778d26ec2c2317d14c38a1843f014651e0cbd10aa0d0bc4ded729b01792d`
- `tree.json`：`0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd`
- `candidate-scenarios.v2.json`：`122fd83fab7856b37928288c7f086a6350812946dd05540d9c8ea9fafb7e8dda`
- `review-packet.v1.json`：`acea6d6636036d6e21deaa07a1679e341767acab707f13d02bfc26dcf285239b`
- `review-decisions.hidden.v1.json`：`3e6ed29cf499dc5207cfd8d79fee5584b75140bb9e1ac0416254e37f4a56bd7e`
- `scenarios.v2.json`：`5277c698b6eac2ed21b1249f99b681bcde6daec9c2a5bdbead2621d99dac637f`
- `phase2a-preflight.v1.json`：`76154abe2999ea030936e9989462f7c30b6e4af72d135ec120008a74d985ab25`

### 审核结论与停线

- 首次审核在写决定前发现“项目完成条件”缺少独立 curated 目标，回退蓝图后整批重建；
- L2/L3 发现“这台机器什么时候再保养”不唯一，收紧为“激光切割机什么时候再保养”并重新
  生成候选、审核与冻结结果；
- 最终节点标签 736/736 唯一，41 个非叶节点的精确 child label vector 最大重复组为 1；
- background pairwise 组合密度均低于 35%；没有 filler 成为目标；
- 目前无 blocking finding，状态停在 data-commit 审阅门。

不得自动进入 Phase 2B。Oracle、freeze report、data commit 后物化、execution manifest、模型
或产品链路都需要后续独立批准。

## C1 执行前拒绝

C1 的 Phase 2A 数据提交为 `70675601e3d53649bee440935199f4cf9fbf3ff0`，但在首次 Phase 2B
适配检查中发现批次级阻塞合同冲突，因此不得生成 Oracle、execution manifest 或进入模型实验：

- 4/4 条冻结 `WEAK_EVIDENCE` Scenario 的 Silver 决定均记录非空 `evidence_gap`，且
  `reviewed_target_ids` 与 `compatible_target_ids` 均为空；
- 公开 `navigation-copilot-sealed-oracle.v2` 强制 `WEAK_EVIDENCE` 为
  `TARGET_PRESENT`，并要求恰好一个 `acceptable_node_id`；
- 在没有受审目标的情况下补写唯一节点会构成 `DATASET_ORACLE_OVERCLAIM` 和事后拟合。

C1 状态固定为 `REJECTED_PREEXECUTION_ORACLE_CONTRACT_MISMATCH`。已提交工件只作为拒绝证据
保留，不得改写、删除、作为执行分母或被测模型输入。该拒绝不否定树本身、其余 Scenario
覆盖或 C0 审核合同，只否定 C1 作为完整 sealed evaluation batch 的资格。

## C2 Dataset Charter

### 身份与目的

- dataset：继续使用 `navigation-copilot-sealed-v3c-b03-maker-lab-c`；
- batch：`NAVCOP_SEALED_V3C_B03_20260817_C2`；
- Scenario 引用前缀：`b03c2:`；
- selection algorithm：`treeguard.navigation-copilot-b03c2-slot-selection.v1`；
- function commit：`40098afe985dfc81183c928a473a2e8a3c2176dc`；
- 主角色：`SEMANTIC_CHALLENGE`；
- 来源固定为 `CLEANROOM_SYNTHETIC / fictional=true / derived_from_real=false`；
- `gold_eligible=false / patch_eligible=false`。

C2 只修复 Scenario—Oracle 可执行性，不修改产品 Oracle v2 合同。C1 树未进入模型实验且
树审查本身无 finding，因此 C2 精确复用提交 `7067560` 中的 `tree.json` 原始字节及其
736 节点、0 `VALUE`、curated/background/filler=`160/456/120` 结构。C2 不生成新树、
不修改稳定节点身份，也不把 C1 Scenario 或审核状态原样晋升为新批次。

### 覆盖与弱证据修复

C2 重新建立 56 条候选并确定性冻结 48 条，类别配额仍为候选
`11/12/10/4/7/5/7`、执行集 `10/10/8/4/6/4/6`；最终仍包含 42 条目标存在、6 条
目标缺失、8 条错误上下文和 16 条重复子集。

全部 Scenario 使用新 `b03c2:` 引用并重新逐项审核。5 条候选 `WEAK_EVIDENCE` 必须同时满足：

1. 请求文本或获准 `proposed_parent_ref` 能唯一指向一个既有 curated 目标；
2. 证据缺口只发生在期望修改、关系、动作或所需字段上，不能发生在目标身份上；
3. Silver 决定中的 `reviewed_target_ids` 与 `compatible_target_ids` 必须各含恰好
   一个且相同的节点，并记录非空、客观、普通中文 `evidence_gap`；
4. Oracle v2 必须投影为 `TARGET_PRESENT / LIMIT / NEED_EVIDENCE /`
   `EXIT + null + PRESENT_NOT_FOUND`；
5. 任一审核者无法在不猜测的情况下唯一绑定目标时，整批以
   `DATASET_WEAK_EVIDENCE_TARGET_UNBOUND` 停线，禁止用随机节点、父节点或事后结果补位。

### 审核预算

- 56 条候选 Scenario 全量重新审核；
- 5 条弱证据候选全部列为高风险；
- 固定 seed 复核 8 条，其中至少包含最终 4 条弱证据；
- 双审上限为 0，不声称专家共识或 Gold；
- C1 树审查只有在 `tree.json` 原始 SHA-256 与提交 `7067560` 完全一致时才能复用；
- 新增审核预算上限 360 分钟，超过即 `DATASET_REVIEW_BUDGET_EXCEEDED` 停线。

## C2 两阶段实施门

### Phase 2A：Scenario-only

需要新的明确实施批准后才能开始。允许：

- 建立 C2 专属 authoring、review recorder、Phase 2A verifier 和聚焦测试；
- 只读复算 C1 已提交树的原始字节 SHA-256，并复制相同字节到 C2 专属 fixture；
- 生成 56 条新引用候选、全 `PENDING` 审核包、Silver 决定、48 条最终 Scenario 和
  Scenario-only preflight；
- 证明树字节复用、选择不读取 Oracle、弱证据目标唯一、全部 C0 参数化门禁仍成立。

Phase 2A 必须确认 Oracle、freeze report、execution manifest、模型请求/响应和产品结果均不存在，
然后停止在新的 data-commit 审阅门。规划批准不等于 Phase 2A 实施批准。

### Phase 2B：Oracle 与最终冻结

只有 C2 Phase 2A data commit 完成且再次获得独立批准后才能开始。Oracle 必须由独立模块读取
已提交的树、Scenario 和 Silver 决定，严格构造 `navigation-copilot-sealed-oracle.v2`：

- `LITERAL_UNIQUE / NONLITERAL_UNIQUE / STRUCTURAL_INTERFERENCE / MULTI_ACCEPTABLE`
  使用受审兼容目标，route=`PROCEED`，policy=`CANDIDATES_AVAILABLE`；
- `CLARIFICATION` 使用受审 resolved target，route=`CLARIFY`，
  policy 精确为 runner 可达的 `NEED_EVIDENCE`；
- `WEAK_EVIDENCE` 使用受审唯一目标和上节固定 `LIMIT` 终态；
- `TARGET_ABSENT` 不携带目标，route=`PROCEED`，policy=`NONE`，终态为
  `REJECT_ALL + null + ABSENT`；
- `reviewed_bytes_digest` 必须绑定当前树原始字节、单条 Scenario 规范字节和对应 Silver
  决定规范字节；任一来源漂移即拒绝；
- Oracle 不得进入任何被测模型允许列表投影。

Phase 2B 生成隐藏 Oracle、聚合 freeze report 和精确摘要绑定后停止。execution manifest、
Provider、Retrieval、Semantic、Policy、产品链路与外部模型实验继续需要后续独立批准。

## C2 文件所有权与验收

计划新增独立路径，禁止覆盖 C1：

- `scripts/navigation_copilot_b03c_c2/` 下的 author、review、Phase 2A/2B verifier；
- `tests/test_navigation_copilot_b03c_c2_sealed_data.py`；
- `tests/fixtures/fictional/navigation_copilot_sealed_v3c_b03c_c2/`；
- 当前 Trellis 任务目录。

不得修改 `src/treeguard/`、`contracts/`、C0/C1 fixture、其他 sealed batch、Provider、runner
或产品入口。实施阶段只允许运行 C0/C1 公共合同测试、C2 聚焦测试、当前任务 validate、
Python/JSON 语法检查和 `git diff --check`；不得运行会读取其他 sealed fixture 的递归或完整测试。

验收至少覆盖：

- C1 拒绝状态和 7 项已提交工件字节保持不变；
- C2 树与 C1 `tree.json` 原始字节一致，且 736 节点、0 `VALUE`；
- 56/48 配额、42/6、8、16 精确；
- 5/5 弱证据候选具备唯一受审目标和非空证据缺口；
- 48/48 Scenario 与后续 48/48 Oracle 可由公开合同严格回读；
- 任一空弱证据目标、Oracle 泄漏、来源摘要漂移、配额漂移或 C1 改写均 fail closed；
- 无 blocking finding，`gold_eligible=false`，且结论不能外推为生产准确率。

## C2 Phase 2A 实施结果

用户已明确批准 C2 Phase 2A。当前实现保持 C1 七项拒绝证据字节不变，并在独立 C2 路径完成：

- author：强绑定 C1 提交 `7067560` 的 blueprint、tree 与候选摘要；只复用 `tree.json`
  原始字节，全部 56 条 Scenario 使用新 `b03c2:` 引用并重算合同 hash；
- review：51 条未变语义逐项重新绑定，5 条弱证据逐项重写和复核；56/56 为
  `CODEX_SILVER_REVIEWED`，双审 0，不声明 Gold 或专家共识；
- verifier：复用 C0 参数化门禁，验证 C1 canary、C2 来源摘要、弱证据唯一目标、配额、
  选择、泄漏隔离和确定性，冻结 48 条 Scenario；
- 全部 5 条弱证据候选均有一个唯一受审目标和非空客观证据缺口，最终执行集包含其中 4 条；
- Oracle、freeze report、execution manifest、模型请求/响应和产品结果均不存在。

冻结聚合：

- 节点：736，`VALUE=0`，curated/background/filler=`160/456/120`；
- 候选/接受/执行：`56/56/48`；
- 最终类别：`10/10/8/4/6/4/6`；
- 目标存在/缺失：`42/6`；错误上下文：8；重复子集：16；
- 新增审核耗时：240 分钟；固定复核：8，其中最终 4 条弱证据全部覆盖；
- 状态：`C2_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW`。

工件 SHA-256：

- `blueprint.v1.json`：`dabee24cf311675b0bd184f492852797c629f161242c6c32c2cec6d48ba7074a`；
- `tree.json`：`0d6edf17accb680464343ae3e27943143049211cdb8d19df6998c9247bc7f3bd`；
- `candidate-scenarios.v2.json`：`1437568f07ea6c6a01a4d25a9c103f40718e37b3a505e6404dceaabb71c1c34e`；
- `review-packet.v1.json`：`ef1ce849444b1a9cee93c60f6a8567b15a002325ca0b79eb43a1a8f08215ac45`；
- `review-decisions.hidden.v1.json`：`a34ca039ed74bae98dc166f6742b4cac7e3f82a212755648efd160ac09eb71d1`；
- `scenarios.v2.json`：`3b52502c145e065c24418c3688e1019ee2637839279fb2ccd75d61fe9b3ef513`；
- `phase2a-preflight.v1.json`：`adc8371d27bd6eb0d3e82c3b8fba804cfcafa40f433a27237734958f09d1ccc2`。

验证结果：三个专属入口首次与重复运行均通过；C0 公共合同 + C2 聚焦测试 15/15 通过；
7 个 JSON 工件全部可解析；当前 Trellis task validate 与 `git diff --check` 通过。按照隔离合同，
未运行会读取其他 sealed fixture 的递归或完整测试。

当前停止在 data-commit 人工审阅门。未经新批准，不得 stage、commit、进入 Phase 2B、生成
Oracle/freeze report/execution manifest、调用模型、push 或 merge。
