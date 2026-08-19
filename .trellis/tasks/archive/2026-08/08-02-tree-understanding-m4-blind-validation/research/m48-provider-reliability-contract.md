# M4.8 Provider 通用可靠性合同

## 证据与问题

M4.7 主实验的一条 Semantic 合同重试遇到连接失败后立即终止；M4.7b 同一输入两次
独立重复均首发通过，说明该失败不是稳定语义缺陷。另一条字段合同失败也未复现，但现有
固定码无法区分输出不是对象、缺字段或多字段。

百炼官方 OpenAI 兼容参考当前明确列出的结构化输出能力是
`response_format={"type":"json_object"}`；当前 Provider 已使用该模式并关闭 thinking。
官方限流与错误指引把连接、429 和服务端错误视为可重试类别，但 429/5xx 的可靠处理
需要退避或服务端排队。本轮只解决已观察到且无需引入时钟/随机策略的连接失败，不把
即时重试扩展到 HTTP 状态。

公开依据：

- https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions
- https://help.aliyun.com/zh/model-studio/rate-limiting-best-practices

## 冻结方案

- `BailianConfig` 新增 `max_transport_retries`，默认 0，允许值为 0/1；默认行为和历史
  实验保持不变。
- Semantic Provider 将“逻辑合同尝试”和“实际 wire 尝试”分开计数。连接恢复不
  消费合同重试，必须重发完全相同的 request body；每次 wire 尝试独立 trace。
- 全局只允许消费一次连接恢复。`max_attempts=2` 且
  `max_transport_retries=1` 时最多 3 次实际请求，不形成隐藏网络调用。
- 只重试后缀为 `CONNECTION_FAILED` 的 Provider 错误；HTTP、编码、响应过大/非 JSON
  以及本地模型合同错误继续按原分类处理。
- 顶层字段主错误码保持 `SEMANTIC_MODEL_FIELDS_INVALID`。安全细分码只表达形状类别，
  不包含具体字段名、计数、模型正文或来源信息；retry Prompt 仍使用兼容主码。
- 不修改 Semantic v4 Prompt、M4.7/M4.7b 私有结果或主评分。任何后续效果判断必须
  冻结新的调用上限，并使用新密封数据。
