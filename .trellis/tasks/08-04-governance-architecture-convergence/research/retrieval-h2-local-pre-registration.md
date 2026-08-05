# H2 本地 BGE 混合召回预注册

## 决策目的

H1 使用百炼 `text-embedding-v4/512` 后，Recall@20 与非字面 Recall@20 均只比
R2 增加 1 条，未达到预注册的增加 2 条门槛。H2 只回答：保持 H1 节点/查询语义字段、
R2 lexical leg、Top-40、锚点门、排除过滤和 RRF 1:1 不变时，一个可内网本地部署的
小型中文 embedding profile 能否达到同类增益门槛。

H2 是新的开发期架构选择，不是 H1 重试、未见确认或生产资格实验。

## 唯一主要变量

H2 固定为：

- 模型：`BAAI/bge-small-zh-v1.5`；
- revision：`7999e1d3359715c523056ef9478215996d62a620`；
- safetensors SHA-256：
  `354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026`；
- 512维 float32；CPU；`eval()`；禁用梯度；
- tokenizer 使用冻结 revision，padding、truncation、最大 512 tokens；
- `[CLS]` pooling 后 L2 normalize；
- query model text 前添加固定 instruction：
  `为这个句子生成表示以用于检索相关文章：`；
- node passage 不添加 instruction；
- 批大小只有在任何模型输出前根据无语义 smoke 固定，之后不得按准确率调整。

Query instruction、pooling、normalize 和 tokenizer 是一个不可拆分的本地模型 profile，
不算对信息树文档字段或 RRF 的额外调参。

## 保持不变

- `treeguard.hybrid-node-document.h1.v1` 的 name、label、祖先路径、kind、value type、
  cardinality 字段完全不变；
- `treeguard.hybrid-query-document.h1.v1` 的 requirement、TARGET、SCOPE 和结构约束
  完全不变；只有 Provider 的 model-text profile 添加冻结 instruction；
- R2 lexical Top-40、vector Top-40、锚点门、EXCLUSION 本地过滤；
- `k=60`、两 leg 1:1 的整数 RRF、Top-20；
- `allows_addition=false`、无向量阈值、失败不静默计作混合成功；
- Silver 角色、Semantic 与 Policy 不进入本轮变化范围。

H2 使用独立 model-profile、query-embedding 和 index schema/version。模型、revision、
权重 SHA、instruction、pooling、维度或 tokenizer 任一漂移均拒绝旧索引。

## 新开发数据合同

不得读取或改写 H1 24 条场景、H1 Oracle 正文、R2 密封 28 条请求/Oracle 或其逐项
结果来构造 H2。只允许使用已公开 Schema/算法合同、聚合配额和完全虚构的独立树。

冻结一棵新的消防治理 clean-room resource 树：

- 目标规模 600–900 节点，`VALUE` envelope 为 0；
- `source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、非 Gold、非 Patch；
- 不复用既有树的节点名、路径、稳定 ID、场景文本或生成蓝图正文；
- 先冻结 36 条候选，最多审核并选择 28 条执行集；
- 28 条固定为 20 个有目标、4 个 hard negative、4 个显式空目标；
- 20 个有目标包含 10 个非字面、4 个词面基线、3 个边界变化、3 个跨分支干扰；
- 非字面覆盖同义表达、缩写、口语目的表达、轻微错别字和跨层表达，但不围绕 H1
  已知漏例造同构题；
- Oracle 与目标只供本地评分，禁止进入模型输入。

数据冻结后、任何 H2 embedding 前运行 R2 A 基线。若 A 的 Recall@20 高于18/20，或
非字面 Recall@20 高于8/10，则该集合无法验证“增加2条”，使用
`H2_DATASET_NOT_DISCRIMINATIVE` 停止；不得看 H2 结果后改写场景。

## A/B 与门槛

- A：冻结 R2 lexical leg；
- B：同一输入、Silver 角色、树与 Oracle上的 R2 + H2 BGE vector leg；
- 仅首次完整有效 B 运行进入资格判断；传输、依赖、模型加载或合同失败不构成能力
  结果，但修复只能恢复相同冻结 profile；
- 不使用 H1 百炼模型作第三组，不在新集合上比较多个本地模型。

B 必须同时满足：

1. 总 Recall@20 至少18/20，且比 A 至少多2条；
2. 非字面 Recall@20 至少8/10，且比 A 至少多2条；
3. 总 Recall@8 与 MRR 均不低于 A；
4. 4条 hard negative 的排除目标均不进入 Top-8；
5. 4条显式空目标状态均正确；
6. 4条词面基线 Recall@8 相对 A 最多下降1条；
7. 本地 embedding 对相同 model text 逐字节输入产生一致的规范化向量摘要；
8. 融合候选重放28/28；
9. 聚合报告只含固定 code、计数、指标和本地运行时聚合，不含文本、节点、Oracle、
   路径、向量、模型文件清单或机器身份。

本机工程指标记录模型加载时间、索引时间、query P50/P95 与峰值 RSS，只作为部署
估算，不作为跨机器能力门槛。OOM、单次完整运行超过30分钟或进程异常退出时，H2
记录为工程不可行，不改 batch、精度或模型后重跑同一数据作资格结果。

## 实现顺序与停止规则

1. 独立数据任务先物化、审核并冻结新树与28条执行集；
2. 计算并记录 A 基线，检查可判别性；
3. 在无语义固定文本上安装并验证隔离本地运行时、权重 revision/SHA和批大小；
4. 实现独立 H2 profile/index/Provider 合同与 mock 测试；
5. 只运行一次完整有效 Silver A/B；
6. PASS 才冻结本地混合候选并准备新的未见确认；FAIL 则停止 embedding 模型轮换。

H2 FAIL 后不得在同一28条上尝试 BGE base/large、Qwen、另一 instruction、维度、
量化、权重、窗口或 reranker。如要继续，必须另立单一变量合同和新开发分母。
