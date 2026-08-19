# Retrieval R2 边界容忍角色召回预注册

## 单一问题

R2 只回答：在小模型已经给出合法、原文绑定且角色基本正确，但 TARGET 是人工
Silver 的 super-span 或 sub-span 时，一个不依赖完整短语门禁的确定性词法表示，能否
恢复冻结 Top-K 指标。

- 数据仍是已经暴露的 M5 clean-room 虚构校准集；
- 复用 v2 Prompt、同一模型输出合同与18条固定分母，不再修改 Prompt；
- 只改变 R1 角色证据到候选的映射，不修改 Intent、节点源字段、Semantic、Policy、
  Provider、模型版本或生产入口；
- 本实验是 calibration-only 架构选择，不是未见确认或生产资格。

## 冻结算法

算法版本固定为 `treeguard.boundary-tolerant-role-lexical-retrieval.v1`：

1. 角色 span 与节点的 `name`、`label`、逐级 `path_labels` 均使用 NFKC、casefold；
2. 中文使用连续字符二元组，单字 span 才保留单字；ASCII 使用完整字母数字词项；
3. 每个 span 与每个节点字段使用整数 Dice 相似度，取名称字段最大值和路径标签最大值；
4. 多个 TARGET 分别计算后取最大值；TARGET 名称相似度权重 30,000,000，路径相似度
   权重 15,000,000，不再设置完整 TARGET 命中硬门禁；
5. TARGET 名称和路径相似度都为零时，候选不得入围；
6. SCOPE 只软加权，名称权重 2,000,000、路径权重 5,000,000；
7. EXCLUSION 保持 R1 的规范化完整连续短语排除，不在本轮放宽；
8. 保留 B1 基础分和最多100个开发期候选池，最终按整数总分降序、稳定 node ID
   升序，截断为 Top-20；
9. 输出继续固定 `embedding_used=false`、`allows_addition=false`，所有来源漂移和非法
   角色合同 fail closed。

本版本明确不解决同义词、缩写、跨语言或完全无字面重合；若边界容忍仍失败，不在本
集合继续调权重或 n-gram，转入稠密向量或混合召回方案。

## 固定分母与门槛

复用 Oracle v2、18个 `PROCEED`（16个有目标、2个 explicit-empty）、五种视图及每项
三次重放。首先用 Codex/Silver 角色证据做回归上限，再用冻结 v2 Prompt 的小模型角色
证据做真实 R2 运行。

小模型 R2 晋升门槛沿用 R1 门槛：

- `V_REQUIREMENT_ONLY` 与 `V_FREE_TEXT_DROPPED` Recall@8=16/16；
- 两个主视图 MRR 至少0.90；
- `V_CANONICAL` Recall@8=16/16；
- 五个视图 explicit-empty 正确状态=2/2；
- `V_PARENT_ABSENT` Recall@8至少15/16；
- `V_PARENT_WRONG_BRANCH` Recall@20至少15/16；
- 所有视图确定性重放18/18；
- 合同通过率、调用预算和聚合泄漏门禁沿用 v2 实验。

Silver R2 必须至少保持 R1 的 Recall@8=16/16、MRR>=0.90、空目标2/2；否则先判定
实现回归，不进行真实模型运行。

## 决策规则

- Silver 与小模型 R2 全部门槛通过：冻结 R2 为候选生成基线；停止使用暴露集合，
  下一步在新未见树上与向量/混合候选做一次独立确认；
- Silver 通过、小模型仅 MRR 失败但 Recall@8 与空目标通过：R2 保持 FAIL，进入受控
  Top-K semantic rerank 责任设计，不回调词法权重；
- 小模型 Recall 或空目标失败：R2 保持 FAIL，停止本集合词法调优，进入向量/混合召回；
- 合同失败：归因到抽取合同，不归因到 R2；仍不得修改 Prompt v2；
- 任一 PASS 只代表已暴露校准集上的架构可行性，不代表泛化或生产资格。
