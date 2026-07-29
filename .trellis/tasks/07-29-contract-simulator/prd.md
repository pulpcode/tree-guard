# 协议级开发仿真系统

## Goal

在尚未获得内网 Qwen 和信息树仓库真实调用样例前，基于公开 OpenAI Chat
Completions 形状和现有四类只读仓库接口认知，建设完全虚构、确定性、可替换的
Clean-room Simulator。它为 Provider、仓库 Adapter、批量导入、治理工作流和未来
可视化页面提供开发环境，但不冒充真实系统或真实模型效果。

## What I already know

* 当前仓库已有百炼 OpenAI-compatible Provider、严格模型输出合同和文件型治理纵切。
* 当前树源 JSON 的递归形状、版本身份和 `resource/instance` 边界已经由本地材料验证。
* 未来仓库只读边界包含分类、分类资源 HEAD、资源业务版本列表和指定版本全树四类能力。
* 真实接口样例将在后续提供，本任务不能把未验证的路径、字段、分页、排序或认证假设
  写成生产事实。
* 仿真数据只能是完全虚构的确定性数据；不能作为真实领域 Gold 或业务准确率证据。

## Assumptions (temporary)

* 第一版使用 Python 标准库 HTTP Server，保持核心运行时零第三方依赖。
* 模拟 API 使用版本化的暂定开发合同，与未来真实内网薄 Adapter 分离。
* 默认仅监听 loopback，不提供生产部署、远程暴露或任意转发能力。
* 第一版同时提供模拟服务端和最小客户端/合同验证，使它能真正支撑 TreeGuard
  端到端开发，而不只是返回静态 JSON。

## Research References

* [`research/simulator-architecture.md`](research/simulator-architecture.md) — 推荐标准库
  纯函数路由器、loopback HTTP 壳和最小客户端，保持零运行时依赖。

## Feasible Approaches

### A：服务端 + 最小客户端（推荐）

同时交付 Mock OpenAI、Mock Tree Repository、四步仓库读取客户端，以及
`mock` / `bailian-live` 双模型源。Mock 支持确定性与故障测试，百炼使用同一套
完全虚构数据观察真实模型结果。未来内网 Qwen 作为第三种 Provider 配置接入。

### B：只交付模拟服务端

代码更少，但当前 TreeGuard 不能直接连接 loopback Qwen，仓库也没有 HTTP Adapter；
只能用外部工具手工测试，无法形成真正的开发闭环。

### C：只交付静态 fixture

最小，但不能验证 HTTP 协议、状态码、查询和批量获取，不满足本任务目标。

## Requirements (evolving)

* 提供 OpenAI-compatible `/v1/chat/completions` 模拟能力。
* 提供分类、资源 HEAD、版本列表、指定版本树四类只读模拟接口。
* 提供小规模和 2,000+ 节点确定性虚构信息树。
* 支持正常、澄清、非法 JSON、HTTP 错误和超时等受控场景。
* 开发工作流允许选择确定性 `mock` 或现有 `bailian-live`；百炼只接收完全虚构
  数据，并继续要求显式 `--external-data-approved`。
* 百炼真实输出只写私有 sidecar，stdout 继续只报告聚合状态，不进入 fixture、
  Git、Trellis 日志或确定性断言。
* 所有生产未知点必须标记为 `PROVISIONAL_SIMULATOR_CONTRACT`。
* 模拟接口不读取真实材料、不访问外网、不修改生产系统。

## Acceptance Criteria (evolving)

* [x] 同一配置产生字节稳定的分类、资源、版本和树响应。
* [x] 模拟树可被现有 `adapt_tree_document()` 接受并产生稳定快照。
* [x] OpenAI 模拟响应可覆盖意图、单轮澄清和候选语义建议的正常路径。
* [x] 可确定性触发非法 JSON、额外字段、429、500 和超时场景。
* [x] 默认只监听 loopback，输入大小、路径和查询参数失败关闭。
* [x] 仓库客户端可按四步清单获取并验证一个资源的业务版本快照。
* [x] 同一虚构场景可切换到 `bailian-live`，真实模型结果通过现有本地合同后写入
  私有新文件；缺少出域批准时在网络和输出前失败。
* [x] 自动化测试不访问网络、不依赖真实凭据或真实业务数据。

## Definition of Done

* 相关单元、合同和 CLI 测试已增加。
* `uv sync --frozen` 通过。
* 已配置的完整 `unittest` 套件通过。
* `git diff --check` 通过。
* 未配置的 lint、typecheck、coverage 和 CI 不报告为已通过。
* README、架构或开发说明按实际行为更新。

## Out of Scope

* 真实内网地址、认证、证书和实际接口字段映射。
* 内网 Qwen 语义质量、A10 性能、并发和上下文上限验证。
* 把百炼响应固化为真实领域效果结论或确定性测试期望。
* Spring Boot/MongoDB 代码或生产写入。
* Web 可视化页面。
* embedding、正式 Gold 和真实业务效果评测。
* 生产级 Mock 管理平台、录制真实流量或代理真实请求。

## Technical Notes

* 优先复用现有严格 JSON、虚构树、Provider 请求合同和聚合 CLI 规则。
* 需要先检查 `ai_review.py`、`demo_cli.py`、`adapter.py`、CLI 注册和测试服务模式。
* 暂定合同必须容易替换，真实样例到达后通过新任务修订，而不是兼容未知假设。
* 已实现标准库纯函数路由器 + loopback HTTP 壳 + 最小客户端；运行时依赖仍为空。

## Validation Evidence

* `uv sync --frozen --offline`：通过。
* `uv run --frozen --offline python -B -m unittest discover -s tests -v`：
  176 项通过。
* 真实 loopback 冒烟：2,001 节点的两个业务版本读取完成，完整治理六步完成两次
  Mock HTTP 调用。
* timeout 冒烟：模型调用后以
  `SIMULATOR_MODEL_CONNECTION_FAILED`、exit 3 安全停止，未产生完成标志。
* 百炼完全虚构冒烟：真实模型调用成功并返回合同有效的
  `NEEDS_CLARIFICATION`，流程按人工澄清门禁停止；未将结果固化为测试或 Gold。
* `git diff --check`：通过。
* formatter、linter、type checker、coverage、CI 和第三方 JSON Schema validator：
  当前未配置。

## Decision (ADR-lite)

**Context**：单纯 Mock 无法观察真实模型的输出质量，单纯百炼又无法提供稳定回归和
故障注入。

**Decision**：采用双模型源。`mock` 是默认确定性开发与测试能力；
`bailian-live` 复用现有 Provider，只处理完全虚构且显式批准出域的场景。仓库侧
始终使用 Clean-room 模拟数据。未来内网 Qwen 使用相同模型端口加入第三个配置，
不改变治理 Core。

**Consequences**：开发人员既能稳定回放，也能观察真实模型；百炼输出保持私有、
非 Gold、非审批、非 Patch，且不能进入单元测试基线。
