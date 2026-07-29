# 持久化与集成边界

## 当前实现

TreeGuard 当前没有数据库代码、ORM、repository、migration、transaction、入站
HTTP 服务或 Spring Boot/MongoDB 连接器。已实现的持久化模型只有：

- 输入树导出和已解码 API response envelope；
- 可选的私有 AI review bundle；
- 不可变 expert action/session/approval JSON；
- 不可变 intent request/draft/action/confirmation/candidate JSON；
- 不可变 intent clarification answer/round JSON；
- 不可变 semantic recommendation draft/review action/record JSON；
- 一键虚构演示的全新 `0700` 运行目录、`0600` 中间工件和完成标志；
- 从冻结源工件做确定性回放。

唯一实现的网络路径是显式启用的百炼 `POST /chat/completions`。MongoDB、搜索、
Overlay 和 Patch 发布的设计文档不能被写成已存在层的代码规范。

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
