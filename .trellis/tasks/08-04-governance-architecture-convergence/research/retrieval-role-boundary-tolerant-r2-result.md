# Retrieval R2 边界容忍角色召回首次冻结结果

## 冻结运行

- 日期：2026-08-04；
- Silver 回归：`run_fire_m5_retrieval_ab.py --mode r2`；
- 小模型：`qwen3.6-35b-a3b`；
- Prompt：`treeguard.retrieval-role-extraction.zh.v2`，未修改；
- 下游算法：`treeguard.boundary-tolerant-role-lexical-retrieval.v1`；
- 数据：已暴露的 M5 clean-room 虚构校准集，18个 `PROCEED`；
- 运行前已冻结算法、分母、五种视图、门槛与停止规则。

## 结果

Silver R2 回归：五种视图 Recall@8/20=16/16、MRR=1.000000，explicit-empty
正确状态=2/2，确定性重放=18/18，总体 PASS。

小模型 R2：

- 18次首发，0重试，0传输失败，合同通过18/18；
- Silver exact case=10/18；模型 span=36、Silver=29、精确匹配=27；
- 仍漏失2个 Silver TARGET，均由同角色模型 super-span 替代；
- 额外 span=9：TARGET 3、SCOPE 3、EXCLUSION 3；
- 五种视图 Recall@8/20=16/16、MRR=1.000000；
- explicit-empty 正确状态=2/2，重放=18/18；
- 总体 PASS。

## 结论

相同的两个 TARGET super-span 在 R1 中稳定导致 Recall@8=14/16、MRR=0.875，在
R2 中不再造成漏召回。因为模型、Prompt、角色合同、请求、Oracle、分母和五种视图均
未改变，本次差异可以归因到“完整 TARGET 短语硬门禁”被边界容忍的确定性词法相似度
替代。

此前失败不是模型完全不理解 TARGET，也不是 JSON、Provider、上下文窗口、树规模或
parent 污染；直接问题是自然语言 span 边界与树标签边界的接口过于严格。R2 在暴露
开发集上提供了可实现的候选生成基线，并容忍本次运行中更多非必要 span，说明下游不必
要求抽取结果与人工 Silver 字节级一致。

## 限制与下一步

- 本数据已暴露并参与架构选择，PASS 不是泛化或生产资格；
- R2 仍是无 embedding 的字面相似度，只验证边界差异，没有验证同义词、缩写、跨语言
  或完全无词面重合；
- 当前实现未接入生产 `build_candidate_set()`、治理 CLI 或 Semantic；
- 停止在本18条上调整 Prompt、权重或 n-gram；冻结 R2 作为开发候选；
- 下一步使用新的未见树和未见请求独立确认 R2，并另行预注册向量/混合候选比较；未见
  结果不得回流调参。
