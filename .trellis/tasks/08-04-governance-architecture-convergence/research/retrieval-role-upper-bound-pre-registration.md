# Retrieval 角色化 Fact 上限实验预注册合同

## 目的与边界

本实验回答一个单一问题：如果需求中的目标、作用域和排除证据已经被正确标注，当前
确定性节点表示是否足以产生可用的 Top-K 候选与排序。

- 数据仍是已经暴露的 M5 clean-room 虚构校准集；
- 角色标注由 Codex/Silver 只依据请求正文冻结，不读取目标节点来生成标注；
- 不调用 LLM，不评估小模型能否抽取角色；
- 不修改生产 `IntentContent`、`build_candidate_set()`、Prompt、Semantic 或 CLI；
- 结论是 calibration-only 上限，不产生 Gold、泛化或生产资格。

## 最小角色合同

每个角色证据必须绑定原始 `IntentRequest.request_hash`，并包含：

- `role`：`TARGET`、`SCOPE` 或 `EXCLUSION`；
- `text`：原始 requirement text 中逐字复制的非空连续 span；
- `start` / `end`：Python Unicode code-point 半开区间；
- span 必须与原文逐字相等，范围合法且不重复；
- 至少一个 `TARGET`，最多 8 个 span；
- 规范顺序固定为 `(start, end, role)`；
- `provenance=CODEX_SILVER_CALIBRATION`，且固定非 Gold、非 gate、非生产资格；
- 完整对象使用规范 digest 绑定请求和角色字节。

人工冻结输入允许保存精确短语，但不得保存或引用 Oracle 目标、稳定 node ID、模型响应
或答案。宽泛类别请求中的类别短语仍是 TARGET；空目标请求中的不存在名称也仍是
TARGET，零候选由树匹配结果决定。

## 唯一候选算法变化

角色化候选 `R1` 继续复用 B1 的原始需求、整数 IDF、结构字段和最多 100 个开发期
候选，不修改 B1/B2/B3：

1. `TARGET`：候选名称或完整路径必须连续命中至少一个完整 target；名称每命中一个
   加 30,000,000，完整路径每命中一个加 15,000,000；
2. `SCOPE`：只作软上下文，名称每命中一个加 2,000,000，完整路径每命中一个
   加 5,000,000；不得单独让候选入围；
3. `EXCLUSION`：名称或路径连续命中任一完整 exclusion 时直接排除；
4. phrase 使用 NFKC、大小写折叠和空白规范化；
5. B1 基础分保留，最终仍使用整数总分降序、稳定 node ID 升序；
6. 无 target、span 不绑定原文、请求/快照漂移或角色合同非法时 fail closed；
7. 最终 Top-K 仍为 20，Semantic 预算仍只允许未来使用 Top-8。

## 固定分母、视图与门槛

复用 Oracle v2 的18个 `PROCEED`：16个 target-bearing、2个 explicit-empty；复用
五种输入视图，每个单元重放三次。角色证据始终绑定各视图实际重建后的 request；
parent 和模型自由文本变化不得改变人工冻结的正文 span。

门槛不低于此前冻结标准：

- `V_REQUIREMENT_ONLY` 与 `V_FREE_TEXT_DROPPED` Recall@8=16/16；
- 两个主视图 MRR 至少 0.90；
- `V_CANONICAL` Recall@8=16/16；
- 所有视图 explicit-empty 正确状态=2/2；
- `V_PARENT_ABSENT` Recall@8 至少15/16；
- `V_PARENT_WRONG_BRANCH` Recall@20 至少15/16；
- 所有视图确定性重放18/18；
- 聚合报告不得包含请求正文、span 文本、场景/节点身份、hash 或隐藏 Oracle。

## 决策规则

- 全部门槛通过：只证明角色化表示在暴露校准集上具有充分上限；冻结角色合同候选，
  下一步在开发集上测试小模型的 span/role 抽取，不再调召回权重；
- Recall/空目标失败：角色表示仍不足，停止小模型抽取实验，先评估节点表示或混合召回；
- 仅 MRR 失败但 Recall@8 与空目标通过：保持 FAIL，转交 Semantic Top-K 重排职责决策，
  不追溯降低门槛；
- 任何失败后不得修改同一 R1 并保留版本名，且不得用本集合宣称泛化。
