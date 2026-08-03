# M4 非盲校准候选交接

## 目的与边界

- 新身份：`fictional-fire-m4-calibration-v1`；
- 用途：只校准 M4 v1 的 request-observable Intent 评分，再继续观察召回与推荐链路；
- 来源：已暴露的完全虚构 fire v1 冻结字节；
- 固定状态：`EXPOSED`、`CALIBRATION_ONLY`、`gate_eligible=false`、
  `execution_eligible=false`、`PENDING_HUMAN_REVIEW`；
- 不是新 holdout、不是 Gold、不能给出生产准确率或 `GO_SHADOW` 结论。

原盲测 manifest 与 sidecar 保持逐字节不变；其 SHA-256 仍分别为
`33628996…71267` 与 `7f467c0e…9cce0`。本阶段没有调用外部模型、网络或生产数据，
也没有生成正式 fixture。

## 候选变换

8 条原执行场景全部进入候选审核包：7 条 `PROCEED`、1 条 `CLARIFY`。允许的
变换只有：补齐缺失的 `lifecycle` expectation；把没有逐字段确定性来源绑定的
自由文本/list 字段及值为 `UNKNOWN`/`null` 的结构化 hint 改为 `NOT_COMPARED`
并清空 `acceptable_values`；非空结构化 hint 必须保持精确比较。request、route、
召回 Oracle、推荐 Oracle、稳定目标、action、reviewed record 及其来源绑定均不允许
改变。

机器重放得到：

- 59 个 expectation 发生上述白名单变换；
- 29 个保留比较点具有结构化 request 或 route 证据；
- 67 个 expectation 记录为 `PROPOSED_UNBOUND`，等待人工确认暂不参与比较；
- 7 条 `PROCEED` profile 各保留三个非空结构化 hint 的精确比较，以及 route
  支持的 `clarification_question == null` 检查；真正提供区分力的是前三者；
- 1 条 `CLARIFY` profile 的三个结构化 hint 都是 `UNKNOWN`/`null`，因此明确
  `NOT_COMPARED`，由必须非空的 `clarification_question` 提供区分力；
- 每条 profile 都显式且只覆盖全部 12 个 Intent 字段，没有退化为只看 route 或
  无条件通过。

机器通过只说明字节、来源、白名单 diff 和 v1 可满足性成立，不等于 8 条 Oracle
已经得到新一轮人工认可。

## 私有 staging

目录：`artifacts/fictional-validation/fire-m4-calibration-v1/`，目录权限为 `0700`，
九个文件权限均为 `0600`。主要绑定：

- `scenario-candidates.json`：`8a408fb2…0bbbf`；
- `human-review-packet.json`：`f5485a85…2a11`；
- `manifest.json`：`ef4b0c95…08f7`；
- `preflight-report.json`：`312bff84…51d7`。

公开 CLI 只输出聚合计数和固定状态，不输出 request、Oracle、目标或来源 hash。

## 人工审核门

下一步必须逐项审核 8 条候选，不抽样。审核者需要确认：

1. 非空结构化 hint expectation 与冻结 request 完全一致，`UNKNOWN`/`null` hint
   没有被误当成“模型必须输出未知/空”的证据；
2. clarification policy 与 route 一致；
3. 标记为 `PROPOSED_UNBOUND` 的字段在 v1 下确实不应参与机器比较；
4. 未变更的召回与推荐 Oracle 仍可接受；
5. 没有为了提高 match rate 而删除仍有区分价值、可重放的约束。

若任一项需要修改，整批候选必须重新生成并使现有审核绑定失效。只有用户对最终候选
字节明确批准后，才能记录人工决策；正式 fixture 晋升、功能合同提交和模型调用仍是
后续独立门禁。
