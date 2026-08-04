# Dataset Charter：M4.9 新密封验证数据

## 冻结候选

| 项 | 第一阶段规划值 |
|---|---|
| `dataset_ref` | `fictional-fire-m49-sealed-v1`（计划值） |
| primary role | `SEMANTIC_CHALLENGE` |
| secondary purpose | 在常见生产规模上观察语义能力，不作为独立压力测试 |
| functional baseline | `d52e92341b1d081c45c9e4594b98323327379da5` |
| `source_class` | `CLEANROOM_SYNTHETIC` |
| `fictional` | `true` |
| `derived_from_real` | `false` |
| `gold_eligible` | `false` |
| `patch_eligible` | `false` |
| deterministic seed | `20260803` |
| tree hard envelope | 800–2,000 节点 |
| tree planning target | 1,200–1,600 节点 |
| formal execution set | 24 条：18 `PROCEED` + 6 `CLARIFY` |
| sealed reserve | 最多 6 条，单独一批，只有正式候选被拒时才审核和替换 |
| repeated observations | 同一冻结配置三轮，共 72 个正式场景观测 |
| review tier | `CODEX_ASSISTED_SILVER` |
| gate eligibility | `false` |
| current state | `FIXTURE_PROMOTED_AWAITING_RUNTIME_PLAN`；已晋升 fixture，未注册运行时、未调用模型 |

## 目的

1. 判断基线提交上的 Intent v4、确定性召回、Semantic v4 和 M4.8 Provider 恢复
   合同，在一棵从未用于前序调试的新树上能否共同完成“需求理解—证据定位—安全
   推荐”。
2. 区分模型语义错误、模型合同输出错误、确定性召回缺口、Provider 传输波动、
   Oracle 缺陷和实验记账错误。
3. 验证此前改进能否跨样本成立。该数据一旦揭盲即降级为回归/校准资产，不能在其上
   调整实现后再次用作泛化证明。

通过只表示值得进入有人监督、只读、可回退的受保护环境 Shadow 验证，不表示达到
生产准确率、自动创建 Gold 或允许自主修改信息树。

## 明确非目标

- 不复制、改名、翻译、扩写或重排既有消防 401 节点树、青岚树、M4.5 暴露数据、
  既有 scenarios 或历史请求。
- 不验证真实消防领域事实，不模拟真实组织、真实字段清单或真实运行参数。
- 不准备 10,000–50,000 节点压力树；规模上限附近的性能压力另立任务。
- 不把“领域 × 规模 × 风险 × Prompt × 模型”做笛卡尔积。
- 不使用本批数据训练模型、选择 Prompt、扩宽 Oracle 或调整阈值。
- 不让 Codex/LLM 复核自动冒充人工 Gold 或独立双审。

## 独立领域构造声明

第二阶段只从已批准的公共 Schema 形状和本 Charter 独立创作一棵新的虚构消防治理
信息树。它与历史数据只共享“消防治理”这一高层测试领域和运行时 Schema，不共享：

- 组织/设施身份、节点正文、稳定 ID、route、分支次序和版本；
- 历史场景措辞、目标集合、Oracle、Prompt、模型请求/响应或人工答案；
- 历史失败样例中的特定同义词对、候选顺序或局部结构。

这保证本轮继续贴近预期生产领域，同时检验是否只记住旧树词汇。跨领域泛化属于
`DOMAIN_CONTROL` 数据集的另一个问题，不与本轮混为一个门禁。

## 树蓝图预算

- 顶层语义分支规划为 10–14 个；正式场景至少覆盖其中 8 个，任一分支最多承担
  3 条正式场景。
- 自然深度规划为 4–7 层；不为达到深度复制空壳层级。
- curated core 规划为 160–240 个节点，用于 24 条场景及其可接受目标、干扰和
  反例；逐项审核场景相关闭包。
- approved blueprint background 构成其余大部分节点；每个 family 必须有明确
  主体、属性所有者和兼容允许表，只审核蓝图、机器门禁、风险簇代表和随机样本。
- stress-only filler 默认 0。不能用无语义编号兄弟或重复子树把节点数补到目标。
- 重复对象必须通过当前合同的复合列表结构表达；集合级聚合属性与成员级属性分开，
  每个 curated 属性都能唯一回答“值属于谁、是一份还是每个成员一份”。
- 如果自然语义在 800–2,000 硬区间内但未达到 1,200–1,600 目标，不得用组合膨胀
  补数；应记录偏差并重新审阅规模是否仍具代表性。

## 场景批次

- 正式批次恰好 24 条；第二个密封余量批次最多 6 条。两个批次均在功能侧读取任何
  正文前生成并计算 digest。
- 正式批次每条只填一个主覆盖格，最多两个预注册次要 tag。
- 替换只能在同一覆盖格内发生，且必须在第一次正式模型调用前完成；替换后重新冻结
  整套 24 条和所有闭包 digest。
- 首次模型调用后不得启用余量、替换失败场景或调整场景组成。

## 审核预算

| 项 | 上限 |
|---|---:|
| L1 机器检查 | 全树、全部正式候选与余量候选 |
| L2 只读 Critic | 全部候选；非权威、只输出固定 finding code |
| 首批人工审核 | 24 条正式候选及相关 curated 闭包 |
| 余量审核 | 仅实际启用项，最多 6 条 |
| 固定 seed 随机复核 | 5 个 background family 实例 + 5 条已接受场景 |
| 双人独立复核 | 0；出现真实第二审核者前不得声称双审 |
| 总人工预算 | 300 分钟 |
| 单条 revise | 最多 2 轮 |
| 整批修复/重审 | 最多 3 轮 |

用户已选择 Codex-assisted Silver。Codex 将对全部正式候选及实际启用余量给出逐项
Silver 判断，并绑定被审最终字节；这只授权校准/诊断实验，不进入正式
`GO_SHADOW` 门禁。结果只能是 `PROMISING`、`NOT_PROMISING` 或
`INCONCLUSIVE`。本数据始终为 synthetic、`gold_eligible=false`；真实领域 Gold
不在本任务权限内。

## 停线条件

发生任一项立即停止第二阶段，不通过放宽门槛或逐条清洗继续：

- 一个数据边界、来源分类、历史正文派生或 Oracle 泄漏错误；
- 一个树/场景/Oracle/合同/审核 digest 闭包失败；
- 同一实质语义错误跨两个覆盖格重复；
- 固定随机复核中至少两个实质错误；
- 出现无解释的全组合密度、重复 child vector 或编号兄弟扩张；
- 任一候选超过两轮 revise、整批超过三轮修复，或人工预算超过 300 分钟；
- 功能侧在揭盲后修改 Prompt、模型、endpoint、参数、Provider 重试、比较器、Oracle
  或阈值；此时数据自动降级为校准集。

## 第二阶段文件所有权候选

数据 worktree 只拥有新的独立路径，默认不修改共享运行时代码：

```text
artifacts/fictional-validation/fictional-fire-m49-sealed-v1/   # staging，默认忽略
tests/fixtures/fictional/fire_m49_sealed/
├── manifest.json
├── tree.json
├── scenario-candidates.json
├── oracle-sidecar.json
├── silver-review.json
└── promotion.json
scripts/generate_fire_m49_sealed_data.py
scripts/preflight_fire_m49_sealed_data.py
scripts/review_fire_m49_sealed_data.py
scripts/promote_fire_m49_sealed_data.py
tests/test_fire_m49_sealed_data.py
```

若需要共享 Provider 注册、公共 manifest 或 `src/treeguard` 修改，数据侧立即停线，
先与功能侧重新冻结所有权和合并顺序。

## 第二阶段启动门

下列条件全部满足后，用户仍需再次明确发出“开始生成 M4.9 候选数据”的指令：

1. 本 Charter、覆盖蓝图、未见性和 Oracle/交接设计获批；
2. 使用 `silver-runtime-freeze.md` 已冻结的模型、endpoint、生成参数、
   Intent/Semantic 尝试上限和 `max_transport_retries`；
3. 审核等级保持已冻结的 `CODEX_ASSISTED_SILVER`，不得在生成或运行后升级；
4. 文件所有权、合并顺序和验收命令获批；
5. 数据 worktree 仍基于 `d52e92341b1d081c45c9e4594b98323327379da5`，无共享文件
   冲突。

以上启动门已由用户的“开始生成”指令满足；后续明确的“批准”又解除了 fixture
晋升门。候选构建、L1、Codex-assisted Silver 和正式 fixture 晋升均已完成。运行时
仍未注册，必须先冻结精确的运行请求计划，不能由数据晋升隐式触发模型调用。
