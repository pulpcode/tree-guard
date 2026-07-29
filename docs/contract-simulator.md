# TreeGuard 协议级开发仿真

## 定位

该仿真系统用于真实内网 Qwen 和信息树仓库接口样例尚未到达时的外网开发。它提供：

- 完全虚构、确定性、可生成 2,000+ 节点的信息树；
- 分类、资源 HEAD、业务版本列表、指定版本全树四类暂定只读接口；
- OpenAI-compatible `POST /v1/chat/completions`；
- 正常、追问、非法 JSON、额外字段、429、500 和延迟故障场景；
- 严格 loopback 客户端和聚合验证命令。

所有仓库响应都标记
`contract_status=PROVISIONAL_SIMULATOR_CONTRACT`。路径、字段、排序、认证和分页都只是
Clean-room 开发合同，不代表真实生产接口。真实样例到达后，应新增薄 Adapter 并修订
这份暂定合同，不能为了兼容仿真而要求内网系统改变。

## 为什么同时保留 Mock 和百炼

两者解决不同问题：

- `simulator-live` 调用本地确定性 Mock，用于合同回归、故障注入和稳定回放；
- `bailian-live` 调用真实百炼，用于观察同一完全虚构场景下模型能否产出通过本地
  合同的意图和语义建议；
- `offline` 读取冻结模型输出文件，不发起任何模型 HTTP 调用。

Mock 的通过不能证明模型效果，百炼的一次通过也不能作为 Gold、真实领域质量或内网
Qwen 效果证据。两种模型源的产出都仍是待人工复核的建议，固定无生产写权限、非
Patch、非语义审批。

## 启动仿真服务

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-contract-simulator serve \
  --port 8765 \
  --node-count 2001 \
  --model-scenario ready
```

服务只监听 `127.0.0.1`。启动成功后 stdout 只打印一次聚合启动记录，不打印请求、
Authorization、节点或模型内容。开发固定 token 只用于防止误接其他本地服务，不是
生产认证方案。

可用的 `--model-scenario`：

| 场景 | 用途 |
|---|---|
| `ready` | 返回合同有效的意图和语义建议 |
| `clarification` | 初始意图返回一个追问 |
| `invalid-json` | 返回非法 JSON |
| `extra-field` | 返回带合同外字段的模型内容 |
| `http-429` | 模拟限流 |
| `http-500` | 模拟服务失败 |
| `timeout` | 按 `--delay-seconds` 延迟；默认 1 秒会超过本地 Provider 的 0.5 秒超时 |

## 验证四类仓库读取

保持服务运行，在另一个终端执行：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-contract-simulator verify-repository \
  --base-url http://127.0.0.1:8765
```

命令依次读取分类、资源、两个业务版本和两个全树快照，并通过现有
`adapt_tree_document()` 校验。stdout 只包含数量、状态和暂定合同标记。

## 用 Mock 跑完整治理纵切

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-governance-demo \
  --output-dir /tmp/treeguard-fictional-simulator-demo \
  --review-decision confirm \
  --mode simulator-live \
  --simulator-base-url http://127.0.0.1:8765/v1
```

这个模式会真实发起两次 loopback HTTP 模型调用：意图草稿和候选语义建议。完整结果
只写入新建的私有演示目录；stdout 仍为聚合报告。

## 用真实百炼观察模型产出

仿真系统没有替换现有百炼能力。准备私有 `.env` 后，可对内置完全虚构场景执行：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-governance-demo \
  --output-dir /tmp/treeguard-fictional-bailian-demo \
  --review-decision confirm \
  --mode bailian-live \
  --external-data-approved
```

该命令使用真实百炼服务，不使用 Mock。仍必须显式确认允许完全虚构输入出域；模型
输出只进入私有 sidecar，不写入 fixture、Git、Trellis 日志或自动化正确性断言。

## 当前不能验证的内容

- 内网 Qwen 地址、认证、证书、JSON Mode 和上下文上限；
- 真实四类接口的准确路径、请求和响应字段；
- 内网网络、A10 性能、吞吐和并发；
- 真实业务召回率、建议准确率和专家效果；
- 生产写入、MongoDB 或 Spring Boot 集成。

后续拿到严格脱敏的真实接口样例时，优先实现 Qwen 配置和仓库薄 Adapter，不修改
治理 Core。
