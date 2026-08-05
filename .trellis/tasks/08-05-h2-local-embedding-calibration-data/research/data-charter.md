# H2 本地 embedding 数据 Charter

## 目的与范围

本数据集只用于开发期检验新分母对冻结 R2 lexical A 是否具有足够区分度，并为后续
单一 H2 本地 embedding profile 提供同一冻结输入。它不用于训练、模型选择、Gold
标注、生产资格或 Patch 决策。

## 来源声明

* 从空白独立构造一棵完全虚构的消防治理 `resource` 树；不从真实、受保护、外部
  导入或现有 fixture 改写。
* 固定声明：`source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`gold_eligible=false`、`patch_eligible=false`。
* 规模目标 600–900 节点；`VALUE` envelope 固定为 0。
* 新生成器使用本任务独有 seed、namespace、稳定 ID 规则和声明式拓扑参数；不得读取
  现有树、场景、Oracle、生成器或实验临时文件作为输入。

## 独立性与禁读边界

允许的功能研究只有：

* `.trellis/tasks/08-04-governance-architecture-convergence/research/retrieval-h2-local-pre-registration.md`
* `.trellis/tasks/08-04-governance-architecture-convergence/research/retrieval-h2-local-embedding-options.md`

禁止读取 H1 scenarios、Oracle、生成器正文、逐项结果、H1 预注册/结果研究正文；禁止
读取 R2 密封请求、Oracle、私有工件、逐项结果；禁止读取 `/private/tmp` 既有实验
工件；禁止运行会间接加载这些材料的完整或递归测试。

项目 `AGENTS.md`、固定 Trellis spec index、适用规范、当前任务 research 与任务范围
源码不是功能研究，可为合同与实现路由读取，但不得借此加载禁读数据正文。

## 数据角色与许可

* 数据可由 Codex 按固定 rubric 审核为 `CODEX_SILVER_REVIEWED`。
* Silver 只表示开发期一致性审核，不表示 Gold、专家共识、生产能力或 Patch 资格。
* Oracle 只供本地评分，不属于模型输入。
* clean-room 常设 LLM 授权不扩大本任务范围；数据分支仍不得安装或调用 embedding。

## 生命周期

```text
Charter/蓝图/Oracle 设计获批
→ 空白确定性生成
→ 数据专属 preflight
→ 按 12/5/4/5/5/5 精确生成并冻结 36 条未评分候选
→ Silver rubric 审核
→ 按固定配额冻结 28 条
→ 规范摘要绑定全部冻结工件
→ 只运行 R2 lexical A
→ 可判别性通过则只交接，不在本分支运行 B
```

Silver 拒绝导致任一冻结配额不足时立即停线，不补造候选、不跨类别借位。任何召回
结果出现后都不得改写冻结树、场景或 Oracle。冻结后发现内容错误时，本次分母停止并
作废；不得用热修数据继续资格判断。

## 工件与公开边界

计划持久化 Charter、覆盖蓝图、树、候选、冻结执行集、隐藏 Oracle sidecar、Silver
审核、manifest、preflight 聚合和 A 聚合。manifest 公共视图与 A 聚合不得包含场景
文本、节点名、路径、稳定 ID、Oracle、逐项结果、向量或机器身份。

树、场景和 Oracle 是本仓库 clean-room fixture，不是生产 sidecar；Oracle 与未来模型
投影必须物理分离。规范摘要只证明字节完整性与来源绑定，不证明身份或资格。

## 失效条件

以下任一项使数据集不能冻结或继续：来源声明缺失/漂移、节点规模越界、出现 VALUE
envelope、读取依赖指向既有数据、候选总数不是 36、候选类别不是
`12/5/4/5/5/5`、审核后冻结配额不足、Oracle 泄漏、Silver rubric 未完成、摘要
不一致、冻结后改写，或 A 命中超过预注册可判别性上限。
