# 青岚中型语义挑战数据集

## Goal

在已通过小批审核的完全虚构青岚数据线之上，规划一个独立
`SEMANTIC_CHALLENGE` 数据集。它用于验证 TreeGuard 在 300–500 节点规模下对
歧义、归属冲突、类型/基数冲突、证据不足、拒答和有限跨规模重放的处理，不证明
图书馆领域正确性或生产准确率。

## What I already know

- 小型 `DOMAIN_CONTROL` 数据集已经以 48 节点、12 场景晋升，并保持非 Gold、
  非 Patch。
- 用户要求先继续数据编制，之后再把新增测试合入主实现 worktree。
- 现有小型生成器和正式 fixture 必须保持冻结，不在本任务中改写。
- 当前没有第二位人工审核者；本批仍使用单人审核加固定 self-recheck。
- 生成阶段不读取旧消防语义内容；旧数据只允许在候选冻结后的独立相似度审计中
  只读使用。

## Confirmed Decisions

- 推荐继续同一完全虚构青岚数据线，建立独立
  `fictional-qinglan-library-semantic-v1`，而不是立即另起消防/应急领域。
- 目标为 312 节点、20 场景；这是 300–500 区间内最小且可解释的组合：
  `72 curated + 180 background + 60 stress-only`。
- 用户审核发现既有 clean-room 小树和 run-003 都没有明确区分类别概念、实例记录
  与单例政策；此前批准的 24 个 replay anchors 因而失去跨规模语义重放资格。
- 24 个节点只保留为已声明的 clean-room lineage references，并在新 Blueprint
  下重建节点类型、名称或父子关系；精确 replay anchor 和 replay 场景均降为 0。

## Open Questions

- 无。

## Requirements (evolving)

- `source_class=CLEANROOM_SYNTHETIC`
- `fictional=true`
- `derived_from_real=false`
- `gold_eligible=false`
- `patch_eligible=false`
- 主角色固定为 `SEMANTIC_CHALLENGE`。
- 使用独立 Dataset Charter、Semantic Blueprint、coverage matrix 和 seed
  `20260731`。
- 节点目标 312，场景目标 20，每个场景只有一个主要风险。
- 只通过显式 `allowed_facets_by_subject` 和有界 pairwise 选择构建背景节点；
  禁止全局 `subjects × facets`。
- stress-only 节点不得成为语义场景目标或承担 oracle。
- 候选只写入忽略的 staging；未经人工确认不得晋升正式 fixture。
- Codex 先对全部场景和结构聚类做非权威预审，再由用户人工审核。
- `CONCEPT` 必须声明为组织分类或资源单例章节；只有
  `SINGLETON_SECTION` 可以直接承载属于当前资源单例的标量字段。
- 可重复实例必须使用 `PROPERTY(value_type=class, is_list=true)`；嵌套单一
  复合记录使用 class、SINGLE。
- 每个标量 PROPERTY 必须直接属于 class PROPERTY 或已声明的单例章节；
  L1 必须拒绝没有明确值所有者、实例边界或作用层级的字段。
- 数据提交形成后，主实现 worktree 只通过后续独立提交更新 Provider/overlay 和
  集成测试。

## Acceptance Criteria (evolving)

- [x] Charter、Blueprint、coverage matrix 和合并顺序得到用户确认。
- [x] 312 节点由固定 seed 和稳定排序逐字节重建。
- [x] `adapt_tree_document()` 得到 312 节点和 0 个 `VALUE` envelope。
- [x] 20 个场景引用合法、主要风险唯一、coverage cell 不重复。
- [x] 所有 subject/facet 组合属于显式允许表。
- [x] 60 个 stress-only 节点均不可被语义场景引用。
- [x] 52 个重复/复合字段所有者均为 class PROPERTY；其余直接标量字段只能属于
  已声明的 `SINGLETON_SECTION` CONCEPT。
- [x] 不再声明精确 replay anchor 或跨规模稳定性；24 个 lineage references
  单独计数。
- [x] L1 无 blocking finding，L2 Critic 不修改候选或升级 oracle。
- [x] 人工审核不超过 20 个场景和 150 分钟，未触发停线。
- [x] 冻结后才执行旧回归集相似度审计；审计只接受或拒绝候选。
- [x] 晋升前用户明确批准最终字节范围。
- [x] 聚焦测试、完整后端测试、Trellis 测试和 `git diff --check` 通过。
- [x] 数据提交范围保持独立，可按计划 cherry-pick 到主实现 worktree，且不覆盖
  其现有改动。

## Definition of Done

- 下一批数据完成机器门禁、Codex 预审、人工筛查、冻结和独立相似度审计。
- 正式 fixture 只在用户明确批准后晋升。
- 数据分支提交与主实现接线提交分开。
- 未配置的 lint、typecheck、coverage 或 CI 不报告为通过。

## Technical Approach

- 新建独立生成器，不修改已冻结的小型生成器。
- 节点族分为 `curated_core=72`、`blueprint_background=180`、
  `stress_only_filler=60`。
- Blueprint 使用 5 个领域分支、1 个资源单例基本信息章节、13 个组织结构组、
  52 个 class subject 和 240 个显式允许 property placement 组成 312 节点。
- 20 个场景采用 coverage cell 与 pairwise 选择，不做领域/规模/风险全组合。
- 24 个既有 clean-room lineage reference 只用于披露来源关系；因节点合同需要
  修正，不再承担精确重放。四个原重放场景改为实例字段、集合汇总、政策/实例
  分离和单例政策作用域测试。

## Decision (ADR-lite)

**Context**：小型跨领域集已证明数据流水线可行，下一步需要在不扩大人工清洗的
前提下验证中型语义挑战与规模重放。

**Decision**：选择同一青岚数据线的独立 312 节点
`SEMANTIC_CHALLENGE` 数据集。组织概念、资源单例章节和重复记录边界必须显式
区分：单例章节可以拥有资源级字段，重复记录/嵌套结构使用 class PROPERTY。

**Consequences**：本批不再宣称小/中树语义稳定性；需要先证明所有字段有明确的
资源单例或记录所有者。此前小型集需由独立任务评估是否应被后续版本取代。

## Out of Scope

- 不构建 1,800–2,300 节点生产规模树或额外压力树。
- 不读取或复用旧消防节点、路径、场景或生成器语义表。
- 不修改小型青岚正式 fixture 的任何字节。
- 不创建新的共享运行时 Schema、数据集注册表或 Agent 实现。
- 不调用 Web、外部模型、真实仓库或受保护环境。
- 不 stage、commit、push、merge、rebase 或归档，除非用户另行批准。

## File Ownership

- `.trellis/tasks/07-31-fictional-qinglan-library-semantic/`
- `src/treeguard/fictional_qinglan_library_semantic_data.py`
- `artifacts/fictional-validation/qinglan-library-semantic-v1-run-007/`
- `tests/fixtures/fictional/qinglan_library_semantic/`（仅晋升批准后）
- `tests/test_fictional_qinglan_library_semantic_data.py`
- 仅属于本数据集的确定性检查脚本（如确有必要）

不得修改共享运行时模块、既有小型青岚生成器/fixture、并行 Skill 目录或主实现
worktree 文件。

## Merge Order

1. 数据 worktree 完成候选、审核、冻结、审计和晋升。
2. 用户批准后，只提交本任务拥有的数据文件。
3. 主实现 worktree 在保留现有 dirty Core 的前提下 cherry-pick 数据提交。
4. 主实现另建接线提交，更新 Qinglan Provider/overlay 和集成测试。
5. 两个提交分别验证，禁止把数据和运行时接线压成一个不可审阅提交。

## Candidate History

- `run-001` 在进入人工审核前由 Codex 预审停线：QS-C02 的
  `HOMONYM` 标签与当时需求文本不匹配。该批次不得用于审核、冻结或晋升。
- QS-C02 已改为树内确有同名候选的“需要记录陪同人数。”；修订候选必须以
  `run-002` 全量确定性重建，不覆盖 `run-001`。
- `run-002` 在 Codex 逐条预审时再次停线：QS-C09 的旧文本只命中一个精确
  同名属性，不能支撑 `CLARIFICATION_REQUIRED`。QS-C09 已改为可能落到三类
  社区展览的“记录社区展览内容的更新周期。”；修订候选必须以 `run-003`
  全量确定性重建，不覆盖前两批。
- `run-003` 已通过 12 项聚焦数据测试、L1、Codex 20/20 非权威预审、审核页
  构建/渲染测试和 lint；当前停在用户人工筛查门禁，尚未冻结、相似度审计或晋升。
- 用户在 run-003 人工审核中发现“CONCEPT 下的字段无法说明属于集合、类别还是
  单条实例”。该问题横跨多个 subject，触发跨聚类重复语义错误停线。run-003
  整批作废；不能通过改名或人工清洗继续。run-004 必须从修订 Blueprint 全量重建。
- `run-004` 完成实例边界重构后，在 Codex 场景预审中发现 QS-C04 同时混入
  class→string 与 MULTIPLE→SINGLE 两个次生冲突，不能继续宣称主要风险单一。
  run-004 在人工审核前停线；QS-C04 只保留 class PROPERTY 与 CONCEPT 的类型
  冲突，修订候选以 `run-005` 全量重建。
- `run-005` 已通过 15 项聚焦数据测试、L1、Codex 53 个值拥有者和 20/20 场景
  非权威预审，以及审核页构建、3 项渲染测试、lint 和浏览器交互验收。用户完成
  20/20 场景审核后指出“静音阅览区／小组研讨室／多用途活动厅”仍被未经证明地
  假定为资源单例章节；该问题属于整棵树的 scope 假设，不可由场景审核替代。
  run-005 因此不得冻结、审计或晋升。
- `run-006` 将“本馆基本信息”声明为唯一的资源单例章节，并只承载资源级
  “馆舍名称”；三个空间对象均改为 `PROPERTY/class/MULTIPLE`。审核导出新增
  必填的整树作用域决定，场景审核不能再绕过该结构门禁。
- `run-006` 已通过 15 项聚焦数据测试、L1、Codex 53 个值拥有者和 20/20 场景
  非权威预审，以及审核页构建、4 项渲染/合同测试、lint 和完整交互验收。当前
  用户已确认整树作用域并接受 20/20 Codex 建议；固定复核随后发现 QS-C04 的
  父节点提示引入第二个风险、QS-C12 的父节点提示自引用目标节点。同一问题横跨
  `KIND_CONFLICT` 与 `UNUSUAL_DEPTH` 两个聚类，触发停线，run-006 不得冻结。
- `run-007` 只做两项场景合同修正：QS-C04 不再提供父节点提示；QS-C12 明确以
  树根作为提示父节点。信息树和其余 18 条场景保持不变。该批已通过 15 项聚焦
  数据测试、L1、Codex 53 个值拥有者和 20/20 场景非权威预审、审核页构建与
  5 项渲染/合同测试；摘要绑定校验确认整树及其余 18 条场景未变，因此沿用
  run-006 的整树确认和 18 条 ACCEPT 决定。用户已对 QS-C04、QS-C12 完成
  定向复核并接受 Codex 建议；附件通过严格 JSON、精确字段、来源、场景、
  预审和沿用决定的可信回放。固定随机/高风险复检均为 0 个实质错误，未触发
  停线；run-007 已冻结。独立只读任务随后完成旧回归集相似度审计，结论为
  `ACCEPT`、`finding_codes=[]`，没有据此修改生成器或冻结候选。正式 fixture
  已在用户针对最终字节范围明确批准后晋升；六个正式数据文件与冻结候选逐字节
  一致，`promotion.json` 仍明确标记非 Gold、非 Patch、未注册运行时。

## Research References

- [`research/dataset-charter.md`](research/dataset-charter.md)
- [`research/semantic-blueprint.md`](research/semantic-blueprint.md)
- [`research/coverage-matrix.md`](research/coverage-matrix.md)
