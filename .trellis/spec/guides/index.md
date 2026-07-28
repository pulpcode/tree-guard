# TreeGuard 思考与协作指南

这些指南补充后端规范，回答三个高频问题：

1. 该能力是否已有唯一所有者？
2. 改动跨越哪些信任、序列化或副作用边界？
3. Codex 主代理与子代理如何在不泄漏、不覆盖工作的情况下协作？

## 指南

| 指南 | 何时使用 |
|---|---|
| [代码复用](./code-reuse-thinking-guide.md) | 新增 helper、parser、hash、serializer、writer、错误码或重复策略 |
| [跨层思考](./cross-layer-thinking-guide.md) | 数据跨 source、确定性审查、模型投影、专家状态和 CLI/file 边界 |
| [Codex 协作](./codex-collaboration.md) | 开始/恢复任务、并发委派、审查、Git 交接或修改 Codex/Trellis 工作流 |

## 触发条件

以下情况读代码复用指南：

- 可能已有相似函数、常量、精确字段集或校验分支；
- 新 helper 会复制一个正被跨模块私有导入的能力；
- 合同字段涉及 Schema、Python、serializer、hash 或测试。

以下情况读跨层指南：

- 一个值跨两个以上模块或信任边界；
- 内部工件投影给模型或聚合报告；
- 涉及文件、Provider、未来 API adapter 或专家状态迁移；
- 外网开发需要受保护环境产生的工件或外部查询。

以下情况读 Codex 协作指南：

- 开始或恢复 Trellis 任务；
- 并发子任务可能接触相邻文件；
- 修改 workflow、hook、skill、agent 或任务上下文规则；
- check 代理要自修代码，或准备提交/归档。

## 先搜索

```bash
rg -n "symbol_or_value" src tests contracts docs .trellis/spec
rg --files src tests contracts docs .trellis/spec
```

搜索结果只是证据，不代表可以复用私有 helper，也不允许让完整内部表示跨越
数据边界。
