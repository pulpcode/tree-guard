# 治理助手检索与决策架构收敛 PRD（草案）

## 背景

M4.9 与 M5 已经把端到端失败拆分到 Intent、Retrieval 和 Semantic 三个阶段，证明现有实验具有诊断价值，但尚不足以证明产品链路可进入生产试验。当前主要不确定性已经不再是“是否继续调 Prompt”，而是四项彼此耦合的架构选择：最小 Intent 合同、稳定检索表示、候选召回方式，以及 Semantic 阶段的职责边界。

本任务先使用已经暴露的完全虚构 M4.9/M5 数据做校准和 A/B，不新增盲测数据、不进行新的模型资格宣称。架构冻结后，才应使用新的未见数据做一次独立确认。

## 目标

形成一条可实现、可测量、可解释的 MVP 主链路，并用预注册实验选择方案：

1. 冻结用户自然语言到检索查询所需的最小 Intent 字段；
2. 定义树节点及其上下文的稳定、可版本化检索表示；
3. 比较现有词法/结构基线与最小候选检索方案；
4. 冻结 Semantic 只做候选语义判定，还是同时选择动作；
5. 形成架构决策记录和后续未见数据验收门槛。

## 已知事实

- 当前召回是第一版词法与结构规则基线，不代表真实生产召回已经解决。
- Intent 中的自由文本字段会影响召回，但其最小必要集合和字段级质量尚未冻结。
- M5 暴露了召回不足与证据不足之间的阶段边界问题；错误阶段归因会误导后续优化。
- 已暴露的 M4.9/M5 样本只能用于诊断与方案选择，不能再次作为泛化证据。
- 产品常规链路最多保留两次 LLM 调用，并保持只读、证据可追踪和人工可接管。
- M0–M3 的“根据信息树生成代表性验证问题”属于验证准备能力，不等同于本任务的在线理解与检索主链路。

## 待冻结的产品链路

```text
用户自然语言
  → Intent：最小结构化约束；必要时澄清
  → Retrieval：稳定查询表示 + 节点表示 → Top-K 候选
  → Semantic：基于候选证据判定关系/可执行性
  → Deterministic policy：动作、空目标、安全降级与排序
  → 带证据的回答或澄清
```

其中 `Deterministic policy` 是否吸收全部动作选择，是本任务必须明确的决策，不预先假定结论。

## 方案选择原则

### Intent

- 只保留对澄清、召回或安全判定有可证明增益的字段；
- 枚举、基数、作用域等机器可校验约束优先于开放式摘要；
- 不要求模型做确定性排序、去重或可由本地程序完成的格式整理；
- 字段缺失与字段矛盾必须有安全错误码，不能只记录笼统的内容非法。

### Retrieval

- 基线保持不变，候选方案通过新版本接口并行比较；
- 节点表示至少评估：节点自身文本、祖先路径、节点类型、相邻结构和可用约束；
- 检索表示不得依赖界面“当前选中节点”；它只能作为可选上下文，并须防止错误选中污染召回；
- 首轮只比较一个最小候选方案，避免同时改写全部阶段后无法归因。

### Semantic 与动作

- Semantic 只能看到受控 Top-K 候选及必要上下文；
- 优先评估“模型判定候选关系，本地策略映射动作”的收缩方案；
- 如果模型动作选择确有独立增益，必须用专门消融实验和安全错误率证明；
- 召回无证据不得伪装成 Semantic 拒绝，Semantic 拒绝也不得反向算作召回失败。

## 预注册实验

### 数据使用

- 仅使用已暴露的 M4.9/M5 完全虚构样本进行开发期校准；
- 不新增、查看或反复调整未见验收集；
- 不用校准集结果宣称模型已经泛化或达到生产资格。

### 比较组

- A：当前 Intent + 现有词法/结构召回 + 当前 Semantic/动作链路；
- B：冻结后的最小 Intent + 稳定检索表示 + 单一候选召回 + 收缩后的 Semantic/确定性策略。

### 指标

- Intent：合同通过率、字段级错误分布、澄清必要性判定；
- Retrieval：Recall@8、Recall@20、MRR、hard-negative 误召回、Top-K 稳定性；
- Semantic：候选关系准确率、安全动作错误率、空目标正确率；
- 端到端：正确证据命中、正确澄清、安全降级、重复运行一致性；
- 工程约束：常规路径 LLM 调用数、P50/P95 时延、失败可归因率。

具体分母、可接受目标集合和阈值必须在运行候选实现前写入实验合同，禁止看结果后改门槛。

## 验收标准

- 给出一份明确的架构决策记录，四项核心选择均有结论和排除理由；
- A/B 使用相同输入、相同 Oracle 和固定分母，可确定性重放；
- 候选方案至少改善预注册的召回主指标，且 hard-negative 与安全动作不发生不可接受退化；
- 每个失败能稳定归因到 Intent、Retrieval、Semantic、Policy 或合同/执行层；
- 冻结后再定义一次新的未见数据确认实验，未见实验不得继续用于调参；
- 在新的未见确认通过前，不宣称具备生产资格。

## 非目标

- 不接入真实生产信息树或真实用户数据；
- 不在本任务中生成新的盲测集；
- 不把验证问题生成 Agent 产品化；
- 不增加第三次及更多常规 LLM 调用；
- 不允许模型直接修改生产树或自动提交治理补丁；
- 不通过继续扩大 Prompt 来掩盖检索或阶段边界问题。

## 首轮研究问题

1. 哪些 Intent 字段对召回和安全判定确有增益，哪些只是重复表达？
2. 当前节点文本、路径与结构信息如何进入词法召回，失败集中在哪些表示缺口？
3. 在不引入大规模基础设施的前提下，BM25/加权词法、稠密向量或混合检索哪个是最小可行候选？
4. 当前 Semantic 输出中的动作选择是否提供了关系判定之外的真实增益？
5. 哪些 M5 错误是阶段归因错误，而不是模型能力不足？

## Research References

- [`research/repository-facts-and-options.md`](research/repository-facts-and-options.md)：当前
  Intent、召回和 Semantic 职责的仓库事实与三个候选方向。
- [`research/retrieval-ab-pre-registration.md`](research/retrieval-ab-pre-registration.md)：
  Retrieval A/B 的固定分母、查询视图、门槛与失败归因。
- [`research/retrieval-b1-calibration-result.md`](research/retrieval-b1-calibration-result.md)：
  B1 首次冻结运行、算法缺口、Oracle 表达缺口与停线决定。
- [`research/retrieval-b2-pre-registration.md`](research/retrieval-b2-pre-registration.md)：
  Oracle v2 边界、B2 显式强锚点语法、原门槛复用与升级规则。
- [`research/retrieval-b2-calibration-result.md`](research/retrieval-b2-calibration-result.md)：
  B2 首次冻结结果、唯一 Top-8 失败的归因与 B3 升级边界。
- [`research/retrieval-b3-pre-registration.md`](research/retrieval-b3-pre-registration.md)：
  B3 完整短语匹配、固定实验门槛和停止继续语法校准的规则。
- [`research/retrieval-b3-calibration-result.md`](research/retrieval-b3-calibration-result.md)：
  B3 冻结失败、5 个第 2 名目标的角色归因与停止词法调优决定。
- [`research/retrieval-role-upper-bound-pre-registration.md`](research/retrieval-role-upper-bound-pre-registration.md)：
  原文 span 角色合同、R1 唯一变化、固定门槛和后续决策规则。
- [`research/retrieval-role-upper-bound-result.md`](research/retrieval-role-upper-bound-result.md)：
  R1 首次冻结 PASS、可得结论、限制与下一实验边界。
- [`research/retrieval-role-model-extraction-pre-registration.md`](research/retrieval-role-model-extraction-pre-registration.md)：
  小模型原文角色 span 合同、18 条固定分母、调用预算与冻结 R1 下游门槛。
- [`research/retrieval-role-model-v1-result.md`](research/retrieval-role-model-v1-result.md)：
  v1 首次冻结 FAIL、合同与角色语义分层结果及后续诊断边界。
- [`research/retrieval-role-model-v1-diagnostic-result.md`](research/retrieval-role-model-v1-diagnostic-result.md)：
  v1 重放稳定复现两个 TARGET super-span 与14/16召回。
- [`research/retrieval-role-model-v2-pre-registration.md`](research/retrieval-role-model-v2-pre-registration.md)：
  唯一通用目标边界规则、原门槛复用与停止继续调 Prompt 的决策。
- [`research/retrieval-role-model-v2-result.md`](research/retrieval-role-model-v2-result.md)：
  v2 冻结 FAIL、停止 Prompt 调整与转向容错检索表示的架构结论。
- [`research/retrieval-role-boundary-tolerant-r2-pre-registration.md`](research/retrieval-role-boundary-tolerant-r2-pre-registration.md)：
  R2 唯一算法变化、固定门槛和失败后的停止规则。
- [`research/retrieval-role-boundary-tolerant-r2-result.md`](research/retrieval-role-boundary-tolerant-r2-result.md)：
  Silver 与小模型 R2 首次冻结 PASS、可归因结论和未见确认边界。
- [`research/retrieval-r2-sealed-confirmation-contract.md`](research/retrieval-r2-sealed-confirmation-contract.md)：
  R2 未见数据隔离、28条固定分母、两轮门槛和架构分流规则。
- [`research/retrieval-r2-sealed-confirmation-result.md`](research/retrieval-r2-sealed-confirmation-result.md)：
  首次有效密封结果、聚合召回指标、评测器分母缺陷与混合召回升级结论。
- [`research/retrieval-h1-hybrid-pre-registration.md`](research/retrieval-h1-hybrid-pre-registration.md)：
  H1 的 embedding 模型、表示、固定 RRF、开发集分母、门槛与失败降级。
- [`research/retrieval-h1-hybrid-result.md`](research/retrieval-h1-hybrid-result.md)：
  H1 首次有效 A/B、召回增益不足、安全边界结果与停止调参决定。
- [`research/retrieval-h2-local-embedding-options.md`](research/retrieval-h2-local-embedding-options.md)：
  本地开源 embedding 候选、开发机约束与 BGE small 选型。
- [`research/retrieval-h2-local-pre-registration.md`](research/retrieval-h2-local-pre-registration.md)：
  H2 唯一变量、新数据配额、门槛、运行时边界与停止规则。

## 当前已收敛事实

- M5 的理想 retrieval seed 在 16 个有目标场景上 Recall@8=16/16、MRR=1.0，另有
  2 个正确空结果，因此理想 Intent 重放不能用于证明候选检索获得提升。
- 18 个 `PROCEED` 的 Intent Oracle 对全部模型自由文本均为 `NOT_COMPARED`，但当前
  Retrieval 主要依赖这些自由文本；这是明确的阶段接口缺口。
- 首轮实验必须先解耦“可靠查询来源”和“模型解释”，不同时修改 Prompt、Semantic
  或模型版本。

## Decision D1（ADR-lite）：Retrieval 查询权威来源

**Context**：当前 Intent Oracle 不比较模型自由文本，但 v1 Retrieval 主要依赖这些
自由文本，造成 Intent `MATCH` 与召回输入质量脱节。

**Decision**：采用方案 B。原始 requirement text 是稳定主查询；只叠加本地校验的
节点类型、值类型、基数和可选 parent 约束。模型 subject/confirmed facts 只能作为
可关闭的低权重扩展；assumptions、evidence gaps 和 clarification question 不进入主查询。

**Consequences**：召回不再因模型遗漏关键业务词而失去全部信号；错误点击只能软加权；
模型同义改写的潜在增益不会被默认信任，只有独立消融证明后才保留。v1 生产入口保持
不变，候选 B 先通过离线 A/B 再决定晋升。

## 第一实现切片

1. 在确定性 core 中增加版本化 `RetrievalQuery` 与 `NodeSearchDocument`；
2. 实现无外部依赖、整数计分、稳定排序的解耦词法/结构候选算法；
3. 建立只读 M5 离线 A/B harness，固定五种查询视图和聚合错误码；
4. 增加合同、重排确定性、错误 parent、空目标和数据边界测试；
5. 不修改 `build_candidate_set()`、治理 CLI、Semantic Prompt 或生产入口。

## B1 状态

- [x] 版本化解耦查询与确定性整数计分原型；
- [x] M5 五视图离线 A/B harness；
- [x] 首次冻结校准运行，模型调用为 0；
- [x] 确定性重放 18/18；错误 parent 未硬过滤合法目标；
- [ ] B1 晋升：FAIL，Recall@8、MRR 和空目标门槛未通过；
- [ ] B2：因宽泛请求 Oracle 不完整而停线，先冻结校准 Oracle v2。

## Oracle v2 与 B2 状态

- [x] Oracle v2 为内存 overlay，不改原 M5 fixture/Oracle；
- [x] 14 个 source-retained、2 个 request-observable broad class、2 个 explicit-empty；
- [x] overlay 生成、重排、篡改和聚合泄漏测试通过；
- [x] B2 显式强锚点规则及门槛在首次结果前预注册；
- [x] B2 实现与首次冻结运行；
- [ ] B2 晋升：FAIL，Recall@8=15/16、MRR=0.880208；
- [x] 空目标状态 2/2、Recall@20=16/16、五视图结果一致且重放 18/18；
- [ ] B3：完整短语锚点候选须先预注册，不得回写或调参 B2。
- [x] B3 完整短语锚点、固定门槛和停止规则已在实现前预注册；
- [x] B3 实现与首次冻结运行；
- [ ] B3 晋升：FAIL，Recall@8=16/16、空目标 2/2，但 MRR=0.843750；
- [x] 停止增加 B4 词法/句式语法，转入 target/scope 与 Semantic 职责边界设计。

## Decision D2（候选）：Fact 与 Intent 的角色边界

**Context**：仓库没有独立 Fact 合同；`confirmed_facts` 仍是 Intent 内自由文本，缺少
原文 span 与角色证明。B3 的5个第2名目标均暴露 context/scope 与 target 混权问题。

**Candidate decision**：原始 requirement text 继续是权威来源；检索使用绑定原文的
`TARGET / SCOPE / EXCLUSION` 角色证据，而不是把另一份自然语言摘要当作事实。
Intent 负责操作解释、结构约束与澄清，角色 Fact 负责可回放的输入证据。两者未来可由
同一次模型调用产生，但必须分别本地校验。

**Qualification result**：Codex/Silver 角色上限实验已经 PASS。五种视图均为
Recall@8=16/16、MRR=1.0、空目标2/2和重放18/18。该结果允许进入小模型角色抽取
实验，但仅是已暴露校准集上的架构上限，不是泛化或生产资格。

## R1 角色上限状态

- [x] 18条请求正文完成 Silver 角色可标注性审计；
- [x] 角色 span、候选规则、分母与门槛在实现前预注册；
- [x] 实现严格角色合同与角色感知候选；
- [x] 首次冻结上限运行：PASS；
- [x] 五视图 Recall@8=16/16、MRR=1.0、空目标2/2、重放18/18；
- [x] 小模型 source-bound role span 抽取实验已预注册；
- [x] 实现模型输出合同、受控 Provider 与聚合评测；
- [x] v1 首次冻结实验：合同18/18，R1 Recall@8=14/16、MRR=0.875，FAIL；
- [x] 安全诊断重放稳定复现2个 TARGET super-span；
- [x] 单一 v2 Prompt 边界规则已预注册；
- [x] v2 首次冻结：合同18/18，R1仍14/16、MRR=0.875，FAIL；
- [x] 停止在本集合继续调 Prompt，R1 exact target gate 不晋升；
- [x] 预注册 R2 边界容忍角色词法表示，不改角色合同或 Prompt；
- [x] 实现并运行 R2 Silver 回归与冻结 v2 小模型校准；
- [x] R2 首次冻结 PASS：合同18/18，五视图 Recall@8=16/16、MRR=1.0、空目标2/2；
- [x] 停止暴露集调参，冻结候选架构并定义新的未见确认合同；
- [ ] 提交冻结功能基线，随后由独立数据分支绑定该提交准备未见密封集。

当前不修改预注册门槛。B1 结果说明 D1 方向有实质增益，但查询锚点和 Oracle 的
request-observable 完整性都需先修正。

## 状态

当前 R1 人工上限 PASS，但模型 v1/v2 均稳定为 Recall@8=14/16、MRR=0.875。两个
漏失项都是正确 TARGET 角色的 super-span，v2 还增加了过度抽取。问题已收敛到自然
语言目标边界与 R1 完整字面门禁的接口。停止继续调 Prompt；下一步预注册一个容忍
super/sub-span 与非字面表达的最小检索表示，角色合同保持不变且不宣称生产资格。

R2 已在不修改模型、Prompt、角色合同和分母的前提下，把相同 super-span 下的小模型
结果恢复到五视图 Recall@8=16/16、MRR=1.0、空目标2/2。该结果冻结 R2 为开发期候选，
但仍是暴露校准集结论；下一步不得继续使用该集合调参，必须转入新的未见确认。

## R2 未见密封 runner

- 数据提交固定为 `bcdb9718785af08f68f73814899b8af953af05ea`；runner 必须提交在该
  commit 之后，并在首次读取私有请求前由调用方提供精确 `runner_commit`。
- runner 只允许在当前 HEAD 精确等于 `runner_commit`、数据提交为其祖先、工作树
  干净且数据白名单文件从 data commit 到 runner commit 零变化时继续。
- 首次运行前重新验证 v3 final freeze、execution binding、28 条 execution input
  和五视图合同；任何不一致均在模型调用前停线。
- CLI 必须显式选择 `--preflight-only` 或 `--live`；preflight 模式不要求输出目录、
  不创建实验工件且绝不调用模型，live 模式另行要求全新私有输出目录。
- 每条每轮只做一次角色抽取流程，允许一次合同纠错重试；同一角色输出重新绑定到
  五个视图，并同时送入确定性 R1/R2。两轮总调用上限固定为 112。
- 每个视图报告 R1/R2 Recall@8/20、MRR、空目标、hard negative、非字面类别和
  确定性重放；只有 R2 进入冻结 gate，R1 仅作诊断对照。
- 完整请求、响应、角色 span、候选和 Oracle 只写入新建的 `0700` 私有目录下
  `0600` 不可覆盖文件；stdout 只含固定 code、聚合计数和指标。
- 两轮均通过且非字面 Recall@20 均至少 3/4，决策为 `R2_SHADOW_CANDIDATE`；
  总门槛通过但非字面不足为 `R2_LEXICAL_LEG_ONLY`；角色合同失败为
  `ROLE_EXTRACTION_NOT_STABLE`；其他召回失败为 `VECTOR_OR_HYBRID_REQUIRED`。

## R2 未见密封结果与下一切片

- [x] 首次 live 因 Python CA 校验失败，仅形成传输诊断，不作能力结论；
- [x] 仅增加系统 CA 后完成两轮有效执行：角色合同 28/28、传输失败 0；
- [x] R2 两轮 Recall@8 均为 22/24、Recall@20 均为 22/24；
- [x] 非字面 Recall@20 两轮均为 2/4，空目标均为 4/4；
- [x] 决策冻结为 `VECTOR_OR_HYBRID_REQUIRED`，不具备生产资格；
- [x] 发现并修复 hard-negative 主类别与分母记账不一致；不回算首次资格；
- [x] 在独立开发校准数据上预注册单一混合候选，不使用本次28条调参；
- [x] 冻结 embedding 模型、节点/查询表示、融合算法、索引版本和失败降级；
- [x] 基于已暴露 M5 虚构树物化24条透明开发校准数据：16正目标、4 hard negative、
  4显式空目标；Oracle 为 Codex Silver、非 Gold、禁止进入模型输入；
- [x] embedding 前冻结 A 基线：R2 Recall@20=14/16、非字面=6/8、hard negative
  安全=4/4、显式空目标=4/4；
- [x] 实现 H1 节点/查询文档、向量合同、余弦 Top-40、排除过滤、锚点门与固定
  RRF 的纯确定性 core，并用可控向量验证补召回、空目标和 hard-negative 边界；
- [x] 实现可替换的 H1 Embedding Provider 协议、固定 `text-embedding-v4/512`
  百炼实现，以及绑定树/文档/模型的 `0600` 不可覆盖私有索引工件；本地开源模型
  可复用 Provider 形状，但不得混入 H1，须使用新合同与新分母独立验证；
- [x] 实现 R2 lexical leg 与 H1 候选的固定 A/B runner，并完成零模型离线预检；
- [x] 使用冻结百炼 embedding 配置首次运行固定 A/B：Recall@20 从14/16升至15/16、
  非字面从6/8升至7/8，但均未达到相对 A 增加2条的门槛，决策为 `H1_REJECTED`；
- [x] H1 未通过，不运行冻结小模型角色重放，不在24条已揭盲开发集继续调参；
- [x] H2 冻结唯一主要变量：本地 `BAAI/bge-small-zh-v1.5` 512维 profile；H1 文档
  字段、R2、Top-40、锚点/排除和 RRF 1:1 保持不变；
- [x] H2 冻结新的28条开发分母、可判别性门、相对/绝对召回门槛和停止规则；
- [ ] 独立准备并冻结 H2 新树、36条候选和28条执行集；
- [ ] A 基线可判别后，实现隔离本地 Provider/H2 索引合同并首次运行 A/B；
- [ ] 候选冻结后再准备新的未见确认，不在开发集上宣称生产资格。
