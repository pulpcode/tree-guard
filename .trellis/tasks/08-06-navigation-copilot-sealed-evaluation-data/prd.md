# 构建导航 Copilot 密封 clean-room 数据

## Goal

独立构造一棵未参与当前产品调参的虚构 resource 信息树，以及 Navigation Copilot 密封资格
测评所需的公开 scenario、隐藏 Oracle、Codex Silver 审核和冻结 preflight；数据任务不运行
被测链路，不接触模型结果，并在功能测评提交冻结后才允许交接执行。

## What I already know

- 父任务已接受 48 条主分母与 16 条挑战重复子集；
- 现有 H1/H2、M4/M5、M4.9、R2、fire validation 和青岚请求/Oracle 均已参与生成、审核、
  实验或调试，只能作为禁读/相似性边界，不能复用为最终资格样本；
- 本项目独立构造且 manifest 证明为 clean-room 的完全虚构数据可调用外部 LLM，但隐藏 Oracle
  仍不得进入被测模型输入；本任务本身不调用被测模型；
- 数据可由 Codex 审核为 Silver，但不得声称 Gold、专家共识、生产或 Patch 资格。

## Requirements

- 从空白独立构造 700—1,000 节点 resource 树，`VALUE` envelope 为 0，来源固定为
  `CLEANROOM_SYNTHETIC / fictional=true / derived_from_real=false`；
- 树包含 6—10 个语义连贯顶层分支、4—6 层深度、同层近邻、跨分支近义、节点种类冲突、
  值类型/基数冲突和多个可接受目标；
- 禁止使用“维度列表 × 指标列表”笛卡尔积扩充节点；每个子树必须来自独立蓝图并可解释
  父子语义；
- 最多生成 56 条候选，冻结精确 48 条：字面唯一 10、非字面唯一 10、结构干扰 8、多个
  可接受目标 4、合法澄清 6、弱证据目标 4、树中无目标 6；
- 非字面精确覆盖同义、缩写、口语目的、轻微错别字和跨层表达各 2 条；
- 预注册 8 条错误/无关页面上下文压力项；从非字面、结构干扰、澄清和弱证据各固定 4 条，
  形成 16 条重复性子集；标签不改变主类别配额；
- scenario 与 Oracle 物理分离。公开 scenario 只含 runner 必需的请求、显式 hints、页面上下文
  和合法澄清时的冻结回答，不含目标、期望状态或评分答案；
- Oracle 至少绑定 scenario/树/请求、期望路线、可接受结构 profiles、目标存在性、可接受目标
  集、干扰目标、澄清策略、Policy 状态集合和可接受终态联合元组；
- 全部候选由 Codex 按固定 rubric 审核自然性、树内可回答性、唯一/多目标/空目标语义、主
  现象单一性和 Oracle 一致性；最多两轮修订；
- 冻结选择只依据预注册类别、审核状态和候选序号，不得读取或运行当前 Copilot、Prompt、
  Retrieval、Semantic、Policy、H1/H2/M4/M5 逐项结果来挑选“刚好困难”的样本；
- manifest、公开数据、隐藏 Oracle、Silver 审核和 preflight 均绑定规范字节与提交；冻结后
  发现实质错误即整批停线，不热修后继续同一资格 run；
- 所有数据固定 `gold_eligible=false / patch_eligible=false / production_qualification=false`。

## Acceptance Criteria

- [ ] 树节点数在 700—1,000，0 VALUE，Schema 适配通过，节点存储重排不改变规范 digest；
- [ ] 生成器重复运行字节确定，且未读取既有 fixture/scenario/Oracle/Prompt/实验结果；
- [ ] 不存在笛卡尔积命名、无语义 filler、未知父节点、重复 sibling label 或不一致节点合同；
- [ ] 候选不超过 56，冻结精确 48，类别为 10/10/8/4/6/4/6，目标存在/空目标为 42/6；
- [ ] 10 条非字面五类各 2，8 条错误上下文和 16 条重复子集按预注册顺序冻结；
- [ ] 48/48 完成 Codex Silver 审核且零 blocking finding，审核不得产生 Gold/专家声明；
- [ ] Oracle 目标均存在于同一可信树或在空目标 case 中严格为空，多目标与干扰集合无非法
  重叠，路线/Profile/Policy/终态联合约束一致；
- [ ] canary 证明 Oracle、目标 node ID、期望状态和评分答案不进入公开 scenario、模型输入
  构造或 manifest 公共视图；
- [ ] preflight 拒绝来源、节点规模、VALUE、配额、类别、重复子集、审核、Oracle、hash、
  权限、额外字段、bool-as-int 和冻结字节篡改；
- [ ] 数据提交不包含模型请求/响应、Prompt、实验结果、真实材料或受保护路径。

## Definition of Done

- 仅运行数据任务白名单测试、Trellis validate 和 `git diff --check`；禁止递归/完整 suite 在
  clean-room 构造主体中意外读取既有实验材料；
- 数据内容、审核和 preflight 独立提交，Git index 为空，未 push/merge；
- 数据提交完成后停在交接门，不运行 R0/C1、Simulator、百炼、Qwen、Semantic 或任何效果
  评分；
- 最终资格运行必须等待功能测评提交、execution manifest 和显式批准。

## Out of Scope

- 不实现或修改 Navigation Copilot、Provider、Prompt、召回、Semantic、Policy、API 或 UI；
- 不运行当前产品链路、模型、R0/C1 或查看任何逐项实验结果；
- 不复用现有请求/Oracle，不把真实数据删除 VALUE 或改名后作为 clean-room；
- 不声明 Gold、生产资格、真实用户效果或生产 Shadow 通过。

## File Ownership

数据分支独占新 fixture 目录、确定性数据生成器、数据 preflight、数据专属测试和本任务目录。
不得修改功能子任务、当前 Copilot 核心、现有 fixture/manifest、Provider、Prompt 或完整测试
配置。具体路径在开始实施前冻结，避免与功能分支冲突。

## Research Reference

- [`../08-05-governance-navigation-copilot-shadow/research/sealed-fictional-e2e-evaluation-plan.md`](../08-05-governance-navigation-copilot-shadow/research/sealed-fictional-e2e-evaluation-plan.md)
