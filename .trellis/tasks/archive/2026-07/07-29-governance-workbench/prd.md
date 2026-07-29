# 可视化治理工作台首个纵切

## Goal

在不改变现有 TreeGuard 确定性核心、文件型 sidecar 和 Shadow 只读边界的前提下，
建立一个可本地运行的 React + FastAPI 工作台首个纵切：浏览器经后端读取 Clean-room
仿真仓库的分类、信息树、版本和 2,000+ 节点虚构树，并使用 Ant Design Tree 完成
搜索、展开、选择和节点详情查看，为后续意图、候选、AI 建议和专家审查页面建立可信
边界。

## What I already know

- 当前仓库是 Python 3.10+、标准库运行时、`src` 布局，已有六个 CLI、版本化 JSON
  合同、确定性 Core、loopback 仿真仓库和 OpenAI-compatible 模型仿真。
- `ProvisionalRepositoryClient` 已严格验证四类暂定只读仓库合同，并把全树交给
  `adapt_tree_document()` 形成 `CanonicalTree`。
- 完整治理文件纵切已经支持意图草稿、一次澄清、人工确认、全树候选、AI 语义建议、
  人工复核和可信回放；当前没有 Web、入站 API、前端工程或数据库。
- 产品继续使用 sidecar/overlay，不得连接或修改生产信息树、MongoDB 或生产数据。
- 用户已接受 React + TypeScript + Vite、Ant Design Tree、FastAPI 薄应用层的总体
  方向，并要求开始开发。
- 备用工作路径是当前仓库的符号链接，不是第二份代码库。
- 上一任务的归档 bookkeeping 改动尚未提交，本任务不得修改或回退那些文件。

## Requirements

- 新增独立前端工程，使用 React、TypeScript、Vite 和 Ant Design。
- 新增 FastAPI Workbench API；HTTP 层只能调用应用服务和既有 Adapter/Core，
  不得复制领域策略，也不得通过 subprocess 调 CLI。
- 首个纵切只连接现有 loopback Clean-room 仿真仓库；真实 Spring Boot 合同留待后续。
- 后端提供健康检查、分类列表、分类下资源、资源版本和指定版本轻量树投影接口。
- 轻量树投影必须从 `CanonicalTree` 正向允许列表构造，不返回 `VALUE`、
  `metadata_extra`、`extension`、source route、snapshot hash 或文件路径。
- 前端一次加载完整轻量树；2,000+ 节点使用 Ant Design Tree 虚拟滚动，支持名称搜索、
  自动展开祖先、节点选中和详情查看。
- Clean-room 仿真的分类、资源和节点显示名称优先使用完全虚构的中文；英文 label
  和虚构稳定 ID 保留用于验证展示名称与身份解耦。
- 浏览器不得直连仓库、模型服务或读取密钥；开发环境通过 Vite proxy 调用 FastAPI。
- 前端不把树、节点、搜索词或详情写入 `localStorage`，不使用外部 CDN 或第三方埋点。
- API 使用固定非敏感错误码；不得返回底层异常 message、URL、凭据或原始响应。
- 新增依赖必须锁定并说明内网离线导入影响；现有 Python CLI 行为保持兼容。
- 提供本地启动说明和完全虚构的手工冒烟路径。

## Acceptance Criteria

- [x] 仿真服务启动后，Workbench API 可以依次读取分类、资源、版本和一棵
  2,001 节点虚构信息树。
- [x] 树 API 返回精确允许列表字段，并有测试证明 VALUE、额外元数据、哈希和内部
  路径不会进入响应。
- [x] 非 loopback 仓库地址、非法选择器、合同漂移和仓库不可用均失败关闭并返回固定
  错误码。
- [x] 前端可以选择分类、资源和版本，加载并显示完整信息树。
- [x] 搜索命中后自动展开祖先路径并高亮结果；选择节点后显示 kind、类型、基数和
  派生面包屑。
- [x] 2,001 节点虚构树可在浏览器中交互，页面不渲染 2,001 个同时可见的 DOM 行。
- [x] 前端刷新不会修改任何治理工件或生产数据。
- [x] 既有 Python 单元测试、聚焦后端测试、前端构建/测试和 `git diff --check` 通过。
- [x] README 或聚焦文档准确说明启动顺序、当前暂定合同与尚未实现范围。

## Definition of Done

- Tests added/updated（Python `unittest` 与前端聚焦测试）。
- `uv sync --frozen`、配置的 Python 单元测试、前端锁定安装/构建/测试和
  `git diff --check` 通过。
- 未配置的 lint、typecheck、coverage 或 CI 不报告为已通过。
- 新增运行时依赖、离线导入和失败回退已记录。
- 实际 diff 通过 `trellis-check` 审查并自修。
- Git 暂存和提交只在用户审阅范围并明确批准后执行。

## Technical Approach

### Backend

- `treeguard.web` 持有 FastAPI app、HTTP DTO 和错误映射；
- `treeguard.application.workbench` 持有只读目录查询与树视图投影；
- `ProvisionalRepositoryClient` 继续负责 loopback transport 和暂定合同校验；
- `CanonicalTree` 继续是树结构唯一可信内存表示；
- API 返回界面 DTO，不直接暴露 `CanonicalTree.to_dict()`；
- 初期请求同步执行，因为四类仓库读取是本地、确定性、短耗时；AI 长任务在后续
  治理纵切中单独加入 operation/polling，不在本任务预造队列。

### Frontend

- `web/` 作为独立 npm 工程；
- TanStack Query 管理目录和树服务端状态；
- React 局部状态只保存展开、选择和搜索；
- Ant Design `Tree` 使用 `height` 开启虚拟滚动，完整轻量树在加载时转换为
  `treeData`；
- 首屏采用三栏工作台：左侧信息树，中部显示当前选择和后续流程占位，右侧显示
  节点合同详情与只读边界提示。

## Decision (ADR-lite)

**Context**：TreeGuard 需要先验证大型树的浏览、定位和候选联动基础，同时不能把
当前 CLI 编排复制到前端，也不能在接口合同未知时臆造真实仓库集成。

**Decision**：首个纵切选择 Ant Design Tree + FastAPI + 既有 loopback simulator，
只实现只读目录和树浏览，不同时实现 AI 治理操作、数据库或真实 Spring Adapter。

**Consequences**：可以尽快得到可运行、可验证的前后端骨架和 2,001 节点交互证据；
页面暂时不能提交需求或运行 AI。下一任务可在同一应用服务边界上加入治理 case 和
长操作轮询，无需改写树浏览层。

## Research References

- [`research/workbench-stack.md`](research/workbench-stack.md) — Ant Design Tree
  适合作为大型层级治理主视图，jsMind 只保留为未来有界局部关系视图。

## Out of Scope

- 真实 Spring Boot、MongoDB、邮件系统或内网 Qwen 接入。
- 浏览器直连外部模型、百炼或仓库。
- AI 意图草稿、澄清、候选建议、专家审批和 Patch 的 Web 操作。
- 数据库、认证、多人并发、任务队列、SSE 或 WebSocket。
- 信息树编辑、拖拽移动、生产写入和 Patch 发布。
- jsMind、全树脑图或多个树组件之间的双向状态同步。
- embedding 和向量检索。

## Technical Notes

- 适用规范：
  `.trellis/spec/backend/development-data-boundary.md`、
  `directory-structure.md`、`persistence-and-integration.md`、
  `error-handling.md`、`quality-guidelines.md`，以及
  `.trellis/spec/guides/cross-layer-thinking-guide.md`。
- `pyproject.toml` 当前 `dependencies = []`；加入 FastAPI/Uvicorn 会改变当前
  “标准库运行时”事实，需要同步 lock、规范和文档。
- 前端依赖需要提交 npm lockfile，内网导入需要包含 Python wheel/npm tarball
  缓存或经批准的离线制品；本任务只记录要求，不构建生产离线包。
- 任务和测试只能使用仿真器独立生成的完全虚构数据。
