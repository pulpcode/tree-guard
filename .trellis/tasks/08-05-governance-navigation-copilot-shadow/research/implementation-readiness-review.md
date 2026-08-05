# 实施前就绪审查

## 已加载边界

- 永久边界：模型输出不可信；确定性代码负责来源、状态、排序、回放和安全动作；产品输出
  只写 sidecar，不获得生产树、数据库、Gold 或 Patch 权限。
- Shadow 临时限制：只读 resource 快照、单进程 case、最多8个展示候选、人工最终处置。
- 当前事实：v1 Workbench 已有 case/operation/私有 sidecar；v2 只有隔离的四字段理解和
  relation-only Policy，尚未接入 live Provider 或默认 Workbench。

## 推荐职责所有权

- 新的确定性 Copilot case、候选恢复、状态、人工终态和聚合记账由独立核心模块拥有；
  不把策略塞入 FastAPI 或 React。
- `ai_review.py` 复用既有百炼、Qwen、loopback 传输边界，为 v2 增加窄 Provider；不得复制
  HTTP、配置、重试或 trace 实现。
- `workbench_governance.py` 只编排新核心、Provider 和不可覆盖 sidecar；默认 v1 服务保持
  不变，通过隔离 feature path 暴露 Copilot。
- `web.py` 和 `web/` 只处理版本化允许列表 DTO、操作轮询和人工动作，不复制领域 Policy。

## 阻塞冲突：澄清路径的调用预算

当前 PRD 同时规定：

1. 首次调用生成结构理解和可选澄清问题；
2. 回答后最多允许一次澄清；
3. Semantic 是第二个模型阶段；
4. 常规及首版路径不允许第三次模型调用。

清晰路径可以是“理解 → Semantic”两次；但澄清路径若重新理解回答后再做 Semantic，会变成
三次。若完全不重新理解，则原结构意图可能仍包含已解决的问题或与回答冲突，不能安全地
进入 relation-only Semantic。

## 推荐解法

保持单 case 总预算两次：

- 清晰路径：`理解 → 宽召回 → Semantic → 本地 Policy`；
- 澄清路径：`首次理解 → 人工回答 → 重新理解 → 宽召回 → NEED_EVIDENCE`；不再调用
  Semantic，用户根据可信树差异主动选择、候选外纠正、拒绝或退出。

该解法不伪造已解决的结构意图，也不放宽模型调用预算；代价是澄清 case 缺少模型关系比较，
必须在 Shadow 聚合中单独计量，不能与完整路径合并计算 Semantic 成功率。

## 决策结果

上述推荐已由用户接受并固化为 PRD D11。实施计划必须以单 case 两次逻辑模型调用为硬
上限；改变澄清路径调用数需要重新打开 PRD，不得在 Provider 或重试层暗中扩张。

## 被拒绝前不能实施的替代

- 放宽澄清路径为三次模型调用：交互完整，但直接改变已冻结范围和成本上限；
- 不重新理解，直接把回答拼入召回/Semantic：调用少，但 Semantic 绑定陈旧结构意图；
- 本地从自由文本回答猜测结构字段：把不可信自然语言解析伪装成确定性事实。
