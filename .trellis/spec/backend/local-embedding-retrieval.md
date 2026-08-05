# 本地稠密向量召回规范

## Scenario：隔离的本地 embedding 候选

### 1. Scope / Trigger

新增或更换本地 embedding 模型、tokenizer、pooling、instruction、索引或混合召回
实验时适用。目标是让模型运行时、检索算法和评测数据分别可冻结、可归因；开发期
PASS 不自动替换默认产品召回，也不代表生产资格。

### 2. Signatures

```python
LocalBgeH2EmbeddingProvider.from_local_snapshot(snapshot_dir, *, batch_size)
build_h2_index_with_provider(provider, tree) -> H2EmbeddingIndex
build_h2_query_embedding_with_provider(provider, document) -> H2QueryEmbedding
build_h2_candidate_set(evidence, request, confirmation, tree, *,
    profile, index=None, query_embedding=None, max_candidates=20)
read_private_h2_embedding_index(path, tree, profile) -> H2EmbeddingIndex
write_private_h2_embedding_index(path, index) -> bool
```

正式实验 runner 必须有相互排斥的 `--preflight-only` / `--live`；live 还必须显式
提供执行批准、冻结快照、一个 index input 或 output，以及私有逐项结果路径。

### 3. Contracts

- profile 精确绑定 model ID、revision、权重摘要、模型文件 manifest 摘要、维度、
  tokenizer 上限、pooling、normalization、dtype、device、query instruction 和 batch；
- node passage 与 query instruction 分离，查询 instruction 不得污染索引文档；
- 可以复用已冻结的公共节点/查询文档表示和固定 RRF 纯函数，但新的模型 profile
  必须使用独立 profile、index、query embedding 和 candidate-set 版本；
- 索引绑定可信树快照、每个节点文档摘要和 profile；读取时从可信树重新生成文档集；
- 本地 Provider 只从校验后的本地快照加载，`local_files_only=true`、
  `trust_remote_code=false`，默认项目依赖不得为一次实验强制加入 torch/transformers；
- Oracle 只在全部召回完成后进入本地评分，不得进入文档、query、Provider 或公开报告；
- 索引和逐项结果为 `0600`、不可覆盖私有文件。stdout 只含固定版本/code、计数、
  指标和运行时聚合，不含文本、节点、路径、向量、Oracle 或绑定摘要。

### 4. Validation & Error Matrix

| 条件 | 处理 |
|---|---|
| 快照 revision、文件或权重不匹配 | `H2_LOCAL_SNAPSHOT_INVALID`，推理次数为 0 |
| profile 字段、batch 或摘要漂移 | `H2_PROFILE_ARTIFACT_INVALID` |
| index 与树、文档或 profile 不同源 | `H2_INDEX_STALE` |
| query 与文档或 profile 不同源 | `H2_INDEX_STALE` |
| 向量数量、维度、有限性或规范化输出非法 | `H2_LOCAL_OUTPUT_INVALID` |
| 有检索信号但缺 index/query embedding | `H2_EMBEDDING_REQUIRED` |
| 无向量信号却注入向量工件 | `H2_UNEXPECTED_VECTOR_INPUT` |
| preflight 携带 live 输出或模型参数 | `H2_B_PREFLIGHT_OUTPUT_FORBIDDEN` |
| live 缺执行批准或精确路径组合 | `H2_B_EXECUTION_NOT_APPROVED` |
| 相同 query embedding 重放不一致 | `H2_B_EMBEDDING_REPLAY_MISMATCH`，不形成能力结果 |
| 运行超过预注册时间上限 | `H2_B_ENGINEERING_TIMEOUT`，不形成能力结果 |

### 5. Good / Base / Bad Cases

- Good：冻结 profile 构建私有索引，query 使用同一 profile，固定 RRF 只融合两个
  Top-40 leg，公开输出只显示 Recall/MRR、安全计数与运行时聚合。
- Base：`--preflight-only` 重放词法 A 与全部门槛，既不加载模型，也不创建输出。
- Bad：用新模型读取 H1 索引、把 query instruction 加入 node passage、根据准确率
  调整 batch/instruction，或把 index hash 和逐项节点输出到 stdout。

### 6. Tests Required

- profile 精确字段、bool-as-int、revision/权重/文件篡改和摘要漂移；
- 文档稳定 batch、query-only instruction、输出数量/维度/有限性和相同输入重放；
- index `0600`、symlink/公开权限/覆盖拒绝、树/profile/重算摘要篡改；
- H1 回归，证明公共 RRF 抽取不改变旧候选结果和错误码；
- B runner 缺批准在模型加载前失败，预检不调用 Provider，公开报告 canary 不含
  `text`、节点、路径、Oracle、向量和任何 source/index/profile hash；
- A/B 使用相同冻结分母，逐项结果只写私有工件，全部预注册门槛都有正反例。

### 7. Wrong vs Correct

Wrong：

```python
index = read_h1_index(path, tree)
provider = LocalModel("latest")
print({"index_hash": index.index_hash, "cases": private_cases})
```

Correct：

```python
provider = LocalBgeH2EmbeddingProvider.from_local_snapshot(
    frozen_snapshot, batch_size=16
)
index = read_private_h2_embedding_index(path, tree, provider.profile)
report = run_aggregate_only(index=index, provider=provider)
assert "source_index_hash" not in report
```
