# Web 治理交互闭环首个纵切

## Goal

在既有只读信息树工作台上接入第一个可运行的治理交互闭环：用户针对完全虚构的
信息树输入新增字段需求，后端复用现有确定性意图、候选召回、受约束语义建议和
人工复核核心，最终只保存可回放的旁路记录，不修改信息树。

## What I already know

- 已有 React + FastAPI 工作台能够浏览 Clean-room 仿真仓库的分类、资源、版本和
  2,001 节点虚构中文信息树。
- Python 核心已经实现意图草稿、一次澄清、人工确认、全树 Top-20 候选、
  Top-8 语义建议、人工复核和可信来源回放。
- Web 层不得通过 subprocess 调用 CLI，也不得复制领域策略。
- 浏览器不得直连仓库或模型；模型配置和密钥只能由服务端读取。
- Shadow MVP 只写 sidecar/overlay，不修改生产信息树、MongoDB 或业务版本。
- 当前工作区另有既存 Trellis 归档 bookkeeping，不能回退或混入产品提交。

## Requirements

- 首个 Web 闭环只使用完全虚构的开发数据；默认使用 loopback 模型仿真，可显式
  选择百炼真实调用，但仍需服务端出域批准门禁。
- 首版允许一次澄清；模型仍不能确定时安全停止，交给专家重新描述或放弃。
- AI 建议只算待审建议；人工确认也只形成运营反馈，不产生 Gold、语义审批或
  Patch 资格。
- 长模型调用采用 operation 创建与轮询，不让一个浏览器请求无限等待。

- 用户可从当前选定的信息树版本发起治理需求，不要求先在生产前端右键选中子树。
- 用户至少填写自然语言需求；拟挂载节点、节点类型、值类型和基数均为可选提示。
- 后端从当前指定的只读快照重建可信 `CanonicalTree`，不能接受浏览器上传的树。
- API 复用现有核心生成意图、候选和语义建议，不通过 subprocess 调 CLI。
- 浏览器展示 AI 意图、候选比较、建议动作、证据缺口和一次澄清问题。
- 首个纵切的专家可以确认或拒绝建议，并提交自由文本思考；受合同约束的建议修订
  留待后续，但自由文本只进入私有旁路工件，不进入 case GET。
- 完成记录必须保持 `semantic_approval=false`、`gold_eligible=false` 和
  `patch_eligible=false`。
- 错误响应和公开状态只包含固定错误码与聚合状态，不返回需求、节点、模型响应、
  路径、密钥或哈希。

## Acceptance Criteria

- [x] 完全虚构需求可从页面发起并得到结构化意图草稿。
- [x] 需要澄清时页面只允许一轮回答；仍不确定则安全停止。
- [x] 人工确认意图后生成确定性候选并显示前 8 个候选。
- [x] 模型仅能在这些候选中给出受约束建议，本地合同校验失败关闭。
- [x] 专家确认或拒绝后生成可回放旁路记录，且不修改源信息树。
- [x] 刷新或重复轮询不会重复执行同一 operation。
- [x] 2,001 节点虚构树的治理闭环可运行。
- [x] Python、前端测试、前端构建和 `git diff --check` 通过。

## Definition of Done

- Tests added/updated（Python `unittest` 与前端聚焦测试）。
- `uv sync --frozen`、配置的 Python 单元测试、前端测试/构建和
  `git diff --check` 通过。
- 未配置的 lint、typecheck、coverage 或 CI 不报告为已通过。
- 文档准确说明模型模式、旁路边界、失败回退和未实现范围。
- 实际 diff 通过 `trellis-check` 审查并自修。
- Git 暂存和提交只在用户明确批准后执行。

## Out of Scope

- 生产 Spring Boot/MongoDB 写入、信息树编辑和 Patch 发布。
- 真实内网 Qwen 或真实四类接口适配。
- embedding、向量数据库和全树 Recall Gold 评测。
- 多人并发、登录鉴权、组织级权限和生产任务队列。
- 人工对 AI 建议做结构化修订；首版只支持接受、拒绝和私有自由文本理由。
- 把人工反馈自动标为 Gold 或专家先验。

## Technical Notes

- 适用规范：
  `.trellis/spec/backend/development-data-boundary.md`、
  `governance-intake-and-retrieval.md`、`contracts-and-determinism.md`、
  `persistence-and-integration.md`、`error-handling.md`、
  `workbench-api.md` 和跨层思考指南。
- 需要先检查 `governance_cli.py` 中现有编排是否可提取为应用服务，不能让
  FastAPI 复用 CLI 私有 helper 或文件参数协议。

## Research References

- [`research/web-governance-boundary.md`](research/web-governance-boundary.md) —
  现有 Core/Provider 可直接由应用服务编排；CLI subprocess 和浏览器持有完整工件
  都不符合当前边界。

## Technical Approach

- 新增治理应用服务，持有当前 case 的可信树、请求、草稿、确认、候选、建议与
  人工记录；FastAPI 只做 DTO、错误映射和 operation 编排。
- 浏览器只使用 `case_ref`、`operation_ref`、树视图 `N000001` 引用和候选
  `C001`—`C008` 引用；稳定节点 ID、hash 和完整工件只留在服务端私有边界。
- 每次模型调用创建一次 operation；相同 operation 的重复轮询只读状态，不重复
  执行模型。
- 完成的正式工件通过既有不可覆盖私有 JSON writer 写入服务端 case 目录；
  API 只返回界面所需的独立允许列表。
- `simulator-live` 默认调用 loopback Provider；`bailian-live` 只有在请求显式
  声明出域批准且服务端配置有效时才调用。

## Decision (ADR-lite)

**Context**：Web 需要复用成熟治理核心，又不能把 CLI 文件协议、稳定标识或完整
模型工件暴露给浏览器；百炼调用还可能超过普通 HTTP 请求时长。

**Decision**：采用“应用服务 + 进程内 operation registry + 私有 sidecar store”
的首个纵切。领域核心和 Provider 保持唯一策略所有者，FastAPI 不通过 subprocess
调用 CLI。仿真与百炼共享同一应用流程，只在 Provider 和批准门禁处分叉。

**Consequences**：可以端到端展示真实 AI 建议和人工复核，并保持旁路、可回放与
失败隔离；首版 operation 只保证单进程生命周期，服务重启恢复、多 worker 协调和
生产队列留待后续任务。

## Extension：模型交互诊断面板

### Goal

在本地 Web 工作台中查看当前 case 实际交给模型的受控消息、模型返回内容和调用
诊断，帮助定位 Prompt、字段合同和模型质量问题，同时不把凭据、HTTP 头、内部路径
或生产数据扩大暴露到普通专家界面。

### What I already know

- 当前所有正式 Provider 都设置 `enable_thinking=false`，因此没有可展示的模型
  思考链；现有 `rationale`、`assumptions`、`uncertainties` 和
  `evidence_gaps` 是结构化输出，不等于隐藏思考过程。
- 当前 case API 明确禁止返回需求原文、模型 envelope 和 reviewer reasoning；
  浏览器也没有登录鉴权，直接开放完整模型 trace 会改变既有安全边界。
- Provider 当前只向应用服务返回本地校验后的领域对象；原始模型 content 和每次
  重试请求没有作为正式旁路工件持久化。
- 初始意图不会发送全树；语义建议只发送前 8 个临时候选投影。诊断面板应忠实展示
  实际阶段输入，不能误称为全量信息树。

### Assumptions (temporary)

- 无。

### Feasible Approaches

**A. 开发诊断模式（推荐）**

- 服务端开关默认关闭；启用后，折叠面板展示每次调用的 system/user 消息、模型
  content、Prompt 版本、尝试次数、固定校验结果和可用 usage。
- 不展示 Authorization、API key、完整 HTTP envelope、base URL、内部 ID 或路径；
  原始模型 content 仅驻留当前内存，非法输出也能在当前 case 中诊断。
- 安全边界清晰，适合当前无登录、loopback-only 的开发工作台。

**B. 普通专家界面的合同视图**

- 始终只展示已校验的意图/建议对象和输入字段摘要，不展示原始模型 content。
- 风险较低，但无法解释 `INTENT_MODEL_FIELDS_INVALID` 这类原始字段漂移。

**C. 完整 HTTP/推理 Trace**

- 展示请求 envelope、原始响应、隐藏推理或传输信息。
- 与当前数据边界和无鉴权架构冲突，不纳入本任务。

### Requirements

- 采用方案 A，仅在显式服务端开发开关启用时提供模型诊断；默认行为和既有 case
  API 字段保持不变。
- 覆盖初始意图、一次澄清和语义建议三类模型调用；每次调用按 attempt 独立记录。
- 展示 Provider 实际发送的 system/user 消息、模型原始 content、Prompt 版本、
  模型模式、固定本地校验结果以及响应中明确提供的 usage。
- Trace 只存在当前 `WorkbenchGovernanceService` 进程内存中，按 case 绑定，服务
  重启即丢失；不写正式 sidecar、日志、URL、localStorage 或下载文件。
- 不展示 Authorization、API key、HTTP headers、base URL、内部路径、稳定节点
  ID、hash 或完整信息树；诊断 API 继续使用独立正向允许列表。
- 原始 content 必须设大小上限；非 JSON、字段非法和重试失败也只能以有界文本和
  固定错误码显示，不能返回异常或服务端 traceback。
- 页面使用默认折叠的“模型交互诊断”区域，按阶段和 attempt 展开；明确区分
  “原始模型输出”和“本地校验后的结构化结果”。
- 当前保持 `enable_thinking=false`；页面显示 `Thinking: DISABLED`。结构化
  `rationale`、`assumptions`、`uncertainties` 和 `evidence_gaps` 可以展示，但
  不称作思考链。
- MVP 不提供 Trace 下载/导出，不支持普通专家模式，不恢复服务重启前的 Trace。

### Decision (diagnostics ADR-lite)

**Context**：真实模型的字段漂移只有固定错误码时难以定位，但当前 Web 无登录鉴权，
完整模型 trace 又可能包含需求和节点语义。

**Decision**：增加默认关闭、loopback-only 的内存诊断通道。Provider 通过显式
可选 trace sink 上报受限事件；应用服务按 case 保存有界记录；独立诊断 API 只在
服务端开关启用时返回；前端折叠展示。正式领域工件和 sidecar 合同不增加 trace。

**Consequences**：开发者可定位实际 Prompt、原始输出与重试错误，同时保持生产默认
面和回放工件不变；无鉴权普通专家界面、持久化 trace、下载导出及隐藏思考链留在
范围外。

### Acceptance Criteria

- [x] 默认配置下诊断 API 不可用，既有 case 响应字段不变化。
- [x] 显式开发开关下可按调用阶段查看准确的消息与原始模型 content。
- [x] 重试按 attempt 分开展示，并标出固定本地校验结果。
- [x] 页面明确显示 `thinking=DISABLED/UNAVAILABLE`，不把结构化理由称作思考链。
- [x] Trace 不含凭据、HTTP 头、内部路径、稳定节点 ID 或完整信息树。
- [x] Trace 不写入正式 sidecar、日志、URL 或 localStorage。
