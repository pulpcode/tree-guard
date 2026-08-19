# 冻结后审计青岚候选与旧回归集相似度

## 背景

`qinglan-library-control-v1-run-004` 已完成 Codex 非权威预审、单人人工筛查和
确定性冻结。生成阶段未读取旧消防数据。本任务是冻结后的独立只读阶段，只检查
新候选是否与旧回归集存在明显结构、命名、文本或模板雷同。

## 目标

1. 先验证 `freeze-manifest.json`，确认 12 个受审工件未发生字节变化。
2. 用预先固定的确定性算法比较冻结候选与旧消防回归集。
3. 只输出聚合计数、比例、阈值、finding code 和 `ACCEPT`/`REJECT`。
4. 审计只能接受或拒绝冻结候选，不能据此修改 Blueprint、生成器、树或场景。

## 数据边界

- 新候选必须保持：
  `source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`gold_eligible=false`、
  `patch_eligible=false`。
- 旧数据只在本任务的只读进程内加载，不复制到任务、测试、日志或审计报告。
- 不输出旧节点名、路径、场景正文、subject/facet 文本、低熵内容摘要或逐对结果。
- 不调用 Web、外部模型、真实仓库或受保护环境。
- 不把审计通过解释为领域 Gold、生产准确率或正式 fixture 晋升。

## 允许读取

- 冻结候选的 `freeze-manifest.json`、`tree.json`、`scenarios.json` 和
  `semantic-blueprint.json`；
- `tests/fixtures/fictional/fire_validation/` 下旧回归 fixture；
- 为解释 fixture 形状而必须读取的
  `src/treeguard/fictional_fire_data.py` 和
  `src/treeguard/fire_validation_dataset.py`。

读取优先级为 fixture 优先；若 fixture 已足够，便不读取旧生成器源码。

## 冻结的规范化与指标

所有文本先做 Unicode NFKC、大小写折叠，只保留字母和数字。相似度使用长度
2、3、4 的字符 n-gram 并集 Jaccard；不足 2 字符的文本以完整规范化文本作为
单个 token。指标包括：

1. 节点名精确交集与 n-gram 最近邻；
2. 场景正文精确交集与 n-gram 最近邻；
3. 一级分支名称交集、分支数量和后代数量向量；
4. 路径的深度、节点类型序列和逐层分叉数形状；
5. 父节点的名称型 child vector 与类型型 child vector；
6. 从父子关系推导的 subject/facet 精确组合；
7. 将两侧各自节点名按长到短替换为占位符后的场景模板指纹。

结构型 path/child 指标只作诊断，因为通用树合同天然会产生相同形状，不得单独
触发拒绝。

## 预先固定的拒绝阈值

以下任一条件成立即 `REJECT`：

- `NODE_EXACT_OVERLAP`：精确同名节点数 / 两侧较小节点数 `>= 0.10`；
- `NODE_NGRAM_CLUSTER`：至少 20% 的新节点在旧集中的最近邻相似度 `>= 0.70`，
  或任一节点最近邻相似度 `>= 0.95` 且另有至少一个达到 `0.85`；
- `SCENARIO_EXACT_OVERLAP`：存在任一精确相同场景正文；
- `SCENARIO_NGRAM_CLUSTER`：任一场景最近邻相似度 `>= 0.85`，或至少两个达到
  `0.75`；
- `L1_BRANCH_COPY`：一级分支精确同名比例 `>= 0.50`，且后代数量向量完全一致；
- `CHILD_VECTOR_COPY`：至少 15% 的新非空名称型 child vector 在旧集中精确出现；
- `SUBJECT_FACET_COPY`：至少 15% 的新 subject/facet 组合在旧集中精确出现；
- `TEMPLATE_FINGERPRINT_COPY`：存在精确相同的非空模板指纹，或任一模板最近邻
  `>= 0.92`，或至少三个达到 `0.80`。

分母为零时比例记为零。所有阈值在读取旧语义内容前冻结；运行后不得为了让候选
通过而调整。若算法无法可靠解析 fixture，则结论为 `BLOCKED`，不得猜测通过。

## 输出

- 确定性脚本：`scripts/audit_qinglan_legacy_similarity.py`；
- 抽象数据单元测试：`tests/test_qinglan_legacy_similarity_audit.py`；
- 忽略的审计结果：
  `artifacts/fictional-validation/qinglan-library-control-v1-run-004/legacy-similarity-audit.json`。

审计结果只包含输入规模、聚合指标、阈值判断、finding codes、限制和最终结论；
不包含旧语义正文或逐对命中详情。

## 验收标准

- [x] 冻结清单逐字节验证通过后才加载旧数据。
- [x] 测试只使用抽象自造样例，不固化旧消防语义。
- [x] 七类指标均被计算，且相同输入逐字节得到相同结果。
- [x] 输出不泄露旧节点名、路径、场景文本或组合文本。
- [x] `REJECT` 时不修改冻结候选；`ACCEPT` 时也不自动晋升。
- [x] 聚焦测试、后端测试、Trellis 测试与 `git diff --check` 通过。

## 当前结论

冻结后审计结论为 `ACCEPT`，`finding_codes=[]`。节点精确重合、一级分支同名、
名称型 child vector 和 subject/facet 精确组合的命中比例均为零；场景正文与模板
指纹的最大相似度均低于预先固定阈值。结构型 path/child 指标仅作为诊断。

本结论不授予 Gold、不证明真实领域正确性，也不自动晋升正式 fixture。

## 非目标

- 不修改正式 fixture、数据集注册表、共享运行时 Schema 或 Agent 实现。
- 不生成新节点或场景，不清洗旧数据，不将相似度结果反馈给生成器。
- 不 stage、commit、push、merge 或 rebase。
