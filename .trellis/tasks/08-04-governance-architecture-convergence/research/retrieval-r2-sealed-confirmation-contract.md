# Retrieval R2 未见密封确认合同

## 决策目的

本合同在停止 M5 暴露集调参后，使用一棵新构造、未进入 B1–B3、R1、R2 或角色模型
实验的信息树和未见请求，独立回答两个问题：

1. 冻结 v2 角色抽取加 R2 边界容忍词法召回是否能在未见数据上复现有效 Top-K；
2. 失败是否集中于 R2 已声明不解决的非字面表达，从而为后续向量/混合召回提供明确
   升级证据。

本实验不比较尚未冻结的向量或混合算法，不测试 Semantic 或动作选择，不宣称生产资格。

## 隔离与提交绑定

- 功能分支先冻结并提交当前角色合同、v2 Prompt、R2 算法和 sealed runner 合同；
- 数据在独立 worktree/分支构造，绑定功能提交 hash；
- 功能实现者在数据冻结前不得读取请求、目标、Oracle 或审核正文；
- 数据分支只交付 clean-room manifest、完整 fixture、隐藏 Oracle sidecar、审核记录、
  preflight 和精确 SHA-256 绑定；
- runner 首次读取正式请求即视为密封解除；此后不得修改 Prompt、模型、R2 权重、
  n-gram、分母、Oracle 或门槛；
- 首次结果无论 PASS/FAIL 都永久记录为首次结果，失败不得覆盖；
- 请求、模型响应和隐藏目标不写入 Git/Trellis/公开报告；完整执行工件只允许进入
  `0600` 私有临时目录。

## 数据形状

使用一个与现有 M5 标签、场景和生成蓝图独立的同领域 clean-room 虚构数据集：

- `source_class=CLEANROOM_SYNTHETIC`；
- `fictional=true`、`derived_from_real=false`；
- `gold_eligible=false`、`patch_eligible=false`；
- 语义树建议300–800节点；生产上限约2,000节点由已有确定性规模回归覆盖，不把语义
  盲测扩成无意义的大树压力测试；
- 不复用 M5 请求、TARGET/SCOPE/EXCLUSION span、稳定节点 ID、节点标签或 Oracle；
- 不从 R2 结果反向选择“容易命中”的请求。

正式执行集固定28条：24条有可接受目标、4条显式空目标。数据分支最多准备36条候选，
冻结前按覆盖合同选择28条；不得在看到模型结果后替补。

### 有目标覆盖

24条至少满足：

- 6条词面直接但结构/parent 不同的基线请求；
- 6条自然 super-span、sub-span 或外围限定语边界变化；
- 4条跨分支同词、近名、scope 干扰或错误 parent；
- 4条带显式 EXCLUSION 的 hard negative；
- 4条常见同义改写、缩写或无完整标签短语的非字面表达。

同一条可以同时带结构风险，但每条只能有一个主覆盖类别。非字面请求必须由请求自身
可理解的常见语言关系支持，不允许在隐藏 Oracle 中发明模型不可见的私有别名词典。

## Oracle 与审核

- 每条保存稳定可接受 node ID 集、允许状态、主覆盖类别、角色 Silver 和审核结论；
- TARGET/SCOPE/EXCLUSION 必须只依据请求正文标注，再单独核对目标，避免用 Oracle
  反向截取与节点标签一致的 span；
- Codex 可做全量 Silver 工程审核，固定为非 Gold、非生产 gate；
- 首次密封结果只能决定架构路径。进入生产 Shadow 前，28条 Oracle 和角色边界必须由
  领域人工全量复核，或另建正式 Gold 资格集；
- Oracle 变更必须产生新版本和新 digest，不得静默覆盖首次分母。

## 冻结执行

模型固定 `qwen3.6-35b-a3b`、v2 Prompt、temperature 与 thinking 现有配置。每条允许
首次调用和一次合同纠错重试，不允许语义重试。角色证据通过本地 source binding 后同时
送入 R1 和 R2；R1 只作诊断对照，R2 是唯一 gate。

运行两轮相同冻结请求：

- 两轮之间不修改任何字节或配置；
- 每轮分别报告合同、Recall@8/20、MRR、空目标、hard negative 和固定视图；
- 同时报告两轮 R2 指标是否一致，不持久化逐条模型响应；
- 第一轮是首次密封结果，第二轮只验证重复稳定性，不能把较好一轮挑作结论。

## 固定指标与门槛

每轮必须满足：

- 最终角色合同通过28/28，传输失败0；
- `V_REQUIREMENT_ONLY` 与 `V_FREE_TEXT_DROPPED` Recall@8至少22/24；
- 两个主视图 Recall@20至少23/24，MRR至少0.80；
- `V_CANONICAL` Recall@8至少22/24；
- `V_PARENT_ABSENT` Recall@8至少21/24；
- `V_PARENT_WRONG_BRANCH` Recall@20至少22/24；
- 4个 explicit-empty 正确状态=4/4；
- 4个 EXCLUSION hard negative 不得把被排除目标排入Top-8；
- 本地确定性候选重放28/28；
- 聚合报告不含请求、span、节点/场景身份、hash、Oracle 或模型文本。

两轮均须满足上述门槛；不得对两轮取最佳值。非字面主类别另报 Recall@8/20，但不为其
单独降低总门槛。

## 决策规则

- 两轮 PASS，且非字面类别 Recall@20至少3/4：冻结 R2 为 Shadow 候选生成方案，下一步
  收敛 Semantic 只判候选关系、本地 Policy 选动作；仍需人工 Gold 或生产 Shadow 数据；
- 两轮总门槛 PASS，但非字面 Recall@20低于3/4：R2 只可作为 lexical leg，下一步在新
  开发集实现向量/混合召回，不直接晋升为唯一生产召回；
- 任一轮 Recall、空目标或 hard-negative 门槛 FAIL：R2 不晋升，停止词法调参，转向
  向量/混合候选；
- 仅合同失败：归因到角色抽取稳定性，不改 R2；冻结 v2 Prompt 仍不在本集合调整；
- 两轮结论不一致：判定重复性不足，保持 FAIL；不得增加第三轮选择较好结果。

## 停线条件

数据来源/分类、树 digest、功能提交、Prompt/模型配置、scenario/Oracle digest、分母、
首次结果记录或私有输出权限任一不匹配，模型调用前停线。运行中出现未计划请求体、超过
两次调用、Oracle 进入模型输入、原始流量进入仓库或聚合泄漏，立即停线且本轮无资格。
