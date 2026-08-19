# 实现导航 Copilot 密封端到端测评

## Goal

为当前 Navigation Copilot 产品纵切增加独立、可回放的密封虚拟树资格测评：通过真实
Workbench HTTP/API 和 `BAILIAN_LIVE` 执行冻结场景，以隐藏 Oracle 分别评分理解、宽召回、
Semantic、Policy、终态和重复性，并输出是否具备进入受保护环境生产 Shadow 审核的固定
资格状态。

## What I already know

- 父任务已接受 D12：全新 clean-room 树、48 条主分母、16 条挑战子集额外两轮，作为生产
  Shadow 硬门；
- 当前产品链路、Provider、API、sidecar 与生产 Shadow manifest/aggregate 已实现并通过
  回归；本任务不能复制或修改这些产品策略；
- 生产 `NavigationShadowQualification` 的部分安全字段是运行常量，不能直接充当隐藏 Oracle
  评分器，否则会形成恒等指标；
- 数据子任务独立拥有新树、scenario、Oracle、审核和 preflight；本任务不得参与场景选择或
  读取数据构造过程中的候选推理。

## Requirements

- 新增独立 evaluation manifest，冻结功能提交、数据提交、树/场景/Oracle 字节、Provider、
  模型、Prompt 版本、48 条主分母、16 条重复子集、调用上限和全部门槛；
- 新增严格 Oracle 合同，至少绑定期望路线、可接受结构 profiles、目标存在性、可接受目标、
  干扰目标、澄清策略、Policy 状态集合和可接受终态联合元组；
- runner 必须通过当前 `create_app`/Workbench Navigation Copilot API 运行 C1，不允许直接
  调用一套简化的理解、召回、Semantic 或 Policy 实现；
- 同一冻结请求确定性计算 R0 原文保底候选视图；R0 不调用模型、不驱动最终 outcome；
- C1 固定使用 `BAILIAN_LIVE`，不得回退到 Simulator/Qwen；Simulator 仅用于不进入分母的
  协议冒烟；
- Oracle 只在模型调用和产品 sidecar 完成后进入评分器；目标、评分答案和 Oracle canary
  不得进入 Prompt、Workbench API、模型投影或普通聚合；
- runner 以 Oracle 驱动一致的受控审核动作：Top-8 命中则选择可接受目标，漏召回则候选外
  纠正，空目标则拒绝；候选外纠正不得计为 Retrieval 命中；
- 所有 48 条预注册 case 都进入主分母；未运行、Provider/合同失败、无终态均按对应阶段失败
  记账，不得删除；
- 逐项运行工件、请求、模型流量和 Oracle 只写 `0700/0600` 私有路径且不可覆盖；公开结果
  只含固定 code、分桶计数、整数分子/分母、比例和资格状态；
- 逐阶段归因固定为 `UNDERSTANDING / RETRIEVAL / SEMANTIC / POLICY / END_TO_END /
  REPEATABILITY`，同一根因不得在多个阶段重复计为独立失败；
- 不修改当前 Navigation Copilot、Provider、召回算法、Prompt、Workbench API/前端或生产
  Shadow 合同。

## Acceptance Criteria

- [x] evaluation manifest、Oracle、逐项 observation、aggregate 与 qualification 状态均有
  版本化精确 Schema、严格字段集、可信重建、hash/replay 和篡改负例；
- [x] Oracle/目标/Prompt/请求/模型响应 canary 不能进入被测模型输入或公开聚合；
- [x] 完整 API runner 在 mock Provider 下覆盖清晰、澄清、弱证据、多目标、空目标、错误
  上下文、候选外纠正和模型降级，并证明单 case 最多两个逻辑阶段；
- [x] R0/C1 对照分别产生 Hit@40、Hit@8、MRR@8、帮助/伤害 case 数，且 R0 不调用模型；
- [x] scorer 按联合元组评分路线、目标、Policy 和终态，未运行/合同/Provider 失败仍留在
  48 条分母；
- [x] 重复性按 16 个 family 聚合三轮结果，不把重复轮扩大为独立分母；
- [x] 固定判定支持 `READY_FOR_PROTECTED_SHADOW`、`HOLD_RETRIEVAL`、
  `HOLD_SEMANTIC_POLICY`、`HOLD_MODEL_CONTRACT`、`DATA_OR_RUN_INVALID` 和
  `INCONCLUSIVE`；
- [x] 推荐门槛逐项实现为整数比较，并与父计划精确一致；
- [x] 聚焦测试覆盖字段/类型/枚举、bool-as-int、顺序、重复、额外/缺失 case、错误来源、
  Oracle 泄漏、公开权限、symlink/FIFO、覆盖、部分发布和聚合允许列表；
- [x] 当前 Copilot、Provider、Workbench、生产 Shadow、后端完整测试和前端测试/构建保持
  通过。

## Definition of Done

- `uv sync --frozen`、完整 `unittest`、前端 test/build、Trellis validate 和
  `git diff --check` 通过；
- 未配置的 lint/typecheck/coverage 不报告为通过；
- 功能提交先于密封数据揭盲冻结；
- 未执行真实资格运行，除非功能提交、数据提交、最终 request plan 和网络用途均已完成独立
  审核与显式运行批准。

## Out of Scope

- 不生成或修改密封树、scenario、Oracle 与 Silver 审核；
- 不调整 Prompt、Top-K、召回权重、embedding、模型参数或产品交互；
- 不访问生产信息树、真实请求、内网 Qwen 或生产 sidecar；
- 不把 Codex Silver、虚拟测评通过或受控审核动作升级为 Gold/专家共识；
- 不执行生产 Shadow，不修改其 D10 分母或门槛。

## Technical Approach

- 独立纯合同/评分模块拥有 Oracle、observation、aggregate 与资格状态；
- 独立 runner 通过真实 Workbench API 编排场景和私有工件；
- 数据 bundle 与 runner 只通过版本化 Schema、提交 hash 和冻结字节交接；
- 现有 `NavigationShadowQualification` 只作产品回归旁证，不参与本测评主评分。

已实现合同固定为 `navigation-copilot-sealed-{trace,observation,aggregate}.v1` 与
`navigation-copilot-sealed-{evaluation-manifest,scenario,oracle}.v2`。v2 要求错误上下文
挑战实际携带父节点引用，并允许弱证据、目标存在时以 `EXIT/PRESENT_NOT_FOUND` 安全退出。
manifest 分别冻结首次理解、澄清重理解和 Semantic 三个
Prompt 版本，并将 endpoint 类别固定为官方百炼兼容端点；功能提交代码树和数据提交历史均
在读取 Provider 配置前校验。公开 scenario 文件与隐藏 Oracle 文件均为按 scenario ref 升序
排列的 JSON 数组，runner 在创建 Workbench app 前完成跨文件来源、树节点与请求 digest
重放。

## Research Reference

- [`../08-05-governance-navigation-copilot-shadow/research/sealed-fictional-e2e-evaluation-plan.md`](../08-05-governance-navigation-copilot-shadow/research/sealed-fictional-e2e-evaluation-plan.md)
