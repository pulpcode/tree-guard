# 消防领域三档验证数据

## Goal

在独立 worktree 中，为 TreeGuard 治理闭环准备小型、中型和大型三档完全虚构、
可复现的消防主题验证数据，覆盖意图理解、候选召回、受约束语义建议、失败隔离
和模型诊断安全，并为每个场景提供可机器判定的预期结果。

## What I already know

- 数据主题选定为消防领域，但不得复制真实信息树、真实节点字段名、`VALUE`、
  专家文本、模型请求/响应、内部标识、路径或稳定映射。
- `schema-flow` 只可作为待核验的本地参考来源；来源、许可和敏感性未确认的内容
  不得导入本仓库。
- 当前 TreeGuard 已有确定性意图、候选召回、Top-8 语义建议、人工复核、
  旁路记录、2,001 节点仿真树和开发期模型诊断能力。
- 本任务使用独立分支 `codex/fire-domain-test-data`，基于提交 `fb0c0a3`，
  不包含主 worktree 的未提交改动。

## Assumptions

- 三档采用 31、401、2,001 个节点，分别面向精确合同断言、语义干扰验证和规模
  稳定性验证，而不是简单复制同一模板扩容。
- 场景数采用 8、16、24，并允许同一树服务多个确定性验证场景。

## Requirements

- 小型数据用于精确合同断言与人工检查。
- 中型数据包含同义表达、近名干扰、局部与全局候选竞争以及类型/基数冲突。
- 大型数据至少覆盖当前 2,001 节点工作台规模，并保持确定性生成和重排稳定。
- 场景覆盖清晰意图、一次澄清后解决、一次澄清后停止、无信号、无候选、
  Top-8 越界拒绝、人工接受/拒绝和模型故障诊断。
- 所有数据从批准 Schema 和公开概念正向构造，不从任何真实树做删减、改名或
  稳定伪名化。
- 所有机器 oracle 表述为合同预期或可接受集合，不宣称 Gold、语义批准或
  Patch 资格。
- manifest 明确标注 `precision_contract`、`semantic_interference` 和
  `scale_stability` 三种 benchmark role，避免把规模压力数据误作语义主基准。
- 采用来源方案 A：`schema-flow` 只提供公开的方法总结和失败教训；高层覆盖类别
  参考权威公开来源，节点名称、层级、需求和模型输出全部独立虚构。
- fixture 使用明显虚构的组织、设施和自造术语表达消防功能形状，不复制真实消防
  标准术语清单、工程参数、真实字段或真实业务结构。

## Acceptance Criteria

- [x] 小、中、大三档数据可由固定输入确定性重建。
- [x] 每档包含清单、用途、节点数量、场景数量和预期验证项。
- [x] 小型场景可对意图状态、候选和最终状态做精确断言。
- [x] 中型场景覆盖语义干扰与召回排序边界。
- [x] 大型场景覆盖 2,001 节点闭环、重排稳定性和有界输出。
- [x] 诊断场景覆盖非法 JSON、多余字段、缺失字段、超时、429/500、重试、
  截断和虚构泄漏 canary。
- [x] 最终工件扫描不含凭据、真实字段名、内部路径、原始日志或来源不明内容。

## Definition of Done

- Tests added/updated。
- `uv sync --frozen`、配置的 Python `unittest`、适用前端测试/构建和
  `git diff --check` 通过。
- 未配置的 lint、typecheck、coverage 或 CI 不报告为已通过。
- 数据生成方法、场景合同、限制和非 Gold 边界有准确文档。
- 实际 diff 通过 `trellis-check` 审查并自修。
- Git 暂存和提交只在用户明确批准后执行。

## Out of Scope

- 真实消防信息树、真实项目资料、真实专家文本或生产数据导入。
- 把 `schema-flow` 的现有树、期望值、训练 JSONL、模型缓存或 Git 历史直接复制
  到本仓库。
- 生产 Patch、Gold 标注、embedding、向量数据库或生产效果声明。
- 访问 `schema-flow` 的 `.env`、凭据历史、模型原始响应和诊断缓存。

## Technical Notes

- 适用规范：
  `.trellis/spec/backend/development-data-boundary.md`、
  `contracts-and-determinism.md`、`governance-intake-and-retrieval.md`、
  `quality-guidelines.md`、`directory-structure.md` 和跨层思考指南。
- 现有生成入口：`src/treeguard/simulator.py::build_fictional_tree`。
- 现有集中 fixture：`tests/fixtures/fictional/tree_export.json`。
- `schema-flow` 自述同时包含构造样本、消防专项和历史凭据风险，因此必须先做
  来源级筛选，不能把“当前文件可读”等同于“允许派生导入”。

## Research References

- [`research/fire-domain-sources.md`](research/fire-domain-sources.md) —
  `schema-flow` 只用于方法教训；主题语义回到权威公开来源重新取材并独立虚构。

## Feasible Approaches

### A. 公开概念重新取材并独立构造（推荐）

- 只借鉴 `schema-flow` 的分层方法和失败教训。
- 从权威公开来源提取高层主题，不复制条文、树、expected 或节点集合。
- 许可、数据污染和真实字段泄漏风险最低。

### B. 直接派生 `schema-flow` 的消防构造树

- 可以更快得到丰富字段，但该仓库没有许可证，现有资产已被多轮消费。
- 容易把既有偏差、稳定映射和评测污染带入 TreeGuard。

### C. 从真实消防材料脱敏派生

- 可能更接近真实分布，但当前没有最终字节审批和用途绑定。
- 不符合本外网任务的数据边界，不纳入当前实施。

## Decision (ADR-lite)

**Context**：用户希望参考 `schema-flow` 的消防内容，但该仓库没有许可证、现有
评测资产已被开发过程消费，TreeGuard 规范也禁止把真实消防字段或其稳定伪名写入
fixture。

**Decision**：采用方案 A。只复用公开的方法论结论，公开资料仅决定“预防、告警、
疏散、设施、训练、初起处置”等高层覆盖类别；实际数据使用自造术语、虚构设施、
虚构组织和虚构事件从零构造。

**Consequences**：数据可安全进入外网仓库并验证当前合同，但不能用于声明真实消防
schema 兼容性、工程规范符合性或生产准确率。

## Verification Evidence

- 三档节点/场景数量：31/8、401/16、2,001/24。
- 聚焦 `unittest`：7 tests passed。
- 全量 Python `unittest`：196 tests passed。
- 前端 Vitest：1 file、5 tests passed。
- 前端 TypeScript + Vite build：通过；保留既有大 chunk 警告。
- 七个 JSON 均通过标准库 JSON 解析，合计约 1.64 MB。
- `git diff --check` 与凭据模式扫描无发现。
