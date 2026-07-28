# TreeGuard 百炼开发冒烟指南

状态：开发验证

本指南只验证 TreeGuard 的模型协议和受约束审查链路，不证明外部云模型与内网
`Qwen3.6-35B-A3B-FP8` 量化部署具有相同效果。

## 1. 当前选择

- 默认模型：`qwen3.6-35b-a3b`；
- 接口：阿里云百炼 OpenAI 兼容 Chat Completions；
- 输出能力声明：`JSON_OBJECT`，不是 Provider 保证的严格 JSON Schema；
- 推理模式：`enable_thinking=false`；
- 调用次数：首次调用加最多一次受控重试；
- 最终约束：本地代码校验精确字段、枚举和证据引用，再绑定内部 case 与 pack；
- 完整性：只接受 `finish_reason=stop`，并执行 BLOCKED/候选依据跨字段门禁；
- 失败策略：连接、格式、合同或引用校验失败均转为 `ABSTAIN`。

官方资料：

- [Qwen3.6-35B-A3B 模型说明](https://help.aliyun.com/zh/model-studio/qwen3-6-35b-a3b)
- [OpenAI 兼容 Chat 接口](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)
- [结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)

## 2. 数据边界

百炼是外部云服务。只允许发送：

- 完全虚构的数据；或
- 已经过组织审批、严格脱敏并允许出域的最小样本。

不得发送真实信息树、真实节点名称或路径、内部版本说明、VALUE、Prompt/Trace、
邮件模板、内部接口信息或全树一致的假名映射。

EvidencePack 的外部模型视图会机械排除原始 VALUE、未知 metadata、extension、审计
信息、真实 `node_id`、内部哈希和版本标识，但会保留审查所需的节点名称、label 和
路径。因此它是“模型白名单输入”，不是自动完成出域脱敏的证明。内部 EvidencePack
仍保存一次性引用到 `node_id` 的映射，用于审查回指。CLI 要求同时提供 `--live` 和
`--external-data-approved`，缺一即在读取文件前拒绝。

## 3. 环境准备

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
export BAILIAN_API_KEY='replace-with-a-rotated-key'
```

默认配置：

```text
TREEGUARD_LLM_MODEL=qwen3.6-35b-a3b
TREEGUARD_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

API Key 与地域绑定。若 Key 不属于北京区，必须把
`TREEGUARD_LLM_BASE_URL` 改为控制台给出的对应地域或业务空间官方端点。Key 只通过
进程环境注入；不要写入 `.env`、shell 脚本、命令历史、测试产物或 Git。

## 4. 分层验证

先离线验证适配、业务版本 Diff、ReviewCase 和 EvidencePack：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-ai-review \
  /path/to/fictional-base.json \
  /path/to/fictional-target.json
```

成功时状态为 `EVIDENCE_PACK_READY`，输出仅包含聚合计数。

再执行外部模型冒烟：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-ai-review \
  /path/to/fictional-base.json \
  /path/to/fictional-target.json \
  --live \
  --external-data-approved
```

可能的结果：

- `AI_REVIEW_COMPLETED`：返回内容通过本地合同校验；
- `AI_REVIEW_ABSTAIN`：两次以内仍未通过，或网络/鉴权失败；
- `NO_REVIEW_CASE`：两个端点没有需要 AI 审查的结构候选；
- `REJECTED`：输入、顺序、数据出域确认或 EvidencePack 不合规。

需要在受控内网目录检查完整制品时，才显式添加：

```bash
--internal-output /approved/internal/path/review.json
```

该文件含节点文本、路径、版本和模型草稿，不得外传或提交 Git。
文件以 `0600` 新建；目标已存在或为符号链接时拒绝，不会覆盖。

## 5. 内网迁移

内网 Qwen 若提供同一 OpenAI 兼容协议，可以复用 `AIReviewDraft` 和 EvidencePack
合同，只替换 Provider 的鉴权、端点和能力探测。迁移验收必须重新验证：

1. `json_object` 是否真的可用；
2. `enable_thinking=false` 是否生效；
3. 超时、上下文、并发和最大输出；
4. 非法 JSON、未知字段、虚构引用是否 fail-closed；
5. 同一冻结案例在百炼与内网量化模型上的选择性准确率和拒答率。

外部百炼结果只能作为开发基线，不能直接宣称内网模型已经达到相同质量。
