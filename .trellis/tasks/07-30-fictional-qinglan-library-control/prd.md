# 构建青岚社区图书馆跨领域控制数据集

## 背景

TreeGuard 需要一套与既有消防历史回归集语义隔离的跨领域控制数据，用于检查信息树
理解 Agent 和现有治理 MVP 是否隐含依赖消防命名、分支或层级。本任务从空白
Dataset Charter 和 Semantic Blueprint 独立构造完全虚构的“青岚社区图书馆”，
不读取、改写或仿制既有消防数据。

## 目标

1. 构建一个 `DOMAIN_CONTROL` 小型候选集，包含 48 个节点和 12 个场景。
2. 复用 Canonical Tree、`ValidationDatasetProvider` 和现有治理场景合同。
3. 用显式 `allowed_facets_by_subject`、coverage cell 和固定 seed 保证可解释、
   可重建且不存在全局笛卡尔积。
4. 完成 L1 确定性门禁、只读 L2 Critic 和有预算的人工审阅清单。
5. 候选只写入忽略的 staging；正式 fixture 晋升必须另获人工批准。

## 非目标

- 不读取或复用既有消防树、场景、生成器语义表或语义断言。
- 不验证真实图书馆行业正确性，不创建 Gold，不外推生产准确率。
- 不构建中型、大型或压力树。
- 不修改共享运行时 Schema、数据集注册表、Workbench 或信息树理解 Agent。
- 不调用 Web、外部模型、真实仓库或受保护环境。
- 不自动 stage、commit、push、merge、rebase 或晋升正式 fixture。

## 数据边界

- `source_class=CLEANROOM_SYNTHETIC`
- `fictional=true`
- `derived_from_real=false`
- `gold_eligible=false`
- `patch_eligible=false`
- 所有组织、节点、关系和场景均从本任务蓝图独立创造。
- 不包含 `VALUE`、真实字段、真实路径、专家文本、模型流量或稳定伪名映射。
- 旧数据相似度审计只在候选冻结后由独立只读阶段执行；其结果只能接受或拒绝
  候选，不能反向指导生成器。

## 已批准范围

- 领域：完全虚构但贴近现实的“青岚社区图书馆”。
- 一级分支：馆藏资源、服务空间、读者服务、公共活动。
- 首批：48 个节点、12 个场景，固定 seed `20260730`。
- 主角色：`DOMAIN_CONTROL`。
- 人工预算：全部场景一次筛查、固定抽样 4 个、4 个单人重点复查、120 分钟；
  当前不要求双人复核。
- 用户已明确批准把通过冻结后相似度审计的 run-004 晋升为正式 fictional
  fixture；本次批准不包含数据集注册表或运行时 Provider 接入。

## 正式 fixture 晋升范围

正式目录为 `tests/fixtures/fictional/qinglan_library_control/`，只包含：

- 与 run-004 冻结版本逐字节一致的 `dataset-charter.json`、`manifest.json`、
  `coverage-matrix.json`、`semantic-blueprint.json`、`tree.json` 和
  `scenarios.json`；
- 只含聚合审核状态和边界声明的 `promotion.json`；
- 说明用途、限制和未注册状态的 `README.md`。

审核 UI、人工下载文件、逐项审核记录、L1/L2 sidecar、冻结清单和旧数据审计过程
不复制到正式 fixture。`manifest.json.state=MACHINE_VALIDATED` 保留为被审字节；
最终晋升状态只记录在新增的 `promotion.json`，不得改写冻结内容。

## 文件所有权

本任务可拥有：

- 本任务目录及 research；
- `src/treeguard/fictional_qinglan_library_data.py`；
- 忽略目录
  `artifacts/fictional-validation/qinglan-library-control-v1-run-003/` 和
  `artifacts/fictional-validation/qinglan-library-control-v1-run-004/`；
- `tests/fixtures/fictional/qinglan_library_control/`；
- `tests/test_fictional_qinglan_library_data.py` 中仅属于本数据集的聚焦测试；
- 人工批准晋升后才可创建的正式 fixture、聚焦测试和数据说明文档。

本任务不得修改用户列出的共享核心模块、运行时 Schema、数据集注册表和 Agent
实现。现有 `.agents/skills/build-treeguard-test-datasets/` 与其 Trellis 任务
属于并行 Skill 工作，本任务不得覆盖或纳入。

## 共享合同依赖

- 树输入复用 `adapt_tree_document()` 与 `CanonicalTree`。
- 场景复用 `ValidationScenarioRequest` 的 requirement、父节点、节点类型、值类型
  和基数提示。
- oracle 只使用现有公开的可观察状态，不定义语义 Gold。
- `challenge_tags`、来源分类和独立性证据保存在 staging sidecar，不扩展共享
  运行时 Schema。
- 信息树理解 Agent 若需要新的稳定结果投影，由主实现任务提供；本数据任务只记录
  所需状态、候选、澄清、证据不足、拒绝和 snapshot 绑定字段。

## 验收标准

- [x] Charter、Blueprint 和 coverage matrix 与本 PRD 一致并已冻结。
- [x] 生成器只消费本任务蓝图，不导入或读取任何既有消防数据。
- [x] 相同输入与 seed 逐字节重建相同 staging 工件。
- [x] `adapt_tree_document()` 成功，精确得到 48 个节点和 0 个 VALUE envelope。
- [x] 12 个场景引用合法、主风险唯一且 coverage cell 不重复。
- [x] 所有 subject/facet 组合属于显式允许表，不使用全局 `product()`。
- [x] L1 报告无 blocking finding，L2 Critic 不修改候选且不授予 Gold。
- [x] 人工审阅清单符合预算与停线条件。
- [x] 人工批准晋升前，候选始终保持 staging 状态且未写正式 fixture 或注册表。
- [x] 聚焦测试、完整后端测试、Trellis 测试和 `git diff --check` 结果如实报告。
- [x] 六个正式数据文件与 run-004 冻结版本逐字节一致。
- [x] `promotion.json` 准确记录人工筛查、冻结、相似度审计和非 Gold 边界。
- [x] 正式 fixture 可由现有生成器确定性重建，并通过 Adapter 与引用检查。
- [x] 晋升后未修改正式数据集注册表或共享运行时模块。

## 当前候选状态

`qinglan-library-control-v1-run-003` 已完成 12 条单人人工筛查，结论为保留 9
条、修改 3 条、删除 0 条。该 run 作为审核证据保留，不冻结、不晋升。

`qinglan-library-control-v1-run-004` 已按三项人工意见修订蓝图和场景并重新通过
L1/L2；Codex 非权威预审建议保留 12 条，人工筛查最终保留 12 条。审核确认未超过
120 分钟，未触发停线条件。12 个审核相关工件的精确字节已由
`freeze-manifest.json` 绑定，候选状态为 `FROZEN`。独立只读审计已按预先固定的
七类指标和拒绝阈值完成，结论为 `ACCEPT`，没有据此修改冻结候选。用户随后明确
批准正式晋升；六个冻结数据文件现已逐字节复制到
`tests/fixtures/fictional/qinglan_library_control/`，fixture 状态为 `PROMOTED`。
该目录仍保持 `gold_eligible=false`、`patch_eligible=false`，且未加入运行时
数据集注册表。

## 停线条件

- 任一数据边界、安全或 oracle 越权错误；
- 固定随机样本中出现两个及以上实质语义错误；
- 同类问题跨两个覆盖聚类重复；
- 审核超过 120 分钟；
- 发现模板换词、全局笛卡尔积或无法解释的组合密度；
- 冻结后的独立审计发现与旧数据明显雷同。

## 晋升验证

- 六个正式数据文件与 run-004 冻结来源逐字节一致；
- `uv sync --frozen` 完成依赖审计；
- 完整后端 `unittest` 252 项通过；
- Trellis `unittest` 6 项通过；
- 数据任务与相似度审计任务校验通过；
- `git diff --check` 通过。
