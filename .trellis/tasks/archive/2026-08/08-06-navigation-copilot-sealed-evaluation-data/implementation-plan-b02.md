# Navigation Copilot 密封 clean-room 数据 v3-C b02 实施方案

## 0. 阶段与隔离声明

- 本文件只覆盖 b02 第一阶段规划，不授权复制数据、生成 b02 数据工件、激活任务或运行测试。
- 功能合同基线固定为 `88caf25d9be8ebb80f8c443115ebde1d69fc0447`。
- b02 分支固定为 `codex/build-navigation-copilot-sealed-data-v3c-b02`。
- b02 worktree 固定为 `/Users/lau/workspace/tree-flow-navigation-sealed-data-v3c-b02`。
- b01 状态固定标记为 `REJECTED_PRECOMMIT_EXECUTION_CONTRACT_MISMATCH`。b01 只可在获批的第二阶段作为下述逐文件、逐字段迁移源；不得提交、删除、覆盖、修复、继续冻结或写入。
- 第二阶段开始前仍须获得本方案的明确批准。

## 1. b02 固定标识与版本

以下值现在冻结；任一实现工件使用不同值即停线：

| 名称 | 冻结值 |
| --- | --- |
| `batch_ref` | `navigation-copilot-sealed-v3c-20260806-b02` |
| UUID namespace | `b6e2f54c-713a-4d18-a6f9-02b7c5e83d21` |
| seed | `NCV3C-CLEANROOM-20260806-SEED-02` |
| 稳定 ID 算法版本 | `treeguard.navigation-copilot-v3c-stable-id.v2` |
| catalog Schema | `treeguard.navigation-copilot-v3c-blueprint-catalog.v2` |
| 迁移蓝图文件 Schema | `treeguard.navigation-copilot-v3c-blueprint-file.v1` |
| 迁移账本 Schema | `treeguard.navigation-copilot-v3c-b02-migration-ledger.v1` |
| 候选目录 Schema | `treeguard.navigation-copilot-v3c-b02-candidates.v1` |
| Oracle authoring Schema | `treeguard.navigation-copilot-v3c-b02-oracle-authoring.v1` |
| 蓝图审核 Schema | `treeguard.navigation-copilot-v3c-b02-blueprint-review.v1` |
| 候选审核 Schema | `treeguard.navigation-copilot-v3c-b02-candidate-review.v1` |
| preflight Schema | `treeguard.navigation-copilot-v3c-b02-preflight.v1` |
| data manifest Schema | `treeguard.navigation-copilot-v3c-b02-data-manifest.v1` |
| Scenario 合同 Schema | `navigation-copilot-sealed-scenario.v2` |
| Oracle 合同 Schema | `navigation-copilot-sealed-oracle.v2` |
| 执行 manifest Schema | `navigation-copilot-sealed-evaluation-manifest.v2` |
| 阈值策略版本 | `treeguard.navigation-copilot-sealed-gate.v1` |

迁移的 9 个蓝图文件要求原字节不变，因此文件内的 `treeguard.navigation-copilot-v3c-blueprint-file.v1` 不升级；新建的 b02 catalog 负责记录 b02 批次及新 catalog Schema。

### 1.1 稳定节点 ID

节点 ID 仅承担身份分配，不生成任何树语义。算法固定为 RFC 4122 UUIDv5：

```text
uuid5(
  UUID("b6e2f54c-713a-4d18-a6f9-02b7c5e83d21"),
  UTF8(
    "algorithm=treeguard.navigation-copilot-v3c-stable-id.v2\n" +
    "batch_ref=navigation-copilot-sealed-v3c-20260806-b02\n" +
    "seed=NCV3C-CLEANROOM-20260806-SEED-02\n" +
    "blueprint_ref=" + blueprint_ref
  )
)
```

- 输入末尾没有换行，编码固定为 UTF-8，字段顺序固定如上。
- `blueprint_ref` 必须已逐节点显式存在于蓝图文件；生成器不得合成它。
- 名称、role、value type、cardinality、拓扑和描述均不得进入 ID 算法，也不得由 ID 反推出。
- b02 使用新 namespace，因此节点 ID 与 b01 不要求相同；迁移语义相等性由迁移账本的 payload 证明，不能用 ID 相等替代。

## 2. 目录与文件所有权

第二阶段仅允许新增或修改以下 b02 专属路径：

```text
scripts/navigation_copilot_v3c_b02/**
tests/test_navigation_copilot_v3c_b02_*.py
tests/fixtures/fictional/navigation_copilot_sealed_v3c_b02/**
.trellis/tasks/08-06-navigation-copilot-sealed-evaluation-data/**
```

预计 fixture 结构：

```text
tests/fixtures/fictional/navigation_copilot_sealed_v3c_b02/
  catalog.json
  migration-ledger.json
  blueprints/
    root.json
    branch-01.json
    branch-02.json
    branch-03.json
    branch-04.json
    branch-05.json
    branch-06.json
    branch-07.json
    branch-08.json
  authoring/
    candidates.json
    oracle.json
  reviews/
    blueprint-silver-review.json
    candidate-silver-review.json
  frozen/
    tree.json
    scenarios.json
    hidden-oracle.json
    silver-review.json
    preflight.json
    data-manifest.json
```

不得修改 `src/treeguard/**`、`contracts/**`、Provider、Prompt、runner、现有 fixture、现有脚本或非当前任务目录。若现有公开合同不足以直接完成 b02，立即停线，不以产品代码改动绕过。

## 3. b01 authoring source 逐文件允许列表

第二阶段只能从 b01 根目录 `/Users/lau/workspace/tree-flow-navigation-sealed-data-v3c` 读取本节列出的文件和字段。实现前建立迁移读取守卫：每次源文件打开都必须命中闭集路径；每条导入记录必须命中字段投影；否则失败。迁移行为只写 b02。

### 3.1 可原字节迁移的 9 个显式蓝图

以下文件逐个允许复制，要求源字节与 b02 目标字节 SHA-256 相同：

1. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/root.json`
2. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-01.json`
3. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-02.json`
4. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-03.json`
5. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-04.json`
6. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-05.json`
7. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-06.json`
8. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-07.json`
9. `tests/fixtures/fictional/navigation_copilot_sealed_v3c/blueprints/branch-08.json`

`root.json` 是唯一根节点语义来源。生成器不得默认创建、补齐或修复根节点。全目录必须恰有一个根节点；`parent_ref=null` 和 `parent_role=null` 只能同时出现在 `root.json` 的该节点，任何其他节点出现任一空父字段即失败。

迁移后重新校验全部逐节点字段和拓扑；生成器只能验证蓝图、按 1.1 分配稳定 ID、序列化。禁止循环生成语义、共享拓扑模板、列表轮换、模运算、字符串模板或默认值补造任何语义字段。

### 3.2 可重绑的 91 项蓝图审核内容

唯一允许源文件：

- `tests/fixtures/fictional/navigation_copilot_sealed_v3c/reviews/blueprint-silver-review.json`

只允许逐 `blueprint_ref` 迁移以下审核 payload：

- `status`
- `finding_codes`
- `parent_responsibility`
- `child_role_assessment`
- `boundary_assessment`

源批次、Schema、轮次、时间、路径、摘要 digest、权限信息及其他绑定元数据不得迁移。b02 对 91 条记录写入新的 Schema、batch 和来源证明。

语义 payload 不变证明固定为：

1. 按 `blueprint_ref` 对源和 b02 投影建立 91 项一一对应，禁止缺项、增项或重复；
2. 对上述五个字段按现有 canonical JSON 规则形成逐项 payload；
3. 逐项比较规范字节与 `canonical_digest`，两者均须相同；
4. 审核覆盖集合必须等于 b02 中全部符合条件的非叶蓝图集合；
5. b02 重新绑定字段不得进入语义 payload。

任一 payload 改动不属于“重绑”，必须停线并请求重新审核。

### 3.3 可迁移的 56 条候选预注册内容

唯一允许源文件：

- `tests/fixtures/fictional/navigation_copilot_sealed_v3c/candidates/candidate-catalog.json`

每条候选只允许迁移：

- request 原文；
- authoring category；
- category 内 ordinal；
- 已预注册的 `non_literal_subtype`；
- 已预注册的 `context_pressure` 标签；
- 已预注册的 repeatability/subset 标签。

b01 `scenario_ref`、执行类别值、page context、提示字段、`clarification_answer`、ID、digest、审核状态及未列字段均不得迁移。b02 的 56 个 `scenario_ref` 必须在 authoring 文件中逐项显式写出并保持唯一；生成器不得按字符串模板批量合成。

7 条 `CLARIFICATION` 的 `frozen_clarification_answer` 是 b02 新 authoring：必须逐条直接写在 `authoring/candidate-bindings.json`，并由同一记录的 b02 Silver `clarification_contrast` 结果和逐项 assessment 审核。迁移器只能从该 b02 文件读取答案；不得读取、比较、回退到或以任何方式依赖 b01 candidate 的 `clarification_answer`。来源隔离 canary 必须证明删除或篡改 b01 的该字段不会改变 b02 Scenario 字节。

authoring category 到公开执行 category 的映射固定为：

| authoring | execution |
| --- | --- |
| `LITERAL_UNIQUE` | `LITERAL_UNIQUE` |
| `NON_LITERAL_UNIQUE` | `NONLITERAL_UNIQUE` |
| `STRUCTURAL_DISTRACTOR` | `STRUCTURAL_INTERFERENCE` |
| `MULTIPLE_ACCEPTABLE` | `MULTI_ACCEPTABLE` |
| `CLARIFICATION` | `CLARIFICATION` |
| `WEAK_EVIDENCE` | `WEAK_EVIDENCE` |
| `NO_TARGET` | `TARGET_ABSENT` |

映射只在冻结边界做显式枚举校验，不允许复用 b01 的平行执行枚举或终态。

### 3.4 可迁移的非弱证据语义判断

唯一允许源文件：

- `tests/fixtures/fictional/navigation_copilot_sealed_v3c/oracle/hidden-oracle.json`

仅 51 条非 `WEAK_EVIDENCE` 候选可按 `scenario_ref`/预注册身份读取并迁移下列 authoring 语义判断：

- 目标存在/不存在判断；
- acceptable target 的 `blueprint_ref`；
- distractor/forbidden comparison 的 `blueprint_ref`；
- 目标与干扰项的显式结构画像；
- 澄清目标、比较对象、澄清策略和冻结澄清答案。

不得迁移 b01 节点 ID、`expected_route`、Policy status、terminal、错误码、评分、hash、digest 或任何执行结果。b02 节点 ID 只能从 b02 蓝图生成结果绑定。`TARGET_ABSENT` 冻结为公开 Oracle 时，`forbidden_node_ids` 必须为空；附近比较对象只能留在 authoring/review 证据中。

### 3.5 必须废弃的 5 条弱证据 Oracle

- b01 的 5 条 `WEAK_EVIDENCE` Oracle 除“该候选属于弱证据且必须排除旧 payload”的身份核对外，所有字段一律不可复用。
- b02 必须逐项重新写出一个隐藏目标 `blueprint_ref` 和至少两个相互竞争的候选 `blueprint_ref`，并重新完成 5/5 Silver 语义审核。
- 隐藏目标必须唯一；竞争项不得与目标重复，且必须由显式蓝图支持真实的结构竞争关系。
- 最终冻结的 4 条弱证据 Oracle 必须精确满足：
  - `expected_route = LIMIT`
  - `acceptable_policy_statuses = [NEED_EVIDENCE]`
  - 唯一 terminal 为 `TerminalExpectation(action=EXIT, target_node_id=null, target_disposition=PRESENT_NOT_FOUND)`
- 第 5 条保留项也必须完成新审核，但不进入冻结 48；不得用它替换上述合同语义。

### 3.6 不迁移、需在 b02 新写的审核

- b01 `reviews/candidate-silver-review.json` 不在允许列表中，不迁移。
- b02 对 56/56 候选重新形成逐项 Silver 审核记录；允许迁移的非弱证据判断仅作为输入证据，审核状态、意见、digest 和结论记录均为 b02 新工件。
- 5 条弱证据不得把 b01 判断作为输入证据。

## 4. 明确禁止迁移

以下内容为闭集拒绝项；迁移工具必须有负向路径与字段断言：

- b01 `tests/fixtures/fictional/navigation_copilot_sealed_v3c/frozen/**` 全部内容；
- b01 catalog、manifest、preflight、data-commit review、所有 digest、权限声明与权限检查结果；
- b01 的平行执行枚举、route、Policy status、terminal、错误终态及其映射；
- b01 脚本、生成器和测试；
- b01 candidate Silver 审核文件；
- b01 5 条弱证据 Oracle 的全部语义 payload；
- 任何模型请求/响应、Retrieval、Semantic、Policy、评分或产品链路结果；
- v1、v2、v3-A、v3-B 的工作树、数据、生成器、场景、Oracle、审核和逐项结论；
- 允许列表之外的任何 b01 文件或字段。

禁止项即使与预期值恰好相同也不能作为迁移来源。

## 5. 生成器职责与语义来源证明

### 5.1 唯一语义来源

- 树的全部语义来自 9 个逐节点显式蓝图文件；根节点只来自 `root.json`。
- 候选请求和预注册标签来自 56 条显式 authoring 记录。
- Oracle authoring 语义来自获准迁移的 51 条逐项判断及重新编写的 5 条弱证据判断。
- 生成器不得创建缺失语义、修正审核结论或选择目标/干扰项。

### 5.2 生成器允许操作

生成器只有四类权限：

1. 校验 Schema、引用、唯一性、父子闭包、root 约束和逐项审核覆盖；
2. 按 1.1 为已存在的 `blueprint_ref` 分配稳定节点 ID；
3. 将显式 authoring 引用绑定为 b02 节点 ID 或公开树引用；
4. 通过公开合同构造并确定性序列化。

AST/源码门禁和规避型负例必须拒绝：用于语义字段的循环填充、共享拓扑、列表轮换、模运算、字符串模板、隐式默认、复制上一项、按 ordinal 推导角色/类型/基数，以及先建立统一骨架再轮换字段。

## 6. 双签名门禁

每个符合审核条件的非叶蓝图生成两个只用于检查的签名；签名不替代逐项 Silver 审核。

### 6.1 语义签名

严格按 PRD 对节点递归构造 canonical JSON：

- 当前节点的 `kind`、`value_type`、`cardinality`；
- 每个直接子节点的显式 `parent_role`；
- 每个直接子节点递归得到的语义签名 payload；
- 子项按其 canonical bytes 排序后再进入父 payload，从而排除 sibling 顺序。

语义签名明确排除节点名称、label、semantic note、稳定 ID、`blueprint_ref` 和 sibling
顺序；不得加入“责任类别”“边界标签”或其他 PRD 未定义字段。最终签名只使用
`canonical_digest()` 计算该递归 payload。

### 6.2 骨架签名

严格按 PRD 对节点递归构造 canonical JSON：

- 当前节点的 `kind`；
- 当前节点的直接子节点数量；
- 每个直接子节点递归得到的骨架签名 payload；
- 子项按其 canonical bytes 排序后再进入父 payload，从而排除 sibling 顺序。

骨架签名明确排除 role、value type、cardinality、节点名称、label、semantic note、
稳定 ID、`blueprint_ref` 和 sibling 顺序；不得加入路径或深度编号等替代字段。最终
签名只使用 `canonical_digest()` 计算该递归 payload。测试必须证明修改 role、
value type 或 cardinality 不改变骨架签名，但会改变语义签名。

### 6.3 阈值与规避型负例

- 91/91 符合条件的非叶蓝图必须逐项审核，允许未审数量为 0。
- 对含至少 5 个后代的实例，语义签名最大重复组不得超过 3，重复实例比例不得超过 20%。
- 对同一合格集合，骨架签名最大重复组不得超过 4，重复实例比例不得超过 40%。
- preflight 必须分别报告两类签名的合格实例数、唯一数、最大重复组、重复实例数和比例。
- 对同一骨架组，若语义差异只来自 role、value type、cardinality 的规则轮换、ordinal 或模运算，立即失败，不因占比低而放行。
- 负例必须覆盖：统一骨架加字段轮换、跨文件共享拓扑、字符串模板改名、列表循环换 role、ordinal 模运算换 type/cardinality、骨架签名错误包含被排除字段、root 自动补造。

## 7. 8 条错误上下文绑定

- 56 条候选中必须显式预注册恰好 8 条 `context_pressure=true`，且每条在 b02 authoring 中逐项写出 `wrong_parent_blueprint_ref`。
- 这 8 个错误父节点必须存在于 9 个显式蓝图文件，且不得等于该项的可接受目标。
- 生成 b02 树后，先由蓝图绑定取得错误父节点的 canonical `node_id`，再只调用公开的 `build_tree_reference_index(tree)` 得到对应 `Nxxxxxx`。
- `SealedScenario.proposed_parent_ref` 必须使用该公开索引结果；禁止自建 DFS、计数器、公式、缓存映射或从 b01 迁移 `Nxxxxxx`。
- 冻结 48 中必须恰有 8 条 `wrong_context_challenge=true`，并与这 8 条显式绑定逐项一致；其余冻结项为 false 且 `proposed_parent_ref=null`。

## 8. 56 候选到 48 冻结与 Silver 流程

1. 先写出 56 条显式候选 authoring 记录；迁移字段受 3.3 限制，新字段逐项显式编写。
2. 先锁定 category、ordinal、预注册标签、错误上下文 8 项和 repeat subset，不允许根据后续审核结果重新排序来凑配额。
3. 完成 56/56 候选逐项 Silver 审核；蓝图审核必须覆盖全部 91 个符合条件的非叶节点。
4. 5 条弱证据从零重新审核；51 条非弱证据迁移 payload 完成逐项相等证明。
5. 按 `(authoring category 固定顺序, ordinal)` 做确定性选择；每类只取通过审核的最小 ordinal，冻结配额为：10/10/8/4/6/4/6。
6. 任一类通过数量不足即停线，不跨类替补、不改 ordinal、不降低审核门槛。
7. 冻结后校验 48 条、42 条 target present、8 条 wrong context、16 条 repeat；repeat 在 `NONLITERAL_UNIQUE`、`STRUCTURAL_INTERFERENCE`、`CLARIFICATION`、`WEAK_EVIDENCE` 各 4 条。
8. 所有确定性排序必须在审核前定义；Silver 结果只能决定通过/拒绝，不能改变预注册顺序。

## 9. 直接使用公开执行合同

### 9.1 Scenario

- Scenario authoring 是 Oracle 之前的独立冻结阶段。56 条候选的 `scenario_ref`、
  execution category、`requirement_text`、显式错误父蓝图绑定、`node_kind_hint`、
  `value_type_hint`、`cardinality_hint`、`frozen_clarification_answer`、
  `wrong_context_challenge` 和 `repeat_challenge` 必须先逐项显式写出并完成自身审核；
  不得从 Oracle 的目标、profile、route、Policy 或 terminal 反推、补齐或改写。
- 其中 7 条 `frozen_clarification_answer` 只来自 b02 `candidate-bindings.json` 的逐项
  显式字段；b01 candidate 中同名或近似字段属于禁止迁移字段，存在、缺失或篡改均不得
  影响 b02 authoring、审核、Scenario 或其 digest。
- 对 8 条错误上下文，Scenario 阶段只把已显式写出的错误父蓝图绑定经
  `build_tree_reference_index()` 投影为 `proposed_parent_ref`。该投影不授权读取
  Oracle；其余 Scenario 字段不得由蓝图目标或 Oracle 推导。
- 每个冻结项直接调用 `SealedScenario.create(...)`。
- `scenarios.json` 只保存 48 个 `to_dict()` 结果的 JSON 数组，不定义 b02 平行 Scenario Schema 或平行执行字段。
- 写出前后每项必须通过 `SealedScenario.from_dict()`，并与 create 结果相等；要求 48/48。
- 48 条 Scenario 的规范字节、`request_digest` 与 `scenario_hash` 全部锁定并回读
  成功后，才允许进入 Oracle authoring/冻结阶段。缺少任何 Scenario 字段时必须
  失败，禁止由后续 Oracle 默认补回。

### 9.2 Oracle

- Oracle 阶段只能消费已锁定的 Scenario 公共合同和独立、逐项审核的 Oracle
  authoring source；只允许按 `scenario_ref`、`tree_digest`、`request_digest`、
  category、澄清答案与错误上下文标志做一致性绑定。Oracle 不得修改或重新序列化
  Scenario 字段。
- 结构画像使用公开 `StructuralProfile`。
- 终态只使用公开 `TerminalExpectation`；不得建立 b02 terminal 枚举或字典替身。
- 每个冻结项直接调用 `SealedCaseOracle.create(...)`。
- `hidden-oracle.json` 只保存 48 个 `to_dict()` 结果的 JSON 数组，不定义平行 Oracle Schema。
- 写出前后每项必须通过 `SealedCaseOracle.from_dict()`，并与 create 结果相等；要求 48/48。
- `reviewed_bytes_digest` 必须由 b02 当次候选 authoring、Oracle authoring 和 b02 Silver 最终记录的规范化审核 payload 新算；不得迁移 b01 digest。

### 9.3 完整计划兼容性

- 以公开 `SealedEvaluationManifest` 所需的固定顺序组装 48 个 ref 和 16 个 repeat ref。
- 数据提交前没有真实 `data_commit`，因此不得序列化或发布伪执行 manifest。
- pre-commit 聚焦测试可在内存中用明确标记的 40 位占位提交值构造临时 manifest，仅用于调用 `validate_sealed_plan(manifest, scenarios, oracles)`；该对象不得落盘、进入 digest 或被称为可执行 manifest。
- 获得真实 data commit 后，单独在 fresh checkout 门禁中用公开 `SealedEvaluationManifest.create()/from_dict()` 生成和回读真实执行 manifest，再调用 `validate_sealed_plan()`；在此之前停在 data-commit 审阅门。

## 10. Git 可重放权限策略

- 仓库内所有受版本控制的 JSON、脚本和测试按 Git 可重放普通文件设计，预期 index mode 为 `100644`；正确性不得依赖 checkout 后的 OS `0600`。
- 仓库内不得写入“当前文件已是 0600”作为安全断言，也不得把本机权限位 digest 当作合同。
- 只有执行阶段、真实 data commit 获批后，才把获批字节物化到一个全新私有目录：目录创建为 `0700`，隐藏 Oracle、Silver sidecar 和执行 manifest 以独占创建方式写成 `0600`。
- 物化前验证目标不存在、父路径无符号链接；物化后从磁盘重读并比对原始字节 SHA-256。失败时不保留可误用的部分执行集。
- runner 所需 tree/scenario/oracle 原始文件 SHA-256 只按现有执行 manifest 合同计算；authoring 语义相等性使用项目 canonical digest，二者不得混用。

## 11. 聚焦测试与 fresh-checkout 重放计划

第二阶段只运行 b02 聚焦测试，不运行完整测试、模型或产品链路。白名单包括：

- 9 个蓝图源/目标逐文件字节一致、root 唯一性、非根父字段非空；
- 91 项审核 payload 逐项规范字节及 digest 一致；
- 56 条候选迁移字段投影与禁止字段 canary；
- b01 candidate `clarification_answer` 删除/篡改不改变 b02 Scenario 字节的来源隔离 canary；
- 51 条非弱语义投影一致，5 条弱证据旧 payload 零复用；
- 生成器源码/AST 语义生成禁令及规避型负例；
- 双签名排除字段、阈值、统一骨架字段轮换负例；
- 8/8 错误父蓝图绑定，并以 `build_tree_reference_index()` 校验 `Nxxxxxx`；
- 56 候选审核、确定性 48 冻结、配额和 16 条 repeat；
- `SealedScenario.create()/from_dict()` 48/48；
- Scenario 先行隔离 canary：Oracle 目标/profile/route/Policy/terminal 的任意变化
  不得改变 Scenario 规范字节；缺失 Scenario hint/answer/flag 时不得由 Oracle 补齐；
- `SealedCaseOracle.create()/from_dict()` 48/48；
- 4 条冻结弱证据精确 terminal 合同；
- `validate_sealed_plan()` 完整兼容及逐项篡改负例；
- 所有新增 tracked 文件 mode 可由 Git 重放，不依赖 `0600`。

获得真实 data commit 后、进入任何执行前，必须从该 commit 建立全新 detached checkout，运行只读重放门禁：

1. 验证 HEAD、tracked 文件列表、index mode 和原始字节 hash；
2. 不运行生成器，直接回读 48/48 Scenario、48/48 Oracle；
3. 回读真实执行 manifest 并运行完整 `validate_sealed_plan()`；
4. 在 checkout 外的全新私有目录测试 `0700`/`0600` 物化及原始字节 digest；
5. 任何本机未跟踪文件参与通过条件即失败。

## 12. 实施顺序与审阅门

明确批准第二阶段后才按以下顺序推进：

1. 激活当前 Trellis 任务并重新加载 `trellis-before-dev`；
2. 建立 b02 迁移读取守卫、Schema 和聚焦负例；
3. 只按允许列表迁移 9 个蓝图与允许字段，生成逐项迁移账本；
4. 新写 b02 catalog、候选补充字段、5 条弱证据 authoring 和全部候选 Silver 审核；
5. 校验 91 项蓝图审核、双签名、错误父绑定与 56 候选；
6. 生成 b02 树并经公开合同冻结 48 Scenario/48 Oracle；
7. 运行聚焦白名单测试和 pre-commit 内存兼容性检查；
8. 停在 data-commit 审阅门，不 stage、commit、push 或 merge。

真实 data commit、fresh-checkout 重放、私有物化和执行 manifest 属于后续单独批准步骤，不由本方案第一阶段或下一次数据构造批准自动授权。

## 13. 停线条件

出现任一情况立即停止，不自动修复或扩大范围：

- 当前分支、worktree 或 HEAD 偏离本文件固定值；
- 对 b01 发生任何写入、提交、删除、覆盖、权限修改或继续冻结；
- 读取或复制允许列表之外的 b01/v1/v2/v3-A/v3-B 文件或字段；
- 9 个蓝图任一字节变化，或生成器补造 root/其他语义；
- `parent_ref=null` 或 `parent_role=null` 出现在唯一根节点之外；
- 91 项审核集合或语义 payload 不能逐项证明相等；
- 56 条候选迁移超出字段投影，或 51 条非弱判断不能逐项证明相等；
- 5 条弱证据复用任一 b01 Oracle 语义字段，或不能形成单一隐藏目标加至少两个竞争项；
- 8 条错误上下文缺少显式错误父蓝图，或实现试图自建 `Nxxxxxx` 映射；
- 出现平行 Scenario、Oracle、Terminal、route、Policy 或执行枚举；
- 48/48 Scenario、48/48 Oracle round-trip 或 `validate_sealed_plan()` 任一失败；
- Git checkout 结果需要仓库文件保持 `0600` 才能通过；
- 需要修改产品核心、现有合同、Provider、Prompt 或 runner；
- 需要运行模型、Retrieval、Semantic、Policy、评分、产品链路或完整测试；
- 发现真实/受保护数据，或任何来源敏感性不明确；
- 任何人要求在 data-commit 审阅门前 stage、commit、push 或 merge。

## 14. 第一阶段完成定义

本文件落盘并通过文本格式/Trellis 任务校验、Git 状态复核后，第一阶段即停止。此时应满足：

- 只有当前任务目录新增本实施方案；
- 没有 b02 fixture、数据脚本、测试或冻结工件；
- b01 未被修改；
- 当前 Trellis 任务仍为 planning；
- Git 未 stage、commit、push 或 merge。
