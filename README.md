# TreeGuard

TreeGuard 是面向大型信息树的语义编译与变更治理助手。

它将建设人员提交的自然语言需求和领域专家的思考，编译为结构化变更意图；在整棵信息树中检索可能复用或冲突的语义；经过人机协作审查后，生成可验证、可审计、可回放的声明式 Schema Patch。

> 当前阶段：TreeSnapshot/TreeDiff/HistoryReview v1、跨业务版本审查、白名单
> LLM EvidencePack、受约束 AI 初审、可回放专家审查账本，以及“新增需求 →
> AI 意图草稿 → 人工确认 → 确定性全树候选 → AI 语义建议 → 人工复核 →
> 可信回放”的文件型纵切已实现。主运行目标
> 仍是无生产写权限的内网 Shadow MVP；外部百炼只用于完全虚构或经明确审批的
> 脱敏样本。

2026-07-28 已使用完全虚构版本对完成百炼 AI 初审、专家思考 AI 整理和无网络回放
冒烟；该结果只证明工程协议链路可运行，不代表消防领域质量或内网量化模型效果已经
通过验证。

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
- [协议级开发仿真](docs/contract-simulator.md)

## 当前实现

当前代码覆盖确定性 Diff、两类版本审查、模型安全投影、AI 初审、专家审查，以及
新增需求意图确认、一次受约束澄清、无 embedding 的全树词法/结构召回、受约束
候选语义建议和人工复核。另有一个只连接 Clean-room 仿真仓库的 FastAPI + React
只读工作台纵切；尚不包含治理流程 Web 操作、数据库连接、向量检索、语义 Gold 或
Patch 发布：

- `contracts/tree-snapshot.v1.schema.json`：Canonical Tree JSON Schema；
- `contracts/tree-diff.v1.schema.json`：字段级 Snapshot Diff JSON Schema；
- `contracts/history-review.v1.schema.json`：历史结构候选簇、安全门和信息观察 JSON Schema；
- `contracts/business-version-review.v1.schema.json`：相邻业务版本端点净变化审查合同；
- `contracts/llm-evidence-pack.v1.schema.json`：模型输入白名单合同；
- `contracts/ai-review-model-output.v1.schema.json`：不可信模型原始 JSON 合同；
- `contracts/ai-review-draft.v1.schema.json`：AI 审查草稿合同；
- `contracts/expert-synthesis-model-output.v1.schema.json`：不含状态或审批字段的专家思考 AI 整理合同；
- `contracts/expert-synthesis-draft.v1.schema.json`：绑定来源会话、专家原文引用和初审草稿的 AI 整理制品；
- `contracts/expert-review-action.v1.schema.json`：单次专家动作输入合同；
- `contracts/expert-review-session.v1.schema.json`：追加式专家审查事件账本合同；
- `contracts/external-expert-synthesis-approval.v1.schema.json`：精确外发请求计划的两阶段审批清单合同；
- `contracts/intent-request.v1.schema.json`：私有新增需求输入合同；
- `contracts/change-intent-model-output.v1.schema.json`：不含 ID、审批或动作的模型意图输出合同；
- `contracts/change-intent-draft.v1.schema.json`：绑定需求与快照的 AI 意图草稿；
- `contracts/intent-clarification-answer.v1.schema.json`：绑定待澄清草稿的单轮用户回答；
- `contracts/intent-clarification-model-input.v1.schema.json`：不含稳定 ID 的有界澄清模型投影；
- `contracts/intent-clarification-round.v1.schema.json`：绑定初始草稿、回答和修订意图的单轮制品；
- `contracts/intent-review-action.v1.schema.json`：人工确认、修订或拒绝草稿的输入合同；
- `contracts/intent-confirmation.v1.schema.json`：只允许进入检索的确认制品；
- `contracts/candidate-set.v1.schema.json`：确定性全树候选与可解释评分合同；
- `contracts/semantic-recommendation-model-input.v1.schema.json`：不含稳定 ID 和哈希的 Top-8 模型投影合同；
- `contracts/semantic-recommendation-model-output.v1.schema.json`：候选逐项关系与单一选择性建议合同；
- `contracts/semantic-recommendation-draft.v1.schema.json`：绑定确认、候选集、快照和模型来源的建议草稿；
- `contracts/semantic-recommendation-content.v1.schema.json`：人工修订建议的本地约束合同；
- `contracts/recommendation-review-action.v1.schema.json`：确认、修订或拒绝建议的人工 action；
- `contracts/recommendation-record.v1.schema.json`：只作运营反馈、可可信回放的审查记录；
- `contracts/provisional-simulator-response.v1.schema.json`：明确标记为暂定的
  Clean-room 仓库仿真响应合同；
- `src/treeguard/adapter.py`：直接导出和 API 响应的递归适配器；
- `src/treeguard/hashing.py`：排除 VALUE 和审计字段的稳定 Schema 哈希；
- `src/treeguard/diff.py`：只按稳定 `node_id` 匹配的保存修订/业务版本 Diff；
- `src/treeguard/history.py`：同一业务版本内、只读、确定性的历史证据分簇、VALUE 风险门禁与可信快照重放校验；
- `src/treeguard/business_review.py`：按外部显式顺序比较相邻业务版本，不解析版本字符串，也不依赖 `concurrent_version` 连续；
- `src/treeguard/evidence.py`：过滤未知字段、审计信息和原始 VALUE，以临时 `F/X/C` 引用构造有界 EvidencePack；
- `src/treeguard/ai_review.py`：百炼 OpenAI 兼容 Provider、版本审查和意图草稿的本地严格校验、最多一次受控重试和失败拒答；
- `src/treeguard/ai_cli.py`：默认只输出聚合信息的内部冒烟 CLI；
- `src/treeguard/expert_synthesis.py`：专家原文 AI 整理、本地来源绑定和外部载荷授权门；
- `src/treeguard/expert_review.py`：专家思考、AI 整理、暂定状态和最终裁决的确定性状态机与回放；
- `src/treeguard/expert_cli.py`：单动作追加与只读回放 CLI，完整会话使用 `0600` 新文件保存；
- `src/treeguard/change_intent.py`：需求、AI 草稿、单轮澄清、人工确认和可信来源回放；
- `src/treeguard/lexical.py`：历史 Evidence 与在线召回共享的确定性词法切分；
- `src/treeguard/retrieval.py`：全树词法/结构召回、父位置 boost、确定性排序和候选回放；
- `src/treeguard/semantic_recommendation.py`：Top-8 候选投影、语义关系/动作门禁、人工复核记录和可信回放；
- `src/treeguard/private_io.py`：敏感 JSON 的有界私有读取和不可覆盖原子发布；
- `src/treeguard/governance_cli.py`：意图、召回、语义建议、人工复核和回放的文件型旁路工作流；
- `src/treeguard/demo_cli.py`：使用内置完全虚构数据编排正式六步治理命令的一键演示；
- `src/treeguard/simulator.py`：确定性虚构树、四类仓库路由和受控模型故障场景；
- `src/treeguard/simulator_server.py`：只监听 loopback 的标准库 HTTP 开发壳；
- `src/treeguard/repository_client.py`：严格验证暂定四类只读仓库响应的最小客户端；
- `src/treeguard/simulator_cli.py`：启动仿真服务和验证仓库读取的聚合 CLI；
- `src/treeguard/workbench.py`：目录查询与浏览器树视图正向允许列表投影；
- `src/treeguard/web.py`：只读 FastAPI Workbench API、固定错误合同和 no-store
  响应边界；
- `src/treeguard/workbench_cli.py`：只监听 loopback、关闭访问日志的工作台 API
  启动入口；
- `web/`：React、TypeScript、Vite、Ant Design Tree 和 TanStack Query 工作台；
- `src/treeguard/json_utils.py`：拒绝重复键、非有限数和超长整数的严格 JSON 解析；
- `src/treeguard/cli.py`：不输出名称、ID、路径和 VALUE 的聚合式 Conformance CLI；
- `tests/fixtures/fictional/`：完全虚构的递归复合属性样例；
- `tests/`：以标准库 `unittest` 为主的 Python 测试，Workbench API 聚焦测试使用
  开发依赖 HTTPX；
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

## 只读可视化工作台

工作台当前只验证分类、资源、版本和 2,000+ 节点信息树浏览，不提供 AI 治理操作，
不写 sidecar，也没有生产写权限。三个终端依次启动：

```bash
# 终端 1：完全虚构的 2,001 节点仓库
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-contract-simulator serve \
  --port 8765 \
  --node-count 2001 \
  --model-scenario ready

# 终端 2：只读 Workbench API
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-workbench --port 8000

# 终端 3：前端开发服务器
cd web
npm ci
npm run dev
```

然后访问 `http://127.0.0.1:5173/`。若 8000 端口被其他本地服务占用，可以让 API
使用其他端口，并在启动 Vite 时设置仅供开发代理读取的
`TREEGUARD_WEB_API_URL=http://127.0.0.1:<PORT>`。

浏览器只连接 FastAPI；仓库地址和凭据不能由页面提交。树接口使用独立允许列表，
不返回稳定 `node_id`、VALUE、未知 metadata、extension、source route、快照哈希
或文件路径。前端搜索 2,001 节点时只渲染命中路径，Ant Design Tree 继续使用虚拟
滚动。

前端验证：

```bash
cd web
npm ci
npm test
npm run build
```

离线构造一次“业务版本审查 + EvidencePack”，不会调用模型：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-ai-review \
  /path/to/base-version.json \
  /path/to/target-version.json
```

外部百炼开发冒烟必须使用虚构或已获批脱敏的数据，并显式确认。本地开发可复制
仓库中的私有配置模板：

```bash
cp .env.example .env
chmod 600 .env
# 在 .env 的 BAILIAN_API_KEY= 后填入轮换后的 Key
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-ai-review \
  /path/to/fictional-base.json \
  /path/to/fictional-target.json \
  --live \
  --external-data-approved
```

默认使用北京区 OpenAI 兼容端点。其他地域或业务空间通过
`TREEGUARD_LLM_BASE_URL` 显式配置，且只接受阿里云官方 HTTPS 域名。
进程环境变量优先于当前工作目录的 `.env`。本地 `.env` 必须是 `0600` 普通文件，
不得是符号链接，并已被 Git 忽略；生产环境仍应使用进程环境或密钥管理服务。密钥
不得写入源码、`.env.example`、测试、Trace、日志或 Git。
完整 EvidencePack 和 AI 草稿仍属于敏感内部制品；除非显式指定
`--internal-output`，CLI 只输出固定状态和聚合计数。内部输出以 `0600` 新建并拒绝
覆盖已有目标。

## AI 辅助新增需求治理

### 一键虚构 E2E 演示

先用独立演示入口验证完整工程闭环。输出目录必须尚不存在；命令会以 `0700`
新建目录，并以 `0600` 保存全部虚构中间工件：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-governance-demo \
  --output-dir /tmp/treeguard-fictional-demo \
  --review-decision confirm
```

`--review-decision` 是调用者显式提交的虚构建议复核动作，可选 `confirm` 或
`reject`。演示为了贯通召回，会生成一条固定为“只允许进入检索”的虚构意图确认；
它不是语义审批。只有存在 `12-demo-completion.json` 且命令 exit 0，才能认为本次
演示六步回放完成。stdout 不包含目录、节点、文本或哈希，只报告固定状态和聚合
计数；无论确认还是拒绝，结果都固定为非 Gold、非语义审批、非 Patch。

离线模式是默认基线，不调用模型。要用内置虚构数据验证百炼的两段模型调用，必须
显式启用 live 和出域批准：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-governance-demo \
  --output-dir /tmp/treeguard-fictional-live-demo \
  --review-decision confirm \
  --mode bailian-live \
  --external-data-approved
```

该 live 命令只证明外部协议链路和本地合同可以贯通，不代表真实领域质量、内网
Qwen 效果或专家审批已经验证。如果意图模型返回 `NEEDS_CLARIFICATION`，一键演示
会在保存私有草稿后以 `INTENT_CLARIFICATION_REQUIRED` 安全停止，不会自动确认；
回答和重新编译应使用下面的分步工作流。

### 协议级仿真与双模型源

真实内网接口样例尚未到达时，可启动只监听 loopback 的 Clean-room Simulator。
它同时提供四类暂定仓库接口和 OpenAI-compatible 模型接口：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-contract-simulator serve \
  --port 8765 \
  --node-count 2001 \
  --model-scenario ready
```

保持服务运行，在另一个终端验证四类仓库读取：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-contract-simulator verify-repository \
  --base-url http://127.0.0.1:8765
```

也可让完整治理演示真实调用本地 Mock 模型：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  treeguard-governance-demo \
  --output-dir /tmp/treeguard-fictional-simulator-demo \
  --review-decision confirm \
  --mode simulator-live \
  --simulator-base-url http://127.0.0.1:8765/v1
```

`simulator-live` 用于确定性回归；上面的 `bailian-live` 仍会调用真实百炼，用于观察
真实模型对同一完全虚构场景的处理结果。二者产出都只是待人工复核的 sidecar 建议，
不是 Gold、审批或 Patch。暂定接口和限制详见
[协议级开发仿真](docs/contract-simulator.md)。

### 手工文件工作流

`treeguard-governance` 将新需求处理拆成可回放的文件步骤：

```text
私有 IntentRequest
→ AI ChangeIntentDraft
→ （需要时）用户回答一次 → AI IntentClarificationRound
→ 建设人员 CONFIRM_FOR_RETRIEVAL / REJECT_DRAFT
→ 确定性全树 CandidateSet
→ AI Top-8 SemanticRecommendationDraft
→ 人工 CONFIRM / REVISE / REJECT
→ RecommendationRecord
```

所有树、需求、模型输出、草稿、action、确认和候选文件必须为不宽于 `0600` 的普通文件。
完整文本、节点 ID、路径和候选只进入显式 `--internal-output`；stdout 只包含固定状态
与聚合计数。人工确认只允许进入候选检索，固定
`semantic_approval=false`、`patch_eligible=false`，不等同于专家语义审批。
初始草稿为 `NEEDS_CLARIFICATION` 时不能直接确认；MVP 每份草稿最多一个问题，
最多执行一轮澄清。澄清后仍有问题时固定
`CLARIFICATION_LIMIT_REACHED`，只能拒绝或转人工调查。

先用冻结模型输出完成无网络验证：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-governance draft \
  /approved/internal/current-tree.json \
  /approved/internal/intent-request.json \
  --model-output-file /approved/internal/model-output.json \
  --internal-output /approved/internal/intent-draft.json
```

如果草稿状态是 `NEEDS_CLARIFICATION`，建设人员查看草稿中的唯一问题，另存一份
符合 `intent-clarification-answer.v1` 的私有回答文件。回答必须用
`expected_draft_hash` 绑定实际查看的初始草稿。然后使用冻结模型输出重新编译：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-governance clarify \
  /approved/internal/current-tree.json \
  /approved/internal/intent-request.json \
  /approved/internal/intent-draft.json \
  /approved/internal/clarification-answer.json \
  --model-output-file /approved/internal/clarified-model-output.json \
  --internal-output /approved/internal/clarification-round.json
```

受控外部百炼改用 `--live --external-data-approved`，不再提供
`--model-output-file`。澄清路径最多发生三段顺序模型调用：初次意图编译、回答后
重新编译、候选语义建议；无澄清路径仍最多两段。后续 confirm/search/recommend
命令中的 `<draft_file>` 使用最新的 `clarification-round.json`。

建设人员复制并修订草稿中的 `intent`，写入符合
`intent-review-action.v1` 的 action；无澄清时绑定 `draft_hash`，澄清后绑定
`round_hash`。
然后确认并检索：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-governance confirm \
  /approved/internal/current-tree.json \
  /approved/internal/intent-request.json \
  /approved/internal/intent-draft.json \
  /approved/internal/intent-action.json \
  --internal-output /approved/internal/intent-confirmation.json

UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-governance search \
  /approved/internal/current-tree.json \
  /approved/internal/intent-request.json \
  /approved/internal/intent-draft.json \
  /approved/internal/intent-action.json \
  /approved/internal/intent-confirmation.json \
  --internal-output /approved/internal/candidate-set.json
```

第一版召回不要求 embedding：名称、主体覆盖、路径、类型、基数和拟挂载位置形成
可解释分项；拟挂载位置只 boost，不裁剪全树。零候选和信号不足均保持
`allows_addition=false`。外部百炼 live 草稿仍必须显式添加 `--live` 和
`--external-data-approved`；真实需求默认只在内网处理。

语义建议固定从可信 Top-20 `CandidateSet` 投影前 8 个候选，以一次性
`C001`—`C008` 引用交给模型。投影排除稳定节点 ID、哈希、VALUE 和未知字段，
并限制规范 JSON 总长不超过 48,000 字符。
先用冻结模型输出验证合同：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-governance recommend \
  /approved/internal/current-tree.json \
  /approved/internal/intent-request.json \
  /approved/internal/intent-draft.json \
  /approved/internal/intent-action.json \
  /approved/internal/intent-confirmation.json \
  /approved/internal/candidate-set.json \
  --model-output-file /approved/internal/semantic-model-output.json \
  --internal-output /approved/internal/recommendation-draft.json
```

模型必须按顺序逐项判断候选关系，并且只给一个
`USE_EXISTING_NODE`、`ADD_NODE_FROM_CONTRACT`、`ADD_CONTEXT_FIELD`、
`NEED_CLARIFICATION`、`NEED_EVIDENCE` 或 `ABSTAIN`。正向动作必须引用具有匹配
关系的候选；零候选、证据不足或越权字段均不能产生正向动作。

审查人员把实际查看的 `draft_hash` 写入
`recommendation-review-action.v1`，再执行：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-governance review-recommendation \
  /approved/internal/current-tree.json \
  /approved/internal/intent-request.json \
  /approved/internal/intent-draft.json \
  /approved/internal/intent-action.json \
  /approved/internal/intent-confirmation.json \
  /approved/internal/candidate-set.json \
  /approved/internal/recommendation-draft.json \
  /approved/internal/recommendation-action.json \
  --internal-output /approved/internal/recommendation-record.json

UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-governance replay-recommendation \
  /approved/internal/current-tree.json \
  /approved/internal/intent-request.json \
  /approved/internal/intent-draft.json \
  /approved/internal/intent-action.json \
  /approved/internal/intent-confirmation.json \
  /approved/internal/candidate-set.json \
  /approved/internal/recommendation-draft.json \
  /approved/internal/recommendation-action.json \
  /approved/internal/recommendation-record.json
```

`RecommendationRecord` 固定为 `OPERATIONAL_FEEDBACK_ONLY`，即使人工确认也保持
`semantic_approval=false`、`patch_eligible=false`、`gold_eligible=false`。
详细 reviewer reasoning 只保存在私有工件；回放 stdout 只给固定状态和门禁。
评测 Gold、召回指标和效果报告不属于本纵切，仍是待验证的后续设计。

## AI 辅助专家审查

先用 `treeguard-ai-review --internal-output` 生成包含非空 `ai_review_draft` 的内部
bundle。专家动作从 JSON 文件读取，不把原文、理由或来源哈希放入命令行。action
顶层必须包含：

- 唯一的 64 位十六进制 `action_id`；
- bundle 内 `ai_review_draft.case_id` 对应的 `case_id`；
- 首次动作为 `null`、后续动作为上一会话 `session_hash` 的
  `expected_session_hash`；
- `action_type`、`actor_role`、`actor_ref`、带时区的 `recorded_at` 和 `payload`。

每次命令只追加一个专家动作，并把新会话写到一个尚不存在的新文件：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-expert-review apply \
  /path/to/base-version.json \
  /path/to/target-version.json \
  /approved/internal/ai-bundle.json \
  /approved/internal/expert-action.json \
  --session-input /approved/internal/session-001.json \
  --internal-output /approved/internal/session-002.json
```

首条思考不提供 `--session-input`。若要让外部百炼整理本次专家原文，动作必须是
`EXPERT_THOUGHT_SUBMITTED`。先离线生成精确请求计划的 `PENDING` 清单，不会联网：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-expert-review prepare-approval \
  /path/to/base-version.json \
  /path/to/target-version.json \
  /approved/internal/ai-bundle.json \
  /approved/internal/expert-action.json \
  --internal-output /approved/internal/approval-request.json
```

审批人应保留该文件，并在受控流程中另存一份 `APPROVED` 清单：只把
`approval_status` 改为 `APPROVED`，填写 `approved_by` 与不晚于模型事件的
RFC3339 `approved_at`，其余字段原样保留。当前文件只是
`UNVERIFIED_FILE_ASSERTION`，不能证明审批人身份。随后才能执行：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-expert-review apply \
  /path/to/base-version.json \
  /path/to/target-version.json \
  /approved/internal/ai-bundle.json \
  /approved/internal/expert-action.json \
  --internal-output /approved/internal/session-001.json \
  --live-synthesis \
  --external-data-approved \
  --external-approval-file /approved/internal/approval-approved.json
```

Provider 和回放都会根据冻结来源、专家原文、端点、模型、Prompt 及最多两次请求体
重新计算审批哈希；不匹配时在联网前或回放时拒绝。真实专家讨论默认不应出内网。

回放只使用冻结制品，不调用模型或网络：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen treeguard-expert-review replay \
  /path/to/base-version.json \
  /path/to/target-version.json \
  /approved/internal/ai-bundle.json \
  /approved/internal/session-002.json
```

AI 整理事件永远不改变权威状态。只有领域专家能进入 `NEED_EVIDENCE`、
`PROVISIONAL`、`APPROVED` 或 `REJECTED`；最终动作还必须携带专家实际查看过的
`expected_session_hash`。当前 `APPROVED` 只表示专家语义裁决，仍然
`patch_eligible=false`、`gold_eligible=false`，等待后续结构审批和独立盲评。

所有树导出、bundle、action、上一会话和审批清单都是敏感输入，文件模式要求其权限
不宽于 `0600`（例如在受控目录执行 `chmod 600 <files...>`）；符号链接、管道、超限
文件和宽权限输入会被拒绝。会话中的 actor 与初始 AI 来源分别标为
`UNVERIFIED_FILE_ASSERTION` 和 `UNVERIFIED_FILE_BUNDLE`。哈希链用于完整性检查，
不是签名。文件模式也没有全局权威 HEAD：同一输入可以产生多个各自可回放的后继
分支，必须由未来的受控仓库/数据库选择 head 或记录 supersession，不能把任一文件
分支自动视为权威发布结果。v1 每个会话最多保存一次 AI 整理；后续补充由人工继续
裁决，或为新的模型整理创建新会话。

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
