# 新增需求意图、候选召回与语义推荐

## Scenario：文件型新增需求治理纵切

### 1. Scope / Trigger

当改动涉及 `IntentRequest`、`ChangeIntentDraft`、人工确认、候选评分、
`SemanticRecommendationDraft`、`RecommendationRecord` 或
`treeguard-governance` 或 `treeguard-governance-demo` 时使用本规范。该能力属于
Shadow MVP 临时范围：

- AI 可以起草意图，并在有界候选上给出一个受约束建议，但不确认、不审批、不生成
  Patch；
- 人工确认只授权候选检索，不构成语义批准；
- 候选缺失或信号不足不产生新增许可；
- 人工确认、修订或拒绝建议只形成运营反馈，不构成 Gold、语义批准或 Patch 资格；
- 完整工件只进入私有 sidecar，不修改生产树或数据库。

### 2. Signatures

```bash
treeguard-governance draft \
  <tree_file> <request_file> \
  (--model-output-file <file> | --live) \
  [--external-data-approved] \
  --internal-output <new_file>

treeguard-governance clarify \
  <tree_file> <request_file> <initial_draft_file> <answer_file> \
  (--model-output-file <file> | --live) \
  [--external-data-approved] \
  --internal-output <new_file>

treeguard-governance confirm \
  <tree_file> <request_file> <draft_file> <action_file> \
  --internal-output <new_file>

treeguard-governance search \
  <tree_file> <request_file> <draft_file> <action_file> \
  <confirmation_file> \
  [--max-candidates 20] \
  --internal-output <new_file>

treeguard-governance recommend \
  <tree_file> <request_file> <draft_file> <action_file> \
  <confirmation_file> <candidate_file> \
  (--model-output-file <file> | --live) \
  [--external-data-approved] \
  --internal-output <new_file>

treeguard-governance review-recommendation \
  <tree_file> <request_file> <draft_file> <action_file> \
  <confirmation_file> <candidate_file> \
  <recommendation_draft_file> <recommendation_action_file> \
  --internal-output <new_file>

treeguard-governance replay-recommendation \
  <tree_file> <request_file> <draft_file> <action_file> \
  <confirmation_file> <candidate_file> \
  <recommendation_draft_file> <recommendation_action_file> \
  <recommendation_record_file>

treeguard-governance-demo \
  --output-dir <new_directory> \
  --review-decision (confirm | reject) \
  [--mode (offline | bailian-live)] \
  [--external-data-approved]
```

`confirm` 及其所有下游命令的 `<draft_file>` 接受原始
`change-intent-draft.v1`，或已经过一次回答的
`intent-clarification-round.v1`。人工 action 的 `expected_draft_hash` 相应绑定
`draft_hash` 或 `round_hash`；不得把初始草稿和澄清轮次混用。

核心签名：

```python
IntentRequest.from_dict(payload, tree)
ChangeIntentDraft.from_model_dict(payload, request, tree, ...)
ChangeIntentDraft.from_dict(payload, request, tree)
IntentClarificationAnswer.from_dict(payload)
build_intent_clarification_model_input(request, initial_draft, answer, tree)
IntentClarificationRound.from_model_dict(
    payload, request, initial_draft, answer, tree, ...
)
IntentClarificationRound.from_dict(payload, request, tree)
reviewable_intent_draft_from_dict(payload, request, tree)
apply_intent_review(request, draft, action, tree)
IntentConfirmation.from_dict(payload, request, draft, action, tree)
build_candidate_set(confirmation, tree, max_candidates=20)
CandidateSet.from_dict(payload, confirmation, tree)
build_semantic_candidate_projection(confirmation, candidate_set, tree)
SemanticRecommendationDraft.from_model_dict(payload, projection, ...)
SemanticRecommendationDraft.from_dict(payload, confirmation, candidate_set, tree)
RecommendationReviewAction.from_dict(payload, confirmation, candidate_set, tree)
apply_recommendation_review(draft, action, confirmation, candidate_set, tree)
RecommendationRecord.from_dict(payload, draft, action, confirmation, candidate_set, tree)
```

### 3. Contracts

| 工件 | 合同 | 关键边界 |
|---|---|---|
| 需求 | `intent-request.v1` | 原文、可选拟挂载 ID、类型/基数提示 |
| 模型输出 | `change-intent-model-output.v1` | 不含 ID、状态、审批、动作或 Patch |
| 草稿 | `change-intent-draft.v1` | 绑定需求哈希、快照哈希和模型来源声明 |
| 澄清回答 | `intent-clarification-answer.v1` | 绑定初始草稿哈希、一次回答原文和未认证回答者声明 |
| 澄清模型输入 | `intent-clarification-model-input.v1` | 原需求、初始意图、唯一问题和回答的 48,000 字符允许列表投影 |
| 澄清轮次 | `intent-clarification-round.v1` | 内嵌并绑定初始草稿、回答、模型来源和修订意图；固定第一轮 |
| 人工 action | `intent-review-action.v1` | 绑定实际草稿哈希，可确认、修订或拒绝 |
| 确认 | `intent-confirmation.v1` | `semantic_approval=false`、`patch_eligible=false` |
| 候选集 | `candidate-set.v1` | 绑定确认/快照，`embedding_used=false`、`allows_addition=false` |
| 语义模型输入 | `semantic-recommendation-model-input.v1` | 可信 Top-20 的固定 Top-8 临时引用投影 |
| 语义模型输出 | `semantic-recommendation-model-output.v1` | 全候选逐项关系和一个选择性动作 |
| 建议草稿 | `semantic-recommendation-draft.v1` | 绑定确认、候选集、快照、投影和模型来源 |
| 人工建议 action | `recommendation-review-action.v1` | 绑定实际草稿，可确认、修订或拒绝 |
| 人工修订内容 | `semantic-recommendation-content.v1` | 与模型建议使用同一跨字段政策 |
| 建议记录 | `recommendation-record.v1` | 可信回放，固定为非 Gold、非审批、非 Patch |

模型投影只包含需求、提示和不带稳定 ID 的拟挂载节点视图。完整模型投影仍可能含
真实语义，外部百炼调用必须有 `--live --external-data-approved`。没有新增环境键；
复用 `BAILIAN_API_KEY`、`TREEGUARD_LLM_BASE_URL` 和 `TREEGUARD_LLM_MODEL`。

初始草稿只有在 `review_status=NEEDS_CLARIFICATION` 时才能进入 `clarify`。回答以
`expected_draft_hash` 绑定实际初始草稿；回答文本不得包含已知或常见伪造内部 ID。
澄清投影不会新增结构化稳定 ID 或哈希，但原始需求文本仍必须遵守外传审批边界。
澄清模型仍返回 `change-intent-model-output.v1` 的完整意图字段，本地
再构造 `IntentClarificationRound v1`。修订意图无追问时状态为
`READY_FOR_HUMAN_REVIEW`；仍有追问时状态固定为
`CLARIFICATION_LIMIT_REACHED`，不得再次自动澄清或确认进入检索。人工拒绝仍允许。
`treeguard.change-intent-clarification.zh.v2` Prompt 要求已经由回答明确解决的事实
不得同时保留为假设、证据缺口或再次追问；剩余追问只能选择一个原子问题，不能拼接
多个问题。这是模型质量约束，本地确定性门禁仍只依据合同字段和状态安全停止。
无澄清路径最多发生意图与语义建议两段顺序模型调用；单轮澄清路径最多三段。

第一版 `CandidateSet` 算法版本为
`treeguard.lexical-structural-retrieval.v1`。评分分项固定包含名称重叠、路径重叠、
主体覆盖、节点类型、值类型、基数和父位置关系；总分降序、`node_id` 升序打破
并列。拟挂载位置只 boost，不裁剪全树。

语义投影版本为 `treeguard.semantic-candidate-projection.v1`，只接受使用默认
Top-20 策略生成的 `CandidateSet`，并固定取前 8 个候选映射为 `C001`—`C008`。
投影不得包含稳定 ID、hash、VALUE 或未知字段，规范 JSON 总长不得超过 48,000
字符。关系仅允许
`SEMANTICALLY_EQUIVALENT`、`REUSES_CONTRACT`、`CONTEXTUALLY_RELATED`、
`NOT_EQUIVALENT`、`NEED_EVIDENCE`。

建议动作仅允许 `USE_EXISTING_NODE`、`ADD_NODE_FROM_CONTRACT`、
`ADD_CONTEXT_FIELD`、`NEED_CLARIFICATION`、`NEED_EVIDENCE`、`ABSTAIN`。前三个
动作必须选择候选，且关系依次匹配前三个关系。Shadow MVP 中
`ADD_CONTEXT_FIELD` 还要求确认意图有非空 `scenario` 和至少一项
`confirmed_facts`；该门槛是待效果验证的临时合同。`RecommendationRecord` 无论
人工决策为何都固定为 `OPERATIONAL_FEEDBACK_ONLY`、
`identity_status=UNVERIFIED_FILE_ASSERTION`、`semantic_approval=false`、
`patch_eligible=false`、`gold_eligible=false`。

### 4. Validation & Error Matrix

| 条件 | 稳定错误/状态 |
|---|---|
| 非 `resource` 树 | `INTENT_SOURCE_NOT_RESOURCE` / `CANDIDATE_SOURCE_NOT_RESOURCE` |
| 需求字段/版本非法 | `INTENT_REQUEST_FIELDS_INVALID` / `INTENT_REQUEST_VERSION_INVALID` |
| 拟挂载节点未知或 unsupported | `INTENT_PARENT_UNKNOWN` |
| 模型多字段、越权字段或非法版本 | `INTENT_MODEL_FIELDS_INVALID` / `INTENT_MODEL_VERSION_INVALID` |
| 模型文本包含已知节点 ID 或常见伪造内部 ID 形态 | `INTENT_MODEL_INTERNAL_ID_FORBIDDEN` |
| 无追问草稿尝试澄清 | `INTENT_CLARIFICATION_NOT_REQUIRED` |
| 回答未绑定当前初始草稿 | `INTENT_CLARIFICATION_ANSWER_STALE` |
| 回答字段/版本/值非法 | `INTENT_CLARIFICATION_ANSWER_*` |
| 回答含内部 ID 或投影超限 | `INTENT_CLARIFICATION_INTERNAL_ID_FORBIDDEN` / `INTENT_CLARIFICATION_PROJECTION_TOO_LARGE` |
| 澄清轮次字段、版本、完整性或来源非法 | `INTENT_CLARIFICATION_ROUND_*` |
| 初始草稿仍需澄清却尝试确认 | `INTENT_CLARIFICATION_REQUIRED` |
| 单轮后仍需澄清却尝试确认 | `INTENT_CLARIFICATION_LIMIT_REACHED` |
| 人工确认内容仍携带追问 | `INTENT_ACTION_CLARIFICATION_UNRESOLVED` |
| action 未绑定当前草稿 | `INTENT_ACTION_STALE` |
| 草稿/确认与可信来源不一致 | `INTENT_DRAFT_SOURCE_MISMATCH` / `INTENT_CONFIRMATION_SOURCE_MISMATCH` |
| 被拒绝或未确认意图进入召回 | `CANDIDATE_INTENT_NOT_CONFIRMED` |
| 快照已变化 | `CANDIDATE_SOURCE_STALE` |
| 没有可检索文本 | `INSUFFICIENT_SIGNAL` 且 `allows_addition=false` |
| 有信号但零候选 | `NO_CANDIDATES` 且 `allows_addition=false` |
| 候选集不是默认 Top-20 策略或来源漂移 | `SEMANTIC_CANDIDATE_POLICY_INVALID` / `SEMANTIC_CANDIDATE_SOURCE_MISMATCH` |
| Top-8 投影超过 48,000 字符 | `SEMANTIC_PROJECTION_TOO_LARGE` |
| 模型未按顺序评估全部 Top-8 或引用未知候选 | `SEMANTIC_CANDIDATE_COVERAGE_INVALID` / `SEMANTIC_CANDIDATE_REF_INVALID` |
| 模型/人工建议含稳定或伪造内部 ID | `SEMANTIC_INTERNAL_ID_FORBIDDEN` |
| 正向动作无候选、关系不匹配或证据不足 | `SEMANTIC_ACTION_POLICY_INVALID` |
| 上下文扩展缺场景或已确认事实 | `SEMANTIC_CONTEXT_EVIDENCE_REQUIRED` |
| 澄清问题/证据缺口与动作不一致 | `SEMANTIC_ACTION_POLICY_INVALID` |
| 人工 action 未绑定当前建议草稿 | `RECOMMENDATION_ACTION_STALE` |
| 人工修订违反相同语义政策 | `RECOMMENDATION_ACTION_VALUE_INVALID` 或具体 `SEMANTIC_*` code |
| 保存的建议记录不能由可信来源重放 | `RECOMMENDATION_RECORD_SOURCE_MISMATCH` |
| live 缺少出域确认 | `EXTERNAL_DATA_APPROVAL_REQUIRED`，网络调用数为零 |
| 私有输出已存在或不可安全创建 | `INTERNAL_OUTPUT_WRITE_FAILED` |

模型已经开始调用后的传输/输出失败使用 exit 3 且 `ai.called=true`；确定性输入、
配置 preflight、批准或私有 IO 拒绝使用 exit 2。

演示入口只生成与真实领域无关的固定虚构输入，并依次调用六个正式治理命令。它不
复制召回、哈希、模型校验或回放策略。`--review-decision` 必须显式提供；首段意图
确认固定只授权检索，不是语义审批。若 live 意图返回 `NEEDS_CLARIFICATION`，演示
必须在保存私有草稿后以 `failed_step=CLARIFY` 安全停止，不能创建意图 action、
确认或完成标志。offline 输出应在不同新目录间字节级确定；
bailian-live 缺批准时必须在创建目录、生成输入和网络调用前失败。成功目录为
`0700`、工件为 `0600`，只有完整回放后存在 `12-demo-completion.json`。

### 5. Good / Base / Bad Cases

- Good：确认意图的主体与全树远端节点精确匹配；即使拟挂载位置不同，该节点仍可
  排在局部弱匹配之前。
- Good：Top-8 中存在语义等价候选，模型逐项比较并建议
  `USE_EXISTING_NODE`；人工确认后记录仍明确为运营反馈且可从全部来源重放。
- Good：初始意图只提出一个问题，回答绑定该草稿；一次重新编译后问题消失，人工
  action 绑定 `round_hash` 并进入全树检索。
- Base：完全离线读取两份私有模型输出文件，生成意图草稿、确认、Top-20 候选、
  Top-8 建议和人工记录；不需要 embedding 或网络。
- Base：父节点为 `null`、节点类型和基数为 `UNKNOWN`、值类型为 `null`，只使用
  自然语言需求完成初次意图编译。
- Base：模型合法 `ABSTAIN`，命令成功保存草稿，不把选择性拒答当作传输失败。
- Bad：初始或单轮修订意图仍携带追问，却由 CLI/demo 自动生成
  `CONFIRM_FOR_RETRIEVAL`。
- Bad：把 `NO_CANDIDATES` 解释为“允许新增”，或让拟挂载位置把全树候选过滤掉。
- Bad：只验证 `confirmation_hash` 自洽，不从需求、草稿、action 和快照重放。
- Bad：人工点击确认后把 `RecommendationRecord` 标为 Gold、语义批准或可发布。

### 6. Tests Required

- 合同字段：Schema `required` 与 `to_dict()` 精确一致；
- 澄清合同：回答/轮次精确字段、第一轮限制、状态—追问一致、输入输出容器脱离、
  哈希域和重算哈希篡改覆盖；
- 澄清门禁：无需澄清、陈旧回答、内部 ID、超限投影、直接确认、单轮耗尽和人工
  confirmed intent 残留问题均使用精确错误码失败；
- 模型边界：额外字段、审批字段、已知/常见伪造节点 ID、超限文本和非法 JSON
  拒绝；
- 来源绑定：错误需求、陈旧草稿、重算哈希后的确认篡改仍拒绝；
- 召回：全树强匹配可超过局部弱匹配，节点存储重排不改变结果；
- 安全状态：未确认、拒绝、过期、无信号和零候选均不产生新增许可；
- 投影：固定 Top-8 顺序、只用临时引用，稳定 ID/hash/VALUE/未知字段不进入模型；
- 语义政策：六类动作、五类关系、正向映射、澄清/证据字段、上下文临时门槛和
  合法 `ABSTAIN` 全部覆盖；
- 人工复核：确认、修订、拒绝、陈旧 action、非法修订和可信记录篡改覆盖；
- 反馈边界：所有记录保持非 Gold/非审批/非 Patch，reasoning 不进入聚合 stdout；
- 文件边界：`0600`、symlink/FIFO/公开权限/覆盖拒绝和部分发布清理；
- CLI 泄漏：stdout 不含需求文本、节点 ID/路径、hash、模型内容或凭据；
- Provider：意图、澄清和语义建议 Prompt 均为 JSON Object、每段最多两次尝试、
  批准前零网络、失败时准确 `ai.called`。
- 演示：confirm/reject 均可回放、离线字节确定、live Mock 双调用、澄清安全停止、
  输出目录
  existing/symlink/公开权限拒绝、失败无完成标志、聚合无路径/ID/文本/hash/凭据。

### 7. Wrong vs Correct

#### Wrong

```python
if not candidates:
    return {"action": "ADD_NODE"}
```

#### Correct

```python
candidate_set = build_candidate_set(confirmation, tree)
assert candidate_set.to_dict()["allows_addition"] is False
# 后续语义比较或人工审查决定下一步；召回层不批准新增。
```

#### Wrong

```python
candidates = search_only_under(proposed_parent)
```

#### Correct

```python
candidates = build_candidate_set(confirmation, complete_tree)
# proposed_parent 只贡献可解释 boost。
```

#### Wrong

```python
record = {"semantic_approval": True, "gold_eligible": True}
```

#### Correct

```python
record = apply_recommendation_review(
    draft,
    action,
    confirmation,
    candidate_set,
    tree,
)
payload = record.to_dict()
assert payload["semantic_approval"] is False
assert payload["gold_eligible"] is False
assert payload["patch_eligible"] is False
```

#### Wrong

```python
if draft.review_status == "NEEDS_CLARIFICATION":
    confirmation = apply_intent_review(request, draft, generated_action, tree)
```

#### Correct

```python
if draft.review_status == "NEEDS_CLARIFICATION":
    clarification = provider.clarify(request, draft, answer, tree)
    if clarification.review_status != "READY_FOR_HUMAN_REVIEW":
        raise IntentValidationError(
            "INTENT_CLARIFICATION_LIMIT_REACHED",
            "single clarification round did not resolve the intent",
        )
```
