# b03 新密封数据 clean-room 交接

## 目的与状态

本文件只冻结下一轮独立数据任务的公开合同，不授权生成数据。b03 用于在从未参与
Prompt v2 校准的全新虚构信息树上，重新验证 Navigation Copilot 是否达到进入受保护环境
Shadow 审核的门槛。它不创建 Gold，不证明真实领域正确性，也不恢复已经揭盲的 b02
资格。

- 功能基线：`40098afe985dfc81183c928a473a2e8a3c2176dc`；
- 来源：`CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`；
- 权威性：`quality_tier=SILVER`、`assessment_authority=CODEX_ASSISTED`、
  `gold_eligible=false`、`patch_eligible=false`；
- 当前状态：`PLANNED_AWAITING_INDEPENDENT_DATA_TASK`。

## 隔离要求

b03 必须由新的对话和独立 worktree 从上述功能基线开始。数据作者只可读取当前公开
Schema、`navigation_copilot_sealed_validation.py` 中的确定性合同以及本交接，不得读取或
执行下列材料：

- b01/b02 的 tree、blueprint、candidate、scenario、Oracle、Silver、preflight、manifest、
  runner 输出或实验结果；
- 当前任务中记录 b01/b02 逐批构造或运行结论的 research 正文；
- H1/H2、M4/M5、R2、青岚等既有语义 fixture、scenario、Oracle、生成器或逐项结果；
- `/private/tmp` 中任何既有实验工件；
- 会递归加载上述材料的完整测试或 `unittest discover`。

只要数据作者、生成器或审核过程读取了禁读材料，本批次立即失去 clean-room 资格，不能靠
改名、重排或重新审核恢复。必须另起 batch、namespace、seed 和执行主体。

## Dataset Charter

- 主角色：`SEMANTIC_CHALLENGE`；
- 树规模：700—1,000 节点，精确值在生成前冻结；
- `VALUE` envelope：0；
- 顶层结构、领域、namespace、seed、稳定 ID 规则和语义蓝图由独立数据任务重新选择；
- 不复用旧树的节点、语义蓝图、子树骨架、scenario 文本或 Oracle；
- 语义内容必须由逐节点显式蓝图提供，生成器只做闭集校验、稳定 ID 分配和规范序列化；
- 禁止笛卡尔积造树、统一服务单元骨架、编号兄弟、批量同义改写和通过 ID/顺序扰动伪造
  多样性；
- 对所有可成为目标或干扰项的非叶蓝图逐项 Silver 审核；背景填充节点不得承担 Oracle；
- 候选上限 56，冻结执行集精确 48；候选不足不得降低门槛、跨类别借位或临时补造。

## 冻结执行分母

48 条场景必须精确满足：

| 类别 | 数量 | 主要验证问题 |
|---|---:|---|
| `LITERAL_UNIQUE` | 10 | 字面直接请求能否恢复唯一目标 |
| `NONLITERAL_UNIQUE` | 10 | 同义、缩写、口语、轻微错别字、跨层表达 |
| `STRUCTURAL_INTERFERENCE` | 8 | 近名、跨分支、类型或基数干扰 |
| `MULTI_ACCEPTABLE` | 4 | 多个等价目标不被错误压成唯一答案 |
| `CLARIFICATION` | 6 | 请求本身存在实质歧义，澄清一次后安全继续 |
| `WEAK_EVIDENCE` | 4 | 目标存在但证据不足时不强推 |
| `TARGET_ABSENT` | 6 | 树中确无目标时不产生错误自信推荐 |

同时满足：

- 目标存在 42 条、目标不存在 6 条；
- 错误上下文 8 条，均绑定树内真实存在但语义错误的公开父节点引用；
- 重复性子集 16 条，分别从 `NONLITERAL_UNIQUE`、
  `STRUCTURAL_INTERFERENCE`、`CLARIFICATION`、`WEAK_EVIDENCE` 各取 4 条；
- 非字面 10 条覆盖五类现象，每类 2 条，每条只设一个主要非字面现象；
- 场景先于 Oracle 独立显式编写并冻结；Oracle 不能反向改写请求，使其更容易命中。

## 可达的 Oracle 合同

所有字段必须符合已提交的 v2 Scenario/Oracle Schema，并额外满足当前产品路径：

- `CLARIFICATION`：`expected_route=CLARIFY`、
  `clarification_policy=CLARIFICATION_REQUIRED`、单一可接受目标、非空冻结回答，且
  `acceptable_policy_statuses` 必须精确为 `[NEED_EVIDENCE]`。产品两次调用路径在重新理解
  后不再调用 Semantic，因此不得期待 `AMBIGUOUS` 或 `CANDIDATES_AVAILABLE`；
- `WEAK_EVIDENCE`：`expected_route=LIMIT`、目标存在、
  `acceptable_policy_statuses=[NEED_EVIDENCE]`，终态必须为
  `EXIT / null / PRESENT_NOT_FOUND`；
- `TARGET_ABSENT`：`expected_route=PROCEED`、目标集合为空、不得设置禁止目标；
- `MULTI_ACCEPTABLE`：至少两个稳定可接受节点；
- 其余目标存在类：单一可接受节点；
- 可接受/禁止节点必须属于冻结树且互不重叠；结构 profile、Policy 和终态必须来自当前
  可观察产品合同，不以期望模型答案反推；
- 隐藏 Oracle、目标、评分答案和 Silver sidecar 不得进入模型请求、公共 scenario、公开
  manifest 或生成日志。

## 文件所有权与实施顺序

独立数据任务只拥有：

- b03 专属 Trellis 任务目录；
- b03 专属显式蓝图和确定性数据脚本；
- `tests/fixtures/fictional/` 下新的 b03 独占目录；
- b03 专属聚焦数据测试。

不得修改产品源码、Prompt、Provider、Retrieval、Semantic、Policy、Workbench、现有 fixture
或现有测试。顺序固定为：

1. 规划：冻结领域、蓝图、节点数、候选选择、审核预算、文件白名单和测试白名单；
2. 获得用户明确实施批准；
3. 显式编写树与场景，运行专属确定性 preflight；
4. 在 Oracle 不进入模型输入的前提下完成 Codex Silver 审核；
5. 确定性冻结 48 条执行集及隐藏 Oracle；
6. 停在 data-commit 人工审阅门；
7. 获批后提交数据；由功能会话集成数据提交并生成 execution manifest；
8. fresh-checkout 重放通过并另获运行批准后，才可执行一次真实资格实验。

数据任务不得生成 execution manifest，不得调用产品链路或模型，不得 push/merge。完全虚构
数据后续调用 LLM 适用项目常设授权，但仍须保持 Oracle 隔离，且 Prompt、请求、响应和
trace 不进入 Git。

## 门禁与停线

规划阶段只允许 Trellis validate 和 `git diff --check`。实施阶段在冻结前只允许运行 b03
专属数据测试、专属 preflight、Trellis validate 和 `git diff --check`；禁止完整或递归测试。

任一情况立即整批停线：

- 访问禁读材料或白名单外文件；
- 来源、节点数、`VALUE`、类别、目标、错误上下文或重复子集配额不符；
- 语义由生成器推导、出现笛卡尔积或重复骨架超过预注册门槛；
- Scenario 在 Oracle 之后编写，或 Oracle 影响请求文本；
- 澄清/弱证据 Oracle 与当前两调用产品路径不可达；
- Oracle、目标、review sidecar 或模型流量泄漏到公开工件；
- 审核不完整、预算超限、冻结字节漂移或需要热修已冻结内容。

冻结后发现任何数据错误，当前 batch 作废，不在同一分母上修补后继续资格运行。
