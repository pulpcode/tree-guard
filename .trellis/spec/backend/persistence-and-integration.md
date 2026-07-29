# 持久化与集成边界

## 当前实现

TreeGuard 当前没有数据库代码、ORM、migration、transaction 或
Spring Boot/MongoDB 连接器。除既有 CLI/file 边界外，已实现一个只监听 loopback
的只读 FastAPI Workbench API。已实现的持久化模型只有：

- 输入树导出和已解码 API response envelope；
- 可选的私有 AI review bundle；
- 不可变 expert action/session/approval JSON；
- 不可变 intent request/draft/action/confirmation/candidate JSON；
- 不可变 intent clarification answer/round JSON；
- 不可变 semantic recommendation draft/review action/record JSON；
- 一键虚构演示的全新 `0700` 运行目录、`0600` 中间工件和完成标志；
- 从冻结源工件做确定性回放。

已实现的网络路径包括显式启用的百炼 `POST /chat/completions`、只监听 loopback
的暂定开发仿真服务/客户端，以及读取该客户端的 loopback Workbench API。后两者
都不是生产入站 API、生产 repository 或真实内网合同。MongoDB、搜索、Overlay
和 Patch 发布的设计文档不能被写成已存在层的代码规范。

## 永久职责边界

确定性领域模块只处理内存中的规范对象：

- `diff.py`
- `history.py`
- `business_review.py`
- `evidence.py`
- `expert_review.py`
- `change_intent.py`
- `retrieval.py`
- `semantic_recommendation.py`

它们不得读取环境变量、打开文件、调用 HTTP 或获取数据库凭据。副作用只能在
Adapter、Provider 或 CLI 边界发生。

`adapter.py` 负责源树格式转换。未来 API client 可以 fetch payload，但应把已
解码 response 交给 `adapt_tree_document()`，不能让领域模块理解内部 DTO/
envelope。

## 两种现有输入 profile

### 普通树导入

`adapter.load_tree_export()` 读取 UTF-8 并用普通 `json.loads()`。默认支持纯
JSON，只有显式 opt-in 才支持 curl transcript；适配时限制 tree/node/depth，
但当前不校验 owner、`0600`、byte size、no-follow 或重复 key。

### 私有专家工作流

`private_io.read_private_json()` 是敏感文件边界：

- 在支持的平台使用 no-follow/non-blocking flag；
- 只接受普通文件；
- 拒绝 group/other permission bit；
- 按工件限制 byte；
- 使用 `strict_json_loads()`。

expert workflow 的树输入使用更强 profile。该函数当前不校验 owner UID，不得
写成已校验。

新增处理 expert text、模型工件、approval、session 或其他敏感材料的命令时，
必须复用强 profile 或提取公共等价实现，不得静默改用 `Path.read_text()`。

## 私有输出发布

敏感输出通过 `private_io.write_private_json()`：

1. 接触最终路径前完整序列化 JSON；
2. 以 `O_CREAT | O_EXCL`、no-follow（如支持）和 `0600` 创建随机同级临时文件；
3. 完成 write loop 并 `fsync()`；
4. 通过 hard link 发布，绝不覆盖已有最终目标；
5. 成功或失败都清理临时文件。

每次状态迁移写新的完整 session 文件，不原地更新 bundle/session；外部调用或
写入失败不能留下部分发布工件。

`treeguard-governance-demo` 只接受尚不存在的最终运行目录，并以 `0700` 创建。
目录中的每个 JSON 仍通过 `write_private_json()` 以 `0600` 不可覆盖发布；只有
六个正式步骤全部成功并完成回放后才写 `12-demo-completion.json`。live 意图需要
澄清时，在私有发布草稿后安全停止，不生成自动确认或完成标志。失败可能保留私有的
已完成前序工件，但不能写完成标志。

`private_io.preflight_private_output()` 用于在 live 模型调用前确认目标尚不存在且
目录可创建私有文件。最终发布仍必须调用 `write_private_json()`，不能把 preflight
当作原子保留。所有 CLI 复用这些公共 API，不得再复制或跨模块导入私有 writer。

## 本地配置

`BailianConfig.from_env()` 先读取 process environment，再读取 cwd 中私有
`.env`，设置项采用显式允许列表：

- 真实 `.env` 保持 Git ignore，并必须是当前用户拥有、无 group/other 权限的
  普通文件；
- 最大 16 KiB，解析时不修改 `os.environ`；
- 拒绝重复/未知 key 和控制字符；
- API key 不出现在 dataclass repr；
- `.env.example` 只含名称/默认值，不含 key。

生产部署使用托管 secret 或受控 process environment，不分发 `.env`。

## 外部网络

Provider transport 必须显式启用并 fail-closed：

- 仅批准的官方 HTTPS host 和精确 compatible-mode base path；
- 禁止 URL credential、自定义 port、query、fragment、redirect 和继承 proxy；
- response 大小有界，并严格解析 JSON；
- authorization token 只在 header；
- 最多两次顺序尝试；
- 读取/发送选定文件前取得明确数据批准；
- expert text 还必须绑定精确批准的 request-plan manifest。

模型投影不等于外传权限。去掉内部 ID 和 `VALUE` 后，真实字段名、路径和结构
仍可能敏感；必须遵守开发数据边界。

## Scenario：协议级 Clean-room 仿真

### 1. Scope / Trigger

真实内网 Qwen 与四类仓库接口样例尚未到达时，开发只能使用完全虚构数据和明确标记
的暂定合同。该场景用于协议编排、确定性回归和故障注入，不能用于声明生产兼容性或
模型效果。

### 2. Signatures

- `treeguard-contract-simulator serve --port PORT --node-count N
  --model-scenario SCENARIO [--delay-seconds SECONDS]`
- `treeguard-contract-simulator verify-repository --base-url
  http://127.0.0.1:PORT`
- `treeguard-governance {draft|clarify|recommend} ... --simulator-base-url
  http://127.0.0.1:PORT/v1`
- `treeguard-governance-demo ... --mode simulator-live
  --simulator-base-url http://127.0.0.1:PORT/v1`

`--model-output-file`、`--live` 与 `--simulator-base-url` 互斥。
`bailian-live` 继续调用真实百炼并要求 `--external-data-approved`；
`simulator-live` 只允许 loopback，不要求外部出域批准。

### 3. Contracts

- 仿真仓库响应必须携带
  `contract_status=PROVISIONAL_SIMULATOR_CONTRACT`；
- 四类只读能力是分类平铺列表、分类资源 HEAD、显式最旧到最新业务版本列表、
  `version` 或 `version_record_id` 二选一的全树；
- `ContractSimulator.handle()` 是确定性唯一事实来源，HTTP Server 只负责有界
  协议转换；
- `ProvisionalRepositoryClient` 严格验证信封、字段集、顺序、HEAD、版本身份，
  再把全树交给 `adapt_tree_document()`；
- `LoopbackSimulatorConfig` 只接受 `http://127.0.0.1|localhost:PORT/v1`，
  禁止 URL credential、query、fragment、redirect 和继承 proxy；
- 仿真模型与百炼共享意图/语义输出合同，但 Provider 名称、地址门禁和错误码分离；
- 百炼真实响应只进入私有 sidecar，不得成为 fixture、Git 工件或确定性断言。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 非 loopback 仿真 URL、无显式端口或路径不是 `/v1` | `SIMULATOR_MODEL_BASE_URL_INVALID` |
| 仓库客户端目标不是显式 loopback HTTP 端口 | `REPOSITORY_SIMULATOR_BASE_URL_INVALID` |
| 仿真请求缺少固定 Bearer token | HTTP 401 / `SIMULATOR_AUTH_REQUIRED` |
| 未知路径、方法或查询字段 | 固定 4xx 与 `SIMULATOR_*` 错误码 |
| 模型非法 JSON、额外字段、429/500、延迟 | Provider 或本地输出合同失败关闭 |
| 仓库响应字段、顺序、HEAD 或身份不一致 | `RepositoryClientError`，不返回部分结果 |
| `bailian-live` 缺少出域批准 | 网络和私有输出前 exit 2 |

### 5. Good/Base/Bad Cases

- Good：2,001 节点虚构树经四类接口读取，两个版本均通过 Adapter，模型源可在
  `simulator-live` 与 `bailian-live` 间显式切换。
- Base：`offline` 使用冻结模型输出文件，不启动服务、不发网络请求。
- Bad：把仿真字段写成真实内网 API 事实，或因 Mock 通过就宣称 Qwen/百炼语义准确。

### 6. Tests Required

- 生成器：同配置字节稳定，2,000+ 节点可适配，跨版本 `node_id` 稳定且快照变化；
- 纯路由：认证、路径、查询、方法和所有模型故障场景；
- 客户端：四步读取、显式顺序、HEAD、selector、版本和树身份；
- 双模型源 CLI：`simulator-live` 真实进入两段 Provider，本地输出仍非 Gold/
  非 Patch；`bailian-live` 的既有批准门禁继续通过回归；
- 自动化测试使用进程内纯路由，不打开 socket、不使用凭据、不访问真实网络。
  真实 loopback HTTP 只作为获准的本地冒烟步骤。

### 7. Wrong vs Correct

Wrong：

```python
BailianConfig(api_key=token, base_url="http://127.0.0.1:8765/v1")
```

这会混淆外部百炼允许列表与本地 Mock 身份。

Correct：

```python
LoopbackSimulatorConfig(
    api_key=SIMULATOR_BEARER_TOKEN,
    base_url="http://127.0.0.1:8765/v1",
)
```

真实内网样例到达后新增薄 Adapter/Provider 配置，不删除暂定标记，也不让生产系统
适配 Mock。

## Shadow MVP 旁路规则

首期产品集成采用：

```text
批准的只读版本快照
→ 确定性分析与有界 AI 建议
→ sidecar/overlay 审查工件
→ 人工裁决
```

- 不修改生产 MongoDB、生产信息树或业务版本；
- 不自动发布 Patch；
- 失败不能影响生产业务状态；
- sidecar 必须版本化、来源绑定并可回放；
- 外网测试只使用 Mock/file transport 和完全虚构数据。

“只读/无生产写入”是 Shadow MVP 风险控制。最小可行性验证后，只有在产品指标、
审计与回滚方案证明可接受时，才能通过新任务审议是否放开；它不是默认为永久
禁止写入的产品结论。

## 未来内部系统 Adapter

获得严格脱敏的真实 API 合同后，只实现最小边界：

- fetching/auth 与 source normalization 分离；
- 首先只读，并保持旁路失败隔离；
- 业务版本顺序必须显式且有来源；
- credential 不进入 core object 或模型 tool；
- 不在合同提供前臆造 payload 字段、重试、分页或 transaction。

当前任务范围外：直接访问 MongoDB、复制 Spring Boot 代码、隐藏 LLM 查询、
自动生产 Patch 写入。
