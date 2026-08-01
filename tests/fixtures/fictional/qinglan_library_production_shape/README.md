# 青岚社区图书馆生产形状 fixture

这是一个在完全虚构青岚数据线上独立构造的生产形状数据集，用于检查 TreeGuard
在 2,001 节点规模下的确定性构建、适配、候选上限、节点重排稳定性，以及仅限
24 个声明锚点的跨规模重放。

## 内容

- `tree.json`：2,001 个节点、0 个 `VALUE` envelope 的虚构源树；
- `scenarios.json`：8 个单一主风险场景，其中 4 个是声明的跨规模重放；
- `dataset-charter.json`：用途、非目标、来源和人工预算；
- `semantic-blueprint.json`：记录指代、实体作用域、节点族和显式允许表；
- `coverage-matrix.json`：场景覆盖格；
- `manifest.json`：被人工审核和冻结的生成阶段 manifest；
- `promotion.json`：冻结、单人人工审核、相似度审计和正式晋升的聚合状态。

六个 JSON 数据文件与 `qinglan-library-production-shape-v1-run-003` 的冻结版本
逐字节一致。`manifest.json` 中的 `state=MACHINE_VALIDATED` 是被审字节的一部分，
因此没有在晋升时改写；正式状态由 `promotion.json` 单独记录。

## 边界

- `source_class=CLEANROOM_SYNTHETIC`
- `fictional=true`
- `derived_from_real=false`
- `gold_eligible=false`
- `patch_eligible=false`

本 fixture 不证明真实图书馆领域正确性，不能外推生产准确率。跨规模结论只适用
于声明的 24 个锚点和 4 个配对场景；400 个 stress-only 节点不参与语义准确率。
当前未加入运行时数据集注册表。生成器位于
`src/treeguard/fictional_qinglan_library_production_shape_data.py`。
