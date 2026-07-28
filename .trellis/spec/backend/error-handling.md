# 错误处理

## 三种失败表示

### 可收集的源数据 issue

树适配可能发现多个相互独立的一致性问题。通过 `IssueCollector` 记录
`ValidationIssue(severity, code, location, message)`，并由 `ImportResult` 返回。

只有在继续同一有界遍历仍安全且完整计数有价值时使用。location/message 保留
在内部；一致性 CLI 只输出 severity/code 的聚合计数。

参考：`validation.py`、`models.ValidationIssue`、`adapter.py`。

### 带稳定 code 的领域异常

可预期的操作拒绝使用带稳定 `.code` 和内部可读 message 的领域异常：

- `SnapshotDiffError`
- `HistoryMiningError`
- `BusinessVersionReviewError`
- `EvidenceProjectionError`
- `AIReviewValidationError`
- `BailianProviderError`
- `ExpertSynthesisValidationError`
- `ExpertReviewError`

code 使用大写 snake case，通常以领域开头，如 `EVIDENCE_*`、`AI_REVIEW_*`、
`BAILIAN_*`、`EXPERT_*`；`BAILIAN_HTTP_<status>` 是明确允许的动态 code family。

message 不是公开诊断合同，可能含进程内调试细节，不能跨安全 CLI 边界输出。

### 内部不变量失败

constructor/`__post_init__()` 在代码尝试创建内部不一致工件时抛 `ValueError`，
例如顺序错误、summary 不匹配、版本常量非法、tuple 字段可变或 digest 错误。

接纳边界用领域异常，程序/工件不变量用 `ValueError`。公共操作需要稳定 code
时，在所属领域边界转换底层错误。

## 传播与转换

- 只捕获当前边界能够分类的异常；
- 内部上下文有用且安全时使用 `raise ... from exc`；
- 底层 message 可能泄漏不可信/Provider 细节，或稳定错误已表达全部公开语义时
  使用 `from None`；
- 确定性校验失败不重试；
- Provider 输出最多重新生成一次；超过尝试次数后抛固定
  `BailianProviderError`，不返回原始响应；
- 不自动修补未知字段、引用、ID 或枚举；
- 不用 `except Exception` 把编程缺陷伪装成业务拒绝。

`TreeFormatError` 有意没有 `.code`，message 可能含路径/OS 细节。CLI 必须映射
为固定 `TREE_FORMAT_ERROR`，不得输出原文。

## CLI 映射

已处理失败输出版本化聚合 JSON，不输出异常 message 或 stack trace：

- exit 2：输入、preflight、确定性 gate、配置或私有写入拒绝；
- 两个 AI CLI 的 exit 3：已经尝试外部模型调用，但失败或 abstain；
- exit 0：请求操作完成，包括合法空结果/无 case。

详见 [CLI 输出与诊断](./cli-output-and-diagnostics.md)。`ai.called` 必须与网络
执行是否真正开始一致；当前已知偏差需由独立缺陷任务修复。

## Fail-closed 解析

安全敏感 JSON 使用 `strict_json_loads()`，随后执行所属合同校验。严格 parser
拒绝：

- 重复 object member；
- `NaN`、infinity 等非有限数；
- float overflow 到非有限值；
- 超过本地 digit bound 的整数。

普通树导入当前仍使用普通 `json.loads()`，不能声称严格 JSON 已全局应用，也
不能把 expert/AI/approval/session 输入降级为普通解析。

语法解析后还必须验证精确字段、类型（含 bool/int 区分）、版本、边界、枚举、
唯一引用、来源绑定和跨字段策略。

## 审查清单

- 这是可收集 issue、预期领域拒绝，还是内部不变量？
- 新边界错误是否有稳定、非敏感 code？
- Provider 配置 code 变化时，两个 AI CLI 的 preflight 集合和测试是否同步？
- 缺少批准时，是否在读文件/发网络之前失败？
- 错误是否可能泄漏路径、源文本、Provider 响应、Prompt、key 或 hash？
- 可重试传输失败是否与确定性非法输入分离？
- 测试是否断言精确 code、退出类别、`ai.called` 和无部分输出？

禁止 `print(exc)`、返回 Provider body、把 secret 插入异常、吞掉不变量失败，
以及把所有失败强制转换为 `ABSTAIN`。
