# M4.6 Silver 评分校准结果

## 范围

- 数据：已揭盲 M4.5 clean-room Silver，仅作校准；
- 模型与 Prompt：保持 M4.5 冻结配置，不重新调用 Intent；
- 观测：三轮共 54 个 `PROCEED` 单元；6 个 `CLARIFY` 场景继续沿用原澄清矩阵，
  不进入本轮召回/Semantic 分母；
- 结论固定非 Gold、非门禁、非泛化证明。

## 离线 A/B

| 指标 | v1 严格评分 | M4.6 校准评分 |
|---|---:|---:|
| Retrieval MATCH | 24/54 | 44/54 |
| Retrieval MISMATCH | 29/54 | 9/54 |
| Retrieval NOT_RUN | 1/54 | 1/54 |
| 新增可达但未执行的 Semantic | — | 20 |

校准后的 44 个 MATCH 包含 20 个 `TARGET_HIT` 和 24 个
`BOUNDED_EVIDENCE`。因此旧分数至少把 20 个“有界证据已准备好”的观测错误地按
“未命中任意冻结 Top-1”短路，不能把原 24/53 直接解释为纯召回能力。

## 补充 Semantic

只对上述 20 个旧短路单元复用原实际 Intent 和确定性候选集，使用冻结模型/Prompt
补充 Semantic；没有重新调用 Intent，也没有修改 policy。20 个单元全部取得模型
合同结果，18 个首发通过、2 个重试后通过。

合并原始与补充观测后的 54 个 `PROCEED` 结果：

| Semantic 分类 | 数量 |
|---|---:|
| `PREFERRED_MATCH` | 12 |
| `SAFE_ALTERNATIVE` | 23 |
| `UNSAFE_MISMATCH` | 7 |
| `RUN_FAILED` | 2 |
| `NOT_OBSERVED` | 10 |

10 个未观测单元来自 9 个校准后仍未命中目标的 Retrieval 和 1 个 Intent 运行失败。
2 个 Semantic 运行失败来自原 M4.5 Provider 连接失败，不是本次补充调用。

补充的 20 个单元中，16 个输出 `NEED_CLARIFICATION`，4 个输出
`ADD_NODE_FROM_CONTRACT`。合并全部观测后：

- `SAFE_ALTERNATIVE` 主要是 hard negative、kind/cardinality 冲突、显式新增、
  multi-acceptable 和 Top-K 场景中的 `NEED_CLARIFICATION`；
- 7 个 `UNSAFE_MISMATCH` 均为 `ADD_NODE_FROM_CONTRACT`：Top-K 边界 3、
  cardinality 冲突 2、显式新增 2。

这里的 `UNSAFE_MISMATCH` 表示“非 Oracle 首选的正向治理动作”，不是已经写入生产或
已发生错误复用；所有产品输出仍是非 Patch 建议。特别是显式新增中的
`ADD_NODE_FROM_CONTRACT` 是否应属于可接受结果，不能因看到模型输出后自动扩宽
Silver Oracle。后续 Codex 辅助 Silver 复核没有发现可接受替代，详见
`m46-codex-silver-action-review.md`；人工 Gold 审核仍未进行。

## 执行环境插曲

第一次补充尝试使用未配置默认 CA 文件的系统 Python，20 个单元全部在连接层返回固定
`BAILIAN_CONNECTION_FAILED`，没有模型草案。无密钥 endpoint 连通性与项目 `.venv`
CA 路径核验后，使用项目冻结运行时原样重试；失败工件保留为 Provider/运行环境诊断，
不计入模型语义结果。

## 结论

1. 评测合同修正产生了实质进展：确认旧 Retrieval 指标混入了 20 个评分语义错误；
2. 模型对复杂场景多数能识别“不应直接复用”，但倾向统一退回澄清，尚不能稳定选择
   首选治理动作；
3. 当前主要瓶颈从“模型是否看到证据”收窄为“复杂场景中的动作决策与澄清边界”；
4. 本轮是开发集校准，不证明泛化。后续只能先做受控 A/B，再在新密封数据上验收。
