# Workbench 治理 API

## Scenario：本地 Shadow 治理交互闭环

### 1. Scope / Trigger

修改 `workbench_governance.py`、`web.py` 的 `/api/v1/governance/*` 路由、
`GovernancePanel.tsx`、模型模式、operation 状态或 Web sidecar 时适用。

该场景允许在服务端调用既有意图与语义 Provider，并保存私有旁路工件；它不获得
生产信息树、MongoDB、Gold、语义批准或 Patch 发布权限。

### 2. Signatures

```text
POST /api/v1/governance/cases
GET  /api/v1/governance/cases/{case_ref}
GET  /api/v1/governance/cases/{case_ref}/model-traces
GET  /api/v1/governance/operations/{operation_ref}
POST /api/v1/governance/cases/{case_ref}/clarification
POST /api/v1/governance/cases/{case_ref}/intent-review
POST /api/v1/governance/cases/{case_ref}/recommendation-review
```

进程环境：

```text
TREEGUARD_WORKBENCH_SIDECAR_DIR
TREEGUARD_WORKBENCH_SIMULATOR_MODEL_URL
TREEGUARD_WORKBENCH_MODEL_DIAGNOSTICS   # 0 | 1；缺省为 0
TREEGUARD_QWEN_BASE_URL
TREEGUARD_QWEN_MODEL
```

sidecar 目录未配置时使用当前用户专属的操作系统临时目录；显式配置必须是绝对
路径。仿真模型 URL 继续受 `LoopbackSimulatorConfig` 门禁约束。百炼配置继续由
`BailianConfig.from_env()` 读取；内网 Qwen 使用无 API Key 的
`InternalQwenConfig.from_env()`。浏览器不能提交 base URL、model 或 key。

### 3. Contracts

创建 case 的浏览器请求只包含：

```text
resource_id
version
requirement_text
proposed_parent_ref?       # N000001 形式临时引用
node_kind_hint
value_type_hint?
cardinality_hint
model_mode                # SIMULATOR_LIVE | BAILIAN_LIVE | QWEN_LIVE
external_data_approved
```

三个引用均为 1–128 字符，匹配
`^[A-Za-z0-9][A-Za-z0-9._:-]*$`。注册表最多 32 个数据集；每个 manifest 最多
32 个变体、32 条限制；单个变体最多 128 个场景，且场景数量必须与 manifest
声明精确一致。

服务端必须重新读取 `resource_id + version` 的可信树，并使用与树视图相同的
`TreeReferenceIndex` 把临时父引用映射回内部节点。不得接受浏览器上传树、稳定
`node_id`、hash、Provider 配置或完整治理工件。

模型调用返回一次 operation：

```text
schema_version = workbench-operation-view.v1
operation_ref
case_ref
kind
status              # PENDING | RUNNING | SUCCEEDED | FAILED
error_code?
case_status
```

case 视图版本为 `workbench-governance-case-view.v1`，只包含运行状态、模型模式、
意图内容、前 8 个临时候选、建议内容和最终聚合记录。候选使用 `C001`—`C008`；
中文 `path_names` 只用于页面，`path_labels` 保留既有模型合同。禁止返回需求原文、
稳定节点 ID、hash、reviewer reasoning、模型 envelope、路径或 sidecar 位置。

正式工件按步骤写入全新 `0700` case 目录，每个 JSON 使用既有
`write_private_json()` 以 `0600` 不可覆盖发布。最终记录必须从可信请求、草稿、
人工动作、候选、快照和建议重新构造，并保持：

```text
record_semantics = OPERATIONAL_FEEDBACK_ONLY
semantic_approval = false
gold_eligible = false
patch_eligible = false
```

operation registry 当前是单进程内存实现。页面可把随机 `case_ref` 和
`operation_ref` 放入 localhost URL 以支持刷新；不得把树、需求、节点或模型内容
写入 URL、localStorage 或第三方服务。重复 GET 只读同一 operation，不得重新调用
模型。百炼出域批准只绑定当前 case；重新发起或切换树版本时必须清除浏览器勾选，
不得把批准状态写入 URL、localStorage 或自动沿用到下一次需求。`QWEN_LIVE`
属于受保护环境，不要求百炼出域批准，配置/调用失败也不得回退到其他 Provider。

模型交互诊断是独立的开发合同，不属于普通 case 视图或正式旁路工件。只有服务端
设置 `TREEGUARD_WORKBENCH_MODEL_DIAGNOSTICS=1` 时，`model-traces` 才返回
`workbench-model-trace-view.v1`：

```text
case_ref
model_mode               # SIMULATOR_LIVE | BAILIAN_LIVE | QWEN_LIVE
thinking_status = DISABLED
items[]:
  stage                   # INTENT_DRAFT | INTENT_CLARIFICATION |
                          # SEMANTIC_RECOMMENDATION
  attempt
  provider
  model
  prompt_version
  thinking_status = DISABLED
  request_messages[]      # role/content/content_truncated
  response_content?
  response_content_truncated
  validation_status       # PASSED | FAILED
  validation_error_code?
  usage?                  # prompt/completion/total token 计数
```

Provider 必须从实际 request body 投影 system/user 消息，并在本地合同校验后记录
每次 attempt。trace sink 是可选依赖；未提供时 Provider 行为不变。Trace 最多保存
当前 case 的 8 次尝试，单段文本最多 64,000 字符，只驻留
`WorkbenchGovernanceService` 当前进程内存。不得写入 sidecar、普通日志、URL、
localStorage 或下载文件。正向允许列表不得包含 API key、Authorization、headers、
base URL、完整响应 envelope、内部路径、稳定节点 ID、hash 或完整信息树。

百炼/仿真发送顶层 `enable_thinking=false`，内网 Qwen 发送
`chat_template_kwargs.enable_thinking=false`；因此只能显示
`thinking_status=DISABLED`。模型输出中的 `rationale`、`assumptions`、
`uncertainties` 和 `evidence_gaps` 是结构化结论，不得标成隐藏思考链。

### 4. Validation & Error Matrix

| 条件 | HTTP / operation 结果 |
|---|---|
| 请求缺字段、超长、枚举非法 | 422 / `WORKBENCH_REQUEST_INVALID` |
| 临时父引用不属于当前树 | 422 / `WORKBENCH_PARENT_REF_INVALID` |
| 百炼模式未显式批准 | 422 / `EXTERNAL_DATA_APPROVAL_REQUIRED`，无目录、无网络 |
| case 或 operation 不存在 | 404 / `WORKBENCH_*_NOT_FOUND` |
| 模型诊断未启用 | 404 / `WORKBENCH_DIAGNOSTICS_DISABLED` |
| 模型诊断环境值不是 `0`/`1` | 服务启动拒绝 / `WORKBENCH_DIAGNOSTICS_CONFIG_INVALID` |
| 人工动作与当前 case 状态不符 | 409 / `WORKBENCH_CASE_STATE_INVALID` |
| sidecar 不是绝对、安全私有目录 | 409 / `WORKBENCH_SIDECAR_DIRECTORY_UNSAFE` |
| 私有工件发布失败 | operation `FAILED` / `WORKBENCH_SIDECAR_WRITE_FAILED` |
| Provider/模型合同失败 | operation `FAILED` / 原固定 Provider 或合同 code |
| 一轮澄清后仍有问题 | case `CLARIFICATION_LIMIT_REACHED`，不进入检索 |
| Workbench API 服务重启 | 当前内存 case 不恢复；私有文件不自动删除或伪装恢复 |

错误响应与 operation 都不得包含异常 message、需求、节点、模型响应、路径、key
或 hash。

### 5. Good / Base / Bad Cases

- Good：完全虚构自然语言经仿真 Provider 形成意图，人工确认后 Top-8 出现中文
  候选路径，AI 建议复用 `C001`，人工接受后得到非 Gold 的可回放记录。
- Good：百炼模式只有显式批准后才在后台 operation 中调用，并继续经过相同本地
  输出合同。
- Good：Qwen 模式不发送 Authorization、不使用百炼批准状态，并继续经过相同本地
  输出合同。
- Base：用户不选择拟挂载节点，也不给类型和基数提示；以 `UNKNOWN` 完成意图整理。
- Base：AI 提出一个问题；用户可提交判断、思路或不确定原因，一轮后仍不明确则
  安全停止。
- Good：开发开关启用后，可查看失败 attempt 的原始 content 和固定合同错误码；
  正式 case JSON 与 sidecar 文件集合不发生变化。
- Base：开关缺省关闭，前端隐藏诊断区域，独立接口返回固定 404。
- Bad：FastAPI 通过 subprocess 调治理 CLI，浏览器持有完整 `to_dict()`，或把
  `NO_CANDIDATES` 解释成允许新增。
- Bad：刷新页面重新 POST create/review，或把 reviewer reasoning 放进 case GET。
- Bad：把模型 trace 加入正式 case GET、sidecar、访问日志或下载功能；展示
  `reasoning_content`，或在 `enable_thinking=false` 时推测模型思考。

### 6. Tests Required

- 同一 canonical tree 的浏览和治理使用相同 `N` 引用映射，未知引用拒绝；
- 仿真完整闭环发布预期 `0700/0600` 文件，最终记录可从可信来源重放；
- 一轮澄清的 resolved 和 limit-reached 两条路径；
- 百炼未批准时 Provider 调用数为零且 sidecar 根目录不存在；
- Qwen 模式无百炼批准也可创建 case，且工厂只选择 Qwen Provider；
- 重复 operation GET 不改变状态、不新增文件、不重复 Provider；
- case/API JSON canary 不含稳定 ID、hash、reasoning、路径和凭据；
- 诊断默认关闭；启用时按 attempt 返回实际消息、原始 content、固定校验结果和
  usage 允许列表，且不新增 sidecar 文件；
- Provider 重试 trace 包含失败与成功两次记录，禁止 key、base URL 和未知 usage；
- API 请求字段、固定错误、`no-store` 和 `nosniff`；
- 前端构建与聚焦测试；浏览器冒烟覆盖 2,001 节点、中文候选路径、人工完成状态和
  刷新恢复。

### 7. Wrong vs Correct

Wrong：

```python
subprocess.run(["treeguard-governance", "draft", ...])
```

这会把 CLI 文件协议、路径和 stdout 变成 Web 内部接口。

Correct：

```python
draft = provider.draft(request, tree)
confirmation = apply_intent_review(request, draft, action, tree)
candidate_set = build_candidate_set(confirmation, tree)
```

应用服务直接编排公共 Core/Provider API；FastAPI 只返回独立正向允许列表视图。

诊断场景中的 Wrong：

```python
case_view["model_trace"] = provider_response
write_private_json(case_dir / "model-trace.json", provider_response)
```

诊断场景中的 Correct：

```python
provider = factory.intent_provider(mode, runtime_trace_sink)
trace_view = governance.model_trace_view(case_ref)  # 仅显式开发开关
```

诊断使用独立的有界内存通道；正式 case 和可回放 sidecar 合同保持不变。

## Scenario：数据集驱动的虚构场景验证叠加层

### 1. Scope / Trigger

修改虚构验证数据 Provider、`workbench_validation.py`、`/api/v1/validation/*`、
场景预设或合同对照界面时适用。该叠加层只负责把服务端注册的可信 fixture 绑定到
既有治理 case，不建立第二套治理状态机，也不把 oracle 提升为专家 Gold。消防是
当前第一个注册数据集，不得成为通用服务、HTTP DTO、路由或前端流程的分支条件。

### 2. Signatures

```text
GET  /api/v1/validation/datasets
GET  /api/v1/validation/datasets/{dataset_ref}/scenarios?variant_ref=...
POST /api/v1/validation/runs
GET  /api/v1/validation/runs/{case_ref}/comparison
```

运行请求只包含：

```text
dataset_ref
variant_ref
scenario_ref
model_mode                # SIMULATOR_LIVE | BAILIAN_LIVE | QWEN_LIVE
external_data_approved
```

### 3. Contracts

- `ValidationDatasetProvider` 提供 manifest、变体和可信场景；通用服务只按注册表
  解析 `dataset_ref / variant_ref / scenario_ref`；
- 仿真仓库把 31、401、2,001 节点消防树暴露为当前 Provider 的三个只读资源；
- catalog 只返回数据集、变体、虚构资源选择器、节点/场景数量和非 Gold 限制；
- scenario 视图只返回需求、类型/基数提示、`Nxxxxxx` 临时父引用和可观察状态预期；
  禁止返回稳定节点 ID、冻结模型输出、要求命中的内部候选 ID；
- 创建运行时，服务端必须按三个引用重新读取已注册 Provider，不信任浏览器回传的
  需求、父节点或 oracle；
- 新增虚构领域时只增加 Provider/fixture 与注册项，不修改通用验证服务、HTTP
  合同、路由或前端流程组件；
- `case_ref` 到场景的绑定只存在当前进程内存；比较接口读取既有治理 case，只比较
  意图、候选、人工记录和三个安全标志等可观察合同状态；
- 比较结果必须固定为 `fictional=true`、`gold_eligible=false`，并明确说明不比较
  模型文本、语义结论、冻结模型输出、完整候选召回率或专家 Gold；
- `SIMULATOR_LIVE` 只验证 OpenAI 格式和治理合同。仿真器可从显式 clean-room
  需求与 hints 形成确定性草稿，但不得把 fixture 中的冻结模型输出伪装成当前
  模型推理结果。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| HTTP 引用/模型枚举或字段格式非法 | 422 / `WORKBENCH_REQUEST_INVALID` |
| 未注册 dataset_ref | 404 / `VALIDATION_DATASET_NOT_FOUND` |
| 未知 variant_ref | 404 / `VALIDATION_VARIANT_NOT_FOUND` |
| 未知 scenario_ref | 404 / `VALIDATION_SCENARIO_NOT_FOUND` |
| Provider manifest/场景数量不一致 | 422 / `VALIDATION_DATASET_CONTRACT_INVALID` |
| 场景父节点不在绑定树 | 422 / `VALIDATION_SCENARIO_SOURCE_INVALID` |
| 应用服务收到非允许模型模式 | `VALIDATION_MODEL_MODE_INVALID` |
| 百炼未显式批准 | 422 / `EXTERNAL_DATA_APPROVAL_REQUIRED`，无树读取、无 case |
| 治理服务未返回 case_ref | 422 / `VALIDATION_OPERATION_INVALID` |
| case_ref 没有当前进程绑定 | 404 / `VALIDATION_RUN_NOT_FOUND` |
| 绑定树不可读取或不合法 | 既有 `WORKBENCH_TREE_NOT_AVAILABLE` |
| case 失败或状态不符 | 比较为 `RUN_FAILED` 或 `MISMATCH`，不得写完成假象 |

### 5. Good / Base / Bad Cases

- Good：选择消防数据集的 small/clear-intent 后，页面自动切换 31 节点树，以
  只读预设进入既有意图、候选、建议和人工复核闭环，最终显示非 Gold 合同匹配。
- Good：注册第二个非消防 Provider 后，同一 catalog、场景、运行和对照服务直接
  工作，不增加领域路由或治理分支。
- Good：百炼模式只有当前虚构运行得到显式批准后才调用真实 Provider。
- Base：本地仿真显示“仅合同通路”，即使状态匹配也不声明语义正确。
- Bad：浏览器上传完整树、稳定节点 ID、冻结输出或 oracle，服务端直接信任。
- Bad：为每个领域复制一套 Service、DTO、路由或前端流程。
- Bad：本地仿真固定选择 `C001` 后，将“符合合同预期”展示成领域语义准确。

### 6. Tests Required

- 三档资源通过同一仓库客户端读取，节点数与版本身份精确匹配；
- 第二个非消防测试 Provider 通过注册复用同一目录、场景和运行服务；
- catalog/scenario JSON canary 不含 `ffv-`、冻结输出、内部候选 ID 或稳定节点 ID；
- 百炼批准门禁发生在树读取、sidecar 创建和 Provider 调用之前；
- small 场景通过真实 Governance Service 完成，最终三个安全标志均为 false；
- comparison 覆盖运行中、匹配、失败和未知绑定，并保持 `no-store`、`nosniff`；
- 本地仿真只回显显式 clean-room 需求与 hints，不串入其他领域示例；
- 通用服务、HTTP 路由/DTO 和前端流程模块不得包含消防分支；
- 前端聚焦测试、构建和浏览器冒烟覆盖可信预设、仿真限制、中文消防树和人工完成。

### 7. Wrong vs Correct

Wrong：

```python
governance.create_case(**browser_request["scenario"])
```

这会让浏览器修改基准需求、父节点或预期。

Correct：

```python
operation = validation.create_run(
    dataset_ref=dataset_ref,
    variant_ref=variant_ref,
    scenario_ref=scenario_ref,
    model_mode=model_mode,
    external_data_approved=external_data_approved,
)
```

浏览器只提交引用；服务端从已注册的可信 Provider 重建输入，并把运行交给既有
治理服务。
