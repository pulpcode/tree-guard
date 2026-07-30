#!/usr/bin/env python3
"""Run the frozen, aggregate-only legacy similarity audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable


NODE_EXACT_LIMIT = 0.10
NODE_CLUSTER_LIMIT = 0.20
SCENARIO_MAX_LIMIT = 0.85
SCENARIO_CLUSTER_COUNT = 2
L1_NAME_LIMIT = 0.50
CHILD_VECTOR_LIMIT = 0.15
SUBJECT_FACET_LIMIT = 0.15
TEMPLATE_MAX_LIMIT = 0.92
TEMPLATE_CLUSTER_COUNT = 3

REQUIRED_FROZEN_ARTIFACTS = {
    "codex-pre-review.json",
    "coverage-matrix.json",
    "dataset-charter.json",
    "human-review-checklist.json",
    "human-review.json",
    "l1-report.json",
    "l2-critic-findings.json",
    "l3-human-review-report.json",
    "manifest.json",
    "scenarios.json",
    "semantic-blueprint.json",
    "tree.json",
}


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _ngrams(value: str) -> frozenset[str]:
    normalized = _normalize(value)
    if not normalized:
        return frozenset()
    if len(normalized) < 2:
        return frozenset({f"1:{normalized}"})
    tokens: set[str] = set()
    for size in (2, 3, 4):
        if len(normalized) < size:
            continue
        tokens.update(
            f"{size}:{normalized[index:index + size]}"
            for index in range(len(normalized) - size + 1)
        )
    return frozenset(tokens)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _rounded(value: float) -> float:
    return round(value, 6)


def verify_freeze_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "freeze-manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("candidate_state") != "FROZEN":
        raise ValueError("freeze manifest is not in FROZEN state")
    expected_flags = {
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }
    for field, expected in expected_flags.items():
        if manifest.get(field) != expected:
            raise ValueError(f"freeze manifest has invalid {field}")

    entries = manifest.get("artifacts")
    if not isinstance(entries, list):
        raise ValueError("freeze manifest artifacts must be a list")
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if len(entries) != len(REQUIRED_FROZEN_ARTIFACTS):
        raise ValueError("freeze manifest must bind exactly 12 artifacts")
    if set(paths) != REQUIRED_FROZEN_ARTIFACTS or len(paths) != len(set(paths)):
        raise ValueError("freeze manifest does not bind the required artifacts")

    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("freeze manifest contains an unsafe artifact path")
        observed = hashlib.sha256((run_dir / relative).read_bytes()).hexdigest()
        if observed != entry.get("byte_sha256"):
            raise ValueError(f"frozen artifact changed: {relative.name}")
    return manifest


def _validate_cleanroom_inputs(
    tree: dict[str, Any],
    scenarios: list[dict[str, Any]],
    blueprint: dict[str, Any],
) -> None:
    metadata = tree.get("metadata", {})
    expected_tree_flags = {
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
    }
    for field, expected in expected_tree_flags.items():
        if metadata.get(field) != expected:
            raise ValueError(f"new tree has invalid {field}")
    if blueprint.get("source_class") != "CLEANROOM_SYNTHETIC":
        raise ValueError("new blueprint has invalid source_class")
    for scenario in scenarios:
        if scenario.get("source_class") != "CLEANROOM_SYNTHETIC":
            raise ValueError("new scenario has invalid source_class")
        for field, expected in (
            ("fictional", True),
            ("gold_eligible", False),
            ("patch_eligible", False),
        ):
            if scenario.get(field) != expected:
                raise ValueError(f"new scenario has invalid {field}")


def _extract_tree(document: dict[str, Any]) -> list[dict[str, Any]]:
    topology = document.get("map_topology")
    if not isinstance(topology, dict) or not topology:
        raise ValueError("tree document has no map_topology")
    nodes: list[dict[str, Any]] = []

    def visit(
        envelope: dict[str, Any],
        parent_id: str | None,
        depth: int,
        ancestor_ids: tuple[str, ...],
    ) -> str:
        metadata = envelope.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("tree node has no metadata")
        node_id = metadata.get("node_id")
        node_name = metadata.get("node_name")
        node_kind = metadata.get("node_type")
        if not all(isinstance(item, str) and item for item in (node_id, node_name, node_kind)):
            raise ValueError("tree node is missing id, name, or type")
        subnodes = envelope.get("subnodes") or {}
        if not isinstance(subnodes, dict):
            raise ValueError("tree node subnodes must be an object")
        record = {
            "id": node_id,
            "name": node_name,
            "kind": node_kind.upper(),
            "value_type": str(metadata.get("value_type") or "").casefold(),
            "cardinality": (
                "MULTIPLE" if metadata.get("is_list") is True else "SINGLE"
            ),
            "parent_id": parent_id,
            "depth": depth,
            "ancestor_ids": ancestor_ids,
            "child_ids": [],
        }
        nodes.append(record)
        for child in subnodes.values():
            if not isinstance(child, dict):
                raise ValueError("tree child must be an object")
            child_id = visit(
                child,
                node_id,
                depth + 1,
                ancestor_ids + (node_id,),
            )
            record["child_ids"].append(child_id)
        return node_id

    for root in topology.values():
        if not isinstance(root, dict):
            raise ValueError("tree root must be an object")
        visit(root, None, 0, ())
    return nodes


def _extract_scenarios(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = document.get("items")
    else:
        items = None
    if not isinstance(items, list):
        raise ValueError("scenario document must contain an item list")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("scenario items must be objects")
    return items


def _requirement_texts(items: Iterable[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in items:
        request = item.get("request")
        text = request.get("requirement_text") if isinstance(request, dict) else None
        if not isinstance(text, str) or not text:
            raise ValueError("scenario is missing requirement_text")
        texts.append(text)
    return texts


def _similarity_profile(
    new_values: Iterable[str],
    legacy_values: Iterable[str],
) -> dict[str, Any]:
    new = sorted({_normalize(value) for value in new_values if _normalize(value)})
    legacy = sorted(
        {_normalize(value) for value in legacy_values if _normalize(value)}
    )
    legacy_set = set(legacy)
    exact_count = sum(value in legacy_set for value in new)
    denominator = min(len(new), len(legacy))
    legacy_grams = [_ngrams(value) for value in legacy]
    nearest = [
        max((_jaccard(_ngrams(value), grams) for grams in legacy_grams), default=0.0)
        for value in new
    ]
    return {
        "new_unique_count": len(new),
        "legacy_unique_count": len(legacy),
        "exact_overlap_count": exact_count,
        "exact_overlap_ratio": _rounded(exact_count / denominator)
        if denominator
        else 0.0,
        "max_similarity": _rounded(max(nearest, default=0.0)),
        "count_ge_0_70": sum(value >= 0.70 for value in nearest),
        "ratio_ge_0_70": _rounded(
            sum(value >= 0.70 for value in nearest) / len(new)
        )
        if new
        else 0.0,
        "count_ge_0_75": sum(value >= 0.75 for value in nearest),
        "count_ge_0_80": sum(value >= 0.80 for value in nearest),
        "count_ge_0_85": sum(value >= 0.85 for value in nearest),
        "count_ge_0_92": sum(value >= 0.92 for value in nearest),
        "count_ge_0_95": sum(value >= 0.95 for value in nearest),
    }


def _node_map(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped = {node["id"]: node for node in nodes}
    if len(mapped) != len(nodes):
        raise ValueError("tree contains duplicate node ids")
    return mapped


def _path_shapes(nodes: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    mapped = _node_map(nodes)
    shapes: list[tuple[Any, ...]] = []
    for node in nodes:
        path_ids = node["ancestor_ids"] + (node["id"],)
        path = [mapped[node_id] for node_id in path_ids]
        shapes.append(
            (
                node["depth"],
                tuple(item["kind"] for item in path),
                tuple(len(item["child_ids"]) for item in path),
            )
        )
    return shapes


def _child_vectors(
    nodes: list[dict[str, Any]],
) -> tuple[list[tuple[str, ...]], list[tuple[tuple[str, str, str], ...]]]:
    mapped = _node_map(nodes)
    name_vectors: list[tuple[str, ...]] = []
    type_vectors: list[tuple[tuple[str, str, str], ...]] = []
    for node in nodes:
        children = [mapped[child_id] for child_id in node["child_ids"]]
        if not children:
            continue
        name_vectors.append(tuple(sorted(_normalize(child["name"]) for child in children)))
        type_vectors.append(
            tuple(
                sorted(
                    (
                        child["kind"],
                        child["value_type"],
                        child["cardinality"],
                    )
                    for child in children
                )
            )
        )
    return name_vectors, type_vectors


def _subject_facet_pairs(nodes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    mapped = _node_map(nodes)
    pairs: list[tuple[str, str]] = []
    for child in nodes:
        if child["kind"] != "PROPERTY" or child["parent_id"] is None:
            continue
        parent = mapped[child["parent_id"]]
        pairs.append((_normalize(parent["name"]), _normalize(child["name"])))
    return pairs


def _vector_profile(
    new_vectors: Iterable[tuple[Any, ...]],
    legacy_vectors: Iterable[tuple[Any, ...]],
) -> dict[str, Any]:
    new = list(new_vectors)
    legacy = set(legacy_vectors)
    matched = sum(vector in legacy for vector in new)
    return {
        "new_vector_count": len(new),
        "legacy_unique_vector_count": len(legacy),
        "matched_new_vector_count": matched,
        "matched_new_vector_ratio": _rounded(matched / len(new)) if new else 0.0,
    }


def _descendant_count(
    node_id: str,
    mapped: dict[str, dict[str, Any]],
) -> int:
    return sum(
        1 + _descendant_count(child_id, mapped)
        for child_id in mapped[node_id]["child_ids"]
    )


def _l1_signature(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    mapped = _node_map(nodes)
    roots = [node for node in nodes if node["parent_id"] is None]
    l1_nodes = [
        mapped[child_id]
        for root in roots
        for child_id in root["child_ids"]
    ]
    return {
        "names": {_normalize(node["name"]) for node in l1_nodes},
        "descendant_vector": tuple(
            sorted(_descendant_count(node["id"], mapped) for node in l1_nodes)
        ),
    }


def _l1_profile(
    new_nodes: list[dict[str, Any]],
    legacy_by_tier: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    new = _l1_signature(new_nodes)
    max_name_ratio = 0.0
    descendant_matches = 0
    joint_matches = 0
    for legacy_nodes in legacy_by_tier.values():
        legacy = _l1_signature(legacy_nodes)
        denominator = min(len(new["names"]), len(legacy["names"]))
        name_ratio = (
            len(new["names"] & legacy["names"]) / denominator
            if denominator
            else 0.0
        )
        vector_match = new["descendant_vector"] == legacy["descendant_vector"]
        max_name_ratio = max(max_name_ratio, name_ratio)
        descendant_matches += int(vector_match)
        joint_matches += int(name_ratio >= L1_NAME_LIMIT and vector_match)
    return {
        "new_branch_count": len(new["names"]),
        "legacy_tier_count": len(legacy_by_tier),
        "max_exact_name_overlap_ratio": _rounded(max_name_ratio),
        "descendant_vector_match_tier_count": descendant_matches,
        "joint_copy_match_tier_count": joint_matches,
    }


def _template_fingerprints(texts: Iterable[str], node_names: Iterable[str]) -> list[str]:
    normalized_names = sorted(
        {
            _normalize(name)
            for name in node_names
            if len(_normalize(name)) >= 2
        },
        key=lambda value: (-len(value), value),
    )
    fingerprints: list[str] = []
    for text in texts:
        fingerprint = _normalize(text)
        for name in normalized_names:
            fingerprint = fingerprint.replace(name, "x")
        fingerprints.append(re.sub(r"x+", "x", fingerprint))
    return fingerprints


def _check(
    triggered: bool,
    observed: dict[str, Any],
    rule: str,
) -> dict[str, Any]:
    return {"triggered": triggered, "observed": observed, "rule": rule}


def build_audit_result(
    freeze_manifest: dict[str, Any],
    new_tree: dict[str, Any],
    new_scenarios: list[dict[str, Any]],
    legacy_trees: dict[str, dict[str, Any]],
    legacy_scenarios: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    new_nodes = _extract_tree(new_tree)
    legacy_nodes_by_tier = {
        tier: _extract_tree(document)
        for tier, document in legacy_trees.items()
    }
    all_legacy_nodes = [
        node
        for tier in sorted(legacy_nodes_by_tier)
        for node in legacy_nodes_by_tier[tier]
    ]
    new_texts = _requirement_texts(new_scenarios)
    legacy_texts = [
        text
        for tier in sorted(legacy_scenarios)
        for text in _requirement_texts(legacy_scenarios[tier])
    ]

    node_profile = _similarity_profile(
        (node["name"] for node in new_nodes),
        (node["name"] for node in all_legacy_nodes),
    )
    scenario_profile = _similarity_profile(new_texts, legacy_texts)
    l1_profile = _l1_profile(new_nodes, legacy_nodes_by_tier)

    new_name_vectors, new_type_vectors = _child_vectors(new_nodes)
    legacy_name_vectors: list[tuple[str, ...]] = []
    legacy_type_vectors: list[tuple[tuple[str, str, str], ...]] = []
    for nodes in legacy_nodes_by_tier.values():
        name_vectors, type_vectors = _child_vectors(nodes)
        legacy_name_vectors.extend(name_vectors)
        legacy_type_vectors.extend(type_vectors)
    name_vector_profile = _vector_profile(new_name_vectors, legacy_name_vectors)
    type_vector_profile = _vector_profile(new_type_vectors, legacy_type_vectors)
    path_profile = _vector_profile(
        _path_shapes(new_nodes),
        (
            shape
            for nodes in legacy_nodes_by_tier.values()
            for shape in _path_shapes(nodes)
        ),
    )
    subject_facet_profile = _vector_profile(
        _subject_facet_pairs(new_nodes),
        (
            pair
            for nodes in legacy_nodes_by_tier.values()
            for pair in _subject_facet_pairs(nodes)
        ),
    )
    template_profile = _similarity_profile(
        _template_fingerprints(
            new_texts,
            (node["name"] for node in new_nodes),
        ),
        _template_fingerprints(
            legacy_texts,
            (node["name"] for node in all_legacy_nodes),
        ),
    )

    checks = {
        "NODE_EXACT_OVERLAP": _check(
            node_profile["exact_overlap_ratio"] >= NODE_EXACT_LIMIT,
            {"ratio": node_profile["exact_overlap_ratio"]},
            "ratio >= 0.10",
        ),
        "NODE_NGRAM_CLUSTER": _check(
            (
                node_profile["ratio_ge_0_70"] >= NODE_CLUSTER_LIMIT
                or (
                    node_profile["count_ge_0_95"] >= 1
                    and node_profile["count_ge_0_85"] >= 2
                )
            ),
            {
                "ratio_ge_0_70": node_profile["ratio_ge_0_70"],
                "count_ge_0_85": node_profile["count_ge_0_85"],
                "count_ge_0_95": node_profile["count_ge_0_95"],
            },
            "ratio_ge_0_70 >= 0.20 or (count_ge_0_95 >= 1 and count_ge_0_85 >= 2)",
        ),
        "SCENARIO_EXACT_OVERLAP": _check(
            scenario_profile["exact_overlap_count"] > 0,
            {"count": scenario_profile["exact_overlap_count"]},
            "count > 0",
        ),
        "SCENARIO_NGRAM_CLUSTER": _check(
            (
                scenario_profile["max_similarity"] >= SCENARIO_MAX_LIMIT
                or scenario_profile["count_ge_0_75"] >= SCENARIO_CLUSTER_COUNT
            ),
            {
                "max_similarity": scenario_profile["max_similarity"],
                "count_ge_0_75": scenario_profile["count_ge_0_75"],
            },
            "max_similarity >= 0.85 or count_ge_0_75 >= 2",
        ),
        "L1_BRANCH_COPY": _check(
            l1_profile["joint_copy_match_tier_count"] > 0,
            {
                "max_exact_name_overlap_ratio": l1_profile[
                    "max_exact_name_overlap_ratio"
                ],
                "joint_copy_match_tier_count": l1_profile[
                    "joint_copy_match_tier_count"
                ],
            },
            "same tier has exact-name ratio >= 0.50 and identical descendant vector",
        ),
        "CHILD_VECTOR_COPY": _check(
            name_vector_profile["matched_new_vector_ratio"] >= CHILD_VECTOR_LIMIT,
            {"ratio": name_vector_profile["matched_new_vector_ratio"]},
            "name-bearing child-vector ratio >= 0.15",
        ),
        "SUBJECT_FACET_COPY": _check(
            subject_facet_profile["matched_new_vector_ratio"]
            >= SUBJECT_FACET_LIMIT,
            {"ratio": subject_facet_profile["matched_new_vector_ratio"]},
            "subject/facet exact-pair ratio >= 0.15",
        ),
        "TEMPLATE_FINGERPRINT_COPY": _check(
            (
                template_profile["exact_overlap_count"] > 0
                or template_profile["max_similarity"] >= TEMPLATE_MAX_LIMIT
                or template_profile["count_ge_0_80"] >= TEMPLATE_CLUSTER_COUNT
            ),
            {
                "exact_overlap_count": template_profile["exact_overlap_count"],
                "max_similarity": template_profile["max_similarity"],
                "count_ge_0_80": template_profile["count_ge_0_80"],
            },
            "exact > 0 or max >= 0.92 or count_ge_0_80 >= 3",
        ),
    }
    finding_codes = sorted(
        code for code, finding in checks.items() if finding["triggered"]
    )
    return {
        "audit_version": "fictional-legacy-similarity.v1",
        "authority": "DETERMINISTIC_READ_ONLY",
        "candidate_state": "FROZEN",
        "dataset_ref": freeze_manifest["dataset_ref"],
        "run_ref": freeze_manifest["run_ref"],
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "patch_eligible": False,
        "freeze_verified": True,
        "decision": "REJECT" if finding_codes else "ACCEPT",
        "finding_codes": finding_codes,
        "checks": checks,
        "input_counts": {
            "new_nodes": len(new_nodes),
            "new_scenarios": len(new_scenarios),
            "legacy_tiers": len(legacy_nodes_by_tier),
            "legacy_nodes_by_tier": {
                tier: len(nodes)
                for tier, nodes in sorted(legacy_nodes_by_tier.items())
            },
            "legacy_scenarios_by_tier": {
                tier: len(items)
                for tier, items in sorted(legacy_scenarios.items())
            },
        },
        "metrics": {
            "node_names": node_profile,
            "scenario_text": scenario_profile,
            "l1_branches": l1_profile,
            "name_child_vectors": name_vector_profile,
            "subject_facet_pairs": subject_facet_profile,
            "template_fingerprints": template_profile,
        },
        "diagnostic_only": {
            "path_shapes": path_profile,
            "type_child_vectors": type_vector_profile,
        },
        "limitations": [
            "该审计只检测冻结候选与当前旧回归集之间的雷同，不证明领域正确性。",
            "通用树合同造成的结构形状重合只作诊断，不单独触发拒绝。",
            "审计通过不授予 Gold，也不自动晋升正式 fixture。",
            "审计结果不得反馈给生成器以靠近或规避旧数据。",
        ],
    }


def run_audit(run_dir: Path, legacy_dir: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze_manifest(run_dir)
    new_tree = _read_json(run_dir / "tree.json")
    new_scenarios = _extract_scenarios(_read_json(run_dir / "scenarios.json"))
    blueprint = _read_json(run_dir / "semantic-blueprint.json")
    _validate_cleanroom_inputs(new_tree, new_scenarios, blueprint)

    tree_files = sorted(legacy_dir.glob("tree-*.json"))
    if not tree_files:
        raise ValueError("legacy fixture directory has no tree tiers")
    legacy_trees: dict[str, dict[str, Any]] = {}
    legacy_scenarios: dict[str, list[dict[str, Any]]] = {}
    for tree_path in tree_files:
        tier = tree_path.stem.removeprefix("tree-")
        scenario_path = legacy_dir / f"scenarios-{tier}.json"
        if not scenario_path.is_file():
            raise ValueError(f"legacy tier has no scenario fixture: {tier}")
        legacy_trees[tier] = _read_json(tree_path)
        legacy_scenarios[tier] = _extract_scenarios(_read_json(scenario_path))
    return build_audit_result(
        freeze_manifest,
        new_tree,
        new_scenarios,
        legacy_trees,
        legacy_scenarios,
    )


def _parse_args() -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[1]
    run_dir = (
        repository
        / "artifacts"
        / "fictional-validation"
        / "qinglan-library-control-v1-run-004"
    )
    parser = argparse.ArgumentParser(
        description="Audit frozen synthetic data against legacy fixtures."
    )
    parser.add_argument("--run-dir", type=Path, default=run_dir)
    parser.add_argument(
        "--legacy-dir",
        type=Path,
        default=repository / "tests" / "fixtures" / "fictional" / "fire_validation",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=run_dir / "legacy-similarity-audit.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_audit(args.run_dir, args.legacy_dir)
    payload = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "finding_codes": result["finding_codes"],
                "output": args.output.name,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["decision"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
