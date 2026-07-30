"""Deterministic clean-room data and routes for development simulation."""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Mapping

from treeguard.fictional_fire_data import (
    FIRE_VALIDATION_CATEGORY_ID,
    FIRE_VALIDATION_RESOURCE_IDS,
    FIRE_VALIDATION_TIERS,
    TIER_SPECS,
    build_fictional_fire_tree,
    fire_validation_record_id,
    fire_validation_tree_id,
    fire_validation_version,
)
from treeguard.json_utils import StrictJSONError, strict_json_loads


SIMULATOR_CONTRACT_STATUS = "PROVISIONAL_SIMULATOR_CONTRACT"
SIMULATOR_BEARER_TOKEN = "treeguard-simulator-token"
SIMULATOR_MODEL_NAME = "treeguard-simulator-model"
SIMULATOR_RESOURCE_ID = "fictional-museum-resource"
SIMULATOR_CATEGORY_ID = "fictional-catalog-category"
SIMULATOR_TREE_ID = "fictional-museum-tree"
SIMULATOR_HEAD_VERSION = "SIM-V2"
SIMULATOR_RESOURCE_TREE_IDS = {
    SIMULATOR_RESOURCE_ID: SIMULATOR_TREE_ID,
    **{
        FIRE_VALIDATION_RESOURCE_IDS[tier]: fire_validation_tree_id(tier)
        for tier in FIRE_VALIDATION_TIERS
    },
}
SIMULATOR_MODEL_SCENARIOS = {
    "ready",
    "clarification",
    "invalid-json",
    "extra-field",
    "http-429",
    "http-500",
    "timeout",
}
MIN_SIMULATOR_NODES = 5
MAX_SIMULATOR_NODES = 10_000
MAX_SIMULATOR_REQUEST_BYTES = 1_000_000
_RESOURCE_PATH = re.compile(
    r"^/provisional/v1/resources/([^/]+)/(versions|tree)$"
)
_RECORDED_SUBJECT = re.compile(
    r"记录\s*(?P<subject>.+?)[。.]*$"
)


class SimulatorValidationError(ValueError):
    """A simulator configuration or pure request failed its local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SimulatorResponse:
    status_code: int
    body: bytes
    content_type: str = "application/json"
    delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status_code, int)
            or isinstance(self.status_code, bool)
            or self.status_code < 100
            or self.status_code > 599
        ):
            raise ValueError("simulator HTTP status is invalid")
        if not isinstance(self.body, bytes):
            raise ValueError("simulator response body must be bytes")
        if not isinstance(self.content_type, str) or not self.content_type:
            raise ValueError("simulator content_type is invalid")
        if (
            not isinstance(self.delay_seconds, (int, float))
            or isinstance(self.delay_seconds, bool)
            or self.delay_seconds < 0
            or self.delay_seconds > 5
        ):
            raise ValueError("simulator delay is invalid")


def build_fictional_tree(
    *,
    node_count: int = 5,
    version: str = SIMULATOR_HEAD_VERSION,
) -> dict[str, Any]:
    """Build an unrelated deterministic source-format tree with stable IDs."""

    if (
        not isinstance(node_count, int)
        or isinstance(node_count, bool)
        or node_count < MIN_SIMULATOR_NODES
        or node_count > MAX_SIMULATOR_NODES
    ):
        raise SimulatorValidationError(
            "SIMULATOR_NODE_COUNT_INVALID",
            "simulator node_count is outside the supported development range",
        )
    if version not in {"SIM-V1", "SIM-V2"}:
        raise SimulatorValidationError(
            "SIMULATOR_VERSION_INVALID",
            "simulator version is unsupported",
        )

    root_id = "fictional-museum-root"
    catalog_id = "fictional-catalog"
    dimensions_id = "fictional-dimensions"
    height_name = "展品高度" if version == "SIM-V1" else "陈列高度"
    catalog_subnodes: dict[str, Any] = {
        "DIMENSIONS": {
            "metadata": _property_metadata(
                node_id=dimensions_id,
                parent_node_id=catalog_id,
                name="展品尺寸",
                label="DIMENSIONS",
                route="MUSEUM/-/CATALOG/-/DIMENSIONS",
                order=1,
                value_type="class",
            ),
            "subnodes": {
                "HEIGHT": {
                    "metadata": _property_metadata(
                        node_id="fictional-height",
                        parent_node_id=dimensions_id,
                        name=height_name,
                        label="HEIGHT",
                        route=(
                            "MUSEUM/-/CATALOG/-/DIMENSIONS/-/HEIGHT"
                        ),
                        order=1,
                        value_type="float",
                    )
                },
                "WIDTH": {
                    "metadata": _property_metadata(
                        node_id="fictional-width",
                        parent_node_id=dimensions_id,
                        name="陈列宽度",
                        label="WIDTH",
                        route=(
                            "MUSEUM/-/CATALOG/-/DIMENSIONS/-/WIDTH"
                        ),
                        order=2,
                        value_type="float",
                    )
                },
            },
        }
    }
    for index in range(1, node_count - 4):
        label = f"FIELD_{index:05d}"
        catalog_subnodes[label] = {
            "metadata": _property_metadata(
                node_id=f"fictional-field-{index:05d}",
                parent_node_id=catalog_id,
                name=f"模拟藏品字段 {index:05d}",
                label=label,
                route=f"MUSEUM/-/CATALOG/-/{label}",
                order=index + 1,
                value_type="string",
            )
        }

    return {
        "metadata": {
            "id": f"fictional-record-{version.lower()}",
            "map_id": SIMULATOR_TREE_ID,
            "map_type": "resource",
            "map_name": "虚构博物馆藏品目录",
            "version": version,
            "category_id": SIMULATOR_CATEGORY_ID,
            "concurrent_version": 1 if version == "SIM-V1" else 2,
        },
        "map_topology": {
            "MUSEUM": {
                "metadata": {
                    "node_id": root_id,
                    "node_type": "concept",
                    "node_name": "虚构博物馆",
                    "node_label": "MUSEUM",
                    "node_label_route": "MUSEUM",
                    "node_order": 1,
                },
                "subnodes": {
                    "CATALOG": {
                        "metadata": {
                            "node_id": catalog_id,
                            "parent_node_id": root_id,
                            "node_type": "concept",
                            "node_name": "藏品目录",
                            "node_label": "CATALOG",
                            "node_label_route": "MUSEUM/-/CATALOG",
                            "node_order": 1,
                        },
                        "subnodes": catalog_subnodes,
                    }
                },
            }
        },
    }


def _property_metadata(
    *,
    node_id: str,
    parent_node_id: str,
    name: str,
    label: str,
    route: str,
    order: int,
    value_type: str,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "parent_node_id": parent_node_id,
        "node_type": "property",
        "node_name": name,
        "node_label": label,
        "node_label_route": route,
        "node_order": order,
        "value_type": value_type,
        "is_list": False,
        "value_constraints": {"raw_constraints": {}},
    }


class ContractSimulator:
    """Pure provisional repository and OpenAI-compatible request router."""

    def __init__(
        self,
        *,
        node_count: int = 50,
        model_scenario: str = "ready",
        delay_seconds: float = 1.0,
    ) -> None:
        build_fictional_tree(node_count=node_count)
        if model_scenario not in SIMULATOR_MODEL_SCENARIOS:
            raise SimulatorValidationError(
                "SIMULATOR_MODEL_SCENARIO_INVALID",
                "simulator model scenario is unsupported",
            )
        if (
            not isinstance(delay_seconds, (int, float))
            or isinstance(delay_seconds, bool)
            or delay_seconds < 0
            or delay_seconds > 5
        ):
            raise SimulatorValidationError(
                "SIMULATOR_DELAY_INVALID",
                "simulator delay is outside the supported development range",
            )
        self.node_count = node_count
        self.model_scenario = model_scenario
        self.delay_seconds = float(delay_seconds)

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> SimulatorResponse:
        normalized_headers = {
            str(key).lower(): str(value) for key, value in headers.items()
        }
        if normalized_headers.get("authorization") != (
            f"Bearer {SIMULATOR_BEARER_TOKEN}"
        ):
            return _error_response(401, "SIMULATOR_AUTH_REQUIRED")
        if len(body) > MAX_SIMULATOR_REQUEST_BYTES:
            return _error_response(413, "SIMULATOR_REQUEST_TOO_LARGE")
        try:
            parsed = urllib.parse.urlsplit(target)
        except ValueError:
            return _error_response(400, "SIMULATOR_TARGET_INVALID")
        if parsed.scheme or parsed.netloc or parsed.fragment:
            return _error_response(400, "SIMULATOR_TARGET_INVALID")
        if method == "POST" and parsed.path == "/v1/chat/completions":
            if parsed.query:
                return _error_response(400, "SIMULATOR_QUERY_INVALID")
            return self._handle_chat(normalized_headers, body)
        if method != "GET":
            return _error_response(405, "SIMULATOR_METHOD_NOT_ALLOWED")
        return self._handle_repository(parsed)

    def _handle_repository(
        self,
        parsed: urllib.parse.SplitResult,
    ) -> SimulatorResponse:
        try:
            query = urllib.parse.parse_qs(
                parsed.query,
                strict_parsing=bool(parsed.query),
                keep_blank_values=True,
            )
        except ValueError:
            return _error_response(400, "SIMULATOR_QUERY_INVALID")
        if parsed.path == "/provisional/v1/categories":
            if query:
                return _error_response(400, "SIMULATOR_QUERY_INVALID")
            return _json_response(_category_response())
        if parsed.path == "/provisional/v1/resources":
            if set(query) != {"category_id"} or len(query["category_id"]) != 1:
                return _error_response(400, "SIMULATOR_QUERY_INVALID")
            category_id = query["category_id"][0]
            if category_id == SIMULATOR_CATEGORY_ID:
                return _json_response(_resource_response())
            if category_id == FIRE_VALIDATION_CATEGORY_ID:
                return _json_response(_fire_resource_response())
            return _json_response(_resource_response(items=[]))
        match = _RESOURCE_PATH.fullmatch(parsed.path)
        if match is None:
            return _error_response(404, "SIMULATOR_ROUTE_NOT_FOUND")
        resource_id = urllib.parse.unquote(match.group(1))
        operation = match.group(2)
        if resource_id not in SIMULATOR_RESOURCE_TREE_IDS:
            return _error_response(404, "SIMULATOR_RESOURCE_NOT_FOUND")
        if operation == "versions":
            if query:
                return _error_response(400, "SIMULATOR_QUERY_INVALID")
            return _json_response(_version_response(resource_id))
        return self._tree_response(resource_id, query)

    def _tree_response(
        self,
        resource_id: str,
        query: dict[str, list[str]],
    ) -> SimulatorResponse:
        if len(query) != 1:
            return _error_response(400, "SIMULATOR_QUERY_INVALID")
        if resource_id == SIMULATOR_RESOURCE_ID:
            versions = {
                "SIM-V1": "fictional-record-sim-v1",
                "SIM-V2": "fictional-record-sim-v2",
            }
        else:
            tier = _fire_tier_for_resource(resource_id)
            versions = {
                fire_validation_version(tier): fire_validation_record_id(tier)
            }
        if "version" in query and len(query["version"]) == 1:
            version = query["version"][0]
        elif (
            "version_record_id" in query
            and len(query["version_record_id"]) == 1
        ):
            record_id = query["version_record_id"][0]
            record_to_version = {
                record_id: business_version
                for business_version, record_id in versions.items()
            }
            version = record_to_version.get(record_id, "")
        else:
            return _error_response(400, "SIMULATOR_QUERY_INVALID")
        if version not in versions:
            return _error_response(404, "SIMULATOR_VERSION_NOT_FOUND")
        if resource_id == SIMULATOR_RESOURCE_ID:
            tree = build_fictional_tree(
                node_count=self.node_count,
                version=version,
            )
        else:
            tree = build_fictional_fire_tree(
                _fire_tier_for_resource(resource_id)
            )
        return _json_response(
            {
                "schema_version": "provisional-simulator-tree.v1",
                "contract_status": SIMULATOR_CONTRACT_STATUS,
                "status": 0,
                "message": "OK",
                "data": tree,
            }
        )

    def _handle_chat(
        self,
        headers: Mapping[str, str],
        body: bytes,
    ) -> SimulatorResponse:
        if headers.get("content-type", "").split(";", 1)[0].strip() != (
            "application/json"
        ):
            return _error_response(415, "SIMULATOR_CONTENT_TYPE_REQUIRED")
        if self.model_scenario == "http-429":
            return _error_response(429, "SIMULATOR_RATE_LIMITED")
        if self.model_scenario == "http-500":
            return _error_response(500, "SIMULATOR_MODEL_FAILED")
        delay = (
            self.delay_seconds
            if self.model_scenario == "timeout"
            else 0.0
        )
        if self.model_scenario == "invalid-json":
            return SimulatorResponse(
                status_code=200,
                body=b"{",
                delay_seconds=delay,
            )
        try:
            request = strict_json_loads(body)
        except (
            StrictJSONError,
            RecursionError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            return _error_response(400, "SIMULATOR_REQUEST_NOT_JSON")
        if not _valid_chat_request(request):
            return _error_response(400, "SIMULATOR_CHAT_REQUEST_INVALID")
        user_payload = _last_user_payload(request["messages"])
        if user_payload is None:
            return _error_response(400, "SIMULATOR_CHAT_REQUEST_INVALID")
        output = _model_output(
            user_payload,
            clarification=(
                self.model_scenario == "clarification"
            ),
        )
        if self.model_scenario == "extra-field":
            output["unexpected"] = True
        envelope = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            output,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                }
            ]
        }
        return _json_response(envelope, delay_seconds=delay)


def _valid_chat_request(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    required = {"model", "messages", "temperature", "stream"}
    if not required.issubset(payload):
        return False
    if not isinstance(payload["model"], str) or not payload["model"]:
        return False
    if not isinstance(payload["messages"], list) or not payload["messages"]:
        return False
    if payload["stream"] is not False or payload["temperature"] != 0:
        return False
    response_format = payload.get("response_format")
    if response_format is not None and response_format != {
        "type": "json_object"
    }:
        return False
    enable_thinking = payload.get("enable_thinking")
    return enable_thinking in {None, False}


def _last_user_payload(messages: list[Any]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if (
            isinstance(message, dict)
            and message.get("role") == "user"
            and isinstance(message.get("content"), str)
        ):
            try:
                payload = strict_json_loads(message["content"])
            except (
                StrictJSONError,
                RecursionError,
                TypeError,
                UnicodeError,
                json.JSONDecodeError,
            ):
                return {"hello": True}
            return payload if isinstance(payload, dict) else None
    return None


def _model_output(
    user_payload: dict[str, Any],
    *,
    clarification: bool,
) -> dict[str, Any]:
    output_contract = user_payload.get("output_contract")
    schema_version = (
        output_contract.get("schema_version")
        if isinstance(output_contract, dict)
        else None
    )
    if schema_version == "change-intent-model-output.v1":
        is_clarification = "clarification_input" in user_payload
        question = (
            "还需要补充哪项关键需求约束？"
            if clarification and not is_clarification
            else None
        )
        simulated_output = _simulated_intent_output(
            user_payload,
            schema_version=schema_version,
            question=question,
        )
        if simulated_output is not None:
            return simulated_output
        return {
            "schema_version": schema_version,
            "subject": "陈列高度",
            "role": "藏品尺寸测量",
            "scenario": "虚构展览",
            "lifecycle": "目录使用期",
            "ownership": "LONG_LIVED_SUBJECT_PROPERTY",
            "node_kind": "PROPERTY",
            "value_type": "float",
            "cardinality": "SINGLE",
            "confirmed_facts": [
                "需要记录完全虚构的陈列高度。"
            ],
            "assumptions": [],
            "evidence_gaps": (
                ["尚未说明虚构计量单位。"]
                if question is not None
                else []
            ),
            "clarification_question": question,
        }
    if schema_version == "semantic-recommendation-model-output.v1":
        semantic_input = user_payload.get("semantic_input")
        candidates = (
            semantic_input.get("candidates", [])
            if isinstance(semantic_input, dict)
            else []
        )
        refs = [
            item.get("candidate_ref")
            for item in candidates
            if isinstance(item, dict)
            and isinstance(item.get("candidate_ref"), str)
        ]
        assessments = [
            {
                "candidate_ref": ref,
                "relation": (
                    "SEMANTICALLY_EQUIVALENT"
                    if index == 0
                    else "NOT_EQUIVALENT"
                ),
                "reason": "已比较一个确定性的虚构候选。",
            }
            for index, ref in enumerate(refs)
        ]
        return {
            "schema_version": schema_version,
            "candidate_assessments": assessments,
            "recommended_action": (
                "USE_EXISTING_NODE" if refs else "ABSTAIN"
            ),
            "selected_candidate_ref": refs[0] if refs else None,
            "rationale": "仿真器返回固定且符合合同的结果。",
            "uncertainties": [],
            "evidence_gaps": [],
            "clarification_question": None,
        }
    return {"message": "hello", "valid": True}


def _simulated_intent_output(
    user_payload: dict[str, Any],
    *,
    schema_version: str,
    question: str | None,
) -> dict[str, Any] | None:
    """Echo an explicit clean-room request without adding domain knowledge."""

    intent_request = user_payload.get("intent_request")
    if not isinstance(intent_request, dict):
        return None
    requirement_text = intent_request.get("requirement_text")
    if not isinstance(requirement_text, str):
        return None
    requirement_text = requirement_text.strip()
    if not requirement_text:
        return None
    hints = intent_request.get("hints")
    if not isinstance(hints, dict):
        return None
    node_kind = hints.get("node_kind")
    value_type = hints.get("value_type")
    cardinality = hints.get("cardinality")
    if (
        node_kind not in {"CONCEPT", "PROPERTY", "UNKNOWN"}
        or not (
            value_type is None
            or isinstance(value_type, str)
            and value_type
        )
        or cardinality not in {"SINGLE", "MULTIPLE", "UNKNOWN"}
    ):
        return None
    match = _RECORDED_SUBJECT.search(requirement_text)
    subject = (
        match.group("subject").strip()
        if match is not None
        else requirement_text
    )
    subject = subject[:1_000] or None
    return {
        "schema_version": schema_version,
        "subject": subject,
        "role": None,
        "scenario": None,
        "lifecycle": None,
        "ownership": "UNKNOWN",
        "node_kind": node_kind,
        "value_type": value_type,
        "cardinality": cardinality,
        "confirmed_facts": [requirement_text[:1_000]],
        "assumptions": [],
        "evidence_gaps": (
            ["尚有一个最重要的需求细节需要确认。"]
            if question is not None
            else []
        ),
        "clarification_question": question,
    }


def _category_response() -> dict[str, Any]:
    items = [
        {
            "category_id": "fictional-root-category",
            "parent_id": None,
            "name": "虚构资料库",
            "order": 1,
        },
        {
            "category_id": SIMULATOR_CATEGORY_ID,
            "parent_id": "fictional-root-category",
            "name": "虚构藏品目录",
            "order": 1,
        },
        {
            "category_id": FIRE_VALIDATION_CATEGORY_ID,
            "parent_id": "fictional-root-category",
            "name": "虚构消防验证数据",
            "order": 2,
        },
    ]
    return {
        "schema_version": "provisional-simulator-categories.v1",
        "contract_status": SIMULATOR_CONTRACT_STATUS,
        "status": 0,
        "message": "OK",
        "data": {"items": items, "total": len(items)},
    }


def _resource_response(
    *,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if items is None:
        items = [
            {
                "resource_id": SIMULATOR_RESOURCE_ID,
                "category_id": SIMULATOR_CATEGORY_ID,
                "name": "虚构博物馆藏品目录",
                "head_version": SIMULATOR_HEAD_VERSION,
                "head_version_record_id": "fictional-record-sim-v2",
            }
        ]
    return {
        "schema_version": "provisional-simulator-resources.v1",
        "contract_status": SIMULATOR_CONTRACT_STATUS,
        "status": 0,
        "message": "OK",
        "data": {"items": items, "total": len(items)},
    }


def _fire_resource_response() -> dict[str, Any]:
    items = [
        {
            "resource_id": FIRE_VALIDATION_RESOURCE_IDS[tier],
            "category_id": FIRE_VALIDATION_CATEGORY_ID,
            "name": f"虚构消防任务治理验证树 · {tier}",
            "head_version": fire_validation_version(tier),
            "head_version_record_id": fire_validation_record_id(tier),
        }
        for tier in FIRE_VALIDATION_TIERS
    ]
    return _resource_response(items=items)


def _version_response(resource_id: str) -> dict[str, Any]:
    if resource_id == SIMULATOR_RESOURCE_ID:
        items = [
            {
                "position": 0,
                "version": "SIM-V1",
                "version_record_id": "fictional-record-sim-v1",
                "description": None,
                "is_head": False,
            },
            {
                "position": 1,
                "version": "SIM-V2",
                "version_record_id": "fictional-record-sim-v2",
                "description": "模拟陈列用语更新。",
                "is_head": True,
            },
        ]
    else:
        tier = _fire_tier_for_resource(resource_id)
        items = [
            {
                "position": 0,
                "version": fire_validation_version(tier),
                "version_record_id": fire_validation_record_id(tier),
                "description": (
                    f"完全虚构的 {TIER_SPECS[tier]['node_count']} 节点验证树。"
                ),
                "is_head": True,
            }
        ]
    return {
        "schema_version": "provisional-simulator-versions.v1",
        "contract_status": SIMULATOR_CONTRACT_STATUS,
        "status": 0,
        "message": "OK",
        "data": {
            "resource_id": resource_id,
            "ordering": "OLDEST_FIRST",
            "items": items,
            "total": len(items),
        },
    }


def _fire_tier_for_resource(resource_id: str) -> str:
    for tier in FIRE_VALIDATION_TIERS:
        if FIRE_VALIDATION_RESOURCE_IDS[tier] == resource_id:
            return tier
    raise ValueError("resource is not a fictional fire validation tree")


def _json_response(
    payload: dict[str, Any],
    *,
    status_code: int = 200,
    delay_seconds: float = 0.0,
) -> SimulatorResponse:
    return SimulatorResponse(
        status_code=status_code,
        body=json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        delay_seconds=delay_seconds,
    )


def _error_response(status_code: int, code: str) -> SimulatorResponse:
    return _json_response(
        {
            "schema_version": "provisional-simulator-error.v1",
            "contract_status": SIMULATOR_CONTRACT_STATUS,
            "status": status_code,
            "message": "Simulator request rejected.",
            "error_code": code,
        },
        status_code=status_code,
    )


__all__ = [
    "ContractSimulator",
    "MAX_SIMULATOR_NODES",
    "MIN_SIMULATOR_NODES",
    "SIMULATOR_BEARER_TOKEN",
    "SIMULATOR_CATEGORY_ID",
    "SIMULATOR_CONTRACT_STATUS",
    "SIMULATOR_HEAD_VERSION",
    "SIMULATOR_MODEL_NAME",
    "SIMULATOR_MODEL_SCENARIOS",
    "SIMULATOR_RESOURCE_ID",
    "SIMULATOR_TREE_ID",
    "SimulatorResponse",
    "SimulatorValidationError",
    "build_fictional_tree",
]
