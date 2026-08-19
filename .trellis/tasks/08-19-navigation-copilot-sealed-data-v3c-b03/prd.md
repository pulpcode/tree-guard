# 构建导航 Copilot 密封 clean-room 数据 v3-C b03

## 目标

按已冻结的 b03 密封数据交接合同构造 v3-C `b03` clean-room 密封数据，替代因
执行合同不兼容被拒绝的 `b01` 与已用于 Semantic v2 开发验证的 `b02`，为下一轮
导航 Copilot 密封资格测评提供未参与调参的执行分母。

## 已确认事实

- 交接合同已冻结：`.trellis/tasks/08-05-governance-navigation-copilot-shadow/research/b03-cleanroom-data-handoff.md`（提交 `7d8bd6d`）。
- `b02` 数据任务（08-06-navigation-copilot-sealed-evaluation-data）已冻结并完成，
  其分母已参与 Semantic v2 开发与归因诊断，不能继续承担未见资格结论。
- 数据构造尚未开始；本任务当前只冻结交接边界。

## 范围

1. 按交接合同建立新的 clean-room 构造主体、batch ref、namespace、seed 与稳定身份绑定。
2. 构造未参与调参的虚构 resource 树、公开 scenario、隐藏 Oracle 与 Silver 审核。
3. 冻结数据提交与 execution manifest 后才允许交接执行。

## 非目标

- 不运行被测链路、不接触模型结果；
- 不复用 `b01`/`b02` 的冻结 scenario、Oracle、manifest 或 digest；
- 不修改 Prompt、Provider、Retrieval、Semantic、Policy 或 Workbench。

## 验收

- 满足交接合同中冻结的全部数据边界、泄漏隔离与 preflight 门禁；
- 数据提交不包含模型请求/响应、Prompt、实验结果或受保护路径。
