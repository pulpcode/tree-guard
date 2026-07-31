# TreeGuard 多测试数据集流水线合同

本文件定义 Skill 的阶段输入、输出、门禁和回退规则。它是开发工作流合同，不是
新的运行时 Schema；持久化 fixture 时仍以 `src/treeguard/` 中的现有 Python
合同和已提交测试为准。

## 0. 人工启动门

默认只允许完成 Dataset Charter、组合表和覆盖计划。满足以下全部条件前，不创建
候选数据、不修改生成器、不晋升 fixture：

- 用户已经明确敲定开发 Plan；
- 用户已经明确要求开始实施；
- 功能实现和数据准备 worktree 的基线提交、文件所有权、共享合同和合并顺序已写清；
- 数据准备对话/worktree 已由用户在实施阶段另行启动。

Skill 被调用、Charter 被批准或某个检查通过，都不能替代上述人工启动授权。

## 1. 工件分类

| 分类 | 允许内容 | 可否入库 | 权威性 |
|---|---|---|---|
| `CLEANROOM_SYNTHETIC` | 从批准合同形状独立构造的虚构树、场景和 oracle | 人工批准后可进入 fictional fixture | 只证明测试合同 |
| `DETERMINISTIC_REPORT` | 固定 finding code、状态和聚合计数 | 可 | 只证明所执行检查 |
| `EXTERNAL_MODEL_CRITIQUE` | 允许列表化的非权威 sidecar | 必要且批准后可 | 不可自证语义正确 |
| `PUBLIC_BACKGROUND_REFERENCE` | 最小公开技术合同链接和摘要 | 仅 research | 不参与逐项 fixture 派生 |
| `PUBLIC_DERIVED` | 特别批准的公开派生数据 | 默认不建；必须隔离 | 非 clean-room、非 Gold |
| `PROTECTED_DERIVED` | 真实或受保护环境派生内容 | 禁止 | 禁止处理 |
| `REAL_HUMAN_GOLD` | 真实领域专家裁决 | 本 Skill 无权创建 | 仅受保护流程可定义 |

人工审核不会改变来源分类。`reviewed synthetic` 仍然是
`CLEANROOM_SYNTHETIC`，且 `gold_eligible=false`。

## 2. 数据集组合，而非全组合

一个数据集只选一个主角色，可附带少量次要 challenge tags：

| 主角色 | 推荐规模 | 主要人工投入 | 不得声称 |
|---|---:|---|---|
| `PRECISION_CONTRACT` | 约 31–50 节点 | curated core 全审；少量双审 | 真实领域 Gold |
| `SEMANTIC_CHALLENGE` | 以覆盖缺口决定 | 风险簇代表 + 随机抽检 | 全量语义正确率 |
| `PRODUCTION_SHAPE` | 生产聚合分桶附近 | 形状策略和泄漏检查 | 复现生产语义 |
| `SCALE_STRESS` | 当前上限附近；非默认超大 | 机器检查为主 | 大小等于真实效果 |
| `DOMAIN_CONTROL` | 约 31–50 节点 | 小型全审 | 第二领域代表所有领域 |

默认先复用当前约 `31 / 401 / 2,001` 节点档位。只有发现明确的复杂度拐点、内存/
时延风险或生产上限扩张证据时，才新建更大压力树；不要习惯性生成 1–5 万节点。

覆盖计划使用 pairwise/covering-array 思路，至少记录：

```text
coverage_cell =
  primary_role
  + challenge_tags
  + tree_size_bucket
  + expected_observable_state
```

新增场景必须填补一个空 coverage cell，或作为一个已知回归的最小反例。不同模型、
Prompt 和 transport 故障不能与所有领域/规模全展开。

## 3. Dataset Charter

Charter 可先写入当前 Trellis 任务 research 或 staging。最小字段：

```yaml
dataset_ref: fictional-<domain>-<purpose>
primary_role: DOMAIN_CONTROL
purpose: 验证通用治理流程没有依赖消防专属分支
non_goals:
  - 不验证真实行业正确性
  - 不创建 Gold
source_class: CLEANROOM_SYNTHETIC
fictional: true
derived_from_real: false
gold_eligible: false
seed: 20260730
target:
  nodes: 31
  scenarios: 8
challenge_tags:
  - clear_intent
  - semantic_interference
  - insufficient_evidence
coverage_gap: 当前只有单一虚构领域，无法识别领域专属实现
review_budget:
  batch_limit: 8
  random_sample: 3
  dual_review_limit: 0
  time_limit_minutes: 120
stop_rules:
  critical_boundary_errors: 1
  material_random_sample_errors: 2
planned_owners:
  generator: src/treeguard/<fictional_generator>.py
  fixtures: tests/fixtures/fictional/<dataset_ref>/
  provider: src/treeguard/<dataset_provider>.py
  tests: tests/test_<fictional_generator>.py
```

例子中的名称和数字只是完全虚构的工作流示意，不自动成为运行时枚举或产品目标。

## 4. Semantic Blueprint

蓝图至少包含：

```yaml
semantic_scope:
  tree_subject_scope: SINGLE_ENTITY
  described_subject_ref: fictional-subject-root
  attribute_owners:
    fictional-property-alpha: ROOT_ENTITY
  repeated_entities:
    - collection_ref: fictional-collection-beta
      member_container_ref: fictional-member-list
      member_container_contract:
        node_kind: PROPERTY
        value_type: class
        cardinality: MULTIPLE
node_families:
  curated_core:
    - family_ref: fictional-core-alpha
      purpose: 精确合同锚点
      human_review_required: true
  blueprint_background:
    - family_ref: fictional-background-beta
      allowed_facets_by_subject:
        subject_alpha: [facet_one, facet_two]
        subject_beta: [facet_two]
      semantic_oracle_eligible: false
  stress_only_filler:
    - family_ref: fictional-filler-gamma
      targetable_by_semantic_scenario: false
      semantic_oracle_eligible: false
```

`SINGLE_ENTITY`、`ENTITY_COLLECTION`、`ROOT_ENTITY`、`COLLECTION_ITEM` 和
`COLLECTION_AGGREGATE` 只用于蓝图说明属性归属，不新增运行时枚举。规则如下：

- `CONCEPT` 是否可带属性取决于其语义主体，不取决于节点类型的全局禁令。当前
  树明确描述一个单一对象时，概念节点可包含该对象的属性。
- 类别或集合概念下的成员级属性必须先经过重复成员容器；当前合同用
  `PROPERTY`、`value_type=class`、`cardinality=MULTIPLE` 表达该容器。
- 集合级属性必须明确标记为 `COLLECTION_AGGREGATE`，并使用能观察到聚合含义的
  名称和场景文本。
- 每个 curated 属性和场景目标都必须能回答“值属于哪个主体、是一份还是每个
  成员一份”。答案不唯一时，先修蓝图，不进入生成。

不得只声明两个独立列表后计算 `subjects × facets`。每个允许组合需要属于一个
有测试目的的 family；密度接近全组合时，作者必须证明每个组合有独立意义，否则
门禁失败。

## 5. 阶段状态机

```text
CHARTERED
→ BLUEPRINT_APPROVED
→ GENERATED
→ MACHINE_VALIDATED
→ HUMAN_SCREENED
→ FROZEN
```

- `DUAL_REVIEWED` 是从 `HUMAN_SCREENED` 到 `FROZEN` 之间的可选附加状态，仅当
  Charter 的 `dual_review_limit > 0` 且确有第二审核者时使用；
- 只有一名审核者时必须将 `dual_review_limit` 设为 0，不能由同一个人或同一个
  模型重复检查来声称双审；
- `L1 FAIL`：回到 Charter、Blueprint 或 Generator 中最早的缺陷阶段；
- `L2 BLOCK`：回到 Blueprint/Scenario，不自动改 oracle；
- `L3 STOP`：整批暂停，修生成器后重新生成并重新抽样；
- 任一阶段超过 3 轮修复：结束本次 run，不能放宽门禁继续；
- 任一工件字节变化：后续审核状态失效，从相应门禁重新开始。

`FROZEN` 仅表示已批准的 fictional fixture 版本，不表示 Gold 或生产验证通过。

## 6. L1 finding codes

未来实现 preflight 时使用稳定 code，并只输出允许列表化聚合。建议起始集合：

| code | 含义 | 回退 |
|---|---|---|
| `DATASET_SOURCE_CLASS_INVALID` | 来源分类缺失或不允许 | Charter |
| `DATASET_BOUNDARY_CANARY_FOUND` | 禁止内容或 canary 泄漏 | 立即停线 |
| `DATASET_NONDETERMINISTIC` | 相同输入无法逐字节重建 | Generator |
| `DATASET_COUNT_MISMATCH` | 节点/场景数不符 | Generator |
| `DATASET_REFERENCE_INVALID` | manifest、父子或场景引用无效 | Generator |
| `DATASET_ROLE_MISMATCH` | 数据内容超出主角色允许用途 | Charter/Blueprint |
| `DATASET_COMBINATION_UNAPPROVED` | subject/facet 不在允许表 | Blueprint |
| `DATASET_ATTRIBUTE_OWNER_AMBIGUOUS` | 属性主体或单体/集合范围无法唯一判断 | Blueprint |
| `DATASET_ITEM_ATTRIBUTE_ON_COLLECTION` | 成员级属性直接挂在集合概念下 | Blueprint |
| `DATASET_CARTESIAN_DENSITY_HIGH` | 组合密度异常且无逐项理由 | Blueprint |
| `DATASET_REPEATED_VECTOR` | child/facet vector 重复 | Blueprint |
| `DATASET_SCENARIO_COVERAGE_DUPLICATE` | 未填补新覆盖格 | Scenario |
| `DATASET_FILLER_TARGETED` | 语义场景把 filler 当目标 | Scenario |
| `DATASET_ORACLE_OVERCLAIM` | oracle 超出可观察确定性状态 | Scenario |
| `DATASET_REVIEW_BUDGET_EXCEEDED` | 人审超过 Charter 预算 | 停线 |

报告中不得包含真实字段、完整树、稳定内部 ID、路径、原始文本、Prompt、响应或
trace。稳定 code 只是诊断合同，不证明真实数据已脱敏。

## 7. L2 Critic 合同

Critic 输入：

- 本文件；
- 经 L1 通过的完全虚构候选；
- Dataset Charter 和 Semantic Blueprint；
- L1 的固定 code 与聚合结果。

Critic 输出为只读 findings：

```yaml
critic_authority: NON_AUTHORITATIVE
source_class: CLEANROOM_SYNTHETIC
findings:
  - code: SEMANTIC_HIERARCHY_UNNATURAL
    severity: blocking
    fictional_ref: fictional-core-alpha
    summary: 一句最小、完全虚构的说明
```

Critic 还必须检查属性所有者是否明确，以及成员级属性是否错误地直接挂在集合
概念下；这类问题返回只读 finding，不能靠改写 oracle 掩盖。

Critic 不访问生成日志，不自动编辑 expected/oracle，不把“另一个模型同意”当作
独立事实。原始模型流量不得写入仓库或 Trellis 工件。

## 8. L3 审核合同

每批按以下顺序选样：

1. 全部 `blocking/high-risk`；
2. 每个新 challenge/结构聚类至少一个代表；
3. 使用 Charter 固定 seed 选取规定数量的随机样本；
4. 仅当 Charter 配置且第二审核者可用时，从计划进入 `PRECISION_CONTRACT` 的
   项目中选择最多 3–5 个双审项；否则该步跳过并记录预算为 0。

记录：

- 计划数、实际审核数和用时；
- `accept / revise / reject` 计数；
- 分歧计数与是否完成仲裁；
- 是否触发预先声明的停线条件；
- 只使用虚构引用和允许列表 finding code。

不要记录专家自由文本、真实身份、原始模型输出或受保护案例。需要详细语义意见时，
意见本身也必须完全虚构且限制在当前测试合同。

## 9. Promotion checklist

- [ ] 当前任务和 worktree 独立，未覆盖其他并行工作
- [ ] 用户已批准开发 Plan，并明确发出实施指令
- [ ] 数据准备 worktree 的基线、文件所有权、共享合同和合并顺序已冻结
- [ ] 最终文件全部为 `CLEANROOM_SYNTHETIC`
- [ ] `fictional=true`、`derived_from_real=false`、`gold_eligible=false`
- [ ] Dataset Charter 与 Semantic Blueprint 已批准
- [ ] L1 全通过且重建逐字节稳定
- [ ] L2 无 blocking finding
- [ ] L3 未触发停线，预算未超
- [ ] 修改后版本与被审最终字节一致
- [ ] 生成器、fixture、Provider、manifest、文档、测试同步
- [ ] 正式 fixture 晋升已得到用户明确批准
- [ ] 聚焦测试、完整后端测试、Trellis 测试、`git diff --check` 已真实通过

Promotion 不包含自动 stage、commit、push、生产写入或外部模型调用。
