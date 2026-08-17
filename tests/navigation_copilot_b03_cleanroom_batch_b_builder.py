"""Batch B Phase 2A builder for the clean-room Navigation Copilot dataset.

This module consumes only the explicit Batch B blueprint and public deterministic
contracts. It never opens Batch A paths and never creates Oracle, Silver, freeze,
manifest, model, or product-chain artifacts.
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


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/fictional/navigation_copilot_b03_cleanroom_v2"
BLUEPRINT_PATH = FIXTURE_DIR / "blueprint.v1.json"
TREE_PATH = FIXTURE_DIR / "tree.json"
SCENARIOS_PATH = FIXTURE_DIR / "scenarios.v2.json"
CLASSIFICATION_PATH = FIXTURE_DIR / "dataset-classification.v1.json"
STAGING_DIR = ROOT / "artifacts/fictional-validation/navigation-copilot-b03-20260817-b"
CANDIDATES_PATH = STAGING_DIR / "candidate-scenarios.v2.json"
PREFLIGHT_PATH = STAGING_DIR / "scenario-only-preflight.v1.json"
SELECTION_PATH = STAGING_DIR / "phase2a-selection-plan.v1.json"
MANUAL_REVIEW_PATH = STAGING_DIR / "phase2a-manual-review-checklist.v1.json"
HIERARCHY_REVIEW_PATH = STAGING_DIR / "phase2a-hierarchy-review.v1.json"

DATASET_REF = "navigation-copilot-sealed-v3c-b03-civic-atrium-b"
BATCH_REF = "NAVCOP_SEALED_V3C_B03_20260817_B"
NAMESPACE = "urn:treeguard:fictional:navigation-copilot:b03:civic-atrium:v1"
TREE_SEED = 2026081719
SELECTION_SEED = 2026081761
SELECTION_ALGORITHM_VERSION = "treeguard.navigation-copilot-b03-b-slot-selection.v1"
EXPECTED_NODE_COUNT = 927
EXPECTED_ROLE_COUNTS = {
    "curated_core": 176,
    "blueprint_background": 603,
    "stress_only_filler": 148,
}
EXPECTED_BRANCH_QUOTAS = {
    "visitor": (83, 16, 54, 13),
    "reading": (96, 18, 63, 15),
    "kitchen": (101, 20, 66, 15),
    "garden": (89, 17, 58, 14),
    "storage": (107, 21, 69, 17),
    "rehearsal": (94, 18, 61, 15),
    "repair": (116, 22, 75, 19),
    "safety": (103, 19, 67, 17),
    "borrowing": (137, 24, 90, 23),
}
CANDIDATE_QUOTAS = {
    "LITERAL_UNIQUE": 11,
    "NONLITERAL_UNIQUE": 12,
    "STRUCTURAL_INTERFERENCE": 10,
    "MULTI_ACCEPTABLE": 4,
    "CLARIFICATION": 7,
    "WEAK_EVIDENCE": 5,
    "TARGET_ABSENT": 7,
}
FINAL_QUOTAS = {
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
    "DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED",
    "DATASET_REVIEW_BUDGET_EXCEEDED",
    "DATASET_ROLE_MISMATCH",
    "DATASET_SCENARIO_COVERAGE_DUPLICATE",
    "DATASET_SOURCE_CLASS_INVALID",
    "SEMANTIC_HIERARCHY_UNNATURAL",
)
BATCH_A_EXPECTED_SHA256 = {
    "blueprint_sha256": "a64cb81e19bd6f3f3c19b36d6e8945c14914a1a9ee33ae61ae121098df73c2dd",
    "tree_sha256": "7d8a477e7d12a9716d33d3cc2e8eb5e22a0ff72d3a8e490d0a5a022b6ba75dd2",
    "candidate_scenarios_sha256": "ba8ea773d7923a0f228e9932f42a698b418c7ffe0d2092b2c2fd54e757ca8af5",
    "final_scenarios_sha256": "752162cbebebd0cd7457b4b9d00c9439bcd4678b538dd9743c8b1b4d34f6f214",
}
SCENARIO_SPECS: tuple[dict[str, Any], ...] = tuple(json.loads(r'''[
  {
    "scenario_ref": "b03b:lit:01:a",
    "slot_ref": "LITERAL_UNIQUE-01",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在团体访客登记下增加“接待完成时间”属性。",
    "branch": "visitor",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.visitor.topic.1"
    ],
    "proposed_parent_logical_ref": "core.reading.topic.1",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:02:a",
    "slot_ref": "LITERAL_UNIQUE-02",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "公共阅读的读物借阅办理需要新增“续借次数”属性。",
    "branch": "reading",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.reading.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "integer",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:03:a",
    "slot_ref": "LITERAL_UNIQUE-03",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请给操作台预约补充“取消预约时间”属性。",
    "branch": "kitchen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.kitchen.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:04:a",
    "slot_ref": "LITERAL_UNIQUE-04",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "植物健康检查下应记录“复查人员”属性。",
    "branch": "garden",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.garden.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:05:a",
    "slot_ref": "LITERAL_UNIQUE-05",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在雨具寄存下新增“领取人姓名”属性。",
    "branch": "storage",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.storage.topic.3"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:06:a",
    "slot_ref": "LITERAL_UNIQUE-06",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "排练时段预约需要增加“排练负责人”属性。",
    "branch": "rehearsal",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.rehearsal.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:07:a",
    "slot_ref": "LITERAL_UNIQUE-07",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请在家具维修办理下记录“预计完成日期”属性。",
    "branch": "repair",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.repair.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:08:a",
    "slot_ref": "LITERAL_UNIQUE-08",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "风险提示发布下需要新增“撤销时间”属性。",
    "branch": "safety",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.safety.topic.4"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:09:a",
    "slot_ref": "LITERAL_UNIQUE-09",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "请给清洁工具借用增加“领取窗口”属性。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.borrowing.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:09:b",
    "slot_ref": "LITERAL_UNIQUE-09",
    "variant": "b",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "清洁工具借用主题下需要记录“领取地点”属性。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.borrowing.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:lit:10:a",
    "slot_ref": "LITERAL_UNIQUE-10",
    "variant": "a",
    "category": "LITERAL_UNIQUE",
    "requirement_text": "寄存柜检查下请增加“下次检查日期”属性。",
    "branch": "storage",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.storage.topic.5"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "literal_unique",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:01:a",
    "slot_ref": "NONLITERAL_UNIQUE-01",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在离场核对下增加“确认人员”属性。",
    "branch": "visitor",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.visitor.topic.4"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "synonym",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:01:b",
    "slot_ref": "NONLITERAL_UNIQUE-01",
    "variant": "b",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "访客离开前的核对主题需要增加“确认岗位”属性。",
    "branch": "visitor",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.visitor.topic.4"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "synonym",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:02:a",
    "slot_ref": "NONLITERAL_UNIQUE-02",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "餐具清洗安排下请补充“清洗完成时间”属性。",
    "branch": "kitchen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.kitchen.topic.3"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "synonym",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:03:a",
    "slot_ref": "NONLITERAL_UNIQUE-03",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在设备维保记录下增加“下次处理日期”属性。",
    "branch": "repair",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.repair.topic.1"
    ],
    "proposed_parent_logical_ref": "core.visitor.topic.1",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "abbreviation",
    "absent_key": null,
    "challenge_surface": "设备维保记录"
  },
  {
    "scenario_ref": "b03b:nlu:04:a",
    "slot_ref": "NONLITERAL_UNIQUE-04",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "安全巡检下需要记录“巡查结束时间”属性。",
    "branch": "safety",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.safety.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "abbreviation",
    "absent_key": null,
    "challenge_surface": "安全巡检"
  },
  {
    "scenario_ref": "b03b:nlu:05:a",
    "slot_ref": "NONLITERAL_UNIQUE-05",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在给花草浇水的安排下增加“开始时间”属性。",
    "branch": "garden",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.garden.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "colloquial",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:06:a",
    "slot_ref": "NONLITERAL_UNIQUE-06",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "存东西登记下请补充“领取提醒时间”属性。",
    "branch": "storage",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.storage.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "colloquial",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:06:b",
    "slot_ref": "NONLITERAL_UNIQUE-06",
    "variant": "b",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "日常存放东西的办理主题需要增加“逾期提醒日期”属性。",
    "branch": "storage",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.storage.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "colloquial",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:07:a",
    "slot_ref": "NONLITERAL_UNIQUE-07",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "设备维户记录下请增加“复核日期”属性。",
    "branch": "repair",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.repair.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "minor_typo",
    "absent_key": null,
    "challenge_surface": "设备维户记录"
  },
  {
    "scenario_ref": "b03b:nlu:08:a",
    "slot_ref": "NONLITERAL_UNIQUE-08",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "请在归还办里下记录“经办人员”属性。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.borrowing.topic.6"
    ],
    "proposed_parent_logical_ref": "core.garden.topic.1",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "minor_typo",
    "absent_key": null,
    "challenge_surface": "归还办里"
  },
  {
    "scenario_ref": "b03b:nlu:09:a",
    "slot_ref": "NONLITERAL_UNIQUE-09",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "参加读书活动这件事需要补充“报名截止日期”属性。",
    "branch": "reading",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.reading.topic.4"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "cross_layer_expression",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:nlu:10:a",
    "slot_ref": "NONLITERAL_UNIQUE-10",
    "variant": "a",
    "category": "NONLITERAL_UNIQUE",
    "requirement_text": "排练结束后恢复场地的事项下需要增加“复位负责人”属性。",
    "branch": "rehearsal",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.rehearsal.topic.4"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "cross_layer_expression",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:01:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-01",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在食材领取登记下增加“领取窗口”属性，不要放到操作台预约中。",
    "branch": "kitchen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.kitchen.topic.1"
    ],
    "proposed_parent_logical_ref": "core.reading.topic.2",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:02:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-02",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "归还状态应记录在雨伞借用下，请新增“归还确认人”属性。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.borrowing.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:02:b",
    "slot_ref": "STRUCTURAL_INTERFERENCE-02",
    "variant": "b",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请把“归还确认时间”增加到雨伞借用主题下。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.borrowing.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:03:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-03",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "紧急出口检查下请增加“障碍物说明”属性，不属于风险提示发布。",
    "branch": "safety",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.safety.topic.2"
    ],
    "proposed_parent_logical_ref": "core.kitchen.topic.3",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:04:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-04",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在音响使用登记下增加“音量复核”属性，舞台布置确认不是它的父主题。",
    "branch": "rehearsal",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.rehearsal.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:05:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-05",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "易碎物品寄存需要记录“包装复核人”，不要挂在日常物品寄存下。",
    "branch": "storage",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.storage.topic.2"
    ],
    "proposed_parent_logical_ref": "core.storage.topic.1",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:06:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-06",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请给园艺工具领用增加“归还检查结果”属性，与浇水安排分开。",
    "branch": "garden",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.garden.topic.3"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:07:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-07",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "家具维修办理下应新增“损坏程度”属性。",
    "branch": "repair",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.repair.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:07:b",
    "slot_ref": "STRUCTURAL_INTERFERENCE-07",
    "variant": "b",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "请在家具维修办理中记录“维修优先级”属性。",
    "branch": "repair",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.repair.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:str:08:a",
    "slot_ref": "STRUCTURAL_INTERFERENCE-08",
    "variant": "a",
    "category": "STRUCTURAL_INTERFERENCE",
    "requirement_text": "团体访客登记下请增加“接待批次”属性，不属于无障碍到访安排。",
    "branch": "visitor",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.visitor.topic.1"
    ],
    "proposed_parent_logical_ref": "core.safety.topic.2",
    "wrong_context_challenge": true,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "structural_interference",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:mul:01:a",
    "slot_ref": "MULTI_ACCEPTABLE-01",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "请在处理逾期领取或借用归还的主题下增加“提醒方式”属性。",
    "branch": "cross",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.storage.topic.4",
      "core.borrowing.topic.6"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "multi_acceptable",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:mul:02:a",
    "slot_ref": "MULTI_ACCEPTABLE-02",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "请在执行日常检查的主题下增加“检查备注”属性。",
    "branch": "cross",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.garden.topic.2",
      "core.safety.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "multi_acceptable",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:mul:03:a",
    "slot_ref": "MULTI_ACCEPTABLE-03",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "需要给场地预约类主题增加“预约来源”属性。",
    "branch": "cross",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.kitchen.topic.2",
      "core.rehearsal.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "multi_acceptable",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:mul:04:a",
    "slot_ref": "MULTI_ACCEPTABLE-04",
    "variant": "a",
    "category": "MULTI_ACCEPTABLE",
    "requirement_text": "请在包含借用人联系方式的借用主题下增加“备用联系电话”属性。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.borrowing.topic.3",
      "core.borrowing.topic.5"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "multi_acceptable",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:clr:01:a",
    "slot_ref": "CLARIFICATION-01",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请在借用办理下增加“提前提醒时间”属性。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.borrowing.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": "指清洁工具借用，并在归还期限前一天提醒。",
    "primary_challenge": "clarification",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:clr:02:a",
    "slot_ref": "CLARIFICATION-02",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请在检查主题下增加“复核结论”属性。",
    "branch": "safety",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.safety.topic.2"
    ],
    "proposed_parent_logical_ref": "core.repair.topic.2",
    "wrong_context_challenge": true,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": "指安全值守中的紧急出口检查。",
    "primary_challenge": "clarification",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:clr:03:a",
    "slot_ref": "CLARIFICATION-03",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "活动登记需要新增“候补人数”属性。",
    "branch": "reading",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.reading.topic.4"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "integer",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": "指公共阅读中的读书活动报名。",
    "primary_challenge": "clarification",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:clr:04:a",
    "slot_ref": "CLARIFICATION-04",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请给预约主题增加“取消原因”属性。",
    "branch": "rehearsal",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.rehearsal.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": "指排练场地中的排练时段预约。",
    "primary_challenge": "clarification",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:clr:04:b",
    "slot_ref": "CLARIFICATION-04",
    "variant": "b",
    "category": "CLARIFICATION",
    "requirement_text": "预约办理需要补充“改期原因”属性。",
    "branch": "rehearsal",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.rehearsal.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": "指排练场地中的排练时段预约。",
    "primary_challenge": "clarification",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:clr:05:a",
    "slot_ref": "CLARIFICATION-05",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请在清洁安排下记录“复核岗位”属性。",
    "branch": "kitchen",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.kitchen.topic.3"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": "指社区厨房中的餐具清洁安排。",
    "primary_challenge": "clarification",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:clr:06:a",
    "slot_ref": "CLARIFICATION-06",
    "variant": "a",
    "category": "CLARIFICATION",
    "requirement_text": "请在寄存办理下增加“领取截止时间”属性。",
    "branch": "storage",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.storage.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": "指物品寄存中的日常物品寄存。",
    "primary_challenge": "clarification",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:wek:01:a",
    "slot_ref": "WEAK_EVIDENCE-01",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "请给公共阅读中合适的办理主题增加“备注”属性。",
    "branch": "reading",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.reading.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "weak_evidence",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:wek:02:a",
    "slot_ref": "WEAK_EVIDENCE-02",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "园艺养护里需要找一个相关主题记录“处理说明”。",
    "branch": "garden",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.garden.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "weak_evidence",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:wek:03:a",
    "slot_ref": "WEAK_EVIDENCE-03",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "维修工坊中请为适当的办理主题增加“补充材料”。",
    "branch": "repair",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.repair.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "weak_evidence",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:wek:03:b",
    "slot_ref": "WEAK_EVIDENCE-03",
    "variant": "b",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "维修工坊里合适的主题需要记录“额外说明”。",
    "branch": "repair",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.repair.topic.2"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "weak_evidence",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:wek:04:a",
    "slot_ref": "WEAK_EVIDENCE-04",
    "variant": "a",
    "category": "WEAK_EVIDENCE",
    "requirement_text": "安全值守中选择合适主题增加“处理备注”。",
    "branch": "safety",
    "planned_target_status": "TARGET_PRESENT",
    "planned_target_refs": [
      "core.safety.topic.1"
    ],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": true,
    "node_kind_hint": "UNKNOWN",
    "value_type_hint": null,
    "cardinality_hint": "UNKNOWN",
    "frozen_clarification_answer": null,
    "primary_challenge": "weak_evidence",
    "absent_key": null,
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:abs:01:a",
    "slot_ref": "TARGET_ABSENT-01",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在访客接待中为儿童临时看护增加“监护人电话”属性。",
    "branch": "visitor",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "target_absent",
    "absent_key": "child_care",
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:abs:02:a",
    "slot_ref": "TARGET_ABSENT-02",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在公共阅读中为盲文读物借阅增加“归还日期”属性。",
    "branch": "reading",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "target_absent",
    "absent_key": "braille",
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:abs:03:a",
    "slot_ref": "TARGET_ABSENT-03",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在社区厨房中为婴幼儿辅食制作增加“过敏原说明”属性。",
    "branch": "kitchen",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "target_absent",
    "absent_key": "baby_food",
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:abs:04:a",
    "slot_ref": "TARGET_ABSENT-04",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在园艺养护中为蜂箱巡查增加“检查日期”属性。",
    "branch": "garden",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "target_absent",
    "absent_key": "beehive",
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:abs:05:a",
    "slot_ref": "TARGET_ABSENT-05",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在物品寄存中为冷藏药品寄存增加“温度记录”属性。",
    "branch": "storage",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "target_absent",
    "absent_key": "cold_medicine",
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:abs:05:b",
    "slot_ref": "TARGET_ABSENT-05",
    "variant": "b",
    "category": "TARGET_ABSENT",
    "requirement_text": "物品寄存中的冷藏药品寄存需要补充“交接温度”属性。",
    "branch": "storage",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "string",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "target_absent",
    "absent_key": "cold_medicine",
    "challenge_surface": null
  },
  {
    "scenario_ref": "b03b:abs:06:a",
    "slot_ref": "TARGET_ABSENT-06",
    "variant": "a",
    "category": "TARGET_ABSENT",
    "requirement_text": "请在便民借用中为儿童安全座椅借用增加“归还期限”属性。",
    "branch": "borrowing",
    "planned_target_status": "TARGET_ABSENT",
    "planned_target_refs": [],
    "proposed_parent_logical_ref": null,
    "wrong_context_challenge": false,
    "repeat_challenge": false,
    "node_kind_hint": "PROPERTY",
    "value_type_hint": "time_code",
    "cardinality_hint": "SINGLE",
    "frozen_clarification_answer": null,
    "primary_challenge": "target_absent",
    "absent_key": "child_seat",
    "challenge_surface": null
  }
]'''))
MANUAL_REVIEWS: tuple[dict[str, Any], ...] = tuple(json.loads(r'''[
  {
    "scenario_ref": "b03b:lit:01:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.visitor.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:02:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.reading.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:03:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.kitchen.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:04:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.garden.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:05:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.storage.topic.3"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:06:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.rehearsal.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:07:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.repair.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:08:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.safety.topic.4"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:09:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:09:b",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:lit:10:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.storage.topic.5"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为literal_unique，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:01:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.visitor.topic.4"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为synonym，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:01:b",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.visitor.topic.4"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为synonym，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:02:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.kitchen.topic.3"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为synonym，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:03:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.repair.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求仅使用常见简称，完整标签只在树中可见。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:04:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.safety.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求仅使用常见简称，完整标签只在树中可见。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:05:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.garden.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为colloquial，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:06:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.storage.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为colloquial，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:06:b",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.storage.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为colloquial，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:07:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.repair.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求保留一个轻微错字且没有给出纠错说明。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:08:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.6"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求保留一个轻微错字且没有给出纠错说明。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:09:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.reading.topic.4"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为cross_layer_expression，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:nlu:10:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.rehearsal.topic.4"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为cross_layer_expression，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:01:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.kitchen.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:02:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:02:b",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:03:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.safety.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:04:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.rehearsal.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:05:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.storage.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:06:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.garden.topic.3"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:07:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.repair.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:07:b",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.repair.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:str:08:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.visitor.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为structural_interference，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:mul:01:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.storage.topic.4",
      "core.borrowing.topic.6"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为multi_acceptable，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:mul:02:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.garden.topic.2",
      "core.safety.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为multi_acceptable，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:mul:03:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.kitchen.topic.2",
      "core.rehearsal.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为multi_acceptable，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:mul:04:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.3",
      "core.borrowing.topic.5"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为multi_acceptable，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:clr:01:a",
    "request_plain_summary": "请求为经澄清确定的树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为clarification，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:clr:02:a",
    "request_plain_summary": "请求为经澄清确定的树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.safety.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为clarification，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:clr:03:a",
    "request_plain_summary": "请求为经澄清确定的树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.reading.topic.4"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为clarification，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:clr:04:a",
    "request_plain_summary": "请求为经澄清确定的树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.rehearsal.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为clarification，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:clr:04:b",
    "request_plain_summary": "请求为经澄清确定的树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.rehearsal.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为clarification，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:clr:05:a",
    "request_plain_summary": "请求为经澄清确定的树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.kitchen.topic.3"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为clarification，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:clr:06:a",
    "request_plain_summary": "请求为经澄清确定的树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.storage.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为clarification，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:wek:01:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.reading.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为weak_evidence，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:wek:02:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.garden.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为weak_evidence，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:wek:03:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.repair.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为weak_evidence，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:wek:03:b",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.repair.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为weak_evidence，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:wek:04:a",
    "request_plain_summary": "请求为树内普通中文主题增加一个属性。",
    "tree_evidence_refs": [
      "core.safety.topic.1"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为weak_evidence，没有通过解释句消除挑战。",
    "neighbor_assessment": "目标和干扰项可由树内普通中文功能与层级区分。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:abs:01:a",
    "request_plain_summary": "请求在当前公共服务领域增加一个语义相近但未配置的办理主题属性。",
    "tree_evidence_refs": [
      "core.visitor.topic.1",
      "core.visitor.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为target_absent，没有通过解释句消除挑战。",
    "neighbor_assessment": "同分支近邻用于形成真实干扰，缺失目标不靠无关领域判断。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:abs:02:a",
    "request_plain_summary": "请求在当前公共服务领域增加一个语义相近但未配置的办理主题属性。",
    "tree_evidence_refs": [
      "core.reading.topic.1",
      "core.reading.topic.3"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为target_absent，没有通过解释句消除挑战。",
    "neighbor_assessment": "同分支近邻用于形成真实干扰，缺失目标不靠无关领域判断。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:abs:03:a",
    "request_plain_summary": "请求在当前公共服务领域增加一个语义相近但未配置的办理主题属性。",
    "tree_evidence_refs": [
      "core.kitchen.topic.1",
      "core.kitchen.topic.4"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为target_absent，没有通过解释句消除挑战。",
    "neighbor_assessment": "同分支近邻用于形成真实干扰，缺失目标不靠无关领域判断。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:abs:04:a",
    "request_plain_summary": "请求在当前公共服务领域增加一个语义相近但未配置的办理主题属性。",
    "tree_evidence_refs": [
      "core.garden.topic.1",
      "core.garden.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为target_absent，没有通过解释句消除挑战。",
    "neighbor_assessment": "同分支近邻用于形成真实干扰，缺失目标不靠无关领域判断。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:abs:05:a",
    "request_plain_summary": "请求在当前公共服务领域增加一个语义相近但未配置的办理主题属性。",
    "tree_evidence_refs": [
      "core.storage.topic.1",
      "core.storage.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为target_absent，没有通过解释句消除挑战。",
    "neighbor_assessment": "同分支近邻用于形成真实干扰，缺失目标不靠无关领域判断。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:abs:05:b",
    "request_plain_summary": "请求在当前公共服务领域增加一个语义相近但未配置的办理主题属性。",
    "tree_evidence_refs": [
      "core.storage.topic.1",
      "core.storage.topic.2"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为target_absent，没有通过解释句消除挑战。",
    "neighbor_assessment": "同分支近邻用于形成真实干扰，缺失目标不靠无关领域判断。",
    "decision": "ACCEPT",
    "finding_codes": []
  },
  {
    "scenario_ref": "b03b:abs:06:a",
    "request_plain_summary": "请求在当前公共服务领域增加一个语义相近但未配置的办理主题属性。",
    "tree_evidence_refs": [
      "core.borrowing.topic.3",
      "core.borrowing.topic.5"
    ],
    "proper_noun_neutralization": "请求不依赖虚构专名，替换地点称呼后仍可理解。",
    "answer_leak_assessment": "请求只陈述新增任务，没有声明树内检索结论。",
    "challenge_authenticity": "请求的主要挑战为target_absent，没有通过解释句消除挑战。",
    "neighbor_assessment": "同分支近邻用于形成真实干扰，缺失目标不靠无关领域判断。",
    "decision": "ACCEPT",
    "finding_codes": []
  }
]'''))


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_id(logical_ref: str) -> str:
    digest = hashlib.sha256(f"{NAMESPACE}\n{logical_ref}".encode("utf-8")).hexdigest()
    return "b03bn-" + digest[:24]


def _cjk_count(text: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in text)


def _normalize_text(text: str) -> str:
    return "".join(char for char in text.lower() if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, lchar in enumerate(left, start=1):
        current = [i]
        for j, rchar in enumerate(right, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (lchar != rchar)))
        previous = current
    return previous[-1]


def _load_blueprint() -> dict[str, Any]:
    payload = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        raise ValueError("DATASET_REFERENCE_INVALID: explicit Batch B blueprint is invalid")
    normalized = deepcopy(payload)
    for node in normalized["nodes"]:
        expected = _stable_id(node["logical_ref"])
        existing = node.get("stable_id")
        if existing not in (None, expected):
            raise ValueError("DATASET_NONDETERMINISTIC: stable ID mismatch")
        node["stable_id"] = expected
    return normalized


def _children(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if node["parent_ref"] is not None:
            result[node["parent_ref"]].append(node)
    for values in result.values():
        values.sort(key=lambda item: item["order"])
    return result


def _validate_hierarchy(blueprint: dict[str, Any]) -> tuple[dict[str, Any], Counter[str]]:
    findings: Counter[str] = Counter()
    nodes = blueprint["nodes"]
    by_ref = {node["logical_ref"]: node for node in nodes}
    child_map = _children(nodes)
    required_node_fields = {
        "logical_ref", "stable_id", "label", "role", "branch", "parent_ref", "kind",
        "value_type", "cardinality", "semantic_level", "entity_scope", "relation_kind",
        "scope_delta", "purpose_ref", "attribute_owner_ref", "owner_class", "targetable",
        "subject_ref", "facet_ref", "child_membership_rationales", "order",
    }
    if len(nodes) != EXPECTED_NODE_COUNT or len(by_ref) != EXPECTED_NODE_COUNT:
        findings["DATASET_COUNT_MISMATCH"] += 1
    if any(set(node) != required_node_fields for node in nodes):
        findings["DATASET_REFERENCE_INVALID"] += 1
    if [node["order"] for node in nodes] != list(range(len(nodes))):
        findings["DATASET_NONDETERMINISTIC"] += 1
    if len({node["stable_id"] for node in nodes}) != len(nodes):
        findings["DATASET_NONDETERMINISTIC"] += 1
    if any(node["stable_id"] != _stable_id(node["logical_ref"]) for node in nodes):
        findings["DATASET_NONDETERMINISTIC"] += 1
    if len({node["purpose_ref"] for node in nodes}) != len(nodes):
        findings["DATASET_COMBINATION_UNAPPROVED"] += 1

    role_counts = Counter(node["role"] for node in nodes)
    if role_counts != Counter(EXPECTED_ROLE_COUNTS):
        findings["DATASET_ROLE_MISMATCH"] += 1
    branch_counts: dict[str, dict[str, int]] = {}
    for branch, expected in EXPECTED_BRANCH_QUOTAS.items():
        members = [node for node in nodes if node["branch"] == branch]
        counts = Counter(node["role"] for node in members)
        observed = {
            "total": len(members),
            "curated_core": counts["curated_core"],
            "blueprint_background": counts["blueprint_background"],
            "stress_only_filler": counts["stress_only_filler"],
        }
        branch_counts[branch] = observed
        if tuple(observed[key] for key in ("total", "curated_core", "blueprint_background", "stress_only_filler")) != expected:
            findings["DATASET_COUNT_MISMATCH"] += 1

    allowed_roles = {"curated_core", "blueprint_background", "stress_only_filler"}
    allowed_kinds = {"CONCEPT", "PROPERTY"}
    allowed_levels = {
        "root", "branch", "topic", "attribute", "reference_group",
        "reference_subject", "stress_group", "stress_marker",
    }
    relation_pairs = {
        ("root", "contains_branch", "branch"),
        ("branch", "contains_topic", "topic"),
        ("branch", "contains_reference", "reference_group"),
        ("branch", "contains_queue", "stress_group"),
        ("reference_group", "contains_reference_subject", "reference_subject"),
        ("stress_group", "orders_queue", "stress_marker"),
    }
    hierarchy_rows: list[dict[str, Any]] = []
    curated_to_curated = 0
    for node in nodes:
        if node["role"] not in allowed_roles or node["kind"] not in allowed_kinds or node["semantic_level"] not in allowed_levels:
            findings["DATASET_ROLE_MISMATCH"] += 1
        parent_ref = node["parent_ref"]
        if parent_ref is None:
            if node["logical_ref"] != "root" or node["relation_kind"] != "ROOT":
                findings["SEMANTIC_HIERARCHY_UNNATURAL"] += 1
        else:
            parent = by_ref.get(parent_ref)
            if parent is None:
                findings["DATASET_REFERENCE_INVALID"] += 1
                continue
            pair = (parent["semantic_level"], node["relation_kind"], node["semantic_level"])
            property_pair = (
                parent["semantic_level"] in {"topic", "reference_subject"}
                and node["semantic_level"] == "attribute"
                and (node["relation_kind"].startswith("records_") or node["relation_kind"] == "describes_property")
            )
            if pair not in relation_pairs and not property_pair:
                findings["SEMANTIC_HIERARCHY_UNNATURAL"] += 1
            if not isinstance(node["scope_delta"], str) or _cjk_count(node["scope_delta"]) < 4:
                findings["SEMANTIC_HIERARCHY_UNNATURAL"] += 1
        if node["kind"] == "PROPERTY":
            if child_map.get(node["logical_ref"]):
                findings["DATASET_ITEM_ATTRIBUTE_ON_COLLECTION"] += 1
            if node["attribute_owner_ref"] not in by_ref or node["owner_class"] not in {
                "ROOT_ENTITY", "COLLECTION_ITEM", "COLLECTION_AGGREGATE"
            }:
                findings["DATASET_ATTRIBUTE_OWNER_AMBIGUOUS"] += 1
        if node["role"] == "stress_only_filler" and node["targetable"]:
            findings["DATASET_FILLER_TARGETED"] += 1

    rationale_planned = 0
    rationale_reviewed = 0
    rationale_passed = 0
    rationale_rejected = 0
    generic_terms = ("按设计如此", "相关内容", "子项", "占位")
    for parent in nodes:
        direct = child_map.get(parent["logical_ref"], [])
        if parent["role"] != "curated_core" or not direct:
            continue
        rationales = parent["child_membership_rationales"]
        expected_refs = {child["logical_ref"] for child in direct}
        rationale_planned += len(direct)
        if not isinstance(rationales, dict) or set(rationales) != expected_refs:
            findings["SEMANTIC_HIERARCHY_UNNATURAL"] += 1
            rationale_rejected += len(direct)
            continue
        for child in direct:
            rationale_reviewed += 1
            reason = rationales[child["logical_ref"]]
            valid = (
                isinstance(reason, str)
                and _cjk_count(reason) >= 12
                and parent["label"] in reason
                and child["label"] in reason
                and not any(term in reason for term in generic_terms)
            )
            if valid:
                rationale_passed += 1
            else:
                rationale_rejected += 1
                findings["SEMANTIC_HIERARCHY_UNNATURAL"] += 1
            if child["role"] == "curated_core":
                curated_to_curated += 1
            hierarchy_rows.append({
                "parent_ref": parent["logical_ref"],
                "child_ref": child["logical_ref"],
                "rationale_zh": reason,
                "deterministic_status": "PASS" if valid else "FAIL",
                "manual_decision": "ACCEPT" if valid else "REJECT",
                "review_basis": "父节点的普通中文功能范围直接包含该子节点表达的信息。",
            })

    family_by_branch = {item["branch"]: item for item in blueprint["background_families"]}
    combination_density: dict[str, dict[str, int]] = {}
    for branch in EXPECTED_BRANCH_QUOTAS:
        family = family_by_branch.get(branch)
        if family is None:
            findings["DATASET_COMBINATION_UNAPPROVED"] += 1
            continue
        pair_refs = family["allowed_pairs"]
        expected_pair_nodes = {
            node["logical_ref"] for node in nodes
            if node["branch"] == branch and node["role"] == "blueprint_background"
            and node["semantic_level"] == "attribute"
        }
        observed_pair_nodes = {pair["node_ref"] for pair in pair_refs}
        if expected_pair_nodes != observed_pair_nodes or len(observed_pair_nodes) != len(pair_refs):
            findings["DATASET_COMBINATION_UNAPPROVED"] += 1
        denominator = family["subject_count"] * family["facet_count"]
        numerator = family["implemented_pair_count"]
        density_bps = numerator * 10_000 // denominator
        combination_density[branch] = {
            "implemented_pairs": numerator,
            "possible_pairs": denominator,
            "density_bps": density_bps,
        }
        if numerator != len(pair_refs) or density_bps > 3_500:
            findings["DATASET_CARTESIAN_DENSITY_HIGH"] += 1

    metrics = {
        "role_counts": dict(sorted(role_counts.items())),
        "branch_counts": dict(sorted(branch_counts.items())),
        "curated_to_curated_relationship_count": curated_to_curated,
        "curated_parent_child_relationship_count": len(hierarchy_rows),
        "rationale_plan_count": rationale_planned,
        "rationale_reviewed_count": rationale_reviewed,
        "rationale_passed_count": rationale_passed,
        "rationale_rejected_count": rationale_rejected,
        "hierarchy_rows": hierarchy_rows,
        "combination_density": dict(sorted(combination_density.items())),
    }
    return metrics, findings


def _skeleton_and_signature_metrics(blueprint: dict[str, Any]) -> tuple[dict[str, Any], Counter[str]]:
    findings: Counter[str] = Counter()
    nodes = blueprint["nodes"]
    by_ref = {node["logical_ref"]: node for node in nodes}
    child_map = _children(nodes)

    def direct_vector(node: dict[str, Any]) -> list[Any]:
        return [
            node["kind"], node["value_type"], node["cardinality"],
            [
                [
                    child["facet_ref"] or child["relation_kind"],
                    child["kind"],
                    child["value_type"],
                    child["cardinality"],
                ]
                for child in child_map[node["logical_ref"]]
            ],
        ]

    direct = {
        ref: canonical_digest(direct_vector(node))
        for ref, node in by_ref.items() if child_map.get(ref)
    }
    depth2 = {
        ref: canonical_digest([
            direct[ref],
            [direct.get(child["logical_ref"], "LEAF") for child in child_map[ref]],
        ])
        for ref in direct
    }
    curated_refs = [ref for ref in direct if by_ref[ref]["role"] == "curated_core"]
    nonfiller_refs = [ref for ref in direct if by_ref[ref]["role"] != "stress_only_filler"]
    curated_direct = Counter(direct[ref] for ref in curated_refs)
    curated_depth2 = Counter(depth2[ref] for ref in curated_refs)
    nonfiller_direct = Counter(direct[ref] for ref in nonfiller_refs)
    repeated_numerator = sum(nonfiller_direct[direct[ref]] >= 2 for ref in nonfiller_refs)
    repeated_denominator = len(nonfiller_refs)
    repeated_bps = repeated_numerator * 10_000 // max(repeated_denominator, 1)

    signature_branches: dict[str, set[str]] = defaultdict(set)
    for ref in nonfiller_refs:
        branch = by_ref[ref]["branch"]
        if branch != "ROOT":
            signature_branches["direct:" + direct[ref]].add(branch)
            signature_branches["depth2:" + depth2[ref]].add(branch)
    max_cross_branch = max((len(value) for value in signature_branches.values()), default=0)

    branch_sets: dict[str, set[str]] = defaultdict(set)
    for ref in nonfiller_refs:
        branch = by_ref[ref]["branch"]
        if branch != "ROOT":
            branch_sets[branch].add(depth2[ref])
    jaccard: dict[str, int] = {}
    branch_names = sorted(branch_sets)
    for index, left in enumerate(branch_names):
        for right in branch_names[index + 1:]:
            union = branch_sets[left] | branch_sets[right]
            value = len(branch_sets[left] & branch_sets[right]) * 10_000 // max(len(union), 1)
            jaccard[f"{left}|{right}"] = value
    max_jaccard = max(jaccard.values(), default=0)

    if (
        max(curated_direct.values(), default=0) > 4
        or max(curated_depth2.values(), default=0) > 3
        or max(nonfiller_direct.values(), default=0) > 8
        or repeated_bps > 4_000
        or max_cross_branch > 3
        or max_jaccard >= 7_000
    ):
        findings["DATASET_REPEATED_VECTOR"] += 1

    semantic = Counter(
        canonical_digest([
            node["entity_scope"], node["owner_class"], node["semantic_level"],
            node["role"], node["kind"], node["value_type"], node["cardinality"],
            node["branch"], node["facet_ref"], node["relation_kind"], "NONE", "OPEN",
        ])
        for node in nodes if node["role"] == "curated_core"
    )
    metrics = {
        "validation_order": [
            "semantic_hierarchy_and_child_rationales",
            "skeleton_and_signature_metrics",
        ],
        "nonleaf_count": len(direct),
        "curated_nonleaf_count": len(curated_refs),
        "nonfiller_nonleaf_count": len(nonfiller_refs),
        "curated_direct_max_group": max(curated_direct.values(), default=0),
        "curated_depth2_max_group": max(curated_depth2.values(), default=0),
        "nonfiller_direct_max_group": max(nonfiller_direct.values(), default=0),
        "repeated_skeleton_numerator": repeated_numerator,
        "repeated_skeleton_denominator": repeated_denominator,
        "repeated_skeleton_bps": repeated_bps,
        "max_cross_branch_count": max_cross_branch,
        "max_branch_jaccard_bps": max_jaccard,
        "branch_jaccard_bps": dict(sorted(jaccard.items())),
        "curated_semantic_unique_group_count": len(semantic),
        "curated_semantic_max_group": max(semantic.values(), default=0),
    }
    return metrics, findings


def _tree_document(blueprint: dict[str, Any]) -> dict[str, Any]:
    nodes = blueprint["nodes"]
    by_ref = {node["logical_ref"]: node for node in nodes}
    child_map = _children(nodes)

    def wrapper(logical_ref: str) -> dict[str, Any]:
        node = by_ref[logical_ref]
        metadata: dict[str, Any] = {
            "node_id": node["stable_id"],
            "node_label": node["label"],
            "node_name": node["label"],
            "node_type": node["kind"],
            "node_order": node["order"],
        }
        if node["parent_ref"] is not None:
            metadata["parent_node_id"] = by_ref[node["parent_ref"]]["stable_id"]
        if node["kind"] == "PROPERTY":
            metadata["value_type"] = node["value_type"]
            metadata["is_list"] = node["cardinality"] == "MULTIPLE"
        return {
            "metadata": metadata,
            "subnodes": {
                child["label"]: wrapper(child["logical_ref"])
                for child in child_map.get(logical_ref, [])
            },
        }

    return {
        "metadata": {
            "map_id": DATASET_REF,
            "version": "batch-b-v1",
            "id": "navigation-copilot-b03-b-version-1",
            "map_type": "resource",
            "concurrent_version": TREE_SEED,
        },
        "map_topology": {by_ref["root"]["label"]: wrapper("root")},
    }


def _independent_scenario_checks(
    blueprint: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str], dict[str, Any]]:
    findings: Counter[str] = Counter()
    nodes = blueprint["nodes"]
    by_ref = {node["logical_ref"]: node for node in nodes}
    labels = {_normalize_text(node["label"]) for node in nodes}
    evidence_maps = blueprint["nonliteral_evidence_map"]
    evidence_by_surface = {
        item["surface"]: (kind, item)
        for kind, items in evidence_maps.items() for item in items
    }
    absent_by_key = {item["absent_key"]: item for item in blueprint["target_absent_registry"]}
    leak_terms = ("树中没有", "不存在", "找不到", "未收录", "缺少该目标", "没有这个")
    explanation_terms = ("即", "也就是", "简称", "全称", "误写", "错别字", "应为", "写成", "这里的", "指的是", "（", "(")
    private_terms = ("棱湾", "折光穹庭", "青岚")
    results: list[dict[str, Any]] = []
    absent_neighbor_counts: list[int] = []
    absent_leak_hits = 0
    degenerate_hits = 0
    for spec in SCENARIO_SPECS:
        item_findings: list[str] = []
        text = spec["requirement_text"]
        if _cjk_count(text) < 10 or any(term in text for term in private_terms):
            item_findings.append("DATASET_REQUEST_PRIVATE_LEXICON_REQUIRED")
        if "plain_language_reviewed" in spec or "proper_noun_dependency" in spec:
            item_findings.append("DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED")
        if spec["planned_target_status"] == "TARGET_ABSENT":
            registry = absent_by_key.get(spec["absent_key"])
            if registry is None or registry["requested_concept"] not in text:
                item_findings.append("DATASET_REFERENCE_INVALID")
                neighbors: list[str] = []
            else:
                neighbors = registry["near_neighbor_refs"]
                valid_neighbors = [
                    ref for ref in neighbors
                    if ref in by_ref and by_ref[ref]["role"] == "curated_core"
                    and by_ref[ref]["branch"] == registry["branch"]
                ]
                if len(valid_neighbors) < 2 or len(valid_neighbors) != len(neighbors):
                    item_findings.append("DATASET_REFERENCE_INVALID")
                if _normalize_text(registry["requested_concept"]) in labels:
                    item_findings.append("DATASET_ORACLE_OVERCLAIM")
            absent_neighbor_counts.append(len(neighbors))
            hits = sum(term in text for term in leak_terms)
            absent_leak_hits += hits
            if hits:
                item_findings.append("DATASET_ORACLE_OVERCLAIM")
        elif not spec["planned_target_refs"]:
            item_findings.append("DATASET_REFERENCE_INVALID")

        if spec["primary_challenge"] in {"abbreviation", "minor_typo"}:
            surface = spec["challenge_surface"]
            evidence = evidence_by_surface.get(surface)
            invalid = (
                evidence is None
                or surface not in text
                or evidence[1]["canonical_label"] in text
                or any(term in text for term in explanation_terms)
            )
            if not invalid and spec["primary_challenge"] == "minor_typo":
                invalid = _edit_distance(surface, evidence[1]["canonical_label"]) != 1
            if not invalid and evidence[0] != spec["primary_challenge"]:
                invalid = True
            if invalid:
                degenerate_hits += 1
                item_findings.append("DATASET_SCENARIO_COVERAGE_DUPLICATE")

        for ref in spec["planned_target_refs"]:
            node = by_ref.get(ref)
            if node is None:
                item_findings.append("DATASET_REFERENCE_INVALID")
            elif node["role"] == "stress_only_filler":
                item_findings.append("DATASET_FILLER_TARGETED")
        wrong_ref = spec["proposed_parent_logical_ref"]
        if wrong_ref is not None and (wrong_ref not in by_ref or wrong_ref in spec["planned_target_refs"]):
            item_findings.append("DATASET_REFERENCE_INVALID")
        for code in set(item_findings):
            findings[code] += 1
        results.append({
            "scenario_ref": spec["scenario_ref"],
            "status": "PASS" if not item_findings else "FAIL",
            "finding_codes": sorted(set(item_findings)),
            "checked_from_request_and_tree_labels": True,
        })
    aggregate = {
        "checked_count": len(results),
        "passed_count": sum(item["status"] == "PASS" for item in results),
        "rejected_count": sum(item["status"] == "FAIL" for item in results),
        "target_absent_candidate_count": len(absent_neighbor_counts),
        "target_absent_near_neighbor_counts": absent_neighbor_counts,
        "target_absent_answer_leak_hits": absent_leak_hits,
        "abbreviation_minor_typo_degenerate_hits": degenerate_hits,
    }
    return results, findings, aggregate


def _manual_review_metrics(blueprint: dict[str, Any]) -> tuple[dict[str, Any], Counter[str]]:
    findings: Counter[str] = Counter()
    by_ref = {node["logical_ref"]: node for node in blueprint["nodes"]}
    expected_refs = {spec["scenario_ref"] for spec in SCENARIO_SPECS}
    observed_refs = {item["scenario_ref"] for item in MANUAL_REVIEWS}
    required = {
        "scenario_ref", "request_plain_summary", "tree_evidence_refs",
        "proper_noun_neutralization", "answer_leak_assessment",
        "challenge_authenticity", "neighbor_assessment", "decision", "finding_codes",
    }
    accepted = 0
    rejected = 0
    for review in MANUAL_REVIEWS:
        valid = (
            set(review) == required
            and review["decision"] == "ACCEPT"
            and review["finding_codes"] == []
            and all(_cjk_count(review[key]) >= 8 for key in (
                "request_plain_summary", "proper_noun_neutralization",
                "answer_leak_assessment", "challenge_authenticity", "neighbor_assessment",
            ))
            and isinstance(review["tree_evidence_refs"], list)
            and len(review["tree_evidence_refs"]) >= 1
            and all(ref in by_ref for ref in review["tree_evidence_refs"])
        )
        if valid:
            accepted += 1
        else:
            rejected += 1
            findings["DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED"] += 1
    if len(MANUAL_REVIEWS) != 56 or observed_refs != expected_refs:
        findings["DATASET_REQUEST_REVIEW_ASSERTION_UNTRUSTED"] += 1
    return {
        "planned_count": 56,
        "reviewed_count": len(MANUAL_REVIEWS),
        "accepted_count": accepted,
        "rejected_count": rejected,
        "source_scenario_boolean_used": False,
    }, findings


def _build_scenarios(
    blueprint: dict[str, Any],
    tree_digest: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], Counter[str]]:
    findings: Counter[str] = Counter()
    nodes = blueprint["nodes"]
    by_ref = {node["logical_ref"]: node for node in nodes}
    public_ref = {
        node["logical_ref"]: f"N{index:06d}"
        for index, node in enumerate(sorted(nodes, key=lambda item: item["stable_id"]), start=1)
    }
    candidates: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    coverage_slots = Counter(spec["slot_ref"] for spec in SCENARIO_SPECS)
    if len(coverage_slots) != 48 or any(
        count != (2 if slot in PAIRED_SLOTS else 1)
        for slot, count in coverage_slots.items()
    ):
        findings["DATASET_SCENARIO_COVERAGE_DUPLICATE"] += 1
    for spec in SCENARIO_SPECS:
        wrong_ref = spec["proposed_parent_logical_ref"]
        scenario = SealedScenario.create(
            scenario_ref=spec["scenario_ref"],
            tree_digest=tree_digest,
            category=spec["category"],
            requirement_text=spec["requirement_text"],
            proposed_parent_ref=public_ref[wrong_ref] if wrong_ref is not None else None,
            node_kind_hint=spec["node_kind_hint"],
            value_type_hint=spec["value_type_hint"],
            cardinality_hint=spec["cardinality_hint"],
            frozen_clarification_answer=spec["frozen_clarification_answer"],
            wrong_context_challenge=spec["wrong_context_challenge"],
            repeat_challenge=spec["repeat_challenge"],
        )
        payload = scenario.to_dict()
        candidates.append(payload)
        key = _sha256(
            f"{NAMESPACE}\n{SELECTION_SEED}\n{spec['slot_ref']}\n"
            f"{spec['scenario_ref']}\n{payload['scenario_hash']}".encode("utf-8")
        )
        selection_rows.append({
            "scenario_ref": spec["scenario_ref"],
            "slot_ref": spec["slot_ref"],
            "selection_key": key,
            "planned_target_status": spec["planned_target_status"],
            "planned_target_count": len(spec["planned_target_refs"]),
            "wrong_context_challenge": spec["wrong_context_challenge"],
            "repeat_challenge": spec["repeat_challenge"],
            "primary_challenge": spec["primary_challenge"],
            "branch": spec["branch"],
        })
    candidates.sort(key=lambda item: item["scenario_ref"])
    candidate_by_ref = {item["scenario_ref"]: item for item in candidates}
    rows_by_slot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selection_rows:
        rows_by_slot[row["slot_ref"]].append(row)
    selected_rows = [
        min(rows, key=lambda row: (row["selection_key"], row["scenario_ref"]))
        for _, rows in sorted(rows_by_slot.items())
    ]
    selected = sorted(
        (candidate_by_ref[row["scenario_ref"]] for row in selected_rows),
        key=lambda item: item["scenario_ref"],
    )
    selected_ref_set = {item["scenario_ref"] for item in selected}
    selected_specs = [spec for spec in SCENARIO_SPECS if spec["scenario_ref"] in selected_ref_set]
    candidate_quotas = Counter(item["category"] for item in candidates)
    final_quotas = Counter(item["category"] for item in selected)
    target_present = sum(spec["planned_target_status"] == "TARGET_PRESENT" for spec in selected_specs)
    wrong_context = sum(spec["wrong_context_challenge"] for spec in selected_specs)
    repeat_refs = sorted(spec["scenario_ref"] for spec in selected_specs if spec["repeat_challenge"])
    repeat_quotas = Counter(spec["category"] for spec in selected_specs if spec["repeat_challenge"])
    phenomena = Counter(
        spec["primary_challenge"] for spec in selected_specs
        if spec["category"] == "NONLITERAL_UNIQUE"
    )
    if candidate_quotas != Counter(CANDIDATE_QUOTAS) or final_quotas != Counter(FINAL_QUOTAS):
        findings["DATASET_COUNT_MISMATCH"] += 1
    if target_present != 42 or len(selected) - target_present != 6 or wrong_context != 8 or len(repeat_refs) != 16:
        findings["DATASET_COUNT_MISMATCH"] += 1
    if repeat_quotas != Counter({
        "NONLITERAL_UNIQUE": 4,
        "STRUCTURAL_INTERFERENCE": 4,
        "CLARIFICATION": 4,
        "WEAK_EVIDENCE": 4,
    }):
        findings["DATASET_COUNT_MISMATCH"] += 1
    if phenomena != Counter({
        "synonym": 2,
        "abbreviation": 2,
        "colloquial": 2,
        "minor_typo": 2,
        "cross_layer_expression": 2,
    }):
        findings["DATASET_COUNT_MISMATCH"] += 1

    signatures = Counter(
        canonical_digest([
            spec["category"], spec["primary_challenge"], spec["branch"],
            spec["node_kind_hint"], spec["value_type_hint"], spec["cardinality_hint"],
            spec["planned_target_status"], len(spec["planned_target_refs"]),
            bool(spec["proposed_parent_logical_ref"]),
        ])
        for spec in SCENARIO_SPECS
    )
    selection = {
        "schema_version": "navigation-copilot-b03-b-selection-plan.v1",
        "selection_algorithm_version": SELECTION_ALGORITHM_VERSION,
        "namespace": NAMESPACE,
        "selection_seed": SELECTION_SEED,
        "paired_slots": sorted(PAIRED_SLOTS),
        "candidate_rows": sorted(selection_rows, key=lambda row: row["scenario_ref"]),
        "selected_scenario_refs": sorted(selected_ref_set),
        "repeat_scenario_refs": repeat_refs,
    }
    metrics = {
        "candidate_category_quotas": dict(sorted(candidate_quotas.items())),
        "final_category_quotas": dict(sorted(final_quotas.items())),
        "target_present_plan_count": target_present,
        "target_absent_plan_count": len(selected) - target_present,
        "wrong_context_count": wrong_context,
        "repeat_scenario_refs": repeat_refs,
        "repeat_category_quotas": dict(sorted(repeat_quotas.items())),
        "nonliteral_final_phenomena": dict(sorted(phenomena.items())),
        "scenario_semantic_unique_group_count": len(signatures),
        "scenario_semantic_max_group": max(signatures.values(), default=0),
    }
    return candidates, selected, selection, findings | Counter(), metrics


def _phase2a_canary() -> dict[str, bool]:
    oracle_path = FIXTURE_DIR / "oracle.v2.json"
    freeze_path = FIXTURE_DIR / "freeze-report.v1.json"
    manifest_path = FIXTURE_DIR / "evaluation-manifest.v2.json"
    silver_paths = list(FIXTURE_DIR.glob("*silver*")) + list(STAGING_DIR.glob("*silver*"))
    return {
        "oracle_absent": not oracle_path.exists(),
        "silver_absent": not silver_paths,
        "freeze_report_absent": not freeze_path.exists(),
        "evaluation_manifest_absent": not manifest_path.exists(),
    }


def _build_once(blueprint: dict[str, Any]) -> dict[str, Any]:
    hierarchy, hierarchy_findings = _validate_hierarchy(blueprint)
    if any(hierarchy_findings.values()):
        return {"early_findings": hierarchy_findings}
    skeleton, skeleton_findings = _skeleton_and_signature_metrics(blueprint)
    tree_document = _tree_document(blueprint)
    imported = adapt_tree_document(tree_document, source_hint="navigation-copilot-b03-b")
    findings = hierarchy_findings + skeleton_findings
    if not imported.is_valid or imported.tree is None:
        findings["DATASET_REFERENCE_INVALID"] += 1
        return {"early_findings": findings, "adapter_issues": [issue.to_dict() for issue in imported.issues]}
    independent_rows, independent_findings, independent_metrics = _independent_scenario_checks(blueprint)
    manual_metrics, manual_findings = _manual_review_metrics(blueprint)
    candidates, selected, selection, scenario_findings, scenario_metrics = _build_scenarios(
        blueprint, imported.tree.snapshot_hash
    )
    findings += independent_findings + manual_findings + scenario_findings
    canary = _phase2a_canary()
    if not all(canary.values()):
        findings["DATASET_BOUNDARY_CANARY_FOUND"] += 1

    blueprint_bytes = _bytes(blueprint)
    tree_bytes = _bytes(tree_document)
    candidate_document = {
        "schema_version": "navigation-copilot-b03-b-candidate-set.v1",
        "dataset_ref": DATASET_REF,
        "scenario_count": len(candidates),
        "scenarios": candidates,
    }
    final_document = {
        "schema_version": "navigation-copilot-b03-b-scenario-set.v1",
        "dataset_ref": DATASET_REF,
        "scenario_count": len(selected),
        "scenarios": selected,
    }
    candidate_bytes = _bytes(candidate_document)
    final_bytes = _bytes(final_document)
    hashes = {
        "blueprint_sha256": _sha256(blueprint_bytes),
        "tree_sha256": _sha256(tree_bytes),
        "candidate_scenarios_sha256": _sha256(candidate_bytes),
        "final_scenarios_sha256": _sha256(final_bytes),
    }
    hierarchy_review = {
        "schema_version": "navigation-copilot-b03-b-hierarchy-review.v1",
        "validation_order": skeleton["validation_order"],
        "planned_count": hierarchy["rationale_plan_count"],
        "reviewed_count": hierarchy["rationale_reviewed_count"],
        "accepted_count": hierarchy["rationale_passed_count"],
        "rejected_count": hierarchy["rationale_rejected_count"],
        "rows": hierarchy["hierarchy_rows"],
    }
    manual_review = {
        "schema_version": "navigation-copilot-b03-b-manual-scenario-review.v1",
        "source_is_independent_of_scenario_boolean": True,
        "reviews": list(MANUAL_REVIEWS),
        "aggregate": manual_metrics,
    }
    classification = {
        "schema_version": "navigation-copilot-b03-b-dataset-classification.v1",
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "namespace": NAMESPACE,
        "seed": TREE_SEED,
        "selection_seed": SELECTION_SEED,
        "selection_algorithm_version": SELECTION_ALGORITHM_VERSION,
        "node_count": EXPECTED_NODE_COUNT,
        "role_counts": hierarchy["role_counts"],
        "candidate_count": len(candidates),
        "final_count": len(selected),
        "public_contract_versions": {
            "scenario": "navigation-copilot-sealed-scenario.v2",
            "oracle": "navigation-copilot-sealed-oracle.v2",
            "evaluation_manifest": "navigation-copilot-sealed-evaluation-manifest.v2",
            "deterministic_contract_commit": "7d8bd6d06ae1a16c87dcb91cd45f7820173ed6fc",
            "function_contract_commit": "40098afe985dfc81183c928a473a2e8a3c2176dc",
        },
        "artifact_sha256": hashes,
    }
    finding_counts = {code: findings[code] for code in FINDING_CODES}
    preflight = {
        "schema_version": "navigation-copilot-b03-b-phase2a-preflight.v1",
        "artifact_status": "MACHINE_AND_MANUAL_VALIDATED_PHASE2A",
        "dataset_ref": DATASET_REF,
        "batch_ref": BATCH_REF,
        "artifact_sha256": hashes,
        "node_count": imported.observed_node_count,
        "value_envelope_count": imported.observed_value_count,
        "role_counts": hierarchy["role_counts"],
        "branch_counts": hierarchy["branch_counts"],
        "hierarchy_gate": {
            "curated_to_curated_relationship_count": hierarchy["curated_to_curated_relationship_count"],
            "curated_parent_child_relationship_count": hierarchy["curated_parent_child_relationship_count"],
            "rationale_plan_count": hierarchy["rationale_plan_count"],
            "rationale_reviewed_count": hierarchy["rationale_reviewed_count"],
            "rationale_passed_count": hierarchy["rationale_passed_count"],
            "rationale_rejected_count": hierarchy["rationale_rejected_count"],
        },
        "skeleton_signatures": skeleton,
        "combination_density": hierarchy["combination_density"],
        "independent_scenario_checks": independent_metrics,
        "manual_scenario_review": manual_metrics,
        **scenario_metrics,
        "finding_code_counts": finding_counts,
        "phase2a_canary": canary,
        "batch_a_protection": {
            "access_mode": "NOT_OPENED_BY_BATCH_B_BUILDER",
            "expected_sha256": BATCH_A_EXPECTED_SHA256,
            "external_streaming_hash_verification_required": True,
        },
        "deterministic_rebuild_match": True,
        "gold_eligible": False,
        "patch_eligible": False,
    }
    return {
        "findings": findings,
        "blueprint": blueprint_bytes,
        "tree": tree_bytes,
        "candidates": candidate_bytes,
        "final": final_bytes,
        "classification": _bytes(classification),
        "selection": _bytes(selection),
        "manual_review": _bytes(manual_review),
        "hierarchy_review": _bytes(hierarchy_review),
        "preflight": _bytes(preflight),
        "preflight_payload": preflight,
        "independent_rows": independent_rows,
    }


def build_artifacts() -> dict[str, Any]:
    blueprint = _load_blueprint()
    first = _build_once(blueprint)
    if "early_findings" in first:
        raise ValueError("Phase 2A hierarchy/adapter preflight failed: " + json.dumps(dict(first["early_findings"]), sort_keys=True))
    second = _build_once(deepcopy(blueprint))
    byte_keys = (
        "blueprint", "tree", "candidates", "final", "classification",
        "selection", "manual_review", "hierarchy_review", "preflight",
    )
    deterministic = all(first[key] == second[key] for key in byte_keys)
    if not deterministic:
        first["findings"]["DATASET_NONDETERMINISTIC"] += 1
    first["preflight_payload"]["deterministic_rebuild_match"] = deterministic
    first["preflight_payload"]["finding_code_counts"] = {
        code: first["findings"][code] for code in FINDING_CODES
    }
    first["preflight"] = _bytes(first["preflight_payload"])
    if any(first["findings"].values()):
        details = {code: count for code, count in first["findings"].items() if count}
        diagnostic = {
            "finding_counts": details,
            "skeleton_signatures": first["preflight_payload"]["skeleton_signatures"],
        }
        raise ValueError("Phase 2A preflight failed: " + json.dumps(diagnostic, sort_keys=True))
    return first


def _write_or_verify(path: Path, payload: bytes, *, allow_blueprint_normalization: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == payload:
            return "verified_existing"
        if allow_blueprint_normalization:
            decoded = json.loads(existing.decode("utf-8"))
            if all("stable_id" not in node for node in decoded.get("nodes", [])):
                path.write_bytes(payload)
                return "normalized_stable_ids"
        raise ValueError(f"DATASET_NONDETERMINISTIC: refusing to overwrite changed artifact {path.name}")
    path.write_bytes(payload)
    return "created"


def write_artifacts(artifacts: dict[str, Any]) -> dict[str, str]:
    statuses = {
        "blueprint": _write_or_verify(BLUEPRINT_PATH, artifacts["blueprint"], allow_blueprint_normalization=True),
        "tree": _write_or_verify(TREE_PATH, artifacts["tree"]),
        "final_scenarios": _write_or_verify(SCENARIOS_PATH, artifacts["final"]),
        "classification": _write_or_verify(CLASSIFICATION_PATH, artifacts["classification"]),
        "candidate_scenarios": _write_or_verify(CANDIDATES_PATH, artifacts["candidates"]),
        "selection_plan": _write_or_verify(SELECTION_PATH, artifacts["selection"]),
        "manual_review": _write_or_verify(MANUAL_REVIEW_PATH, artifacts["manual_review"]),
        "hierarchy_review": _write_or_verify(HIERARCHY_REVIEW_PATH, artifacts["hierarchy_review"]),
        "preflight": _write_or_verify(PREFLIGHT_PATH, artifacts["preflight"]),
    }
    return statuses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", required=True)
    parser.parse_args()
    artifacts = build_artifacts()
    statuses = write_artifacts(artifacts)
    report = dict(artifacts["preflight_payload"])
    report["write_status"] = statuses
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
