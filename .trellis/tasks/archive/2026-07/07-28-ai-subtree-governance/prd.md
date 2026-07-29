# AI 辅助子树治理 Shadow MVP

## Goal

把 TreeGuard 从“历史版本事后审查”推进到“新增需求进入建树前的在线旁路治理”：
建设人员以自然语言描述新增需求和拟挂载位置，AI 生成可修订的结构化意图草稿，
人工确认后由确定性代码在整棵信息树中召回疑似复用、重复或相关候选，为后续语义
比较、专家裁决和 Patch 提供可信输入。

## What I already know

* 当前仓库已经实现 Schema-only 导入、稳定哈希、版本 Diff、历史/业务版本审查、
  白名单 EvidencePack、受约束 AI 初审和可回放专家审查。
* 当前没有 `ChangeIntent` 合同、面向新需求的全树候选检索、Semantic Overlay、
  Schema Patch 或生产写入路径。
* 现有候选排序是历史审查 EvidencePack 内的私有词法 helper，查询来自已变更节点，
  不能直接充当新需求检索合同。
* 单棵树通常约 2,000 个节点；MVP 应全树查重、局部治理。拟挂载父节点只能提高
  局部候选权重，不能裁剪全树候选。
* 业务专家可以提交思考、假设和证据缺口；系统不能强迫其形成虚假确定结论。
* 产品运行保持文件型 Shadow：AI 输出只写 sidecar/overlay，不修改 Spring Boot、
  MongoDB、生产信息树或邮件数据。
* 内网模型通过 OpenAI 兼容接口提供服务；外网百炼只允许处理完全虚构或按用途
  明确批准的严格脱敏输入。

## Confirmed Scope

* 本任务交付一个可独立验证的纵切：需求文件 → AI 意图草稿 → 人工确认 →
  确定性全树 Top-20 候选；不在同一任务内实现最终动作建议、Overlay 或 Patch。
* 每次运行只处理一个新增需求案例；输入至少包含自然语言需求，可选包含拟挂载
  `node_id` 和已知类型/基数提示。
* 第一版召回采用可解释、可离线回放的词法与结构特征，不把 embedding 模型设为
  冒烟环境前置条件；接口应为后续混合召回预留扩展点。
* AI 只起草主体、角色、场景、生命周期、属性归属、类型、基数、事实、假设、
  证据缺口和一个最高价值追问；它不能确认意图，也不能生成节点 ID 或 Patch。
* 只有显式人工确认并绑定草稿哈希的意图才能进入候选检索。

## Requirements

* 增加版本化、严格字段集的需求输入、模型输出、意图草稿和人工确认合同。
* 原始自然语言需求和完整内部制品只能通过权限受限的文件传入/写出，不进入命令行、
  聚合 stdout、日志或外部开发工件。
* AI 输出必须作为不可信输入进行精确字段、枚举、长度、数量和跨字段校验；非法
  JSON、未知字段、越权状态或结构异常均 fail-closed。
* 意图草稿必须绑定源需求和基础快照；人工确认必须绑定实际查看的草稿哈希。
* 未确认或基础快照已变化的意图不得进入候选检索。
* 候选召回覆盖整棵 `resource` 树，排除 `UNSUPPORTED` 节点和 VALUE；拟挂载位置
  只能作为 boost。
* 候选排序、截断、tie-break 和结果哈希必须确定、可回放并可单独评测。
* 无候选只能解释为“当前基线未召回”，不得自动推导为“允许新增”。
* Mock/离线验证不依赖网络或 embedding；外部百炼路径继续要求显式出域确认。
* 内网 Qwen 的真实端点、JSON Mode 兼容性和中文召回质量标为内网核验项，不在
  外网仓库记录内部地址、真实请求或响应。

## Acceptance Criteria

* [x] 使用完全虚构的 `resource` 树和需求文件，可生成通过本地合同校验的 AI
      意图草稿。
* [x] 模型编造内部 ID、输出确认状态、超限内容、未知字段或非法 JSON 时，在任何
      候选产物写入前被拒绝。
* [x] 人工确认制品绑定源需求、基础快照和草稿哈希；篡改任一来源后回放失败。
* [x] 未确认、被拒绝、来源不匹配或已过期的意图无法执行候选检索。
* [x] 同一确认意图与同一快照重复运行得到相同的候选顺序和结果哈希。
* [x] 候选覆盖全树，拟挂载位置 boost 不会隐藏全局更匹配候选；默认最多返回
      Top-20，并保留可解释的分项信号。
* [x] `instance`、`UNSUPPORTED`、VALUE 和未分类扩展字段不会进入治理候选或模型
      投影。
* [x] 第一版不使用持久化索引；零候选或输入信号不足返回明确的安全状态，不产生
      “允许新增”结论。
* [x] CLI 默认 stdout 仅输出固定状态、错误码和聚合计数；敏感完整输出使用
      `0600`、独占创建且拒绝符号链接。
* [x] 现有测试保持通过，并新增合同、AI 边界、确认、召回、确定性、过期和 CLI
      安全测试。

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* `uv sync --frozen`、已配置的 `unittest` 测试和 `git diff --check` 通过
* 未配置的 lint、typecheck 和 coverage 不宣称已通过
* 行为变化同步更新 README、架构与内网迁移说明
* 所有 fixture 完全虚构，候选 diff 通过开发数据边界审查
* 不增加生产写路径，回滚方式为停用新 CLI 并保留原有审查链路

## Out of Scope (explicit)

* Spring Boot/MongoDB 读写 Adapter、生产编辑器或 Web UI
* Semantic Overlay 审批、最终语义动作、Schema Patch、Dry Run 和发布
* 邮件 Usage Manifest 与影响分析
* embedding/reranker 模型部署、向量数据库或微调
* 自动删除、移动、合并、改类型或改基数
* 直接处理真实树、真实节点字段名、VALUE、专家原文或内部模型 trace
* 用虚构或 AI 合成案例宣称真实业务准确率

## Technical Approach

采用“AI 只编译、人工确认、确定性召回”的分层方案：

1. `IntentRequest` 仅从私有文件读取，绑定 CanonicalTree 快照。
2. 模型只返回不含内部 ID、审批字段和动作结论的 `ChangeIntentModelOutput`。
3. 本地代码校验后生成带来源哈希的 `ChangeIntentDraft`。
4. 人工通过独立 action 文件确认、修订或拒绝草稿；确认结果绑定
   `expected_draft_hash`。
5. 确定性 Retriever 使用意图字段、路径、节点类型、数据类型、基数和拟挂载位置
   计算可解释分数，输出冻结候选集。
6. 后续任务才把候选集投影给 Qwen 做语义比较，并接入现有专家审查状态机。

## Decision (ADR-lite)

**Context**：当前完整 Shadow 路线同时缺少新需求意图合同、在线候选检索、
Semantic Overlay 和 Patch。一次实现全部能力会扩大信任边界，并使召回错误和模型
决策错误难以独立评测。

**Decision**：首个实施任务采用“AI 意图草稿 + 显式人工确认 + 确定性全树
Top-20 召回”。第一版不要求 embedding，也不输出最终语义动作。

**Consequences**：本任务可以形成比单纯结构化表单更完整的演示闭环，并在无网络
环境回放；召回质量不足时会安全返回待人工处理。混合召回、候选语义比较、Overlay
和 Patch 由后续独立任务增加。

## Research References

* [`research/next-slice.md`](research/next-slice.md) — 依据当前实现缺口比较三个下一步
  纵切，推荐先完成“意图确认 + 确定性全树召回”。

## Technical Notes

* 适用入口：`src/treeguard/adapter.py`、`src/treeguard/models.py`、
  `src/treeguard/evidence.py`、`src/treeguard/ai_review.py` 和现有文件型 CLI。
* 历史 EvidencePack 与在线召回共享 `treeguard.lexical.text_terms()`；各自保留
  不同的候选评分和合同，避免改变历史投影语义。
* 敏感读取、输出 preflight 和不可覆盖发布已提取到 `treeguard.private_io`，现有
  AI/专家 CLI 与新治理 CLI 共同复用，不再跨 CLI 私有导入。
* 意图 Provider 复用 `BailianConfig` 和既有安全传输，在独立 Prompt 与严格输出
  合同后生成 `ChangeIntentDraft`。
* 需要内网核验：Qwen 的结构化输出能力、端点配置边界、中文分词效果和真实
  Top-K 召回质量；外网只提供 Mock 与虚构百炼冒烟。

## Implementation Evidence

* 新增 `treeguard-governance draft/confirm/search` 文件型 CLI。
* 新增六份版本化合同、确定性意图/确认/候选核心和公共私有 IO/词法模块。
* `uv sync --frozen` 通过；完整 `unittest` 共 129 项通过，`git diff --check`
  和 Trellis task validate 通过。
