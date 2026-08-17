"""Build and verify the Navigation Copilot v3-C b02 sealed data candidate.

Tree and scenario semantics are read from explicit JSON authoring files.  This
module validates, assigns identity, binds references, and serializes; it never
creates semantic labels, topology, requests, hints, targets, or review text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from treeguard.adapter import adapt_tree_document, load_tree_export
from treeguard.hashing import canonical_digest
from treeguard.json_utils import strict_json_loads
from treeguard.navigation_copilot_sealed_validation import (
    SealedCaseOracle,
    SealedEvaluationManifest,
    SealedScenario,
    StructuralProfile,
    TerminalExpectation,
    validate_sealed_plan,
)
from treeguard.workbench import build_tree_reference_index


BATCH_REF = "navigation-copilot-sealed-v3c-20260806-b02"
NAMESPACE = uuid.UUID("b6e2f54c-713a-4d18-a6f9-02b7c5e83d21")
SEED = "NCV3C-CLEANROOM-20260806-SEED-02"
STABLE_ID_VERSION = "treeguard.navigation-copilot-v3c-stable-id.v2"
CATALOG_SCHEMA_VERSION = "treeguard.navigation-copilot-v3c-blueprint-catalog.v2"
BLUEPRINT_SCHEMA_VERSION = "treeguard.navigation-copilot-v3c-blueprint-file.v1"
CANDIDATE_BINDINGS_SCHEMA_VERSION = (
    "treeguard.navigation-copilot-v3c-b02-candidate-bindings.v1"
)
CANDIDATES_SCHEMA_VERSION = "treeguard.navigation-copilot-v3c-b02-candidates.v1"
ORACLE_AUTHORING_SCHEMA_VERSION = (
    "treeguard.navigation-copilot-v3c-b02-oracle-authoring.v1"
)
BLUEPRINT_REVIEW_SCHEMA_VERSION = (
    "treeguard.navigation-copilot-v3c-b02-blueprint-review.v1"
)
CANDIDATE_REVIEW_SCHEMA_VERSION = (
    "treeguard.navigation-copilot-v3c-b02-candidate-review.v1"
)
MIGRATION_LEDGER_SCHEMA_VERSION = (
    "treeguard.navigation-copilot-v3c-b02-migration-ledger.v1"
)
PREFLIGHT_SCHEMA_VERSION = "treeguard.navigation-copilot-v3c-b02-preflight.v1"
DATA_MANIFEST_SCHEMA_VERSION = (
    "treeguard.navigation-copilot-v3c-b02-data-manifest.v1"
)
WEAK_REVIEW_SCHEMA_VERSION = (
    "treeguard.navigation-copilot-v3c-b02-weak-oracle-review.v1"
)
FUNCTION_COMMIT = "88caf25d9be8ebb80f8c443115ebde1d69fc0447"

SOURCE_CLASS = "CLEANROOM_SYNTHETIC"
BLUEPRINT_FILES = (
    "root.json",
    "branch-01.json",
    "branch-02.json",
    "branch-03.json",
    "branch-04.json",
    "branch-05.json",
    "branch-06.json",
    "branch-07.json",
    "branch-08.json",
)
SOURCE_BLUEPRINT_PATHS = tuple(f"blueprints/{name}" for name in BLUEPRINT_FILES)
SOURCE_BLUEPRINT_REVIEW = "reviews/blueprint-silver-review.json"
SOURCE_CANDIDATES = "candidates/candidate-catalog.json"
SOURCE_ORACLE = "oracle/hidden-oracle.json"
SOURCE_ALLOWLIST = frozenset(
    (*SOURCE_BLUEPRINT_PATHS, SOURCE_BLUEPRINT_REVIEW, SOURCE_CANDIDATES, SOURCE_ORACLE)
)

AUTHORING_CATEGORY_ORDER = (
    "LITERAL_UNIQUE",
    "NON_LITERAL_UNIQUE",
    "STRUCTURAL_DISTRACTOR",
    "MULTIPLE_ACCEPTABLE",
    "CLARIFICATION",
    "WEAK_EVIDENCE",
    "NO_TARGET",
)
AUTHORING_COUNTS = (12, 12, 9, 5, 7, 5, 6)
FREEZE_COUNTS = (10, 10, 8, 4, 6, 4, 6)
CATEGORY_MAP = {
    "LITERAL_UNIQUE": "LITERAL_UNIQUE",
    "NON_LITERAL_UNIQUE": "NONLITERAL_UNIQUE",
    "STRUCTURAL_DISTRACTOR": "STRUCTURAL_INTERFERENCE",
    "MULTIPLE_ACCEPTABLE": "MULTI_ACCEPTABLE",
    "CLARIFICATION": "CLARIFICATION",
    "WEAK_EVIDENCE": "WEAK_EVIDENCE",
    "NO_TARGET": "TARGET_ABSENT",
}
NON_LITERAL_SUBTYPE_COUNTS = {
    "SYNONYM": 2,
    "ABBREVIATION": 2,
    "COLLOQUIAL_PURPOSE": 2,
    "MINOR_TYPO": 2,
    "CROSS_LEVEL": 2,
}
RUBRIC_ORDER = (
    "naturalness",
    "tree_answerability",
    "category_semantics",
    "primary_phenomenon",
    "oracle_consistency",
    "clarification_contrast",
    "weak_evidence_objectivity",
)
BLUEPRINT_FIELDS = {
    "blueprint_ref",
    "parent_ref",
    "parent_role",
    "label",
    "name",
    "kind",
    "value_type",
    "cardinality",
    "child_refs",
    "semantic_note",
}
BLUEPRINT_REVIEW_PAYLOAD_FIELDS = (
    "blueprint_ref",
    "status",
    "finding_codes",
    "parent_responsibility",
    "child_role_assessment",
    "boundary_assessment",
)
CANDIDATE_MIGRATION_FIELDS = (
    "category",
    "ordinal",
    "request",
    "non_literal_subtype",
    "context_pressure",
    "repeatability_subset",
)
class DataBuildError(ValueError):
    """A deterministic b02 authoring or freeze rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DataBuildError(message)


def _read_json(path: Path) -> Any:
    _require(path.is_file() and not path.is_symlink(), "input must be a regular file")
    return strict_json_loads(path.read_text(encoding="utf-8"))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _raw_sha256(path.read_bytes())


def _allowed_source(source_root: Path, relative: str) -> Path:
    _require(relative in SOURCE_ALLOWLIST, "source path is outside the migration allowlist")
    root = source_root.resolve(strict=True)
    candidate = (root / relative).resolve(strict=True)
    _require(candidate.parent == (root / relative).parent.resolve(strict=True), "source path escaped")
    _require(candidate.is_file() and not candidate.is_symlink(), "source must be a regular file")
    return candidate


def stable_node_id(blueprint_ref: str) -> str:
    name = (
        f"algorithm={STABLE_ID_VERSION}\n"
        f"batch_ref={BATCH_REF}\n"
        f"seed={SEED}\n"
        f"blueprint_ref={blueprint_ref}"
    )
    return str(uuid.uuid5(NAMESPACE, name))


def _category_key(item: dict[str, Any]) -> tuple[int, int]:
    return (AUTHORING_CATEGORY_ORDER.index(item["authoring_category"]), item["ordinal"])


def _binding_key(item: dict[str, Any]) -> tuple[str, int]:
    return (item["source_category"], item["source_ordinal"])


def load_blueprints(fixture_root: Path) -> tuple[dict[str, Any], ...]:
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for filename in BLUEPRINT_FILES:
        payload = _read_json(fixture_root / "blueprints" / filename)
        _require(
            set(payload) == {"schema_version", "branch_ref", "nodes"}
            and payload["schema_version"] == BLUEPRINT_SCHEMA_VERSION
            and isinstance(payload["nodes"], list),
            "blueprint file contract is invalid",
        )
        for node in payload["nodes"]:
            _require(isinstance(node, dict) and set(node) == BLUEPRINT_FIELDS, "blueprint fields invalid")
            ref = node["blueprint_ref"]
            _require(isinstance(ref, str) and ref and ref not in seen, "blueprint ref invalid")
            seen.add(ref)
            _require(
                isinstance(node["label"], str)
                and node["label"]
                and isinstance(node["name"], str)
                and node["name"]
                and isinstance(node["semantic_note"], str)
                and node["semantic_note"],
                "blueprint semantic text invalid",
            )
            _require(node["kind"] in {"concept", "property"}, "blueprint kind invalid")
            _require(
                isinstance(node["child_refs"], list)
                and len(node["child_refs"]) == len(set(node["child_refs"])),
                "blueprint children invalid",
            )
            if node["kind"] == "concept":
                _require(node["value_type"] is None and node["cardinality"] is None, "concept value contract invalid")
            else:
                _require(
                    isinstance(node["value_type"], str)
                    and node["value_type"]
                    and node["cardinality"] in {"SINGLE", "MULTIPLE"},
                    "property value contract invalid",
                )
            nodes.append(node)
    by_ref = {node["blueprint_ref"]: node for node in nodes}
    roots = [node for node in nodes if node["parent_ref"] is None or node["parent_role"] is None]
    _require(
        len(roots) == 1
        and roots[0]["blueprint_ref"] == "root"
        and roots[0]["parent_ref"] is None
        and roots[0]["parent_role"] is None,
        "root.json must be the unique null-parent source",
    )
    for node in nodes:
        if node["blueprint_ref"] == "root":
            continue
        _require(
            isinstance(node["parent_ref"], str)
            and node["parent_ref"] in by_ref
            and isinstance(node["parent_role"], str)
            and node["parent_role"],
            "non-root parent binding invalid",
        )
        parent = by_ref[node["parent_ref"]]
        _require(node["blueprint_ref"] in parent["child_refs"], "parent does not name child")
    for parent in nodes:
        child_labels = []
        for child_ref in parent["child_refs"]:
            _require(child_ref in by_ref, "child ref is unknown")
            child = by_ref[child_ref]
            _require(child["parent_ref"] == parent["blueprint_ref"], "child parent mismatch")
            child_labels.append(child["label"])
        _require(len(child_labels) == len(set(child_labels)), "duplicate sibling label")
    _require(len(nodes) == 700, "b02 requires exactly 700 explicit blueprint nodes")
    _require(len(by_ref["root"]["child_refs"]) == 8, "b02 requires eight top branches")
    return tuple(nodes)


def _descendant_counts(nodes: Iterable[dict[str, Any]]) -> dict[str, int]:
    by_ref = {node["blueprint_ref"]: node for node in nodes}
    memo: dict[str, int] = {}

    def count(ref: str, stack: frozenset[str]) -> int:
        _require(ref not in stack, "blueprint cycle detected")
        if ref not in memo:
            memo[ref] = sum(1 + count(child, stack | {ref}) for child in by_ref[ref]["child_refs"])
        return memo[ref]

    for ref in by_ref:
        count(ref, frozenset())
    return memo


def _semantic_signature(ref: str, by_ref: dict[str, dict[str, Any]], memo: dict[str, str]) -> str:
    if ref not in memo:
        node = by_ref[ref]
        children = sorted(
            (
                {
                    "role": by_ref[child]["parent_role"],
                    "semantic_signature": _semantic_signature(child, by_ref, memo),
                }
                for child in node["child_refs"]
            ),
            key=canonical_digest,
        )
        memo[ref] = canonical_digest(
            {
                "kind": node["kind"],
                "value_type": node["value_type"],
                "cardinality": node["cardinality"],
                "children": children,
            }
        )
    return memo[ref]


def _skeleton_signature(ref: str, by_ref: dict[str, dict[str, Any]], memo: dict[str, str]) -> str:
    if ref not in memo:
        node = by_ref[ref]
        children = sorted(_skeleton_signature(child, by_ref, memo) for child in node["child_refs"])
        memo[ref] = canonical_digest(
            {
                "kind": node["kind"],
                "direct_child_count": len(node["child_refs"]),
                "children": children,
            }
        )
    return memo[ref]


def signature_report(nodes: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    by_ref = {node["blueprint_ref"]: node for node in nodes}
    descendants = _descendant_counts(nodes)
    eligible = sorted(ref for ref, count in descendants.items() if count >= 5)
    semantic_memo: dict[str, str] = {}
    skeleton_memo: dict[str, str] = {}
    semantic = Counter(_semantic_signature(ref, by_ref, semantic_memo) for ref in eligible)
    skeleton = Counter(_skeleton_signature(ref, by_ref, skeleton_memo) for ref in eligible)

    def stats(counter: Counter[str]) -> dict[str, Any]:
        repeated = sum(size for size in counter.values() if size > 1)
        return {
            "eligible_instance_count": len(eligible),
            "unique_signature_count": len(counter),
            "max_repeat_group": max(counter.values(), default=0),
            "repeated_instance_count": repeated,
            "repeated_instance_ratio_bps": (repeated * 10_000) // len(eligible),
        }

    report = {
        "eligible_blueprint_refs": eligible,
        "semantic": stats(semantic),
        "skeleton": stats(skeleton),
    }
    _require(len(eligible) == 91, "eligible blueprint count changed")
    _require(
        report["semantic"]["max_repeat_group"] <= 3
        and report["semantic"]["repeated_instance_ratio_bps"] <= 2_000,
        "semantic signature gate failed",
    )
    _require(
        report["skeleton"]["max_repeat_group"] <= 4
        and report["skeleton"]["repeated_instance_ratio_bps"] <= 4_000,
        "skeleton signature gate failed",
    )
    return report


def _load_bindings(fixture_root: Path) -> tuple[dict[str, Any], ...]:
    payload = _read_json(fixture_root / "authoring" / "candidate-bindings.json")
    _require(
        set(payload) == {"schema_version", "batch_ref", "rubric_order", "bindings"}
        and payload["schema_version"] == CANDIDATE_BINDINGS_SCHEMA_VERSION
        and payload["batch_ref"] == BATCH_REF
        and tuple(payload["rubric_order"]) == RUBRIC_ORDER
        and isinstance(payload["bindings"], list)
        and len(payload["bindings"]) == 56,
        "candidate bindings contract invalid",
    )
    base_fields = {
        "source_category", "source_ordinal", "scenario_ref", "execution_category",
        "node_kind_hint", "value_type_hint", "cardinality_hint",
        "wrong_parent_blueprint_ref", "review",
    }
    review_fields = {"status", "finding_codes", "rubric", "assessment"}
    seen_refs: set[str] = set()
    seen_keys: set[tuple[str, int]] = set()
    for item in payload["bindings"]:
        _require(isinstance(item, dict), "candidate binding fields invalid")
        expected_fields = (
            base_fields | {"frozen_clarification_answer"}
            if item.get("source_category") == "CLARIFICATION"
            else base_fields
        )
        _require(set(item) == expected_fields, "candidate binding fields invalid")
        key = _binding_key(item)
        _require(key not in seen_keys, "candidate binding key duplicated")
        seen_keys.add(key)
        _require(
            item["source_category"] in CATEGORY_MAP
            and item["execution_category"] == CATEGORY_MAP[item["source_category"]]
            and isinstance(item["source_ordinal"], int)
            and not isinstance(item["source_ordinal"], bool),
            "candidate binding category invalid",
        )
        _require(item["scenario_ref"] not in seen_refs, "scenario ref duplicated")
        seen_refs.add(item["scenario_ref"])
        _require(item["node_kind_hint"] in {"CONCEPT", "PROPERTY", "UNKNOWN"}, "node hint invalid")
        _require(item["cardinality_hint"] in {"SINGLE", "MULTIPLE", "UNKNOWN"}, "cardinality hint invalid")
        if item["source_category"] == "CLARIFICATION":
            _require(
                isinstance(item["frozen_clarification_answer"], str)
                and item["frozen_clarification_answer"],
                "clarification answer must be explicit b02 authoring",
            )
        review = item["review"]
        _require(isinstance(review, dict) and set(review) == review_fields, "candidate review fields invalid")
        _require(
            review["status"] in {"SILVER_ACCEPTED", "SILVER_REJECTED"}
            and isinstance(review["finding_codes"], list)
            and all(
                isinstance(code, str) and code
                for code in review["finding_codes"]
            )
            and len(review["finding_codes"]) == len(set(review["finding_codes"]))
            and isinstance(review["rubric"], list)
            and len(review["rubric"]) == len(RUBRIC_ORDER)
            and all(value in {"PASS", "FAIL", "NOT_APPLICABLE"} for value in review["rubric"])
            and isinstance(review["assessment"], str)
            and review["assessment"],
            "candidate review invalid",
        )
        rubric = dict(zip(RUBRIC_ORDER, review["rubric"]))
        if review["status"] == "SILVER_ACCEPTED":
            _require("FAIL" not in review["rubric"], "accepted candidate has a failed rubric")
            if item["source_category"] == "CLARIFICATION":
                _require(
                    rubric["clarification_contrast"] == "PASS",
                    "accepted clarification must pass contrast review",
                )
            if item["source_category"] == "WEAK_EVIDENCE":
                _require(
                    rubric["weak_evidence_objectivity"] == "PASS",
                    "accepted weak evidence must pass objectivity review",
                )
        else:
            _require(
                "FAIL" in review["rubric"] and bool(review["finding_codes"]),
                "rejected candidate requires a failed rubric and finding code",
            )
    counts = Counter(item["source_category"] for item in payload["bindings"])
    _require(
        tuple(counts[name] for name in AUTHORING_CATEGORY_ORDER) == AUTHORING_COUNTS,
        "candidate binding quotas invalid",
    )
    return tuple(payload["bindings"])


def _selection_dispositions(bindings: tuple[dict[str, Any], ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for category, quota in zip(AUTHORING_CATEGORY_ORDER, FREEZE_COUNTS):
        accepted = sorted(
            (
                item for item in bindings
                if item["source_category"] == category
                and item["review"]["status"] == "SILVER_ACCEPTED"
            ),
            key=lambda item: item["source_ordinal"],
        )
        _require(len(accepted) >= quota, "insufficient accepted candidates for quota")
        frozen_refs = {item["scenario_ref"] for item in accepted[:quota]}
        for item in (entry for entry in bindings if entry["source_category"] == category):
            if item["review"]["status"] == "SILVER_REJECTED":
                result[item["scenario_ref"]] = "REJECTED"
            elif item["scenario_ref"] in frozen_refs:
                result[item["scenario_ref"]] = "FROZEN_ACCEPTED"
            else:
                result[item["scenario_ref"]] = "RESERVE_ACCEPTED"
    return result


def migrate_scenario_sources(source_root: Path, fixture_root: Path) -> None:
    bindings = _load_bindings(fixture_root)
    blueprint_ledger = []
    for relative, filename in zip(SOURCE_BLUEPRINT_PATHS, BLUEPRINT_FILES):
        source = _allowed_source(source_root, relative)
        data = source.read_bytes()
        target = fixture_root / "blueprints" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        _require(target.read_bytes() == data, "blueprint byte migration changed payload")
        blueprint_ledger.append(
            {"relative_path": relative, "source_sha256": _raw_sha256(data), "target_sha256": _file_sha256(target), "byte_equal": True}
        )
    nodes = load_blueprints(fixture_root)
    signatures = signature_report(nodes)
    by_ref = {node["blueprint_ref"]: node for node in nodes}
    binding_by_key = {_binding_key(item): item for item in bindings}

    source_candidates = _read_json(_allowed_source(source_root, SOURCE_CANDIDATES))
    _require(
        isinstance(source_candidates, dict)
        and isinstance(source_candidates.get("candidates"), list)
        and len(source_candidates["candidates"]) == 56,
        "source candidate catalog invalid",
    )
    candidate_rows = []
    candidate_digest_rows = []
    for source in source_candidates["candidates"]:
        key = (source.get("category"), source.get("ordinal"))
        _require(key in binding_by_key, "source candidate is not explicitly bound")
        binding = binding_by_key[key]
        projection = {name: source.get(name) for name in CANDIDATE_MIGRATION_FIELDS}
        answer = binding.get("frozen_clarification_answer")
        wrong_parent = binding["wrong_parent_blueprint_ref"]
        _require(wrong_parent is None or wrong_parent in by_ref, "wrong parent blueprint is unknown")
        row = {
            "scenario_ref": binding["scenario_ref"],
            "authoring_category": source["category"],
            "execution_category": binding["execution_category"],
            "ordinal": source["ordinal"],
            "requirement_text": source["request"],
            "non_literal_subtype": source.get("non_literal_subtype"),
            "context_pressure": source["context_pressure"],
            "repeat_challenge": source["repeatability_subset"],
            "node_kind_hint": binding["node_kind_hint"],
            "value_type_hint": binding["value_type_hint"],
            "cardinality_hint": binding["cardinality_hint"],
            "frozen_clarification_answer": answer,
            "wrong_parent_blueprint_ref": wrong_parent,
            "migration_payload_digest": canonical_digest(projection),
        }
        candidate_rows.append(row)
        candidate_digest_rows.append(
            {
                "authoring_category": source["category"],
                "ordinal": source["ordinal"],
                "source_payload_digest": canonical_digest(projection),
                "target_payload_digest": canonical_digest(
                    {
                        "category": row["authoring_category"],
                        "ordinal": row["ordinal"],
                        "request": row["requirement_text"],
                        "non_literal_subtype": row["non_literal_subtype"],
                        "context_pressure": row["context_pressure"],
                        "repeatability_subset": row["repeat_challenge"],
                    }
                ),
                "semantic_payload_equal": True,
            }
        )
    candidate_rows.sort(key=_category_key)
    _require(len({item["scenario_ref"] for item in candidate_rows}) == 56, "candidate refs invalid")
    _require(sum(item["context_pressure"] for item in candidate_rows) == 8, "wrong-context count invalid")
    _require(
        all((item["wrong_parent_blueprint_ref"] is not None) == item["context_pressure"] for item in candidate_rows),
        "wrong-parent binding must exactly match pressure labels",
    )
    _write_json(
        fixture_root / "authoring" / "candidates.json",
        {"schema_version": CANDIDATES_SCHEMA_VERSION, "batch_ref": BATCH_REF, "candidates": candidate_rows},
    )

    dispositions = _selection_dispositions(bindings)
    candidate_reviews = []
    for binding in sorted(bindings, key=lambda item: (AUTHORING_CATEGORY_ORDER.index(item["source_category"]), item["source_ordinal"])):
        review = binding["review"]
        candidate_reviews.append(
            {
                "scenario_ref": binding["scenario_ref"],
                "round": 1,
                "status": review["status"],
                "selection_disposition": dispositions[binding["scenario_ref"]],
                "finding_codes": review["finding_codes"],
                "rubric_results": dict(zip(RUBRIC_ORDER, review["rubric"])),
                "assessment": review["assessment"],
            }
        )
    _require(len({item["assessment"] for item in candidate_reviews}) == 56, "candidate assessments must be item-specific")
    _write_json(
        fixture_root / "reviews" / "candidate-silver-review.json",
        {"schema_version": CANDIDATE_REVIEW_SCHEMA_VERSION, "batch_ref": BATCH_REF, "reviews": candidate_reviews},
    )

    source_reviews = _read_json(_allowed_source(source_root, SOURCE_BLUEPRINT_REVIEW))
    _require(isinstance(source_reviews.get("reviews"), list) and len(source_reviews["reviews"]) == 91, "source blueprint reviews invalid")
    migrated_reviews = []
    review_ledger = []
    for source in source_reviews["reviews"]:
        projection = {name: source[name] for name in BLUEPRINT_REVIEW_PAYLOAD_FIELDS}
        migrated = {**projection, "round": 1, "source_semantic_payload_digest": canonical_digest(projection)}
        migrated_reviews.append(migrated)
        target_projection = {name: migrated[name] for name in BLUEPRINT_REVIEW_PAYLOAD_FIELDS}
        review_ledger.append(
            {
                "blueprint_ref": source["blueprint_ref"],
                "source_payload_digest": canonical_digest(projection),
                "target_payload_digest": canonical_digest(target_projection),
                "semantic_payload_equal": projection == target_projection,
            }
        )
    eligible = set(signatures["eligible_blueprint_refs"])
    _require({item["blueprint_ref"] for item in migrated_reviews} == eligible, "blueprint Silver coverage invalid")
    _require(all(item["semantic_payload_equal"] for item in review_ledger), "blueprint review payload changed")
    _write_json(
        fixture_root / "reviews" / "blueprint-silver-review.json",
        {"schema_version": BLUEPRINT_REVIEW_SCHEMA_VERSION, "batch_ref": BATCH_REF, "reviews": sorted(migrated_reviews, key=lambda item: item["blueprint_ref"])},
    )

    catalog = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "batch_ref": BATCH_REF,
        "namespace": str(NAMESPACE),
        "seed": SEED,
        "stable_id_algorithm_version": STABLE_ID_VERSION,
        "blueprint_file_schema_version": BLUEPRINT_SCHEMA_VERSION,
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "root_blueprint_file": "blueprints/root.json",
        "blueprint_files": [f"blueprints/{name}" for name in BLUEPRINT_FILES],
        "node_count": len(nodes),
        "value_envelope_count": 0,
        "gold_eligible": False,
        "patch_eligible": False,
        "production_qualification": False,
    }
    _write_json(fixture_root / "catalog.json", catalog)
    _write_json(
        fixture_root / "migration-ledger.json",
        {
            "schema_version": MIGRATION_LEDGER_SCHEMA_VERSION,
            "batch_ref": BATCH_REF,
            "b01_status": "REJECTED_PRECOMMIT_EXECUTION_CONTRACT_MISMATCH",
            "source_allowlist": sorted(SOURCE_ALLOWLIST),
            "blueprint_files": blueprint_ledger,
            "blueprint_review_payloads": review_ledger,
            "candidate_payloads": candidate_digest_rows,
            "oracle_payloads": [],
            "weak_oracle_source_semantic_payload_reused": False,
        },
    )


def _build_tree_document(nodes: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    by_ref = {node["blueprint_ref"]: node for node in nodes}
    ids = {ref: stable_node_id(ref) for ref in by_ref}

    def serialize(ref: str, path_labels: tuple[str, ...], order: int) -> dict[str, Any]:
        node = by_ref[ref]
        labels = (*path_labels, node["label"])
        metadata: dict[str, Any] = {
            "node_id": ids[ref],
            "parent_node_id": ids[node["parent_ref"]] if node["parent_ref"] is not None else None,
            "node_type": node["kind"],
            "node_name": node["name"],
            "node_label": node["label"],
            "node_label_route": "/-/".join(labels),
            "node_order": order,
            "remark": node["semantic_note"],
            "extension": {
                "blueprint_ref": ref,
                "parent_role": node["parent_role"],
                "source_class": SOURCE_CLASS,
                "fictional": True,
                "derived_from_real": False,
            },
        }
        if node["kind"] == "property":
            metadata.update(
                {
                    "value_type": node["value_type"],
                    "is_list": node["cardinality"] == "MULTIPLE",
                    "value_placeholder": "",
                    "value_constraints": {"raw_constraints": {}},
                }
            )
        subnodes = {
            by_ref[child]["label"]: serialize(child, labels, child_order)
            for child_order, child in enumerate(node["child_refs"], start=1)
        }
        return {"metadata": metadata, "subnodes": subnodes}

    root = by_ref["root"]
    return {
        "metadata": {
            "id": "navigation-copilot-v3c-b02-record",
            "map_id": "navigation-copilot-v3c-b02-tree",
            "map_type": "resource",
            "version": "V3C-B02",
            "concurrent_version": 1,
            "source_class": SOURCE_CLASS,
            "fictional": True,
            "derived_from_real": False,
            "batch_ref": BATCH_REF,
        },
        "map_topology": {root["label"]: serialize("root", (), 1)},
    }


def build_tree(fixture_root: Path) -> None:
    nodes = load_blueprints(fixture_root)
    report = signature_report(nodes)
    document = _build_tree_document(nodes)
    result = adapt_tree_document(document)
    _require(result.is_valid and result.tree is not None, "generated tree does not adapt")
    _require(result.observed_node_count == 700 and result.observed_value_count == 0, "tree counts invalid")
    _write_json(fixture_root / "frozen" / "tree.json", document)
    _write_json(
        fixture_root / "frozen" / "tree-preflight.json",
        {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "phase": "TREE_ONLY",
            "batch_ref": BATCH_REF,
            "node_count": result.observed_node_count,
            "value_envelope_count": result.observed_value_count,
            "tree_digest": result.tree.snapshot_hash,
            "signature_report": report,
        },
    )


def _load_candidates(fixture_root: Path) -> tuple[dict[str, Any], ...]:
    payload = _read_json(fixture_root / "authoring" / "candidates.json")
    _require(
        set(payload) == {"schema_version", "batch_ref", "candidates"}
        and payload["schema_version"] == CANDIDATES_SCHEMA_VERSION
        and payload["batch_ref"] == BATCH_REF
        and isinstance(payload["candidates"], list)
        and len(payload["candidates"]) == 56,
        "candidate authoring file invalid",
    )
    return tuple(payload["candidates"])


def _load_candidate_reviews(fixture_root: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(fixture_root / "reviews" / "candidate-silver-review.json")
    _require(
        payload.get("schema_version") == CANDIDATE_REVIEW_SCHEMA_VERSION
        and payload.get("batch_ref") == BATCH_REF
        and isinstance(payload.get("reviews"), list)
        and len(payload["reviews"]) == 56,
        "candidate reviews invalid",
    )
    return {item["scenario_ref"]: item for item in payload["reviews"]}


def freeze_scenarios(fixture_root: Path) -> None:
    candidates = _load_candidates(fixture_root)
    reviews = _load_candidate_reviews(fixture_root)
    result = load_tree_export(fixture_root / "frozen" / "tree.json")
    _require(result.is_valid and result.tree is not None, "tree replay failed")
    tree = result.tree
    refs = build_tree_reference_index(tree).ref_by_node_id
    selected = sorted(
        (
            item for item in candidates
            if reviews[item["scenario_ref"]]["selection_disposition"] == "FROZEN_ACCEPTED"
        ),
        key=lambda item: item["scenario_ref"],
    )
    _require(len(selected) == 48, "scenario freeze selection must contain 48 records")
    scenarios = []
    for item in selected:
        wrong_blueprint = item["wrong_parent_blueprint_ref"]
        proposed_parent_ref = refs[stable_node_id(wrong_blueprint)] if wrong_blueprint is not None else None
        scenario = SealedScenario.create(
            scenario_ref=item["scenario_ref"],
            tree_digest=tree.snapshot_hash,
            category=item["execution_category"],
            requirement_text=item["requirement_text"],
            proposed_parent_ref=proposed_parent_ref,
            node_kind_hint=item["node_kind_hint"],
            value_type_hint=item["value_type_hint"],
            cardinality_hint=item["cardinality_hint"],
            frozen_clarification_answer=item["frozen_clarification_answer"],
            wrong_context_challenge=item["context_pressure"],
            repeat_challenge=item["repeat_challenge"],
        )
        _require(SealedScenario.from_dict(scenario.to_dict()) == scenario, "scenario round trip failed")
        scenarios.append(scenario)
    payload = [item.to_dict() for item in scenarios]
    _write_json(fixture_root / "frozen" / "scenarios.json", payload)
    _write_json(
        fixture_root / "frozen" / "scenario-freeze.json",
        {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "phase": "SCENARIO_ONLY",
            "batch_ref": BATCH_REF,
            "scenario_count": len(scenarios),
            "scenario_refs": [item.scenario_ref for item in scenarios],
            "scenario_bytes_sha256": _file_sha256(fixture_root / "frozen" / "scenarios.json"),
            "scenario_round_trip_count": len(scenarios),
            "oracle_read_or_used": False,
        },
    )


def _profile_dict(profile: str) -> dict[str, Any]:
    parts = profile.split("/")
    _require(len(parts) == 3, "source structural profile invalid")
    return {"node_kind": parts[0].upper(), "value_type": None if parts[1] == "None" else parts[1], "cardinality": parts[2]}


def migrate_oracle_sources(source_root: Path, fixture_root: Path) -> None:
    scenario_payload = _read_json(fixture_root / "frozen" / "scenarios.json")
    scenarios = tuple(SealedScenario.from_dict(item) for item in scenario_payload)
    _require(len(scenarios) == 48, "Scenario freeze must precede Oracle migration")
    candidates = _load_candidates(fixture_root)
    candidate_by_key = {(item["authoring_category"], item["ordinal"]): item for item in candidates}
    source_candidates = _read_json(_allowed_source(source_root, SOURCE_CANDIDATES))["candidates"]
    source_oracles = _read_json(_allowed_source(source_root, SOURCE_ORACLE))["oracles"]
    source_oracle_by_ref = {item["scenario_ref"]: item for item in source_oracles}
    rows = []
    ledger_rows = []
    weak_new_refs = {item["scenario_ref"] for item in candidates if item["authoring_category"] == "WEAK_EVIDENCE"}
    for source_candidate in source_candidates:
        if source_candidate["category"] == "WEAK_EVIDENCE":
            continue
        target = candidate_by_key[(source_candidate["category"], source_candidate["ordinal"])]
        source = source_oracle_by_ref[source_candidate["scenario_ref"]]
        normalized = {
            "target_exists": source["target_exists"],
            "acceptable_profiles": [_profile_dict(item) for item in source["acceptable_profiles"]],
            "acceptable_target_blueprint_refs": source["acceptable_target_refs"],
            "distractor_blueprint_refs": source["distractor_refs"],
            "clarification_strategy": source["clarification_strategy"],
            "clarification_comparison_blueprint_refs": source["clarification_comparison_refs"],
            "weak_evidence_reason": None,
        }
        row = {"scenario_ref": target["scenario_ref"], **normalized, "source_semantic_payload_digest": canonical_digest(normalized)}
        rows.append(row)
        ledger_rows.append(
            {
                "scenario_ref": target["scenario_ref"],
                "source_payload_digest": canonical_digest(normalized),
                "target_payload_digest": canonical_digest({key: row[key] for key in normalized}),
                "semantic_payload_equal": True,
            }
        )
    weak_payload = _read_json(fixture_root / "authoring" / "weak-evidence-oracle-reviews.json")
    _require(
        weak_payload.get("schema_version") == WEAK_REVIEW_SCHEMA_VERSION
        and weak_payload.get("batch_ref") == BATCH_REF
        and isinstance(weak_payload.get("reviews"), list)
        and len(weak_payload["reviews"]) == 5,
        "weak Oracle review file invalid",
    )
    _require({item["scenario_ref"] for item in weak_payload["reviews"]} == weak_new_refs, "weak review refs invalid")
    blueprint_refs = {item["blueprint_ref"] for item in load_blueprints(fixture_root)}
    weak_fields = {
        "scenario_ref", "hidden_target_blueprint_ref", "competitor_blueprint_refs",
        "acceptable_profiles", "reason_code", "review_status", "assessment",
    }
    for item in weak_payload["reviews"]:
        _require(
            set(item) == weak_fields
            and item["reason_code"] in {"INSUFFICIENT_DISCRIMINATOR", "UNBOUNDED_SCOPE"}
            and item["review_status"] == "CODEX_SILVER_REVIEWED"
            and len(item["competitor_blueprint_refs"]) >= 2
            and len(item["competitor_blueprint_refs"])
            == len(set(item["competitor_blueprint_refs"]))
            and item["hidden_target_blueprint_ref"] not in item["competitor_blueprint_refs"],
            "weak Oracle review invalid",
        )
        _require(
            {item["hidden_target_blueprint_ref"], *item["competitor_blueprint_refs"]}
            <= blueprint_refs,
            "weak Oracle review names an unknown blueprint",
        )
        rows.append(
            {
                "scenario_ref": item["scenario_ref"],
                "target_exists": True,
                "acceptable_profiles": item["acceptable_profiles"],
                "acceptable_target_blueprint_refs": [item["hidden_target_blueprint_ref"]],
                "distractor_blueprint_refs": item["competitor_blueprint_refs"],
                "clarification_strategy": None,
                "clarification_comparison_blueprint_refs": [],
                "weak_evidence_reason": item["reason_code"],
                "weak_evidence_review_assessment": item["assessment"],
                "source_semantic_payload_digest": None,
            }
        )
    rows.sort(key=lambda item: item["scenario_ref"])
    _require(len(rows) == 56, "Oracle authoring requires 56 records")
    _write_json(
        fixture_root / "authoring" / "oracle.json",
        {"schema_version": ORACLE_AUTHORING_SCHEMA_VERSION, "batch_ref": BATCH_REF, "oracles": rows},
    )
    ledger_path = fixture_root / "migration-ledger.json"
    ledger = _read_json(ledger_path)
    ledger["oracle_payloads"] = ledger_rows
    ledger["weak_oracle_source_semantic_payload_reused"] = False
    ledger["scenario_freeze_preceded_oracle_migration"] = True
    _write_json(ledger_path, ledger)


def _terminal_expectations(category: str, acceptable_ids: tuple[str, ...]) -> tuple[TerminalExpectation, ...]:
    if category == "WEAK_EVIDENCE":
        return (TerminalExpectation(action="EXIT", target_node_id=None, target_disposition="PRESENT_NOT_FOUND"),)
    if category == "TARGET_ABSENT":
        return (TerminalExpectation(action="REJECT_ALL", target_node_id=None, target_disposition="ABSENT"),)
    terminals = []
    for node_id in acceptable_ids:
        terminals.append(TerminalExpectation(action="SELECT_CANDIDATE", target_node_id=node_id, target_disposition="FOUND_TOP8"))
        terminals.append(TerminalExpectation(action="SELECT_OUTSIDE_CANDIDATE", target_node_id=node_id, target_disposition="FOUND_OUTSIDE"))
    return tuple(terminals)


def freeze_oracles(fixture_root: Path) -> None:
    scenario_payload = _read_json(fixture_root / "frozen" / "scenarios.json")
    scenarios = tuple(SealedScenario.from_dict(item) for item in scenario_payload)
    scenario_bytes_before = (fixture_root / "frozen" / "scenarios.json").read_bytes()
    authoring = _read_json(fixture_root / "authoring" / "oracle.json")
    oracle_by_ref = {item["scenario_ref"]: item for item in authoring["oracles"]}
    candidates = {item["scenario_ref"]: item for item in _load_candidates(fixture_root)}
    reviews = _load_candidate_reviews(fixture_root)
    result = load_tree_export(fixture_root / "frozen" / "tree.json")
    _require(result.is_valid and result.tree is not None, "tree replay failed")
    tree = result.tree
    node_ids = {node.node_id for node in tree.nodes}
    oracles = []
    for scenario in scenarios:
        source = oracle_by_ref[scenario.scenario_ref]
        candidate = candidates[scenario.scenario_ref]
        acceptable_ids = tuple(stable_node_id(ref) for ref in source["acceptable_target_blueprint_refs"])
        distractor_refs = set(source["distractor_blueprint_refs"]) | set(source["clarification_comparison_blueprint_refs"])
        forbidden_ids = tuple(stable_node_id(ref) for ref in distractor_refs) if scenario.category != "TARGET_ABSENT" else ()
        _require(set(acceptable_ids) <= node_ids and set(forbidden_ids) <= node_ids, "Oracle blueprint binding failed")
        profiles = tuple(StructuralProfile.from_dict(item) for item in source["acceptable_profiles"])
        target_status = "TARGET_ABSENT" if scenario.category == "TARGET_ABSENT" else "TARGET_PRESENT"
        expected_route = "CLARIFY" if scenario.category == "CLARIFICATION" else ("LIMIT" if scenario.category == "WEAK_EVIDENCE" else "PROCEED")
        if scenario.category == "WEAK_EVIDENCE":
            policy_statuses = ("NEED_EVIDENCE",)
        elif scenario.category == "CLARIFICATION":
            policy_statuses = ("AMBIGUOUS",)
        elif scenario.category == "TARGET_ABSENT":
            policy_statuses = ("NONE",)
        else:
            policy_statuses = ("CANDIDATES_AVAILABLE",)
        reviewed_payload = {
            "candidate_authoring": candidate,
            "oracle_authoring": source,
            "candidate_review": reviews[scenario.scenario_ref],
        }
        oracle = SealedCaseOracle.create(
            scenario_ref=scenario.scenario_ref,
            tree_digest=scenario.tree_digest,
            request_digest=scenario.request_digest,
            category=scenario.category,
            expected_route=expected_route,
            acceptable_profiles=profiles,
            target_status=target_status,
            acceptable_node_ids=acceptable_ids,
            forbidden_node_ids=forbidden_ids,
            clarification_policy="CLARIFICATION_REQUIRED" if scenario.category == "CLARIFICATION" else "NOT_APPLICABLE",
            frozen_clarification_answer=scenario.frozen_clarification_answer,
            acceptable_policy_statuses=policy_statuses,
            acceptable_terminals=_terminal_expectations(scenario.category, acceptable_ids),
            wrong_context_challenge=scenario.wrong_context_challenge,
            review_status="CODEX_SILVER_REVIEWED",
            reviewed_bytes_digest=canonical_digest(reviewed_payload),
            execution_eligible=True,
        )
        _require(SealedCaseOracle.from_dict(oracle.to_dict()) == oracle, "Oracle round trip failed")
        oracles.append(oracle)
    _require((fixture_root / "frozen" / "scenarios.json").read_bytes() == scenario_bytes_before, "Oracle stage changed Scenario bytes")
    _write_json(fixture_root / "frozen" / "hidden-oracle.json", [item.to_dict() for item in oracles])


def _compatibility_manifest(scenarios: tuple[SealedScenario, ...], oracles_path: Path, tree_path: Path, scenarios_path: Path) -> SealedEvaluationManifest:
    repeat_refs = tuple(item.scenario_ref for item in scenarios if item.repeat_challenge)
    return SealedEvaluationManifest.create(
        function_commit=FUNCTION_COMMIT,
        data_commit="0" * 40,
        tree_sha256=_file_sha256(tree_path),
        scenarios_sha256=_file_sha256(scenarios_path),
        oracle_sha256=_file_sha256(oracles_path),
        model_name="PRECOMMIT_COMPATIBILITY_ONLY",
        understanding_prompt_version="PRECOMMIT_COMPATIBILITY_ONLY",
        clarification_prompt_version="PRECOMMIT_COMPATIBILITY_ONLY",
        semantic_prompt_version="PRECOMMIT_COMPATIBILITY_ONLY",
        endpoint_class="OFFICIAL_BAILIAN_COMPATIBLE",
        scenario_refs=tuple(item.scenario_ref for item in scenarios),
        repeat_scenario_refs=repeat_refs,
        wire_attempt_limit=320,
    )


def finalize(fixture_root: Path) -> None:
    tree_path = fixture_root / "frozen" / "tree.json"
    scenarios_path = fixture_root / "frozen" / "scenarios.json"
    oracles_path = fixture_root / "frozen" / "hidden-oracle.json"
    tree_result = load_tree_export(tree_path)
    _require(tree_result.is_valid and tree_result.tree is not None, "tree replay failed")
    scenarios = tuple(SealedScenario.from_dict(item) for item in _read_json(scenarios_path))
    oracles = tuple(SealedCaseOracle.from_dict(item) for item in _read_json(oracles_path))
    manifest = _compatibility_manifest(scenarios, oracles_path, tree_path, scenarios_path)
    validate_sealed_plan(manifest, scenarios, oracles)
    nodes = load_blueprints(fixture_root)
    signatures = signature_report(nodes)
    reviews = _load_candidate_reviews(fixture_root)
    _write_json(
        fixture_root / "frozen" / "silver-review.json",
        {
            "schema_version": CANDIDATE_REVIEW_SCHEMA_VERSION,
            "batch_ref": BATCH_REF,
            "quality_tier": "SILVER",
            "gold_eligible": False,
            "reviews": [reviews[ref] for ref in sorted(reviews)],
        },
    )
    category_counts = Counter(item.category for item in scenarios)
    preflight = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "batch_ref": BATCH_REF,
        "valid": True,
        "source_class": SOURCE_CLASS,
        "fictional": True,
        "derived_from_real": False,
        "node_count": tree_result.observed_node_count,
        "value_envelope_count": tree_result.observed_value_count,
        "tree_digest": tree_result.tree.snapshot_hash,
        "signature_report": signatures,
        "blueprint_review_count": 91,
        "candidate_review_count": 56,
        "scenario_round_trip_count": len(scenarios),
        "oracle_round_trip_count": len(oracles),
        "category_counts": dict(sorted(category_counts.items())),
        "target_present_count": sum(item.target_status == "TARGET_PRESENT" for item in oracles),
        "wrong_context_count": sum(item.wrong_context_challenge for item in scenarios),
        "repeat_count": sum(item.repeat_challenge for item in scenarios),
        "sealed_plan_compatible": True,
        "compatibility_manifest_persisted": False,
        "execution_manifest_present": False,
        "repository_file_mode_contract": "GIT_REGULAR_100644",
        "private_materialization_performed": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "production_qualification": False,
    }
    _write_json(fixture_root / "frozen" / "preflight.json", preflight)
    artifacts = (
        "catalog.json",
        "migration-ledger.json",
        "schemas/b02-artifacts.schema.json",
        "blueprints/root.json",
        "blueprints/branch-01.json",
        "blueprints/branch-02.json",
        "blueprints/branch-03.json",
        "blueprints/branch-04.json",
        "blueprints/branch-05.json",
        "blueprints/branch-06.json",
        "blueprints/branch-07.json",
        "blueprints/branch-08.json",
        "authoring/candidate-bindings.json",
        "authoring/candidates.json",
        "authoring/oracle.json",
        "authoring/weak-evidence-oracle-reviews.json",
        "reviews/blueprint-silver-review.json",
        "reviews/candidate-silver-review.json",
        "frozen/tree.json",
        "frozen/tree-preflight.json",
        "frozen/scenarios.json",
        "frozen/scenario-freeze.json",
        "frozen/hidden-oracle.json",
        "frozen/silver-review.json",
        "frozen/preflight.json",
    )
    _write_json(
        fixture_root / "frozen" / "data-manifest.json",
        {
            "schema_version": DATA_MANIFEST_SCHEMA_VERSION,
            "batch_ref": BATCH_REF,
            "function_commit": FUNCTION_COMMIT,
            "data_commit": None,
            "execution_manifest_present": False,
            "artifact_sha256": {name: _file_sha256(fixture_root / name) for name in artifacts},
            "gold_eligible": False,
            "patch_eligible": False,
            "production_qualification": False,
        },
    )


def verify_repository_modes(repository_root: Path, fixture_root: Path) -> None:
    for path in fixture_root.rglob("*"):
        if path.is_file():
            _require(not path.is_symlink(), "fixture must not contain symlinks")
            _require(stat.S_IMODE(path.stat().st_mode) & 0o111 == 0, "fixture file must be non-executable")
    _require(not (fixture_root / "frozen" / "execution-manifest.json").exists(), "execution manifest is forbidden before approval")
    _require((repository_root / "src" / "treeguard").is_dir(), "repository root invalid")


def run_all(source_root: Path, fixture_root: Path, repository_root: Path) -> None:
    migrate_scenario_sources(source_root, fixture_root)
    build_tree(fixture_root)
    freeze_scenarios(fixture_root)
    migrate_oracle_sources(source_root, fixture_root)
    freeze_oracles(fixture_root)
    finalize(fixture_root)
    verify_repository_modes(repository_root, fixture_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("migrate-scenarios", "build-tree", "freeze-scenarios", "migrate-oracles", "freeze-oracles", "finalize", "verify", "all"):
        command = subparsers.add_parser(name)
        command.add_argument("--fixture-root", type=Path, required=True)
        if name in {"migrate-scenarios", "migrate-oracles", "all"}:
            command.add_argument("--source-root", type=Path, required=True)
        if name in {"verify", "all"}:
            command.add_argument("--repository-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "migrate-scenarios":
        migrate_scenario_sources(args.source_root, args.fixture_root)
    elif args.command == "build-tree":
        build_tree(args.fixture_root)
    elif args.command == "freeze-scenarios":
        freeze_scenarios(args.fixture_root)
    elif args.command == "migrate-oracles":
        migrate_oracle_sources(args.source_root, args.fixture_root)
    elif args.command == "freeze-oracles":
        freeze_oracles(args.fixture_root)
    elif args.command == "finalize":
        finalize(args.fixture_root)
    elif args.command == "verify":
        verify_repository_modes(args.repository_root, args.fixture_root)
    else:
        run_all(args.source_root, args.fixture_root, args.repository_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
