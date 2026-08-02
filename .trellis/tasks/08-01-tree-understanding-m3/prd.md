# brainstorm: 信息树理解 M3 结构变更测试场景规划

## Goal

把 M2 的有界树理解能力用于准备自然语言信息树建模/变更测试候选：本地确定性
规划器从可信树结构、类型/基数合同和启发式信号中选择有界场景锚点，内网 LLM
只把这些锚点转写为自然语言结构需求并关联投影内证据，本地校验、归并后形成待
人工审核的候选批次。候选合同面向完整的意图理解—召回—语义推荐流水线，首个
可执行切片只比较意图阶段状态，不把实例查询、模型自评或节点投影次数当成全树
理解证明。

## What I already know

- 父任务已经实现完整树结构画像、一级分支统计、有界投影、内网 Qwen/百炼
  Provider、严格本地输出合同和可信来源绑定；
- 当前信息树主要描述字段、层级、节点类型、值类型和基数，通常不包含可供事实
  问答的实例值；
- 当前 MVP 接收 `requirement_text`、可选父节点提示和 kind/value type/cardinality
  hints，随后经过意图理解、人工确认、全树召回和语义推荐；
- 当前青岚运行时验证适配器只比较意图阶段状态，不比较召回候选或语义推荐结果；
- 完全虚构实验中，模型能概括树的主要业务区域并生成自然语言，但自由生成会遗漏
  分支、稳定产生跨分支组合，并偶尔遗漏自然语言诉求所需的证据；
- 显式分配单分支后结构归属明显改善，但单分支限制无法生成同名消歧、错误父节点、
  跨分支冲突和无界组合拒绝等关键挑战场景；
- 生产树规模预期通常不超过约 2,000 个节点，单次模型投影继续受 128 节点和
  48,000 字符硬上限约束；
- 当前分支已经包含 48/312/2,001 节点青岚完全虚构树及 12/20/8 个已审核冻结、
  非 Gold 场景；三档数据分别适合作为控制、语义挑战和生产形状基座；
- 现有参考场景覆盖 7 个核心风险族，缺少明确的 `NEW_NODE_PLACEMENT` 场景；
- 本任务是 M3 规划任务；M0–M2 的既有实现、未提交改动和安全边界不得被隐式改写。

## Confirmed Decisions

- 生成对象是自然语言信息树建模/变更需求，不是“几点开放、数量多少”等实例值
  查询；实例数据缺失类输入只可作为有意设计的越界/防幻觉负例；
- 候选合同预留意图、召回和语义推荐三个阶段的目标与预期槽位；
- 首个运行切片只执行并比较意图阶段，召回和推荐预期保持未执行，不能报告为通过；
- LLM 生成结果是候选，不是 Oracle、Gold、Patch 或可直接注册的测试数据；
- 分支覆盖、风险类型、计划顺序、输入锚点、调用预算和完成状态由本地确定性代码
  决定，不能由模型自报；
- 采用稀疏覆盖计划，不对“每个分支 × 每种风险类型”做笛卡尔积展开。
- 首个候选规划切片采用下述核心 8 个风险族；扩展风险族留待后续切片。
- 单次运行默认最多 `16` 个计划单元，公开硬上限为 `32`；每个单元最多形成一个
  通过本地合同校验的候选，Provider 对该单元最多尝试两次，因此默认/硬上限下
  最坏分别不超过 `32`/`64` 次模型 HTTP 调用。
- 部分计划单元失败时，已成功候选仍以 `PENDING_HUMAN_REVIEW` 独立进入人工审核；
  批次保持 `PARTIAL` 并披露失败/遗漏单元，审核资格不得被解释为覆盖完成。
- 计划采用均衡预留：最多为 8 个确定性适用的核心风险族各保留一个挑战单元，
  剩余名额用于一级分支基础单元；不适用的风险名额自动归还分支覆盖。
- 每个候选原则上只表达一个主要结构诉求；多个目标是有意的澄清或拒绝场景时才
  允许例外；
- finding 的质量裁决继续属于独立模式，但机械 finding 可以作为挑战场景的只读
  锚点，不因此被升级为真实业务错误；
- 首版不接 Workbench、不写 sidecar、不注册 `ValidationDatasetProvider`；
- 继续复用现有 Qwen/Bailian transport，不增加运行时依赖。
- 一级分支超过剩余名额时采用结构代表性选择：按固定顺序先选节点数最大、相对
  深度最大、直接子节点数最大的分支并去重，再按规范化结构向量差异补足；稳定
  内部 ID 只用于同分决胜，不作为业务优先级。
- M3 以现有青岚 48/312/2,001 节点完全虚构 fixture 为主要开发和验收基座，不再
  创建平行规模树；既有 `scenarios.json`、覆盖矩阵和 promotion 只作生成后的隐藏
  参照，不能进入真实模型输入；
- 既有人工审核冻结场景是完全虚构回归参照，不是领域 Gold 或自动 Oracle；M3 在
  既有树上新增一个 `NEW_NODE_PLACEMENT` 专用 overlay 补齐风险覆盖，不改写基础
  fixture。
- 312 节点真实模型实验后，M3 Prompt 升级为 v2：对象模板中的自然语言示例改为
  必须改写且最终输出禁止出现的哨兵；本地只拒绝可确定判断的占位文本、面向用户
  需求中的投影临时引用和风险族最小跨字段政策，不以关键词规则冒充领域语义审核；
- `HOMONYM_CLARIFICATION` 和 `UNBOUNDED_COMBINATION` 候选至少披露一项
  `uncertainties`，`INSUFFICIENT_EVIDENCE` 至少披露一项 `evidence_gaps`；其他
  风险族通过确定性 Prompt 任务说明约束生成目标，真实的需求—证据等价仍由
  Codex/人工审核；
- Prompt v2 不增加模型输入/输出字段，不改变 v1 Schema、candidate digest 域或
  Provider 尝试上限；Prompt 版本进入候选 provenance，全部新外发请求必须重新
  冻结并按最终字节单独批准。
- Prompt v2 的独立语义审核完成后，后续提示升级为 v3：投影临时引用禁令扩展到
  候选的全部自然语言字段，证据不足模板增加必须改写的专用哨兵；这两项属于本地
  可证明的文本合同，不改变 v1 Schema、candidate digest 域或 Provider 尝试上限。
- Prompt v3 必须明确区分“信息树的结构定义”与“业务实例值”：已有节点复用只表示
  复用节点/字段定义，不能据此要求读取、填写或声称存在实例值；所有候选从自然用户
  的结构建模/变更诉求出发，不把测试规划器、计划单元、主要锚点等内部术语写入需求。
- `UNBOUNDED_COMBINATION` 的 requirement 保留自然且尚未收敛的过宽诉求，缩小
  范围的建议只进入 uncertainty；`INSUFFICIENT_EVIDENCE` 必须具体说明完成该请求
  仍缺什么证据或输入；`NEW_NODE_PLACEMENT` 的自然语言基数描述必须与锁定 hint
  一致。上述领域语义仍由 Codex/人工审核，不能由宽泛中文关键词规则自动判定通过。
- Prompt v3 不新增中文内部元语言关键词门禁；“系统”“验证”“检索”“主要锚点”
  等词可能属于真实领域需求，靠子串拒绝既会误杀也不能证明自然度。应从 Prompt
  源头移除实验话术，并继续由 Codex/人工审核自然度；任何新的真实模型实验仍需
  重新冻结完整请求字节并另行获批，本轮本地实现不继承 Prompt v2 的外发授权。
- 存储候选回放继续使用当前文本政策并全局失败关闭，不依据候选自带的
  `prompt_version` 放宽旧文本；因此历史 v2 候选若在新增受检字段中保留独立临时
  引用，将不再通过当前 v1 回放。当前实验候选原文未落库且候选本来非 Gold；未来
  如需长期兼容此类持久化候选，应升级可信候选合同，而不是增加可伪造的版本绕过。

## Scenario Families

规划器而非模型选择 `scenario_family`。M3 首个切片固定包含以下核心 8 个候选族：

1. `CLEAR_EXISTING_REUSE`：清晰需求应找到并复用已有节点；
2. `NEW_NODE_PLACEMENT`：当前没有等价节点时，验证合理父节点与新增合同；
3. `HOMONYM_CLARIFICATION`：多个上下文存在同名节点且需求信息不足；
4. `WRONG_PARENT_OR_CROSS_BRANCH`：父提示或需求语义与树分支冲突；
5. `KIND_CONFLICT`：概念/属性提示与已有结构冲突；
6. `CARDINALITY_CONFLICT`：单值/多值提示与已有合同冲突；
7. `INSUFFICIENT_EVIDENCE`：请求要求业务判断，但树结构不提供判断证据；
8. `UNBOUNDED_COMBINATION`：要求对大量分支统一组合字段，应拒绝或要求缩小范围。

同名、近名、合同冲突等机械信号只有在树中存在确定性锚点时才产生对应计划单元；
不存在锚点时记为 `NOT_APPLICABLE`，不能让模型编造结构风险。

祖先作用域、集合汇总、粒度歧义、政策/实例边界、单例政策和异常深度等扩展风险
不进入首切片；新计划/候选合同仍以开放枚举升级方式支持后续版本，而不是预先加入
未实现分支。

## Planning Modes

### `BRANCH_LOCAL`

- 只包含一个一级分支的根、必要祖先和有界后代；
- 用于已有节点复用、新节点放置和清晰的类型/基数需求；
- 所有结构证据必须具有同一个可信一级祖先。

### `CONTRAST`

- 由确定性规划器选择两个或少量相关分支/上下文；
- 只用于同名、近名、错误父节点、跨分支和合同差异挑战；
- 必须记录为何允许多个上下文，不能把任意跨分支混合作为合法场景。

### `AMBIGUITY`

- 允许缺少父节点提示、存在多个有界候选，或包含有意冲突的提示；
- 用于澄清、证据不足和拒绝无界组合；
- 计划必须声明预期验证的是“保持不确定性”，而不是寻找任意一个节点。

## Candidate Contract

### 确定性计划输入

每个 `ScenarioPlanUnit` 至少绑定：

- 运行内连续 `plan_unit_ref`；
- `planning_mode`、`scenario_family` 和目标验证阶段；
- 来源 tree/profile/plan digest；
- 一个或多个受限结构锚点及其可信分支归属；
- 父节点提示政策：`ABSENT`、`CORRECT` 或 `INTENTIONALLY_CONFLICTING`；
- kind/value type/cardinality hint 政策；
- 本单元节点/字符预算、包含和遗漏计数；
- 可选的机械 finding 锚点，但不包含 finding 质量结论。

### 模型输出候选

每个 `ScenarioCandidateDraft` 至少包含：

- 投影内连续场景引用；
- 来自计划的 `scenario_family` 与目标阶段，不允许模型改写；
- `requirement_text`，必须是信息树结构建模/变更需求；
- 投影内拟议父节点引用或 `null`；
- `node_kind_hint`、`value_type_hint`、`cardinality_hint`；
- 支持节点引用，以及按主要诉求拆分的 `requested_aspects`—引用对应；
- 生成理由、不确定性和证据缺口；
- `PENDING_HUMAN_REVIEW`、非 Gold、非 Patch 固定状态。

模型不得生成 expected Oracle、覆盖完成状态、内部稳定节点 ID、人工审批或数据集
注册资格。

### 审核后兼容目标

人工审核后的候选应能被单独的后续编制边界转换为当前
`ValidationScenarioRequest` 所需字段：

- `requirement_text`；
- `proposed_parent_node_id`；
- `node_kind_hint`；
- `value_type_hint`；
- `cardinality_hint`。

审核者而非生成模型负责冻结 `ValidationScenarioOracle` 的可观察预期。M3 不实现
上述数据集注册或 Gold 转换，只保证候选字段可映射且保留来源证据。

### 审核与首切片执行边界

- `ScenarioCandidateDraft` 不能直接转换或冒充 `ValidationScenario`；
- 显式可信审核输入必须同时确认最终 `ValidationScenarioRequest` 和可观察的
  `ValidationScenarioOracle`，并绑定候选及来源 digest；
- M3 不持久化审核结论、不注册数据集 Provider，但允许已审核的内存场景进入现有
  验证边界；
- 只有显式审核通过的场景可以执行首个 `INTENT` 切片；模型生成候选保持
  `PENDING_HUMAN_REVIEW` 时不得运行或计为验证证据；
- 首切片只比较意图阶段可观察状态，召回和推荐保持 `NOT_RUN`。

## Stage Boundary

- 候选计划字段允许目标为 `INTENT`、`RETRIEVAL` 或 `RECOMMENDATION`；
- 首个可执行切片只运行 `INTENT`，比较 `draft_status`，其余阶段必须记录
  `NOT_RUN`，不能用 `null` 冒充通过；
- 后续切片扩展到召回时，才允许比较 candidate status/目标候选范围；
- 后续切片扩展到语义推荐时，才允许比较 recommended action、候选关系和澄清；
- 任一阶段的模型候选都不能自动成为该阶段 Oracle。

## Coverage Semantics

候选批次同时报告四种不同覆盖，禁止合并成一个“理解率”：

1. `branch_coverage`：哪些一级分支获得至少一个 branch-local 候选；
2. `scenario_family_coverage`：哪些适用的风险族获得候选、失败或未执行；
3. `target_stage_coverage`：哪些阶段只有候选、已运行或未运行；
4. `projected_node_coverage`：节点是否进入过模型投影，仅作输入覆盖披露。

默认稀疏计划：最多为 8 个确定性可适用的核心风险族各预留一个全局挑战单元，
剩余预算用于每个被选一级分支至少一个 branch-local 单元；不适用的风险名额归还
分支覆盖。不得对全部分支和全部风险族做笛卡尔积。

## Requirements

1. 从可信 `CanonicalTree` 与匹配的 `TreeDiagnosticProfile` 构建不可变、规范排序、
   有界且带 digest 的 `ScenarioPreparationPlan`；
2. 计划单元只能使用 `BRANCH_LOCAL`、`CONTRAST` 或 `AMBIGUITY` 明确模式，模式与
   允许的分支范围必须由本地校验；
3. 模型请求使用独立正向允许列表和单次作用域临时引用，公开节点/finding 包含与
   遗漏计数，不含稳定内部 ID/hash/路径/`VALUE`/extension/metadata；
4. 模型只生成结构变更需求候选和证据说明，不能选择覆盖目标、风险族、Oracle、
   Gold、Patch 或发布状态；
5. 本地确定性校验引用格式、允许列表、唯一性、父子关系、规划模式的分支边界、
   计划字段原样回显和来源绑定；
6. `requested_aspects` 中每项必须绑定至少一个允许引用；这只证明模型声明了证据，
   自然语言与证据的真实语义一致性仍由人工/Codex 审核；
7. 多投影归并使用运行级候选引用，不能把局部 `N`/`D`/`S` 引用当作跨投影稳定
   身份；
8. 归并批次绑定 tree/profile/plan/全部通过草案 digest，准确报告成功、失败、
   不适用、未执行和遗漏单元；
9. 部分批次中已成功候选可以独立进入人工审核，但批次保持 `PARTIAL`，逐项披露
   失败/遗漏单元，不得满足覆盖完成条件；全部执行单元均失败时批次为 `FAILED`，
   不产生可审核候选；
10. 计划单元预算默认值为 `16`、硬上限为 `32`；超预算单元按确定性优先级截断，
    明确记录为遗漏并使批次保持 `PARTIAL`，不得静默声称计划或覆盖完成；
11. 计划先为每个确定性适用的核心风险族预留最多一个挑战单元、总计不超过 8 个，
    剩余名额分配给一级分支基础单元；风险族 `NOT_APPLICABLE` 时释放对应名额；
12. 一级分支超过剩余名额时，先按固定顺序选择节点数最大、相对深度最大、最大
    直接子节点数最大的分支并去重，再以规范化结构向量的确定性差异选择补足；
    稳定内部 ID 只能用于同分决胜，所有未选分支必须显式记为遗漏；
13. 每个计划单元最多产生一个被接受的候选；Provider 最多尝试两次，重试替换该
    单元先前的无效输出，不得把两次输出归并为两个候选；
14. 候选字段面向完整 MVP 流水线；只有显式可信审核输入同时冻结最终请求、可观察
    Oracle 并绑定候选/来源 digest 后，才能执行首个意图阶段切片，其他阶段明确
    标记未运行；
15. 待审核候选不能自动转换为 `ValidationScenario`、注册验证数据集或计为执行
    证据；M3 只提供无持久化的已审核内存执行边界；
16. 外网自动化测试只使用独立构造的完全虚构树和虚构 transport；真实树与模型
    流量只留在受保护环境；
17. 自动化测试不得调用真实 Qwen、百炼、Web 或 MCP；手工百炼虚构数据实验仍需
    按最终请求字节和用途单独批准；
18. 48/312/2,001 节点青岚 fixture 分别作为控制、语义挑战和生产形状输入；基础
    fixture 保持不变，M3 合同与新增节点放置缺口通过独立 overlay 表达；
19. 真实模型生成请求不得包含既有参考场景文本、风险标签、建议观察类别、覆盖矩阵
    或 promotion 结论；这些工件只在输出完成后用于结构/风险/证据等价审核；
20. 自动化固定 transport 可以复用既有参考请求验证确定性合同，但必须明确标记为
    fixture replay，不能把逐字复现结果报告为真实模型语义能力；
21. 首切片中，核心风险族全部接受候选准备评估，但只有可由意图状态观察的场景计入
    MVP INTENT 验证；其他场景的召回/推荐能力保持 `NOT_RUN`。
22. Prompt 的对象模板使用三个不可作为最终文本的固定哨兵；任一哨兵原样出现在
    `requirement_text`、`requested_aspects[].aspect` 或 `rationale` 时，使用固定
    模型文本政策错误码拒绝并按既有上限完整重试，不得本地改写；
23. `requirement_text` 不得包含单次投影的 `N`/`D`/`S` 临时引用；证据身份只通过
    结构化引用字段表达，避免局部引用进入面向用户的需求或跨投影失效；
24. Prompt 为每个风险族提供与本 PRD 一致的确定性任务说明；本地只强制同名澄清/
    无界组合的非空 uncertainty 和证据不足的非空 evidence gap，不用中文关键词、
    模型自评或隐藏参照自动裁决其余语义质量。
25. `requirement_text`、`requested_aspects[].aspect`、`rationale`、`uncertainties[]`
    和 `evidence_gaps[]` 均不得出现独立的 `N`/`D`/`S` 投影临时引用；同样的引用只
    能通过原有结构化引用字段表达，嵌入普通标识的相似字符串不得被误拒绝；这些
    三位数字形式在候选自然语言中属于协议保留命名空间，若生产领域确需同形编码，
    应另行设计显示名称/转义合同而不是让模型猜测；
26. 证据不足对象模板使用独立的必须改写哨兵；该哨兵和既有三个哨兵在任一自然语言
    字段中原样残留时，继续使用固定模型文本政策错误码失败关闭并按既有上限完整重试；
27. Prompt v3 的系统说明和固定风险族任务必须共同约束结构定义/实例值边界、自然
    用户视角、无界组合的未收敛需求、具体证据缺口和新增节点基数一致性；本地校验
    只证明哨兵和协议保留临时引用等可判定事实，不宣称理解这些语义；
28. Prompt v3 只升级 Prompt provenance；模型输入/输出及候选 Schema 仍为 v1，
    结构化引用规范排序、单元级一次完整重试和候选非 Gold/非 Patch 资格保持不变。
29. Prompt v3 如需真实模型复验，必须重新冻结最终请求字节并单独批准；此前不得
    复用 Prompt v2 请求正文、哈希或外发授权，保持零网络调用。
30. 当前候选直接构造、模型解析和存储回放统一使用 Prompt v3 文本政策；不得根据
    `prompt_version` 对旧候选放宽临时引用或哨兵检查，兼容性例外必须另行版本化。

## Prompt v2 Follow-up Acceptance

- [x] Prompt 版本升级且请求中八个风险族分别获得固定任务说明；Schema 字段集与
  版本保持不变；
- [x] 三个模板哨兵在未改写时均以同一固定错误码失败，合法自然文本不受影响；
- [x] `requirement_text` 中独立出现 `N001`、`D001` 或 `S001` 均失败，结构化引用
  字段继续按原合同接受和规范排序；
- [x] 同名澄清/无界组合缺少 uncertainty、证据不足缺少 evidence gap 均失败；补齐
  对应字段后通过，其他风险族不被误加该跨字段门禁；
- [x] Provider 对上述 v2 合同失败仍只完整重试一次，不回填、删除或改写模型文本；
- [x] 聚焦回归、完整后端、前端测试/构建、任务校验和 `git diff --check` 通过；
- [x] 同一 312 节点完全虚构输入的新请求清单只在本地冻结，未获新的最终字节批准
  前保持零网络调用。

## Prompt v3 Follow-up Acceptance

- [x] Prompt provenance 升级为 v3，模型输入/输出及候选 v1 Schema、字段集和 digest
  域保持不变；
- [x] 独立 `N001`、`D001`、`S001` 在五组自然语言字段的任一位置均以固定文本政策
  错误码失败，结构化引用继续接受并由本地规范排序，`N001A` 等普通字符串不误拒绝；
- [x] 证据不足模板使用第四个必须改写哨兵，四个哨兵在任一自然语言字段残留均失败，
  Provider 仍只完整重试一次且不本地修补模型文本；
- [x] Prompt 明确已有节点复用的是结构定义而非实例值，候选采用自然用户视角；无界
  组合的缩小范围只写入 uncertainty，证据不足缺口必须具体化，新增节点描述与锁定
  cardinality hint 一致；
- [x] 不新增中文关键词门禁；内部元叙述、结构—实例边界与真实语义继续交给
  Codex/人工审核，不把 Prompt 文字断言或关键词命中率报告成信息树理解率；
- [x] 聚焦回归、完整后端、前端测试/构建、任务校验和 `git diff --check` 通过；
- [x] Prompt v3 未复用任何 Prompt v2 外发批准；如需真实模型复验，先重新冻结并
  审批完整请求字节，本轮实现阶段保持零网络调用。
- [x] 直接构造与存储回放不能通过伪装成 v2 的 `prompt_version` 绕过新文本政策；
  当前实验没有持久化候选原文，未来兼容需求留待可信合同版本升级。

## Acceptance Criteria

- [x] 相同树的节点存储重排产生相同计划、单元顺序、临时引用、覆盖矩阵和 digest；
- [x] 现有 48 节点青岚控制树产生所有预算内 branch-local 单元及适用挑战单元，
  不使用实例值作为候选答案；
- [x] 现有 312 节点语义树的隐藏参照可映射到 7 个核心风险族；新增节点放置通过
  独立 M3 overlay 补齐，基础 fixture 文件字节保持不变；
- [x] 核心 8 个风险族逐一得到 `CANDIDATE_READY` 或有确定性依据的
  `NOT_APPLICABLE`，不能静默遗漏；
- [x] 现有 2,001 节点青岚生产形状树在固定调用、节点和字符预算内生成计划，准确
  报告未投影节点/分支/风险族；
- [x] 未显式配置时最多生成 16 个计划单元；显式配置 32 可接受，超过 32 或布尔值
  使用固定错误码拒绝；
- [x] 默认预算内最多 8 个适用风险族各获得一个挑战单元，剩余名额用于一级分支；
  风险族不适用时，其名额可被分支基础单元确定性复用；
- [x] 一级分支超额时，最大、最深和最宽分支按固定顺序优先入选且去重，其余名额
  由规范化结构差异确定性补足；改变存储顺序不改变结构优先结果，同分才使用规范
  键决胜；
- [x] 超出计划单元预算的目标按确定性优先级记录为遗漏，批次为 `PARTIAL`，且相同
  输入重排得到相同的保留/遗漏集合；
- [x] 模型 transport 的总尝试次数不超过计划单元数的两倍；重试成功仍只归并一个
  候选，并分别报告 attempted/completed/failed/omitted 单元计数；
- [x] `BRANCH_LOCAL` 的所有证据引用具有相同一级祖先，跨分支引用固定错误码拒绝；
- [x] `CONTRAST` 只接受计划声明的有界上下文，额外分支固定错误码拒绝；
- [x] `AMBIGUITY` 可以合法缺少父提示或携带计划声明的冲突提示，不被错误修补；
- [x] 未知、重复、投影外、计划外和篡改引用使用固定错误码失败关闭；
- [x] `requested_aspects` 每项至少一个支持引用，多个非挑战主要诉求被拒绝或转人工；
- [x] 多个投影中的局部 `N001`/`S001` 不发生跨作用域碰撞；
- [x] 候选能无稳定 ID 外发地表达当前 `ValidationScenarioRequest` 的全部请求字段；
- [x] 待审核候选不能直接执行；缺少可信审核确认、最终请求、可观察 Oracle 或候选/
  来源 digest 绑定时固定错误码失败关闭；
- [x] 显式审核通过的内存场景可以执行首个意图阶段切片，且只产生意图阶段运行
  证据，召回和推荐阶段明确为 `NOT_RUN`；
- [x] 部分单元失败时，成功候选仍可独立审核，批次准确标记 `PARTIAL` 并披露失败
  单元，不能声称覆盖完成；全部执行单元失败时批次为 `FAILED` 且无可审核候选；
- [x] 候选和归并批次保持待人工审核、非 Gold、非 Patch，不直接注册验证数据集；
- [x] 模型视图不含稳定 node/tree ID、hash、label、route、path、`VALUE`、
  extension、metadata 或凭据；
- [x] 真实模型输入不含既有场景 request、风险标签、建议观察类别、覆盖矩阵或
  promotion 结论；隐藏参照只在模型输出完成后读取并审核；
- [x] 固定 transport replay 与真实模型评估分开报告，逐字复现不计为语义理解证据；
- [x] 聚焦 unittest、完整后端 unittest、前端回归和 `git diff --check` 通过。

## Definition of Done

- Tests added/updated，包括成功、边界、重排、篡改、模式越界、失败恢复、阶段边界
  和泄漏反例；
- `UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen` 通过；
- 配置的完整 `unittest` suite、前端 `npm test`/`npm run build` 和
  `git diff --check` 通过；
- 未配置的 lint、typecheck、coverage 或 CI 不报告为已通过；
- Python/Schema/serializer/parser/hash/replay 合同原子更新；
- 架构、规范和受保护环境部署说明随真实实现同步；
- 不自动 stage、commit、push、merge、归档或写工作日志。

## Research References

- [`research/branch-planning-options.md`](research/branch-planning-options.md) —
  修正后的场景规划、风险矩阵和分阶段验证方案。
- [`research/existing-dataset-reuse.md`](research/existing-dataset-reuse.md) —
  青岚三档 fixture 的复用层次、隐藏参照、风险映射和新增节点放置缺口。
- [`research/bailian-m3-scenario-preparation-experiment.md`](research/bailian-m3-scenario-preparation-experiment.md)
  — 312 节点完全虚构树的 M3 真实模型合同、覆盖和 Codex 聚合语义审核结果。
- [`research/bailian-m3-scenario-preparation-prompt-v2-experiment.md`](research/bailian-m3-scenario-preparation-prompt-v2-experiment.md)
  — 相同 312 节点虚构树的 Prompt v2 合同复验、已知缺陷 canary 和 A/B 限制。
- [`research/bailian-m3-scenario-preparation-prompt-v3-experiment.md`](research/bailian-m3-scenario-preparation-prompt-v3-experiment.md)
  — Prompt v3 的 312 节点虚构树首发合同结果、机械 canary 和语义复验限制。
- 父任务
  [`../07-30-tree-understanding-core/research/bailian-fictional-scale-experiment.md`](../07-30-tree-understanding-core/research/bailian-fictional-scale-experiment.md)
  — 完全虚构规模、合同、受引导和自主场景实验的聚合结果。

## Decision (ADR-lite)

**Context**：单次全树自由生成可以概括业务区域并生成自然语言，但不能稳定承担
覆盖规划、结构归属或测试 Oracle；当前信息树又没有实例值，事实问答不是目标。

**Decision**：采用确定性稀疏场景计划。规划器选择分支与风险锚点，模型生成结构
变更需求候选；计划支持 branch-local、contrast、ambiguity 三种模式；候选合同
面向完整 MVP，首个运行切片只验证意图阶段，并固定采用核心 8 个风险族；单次运行
默认最多 16 个计划单元、硬上限 32 个；最多 8 个名额用于适用风险族，其余用于
一级分支基础覆盖，未使用的风险名额自动归还分支覆盖；超额分支用结构极值和
规范化结构差异选择，内部 ID 仅作同分决胜；候选经显式可信审核冻结请求和可观察
Oracle 后，才允许进入仅执行意图阶段的首个验证切片。

现有青岚 48/312/2,001 节点 fixture 是 M3 的主要基座；基础树与已审核场景保持
不变，真实模型只接收从树生成的有界投影，既有场景作为隐藏参照在输出后审核；
缺少的新增节点放置风险通过独立 overlay 补齐。

**Consequences**：调用量和覆盖状态可审计，关键挑战场景不被单分支限制阻断；代价
是需要新计划/候选/批次合同及人工审核边界。节点投影覆盖只作披露，不能解释为
全树语义理解。

## Expansion Sweep

### Future evolution

- 在大分支内按结构或风险锚点继续递归细分，不改变运行级批次合同；
- 审核后的候选未来可进入独立的数据集编制任务，再扩展召回和推荐阶段 Oracle。
- 后续可增加显式业务重点或轮换游标作为规划输入，但不得让隐式运行状态破坏同一
  输入产生相同计划的可复现性。

### Related scenarios

- finding 质量审查与 finding 作为挑战场景锚点共享结构事实，但保持不同输出语义；
- 自由探索可作为确定性覆盖后的补充候选来源，不能改变覆盖完成状态。

### Failure and edge cases

- 多根树、无子节点根、超多一级分支、单分支超过预算和风险族不适用；
- 单元失败/重试、全单元失败、局部引用碰撞、树更新导致计划陈旧；
- 同名跨分支、模型遗漏诉求证据、模型生成实例查询或改变计划风险类型。

## Out of Scope (explicit)

- 实例数据事实问答或从 Schema 推测实际值；
- 自动 Oracle、自动 Gold、自动 Patch、生产树写入或验证数据集注册；
- 首切片执行召回和语义推荐阶段比较；
- Workbench UI、sidecar 持久化、数据库、队列、向量索引或新运行时依赖；
- 首切片的业务重点分支配置、跨运行轮换状态或自动审核/自动冻结 Oracle；
- 重新创建与现有青岚三档规模和角色重复的平行测试树；
- 对分支和风险族做笛卡尔积式全组合；
- 把自由探索结果计入确定性覆盖；
- 历史版本/Diff 联合理解；
- 真实生产数据外传或百炼自动回退。

## Technical Notes

- 确定性计划、候选草案与归并批次的所有者应继续位于
  `tree_understanding.py`；
- Provider 编排仍属于 `ai_review.py`，核心模块不得发起网络；
- 新持久化合同需要匹配的 `contracts/*.schema.json`、严格重建和可信来源回放；
- 可复用 `TopLevelBranchProfile`、现有树关系校验、`canonical_digest()`、
  `ValidationScenarioRequest` 字段形状和模型安全 helper，不复制源 DTO 遍历或
  哈希实现；
- 现有 `ValidationScenarioOracle` 只表达可观察合同状态，不是专家语义 Gold；
- 现有 fixture 路径为 `tests/fixtures/fictional/qinglan_library_control/`、
  `qinglan_library_semantic/` 与 `qinglan_library_production_shape/`；真实模型调用前
  只能读取树并构建允许列表投影，不能加载同目录参考场景或覆盖结论；
- 当前任务复杂度：Complex；当前三档完全虚构树分别有 4、6、6 个一级分支，按
  每分支一个基础
  单元加最多 8 个风险单元计算，预计需要不超过 12、14、14 个计划单元，均落在
  默认 16 单元预算内。每个单元最多两次 Provider 尝试，默认/硬上限下最坏模型
  HTTP 调用数分别为 32/64。

## Implementation Plan

1. **核心合同与 Schema**：新增不可变计划、单元、模型输入/输出、候选、审核输入、
   批次与覆盖合同；完成严格重建、digest、错误码和 JSON Schema 测试；
2. **确定性规划器**：实现核心 8 风险族锚点、三种规划模式、16/32 预算、均衡预留、
   结构代表性分支选择和有界局部投影；
3. **模型生成与归并**：在 `ai_review.py` 复用 Qwen/Bailian transport，实现每单元
   最多两次尝试、本地合同校验、运行级引用、去重以及 `SUCCESS/PARTIAL/FAILED`
   批次统计；
4. **显式审核与 INTENT 切片**：增加无持久化的可信审核门，绑定最终请求、可观察
   Oracle 与来源 digest，仅对已审核场景复用现有意图验证边界，其他阶段写
   `NOT_RUN`；
5. **现有数据集验证与文档**：直接复用青岚 48/312/2,001 节点树，以隐藏参照审核
   7 个既有风险族，并用独立 overlay 补齐新增节点放置；覆盖风险不适用、超预算、
   重排、篡改、重试/全失败、答案泄漏和审核绕过，再运行完整后端、前端与差异
   检查。
