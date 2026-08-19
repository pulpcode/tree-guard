# H1 最小混合召回预注册

## 决策目的

R2 未见密封确认两轮 Recall@20 均为 22/24，非字面 Recall@20 均为 2/4，已触发
`VECTOR_OR_HYBRID_REQUIRED`。H1 只回答：在保持 R2 lexical leg、角色合同、Semantic
和 Policy 不变时，增加一个最小稠密向量 leg 能否改善非字面召回且不破坏安全边界。

H1 是开发期架构选择，不是生产资格实验。不得使用已经揭盲的 R2 密封 28 条调整模型、
文档表示、融合参数、阈值或门槛。

## 官方能力依据

核对日期：2026-08-05。

- 百炼文本向量同步 API 支持 OpenAI-compatible `/embeddings`；
- `text-embedding-v4` 支持 64–2048 维，单请求最多 10 条、每条最多 8192 tokens；
- 官方知识库默认使用 `text-embedding-v4` 的 512 维表示；
- 本实验使用普通同步接口，不使用 Batch、知识库、reranker 或向量数据库。

公开依据：

- <https://help.aliyun.com/zh/model-studio/embedding>
- <https://help.aliyun.com/zh/model-studio/text-embedding-v4>
- <https://help.aliyun.com/zh/model-studio/rag-knowledge-base-specifications>

## 固定候选 H1

### 向量模型与接口

- 模型：`text-embedding-v4`；
- 维度：512；
- 编码：`float`；
- 接口：现有百炼 workspace 的 OpenAI-compatible `/embeddings`；
- 每批最多 10 个节点文档；
- 不跟随 redirect、不继承 proxy、凭据只进入 Authorization header；
- 返回必须严格校验字段、index 连续性、数量、维度、有限数和响应大小。

模型 ID、维度、节点表示版本、树摘要任一变化都必须重建索引，不允许混用向量。

### 查询表示

版本固定为 `treeguard.hybrid-query-document.h1.v1`：

1. 原始 requirement text；
2. 经 source binding 的 `TARGET` span；
3. 经 source binding 的 `SCOPE` span；
4. 本地校验的 node kind、value type、cardinality；
5. 可选 parent 只作为现有 R2 的低信任结构 boost，不进入向量硬过滤。

`EXCLUSION`、assumptions、clarification question、模型解释、Oracle 和候选答案不进入
query embedding。EXCLUSION 继续由确定性 lexical/policy leg 处理。

### 节点表示

版本固定为 `treeguard.hybrid-node-document.h1.v1`，从规范树正向构造：

1. 节点自身 name 与 label；
2. 从根到父节点的祖先 name/label 路径；
3. node kind；
4. PROPERTY 的 value type 与 cardinality；
5. 不包含 `VALUE`、审计字段、稳定 ID、后代全文、邻接大窗口、Overlay 或历史案例。

单个文档字符数固定上限 2,000，超过即在 embedding 前失败，不静默截断。

### 向量检索与融合

- vector leg 只有在 source-bound `TARGET`/`SCOPE` 与任一节点文档存在至少一个规范
  token 或中文双字片段锚点时启用；完全无树内锚点时保持 R2 的
  `INSUFFICIENT_SIGNAL`/`NO_CANDIDATES`，不得用无阈值向量 Top-K 制造候选；
- 节点向量和查询向量都校验后做余弦相似度；
- vector leg 取稳定 Top-40；R2 lexical leg 取稳定 Top-40；
- 使用固定 Reciprocal Rank Fusion，不直接混合词法分数与 cosine：
  `score = 1_000_000 // (60 + lexical_rank) + 1_000_000 // (60 + vector_rank)`；
- 某一 leg 未召回节点时，该 leg 贡献 0；
- 按融合整数分数降序、稳定 node ID 升序排序，输出 Top-20；
- 固定参数 `k=60`、两 leg 权重 1:1，本开发切片不调权；
- `allows_addition` 始终为 false；向量失败不得解释为允许新增。

### 失败与降级

- 索引缺失、模型/维度/树/表示版本漂移：`HYBRID_INDEX_STALE`，不使用旧索引；
- 非有限数、错误维度、数量或顺序：`HYBRID_EMBEDDING_RESPONSE_INVALID`；
- 在线 embedding 传输失败：本次 H1 评测失败，不偷偷回退并计作 H1；
- 产品 Shadow 可显式降级到 R2 lexical leg，但必须报告 `HYBRID_DEGRADED_TO_LEXICAL`，
  不得把降级结果算作混合召回成功；
- 任一错误都不得输出节点文本、向量、请求、路径、响应、凭据或异常 message。

## 开发校准数据

H1 不使用 R2 密封 28 条调参。使用单独、公开可见、完全虚构且非 Gold 的开发集：

- 固定 24 条：16 条有目标、4 条 hard negative、4 条显式空目标；
- 16 条有目标中至少 8 条为同义改写、缩写、跨层表达或无完整标签短语；
- 其余覆盖词面基线、边界变化和跨分支干扰；
- 先冻结请求、Silver 角色、可接受目标集合与排除目标，再生成任何向量；
- 数据只用于工程校准，不能宣称泛化或生产资格。

## A/B 与门槛

- A：冻结 R2 lexical leg；
- B：固定 H1 vector leg + R2，以本合同的 RRF 融合；
- 两组使用相同请求、Silver 角色、树、Oracle、Top-K 和重放规则；
- 第一阶段不调用角色 LLM，隔离验证 retrieval；候选通过后才用同一份冻结模型角色
  输出做第二阶段回放，两组不得各自重新抽取角色。

B 必须同时满足：

1. 总 Recall@20 至少 15/16，且比 A 至少多命中 2 条；
2. 非字面 Recall@20 至少 6/8，且比 A 至少多命中 2 条；
3. 总 Recall@8 不低于 A；
4. 4 条 hard negative 的被排除目标均不进入 Top-8；
5. 4 条显式空目标状态均正确；
6. 词面基线 Recall@8 相对 A 最多下降 1 条；
7. 本地融合与候选重放 24/24；
8. 聚合报告只含固定 code、计数和指标。

任一门槛失败即不冻结 H1；不在同一开发集尝试第二组维度、权重、文档窗口、reranker
或 embedding 模型。若需要 H2，必须先写新合同并使用新的开发校准分母。

## 实现顺序

1. 先物化并冻结24条公开开发校准合同；
2. 实现纯确定性的向量校验、余弦排名和 RRF core；
3. 实现受控百炼 embedding Provider 与私有索引工件；
4. 运行 Silver 角色 A/B；
5. 通过后才运行冻结小模型角色重放；
6. 架构冻结后另建未见确认集，不复用开发集作资格证明。

## 数据冻结与 A 基线

24条开发校准数据已在首次生成任何 embedding 前物化并通过确定性 preflight。使用
Silver 角色运行冻结 R2 lexical leg，模型调用为0，聚合结果为：

- 正目标 Recall@8/20：14/16；
- 非字面 Recall@8/20：6/8；
- hard negative Top-8 安全：4/4；
- 显式空目标状态：4/4。

因此原门槛不变时，H1 必须补回2条正目标，使总 Recall@20 达到16/16、非字面
Recall@20 达到8/8，同时保持 hard negative、空目标和 Recall@8 零退化。该集合从此
只允许运行预注册 H1，不用于修改512维、文档字段、锚点门、Top-40、RRF参数或门槛。
