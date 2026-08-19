# M4.9 Oracle、审核与交接设计

## 功能合同绑定

本数据任务不创建或放宽运行时 Schema。第二阶段必须精确复用功能基线中的现有合同：

| 能力 | 冻结值 |
|---|---|
| feature commit | `d52e92341b1d081c45c9e4594b98323327379da5` |
| Intent Prompt | `treeguard.change-intent.zh.v4` |
| Semantic Prompt | `treeguard.semantic-recommendation.zh.v4` |
| retrieval | `treeguard.lexical-structural-retrieval.v1` |
| overlay | `scenario-capability-overlay.v1` |
| run | `scenario-capability-run.v1` |
| repeatability report | `scenario-repeatability-report.v1` |
| repeatability policy | `treeguard.m45-sealed-repeatability-gate.v1` |
| request-aware policy | `treeguard.capability-oracle-request-policy.v1` |
| Semantic contract attempts | 最多 2 次逻辑尝试 |
| transport recovery | `max_transport_retries=1`；只恢复一次 Semantic 连接失败 |
| maximum wire calls | 每个 Semantic 单元最多 3 次，执行前由请求计划复算 |

精确模型、endpoint、请求选项、超时、Intent/Semantic 尝试上限与三轮最大调用预算
已冻结在 `silver-runtime-freeze.md`。运行 manifest 必须逐项匹配；任何差异都在网络
前拒绝。

## Oracle wrapper 概念 Schema

`m49-sealed-oracle-sidecar.v1` 只是数据侧 wrapper 计划名，不是新的运行时 Schema。
每个可执行项仍须确定性重建一个现有 `scenario-capability-overlay.v1`。

### 数据与来源闭包

- `dataset_ref`、`source_class`、`fictional`、`derived_from_real`；
- `gold_eligible=false`、`patch_eligible=false`；
- tree canonical digest、fixture SHA、场景批次 SHA、Oracle SHA；
- feature commit、合同版本、运行配置 digest；
- scenario ref、覆盖格、受审最终字节 digest 和审核状态。

### Intent Oracle

- `expected_route`: `PROCEED` 或 `CLARIFY`；
- 精确覆盖现有 12 个 Intent 字段的比较政策；
- 只有 request 中显式且非未知的结构化 hints 可用 `EXACT_ONE_OF`；
- 没有逐字段证据绑定的自由文本/list 字段保持 `NOT_COMPARED`；
- `PROCEED` 至少一个有区分力的结构字段可比较；
- `CLARIFY` 要求非空原子问题，并以歧义类别/必须消解的差异评分，不做逐字匹配。

### Retrieval Oracle

- `retrieval_applicable`；
- 可接受稳定虚构 node ID 集合；
- 固定 Top-K 和允许状态；
- 默认 Hit@K 规则，以及 Top-K 边界格的精确边界声明；
- 当次 `C001` 等临时引用必须先映射回同次候选集中的稳定 node ID。

### Semantic Oracle

- `recommendation_applicable`；
- 一到多个完整的可接受联合结果：`action + stable target/null + relation/null`；
- `MUST_BE_NULL` 与非空目标互斥；
- 明确标记首选与安全替代，但两者都必须有冻结树证据；
- kind/cardinality/跨分支硬冲突不得作为安全替代接受。

模型 rationale、候选排序、运行时临时 ref 和运行后发现的答案不属于 Oracle。

## 审核等级

本轮已冻结选择 `CODEX_ASSISTED_SILVER`，`gate_eligible=false`。下表中的其他等级
只说明边界，不是本轮可切换选项。

| 等级 | 允许做什么 | 不允许声称 |
|---|---|---|
| `CODEX_ASSISTED_SILVER` | 检查合同、可答性、目标闭包并运行诊断实验 | Gold、正式泛化门禁、生产准确率 |
| `HUMAN_SCREENED_SYNTHETIC` | 人工逐项冻结后进入预注册 Shadow 门禁 | 真实领域 Gold、生产代表性 |
| `REAL_HUMAN_GOLD` | 本任务无权创建 | 不适用 |

本轮实验可以验证流程是否走通并产生 `PROMISING`、`NOT_PROMISING` 或
`INCONCLUSIVE` 诊断，但不能输出正式 `GO_SHADOW`。若未来需要正式门禁，应在模型
尚未看见正文时另立任务并冻结人工审核；模型运行后补审不能恢复同一批数据的未见性
门禁资格。

## 逐项审核 rubric

1. 数据来源五项固定值正确，无历史正文派生和边界泄漏。
2. 树、场景、Oracle、合同提交、运行配置和受审字节 digest 闭包一致。
3. 属性主体、单体/成员/集合范围明确，不存在笛卡尔积或模板化扩张。
4. request 在没有“选中节点”的情况下仍自然、可理解；需要选中上下文的样本不得
   混入自由对话主集。
5. route 合法；澄清来自 request 的真实互斥解释，不是候选冲突。
6. 可接受 Intent profiles 不要求模型复述无来源自由文本。
7. 召回目标集合完整，Top-K 可确定性复算，稳定目标均存在。
8. Semantic 的动作、目标和关系联合合法，安全替代有独立树证据。
9. 每条只承担一个主覆盖风险，且确实增加覆盖。
10. 模型投影不含 Oracle、稳定目标、审核结论、Prompt/响应或泄漏 canary。

审核状态只允许 `PENDING`、`ACCEPTED`、`REVISED_ACCEPTED`、`REJECTED`；修改字节后
旧审核立即失效。公开报告只保留状态计数、固定 finding code、分钟数和覆盖计数。

## 评分与预注册门槛

正式 `HUMAN_SCREENED_SYNTHETIC` 运行沿用已提交的重复性门槛，不看结果改线：

1. 数据边界、来源、合同完整性、结果记账和 Oracle 泄漏为零失败；
2. Intent 与 Semantic 重试后最终合同合法率分别至少 98%；同时报告首发合法率；
3. 真正执行的确定性召回 Hit@K 为 100%；
4. 三轮任一轮端到端完整匹配至少 18/24；
5. 至少 18/24 场景三次全部端到端匹配；
6. 澄清 precision、recall 和 3/3 稳定数单列，不用“问题非空”冒充正确；
7. 被本地门禁接受的硬结构冲突错误复用为 0，否则直接 `NO_GO`。

上游失败按适用性短路，不重复记为下游错误；Semantic 合同分母只含实际调用单元。
三轮不取最好一次或多数票。Codex-assisted Silver 可计算同一组指标，但决定必须使用
不同标签，不能输出正式 `GO_SHADOW`。

## 第二阶段交接顺序

1. 用户审阅并批准本阶段四份规划文件。
2. 功能侧验证 `silver-runtime-freeze.md`，并把相同配置和 wire 调用上限写入私有
   运行 manifest。
3. 用户明确批准开始生成；数据侧构建新树与 24+最多 6 条候选到 staging。
4. L1 全量门禁；失败回到最早缺陷阶段，最多三轮。
5. L2 只读 Critic 输出固定 code；不改数据、不授予 Gold。
6. 完成已选定的 Codex-assisted Silver 审核；在首次模型调用前冻结最终 24 条和全部
   digest，且 `gate_eligible=false`。
7. 数据侧只向功能侧交付 identity、规模、覆盖计数、合同版本和 digest；不在聊天中
   展示隐藏正文。
8. 功能侧冻结精确请求计划与运行 manifest，再读取执行数据并运行三轮。
9. 私有结果冻结后揭盲评分，仓库只保存允许列表聚合和固定 code。
10. 一旦揭盲，数据永久转为回归/校准；下一轮正式门禁需要另一套新密封数据。

## 计划验证

第二阶段至少实现：

- source flags、未知字段、bool-as-int、节点/场景数和 18+6 组成门禁；
- tree/fixture/scenario/oracle/review/config digest 及可信重建；
- parent/child、稳定目标和 coverage ref 完整性；
- subject/facet 允许表、属性所有权、重复向量和笛卡尔积密度检查；
- Oracle 不进入模型投影的 canary；
- 24×3 的 route 集合一致、round 内唯一和调用上限；
- 余量不能在首次请求后启用，rejected/pending 不进入分母；
- 公开聚合不含 request、节点、目标、hash、Prompt、响应或审核正文；
- 聚焦数据测试、聚焦功能合同测试、完整后端测试、前端回归/构建、Trellis validate
  和 `git diff --check`。

## 第一阶段停点

该历史停点已由用户明确发出的第二阶段实施指令解除，随后 fixture 晋升也得到单独
批准。当前完成到 `FIXTURE_PROMOTED_AWAITING_RUNTIME_PLAN`：最终候选、Oracle、
L1、Silver 审核和正式 fixture 已冻结；模型调用数仍为 0，运行计划和实验结果尚未
生成。

晋升只消费最终冻结批次，没有从三个 rejected round 中挑选样本，也没有修改场景
正文或 Oracle。下一步必须先冻结运行时入口、72 个正式观测的精确记账和请求正文
digest；fixture 晋升本身不授予执行资格。
