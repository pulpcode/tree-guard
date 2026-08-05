# Semantic P1：关系判定与动作策略收缩结果

## 结论

首次有效冻结运行判定为 `RELATION_ONLY_POLICY_VIABLE`。在完全复用同一批模型逐候选
关系判断、且模型调用为 0 的条件下，确定性动作策略把首选匹配从 19/51 提高到 41/51，
其余 10/51 均为安全退让；不安全动作 0，确定性重放 51/51。

这支持 Shadow MVP 将“候选关系判断”留给 Semantic，把“动作、目标空值和安全降级”
交给本地 Policy。它不证明关系模型已经达到生产要求，也不评价 H2 Retrieval。

## 冻结结果

- 质量：`CODEX_ASSISTED_SILVER / CALIBRATION_ONLY`；
- 有效分母：51；
- 新模型调用：0；
- A（模型关系 + 模型动作）：
  - `PREFERRED_MATCH=19`；
  - `SAFE_ALTERNATIVE=32`；
  - `UNSAFE_MISMATCH=0`；
- B（模型关系 + 确定性动作）：
  - `PREFERRED_MATCH=41`；
  - `SAFE_ALTERNATIVE=10`；
  - `UNSAFE_MISMATCH=0`；
- 迁移：
  - 首选→首选：19；
  - 安全退让→首选：22；
  - 安全退让→安全退让：10；
- 完整三轮场景：15；三轮输出稳定：15；
- 相同输入确定性重放：51/51；
- 全部门槛通过。

## 解释

M4.9 当前模型动作主要在 `USE_EXISTING_NODE` 与 `NEED_CLARIFICATION` 之间选择。P1
忽略动作字段后，依据模型已经给出的等价关系和本地结构兼容性选择直接复用；没有等价
证据时采用 Oracle 可接受的 `ABSTAIN` 安全退让。22 个观测从安全退让转为首选，说明
当前动作层存在明显的过度澄清，而不是必须依靠模型才能作出更好的动作选择。

本轮没有把 `CONTEXTUALLY_RELATED` 或 `REUSES_CONTRACT` 自动映射成新增动作，因为当前
Silver Oracle 没有为这些新增权限提供足够覆盖。它们应暂时作为人工审查信号，待独立
Oracle 和未见数据覆盖后再决定是否开放。

## 边界

- 这是已暴露 M4.9 数据上的开发期架构消融，不能作为泛化或生产资格；
- 结果依赖现有关系标签，不能推出关系模型的准确率已经足够；
- 41/51 中包含安全空目标的正确 `ABSTAIN`，不能把全部提升解释为目标节点定位提升；
- 当前只证明模型动作字段没有显示不可替代增益，并且在该分母上显著劣于确定性策略；
- 不修改现有 v1 Semantic 合同和生产入口，先形成下一版本候选合同与迁移测试。

## 后续决策建议

形成 Decision D3 候选：

1. 下一版本 Semantic 模型输出只保留逐候选 relation、reason 和证据充分性；
2. 本地 Policy 负责 selected candidate、action、空目标和安全降级；
3. 直接复用只允许唯一且结构兼容的 `SEMANTICALLY_EQUIVALENT`；
4. 多个等价候选转为结构化澄清状态，不让模型任意选择；
5. `REUSES_CONTRACT`、`CONTEXTUALLY_RELATED` 暂不自动授权新增；
6. 人工审查、非 Gold、非 Patch 边界保持不变。
