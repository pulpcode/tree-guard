# 信息树理解核心 M0-M2 与百炼虚构数据验证通道

## 目标

为后续内网 Qwen 信息树理解与虚拟场景生成建立最小、确定性、可回放的共同基线：
冻结 `TreeDiagnosticProfile v1` 合同，实现对完整 `CanonicalTree` 的全树结构画像，
并在此基础上建立有界模型投影、内网 Qwen Provider 与待人工审核的虚拟验证场景
草案。本任务不接入 Workbench。用户进一步确认：外网阶段可使用百炼上的 Qwen
对完全虚构数据做语义效果冒烟，因此补充一个显式批准、无自动回退的验证通道；
该通道不改变真实树只能留在受保护环境的边界。

## 已确认范围

- 用户已明确要求开始开发，并与独立测试数据 worktree 并行推进。
- 首个切片采用“100% 确定性结构扫描 + 后续有界语义理解”，不要求首版对约
  2,000 个节点逐项执行完整 LLM 语义摘要。
- 真实树、字段名、`VALUE`、专家文本和模型流量只允许留在受保护环境；外网开发
  只使用完全虚构的最小树。
- 数据 worktree 独立创造新数据，不读取或改写现有消防 fixture 的语义内容。
- M2 单次模型投影不是“完整理解证明”：它必须公开包含/遗漏节点和 finding 数量；
  超大树的多批 Map/Reduce 编排在后续切片实现。

## 功能需求

1. 新增 `treeguard.tree_understanding` 确定性核心，只消费可信构建的
   `CanonicalTree`，不解析源 DTO。
2. 生成不可变的 `TreeDiagnosticProfile`，至少绑定：
   - 合同版本；
   - 来源树引用与 `snapshot_hash`；
   - 节点总数、根节点数、最大深度；
   - 按节点类型、值类型、基数和深度的规范排序计数；
   - 每个顶层分支的节点数、最大相对深度和最大直接子节点数；
   - 确定性启发式 findings。
3. 首版 findings 只报告可机械证明的候选信号，不声称真实业务错误：
   - 不同路径复用相同规范化名称；
   - 同名节点的类型/值类型/基数合同冲突；
   - 多个非叶节点复用完全相同的直接子节点合同向量。
4. 每条 finding 使用固定 code、规范排序的内部节点引用和最小计数；不得给总体
   “质量分”。
5. profile 提供精确字段的 `to_dict()`、规范 digest 和不含节点名称、路径、
   内部 ID 或 hash 的聚合报告。
6. 新增匹配 Python 运行时字段的 JSON Schema 合同。
7. 输入节点存储顺序变化不得改变 profile、finding 顺序或 digest。

## M2 功能需求

1. 从可信 `CanonicalTree` 和已复核 `TreeDiagnosticProfile` 构建
   `TreeUnderstandingProjection`：
   - 默认最多包含 64 个节点和 20 条 finding；
   - 优先根、finding 相关节点及其祖先，再按规范深度/ID 顺序补足；
   - 每个已投影节点只使用调用内临时 `N001` 引用；
   - 每条已投影 finding 只使用调用内临时 `D001` 引用；
   - 模型视图包含精确覆盖计数与 `coverage_complete`，不得隐瞒截断。
2. 模型节点视图只允许 name、kind、value type、cardinality、depth、直接子节点
   数量和已投影父子临时引用；不得包含 node/tree ID、label、route、path label、
   source/profile hash、`VALUE`、extension 或 metadata。
3. 定义内网 Qwen 模型输出合同，模型只能：
   - 摘要当前有界投影；
   - 对每条 projected finding 按顺序给出
     `POTENTIAL_ISSUE`、`EXPECTED_PATTERN` 或 `NEED_EVIDENCE`；
   - 生成最多 8 个带连续 `S001` 引用的自然语言验证场景；
   - 或以 `NEED_EVIDENCE` / `ABSTAIN` 明确不生成场景。
4. 每个虚拟场景包含标题、自然语言需求、固定 validation goal、支持节点引用、
   finding 引用和理由。所有引用必须属于当前投影，不得引用或编造内部 ID。
   支持节点与来源 finding 引用按集合解释，输入数组顺序不表达优先级；本地在
   验证格式、允许列表和唯一性后统一升序规范化，未知、重复、格式错误或空的
   支持引用仍失败关闭。
5. 模型输出在本地重建为不可变 `TreeUnderstandingDraft`，并绑定 profile、
   snapshot 和 projection digest。草案固定：
   - `PENDING_HUMAN_REVIEW`；
   - `semantic_approval=false`；
   - `gold_eligible=false`；
   - `patch_eligible=false`。
6. 新增仅面向 `InternalQwenConfig` 的 Provider：
   - 复用现有禁 proxy/redirect、有界响应和严格 JSON transport；
   - JSON-object mode、关闭 thinking、temperature 0、最多两次尝试；
   - 不发送 Authorization，不自动回退百炼；
   - 模型输出合同失败时 fail closed，不返回部分草案。
7. 为模型输入、模型输出和持久化待审草案分别新增版本化 JSON Schema。

## 百炼虚构数据验证需求

1. 新增 `BailianTreeUnderstandingProvider`，复用同一有界投影、Prompt、模型输出
   合同、本地回放校验和百炼隔离 transport，不复制信息树理解逻辑。
2. 百炼调用必须显式传入 `external_data_approved=True`；缺少批准时在网络调用前
   以既有 `EXTERNAL_DATA_APPROVAL_REQUIRED` 失败。
3. 百炼请求只允许用于本仓库独立构造的完全虚构树，或另行经过最终字节与用途
   审批的投影；真实树、真实节点名称、专家文本和生产模型流量不得进入该通道。
4. 百炼与内网 Qwen 必须显式选择，不自动回退。草案在两种 Provider 下都保持
   `PENDING_HUMAN_REVIEW`、非 Gold、非 Patch。
5. 自动化测试只使用虚构 transport；若本地百炼凭据可用，可另做不落盘、只输出
   固定状态与聚合计数的 live 冒烟，不把模型请求/响应写入 Git、任务或日志。
6. 聚合冒烟通过后，可对最终字节与用途单独获批的完全虚构投影执行人工语义质量
   评审：
   - 只展示通过本地完整合同重建后的草案字段，不展示 Provider 原始 envelope；
   - 草案文本只在当前人工评审对话中展示，不写入 Git、Trellis、日志或 sidecar；
   - 按清晰性、可执行性、证据关联、场景差异性和不过度声称评审；
   - 评审结论仍是实验观察，不授予语义审批、Gold、Patch 或自动注册资格。

## 安全与可信边界

- 自动化测试不调用真实 Qwen、百炼、Web、MCP 或其他外部服务；经用户明确授权
  的手工百炼 live 冒烟不属于自动化 suite，并且只发送完全虚构投影。
- 不读取 `VALUE`，不从 `metadata_extra` 或未知 extension 推断语义。
- profile 是受保护环境内部工件；模型输入使用独立正向允许列表和临时引用，
  不直接发送内部 profile `to_dict()`。
- 真实节点 name 只能在受保护环境内发给内网 Qwen。本仓库测试和百炼手工冒烟
  只使用完全虚构 name；百炼路径不得成为真实树的自动回退。
- 聚合报告只含合同版本、固定 code 和计数，不含节点名、路径、ID、树引用、
  `snapshot_hash` 或 profile digest。
- findings 是待审启发式信号，不是业务质量结论、Gold、Patch 或生产写入授权。
- Qwen 草案只帮助人工准备验证需求，不能直接写入 ValidationDatasetProvider，
  也不能成为自动验收 oracle。
- 完全虚构草案的人工语义评审只允许展示已通过本地合同的字段；原始模型响应、
  请求正文和 trace 仍不得持久化。

## 非目标

- 多批 Map/Reduce、跨投影归并、长期树摘要或向量索引；
- Workbench API、前端、operation、sidecar 文件写入；
- 修改 Adapter、CanonicalTree、召回、语义建议或现有验证数据；
- embedding、向量库、学习型 reranker、工具调用 Agent；
- 总体质量评分、自动修复、可信 oracle 或真实领域 Gold；
- 历史版本/Diff 联合理解；
- 生产信息树、数据库或 Patch 写入。

## 技术方案

```text
CanonicalTree
→ 确定性父子/深度索引
→ 聚合统计
→ 同名与直接子合同向量分组
→ 规范排序的 TreeDiagnosticFinding
→ TreeDiagnosticProfile + aggregate_report
→ 有界正向允许列表投影（N/D 临时引用）
→ 内网 Qwen JSON-object 输出
→ 本地严格校验与来源绑定
→ PENDING_HUMAN_REVIEW 场景草案
```

复用现有：

- `treeguard.models.CanonicalTree` / `CanonicalNode`；
- `treeguard.hashing.canonical_digest()`；
- 当前 frozen dataclass、精确字段、规范排序与测试模式。

不复用 Workbench 临时节点引用；该引用属于响应域。内部 finding 绑定可信
Canonical node ID，M2 模型投影使用自己作用域内的 `N` / `D` / `S` 引用。

## 验收标准

- [x] JSON Schema 必填字段与 `TreeDiagnosticProfile.to_dict()` 精确一致。
- [x] 完全虚构的正常树得到正确的节点、深度、类型、基数和分支统计。
- [x] 同名跨路径、同名合同冲突和重复直接子合同向量按固定 code 报告。
- [x] 合法输入重排后 `to_dict()` 和 digest 完全一致。
- [x] 构造的重复、未知节点引用或与来源树不一致的 profile/finding 被拒绝。
- [x] aggregate report 不包含节点名称、路径、ID、树引用、hash 或测试 canary。
- [x] 2,001 节点独立规模树完成全扫描；现有 fixture、生成器和 Provider 未修改。
- [x] 模型投影严格有界、确定、引用连续，且模型视图不含内部 ID/hash/未允许字段。
- [x] 模型输出额外字段、未知/重复引用、越界文本和策略冲突使用固定 code
  拒绝；合法唯一引用的任意输入顺序规范化为相同草案和 digest。
- [x] 草案可从可信 projection/profile/tree 重建；重新哈希的错误来源仍被拒绝。
- [x] 内网 Qwen 虚构 transport 证明无 Authorization、thinking 关闭、JSON mode、
  重试上限和失败关闭。
- [x] 模型输入、输出和草案 Schema 与 Python 字段精确一致。
- [x] 聚焦 unittest、完整后端 unittest、Trellis 测试、前端回归和
  `git diff --check` 通过。
- [x] 百炼信息树 Provider 缺少显式批准时在网络前拒绝，获批后复用同一严格
  输出合同并使用 Authorization header、JSON mode、关闭 thinking。
- [x] 内网 Provider 仍拒绝百炼配置；两种 Provider 不自动回退，结果均保持待审、
  非 Gold、非 Patch。
- [x] 百炼虚构 transport 聚焦测试通过；凭据可用时执行一次不落盘的聚合 live
  冒烟，否则只报告未配置，不把缺少凭据视为单元测试失败。
- [x] 对获批的完全虚构 48/64 节点投影各取得一份通过本地合同的 v5 草案，并按
  固定人工 rubric 评审场景质量；不把结果升级为 Gold 或写入仓库。

## 后续里程碑

- M3：多批投影/归并；人工选择候选场景后复用现有 Governance Workbench；
- M4：人工审核并冻结的完全虚构候选，才可进入正式 ValidationDatasetProvider。

## 并行 worktree 合同

- 功能 worktree 当前独占：
  - `src/treeguard/tree_understanding.py`
  - `src/treeguard/model_safety.py`
  - `src/treeguard/semantic_recommendation.py` 中共享 ID 防泄漏 helper 的最小迁移
  - `src/treeguard/ai_review.py` 中内网 Qwen Tree Understanding Provider
  - `contracts/tree-diagnostic-profile.v1.schema.json`
  - `contracts/tree-understanding-*.v1.schema.json`
  - `tests/test_tree_understanding.py`
  - `tests/test_tree_understanding_ai.py`
  - `README.md`
  - `docs/architecture.md`
  - `docs/internal-adapters.md`
  - `.trellis/spec/backend/tree-understanding.md`
  - `.trellis/spec/backend/index.md`
  - `.trellis/spec/backend/directory-structure.md`
  - 当前 Trellis 任务
- 数据 worktree 不修改上述运行时合同；发现需要时只提出字段需求。
- 功能 worktree不修改新数据生成器、fixture、数据说明或数据任务。
- 两侧未经用户批准均不 stage、commit、push、merge 或 rebase。
