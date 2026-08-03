# M4.7 Semantic 动作政策

## 问题与范围

M4.6 Codex 辅助复核确认 7 条非首选正向动作均不可接受，但错误分为“证据正确、动作
错误”和“证据与动作均错误”。M4.7 只验证一个前瞻式候选政策能否降低这类错误，同时
不让原首选/安全结果退化；它不恢复 holdout、不修改 Oracle，也不声称模型已经泛化。

仓库检查确认 Semantic 投影已经包含确认 Intent 的 subject、scenario、confirmed
facts 和 assumptions。显式空目标约束在当前样本中已进入上述字段，因此本轮不扩展
Intent 或 Semantic Schema。当前 v3 本地结构冲突门禁只约束
`USE_EXISTING_NODE`，Prompt 也没有明确候选排序、业务对象优先和正向动作优先级。

## 方案比较

### 仅改 Prompt

可以改善分支和动作判断，但不阻止模型再次用 `ADD_NODE_FROM_CONTRACT` 绕过显式
结构冲突，安全边界不足。

### 仅加本地门禁

可以确定性拒绝结构冲突，但无法判断同名异分支、不同业务对象或“已存在应直接复用”
等语义问题，覆盖不足。

### 混合政策（采用）

- 保留默认 Semantic v3 和历史草案 replay；
- 新增显式 v4 实验 Provider；
- v4 Prompt 要求先比较业务对象、路径/场景和确认事实，再比较结构字段；候选顺序不
  表示语义优先；已有语义等价候选时使用 `USE_EXISTING_NODE`；
- v4 本地门禁要求 `ADD_NODE_FROM_CONTRACT` 的选中候选与显式
  `node_kind/value_type/cardinality` 兼容；失败沿用
  `SEMANTIC_SELECTED_CANDIDATE_CONTRACT_CONFLICT` 并允许一次完整重试；
- 其他业务语义仍由模型判断，不在本地用关键词或 Oracle 修补输出。

该方案把可证明的结构不变量交给确定性代码，把业务语义留给模型，同时通过 Prompt
版本限定保持 v3 历史工件可重放。

## A/B 冻结合同

- 数据：已揭盲 M4.6 clean-room Silver；
- 分母：校准 Retrieval 为 MATCH 且具备可信 Intent/候选集的 44 个观测；
- A 组：M4.6 已保存的 v3 分类；
- B 组：相同模型、相同 Intent、相同候选集，仅使用 v4 Prompt 与 v4 本地门禁；
- 不重新调用 Intent，不修改召回排序、Oracle 或 M4.6 policy；
- 执行前生成 44 个精确首发请求和每个允许错误码对应的有界重试模板，私有文件绑定
  来源 SHA-256；隐藏 Oracle 只在本地评分，不能进入请求；
- 私有结果保存来源 hash、草案和安全 trace；仓库只保存固定 code 和聚合计数。

候选政策记为 `PROMISING_FOR_SEALED_VALIDATION` 必须同时满足：

1. 重试后最终合同合法至少 43/44；
2. v3 的 `PREFERRED_MATCH` 或 `SAFE_ALTERNATIVE` 不新增
   `UNSAFE_MISMATCH`；
3. v4 `PREFERRED_MATCH` 不少于 v3 的 12；
4. v4 `UNSAFE_MISMATCH` 少于 v3 的 7。

原 7 条错误的迁移、动作分布、首发/重试和合同错误码只作定位指标，不能单独证明政策
有效。即使满足上述条件，也只获得进入新密封数据验证的候选资格。

## 防过拟合边界

- 不为单条 observation、临时候选引用或稳定节点 ID 增加例外；
- 不在当前 7 条上修改 Oracle 或回填 M4.6 主评分；
- 不把统一退回澄清当作无条件改进，必须同时满足首选不下降；
- 当前数据只能做校准回归，最终能力结论必须来自冻结后的新密封数据。
