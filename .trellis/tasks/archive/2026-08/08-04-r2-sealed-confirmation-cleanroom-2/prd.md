# R2 未见密封确认数据：第二次 clean-room 构造

## Goal

从功能基线 `03faee0a7a33e0ee413a4d91b70e8f577085751f` 的全新工作树独立构造一套
R2 未见密封确认数据。数据只用于后续独立执行；本任务不运行模型或任何召回/语义实验。

## 永久停线条件

出现以下任一行为立即停线，不尝试改名、删字段、重做局部样本或继续测试：

* 读取、扫描、引用或复用第一次 R2 数据分支、工作树或其任何公开/私有工件；
* 读取或扫描 M5、B1–B3、R1/R2 fixture、测试源码、请求、Oracle、标注、实验记录或结果；
* 读取 `tests/fixtures/fictional/` 中任何既有实验数据；
* 运行递归测试发现、完整测试套件、模型、R1、R2、Semantic 或其他功能实验；
* 依据预期召回效果、功能输出或模型输出修改、选择或替补请求。

## Requirements

### 数据来源与形状

* 仅使用本 PRD、固定项目规范和从空白独立发明的同领域高层概念。
* 数据分类固定为 `CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`gold_eligible=false`、`patch_eligible=false`。
* 构造一棵全新 300–800 节点 `resource` 树；结构、节点名称和 ID 均不得沿用第一次构造。
* 候选最多 36 条，文字与 scenario brief 全新；冻结 28 条。
* 冻结配额为：6 条词面基线、6 条边界变化、4 条跨分支干扰、4 条 EXCLUSION hard
  negative、4 条非字面表达、4 条显式空目标。
* 每条只有一个主类别；选择固定为各类别通过审核的最低序号，不使用表现分数。

### 私有阶段顺序

```text
请求与 scenario brief 不可覆盖发布
→ 只读取请求正文完成 text-only TARGET/SCOPE/EXCLUSION Silver
→ 锁定 Silver 后映射 Oracle
→ 工程审核
→ 按预定槽位冻结 28 条
→ 生成提交前 handoff template
```

请求、brief、Silver、Oracle、审核、选择正文和所有 digest 只进入仓库外 `0700` 私有
根目录中的 `0600` 不可覆盖文件，不进入 Git、Trellis、公开报告或被测输入。

### 提交绑定

* `function_baseline_commit=03faee0a7a33e0ee413a4d91b70e8f577085751f`。
* 公开数据经人工审阅并获 Git 批准后才可产生 `data_commit`；该提交必须以后述功能
  基线为祖先。
* 正式 preflight 必须验证 HEAD 精确等于 `data_commit`、工作树/index 干净，并且
  `function_baseline_commit..data_commit` 只新增本 PRD 白名单文件。
* 白名单外所有文件（包括 R2、Prompt、Provider、角色合同、runner 和通用测试）相对
  功能基线必须零差异。
* v3 扩展的提交前 HEAD 固定为已有数据提交
  `16534dd870c8a23feeab4f4e549fe67f0dd6fa26`；只允许修改本 PRD、数据
  preflight 和数据专属测试。后续新 `data_commit` 仍必须以功能基线为祖先。
* 本轮不 stage、commit、push 或 merge，因此不得运行 `finalize`，
  不得生成最终 ledger、digest 或 freeze receipt。

### 最终冻结模式

* `finalize` 仅在真实 `data_commit` 产生后运行；必须重新验证
  commit 绑定、清洁工作树/index、白名单新增、公开数据与私有
  01–06，且最终目录必须尚不存在。
* 执行合同由额外的私有 `0600` JSON 输入提供，字段集、类型、数组顺序与值
  必须精确等于：

  ```text
  schema_version=treeguard.fire-r2-c2-execution-binding.v1
  model_id=qwen3.6-35b-a3b
  prompt_version=treeguard.retrieval-role-extraction.zh.v2
  role_contract_version=retrieval-role-model-output.v1
  r1_strategy_id=treeguard.decoupled-role-evidence-retrieval.v1
  r2_strategy_id=treeguard.boundary-tolerant-role-lexical-retrieval.v1
  temperature=0
  enable_thinking=false
  candidate_limit=20
  gate_k_values=[8,20]
  round_count=2
  scenario_count=28
  max_attempts_per_unit=2
  maximum_actual_call_count=112
  ```

  整数必须严格拒绝 bool。`finalize` 和 `verify-frozen` 必须各自重新读取
  同一执行配置的原始字节。
* `finalize` 在私有根目录下使用随机 `0700` 临时子目录，以 no-follow、
  `0600` 不可覆盖方式写入 ledger/receipt，全部回读验证后使用同根
  no-replace 原子 rename 发布为 `08-final-freeze.v1/`。
* ledger 绑定两个 commit、数据集/合同版本、全部已提交白名单文件与私有
  01–06 的 byte length/SHA-256、冻结分母/配额与执行合同；执行配置还必须
  以固定逻辑名 `execution-binding.v1.json`、byte length 和 SHA-256 绑定原始字节，
  不保存真实私有路径，并固定
  `sealed=true` / `opened=false`。
* receipt 绑定 ledger 精确字节长度与 SHA-256、`data_commit` 和密封状态。
  SHA-256 仅声明完整性，不声明身份、Gold 或生产资格。
* `verify-frozen` 必须重做 commit/公开/私有校验，严格重算全部长度与摘要，
  拒绝字段、顺序、权限、owner、symlink、commit、摘要或密封状态篡改。
  stdout 只输出聚合状态。

### v3 执行输入 sidecar

* 保留 v1/v2 私有根与冻结工件，不覆盖、不删除；v3 使用全新 `0700`
  私有根。
* v3 字节复制已校验的私有 01–06，不修改其任何内容，并新增
  `07-execution-input.v1.json` `0600` 不可覆盖 sidecar。
* sidecar 按冻结集精确顺序保存 28 条；每条只依据锁定请求、scenario
  brief 和公开树编制 `proposed_parent_node_id`、不同顶层分支的
  `wrong_branch_parent_node_id`、三类结构提示与完整 `IntentContent`
  `retrieval_seed`。
* sidecar 不使用 Silver、Oracle、审核内容、模型或任何召回/实验结果；
  preflight 只做严格字段、枚举、引用、分支和来源绑定，并报告
  `28 * 5 = 140` 个可执行输入单元，不运行五视图。
* 五视图名称和变换精确固定为 `V_CANONICAL`、`V_FREE_TEXT_DROPPED`、
  `V_PARENT_ABSENT`、`V_PARENT_WRONG_BRANCH`、`V_REQUIREMENT_ONLY`；
  preflight 必须实际构造五类 `IntentRequest` / `IntentContent` 输入并验证
  parent、自由文本和 expansion 开关差异，不能用五个字段分组代替五个实验视图。
* 最终 ledger 的私有文件域必须按顺序绑定 01–06 与
  `07-execution-input.v1.json` 的精确原始字节、长度和 SHA-256。

## 公开文件路径与所有权（冻结）

本任务只可新增以下路径：

* `.trellis/tasks/08-04-r2-sealed-confirmation-cleanroom-2/**`；
* `tests/fixtures/fictional/fire_r2_sealed_confirmation_cleanroom_2/tree.v1.json`；
* `tests/fixtures/fictional/fire_r2_sealed_confirmation_cleanroom_2/manifest.v1.json`；
* `scripts/generate_fire_r2_sealed_confirmation_cleanroom_2.py`；
* `scripts/preflight_fire_r2_sealed_confirmation_cleanroom_2.py`；
* `tests/test_fire_r2_sealed_confirmation_data.py`。

禁止修改或新增其他路径。公开 manifest 不内嵌自引用 `data_commit`，只声明
`data_commit_binding=PRIVATE_FREEZE_LEDGER`。

## 测试纪律

唯一允许的 Python 测试命令是：

```bash
PYTHONPATH=src python3 -B -m unittest \
  tests.test_fire_r2_sealed_confirmation_data -v
```

另外只允许运行：

* `python3 scripts/preflight_fire_r2_sealed_confirmation_cleanroom_2.py ...`；
* `python3 ./.trellis/scripts/task.py validate <current-task>`；
* `git diff --check`；
* 非递归的 `py_compile`，且 cache 必须定向到 `/tmp`。

严禁 `unittest discover`、目录级测试目标、pytest 收集或任何可能加载其他测试模块的命令。

## Acceptance Criteria

* [x] 公开树节点数在 300–800，能通过 Adapter，且不含 VALUE envelope。
* [x] 公开 manifest 来源分类、功能基线、数量与禁止执行标志准确。
* [x] 私有候选精确为 36 条；冻结集精确为 28 条、24 有目标和 4 空目标。
* [x] 冻结主类别配额精确为 `6/6/4/4/4 + 4`。
* [x] 请求和 brief 先锁定，Silver 仅由请求正文生成，Oracle 后置映射。
* [x] 24 条有目标 Oracle 引用公开树稳定 ID；4 条空目标显式为空。
* [x] 4 条 hard negative 同时绑定正目标和显式排除目标。
* [x] 全部 36 条完成非 Gold 工程审核，冻结选择不使用模型/召回表现。
* [x] prepare preflight 只输出聚合计数，且明确 `DATA_COMMIT_REQUIRED`。
* [x] 单一数据专属测试、`task.py validate` 和 `git diff --check` 通过。
* [x] Git index 为空，未 stage、commit、push、merge，未生成最终 ledger/receipt。
* [x] `finalize` 原子且不可覆盖，失败不遗留最终目录或部分冻结状态。
* [x] `verify-frozen` 能从可信来源重算并拒绝 commit、字节、权限、字段、
  顺序、symlink、digest 和 sealed/opened 篡改。
* [x] 数据专属测试覆盖正常冻结原语、不可覆盖、篡改、错误 commit、
  symlink/公开权限、失败清理和 stdout 泄漏。
* [x] 执行配置精确拒绝任一字段、类型、值或数组顺序偏差，包括
  bool-as-int。
* [x] ledger 同时绑定执行配置语义与原始字节；仅重新格式化配置或改变
  任一已冻结公开文件后，`verify-frozen` 必须拒绝。
* [x] v3 私有根保留 01–06 精确字节，新增 28 条严格顺序的 execution-input
  sidecar，且 proposed/wrong parent 均存在并位于不同顶层分支。
* [x] 五视图可执行性 preflight 报告 28 条、5 视图和 140 单元，不调用
  模型、R1、R2、Semantic 或任何功能实验。
* [x] 最终 ledger 预备绑定 execution-input sidecar 的原始字节、长度和 SHA-256；
  新 `data_commit` 前不生成 `08-final-freeze.v1/`。

## Out of Scope

* 任何被测模型调用、网络请求、R1/R2/Semantic 或功能实验；
* 读取或运行既有数据/测试以做回归；
* 修改功能实现、Prompt、Provider、角色合同、runner 或通用测试；
* Gold、生产资格、Patch 资格、Shadow 晋升或实验结论；
* 在没有真实 `data_commit` 时伪造最终冻结。

## Technical Notes

* 新工作树：`/Users/lau/workspace/tree-flow-r2-sealed-cleanroom-2`。
* 新分支：`codex/build-r2-sealed-confirmation-data-cleanroom-2`。
* 本任务不得读取其他任务 research 或 JSONL；需求事实只来自本 PRD和本轮用户合同。
