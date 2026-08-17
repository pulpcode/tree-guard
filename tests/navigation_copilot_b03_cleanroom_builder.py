"""Phase 2A builder and preflight for the b03 clean-room dataset.

The tracked blueprint and the literal SCENARIO_SPECS are the only semantic
sources. This module assigns stable IDs, serializes approved structures, runs
deterministic gates, and never creates Oracle, Silver, or freeze-report data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from treeguard.adapter import adapt_tree_document
from treeguard.hashing import canonical_digest
from treeguard.navigation_copilot_sealed_validation import SealedScenario

DATASET_REF = "navigation-copilot-sealed-v3c-b03-prismatic-canopy"
NAMESPACE = "urn:treeguard:fictional:navigation-copilot:b03:prismatic-canopy:v1"
SELECTION_SEED = 2026081748
SELECTION_ALGORITHM_VERSION = "treeguard.navigation-copilot-b03-slot-selection.v1"
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v1"
STAGING_DIR = ROOT / "artifacts/fictional-validation/navigation-copilot-b03-20260817-a"
BLUEPRINT_PATH = FIXTURE_DIR / "blueprint.v1.json"
TREE_PATH = FIXTURE_DIR / "tree.json"
FINAL_SCENARIOS_PATH = FIXTURE_DIR / "scenarios.v2.json"
CLASSIFICATION_PATH = FIXTURE_DIR / "dataset-classification.v1.json"
CANDIDATES_PATH = STAGING_DIR / "candidate-scenarios.v2.json"
SELECTION_PLAN_PATH = STAGING_DIR / "phase2a-selection-plan.v1.json"
PREFLIGHT_PATH = STAGING_DIR / "scenario-only-preflight.v1.json"
REVIEW_PATH = STAGING_DIR / "phase2a-review-checklist.v1.json"

FORBIDDEN_PHASE2A_PATHS = (
    FIXTURE_DIR / "oracle.v2.json",
    FIXTURE_DIR / "freeze-report.v1.json",
    STAGING_DIR / "oracle.v2.json",
    STAGING_DIR / "silver-review-summary.v1.json",
    STAGING_DIR / "freeze-report.v1.json",
)
CATEGORY_QUOTAS_CANDIDATE = {
    "LITERAL_UNIQUE": 11,
    "NONLITERAL_UNIQUE": 12,
    "STRUCTURAL_INTERFERENCE": 10,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 7,
    "WEAK_EVIDENCE": 5,
    "TARGET_ABSENT": 7,
}
CATEGORY_QUOTAS_FINAL = {
    "LITERAL_UNIQUE": 10,
    "NONLITERAL_UNIQUE": 10,
    "STRUCTURAL_INTERFERENCE": 8,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 6,
    "WEAK_EVIDENCE": 4,
    "TARGET_ABSENT": 6,
}
PAIRED_SLOTS = {
    "LITERAL_UNIQUE-09",
    "NONLITERAL_UNIQUE-01",
    "NONLITERAL_UNIQUE-06",
    "STRUCTURAL_INTERFERENCE-02",
    "STRUCTURAL_INTERFERENCE-07",
    "CLARIFICATION-04",
    "WEAK_EVIDENCE-03",
    "TARGET_ABSENT-05",
}
FINDING_CODES = (
    "DATASET_ATTRIBUTE_OWNER_AMBIGUOUS",
    "DATASET_BOUNDARY_CANARY_FOUND",
    "DATASET_CARTESIAN_DENSITY_HIGH",
    "DATASET_COMBINATION_UNAPPROVED",
    "DATASET_COUNT_MISMATCH",
    "DATASET_FILLER_TARGETED",
    "DATASET_ITEM_ATTRIBUTE_ON_COLLECTION",
    "DATASET_NONDETERMINISTIC",
    "DATASET_ORACLE_OVERCLAIM",
    "DATASET_REFERENCE_INVALID",
    "DATASET_REPEATED_VECTOR",
    "DATASET_REQUEST_PRIVATE_LEXICON_REQUIRED",
    "DATASET_REVIEW_BUDGET_EXCEEDED",
    "DATASET_ROLE_MISMATCH",
    "DATASET_SCENARIO_COVERAGE_DUPLICATE",
    "DATASET_SOURCE_CLASS_INVALID",
)

SCENARIO_SPECS: tuple[dict[str, Any], ...] = tuple(json.loads(r'''[
  {
    "scenario_ref": "b03:lit:01:a",
    "slot_ref": "LITERAL_UNIQUE-01",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在访客路线的“雨天防滑提醒位置”主题下新增“提醒更新时间”属性，用来记录防滑提示最近一次更新的时间。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n002"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:02:a",
    "slot_ref": "LITERAL_UNIQUE-02",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在栽培舱的“清晨通风启动条件”主题下新增“确认人员”属性，用来记录谁确认了通风条件。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n002"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:03:a",
    "slot_ref": "LITERAL_UNIQUE-03",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在“晨间入场核对规则”主题下新增“核对完成时间”属性。当前建议的父位置属于广播设备档案，并不适合这项入场核对记录。",
    "branch": "spectrum",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-spectrum-n002"
    ],
    "proposed_parent_logical_ref": "branch-echo-n002",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:04:a",
    "slot_ref": "LITERAL_UNIQUE-04",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在标本转运的“转运箱领取位置”主题下新增“领取窗口开放时间”属性。",
    "branch": "specimen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-specimen-n002"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:05:a",
    "slot_ref": "LITERAL_UNIQUE-05",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在夜间演出的“演出入场开放时段”主题下新增“最晚入场时间”属性。",
    "branch": "night",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-night-n002"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:06:a",
    "slot_ref": "LITERAL_UNIQUE-06",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在“每日用电上限说明”主题下新增“上限复核日期”属性。",
    "branch": "energy",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-energy-n002"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:07:a",
    "slot_ref": "LITERAL_UNIQUE-07",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在“静默状态启动条件”主题下新增“启动确认方式”属性。",
    "branch": "silence",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-silence-n002"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:08:a",
    "slot_ref": "LITERAL_UNIQUE-08",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在“广播音量检查标准”主题下新增“检查结果记录人”属性。",
    "branch": "echo",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-echo-n002"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:09:a",
    "slot_ref": "LITERAL_UNIQUE-09",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在“团体入场集合范围”主题下新增“集合区负责人”属性。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:09:b",
    "slot_ref": "LITERAL_UNIQUE-09",
    "variant": "b",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请给“团体入场集合范围”增加“现场负责人”属性，用来记录负责引导集合的人。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-替代措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:lit:10:a",
    "slot_ref": "LITERAL_UNIQUE-10",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在“幼苗浇水确认事项”主题下新增“浇水完成标记”属性。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "lexical_motif": "literal_unique-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:01:a",
    "slot_ref": "NONLITERAL_UNIQUE-01",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请给观众进场前的柔和灯光开启规则增加“复查人”属性；这里说的是柔光设备启用条件，不是当前给出的标本转运位置。",
    "branch": "spectrum",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-spectrum-n003"
    ],
    "proposed_parent_logical_ref": "branch-specimen-n003",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "synonym-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:01:b",
    "slot_ref": "NONLITERAL_UNIQUE-01",
    "variant": "b",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在用于舒缓照明的设备开启要求下补充“复核人员”；不要放到当前建议的标本交接记录中。",
    "branch": "spectrum",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-spectrum-n003"
    ],
    "proposed_parent_logical_ref": "branch-specimen-n003",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "synonym-替代措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:02:a",
    "slot_ref": "NONLITERAL_UNIQUE-02",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在易碎物搬运注意事项下增加“防碰撞确认”属性。",
    "branch": "specimen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-specimen-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "synonym-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:03:a",
    "slot_ref": "NONLITERAL_UNIQUE-03",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请给静默解除流程增加“恢复确认人”属性；“静默解除”就是结束安静状态并恢复正常提示。",
    "branch": "silence",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-silence-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "abbreviation-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:04:a",
    "slot_ref": "NONLITERAL_UNIQUE-04",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在夜演入场时间说明下新增“检票开始时间”；这里的“夜演”指夜间演出。",
    "branch": "night",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-night-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "abbreviation-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:05:a",
    "slot_ref": "NONLITERAL_UNIQUE-05",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请给“临时多用一点电要到哪里申请”这项说明加上“审批进度”属性。",
    "branch": "energy",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-energy-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "colloquial-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:06:a",
    "slot_ref": "NONLITERAL_UNIQUE-06",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请给轮椅转弯那段说明加上“最小通行宽度”；当前建议的父位置属于音响检查，不是访客通行。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n004"
    ],
    "proposed_parent_logical_ref": "branch-echo-n003",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "MULTIPLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "colloquial-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:06:b",
    "slot_ref": "NONLITERAL_UNIQUE-06",
    "variant": "b",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在方便轮椅转弯的路线说明下补充“通道宽度”；不要使用当前的广播设备父位置。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n004"
    ],
    "proposed_parent_logical_ref": "branch-echo-n003",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "MULTIPLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "colloquial-替代措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:07:a",
    "slot_ref": "NONLITERAL_UNIQUE-07",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在“湿渡过高处置步骤”下增加“开始处置时间”；这里的“湿渡”是对“湿度”的轻微误写。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n004"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "MULTIPLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "minor_typo-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:08:a",
    "slot_ref": "NONLITERAL_UNIQUE-08",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在“提示音播方时段”下增加“结束时间”；“播方”是“播放”的轻微误写。",
    "branch": "echo",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-echo-n003"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "minor_typo-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:09:a",
    "slot_ref": "NONLITERAL_UNIQUE-09",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请从标本转运流程这一层找到“空柜清洁责任范围”，并在它下面增加“清洁复核人”属性。",
    "branch": "specimen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-specimen-n004"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "MULTIPLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "cross_layer_expression-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:nlu:10:a",
    "slot_ref": "NONLITERAL_UNIQUE-10",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请从照明演练的安全要求中定位“眩光投诉处理步骤”，并新增“处理完成时间”属性。",
    "branch": "spectrum",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-spectrum-n004"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "MULTIPLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "nonliteral_unique",
    "lexical_motif": "cross_layer_expression-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:01:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-01",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在访客路线的“儿童停留安全边界”下新增“陪同要求”，不要放到当前建议的栽培工具消毒步骤中。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n005"
    ],
    "proposed_parent_logical_ref": "branch-mist-n005",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "near_name_cross_branch",
    "lexical_motif": "near_name_cross_branch-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:02:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-02",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在栽培舱的“叶面检查记录入口”下新增“检查照片说明”，当前给出的夜间演出清场位置语义不符。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n005"
    ],
    "proposed_parent_logical_ref": "branch-night-n005",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "wrong_branch",
    "lexical_motif": "wrong_branch-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:02:b",
    "slot_ref": "STRUCTURAL_INTERFERENCE-02",
    "variant": "b",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请把“检查照片说明”放在植物叶面检查记录下，而不是当前建议的舞台清场主题。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n005"
    ],
    "proposed_parent_logical_ref": "branch-night-n005",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "wrong_branch",
    "lexical_motif": "wrong_branch-替代措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:03:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-03",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在照明演练的“观众视线保护范围”下新增“遮挡观察结果”，不要选择名称相近但只描述灯具亮度的节点。",
    "branch": "spectrum",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-spectrum-n005"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "scope_interference",
    "lexical_motif": "scope_interference-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:04:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-04",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在标本转运的“空柜清洁责任范围”下新增“清洁完成标记”，当前建议的访客通行清洁区不是标本柜。",
    "branch": "specimen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-specimen-n005"
    ],
    "proposed_parent_logical_ref": "branch-bridge-n005",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "type_interference",
    "lexical_motif": "type_interference-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:05:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-05",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在夜间演出的“观众离场引导路线”下新增“拥堵观察记录”，不要放到同一分支的入场开放时间下。",
    "branch": "night",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-night-n005"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "sibling_interference",
    "lexical_motif": "sibling_interference-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:06:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-06",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在“照明节能切换条件”下新增“切换确认方式”，不要选择只记录每日用电上限的说明。",
    "branch": "energy",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-energy-n005"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "condition_vs_limit",
    "lexical_motif": "condition_vs_limit-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:07:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-07",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在“文字提示张贴范围”下新增“覆盖区域说明”，当前给出的广播内容复核流程依赖声音，不符合静默提示要求。",
    "branch": "silence",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-silence-n005"
    ],
    "proposed_parent_logical_ref": "branch-echo-n005",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "modality_interference",
    "lexical_motif": "modality_interference-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:07:b",
    "slot_ref": "STRUCTURAL_INTERFERENCE-07",
    "variant": "b",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请给无声文字提示的张贴范围增加“覆盖区域”，不要使用当前的有声广播父位置。",
    "branch": "silence",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-silence-n005"
    ],
    "proposed_parent_logical_ref": "branch-echo-n005",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "modality_interference",
    "lexical_motif": "modality_interference-替代措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:str:08:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-08",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在“安静区域提醒范围”下新增“边界检查日期”，不要选择只控制夜间静音开关的节点。",
    "branch": "echo",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-echo-n004"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "class",
    "cardinality_hint": "MULTIPLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "range_vs_switch",
    "lexical_motif": "range_vs_switch-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:mul:01:a",
    "slot_ref": "MULTI_ACCEPTABLE-01",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "请在“团体入场集合范围”或“观众离场引导路线”任一主题下新增“现场引导人”属性；两个位置都能承载这项访客引导信息。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n006",
      "branch-night-n006"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "two_equivalent_routes",
    "lexical_motif": "two_equivalent_routes-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:mul:02:a",
    "slot_ref": "MULTI_ACCEPTABLE-02",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "请在“喷雾设备停用条件”或“冷藏柜温度复查要求”任一主题下新增“复查人员”属性；两者都是设备状态复核记录。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n006",
      "branch-specimen-n006"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "two_equivalent_checks",
    "lexical_motif": "two_equivalent_checks-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:mul:03:a",
    "slot_ref": "MULTI_ACCEPTABLE-03",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "请在“演练主持交接说明”或“访客求助呼叫方法”任一主题下新增“当班联系人”属性；两处都接受联络信息。",
    "branch": "spectrum",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-spectrum-n006",
      "branch-echo-n005"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "two_equivalent_contacts",
    "lexical_motif": "two_equivalent_contacts-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:mul:04:a",
    "slot_ref": "MULTI_ACCEPTABLE-04",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "请在“设备待机关闭要求”或“设备蜂鸣停用要求”任一主题下新增“确认时间”属性；两个停用要求都可记录确认时间。",
    "branch": "energy",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-energy-n006",
      "branch-silence-n006"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "CONCEPT",
    "value_type_hint": null,
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "two_equivalent_shutdowns",
    "lexical_motif": "two_equivalent_shutdowns-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:clr:01:a",
    "slot_ref": "CLARIFICATION-01",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请给访客路线里的临时安排增加一个“开始时间”属性。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n007"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": "请放在“临时封闭绕行步骤”下，记录绕行开始时间。",
    "primary_challenge": "ambiguous_temporary_route",
    "lexical_motif": "ambiguous_temporary_route-普通措辞",
    "ambiguity_mode": "SUBSTANTIVE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:clr:02:a",
    "slot_ref": "CLARIFICATION-02",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请给栽培舱的检查记录增加一个“负责人”属性。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n007"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": "请放在“叶面检查记录入口”下，记录叶面检查负责人。",
    "primary_challenge": "ambiguous_growing_check",
    "lexical_motif": "ambiguous_growing_check-普通措辞",
    "ambiguity_mode": "SUBSTANTIVE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:clr:03:a",
    "slot_ref": "CLARIFICATION-03",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请给照明演练里的等待要求增加“结束时间”。",
    "branch": "spectrum",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-spectrum-n007"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": "请放在“灯具降温等待要求”下，记录降温等待结束时间。",
    "primary_challenge": "ambiguous_wait",
    "lexical_motif": "ambiguous_wait-普通措辞",
    "ambiguity_mode": "SUBSTANTIVE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:clr:04:a",
    "slot_ref": "CLARIFICATION-04",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请给转运柜的登记事项增加“经办人”。当前建议的父位置是用电登记，无法确定是否合适。",
    "branch": "specimen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-specimen-n007"
    ],
    "proposed_parent_logical_ref": "branch-energy-n007",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": "请放在“运输标签补写流程”下，记录标签补写经办人。",
    "primary_challenge": "ambiguous_registration",
    "lexical_motif": "ambiguous_registration-普通措辞",
    "ambiguity_mode": "SUBSTANTIVE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:clr:04:b",
    "slot_ref": "CLARIFICATION-04",
    "variant": "b",
    "category": "CLARIFICATION",
    "requirement_text": "请在标本转运的登记流程里增加“经办人”；当前用电登记父位置不是我要找的范围。",
    "branch": "specimen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-specimen-n007"
    ],
    "proposed_parent_logical_ref": "branch-energy-n007",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": "请放在“运输标签补写流程”下，记录标签补写经办人。",
    "primary_challenge": "ambiguous_registration",
    "lexical_motif": "ambiguous_registration-替代措辞",
    "ambiguity_mode": "SUBSTANTIVE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "WRONG_PARENT",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:clr:05:a",
    "slot_ref": "CLARIFICATION-05",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请给夜间演出的通知内容增加“发布时间”。",
    "branch": "night",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-night-n007"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": "请放在“音响测试通知范围”下，记录通知发布时间。",
    "primary_challenge": "ambiguous_notice",
    "lexical_motif": "ambiguous_notice-普通措辞",
    "ambiguity_mode": "SUBSTANTIVE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:clr:06:a",
    "slot_ref": "CLARIFICATION-06",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请给用电规则里的调整事项增加“生效日期”。",
    "branch": "energy",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-energy-n007"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": "请放在“配额调整公告范围”下，记录调整生效日期。",
    "primary_challenge": "ambiguous_adjustment",
    "lexical_motif": "ambiguous_adjustment-普通措辞",
    "ambiguity_mode": "SUBSTANTIVE",
    "evidence_mode": "SUFFICIENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:wek:01:a",
    "slot_ref": "WEAK_EVIDENCE-01",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "请给静默协议里那个临时用的提示位置加一个“备注”属性，我暂时不能说明是文字提示、手势提示还是备用指示牌。",
    "branch": "silence",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-silence-n007"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "underspecified_hint",
    "lexical_motif": "underspecified_hint-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "WEAK",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:wek:02:a",
    "slot_ref": "WEAK_EVIDENCE-02",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "请给信标档案中的某项播放记录增加“说明”属性，目前没有提供设备位置、播放时段或广播用途。",
    "branch": "echo",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-echo-n006"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "underspecified_broadcast",
    "lexical_motif": "underspecified_broadcast-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "WEAK",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:wek:03:a",
    "slot_ref": "WEAK_EVIDENCE-03",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "请给访客路线里某个安全主题增加“复查日期”，但我还不能说明是护栏、防滑还是疏散安全。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n008"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "underspecified_safety",
    "lexical_motif": "underspecified_safety-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "WEAK",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:wek:03:b",
    "slot_ref": "WEAK_EVIDENCE-03",
    "variant": "b",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "请在访客路线的某项安全说明下增加“复核时间”，目前无法确定是通行、停留还是紧急疏散安全。",
    "branch": "bridge",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-bridge-n008"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "underspecified_safety",
    "lexical_motif": "underspecified_safety-替代措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "WEAK",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:wek:04:a",
    "slot_ref": "WEAK_EVIDENCE-04",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "请给栽培舱的一项设备检查增加“处理人”，目前没有说明是喷雾、通风、水箱还是遮阳设备。",
    "branch": "mist",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "branch-mist-n008"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "underspecified_equipment",
    "lexical_motif": "underspecified_equipment-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "WEAK",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:abs:01:a",
    "slot_ref": "TARGET_ABSENT-01",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在宠物寄养登记主题下新增“每日喂食时间”属性；当前树中没有宠物寄养主题。",
    "branch": "absent",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "absent_pet_care",
    "lexical_motif": "absent_pet_care-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "ABSENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:abs:02:a",
    "slot_ref": "TARGET_ABSENT-02",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在餐厅菜单管理主题下新增“过敏原提示”属性；当前树中没有餐厅菜单主题。",
    "branch": "absent",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "absent_menu",
    "lexical_motif": "absent_menu-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "ABSENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:abs:03:a",
    "slot_ref": "TARGET_ABSENT-03",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在酒店客房清洁主题下新增“退房检查时间”属性；当前树中没有酒店客房主题。",
    "branch": "absent",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "absent_hotel",
    "lexical_motif": "absent_hotel-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "ABSENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:abs:04:a",
    "slot_ref": "TARGET_ABSENT-04",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在车辆维修工单主题下新增“更换零件清单”属性；当前树中没有车辆维修主题。",
    "branch": "absent",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "absent_vehicle",
    "lexical_motif": "absent_vehicle-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "ABSENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:abs:05:a",
    "slot_ref": "TARGET_ABSENT-05",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在图书借阅登记主题下新增“归还日期”属性；当前树中没有图书借阅主题。",
    "branch": "absent",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "absent_library",
    "lexical_motif": "absent_library-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "ABSENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:abs:05:b",
    "slot_ref": "TARGET_ABSENT-05",
    "variant": "b",
    "category": "TARGET_ABSENT",
    "requirement_text": "请给图书借还记录增加“应还时间”；这棵树没有图书借还主题。",
    "branch": "absent",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "absent_library",
    "lexical_motif": "absent_library-替代措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "ABSENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  },
  {
    "scenario_ref": "b03:abs:06:a",
    "slot_ref": "TARGET_ABSENT-06",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在课程成绩登记主题下新增“补考结果”属性；当前树中没有课程成绩主题。",
    "branch": "absent",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "absent_course",
    "lexical_motif": "absent_course-普通措辞",
    "ambiguity_mode": "NONE",
    "evidence_mode": "ABSENT",
    "context_mode": "OPEN",
    "plain_language_reviewed": true,
    "proper_noun_dependency": false
  }
]'''))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_id(logical_ref: str) -> str:
    payload = f"{NAMESPACE}\n{logical_ref}".encode("utf-8")
    return "b03n-" + hashlib.sha256(payload).hexdigest()[:24]


def _load_blueprint() -> dict[str, Any]:
    blueprint = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    normalized = deepcopy(blueprint)
    parent_refs = {
        node["parent_ref"]
        for node in normalized["nodes"]
        if node["parent_ref"] is not None
    }
    for node in normalized["nodes"]:
        expected = _stable_id(node["logical_ref"])
        present = node.get("stable_id")
        if present not in (None, expected):
            raise ValueError("DATASET_REFERENCE_INVALID: stable ID mismatch")
        node["stable_id"] = expected
        if node["logical_ref"] in parent_refs:
            node["kind"] = "CONCEPT"
            node["value_type"] = None
            node["cardinality"] = None
        elif node["kind"] == "PROPERTY" and node["value_type"] == "class":
            node["value_type"] = "string"
            node["cardinality"] = "SINGLE"
    return normalized


def _validate_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    findings = Counter({code: 0 for code in FINDING_CODES})
    if (
        blueprint.get("source_class") != "CLEANROOM_SYNTHETIC"
        or blueprint.get("fictional") is not True
        or blueprint.get("derived_from_real") is not False
        or blueprint.get("gold_eligible") is not False
    ):
        findings["DATASET_SOURCE_CLASS_INVALID"] += 1
    nodes = blueprint["nodes"]
    by_ref = {node["logical_ref"]: node for node in nodes}
    if len(nodes) != 864 or len(by_ref) != 864:
        findings["DATASET_COUNT_MISMATCH"] += 1
    stable_ids = [node["stable_id"] for node in nodes]
    if len(set(stable_ids)) != len(stable_ids):
        findings["DATASET_REFERENCE_INVALID"] += 1
    role_counts = Counter(node["role"] for node in nodes)
    if role_counts != Counter(
        curated_core=160,
        blueprint_background=560,
        stress_only_filler=144,
    ):
        findings["DATASET_ROLE_MISMATCH"] += 1
    for node in nodes:
        parent_ref = node["parent_ref"]
        if (parent_ref is None) != (node["logical_ref"] == "root"):
            findings["DATASET_REFERENCE_INVALID"] += 1
        elif parent_ref is not None and parent_ref not in by_ref:
            findings["DATASET_REFERENCE_INVALID"] += 1
        if not node.get("owner_ref") or not node.get("owner_class"):
            findings["DATASET_ATTRIBUTE_OWNER_AMBIGUOUS"] += 1
        if node["role"] == "stress_only_filler" and node["targetable"]:
            findings["DATASET_FILLER_TARGETED"] += 1
        if (
            node["kind"] == "PROPERTY"
            and node["value_type"] == "class"
            and node["cardinality"] not in {"SINGLE", "MULTIPLE"}
        ):
            findings["DATASET_ITEM_ATTRIBUTE_ON_COLLECTION"] += 1

    background_pairs_by_branch: dict[str, set[tuple[str, str]]] = defaultdict(set)
    densities: dict[str, float] = {}
    branch_by_ref = {
        item["branch_ref"]: item for item in blueprint["branch_blueprints"]
    }
    for node in nodes:
        if node["role"] == "blueprint_background":
            pair = (node["subject_key"], node["facet_key"])
            if pair in background_pairs_by_branch[node["branch"]]:
                findings["DATASET_COMBINATION_UNAPPROVED"] += 1
            background_pairs_by_branch[node["branch"]].add(pair)
            branch = branch_by_ref[node["branch"]]
            allowed = branch["allowed_facets_by_subject"].get(node["subject_key"], [])
            if node["facet_key"] not in allowed:
                findings["DATASET_COMBINATION_UNAPPROVED"] += 1
    for ref, branch in branch_by_ref.items():
        possible = len(branch["subject_universe"]) * len(branch["facet_universe"])
        realized = len(background_pairs_by_branch[ref])
        density = realized / possible
        densities[ref] = density
        if density > 0.35 or (
            len(branch["subject_universe"]) >= 3
            and len(branch["facet_universe"]) >= 3
            and realized == possible
        ):
            findings["DATASET_CARTESIAN_DENSITY_HIGH"] += 1

    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if node["parent_ref"] is not None:
            children[node["parent_ref"]].append(node)
    for values in children.values():
        values.sort(key=lambda item: item["stable_id"])

    def direct_signature(node: dict[str, Any]) -> str:
        vector = {
            "node_kind": node["kind"],
            "value_type": node["value_type"],
            "cardinality": node["cardinality"],
            "children": [
                [
                    child["edge_role"],
                    child["kind"],
                    child["value_type"],
                    child["cardinality"],
                ]
                for child in children.get(node["logical_ref"], [])
            ],
        }
        return canonical_digest(vector)

    direct = {
        ref: direct_signature(node)
        for ref, node in by_ref.items()
        if children.get(ref)
    }
    depth2 = {
        ref: canonical_digest(
            {
                "direct": direct[ref],
                "child_direct": [
                    direct.get(child["logical_ref"], "LEAF")
                    for child in children[ref]
                ],
            }
        )
        for ref in direct
    }
    curated_direct = Counter(
        direct[ref]
        for ref, node in by_ref.items()
        if ref in direct and node["role"] == "curated_core"
    )
    curated_depth2 = Counter(
        depth2[ref]
        for ref, node in by_ref.items()
        if ref in depth2 and node["role"] == "curated_core"
    )
    nonfiller_direct = Counter(
        direct[ref]
        for ref, node in by_ref.items()
        if ref in direct and node["role"] != "stress_only_filler"
    )
    signature_branches: dict[str, set[str]] = defaultdict(set)
    branch_sets: dict[str, set[str]] = defaultdict(set)
    for ref, signature in depth2.items():
        branch = by_ref[ref]["branch"]
        if branch != "ROOT":
            signature_branches[signature].add(branch)
            branch_sets[branch].add(signature)
    similarities: dict[str, float] = {}
    branch_refs = sorted(branch_sets)
    for index, left in enumerate(branch_refs):
        for right in branch_refs[index + 1 :]:
            union = branch_sets[left] | branch_sets[right]
            similarity = len(branch_sets[left] & branch_sets[right]) / len(union)
            similarities[f"{left}|{right}"] = similarity
    max_depth2_share = max(Counter(depth2.values()).values(), default=0) / max(
        len(depth2), 1
    )
    skeleton_metrics = {
        "nonleaf_count": len(direct),
        "curated_direct_max_repetition": max(curated_direct.values(), default=0),
        "curated_depth2_max_repetition": max(curated_depth2.values(), default=0),
        "nonfiller_direct_max_repetition": max(nonfiller_direct.values(), default=0),
        "max_cross_branch_repetition": max(
            (len(value) for value in signature_branches.values()), default=0
        ),
        "max_depth2_share_bps": int(max_depth2_share * 10_000),
        "max_branch_jaccard_bps": int(max(similarities.values(), default=0) * 10_000),
        "branch_jaccard_bps": {
            key: int(value * 10_000) for key, value in sorted(similarities.items())
        },
    }
    if (
        skeleton_metrics["curated_direct_max_repetition"] > 2
        or skeleton_metrics["curated_depth2_max_repetition"] > 1
        or skeleton_metrics["nonfiller_direct_max_repetition"] > 6
        or skeleton_metrics["max_cross_branch_repetition"] > 2
        or skeleton_metrics["max_depth2_share_bps"] >= 500
        or skeleton_metrics["max_branch_jaccard_bps"] >= 7000
    ):
        findings["DATASET_REPEATED_VECTOR"] += 1

    curated_semantic = Counter(
        canonical_digest(
            [
                node["subject_scope"],
                node["owner_class"],
                node["semantic_key"],
                node["role"],
                node["kind"],
                node["value_type"],
                node["cardinality"],
                node["branch"],
                node["label"],
                "NONE",
                "SUFFICIENT",
                "OPEN",
            ]
        )
        for node in nodes
        if node["role"] == "curated_core"
    )
    if max(curated_semantic.values(), default=0) > 1:
        findings["DATASET_SCENARIO_COVERAGE_DUPLICATE"] += 1
    return {
        "findings": findings,
        "role_counts": dict(sorted(role_counts.items())),
        "combination_density_bps": {
            key: int(value * 10_000) for key, value in sorted(densities.items())
        },
        "skeleton_metrics": skeleton_metrics,
        "curated_semantic_signature_count": len(curated_semantic),
    }


def _tree_document(blueprint: dict[str, Any]) -> dict[str, Any]:
    by_ref = {node["logical_ref"]: node for node in blueprint["nodes"]}
    child_refs: dict[str, list[str]] = defaultdict(list)
    for node in blueprint["nodes"]:
        if node["parent_ref"] is not None:
            child_refs[node["parent_ref"]].append(node["logical_ref"])
    for refs in child_refs.values():
        refs.sort(key=lambda ref: by_ref[ref]["stable_id"])

    def wrapper(
        logical_ref: str,
        order: int,
        parent_logical_ref: str | None,
    ) -> dict[str, Any]:
        node = by_ref[logical_ref]
        metadata: dict[str, Any] = {
            "node_id": node["stable_id"],
            "node_label": node["label"],
            "node_name": node["label"],
            "node_type": node["kind"],
            "node_order": order,
        }
        if parent_logical_ref is not None:
            metadata["parent_node_id"] = by_ref[parent_logical_ref]["stable_id"]
        if node["kind"] == "PROPERTY":
            metadata["value_type"] = node["value_type"]
            metadata["is_list"] = node["cardinality"] == "MULTIPLE"
        children: dict[str, Any] = {}
        for child_order, child_ref in enumerate(child_refs.get(logical_ref, [])):
            child = by_ref[child_ref]
            if child["label"] in children:
                raise ValueError("DATASET_REPEATED_VECTOR: duplicate sibling label")
            children[child["label"]] = wrapper(
                child_ref,
                child_order,
                logical_ref,
            )
        return {"metadata": metadata, "subnodes": children}

    root = by_ref["root"]
    return {
        "metadata": {
            "map_id": "b03-prismatic-canopy-tree",
            "version": "b03-v1",
            "id": "b03-prismatic-canopy-version-1",
            "map_type": "resource",
            "concurrent_version": 1,
        },
        "map_topology": {root["label"]: wrapper("root", 0, None)},
    }


def _natural_language_findings(specs: tuple[dict[str, Any], ...]) -> list[str]:
    forbidden_private_terms = ("棱湾", "折光穹庭", "暗号", "密语")
    findings: list[str] = []
    for spec in specs:
        text = spec["requirement_text"]
        answer = spec["frozen_clarification_answer"] or ""
        if (
            not spec["plain_language_reviewed"]
            or spec["proper_noun_dependency"]
            or len(text) < 18
            or sum("\u4e00" <= char <= "\u9fff" for char in text) < 12
            or any(term in text or term in answer for term in forbidden_private_terms)
        ):
            findings.append(spec["scenario_ref"])
    return findings


def _scenario_signature_metrics(specs: tuple[dict[str, Any], ...]) -> dict[str, int]:
    full: Counter[str] = Counter()
    simplified: Counter[str] = Counter()
    for spec in specs:
        target_shape = ",".join(spec["planned_target_refs"]) or "ABSENT"
        fields = [
            "ENTITY_COLLECTION",
            "COLLECTION_ITEM",
            target_shape,
            "NAVIGATION_PARENT",
            spec["node_kind_hint"],
            spec["value_type_hint"],
            spec["cardinality_hint"],
            spec["category"],
            spec["primary_challenge"],
            spec["branch"],
            spec["lexical_motif"],
            spec["ambiguity_mode"],
            spec["evidence_mode"],
            spec["context_mode"],
        ]
        full[canonical_digest(fields)] += 1
        simplified[canonical_digest(fields[:9] + fields[11:])] += 1
    return {
        "full_signature_count": len(full),
        "full_max_repetition": max(full.values(), default=0),
        "simplified_max_repetition": max(simplified.values(), default=0),
    }


def _build_scenarios(
    tree_digest: str,
    blueprint: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    by_ref = {node["logical_ref"]: node for node in blueprint["nodes"]}
    public_ref_by_logical = {
        node["logical_ref"]: f"N{index:06d}"
        for index, node in enumerate(
            sorted(blueprint["nodes"], key=lambda item: item["stable_id"]),
            start=1,
        )
    }
    candidates: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    for spec in SCENARIO_SPECS:
        for target_ref in spec["planned_target_refs"]:
            node = by_ref.get(target_ref)
            if node is None or not node["targetable"] or node["role"] != "curated_core":
                raise ValueError("DATASET_REFERENCE_INVALID: target plan is not curated")
        wrong_ref = spec["proposed_parent_logical_ref"]
        if wrong_ref is not None:
            if wrong_ref not in by_ref or wrong_ref in spec["planned_target_refs"]:
                raise ValueError("DATASET_REFERENCE_INVALID: wrong context is invalid")
        scenario = SealedScenario.create(
            scenario_ref=spec["scenario_ref"],
            tree_digest=tree_digest,
            category=spec["category"],
            requirement_text=spec["requirement_text"],
            proposed_parent_ref=(
                public_ref_by_logical[wrong_ref] if wrong_ref is not None else None
            ),
            node_kind_hint=spec["node_kind_hint"],
            value_type_hint=spec["value_type_hint"],
            cardinality_hint=spec["cardinality_hint"],
            frozen_clarification_answer=spec["frozen_clarification_answer"],
            wrong_context_challenge=spec["wrong_context_challenge"],
            repeat_challenge=spec["repeat_challenge"],
        )
        payload = scenario.to_dict()
        candidates.append(payload)
        selection_key = _sha256(
            (
                NAMESPACE
                + "\n"
                + str(SELECTION_SEED)
                + "\n"
                + spec["slot_ref"]
                + "\n"
                + spec["scenario_ref"]
                + "\n"
                + payload["scenario_hash"]
            ).encode("utf-8")
        )
        selection_rows.append(
            {
                "scenario_ref": spec["scenario_ref"],
                "slot_ref": spec["slot_ref"],
                "selection_key": selection_key,
                "planned_target_status": spec["planned_target_status"],
                "planned_target_count": len(spec["planned_target_refs"]),
                "wrong_context_challenge": spec["wrong_context_challenge"],
                "repeat_challenge": spec["repeat_challenge"],
                "primary_challenge": spec["primary_challenge"],
                "nonliteral_phenomenon": (
                    spec["lexical_motif"].rsplit("-", 1)[0]
                    if spec["category"] == "NONLITERAL_UNIQUE"
                    else None
                ),
            }
        )
    candidates.sort(key=lambda item: item["scenario_ref"])
    by_slot: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    candidate_by_ref = {item["scenario_ref"]: item for item in candidates}
    for row in selection_rows:
        by_slot[row["slot_ref"]].append((candidate_by_ref[row["scenario_ref"]], row))
    selected: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for slot_ref in sorted(by_slot):
        rows = sorted(by_slot[slot_ref], key=lambda pair: pair[1]["selection_key"])
        expected = 2 if slot_ref in PAIRED_SLOTS else 1
        if len(rows) != expected:
            raise ValueError("DATASET_COUNT_MISMATCH: slot candidate count")
        selected.append(rows[0][0])
        selected_rows.append(rows[0][1])
    selected.sort(key=lambda item: item["scenario_ref"])
    selected_rows.sort(key=lambda item: item["scenario_ref"])
    plan = {
        "schema_version": "navigation-copilot-b03-phase2a-selection-plan.v1",
        "source_class": "CLEANROOM_SYNTHETIC",
        "oracle_eligible": False,
        "selection_algorithm_version": SELECTION_ALGORITHM_VERSION,
        "selection_seed": SELECTION_SEED,
        "candidate_rows": sorted(selection_rows, key=lambda row: row["scenario_ref"]),
        "selected_rows": selected_rows,
    }
    return candidates, selected, plan


def build_artifacts() -> dict[str, Any]:
    blueprint = _load_blueprint()
    blueprint_metrics = _validate_blueprint(blueprint)
    findings: Counter[str] = Counter(blueprint_metrics.pop("findings"))
    blueprint_bytes = _json_bytes(blueprint)
    tree_document = _tree_document(blueprint)
    imported = adapt_tree_document(tree_document, source_hint="b03-cleanroom")
    if imported.tree is None or not imported.is_valid:
        findings["DATASET_REFERENCE_INVALID"] += 1
        raise ValueError(
            "DATASET_REFERENCE_INVALID: "
            + ",".join(issue.code for issue in imported.issues)
        )
    if imported.observed_node_count != 864 or imported.observed_value_count != 0:
        findings["DATASET_COUNT_MISMATCH"] += 1
    tree_bytes = _json_bytes(tree_document)
    candidates, selected, selection_plan = _build_scenarios(
        imported.tree.snapshot_hash,
        blueprint,
    )
    natural_language_failures = _natural_language_findings(SCENARIO_SPECS)
    if natural_language_failures:
        findings["DATASET_REQUEST_PRIVATE_LEXICON_REQUIRED"] += len(
            natural_language_failures
        )
    scenario_signatures = _scenario_signature_metrics(SCENARIO_SPECS)
    if (
        scenario_signatures["full_signature_count"] != 56
        or scenario_signatures["full_max_repetition"] != 1
        or scenario_signatures["simplified_max_repetition"] > 2
    ):
        findings["DATASET_SCENARIO_COVERAGE_DUPLICATE"] += 1

    candidate_quotas = Counter(item["category"] for item in candidates)
    final_quotas = Counter(item["category"] for item in selected)
    selected_refs = {item["scenario_ref"] for item in selected}
    spec_by_ref = {spec["scenario_ref"]: spec for spec in SCENARIO_SPECS}
    selected_specs = tuple(spec_by_ref[ref] for ref in sorted(selected_refs))
    target_present = sum(
        spec["planned_target_status"] == "TARGET_PRESENT" for spec in selected_specs
    )
    wrong_context = sum(spec["wrong_context_challenge"] for spec in selected_specs)
    repeat_refs = sorted(
        spec["scenario_ref"] for spec in selected_specs if spec["repeat_challenge"]
    )
    repeat_quotas = Counter(
        spec["category"] for spec in selected_specs if spec["repeat_challenge"]
    )
    nonliteral = Counter(
        spec["lexical_motif"].rsplit("-", 1)[0]
        for spec in selected_specs
        if spec["category"] == "NONLITERAL_UNIQUE"
    )
    if (
        candidate_quotas != Counter(CATEGORY_QUOTAS_CANDIDATE)
        or final_quotas != Counter(CATEGORY_QUOTAS_FINAL)
        or target_present != 42
        or wrong_context != 8
        or len(repeat_refs) != 16
        or repeat_quotas
        != Counter(
            {
                "NONLITERAL_UNIQUE": 4,
                "STRUCTURAL_INTERFERENCE": 4,
                "CLARIFICATION": 4,
                "WEAK_EVIDENCE": 4,
            }
        )
        or nonliteral
        != Counter(
            synonym=2,
            abbreviation=2,
            colloquial=2,
            minor_typo=2,
            cross_layer_expression=2,
        )
    ):
        findings["DATASET_COUNT_MISMATCH"] += 1

    for forbidden in FORBIDDEN_PHASE2A_PATHS:
        if forbidden.exists():
            findings["DATASET_ORACLE_OVERCLAIM"] += 1

    candidate_bytes = _json_bytes(candidates)
    final_bytes = _json_bytes(selected)
    plan_bytes = _json_bytes(selection_plan)
    artifact_hashes = {
        "blueprint_sha256": _sha256(blueprint_bytes),
        "tree_sha256": _sha256(tree_bytes),
        "candidate_scenarios_sha256": _sha256(candidate_bytes),
        "final_scenarios_sha256": _sha256(final_bytes),
    }
    repeated = {
        "blueprint": _json_bytes(deepcopy(blueprint)),
        "tree": _json_bytes(_tree_document(deepcopy(blueprint))),
        "candidates": _json_bytes(
            _build_scenarios(imported.tree.snapshot_hash, deepcopy(blueprint))[0]
        ),
        "final": _json_bytes(
            _build_scenarios(imported.tree.snapshot_hash, deepcopy(blueprint))[1]
        ),
    }
    deterministic_match = (
        repeated["blueprint"] == blueprint_bytes
        and repeated["tree"] == tree_bytes
        and repeated["candidates"] == candidate_bytes
        and repeated["final"] == final_bytes
    )
    if not deterministic_match:
        findings["DATASET_NONDETERMINISTIC"] += 1

    finding_counts = {code: findings[code] for code in FINDING_CODES}
    preflight = {
        "schema_version": "navigation-copilot-b03-phase2a-preflight.v1",
        "source_class": "DETERMINISTIC_REPORT",
        "dataset_ref": DATASET_REF,
        "artifact_status": "MACHINE_VALIDATED_PHASE2A",
        "artifact_sha256": artifact_hashes,
        "node_count": imported.observed_node_count,
        "value_envelope_count": imported.observed_value_count,
        "role_counts": blueprint_metrics["role_counts"],
        "candidate_count": len(candidates),
        "final_count": len(selected),
        "candidate_category_quotas": dict(sorted(candidate_quotas.items())),
        "final_category_quotas": dict(sorted(final_quotas.items())),
        "target_present_plan_count": target_present,
        "target_absent_plan_count": len(selected) - target_present,
        "wrong_context_count": wrong_context,
        "repeat_scenario_refs": repeat_refs,
        "repeat_category_quotas": dict(sorted(repeat_quotas.items())),
        "natural_language_gate": {
            "reviewed_count": 56,
            "passed_count": 56 - len(natural_language_failures),
            "failed_count": len(natural_language_failures),
            "proper_noun_placeholder_check_passed_count": 56
            - len(natural_language_failures),
        },
        "semantic_signatures": {
            **scenario_signatures,
            "curated_blueprint_signature_count": blueprint_metrics[
                "curated_semantic_signature_count"
            ],
        },
        "skeleton_signatures": blueprint_metrics["skeleton_metrics"],
        "combination_density_bps": blueprint_metrics["combination_density_bps"],
        "finding_code_counts": finding_counts,
        "deterministic_rebuild_match": deterministic_match,
        "phase2a_canary": {
            "oracle_absent": not any(
                path.name == "oracle.v2.json" and path.exists()
                for path in FORBIDDEN_PHASE2A_PATHS
            ),
            "silver_absent": not any(
                "silver" in path.name and path.exists()
                for path in FORBIDDEN_PHASE2A_PATHS
            ),
            "freeze_report_absent": not any(
                "freeze-report" in path.name and path.exists()
                for path in FORBIDDEN_PHASE2A_PATHS
            ),
        },
        "staging_preservation_required": True,
        "gold_eligible": False,
        "patch_eligible": False,
    }
    if any(finding_counts.values()):
        raise ValueError(
            "Phase 2A preflight failed: "
            + ",".join(
                f"{code}={count}"
                for code, count in finding_counts.items()
                if count
            )
        )
    classification = {
        "schema_version": "navigation-copilot-b03-dataset-classification.v1",
        "dataset_ref": DATASET_REF,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "namespace": NAMESPACE,
        "seed": 2026081703,
        "selection_seed": SELECTION_SEED,
        "selection_algorithm_version": SELECTION_ALGORITHM_VERSION,
        "node_count": 864,
        "candidate_count": 56,
        "final_count": 48,
        "tree_snapshot_hash": imported.tree.snapshot_hash,
        "artifact_sha256": artifact_hashes,
        "public_contract_versions": {
            "tree": "tree-snapshot.v1",
            "scenario": "navigation-copilot-sealed-scenario.v2",
            "oracle": "navigation-copilot-sealed-oracle.v2",
            "evaluation_manifest": "navigation-copilot-sealed-evaluation-manifest.v2",
            "deterministic_validation": "treeguard.navigation-copilot-sealed-gate.v1",
        },
        "function_contract_commit": "40098afe985dfc81183c928a473a2e8a3c2176dc",
        "planning_baseline_commit": "7d8bd6d06ae1a16c87dcb91cd45f7820173ed6fc",
        "phase2a_complete": True,
        "phase2b_approved": False,
    }
    review = {
        "schema_version": "navigation-copilot-b03-phase2a-review-checklist.v1",
        "source_class": "DETERMINISTIC_REPORT",
        "candidate_count": 56,
        "natural_language_reviewed_count": 56,
        "natural_language_passed_count": 56,
        "oracle_reviewed_count": 0,
        "silver_reviewed_count": 0,
        "phase2b_approved": False,
        "candidate_scenarios_sha256": artifact_hashes[
            "candidate_scenarios_sha256"
        ],
        "preserve_until_phase2b_review": True,
    }
    return {
        "blueprint_bytes": blueprint_bytes,
        "tree_bytes": tree_bytes,
        "candidate_bytes": candidate_bytes,
        "final_bytes": final_bytes,
        "selection_plan_bytes": plan_bytes,
        "classification_bytes": _json_bytes(classification),
        "preflight_bytes": _json_bytes(preflight),
        "review_bytes": _json_bytes(review),
        "preflight": preflight,
    }


def _write_or_verify(path: Path, data: bytes, *, normalize_blueprint: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == data:
            return "verified_existing"
        if normalize_blueprint and path == BLUEPRINT_PATH:
            parsed = json.loads(existing.decode("utf-8"))
            if all("stable_id" not in node for node in parsed.get("nodes", [])):
                path.write_bytes(data)
                return "normalized_stable_ids"
        raise ValueError(f"DATASET_NONDETERMINISTIC: refusing to rewrite {path.name}")
    path.write_bytes(data)
    return "created"


def write_artifacts(artifacts: dict[str, Any]) -> dict[str, str]:
    statuses = {
        "blueprint": _write_or_verify(
            BLUEPRINT_PATH,
            artifacts["blueprint_bytes"],
            normalize_blueprint=True,
        ),
        "tree": _write_or_verify(TREE_PATH, artifacts["tree_bytes"]),
        "candidate_scenarios": _write_or_verify(
            CANDIDATES_PATH, artifacts["candidate_bytes"]
        ),
        "final_scenarios": _write_or_verify(
            FINAL_SCENARIOS_PATH, artifacts["final_bytes"]
        ),
        "selection_plan": _write_or_verify(
            SELECTION_PLAN_PATH, artifacts["selection_plan_bytes"]
        ),
        "classification": _write_or_verify(
            CLASSIFICATION_PATH, artifacts["classification_bytes"]
        ),
        "preflight": _write_or_verify(
            PREFLIGHT_PATH, artifacts["preflight_bytes"]
        ),
        "review_checklist": _write_or_verify(
            REVIEW_PATH, artifacts["review_bytes"]
        ),
    }
    return statuses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", required=True)
    parser.parse_args()
    artifacts = build_artifacts()
    statuses = write_artifacts(artifacts)
    print(
        json.dumps(
            {"write_status": statuses, **artifacts["preflight"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
