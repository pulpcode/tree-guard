---
name: trellis-continue
description: "恢复 Codex 中的 TreeGuard Trellis 任务，通过 PRD、实际差异、提交和验证证据定位步骤。"
---

# 恢复当前任务

## 1. 加载上下文

```bash
python3 ./.trellis/scripts/get_context.py
python3 ./.trellis/scripts/get_context.py --mode phase
git status --short
```

若 `CURRENT TASK` 为空：

- 只有一个与请求匹配的活动任务时，把它作为明确恢复候选；
- 零个或多个候选时索要精确任务；
- 不修改 `.trellis/.runtime/`，不猜测，不创建替代任务。

## 2. 校验任务路径

任务必须是仓库相对 `.trellis/tasks/<name>/`，不含 `..`，不在 `archive/`，
realpath 不得通过 symlink 逃逸，并且存在 `task.json` 和 `prd.md`。

## 3. 用证据定位步骤

`task.json.status` 只给出大阶段：

- `planning` 且无 PRD：1.1 `trellis-brainstorm`；
- `planning` 且 PRD 尚未可实施：继续 1.1/1.2；
- `planning` 且 PRD/验收可实施：1.3 选择固定 spec 上下文，然后 1.4
  `task.py start`；
- `in_progress`：检查 PRD checkbox、tracked/untracked diff、相关 commits 和
  最近验证；未实施进 2.1，未充分检查进 2.2，证据完整才进 Phase 3；
- `completed`：只有工作提交存在且满足 finish 条件时进入归档。

Codex 不以 `implement.jsonl` / `check.jsonl` 是否存在或已填充作为门禁，也不
读取其中的任意路径。无法证明某一步完成时，重跑该步骤。

## 4. 加载具体步骤

```bash
python3 ./.trellis/scripts/get_context.py \
  --mode phase --step <X.X> --platform codex
```

按 `.trellis/workflow.md` 顺序继续；发现 PRD、合同或权限问题时允许返回 Plan。
