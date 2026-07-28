# TreeGuard

TreeGuard 是面向大型信息树的语义编译与变更治理助手。

它将建设人员提交的自然语言需求和领域专家的思考，编译为结构化变更意图；在整棵信息树中检索可能复用或冲突的语义；经过人机协作审查后，生成可验证、可审计、可回放的声明式 Schema Patch。

> 当前阶段：TreeSnapshot/TreeDiff/HistoryReview v1、跨业务版本审查、白名单 LLM EvidencePack、受约束 AI 审查草稿和百炼冒烟 Provider 已实现。主运行目标仍是一个文件驱动、无生产写权限的内网 Shadow MVP；外部百炼只用于完全虚构或经明确审批的脱敏样本。

## 为什么做 TreeGuard

现有信息树通常包含 2,000 个以上节点。随着长期迭代，手工建设和维护会产生以下问题：

- 难以全盘发现语义重复、近义和冲突节点；
- 同一业务主体可能出现在不同任务上下文中，字段归属难以判断；
- 历史版本只记录粗略的新增、修改和删除，不能直接作为正确先验；
- 下游邮件模板按 `node_id` 使用节点，但信息树侧缺少完整反向依赖视图；
- 领域专家可能只能描述思路和不确定性，无法立即给出确定分类。

TreeGuard 的目标不是替代专家，而是把变更过程变成一条受约束、可回放、可评测的治理流水线，从源头降低新增语义债务。

## 产品定位

一句话定义：

> TreeGuard 是信息树编辑流程中的增量语义治理门禁：将模糊业务需求和专家思考编译为可审计的变更意图，全树判断已有节点是否可用、字段应归属何处以及是否需要场景扩展，经人工审批后生成安全的版本化 Patch。

TreeGuard 不是：

- 自动生成整棵信息树的工具；
- 通用自然文本抽取系统；
- 可以自由调用数据库和执行写操作的通用 Agent；
- 自动代替领域专家作出最终业务判断的系统。

## MVP 主流程

```text
自然语言需求
→ 变更意图卡
→ 全树候选召回与精排
→ 复用 / 扩展 / 新增 / 追问 / 拒答建议
→ 专家讨论与证据补充
→ 语义结论审批
→ 声明式 Patch
→ 结构校验、Dry Run 与影响分析
→ Shadow 对比
→ Trace 回放与冻结评测
```

MVP 只生成 Patch 文件，不接入 Spring Boot 正式写接口，不直接写 MongoDB。

## 关键设计原则

1. **全树查重，局部治理**：读取和检索覆盖完整信息树，Overlay 审批和 Patch 建议只作用于试点子树。
2. **专家拥有最终语义权**：AI 可以建议、追问或拒答，只有 `APPROVED` 的语义结论才能进入 Patch。
3. **复用语义不等于复用物理节点**：严格区分直接使用已有节点、基于语义合同新增物理节点和增加场景字段。
4. **确定性代码掌管安全门**：版本检查、节点 ID 校验、结构校验、Dry Run 和权限控制不交给 LLM。
5. **历史是证据，不是 Gold**：历史端点 Diff 只能说明两个已观察快照之间的净变化；有修订缺口时连中间操作都不可还原。结构候选簇必须经过专家重新裁决才能进入冻结评测集。
6. **允许拒答**：选择性高精度优先于强制覆盖所有案例。
7. **真实数据不出内网**：外网只建设通用 Core、契约、虚构数据和测试工具。
8. **所有结论可追踪**：树版本、Overlay、索引、Prompt、模型、候选、人工审批和 Patch 均进入版本化 Trace。

## 文档导航

- [产品规格](docs/product-spec.md)
- [技术架构](docs/architecture.md)
- [安全边界与评测](docs/security-and-evaluation.md)
- [六周实施路线](docs/roadmap.md)
- [决策记录与待核实事项](docs/decision-log.md)
- [实际源格式分析](docs/source-format-findings.md)
- [百炼开发冒烟指南](docs/bailian-smoke.md)

## 当前实现

当前代码覆盖确定性 Diff、两类版本审查、模型安全投影和一个可替换的百炼开发 Provider；尚不包含 Web、数据库连接、向量检索或 Patch 发布：

- `contracts/tree-snapshot.v1.schema.json`：Canonical Tree JSON Schema；
- `contracts/tree-diff.v1.schema.json`：字段级 Snapshot Diff JSON Schema；
- `contracts/history-review.v1.schema.json`：历史结构候选簇、安全门和信息观察 JSON Schema；
- `contracts/business-version-review.v1.schema.json`：相邻业务版本端点净变化审查合同；
- `contracts/llm-evidence-pack.v1.schema.json`：模型输入白名单合同；
- `contracts/ai-review-model-output.v1.schema.json`：不可信模型原始 JSON 合同；
- `contracts/ai-review-draft.v1.schema.json`：AI 审查草稿合同；
- `src/treeguard/adapter.py`：直接导出和 API 响应的递归适配器；
- `src/treeguard/hashing.py`：排除 VALUE 和审计字段的稳定 Schema 哈希；
- `src/treeguard/diff.py`：只按稳定 `node_id` 匹配的保存修订/业务版本 Diff；
- `src/treeguard/history.py`：同一业务版本内、只读、确定性的历史证据分簇、VALUE 风险门禁与可信快照重放校验；
- `src/treeguard/business_review.py`：按外部显式顺序比较相邻业务版本，不解析版本字符串，也不依赖 `concurrent_version` 连续；
- `src/treeguard/evidence.py`：过滤未知字段、审计信息和原始 VALUE，以临时 `F/X/C` 引用构造有界 EvidencePack；
- `src/treeguard/ai_review.py`：百炼 OpenAI 兼容 Provider、本地严格合同校验、最多一次受控重试和失败拒答；
- `src/treeguard/ai_cli.py`：默认只输出聚合信息的内部冒烟 CLI；
- `src/treeguard/cli.py`：不输出名称、ID、路径和 VALUE 的聚合式 Conformance CLI；
- `tests/fixtures/fictional/`：完全虚构的递归复合属性样例；
- `tests/`：标准库单元测试，无运行时第三方依赖；
- `uv.lock`：可复现 Python 环境锁。

运行测试：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen python -B -m unittest discover -s tests -v
```

验证纯 JSON 树导出：

```bash
PYTHONPATH=src python3 -B -m treeguard /path/to/tree.json
```

默认拒绝“curl 命令行 + JSON 响应”的混合文本。只有明确处理接口说明材料时才可以启用：

```bash
PYTHONPATH=src python3 -B -m treeguard /path/to/transcript.txt --allow-curl-transcript
```

真实格式样本目录 `tree-schema/` 已加入 `.gitignore`，不得提交。

离线构造一次“业务版本审查 + EvidencePack”，不会调用模型：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-ai-review \
  /path/to/base-version.json \
  /path/to/target-version.json
```

外部百炼开发冒烟必须使用虚构或已获批脱敏的数据，并显式确认：

```bash
export BAILIAN_API_KEY='replace-with-a-rotated-key'
export TREEGUARD_LLM_MODEL='qwen3.6-35b-a3b'
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-ai-review \
  /path/to/fictional-base.json \
  /path/to/fictional-target.json \
  --live \
  --external-data-approved
```

默认使用北京区 OpenAI 兼容端点。其他地域或业务空间通过
`TREEGUARD_LLM_BASE_URL` 显式配置，且只接受阿里云官方 HTTPS 域名。
密钥只从环境变量读取，不得写入源码、`.env`、测试、Trace 或 Git。
完整 EvidencePack 和 AI 草稿仍属于敏感内部制品；除非显式指定
`--internal-output`，CLI 只输出固定状态和聚合计数。内部输出以 `0600` 新建并拒绝
覆盖已有目标。

## 当前运行约束

- 硬件：内网 A10 服务器；
- 模型：内网量化 Qwen3.6-35B-A3B-FP8；
- 现有核心：Spring Boot + MongoDB 信息树仓库；
- 外网开发：Codex；
- 数据流向：允许外部通用代码经安全审查单向导入内网；
- 外传限制：真实数据、代码、Prompt、Trace 和内部接口不得直接传出，少量材料必须经过严格脱敏和人工复核。

## 成功标准

MVP 的目标是证明“AI 能否安全地辅助新增信息树节点决策”，而不是证明已经具备生产自动发布能力。

建议试点门槛：

- `Candidate Recall@5 ≥ 90%`；
- 明确建议的选择性准确率 `≥ 85%`；
- 明确建议覆盖率 `≥ 50%`；
- 专家决策时间中位数下降 `≥ 40%`；
- 非法、越权或版本过期 Patch 放行数 `= 0`；
- Trace 关键步骤完整率 `= 100%`。

至少 30 条真实专家冻结案例只能支撑 MVP 方向判断，不能包装为生产准确率。
