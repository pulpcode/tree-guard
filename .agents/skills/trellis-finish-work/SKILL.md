---
name: trellis-finish-work
description: "Wrap up a verified task by safely archiving it, recording a sanitized journal summary, and presenting bookkeeping changes for explicit review."
---

# Finish Work

Use this only after workflow Phase 3.4 has committed the reviewed product/spec work.
TreeGuard disables Trellis auto-commit, so this skill never silently stages or commits
archive or journal changes.

## Step 1: Survey

```bash
python3 ./.trellis/scripts/get_context.py --mode record
git status --porcelain
```

Select the current session task. If the session pointer is absent, show the active-task
candidates and ask for the exact task when the choice is not unique. Do not edit
`.trellis/.runtime/` or guess.

## Step 2: Verify work is ready

- Confirm the PRD acceptance criteria and configured quality checks passed.
- Any uncommitted current-task code, spec, config, or documentation change means stop
  and return to Phase 3.4.
- Preserve unrelated parallel work; do not include it in bookkeeping.
- Confirm task/research content already satisfies
  `.trellis/spec/backend/development-data-boundary.md`.

## Step 3: Archive without Git actions

```bash
python3 ./.trellis/scripts/task.py archive <task-name> --no-commit
```

Archive preserves and moves the task directory, writes `status=completed`, and clears
runtime pointers that reference it. It does not prove that product work was committed.

## Step 4: Record a minimal journal entry

```bash
python3 ./.trellis/scripts/add_session.py \
  --title "会话标题" \
  --commit "work-hash1,work-hash2" \
  --summary "仅记录非敏感中文结论" \
  --no-commit
```

标题、摘要和详细内容优先使用中文；命令、代码标识、公开 hash 和已有清晰英文
无需为了形式统一而改写。摘要可以包含公开提交 hash、固定 code、测试数量和
简短结论，不得包含受保护数据/
代码、真实字段名、Prompt、trace、原始日志、内部路径或模型/专家内容。

## Step 5: Review bookkeeping

Run `git status --short`, inspect every changed task/workspace file, and present one
bookkeeping commit plan. Do not stage or commit it without explicit user approval.
Report separately any pre-existing staged or unrelated dirty paths.
