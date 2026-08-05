#!/usr/bin/env python3
"""Run the frozen two-round R2 sealed confirmation experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import preflight_fire_r2_sealed_confirmation_cleanroom_2 as data_preflight  # noqa: E402
from treeguard.ai_review import (  # noqa: E402
    RETRIEVAL_ROLE_PROMPT_VERSION,
    RETRIEVAL_ROLE_RETRY_CODES,
    BailianConfig,
    BailianProviderError,
    BailianRetrievalRoleProvider,
    build_retrieval_role_request_body,
)
from treeguard.change_intent import (  # noqa: E402
    CONFIRMATION_SCHEMA_VERSION,
    IntentConfirmation,
    IntentContent,
    IntentRequest,
)
from treeguard.hashing import canonical_digest  # noqa: E402
from treeguard.private_io import write_private_json  # noqa: E402
from treeguard.retrieval import CandidateRetrievalError  # noqa: E402
from treeguard.retrieval_role_tolerant import (  # noqa: E402
    ALGORITHM_VERSION as R2_ALGORITHM_VERSION,
    build_boundary_tolerant_role_candidate_set,
)
from treeguard.retrieval_roles import (  # noqa: E402
    ALGORITHM_VERSION as R1_ALGORITHM_VERSION,
    RetrievalRoleEvidence,
    build_model_retrieval_role_evidence,
    build_role_candidate_set,
)


REPORT_VERSION = "fire-r2-sealed-confirmation-report.v1"
PRIVATE_ROUND_VERSION = "fire-r2-sealed-confirmation-private-round.v1"
PRIVATE_FINAL_VERSION = "fire-r2-sealed-confirmation-private-final.v1"
RUNNER_VERSION = "treeguard.fire-r2-sealed-confirmation-runner.v1"
ROUND_COUNT = 2
SCENARIO_COUNT = 28
POSITIVE_COUNT = 24
EMPTY_COUNT = 4
MAXIMUM_ACTUAL_CALL_COUNT = 112
MODEL_ID = "qwen3.6-35b-a3b"
VIEW_ORDER = data_preflight.FIVE_VIEW_NAMES
ALGORITHMS = ("R1", "R2")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
Transport = Callable[[dict[str, Any]], Any]


class SealedRunnerError(RuntimeError):
    def __init__(self, code: str, *, llm_called: bool = False) -> None:
        self.code = code
        self.llm_called = llm_called
        super().__init__(code)


def _git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_PAGER": "cat"},
    )


def _wire_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _request_allowlist(request: IntentRequest, model: str) -> frozenset[str]:
    bodies = [build_retrieval_role_request_body(request, model)]
    bodies.extend(
        build_retrieval_role_request_body(request, model, retry_code=code)
        for code in sorted(RETRIEVAL_ROLE_RETRY_CODES)
    )
    return frozenset(hashlib.sha256(_wire_bytes(body)).hexdigest() for body in bodies)


class PlannedRoleProvider(BailianRetrievalRoleProvider):
    """Enforce per-unit request allowlists and retain traffic only in private memory."""

    def __init__(
        self,
        config: BailianConfig,
        allowed_hashes: frozenset[str],
        forbidden_values: frozenset[str],
        *,
        transport: Transport | None = None,
    ) -> None:
        super().__init__(config)
        self.allowed_hashes = allowed_hashes
        self.forbidden_values = forbidden_values
        self.transport = transport
        self.records: list[dict[str, Any]] = []

    def _post_json(self, body: dict[str, Any]) -> Any:
        encoded = _wire_bytes(body)
        text = encoded.decode("utf-8")
        if any(value and value in text for value in self.forbidden_values):
            raise SealedRunnerError("R2_SEALED_MODEL_INPUT_LEAK")
        if hashlib.sha256(encoded).hexdigest() not in self.allowed_hashes:
            raise SealedRunnerError("R2_SEALED_UNPLANNED_REQUEST_BODY")
        if len(self.records) >= 2:
            raise SealedRunnerError("R2_SEALED_UNIT_CALL_LIMIT_EXCEEDED")
        record = {"request": body, "response": None}
        self.records.append(record)
        response = self.transport(body) if self.transport is not None else super()._post_json(body)
        record["response"] = response
        return response


def validate_runtime_binding(
    repo: Path,
    private_root: Path,
    execution_binding_path: Path,
    data_commit: str,
    runner_commit: str,
) -> tuple[Any, dict[str, Any]]:
    if _COMMIT.fullmatch(data_commit) is None or _COMMIT.fullmatch(runner_commit) is None:
        raise SealedRunnerError("R2_SEALED_COMMIT_INVALID")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != runner_commit:
        raise SealedRunnerError("R2_SEALED_RUNNER_HEAD_MISMATCH")
    if _git(repo, "merge-base", "--is-ancestor", data_commit, runner_commit, check=False).returncode:
        raise SealedRunnerError("R2_SEALED_DATA_NOT_ANCESTOR")
    if _git(repo, "status", "--porcelain=v1").stdout.strip():
        raise SealedRunnerError("R2_SEALED_WORKTREE_NOT_CLEAN")
    changed_data_files = _git(
        repo,
        "diff",
        "--name-only",
        data_commit,
        runner_commit,
        "--",
        *sorted(data_preflight.PUBLIC_FILES),
    ).stdout.strip()
    if changed_data_files:
        raise SealedRunnerError("R2_SEALED_DATA_FILES_CHANGED")

    rows = []
    for line in _git(
        repo,
        "diff",
        "--name-status",
        "--no-renames",
        data_preflight.BASELINE,
        data_commit,
    ).stdout.splitlines():
        pieces = line.split("\t")
        if len(pieces) != 2:
            raise SealedRunnerError("R2_SEALED_DATA_DIFF_INVALID")
        rows.append((pieces[0], pieces[1]))
    try:
        data_preflight.validate_commit_rows(rows)
        node_ids = data_preflight.validate_public(repo)
        data_preflight.validate_private(repo, private_root, node_ids)
        binding, binding_raw = data_preflight.load_execution_binding(execution_binding_path)
        public_paths = tuple(path for _, path in rows)
        if public_paths != tuple(sorted(public_paths)):
            raise SealedRunnerError("R2_SEALED_DATA_DIFF_ORDER_INVALID")
        ledger = data_preflight.build_binding_ledger(
            repo,
            private_root,
            data_commit,
            public_paths,
            binding,
            binding_raw,
        )
        data_preflight.verify_final_freeze(private_root, ledger)
    except (data_preflight.GateError, OSError, ValueError) as error:
        raise SealedRunnerError("R2_SEALED_DATA_FREEZE_INVALID") from error
    if (
        binding["model_id"] != MODEL_ID
        or binding["prompt_version"] != RETRIEVAL_ROLE_PROMPT_VERSION
        or binding["r1_strategy_id"] != R1_ALGORITHM_VERSION
        or binding["r2_strategy_id"] != R2_ALGORITHM_VERSION
        or binding["round_count"] != ROUND_COUNT
        or binding["scenario_count"] != SCENARIO_COUNT
        or binding["maximum_actual_call_count"] != MAXIMUM_ACTUAL_CALL_COUNT
    ):
        raise SealedRunnerError("R2_SEALED_EXECUTION_BINDING_MISMATCH")
    generator = data_preflight.load_generator(repo)
    tree_document = data_preflight.public_json(repo / generator.TREE_FILE, 10_000_000)
    imported = data_preflight.adapt_tree_document(tree_document, source_hint="fire-r2-sealed-runner")
    if imported.tree is None or imported.issues:
        raise SealedRunnerError("R2_SEALED_TREE_INVALID")
    return imported.tree, binding


def _confirmation(
    request: IntentRequest,
    seed: IntentContent,
    tree: Any,
    view: str,
) -> IntentConfirmation:
    draft_hash = canonical_digest([RUNNER_VERSION, view, "draft"])
    action_hash = canonical_digest([RUNNER_VERSION, view, "action"])
    payload = {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "status": "CONFIRMED_FOR_RETRIEVAL",
        "identity_status": "UNVERIFIED_FILE_ASSERTION",
        "semantic_approval": False,
        "patch_eligible": False,
        "source_request_hash": request.request_hash,
        "source_snapshot_hash": tree.snapshot_hash,
        "source_draft_hash": draft_hash,
        "source_action_hash": action_hash,
        "proposed_parent_node_id": request.proposed_parent_node_id,
        "reviewer_ref": "r2-sealed-runner",
        "recorded_at": "2026-08-05T00:00:00Z",
        "intent": seed.to_dict(),
    }
    return IntentConfirmation(
        status="CONFIRMED_FOR_RETRIEVAL",
        source_request_hash=request.request_hash,
        source_snapshot_hash=tree.snapshot_hash,
        source_draft_hash=draft_hash,
        source_action_hash=action_hash,
        proposed_parent_node_id=request.proposed_parent_node_id,
        reviewer_ref="r2-sealed-runner",
        recorded_at="2026-08-05T00:00:00Z",
        intent=seed,
        confirmation_hash=canonical_digest(payload),
    )


def _rank(candidate_set: Any, acceptable_ids: set[str]) -> int | None:
    ranks = [item.rank for item in candidate_set.candidates if item.node_id in acceptable_ids]
    return min(ranks) if ranks else None


def _aggregate(observations: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [item for item in observations if item["positive"]]
    empties = [item for item in observations if not item["positive"]]
    hard_negatives = [item for item in observations if item["hard_negative"]]
    non_literal = [
        item for item in positives if item["primary_category"] == "NON_LITERAL"
    ]
    ranks = [item["rank"] for item in positives]
    return {
        "target_count": len(positives),
        "recall_at_8": sum(rank is not None and rank <= 8 for rank in ranks),
        "recall_at_20": sum(rank is not None and rank <= 20 for rank in ranks),
        "mrr_scaled_1e6": (
            sum(1_000_000 // rank for rank in ranks if rank is not None) // len(positives)
            if positives
            else 0
        ),
        "empty_count": len(empties),
        "empty_status_match_count": sum(item["empty_match"] for item in empties),
        "hard_negative_count": len(hard_negatives),
        "hard_negative_top8_safe_count": sum(item["hard_negative_safe"] for item in hard_negatives),
        "non_literal_count": len(non_literal),
        "non_literal_recall_at_8": sum(
            item["rank"] is not None and item["rank"] <= 8 for item in non_literal
        ),
        "non_literal_recall_at_20": sum(
            item["rank"] is not None and item["rank"] <= 20 for item in non_literal
        ),
        "replay_count": len(observations),
        "replay_match_count": sum(item["replay_match"] for item in observations),
        "status_counts": dict(sorted(Counter(item["status"] for item in observations).items())),
    }


def _round_failure_codes(report: dict[str, Any]) -> list[str]:
    if report["contract_success_count"] != SCENARIO_COUNT:
        return ["R2_SEALED_ROLE_CONTRACT_FAILURE"]
    codes = []
    if report["transport_failure_count"]:
        codes.append("R2_SEALED_TRANSPORT_FAILURE")
    if not SCENARIO_COUNT <= report["actual_call_count"] <= SCENARIO_COUNT * 2:
        codes.append("R2_SEALED_ROUND_CALL_BUDGET_INVALID")
    r2 = report["views"]["R2"]
    for view in ("V_REQUIREMENT_ONLY", "V_FREE_TEXT_DROPPED"):
        if r2[view]["recall_at_8"] < 22:
            codes.append("R2_SEALED_PRIMARY_RECALL8_BELOW_MINIMUM")
        if r2[view]["recall_at_20"] < 23:
            codes.append("R2_SEALED_PRIMARY_RECALL20_BELOW_MINIMUM")
        if r2[view]["mrr_scaled_1e6"] < 800_000:
            codes.append("R2_SEALED_PRIMARY_MRR_BELOW_MINIMUM")
    if r2["V_CANONICAL"]["recall_at_8"] < 22:
        codes.append("R2_SEALED_CANONICAL_RECALL_BELOW_MINIMUM")
    if r2["V_PARENT_ABSENT"]["recall_at_8"] < 21:
        codes.append("R2_SEALED_PARENT_ABSENT_BELOW_MINIMUM")
    if r2["V_PARENT_WRONG_BRANCH"]["recall_at_20"] < 22:
        codes.append("R2_SEALED_WRONG_PARENT_BELOW_MINIMUM")
    if any(item["empty_status_match_count"] != EMPTY_COUNT for item in r2.values()):
        codes.append("R2_SEALED_EMPTY_STATUS_FAILURE")
    if any(item["hard_negative_top8_safe_count"] != 4 for item in r2.values()):
        codes.append("R2_SEALED_HARD_NEGATIVE_FAILURE")
    if any(item["replay_match_count"] != SCENARIO_COUNT for item in r2.values()):
        codes.append("R2_SEALED_REPLAY_FAILURE")
    return sorted(set(codes))


def load_sources(private_root: Path, tree: Any) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    locked = data_preflight.private_json(private_root, data_preflight.PRIVATE_FILES[0])
    oracle = data_preflight.private_json(private_root, data_preflight.PRIVATE_FILES[2])
    frozen = data_preflight.private_json(private_root, data_preflight.PRIVATE_FILES[4])
    execution = data_preflight.private_json(private_root, data_preflight.EXECUTION_INPUT_FILE)
    candidates = {item["candidate_id"]: item for item in locked["candidates"]}
    oracle_by_id = {item["candidate_id"]: item for item in oracle["entries"]}
    execution_by_id = {item["candidate_id"]: item for item in execution["entries"]}
    selected = list(frozen["selected_candidate_ids"])
    if selected != list(data_preflight.FROZEN_IDS):
        raise SealedRunnerError("R2_SEALED_FROZEN_ORDER_INVALID")
    units = [
        {
            "candidate": candidates[item],
            "oracle": oracle_by_id[item],
            "execution": execution_by_id[item],
        }
        for item in selected
    ]
    if len(units) != SCENARIO_COUNT:
        raise SealedRunnerError("R2_SEALED_DENOMINATOR_INVALID")
    return units, candidates, execution_by_id


def run_round(
    round_number: int,
    units: list[dict[str, Any]],
    tree: Any,
    config: BailianConfig,
    *,
    transport: Transport | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    observations = {
        algorithm: {view: [] for view in VIEW_ORDER} for algorithm in ALGORITHMS
    }
    private_units = []
    contract_success_count = 0
    actual_call_count = 0
    transport_failure_count = 0
    validation_codes: Counter[str] = Counter()
    forbidden_values = frozenset(node.node_id for node in tree.nodes)
    for unit in units:
        candidate = unit["candidate"]
        oracle = unit["oracle"]
        entry = unit["execution"]
        views = data_preflight.build_execution_views(entry, candidate, tree)
        canonical_request = views[0][1]
        provider = PlannedRoleProvider(
            config,
            _request_allowlist(canonical_request, config.model),
            forbidden_values,
            transport=transport,
        )
        try:
            source_evidence = provider.extract_roles(canonical_request)
        except (BailianProviderError, CandidateRetrievalError, SealedRunnerError) as error:
            code = getattr(error, "code", "R2_SEALED_ROLE_EXTRACTION_FAILED")
            validation_codes[code] += 1
            transport_failure_count += code.startswith("BAILIAN_")
            private_units.append({
                "candidate_id": candidate["candidate_id"],
                "status": "ROLE_EXTRACTION_FAILED",
                "error_code": code,
                "traffic": provider.records,
            })
            actual_call_count += len(provider.records)
            continue
        actual_call_count += len(provider.records)
        contract_success_count += 1
        private_views: dict[str, Any] = {}
        for view_name, request, seed, include_expansion in views:
            evidence = build_model_retrieval_role_evidence(source_evidence.to_model_dict(), request)
            confirmation = _confirmation(request, seed, tree, view_name)
            private_views[view_name] = {}
            for algorithm in ALGORITHMS:
                if algorithm == "R1":
                    build = lambda: build_role_candidate_set(
                        evidence,
                        request,
                        confirmation,
                        tree,
                        include_model_expansion=include_expansion,
                    )
                else:
                    build = lambda: build_boundary_tolerant_role_candidate_set(
                        evidence,
                        request,
                        confirmation,
                        tree,
                        include_model_expansion=include_expansion,
                    )
                first = build()
                second = build()
                acceptable = set(oracle["acceptable_node_ids"])
                excluded = set(oracle["excluded_node_ids"])
                top8 = {item.node_id for item in first.candidates[:8]}
                observation = {
                    "primary_category": oracle["primary_category"],
                    "positive": bool(acceptable),
                    "rank": _rank(first, acceptable),
                    "empty_match": not acceptable and first.status == "NO_CANDIDATES",
                    "hard_negative": bool(excluded),
                    "hard_negative_safe": bool(excluded) and not bool(top8 & excluded),
                    "replay_match": first.to_dict() == second.to_dict(),
                    "status": first.status,
                }
                observations[algorithm][view_name].append(observation)
                private_views[view_name][algorithm] = first.to_dict()
        private_units.append({
            "candidate_id": candidate["candidate_id"],
            "status": "COMPLETED",
            "role_output": source_evidence.to_model_dict(),
            "traffic": provider.records,
            "views": private_views,
        })
    if actual_call_count > SCENARIO_COUNT * 2:
        raise SealedRunnerError("R2_SEALED_ROUND_CALL_LIMIT_EXCEEDED")
    views = {
        algorithm: {
            view: _aggregate(observations[algorithm][view])
            for view in VIEW_ORDER
        }
        for algorithm in ALGORITHMS
    }
    report = {
        "round": round_number,
        "contract_success_count": contract_success_count,
        "transport_failure_count": transport_failure_count,
        "actual_call_count": actual_call_count,
        "validation_error_code_counts": dict(sorted(validation_codes.items())),
        "views": views,
    }
    report["failure_codes"] = _round_failure_codes(report)
    report["status"] = "PASS" if not report["failure_codes"] else "FAIL"
    private_report = {
        "schema_version": PRIVATE_ROUND_VERSION,
        "round": round_number,
        "aggregate": report,
        "units": private_units,
    }
    return report, private_report


def run_experiment(
    repo: Path,
    private_root: Path,
    output_root: Path,
    execution_binding_path: Path,
    data_commit: str,
    runner_commit: str,
    config: BailianConfig,
    *,
    transport: Transport | None = None,
) -> dict[str, Any]:
    tree, _ = validate_runtime_binding(
        repo, private_root, execution_binding_path, data_commit, runner_commit
    )
    if config.model != MODEL_ID or config.max_attempts != 2 or config.max_transport_retries != 0:
        raise SealedRunnerError("R2_SEALED_PROVIDER_CONFIG_MISMATCH")
    if not output_root.is_absolute() or output_root.exists():
        raise SealedRunnerError("R2_SEALED_OUTPUT_ROOT_INVALID")
    units, _, _ = load_sources(private_root, tree)
    output_root.mkdir(mode=0o700)
    details = output_root.stat()
    if details.st_mode & 0o777 != 0o700 or details.st_uid != os.getuid():
        raise SealedRunnerError("R2_SEALED_OUTPUT_ROOT_MODE_INVALID")
    rounds = []
    total_calls = 0
    for round_number in range(1, ROUND_COUNT + 1):
        aggregate, private_report = run_round(
            round_number, units, tree, config, transport=transport
        )
        if not write_private_json(output_root / f"round-{round_number}.private.v1.json", private_report):
            raise SealedRunnerError("R2_SEALED_ROUND_WRITE_FAILED", llm_called=True)
        rounds.append(aggregate)
        total_calls += aggregate["actual_call_count"]
    if total_calls > MAXIMUM_ACTUAL_CALL_COUNT:
        raise SealedRunnerError("R2_SEALED_TOTAL_CALL_LIMIT_EXCEEDED", llm_called=True)
    repeatable = rounds[0]["views"]["R2"] == rounds[1]["views"]["R2"]
    status = "PASS" if all(item["status"] == "PASS" for item in rounds) and repeatable else "FAIL"
    non_literal_pass = all(
        item["views"]["R2"]["V_REQUIREMENT_ONLY"]["non_literal_recall_at_20"] >= 3
        for item in rounds
    )
    if status == "PASS" and non_literal_pass:
        decision = "R2_SHADOW_CANDIDATE"
    elif status == "PASS":
        decision = "R2_LEXICAL_LEG_ONLY"
    elif any(item["contract_success_count"] != SCENARIO_COUNT for item in rounds):
        decision = "ROLE_EXTRACTION_NOT_STABLE"
    else:
        decision = "VECTOR_OR_HYBRID_REQUIRED"
    public_report = {
        "report_version": REPORT_VERSION,
        "status": status,
        "source_class": "CLEANROOM_SYNTHETIC",
        "fictional": True,
        "derived_from_real": False,
        "gold_eligible": False,
        "production_qualification": False,
        "decision": decision,
        "llm_called": total_calls > 0,
        "round_count": ROUND_COUNT,
        "scenario_count": SCENARIO_COUNT,
        "positive_count": POSITIVE_COUNT,
        "empty_count": EMPTY_COUNT,
        "actual_call_count": total_calls,
        "repeatable": repeatable,
        "rounds": rounds,
        "failure_codes": sorted(
            set(code for item in rounds for code in item["failure_codes"])
            | ({"R2_SEALED_REPEATABILITY_FAILURE"} if not repeatable else set())
        ),
    }
    private_final = {
        "schema_version": PRIVATE_FINAL_VERSION,
        "runner_version": RUNNER_VERSION,
        "data_commit": data_commit,
        "runner_commit": runner_commit,
        "aggregate": public_report,
    }
    if not write_private_json(output_root / "final.private.v1.json", private_final):
        raise SealedRunnerError("R2_SEALED_FINAL_WRITE_FAILED", llm_called=True)
    return public_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--execution-binding", type=Path, required=True)
    parser.add_argument("--data-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    execution_mode = parser.add_mutually_exclusive_group(required=True)
    execution_mode.add_argument("--preflight-only", action="store_true")
    execution_mode.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight_only:
        try:
            validate_runtime_binding(
                ROOT,
                args.private_root,
                args.execution_binding,
                args.data_commit,
                args.runner_commit,
            )
        except (OSError, SealedRunnerError, TypeError, ValueError) as error:
            code = getattr(error, "code", "R2_SEALED_PREFLIGHT_FAILED")
            print(json.dumps({"report_version": REPORT_VERSION, "status": "ERROR", "error_code": code, "llm_called": False}, sort_keys=True))
            return 2
        print(json.dumps({"report_version": REPORT_VERSION, "status": "PREFLIGHT_READY", "scenario_count": SCENARIO_COUNT, "round_count": ROUND_COUNT, "five_view_count": len(VIEW_ORDER), "llm_called": False}, sort_keys=True))
        return 0
    if args.output_root is None:
        print(json.dumps({"report_version": REPORT_VERSION, "status": "ERROR", "error_code": "R2_SEALED_OUTPUT_ROOT_REQUIRED", "llm_called": False}, sort_keys=True))
        return 2
    try:
        report = run_experiment(
            ROOT,
            args.private_root,
            args.output_root,
            args.execution_binding,
            args.data_commit,
            args.runner_commit,
            BailianConfig.from_env(),
        )
    except (BailianProviderError, CandidateRetrievalError, OSError, SealedRunnerError, TypeError, ValueError) as error:
        code = getattr(error, "code", "R2_SEALED_EXPERIMENT_FAILED")
        print(json.dumps({"report_version": REPORT_VERSION, "status": "ERROR", "error_code": code, "llm_called": bool(getattr(error, "llm_called", False))}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
