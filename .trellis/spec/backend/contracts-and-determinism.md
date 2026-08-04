# 合同与确定性

修改序列化工件、dataclass 不变量、JSON Schema、枚举、排序、摘要、模型视图、
事件账本或回放函数时，必须遵守本规范。

## 合同层必须一起修改

持久化工件通常同时具有：

1. `contracts/` 中的版本化 JSON Schema；
2. Python 版本、算法和策略常量；
3. 不可变运行时类型或严格 parser；
4. 显式 `to_dict()`，必要时还有 `from_dict()`；
5. 精确定义的哈希载荷；
6. 合同与篡改测试。

这些层必须原子修改。只在 Schema 或 serializer 增加字段是合同缺陷；改变
已有 v1 语义却不升级相应 Schema、algorithm、policy、prompt、projection 或
workflow 版本，同样是缺陷。

当前对应关系包括：

- `CanonicalTree` ↔ `contracts/tree-snapshot.v1.schema.json`
- `TreeDiff` ↔ `contracts/tree-diff.v1.schema.json`
- `BusinessVersionReviewRun` ↔
  `contracts/business-version-review.v1.schema.json`
- `LLMEvidencePack` ↔ `contracts/llm-evidence-pack.v1.schema.json`
- `ExpertReviewSession` ↔ `contracts/expert-review-session.v1.schema.json`
- `IntentClarificationAnswer` ↔
  `contracts/intent-clarification-answer.v1.schema.json`
- `build_intent_clarification_model_input()` ↔
  `contracts/intent-clarification-model-input.v1.schema.json`
- `IntentClarificationRound` ↔
  `contracts/intent-clarification-round.v1.schema.json`
- `SemanticCandidateProjection` ↔
  `contracts/semantic-recommendation-model-input.v1.schema.json`
- `SemanticRecommendationDraft` ↔
  `contracts/semantic-recommendation-draft.v1.schema.json`
- `SemanticRecommendationContent` ↔
  `contracts/semantic-recommendation-content.v1.schema.json`
- `RecommendationReviewAction` ↔
  `contracts/recommendation-review-action.v1.schema.json`
- `RecommendationRecord` ↔
  `contracts/recommendation-record.v1.schema.json`
- `AssistedShadowAdmissionReport` ↔
  `contracts/scenario-assisted-shadow-report.v1.schema.json`

当前没有运行时 `jsonschema` 依赖。JSON Schema 是跨边界合同，Python 自己做
精确字段与语义校验；现有测试只验证 Schema 可解析和必填字段与序列化对象
一致，不等于完整第三方 Schema 验证。

## 不可变工件

公共或持久化工件使用 `@dataclass(frozen=True, slots=True)`。嵌套 JSON 通过
`freeze_json()` 与调用者的可变容器脱离，输出通过 `thaw_json()` 返回副本。
参考：

- `src/treeguard/models.py`
- `src/treeguard/diff.py`
- `src/treeguard/history.py`
- `src/treeguard/evidence.py`
- `src/treeguard/expert_review.py`
- `src/treeguard/semantic_recommendation.py`

私有、短生命周期 builder（如 `adapter._NodeDraft`）可以可变。不得把调用方的
`dict`/`list` 直接放入 frozen dataclass；测试必须覆盖修改原始输入和修改
`to_dict()` 结果都不会改变工件。

## 封闭字段与跨字段不变量

不可信边界对象使用精确字段集、固定 Schema 版本、有界字符串/数组、枚举允许
列表、唯一引用和跨字段策略。例如 `ai_review.py` 的 `_MODEL_DRAFT_KEYS`、
`expert_review.py` 的 `_SESSION_KEYS`，以及 `expert_cli.py` 的 action/approval
parser。

多数 Schema 对象使用 `additionalProperties: false`；`constraints`、
`extension`、count map 和 reference map 等映射容器有意开放。保持这一区别，
不能把所有对象一律封闭。

数字合同边界必须区分 `bool` 与 `int`；position、count、timeout、limit 不接受
布尔值。

## 规范排序

不得依赖源对象插入顺序、set 迭代或偶然 dict 顺序：

- node 和 node delta 按稳定 `node_id` 排序；
- change type、reason code、risk level、gate 使用显式等级表；
- review case 和 observation 使用确定性 tuple key；
- dict key 只在哈希/输出序列化时规范化。

`sort_keys=True` 不能规范化数组。构造工件前先排序/分级，并在 `__post_init__()`
或 `validate()` 校验顺序。

## 哈希

内容摘要统一使用 `treeguard.hashing.canonical_digest()`，不得再实现一套
`json.dumps()` + hash。该函数使用 UTF-8 JSON、`ensure_ascii=False`、
排序对象 key、紧凑分隔符和 SHA-256。

每个哈希域必须明确：

- snapshot/node hash 有意排除原始 `VALUE` 和审计字段；
- diff、review、evidence、draft、event、session hash 绑定声明载荷，并排除
  正在计算的 hash 字段；
- observation flag 是否属于哈希域是合同决定，不是实现细节。

哈希是完整性机制，不是签名。匹配摘要不能推出身份、可信来源、权威 HEAD、
发布权限或人工批准。低熵业务值的哈希也不得作为外网脱敏材料。

## 可信来源回放

跨进程/文件边界的工件只做自洽校验不够，必须从可信来源重新计算并比较整个
规范对象：

- `verify_history_run_against_snapshots()`
- `verify_business_version_review_against_snapshots()`
- `ExpertReviewSession.from_dict()` /
  `verify_expert_review_session_against_sources()`
- `SemanticRecommendationDraft.from_dict()`：从确认、Top-20 候选和快照重建 Top-8
  投影；
- `RecommendationRecord.from_dict()`：从建议草稿、人工 action、确认、候选集和
  快照重建完整记录。

单轮澄清的 `IntentClarificationRound` 内嵌初始草稿和回答，并分别绑定
`source_initial_draft_hash`、`source_answer_hash`；后续人工 action 必须绑定实际
查看的 `round_hash`。因此对内嵌来源重新哈希篡改后，完整确认回放仍必须因 action
陈旧而拒绝。哈希只提供链路完整性，不认证回答者或模型身份。

不可信生产者即使重新计算外层 hash，也不能让篡改工件变可信。

## 树与版本身份

- 跨快照节点只按稳定 `node_id` 匹配；
- 不从 name、label、route 或词法相似度推断身份；
- 确定性领域核心不解析业务版本字符串推断顺序；
- 业务版本审查只消费 Adapter/调用方提供的显式相邻位置；真实仓库 Adapter 可按
  D-045 已确认的版本格式产生位置，其他来源仍记录
  `UNVERIFIED_EXPLICIT_SEQUENCE`；
- 保存修订与业务版本比较是语义不同的范围。

`ENDPOINT_NET_CHANGE` 不能重建操作顺序、版本原因或专家意图；历史输出保持
`EVIDENCE_ONLY`。

## 模型边界合同

不得把内部工件完整 `to_dict()` 发给模型：

- 构建有界 `LLMEvidencePack`；
- 只发送 `to_model_dict()` 的允许列表字段；
- 用临时 `F`、`X`、`C`、`T` 引用替换稳定内部标识；
- 校验模型返回的每个引用；
- 本地把通过校验的输出绑定回可信 case/pack；
- AI 建议与专家状态迁移、Patch 资格分离；
- 真实字段名仍需严格脱敏；临时 ID 替换不能解决字段语义泄漏。

参考：`evidence.py`、`ai_review.py`、`expert_synthesis.py`、
`expert_review.py`、`semantic_recommendation.py`。

语义建议模型输入使用 Top-8 的 `C001`—`C008` 引用。虽然 `C` 前缀也用于其他
一次性 EvidencePack，但引用作用域仅限各自工件，禁止跨 pack/投影复用。模型必须
按投影顺序返回每个候选一次；本地代码校验正向动作与关系匹配。人工修订复用同一
语义政策，不能通过人工 action 绕过模型输出门禁。

## 合同变更最低测试

- Schema 必填字段一致性和版本常量；
- 缺失/额外字段、错误版本、非法枚举/类型、重复或未知引用；
- 源对象/存储节点重排后的规范顺序；
- 排除字段变化时 hash 不变，域内语义变化时 hash 改变；
- 调用方输入和 `to_dict()` 输出的可变性攻击；
- 篡改、重新哈希篡改、错误来源和可信回放拒绝；
- 空 diff/review 有意义时的合法空结果。

不能只测试 happy path 或只证明外层 hash 自洽。
