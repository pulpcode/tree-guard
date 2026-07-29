"""One-command fictional demonstration of the governance sidecar workflow."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import stat
from collections.abc import Sequence
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from treeguard.governance_cli import main as governance_main
from treeguard.json_utils import StrictJSONError, strict_json_loads
from treeguard.private_io import read_private_json, write_private_json


_MAX_ARTIFACT_BYTES = 16_000_000
_RECORDED_AT = "2030-01-02T03:04:05Z"
_REVIEWER_REF = "fictional-demo-reviewer"
_STEP_ORDER = (
    "DRAFT",
    "CONFIRM",
    "SEARCH",
    "RECOMMEND",
    "REVIEW_RECOMMENDATION",
    "REPLAY_RECOMMENDATION",
)
_STEP_STATUSES = {
    "DRAFT": {"READY_FOR_HUMAN_REVIEW", "NEEDS_CLARIFICATION"},
    "CONFIRM": {"CONFIRMED_FOR_RETRIEVAL"},
    "SEARCH": {
        "CANDIDATES_READY",
        "NO_CANDIDATES",
        "INSUFFICIENT_SIGNAL",
    },
    "RECOMMEND": {"READY_FOR_HUMAN_REVIEW"},
    "REVIEW_RECOMMENDATION": {"CONFIRMED", "REJECTED"},
    "REPLAY_RECOMMENDATION": {"CONFIRMED", "REJECTED"},
}
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class DemoError(RuntimeError):
    """The demonstration failed at a stable, non-sensitive boundary."""

    def __init__(
        self,
        code: str,
        *,
        failed_step: str,
        exit_code: int = 2,
        ai_called: bool = False,
    ) -> None:
        self.code = code
        self.failed_step = failed_step
        self.exit_code = exit_code
        self.ai_called = ai_called
        super().__init__(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard-governance-demo")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new private directory for fictional demonstration artifacts",
    )
    parser.add_argument(
        "--review-decision",
        choices=("confirm", "reject"),
        required=True,
        help="explicit fictional reviewer decision for the AI recommendation",
    )
    parser.add_argument(
        "--mode",
        choices=("offline", "simulator-live", "bailian-live"),
        default="offline",
    )
    parser.add_argument(
        "--simulator-base-url",
        help="loopback OpenAI-compatible base URL ending in /v1",
    )
    parser.add_argument(
        "--external-data-approved",
        action="store_true",
        help="confirm live fictional inputs are approved for external transfer",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (
        args.mode == "bailian-live"
        and not args.external_data_approved
    ):
        _print_error(
            "EXTERNAL_DATA_APPROVAL_REQUIRED",
            failed_step="PREFLIGHT",
        )
        return 2
    if (
        args.mode == "simulator-live"
        and args.simulator_base_url is None
    ):
        _print_error(
            "SIMULATOR_MODEL_BASE_URL_REQUIRED",
            failed_step="PREFLIGHT",
        )
        return 2
    if (
        args.mode != "simulator-live"
        and args.simulator_base_url is not None
    ):
        _print_error(
            "SIMULATOR_MODEL_BASE_URL_UNEXPECTED",
            failed_step="PREFLIGHT",
        )
        return 2

    try:
        _create_private_run_directory(args.output_dir)
        report = _run_demo(
            args.output_dir,
            mode=args.mode,
            review_decision=args.review_decision,
            external_data_approved=args.external_data_approved,
            simulator_base_url=args.simulator_base_url,
        )
        completion_file = args.output_dir / "12-demo-completion.json"
        if not write_private_json(completion_file, report):
            raise DemoError(
                "DEMO_COMPLETION_WRITE_FAILED",
                failed_step="COMPLETION",
            )
    except DemoError as exc:
        _print_error(
            exc.code,
            failed_step=exc.failed_step,
            ai_called=exc.ai_called,
        )
        return exc.exit_code
    except (
        OSError,
        StrictJSONError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ):
        _print_error(
            "DEMO_INTERNAL_ARTIFACT_INVALID",
            failed_step="ORCHESTRATION",
        )
        return 2

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def _run_demo(
    directory: Path,
    *,
    mode: str,
    review_decision: str,
    external_data_approved: bool,
    simulator_base_url: str | None,
) -> dict[str, Any]:
    paths = {
        "tree": directory / "01-fictional-tree.json",
        "request": directory / "02-intent-request.json",
        "intent_model": directory / "03-intent-model-output.json",
        "intent_draft": directory / "04-intent-draft.json",
        "intent_action": directory / "05-intent-review-action.json",
        "confirmation": directory / "06-intent-confirmation.json",
        "candidates": directory / "07-candidate-set.json",
        "semantic_model": directory / "08-semantic-model-output.json",
        "recommendation_draft": directory / "09-recommendation-draft.json",
        "recommendation_action": (
            directory / "10-recommendation-review-action.json"
        ),
        "recommendation_record": directory / "11-recommendation-record.json",
    }
    _write_input(paths["tree"], _fictional_tree())
    _write_input(paths["request"], _fictional_request())
    if mode == "offline":
        _write_input(paths["intent_model"], _fictional_intent_model_output())

    step_reports: dict[str, dict[str, Any]] = {}
    draft_arguments = [
        "draft",
        str(paths["tree"]),
        str(paths["request"]),
    ]
    if mode == "offline":
        draft_arguments.extend(
            ["--model-output-file", str(paths["intent_model"])]
        )
    elif mode == "bailian-live":
        draft_arguments.extend(["--live", "--external-data-approved"])
    else:
        assert simulator_base_url is not None
        draft_arguments.extend(
            ["--simulator-base-url", simulator_base_url]
        )
    draft_arguments.extend(
        ["--internal-output", str(paths["intent_draft"])]
    )
    step_reports["DRAFT"] = _run_step("DRAFT", draft_arguments)

    intent_draft = _read_artifact(paths["intent_draft"])
    if step_reports["DRAFT"]["status"] == "NEEDS_CLARIFICATION":
        raise DemoError(
            "INTENT_CLARIFICATION_REQUIRED",
            failed_step="CLARIFY",
            ai_called=(
                step_reports["DRAFT"].get("ai", {}).get("called") is True
            ),
        )
    intent = intent_draft.get("intent")
    draft_hash = intent_draft.get("draft_hash")
    if not isinstance(intent, dict) or not isinstance(draft_hash, str):
        raise DemoError(
            "DEMO_INTERNAL_ARTIFACT_INVALID",
            failed_step="CONFIRM",
        )
    _write_input(
        paths["intent_action"],
        {
            "schema_version": "intent-review-action.v1",
            "expected_draft_hash": draft_hash,
            "decision": "CONFIRM_FOR_RETRIEVAL",
            "reviewer_ref": _REVIEWER_REF,
            "recorded_at": _RECORDED_AT,
            "confirmed_intent": intent,
        },
    )
    confirmation_sources = [
        str(paths["tree"]),
        str(paths["request"]),
        str(paths["intent_draft"]),
        str(paths["intent_action"]),
    ]
    step_reports["CONFIRM"] = _run_step(
        "CONFIRM",
        [
            "confirm",
            *confirmation_sources,
            "--internal-output",
            str(paths["confirmation"]),
        ],
    )
    semantic_sources = [
        *confirmation_sources,
        str(paths["confirmation"]),
        str(paths["candidates"]),
    ]
    step_reports["SEARCH"] = _run_step(
        "SEARCH",
        [
            "search",
            *confirmation_sources,
            str(paths["confirmation"]),
            "--internal-output",
            str(paths["candidates"]),
        ],
    )

    if mode == "offline":
        _write_input(
            paths["semantic_model"],
            _fictional_semantic_model_output(paths["candidates"]),
        )
    recommend_arguments = ["recommend", *semantic_sources]
    if mode == "offline":
        recommend_arguments.extend(
            ["--model-output-file", str(paths["semantic_model"])]
        )
    elif mode == "bailian-live":
        if not external_data_approved:
            raise DemoError(
                "EXTERNAL_DATA_APPROVAL_REQUIRED",
                failed_step="RECOMMEND",
            )
        recommend_arguments.extend(["--live", "--external-data-approved"])
    else:
        assert simulator_base_url is not None
        recommend_arguments.extend(
            ["--simulator-base-url", simulator_base_url]
        )
    recommend_arguments.extend(
        ["--internal-output", str(paths["recommendation_draft"])]
    )
    step_reports["RECOMMEND"] = _run_step(
        "RECOMMEND",
        recommend_arguments,
    )

    recommendation_draft = _read_artifact(paths["recommendation_draft"])
    recommendation_draft_hash = recommendation_draft.get("draft_hash")
    if not isinstance(recommendation_draft_hash, str):
        raise DemoError(
            "DEMO_INTERNAL_ARTIFACT_INVALID",
            failed_step="REVIEW_RECOMMENDATION",
        )
    recommendation_decision = {
        "confirm": "CONFIRM_RECOMMENDATION",
        "reject": "REJECT_RECOMMENDATION",
    }[review_decision]
    _write_input(
        paths["recommendation_action"],
        {
            "schema_version": "recommendation-review-action.v1",
            "identity_status": "UNVERIFIED_FILE_ASSERTION",
            "expected_draft_hash": recommendation_draft_hash,
            "decision": recommendation_decision,
            "reviewer_ref": _REVIEWER_REF,
            "recorded_at": _RECORDED_AT,
            "reviewer_reasoning": (
                "This is an explicit fictional demonstration decision."
            ),
            "revised_recommendation": None,
        },
    )
    recommendation_sources = [
        *semantic_sources,
        str(paths["recommendation_draft"]),
        str(paths["recommendation_action"]),
    ]
    step_reports["REVIEW_RECOMMENDATION"] = _run_step(
        "REVIEW_RECOMMENDATION",
        [
            "review-recommendation",
            *recommendation_sources,
            "--internal-output",
            str(paths["recommendation_record"]),
        ],
    )
    step_reports["REPLAY_RECOMMENDATION"] = _run_step(
        "REPLAY_RECOMMENDATION",
        [
            "replay-recommendation",
            *recommendation_sources,
            str(paths["recommendation_record"]),
        ],
    )
    return _success_report(
        mode=mode,
        review_decision=review_decision,
        step_reports=step_reports,
    )


def _create_private_run_directory(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
        created = os.lstat(path)
    except OSError:
        raise DemoError(
            "DEMO_OUTPUT_DIRECTORY_INVALID",
            failed_step="PREFLIGHT",
        ) from None
    if not stat.S_ISDIR(created.st_mode) or created.st_mode & 0o077:
        raise DemoError(
            "DEMO_OUTPUT_DIRECTORY_INVALID",
            failed_step="PREFLIGHT",
        )


def _run_step(step: str, arguments: list[str]) -> dict[str, Any]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = governance_main(arguments)
    try:
        report = strict_json_loads(stdout.getvalue())
    except (StrictJSONError, TypeError, UnicodeError, ValueError):
        raise DemoError(
            "DEMO_STEP_REPORT_INVALID",
            failed_step=step,
            exit_code=2,
        ) from None
    if not isinstance(report, dict):
        raise DemoError(
            "DEMO_STEP_REPORT_INVALID",
            failed_step=step,
            exit_code=2,
        )
    if exit_code != 0:
        code = report.get("error_code")
        if (
            not isinstance(code, str)
            or _ERROR_CODE.fullmatch(code) is None
        ):
            code = "DEMO_STEP_FAILED"
        ai = report.get("ai")
        ai_called = isinstance(ai, dict) and ai.get("called") is True
        raise DemoError(
            code,
            failed_step=step,
            exit_code=3 if exit_code == 3 else 2,
            ai_called=ai_called,
        )
    operation = report.get("operation")
    status = report.get("status")
    if (
        operation != step
        or not isinstance(status, str)
        or status not in _STEP_STATUSES[step]
    ):
        raise DemoError(
            "DEMO_STEP_REPORT_INVALID",
            failed_step=step,
        )
    return report


def _read_artifact(path: Path) -> dict[str, Any]:
    payload = read_private_json(path, max_bytes=_MAX_ARTIFACT_BYTES)
    if not isinstance(payload, dict):
        raise DemoError(
            "DEMO_INTERNAL_ARTIFACT_INVALID",
            failed_step="ORCHESTRATION",
        )
    return payload


def _write_input(path: Path, payload: dict[str, Any]) -> None:
    if not write_private_json(path, payload):
        raise DemoError(
            "DEMO_INPUT_WRITE_FAILED",
            failed_step="ORCHESTRATION",
        )


def _success_report(
    *,
    mode: str,
    review_decision: str,
    step_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    statuses = {
        step.lower(): step_reports[step]["status"] for step in _STEP_ORDER
    }
    final_status = statuses["replay_recommendation"]
    expected_status = (
        "CONFIRMED" if review_decision == "confirm" else "REJECTED"
    )
    if (
        statuses["review_recommendation"] != final_status
        or final_status != expected_status
    ):
        raise DemoError(
            "DEMO_FINAL_STATE_INVALID",
            failed_step="COMPLETION",
        )
    candidate_count = step_reports["SEARCH"].get("candidate_count")
    if (
        not isinstance(candidate_count, int)
        or isinstance(candidate_count, bool)
        or candidate_count < 0
    ):
        raise DemoError(
            "DEMO_STEP_REPORT_INVALID",
            failed_step="SEARCH",
        )
    return {
        "report_version": "governance-demo-aggregate.v1",
        "valid": True,
        "completed": True,
        "fictional_demo": True,
        "mode": mode.upper().replace("-", "_"),
        "review_decision": review_decision.upper(),
        "record_status": final_status,
        "step_count": len(_STEP_ORDER),
        "candidate_count": candidate_count,
        "steps": statuses,
        "semantic_approval": False,
        "patch_eligible": False,
        "gold_eligible": False,
        "ai": {
            "intent_called": (
                step_reports["DRAFT"].get("ai", {}).get("called") is True
            ),
            "semantic_called": (
                step_reports["RECOMMEND"].get("ai", {}).get("called") is True
            ),
        },
    }


def _print_error(
    code: str,
    *,
    failed_step: str,
    ai_called: bool = False,
) -> None:
    clarification_required = code == "INTENT_CLARIFICATION_REQUIRED"
    print(
        json.dumps(
            {
                "report_version": "governance-demo-aggregate.v1",
                "valid": False,
                "completed": False,
                "fictional_demo": True,
                "status": (
                    "NEEDS_CLARIFICATION"
                    if clarification_required
                    else "REJECTED"
                ),
                "failed_step": failed_step,
                "error_code": code,
                "semantic_approval": False,
                "patch_eligible": False,
                "gold_eligible": False,
                "ai": {
                    "called": ai_called,
                    "status": (
                        "COMPLETED"
                        if clarification_required and ai_called
                        else "ABSTAIN" if ai_called else "NOT_CALLED"
                    ),
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _fictional_tree() -> dict[str, Any]:
    return {
        "metadata": {
            "id": "fictional-version-record",
            "map_id": "fictional-museum-tree",
            "map_type": "resource",
            "map_name": "虚构博物馆藏品目录",
            "version": "V1",
            "category_id": "fictional-category",
            "concurrent_version": 1,
        },
        "map_topology": {
            "MUSEUM": {
                "metadata": {
                    "node_id": "fictional-museum-root",
                    "node_type": "concept",
                    "node_name": "虚构博物馆",
                    "node_label": "MUSEUM",
                    "node_label_route": "MUSEUM",
                    "node_order": 1,
                },
                "subnodes": {
                    "CATALOG": {
                        "metadata": {
                            "node_id": "fictional-catalog",
                            "parent_node_id": "fictional-museum-root",
                            "node_type": "concept",
                            "node_name": "藏品目录",
                            "node_label": "CATALOG",
                            "node_label_route": "MUSEUM/-/CATALOG",
                            "node_order": 1,
                        },
                        "subnodes": {
                            "DIMENSIONS": {
                                "metadata": {
                                    "node_id": "fictional-dimensions",
                                    "parent_node_id": "fictional-catalog",
                                    "node_type": "property",
                                    "node_name": "展品尺寸",
                                    "node_label": "DIMENSIONS",
                                    "node_label_route": (
                                        "MUSEUM/-/CATALOG/-/DIMENSIONS"
                                    ),
                                    "node_order": 1,
                                    "value_type": "class",
                                    "is_list": False,
                                    "value_constraints": {
                                        "raw_constraints": {}
                                    },
                                },
                                "subnodes": {
                                    "HEIGHT": {
                                        "metadata": {
                                            "node_id": "fictional-height",
                                            "parent_node_id": (
                                                "fictional-dimensions"
                                            ),
                                            "node_type": "property",
                                            "node_name": "陈列高度",
                                            "node_label": "HEIGHT",
                                            "node_label_route": (
                                                "MUSEUM/-/CATALOG/-/"
                                                "DIMENSIONS/-/HEIGHT"
                                            ),
                                            "node_order": 1,
                                            "value_type": "float",
                                            "is_list": False,
                                            "value_constraints": {
                                                "raw_constraints": {}
                                            },
                                        }
                                    },
                                    "WIDTH": {
                                        "metadata": {
                                            "node_id": "fictional-width",
                                            "parent_node_id": (
                                                "fictional-dimensions"
                                            ),
                                            "node_type": "property",
                                            "node_name": "陈列宽度",
                                            "node_label": "WIDTH",
                                            "node_label_route": (
                                                "MUSEUM/-/CATALOG/-/"
                                                "DIMENSIONS/-/WIDTH"
                                            ),
                                            "node_order": 2,
                                            "value_type": "float",
                                            "is_list": False,
                                            "value_constraints": {
                                                "raw_constraints": {}
                                            },
                                        }
                                    },
                                },
                            }
                        },
                    }
                },
            }
        },
    }


def _fictional_request() -> dict[str, Any]:
    return {
        "schema_version": "intent-request.v1",
        "requirement_text": (
            "为虚构博物馆藏品目录记录陈列高度。"
        ),
        "proposed_parent_node_id": "fictional-dimensions",
        "node_kind_hint": "PROPERTY",
        "value_type_hint": "float",
        "cardinality_hint": "SINGLE",
    }


def _fictional_intent_model_output() -> dict[str, Any]:
    return {
        "schema_version": "change-intent-model-output.v1",
        "subject": "陈列高度",
        "role": "藏品尺寸测量",
        "scenario": "虚构展览",
        "lifecycle": "目录使用期",
        "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
        "node_kind": "PROPERTY",
        "value_type": "float",
        "cardinality": "SINGLE",
        "confirmed_facts": ["需要记录完全虚构的陈列高度。"],
        "assumptions": [],
        "evidence_gaps": [],
        "clarification_question": None,
    }


def _fictional_semantic_model_output(
    candidate_path: Path,
) -> dict[str, Any]:
    candidate_set = _read_artifact(candidate_path)
    candidates = candidate_set.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise DemoError(
            "DEMO_OFFLINE_CANDIDATES_INVALID",
            failed_step="RECOMMEND",
        )
    assessments = [
        {
            "candidate_ref": f"C{index:03d}",
            "relation": (
                "SEMANTICALLY_EQUIVALENT"
                if index == 1
                else "NOT_EQUIVALENT"
            ),
            "reason": "已比较一个虚构候选。",
        }
        for index, _ in enumerate(candidates[:8], start=1)
    ]
    return {
        "schema_version": "semantic-recommendation-model-output.v1",
        "candidate_assessments": assessments,
        "recommended_action": "USE_EXISTING_NODE",
        "selected_candidate_ref": "C001",
        "rationale": "一个虚构候选与已确认意图匹配。",
        "uncertainties": [],
        "evidence_gaps": [],
        "clarification_question": None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
