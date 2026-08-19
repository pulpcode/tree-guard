# Dataset Charter：青岚社区图书馆跨领域控制集

```yaml
dataset_ref: fictional-qinglan-library-control-v1
primary_role: DOMAIN_CONTROL
purpose:
  - 检查通用实现是否依赖消防领域命名、分支或层级
  - 验证独立数据生成、机器门禁和人工审阅流水线
  - 为后续跨规模重放建立小型基线
non_goals:
  - 不验证真实图书馆行业正确性
  - 不创建 Gold
  - 不声明生产准确率
  - 不承担性能或生产形状结论
source_class: CLEANROOM_SYNTHETIC
fictional: true
derived_from_real: false
gold_eligible: false
patch_eligible: false
seed: 20260730
target:
  nodes: 48
  scenarios: 12
  value_envelopes: 0
determinism:
  stable_blueprint_order: true
  stable_explicit_ids: true
  canonical_json_output: true
  seed_usage:
    - covering_selection
    - review_sampling
review_budget:
  candidate_limit: 12
  human_screen_all: true
  random_sample: 4
  self_recheck: 4
  dual_review_limit: 0
  time_limit_minutes: 120
independence:
  generation_blind_to_legacy_fire_semantics: true
  legacy_similarity_audit_stage: POST_FREEZE_ONLY
  audit_may_reject_but_must_not_guide_generation: true
planned_owners:
  generator: src/treeguard/fictional_qinglan_library_data.py
  reviewed_staging: artifacts/fictional-validation/qinglan-library-control-v1-run-004/
  fixtures: tests/fixtures/fictional/qinglan_library_control/
  tests:
    - tests/test_fictional_qinglan_library_data.py
    - tests/test_qinglan_legacy_similarity_audit.py
  fixture_docs: tests/fixtures/fictional/qinglan_library_control/README.md
```

## 挑战标签

`clear_intent`、`category_scope`、`homonym`、`cross_branch`、`kind_conflict`、
`cardinality_conflict`、`wrong_parent_hint`、`near_name_negative`、
`insufficient_evidence`、`judgment_requires_evidence`、
`clarification_required`、`refusal`、
`cartesian_request`、`near_duplicate_subtree`、`unusual_depth`、
`small_tree_replay_baseline`。

## 停线规则

1. 任一边界、安全或 oracle 越权错误立即停线。
2. 固定随机样本中两个及以上实质语义错误停线。
3. 同类问题跨两个聚类重复停线。
4. 审核超过 120 分钟停线。
5. 模板换词、全局笛卡尔积或无解释组合密度停线。
6. 冻结后独立相似度审计发现明显雷同则拒绝候选。
