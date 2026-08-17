# Navigation Copilot b03c C0 审核合同证明

## 状态

`C0_VERIFIED_AWAITING_C1_PHASE2A_APPROVAL`

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

C0 只证明审核合同能够识别已知伪造通过，不证明产品模型、召回或端到端效果。C1 未创建，
必须获得新的 Phase 2A 明确批准后才能开始。
