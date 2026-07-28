# CLI 输出与诊断

## 当前没有日志框架

仓库当前没有 logger、level、结构化日志 backend 或 telemetry。不得把计划能力
写成已实现规范，也不得以此为由零散加入 logger 调用。

已实现的诊断边界是版本化、机器可读的 CLI stdout。已处理的成功/失败报告均为
单个 JSON object，使用 `ensure_ascii=False` 和 `sort_keys=True` 序列化。
`argparse` 参数用法错误是例外：保持默认 stderr 和 exit 2。

双环境排障确实需要结构化事件，但其批准方向是：

```text
内网结构化事件
→ 正向允许列表诊断导出器
→ 人工逐字节审核
→ 单向外网诊断包
```

这是初始化提交后建立的产品任务；原始日志直接外传不是批准方案。

## 报告形状

每份报告都有稳定 `report_version`，并按命令只包含允许列表字段，例如：

- `valid`
- `status` / `operation`
- 聚合计数和固定枚举
- `error_code`
- `ai.called` / `ai.status`

参考：

- `models.py` 的 `ImportResult.conformance_report()`
- `business_review.py` 的 `BusinessVersionReviewRun.aggregate_report()`
- `expert_review.py` 的 `ExpertReviewSession.aggregate_report()`
- `ai_cli.py` / `expert_cli.py` 的 `_print_error()`

扩展报告时从正向允许列表构造，不能先构造内部 payload 再删除少数敏感 key。

## 退出合同

| 命令 | Exit 0 | Exit 2 | Exit 3 |
|---|---|---|---|
| `treeguard` | 一致性有效 | 格式/一致性拒绝 | 不使用 |
| `treeguard-ai-review` | 离线 evidence、无 case 或 AI 审查完成 | 输入、批准、Provider preflight、确定性 gate、私有写入拒绝 | 已尝试模型，但网络/响应/输出校验失败 |
| `treeguard-expert-review` | apply、replay 或 approval preparation 完成 | 输入、批准、Provider preflight、状态/完整性、私有写入拒绝 | 已尝试外部 synthesis 且失败 |

preflight 失败保持 `ai.called=false`。新增 Provider error 时，必须同步两个 CLI
的 preflight code 分类和测试。

### 已知偏差

`treeguard-ai-review` 在 live review 成功、随后 `--internal-output` 发布失败时
调用通用 `_print_error()`，可能错误报告 `ai.called=false`。修复前不得依赖该
失败路径的字段；初始化提交后建立独立缺陷任务并增加回归测试。

## 跨边界诊断允许列表

可安全外传的诊断词汇仅限：

- 固定错误码/状态码；
- PASS/FAIL 或 validity；
- 公开合同/包版本；
- 无法识别来源的聚合或分桶 count/metric；
- 经批准的一次性非识别 case reference；
- 人工重写、完全虚构的最小复现。

聚合输出不得包含：

- 异常 message、traceback；
- 本地/内部路径、包细节、系统拓扑；
- 真实字段名、node label/route/ID、before/after 字段或原始 `VALUE`；
- 专家文本、evidence reference、actor、内部版本或 session hash；
- Prompt、模型请求/响应、Trace、approval payload hash 或内部 bundle；
- 凭据、authorization header；
- 低熵业务值的确定性 hash；
- 能跨导出重新关联的稳定伪名 map。

`tests/test_ai_cli.py`、`tests/test_expert_cli.py`、
`tests/test_business_review.py` 使用 canary 和 `assertNotIn` 验证边界。

## 完整内部工件

完整 review、evidence、draft、approval、session 数据只能在用户提供明确获批准
的内网输出路径时写入。它们受
[持久化与集成](./persistence-and-integration.md)约束，不是日志，不得复制到
stdout、外网诊断包或 Git。

Shadow MVP 的产品建议与审查记录写入 sidecar/overlay 工件，不修改生产信息树。

## 意外失败

预期领域异常输出稳定 code 或固定 fallback，不输出 `str(exc)`、Provider body
或 traceback。

当前没有包住每个命令的最终 catch-all，意外编程错误仍可能输出 Python 默认
traceback。此 stderr 必须留在受保护运行边界，不能直接转移到外网。优先通过
窄校验、测试和明确异常转换预防；不得用广泛 `except Exception` 隐藏缺陷。

未来引入运行日志时，必须：

- 作为独立、经审查的合同；
- 使用不污染 JSON stdout 的 channel；
- 保持相同的敏感数据正向允许列表；
- 对导出字段、未知字段、大小、approval binding 和泄漏反例建立测试。
