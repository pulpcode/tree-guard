# H2 本地 embedding clean-room 校准数据

## Goal

在独立数据分支准备全新、完全虚构、可确定性重建的消防治理 resource 树与冻结校准
分母，用于后续比较冻结 R2 lexical A 与单一 H2 本地 embedding profile。本任务只
负责数据、数据门禁与 A 基线聚合，不修改 Provider、索引、混合召回核心或产品入口。

## Requirements

### 数据与独立性

* 使用独立 worktree 和分支，基线固定为 `47be85c`。
* 新树为 600–900 节点的 `resource` 树，`VALUE` envelope 数量固定为 0。
* 所有数据声明 `source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`gold_eligible=false`、`patch_eligible=false`。
* 不读取或复用既有树的节点名、路径、稳定 ID、场景文本或生成蓝图正文。
* 禁读 H1 scenarios、Oracle、生成器正文、逐项结果、H1 预注册与结果研究正文；禁读
  R2 密封请求、Oracle、私有工件、逐项结果；禁读 `/private/tmp` 既有实验工件。
* 功能研究仅限两份已批准 H2 研究；项目规范、当前任务工件和范围源码仍按固定
  Trellis 索引读取。

### 候选、冻结与覆盖

* 精确生成并冻结 36 条候选，类别数量固定为非字面有目标 12、词面基线 5、边界
  变化 4、跨分支干扰 5、hard negative 5、显式空目标 5；任何召回评分前按审核规则
  从该冻结候选集选出 28 条执行集。
* 冻结集固定为 20 条有目标、4 条 hard negative、4 条显式空目标。
* 20 条有目标固定为 10 条非字面、4 条词面基线、3 条边界变化、3 条跨分支干扰。
* 10 条非字面以同义表达、缩写、口语目的表达、轻微错别字、跨层表达五类各 2 条
  独立覆盖；每条只有一个主要非字面现象，不围绕已知 H1 漏例造同构题。
* 候选选择只依据覆盖、可判定性、歧义、干扰质量和数据边界审核；不得运行或查看
  A/B 结果辅助选择。
* Silver 审核拒绝导致任一冻结配额不足时立即停线；不得补造候选，不得跨类别借位。
* 冻结后场景、Oracle、树和执行集不再因 A 或未来 B 结果改写。

### Oracle、审核与角色

* Oracle 只存在于本地评分 sidecar；模型输入、公共 manifest 视图和聚合报告不得
  包含目标、排除目标、答案或评分字段。
* 每条有目标场景只有一个主要目标节点，进入 Recall@20、Recall@8 与 MRR 分母。
* hard negative 只进入排除目标 Top-8 门禁；显式空目标只进入期望状态门禁；两类
  均不进入 20 条有目标的 Recall/MRR 分母。
* Codex 可按固定 rubric 审核为 Silver；审核记录声明非 Gold、非生产、非 Patch，
  不记录真实人员身份。
* 冻结 manifest 绑定树、候选集、执行集、Oracle sidecar、审核记录和生成配置摘要；
  摘要只表示完整性，不表示权威或 Gold。

### A 基线与停止规则

* 数据冻结后只运行冻结 R2 lexical A：Top-40 lexical leg、锚点门、EXCLUSION 本地
  过滤和 Top-20 输出保持冻结；不安装、不加载、不调用 embedding。
* A 聚合只含版本、固定状态/错误码、分组计数和指标，不含文本、节点、路径、稳定
  ID、Oracle 内容或逐项结果。
* 总 Recall@20 大于 `18/20` 或非字面 Recall@20 大于 `8/10` 时记录
  `H2_DATASET_NOT_DISCRIMINATIVE` 并停线；等于阈值不触发。
* A 通过只表示数据可交接给后续 H2 实现任务，不表示 H2、Gold、生产或 Patch 资格。

## Acceptance Criteria

* [x] 确定性生成器在相同配置下产生逐字节一致的允许工件。
* [x] preflight 验证 600–900 节点、resource、0 VALUE envelope、来源声明、唯一 ID、
  父子/路径一致性、无既有数据依赖和全部摘要绑定。
* [x] 候选严格为 36，候选类别严格为 `12/5/4/5/5/5`，冻结执行集严格为 28，
  冻结类别与非字面子类别配额精确匹配。
* [x] Silver 拒绝造成任一冻结配额不足时以固定错误码停线，且不产生补造或借位工件。
* [x] Oracle sidecar 与执行集逐项绑定，三类 Oracle 不变量明确且互斥。
* [x] Silver 审核完成，所有条目通过固定 rubric，拒绝项只记录固定原因码。
* [x] canary 证明 Oracle、目标 ID、排除 ID、评分答案不进入模型输入或聚合报告。
* [x] 冻结摘要能检测树、场景、Oracle、审核或配置的域内篡改。
* [x] A 只调用冻结 lexical 路径，证明 embedding 依赖未导入且 Provider 未调用。
* [x] A 准确聚合 Recall@20/8、MRR、hard-negative Top-8 与空目标状态，并执行严格
  大于阈值的停线规则。
* [x] 只运行数据专属测试白名单与 `git diff --check`，不运行完整或递归测试。

## Definition of Done

* 数据任务、三份规划研究、确定性生成器、冻结工件、数据专属 preflight/测试和 A
  聚合均完成且可回放。
* 实施只运行白名单；不安装或调用 embedding。
* 所有数据保持 clean-room、Silver、非 Gold、非生产、非 Patch 声明。
* stage、commit、push、merge 均需单独明确批准。

## Technical Approach

1. **批准门**：本阶段只冻结 Charter、覆盖蓝图、Oracle/审核设计和所有权，任务保持
   planning；用户批准后才激活并生成。
2. **确定性生成**：使用新 seed/namespace 和任务独有的声明式拓扑参数，从空白构造
   resource 树；生成器不读取现有 fixture、H1/R2 生成器或实验临时文件。
3. **两阶段冻结**：先按 `12/5/4/5/5/5` 精确物化并冻结 36 条未评分候选，再做
   Silver rubric；审核通过数量满足全部冻结配额时，按固定候选顺序选出 28 条并写入
   不可变 manifest 摘要，否则立即停线且不补造、不借位。
4. **Oracle 隔离**：执行视图与 Oracle sidecar 分文件；评分器显式接收二者，模型
   视图只接收执行视图，并以泄漏 canary 验证。
5. **A 基线**：只复用冻结 R2 lexical 公共确定性入口，固定 Top-40，生成 Top-20
   后本地评分，最终只持久化聚合报告。

## A Baseline Evidence

* 数据提交绑定：`3af7671ce4bd5e32179b94605e0f3b16f3275880`。
* manifest 绑定：`61533ab2dcd7c5d982da9c994076484e689c1de56b726ddf2ff508f94dd3712f`。
* 冻结路径：Top-40 lexical、既定锚点门、EXCLUSION 过滤、Top-20；
  `embedding_used=false`、`provider_called=false`、`index_used=false`。
* 聚合结果：Recall@20 `16/20`，Recall@8 `16/20`，MRR@20 `0.775`，非字面
  Recall@20 `6/10`，hard-negative Top-8 `4/4`，显式空目标 `4/4`。
* 判定：`H2_DATASET_DISCRIMINATIVE`；总 Recall 与非字面 Recall 均未超过严格停线阈值。
* 结果仅为本地 Silver 数据校准，不表示 Gold、生产或 Patch 资格。

## Decision (ADR-lite)

**Context**：新分母必须独立且不能被 A/B 结果反向塑形，同时允许 Codex 做 Silver
质量审核。

**Decision**：采用“候选池 → 无评分 rubric 审核 → 配额冻结 → 摘要绑定 → A 基线”
单向流程；五类非字面现象各 2 条，Oracle 物理隔离，任何结果后编辑均不得用于本次
资格判断。

**Consequences**：冻结后发现歧义或错误不能热修后继续实验，只能停线并另立新分母。

## File Ownership

### 本阶段可写

* `.trellis/tasks/08-05-h2-local-embedding-calibration-data/prd.md`
* `.trellis/tasks/08-05-h2-local-embedding-calibration-data/research/data-charter.md`
* `.trellis/tasks/08-05-h2-local-embedding-calibration-data/research/coverage-blueprint.md`
* `.trellis/tasks/08-05-h2-local-embedding-calibration-data/research/oracle-review-design.md`
* `.trellis/workspace/h2-codex/`（仅 Trellis 初始化产生的最小工作区）

### 批准实施后计划拥有

* `scripts/generate_fire_h2_local_embedding_calibration.py`
* `scripts/preflight_fire_h2_local_embedding_calibration.py`
* `scripts/run_fire_h2_local_embedding_lexical_a.py`
* `tests/test_generate_fire_h2_local_embedding_calibration.py`
* `tests/test_preflight_fire_h2_local_embedding_calibration.py`
* `tests/test_run_fire_h2_local_embedding_lexical_a.py`
* `tests/fixtures/fictional/fire_h2_local_embedding_calibration/` 下本任务独有工件

### 明确禁止修改

* `src/treeguard/` 中 Provider、索引、混合召回和产品入口；
* 现有 H1、R2、M4/M5 数据、生成器、Oracle、测试和结果；
* 其他 Trellis 任务、archive 或其他 worktree。

## Test Whitelist

实施获批后只允许从仓库根目录运行：

```bash
UV_CACHE_DIR=/tmp/treeguard-h2-local-data-uv-cache uv run --frozen \
  python -B -m unittest tests.test_generate_fire_h2_local_embedding_calibration -v
UV_CACHE_DIR=/tmp/treeguard-h2-local-data-uv-cache uv run --frozen \
  python -B -m unittest tests.test_preflight_fire_h2_local_embedding_calibration -v
UV_CACHE_DIR=/tmp/treeguard-h2-local-data-uv-cache uv run --frozen \
  python -B -m unittest tests.test_run_fire_h2_local_embedding_lexical_a -v
python3 ./.trellis/scripts/task.py validate 08-05-h2-local-embedding-calibration-data
git diff --check
```

禁止 `unittest discover`、目录递归测试、完整 suite、embedding smoke、安装命令，以及
会加载现有 H1/R2/M4/M5 fixture 或 `/private/tmp` 既有实验工件的测试。

## Stop Conditions

* 第一阶段规划文件完成后立即停止，等待用户明确批准。
* 来源、独立性或禁读边界不确定时停止并索要安全替代材料。
* preflight 任一来源、规模、VALUE、配额、Oracle 隔离、摘要或 Silver 声明失败时
  停止，不冻结、不运行 A。
* 36 条候选总数或 `12/5/4/5/5/5` 类别数量不精确，或 Silver 拒绝导致任一 28 条
  执行集配额不足时停止；不补造、不跨类别借位。
* 冻结后发现任何场景/Oracle 错误或需要改写时停止，本次分母作废，不原地续跑。
* A 总 Recall@20 `>18/20` 或非字面 Recall@20 `>8/10` 时记录
  `H2_DATASET_NOT_DISCRIMINATIVE` 并停线。
* 任何操作需要读取禁读材料、安装/调用 embedding、修改核心或扩大测试范围时停止并
  请求新的明确批准。

## Out of Scope

* H2 Provider、模型运行时、权重安装/下载、索引 schema、query embedding 合同；
* 混合召回核心、RRF、节点/查询文档字段或产品入口修改；
* B 运行、模型比较、参数调整、reranker、生产资格、Gold 或 Patch；
* stage、commit、push、merge、任务归档。

## Research References

* [`research/data-charter.md`](research/data-charter.md) — 来源、角色、冻结与发布边界。
* [`research/coverage-blueprint.md`](research/coverage-blueprint.md) — 配额与无评分选择规则。
* [`research/oracle-review-design.md`](research/oracle-review-design.md) — 隐藏 Oracle、Silver 审核与防泄漏。
* `../08-04-governance-architecture-convergence/research/retrieval-h2-local-pre-registration.md`
  — 唯一允许的 H2 实验预注册依据。
* `../08-04-governance-architecture-convergence/research/retrieval-h2-local-embedding-options.md`
  — 唯一允许的 H2 选型依据；本任务不安装或调用模型。

## Open Questions

* 无；当前按批准停止在 28 条执行集冻结与 preflight 完成点，等待是否运行 A 的进一步
  明确确认。

## Phase 2 Evidence

* 生成并冻结树：733 节点、resource、0 VALUE envelope。
* 候选：严格 36，类别计数 `12/5/4/5/5/5`；Silver 审核 36/36 PASS。
* 执行集：严格 28，类别计数 `10/4/3/3/4/4`；非字面五类各 2。
* 数据状态：`FROZEN_CODEX_SILVER`；`embedding_used=false`；A 为 `NOT_RUN`。
* 白名单测试：生成器 4 项通过，preflight 3 项通过；未运行完整或递归测试。
* 任务专属 preflight：通过；A 聚合工件不存在。
