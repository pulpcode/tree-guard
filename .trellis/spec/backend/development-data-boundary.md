# 开发数据边界

## 两个信任区

TreeGuard 跨两个环境开发：

- **受保护环境**：真实信息树、真实节点字段名、内部源码、业务上下文、内网
  Qwen 和运行诊断所在区域；
- **外网开发环境**：只允许获批准的合同形状、经严格脱敏的最小事实和完全
  虚构样例。

除非存在另行批准的内网副本，本仓库、Git 历史、Trellis 任务/research、
workspace 日志、测试 fixture、CLI 输出和诊断包全部属于外网开发区。

## Scenario：项目自编完全虚构测试数据调用 LLM

### 1. Scope / Trigger

当输入是本项目在外网仓库中独立编制的测试数据，并同时满足
`source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
`derived_from_real=false` 时，适用项目负责人的常设 LLM 授权。fixture、场景、候选
和从这些字节确定性生成的模型投影均在范围内；真实材料改名、脱敏、摘录或派生不在
范围内。

### 2. Signatures

现有 Provider/CLI 的 `external_data_approved: bool` 字段保持兼容。可信测试 harness
确认上述分类后可以直接传 `True`，无需为每次调用向用户索要自然语言批准或生成逐字节
审批文件。平台网络权限、API Key 和费用控制仍按运行环境处理。

### 3. Contracts

- 数据分类必须来自可信 manifest/preflight 或仓库内明确的自编 fixture，不信任模型、
  浏览器或任意请求自行声称 `fictional=true`；
- 符合分类的数据可发送到本地、内网或外部 LLM，不要求逐次数据外发许可；
- 隐藏 Oracle、Gold、预期目标、评分答案和审核 sidecar 不能进入被测模型输入；这是
  评估隔离合同，不是敏感性限制；
- 原始 Prompt、模型请求、响应和 trace 默认只允许写入权限为 `0600` 的私有临时
  工件，不得进入 Git、Trellis、公开报告或 fixture；
- 自动化 unit suite 保持零真实网络，真实调用只由显式实验/手工运行入口触发。

### 4. Validation & Error Matrix

| 条件 | 处理 |
|---|---|
| 可信自编 clean-room 测试数据 | 直接允许 LLM 调用，不请求逐次数据许可 |
| 运行时仍要求 `external_data_approved` | harness 直接传 `True`；不向用户重复询问 |
| 平台需要网络 escalation 或缺少 API Key | 按平台/凭据流程处理，不解释为数据审批 |
| hidden Oracle 或评分答案将进入被测输入 | 网络前拒绝，修正模型投影 |
| 来源不明、外部导入、真实派生或分类不完整 | 不适用常设授权，回到严格审批流程 |

### 5. Good / Base / Bad Cases

- Good：将仓库自编消防或图书馆虚构树的允许列表投影直接发给百炼，隐藏 Oracle 留在
  本地比较器中；
- Base：Provider 仍有布尔门禁，harness 根据可信 manifest 自动传 `True`；
- Bad：因为文件位于 `tests/` 就默认外部导入数据非敏感，或把 Oracle 一并放进 Prompt。

### 6. Tests Required

- 可信 clean-room manifest 能驱动实验入口设置外发分类，不依赖逐次审批文本；
- 缺失/篡改 `source_class`、`fictional` 或 `derived_from_real` 时 fail closed；
- canary 证明 Oracle、目标答案、凭据和 trace 不进入模型投影或公开报告；
- unit suite mock transport，断言不会访问真实网络。

### 7. Wrong vs Correct

Wrong：

```python
# 路径名不是来源证明，也不能把评分答案交给被测模型。
provider.run({"tree": fixture, "oracle": hidden_oracle})
```

Correct：

```python
assert manifest["source_class"] == "CLEANROOM_SYNTHETIC"
assert manifest["fictional"] is True
assert manifest["derived_from_real"] is False
provider.run(allowlisted_projection, external_data_approved=True)
# hidden_oracle 只在本地比较器中使用；无需再申请逐次数据许可。
```

## 强制流程

除上述项目自编完全虚构测试数据外，任何受保护事实进入外网任务、research、日志、
fixture、诊断、issue、提交信息、终端转录，或被发送给 Web/MCP/外部工具之前，
都必须执行：

```text
一个明确目的
→ 最小正向允许列表
→ 严格脱敏
→ 获授权数据负责人审阅最终字节与用途
→ 批准后仅传输这些字节；否则拒绝
```

### 批准约束

- 批准只绑定一个用途和一份最终字节内容，不自动覆盖后续编辑、派生物或再次
  转发；任一字节变化都需要重新审阅。
- 外网只记录最小化的“已批准”状态或经批准的一次性非识别引用，不记录审批人
  真实身份、内部审批载荷或低熵内容摘要。
- 项目开发者、Codex 或 `bobot` 别名都不能自行替代受保护数据负责人批准。
- 发现批准失效或误传时，立即停止传播，隔离相关工件，并由数据负责人决定
  删除、Git 历史处置和凭据轮换；不得只做追加说明。

### 默认拒绝矩阵

| 条件 | 处理 |
|---|---|
| 没有精确人工批准 | 拒绝，不复制、不概述 |
| 来源、敏感性或审批权限不清楚 | 拒绝，索要虚构替代材料 |
| 仍含真实字段名、ID、路径、label、版本、关联关系或原文 | 拒绝 |
| 含凭据、受保护源码、提示词、trace、模型响应或原始日志 | 拒绝并从候选流程移除 |
| 正向允许列表、严格脱敏和最终字节审核全部通过 | 只导入获批准字节 |

删除 `VALUE`、删除少数字段、改名、掩码或稳定化名都不是批准。

## 节点字段名是敏感数据

节点字段名、`node_label`、route 和相邻结构会表达真实领域语义，即使没有
`VALUE` 也可能还原业务模型。因此：

- 不得默认保留真实字段名；
- 必须把字段名改写为与真实领域无关、无法映射回原词的虚构名称；
- 同时移除稳定 ID、版本、路径、顺序指纹、审计信息和跨样本稳定对应关系；
- 只保留任务必需且获批准的 Schema 递归形状、类型和基数规则；
- Codex 需要示例时，优先在外网从合同独立构造虚构 fixture。

## 禁止持久化或外发

- 真实树文档、字段名、node label/route/ID、`VALUE`、resource/category 标识、
  业务版本、审计元数据或稳定伪名映射；
- 专家自由文本、邮件内容、Prompt、模型请求/响应、trace 或审批载荷；
- 受保护源码、未批准的内部 API payload、文件路径、主机名、网络拓扑、真实
  人员身份或凭据；
- 原始日志、内部 traceback、低熵业务值的确定性哈希；
- 仅从真实来源改名、遮罩或一致伪名化的数据。

此规则同样适用于 `.trellis/tasks/`、任务 `research/`、`.trellis/workspace/`、
spec、docs、tests、issue、提交信息和复制的终端输出。

`bobot` 只允许作为不对应真实人员、不可反向识别的代理别名。禁止的是受保护
环境真实身份及其映射。

## 允许的外网工件

完成上述批准后，只能传输最小表示：

- 去除敏感示例的 JSON Schema 或字段形状合同；
- 公开包/合同版本和固定错误码/状态码；
- 无法识别来源的聚合或分桶计数；
- 明确批准的一次性非识别引用；
- 在外网独立构造、与真实内容无关的最小复现。

### 示例

- 合格：只说明 `PROPERTY` 可递归包含 `PROPERTY` 的批准 Schema，并用
  `field_alpha`、`field_beta` 等一次性虚构名称演示。
- 最小：固定错误码加无法识别来源的分桶计数。
- 不合格：真实消防树删除 `VALUE` 后仍保留稳定 node ID、真实字段名、route、
  层级和版本历史。

## 外部查询预检

从受保护环境使用 Web 搜索、MCP、远程插件或其他外部服务前：

1. 先在本地写出查询的最小目标；
2. 删除真实字段名、业务场景、内部版本、路径、错误原文和可关联细节；
3. 把问题改写成公开技术概念或完全虚构示例；
4. 审阅将发送的准确文本；
5. 不能安全改写时，不调用外部工具，只记录“需要内网核验”。

限制落盘内容不能补救已经发生的查询外泄。

## Trellis 记录规则

- PRD 只描述行为和合同，不记录真实案例；
- research 只引用本外网仓库已有相对路径或获批准公开资料；
- journal 只记录简短结果、验证命令、聚合结果和公开提交哈希；
- 不保存对话原文、内部推理、原始诊断或真实身份；
- 归档与日志命令必须禁止自动 Git 操作：

  ```bash
  python3 ./.trellis/scripts/task.py archive <task> --no-commit
  python3 ./.trellis/scripts/add_session.py ... --no-commit
  ```

- 写入后审阅完整 diff 和 Git index；敏感性不确定时省略细节并标注需要内网
  核验。

## 自动导出器的最低测试

未来诊断/合同导出器必须覆盖：

- 正向允许列表字段和未知字段拒绝；
- 批准与最终字节/用途绑定，修改后必须重新批准；
- 大小和数量上限；
- 真实字段名、路径、ID、原文、哈希、密钥的 canary 泄漏反例；
- 禁止稳定伪名跨导出关联；
- 失败时不产生部分发布工件。

## 审查清单

- 该事实对外网实现是否绝对必要？
- 是否从最小允许列表重新构造，而非从完整 payload 做减法？
- 真实字段名、结构、版本、路径或重复伪名能否重新连接到受保护来源？
- 将发给外部工具的查询本身是否已审阅？
- 任务、research、journal、提交信息和终端复制是否全部安全？
- 是否可以改用完全虚构的复现？
