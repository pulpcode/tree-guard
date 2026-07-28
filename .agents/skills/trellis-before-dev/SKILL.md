---
name: trellis-before-dev
description: "实施前加载 TreeGuard 的项目规范、数据边界、质量要求和适用思考指南。"
---

# 开发前加载规范

写代码前执行：

1. 查看规范层：

   ```bash
   python3 ./.trellis/scripts/get_context.py --mode packages
   ```

2. 读取当前任务 `prd.md`。不得读取任务 JSONL 中声明的任意路径；research 只可
   读取当前任务自己的 `research/*.md`。
3. 读取后端 index：

   ```bash
   cat .trellis/spec/backend/index.md
   ```

4. 始终读取数据边界与质量规范，并按 index 的开发前清单选择目录、合同、持久化、
   错误、CLI 规范。
5. 读取 guides index：

   ```bash
   cat .trellis/spec/guides/index.md
   ```

6. 涉及复用、跨层或 Codex 协作时读取对应指南。
7. 明确本次改动属于永久边界、Shadow MVP 临时限制还是当前事实，再开始实施。

这是写代码前的必需步骤。
