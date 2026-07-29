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
