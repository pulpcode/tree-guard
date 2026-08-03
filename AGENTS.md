<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## TreeGuard 开发数据边界

Trellis 任务、research、规范和工作日志都是仓库内容，必须按外网开发工件处理：

- 不得把真实信息树、真实节点字段名、`VALUE` 载荷、专家文本、模型请求/响应、
  内部标识、凭据、受保护环境源码、内部路径或网络拓扑复制到本仓库。
- 只使用经批准的 Schema 形状、固定错误码、聚合统计、公开合同版本和完全虚构
  的样例。删除 `VALUE`、替换 ID 或使用稳定化名都不等于充分脱敏。
- 任何从受保护环境到外网的单向导入，都必须先严格脱敏，再由获授权人员对
  最终字节内容明确批准，之后才可写入 `.trellis/`、测试、文档或诊断工件。
- 从受保护环境调用 Web、MCP 或其他外部工具前，必须先审查和脱敏查询文本；
  不能只约束工具返回内容是否落盘。
- 产品 AI 审查结果只写 sidecar/overlay，不修改生产信息树或生产数据。开发
  check 代理可在本外网仓库内修复任务范围代码并运行检查，但不得访问或修改
  生产环境、生产数据或受保护源码。
- 任务和日志优先使用最小化中文摘要；已有清晰英文、命令和代码标识无需为了
  形式统一而改写。`bobot` 等名称只能是不对应真实人员的
  非识别性别名。来源或敏感性不确定时，停止并索要安全替代材料。

## 完全虚构测试数据的常设 LLM 授权

- 本项目编制的测试数据统一定义为：在本外网仓库中独立构造、未使用或改写任何
  受保护材料，并标记为 `CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false` 的 fixture、候选、场景和配套测试输入。这些数据不存在
  敏感性，已获得调用本地或外部 LLM 的项目级常设授权。
- 对上述数据，Codex 和测试工具无需逐次请求数据外发许可，也无需先冻结完整请求
  字节供人工审批；可以直接调用内网模型、本地模型或外部模型。现有
  `external_data_approved=True` 等字段只作为数据分类与技术门禁声明，可以直接设置，
  不表示还需向用户申请一次许可。
- 平台网络沙箱、API 凭据、模型服务可用性和费用控制仍须满足；它们是执行条件，
  不是数据敏感性审批。自动化单元测试仍不得访问真实网络。
- 非敏感不等于可以破坏实验隔离：隐藏 Oracle、Gold、预期目标和评分答案不得进入
  被测模型输入；原始 Prompt、请求、响应和 trace 默认仍只保存在私有临时工件中，
  不写入 Git、Trellis、公开报告或 fixture。
- 任何真实、受保护、外部导入、来源不明或由真实材料改写的数据都不属于此常设授权，
  继续适用上方严格数据边界和逐字节批准流程。
