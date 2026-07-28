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

专家原文不包含在上述授权中。让百炼整理专家思考时，必须先用
`prepare-approval` 对本次 action 的准确 `raw_text`、EvidencePack、初审草稿、
端点、模型、Prompt 和可能发生的两次请求体生成 `PENDING` 私有清单，再由审批人
另存为 `APPROVED` 私有清单。Provider 会在联网前重算并核对精确请求计划；不会发送
actor、时间、会话状态、最终理由或内部哈希。真实专家讨论默认不得使用此外部路径。
文件清单中的审批身份只是 `UNVERIFIED_FILE_ASSERTION`，不等于身份认证或签名。

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

专家审查 CLI 会拒绝组/其他用户可读的输入。在运行第 5 节各条命令前，对本次实际
存在的全部输入执行，例如：

```bash
chmod 600 \
  /path/to/fictional-base.json \
  /path/to/fictional-target.json \
  /approved/internal/ai-bundle.json \
  /approved/internal/expert-thought.action.json \
  /approved/internal/session-001.json \
  /approved/internal/approval-approved.json
```

初次运行时尚不存在的可选文件应从命令中省略。后续生成的 session 和 approval
文件本身会以 `0600` 独占创建。不要把符号链接、FIFO 或已有文件作为输出目标。

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

## 5. 专家思考 AI 整理冒烟

先用上一节的 `treeguard-ai-review --live --external-data-approved
--internal-output /approved/internal/ai-bundle.json` 生成非空 AI 初审 bundle。
专家 action 使用 `expert-review-action.v1`，首条思考示例为：

```json
{
  "schema_version": "expert-review-action.v1",
  "action_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "case_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "expected_session_hash": null,
  "action_type": "EXPERT_THOUGHT_SUBMITTED",
  "actor_role": "DOMAIN_EXPERT",
  "actor_ref": "fictional-expert-01",
  "recorded_at": "2026-07-28T03:00:00Z",
  "payload": {
    "raw_text": "这是一段完全虚构、尚未形成分类结论的专家思考。",
    "evidence_refs": ["F001"]
  }
}
```

示例中的 `action_id` 必须替换为本次动作唯一的 64 位十六进制幂等标识；
`case_id` 必须从 bundle 的 `ai_review_draft.case_id` 原样复制。首条动作的
`expected_session_hash` 为 `null`，后续动作必须使用实际上一会话的
`session_hash`。保存并 `chmod 600` 后，先离线生成请求审批清单：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-expert-review prepare-approval \
  /path/to/fictional-base.json \
  /path/to/fictional-target.json \
  /approved/internal/ai-bundle.json \
  /approved/internal/expert-thought.action.json \
  --internal-output /approved/internal/approval-request.json
```

该命令不调用模型，标准输出也不显示审批哈希。它独占创建包含
`approval_status=PENDING`、`approved_by=null`、`approved_at=null` 的私有文件。
审批人应保留请求文件，并通过受控工具另存
`/approved/internal/approval-approved.json`，只做以下三项修改：

```json
{
  "approval_status": "APPROVED",
  "approved_by": "security-reviewer-01",
  "approved_at": "2026-07-28T03:05:00Z"
}
```

这里是字段变更片段，不是完整清单；其余生成字段必须原样保留。审批时间必须是严格
RFC3339、不能在未来，并且必须早于或等于随后记录的 AI 整理事件。两个审批文件都
应为 `0600`。只对完全虚构或已获批脱敏内容执行实际外部调用：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-expert-review apply \
  /path/to/fictional-base.json \
  /path/to/fictional-target.json \
  /approved/internal/ai-bundle.json \
  /approved/internal/expert-thought.action.json \
  --internal-output /approved/internal/session-001.json \
  --live-synthesis \
  --external-data-approved \
  --external-approval-file /approved/internal/approval-approved.json
```

成功时同一原子输出包含一条专家原文事件和一条 AI 整理事件，但权威状态仍为
`DELIBERATING`。模型或网络失败不会留下部分会话文件。后续状态和最终裁决分别通过
新的 action 文件追加到新的 session 文件；回放使用 `treeguard-expert-review
replay`，不会调用模型。

回放会重算事件链、来源绑定、状态和外发请求计划哈希，但不能认证 action/审批文件
中声明的人是谁。文件模式也没有全局权威 HEAD，同一 session 可以产生多个分别有效
的后继文件；它们都不是自动选定的发布分支。辅助会话即使到达 `APPROVED`，仍然
`patch_eligible=false`、`gold_eligible=false`。v1 每个会话最多一次 AI 整理。

## 6. 内网迁移

内网 Qwen 若提供同一 OpenAI 兼容协议，可以复用 `AIReviewDraft` 和 EvidencePack
合同，只替换 Provider 的鉴权、端点和能力探测。迁移验收必须重新验证：

1. `json_object` 是否真的可用；
2. `enable_thinking=false` 是否生效；
3. 超时、上下文、并发和最大输出；
4. 非法 JSON、未知字段、虚构引用是否 fail-closed；
5. 同一冻结案例在百炼与内网量化模型上的选择性准确率和拒答率。

外部百炼结果只能作为开发基线，不能直接宣称内网模型已经达到相同质量。
