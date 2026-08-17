#!/usr/bin/env python3
"""Run the frozen Navigation Copilot evaluation through its Workbench API.

The CLI is intentionally inert until given a committed manifest and private
Oracle. It has no data-generation or threshold-tuning mode.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from treeguard import load_tree_export  # noqa: E402
from treeguard.ai_review import (  # noqa: E402
    BailianConfig,
    BailianNavigationSemanticProviderV2,
    BailianNavigationUnderstandingProvider,
    NAVIGATION_SEMANTIC_PROMPT_VERSION_V2,
    NAVIGATION_UNDERSTANDING_CLARIFICATION_PROMPT_VERSION,
    NAVIGATION_UNDERSTANDING_PROMPT_VERSION,
)
from treeguard.change_intent import IntentRequest  # noqa: E402
from treeguard.navigation_copilot import (  # noqa: E402
    NavigationInterpretation,
    build_navigation_candidate_set,
)
from treeguard.navigation_copilot_sealed_validation import (  # noqa: E402
    SealedCaseOracle,
    SealedCaseTrace,
    SealedEvaluationError,
    SealedEvaluationManifest,
    SealedScenario,
    StructuralProfile,
    TerminalExpectation,
    public_sealed_aggregate,
    public_sealed_diagnostic_aggregate,
    score_sealed_case,
    validate_sealed_plan,
)
from treeguard.json_utils import strict_json_loads  # noqa: E402
from treeguard.models import ImportResult  # noqa: E402
from treeguard.private_io import read_private_json, write_private_json  # noqa: E402
from treeguard.web import create_app  # noqa: E402
from treeguard.workbench import WorkbenchService, build_tree_reference_index  # noqa: E402
from treeguard.workbench_navigation_copilot import (  # noqa: E402
    WorkbenchNavigationCopilotService,
)
from treeguard.workbench_sidecar import (  # noqa: E402
    create_private_directory,
    ensure_private_directory,
    validate_private_directory,
)


UNEXPECTED_CLARIFICATION_ANSWER = "请仅依据原始需求继续，并保留不确定性。"
MAX_PUBLIC_INPUT_BYTES = 30_000_000
MAX_PRIVATE_INPUT_BYTES = 20_000_000
FUNCTION_PATHS = (
    "src/treeguard/navigation_copilot.py",
    "src/treeguard/ai_review.py",
    "src/treeguard/workbench_navigation_copilot.py",
    "src/treeguard/navigation_copilot_sealed_validation.py",
    "scripts/run_navigation_copilot_sealed_eval.py",
    "contracts/navigation-copilot-semantic-input.v2.schema.json",
    "contracts/navigation-copilot-semantic-projection.v2.schema.json",
    "contracts/navigation-copilot-semantic-output.v2.schema.json",
    "contracts/navigation-copilot-semantic-draft.v2.schema.json",
    "contracts/navigation-copilot-policy-decision.v2.schema.json",
    "contracts/navigation-copilot-sealed-evaluation-manifest.v2.schema.json",
    "contracts/navigation-copilot-sealed-scenario.v2.schema.json",
    "contracts/navigation-copilot-sealed-oracle.v2.schema.json",
    "contracts/navigation-copilot-sealed-trace.v2.schema.json",
    "contracts/navigation-copilot-sealed-observation.v2.schema.json",
    "contracts/navigation-copilot-sealed-aggregate.v2.schema.json",
    "contracts/navigation-copilot-sealed-diagnostic-aggregate.v2.schema.json",
)


class FrozenTreeRepository:
    """Small read-only repository adapter over one already validated tree."""

    def __init__(self, result: Any) -> None:
        if not result.is_valid or result.tree is None:
            raise ValueError("sealed runner requires one valid tree")
        self._result = result

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ) -> Any:
        tree = self._result.tree
        assert tree is not None
        if resource_id != tree.tree_id or (
            version is not None and version != tree.tree_version
        ):
            raise ValueError("sealed repository source does not match")
        return self._result

    def list_categories(self) -> tuple[Any, ...]:
        return ()

    def list_resources(self, category_id: str) -> tuple[Any, ...]:
        return ()

    def list_versions(self, resource_id: str) -> tuple[Any, ...]:
        return ()


class FrozenBailianProviderFactory:
    """Reuse one preflighted config for every logical stage in the run."""

    def __init__(self, config: BailianConfig) -> None:
        self._config = config

    def understanding_provider(self, mode: str, trace_sink=None):
        if mode != "BAILIAN_LIVE":
            raise ValueError("sealed runner forbids Provider fallback")
        return BailianNavigationUnderstandingProvider(
            self._config,
            trace_sink=trace_sink,
        )

    def semantic_provider(self, mode: str, trace_sink=None):
        if mode != "BAILIAN_LIVE":
            raise ValueError("sealed runner forbids Provider fallback")
        return BailianNavigationSemanticProviderV2(
            self._config,
            trace_sink=trace_sink,
        )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_public_json(path: Path, *, max_bytes: int) -> tuple[bytes, Any]:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise OSError("public sealed input must be an absolute regular file")
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise OSError("public sealed input exceeds its size limit")
    return raw, strict_json_loads(raw.decode("utf-8"))


def _read_private_raw_json(path: Path, *, max_bytes: int) -> tuple[bytes, Any]:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_mode & 0o077
            or file_stat.st_size > max_bytes
        ):
            raise OSError("private sealed input is not a bounded 0600 file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise OSError("private sealed input exceeds its size limit")
        return raw, strict_json_loads(raw.decode("utf-8"))
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _verify_function_commit(function_commit: str) -> None:
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", function_commit, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    unchanged = subprocess.run(
        ["git", "diff", "--quiet", function_commit, "--", *FUNCTION_PATHS],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0 or unchanged.returncode != 0:
        raise ValueError("running evaluation code does not match function_commit")


def _verify_data_commit(data_commit: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", data_commit, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError("sealed data_commit is not in the running history")


def _preflight_output_paths(sidecar_root: Path, output_root: Path) -> None:
    if sidecar_root == output_root:
        raise ValueError("sidecar and evaluation output roots must be distinct")
    ensure_private_directory(sidecar_root)
    validate_private_directory(output_root.parent)
    try:
        os.lstat(output_root)
    except FileNotFoundError:
        return
    except OSError:
        raise OSError("sealed output root cannot be inspected safely") from None
    raise OSError("sealed output root already exists")


def validate_input_collections(
    manifest: SealedEvaluationManifest,
    scenarios: tuple[SealedScenario, ...],
    oracles: tuple[SealedCaseOracle, ...],
    tree: Any,
) -> None:
    """Validate the cross-file handoff before an app or Provider is created."""

    for oracle in oracles:
        if (
            oracle.category == "CLARIFICATION"
            and oracle.acceptable_policy_statuses != ("NEED_EVIDENCE",)
        ):
            raise SealedEvaluationError(
                "SEALED_CLARIFICATION_POLICY_UNREACHABLE",
                "clarification Oracle conflicts with the two-call product path",
            )
    validate_sealed_plan(manifest, scenarios, oracles)
    if tree.snapshot_hash != scenarios[0].tree_digest:
        raise ValueError("sealed tree digest does not match scenarios")
    if any(item.tree_digest != tree.snapshot_hash for item in scenarios + oracles):
        raise ValueError("sealed scenario and Oracle tree sources do not align")
    references = build_tree_reference_index(tree)
    if any(
        scenario.proposed_parent_ref is not None
        and scenario.proposed_parent_ref not in references.node_id_by_ref
        for scenario in scenarios
    ):
        raise ValueError("sealed scenario parent reference is outside the frozen tree")
    node_ids = {node.node_id for node in tree.nodes}
    for oracle in oracles:
        if not set(oracle.acceptable_node_ids).issubset(node_ids) or not set(
            oracle.forbidden_node_ids
        ).issubset(node_ids):
            raise ValueError("sealed Oracle names a node outside the frozen tree")


def build_r0_candidate_node_ids(scenario: SealedScenario, tree: Any) -> tuple[str, ...]:
    """Compute the raw-requirement floor without a model or Oracle."""

    references = build_tree_reference_index(tree)
    request = IntentRequest.from_dict(
        {
            "schema_version": "intent-request.v1",
            "requirement_text": scenario.requirement_text,
            "proposed_parent_node_id": (
                references.node_id_by_ref[scenario.proposed_parent_ref]
                if scenario.proposed_parent_ref is not None
                else None
            ),
            "node_kind_hint": scenario.node_kind_hint,
            "value_type_hint": scenario.value_type_hint,
            "cardinality_hint": scenario.cardinality_hint,
        },
        tree,
    )
    interpretation = NavigationInterpretation.degraded(
        request,
        tree,
        degradation_code="SEALED_R0_RAW_REQUIREMENT",
    )
    candidates = build_navigation_candidate_set(request, interpretation, tree)
    return tuple(item.node_id for item in candidates.candidates)


async def _await_operation(
    client: httpx.AsyncClient,
    operation: dict[str, Any],
    *,
    poll_limit: int = 12_000,
) -> dict[str, Any]:
    if operation.get("status") in {"SUCCEEDED", "FAILED"}:
        return operation
    operation_ref = operation.get("operation_ref")
    if not isinstance(operation_ref, str):
        raise RuntimeError("Workbench operation reference is missing")
    for _ in range(poll_limit):
        response = await client.get(
            f"/api/v1/navigation-copilot/operations/{operation_ref}"
        )
        response.raise_for_status()
        current = response.json()
        if current.get("status") in {"SUCCEEDED", "FAILED"}:
            return current
        await asyncio.sleep(0.05)
    raise TimeoutError("Workbench operation did not reach a terminal state")


def _route(initially_clarified: bool, case_view: dict[str, Any]) -> str:
    if initially_clarified:
        return "CLARIFY"
    if case_view.get("candidate_status") == "NEED_EVIDENCE":
        return "LIMIT"
    return "PROCEED"


def _controlled_outcome(
    oracle: SealedCaseOracle,
    case_view: dict[str, Any],
    references: Any,
) -> tuple[dict[str, Any], TerminalExpectation]:
    if oracle.category == "WEAK_EVIDENCE":
        terminal = TerminalExpectation(
            action="EXIT",
            target_node_id=None,
            target_disposition="PRESENT_NOT_FOUND",
        )
        return (
            {
                "action": terminal.action,
                "selected_candidate_ref": None,
                "selected_node_ref": None,
                "rejection_disposition": None,
            },
            terminal,
        )
    candidates = tuple(case_view.get("candidates", ()))
    acceptable = set(oracle.acceptable_node_ids)
    for candidate in candidates:
        node_id = references.node_id_by_ref[candidate["node_ref"]]
        if node_id in acceptable:
            terminal = TerminalExpectation(
                action="SELECT_CANDIDATE",
                target_node_id=node_id,
                target_disposition="FOUND_TOP8",
            )
            return (
                {
                    "action": terminal.action,
                    "selected_candidate_ref": candidate["candidate_ref"],
                    "selected_node_ref": candidate["node_ref"],
                    "rejection_disposition": None,
                },
                terminal,
            )
    if oracle.target_status == "TARGET_PRESENT":
        target_id = oracle.acceptable_node_ids[0]
        terminal = TerminalExpectation(
            action="SELECT_OUTSIDE_CANDIDATE",
            target_node_id=target_id,
            target_disposition="FOUND_OUTSIDE",
        )
        return (
            {
                "action": terminal.action,
                "selected_candidate_ref": None,
                "selected_node_ref": references.ref_by_node_id[target_id],
                "rejection_disposition": None,
            },
            terminal,
        )
    terminal = TerminalExpectation(
        action="REJECT_ALL",
        target_node_id=None,
        target_disposition="ABSENT",
    )
    return (
        {
            "action": terminal.action,
            "selected_candidate_ref": None,
            "selected_node_ref": None,
            "rejection_disposition": "ABSENT",
        },
        terminal,
    )


def _sidecars_complete(
    sidecar_root: Path,
    case_ref: str,
    *,
    initially_clarified: bool,
    semantic_status: str,
) -> bool:
    names = {
        "01-intent-request.json",
        "02-interpretation.json",
        "05-candidate-set.json",
        "08-policy-decision.json",
        "09-outcome.json",
    }
    directory = sidecar_root / case_ref
    if not all((directory / name).is_file() for name in names):
        return False
    projection = directory / "06-semantic-projection.json"
    draft = directory / "07-semantic-draft.json"
    if initially_clarified:
        return (
            semantic_status == "SKIPPED_CLARIFICATION_PATH"
            and (directory / "03-clarification-answer.json").is_file()
            and (directory / "04-clarification-round.json").is_file()
            and projection.is_file()
            and not draft.exists()
        )
    if semantic_status == "SUCCEEDED":
        return projection.is_file() and draft.is_file()
    if semantic_status == "DEGRADED":
        return projection.is_file() and not draft.exists()
    if semantic_status == "NOT_APPLICABLE":
        return not projection.exists() and not draft.exists()
    return False


def _infer_failure_stage(
    sidecar_root: Path,
    case_ref: str,
    *,
    logical_model_stage_count: int,
) -> str:
    directory = sidecar_root / case_ref
    if not (directory / "02-interpretation.json").is_file():
        return "UNDERSTANDING"
    if not (directory / "05-candidate-set.json").is_file():
        return (
            "SEMANTIC"
            if logical_model_stage_count >= 2
            else "RETRIEVAL"
        )
    if not (directory / "08-policy-decision.json").is_file():
        if (directory / "06-semantic-projection.json").is_file() and not (
            directory / "07-semantic-draft.json"
        ).is_file():
            return "SEMANTIC"
        return "POLICY"
    return "END_TO_END"


def _validate_model_trace_binding(
    items: list[dict[str, Any]],
    manifest: SealedEvaluationManifest,
) -> None:
    prompt_by_stage = {
        "CHANGE_UNDERSTANDING": manifest.understanding_prompt_version,
        "CHANGE_UNDERSTANDING_CLARIFICATION": manifest.clarification_prompt_version,
        "SEMANTIC_RELATION": manifest.semantic_prompt_version,
    }
    if not items:
        raise ValueError("sealed live run requires private model traces")
    if any(
        item.get("stage") not in prompt_by_stage
        or item.get("provider") != "BAILIAN_OPENAI_COMPATIBLE"
        or item.get("model") != manifest.model_name
        or item.get("prompt_version") != prompt_by_stage.get(item.get("stage"))
        or item.get("thinking_status") != "DISABLED"
        for item in items
    ):
        raise ValueError("sealed model trace does not match the frozen manifest")


async def execute_case_via_workbench_api(
    client: httpx.AsyncClient,
    *,
    scenario: SealedScenario,
    oracle: SealedCaseOracle,
    tree: Any,
    sidecar_root: Path,
    round_index: int,
    expected_manifest: SealedEvaluationManifest | None = None,
) -> SealedCaseTrace:
    """Execute one case through HTTP, then normalize its completed sidecars."""

    r0_candidates = build_r0_candidate_node_ids(scenario, tree)
    references = build_tree_reference_index(tree)
    payload = {
        "resource_id": tree.tree_id,
        "version": tree.tree_version,
        **scenario.model_request_dict(),
        "model_mode": "BAILIAN_LIVE",
        "external_data_approved": True,
    }
    created = await client.post("/api/v1/navigation-copilot/cases", json=payload)
    created.raise_for_status()
    operation = await _await_operation(client, created.json())
    case_ref = operation["case_ref"]
    case_response = await client.get(f"/api/v1/navigation-copilot/cases/{case_ref}")
    case_response.raise_for_status()
    case_view = case_response.json()
    initially_clarified = case_view["status"] == "NEEDS_CLARIFICATION"
    if initially_clarified:
        answer = (
            scenario.frozen_clarification_answer
            or UNEXPECTED_CLARIFICATION_ANSWER
        )
        clarified = await client.post(
            f"/api/v1/navigation-copilot/cases/{case_ref}/clarification",
            json={"answer_text": answer},
        )
        if clarified.is_error:
            raise RuntimeError(
                f"clarification API rejected the frozen answer: {clarified.text}"
            )
        operation = await _await_operation(client, clarified.json())
        case_response = await client.get(
            f"/api/v1/navigation-copilot/cases/{case_ref}"
        )
        case_response.raise_for_status()
        case_view = case_response.json()
    if operation.get("status") != "SUCCEEDED" or case_view.get("status") != "AWAITING_OUTCOME":
        code = operation.get("error_code") or "SEALED_WORKBENCH_OPERATION_FAILED"
        failed_trace_response = await client.get(
            f"/api/v1/navigation-copilot/cases/{case_ref}/model-traces"
        )
        failed_trace_response.raise_for_status()
        failed_model_traces = failed_trace_response.json()["items"]
        if expected_manifest is not None and failed_model_traces:
            _validate_model_trace_binding(failed_model_traces, expected_manifest)
        return SealedCaseTrace.create(
            scenario_ref=scenario.scenario_ref,
            round_index=round_index,
            tree_digest=scenario.tree_digest,
            request_digest=scenario.request_digest,
            provider_mode="BAILIAN_LIVE",
            run_status="CONTRACT_FAILED",
            failure_code=code,
            failure_stage=_infer_failure_stage(
                sidecar_root,
                case_ref,
                logical_model_stage_count=case_view.get("model_call_count", 0),
            ),
            logical_model_stage_count=case_view.get("model_call_count", 0),
            wire_attempt_count=len(failed_model_traces),
            sidecar_complete=False,
            interpretation_status=None,
            observed_route=None,
            observed_profile=None,
            r0_candidate_node_ids=r0_candidates,
            c1_candidate_node_ids=(),
            policy_status=None,
            semantic_status=None,
            highlighted_node_id=None,
            outcome=None,
        )
    outcome_payload, terminal = _controlled_outcome(oracle, case_view, references)
    completed = await client.post(
        f"/api/v1/navigation-copilot/cases/{case_ref}/outcome",
        json=outcome_payload,
    )
    completed.raise_for_status()
    final_view = completed.json()
    candidate_payload = read_private_json(
        sidecar_root / case_ref / "05-candidate-set.json",
        max_bytes=2_000_000,
    )
    c1_candidates = tuple(
        item["node_id"] for item in candidate_payload["candidates"]
    )
    policy_payload = read_private_json(
        sidecar_root / case_ref / "08-policy-decision.json",
        max_bytes=1_000_000,
    )
    semantic_status = policy_payload.get("semantic_status")
    if not isinstance(semantic_status, str):
        raise ValueError("sealed policy sidecar lacks semantic status")
    highlighted_node_id = None
    highlighted_ref = final_view.get("highlighted_candidate_ref")
    if highlighted_ref is not None:
        highlighted_node_id = next(
            references.node_id_by_ref[item["node_ref"]]
            for item in final_view["candidates"]
            if item["candidate_ref"] == highlighted_ref
        )
    interpretation = final_view["interpretation"]
    trace_response = await client.get(
        f"/api/v1/navigation-copilot/cases/{case_ref}/model-traces"
    )
    trace_response.raise_for_status()
    model_trace_items = trace_response.json()["items"]
    if expected_manifest is not None:
        _validate_model_trace_binding(model_trace_items, expected_manifest)
    wire_attempt_count = len(model_trace_items)
    return SealedCaseTrace.create(
        scenario_ref=scenario.scenario_ref,
        round_index=round_index,
        tree_digest=scenario.tree_digest,
        request_digest=scenario.request_digest,
        provider_mode="BAILIAN_LIVE",
        run_status="COMPLETE",
        failure_code=None,
        failure_stage=None,
        logical_model_stage_count=final_view["model_call_count"],
        wire_attempt_count=wire_attempt_count,
        sidecar_complete=_sidecars_complete(
            sidecar_root,
            case_ref,
            initially_clarified=initially_clarified,
            semantic_status=semantic_status,
        ),
        interpretation_status=interpretation["status"],
        observed_route=_route(initially_clarified, final_view),
        observed_profile=StructuralProfile(
            interpretation["node_kind"],
            interpretation["value_type"],
            interpretation["cardinality"],
        ),
        r0_candidate_node_ids=r0_candidates,
        c1_candidate_node_ids=c1_candidates,
        policy_status=final_view["candidate_status"],
        semantic_status=semantic_status,
        highlighted_node_id=highlighted_node_id,
        outcome=terminal,
    )


async def execute_frozen_run(
    *,
    manifest: SealedEvaluationManifest,
    scenarios: tuple[SealedScenario, ...],
    oracles: tuple[SealedCaseOracle, ...],
    tree: Any,
    sidecar_root: Path,
    output_root: Path,
    provider_factory: Any,
) -> dict[str, Any]:
    validate_input_collections(manifest, scenarios, oracles, tree)
    ensure_private_directory(sidecar_root)
    create_private_directory(output_root)
    repository = FrozenTreeRepository(
        ImportResult(
            tree=tree,
            issues=(),
            observed_node_count=len(tree.nodes),
            observed_value_count=sum(node.has_value_envelope for node in tree.nodes),
            source_format=tree.source_format,
        )
    )
    service = WorkbenchNavigationCopilotService(
        repository=repository,
        sidecar_root=sidecar_root,
        provider_factory=provider_factory,
        diagnostics_enabled=True,
        semantic_contract_version="v2",
    )
    app = create_app(
        WorkbenchService(repository),
        navigation_copilot_service=service,
    )
    oracle_by_ref = {item.scenario_ref: item for item in oracles}
    scenario_by_ref = {item.scenario_ref: item for item in scenarios}
    observations = []
    traces = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://sealed-evaluation.invalid",
    ) as client:
        schedule = tuple((ref, 1) for ref in manifest.scenario_refs) + tuple(
            (ref, round_index)
            for round_index in (2, 3)
            for ref in manifest.repeat_scenario_refs
        )
        for ref, round_index in schedule:
            trace = await execute_case_via_workbench_api(
                client,
                scenario=scenario_by_ref[ref],
                oracle=oracle_by_ref[ref],
                tree=tree,
                sidecar_root=sidecar_root,
                round_index=round_index,
                expected_manifest=manifest,
            )
            observation = score_sealed_case(oracle_by_ref[ref], trace)
            prefix = f"{ref}.r{round_index}"
            if not write_private_json(output_root / f"{prefix}.trace.json", trace.to_dict()):
                raise OSError("sealed trace could not be published")
            if not write_private_json(
                output_root / f"{prefix}.observation.json",
                observation.to_dict(),
            ):
                raise OSError("sealed observation could not be published")
            observations.append(observation)
            traces.append(trace)
    run_integrity_valid = (
        len(traces) == 80
        and sum(item.logical_model_stage_count for item in traces)
        <= 160
        and sum(item.wire_attempt_count for item in traces)
        <= manifest.wire_attempt_limit
        and all(item.provider_mode == "BAILIAN_LIVE" for item in traces)
        and all(
            item.sidecar_complete
            for item in traces
            if item.run_status == "COMPLETE"
        )
    )
    aggregate = public_sealed_aggregate(
        manifest,
        tuple(observations),
        run_integrity_valid=run_integrity_valid,
    )
    if not write_private_json(output_root / "aggregate.json", aggregate):
        raise OSError("sealed aggregate could not be published")
    diagnostic = public_sealed_diagnostic_aggregate(
        manifest,
        tuple(observations),
    )
    if not write_private_json(
        output_root / "diagnostic-aggregate.json",
        diagnostic,
    ):
        raise OSError("sealed diagnostic aggregate could not be published")
    return aggregate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--sidecar-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not all(
        path.is_absolute()
        for path in (
            args.manifest,
            args.tree,
            args.scenarios,
            args.oracle,
            args.sidecar_root,
            args.output_root,
        )
    ):
        raise SystemExit("all sealed evaluation paths must be absolute")
    _, manifest_payload = _read_private_raw_json(
        args.manifest, max_bytes=1_000_000
    )
    manifest = SealedEvaluationManifest.from_dict(manifest_payload)
    tree_raw, _ = _read_public_json(args.tree, max_bytes=MAX_PUBLIC_INPUT_BYTES)
    scenarios_raw, scenarios_payload = _read_public_json(
        args.scenarios, max_bytes=MAX_PUBLIC_INPUT_BYTES
    )
    oracle_raw, oracle_payload = _read_private_raw_json(
        args.oracle, max_bytes=MAX_PRIVATE_INPUT_BYTES
    )
    if (
        _sha256(tree_raw) != manifest.tree_sha256
        or _sha256(scenarios_raw) != manifest.scenarios_sha256
        or _sha256(oracle_raw) != manifest.oracle_sha256
    ):
        raise SystemExit("sealed evaluation byte binding failed")
    if not isinstance(scenarios_payload, list) or not isinstance(oracle_payload, list):
        raise SystemExit("sealed scenario and Oracle files must be arrays")
    scenarios = tuple(SealedScenario.from_dict(item) for item in scenarios_payload)
    oracles = tuple(SealedCaseOracle.from_dict(item) for item in oracle_payload)
    result = load_tree_export(args.tree)
    if not result.is_valid or result.tree is None:
        raise SystemExit("sealed tree did not pass the adapter")
    try:
        validate_input_collections(manifest, scenarios, oracles, result.tree)
    except SealedEvaluationError as exc:
        raise SystemExit(exc.code) from None
    _verify_function_commit(manifest.function_commit)
    _verify_data_commit(manifest.data_commit)
    if not args.execute:
        print("SEALED_EVALUATION_PREFLIGHT_READY")
        return 0
    _preflight_output_paths(args.sidecar_root, args.output_root)
    config = BailianConfig.from_env()
    if (
        config.model != manifest.model_name
        or manifest.understanding_prompt_version
        != NAVIGATION_UNDERSTANDING_PROMPT_VERSION
        or manifest.clarification_prompt_version
        != NAVIGATION_UNDERSTANDING_CLARIFICATION_PROMPT_VERSION
        or manifest.semantic_prompt_version
        != NAVIGATION_SEMANTIC_PROMPT_VERSION_V2
    ):
        raise SystemExit("sealed model or Prompt binding failed")
    aggregate = asyncio.run(
        execute_frozen_run(
            manifest=manifest,
            scenarios=scenarios,
            oracles=oracles,
            tree=result.tree,
            sidecar_root=args.sidecar_root,
            output_root=args.output_root,
            provider_factory=FrozenBailianProviderFactory(config),
        )
    )
    print(aggregate["qualification_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
