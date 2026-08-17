# Navigation Copilot b03c C0 审核合同证明

## 状态

`C1_PHASE2A_FROZEN_AWAITING_DATA_COMMIT_REVIEW`

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
