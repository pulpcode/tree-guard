# M4.9 新密封验证数据

## 目标

为提交 `d52e92341b1d081c45c9e4594b98323327379da5` 上的信息树理解链路规划一套全新、独立、未进入既往模型请求的 clean-room 虚构密封验证数据，用于判断 M4.6–M4.8 的改进能否泛化，而不是继续在既有样本上调参。

## 当前阶段

用户已明确批准第二阶段生成与正式 fixture 晋升。全新候选树、24 条正式场景、6 条
密封余量、隐藏 Oracle、L1 报告和 Codex-assisted Silver 审阅已经生成并绑定；模型
调用在数据生成与审核阶段保持为 0，随后才按冻结计划执行 Intent 和 Semantic 实验。

状态：`ASSISTED_SHADOW_ADMISSION_CONTRACT_IMPLEMENTED`。首次 Intent
执行因无 CA roots 被标记为基础设施无效；用户随后明确批准使用项目 `uv` 解释器重跑。
修正运行的 72 个 Intent 观测已冻结，隐藏 Oracle 本地评分完成，并只为 53 个上游完整
匹配单元生成精确 Semantic v4 私有请求计划。用户明确批准该冻结计划后，Semantic
观测已完成并通过本地结果合同校验。当前结果只用于 Silver 诊断，不授权 Gold 晋升、
运行时注册、生产门禁、Patch 或 Git stage/commit。

M4.9 后续已冻结一份只读、人工在环 Shadow 的准入政策候选，见
`research/assisted-shadow-admission-policy.md`。该政策不修改 M4.5 严格门禁，也不把
M4.6 Silver 校准改写为正式门禁。按候选政策反事实重放，M4.9 的合同合法率、安全
完整路径、稳定性和零非首选正向动作达到候选阈值，但确定性 Retrieval 为 `52/53`，
且数据已揭盲、只经过 Codex-assisted Silver 审核，因此正式判定仍为
`EVALUATION_PENDING`。当时的下一步被限定为先确认产品政策，再准备新的未见资格集；
确认前不得继续造数据、调 Prompt 或调用模型。

用户随后接受继续推进，M5 确定性合同已实现为
`scenario-assisted-shadow-report.v1` / `treeguard.m5-assisted-shadow-admission.v1`。
它新增证据资格、三轮安全路径、Semantic 联合结果、安全退让人工审核和阶段短路
记账，不修改 M4.5/M4.6。M4.9 精确反事实仍为 `EVALUATION_PENDING`：除政策冻结
晚于实验和非人工 Oracle 外，Retrieval `52/53` 以及 1 个 Retrieval MISMATCH 后仍实际调用
Semantic 的观测都会被新合同明确记录。当前尚未生成新的资格数据或发起模型调用。

## 第二阶段结果

- 全新岚序湾虚构消防治理树：1,453 节点、12 个顶层分支、最大自然深度 5、
  `VALUE` envelope 0；216 个 curated core，1,237 个 approved background，
  stress filler 0。
- 场景：24 条正式（18 `PROCEED` + 6 `CLARIFY`）和 6 条独立 reserve；正式场景
  覆盖 12/12 顶层分支。
- L1：`PASS`；17 个数据专属测试通过。
- L2/Silver：第 4 次审阅 30/30 接受，0 blocking finding；审核者与生成者不独立，
  因此只标记 `CODEX_ASSISTED_SILVER`，继续保持 `gold_eligible=false`、
  `gate_eligible=false`、`execution_eligible=false`。
- 前三轮候选分别因字段类型/Top-K 目标语义、reserve 风险合同不匹配、正式分支
  上限门禁错误而退回；三次整批修复额度已用完，staging 原样保留为 ignored 的
  rejected round 记录。未通过放宽 Oracle 或 Charter 消除问题。
- 最终 snapshot：`65c5c9d06ffefe36433b1ec233f128658aa83422414c3ac681249dce7ad4d2b6`；
  candidate digest：`b2772c1d70a776b38efc326eb09470f0eaebb45d9c026a705c948eddf84faeca`；
  Oracle digest：`8abbb62eb00be8491c056aa15f48c52f9350140cf906c26e7e5146fa311214bd`；
  Silver review digest：`71bc8ff7e3ba3a48c282c01c2810e5af3a8ceb02935dd48d6c66f09ef6557d00`。
- 正式 fixture 已原子晋升到 `tests/fixtures/fictional/fire_m49_sealed/`，包含聚合
  manifest、树、公开场景请求、隐藏 Oracle、Silver 审核和独立 promotion 工件；
  `formal_fixture_promoted=true`，但 `runtime_registered=false`、
  `experiment_executed=false`。

## 运行计划冻结结果

- 新增 `scripts/prepare_fire_m49_runtime_plan.py`，只从晋升 fixture 的公开场景、树和
  Silver 来源绑定重建 Intent 模型投影；隐藏 Oracle 仅由本地泄漏校验读取，不参与
  请求构造。
- 三轮共 72 个观测单元；每个单元冻结 1 个首发正文及 17 个可能的第二次合同重试
  正文，共 1,296 个计划槽位。相同场景三轮正文必须逐字节相同，因此不同正文为
  24×18=432 份，不以人为改变 Prompt 制造“独立性”。
- Intent 实际首发 72 次、最多 144 次；Semantic 首发上界 54 次、包含一次连接恢复
  的 wire 上界 162 次；总 wire 上界 306 次。
- 私有计划固定 `execution_authorized=false`、`contains_oracle=false`、
  `contains_credentials=false`、`runtime_registered=false` 和
  `experiment_executed=false`；下一道门为 `EXPLICIT_INTENT_EXECUTION_APPROVAL`。
- 新增 9 个运行计划测试，覆盖确定性、24×3 记账、跨轮同正文、全部 retry code、
  Oracle/凭据隔离、0600/不可覆盖、来源篡改、bool-as-int 和重哈希正文篡改。

### 为什么 Semantic 计划分两段冻结

Semantic 模型输入由“模型实际输出的 Intent → 本地确认/比较 → 确定性召回 → 有界候选
投影”产生。首次 Intent 调用前不存在真实的 candidate set，因此无法诚实地列出
Semantic wire body。若提前使用隐藏 Oracle 或人工 Intent 代替，就会改变被测能力并
泄漏答案。正确顺序是先冻结并执行 Intent，再对冻结结果做可信回放，只为真正进入
Semantic 的单元生成第二份精确私有请求计划；任何 Semantic 外发仍须命中该计划。

## 首次 Intent 基础设施无效运行

- 用户批准绑定冻结计划后，执行器完成 72 个单元；聚合为 72 次首发、0 次合同重试、
  0 `DRAFT_READY`、72 `RUN_FAILED`，唯一固定错误码为
  `BAILIAN_CONNECTION_FAILED`。
- 运行使用 `/usr/local/bin/python3`，其默认 SSL context 加载 CA roots 为 0；项目
  `uv` 解释器加载 128 个 CA roots，且对默认百炼域名的无认证 HEAD 诊断成功到达
  HTTP 层。因此失败定位为本地解释器 TLS 信任环境，而不是 endpoint、Prompt、JSON
  合同或模型语义。
- 私有结果保持 0600，只含调用摘要和空 draft；原始异常、Prompt、响应、凭据未写入
  仓库或公开报告。因为 0 个模型响应，未见性未被模型输出污染，但整批重跑仍是新的
  实验动作，不能由实现自行视为已批准。
- 执行器新增批量前 CA trust preflight：默认 SSL context 无可信根时以
  `M49_INTENT_TLS_TRUST_UNAVAILABLE` 在环境读取和模型 transport 前失败。修正运行必须
  显式使用项目 `uv run --frozen --offline` 解释器。

## 修正 Intent 运行与 Semantic 计划

- 修正运行使用相同 72 个冻结单元、相同正文和默认 endpoint；72/72 最终合同合法，
  66 条首发通过、6 条经一次完整合同重试通过，实际 78 次 wire request，0 run
  failure。
- 6 次重试的本地错误细分为 `INTENT_MODEL_OWNERSHIP_INVALID` 5 次和
  `INTENT_MODEL_FIELDS_INVALID` 1 次；只记录固定 code 聚合，不公开模型正文。
- 隐藏 Oracle 本地评分：route 匹配 71/72，完整 Intent profile 匹配 68/72。合同合法
  只说明 JSON/字段/跨字段约束通过，不等于意图正确；两组指标保持分离。
- 只有完整 Intent 匹配且期望 route 为 `PROCEED` 的 53 个观测进入 Semantic 计划；
  其余单元按上游不匹配或合法澄清短路，不伪装成 Semantic 失败。
- Semantic v4 私有计划包含 53 个首发单元、901 个可能正文槽位；两次合同尝试并允许
  一次相同正文连接恢复，最大实际 wire request 为 159。计划保持
  `execution_authorized=false`、非 Gold、非门禁、非 Patch，且模型正文中无隐藏 Oracle
  目标。

## Semantic Silver 运行结果

- 用户批准绑定的 Semantic 计划 SHA-256 为
  `07904d7537c958dd15668810a8af0d4553e8d2d0091eca10d27b7e735ba0a299`；执行前按
  来源 Intent 计划、Intent 结果和 fixture 确定性重建，逐字节一致。每次实际传输均
  命中所属单元的冻结正文哈希，单元上限为 3 次。
- 53 个 Semantic 观测实际产生 58 次 wire request；48 个一次完成，5 个发生一次
  合同重试，0 个连接恢复。52 个最终形成合同合法 draft，1 个两次尝试后仍以
  `SEMANTIC_MODEL_VERSION_INVALID` 结束。合同失败 trace 聚合为
  `SEMANTIC_SELECTED_CANDIDATE_CONTRACT_CONFLICT` 3 次、
  `SEMANTIC_MODEL_VERSION_INVALID` 3 次。
- 原执行计划把 53 个“Intent 完整匹配且期望 PROCEED”的观测都送入 Semantic，
  但审计确认 M4 阶段合同还要求 Retrieval MATCH。确定性召回实际为 52/53 MATCH；
  唯一不匹配单元虽已在冻结外发计划内完成调用，却必须在评分时记为上游短路，不能
  进入 Semantic 正确率分母。无需重跑模型，确定性重评分把有效 Semantic 分母修正
  为 52。
- 修正分母后 Recommendation 为 19 个首选联合结果、32 个无目标安全退让、0 个
  非首选正向危险动作和 1 个合同失败。严格首选命中率为 19/52；若只判断“首选或
  安全退让”，则为 51/52。原始私有结果仍保持不可变，不把重评分伪装成原始执行。
- 端到端 72 个观测中 34 MATCH、38 MISMATCH；其中 15 个是正确短路的澄清观测，
  19 个是完整链路命中。24 个场景中仅 8 个达到三轮 3/3，全链路结果尚不满足稳定
  自主验证要求。按 M4.6 的“首选或无目标安全退让”辅助口径，端到端为 66/72，
  三轮稳定为 18/24；该辅助口径只说明较少给出危险正向动作，不能替代严格正确率。
- 聚合归因显示明显的动作偏置：模型在唯一目标和部分跨分支干扰场景能够稳定选择
  `USE_EXISTING_NODE`，但 7 个期望安全拒绝的结构冲突/无安全复用场景共 21 个观测
  中没有一次命中 `ABSTAIN`，20 次选择 `NEED_CLARIFICATION`，另 1 次合同失败；
  多可接受目标和 Top-K 边界也多数退化为澄清。故当前主要瓶颈不是 JSON 格式，也
  不是整批召回，而是“何时澄清、何时拒绝、选择哪个目标及关系”的联合决策策略。
- 私有结果保持 0600，SHA-256 为
  `799883f8d4d27d33591a876ee16ed4108b306cfd20b15b7e1aecfac9724363fe`；不在仓库保存
  原始请求、模型响应、隐藏目标或凭据。该 SHA 只绑定本次诊断来源，不使结果获得
  Gold 或门禁资格。

### Codex-assisted Silver 复核

- 不修改本次密封 Oracle，也不把已经观察到的模型动作追加为严格正确答案；原始严格
  34/72 与 8/24 继续保留，避免事后放宽导致过拟合。
- 逐类复核显示，32 个 `SAFE_ALTERNATIVE` 不能全部解释为模型不理解树。两个“多可
  接受目标”请求明确把最终二选一留给后续上下文，模型追问具体目标符合对话式产品；
  两个 Top-K 边界请求缺少能唯一绑定目标的业务对象/阶段限定，模型追问也有实质
  理由。把这些场景只冻结为任取一个 `USE_EXISTING_NODE`，作为 Gold 会过窄。
- 结构 hard negative、kind/type/cardinality 冲突和无安全来源场景中，模型没有绕过
  冲突给出正向动作，而是追问用户确认冲突 hint 或补充来源。对“验证准备助手”而言，
  这通常比无说明的 `ABSTAIN` 更有交互价值；但部分问题混合了两个子问题，或暗示
  修改现有合同/忽略冲突，问题质量仍需人工约束，不能直接视为严格正确。
- 因此本轮同时暴露模型能力边界和评测设计边界：模型在明确唯一目标上有可重复能力，
  在歧义/冲突上明显偏向安全澄清；严格 Oracle 没有表达对话式产品可接受的安全退让。
  当前技术路径适合作为只读、人工在环的保守辅助器，不足以支持自主联合决策。
- 后续不能针对本轮 32 条逐条改答案。应先冻结跨数据集的动作政策：唯一等价目标用
  `PREFERRED_MATCH`；输入存在可由用户回答的原子歧义/冲突时允许
  `NEED_CLARIFICATION`；缺少外部来源时允许 `NEED_EVIDENCE`；不可安全推进且无可
  回答问题时用 `ABSTAIN`。下一份未见数据应在调用前同时冻结严格首选和安全退让
  Oracle，再分别验收任务正确性与安全性。

## 已知约束

- 功能基线固定为 `d52e92341b1d081c45c9e4594b98323327379da5`。
- 数据必须从零独立创作，不复用既有消防 401 节点树、青岚树或已经暴露的 M4.5 数据快照。
- 数据分类必须为 `source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、`derived_from_real=false`。
- 隐藏 Oracle、期望目标、评分答案和审核 sidecar 永不进入被测模型输入。
- 规划只能使用既有实验的聚合结论、固定错误码和公开合同，不读取或复制历史原始请求、响应、Prompt、场景正文或隐藏答案。
- 覆盖类别须在数据生成前冻结，不得针对某一条历史失败样例编写同义改写。

## 建议验证规模

- 一棵全新 800–2,000 节点虚构树；具体规模与结构分布在 Dataset Charter 中冻结。
- 24 条正式密封执行场景：18 条完整链路、6 条澄清/拒绝类场景。
- 同一冻结请求执行三轮，区分单轮正确性与跨轮稳定性。

## 第一阶段交付物

- `research/dataset-charter.md`
- `research/coverage-blueprint.md`
- `research/unseenness-and-anti-overfit.md`
- `research/oracle-review-handoff.md`
- `research/silver-runtime-freeze.md`
- `research/assisted-shadow-admission-policy.md`

## 第一阶段退出条件

- 数据来源、规模、结构分布、覆盖矩阵和明确排除项已冻结；
- Oracle Schema、审核角色、Silver/Gold 边界、摘要报告边界已定义；
- 功能合同、Provider、模型/端点、重试与计分分母的绑定项已列清；
- 第二阶段所需的生成、preflight、审核、冻结和停线顺序已定义；
- 未产生任何实际树、场景或 Oracle 内容。

## 非目标

- 本阶段不证明模型能力，不运行百炼实验；
- 不修改功能代码、Provider、现有 fixture、manifest 或既有实验记录；
- 不以新数据作为训练集或 Prompt 调优集；
- 不将 Silver 自动宣称为 Gold。

## 待确认

- 模型与运行配置已冻结在 `research/silver-runtime-freeze.md`：复用百炼
  `qwen3.6-35b-a3b`、默认 endpoint、temperature 0、90 秒 timeout；Intent 最多
  2 次，Semantic 最多 2 次合同尝试并允许 1 次连接恢复。
- 本轮审核等级已固定为 `CODEX_ASSISTED_SILVER`；不设置 Gold 晋升路径，不进入正式
  `GO_SHADOW` 门禁。未来若需要正式门禁，必须在模型看见正文前另行冻结人工审核方案。

## 第一阶段决策摘要

- 主角色固定为 `SEMANTIC_CHALLENGE`，继续使用完全虚构消防治理领域，但树、语义、
  ID、场景和 Oracle 全部从零创作；跨领域控制另立数据集。
- 树硬区间固定为 800–2,000 节点，规划目标为 1,200–1,600；stress filler 默认 0，
  不用笛卡尔积补规模。
- 正式执行集固定 24 条（18 `PROCEED` + 6 `CLARIFY`），另有最多 6 条运行前密封
  余量；每条一个主风险，最多两个次要 tag。
- 正式执行三轮；沿用 98% 合同合法率、100% 实际召回、每轮 18/24、稳定 18/24
  和零硬冲突错误复用门槛。
- Codex 审核只能形成 Silver 诊断；正式 Shadow 门禁需要首次模型调用前完成人工逐项
  冻结。两者都不创建真实领域 Gold。
- 用户已选择本轮采用 Codex-assisted Silver，因此本轮最终决定只允许
  `PROMISING` / `NOT_PROMISING` / `INCONCLUSIVE`，不得输出正式 `GO_SHADOW`。
