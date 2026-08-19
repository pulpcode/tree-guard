# 青岚数据运行时接入与理解验证

## 目标

把已人工筛查、冻结、相似度审计通过并正式晋升的
`fictional-qinglan-library-control-v1` 与
`fictional-qinglan-library-semantic-v1` 接入本地模拟模式的
`ValidationDatasetProvider`，同时验证 48 节点控制树与 312 节点语义挑战树可被
Tree Understanding Core 画像和有界投影。该接入只证明数据、Provider、
Workbench 与理解核心之间的合同管线，不证明图书馆领域语义正确性。

## 已知事实

- 小型数据提交为 `6323609`，中型增量提交为 `af1fc7e`，来源分支均为
  `codex/build-test-datasets`。
- 数据保持 `CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`gold_eligible=false`、
  `patch_eligible=false`。
- 小型 fixture 包含 48 个节点和 12 个场景；中型 fixture 包含 312 个节点和
  20 个场景；两者均包含 0 个 `VALUE` envelope。
- 现有 Tree Understanding Core worktree 有未提交改动；除本任务明确拥有的
  `web.py` 装配位置外，不得覆盖、暂存或提交这些相邻改动。
- 当前 `ValidationScenarioOracle` 只能比较意图、候选和推荐的运行时状态，不能
  直接表达数据侧的全部 challenge tag 或领域判断。

## 需求

1. 确认数据提交与现有 dirty paths 不重叠；小型数据若已有等价提交则复用，
   只接入中型增量提交。
2. 分别新增小型控制集与中型语义挑战集的青岚
   `ValidationDatasetProvider`：
   - 只消费已提交的确定性生成器视图，不读取 staging 或下载目录；
   - 分别暴露 `small` variant（48 个节点、12 个场景）和 `medium` variant
     （312 个节点、20 个场景）；
   - 场景父节点引用必须由现有 `ValidationWorkbenchService` 投影为临时引用；
   - oracle 只断言意图阶段状态，候选和推荐状态保持 `None`。
3. 意图阶段采用保守映射：
   - `NEED_CLARIFICATION` → `NEEDS_CLARIFICATION`；
   - 其他已审类别 → `READY_FOR_HUMAN_REVIEW`；
   - 不把该映射解释为语义 Gold。
4. 新增本地模拟仓库 overlay：
   - 只在 `SIMULATOR` 模式加入一个青岚分类，以及小型、中型两个独立资源、
     版本和树；
   - 非青岚请求委托现有只读仓库；
   - `INTERNAL` 模式不注册或注入青岚数据；
   - selector 冲突或错误必须用固定本地错误码失败关闭。
5. 默认本地 Workbench 验证注册表同时包含现有消防 Provider、青岚小型
   Provider 和青岚中型 Provider；现有服务核心不增加领域分支。
6. 增加集成测试：
   - 两个 Provider 逐项重建共 32 个正式场景，且只断言意图状态；
   - overlay 的分类、资源、版本、树与委托行为正确；
   - 32 个场景均通过现有服务完成父引用投影与 run binding；
   - 至少一个稳定场景通过真实治理服务的虚构 transport；
   - 小型树产生 48 节点 diagnostic profile，默认投影完整覆盖；
   - 中型树产生 312 节点 diagnostic profile，默认投影稳定纳入 64 个节点并
     明确标记剩余 248 个节点未覆盖。

## Decision（ADR-lite）

**Context**：两套数据侧审核的是单一主要风险和粗粒度可观察类别，并未审核候选
排序、推荐动作或精确语义 oracle。

**Decision**：MVP 只将已审类别映射为意图阶段状态，其他 oracle 字段为 `None`；
使用模拟仓库 overlay 接入现有 Workbench，不修改通用 Provider 协议。

**Consequences**：可以验证跨领域管线、小树完整理解和中型树有界理解，不会把
synthetic 数据升级为 Gold；候选、拒答、证据不足和推荐结果的精确比较需要后续
独立 oracle 审核。

## 验收标准

- [x] 冻结数据字节和本任务所有权外的 Tree Understanding Core dirty paths
  保持内容不变。
- [x] 两个青岚 Provider manifest 与各自生成器计数、身份和限制一致。
- [x] 32 个场景引用合法，公开视图不包含稳定节点 ID。
- [x] 所有青岚 oracle 的候选和推荐状态均为 `None`。
- [x] 模拟模式注册三个 Provider；内部模式行为不变。
- [x] 48 节点投影完整覆盖；312 节点投影稳定纳入 64 个节点并标记 248 个节点
  未覆盖；两者仍为非 Gold/非 Patch。
- [x] 聚焦测试、完整后端测试、Trellis 测试、前端测试与构建、
  `git diff --check` 通过。

## 非目标

- 不修改 `ValidationDatasetProvider`、共享运行时 Schema 或
  `workbench_validation.py`；
- 不自动生成或升级语义 oracle；
- 不对 32 个场景声明候选召回率、推荐准确率或生产效果；
- 不调用真实 Qwen、百炼、Web、MCP 或受保护环境；
- 不修改 Tree Understanding Core 当前拥有的源码、合同、测试、规范或文档；
- 不 stage、commit、push、merge、rebase 或归档本任务，除非用户另行批准。

## 文件所有权

本任务只新增或修改：

- `.trellis/tasks/07-31-qinglan-runtime-validation/`；
- `src/treeguard/qinglan_validation_dataset.py`；
- `src/treeguard/web.py` 中模拟模式 repository/provider 装配；
- `tests/test_qinglan_validation_integration.py`。

数据提交本身保持原提交字节；Tree Understanding Core 的其他现有 dirty paths
只作为集成测试依赖，不纳入本任务所有权。
