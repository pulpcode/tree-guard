# TreeGuard Trellis 工作流

本项目当前只维护 Codex。默认由主代理内联实施和检查；Trellis 提供任务、规范、
可恢复状态和经审阅的最小工作日志。

## 核心原则

1. **先理解再修改**：先读 PRD、适用 spec 和真实源码。
2. **任务是需求事实来源**：复杂或持久化改动必须有
   `.trellis/tasks/<task>/prd.md`。
3. **规范是开发规则来源**：实现前加载 `.trellis/spec/`。
4. **证据决定恢复位置**：`task.json.status` 不能证明实现/check/提交已完成；
   必须检查 PRD、diff、commit 和验证结果。
5. **Codex 不消费任意 JSONL 路径**：上下文只来自当前 PRD、固定 spec index、
   适用规范和当前任务 `research/`。
6. **受保护数据默认不外传**：真实节点字段名也需严格脱敏；删除 `VALUE` 或稳定
   化名不够。
7. **产品旁路与开发权限分离**：产品 AI 只写 sidecar/overlay，不改生产；
   开发 check 可在外网仓库内自修，但不得访问/修改生产环境或数据。
8. **Git 操作显式批准**：任务归档、日志、暂存和提交都不自动执行。

## 常用命令

```bash
# 会话、活动任务、Git 状态
python3 ./.trellis/scripts/get_context.py

# 规范索引
python3 ./.trellis/scripts/get_context.py --mode packages

# 某一步的详细说明
python3 ./.trellis/scripts/get_context.py --mode phase --step <X.Y> --platform codex

# 任务
python3 ./.trellis/scripts/task.py list
python3 ./.trellis/scripts/task.py current --source
python3 ./.trellis/scripts/task.py create "<title>" --slug <slug>
python3 ./.trellis/scripts/task.py start <task>
python3 ./.trellis/scripts/task.py validate <task>
```

## 目录合同

```text
.trellis/
├── workflow.md
├── config.yaml
├── spec/
│   ├── backend/
│   └── guides/
├── tasks/
│   ├── <active-task>/
│   │   ├── task.json
│   │   ├── prd.md
│   │   └── research/       # 可选，只保存获批准非敏感结论
│   └── archive/YYYY-MM/
└── workspace/<alias>/
    ├── index.md
    └── journal-N.md
```

`implement.jsonl` / `check.jsonl` 可能作为旧版兼容元数据存在，但 Codex 不按其
`file` 字段加载文件，也不以是否已填充来判断任务是否可开始。

## Phase Index

```text
Phase 1: Plan
  1.0 建立或恢复任务
  1.1 澄清需求并形成 PRD
  1.2 必要时研究
  1.3 选择受限上下文（Codex 不整理 JSONL）
  1.4 激活任务
  1.5 确认进入实施的条件

Phase 2: Execute
  2.1 加载规范并实施
  2.2 审查、自修与验证
  2.3 必要时回退到 Plan

Phase 3: Finish
  3.1 最终质量验证
  3.2 必要时做缺陷复盘
  3.3 判断并更新规范
  3.4 提出提交计划，获批后提交
  3.5 归档并记录最小中文日志
```

### 状态提示块

以下 tag 是 `.codex/hooks/inject-workflow-state.py` 的解析合同。起止状态名必须
完全一致。

[workflow-state:no_task]
先判断请求：只读回答、解释或诊断不需要创建任务；需要修改代码、规范、配置或
产生多步持久化成果时，先检查是否有唯一匹配的活动任务。唯一候选只能明确说明
后作为恢复对象；多个候选必须询问，不得猜测。没有匹配任务时进入 Phase 1。
[/workflow-state:no_task]

[workflow-state:no_task-inline]
Codex inline 模式：只读请求直接回答；涉及代码、规范、配置或多步持久化成果时，
先恢复唯一匹配任务，否则进入 Phase 1 创建任务。不得修改 `.trellis/.runtime/`
伪造 session pointer。
[/workflow-state:no_task-inline]

[workflow-state:planning]
Phase 1：完善可审阅 PRD，外部研究前先脱敏查询。Codex 不读取或整理任意 JSONL
路径；从固定 spec index 选择上下文。PRD 和必要 research 就绪后运行
`task.py start <task>`。
[/workflow-state:planning]

[workflow-state:planning-inline]
Codex inline Phase 1：完善 PRD 与验收条件；按数据边界保存 research。跳过
`implement.jsonl` / `check.jsonl` 整理，从固定 spec index 选择上下文，然后
运行 `task.py start <task>`。
[/workflow-state:planning-inline]

[workflow-state:in_progress]
不要只凭 `status` 推断步骤。检查 PRD、实际 diff/commit 和验证证据：未实施则
执行 2.1；证据不完整则执行 2.2；全部通过后执行 Phase 3。产品输出只写旁路，
开发修改只限外网仓库。暂存/提交前必须提出范围并获得用户明确批准。
[/workflow-state:in_progress]

[workflow-state:in_progress-inline]
Codex inline：加载 `trellis-before-dev` 后实施，加载 `trellis-check` 审核并自修，
运行规范中的真实验证，再判断 `trellis-update-spec`。不要读取任务 JSONL 中的
任意路径。提交前必须提出范围并获得用户明确批准。
[/workflow-state:in_progress-inline]

[workflow-state:completed]
只有工作提交已经存在且工作树满足 `trellis-finish-work` 条件时才归档。使用
`--no-commit`，记录最小脱敏摘要并优先使用中文；归档/日志 bookkeeping 单独
审阅和提交。
[/workflow-state:completed]

[workflow-state:completed-inline]
Codex inline：确认工作提交和干净边界后运行 `trellis-finish-work`；归档与最小
中文日志禁止自动 commit，必须单独审阅。
[/workflow-state:completed-inline]

## Skill Routing

| 场景 | 使用 |
|---|---|
| 新功能、复杂需求、多种方案 | `trellis-brainstorm` |
| 开始写代码或刷新规范 | `trellis-before-dev` |
| 恢复活动任务 | `trellis-continue` |
| 实施后审查/自修 | `trellis-check` |
| 发现可复用合同或规则 | `trellis-update-spec` |
| 修复反复出现的 bug 后 | `trellis-break-loop` |
| 已验证并提交，准备归档 | `trellis-finish-work` |
| 修改 Trellis 自身 | `trellis-meta` |

主代理默认内联工作。只有用户明确要求委派，且子任务有限、可独立、文件所有权
不重叠时才使用子代理；父代理负责集成和最终验证。

## Phase 1: Plan

#### 1.0 建立或恢复任务 `[required · once]`

先运行：

```bash
python3 ./.trellis/scripts/task.py current --source
python3 ./.trellis/scripts/task.py list
git status --short
```

- session pointer 合法时使用该任务；
- pointer 缺失且只有一个与请求匹配的活动任务时，把它作为明确恢复候选；
- 零个匹配任务时创建；
- 多个候选时询问精确任务；
- 不选择“最新目录”，不手工编辑 `.trellis/.runtime/`。

创建示例：

```bash
python3 ./.trellis/scripts/task.py create "AI 辅助子树治理 Shadow MVP" \
  --slug ai-subtree-governance
```

只读回答、解释和不修改状态的诊断不要求任务。文件修改原则上需要任务；用户明确
要求一次性微小改动且没有需要保留的决策时，可在说明范围后直接完成。

#### 1.1 需求探索 `[required · repeatable]`

加载 `trellis-brainstorm`：

- 一次只解决一个高价值不确定点；
- 能从源码/文档得出的事实先检查，不把它反问用户；
- 明确目标、非目标、输入、输出、错误、安全边界和验收条件；
- 业务专家拿不准时允许记录思路、证据和不确定性，不能强迫虚假确定分类；
- 把已确认内容写入 `prd.md`，不复制对话原文。

#### 1.2 研究 `[optional · repeatable]`

研究可检查本地源码或公开资料。使用 Web/MCP/远程工具前，先按
`development-data-boundary.md` 审阅并脱敏将发送的准确查询。不能安全改写时，
只在 PRD 标注“需要内网核验”。

获批准结论写入当前任务 `research/<topic>.md`，只含问题、范围、日期、公开/
仓库相对依据、结论和限制。不得保存真实字段名、内部路径、原始日志、Prompt、
模型请求/响应或受保护源码。

#### 1.3 选择上下文 `[required · once]`

Codex inline 不整理或读取任务 JSONL：

1. 读当前 `prd.md`；
2. 读 `.trellis/spec/backend/index.md` 与 `.trellis/spec/guides/index.md`；
3. 选择适用规范；
4. 只按需读取当前任务 `research/*.md`；
5. 始终读数据边界和质量规范。

#### 1.4 激活任务 `[required · once]`

PRD 可实施且验收条件明确后：

```bash
python3 ./.trellis/scripts/task.py start <task-dir>
```

该命令把任务置为 `in_progress`；它不证明实现已开始或完成。

#### 1.5 进入实施的条件

- PRD 有目标、非目标和可验证验收条件；
- 关键不确定性已解决或明确标注内网核验；
- 适用规范已识别；
- 数据来源与外传边界明确；
- 不以 JSONL 是否填充为门禁；
- 用户已同意当前 MVP 范围。

## Phase 2: Execute

#### 2.1 实施 `[required · repeatable]`

加载 `trellis-before-dev`，然后：

- 只做满足 PRD 的最小改动；
- 保持确定性 core 与不可信 AI 分离；
- 产品 AI 输出只写 sidecar/overlay，不修改生产信息树/数据库；
- 不访问受保护源码或数据；fixture 完全虚构；
- 保留无关 dirty work，不做破坏性清理；
- 每完成一个可验证切片就运行聚焦检查。

恢复任务时先检查磁盘证据，不能仅凭 conversation history 或 task status 决定
“尚未实施”或“已经完成”。

#### 2.2 质量检查 `[required · repeatable]`

加载 `trellis-check`，按 PRD、规范和实际 diff 审查。check 可以在当前外网
仓库与任务范围内修改代码、运行 Bash/测试以修复发现，但不得：

- 访问/修改生产环境、生产数据或受保护源码；
- 应用产品 Patch；
- 修改无关用户工作；
- commit、push、merge、reset 或破坏性清理。

运行项目实际配置的验证；未配置 linter/type checker 时如实说明。报告修复项、
未解决项、准确命令和结果。

#### 2.3 回退 `[on demand]`

- check 发现 PRD 缺陷：回 Phase 1 修改 PRD，再实施；
- 发现合同/安全边界不清：停止写代码，先研究或索要批准；
- 测试失败：保持任务 `in_progress`，定位并修复；
- 需要新权限、生产写入或新数据：停止并请求项目负责人决定。

## Phase 3: Finish

#### 3.1 最终质量验证 `[required · repeatable]`

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -v
git diff --check
```

按改动范围增加 Trellis/Codex 配置检查。审阅 tracked 和 untracked 全部候选路径，
确认无 credential、真实数据、真实字段名、内部路径或原始日志。

#### 3.2 缺陷复盘 `[on demand]`

修复重复/深层 bug 后使用 `trellis-break-loop`，记录根因类别、失败修复原因和
可执行预防规则；只保存脱敏结论。

#### 3.3 更新规范 `[required · once]`

判断本次是否产生可复用、已验证的合同或约定。需要时使用
`trellis-update-spec`；当前任务的临时实现细节不写成永久规范。明确标注永久
边界、MVP 限制或当前事实。

#### 3.4 提交改动 `[required · once]`

提交前：

1. 展示候选路径和提交分组；
2. 检查 staged/untracked 内容及数据边界；
3. 向用户请求明确批准；
4. 只暂存批准路径；
5. 审阅 cached diff 后提交；
6. 报告真实 hash。

不把工作提交与 archive/journal bookkeeping 混在一起。

#### 3.5 归档提醒

工作提交完成且实现工作树满足要求后使用 `trellis-finish-work`：

- archive 使用 `--no-commit`；
- journal 只写最小脱敏摘要、优先使用中文，并使用 `--no-commit`；
- 单独审阅归档移动、task status、workspace index；
- 获得批准后再提交 bookkeeping。

## Customizing Trellis (for forks)

这是项目本地工作流，可按团队决定修改。修改时保持：

1. `## Phase Index` 与 `#### X.Y` heading，供 `get_context.py --mode phase` 解析；
2. `[workflow-state:STATUS]` / `[/workflow-state:STATUS]` 成对且名称一致；
3. `[required · once]` 步骤在对应状态提示块中有明确提醒；
4. workflow、相关 skill、Codex agent/hook 和 spec 语义同步；
5. 修改后重新启动 Codex 会话或重新加载相关 skill，并运行解析/静态检查。

当前 hook 解析入口：

- `.codex/hooks/inject-workflow-state.py`

不要手工修改 `.trellis/.runtime/` 或 `.trellis/.template-hashes.json`。未来执行
`trellis update` 时，保留上游 baseline hash，并逐项审阅本项目定制冲突。
