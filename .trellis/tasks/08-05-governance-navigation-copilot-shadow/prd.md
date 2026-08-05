# brainstorm: 治理与导航 Copilot Shadow MVP

## Goal

在现有只读 Workbench 中形成一条可实际试用的治理/导航 Copilot 纵切：用户以自然语言
描述需求，系统给出有界候选及差异证据，必要时提出一次高区分度澄清，由人工完成最终
选择、拒绝或退出。成功不再定义为“任意文本自动绑定唯一节点”，而是候选可见、差异
可解释、不确定时安全退让、结果可回放。

## What I already know

- 已接受的 D1—D6 固定：原始 `requirement_text` 是权威输入；角色只是不可信软提议；
  Retrieval 只发现候选；Semantic 只判断候选关系；本地 Policy 产生状态；人工保留最终
  决定权。
- 当前没有达到门槛的 Retrieval 晋升候选。R2 只可作为可解释 lexical leg；H1/H2 不进入
  默认路径，也不在本任务通过更换 embedding、Prompt 或融合参数重启 H3。
- 现有 Workbench 已有“描述需求 → 确认意图 → 比较候选 → 专家复核”的界面和只读
  sidecar 流程，可作为 MVP 产品入口，无需新建另一套应用。
- 仓库已有隔离的 `StructuralIntentV2`、source-bound role proposal、relation-only
  Semantic 与确定性 Policy 合同，但它们尚未接入默认 Workbench，也没有 live v2、未见
  或生产能力资格。
- 当前页面或选中节点可以作为可选低信任上下文，但不得成为前提、硬路由或全树裁剪条件。
- 项目自编且由可信 manifest 证明为 clean-room 的完全虚构数据可调用本地、内网或外部
  LLM；隐藏 Oracle 仍不得进入被测模型输入。

## Assumptions (temporary)

- MVP 复用 Workbench 作为首个交互入口，同时新增清晰的后端 case/view 合同；不先做独立
  CLI 产品。
- 输入由原始需求、显式结构提示和可选页面/选中节点上下文组成；结构提示按本地校验优先，
  页面上下文只软加权。
- 固定展示最多8个候选，候选必须包含可解释的路径、节点种类、值类型、基数以及与请求的
  关系/差异，不把 Top-1 分数显示成业务真值。
- 单个 case 总计最多两次 LLM 调用：清晰路径为理解/角色提议和候选关系比较；澄清路径为
  首次理解和回答后重新理解，不再调用 Semantic；本地完成排序、状态、动作和回放。
- 候选状态至少区分 `CANDIDATES_AVAILABLE`、`AMBIGUOUS`、`NONE`、`NEED_EVIDENCE`；
  即使只有一个推荐候选，也必须由人工确认。
- 候选比较后最多提出一次澄清；仍不能收敛时停止自动处理并交给人工。

## Open Questions

- 无。新增范围或改变既定分母必须重新打开 PRD 审核，不在实现或实验过程中临时调整。

## Decision D1（已接受）：`NONE` 安全停止

**Context**：`NONE` 表示当前候选与证据不足以支持复用。若直接进入新增节点草稿，会把
候选导航、节点设计与新增治理三个职责重新耦合，并扩大首版合同和验收范围。

**Decision**：MVP 在 `NONE` 时展示无合适候选或证据缺口，允许用户改写需求或退出；
不从当前 case 发起新节点草稿，也不把 `NONE` 解释为新增许可。

**Consequences**：首版可以聚焦候选可见性、差异解释和安全退让。新增节点治理未来使用
独立纵切和明确人工状态机，不复用 `NONE` 作为隐式入口。

## Decision D2（已接受）：允许候选外人工纠正

**Context**：只允许从 Top-8 中选择会让召回漏失阻断用户，也无法在 Shadow 中区分“树中
没有目标”与“目标存在但未召回”。Workbench 已有完整树导航，可提供显式人工纠正入口。

**Decision**：当候选均不正确时，用户可以在同一可信树快照中导航并明确确认一个候选外
节点。系统本地校验节点仍存在、快照未漂移并重新展示结构差异，然后记录
`CANDIDATE_MISS / USER_CORRECTED`；不得把该结果计为模型或 Retrieval 命中。

**Consequences**：用户仍能完成导航任务，Shadow 可以直接测量候选覆盖和人工纠正率；
代价是需要新增候选外选择、快照绑定和明确确认的状态分支。该反馈仍是非 Gold、非审批、
非 Patch。

## Decision D3（已接受）：清晰请求直接进入候选比较

**Context**：Retrieval 只产生候选，不执行生产写入或授权动作；再设置一个强制“确认意图”
点击不会增加实质安全性，却会让主要交互重新变成表单审批。请求自身存在的歧义仍需要在
检索前解决。

**Decision**：请求自身没有会改变结构意图的互斥解释时，Workbench 展示精简、可编辑的
理解摘要后直接执行候选检索，不要求单独确认。只有请求自身存在实质歧义时，才在检索前
提出一次澄清；回答后仍不清楚则安全停止。

**Consequences**：常规路径减少一个人工门，保持对话式节奏；最终候选选择仍必须由人工
明确确认。精简摘要不成为权威事实，用户编辑后必须重新绑定请求并重算候选，不能修改旧
case 的已冻结来源。

## Decision D4（已接受）：第一版采用单 case 短对话

**Context**：首版需要验证的是“自然语言需求能否形成可用候选、差异和安全退让”，而不是
长期记忆或多轮任务规划。跨需求记忆会引入上下文污染、case 边界和回放归因问题，也会让
召回、Semantic 与交互失败难以分开统计。

**Decision**：一个 case 只处理一个原始需求；允许最多一次实质澄清，并以一次人工选择、
候选外纠正、拒绝全部或退出结束。用户提出新的需求时创建新 case，不继承上一 case 的
模型摘要、候选、角色提议或页面上下文。

**Consequences**：首版状态机和验收分母保持清楚，每次结果都能绑定唯一请求与树快照；
暂不支持同一 case 内反复改写、连续追问、跨 case 用户画像或长期会话记忆。

## Decision D5（已接受）：原始需求召回保底，角色与上下文只做软重排

**Context**：现有 R2 在进入候选比较前要求 TARGET 名称或路径具有非零词面信号，错误的
角色提议可能使正确候选提前消失；v1 `CandidateSet` 又依赖旧 Intent 和强制确认状态。
两者都不能直接满足 D1—D4 的产品边界。

**Decision**：第一版始终从原始 `requirement_text` 对完整可信树形成有界宽候选池；角色
提议、显式结构提示、页面上下文和选中节点只能参与软重排及解释，不能决定候选资格，也
不能把原始需求恢复路径裁剪为零。多路信号按稳定节点身份确定性合并、去重，最终最多8项
进入 relation-only Semantic 和 Workbench。R2 只可复用为软特征或实验对照腿。

**Consequences**：候选漏失可与 Semantic/人工选择错误分别计量，错误上下文不会成为错误
前提；但该方案仍是可解释的首版召回底座，不因此获得生产检索资格。候选外人工纠正继续
作为安全出口，并严格记为 Retrieval miss。

## Decision D6（已接受）：弱证据候选可见，但不得形成默认推荐

**Context**：若以严格阈值直接隐藏弱候选，非字面表达或首版词法底座的漏失会表现为空白
失败，用户无法判断候选是否仍有帮助；若把弱候选按普通推荐展示，又会把排序分数伪装成
业务置信度。

**Decision**：宽召回存在候选但整体证据不足时进入 `NEED_EVIDENCE`，仍展示最多8项并明确
标记“证据较弱”；不预选、不突出唯一推荐、不允许一键接受。用户必须主动查看差异后选择、
进行候选外纠正、拒绝全部或退出。候选池确实为空时才进入 `NONE`。

**Consequences**：首版保留人工判断机会，并能分别统计“无候选”和“有弱候选但证据不足”；
同时需要 UI、API 和回放合同明确区分候选顺序、证据强弱与业务推荐。

## Decision D7（已接受）：首版终点是导航/高亮与 Shadow 记录

**Context**：候选确认之后继续打开治理操作表单，会把节点导航效果与表单字段、权限和后续
治理流程混入同一验收分母；当前任务首先需要证明“理解—候选恢复—关系比较—人工确认”
这条纵切是否可用。

**Decision**：人工最终选中候选或完成候选外纠正后，Workbench 只导航并高亮可信树快照
中的对应节点，同时写入私有 Shadow sidecar；不自动创建或打开治理操作、草稿、Patch 或
审批表单。拒绝全部、`NONE` 和退出同样只记录终态。

**Consequences**：首版可以独立测量候选导航价值和人工成本，不受后续治理流程干扰；未来
若要衔接治理操作，必须新建纵切并重新审核权限、字段传递和写入边界。

## Decision D8（已接受）：理解模型失败时降级到原始需求召回

**Context**：理解/角色提议只负责提供软信号。若其超时、不可用或合同失败就中止 case，
它实际上会重新成为候选资格的硬门，并违背原始需求召回保底的 D5。

**Decision**：理解模型失败时不重解释其原始响应，也不生成猜测字段；系统记录固定降级
原因，使用原始 `requirement_text` 和本地可信提示继续宽候选恢复，不应用角色软重排，并在
Workbench 标明“理解能力已降级”。只有原始需求未通过本地输入校验或树快照不可信时才
中止 case。

**Consequences**：单次模型故障不会阻断导航，且可以分别统计完整路径与降级路径；降级
结果不得计为理解模型成功，也不得隐藏模型合同失败。

## Decision D9（已接受）：Semantic 失败时保留候选并进入证据不足状态

**Context**：Retrieval 候选及其树结构差异来自本地可信快照。若候选关系比较模型超时、
不可用或合同失败就丢弃候选，会把可用的人工导航能力一并阻断；若在缺少 Semantic 证据时
仍给出推荐，则会制造错误自信。

**Decision**：Semantic 失败时丢弃该次模型关系输出，保留 Retrieval 候选并统一进入
`NEED_EVIDENCE`；Workbench 只展示可信树结构差异和明确的降级原因，不显示模型关系结论、
默认推荐或一键接受。用户仍可主动选择、候选外纠正、拒绝全部或退出。

**Consequences**：第二次模型调用也不成为单点故障，用户仍能完成受控导航；完整路径与
Semantic 降级路径必须分开记账，后者不得计入关系判断成功率。

## Decision D10（已接受）：预注册首轮生产 Shadow 扩围门槛

**Context**：Shadow 的目标是判断候选 Copilot 是否值得扩围，而不是证明模型可以自治。若在
观察结果后再选择样本、分母或阈值，候选覆盖、错误自信和人工效率都可能被重新解释。

**Decision**：首轮生产 Shadow 在受保护环境内至少收集30个有效 case，且覆盖不少于3名
用户。扩围必须同时满足：

- 所有有效 case 的安全终止、可信树快照绑定和零生产写入均为100%；
- 对“人工最终确认树中存在目标”的 case，目标进入初始 Top-8 的比例不低于80%；候选外
  人工纠正只计完成，不计 Retrieval 命中；
- 对“树中存在目标且允许人工纠正”的导航 case，通过候选选择或候选外纠正完成导航的
  比例不低于90%；
- 对系统标记证据充分并突出候选的 case，最终被用户拒绝全部或候选外纠正的比例不高于5%；
- 已完成导航 case 从提交原始需求到最终处置的中位耗时不超过3分钟；
- 外网仓库和公开聚合只保存固定状态、允许字段及聚合统计，不复制生产请求正文、模型原始
  流量、稳定内部节点 ID 或其他受保护内容。

**Consequences**：这些阈值只决定是否扩大 Shadow 范围，不授予自动绑定、生产写入、Gold
或 Patch 资格。任一安全指标不满足立即停线；效果或耗时指标不满足则记录失败并回到对应
阶段分析，不在同一批次修改分母或阈值。

## Decision D11（已接受）：澄清路径保持单 case 两次模型调用

**Context**：清晰路径可以在两次调用内完成“理解 → Semantic”；但澄清路径若依次执行首次
理解、回答后重新理解和 Semantic，会达到三次。跳过重新理解又会让陈旧结构意图进入候选
关系比较，本地从自然语言回答猜测结构字段也不属于确定性事实。

**Decision**：单个 case 的逻辑模型调用总预算固定为两次。清晰路径执行“理解 → 宽召回
→ Semantic → 本地 Policy”；澄清路径执行“首次理解 → 人工回答 → 重新理解 → 宽召回”，
随后统一进入 `NEED_EVIDENCE`，不再调用 Semantic。重新理解后仍有实质歧义则进入
`CLARIFICATION_LIMIT_REACHED` 并安全停止。

**Consequences**：澄清路径不会使用陈旧结构意图或突破调用预算，但缺少模型关系比较；
其候选只展示可信结构差异且不提供默认推荐。Shadow 聚合必须把清晰完整路径、澄清降级
路径和模型失败降级路径分开记账。

## Requirements (evolving)

- 原始需求始终保留为宽候选恢复路径；模型角色提议、页面上下文和选中节点均不得单独把
  合法候选硬裁剪为零。
- 理解模型超时、不可用或合同失败时记录固定降级原因，禁用角色软重排，并继续使用原始
  需求和本地可信提示召回；不得把降级计为模型成功。
- Retrieval 输出有界候选和可回放证据，不批准复用、新增或 Patch。
- Semantic 对候选逐项给出关系和证据充分性；不得输出最终动作或稳定节点 ID。
- Semantic 超时、不可用或合同失败时丢弃模型关系输出，保留 Retrieval 候选并进入
  `NEED_EVIDENCE`；只展示可信结构差异，不提供默认推荐或一键接受。
- 单个 case 总计最多两次逻辑模型调用；澄清路径的第二次调用只重新理解回答，完成召回后
  进入 `NEED_EVIDENCE`，不得再调用 Semantic。
- 本地确定性 Policy 产生候选可用、歧义、无候选或证据不足状态，并构造单一澄清门禁。
- 清晰请求展示精简理解摘要后直接检索；只有请求自身存在实质歧义时才在检索前澄清一次，
  不设置常规“确认意图”门。
- Workbench 展示候选差异，支持人工选择候选、拒绝全部、回答一次澄清或退出。
- `NEED_EVIDENCE` 仍展示最多8项弱证据候选，但不预选、不突出唯一推荐，也不提供一键
  接受；`NONE` 仅用于候选池确实为空。
- 一个 case 固定为一次原始需求、最多一次澄清和一次最终处置；新需求必须创建新 case，
  不继承上一 case 的模型状态或候选状态。
- 候选均不正确时，允许用户从同一树快照显式选择候选外节点；必须记录为召回漏失后的
  人工纠正，而不是系统命中。
- `NONE` 只展示无候选/证据缺口，并允许改写需求或退出；不得创建新节点草稿或新增许可。
- 最终选择或候选外纠正只导航/高亮可信节点并记录私有 Shadow sidecar，不自动打开或创建
  治理操作、草稿、Patch 或审批表单。
- 所有人工反馈保持 `OPERATIONAL_FEEDBACK_ONLY`，不形成 Gold、语义批准或 Patch 资格。
- 完整结果只写私有 sidecar；公开/API 聚合视图使用独立正向允许列表，不暴露凭据、模型
  原始流量、稳定内部 ID、隐藏 Oracle 或受保护字段。
- 默认 v1 产品入口在新纵切完成聚焦验证和显式晋升决定前保持不变。

## Acceptance Criteria (evolving)

- [x] 使用完全虚构树覆盖候选唯一、候选歧义、无候选、证据不足和一次澄清五条完整路径；
- [x] `NEED_EVIDENCE` 可查看弱候选但没有默认选择或一键接受；`NONE` 不展示伪候选；
- [x] 清晰请求无需意图确认即可进入候选比较；请求自身歧义最多澄清一次，仍不清楚则停止；
- [x] 错误选中节点和错误角色提议均不会硬过滤原始需求的宽候选恢复路径；
- [x] 理解模型超时、不可用和合同失败均可降级完成原始需求召回，界面和 Shadow 记账可见，
  且原始需求无效或树快照不可信时安全中止；
- [x] 候选视图最多8项，顺序确定，差异字段来自可信树和本地合同；
- [x] Semantic 输出不含动作，最终状态和人工可执行动作由本地 Policy 决定；
- [x] Semantic 超时、不可用和合同失败均保留候选并进入 `NEED_EVIDENCE`，且不会泄漏不完整
  模型输出或形成默认推荐；
- [x] 清晰路径最多执行理解和 Semantic 两次调用；澄清路径最多执行首次理解和重新理解
  两次调用，Semantic 调用数为零，仍有歧义时安全停止；
- [x] `NONE` 路径不会创建候选外新增草稿、Patch 或任何新增授权，只允许改写需求或退出；
- [x] 人工选择、拒绝、澄清和退出均可从可信来源重放，且保持非 Gold、非审批、非 Patch；
- [x] 单个 case 在一次最终处置后关闭；后续新需求创建新 case，跨 case 不复用模型摘要、
  候选或角色提议；
- [x] 候选外纠正校验可信树快照和节点存在性，记录 `CANDIDATE_MISS/USER_CORRECTED`，
  且不进入模型/召回命中分子；
- [x] 最终选择只触发可信节点导航/高亮和私有 Shadow 记录，不触发治理表单或任何写入；
- [x] Shadow 聚合至少记录候选覆盖、人工接受/纠正、错误自信、澄清次数、审查耗时和证据
  覆盖，不保存逐项敏感正文；
- [x] 生产 Shadow run manifest 可冻结部署提交、Provider、计划 case 数、至少 3 个匿名
  参与者和 D10 阈值，配置不完整、提交漂移、Provider 漂移或参与者未注册时失败关闭；
- [x] 导航 outcome 保持不变，独立资格记录可区分目标存在但未找到、目标不存在、无法判断
  和退出，使 Top-8 与导航完成率使用可解释的目标存在分母；
- [x] 私有离线聚合可跨多个参与者实例严格回放资格记录，拒绝错误 run、重复 outcome、
  超计划记录、公开权限和篡改，并且聚合不输出请求、节点、参与者引用、路径或 hash；
- [ ] 首轮生产 Shadow 的30个有效 case、至少3名用户及 D10 的分母和阈值在启用前冻结，
  运行后不得调整；
- [ ] 扩围门槛同时满足：安全终止/快照绑定/零写入100%，Top-8 覆盖不低于80%，人工导航
  完成不低于90%，错误自信不高于5%，完成耗时中位数不超过3分钟；
- [x] v1 Workbench、CLI、Provider 与既有实验回归保持通过；
- [x] 未获显式晋升前，新纵切只能通过隔离 feature path 使用。

## Definition of Done

- Tests added/updated (unit/integration where appropriate)
- `uv sync --frozen`、已配置的 `unittest`、前端 test/build 和 `git diff --check` 通过
- 未配置的 lint/typecheck/coverage 工具不报告为通过
- 合同、API、Workbench UI 和任务说明同步
- 失败路径安全停止，且没有生产树、数据库或 Patch 写入
- 实际 Shadow rollout/rollback 与数据边界在启用前另行审核

## Out of Scope (explicit)

- 不自动修改信息树、创建节点、发布 Patch 或连接生产数据库；
- 不从 `NONE` case 发起新节点草稿或新增治理流程；
- 不在候选确认后自动打开治理表单或串联后续治理操作；
- 不把人工反馈升级为 Gold 或专家共识；
- 不启动 H3，不在已揭盲 H1/H2 数据上继续调 embedding、Prompt、Top-K 或融合参数；
- 不承诺任意自由文本都能绑定唯一节点；
- 不增加第三次及更多常规模型调用；
- 不支持同一 case 内反复自动改写、多轮任务规划、跨 case 记忆或用户画像；
- 不使用完全虚构数据单独宣称生产资格。

## Technical Approach (provisional)

推荐采用 Workbench-first 的候选 Copilot：复用现有 case/operation/私有 sidecar 外壳，
在独立 v2 feature path 中接入固定四键理解、宽候选恢复、relation-only Semantic 和本地
Policy，再新增候选差异视图与人工状态。这样可以复用现有安全边界，同时避免把实验性的
R1/R2/H1/H2 直接切成默认产品链路。

候选恢复采用第一条路线，另外两条仅保留为被拒绝的备选：

1. **原始需求召回底座 + 软重排（推荐）**：始终保留 `requirement_text` 对全树形成的宽候选
   池，角色提议、页面上下文和选中节点只调整分数和解释，不具备淘汰权；随后稳定去重并
   投影最多8项给 Semantic 和 UI。
2. **直接复用 R2**：代码复用最少，但当前 R2 要求 TARGET 词面信号非零，角色仍是硬门，
   与 D1—D6 的边界冲突。
3. **继续使用 v1 `CandidateSet`**：已接入 Workbench，但依赖旧的自由文本 Intent 和强制
   确认状态，难以表达 D3、D4 以及角色不硬剪枝的新合同。

## Implementation Plan

### Phase 1：冻结 Copilot 核心合同

在独立 `src/treeguard/navigation_copilot.py` 中建立不可变、可回放的产品合同，不修改 v1
`change_intent/retrieval/semantic_recommendation` 的既有语义：

- 有效理解包装：区分 `MODEL_VALID`、`MODEL_DEGRADED` 和回答后重新理解，绑定原始请求、
  树快照、固定降级码和可选 `ChangeUnderstandingV2`；
- 单轮澄清回答/轮次：绑定首次 understanding 和回答，保证第二次 understanding 可从可信
  来源重放，且调用预算为2；
- 候选恢复集：绑定原始需求、有效理解、快照、算法版本和最多40项内部池；角色、显式提示、
  页面/选中上下文只影响显式分项，不具有候选淘汰权；
- Semantic 投影/关系草稿/本地状态：最多8个临时 `C001`—`C008`，模型只返回关系，本地形成
  `CANDIDATES_AVAILABLE / AMBIGUOUS / NONE / NEED_EVIDENCE`；
- 人工终态：`SELECT_CANDIDATE / SELECT_OUTSIDE_CANDIDATE / REJECT_ALL / EXIT`，固定
  `OPERATIONAL_FEEDBACK_ONLY`、非 Gold、非审批、非 Patch；
- Shadow 聚合：只接收已终结的可信 case 记录，按 D10 固定分母产生允许列表指标。

同步新增版本化 `contracts/navigation-copilot-*.v1.schema.json`，并在现有 relation-only
模块中只提取确有两个消费者的公共 assessment parser；不复制规范哈希、严格解析或模型
引用校验。

### Phase 2：实现宽召回保底与软重排

- 复用 `retrieval_query` 的原始需求词法文档和确定性分项，但新增不依赖 v1
  `IntentConfirmation` 的 Copilot 查询构造入口；显式 request hints 优先，模型结构字段仅在
  hint 未指定时补充。
- 从完整可信 resource 树产生最多40项内部正词面候选池；无词面候选才是 `NONE`。
- 从 `retrieval_role_tolerant.py` 提取窄的公共角色相似度特征供 R2 和 Copilot 共用；R2 保持
  原行为，Copilot 只把 TARGET/SCOPE/EXCLUSION 转成正负软分，不执行 TARGET/EXCLUSION
  hard filter。
- 对错误角色、错误选中节点、错误页面上下文建立保底测试：原始需求池中的节点不能因此
  消失；最终稳定节点身份去重、总分降序和 node ID 并列规则确定。

### Phase 3：接入两段 v2 Provider 与降级路径

在 `ai_review.py` 复用现有百炼、Qwen 和 loopback transport，增加窄的
Change Understanding v2 与 Semantic Relation Provider：

- Prompt 只使用各自正向允许列表投影，JSON Object、关闭 thinking、最多一次合同纠错；
- trace stage 新增 `CHANGE_UNDERSTANDING`、`CHANGE_UNDERSTANDING_CLARIFICATION` 和
  `SEMANTIC_RELATION`，仍只驻留显式启用的当前进程内存；
- Provider/合同失败由应用编排捕获并转为固定降级码，不保存原始响应到 sidecar；
- 理解失败使用原始需求和显式 hints 继续召回；Semantic 失败保留候选并进入
  `NEED_EVIDENCE`；
- loopback simulator 仅增加完全虚构的协议响应，不把仿真成功描述为语义能力。

### Phase 4：新增隔离的 Workbench Copilot 服务

新增 `src/treeguard/workbench_navigation_copilot.py`，由它独占新 case 状态机和 sidecar
序列；`workbench_governance.py` 的 v1 路径不改语义：

1. 创建 case、重读可信树并发布请求；
2. 运行理解；清晰时直接召回与 Semantic，存在请求歧义时等待一次人工回答；
3. 澄清回答后重新理解；若解决则召回并进入 `NEED_EVIDENCE`，否则安全停止；
4. 展示最多8项候选和可信结构差异；弱证据/降级路径不预选、不突出、不一键接受；
5. 人工完成候选选择、候选外树导航纠正、拒绝或退出；候选外纠正验证同一快照并记录
   `CANDIDATE_MISS / USER_CORRECTED`；
6. 终态只返回一次性导航引用供页面高亮，并写私有 sidecar；不打开治理表单；
7. 当前进程内聚合 D10 指标，重启后明确重新计数，不伪装 sidecar 自动恢复。

使用默认关闭的 `TREEGUARD_WORKBENCH_NAVIGATION_COPILOT=0|1` 严格开关。关闭时不创建
Copilot service、case 或 sidecar；既有 v1 API 和页面默认入口保持不变。

### Phase 5：HTTP 允许列表与前端短对话

- `web.py` 新增隔离的 `/api/v1/navigation-copilot/*` DTO/路由：capability、创建、读取
  case/operation、提交一次澄清、提交最终 outcome、读取当前进程聚合；所有响应继续
  `no-store/nosniff`，错误只返回固定 code。
- `web/src/api.ts` 增加精确 TypeScript DTO；不返回需求原文、稳定节点 ID、hash、sidecar
  路径、模型原始流量或人工自由文本。
- 新增 `web/src/NavigationCopilotPanel.tsx`，仅在 capability 启用时由 `App.tsx` 显示
  Shadow 入口；现有 `GovernancePanel` 保持默认。
- 页面流程固定为“一次需求 → 可选一次澄清 → 候选差异 → 一次最终处置”；候选选择后调用
  App 的节点导航回调高亮对应 `N` 引用，新需求显式 reset 为新 case。
- `NEED_EVIDENCE`、理解降级、Semantic 降级、`NONE` 和候选外纠正使用不同可见状态；任何
  状态都不显示自动写入或治理表单入口。

### Phase 6：聚焦验收、完整回归与启用前审核

新增/修改测试的文件所有权：

- 核心与合同：`tests/test_navigation_copilot.py`、`tests/test_contract.py`；
- 召回软门：`tests/test_retrieval_query.py`、`tests/test_retrieval_role_tolerant.py`；
- Provider/仿真：`tests/test_ai_review.py`、`tests/test_simulator.py`；
- Workbench/API：`tests/test_workbench_navigation_copilot.py`、`tests/test_web.py`（若现有 HTTP
  测试仍归 `test_workbench_governance.py`，实施前按真实所有者选择其一，不复制套件）；
- 前端：新增聚焦 Vitest，覆盖短对话状态、弱证据无默认选择、候选外纠正、节点高亮和
  feature flag；
- v1 回归：现有 change intent、retrieval、semantic、Workbench governance 和 validation
  套件保持通过。

最小行为矩阵必须覆盖：清晰完整路径、合法澄清两调用路径、澄清耗尽、理解失败降级、
Semantic 失败降级、弱证据、空候选、多个候选、错误角色/上下文、候选外纠正、快照漂移、
重复终态拒绝、重排确定性、sidecar 发布失败、泄漏 canary、D10 分母和默认开关关闭。

实施完成后执行项目真实验证：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -v
cd web && npm ci
cd web && npm test
cd web && npm run build
git diff --check
```

完成代码和本地虚构验证后仍不自动启用生产 Shadow。启用前单独审核 feature flag、受保护
sidecar 位置、Provider 模式、D10 计数起点、停线与回滚；获准后才收集30个有效 case。

### Phase 7：修复生产 Shadow 分母与跨实例记账

- 新增 `navigation_shadow_run.py`，把部署提交、Provider、计划 case 数、匿名参与者和 D10
  阈值冻结为不可变 run manifest；
- 保持 outcome v1 只表达导航动作，另以 qualification sidecar 区分目标存在但未找到、
  目标不存在、无法判断和退出；
- 新增 `treeguard-navigation-shadow prepare-run|aggregate`，只读取/写入受保护的 `0700`/
  `0600` 工件，跨参与者实例输出正向允许列表聚合；
- 生产采样仍需在受保护环境另行创建真实 run manifest 并审核 rollout/rollback，本阶段不
  访问真实树、真实请求、真实人员身份或模型流量。

## Research References

- [`research/repository-entry-points.md`](research/repository-entry-points.md) — 现有 Workbench、
  v2 合同、候选与人工复核边界，以及本任务最小复用路径。
- [`research/candidate-recovery-options.md`](research/candidate-recovery-options.md) — 三条候选
  恢复路线的仓库证据、边界和推荐结论。
- [`research/implementation-readiness-review.md`](research/implementation-readiness-review.md)
  — 实施前规范加载、职责所有权和澄清路径调用预算冲突。
- [`research/production-shadow-readiness-audit.md`](research/production-shadow-readiness-audit.md)
  — 基于已提交实现的启用前审计；说明现有 D10 分母、参与者绑定、跨进程聚合和运行冻结
  的缺口，以及推荐的单参与者实例加私有离线汇总路径。
- [`../08-04-governance-architecture-convergence/research/architecture-convergence-verdict.md`](../08-04-governance-architecture-convergence/research/architecture-convergence-verdict.md)
  — 已接受的 D1—D6、关闭路线和新任务进入条件。

## Technical Notes

- 现有产品服务入口：`src/treeguard/workbench_governance.py`；
- 现有 Workbench 面板：`web/src/GovernancePanel.tsx`；
- 隔离理解合同：`src/treeguard/change_understanding_v2.py`；
- 隔离关系与 Policy：`src/treeguard/semantic_policy_v2.py`；
- 当前任务处于 `in_progress`；核心、Provider、隔离 Workbench/API、短对话前端和本地
  虚构验证已实现。生产 Shadow 的 30 个有效 case、3 名用户、D10 阈值运行及晋升决定仍未
  执行，feature flag 继续缺省关闭。
- 提交 `95e8f99e9227e992a84e7ddd157588087d25436f` 的启用前审计结论为 `NO_GO`：现有
  `REJECT_ALL` 无法区分目标存在、目标不存在和无法判断，参与者数量没有可信绑定，聚合又
  只存在于单进程内存。正式采样前先实现冻结 run manifest、可计算目标存在性的终态合同和
  私有离线汇总；该结论不否定单 case 安全演练能力，也不属于模型效果失败。
- 上述仓库侧缺口已由 Phase 7 实现并通过完整回归；`NO_GO` 的剩余含义仅是尚未在受保护
  环境冻结最终 run、审核 rollout/rollback 和完成 30 个有效 case，不再是分母合同缺失。
