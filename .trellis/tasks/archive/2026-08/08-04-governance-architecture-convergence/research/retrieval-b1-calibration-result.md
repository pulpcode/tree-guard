# Retrieval B1 首次校准结果

## 运行边界

- 数据：已暴露的 M5 clean-room 虚构执行集；
- 运行：A/B 各五种固定查询视图，每个单元确定性重放三次；
- 模型调用：0；
- 结论等级：开发期校准，不产生生产资格；
- 门槛：使用首次运行前写入的 `retrieval-ab-pre-registration.md`，运行后未下调。

## 聚合结果

### 现有 A 基线

- Canonical：Recall@8=16/16、MRR=1.0、空结果=2/2；
- Free-text dropped / requirement-only：Recall@8=6/16、MRR=0.328125、空结果=2/2；
- 说明 v1 在理想模型改写下很强，但模型自由文本缺失时明显失去召回信号。

### 解耦查询 B1

- 所有五种视图的 Recall@20=16/16；
- Recall@8=15/16；
- MRR=0.817307；
- 空结果=0/2，两个 hard negative 均产生了候选；
- 错误 parent 没有把合法目标硬过滤；
- 每个视图 18/18 单元三次结果逐字节一致。

B1 因以下冻结 code 失败：

- `RETRIEVAL_AB_CANONICAL_REGRESSION`；
- `RETRIEVAL_AB_EMPTY_STATUS_REGRESSION`；
- `RETRIEVAL_AB_PRIMARY_MRR_BELOW_MINIMUM`；
- `RETRIEVAL_AB_PRIMARY_RECALL_BELOW_MINIMUM`。

## 失败归因

### B1 算法缺口

hard negative 含一个树中不存在的唯一主题词，但 B1 仍把通用句式中的低区分度词项用于
候选准入，产生 false positive。下一候选需要区分强主题锚点与背景词；结构 match 和
parent 只能加权，不能单独让候选入围。

### M5 Oracle 表达缺口

唯一跌出 Top-8 的单元属于“任一现有某类合同”的宽泛请求。仓库内确定性审计发现：

- 一个宽泛类别请求在树中有 29 个词法与节点类型均符合的节点，Oracle 只接受 6 个；
- 另一个宽泛类别请求有 45 个词法与节点类型均符合的节点，Oracle 只接受 8 个。

请求正文没有提供可观察条件来排除其余同类节点。因此当前 Oracle 把部分实质合法结果
误记为错误，不能用于要求 requirement-only 的唯一 Top-K 排序。这里记录聚合计数，不
保存隐藏目标、节点正文或 ID。

## 停线与决定

按预注册合同的既定规则，A 与 B 无法在 requirement-only 共同满足目标时，应先审核
节点表示与 Oracle，不得继续调权重。故：

1. B1 保留为 FAIL，不覆盖、不改写；
2. D1“原始 requirement text 为稳定主查询”继续成立，因为 B1 已把自由文本缺失时的
   Recall@20 从 6/16 提升到 16/16；
3. 暂停 B2 排序调参；
4. 先形成 M5 Retrieval 校准 Oracle v2：宽泛请求接受全部 request-observable 合法目标，
   hard negative 继续保持显式空目标；
5. Oracle v2 只能用于开发校准，不能恢复 M5 未见或生产资格；
6. Oracle v2 冻结后，再预注册 B2 的强锚点规则并运行一次。

## 当前不能得出的结论

- 不能说方案 B 已通过；
- 不能说加权词法最终足够；
- 不能把 P04 排序失败全归因于模型或召回算法；
- 不能用修订后的校准 Oracle 宣称泛化。
