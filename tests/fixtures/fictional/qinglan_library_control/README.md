# 青岚社区图书馆跨领域控制 fixture

这是一个从独立 Dataset Charter 和 Semantic Blueprint 构建的完全虚构小型
数据集，用于检查 TreeGuard 的通用树合同和验证流程是否隐含依赖消防领域结构。

## 内容

- `tree.json`：48 个节点、0 个 `VALUE` envelope 的虚构源树；
- `scenarios.json`：12 个单一主风险场景；
- `dataset-charter.json`：用途、非目标、来源和人工预算；
- `semantic-blueprint.json`：节点族和显式 subject/facet 允许表；
- `coverage-matrix.json`：场景覆盖格；
- `manifest.json`：被人工审核和冻结的生成阶段 manifest；
- `promotion.json`：冻结、审核、相似度审计和正式晋升的聚合状态。

六个 JSON 数据文件与
`qinglan-library-control-v1-run-004` 的冻结版本逐字节一致。
`manifest.json` 中的 `state=MACHINE_VALIDATED` 是被审字节的一部分，因此没有在
晋升时改写；正式状态由 `promotion.json` 单独记录。

## 边界

- `source_class=CLEANROOM_SYNTHETIC`
- `fictional=true`
- `derived_from_real=false`
- `gold_eligible=false`
- `patch_eligible=false`

本 fixture 不证明真实图书馆领域正确性，不能外推生产准确率，也未加入运行时
数据集注册表。生成器位于
`src/treeguard/fictional_qinglan_library_data.py`。
