"""Codex/Silver request-only role annotations for the exposed M5 calibration."""

from __future__ import annotations

from typing import Any

from treeguard.change_intent import IntentRequest
from treeguard.retrieval import CandidateRetrievalError
from treeguard.retrieval_roles import (
    RetrievalRoleEvidence,
    build_retrieval_role_evidence,
)


ANNOTATION_POLICY = "treeguard.fire-m5-codex-silver-role-spans.v1"

_ANNOTATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "M5S001": (("TARGET", "警戒组织依赖条件"),),
    "M5S002": (("TARGET", "作业区域空间范围"),),
    "M5S003": (("TARGET", "季节影响时间窗口"),),
    "M5S004": (("TARGET", "水源保障关联资源"),),
    "M5S005": (("TARGET", "复测确认触发条件"),),
    "M5S006": (
        ("TARGET", "岗位训练证据要求"),
        ("TARGET", "复盘改进证据要求"),
    ),
    "M5S007": (
        ("TARGET", "升级条件生效范围"),
        ("TARGET", "资源请求生效范围"),
    ),
    "M5S008": (
        ("TARGET", "个人防护通知策略"),
        ("TARGET", "通信器材通知策略"),
    ),
    "M5S009": (
        ("SCOPE", "整改闭环域"),
        ("TARGET", "验证抽样维护主体"),
        ("EXCLUSION", "交通资源启停规则"),
    ),
    "M5S010": (
        ("SCOPE", "外部衔接域"),
        ("TARGET", "信息报送关联资源"),
        ("EXCLUSION", "终止确认反馈渠道"),
    ),
    "M5S011": (
        ("SCOPE", "协同任务域"),
        ("TARGET", "警戒组织交接节点"),
        ("EXCLUSION", "通行节点依赖条件"),
    ),
    "M5S012": (
        ("SCOPE", "全域只读字典"),
        ("TARGET", "责任边界"),
    ),
    "M5S013": (
        ("SCOPE", "全域只读字典"),
        ("TARGET", "启停规则"),
    ),
    "M5S014": (("TARGET", "水源保障确认方式"),),
    "M5S015": (("TARGET", "复测确认关联资源"),),
    "M5S016": (("TARGET", "承包商告知时间窗口"),),
    "M5S017": (("TARGET", "m5voidalpha"),),
    "M5S018": (("TARGET", "m5voidbeta"),),
}


def build_silver_role_evidence(
    scenario: dict[str, Any],
    request: IntentRequest,
) -> RetrievalRoleEvidence:
    scenario_ref = scenario.get("scenario_ref")
    annotations = _ANNOTATIONS.get(scenario_ref)
    if annotations is None:
        raise CandidateRetrievalError(
            "ROLE_CALIBRATION_SCENARIO_UNKNOWN",
            "role calibration scenario is not annotated",
        )
    source_request = scenario.get("request")
    if (
        not isinstance(source_request, dict)
        or source_request.get("requirement_text") != request.requirement_text
    ):
        raise CandidateRetrievalError(
            "ROLE_CALIBRATION_REQUEST_MISMATCH",
            "role calibration scenario does not bind the request text",
        )
    return build_retrieval_role_evidence(request, annotations)


def aggregate_annotation_report(
    formal_scenarios: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    refs = tuple(sorted(item.get("scenario_ref") for item in formal_scenarios))
    if refs != tuple(sorted(_ANNOTATIONS)):
        raise CandidateRetrievalError(
            "ROLE_CALIBRATION_DENOMINATOR_INVALID",
            "role calibration scenarios do not match the frozen annotations",
        )
    role_counts = {role: 0 for role in ("TARGET", "SCOPE", "EXCLUSION")}
    for annotations in _ANNOTATIONS.values():
        for role, _ in annotations:
            role_counts[role] += 1
    return {
        "report_version": "fire-m5-role-annotation-aggregate.v1",
        "status": "PASS",
        "policy": ANNOTATION_POLICY,
        "provenance": "CODEX_SILVER_CALIBRATION",
        "calibration_only": True,
        "gold_eligible": False,
        "gate_eligible": False,
        "production_qualification": False,
        "scenario_count": len(_ANNOTATIONS),
        "role_counts": role_counts,
    }


__all__ = [
    "ANNOTATION_POLICY",
    "aggregate_annotation_report",
    "build_silver_role_evidence",
]
