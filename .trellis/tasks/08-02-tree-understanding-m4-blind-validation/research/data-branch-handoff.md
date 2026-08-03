# M4 功能合同到数据分支的第二阶段交接

## 当前状态

- 功能合同已以 `d7dff79` 提交，数据分支同步后以 `a3acfb2` 冻结完全虚构 fixture，
  两者已在 `codex/tree-understanding-agent` 集成；没有 push；
- 首轮实验发现 v1 request 与 Intent Oracle profile 不可同时满足，数据字节保持
  不变并降级为诊断/校准输入；该结果不是模型准确率；
- 后续功能合同增加 request-aware 执行资格。历史 overlay 可做来源重放，但当前 fire
  v1 在 Provider 前固定失败，不能继续承担 go/no-go。

## 功能分支拥有的冻结候选

| 合同 | 版本 / 文件 |
|---|---|
| 完整能力审核 overlay | `scenario-capability-overlay.v1` / `contracts/scenario-capability-overlay.v1.schema.json` |
| 单场景分阶段运行 | `scenario-capability-run.v1` / `contracts/scenario-capability-run.v1.schema.json` |
| 公开聚合门槛报告 | `scenario-capability-report.v1` / `contracts/scenario-capability-report.v1.schema.json` |
| Python 构造、解析、比较与门槛 | `src/treeguard/scenario_capability_validation.py` |
| 功能验收 | `tests/test_scenario_capability_validation.py` |

M3 的 `scenario-review-action.v1`、`scenario-review-record.v1` 和
`scenario-review-intent-run.v1` 字节与语义保持不变。

## 单条 Oracle 映射

每个可执行数据项必须能够从可信 M3 reviewed scenario、同一 tree 和同一 plan 重建
一个精确的 `ScenarioCapabilityOverlay`：

- 固定边界：`CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`semantic_approval=false`、
  `gold_eligible=false`、`patch_eligible=false`；
- 审核状态只允许 `ACCEPTED`、`REVISED_ACCEPTED`，`review_round` 只允许 1 或 2；
- 来源绑定：reviewed hash、snapshot hash、plan hash，以及 reviewed request 加完整
  capability Oracle 的规范 digest；
- `expected_route`：`PROCEED` 或 `CLARIFY`，并与 M3 observable `draft_status` 一致；
- intent profile：`P001` 起的有序 profile；字段与 policy 精确服从 overlay Schema。
  标量可用 `EXACT_ONE_OF`，标量或 tuple 可用 `NON_EMPTY`，tuple 可用 `EMPTY`，
  显式忽略用 `NOT_COMPARED`；M4 v1 每个可执行 profile 必须完整列出 12 个字段，
  非空结构化 hint 必须精确比较，`UNKNOWN`/`null` hint 与无逐字段来源绑定的字段
  必须 `NOT_COMPARED`；模型 rationale 不进入 Oracle；
- retrieval：完整链路必须 `applicable=true`，状态使用既有三项枚举；有目标时只允许
  `CANDIDATES_READY`，目标保存稳定虚构 node ID，`top_k` 固定在 1–20；无目标时不得
  接受 ready 状态；
- recommendation：完整链路必须 `applicable=true`；每个可接受答案保存完整的
  `action + stable target/null + relation/null` 联合 tuple，不得拆成三个集合；
- 澄清路径的 retrieval/recommendation 均为不适用空合同。

长期 Oracle 不保存运行级 `C001`—`C008`。运行器通过同次候选集将模型引用映射回
稳定 node ID 后再比较。

## 数据 wrapper 与 manifest 所有权

功能分支只定义**单条运行时 overlay**。数据分支继续拥有 dataset manifest、批量
`oracle-sidecar.json` wrapper、fixture SHA、dataset/resource/version selector、
`feature_contract_commit` 和数据专属 preflight：

- wrapper 可以记录上述数据集级绑定，但不得把额外字段塞进单条 overlay；
- 每个 eligible item 必须把精确 overlay payload 交给
  `ScenarioCapabilityOverlay.from_dict()` 做可信重建；
- wrapper 若嵌入 M3 action/reviewed record，必须分别服从既有 v1 Schema，并保留
  candidate/batch/projection/plan/profile/tree 的可信回放输入或明确引用；
- 数据集公开报告不得复用私有 overlay `to_dict()`，只能使用
  `CapabilityGateReport.to_dict()` 的聚合允许列表；
- 数据分支不修改 `src/treeguard`、本页所列三个合同、既有 fire tree/scenarios、
  Provider 或共享 manifest；发现必须改共享字段时停线回到功能分支。

## 执行入口与记账

- 单条执行：`run_reviewed_capability_scenario(...)`；
- 数据准备聚合：`ScenarioPreparationMetrics`；
- 批次门槛：`build_capability_gate_report(...)`；
- 阶段状态：`MATCH`、`MISMATCH`、`NOT_RUN`、`RUN_FAILED`；
- 上游不匹配或运行失败使后续阶段固定 `NOT_RUN`，后续仍保留适用分母，但不重复
  增加 mismatch/run-failed；
- 公开硬失败只允许：`DATA_BOUNDARY_FAILURE`、`SOURCE_BINDING_FAILURE`、
  `CONTRACT_INTEGRITY_FAILURE`、`RESULT_ACCOUNTING_FAILURE`；
- 候选质量门和执行门必须同时 PASS，且硬失败为空，才输出 `GO_SHADOW`；这不是
  Gold、生产准确率或自主决策批准。

当前没有新增 CLI、Workbench API、数据库或文件 loader。第二阶段数据测试可以直接
调用上述纯 Python 入口；如果最终需要产品文件加载或 UI，另立任务，不在数据分支
临时实现。

## 数据分支同步后的最低验收

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -p 'test_scenario_capability_validation.py' -v
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -p 'test_fire_m4_blind_validation_data.py' -v
git diff --check
```

联合回归仍需完整 `python -B -m unittest discover -s tests -v`。项目未配置第三方 JSON
Schema validator、formatter、linter、type checker 或 coverage，不能把未配置项报告
为通过。
