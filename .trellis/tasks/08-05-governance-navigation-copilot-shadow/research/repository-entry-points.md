# 治理/导航 Copilot 仓库入口研究

## 问题与范围

- 日期：2026-08-05；
- 问题：新的治理/导航 Copilot MVP 应复用哪些现有入口，哪些实验合同不能直接晋升；
- 范围：仅检查本外网仓库已有代码、规范和已接受架构判定，不调用模型或外部服务。

## 仓库依据

- `src/treeguard/workbench_governance.py` 已提供只读 case、异步 operation、Provider 分层、
  私有 sidecar 与人工复核编排；
- `web/src/GovernancePanel.tsx` 已提供自然语言输入、可选选中节点、结构提示、单轮澄清、
  候选比较和专家复核四阶段界面；
- `src/treeguard/change_understanding_v2.py` 已提供固定四键理解与独立角色提议的隔离合同；
- `src/treeguard/semantic_policy_v2.py` 已提供 relation-only 输入输出与本地确定性动作策略；
- `src/treeguard/retrieval_query.py`、`src/treeguard/retrieval_roles.py` 和
  `src/treeguard/retrieval_role_tolerant.py` 包含开发期宽查询、角色候选与边界容忍实现；
- 前一任务的 `research/architecture-convergence-verdict.md` 已接受 D1—D6，并明确 R2 只作
  lexical leg、H1/H2 不晋升、默认 v1 不切换。

## 结论

1. MVP 应复用 Workbench，而不是新增另一套应用或把 CLI 当作首要产品界面；后端仍以
   版本化 case/view 合同作为真实边界。
2. 现有 v2 合同适合作为理解—关系—本地 Policy 的工程骨架，但只证明合同和篡改门禁，
   不能被表述为已有 live、未见或生产能力。
3. 新链路需要显式补足：角色软证据与原始需求宽候选恢复、候选差异视图、
   `AMBIGUOUS/NONE/NEED_EVIDENCE` 状态、人工最终选择和 Shadow 聚合指标。
4. 页面/选中节点已有输入位置，但按已接受架构只能作为低信任软上下文；错误上下文必须
   有聚焦测试证明不会硬裁剪合法候选。
5. 候选列表可沿用 Semantic 最多8项的有界投影习惯，但 Top-1 不能升级为业务真值；即使
   唯一推荐也需要人工确认。

## 限制

- 本研究没有运行模型、召回实验或产品 A/B；
- 没有读取受保护数据、真实树、模型请求/响应或隐藏 Oracle；
- 具体 `NONE` 后是否允许发起新节点旁路属于产品范围选择，不能由仓库事实决定。
