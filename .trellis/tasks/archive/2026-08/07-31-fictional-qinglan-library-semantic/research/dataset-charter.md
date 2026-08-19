# Dataset Charter：青岚中型语义挑战集

## 身份

- `dataset_ref`: `fictional-qinglan-library-semantic-v1`
- `run_ref`: `qinglan-library-semantic-v1-run-007`
- `primary_role`: `SEMANTIC_CHALLENGE`
- `source_class`: `CLEANROOM_SYNTHETIC`
- `fictional`: `true`
- `derived_from_real`: `false`
- `gold_eligible`: `false`
- `patch_eligible`: `false`
- `seed`: `20260731`

## Purpose

- 验证 300–500 节点树中的歧义、冲突、证据不足、追问和拒答。
- 验证字段所有者、实例边界、单例政策和集合汇总作用域。
- 发现生成器是否通过模板换词、重复 child vector 或隐式笛卡尔积制造规模。

## Non-goals

- 不证明真实图书馆领域正确性。
- 不创建 Gold、Patch 或生产准确率指标。
- 不逼近真实生产树的字段、比例或结构。
- 不承担模型、Prompt、transport 和故障模式的全组合测试。

## Target

- 节点：312
- 场景：20
- `VALUE` envelopes：0
- 候选批次：1 个 run，每次最多 20 条场景
- 节点族：
  - curated core：72
  - approved blueprint background：180
  - stress-only filler：60

## Declared Synthetic Lineage

既有 24 个完全虚构节点只作为 lineage references 披露：

- 用户审核已证明它们不能承担精确跨规模语义重放；
- run-007 可以修改其节点类型、名称、基数或父子关系；
- exact replay anchors：0；
- replay scenarios：0；
- 全部 lineage 仍只涉及 clean-room synthetic，不涉及真实或受保护来源。

## Coverage Gap

现有小型集只能证明跨领域基本合同与人工审核流程，不能同时检验：

- 中型树中的近名候选密度；
- 多层父节点提示与祖先/实例范围混淆；
- 有解释的重复结构和异常深度；
- 明确无界组合请求的拒答；
- 类别概念、重复实例记录、单例政策和集合汇总之间的作用域区分。

## Review Budget

- 候选场景上限：20
- Codex 非权威预审：20
- 人工筛查：20
- 固定随机 self-recheck：5
- 高风险 self-recheck：5
- 双人复核：0
- 总时限：150 分钟

## Stop Rules

- 任一数据边界、安全或 oracle 越权错误；
- 固定随机样本出现两个及以上实质语义错误；
- 同类问题跨两个结构/风险聚类重复；
- 人工审核超过 150 分钟；
- 发现未声明的模板换词、编号兄弟或全局笛卡尔积；
- stress-only 节点被语义场景引用；
- 任一标量 PROPERTY 没有明确的 class record 或 singleton section 所有者；
- 任一组织分类 CONCEPT 直接承载标量字段；
- 人工审核没有明确确认整棵树的单例章节与重复记录边界；
- 非 anchor 内容与已冻结数据或旧回归集明显雷同。

触发停线后返回 Charter、Blueprint 或生成器，不继续人工清洗整批。

## Planned Files

- `src/treeguard/fictional_qinglan_library_semantic_data.py`
- `tests/test_fictional_qinglan_library_semantic_data.py`
- staging `artifacts/fictional-validation/qinglan-library-semantic-v1-run-007/`
- 正式 fixture 仅在冻结、审计和用户晋升批准后创建。
