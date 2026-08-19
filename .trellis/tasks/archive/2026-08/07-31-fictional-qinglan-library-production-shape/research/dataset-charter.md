# Dataset Charter：青岚生产形状集（草案）

```yaml
dataset_ref: fictional-qinglan-library-production-shape-v1
primary_role: PRODUCTION_SHAPE
purpose:
  - 验证 2,001 节点下的确定性构建、适配和有界候选
  - 验证节点重排不改变声明锚点的可观察结果
  - 检查生成器在大规模下没有模板换词或笛卡尔积扩张
non_goals:
  - 不复现真实生产树语义、结构比例或字段
  - 不创建 Gold、Patch 或生产准确率指标
  - 不让 stress-only 节点承担语义结论
source_class: CLEANROOM_SYNTHETIC
fictional: true
derived_from_real: false
gold_eligible: false
patch_eligible: false
seed: 2026073101
target:
  nodes: 2001
  scenarios: 8
  value_envelopes: 0
  family_counts:
    curated_core: 40
    approved_blueprint_background: 1561
    stress_only_filler: 400
synthetic_lineage:
  source_dataset: fictional-qinglan-library-semantic-v1
  anchor_contract_nodes: 24
  replay_scenarios: 4
  non_anchor_copy_allowed: false
review_budget:
  candidate_limit: 8
  codex_pre_review_all: true
  human_screen_all_scenarios: true
  human_review_curated_nodes: 40
  structural_cluster_representatives: 12
  random_node_sample: 24
  random_self_recheck_scenarios: 3
  high_risk_self_recheck_scenarios: 4
  dual_review_limit: 0
  time_limit_minutes: 180
stop_rules:
  critical_boundary_errors: 1
  ambiguous_value_owner_errors: 1
  missing_record_referent_errors: 1
  undeclared_parent_relation_errors: 1
  scope_ancestry_conflicts: 1
  allowlist_derived_from_output: 1
  material_random_sample_errors: 2
  repeated_error_clusters: 2
  cartesian_or_template_generation: 1
  undeclared_anchor_copy: 1
independence:
  generation_blind_to_legacy_fire_semantics: true
  legacy_similarity_audit_stage: POST_FREEZE_ONLY
  audit_may_reject_but_must_not_guide_generation: true
planned_owners:
  generator: src/treeguard/fictional_qinglan_library_production_shape_data.py
  fixtures: tests/fixtures/fictional/qinglan_library_production_shape/
  tests: tests/test_fictional_qinglan_library_production_shape_data.py
```

## 审核边界

- 当前只有一名审核者，不产生 `DUAL_REVIEWED` 状态。
- 人工审核集中在 8 条场景、40 个 curated 节点、每个新结构簇代表和固定随机
  节点样本，不逐项清洗 2,001 个节点。
- 任一属性所有者不清、未声明锚点复制或生成模板扩张均立即停线并修 Blueprint。
- 任一 class 记录无法完成“每一条该记录描述谁、与父记录是什么关系”，或
  `class/SINGLE` 逃逸其重复祖先作用域，均立即停线。
- `run-002` 已触发上述停线规则；新候选使用 `run-003`，不覆盖旧 staging。
