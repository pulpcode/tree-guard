# M4 独立盲测与 MVP 执行验证

## Goal

使用外网独立构造、完全虚构且未参与上一里程碑提示调优的中型信息树，完成一次冻结
盲测：先评价验证候选的准备质量，再由人工冻结最终请求与可观察 Oracle，分别执行并
报告意图、召回和语义推荐阶段结果。全部产物保持待审、非 Gold、非 Patch。

## Context

- 上一里程碑的开发集和回归集已多次用于提示改进，不能继续承担严格泛化结论；
- 上一里程碑已使用的树快照只能继续作为回归或对照，不能承担本里程碑未见树的
  泛化结论；
- 仓库另有完全虚构的中型候选树，可在通过来源和未见性审计后作为首轮 holdout，
  当前没有重新造同规模树的必要；
- 现有确定性规划器能在该树上形成有界稀疏计划，部分风险因树结构不适用而明确记为
  `NOT_APPLICABLE`，不需要为了凑齐覆盖而修改基础树；
- 现有验证边界可以比较各阶段状态，但状态一致不等于目标节点召回或推荐动作正确；
- 当前来源绑定的候选审核执行只覆盖意图阶段，召回和推荐仍需新的显式合同；
- 数据构建工作流要求先冻结 Charter、文件所有权、共享合同和合并顺序，再由独立
  worktree 并行准备数据工件。
- 首轮 fire M4 v1 实验在 Intent 阶段暴露 request、Prompt 与 Oracle 不可同时满足：
  7 条本地合法草案全部被判 `MISMATCH`，1 条 `RUN_FAILED`，后续阶段零调用；该
  结果属于合同完整性诊断，不是模型准确率；
- fire M4 v1 已进入实验并影响后续合同修复，原字节只保留为诊断/校准输入，不能
  再承担未见 holdout 的门控结论。

## Constraints

- 首轮复用未进入上一里程碑模型请求的虚构 holdout，基础树字节保持不变；并行数据
  任务重点准备 Charter、隐藏参照与可观察 Oracle；
- 生成完成前，功能任务不读取隐藏场景和 Oracle 正文，只使用字段形状与聚合计数；
- 首轮只运行一次冻结的 Prompt、模型和计划组合，评分完成前不根据中间输出调参；
- 全部验证结论只适用于虚构合同，不外推为真实领域准确率。

## Requirements

1. 将“候选准备质量”和“MVP 阶段执行正确性”作为两份结果，禁止合并成理解率；
2. 在执行前冻结树、计划、Prompt、模型、rubric 和隐藏 Oracle，生成完成后才打开
   隐藏参照；
3. 继续使用确定性稀疏规划、有界投影、单元级有限重试和本地失败关闭；
4. 所有合同候选按清晰性、可执行性、证据关联、风险族与目标区分、不过度声称进行
   人工审核，并记录 `accept / revise / reject` 与审核成本；
5. fire M4 v1 首轮最多选择 8 条 `accept` 或人工修订后接受的候选执行；每条都必须冻结最终请求
   和完整能力 Oracle，`reject` 与未完成审核的候选不运行、不进入执行分母；
6. 意图、召回和推荐分别报告 `MATCH / MISMATCH / NOT_RUN / RUN_FAILED`，后一
   阶段不得覆盖前一阶段失败；
7. 完整能力 Oracle 至少包含：意图/澄清预期，召回阶段的内部可接受目标集合与
   Top-K 边界，以及推荐阶段的可接受动作、目标或空值和关系类别；
8. 运行时可以用内部目标身份作精确比较，公开报告只保留聚合结果，不公开隐藏参照；
9. 全部数据与工件保持 `CLEANROOM_SYNTHETIC`、`gold_eligible=false`、
   `patch_eligible=false`；
10. 自动化测试不发网络；本项目自编 clean-room 测试数据适用常设 LLM 授权，实验
    harness 可直接设置外传资格；其他来源仍需对最终请求字节和用途单独批准。
11. 首轮 M4 作为进入受保护环境 Shadow 验证的 go/no-go 可行性门槛；通过只表示
    值得继续受控验证，不表示达到生产准确率或可自主决策。
12. fire M4 v1 门槛采用分层有界失败预算：数据边界、来源绑定、合同完整性和结果记账零失败；
    最多 8 条中至少 6 条完整符合各自 Oracle 预期路径；每个实际适用阶段最多允许
    1 条 `MISMATCH` 或 `RUN_FAILED`，且失败必须可定位、可人工审阅。
13. fire M4 v1 执行样本优先选择 7 条预期进入召回与推荐的完整链路，以及 1 条有真实树证据支持的
    澄清短路；没有合法歧义时将该风险记为 `NOT_APPLICABLE`，以完整链路回填，禁止
    为满足配额制造虚假歧义。
14. 并行数据任务采用两阶段交付：第一阶段只准备 Dataset Charter、覆盖蓝图、审核规则
    和隐藏 Oracle 设计；功能分支冻结运行时 Schema 后，第二阶段再按该合同生成、检查
    和冻结最终数据工件。
15. 功能分支拥有运行时合同、比较逻辑、序列化与功能测试；数据分支拥有独立数据任务、
    数据蓝图、fixture sidecar、数据 preflight 与数据专属测试。数据分支不得修改基础树，
    两个分支不得同时编辑同一文件。
16. 集成顺序为：先冻结并验证功能合同提交，数据分支再同步该提交并生成最终工件，最后
    将数据提交合入功能分支并执行联合回归；任何合同字节变化都使下游审核状态失效。
17. Holdout 身份按树快照判断，而不是按新场景或新 Oracle 判断；任何已进入上一
    里程碑模型请求的树快照均不得承担本次 go/no-go，只可作为非门控回归对照。
18. 完整能力合同采用独立、来源绑定的 overlay，保持上一里程碑 action、record 和
    intent-run v1 不变；overlay 必须绑定已审核场景、树快照、计划和受审字节。
19. 运行器复用既有意图、确定性召回和语义推荐边界；运行级候选引用必须在同次候选集
    内映射回稳定节点身份，再与长期 Oracle 比较。
20. 意图路径不符合 Oracle 或召回目标未命中时，后续阶段固定短路并记录上游原因，
    不把同一根因重复记成多个阶段语义失败。
21. fire M4 v1 候选准备质量进入同一 go/no-go 的独立门：固定计划全部记账，可执行候选至少 8 条，
    其中直接接受至少 4 条，不可用候选最多 3 条，无 blocking finding，人工审核不超过
    150 分钟；候选门和 MVP 执行门必须同时通过。
22. M4 v1 在冻结、数据 preflight 和执行前必须校验 Intent Oracle 是否能由冻结 request
    确定性支持；失败使用 `CAPABILITY_ORACLE_REQUEST_MISMATCH`，且 Provider 零调用。
23. v1 profile 必须显式覆盖全部 12 个 Intent 字段。非 `UNKNOWN`/非 `null` 的
    `node_kind/value_type/cardinality` hint 必须按 request 精确比较；`UNKNOWN`/`null`
    只表示缺少输入证据，必须 `NOT_COMPARED`。没有逐字段来源绑定的
    `subject/role/scenario/lifecycle/ownership` 及
    `confirmed_facts/assumptions/evidence_gaps` 也只能 `NOT_COMPARED`；`PROCEED`
    至少保留一个结构化有区分力比较，`CLARIFY` 必须要求非空澄清问题。
24. 历史形状合法但不可回答的 overlay 允许做来源和字节诊断重放，但不得执行或进入
    go/no-go 分母；公开层将其归入 `CONTRACT_INTEGRITY_FAILURE`，不伪装成模型
    `MISMATCH`。
25. fire M4 v1 原 fixture 字节保持不变并固定为门控不合格；修订版本只能用于非盲
    校准，正式门控必须使用新的、运行前密封且未参与本轮修复的数据包。
26. 下一轮门控在生成数据正文前冻结当前功能提交、Intent v4、Semantic v3、实际
    Provider/模型/endpoint 类别、生成参数、重试政策、比较器和评分线；揭盲后任一项
    改变都会使该数据降级为校准集。
27. 新数据使用一棵独立、同领域、800–2,000 节点的 clean-room 虚构树和 24 条密封
    执行场景，目标为 18 条完整链路与 6 条合法澄清；不复制既有树、不做笛卡尔积，
    不为本轮额外准备 10,000–50,000 节点压力树。
28. 24 条场景各执行三次；分别统计首发与重试后合同合法率、逐阶段 Oracle 匹配率、
    每轮端到端匹配率、场景级 3/3 稳定数及澄清 precision/recall，不采用最好一次或
    多数票替代波动结论。

## Acceptance Criteria

- [ ] 相同 holdout 重排后产生相同画像、计划、覆盖和 digest；
- [ ] 执行前可证明模型输入未读取隐藏参照，Prompt、模型和请求清单已冻结；
- [ ] 数据 Charter 能证明所选树快照未进入上一里程碑模型请求；已见快照被固定拒绝为
  本次门控 holdout；
- [ ] 每个计划单元得到候选、固定失败或未执行状态，调用数不超过合同上限；
- [ ] 所有合同候选完成统一 rubric 审核并输出聚合分级和人工成本；
- [ ] fire M4 v1 固定计划全部得到候选或固定失败；`ACCEPTED + REVISED_ACCEPTED >= 8`、
  `ACCEPTED >= 4`、`REJECTED + 固定生成失败 <= 3`，且审核不超过 150 分钟；
- [ ] 只有来源绑定的人工审核场景能执行，陈旧、篡改或缺失 Oracle 固定错误码拒绝；
- [ ] 三个阶段分别报告分母和结果，不把状态通过解释成实质语义正确；
- [ ] 门槛将数据边界、来源绑定、合同完整性等硬失败与可审阅的语义偏差分开判定；
- [ ] 任何硬失败均输出 `NO_GO`；没有硬失败时，只有整体和逐阶段失败预算同时满足才
  输出 `GO_SHADOW`；
- [ ] fire M4 v1 样本组成满足 7+1 目标，或对澄清风险给出确定性
  `NOT_APPLICABLE` 及回填记录；
- [ ] 数据第一阶段不新增运行时字段、不修改正式 fixture，并能在没有隐藏正文的情况下
  供功能分支实现合同；
- [ ] 第二阶段开始前记录冻结合同版本，数据工件与审核记录绑定同一 digest；
- [ ] 文件所有权无交叉，数据分支同步功能合同后再物化最终 Oracle，合并后联合回归通过；
- [ ] 召回验收能判断可接受目标是否进入约定 Top-K，推荐验收能判断动作、目标或
  空值和关系是否落在人工冻结的可接受范围；
- [ ] 运行级引用与冻结的目标身份解耦，不用一次运行中的临时候选编号充当长期 Oracle；
- [ ] 上一里程碑 v1 序列化和回归保持逐字节兼容，新能力 overlay 使用独立版本并能
  对陈旧、篡改、错树、错计划和错受审字节 fail closed；
- [ ] 意图、召回和推荐的 `MATCH / MISMATCH / NOT_RUN / RUN_FAILED` 具有固定
  上游短路语义，批次汇总不会重复计算级联失败；
- [ ] request 与 Oracle 不可同时满足时在任一 Provider 调用前固定拒绝；历史工件仍
  可来源重放，但数据 preflight 和执行资格均为合同失败；
- [ ] v1 的结构化 hint 比较与冻结 request 精确一致，自由文本/list 字段没有逐字段
  支持绑定时不能使用 `NON_EMPTY` 或 `EMPTY`；
- [ ] fire M4 v1 的公开诊断只含固定 code 和聚合计数，fixture 原字节不被重写，且不
  再计为 `GATING_HOLDOUT`；
- [ ] 新密封验证绑定不可变功能 commit，功能对话在执行前只接收 dataset identity、
  规模、覆盖计数和 digest，不读取新树、场景或 Oracle 正文；
- [ ] 新执行集固定 24 条并完成三轮；硬合同零失败、重试后 Intent/Semantic 合同合法率
  均不低于 98%、确定性召回命中率为 100%、每轮端到端匹配率不低于 75%，且至少
  18/24 场景三次全部匹配；
- [ ] 澄清 precision/recall 和结构冲突错误复用单独记账；任何被本地门禁接受的硬冲突
  错误复用直接 `NO_GO`；
- [ ] 仓库只保存允许列表聚合、固定 code 和审核统计，不保存外部模型原始请求、响应
  或 trace；
- [ ] 聚焦测试、完整后端测试、前端回归/构建、Trellis task validate 和
  `git diff --check` 通过。

## Definition of Done

- 成功、边界、重排、篡改、陈旧审核、阶段短路、失败恢复和泄漏反例测试齐全；
- `uv sync --frozen`、配置的完整 `unittest`、前端测试/构建和
  `git diff --check` 通过；
- 未配置的 lint、typecheck、coverage 或 CI 不报告为通过；
- Python、Schema、序列化、hash 和可信 replay 合同原子更新；
- 数据 Charter、功能/数据 worktree 所有权和合并顺序明确；
- 不自动 stage、commit、push、merge、晋升 fixture、归档或写生产数据。

## Out of Scope (explicit)

- 真实信息树、真实字段、实例值、专家文本或受保护源码的外传；
- 自动 Oracle、自动 Gold、自动 Patch 或生产树写入；
- 为首轮 M4 重建另一棵同规模基础树，除非 holdout 审计发现阻塞；
- 将上一里程碑已使用的树快照重新命名为 holdout 或用于本次 go/no-go；
- 对全部分支与风险族做笛卡尔积；
- 首轮增加 UI、数据库、队列、向量索引或新运行时依赖；
- 查看结果后仍把同一批数据称为未见 holdout。
- 为让 fire M4 v1 重新通过而定向调 Prompt，或把修订后的同一数据重新命名为盲测。

## Technical Notes

- 当前复杂度：Complex；产品门槛已经冻结，实施前需完成 holdout 替换审计和运行时
  合同计划；
- 并行数据任务默认只规划，在用户批准开发 Plan 前不生成或晋升数据。

## Research References

- [`research/runtime-contract-options.md`](research/runtime-contract-options.md) — 比较三种
  完整能力接入方式，推荐在已审核场景上增加来源绑定 overlay。
- [`research/m4-calibration-candidate-handoff.md`](research/m4-calibration-candidate-handoff.md)
  — 记录非盲校准候选的聚合绑定、机器证据和待人工审核门。
- [`research/m4-sealed-validation-freeze.md`](research/m4-sealed-validation-freeze.md)
  — 冻结下一轮新未见数据的规模、隔离、三次重复性、门槛和停线规则，不含隐藏正文。
- [`research/m45-repeatability-contract.md`](research/m45-repeatability-contract.md)
  — 记录 v1 只支持 8 条的合同缺口，并定义保持 v1 兼容的 24×3 聚合报告。

## Technical Approach

采用独立能力 overlay，而不是修改既有 v1 Oracle：新合同冻结完整能力 Oracle、人工
审核绑定、单场景分阶段结果和批次门槛报告。运行器先重放上一里程碑的候选与审核来源，
再执行意图；只有预期路径匹配时才进入召回，只有目标在冻结 Top-K 内命中时才进入推荐。
推荐输出通过同次候选集映射到稳定目标身份，并按可接受的动作—目标—关系联合结果判断。
私有运行工件可保留来源 hash，公开报告只保留固定状态、code、分母和聚合计数。

## Implementation Plan

1. **能力合同与反例测试**：新增独立版本的完整能力 Oracle、审核 overlay、严格
   序列化和来源重放；保持上一里程碑 v1 逐字节兼容，先覆盖未知字段、陈旧绑定、篡改、
   错树、错计划和错受审字节。
2. **分阶段执行与归因**：复用现有意图 Provider、确定性召回和推荐 Provider，实现
   意图 profile、Top-K 稳定目标、动作—目标—关系联合比较，以及上游不匹配/运行失败
   的固定短路语义。
3. **批次门槛与公开报告**：实现候选准备质量和 MVP 执行两套独立分母，再组合为
   `GO_SHADOW / NO_GO`；增加阈值边界、重排、重复失败不重复计数和泄漏 canary 测试。
4. **冻结功能合同并交接数据分支**：完成聚焦与全量回归后，由用户审阅并批准功能合同
   提交；数据分支只在同步该提交后进入第二阶段，生成和人工冻结 sidecar。
5. **集成与虚构模型实验**：数据工件获准晋升并合入后执行联合回归；外部模型请求需
   另行冻结最终字节并取得明确批准，实验结果只报告聚合门槛和限制。
6. **合同完整性修复与重新分流**：保留首轮聚合诊断，增加 request-aware Oracle
   执行资格检查；fire v1 只用于校准，正式 go/no-go 改用新的密封 holdout。
7. **非盲校准候选**：从原 fire v1 冻结字节派生新的 `CALIBRATION_ONLY` staging
   身份，补齐完整 12 字段 profile；把 v1 无逐字段来源绑定的自由文本/list 字段和
   `UNKNOWN`/`null` hint 收窄为 `NOT_COMPARED`，非空结构化 hint 保持精确比较；
   逐项保存提议证据绑定，机器检查后固定停在 `PENDING_HUMAN_REVIEW`，不自动冻结
   或晋升。
8. **Silver 校准执行**：按用户决策把 Codex 辅助审核的 8 条候选冻结为独立
   `CODEX_ASSISTED` / `SILVER` 授权；允许进入本次校准执行，但固定非 Gold、非门禁、
   非 Patch，且实验成功不得自动升级。先冻结并审批 Intent 精确请求，回放结果后再
   冻结和审批实际适用的 Semantic 请求；两阶段均不得在批准前外发。
9. **下游隔离实验**：对首轮中 Intent 失败或不匹配、且 Silver Oracle 预期为
   `PROCEED` 的 5 条场景，使用私有、来源绑定的 Codex 辅助参考 Intent 替代 Intent
   Provider，只运行确定性召回并准备实际可达的 Semantic 请求。参考 Intent 固定为
   `DOWNSTREAM_ISOLATION_ONLY`，不得计入端到端成绩、门禁或 Gold；任何 Semantic
   外发仍须先冻结精确请求字节并取得单独批准。
10. **M4.1 校准修复**：为模型 Intent 内容校验增加不含原文的字段级错误码；明确
    Intent 只负责编译可检索意图，候选冲突留给后续阶段；Semantic 对
    `USE_EXISTING_NODE` 增加 `node_kind/value_type/cardinality` 确定性兼容门禁，
    冲突时拒绝模型输出并允许一次完整重试，不在本地改写建议。使用已暴露 Silver
    数据做回归，不恢复 holdout 或门禁身份。
11. **M4.2 澄清边界校准**：保留“候选冲突不触发 Intent 澄清”，但把“完整 hints
    优先不提问”收窄为只适用于请求文本本身无互斥解释、范围或组合歧义；若不同解释
    会改变结构化意图，即使 hints 完整也必须提出一个原子问题。仍只使用已暴露
    Silver 数据校准，不改变 Oracle、Semantic 门禁或正式 holdout 要求。
12. **M4.3 Semantic 失败诊断**：实验运行器只从 Provider trace 提取固定
    `SEMANTIC_*` 校验错误码并聚合记账，不保存模型响应、理由或候选正文；用同一冻结
    请求重复执行三次，区分稳定失败与输出波动，不以单次最好结果替代重复性结论。
13. **M4.4 Semantic 精确重试**：将首次本地失败的固定 `SEMANTIC_*` code 送入一次
    完整重试，禁止回传原始响应或在本地改写动作；审批白名单枚举所有允许错误码正文，
    但实际调用上限仍保持每场景最多两次。
14. **M4.5 新未见数据密封验证**：冻结当前 Intent v4、Semantic v3、模型、运行时
    合同和评分门槛；由独立 worktree 基于全新同领域 800–2,000 节点虚构树准备 24 条
    密封执行场景，功能对话不读取树、场景或隐藏 Oracle 正文。每条在同一配置下运行
    三次，分别报告合同合法率、Oracle 匹配率和 3/3 稳定性；揭盲后该数据只保留为
    回归/校准，不在同一数据上调参后重新门控。
15. **M4.5 重复性报告合同**：保持 8 条 `scenario-capability-report.v1` 不变，新增
    独立 24×3 聚合报告；严格验证三轮场景集合/route 一致、round 内唯一、18+6 组成，
    并按冻结的 98% 合同合法率、100% 实际召回、每轮 18/24、稳定 18/24 和零硬冲突
    错误复用门槛给出 `GO_SHADOW/NO_GO`。

## Decision (ADR-lite)

- **Context**：只比较阶段状态只能证明流程连通，不能判断目标召回与推荐选择是否正确；
- **Decision**：M4 首切片为最多 8 条人工审核场景冻结完整能力 Oracle，同时验收意图、
  召回目标进入 Top-K、推荐动作、目标或空值及关系；
- **Alternatives rejected**：仅比较三个阶段状态，原因是无法回答实质语义是否正确；
- **Consequences**：数据准备和运行时合同都需增加内部目标身份与可接受集合，报告必须
  隔离隐藏参照并单独统计人工审核成本。
- **Decision**：首轮结果承担进入受保护环境 Shadow 验证的可行性门槛，不承担生产
  准确率验收；
- **Consequences**：报告需给出明确 go/no-go 和逐阶段证据，并持续保留人工审核与
  失败关闭，不能因通过首轮门槛取消保护措施。
- **Decision**：采用分层有界失败预算；硬合同零失败，整体至少 6/8 符合预期路径，
  各适用阶段最多 1 条语义或运行失败；
- **Consequences**：首轮允许带着少量已知、可审阅缺陷进入 Shadow，但任何安全、
  来源或记账缺陷都会关闭门槛。
- **Decision**：执行样本采用 7 条完整链路加 1 条合法澄清短路；无合法歧义时不强造；
- **Consequences**：首轮重点补足召回和推荐证据，同时保留一次“应澄清而不是猜测”的
  验证机会。
- **Decision**：并行数据准备采用“Charter/蓝图先行、冻结 Schema 后物化”的两阶段
  方式，并由功能分支单向提供共享合同；
- **Consequences**：第一阶段可以立即并行且不阻塞功能设计，代价是最终 fixture 必须
  等合同提交后生成；这避免数据反向定义运行时 Schema 和跨 worktree 文件冲突。
- **Context**：数据第一阶段选中的树快照已经参与上一里程碑模型实验；没有复用旧输出
  不等于模型没有见过树；
- **Decision**：本次门控 holdout 必须更换为未进入上一里程碑模型请求的现有中型
  虚构树，已见快照仅保留为非门控回归对照；
- **Consequences**：数据任务需重算基础绑定并复核覆盖格适用性；因尚未造数据，
  不需要作废 fixture 或人工 Oracle。
- **Context**：现有来源绑定执行只覆盖意图，现有 Workbench 对照只比较阶段状态；
- **Decision**：保持既有 v1 不变，在已审核场景上新增来源绑定的完整能力 overlay、
  分阶段运行和批次门槛合同；
- **Consequences**：可以精确归因意图、召回和推荐失败，并与数据 sidecar 解耦；代价是
  需要新增版本化 Schema 和短路/篡改反例测试。
- **Decision**：候选准备质量采用平衡门槛，与 MVP 执行门并列且必须同时通过；
- **Consequences**：少量可执行场景不能掩盖 Agent 大量返工或失败，同时允许首轮未见树
  暴露少量可解释缺陷。
- **Context**：首轮 fire v1 的形状、来源和记账均合法，但 Intent Oracle 要求输出
  request 未结构化支持的自由文本字段，并把允许存在的 assumptions/evidence gaps
  错误冻结为空；
- **Decision**：M4 v1 保持 wire shape 不变，但执行资格只允许确定性 request-observable
  约束；历史不可回答 overlay 可读取、不可执行。更丰富的自由文本 Oracle 以后通过带
  逐 expectation support binding 的新版本实现；
- **Consequences**：fire v1 固定成为诊断/校准数据，不能继续给出盲测泛化结论；修复
  后需要新的密封数据才能重新执行正式门控。
- **Context**：8 条 request-observable 校准候选已经完成 Codex 辅助审核，但尚无独立
  人工 Gold 审核；直接伪装成人工 overlay 会破坏审核来源语义；
- **Decision**：新增独立 Silver 校准授权合同，保留 `CODEX_ASSISTED` 来源，允许验证
  Intent—确定性召回—Semantic 推荐链路是否可运行；
- **Consequences**：本轮可以先获得工程可行性和错误归因证据，但结果不进入
  `GO_SHADOW` 门禁、不证明生产准确率。链路走通后再单独决定 Gold 标准、人工审核
  预算和未见数据执行，不得自动转换现有 Silver。
- **Context**：首轮 Intent 失败会阻止召回和推荐执行，无法判断技术路径是仅上游
  Intent 不稳定，还是下游召回/推荐同样不可用；
- **Decision**：新增一次非生产的下游隔离实验，以 5 条私有 Codex 辅助 Silver 参考
  Intent 替代 Intent Provider，参考文件必须绑定原始请求、Silver 授权和首轮 Intent
  结果 SHA；
- **Consequences**：可以独立观察确定性召回和 Semantic 推荐，但所得结果只能回答
  “给定可接受 Intent 后下游是否工作”，不能回答 LLM 能否自行理解需求，也不能与
  原端到端通过率合并。
