# 构建导航 Copilot 密封 clean-room 数据 v3-C b02

## Goal

在功能实现基线 `cdf3250629ffcbddb9bd9f0c461a89a23affcd4b` 上，并以本 v3-C 合同的最终
提交为数据构造基线，由新的独立 clean-room 构造主体从空白建立一棵未参与当前产品调参的
虚构 resource 信息树，以及 Navigation
Copilot 密封资格测评所需的公开 scenario、隐藏 Oracle、Codex Silver 审核和冻结
preflight。v3-C `b01` 因执行合同不兼容在提交前被拒绝；`b02` 在未接触任何
被测结果的前提下，保留已审核的独立 authoring 语义源，并使用功能基线已有
密封合同重建执行投影。数据任务不运行被测链路、不接触模型结果，并在数据
提交和 execution manifest 分别冻结后才允许交接执行。

## What I already know

- 父任务已接受 48 条主分母与 16 条挑战重复子集；
- 现有 H1/H2、M4/M5、M4.9、R2、fire validation 和青岚请求/Oracle 均已参与生成、审核、
  实验或调试，只能作为禁读/相似性边界，不能复用为最终资格样本；
- 本项目独立构造且 manifest 证明为 clean-room 的完全虚构数据可调用外部 LLM，但隐藏 Oracle
  仍不得进入被测模型输入；本任务本身不调用被测模型；
- 数据可由 Codex 审核为 Silver，但不得声称 Gold、专家共识、生产或 Patch 资格。
- v2 在 data-commit 人工审阅门被拒绝：工程冻结与泄漏隔离通过，但树存在模板乘积扩展，
  且弱证据和个别澄清场景的语义不满足类别定义；v2 不得提交、执行、热修或成为 v3 的
  数据、蓝图、措辞、目标、Oracle、审核决定或生成器来源。
- v3-A 在提交前因共享统一服务单元骨架被拒绝；v3-B 虽达到 105/105 语义签名唯一，仍通过
  列表循环、拓扑复用及 role/type 轮换扩树，证明单一语义签名门禁可被生成公式规避；两批
  均不得提交、执行、热修或成为 v3-C 的数据、蓝图、措辞、目标、Oracle、审核决定、
  生成器或显式目录来源。
- v3-C `b01` 在 data-commit 审阅门被拒绝：700 节点显式蓝图、双签名和逐项
  Silver 审核未发现 v3-A/B 的模板造树问题，但冻结 scenario/Oracle 自建了与
  `SealedScenario` / `SealedCaseOracle` 不兼容的平行合同，且把 `WEAK_EVIDENCE`
  错误定义为 `PROCEED / ALLOW / 选择节点`；冻结器还把 Git 不能持久化的
  `0600` 工作树权限当成 checkout 后合同。`b01` 固定为
  `REJECTED_PRECOMMIT_EXECUTION_CONTRACT_MISMATCH`，不得提交、物化 execution manifest
  或执行资格测评。
- `b01` 拒绝前未运行模型、Retrieval、Semantic、Policy、runner 或任何效果评分，
  因此未产生按被测结果调样的污染。新 `b02` 可在本 PRD 专门例外下保留
  `b01` 已审核的独立语义 authoring source，但必须重建全部执行投影、绑定和
  弱证据 Oracle，不得伪称 `b01` 未被拒绝或继续同一 qualification run。

## Clean-room Restart

- v3-C 必须使用新的 worktree、任务执行主体、batch ref、namespace、seed、稳定 ID 规则和
  显式异构蓝图目录；
- v3-C 构造主体不得读取 v1/v2/v3-A/v3-B 工作树、fixture、生成器、场景、Oracle、审核、preflight、
  Prompt、模型请求/响应或逐项审阅结论；只允许读取本 PRD、功能基线公开合同与项目规范；
- 本 PRD 中记录的历史批次聚合失败类别只用于门禁设计，不授权按旧数据逐项改写；
- 当前审阅主体只负责冻结合同和后续 data-commit 审核，不参与 v3-C 数据生成。

### v3-C b02 恢复边界

- `b02` 必须使用新的 `batch_ref`、namespace、seed、稳定身份绑定和冻结
  digest；实施方案必须在生成任何 `b02` 工件前冻结这些常量。
- 允许保留 `b01` 从空白独立编制且已审核的蓝图语义、树拓扑、候选请求
  文本、非弱证据语义判断和 91 项蓝图审核。重绑时必须证明这些语义
  payload 与 `b01` 逐项相等，除新 batch/version/identity 字段外不得悄然改写。
- 禁止保留或复用 `b01` 的 `frozen/scenarios.json`、`frozen/hidden-oracle.json`、
  `manifest.json`、`preflight.json`、权限声明、文件 digest、执行终态、平行枚举
  与 5 条弱证据 Oracle。
- `b02` 数据主体可读取功能基线的公开 `navigation_copilot_sealed_validation`
  合同及其确定性投影 owner，但仍不得读取任何模型请求/响应、逐项执行结果或
  过往资格评分。

## Requirements

- 从空白独立构造 700—1,000 节点 resource 树，`VALUE` envelope 为 0，来源固定为
  `CLEANROOM_SYNTHETIC / fictional=true / derived_from_real=false`；
- 树包含 6—10 个语义连贯顶层分支、4—6 层深度、同层近邻、跨分支近义、节点种类冲突、
  值类型/基数冲突和多个可接受目标；
- 树的语义来源必须是一份逐项显式编写的异构蓝图目录。每个非叶节点的名称、父子角色、
  kind、值类型、基数、子节点和语义说明必须直接存在于目录中；数据生成器只能严格校验、
  分配稳定身份并序列化该目录，不得生成、轮换、拼接或推导任何语义字段；
- 禁止使用“维度列表 × 指标列表”、对象列表 × 同一子树模板、名称列表 × 账册模板、共享
  topology × role/type 轮换、模运算选取 facet/property 等公式扩充节点；不得通过改名、
  改 ID、调序、替换 role、value type 或 cardinality 制造虚假多样性；
- preflight 必须同时计算两类规范子树签名。两者均排除名称、稳定 ID 和 sibling 顺序：
  - 语义签名保留节点 kind、值类型、基数、子节点角色及递归语义签名；
  - 骨架签名只保留节点 kind、直接子节点数量及递归骨架签名，明确排除 role、值类型和基数；
- 对含至少 5 个后代的实例，语义签名最大重复组不超过 3、重复实例比例不超过 20%；骨架
  签名最大重复组不超过 4、重复实例比例不超过 40%。preflight 分别报告两类签名的合格
  实例数、唯一数、最大重复组、重复实例数和比例；
- 每个含至少 5 个后代的非叶蓝图都必须完成逐项 Codex Silver 父子语义审核，不再只抽样
  24 个签名；审核说明必须针对该节点的具体父职责、子角色组合与边界，不得使用模板句、
  结构 hash、节点计数或“指标已通过”替代语义判断；
- 精确生成 56 条候选，候选类别预配额固定为 12/12/9/5/7/5/6；冻结精确 48 条：字面
  唯一 10、非字面唯一 10、结构干扰 8、多个
  可接受目标 4、合法澄清 6、弱证据目标 4、树中无目标 6；
- 非字面精确覆盖同义、缩写、口语目的、轻微错别字和跨层表达各 2 条；
- 预注册 8 条错误/无关页面上下文压力项；从非字面、结构干扰、澄清和弱证据各固定 4 条，
  形成 16 条重复性子集；标签不改变主类别配额；
- scenario 与 Oracle 物理分离。authoring 候选可保留经审核的页面文本用于说明语义，
  但冻结公开 scenario 只能使用 `SealedScenario` 的正向允许列表；页面压力只通过
  `proposed_parent_ref` 表达。公开 scenario 不得包含目标、期望路线/Policy/终态或评分答案；
- `b02` 不得再发明冻结合同。冻结的 48 条 scenario 必须由功能基线的
  `SealedScenario.create()` 构造，48 条 Oracle 必须由 `SealedCaseOracle.create()` 和
  `TerminalExpectation` 构造；持久化后分别由对应 `from_dict()` 逐条重建。
- authoring 类别到执行类别的映射必须固定为：
  `NON_LITERAL_UNIQUE -> NONLITERAL_UNIQUE`、
  `STRUCTURAL_DISTRACTOR -> STRUCTURAL_INTERFERENCE`、
  `MULTIPLE_ACCEPTABLE -> MULTI_ACCEPTABLE`、
  `NO_TARGET -> TARGET_ABSENT`；其他类别同名传递。冻结文件不得保留
  authoring-only 枚举。
- 目标、干扰与澄清对照必须从 blueprint ref 确定性映射到同一冻结树的稳定
  node ID。错误页面上下文不得作为自由文本绕过执行合同；8 条压力项必须逐项
  绑定到同一树中合法但语义错误的 `proposed_parent_ref`，且由已有确定性投影
  `build_tree_reference_index()` 产生 `Nxxxxxx` 引用，不得新建排序/引用公式。
- Oracle 至少绑定 scenario/树/请求、期望路线、可接受结构 profiles、目标存在性、可接受目标
  集、干扰目标、澄清策略、Policy 状态集合和可接受终态联合元组；
- `CLARIFICATION` 候选必须在冻结作用域内存在至少两个语义合理且结构兼容的候选；Oracle
  固定一个目标和至少一个对照节点，冻结回答必须提供能区分二者的新增信息。若请求在树内
  已能唯一定位，则不得标为澄清；
- `WEAK_EVIDENCE` 不得仅依靠“可能、似乎、不确定”等犹豫措辞制造证据不足。请求不得
  直接包含目标名称、唯一同义词或唯一 route 线索，必须缺少至少一个决定性对象/范围/角色
  约束，并在冻结树中留下至少 3 个跨路径合理候选，或明确属于无法由一个澄清问题界定的
  无边界组合；审核原因只允许 `INSUFFICIENT_DISCRIMINATOR` 或 `UNBOUNDED_SCOPE`；
- `WEAK_EVIDENCE` 的执行 Oracle 必须预注册且只保留一个隐藏意图目标；其他合理
  候选作为干扰/竞争证据，不得全部标为可选目标。其执行联合约束精确为
  `expected_route=LIMIT`、`acceptable_policy_statuses=[NEED_EVIDENCE]`、终态
  `action=EXIT / target_node_id=null / target_disposition=PRESENT_NOT_FOUND`；任何选中节点的
  终态都必须拒绝。
- 全部 56 条候选由 Codex 按固定 rubric 逐项审核自然性、树内可回答性、唯一/多目标/空
  目标语义、主现象单一性、Oracle 一致性、澄清对照和弱证据客观性；最多两轮修订；
- Silver 决定必须逐项记录固定 finding/reason code 和实际 rubric 结果；禁止仅按类别批量
  生成同一通过说明。冻结器只从通过候选按预注册类别与候选序号选取 48 条，未入选候选
  必须保留 `RESERVE_ACCEPTED` 或 `REJECTED` 状态，不能删除后假装只有 48 条候选；
- 冻结选择只依据预注册类别、审核状态和候选序号，不得读取或运行当前 Copilot、Prompt、
  Retrieval、Semantic、Policy、H1/H2/M4/M5 逐项结果来挑选“刚好困难”的样本；
- manifest、公开数据、隐藏 Oracle、Silver 审核和 preflight 均绑定规范字节与提交；冻结后
  发现实质错误即整批停线，不热修后继续同一资格 run；
- Git 中的 authoring/冻结测试 JSON 只能声明 Git 可重放的字节和普通非可执行
  文件模式，不得声称 Git 会持久化 `0600` 与 `0644` 的差异。数据提交后、资格
  执行前，单独物化到全新 `0700` 私有目录，隐藏 Oracle/审核及 execution manifest
  使用 `0600` 且不覆盖发布；执行绑定必须重读实际物化字节和权限。
- 所有数据固定 `gold_eligible=false / patch_eligible=false / production_qualification=false`。

## Acceptance Criteria

- [ ] 树节点数在 700—1,000，0 VALUE，Schema 适配通过，节点存储重排不改变规范 digest；
- [ ] 生成器重复运行字节确定，且未读取既有 fixture/scenario/Oracle/Prompt/实验结果；
  生成器源码不包含语义列表轮换、共享拓扑公式、模运算选取或语义字段合成；
- [ ] 不存在列表乘积造树、无语义 filler、未知父节点、重复 sibling label 或不一致节点合同；
  语义签名最大重复组不超过 3且重复实例比例不超过20%，骨架签名最大重复组不超过4且
  重复实例比例不超过40%；全部合格非叶蓝图均完成逐项语义审核；
- [ ] 候选精确 56、类别为 12/12/9/5/7/5/6；冻结精确 48、类别为
  10/10/8/4/6/4/6，目标存在/空目标为 42/6；
- [ ] 10 条非字面五类各 2，8 条错误上下文和 16 条重复子集按预注册顺序冻结；
- [ ] 56/56 完成逐项 Codex Silver 审核，冻结 48 条零 blocking finding；审核存在真实
  `RESERVE_ACCEPTED`/`REJECTED` 记账，不得产生 Gold/专家声明或类别级自动通过；
- [ ] 6 条澄清均有至少两个合理候选和可区分冻结回答；4 条弱证据均通过客观缺口与多候选
  复核，单靠犹豫措辞、直接目标同义词或唯一 route 线索时 preflight/审核失败；
- [ ] Oracle 目标均存在于同一可信树或在空目标 case 中严格为空，多目标与干扰集合无非法
  重叠，路线/Profile/Policy/终态联合约束一致；
- [ ] 48/48 冻结 scenario 由 `SealedScenario.from_dict()` 重建，48/48 Oracle 由
  `SealedCaseOracle.from_dict()` 重建，完整计划通过 `validate_sealed_plan()`；不存在
  authoring-only 枚举、blueprint ref 或平行终态合同混入执行工件；
- [ ] 4 条冻结弱证据均为 `LIMIT / NEED_EVIDENCE / EXIT`且不选节点；8 条错误
  上下文均绑定合法但语义错误的 `proposed_parent_ref`，并由公开确定性 owner
  重放得到同一引用；
- [ ] canary 证明 Oracle、目标 node ID、期望状态和评分答案不进入公开 scenario、模型输入
  构造或 manifest 公共视图；
- [ ] preflight 拒绝来源、节点规模、VALUE、语义签名重复率、骨架签名重复率、配额、类别、
  重复子集、澄清对照、弱证据原因、审核、Oracle、hash、权限、额外字段、bool-as-int 和
  冻结字节篡改；负例必须证明同一骨架即使轮换 role/type/cardinality 仍被骨架门禁拒绝；
- [ ] 数据提交不包含模型请求/响应、Prompt、实验结果、真实材料或受保护路径。
- [ ] 从数据提交的新 checkout 运行数据 verifier 不依赖 Git 无法表达的 `0600`；
  资格执行的私有物化流程则必须拒绝非 `0700` 目录、非 `0600` 隐藏工件和字节漂移。

## Definition of Done

- 仅运行数据任务白名单测试、Trellis validate 和 `git diff --check`；禁止递归/完整 suite 在
  clean-room 构造主体中意外读取既有实验材料；
- 数据内容、审核和 preflight 形成单一 data commit 候选，提交前 Git index 为空且未
  push/merge；
- 数据提交完成后停在交接门，不运行 R0/C1、Simulator、百炼、Qwen、Semantic 或任何效果
  评分；
- 最终资格运行必须等待功能测评提交、execution manifest 和显式批准。

## Out of Scope

- 不实现或修改 Navigation Copilot、Provider、Prompt、召回、Semantic、Policy、API 或 UI；
- 不运行当前产品链路、模型、R0/C1 或查看任何逐项实验结果；
- 除“v3-C b02 恢复边界”精确允许的未执行 `b01` authoring 语义源外，不复用现有
  请求/Oracle，不把真实数据删除 VALUE 或改名后作为 clean-room；
- 不声明 Gold、生产资格、真实用户效果或生产 Shadow 通过。

## File Ownership

数据分支独占 v3 fixture 目录、确定性数据生成器、数据 preflight、数据专属测试和本任务目录。
不得修改功能子任务、当前 Copilot 核心、现有 fixture/manifest、Provider、Prompt 或完整测试
配置。具体路径在开始实施前冻结，避免与功能分支冲突。

## Research Reference

- [`../08-05-governance-navigation-copilot-shadow/research/sealed-fictional-e2e-evaluation-plan.md`](../08-05-governance-navigation-copilot-shadow/research/sealed-fictional-e2e-evaluation-plan.md)
