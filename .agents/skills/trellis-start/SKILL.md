---
name: trellis-start
description: "初始化或刷新 Codex 的 TreeGuard Trellis 会话，读取工作流、活动任务、Git 状态和项目规范，再选择下一步。"
---

# 启动 Trellis 会话

## 1. 读取当前状态

```bash
python3 ./.trellis/scripts/get_context.py
```

核对开发别名、Git 状态、session task、活动任务、最近提交和 journal。若输出含
`Trellis update available:`，摘要时保留完整行和命令。

## 2. 读取工作流与规范索引

```bash
python3 ./.trellis/scripts/get_context.py --mode phase
python3 ./.trellis/scripts/get_context.py --mode packages
cat .trellis/spec/backend/index.md
cat .trellis/spec/guides/index.md
```

index 是路由，开始实施时还需读取它链接的适用规范。

## 3. 选择下一步

- 有合法活动任务：读取 `task.json`、`prd.md`、Git diff/commit 和验证证据，
  再使用 `trellis-continue`；不得只凭 status 推断步骤。
- 活动任务缺少 `prd.md`：进入 1.1，使用 `trellis-brainstorm`。
- session pointer 缺失但只有一个与请求匹配的活动任务：明确说明它只是恢复
  候选，再使用 `trellis-continue`；不修改 `.trellis/.runtime/`。
- 没有匹配任务且用户要求多步开发：使用 `trellis-brainstorm` 创建任务。
- 有多个候选：索要精确任务，不能猜或创建重复任务。
- 只读问题：直接回答。
- 用户明确要求一次性微小改动且无需保留决策：说明范围后可直接完成。

Codex 默认 inline：写代码前使用 `trellis-before-dev`，完成后使用
`trellis-check`。不要读取任务 JSONL 中声明的任意路径。

## 快速路由

| 意图 | Skill |
|---|---|
| 新功能/需求不清 | `trellis-brainstorm` |
| 开始实施 | `trellis-before-dev` |
| 恢复任务 | `trellis-continue` |
| 质量检查 | `trellis-check` |
| 重复 bug | `trellis-break-loop` |
| 形成持久规范 | `trellis-update-spec` |

完整规则以 `.trellis/workflow.md` 为准。
