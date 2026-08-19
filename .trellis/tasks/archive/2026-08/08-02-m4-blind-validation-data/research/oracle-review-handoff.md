# 隐藏 Oracle、人工审核与第二阶段交接

## 设计状态

下列名称是概念字段，不是新运行时 Schema。第二阶段必须先同步用户提供的冻结功能
合同，再把概念一一映射到精确字段集；不一致时修改本数据设计或停止，不得在数据
分支发明兼容字段。

已同步冻结提交：
`d7dff7994167d606aa2e3269c7606860bf22fc41`。精确运行时版本为：

- overlay：`scenario-capability-overlay.v1`；
- run：`scenario-capability-run.v1`；
- public report：`scenario-capability-report.v1`。

数据分支仍只拥有 wrapper、manifest、fixture SHA 和数据 preflight，不修改上述
合同或 `src/treeguard/scenario_capability_validation.py`。

## Oracle 概念字段及语义

### Envelope 与永久边界

| 概念字段 | 语义 |
|---|---|
| `oracle_schema_version` | 数据 wrapper 固定为 `fire-m4-blind-oracle-sidecar.v1`；单项 overlay 仍使用冻结运行时 v1 |
| `scenario_ref` | 数据集内稳定、非语义性的身份；不等于 case/candidate ref |
| `source_class` | 固定 `CLEANROOM_SYNTHETIC` |
| `fictional` | 固定 `true` |
| `derived_from_real` | 固定 `false` |
| `gold_eligible` | 固定 `false` |
| `patch_eligible` | 固定 `false` |
| `benchmark_role` | M4 blind capability validation，不代表生产指标 |
| `preparation_candidate_digest` | 绑定准备 Agent 的候选最终字节，不保存 Prompt/响应 |

### 来源与合同绑定

| 概念字段 | 语义 |
|---|---|
| `base_dataset_ref` | 固定引用中型虚构 holdout |
| `variant_ref` / `resource_id` / `tree_version` | 绑定公开资源选择器 |
| `tree_snapshot_digest` | 权威 canonical tree digest；树变化使 Oracle 失效 |
| `tree_fixture_sha256` | 可选 fixture 字节绑定；与 canonical digest 不混用 |
| `scenario_plan_hash` | 绑定 fire medium 的 11 单元确定性计划 |
| `plan_unit_ref` | 绑定一个既有计划单元；不能创建计划外候选 |
| `feature_contract_commit` | 用户提供并已同步的冻结功能合同提交 |
| `intent_contract_version` | 意图输入/输出及澄清路径版本 |
| `retrieval_contract_version` | 召回状态、排序、K 和稳定身份映射版本 |
| `recommendation_contract_version` | 动作、目标、关系和空值版本 |
| `comparison_contract_version` | 结果状态、适用性和记账版本 |

合同提交与版本必须同时绑定。任一不匹配都属于零容忍合同失败。

### 意图 Oracle

| 概念字段 | 语义 |
|---|---|
| `expected_route` | `PROCEED` 或 `CLARIFY`；精确枚举由冻结合同映射 |
| `clarification_applicability` | `REQUIRED`、`NOT_REQUIRED` 或格级 `NOT_APPLICABLE` |
| `acceptable_intent_profiles` | 一到多个同等正确的规范化意图 profile |
| `intent_field_policy` | 每个字段采用精确值、可接受集合、必需非空或不比较 |
| `clarification_requirement` | REQUIRED 时必须解决的歧义类别；正文保持隐藏 |

profile 至少能表达主体/角色/场景/生命周期、所有权、节点类型、值类型、基数和
证据缺口的适用子集；最终字段完全服从功能合同。模型 rationale 或人工自由文本
不作为比较 Oracle。

### 召回 Oracle

| 概念字段 | 语义 |
|---|---|
| `retrieval_applicable` | 澄清短路时 false；完整链路 true |
| `acceptable_retrieval_target_node_ids` | 内部可接受稳定虚构 node ID 集合 |
| `top_k` | 冻结合同的 K；不得运行后调参 |
| `retrieval_match_rule` | 默认“至少一个可接受目标在前 K”，精确规则待确认 |
| `acceptable_retrieval_statuses` | 允许的召回阶段状态集合 |

当次运行的 `C001` 等编号只能由比较器映射成稳定 node ID 后使用。Oracle 不保存
临时 ref、固定 rank 或某次 candidate-set hash 作为长期目标身份。

### 推荐 Oracle

| 概念字段 | 语义 |
|---|---|
| `recommendation_applicable` | 澄清短路时 false；完整链路 true |
| `acceptable_actions` | 一组人工认可动作，避免单值过拟合 |
| `target_policy` | `ANY_ACCEPTABLE_TARGET` 或 `MUST_BE_NULL` |
| `acceptable_recommendation_target_node_ids` | target 非空时的稳定 node ID 集合 |
| `acceptable_relations_by_target` | 每个稳定目标对应的合法关系集合 |
| `acceptable_no_target_relations` | target 为空时的合法非选择/证据类别（若合同支持） |

动作、目标和关系作为联合约束判断，不能分别命中后拼成未获人工接受的组合。
澄清短路必须明确后两阶段不适用，而不是把空数组误记成失败。

### 人工审核与执行资格

| 概念字段 | 语义 |
|---|---|
| `review_status` | `PENDING`、`ACCEPTED`、`REVISED_ACCEPTED` 或 `REJECTED` |
| `reviewed_artifact_digest` | 绑定被审最终字节；修改即失效 |
| `rubric_version` | 绑定审核规则版本 |
| `finding_codes` | 仅允许列表 code，不保存身份或长篇自由文本 |
| `review_round` | 有界 revise/recheck 轮次 |
| `execution_eligible` | 仅 accepted 且全部绑定有效时 true |

审核者真实身份、原始意见、模型输出和隐藏正文不进入公开报告。

## 人工审核 rubric

每条候选按顺序审核：

1. **数据边界**：五个固定值正确，无真实/M3 派生、Prompt、响应、专家文本、
   内部标识或受保护内容。
2. **来源绑定**：树、fixture、合同提交和版本 digest 全部匹配。
3. **独立性**：只由 fire medium、对应 plan unit 和覆盖格支持，不读取或重放 M3
   候选/答案、现有 fire scenarios 或旧场景换词。
4. **可答性**：主体、范围、类型/基数和关键证据没有隐性冲突。
5. **覆盖价值**：填补声明格且主风险唯一，无无理由组合或重复模板。
6. **意图正确性**：可接受 profile 完整；澄清只有树证据支持时成立。
7. **召回正确性**：可接受目标完整且有独立树证据，Top-K 可执行。
8. **推荐正确性**：动作、目标/空值和关系的联合组合有树证据。
9. **隐藏性**：公开 request/report 不泄漏稳定目标、Oracle 值或可逆提示。
10. **确定性**：重建、排序、digest 和抽样 seed 固定。

结论：

- `ACCEPTED`：无需语义或绑定修改，可冻结当前字节。
- `REVISED_ACCEPTED`：revise 后对新字节重跑全部适用门禁并接受。
- `REJECTED`：存在不可在预算内修复的边界、可答性、覆盖或 Oracle 缺陷。
- `PENDING`：未完成审核；绝不进入执行分母。

## 停线规则

整批立即停止，不继续全量人工清洗，若发生任一项：

- 1 个数据边界、来源分类、M3 派生或 Oracle 泄漏错误；
- 1 个树 digest、fixture SHA、合同提交/版本或稳定目标绑定失败；
- 功能合同要求数据分支修改功能分支已拥有的同一文件；
- 固定 seed 随机复核 3 条中至少 2 个实质语义错误；
- 同一实质错误跨 2 个覆盖格/聚类重复；
- 人工总时长超过 150 分钟；
- 任一候选超过 2 轮 revise，或整批超过 3 轮修复/重审；
- 冻结后受审字节变化，或基础树/Schema/K/比较语义漂移；
- 存在未解决 blocking finding 仍被要求执行或晋升。

合法歧义不存在不属于停线：B08 记录 `NOT_APPLICABLE` 并回填完整链路。

## 预算与分母

- 人工首审固定覆盖 planner 的 11 个计划单元；冻结执行集最多 8 条。
- 所有高风险候选复核；按 seed `20260802` 随机复核最多 3 条已接受候选。
- 当前 `dual_review_limit=0`；未经更新 Charter 和批准不得增加。
- 候选准备质量可聚合所有已完成审核候选；产品执行分母只含绑定有效的
  ACCEPTED/REVISED_ACCEPTED 场景。
- “至少 6 条完整符合”和各阶段最多 1 条 MISMATCH/RUN_FAILED 由功能分支计算；
  数据分支只保证 Oracle 足以支持判断。

## 第二阶段预期文件

先写入已忽略 staging，批准 promotion 前不进入正式 fixture：

```text
artifacts/fictional-validation/fire-m4-blind-v1/
├── manifest.json
├── scenario-candidates.json
├── oracle-review-packet.json
├── preflight-report.json
├── human-review.json
├── critic-report.json
├── retrieval-preview-report.json
└── promotion-checklist.json
```

上述候选 staging 工件保持原始待审字节不变；人工审核完成后另生成不可覆盖的
`human-review-frozen.json`、`promotion-checklist-frozen.json` 和
`oracle-sidecar.json`。待审 wrapper 没有被改写成运行时 overlay；正式 sidecar
逐项保存可信 action、reviewed record，并只为 8 个执行项保存独立 M4 overlay。

数据分支已新增下列受版本控制文件；当前仅物化，仍未 stage：

```text
tests/fixtures/fictional/fire_validation_m4_blind/
├── manifest.json
└── oracle-sidecar.json
scripts/preflight_fire_m4_blind_validation_data.py
tests/test_fire_m4_blind_validation_data.py
```

本次没有修改现有 fire manifest、tree-medium、scenarios-medium、Provider 或生成器。
新 manifest 只引用基础
dataset/resource/version/digest。若冻结合同要求共享索引或 manifest，先核对功能
分支所有权；有重叠就停止。

计划测试：

- 五个数据边界固定值和未知字段 fail closed；
- 基础资源、canonical digest 和 fixture SHA 精确绑定；
- 场景数 `<=8`，只有 accepted/revised-accepted 可执行；
- 澄清短路与 B08 `NOT_APPLICABLE`/B08F 回填互斥；
- 完整链路具备意图、召回、Top-K、推荐动作、目标/空值和关系 Oracle；
- 稳定 node ID 存在、每个目标有独立树证据、无持久化临时候选 ref；
- plan hash 精确绑定，候选只来自 11 个 plan units，拒绝计划外 ref；
- 动作/目标/关系联合有效，MUST_BE_NULL 不携带目标；
- 固定 seed、规范排序、逐字节重建和 digest 篡改拒绝；
- 公开聚合不含请求正文、目标 ID、Oracle、Prompt、响应或人工意见 canary；
- rejected/pending 不进入执行分母，fixture 变更使审核失效。

这些测试只验证数据工件；运行时比较和 GO_SHADOW 判定测试属于功能分支。

## 冻结合同映射结果

提交 `d7dff7994167d606aa2e3269c7606860bf22fc41` 已提供并冻结：

1. 场景准备候选的精确字段、版本、digest 域和人工审核输入边界；
2. 意图正常/澄清路径的状态枚举、规范化字段和比较策略；
3. 召回状态、稳定 node ID 映射、Top-K 值和命中规则；
4. 推荐动作、target null、关系类别和合法联合约束；
5. Oracle sidecar 精确 Schema、版本、序列化、来源绑定和重放验证；
6. MATCH/MISMATCH/RUN_FAILED/NOT_APPLICABLE 的适用性、分母和记账合同；
7. 数据集/Provider 或执行入口如何读取 sidecar，但不要求数据分支改运行时；
8. 功能分支拥有的完整文件列表、所需数据路径和验收命令。

上述字段已分别映射到现有 M3 action/review record、M4 单 overlay、候选 batch 和
数据自有 manifest/wrapper；数据分支没有新增或放宽运行时 Schema。正式 preflight
从 fire medium 重建 tree/profile/11-unit plan 和 batch，再逐项重放 11 份审核记录
与 8 份 overlay。

## 人工冻结与晋升记录

- 用户在辅助审核基础上完成 11 项审核，记录耗时约 20 分钟；11 项全部
  `ACCEPTED`，无 revise/reject、无 blocking finding、无双审声明。
- 正式执行项为 8 个：7 个 `PROCEED`、1 个 `CLARIFY`；另外 3 个接受项的
  `execution_eligible=false` 且 overlay 为空。
- 最终 sidecar 绑定候选 batch 字节 SHA、待审 packet 字节 SHA、tree fixture
  SHA、canonical tree digest、11-unit plan hash、合同提交和精确合同版本。
- 晋升只写入全新 `fire_validation_m4_blind` 目录、独立 preflight 和独立测试；
  没有共享文件冲突，且未 stage、commit、push 或 merge。

## 最小研究记录

日期：2026-08-02。只检查指定外网仓库的公开合同与完全虚构元数据；未使用 Web、
MCP、外部模型或网络服务。

仓库依据：

- `.agents/skills/build-treeguard-test-datasets/SKILL.md` 及 pipeline contract；
- 数据边界与质量规范；
- fire validation manifest 与 `tree-medium.json`；未读取 scenarios 正文；
- `change_intent.py`、`retrieval.py`、`semantic_recommendation.py` 的公开形状；
- `fire_validation_dataset.py` 与现有确定性 scenario planner 的公开合同。

未读取 M3 overlay 正文、M3 候选正文、Prompt、模型请求/响应、人工语义答案或
实验输出作为数据来源；只读取三份实验记录的聚合来源段落。第一阶段也未读取
fire scenarios 正文，未生成新的盲测场景正文。

第二阶段只消费冻结合同、原始机器验证 staging 字节、用户审核决定和 fire medium
树；未调用外部 LLM、Web、MCP 或其他网络服务，也未读取现有 fire scenarios
正文作为 Oracle 来源。
