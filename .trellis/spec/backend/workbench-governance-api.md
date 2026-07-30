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
```

sidecar 目录未配置时使用当前用户专属的操作系统临时目录；显式配置必须是绝对
路径。仿真模型 URL 继续受 `LoopbackSimulatorConfig` 门禁约束。百炼配置继续由
`BailianConfig.from_env()` 读取，浏览器不能提交 base URL、model 或 key。

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
model_mode                # SIMULATOR_LIVE | BAILIAN_LIVE
external_data_approved
```

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
不得把批准状态写入 URL、localStorage 或自动沿用到下一次需求。

模型交互诊断是独立的开发合同，不属于普通 case 视图或正式旁路工件。只有服务端
设置 `TREEGUARD_WORKBENCH_MODEL_DIAGNOSTICS=1` 时，`model-traces` 才返回
`workbench-model-trace-view.v1`：

```text
case_ref
model_mode               # SIMULATOR_LIVE | BAILIAN_LIVE
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

当前 Provider 明确发送 `enable_thinking=false`；因此只能显示
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
