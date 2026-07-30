# 内网仓库与 Qwen 适配

## Goal

在不接触生产写接口的前提下，为 TreeGuard 增加真实信息树仓库的只读 HTTP
Adapter 和无 API Key 的内网 Qwen OpenAI-compatible Provider，使现有工作台能在
受保护环境中读取分类、资源、业务版本和完整信息树，并复用同一治理闭环调用
Qwen。外网开发与自动测试只使用完全虚构的合同响应。

## What I already know

- 信息树仓库提供分类平铺列表、分类下资源当前/默认版本分页列表、资源业务版本
  列表和完整信息树四类 GET 接口。
- 精确接口路径为
  `/api/v1/category/query-list`、`/api/v1/resource/list`、
  `/api/v1/resource/version-info` 和 `/api/v1/resource/tree`。
- `resource_id / map_id` 跨业务版本稳定；`id` 唯一标识某个业务版本的信息树，
  同一个当前版本在资源列表、版本列表和完整树中的 `id` 一致。
- 完整树可以用 `resource_id + version` 或查询参数 `id` 定位。
- `resource/list` 返回当前/默认版本；该指针可以切换到历史版本，不等于按版本
  字符串排序后的最新版本。
- 版本接口顺序不保证；版本字符串忽略前缀和中间字母后，先比较前半段数字序列，
  再比较后半段数字序列。
- `resource/list` 的 `latest` 参数不参与业务语义；分页先使用保守的
  `page_size=50`。
- 内网 Qwen 使用 OpenAI-compatible `/v1/chat/completions`，模型 ID 为
  `qwen3.6`，不需要 API Key。
- 关闭思考使用
  `chat_template_kwargs={"enable_thinking": false}`；首版使用非流式
  `response_format={"type": "json_object"}`。
- 原始接口说明、内部主机和响应样例不进入 Git；仓库只保存精确路径、公开字段
  形状和完全虚构的测试材料。

## Assumptions (temporary)

- 仓库成功信封使用 `status=200`；缺省或无实质意义的 `message` 不参与成功判断。
- 首版允许通过运行配置注入 loopback、RFC1918 地址或显式内部主机名，不把真实
  主机写入代码或文档。
- 仓库和 Qwen 都不继承系统代理，不跟随重定向。
- 真实错误响应尚未提供；首版对非 2xx、非严格 JSON、字段/身份不一致统一失败
  关闭，不依赖错误正文。

## Open Questions

- 真实错误信封、分页上限和内网 Qwen JSON 输出稳定性仍需在受保护环境冒烟。

## Requirements

- 新增真实仓库只读 Client/Adapter，不修改或伪装现有暂定 simulator client。
- 分类适配 `id/name/order/isRoot/parentId`，允许根分类缺省 `parentId`。
- 资源列表逐页读取，使用 `metadata.total` 判断完成；检测重复页、重复资源、
  总数漂移和有界上限。
- 资源当前/默认版本将列表 `id/resource_id/version` 与版本列表和完整树做来源
  一致性校验。
- 版本列表使用已确认的版本字符串规则产生显式 oldest-first position；历史字段
  `is_head` 只标记唯一当前/默认版本，最新版本由最大 position 独立确定。
- 完整树支持 `resource_id + version` 与 `id` 两种互斥选择器，并继续交给
  `adapt_tree_document()` 规范化。
- 新增独立 Qwen 配置和 Provider 身份；不要求或发送 Authorization，不复用百炼
  的出域批准语义。
- Qwen 复用现有意图、澄清、语义建议和专家综合的本地输出合同；Provider 返回
  始终作为不可信输入校验。
- 工作台增加显式 `QWEN_LIVE` 模式，百炼、Qwen 和 simulator 三种模式不能隐式
  回退。
- 外网测试使用完全虚构 HTTP transport/响应，不打开真实内网连接、不读取原始
  接口文件。

## Acceptance Criteria

- [x] 四类真实仓库响应的虚构合同测试通过，并正确映射到现有目录和
  `CanonicalTree`。
- [x] 无序版本响应能按确认规则稳定排序；非法、重复或歧义版本失败关闭。
- [x] 当前/默认版本可指向历史版本，并与排序后的最新版本分别标记和展示。
- [x] `resource/list.id`、`version-info.id` 和完整树 `metadata.id` 不一致时失败。
- [x] 分页在多页、空页、重复页、总数漂移和上限场景下行为确定。
- [x] Qwen 请求不含 Authorization，包含嵌套 `chat_template_kwargs`，并复用
  JSON-object 输出校验与最多两次有界尝试。
- [x] 工作台可显式选择 Qwen，且不要求百炼出域批准；其他模式行为不回归。
- [x] Python、前端测试、前端构建和 `git diff --check` 通过。

## Definition of Done

- Tests added/updated（Python `unittest` 与必要的前端聚焦测试）。
- `uv sync --frozen`、配置的 Python `unittest`、前端测试/构建和
  `git diff --check` 通过。
- 未配置的 lint、typecheck、coverage 或 CI 不报告为已通过。
- 文档说明受保护环境配置、无认证 Qwen、已确认的 `id` selector 和失败关闭边界。
- 实际 diff 通过 `trellis-check` 审查。
- Git 暂存和提交只在用户明确批准后执行。

## Out of Scope

- 生产写接口、MongoDB 直连、自动 Patch 发布或修改生产信息树。
- 把原始内部主机、真实响应、真实树、节点字段、VALUE、凭据或模型 trace 写入
  仓库。
- 流式 Qwen、工具调用、Web Search、Reasoning 内容持久化或多模型自动回退。
- 小版本保存修订枚举、Schema-only 新接口、embedding 或批量真实模型评测。
- 声称外网模拟通过即代表内网接口或模型效果已经验证。

## Technical Notes

- 预计复用 `treeguard.adapter`、`RepositoryReader`、Workbench Governance
  Service 和现有严格 JSON/HTTP 隔离工具。
- 现有 `ProvisionalRepositoryClient` 保持 simulator 专用；真实合同使用独立
  Adapter，避免把暂定信封与生产形状混合。
- Qwen 与百炼共享模型输出解析和本地语义政策，但配置、请求字段、Provider 身份
  与批准门禁必须分离。

## Decision (ADR-lite)

**Context**：真实仓库和 Qwen 与现有 simulator/百炼共享上层治理合同，但网络
信封、认证、请求字段和信任边界不同。

**Decision**：采用“独立边界 Adapter + 共享领域核心”。真实仓库不修改
`ProvisionalRepositoryClient`；Qwen 不伪装成百炼，也不复制语义解析策略。

**Consequences**：会增加两个明确的基础设施边界，但避免 Provider 身份混乱、
错误批准门禁和生产合同被模拟合同污染。真实网络兼容性仍需在受保护环境冒烟。

## Implementation Result

- 新增 `InternalRepositoryClient`，支持四接口、分页、版本排序、两种树选择器和
  已观察来源之间的 `id` 绑定。
- 新增 `InternalQwenConfig` 及版本初审、意图/澄清、语义建议、专家思考整理
  Provider；工作台新增 `QWEN_LIVE`。
- 外网只用完全虚构 transport/响应验证，未连接真实内网。
- `resource/tree?id=...` 已确认为直接版本记录选择器；当前/默认版本与最新版本已
  分离建模并由虚构合同测试覆盖。
