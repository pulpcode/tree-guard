# Retrieval B2 强锚点预注册合同

## 前置状态

- B1 保持 FAIL，不修改其实现、结果或门槛；
- M5 原始 Oracle 不修改；
- 开发期使用 `treeguard.fire-m5-request-observable-retrieval-oracle.v2` 内存 overlay；
- overlay 只修正两个宽泛类别的可接受目标完整性，其余 16 个单元保持原语义；
- overlay 为 calibration-only、非 Gold、非 gate、非生产资格，且不进入模型输入。

## B2 唯一算法变化

B2 在 B1 全量原文查询与整数 IDF 排序之上增加显式强锚点层，不修改 tokenizer、树表示、
结构约束或 parent 软 boost：

1. 中文/ASCII 引号中的文本是显式锚点；
2. 长度至少 4 的 ASCII 标识词是显式锚点；
3. 位于“不要误用”或“排除”之后的引号/标识词是排除锚点；
4. 排除锚点从正向锚点中移除，并对命中候选施加固定负向分数；
5. 存在正向锚点时，候选至少命中一个正向锚点才能入围；
6. 不存在显式锚点时，完整回退到 B1，不猜测隐含主题词；
7. 结构 match 和 parent 仍不能单独让候选入围；
8. 相同输入必须使用整数分数、稳定 node ID tie-break 和规范 hash。

本规则只理解上述显式语法，不尝试用确定性代码解析任意否定、指代或复杂逻辑。复杂
语义仍由后续受控 Semantic 阶段处理。

## 固定实验

继续使用 B1 的五种视图和相同 18 个 `PROCEED` 分母：16 个 target-bearing、2 个
explicit-empty。每个单元重放三次。A 仍为 v1；B1 只用于历史对照；B2 使用 Oracle v2。

## 门槛

不下调 B1 已冻结门槛：

- `V_REQUIREMENT_ONLY` 与 `V_FREE_TEXT_DROPPED` Recall@8=16/16；
- 两个主视图 MRR 均至少 0.90；
- `V_CANONICAL` Recall@8=16/16；
- 所有视图 explicit-empty 正确状态=2/2；
- `V_PARENT_ABSENT` Recall@8 至少 15/16；
- `V_PARENT_WRONG_BRANCH` Recall@20 至少 15/16；
- 每个视图 18/18 单元三次逐字节一致；
- 不调用 LLM、不修改生产入口、不产生生产资格。

## 决策规则

- 全部门槛通过：冻结 B2 为候选 Retrieval 方案，下一步进入 Semantic/Policy 职责收缩；
- hard negative 仍误召回：强锚点准入失败，B2 不晋升；
- target 跌出 Top-K：检查锚点抽取覆盖，但不得在本轮运行后扩大语法并仍称 B2；
- Oracle v2 自身重放或完整性失败：实验无效，不运行 B2；
- B2 失败后的任何新语法必须升级为 B3 并重新预注册。
