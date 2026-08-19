# Dataset Charter：M4 独立盲测

## 基本声明

| 项 | 第一阶段冻结值 |
|---|---|
| `dataset_ref` | `fictional-fire-m4-blind-v1`（计划值，等待功能合同确认字段名） |
| primary role | `SEMANTIC_CHALLENGE` |
| purpose | 验证 M4 候选准备质量和意图、召回、推荐完整能力的 Shadow 可行性 |
| `source_class` | `CLEANROOM_SYNTHETIC` |
| `fictional` | `true` |
| `derived_from_real` | `false` |
| `gold_eligible` | `false` |
| `patch_eligible` | `false` |
| deterministic seed | `20260802`（用于覆盖格排序、替补选择和复核抽样，不用于造树） |
| candidate review limit | 固定 11 条，等于确定性 planner 的实际计划单元数 |
| frozen execution limit | 最多 8 条 |
| intended mix | 优先 7 条完整链路 + 1 条合法澄清短路 |
| current state | `FROZEN`：11 项已人工接受，8 项正式执行，独立 fixture 已晋升 |

## 目的

1. 衡量信息树理解 Agent 准备的 M4 验证候选是否可答、可绑定、覆盖有效且不泄漏
   Oracle；聚合结果只记录 accept/revise/reject 计数与固定 finding code。
2. 为功能分支提供足以判断意图、召回和语义推荐是否符合人工冻结 Oracle 的隐藏
   数据合同。
3. 在不创建 Gold、不声称生产准确率的前提下，支持零边界失败、阶段误差上限和
   GO_SHADOW 可行性门槛的计算。

## 明确非目标

- 不验证真实图书馆行业知识或生产准确率，不代表真实流量分布。
- 不重复 M3 Prompt 调优，不把 M3 候选、Prompt、请求/响应、人工语义答案或
  实验输出变成 M4 数据。
- 不重建中型树，不修改现有树、场景、Provider、生成器或 fixture。
- 不读取 `fire_validation/scenarios-medium.json` 正文，不从其 Oracle 派生 M4。
- 不自行定义 Python Schema、比较状态、分母、汇总或 GO_SHADOW/NO_GO 逻辑。
- 不让任何模型或单人重复检查冒充第二位审核者。

## 基础树与来源绑定

M4 只引用现有完全虚构 holdout，不复制或改写树：

| 绑定项 | 值 |
|---|---|
| source dataset | `fictional-fire-governance-validation` |
| category | `fictional-fire-validation-category` |
| variant | `medium` |
| resource | `fictional-fire-02-medium` |
| public tree version | `FFV-MEDIUM-V2` |
| benchmark role | `semantic_interference` |
| source policy | `PUBLIC_CATEGORY_CLEAN_ROOM` |
| node count | `401` |
| value envelope count | `0` |
| canonical snapshot digest | `50e6ed21679e105651136d05262434ea56c3beefdf03a2c4941136430e003352` |
| fixture file SHA-256 | `d4ffbc91c462d94cc2daa5246859e8ea0f3d02fd20f1761e8f910a1fcb1d5b0b` |

canonical digest 绑定运行时语义树，文件 SHA-256 绑定被审 fixture 字节。第二阶段
必须使用冻结合同指定的权威 digest 字段；任一值变化都必须停线并重新审核。

fire medium 没有沿用青岚的 curated/background/filler 分类，本任务不得臆造该
分类。每个稳定目标必须由当前树独立支持；M4 不读取或重放现有 fire scenarios
正文，每条候选只能来自 planner 单元并填补本任务蓝图中的一个覆盖格。

## 未见性审计

只检查 M3 v1/v2/v3 的聚合来源段落，结论如下：

- 三次记录均声明输入为 312 节点青岚完全虚构树与 M3 overlay；v2 还声明同一树
  和 13 单元计划，v3 声明 13 个确定性单元。
- fire medium 的 dataset、resource、version、canonical digest 和 fixture SHA
  在 M3 PRD 及三份聚合实验记录中均为零命中。
- 因此在当前仓库聚合证据范围内，fire medium 快照未进入 M3 模型请求。

该结论只证明仓库已有 M3 聚合来源记录的未见性，不外推到仓库外未知实验。审计
未读取 Prompt、候选、请求/响应或人工答案正文。

## 确定性计划绑定

使用现有 `build_tree_diagnostic_profile()` 与
`build_scenario_preparation_plan()` 默认合同对 fire medium 复算：

| 计划项 | 固定值 |
|---|---|
| plan schema | `scenario-preparation-plan.v1` |
| algorithm | `treeguard.scenario-preparation-plan.v1` |
| configured maximum | `16` |
| actual plan units | `11` |
| risk challenge units | `6` |
| branch coverage units | `5` |
| target stages | INTENT 2、RETRIEVAL 6、RECOMMENDATION 3 |
| covered top-level branches | 6/6 |
| plan hash | `b5364de36637719ab75215b20c6b55cefd4ae1a5c11d38aa8bc985a7400dba5b` |

第二阶段候选上限固定为实际 11 单元，而不是 planner 的配置上限 16；每个单元
最多产生一个准备候选，不增加计划外替补调用。树、planner 合同或 plan hash
变化时必须停线并重新审计。

## 场景批次与配额

- 准备候选固定来自 11 个计划单元，人工冻结与执行最多 8 条；reject 后只能从
  尚未选入执行集的既有计划单元回填，不得新增调用。
- 优先冻结 7 条能进入召回和推荐的完整链路。
- 第 8 格优先用于树证据支持的澄清短路。审核者必须能指出至少两个同等合理解释，
  或一个阻止安全进入召回的关键缺口；仅有措辞宽泛不构成合法歧义。
- 若找不到合法歧义，记录格状态 `NOT_APPLICABLE` 和固定理由 code，随后用一个
  完整链路场景回填，最终不制造澄清样本。
- 只有 `ACCEPTED` 或经 revise 后重新审核为 `REVISED_ACCEPTED` 的版本可进入
  frozen execution set。其他状态和旧字节版本不进入执行分母。

## 需要填补的验证缺口

- 当前中型 Provider 只比较意图阶段可观察状态；M4 需要隐藏的完整能力 Oracle。
- 当前语义投影使用临时候选 ref；长期盲测必须改以稳定虚构 node ID 判断。
- 需要覆盖唯一目标、多可接受目标、Top-K 边界、无目标推荐和合法澄清，且不做
  各维度笛卡尔积。
- 需要把候选准备质量和产品执行正确性分开记账，避免 reject 样本污染执行分母。

## 人工预算

| 项目 | 上限 |
|---|---:|
| 准备候选 | 11 条固定计划单元 |
| 冻结/执行 | 8 条 |
| 全量人工首审 | 所有准备候选 |
| 高风险复核 | 所有歧义、Top-K 边界、多目标或显式空目标候选 |
| 固定 seed 随机复核 | 最多 3 条已接受候选 |
| 双人独立复核 | 0（未指定真实第二审核者） |
| 人工总时长 | 150 分钟 |
| 实际记录时长 | 约 20 分钟 |
| 单一候选 revise 轮次 | 最多 2 轮 |
| 整批修复/重审轮次 | 最多 3 轮 |

Charter 通过不等于第二阶段授权；用户已在冻结合同同步后明确发出实施指令。

冻结功能合同现已同步为
`d7dff7994167d606aa2e3269c7606860bf22fc41`。依据数据集构建 Skill 的人工
启动门，收到提交不替代明确的“开始实施/构建候选”指令。

该明确指令现已收到。11 个候选先生成到
`artifacts/fictional-validation/fire-m4-blind-v1/` 并通过确定性重放；随后用户在
辅助审核基础上审完全部 11 项，记录耗时约 20 分钟，并明确接受建议、要求形成
测试样本。同一 AI 会话的本地 Critic 仍只作辅助，不计为人工审核或双审。

最终人工决策为 11 项 `ACCEPTED`、0 revise、0 reject。执行集只含 8 项：7 条
完整链路和 1 条合法澄清；另外 3 项保留接受记录但无 capability overlay，不进入
执行分母。未触发边界、绑定、重复错误、轮次或 150 分钟停线规则。

## 计划所有权

第一阶段只拥有当前 Trellis 任务及其 PRD、Charter、蓝图和审核/交接记录。第二
阶段实际只新增独立 M4 blind 数据路径、离线 preflight 和数据专属测试；未修改
`src/treeguard` 或现有中型 fixture。任何未来必须修改共享文件的发现仍触发停线。
