# 新增需求意图、候选召回与语义推荐

## Scenario：文件型新增需求治理纵切

### 1. Scope / Trigger

当改动涉及 `IntentRequest`、`ChangeIntentDraft`、人工确认、候选评分、
`SemanticRecommendationDraft`、`RecommendationRecord` 或
`treeguard-governance` 时使用本规范。该能力属于 Shadow MVP 临时范围：

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
```

核心签名：

```python
IntentRequest.from_dict(payload, tree)
ChangeIntentDraft.from_model_dict(payload, request, tree, ...)
ChangeIntentDraft.from_dict(payload, request, tree)
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

### 5. Good / Base / Bad Cases

- Good：确认意图的主体与全树远端节点精确匹配；即使拟挂载位置不同，该节点仍可
  排在局部弱匹配之前。
- Good：Top-8 中存在语义等价候选，模型逐项比较并建议
  `USE_EXISTING_NODE`；人工确认后记录仍明确为运营反馈且可从全部来源重放。
- Base：完全离线读取两份私有模型输出文件，生成意图草稿、确认、Top-20 候选、
  Top-8 建议和人工记录；不需要 embedding 或网络。
- Base：模型合法 `ABSTAIN`，命令成功保存草稿，不把选择性拒答当作传输失败。
- Bad：把 `NO_CANDIDATES` 解释为“允许新增”，或让拟挂载位置把全树候选过滤掉。
- Bad：只验证 `confirmation_hash` 自洽，不从需求、草稿、action 和快照重放。
- Bad：人工点击确认后把 `RecommendationRecord` 标为 Gold、语义批准或可发布。

### 6. Tests Required

- 合同字段：Schema `required` 与 `to_dict()` 精确一致；
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
- Provider：两个 Prompt 均为 JSON Object、最多两次、批准前零网络、失败时准确
  `ai.called`。

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
