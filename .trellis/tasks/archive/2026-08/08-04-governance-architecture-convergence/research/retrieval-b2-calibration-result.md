# Retrieval B2 首次冻结校准结果

## 结论

B2 首次冻结运行判定为 **FAIL**。本结论使用预注册的 18 个 `PROCEED` 单元、五种
输入视图、Oracle v2 内存 overlay 和原冻结门槛；未调用 LLM，未修改生产入口、原始
fixture 或原始 Oracle。

失败码：

- `RETRIEVAL_B2_CANONICAL_REGRESSION`
- `RETRIEVAL_B2_PRIMARY_MRR_BELOW_MINIMUM`
- `RETRIEVAL_B2_PRIMARY_RECALL_BELOW_MINIMUM`

## 聚合结果

五种视图的 B2 指标完全一致：

- target-bearing：16；explicit-empty：2；
- Recall@8：15/16；
- Recall@20：16/16；
- MRR：0.880208；
- explicit-empty 正确状态：2/2；
- 确定性重放：18/18。

相比 B1，B2 修复了两个 explicit-empty 的误召回，并消除了 parent 缺失、错误 parent
和模型自由文本移除造成的结果漂移；但仍有一个正确目标位于第 12 名，因此未达到
Recall@8=16/16 和 MRR>=0.90 的冻结门槛。

## 唯一 Top-8 失败归因

失败单元同时包含一个正向引号短语和一个排除引号短语。B2 使用通用词法 tokenizer
把两个中文短语展开为单字及短片段，再按重叠数量施加正向奖励和排除惩罚。正确目标
与排除短语共享通用片段，因而被错误施加排除惩罚，从预期头部位置跌至第 12 名。

这属于 `Retrieval / anchor representation` 的确定性算法错误：

- 不是 LLM 输出或模型能力问题，本实验未调用 LLM；
- 不是 parent 污染，五种视图结果相同；
- 不是 Oracle v2 宽泛类别扩展问题，该单元沿用原 Oracle；
- 不是随机性，三次重放及全部视图均稳定复现。

## 决策

- B2 保持冻结并判定 FAIL，不在 B2 名下修改 tokenizer、权重或门槛；
- 下一候选若继续，应升级为 B3，并在实现前预注册“完整短语锚点”的匹配、排除和
  回退语义；
- B3 仍复用相同校准分母和不降低的门槛；
- B3 通过仍只代表开发期方案选择，之后仍需新的未见数据确认泛化。
