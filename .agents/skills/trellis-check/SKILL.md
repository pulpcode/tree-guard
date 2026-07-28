---
name: trellis-check
description: "依据 TreeGuard PRD、确定性合同、开发数据边界和已配置 unittest 审核并自修外网仓库改动。"
---

# TreeGuard 质量检查

## 1. 确定范围

必须同时检查 tracked 和 untracked；初始化仓库中 `git diff` 看不到新文件。

```bash
git status --short
git diff --name-only
git diff
```

从明确任务路径或 `task.py current --source` 解析任务。无 pointer 时，唯一匹配
任务只能作为明确恢复候选；不修改 `.trellis/.runtime/`，不在多个任务中猜测。

## 2. 读取合同

```bash
python3 ./.trellis/scripts/get_context.py --mode packages
```

始终读取：

- 当前任务 `prd.md`；
- `.trellis/spec/backend/index.md`；
- `.trellis/spec/backend/quality-guidelines.md`；
- `.trellis/spec/backend/development-data-boundary.md`；
- `.trellis/spec/guides/index.md`；
- 按改动选择的具体规范。

不得读取 `check.jsonl` 中声明的任意路径；research 只限当前任务目录。

## 3. 审查并自修

按适用范围检查：

- PRD 验收和 scope；
- Schema、Python 校验、错误码、排序、hash 和 replay 同步；
- 真实字段名、真实/伪名化受保护样例没有进入代码、fixture、诊断、任务或日志；
- adapter → canonical → diff/review → evidence → Provider → local draft →
  expert state/replay → CLI/private sidecar 流程一致；
- helper 所有权正确，没有新增竞争实现或跨模块私有导入；
- 有聚焦 `unittest`，包含相关负例、确定性、tamper、replay 和 leakage；
- 没有 debug output、吞异常、隐式 fallback 或无关重构。

可以直接修改当前外网仓库内任务范围代码并运行 Bash/测试；不得访问或修改生产
环境、生产数据、受保护源码或无关用户工作。产品 AI 结果只写 sidecar/overlay。
不 stage、commit、push、merge、reset、archive 或破坏性清理。

## 4. 运行真实验证

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -v
git diff --check
```

当前未配置 formatter、linter、type checker、coverage、pytest 或第三方 JSON
Schema validator，报告“未配置”，不能报告“通过”。

## 5. 报告

报告检查文件、已修复发现、剩余风险和准确命令/结果。形成可复用合同或非显然
经验时，再使用 `trellis-update-spec`。
