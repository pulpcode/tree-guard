# 仓库事实与首轮方案边界

## 本轮核查范围

只核查当前已提交的 `change_intent.py`、`retrieval.py`、`semantic_recommendation.py`，以及
M4.9/M5 的公开聚合结论；未读取仓库外模型原始请求或响应，未进行新的模型调用。

## 当前链路的事实

### Intent 合同

`IntentContent` 当前包含 12 个语义字段：`subject`、`role`、`scenario`、`lifecycle`、
`ownership`、`node_kind`、`value_type`、`cardinality`、`confirmed_facts`、
`assumptions`、`evidence_gaps`、`clarification_question`。

这 12 个字段并不都进入召回：当前 `_intent_terms()` 只消费 subject、role、scenario、
lifecycle、value_type、confirmed_facts 和 assumptions。ownership、node_kind、cardinality
通过独立的小权重结构匹配使用；evidence_gaps 和 clarification_question 不进入召回。

更关键的是，原始 `requirement_text` 不直接进入召回。召回完全依赖模型先把自然语言
改写为 Intent；模型若省略了一个关键业务词，即使输出合同完全合法，也会永久丢失该
检索信号。反过来，`assumptions` 进入查询词集合，会把模型推测带入召回。

### Retrieval 基线

当前算法是全树扫描的确定性词法/结构打分：

- 查询词使用集合，丢失词频、短语、字段来源和重要度；
- 节点自身 name/label 和祖先 path 分别做精确 token 重叠；
- subject、kind、value type、cardinality 和可选 proposed parent 提供固定加分；
- 没有 IDF、同义表达、拼写/术语归一化、稠密向量或学习排序；
- 同分最终按 node ID 排序，保证确定性，但没有业务排序意义；
- 不要求界面必须提供选中节点。没有 proposed parent 时会全树扫描；错误 parent 则会
  给错误分支结构加分，因此它只能是低信任可选信号，不能成为硬前提。

这解释了为什么当前 401/1453 节点虚构树上能表现出能力，却仍不能推断真实查询一定
顺利：它擅长词面接近且结构 hint 正确的需求，对同义改写、跨层表达和错误上下文缺少
稳定机制。

### Semantic 与动作

当前模型不仅逐候选输出 relation，还同时输出 action 和 selected candidate。合同会在
本地校验 action 与 relation 的联合约束，因此能阻止一部分非法组合，但“选择哪个动作”
仍由模型完成。M5 结果中安全退让没有形成正向误操作，却暴露候选引用和合并问题，说明
安全性与面向用户的交互质量是两个不同维度。

## 对 M5 聚合结果的解释

- Intent 最终合同 72/72，只说明重试后 JSON/字段合同可用；首次仅 39/72，说明合同
  负担仍高，不能据此认为语义抽取已经稳定。
- Retrieval 38/46 是当前最明确的上游缺口；但分母只包含 Intent 已匹配后真正执行的
  单元，不能与 72 个总观测直接比较。
- Semantic 在已通过召回的候选上产生 24 个首选、12 个安全替代、0 个不安全正向错误，
  说明候选受控时模型具有关系判定能力；2 个最终合同失败和退让文本问题仍需处理。
- 因此当前不是“模型完全不能理解树”，也不是“只差调 Prompt”；主要问题是检索信号
  过度依赖 Intent 改写、检索表示较弱，以及 Semantic/Policy 职责未完全收口。

## 首轮候选方案

### A：保持现状

作为冻结基线，不再修改。价值是可重放和可比较，不作为推荐终态。

### B：加权词法/BM25 风格的最小候选（推荐先做）

定义版本化 `RetrievalQuery` 与 `NodeSearchDocument`：

- Query 保留原始 requirement text，同时分开保存 subject、confirmed facts 和机器约束；
- assumptions 默认不进入主查询，只作为可审计的低信任扩展；
- Document 分字段保存节点 name/label、祖先路径、kind、value contract 和有限邻域文本；
- 文本评分采用可解释的字段权重与 IDF/BM25 风格分数；结构约束继续确定性加权；
- proposed parent 仅作软 boost，并单独报告“无上下文/正确上下文/错误上下文”消融结果；
- 同分才使用稳定 node ID 作最终确定性排序。

选择它作为第一候选的原因不是认定它最终优于向量检索，而是它对当前缺口改动最小、
无需新增外部基础设施，且失败归因清晰。

### C：稠密向量或混合检索

只有 B 在同义改写/跨层表达上仍显著不足时再进入下一轮。它需要额外冻结 embedding
模型、切分、索引版本、离线部署能力、相似度阈值与重建策略，不宜和 Intent、Semantic
职责同时改变，否则无法判断增益来源。

## 推荐的职责收缩实验

先比较两种后处理，不增加模型调用：

1. 当前方案：模型输出 relation + selected candidate + action；
2. 收缩方案：模型只负责每个候选的 relation/证据充分性，本地策略根据固定优先级、
   基数和安全规则选择 candidate 与 action。

若收缩方案保持首选命中、降低合同失败且不增加不安全错误，就冻结为 MVP；只有当模型
动作选择在相同候选和相同 relation 输入下展示不可替代增益时才保留。

## 实施前必须补齐的实验合同

1. 从已暴露 M4.9/M5 中冻结开发校准分母，明确 A/B 使用同一输入与同一 Oracle；
2. 增加 Recall@8、Recall@20、MRR，而不是只判断现有 Top-K 集合是否整体 MATCH；
3. 为 requirement text、Intent 文本、结构 hint 分别做消融；
4. 对 proposed parent 做缺失、正确、错误三组消融；
5. 将“召回没有目标”和“召回有目标但 Semantic 拒绝”分开记账；
6. 预先写出 B 相对 A 的最低增益和不可退化指标，再实现候选算法；
7. B 选定并冻结后，才生成新的未见确认集，且确认集只运行一次。

## 当前建议

可以进入“实验合同 + 最小候选接口”的设计，但尚不应直接加入向量数据库或继续修改
模型 Prompt。第一实现切片应只引入版本化检索表示和离线 A/B harness，保持生产入口
继续使用 A，直到 B 在预注册校准指标上通过。
