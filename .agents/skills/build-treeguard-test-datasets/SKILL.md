---
name: build-treeguard-test-datasets
description: "为 TreeGuard 规划、构建、检查和分批晋升多个完全虚构的验证数据集。用于新增验证领域/档位/场景、扩展语义挑战集、构造生产形状或规模压力数据，以及审查生成器是否发生笛卡尔积扩张；不用于真实数据脱敏、生产树导出或创建 Gold。"
---

# 构建 TreeGuard 测试数据集

把测试数据建设当成有来源、有用途、有预算、有门禁的发布流程，而不是一次模型
生成。复用现有 `ValidationDatasetProvider`、Canonical Tree、治理流水线和确定性
测试；不要为新领域复制 Workbench 服务。

开始前必须完整读取 [references/pipeline-contract.md](references/pipeline-contract.md)。

## 硬边界

1. 先读 `AGENTS.md`、活动任务 PRD、
   `.trellis/spec/backend/development-data-boundary.md` 和质量规范；实施前使用
   `trellis-before-dev`。
2. 只使用从批准合同形状独立构造的 `CLEANROOM_SYNTHETIC` 内容。不得输入、
   改写或概述真实树、真实节点字段名、`VALUE`、专家文本、受保护源码、内部
   标识、路径、拓扑、Prompt、模型响应或 trace。
3. 不做 Web harvest，不把公开文章、翻译、真实字段清单或示例值变成 fixture。
   来源或敏感性不清时停止，并请求完全虚构的替代材料。
4. 所有 AI 生成或 AI 评审内容固定 `gold_eligible=false`。人工复核只能把
   synthetic 候选晋升为正式 fictional fixture，不能改变其来源属性或证明真实
   领域正确性。
5. 产品 AI 结果只写 sidecar/overlay。没有明确人工批准时，不修改正式 fixture，
   不 stage、commit、push 或调用外部模型。
6. 调用本 Skill 默认只完成规划。即使 Charter 和覆盖计划已经就绪，也必须等
   用户明确敲定开发 Plan 并发出开始实施指令，才能构建候选数据。

## 选择工作模式

- **只规划数据组合**：完成数据集组合表、charter 和覆盖计划后停止，不生成数据。
- **构建候选批次**：生成到已忽略的 staging 目录，运行 L1/L2，输出待审清单。
- **晋升已有批次**：先验证审阅记录、来源分类和全部门禁，再复制到
  `tests/fixtures/fictional/` 并重跑完整测试。
- **检查现有生成器**：从 L1 开始，重点检查兼容允许表、组合密度、重复形状和
  跨档复用；只报告问题，不擅自重写数据。

多步构建应使用独立 Trellis 任务和独立 worktree。推荐顺序是：

1. 当前任务只完成 Skill；
2. 单独讨论并冻结开发 Plan；
3. 功能实现开始后，由用户新开对话和数据准备 worktree；
4. 数据 worktree 从双方约定的基线提交创建，只拥有 fixture、数据生成器、
   manifest 和对应测试；功能 worktree 不同时修改这些文件；
5. 按 Plan 约定的合同与合并顺序集成。

不得因为 Skill、Charter 或 Plan 已存在就自动创建数据 worktree 或生成数据。

## 阶段 0：盘点和复用

1. 搜索现有数据合同、Provider、生成器、fixture 和测试：

   ```bash
   rg -n "ValidationDatasetProvider|benchmark_role|gold_eligible|write_.*dataset" \
     src tests docs
   ```

2. 复用 `treeguard.adapter`、现有治理核心和 Provider 注册机制。当前消防数据的
   角色、数量或字段不是新领域必须复制的模板。
3. 记录当前基线命令和结果。不要从未经检查的生成数据推断现有语义覆盖。

## 阶段 1：定义数据集组合

先做最小组合，不做“领域 × 规模 × 风险 × 故障 × 模型”的全展开。为每个候选
数据集选择一个主角色：

- `PRECISION_CONTRACT`：小型、人工可读，验证确定性状态合同；
- `SEMANTIC_CHALLENGE`：歧义、冲突、证据不足、近名干扰和拒答；
- `PRODUCTION_SHAPE`：只逼近获批准的规模/形状分桶，不复现生产语义；
- `SCALE_STRESS`：规模、重排、时延和候选上限，不承担语义结论；
- `DOMAIN_CONTROL`：小型第二虚构领域，用于识别领域过拟合。

每个数据集写一份 Dataset Charter，至少声明：

- `dataset_ref`、主角色、目的与明确非目标；
- 完全虚构的领域声明、`derived_from_real=false`、`gold_eligible=false`；
- 目标节点/场景数量、固定 seed 和确定性重建方式；
- challenge tags、覆盖缺口和为什么不能由现有数据集覆盖；
- 人工审核预算、随机抽检数、双人复核上限和停线条件；
- 计划修改的生成器、fixture、Provider、注册项和测试。

没有通过 Charter 审查，不进入生成阶段。

Charter 通过也不等于实施授权。进入阶段 2 前，必须确认用户已批准包含文件所有权、
并行 worktree 基线、接口合同、验收命令和合并顺序的开发 Plan。

## 阶段 2：设计语义蓝图

把节点分成三类并保持边界：

- **curated core**：少量有明确测试目的的节点/场景；需要逐项人工复核；
- **approved blueprint background**：由审核过的 subject/facet 兼容允许表扩展；
  可机器生成，但不独立承担语义 oracle；
- **stress-only filler**：只制造规模和排序压力；不得进入语义评分或作为目标节点。

先冻结整棵树和每个分支描述的主体范围，再设计属性：

- 对每个 `PROPERTY` 明确回答“这个值属于谁”：整棵树描述的单一对象、重复对象
  中的一个成员，还是集合整体的聚合状态。
- `CONCEPT` 并非一律不能带属性。若当前树或分支明确描述一个单一对象，例如一项
  虚构任务，其概念节点下可以有该对象的名称等属性。
- 若 `CONCEPT` 表示类别或对象集合，不得把成员级时长、状态、名称等直接挂在
  集合概念下。应使用现有合同的复合列表结构，即
  `PROPERTY + value_type=class + cardinality=MULTIPLE` 表示重复成员，再把成员
  属性放在该结构下。
- 集合概念可以带集合级聚合属性，但名称、需求文本和场景 oracle 必须明确表达
  “总数、合计、统一规则”等集合语义，不能让审核者猜测。
- 无法唯一判断属性所有者或单体/集合范围时，蓝图不得通过；不能用类型和基数
  合法来替代语义归属正确。

禁止对独立维度直接做全局 `product()`。优先使用：

- `allowed_facets_by_subject` 等显式兼容允许表；
- covering-array/pairwise 覆盖关键维度；
- 一个场景携带多个 challenge tags；
- 只把少量锚点复制到不同规模，验证规模不改变合同结果；
- 将 transport/非法输出故障保留在独立小型合同集。

蓝图必须能解释每个 curated core 和每个组合族为什么存在。无法解释的组合删除，
不能靠批量人工清洗补救。

## 阶段 3：确定性构建到 staging

1. 默认路径：

   ```text
   artifacts/fictional-validation/<run_ref>/
   ```

   `artifacts/` 已被忽略；不要把未批准候选写入正式 fixture。
2. 使用固定 seed、稳定排序和显式 ID 规则。相同输入必须逐字节重建一致。
3. 保存最小工件：charter、blueprint、生成数据、L1 聚合报告、L2 规范化
   findings、人工审阅清单和 promotion checklist。
4. staging 也遵守外网数据边界。忽略目录不是敏感数据豁免区。

## 阶段 4：运行 L1 确定性门禁

所有候选都必须机器检查：

- `adapt_tree_document()` 成功，节点/场景数精确，重建逐字节稳定；
- manifest、父子引用、场景引用、Provider 资源和 oracle 状态一致；
- `fictional=true`、`gold_eligible=false`，禁止字段和 canary 不泄漏；
- curated/background/filler 的允许用途没有越界；
- subject/facet 组合属于显式允许表；
- 每个属性的所有者与单体/成员/集合范围明确，集合概念没有直接承载未建模的
  成员级属性；
- 没有编号兄弟、重复 child vector、异常重复子树或无解释的组合密度跃升；
- 语义场景不把 filler 当目标，规模档不冒充语义主基准；
- 新场景填补声明的覆盖格，而不是重复已有场景。

L1 失败时回退到最早有缺陷的阶段。最多修复 3 轮；仍失败则保留聚合失败摘要并
停止，不通过放宽阈值或人工逐项修数据绕过。

## 阶段 5：运行只读 L2 Critic

Critic 使用冷启动上下文，只读取阶段合同、候选工件和 L1 结果，不读取生成过程。
它只 flag：

- 层级或组合是否自然；
- 场景是否可答、是否存在证据不足或多解；
- oracle 是否只是可观察合同状态；
- challenge tag、目的和实际内容是否一致；
- 是否存在同义重复、模板化语言或疑似领域过拟合。

Critic 不修改候选、不授予 Gold、不裁定真实行业正确性。若使用外部强模型，必须
逐次确认输入完全虚构并得到明确出域批准；原始请求、响应和 trace 不落库，只保留
允许列表化的 finding code、严重度、虚构定位和摘要，并标记非权威。

## 阶段 6：执行有预算的 L3 人工审核

默认每批最多 25 个候选场景，并在生成前写死预算：

- 先让机器检查、去重和聚类覆盖全部候选；
- 人工复核全部高风险项、每个新风险簇至少一个代表、再随机抽 5 个；
- 只有 Charter 明确配置且确有第二审核者时，才选择最多 3–5 个计划进入精确
  合同集的案例进行双人独立复核；当前只有一名审核者时把上限设为 0，不能由
  同一人或同一模型模拟双审；
- 首个可行性批次优先控制在 31–50 节点、8 个场景，能在一次短审阅中完成。

停线条件：

- 任一数据边界、安全或 oracle 越权严重错误；
- 随机样本中出现两个及以上实质语义错误；
- 同一错误跨两个聚类重复；
- 审核用时超过 Charter 预算。

触发停线后修蓝图或生成器并重新抽样，不继续全量人工清洗。`300–500` 个节点
全部人工审核不是首个里程碑；只有小批次证明生成器显著降低审核成本后，才讨论
扩大 curated core。

## 阶段 7：人工批准后晋升

只有同时满足以下条件才可提出 promotion：

- 来源分类、Charter、L1、L2 和 L3 记录完整；
- 没有未解决的 blocking finding；
- 最终字节仍是完全虚构内容，且与被审版本一致；
- fixture、生成器、Provider、manifest、文档和测试的改动计划完整；
- 用户明确批准本次晋升范围。

晋升后重跑确定性重建、聚焦测试、完整后端测试、Trellis 测试和
`git diff --check`。报告准确命令和结果；未配置的 lint、typecheck、coverage
或 CI 不得声称通过。

## 输出要求

每次运行最终报告：

1. 数据集组合及各自主角色；
2. 本批次覆盖的新增验证问题；
3. 机器门禁结果和未解决 findings；
4. 已用/剩余人工预算及是否触发停线；
5. 工件状态：`GENERATED`、`MACHINE_VALIDATED`、`HUMAN_SCREENED`、
   `DUAL_REVIEWED` 或 `FROZEN`；
6. `gold_eligible=false` 和不能外推到生产准确率的限制；
7. 下一次最小批次，而不是笼统要求制造更大数据。
