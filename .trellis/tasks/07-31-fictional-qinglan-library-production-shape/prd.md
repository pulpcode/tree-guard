# 青岚生产形状数据集

## Goal

在已冻结的完全虚构青岚数据线之上，规划独立的 `PRODUCTION_SHAPE` 数据集，
验证 TreeGuard 在约 2,001 节点下的确定性构建、适配、候选上限、重排稳定性和
有限跨规模重放。该数据集不复现真实生产语义、结构比例或准确率。

## What I already know

- 小型 `DOMAIN_CONTROL` 和中型 `SEMANTIC_CHALLENGE` 已分别提交。
- 中型集已完成实体作用域整改、单人审核、冻结、相似度审计和正式晋升。
- 当前没有第二审核者；双审预算必须为 0。
- 生成阶段不得读取消防回归集语义；旧消防内容只允许在候选冻结后的独立只读
  相似度审计中使用。
- 新 Skill 要求每个属性声明单一资源、重复成员或集合聚合作用域。

## Confirmed Decisions

- 目标规模采用现有建议档位中的 2,001 节点，而不是构造额外超大压力树。
- 继续使用完全虚构的青岚图书馆数据线，但不把 312 节点树整体放大。
- 复用 24 个已修正的中型锚点合同，其他节点从新 Blueprint 独立构造。
- 4 条场景重放 medium 的需求、提示和预期可观察类别，另外 4 条是 large 新场景。
- 场景控制为 8 条，人工审核仍可在单次会话内完成。

## Open Questions

- 无。

## Requirements (evolving)

- `source_class=CLEANROOM_SYNTHETIC`
- `fictional=true`
- `derived_from_real=false`
- `gold_eligible=false`
- `patch_eligible=false`
- 主角色固定为 `PRODUCTION_SHAPE`。
- 目标 2,001 节点、8 场景，固定 seed `2026073101`。
- 节点族暂定为 `40 curated + 1,561 background + 400 stress-only`。
- 整棵树描述一个虚构资源单例；组织类别不得直接承载成员级标量字段。
- 可重复实体使用 `PROPERTY(value_type=class, cardinality=MULTIPLE)`，标量字段
  必须属于 class 记录或唯一资源单例章节。
- 每个生成节点必须来自显式 family 和 `allowed_facets_by_subject`；禁止全局
  `subjects × facets`、编号兄弟和模板换词扩张。
- stress-only 节点不得成为语义目标或贡献语义准确率。
- 候选只写入忽略的 staging；用户审核和批准前不得晋升正式 fixture。
- 与中型数据的允许复用只能是预先声明的锚点合同；其余结构、名称和路径不得从
  中型树批量复制。

## Acceptance Criteria (evolving)

- [x] Dataset Charter、Semantic Blueprint 和 coverage matrix 得到用户确认。
- [x] 2,001 节点由固定 seed 和稳定排序逐字节重建。
- [x] `adapt_tree_document()` 得到 2,001 节点和 0 个 `VALUE` envelope。
- [x] 节点族计数、深度分布、父子引用和场景引用精确。
- [x] 每个 class 记录声明描述对象、父子关系、基数和祖先链作用域。
- [x] 每个属性有唯一值所有者和明确的单体/成员/集合范围。
- [x] 所有 subject/facet 组合属于生成前冻结且带 digest 的显式允许表。
- [x] 400 个 stress-only 节点均不可被语义场景引用。
- [x] 只有声明的锚点投影字段可跨规模复用，4 条配对场景结果保持稳定。
- [x] 候选上限和节点重排不会改变配对场景的可观察结果。
- [x] L1 无 blocking finding，L2 Critic 不修改候选或升级 oracle。
- [x] Codex 预审 8/8 场景和 40 个 record-referent cluster 代表。
- [x] 人工审核预算不超过 180 分钟，双审预算为 0。
- [x] 冻结后才执行旧消防回归集相似度审计，审计只接受或拒绝。
- [x] 用户接受 Codex 预审建议并指示推进，候选已晋升；Git 操作仍需另行批准。

## Definition of Done

- Charter、Blueprint、coverage、候选、机器门禁、Codex 预审和单人人工审核均有
  可回放证据。
- 正式 fixture 只在最终字节获批后晋升。
- 聚焦测试、完整后端测试、Trellis 测试和 `git diff --check` 通过。
- 未配置的 lint、typecheck、coverage 或 CI 不报告为通过。

## Technical Approach

- 新建独立生成器，不修改已冻结的小型和中型生成器。
- 只复用现有 Adapter、Canonical Tree、Provider Protocol 和审核页面合同。
- 生成前冻结 record blueprint 和精确 `allowed_facets_by_subject`；两者带独立
  digest，并作为生成器输入。允许表不得从 `_NODES`、成品树或 fixture 反推。
- 每个 class 记录必须显式声明 `represents`、`parent_relation`、
  `entity_scope` 和 `cardinality`；L1 沿祖先链独立复算作用域。
- L1 增加记录指代对象、父子关系、祖先作用域、独立允许表、重复 child vector、
  组合密度、锚点白名单和 stress-only 目标检查。
- 相似度审计保持后置、只读，并与生成任务隔离。

## Decision (ADR-lite)

**Context**：中型集已经覆盖主要语义风险，但尚未证明相同确定性合同在约 2,001
节点时仍保持有界、稳定。

**Decision**：构建 2,001 节点 `PRODUCTION_SHAPE`，只声明 24 个锚点合同和
4 条配对重放场景；其余节点使用新的形状家族。

**Consequences**：可以验证有限跨规模稳定性，但结论只适用于声明的锚点，不外推
到整棵树或生产准确率。

## Out of Scope

- 不构建 1–5 万节点额外压力树。
- 不新增大规模语义挑战覆盖或真实领域 Gold。
- 不读取、改写或复用消防节点、路径、场景和生成器语义表。
- 不修改现有青岚正式 fixture。
- 不修改共享运行时 Schema、数据集注册表、Agent 或 Workbench 实现。
- 不 stage、commit、push、merge、rebase 或归档，除非用户另行批准。

## File Ownership

- `.trellis/tasks/07-31-fictional-qinglan-library-production-shape/`
- `src/treeguard/fictional_qinglan_library_production_shape_data.py`
- `artifacts/fictional-validation/qinglan-library-production-shape-v1-<run>/`
- `tests/fixtures/fictional/qinglan_library_production_shape/`（仅晋升批准后）
- `tests/test_fictional_qinglan_library_production_shape_data.py`
- 仅属于本数据集的确定性检查或审核辅助文件

## Merge Order

1. 当前任务完成规划、生成、审核、冻结和晋升。
2. 用户批准后只提交数据任务拥有的文件。
3. 主实现 worktree 单独接入 Provider/overlay 和集成测试。
4. 数据提交与接线提交分别验证和合并。

## Candidate History

- `run-001` 通过 L1 和 14 项聚焦测试后，在 Codex 场景预审中停线：
  QP-C08 直接点名 stress-only 节点，却预期 Agent 忽略该节点，不能形成公平、
  单一的 filler 隔离测试。该批不得进入人工审核或晋升。
- QP-C08 修订为“大树中缺少效果证据时不得被 filler 诱导下最优结论”，并以
  `run-002` 全量确定性重建；不覆盖 `run-001` staging。
- `run-002` 的原有 L1/L2 和测试结论作废并停线。人工抽查发现
  `ORGANIZATIONAL_CONCEPT` 下的 class 记录虽形式上拥有字段，却未声明每条记录
  具体描述谁；同时嵌套 `class/SINGLE` 被错误提升为 `ROOT_ENTITY`，且
  `allowed_facets_by_subject` 从成品节点反推。旧门禁与生成器共享同一错误假设，
  因而形成相关性漏检。
- `run-003` 必须从冻结的 record blueprint 重建，不覆盖 `run-001` 或
  `run-002` staging。未经新的机器门禁、Codex 预审和单人人工审核，不得晋升。
- `run-003` 已按冻结输入重建 2,001 节点：501 个 class 记录全部具有
  `represents` 与 `parent_relation`，230 个嵌套 `class/SINGLE` 均继承
  `COLLECTION_ITEM`。L1、19 项聚焦数据测试和 4 项审核界面测试通过。
- Codex 已预审 8/8 场景和每个一级下分组的 40 个记录指代代表，未发现阻断项；
  结论仅为 `NON_AUTHORITATIVE`。
- 用户通过对话确认完成单人人工审核并接受 8/8 Codex 建议；记录来源为
  `USER_CHAT_CONFIRMATION`，双人复核为 0，精确审核用时未记录。
- `run-003` 的 13 个候选工件已逐字节冻结；独立只读相似度审计结论为
  `ACCEPT`、`finding_codes=[]`。
- 6 个确定性数据文件已逐字节晋升到
  `tests/fixtures/fictional/qinglan_library_production_shape/`；未修改运行时注册表。
- 晋升后 25 项聚焦测试、291 项完整后端测试、6 项 Trellis 测试、13 项前端
  测试、前端生产构建和 `git diff --check` 均通过。

## Research References

- [`research/dataset-charter.md`](research/dataset-charter.md)
- [`research/semantic-blueprint.md`](research/semantic-blueprint.md)
- [`research/coverage-matrix.md`](research/coverage-matrix.md)
