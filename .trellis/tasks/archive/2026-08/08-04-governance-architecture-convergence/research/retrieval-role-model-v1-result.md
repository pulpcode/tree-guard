# Retrieval 小模型角色抽取 v1 首次冻结结果

## 冻结运行

- 日期：2026-08-04；
- 模型：`qwen3.6-35b-a3b`；
- Prompt：`treeguard.retrieval-role-extraction.zh.v1`；
- 数据：已暴露 M5 clean-room 虚构校准集的18个 `PROCEED`；
- 实际调用：18；首发18、合同重试0、传输失败0；
- 完整请求和响应未写入仓库或本研究记录；
- R1、Oracle v2、Silver 标注、五种视图、分母与门槛保持冻结。

## 抽取层结果

- 最终合同通过：18/18；
- 首次合同通过：18/18；
- 与 Silver exact-case agreement：12/18；
- 模型 span：33；Silver span：29；逐 span 精确匹配：27；
- 相对 Silver precision：0.818181；recall：0.931034；
- 模型比 Silver 多6个 span，少2个 span；Silver 非 Gold，该差异只作诊断。

## 冻结 R1 下游

五种输入视图结果完全一致：

- Recall@8：14/16；
- Recall@20：14/16；
- MRR：0.875000；
- explicit-empty：2/2；
- 重放：18/18；
- 状态：14个 `CANDIDATES_READY`、4个 `NO_CANDIDATES`；
- 总体判定：FAIL。

失败码覆盖主视图 Recall、MRR、canonical、parent absent 和 wrong-parent 门槛；空目标
和确定性门槛没有失败。

## 归因

模型已经稳定遵循最小 JSON 与原文绑定合同，因此本轮不是窗口、格式、字段缺失、
重试或 Provider 传输问题。Silver 上限 R1 为16/16和 MRR 1.0，而相同 R1 接收模型
角色后降为14/16，故两个目标缺失应归因于角色语义选择：模型漏选了对召回必要的目标
证据，并同时倾向多选上下文 span。

R1 没有因为错误 parent 或 Intent 自由文本发生视图漂移；两个 explicit-empty 仍正确，
说明本地不存在目标时的安全停止没有退化。

## 能够与不能得出的结论

能够得出：

- 小模型可稳定产出严格、source-bound 的角色合同；
- 角色化 Fact → R1 的技术接口可执行且错误可以分层归因；
- v1 Prompt 的角色语义精度不足以进入未见生产资格确认。

不能得出：

- 不能据此否定角色化路线；人工上限已证明冻结 R1 在本集合足够；
- 不能把失败归因于 R1、树规模或模型 JSON 能力；
- 不能用本集合继续调整 R1，或把任何后续 Prompt 改进宣称为泛化。

## 下一步边界

先增加不含身份、正文或 hash 的角色差异诊断：区分同一短语角色错标、漏掉 TARGET、
多选 TARGET/SCOPE/EXCLUSION。若需要重复调用 v1，只能标为诊断/重复性，不覆盖本结果。
之后可预注册一个且仅一个 v2 Prompt 候选，重点收缩 TARGET 与 SCOPE 定义；R1、合同、
Oracle 和门槛不变。v2 仍只属于暴露开发集校准，最终必须由新未见树确认。
