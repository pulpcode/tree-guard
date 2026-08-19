# H2 Oracle 与 Silver 审核设计

## 文件隔离

执行数据与评分答案分为两个不相互嵌套的工件：

* `scenarios.v1.json`：只含执行所需请求、结构 hints、类别公开标签和稳定场景引用；
* `oracle-sidecar.v1.json`：只含与稳定场景引用绑定的本地评分字段。

manifest 可以绑定二者摘要，但公共运行视图不得展开 Oracle。未来模型输入构造函数只
接收树与执行场景，不接收 Oracle 参数；评分器在候选结果产生后才同时接收结果与
sidecar。

## Oracle 三类互斥合同

| 场景类 | Oracle 必填 | Oracle 禁止 | 评分用途 |
|---|---|---|---|
| 有目标（20） | 单一 `target_node_id` | 排除目标、空状态 | Recall@20、Recall@8、MRR |
| hard negative（4） | 一个或有界集合 `excluded_node_ids` | 正向目标、空状态 | 排除目标 Top-8 违规数 |
| 显式空目标（4） | 单一 `expected_empty_status` | 正向目标、排除目标 | 空目标状态正确数 |

三类字段精确封闭，不能同时出现。所有引用必须存在于冻结树、场景引用必须与执行集一一
对应，重复、未知、遗漏或额外 Oracle 条目均 fail closed。

## Silver 审核

Codex 可执行两轮确定性审核：

1. **结构审核**：来源声明、resource/规模/VALUE、引用、字段集、配额、摘要、排序、
   执行/Oracle 一一绑定；
2. **语义审核**：按覆盖蓝图 rubric 判断类别独立、Oracle 唯一、负例边界、干扰合理
   和答案不泄漏。

审核记录只使用非识别性 reviewer role `CODEX_SILVER_REVIEWER`、固定 decision、固定
reason code、工件摘要和聚合计数。最终状态最多为 `CODEX_SILVER_REVIEWED`，并重复
声明 `gold_eligible=false`、`production_qualification=false`、
`patch_eligible=false`。

## 冻结与篡改检测

冻结顺序固定为：树 → 候选 → Silver 审核 → 28 条执行集 → Oracle sidecar → manifest。
每个工件使用项目唯一规范摘要实现；manifest 绑定生成配置、seed/namespace、上游
摘要、类别计数与冻结状态。任何域内字节变化必须使摘要或可信重建失败。

摘要只证明完整性。重新计算摘要的篡改仍需因可信生成配置、场景/Oracle 互斥合同或
跨工件重建不一致而拒绝。

## 防泄漏门禁

数据专属测试至少包含：

* 在 Oracle 字段和值中放置 canary，断言模型输入与 A 聚合均不含 canary；
* 断言模型输入构造 API 不接受 Oracle 参数，且输出字段使用独立正向允许列表；
* 断言 manifest 公共视图与错误报告不含场景文本、节点/路径/ID、Oracle 或逐项结果；
* 断言错误只输出固定 code，不输出路径、异常原文或 sidecar 内容；
* 断言 embedding 模块/Provider 未导入、未安装、未调用。

## A 本地评分

A 对每条冻结执行场景只调用冻结 R2 lexical 公共确定性入口，固定 lexical Top-40 并
观察 Top-20。逐项候选只留在进程内，与 Oracle 比较后立即聚合；持久化报告只含：

* 总有目标数与 Recall@20 命中数；
* 非字面总数与 Recall@20 命中数；
* 总 Recall@8 命中数与 MRR 聚合；
* hard negative 总数与 Top-8 违规数；
* 空目标总数与状态正确数；
* 固定算法/报告版本、`embedding_used=false`、状态或固定错误码。

若总命中数大于 18 或非字面命中数大于 8，报告状态固定为
`H2_DATASET_NOT_DISCRIMINATIVE` 并停止。不得持久化逐项结果，也不得据此修改冻结
数据。

## 审核限制

Silver 审核不能宣称专家意图、Gold 或生产资格；A 只证明词法区分度。后续 B 不属于
本数据分支，且 Oracle 在任何情况下都不得进入模型输入。
