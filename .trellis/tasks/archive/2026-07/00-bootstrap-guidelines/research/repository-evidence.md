# TreeGuard 规范的仓库依据

日期：2026-07-28

审核基线：`main` 分支，产品源码提交
`6b55446aa00d7f915184171ef37e9c628da2f3fb`

> 该提交仅用于标识形成规范时所检查的源码状态。后续源码演进时，应重新核对
> “当前事实”，不能把本文件当作永久产品合同。

## 仓库现状

- 单一 Python 包，采用 `src` 布局；
- Python 3.10+，setuptools 构建，当前无运行时第三方依赖；
- 提供三个文件驱动 CLI，没有入站 Web/API 服务；
- 没有数据库驱动、ORM、迁移、队列、worker、向量库或生产 Patch 写入器；
- 唯一明确的外部网络集成是经批准的百炼 Chat Completions Provider。

主要依据：`pyproject.toml`、`README.md` 和 `src/treeguard/` 全部模块。

## 稳定实现模式

- 规范/持久化工件使用冻结且带 slots 的 dataclass，并显式实现 `to_dict()`；
- 确定性序列使用排序后的 ID 或显式等级表；
- 摘要统一使用 `hashing.canonical_digest()`，并明确规定哈希载荷；
- 存储与审查工件校验版本、精确字段、跨字段策略和自洽性；可信回放从源工件
  重新计算；
- JSON Schema 和 Python 运行时校验是同一合同的两份实现，修改时必须同步；
- AI 只接收有界、允许列表化的投影，不接收完整内部工件；
- 预期的边界失败使用稳定错误码；安全 CLI 输出只包含错误码和聚合，不包含
  异常原文；
- 敏感专家工件使用有界私有输入和独占 `0600` 输出。

主要依据：`models.py`、`adapter.py`、`diff.py`、`history.py`、
`business_review.py`、`evidence.py`、`ai_review.py`、
`expert_synthesis.py`、`expert_review.py` 及对应测试。

## 对规范结构的调整

- 以 `persistence-and-integration.md` 取代数据库模板，因为仓库中没有数据库层；
- 以 `cli-output-and-diagnostics.md` 取代通用日志模板，因为当前只有版本化
  JSON stdout 报告，没有日志框架；
- 增加 `contracts-and-determinism.md`，因为版本化合同、规范排序、哈希和回放
  是跨模块核心；
- 保留目录、错误和质量指南，并以真实源码重写；
- 把上游通用 thinking guide 替换为 TreeGuard 的复用、跨层和 Codex 协作
  指南。

## 必须保留为“当前事实”的不对称

- 普通信息树导入使用 `Path.read_text()` 和 `json.loads()`；只有专家工作流使用
  私有、有界、严格文件输入；
- 专家私有文件检查普通文件、权限和大小，但不检查 owner UID；`.env` 会检查
  owner UID；
- 已处理的 CLI 失败输出安全聚合 JSON，但意外编程错误仍可能由 Python 输出
  默认 traceback；该 stderr 只能留在受保护运行边界内；
- `treeguard-ai-review` 在模型调用成功、随后内部输出发布失败时，可能错误报告
  `ai.called=false`；
- 多个模块仍跨模块导入下划线私有 helper，这是不得继续扩散的技术债；
- 当前没有 formatter、linter、type checker、coverage 门禁或完整运行时 JSON
  Schema validator。

这些内容只能描述基线提交，不能自动成为永久产品政策。

## 本轮人工审核结论

项目负责人明确确认：

- 节点字段名本身必须严格脱敏；删除 `VALUE`、替换 ID 或稳定化名仍不足以允许
  外传；
- 首期 AI 治理能力采用 sidecar/overlay 旁路存储，不修改生产环境数据；这是
  Shadow MVP 临时限制，后续由产品效果决定；
- 开发 check 代理可修改外网开发仓库内的任务范围代码并运行 Bash，但不得访问
  或修改生产环境、生产数据和受保护源码；
- 当前只维护 Codex，先不考虑 Claude Code/OpenCode；
- 项目自定义规范和工作日志优先使用中文，不为形式统一机械改写清晰英文；
- 面试展示材料在最小可行性验证后补充；
- 初始化审核和提交完成后，建立并推进实际的 AI 辅助子树治理任务。

双环境诊断的已确认方向为：

```text
内网结构化事件
→ 正向允许列表诊断导出器
→ 人工逐字节审核
→ 单向外网诊断包
```

该能力尚未实现。原始日志文件直接外传不是批准方案。

## Trellis/Codex 审核结论

- 默认由 Codex 主代理内联执行；只有边界清楚、文件所有权不重叠的工作才并发
  委派；
- `.claude/`、`.opencode/` 和根 `CLAUDE.md` 已从项目候选内容中移除，避免
  多平台语义漂移和未来 `trellis update` 的额外审核成本；
- 上游 `.trellis/scripts/` 与 `trellis-meta` 仍保留通用平台知识，仅作为
  Trellis runtime/维护参考；没有对应项目 adapter 目录，不代表本项目支持；
- Codex 不依赖任务 JSONL 的任意路径注入。它从当前任务 PRD、固定 spec
  index、适用规范和当前任务 `research/` 中按需读取；
- 项目本地 Trellis runtime 对兼容 JSONL 命令增加 realpath/允许根校验，并让
  Codex inline 的新任务不再生成 JSONL；该定制在未来 `trellis update` 时需
  作为安全差异复审；
- 显式任务路径必须解析到仓库内 `.trellis/tasks/<name>/` 的活动任务，拒绝
  绝对路径、`..`、归档目录、符号链接逃逸和缺少 `task.json` 的路径；
- `task.json` 的 `in_progress` 不能证明实现或检查处于哪个步骤；恢复时必须
  检查 PRD、实际 diff/提交和验证证据，必要时重跑检查；
- `session_auto_commit: false` 保持启用；任务归档和日志写入均需人工审阅后
  单独提交；
- Trellis 任务、research、workspace 日志、提交信息和复制的终端输出都属于
  外网开发区数据边界；
- `bobot` 被定义为非识别性别名，不代表受保护环境中的真实人员。

## 待建立的正式任务

初始化审核并提交后建立：

1. 结构化诊断事件与正向允许列表导出；
2. 修复 `ai.called` 在模型已调用、内部写入失败后的错误状态；
3. AI 辅助信息树子树治理 Shadow MVP（随后立即推进）。

Shadow MVP 形成可行性结论后再建立：

1. Ruff、mypy、coverage、pre-commit、CI 等工程质量基线；
2. 面试展示材料，包括架构、指标、可回放案例、失败分析和演示脚本。
