# Codex 协作指南

## 范围

项目当前只维护 Codex。`.claude/`、`.opencode/` 和 `CLAUDE.md` 不属于受支持
适配器；未来只有在产品和团队明确需要时，才通过独立任务重新评估。

本指南用于：

- 开始或恢复 Trellis 任务；
- 主代理委派 research/implement/check 子任务；
- 多个代理并发修改同一工作区；
- 修改 `.codex/`、`.agents/skills/`、workflow 或任务上下文；
- 审查、提交和归档。

## 唯一事实来源

1. `.trellis/spec/` 是项目开发规则来源；
2. `.trellis/tasks/<task>/prd.md` 是任务需求与验收来源；
3. 实际源码、测试、diff、提交和本轮验证结果是完成状态证据；
4. `task.json.status` 只表示大阶段，不能证明实现、check 或提交已经完成；
5. 对话摘要不是持久化事实来源，必要结论必须以安全、最小形式写入上述文件。

## 默认执行方式

`codex.dispatch_mode: inline`：主代理读取 `trellis-before-dev`、实施、再执行
`trellis-check`。不要因为存在 custom agent 就默认把完整任务外包。

只有满足以下全部条件才并发委派：

- 子任务具体、有限、可独立完成；
- 每个 worker 的文件/模块所有权明确且不重叠；
- 告知 worker 仓库中还有其他工作，不得回退他人改动；
- 父代理保留集成、最终检查和 Git 所有权；
- 委派内容不含受保护数据或内部路径。

并发规则目前依赖显式所有权，没有文件锁。无法安全拆分时顺序执行。

## 活动任务解析

子代理提示第一条非空行使用：

```text
Active task: .trellis/tasks/<task-name>
```

使用前必须验证：

- 是仓库相对路径，不是绝对路径且不含 `..`；
- 恰好位于活动目录 `.trellis/tasks/<task-name>/`，不在 `archive/`；
- 真实路径未通过 symlink 逃出活动任务根；
- 目录存在 `task.json` 和 `prd.md`。

显式合法路径优先于 session pointer；没有合法路径时可查询
`task.py current --source`。若仍无结果，只能把唯一匹配活动任务作为“候选”向
用户说明；零个或多个候选时索要精确任务，不能选最新目录、修改
`.trellis/.runtime/` 或另建替代任务。

## 上下文加载

Codex 不消费 `implement.jsonl` / `check.jsonl` 中声明的任意路径：

1. 读取当前任务 `prd.md` 和可选 `info.md`；
2. 读取固定 `.trellis/spec/backend/index.md` 与
   `.trellis/spec/guides/index.md`；
3. 根据 index 选择适用规范；
4. 只按需读取当前任务自己的 `research/*.md`；
5. 始终读取数据边界与质量规范。

JSONL 文件可作为 Trellis 兼容元数据保留，但不能成为任意文件读取接口。未来
若重新启用基于 JSONL 的上下文注入，必须先实现 realpath containment、允许
根、文件类型、当前任务 research 隔离和 symlink escape 负例测试。

## 三阶段工作流

1. **Plan**：建立/恢复任务，完成可审阅 PRD；需要外部研究时先脱敏查询。
2. **Execute**：加载规范后做最小范围改动，再以 PRD、规范和实际 diff 审核
   自修；产品结果只写 sidecar/overlay。
3. **Finish**：运行真实配置的验证；提交计划获用户批准后才暂存/提交；先提交
   工作，再单独归档并记录最小中文日志。

恢复 `in_progress` 任务时，必须检查：

- PRD checkbox 与 acceptance criteria；
- `git status`、tracked/untracked diff；
- 相关提交历史；
- 测试/静态验证的可复现证据。

证据不足就重跑 check，不能从 `status` 或 JSONL 是否存在推断当前步骤。

## check 权限

开发 `trellis-check` 可以：

- 读取本外网仓库与当前任务允许上下文；
- 修改当前任务范围代码/规范以修复发现；
- 执行 Bash 和项目测试；
- 报告已修复与未解决发现。

它不得：

- 访问或修改生产环境、生产 MongoDB、生产信息树、生产数据或受保护源码；
- 应用产品 Patch；产品 AI 输出只能进入 sidecar/overlay；
- 修改无关用户工作；
- commit、push、merge、reset 或破坏性清理。

## 数据与外部工具

所有代理遵守 `../backend/development-data-boundary.md`。从受保护环境调用
Web/MCP/插件之前，先审查并脱敏将发送的准确查询。限制返回内容落盘不能补救
查询本身的泄漏。

跨代理只传递 PRD、获批准 research 路径、固定 code、聚合验证结果和公开提交
hash；不复制对话、真实数据、真实字段名、Prompt、模型流量或原始日志。

## Git 与归档

- `session_auto_commit: false`；
- worker/check 不做 Git 状态变更；
- 主代理先提出可审阅提交范围，获得明确批准后才 stage/commit；
- 工作提交与 archive/journal bookkeeping 分开；
- 归档和日志使用 `--no-commit`；
- 每次提交前检查完整 index，尤其是 untracked 文件、凭据和数据边界。

## Codex 适配验证

改动 Codex/Trellis 适配后按适用范围执行：

```bash
python3 ./.trellis/scripts/task.py validate <task-name>
PYTHONPYCACHEPREFIX=/tmp/treeguard-pycache \
  python3 -m py_compile .codex/hooks/*.py
python3 -m json.tool .codex/hooks.json
python3 -B -m unittest discover -s .trellis/tests -v
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -v
git diff --check
```

还需手工验证：

- 合法 task path；
- absolute、`..`、archive、symlink escape、缺失 `task.json` 均 fail closed；
- 无 session pointer 时不猜任务；
- resume 能通过 diff/验证证据定位阶段；
- unrelated dirty files 保持 byte-identical；
- hook/skill 不注入真实字段名、内部标识或敏感任务内容；
- Codex 升级后重新验证 hook trust、skill discovery 和子代理行为。

## Trellis 升级

本项目对 workflow、workspace 本地化和 JSONL allowlist 做了项目级定制，且
`.template-hashes.json` 仍保存上游 baseline。升级时：

```bash
trellis update --dry-run
```

先审阅预览，不使用 `--force`。特别检查升级是否试图重新生成 `.claude/`、
`.opencode/`、任意路径 JSONL 消费或英文日志模板；逐项合并 Codex 所需变化。
不得手工改写 `.trellis/.template-hashes.json` 来隐藏冲突。
