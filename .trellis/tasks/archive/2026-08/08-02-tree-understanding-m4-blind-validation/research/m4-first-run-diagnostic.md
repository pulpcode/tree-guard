# M4 首轮虚构模型实验诊断

## 范围

- 日期：2026-08-03；
- 输入：已冻结的完全虚构 fire medium M4 v1 数据，功能合同提交 `d7dff799`，
  数据提交 `a3acfb2`；
- 目的：记录聚合实验结论和后续处置，不保存请求、Prompt、响应、隐藏 Oracle、
  稳定目标或模型 trace。

## 聚合结果

- 选择 8 条执行样本，Intent 阶段实际发起 14 次请求；
- 7 条得到符合本地 JSON/来源合同的草案，1 条在两次尝试后仍为
  `RUN_FAILED`；
- 冻结 Oracle 下为 0 `MATCH`、7 `MISMATCH`、1 `RUN_FAILED`；
- 召回、推荐和 Semantic 均未执行，Semantic 外部调用数为 0；
- 候选准备的结构与记账门通过，但完整执行门失败，公开决定为 `NO_GO`，硬失败
  归类为 `CONTRACT_INTEGRITY_FAILURE`。

字段级聚合不一致为：`assumptions=7`、`clarification_question=5`、
`evidence_gaps=6`、`role=7`、`scenario=6`、`subject=1`。这些计数只用于定位
合同层，不构成模型准确率。

## 根因

M4 v1 request 只为 `node_kind`、`value_type`、`cardinality` 提供结构化 hint；
自由文本中的 `subject`、`role`、`scenario`、`lifecycle`、`ownership` 没有逐字段
来源绑定，也没有证明请求已完整、无需 assumptions/evidence gaps 的合同字段。

首轮 Oracle 模板却普遍要求多个自由文本字段 `NON_EMPTY`，并要求
`assumptions`/`evidence_gaps` 为 `EMPTY`。Intent Prompt 同时禁止模型把没有直接
证据的内容写成事实。因此 request、Prompt 与 Oracle 不能同时满足；运行后的
`MISMATCH` 不能解释为模型意图或信息树理解错误。

## 处置

- 原 fire M4 v1 manifest 和 sidecar 字节保持不变，用作不可变诊断与校准输入；
- 该数据已执行并暴露失败模式，固定为门控不合格，不能在修订后恢复“未见
  holdout”身份；
- M4 v1 执行资格增加 request-aware Oracle 检查：每个 profile 必须完整覆盖 12 个
  字段；非空结构化 hint 只允许与自身一致的 `EXACT_ONE_OF`，`UNKNOWN`/`null`
  hint 必须 `NOT_COMPARED`，澄清问题只按 route 检查；没有逐字段来源绑定的自由
  文本和三个 list 字段也只能 `NOT_COMPARED`；
- 历史 overlay 仍可做来源/字节重放，但执行、冻结和数据门禁必须在 Provider 前以
  `CAPABILITY_ORACLE_REQUEST_MISMATCH` 失败关闭；公开层继续映射为
  `CONTRACT_INTEGRITY_FAILURE`；
- 修订后的 fire 数据只承担非盲校准。正式 `GO_SHADOW` 仍需新的、运行前密封且未
  参与本轮合同修复的数据包。

## 限制与后续

- 本轮没有验证召回、推荐、整树语义理解或生产准确率；
- 1 条 Intent 内容合同失败仍需在校准阶段单独观察，但不能用本轮无效 Oracle 给它
  追加语义结论；
- 若未来必须比较自由文本字段或断言 assumptions/evidence gaps 为空，应升级
  overlay 合同并逐 expectation 绑定结构化 request 字段或精确文本 span；不能增加
  一个无法重放的 `answerability=true` 布尔值。

## Silver 校准实验（修订后合同）

### 身份与范围

- 日期：2026-08-03；
- 数据身份：`CODEX_ASSISTED` / `SILVER` / `CALIBRATION_ONLY`；
- 8 条均获 Silver 校准执行授权，组成固定为 7 条 `PROCEED`、1 条 `CLARIFY`；
- `gold_eligible=false`、`gate_eligible=false`、`patch_eligible=false`；本节结果不覆盖
  上述首轮门控诊断，也不产生 `GO_SHADOW/NO_GO` 决策。

### 聚合执行结果

- Intent：实际 14 次请求；6 条形成合法草案，2 条两次尝试后仍为
  `INTENT_MODEL_CONTENT_INVALID`；
- Intent Oracle：3 `MATCH`、3 `MISMATCH`、2 `RUN_FAILED`。3 条 mismatch 聚合为
  `UNEXPECTED_CLARIFICATION_ON_PROCEED`，不保存具体问题文本；
- 1 条 `CLARIFY` 在 Intent 阶段匹配并按合同短路，召回与推荐均不适用；
- 2 条 `PROCEED` 同时达到 Intent `MATCH` 和确定性召回 `MATCH`，因此进入
  Semantic；其余场景均按上游状态失败关闭；
- Semantic：实际 3 次请求；1 `MATCH`、1 `MISMATCH`、0 `RUN_FAILED`。mismatch
  聚合为 `OVERCONFIDENT_EXISTING_NODE_REUSE_ON_KIND_CONFLICT`；匹配项首次输出未通过
  本地合同，完整重试后通过；
- 端到端达到预期路径的场景为 2/8：1 条合法澄清短路和 1 条完整链路；该比例只描述
  Silver 校准表现，不是准确率估计或门槛分数。

### 结论与 Gold 判断

- 工程链路已经走通：精确字节审批、百炼 Intent、确定性召回、百炼 Semantic、
  稳定目标回映和联合 Oracle 比较均实际执行；
- 当前主要问题已从“运行前合同不可回答”转为可定位的模型行为：过度澄清、内容合同
  不稳定，以及冲突场景中过度复用现有节点；
- 当前 Silver 不应直接升级为 Gold：样本已暴露、由 Codex 辅助审核、仅 2 条到达
  Semantic，且澄清项只验证问题非空、不验证问题质量；
- 可以对当前 8 条做独立人工复核，形成“Gold calibration reference”，但仍不得恢复
  holdout 或进入正式门控；正式 Gold 验证集必须在模型执行前独立人工冻结，并保持
  未见、非 Patch、来源绑定和结果记账边界。

## Silver 下游隔离实验（外发前）

- 日期：2026-08-03；
- 范围：首轮 Intent `RUN_FAILED` 或 `MISMATCH`、且 Silver Oracle 预期为
  `PROCEED` 的 5 条场景；
- 输入：私有 Codex 辅助 Silver 参考 Intent，逐项绑定原请求、Silver 授权和首轮
  Intent 结果 SHA；Intent Provider 未调用；
- 本地结果：参考 Intent 5/5 `MATCH`，确定性召回 5/5 `MATCH`，5 条均可进入
  Semantic；形成 10 个可能请求体（每条首发一次、仅在本地合同失败后完整重试一次）；
- 当前状态：所有请求仅冻结在 `0600` 私有审批文件中，外部调用数为 0，等待精确字节
  批准；
- 解释边界：该结果说明“给定可接受 Intent 时，当前确定性召回可覆盖这 5 条 Silver
  场景”，不证明 Intent LLM 能自行生成该意图，也不计入端到端成绩、门禁或 Gold。

### 执行结果

- 5 条 Semantic 场景均首发完成，实际请求 5 次，未触发合同重试；
- 推荐结果为 4 `MATCH`、1 `MISMATCH`、0 `RUN_FAILED`；Intent 与召回在本次隔离
  输入下均为 5 `MATCH`；
- 唯一 mismatch 聚合归因为
  `OVERCONFIDENT_EXISTING_NODE_REUSE_ON_CARDINALITY_CONFLICT`：模型在基数冲突下
  仍选择等价复用，Silver Oracle 要求先澄清；不在公开记录中保存具体候选、目标或
  模型文本；
- 结论：给定可接受 Intent 后，当前确定性召回和 Semantic 主链路可运行，Semantic
  对普通复用判断表现稳定，但冲突场景存在过度复用风险。当前技术路径并非不可行，
  主要改进点仍是 Intent 稳定性和推荐冲突政策，而非改换整套架构；
- 本结果仍是已暴露数据上的 Silver 下游隔离证据，不能与原端到端 2/8 合并，也不能
  升级为 Gold、生产准确率或 `GO_SHADOW`。

## M4.1 Prompt 与确定性门禁校准

### 变更范围

- 日期：2026-08-03；
- Intent Prompt 升级为 v3，明确 Intent 只编译可检索意图，不因候选存在性或结构
  冲突提前澄清；模型内容合同失败细分为不含原值的字段级固定错误码；
- Semantic Prompt 升级为 v2，`USE_EXISTING_NODE` 增加
  `node_kind/value_type/cardinality` 本地兼容门禁；冲突输出只允许完整重试，不做
  本地动作改写；
- 输入仍为已暴露的 fire Silver 校准集，固定非 Gold、非门禁、非 Patch。本轮不恢复
  holdout 身份，也不与正式准确率或 `GO_SHADOW` 结论合并。

### 聚合结果

- Intent 实际调用 10 次，8/8 形成合同合法草案，0 `RUN_FAILED`；其中 2 条首次触发
  `INTENT_MODEL_OWNERSHIP_INVALID`，经一次完整重试后恢复；
- 隐藏 Silver Oracle 回放为 Intent 7 `MATCH`、1 `MISMATCH`。唯一 mismatch 是预期
  `CLARIFY` 的场景输出 `PROCEED`，差异字段仅为 `clarification_question`；
- 7 条 Intent match 的确定性召回全部 `MATCH`，并全部进入 Semantic；
- Semantic 实际调用 7 次，全部首发满足本地合同，结果为 6 `MATCH`、1 `MISMATCH`、
  0 `RUN_FAILED`；唯一 mismatch 是模型给出 `NEED_CLARIFICATION`，而 Silver Oracle
  接受 `USE_EXISTING_NODE/SEMANTICALLY_EQUIVALENT`，属于偏保守而非冲突候选的
  过度复用；
- 端到端为 6/8 `MATCH`。沙箱内第一次执行产生的 8 次连接失败只记为传输层诊断，
  没有模型响应，不进入上述模型结果分母。

### 解释与下一步

- 字段级错误码已经实际帮助两条草案从所有权枚举失败中恢复，说明该机制同时承担
  原因分析和有界 Prompt 纠错，而不只是日志细分；
- 本轮没有再出现先前的 kind/cardinality 冲突下强行复用，但单批已暴露样本不能证明
  风险已消失；确定性门禁仍是必要的 fail-closed 边界；
- Intent v3 对“显式 hints 完整时优先不提问”的表达可能过强：它减少了无谓澄清，
  也压掉了 1 条合法歧义。下一次校准应把规则收窄为“候选冲突本身不触发澄清；若
  需求文本自身仍存在互斥范围或组合歧义，仍应提出一个原子问题”；
- Semantic 剩余 mismatch 是保守偏差，可作为后续效果调优项，不应通过放松本地结构
  冲突门禁来消除。

## M4.2 澄清边界与 Semantic 重复性校准

### Intent v4

- v4 只把澄清规则收窄为：候选存在性或结构冲突不在 Intent 阶段提问，但需求文本
  自身仍有会改变结构化意图的互斥解释、范围或组合歧义时，仍应提出一个原子问题；
- 8/8 形成合同合法草案，实际调用 9 次，1 条首次触发
  `INTENT_MODEL_OWNERSHIP_INVALID` 后重试恢复；
- Silver Oracle 回放仍为 7 `MATCH`、1 `MISMATCH`。唯一 mismatch 是预期
  `CLARIFY` 的泛化信息请求继续输出 `PROCEED`；7 条适用召回全部 `MATCH`；
- 因此 v4 改善了格式稳定性，但没有单独解决合法澄清召回。

### 被拒绝的词面粒度规则

- 曾试验一个领域无关候选规则：请求只说某对象的“相关信息、详情或资料”时强制
  澄清；该版本 8/8 首发格式合法，也恢复了原澄清场景；
- 但另外 5 条预期 `PROCEED` 的场景被错误转为澄清，Intent 只剩 3 `MATCH`；
- 该规则因明显过校准立即停线，未执行对应 Semantic，且已从代码、测试、规范和
  PRD 中回退。当前实现继续采用 v4；后续不能用关键词强制澄清。

### Semantic v2 三次固定请求重复性

- 对同一组 v4 Intent、同一 Semantic Prompt 和同一冻结请求字节执行三次，逐轮
  `MATCH/MISMATCH/RUN_FAILED` 分别为 `4/1/2`、`3/1/3`、`4/1/2`；
- 21 个执行单元累计为 11 `MATCH`、3 `MISMATCH`、7 `RUN_FAILED`；3/7 场景
  三次稳定匹配，1/7 三次均合同失败，其余 3/7 在匹配、语义不一致或合同失败之间
  波动；
- 该结果说明单次最好成绩不能代表当前模型的 Semantic 能力，生产验证必须报告
  重复性，并把合同遵循率与 Oracle 匹配率分开。

### 安全错误码诊断

- 运行器结果合同升级为私有 v2，只从 Provider trace 提取固定 `SEMANTIC_*` code，
  不保存模型响应、理由或候选正文；
- 一次独立诊断运行结果为 4 `MATCH`、2 `MISMATCH`、1 `RUN_FAILED`，错误聚合为
  `SEMANTIC_SELECTED_CANDIDATE_CONTRACT_CONFLICT=2`、
  `SEMANTIC_ACTION_POLICY_INVALID=1`；
- 一条场景首轮被结构冲突门禁拒绝，重试后合法但选择“按合同新增”，而 Oracle 要求
  先澄清；另一条合法输出选择澄清，而 Oracle 接受复用；持续失败场景先触发结构
  冲突，重试又违反动作联合政策；
- 因此本地门禁正在阻止高风险过度复用，当前主要缺口是模型收到通用重试提示后，
  不能稳定根据具体错误类别选择合法替代动作。下一步应把固定 Semantic 错误码送入
  一次完整重试，而不是放松门禁或继续增加词面规则。

## M4.4 Semantic 精确错误码重试

### 变更

- Semantic Prompt 升级为 v3；首次本地失败后只把固定 `SEMANTIC_*` code 加入一次
  完整重试，不回传被拒绝响应，也不在本地改写动作；
- 审批生成器为每个适用场景冻结 1 个首发正文和 16 个可能错误码重试正文；白名单
  扩大不改变调用预算，每个场景实际仍最多调用两次；
- 私有结果继续只保存固定错误码聚合，原始请求、响应、理由和隐藏 Oracle 不入仓库。

### 三次固定请求结果

- 三轮 `MATCH/MISMATCH/RUN_FAILED` 分别为 `5/2/0`、`5/1/1`、`5/2/0`；
- 21 个执行单元累计为 15 `MATCH`、5 `MISMATCH`、1 `RUN_FAILED`；相比 Semantic
  v2 的 11/3/7，合同失败由 7 降至 1，匹配由 11 增至 15；
- 4/7 场景三次稳定匹配，1/7 三次稳定语义不匹配，其余 2/7 在匹配、语义不匹配
  或单次合同失败之间波动；
- 精确错误码实际帮助 `SEMANTIC_ACTION_POLICY_INVALID`、
  `SEMANTIC_MODEL_FIELDS_INVALID` 等首次失败恢复；仍有一次结构冲突后重试为
  `SEMANTIC_TEXT_INVALID`，说明格式稳定性尚未完全解决；
- 合同失败减少后，一部分原 `RUN_FAILED` 转化为可审阅的 Oracle mismatch，这是
  诊断质量改善，不应把 mismatch 数增加误解为能力退化。

### 结论

- v4 Intent + v3 Semantic 的三轮端到端结果均为 5/8，低于原参考线 6/8；本数据本就
  是已暴露 Silver 校准，不产生正式门禁决定，但也不能据此升级 Gold 或进入无人值守；
- 当前技术路径已经证明可运行：Intent 合同、确定性召回、结构冲突门禁、精确重试和
  Oracle 比较均能闭环；主要限制转为模型对澄清边界与推荐动作的语义稳定性；
- 下一步不应继续针对 8 条 Silver 调 Prompt。应冻结当前实现，用新增未见样本验证
  澄清 precision/recall、Semantic 合同遵循率、Oracle 匹配率和三次重复性；若内网
  小模型仍不稳定，再比较更强模型或把推荐改为更小的分步分类任务。
