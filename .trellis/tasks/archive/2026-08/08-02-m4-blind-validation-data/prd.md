# M4 独立盲测数据设计与物化

## Goal

在独立 worktree 中，为 TreeGuard M4 编制完全虚构、非 Gold 的盲测数据合同，
使后续冻结合同下最多 8 条人工审核场景能够同时评价候选准备质量，以及意图、
召回和语义推荐的实际正确性，并支持 GO_SHADOW 可行性判断。

第一阶段已冻结 Dataset Charter、覆盖蓝图、人工审核规则和隐藏 Oracle 字段语义。
第二阶段在功能合同提交上物化 11 项人工审核记录与 8 条隐藏能力 Oracle；运行时、
基础树和既有 fixture 保持不变。

## Requirements

- 基线固定为 `07cecf3c78fa94524d21e6a570126249d3d1efa2`，分支固定为
  `codex/build-m4-blind-validation-data`，并在独立 worktree 中实施；本机绝对
  路径不属于数据合同。
- 数据工件必须固定：`source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`gold_eligible=false`、`patch_eligible=false`。
- 复用 `fictional-fire-governance-validation` 的 `medium` 完全虚构 holdout
  树；基础树、现有 scenarios、Provider、生成器和 manifest 逐字节保持不变。
- M3 v1/v2/v3 聚合来源记录必须证明 fire medium 的 dataset/resource/version、
  canonical digest 和 fixture SHA 没有进入模型请求；不得读取 M3 正文工件。
- 不读取或复用 M3 的候选正文、Prompt、模型请求/响应、人工语义答案或实验输出
  作为数据来源。允许依据公开合同、Schema 形状、聚合统计、固定状态/错误码和
  当前完全虚构 holdout 的树及其审核元数据规划 M4。
- 最终执行集最多 8 条人工冻结场景。优先 7 条完整链路和 1 条由树证据支持的
  澄清短路；若没有合法歧义，澄清格记录 `NOT_APPLICABLE` 并由完整链路回填。
- 候选审核上限等于现有确定性 planner 对冻结树产生的固定计划单元数；当前复算
  为 11。不得增加计划外替补调用。
- 只有 `ACCEPTED` 或 `REVISED_ACCEPTED` 场景可冻结和执行；`REJECTED` 与
  未审核场景不进入执行分母。
- 隐藏 Oracle 必须支持意图与澄清、召回可接受目标集合、Top-K、推荐可接受动作、
  可接受目标或明确空值、关系类别，以及来源、树 digest、合同版本和审核状态。
- 长期 Oracle 使用稳定虚构节点身份；某次运行生成的候选编号只可在比较器内
  临时解析，不能持久化为 Oracle 目标。
- 隐藏请求与 Oracle 正文不得进入公开聚合报告；公开报告只允许固定状态、finding
  code 和聚合计数。
- 数据任务不实现运行时 Schema、比较器、汇总或 GO_SHADOW/NO_GO 判定。

## Acceptance Criteria

- [x] 已创建独立 Trellis 数据任务，未修改功能分支 M4 任务。
- [x] Dataset Charter 明确目的、非目标、来源、基础树绑定、场景上限和预算。
- [x] 覆盖蓝图定义最多 8 个无正文覆盖格，以及澄清格的合法性与回填规则。
- [x] M3 聚合来源审计确认 fire medium 未进入 v1/v2/v3 模型请求。
- [x] 现有确定性 planner 在 fire medium 上逐字节重放为固定 11 单元。
- [x] 人工 rubric 定义 `ACCEPTED`、`REVISED_ACCEPTED`、`REJECTED` 和停线门槛。
- [x] Oracle 字段语义覆盖完整能力判断，并禁止绑定临时候选编号。
- [x] 第二阶段候选路径、测试、文件所有权和所需冻结合同已记录。
- [x] 第一阶段未生成最终 fixture，未修改 `src/treeguard`、基础树、Provider、
  生成器、正式 fixture、运行时 Schema 或产品文档。
- [x] 未调用外部 LLM、Web、MCP 或其他网络服务。
- [x] 功能合同提交 `d7dff7994167d606aa2e3269c7606860bf22fc41` 已提供并
  fast-forward 同步。
- [x] 用户已明确发出第二阶段实施指令。
- [x] 11 个计划内候选已生成到 ignored staging，并通过确定性 L1/preflight。
- [x] 用户已审核 11 项候选并按建议全部接受；人工审核记录为 20 分钟，未触发
  150 分钟停线门槛。
- [x] 用户已明确要求据此形成测试样本，作为本次正式 fixture 晋升批准。
- [x] 8 项执行集已冻结为 7 条 `PROCEED` 完整链路和 1 条 `CLARIFY` 短路；
  其余 3 项保留接受记录但无 overlay，不进入执行分母。
- [x] 正式独立 manifest、Oracle sidecar、数据 preflight 和数据专属测试已新增，
  没有修改共享文件。

## Definition of Done

- 当前任务通过 `task.py validate`；文档 diff 通过 `git diff --check`。
- 运行完全离线的聚焦元数据/树 digest 检查和配置的 Python unit suite，并报告
  真实结果；未配置工具不声明通过。
- 正式 sidecar 通过逐项来源重放、数据 preflight、聚焦测试和完整离线 suite。
- 停止在第二阶段已验证但未暂存的状态；不 stage、commit、push 或 merge。

## Technical Approach

采用“复用 fire medium 冻结树 + 新增隐藏 sidecar”的方式。数据任务只拥有新的 M4 blind
sidecar、其离线 preflight 和数据专属测试；功能分支拥有 Python 运行时合同、
三阶段比较、记账与门槛判定。Oracle 以现有中型树的 canonical snapshot digest
和稳定虚构 node ID 绑定，在运行时把临时候选 ref 反解为稳定 node ID 后再比较。
第二阶段只消费确定性 planner 的 11 个固定单元，不做计划外替补调用。

第一阶段设计文件：

- [`research/dataset-charter.md`](research/dataset-charter.md)
- [`research/coverage-blueprint.md`](research/coverage-blueprint.md)
- [`research/oracle-review-handoff.md`](research/oracle-review-handoff.md)

## Decision (ADR-lite)

**Context**：M4 要评价端到端正确性；数据分支必须在冻结合同上物化，并避免
发明 Schema、绑定临时候选编号或与功能分支修改同一文件。

**Decision**：第一阶段先冻结概念字段语义、覆盖格、审核和文件边界；第二阶段
同步 `d7dff7994167d606aa2e3269c7606860bf22fc41`，再以运行时单 overlay 合同和
数据自有批量 wrapper 物化 sidecar。现有中型树保持不变；M4 数据以新 manifest
引用 fire medium，不修改现有 manifest。

**Consequences**：正式 sidecar 可逐项重建 11 份 M3 review record 和 8 份 M4
overlay。任何受审字节、树、计划、字段、枚举、Top-K 或比较规则漂移都会使重放
失败并触发停线。

## Out of Scope

- 不新增/修改运行时 Schema、`src/treeguard`、Provider、生成器或基础树。
- 不修改已有 fixture、现有 manifest、功能测试、产品文档或 M4 功能任务。
- 不调用模型或网络服务，不读取 M3 模型流量、候选正文、人工答案和实验输出。
- 不实现准确率计算、路径比较、状态汇总或 GO_SHADOW/NO_GO 判定。
- 不创建 Gold，不声明真实领域或生产准确率。
- 本次批准仅覆盖独立数据 fixture 晋升；不 stage、commit、push 或 merge。

## Research References

- [`research/dataset-charter.md`](research/dataset-charter.md) — 数据边界、冻结树与预算。
- [`research/coverage-blueprint.md`](research/coverage-blueprint.md) — 无正文覆盖格与配额规则。
- [`research/oracle-review-handoff.md`](research/oracle-review-handoff.md) — Oracle 语义、rubric、停线和第二阶段交接。

## Technical Notes

- 采用 `build-treeguard-test-datasets` 的规划模式和 pipeline contract 人工启动门。
- 永久边界：clean-room、非 Gold、非 Patch、外部工具禁用、隐藏正文不公开、
  sidecar 不修改树。
- M4 临时限制：最多 8 条；澄清格条件式；通过只表示 GO_SHADOW。
- 当前事实：复用树为 401 节点、0 `VALUE` envelope 的正式虚构 fire medium
  holdout；planner 固定为 11 单元。M3 v1/v2/v3 聚合记录只绑定 312 节点青岚树，
  未命中 fire dataset/resource/version 或两种 digest。

## 第二阶段当前状态

- ignored staging：`artifacts/fictional-validation/fire-m4-blind-v1/`；
- 11 个计划单元全部产生本地校验候选，构成 7 个主完整链路、2 个澄清候选和
  2 个计划内回填余量；没有计划外调用；
- 9 个完整链路候选在理想 intent 的确定性预览中全部于 Top-8 命中稳定目标；
- L1/preflight 通过，本地只读 Critic 只标记 4 个必须由人裁决的高风险项；
- 用户已在辅助审核基础上完成 11 项审核，耗时约 20 分钟；11 项均为
  `ACCEPTED`，无 revise/reject 或 blocking finding；
- 正式执行集为 `U001`—`U005`、`U007`—`U009`：7 条 `PROCEED` 加 1 条
  `CLARIFY`。`U006`、`U010`、`U011` 接受但不生成 overlay；
- `tests/fixtures/fictional/fire_validation_m4_blind/` 已物化为 `FROZEN`，正式
  数据提交为 `a3acfb2`，并已合入功能分支；没有 push。

## 首轮实验后的处置

- 首轮模型实验在 Intent 阶段发现冻结 request 与 Oracle profile 的可实现性冲突，
  公开归类为 `CONTRACT_INTEGRITY_FAILURE`；召回、推荐和 Semantic 均未执行；
- 原 manifest 与 sidecar 字节、SHA 和 `FROZEN` 生命周期保持不变，`FROZEN` 只表示
  字节冻结，不再表示具备门控资格；
- 当前数据固定降级为诊断/校准输入，不能在修订后重新声明为未见 holdout；
- 功能分支增加 request-aware Oracle 执行资格后，本 fixture 的门控 preflight 应固定
  返回 `DATASET_CONTRACT_INTEGRITY_FAILURE`，但原有字节、来源、预算、记账和篡改
  反例仍需先完整重放；
- 修订 Oracle 必须使用新 dataset/sidecar 身份并重新人工审核，只能承担非盲校准；
  正式 M4 go/no-go 需要另一个运行前密封的数据包。
