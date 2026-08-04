# Retrieval 角色化 Fact 上限首次冻结结果

## 冻结运行

- 日期：2026-08-04；
- 命令：`PYTHONPATH=src:scripts python3 -B scripts/run_fire_m5_retrieval_ab.py --mode r1`；
- 数据：已暴露的 M5 clean-room 虚构校准集，18 个 `PROCEED`；
- Oracle：内存生成的 request-observable retrieval Oracle v2；
- 标注：21 个 TARGET、5 个 SCOPE、3 个 EXCLUSION，来源为请求正文的
  Codex/Silver 连续 span；
- 模型调用：0；
- 运行前已冻结算法、五种视图、分母、门槛和后续决策规则。

## 聚合结果

R1 在五种视图中的结果完全一致：

- Recall@8：16/16；
- Recall@20：16/16；
- MRR：1.000000；
- explicit-empty 正确状态：2/2；
- 确定性重放：18/18；
- 状态分布：16 个 `CANDIDATES_READY`、2 个 `NO_CANDIDATES`；
- failure codes：空；
- 总体判定：PASS。

同一 harness 中的冻结 B3 对照仍为 Recall@8=16/16、MRR=0.843750、空目标 2/2。
R1 没有借助 parent 或模型自由文本：删除自由文本、删除 parent、注入错误分支 parent
均未改变聚合结果。

## 能够得出的结论

在这组已经暴露的校准请求上，如果 TARGET、SCOPE、EXCLUSION 已被正确且可回放地
标注，当前节点名称、路径和确定性 Top-K 机制足以把所有可接受目标排到第 1，并正确
保留两个空目标。B3 的五个第 2 名不是候选容量不足，而是目标短语与上下文短语未被
区分角色。

因此 D2 的角色化 Fact 表示获得开发期上限支持，下一步可以测试小模型能否从原始请求
抽取同一最小角色合同；不再继续调整 B1/B2/B3/R1 召回权重。

## 不能得出的结论

- Silver 标注是人工冻结的理想输入，本实验没有验证小模型抽取能力；
- 数据已暴露并用于架构校准，不能证明跨树或未见请求泛化；
- 完整短语命中依赖请求与树字段存在可观察重合，不能代表生产自然语言一定如此；
- R1 是 calibration-only 原型，未接入生产治理入口，也未取得生产资格；
- 本实验不评价 Semantic 关系判断或最终动作选择。

## 后续边界

下一实验只允许改变输入侧：让小模型输出 source-bound TARGET/SCOPE/EXCLUSION span，
由本地合同验证后送入冻结 R1。需要分别报告角色合同通过率、span/role 与 Silver 的一致
程度、R1 Recall@8/MRR/空目标，以及失败发生在抽取还是召回。不得根据同一批失败继续
调整 R1 权重；在未见树确认前不得宣称生产资格。
