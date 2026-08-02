"""Runtime adapter for the clean-room fictional Qinglan validation dataset."""

from __future__ import annotations

from typing import Any

from treeguard.adapter import TreeFormatError, adapt_tree_document
from treeguard.fictional_qinglan_library_data import (
    build_qinglan_library_manifest,
    build_qinglan_library_scenarios,
    build_qinglan_library_tree,
)
from treeguard.fictional_qinglan_library_semantic_data import (
    build_qinglan_library_semantic_manifest,
    build_qinglan_library_semantic_scenarios,
    build_qinglan_library_semantic_tree,
)
from treeguard.models import ImportResult
from treeguard.repository_client import (
    CategoryRef,
    RepositoryClientError,
    ResourceHead,
    VersionRef,
)
from treeguard.workbench import ReadOnlyTreeRepository
from treeguard.workbench_validation import (
    ValidationDatasetManifest,
    ValidationScenario,
    ValidationScenarioOracle,
    ValidationScenarioRequest,
    ValidationVariant,
)


_MANIFEST = build_qinglan_library_manifest()
_VARIANT = _MANIFEST["variant"]
_TREE_METADATA = build_qinglan_library_tree()["metadata"]
_SEMANTIC_MANIFEST = build_qinglan_library_semantic_manifest()
_SEMANTIC_VARIANT = _SEMANTIC_MANIFEST["variant"]
_SEMANTIC_TREE_METADATA = (
    build_qinglan_library_semantic_tree()["metadata"]
)

QINGLAN_DATASET_REF = _MANIFEST["dataset_ref"]
QINGLAN_VARIANT_REF = _VARIANT["variant_ref"]
QINGLAN_CATEGORY_ID = _VARIANT["category_id"]
QINGLAN_RESOURCE_ID = _VARIANT["resource_id"]
QINGLAN_VERSION = _VARIANT["version"]
QINGLAN_VERSION_RECORD_ID = _TREE_METADATA["id"]

QINGLAN_SEMANTIC_DATASET_REF = _SEMANTIC_MANIFEST["dataset_ref"]
QINGLAN_SEMANTIC_VARIANT_REF = _SEMANTIC_VARIANT["variant_ref"]
QINGLAN_SEMANTIC_RESOURCE_ID = _SEMANTIC_VARIANT["resource_id"]
QINGLAN_SEMANTIC_VERSION = _SEMANTIC_VARIANT["version"]
QINGLAN_SEMANTIC_VERSION_RECORD_ID = _SEMANTIC_TREE_METADATA["id"]

_RISK_TITLES = {
    "CLEAR_INTENT": "清晰需求",
    "HOMONYM": "同名异义",
    "CROSS_BRANCH": "跨分支归属冲突",
    "KIND_CONFLICT": "节点类型冲突",
    "CARDINALITY_CONFLICT": "基数冲突",
    "WRONG_PARENT_HINT": "父节点提示错误",
    "NEAR_NAME_HARD_NEGATIVE": "近名干扰项",
    "INSUFFICIENT_EVIDENCE": "证据不足",
    "CLARIFICATION_REQUIRED": "需要追问",
    "REFUSAL": "无界组合应当拒绝",
    "STRUCTURAL_ANOMALY_JUDGMENT": "结构异常判断证据不足",
    "REPLAY_BASELINE_ANCHOR": "跨规模重放基线",
    "ANCESTOR_SCOPE": "祖先作用域",
    "CARTESIAN_DENSITY": "笛卡尔密度异常",
    "COLLECTION_AGGREGATE_SCOPE": "集合汇总作用域",
    "CONFLICTING_HINTS": "提示相互冲突",
    "DUPLICATE_SUBSTRUCTURE": "重复子结构",
    "GRANULARITY_AMBIGUITY": "粒度歧义",
    "INSTANCE_FIELD_SCOPE_CLEAR": "实例字段作用域清晰",
    "POLICY_INSTANCE_SEPARATION": "政策与实例边界",
    "SINGLETON_POLICY_SCOPE": "单例政策作用域",
    "UNUSUAL_DEPTH": "异常深度",
}
_NEEDS_CLARIFICATION = "NEED_CLARIFICATION"


class FictionalQinglanValidationDataset:
    """Expose the approved Qinglan batch through the generic validation API."""

    @property
    def dataset_ref(self) -> str:
        return _text(QINGLAN_DATASET_REF)

    def manifest(self) -> ValidationDatasetManifest:
        source = build_qinglan_library_manifest()
        variant = _mapping(source["variant"], "variant")
        limitations = source["limitations"]
        if not isinstance(limitations, list):
            raise ValueError("Qinglan manifest limitations are invalid")
        return ValidationDatasetManifest(
            dataset_ref=_text(source["dataset_ref"]),
            title="青岚社区图书馆跨领域控制集",
            limitations=(
                *tuple(_text(item) for item in limitations),
                "运行时只比较意图阶段状态，不比较候选或推荐结果。",
            ),
            variants=(
                ValidationVariant(
                    variant_ref=_text(variant["variant_ref"]),
                    category_id=_text(variant["category_id"]),
                    resource_id=_text(variant["resource_id"]),
                    version=_text(variant["version"]),
                    benchmark_role=_text(variant["benchmark_role"]),
                    node_count=_positive_integer(
                        variant["node_count"],
                        "node_count",
                    ),
                    scenario_count=_positive_integer(
                        variant["scenario_count"],
                        "scenario_count",
                    ),
                ),
            ),
        )

    def scenarios(
        self,
        variant_ref: str,
    ) -> tuple[ValidationScenario, ...]:
        if variant_ref != QINGLAN_VARIANT_REF:
            return ()
        return tuple(
            _scenario(_mapping(item, "scenario"))
            for item in build_qinglan_library_scenarios()
        )


class FictionalQinglanSemanticValidationDataset:
    """Expose the approved Qinglan medium semantic-challenge batch."""

    @property
    def dataset_ref(self) -> str:
        return _text(QINGLAN_SEMANTIC_DATASET_REF)

    def manifest(self) -> ValidationDatasetManifest:
        source = build_qinglan_library_semantic_manifest()
        variant = _mapping(source["variant"], "variant")
        limitations = source["limitations"]
        if not isinstance(limitations, list):
            raise ValueError("Qinglan manifest limitations are invalid")
        return ValidationDatasetManifest(
            dataset_ref=_text(source["dataset_ref"]),
            title="青岚社区图书馆中型语义挑战集",
            limitations=(
                *tuple(_text(item) for item in limitations),
                "运行时只比较意图阶段状态，不比较候选或推荐结果。",
            ),
            variants=(
                ValidationVariant(
                    variant_ref=_text(variant["variant_ref"]),
                    category_id=_text(variant["category_id"]),
                    resource_id=_text(variant["resource_id"]),
                    version=_text(variant["version"]),
                    benchmark_role=_text(variant["benchmark_role"]),
                    node_count=_positive_integer(
                        variant["node_count"],
                        "node_count",
                    ),
                    scenario_count=_positive_integer(
                        variant["scenario_count"],
                        "scenario_count",
                    ),
                ),
            ),
        )

    def scenarios(
        self,
        variant_ref: str,
    ) -> tuple[ValidationScenario, ...]:
        if variant_ref != QINGLAN_SEMANTIC_VARIANT_REF:
            return ()
        return tuple(
            _scenario(_mapping(item, "scenario"))
            for item in build_qinglan_library_semantic_scenarios()
        )


class FictionalQinglanRepositoryOverlay:
    """Add local fictional resources without changing the delegate client."""

    def __init__(self, delegate: ReadOnlyTreeRepository) -> None:
        self._delegate = delegate

    def list_categories(self) -> tuple[CategoryRef, ...]:
        categories = self._delegate.list_categories()
        if any(
            item.category_id == QINGLAN_CATEGORY_ID for item in categories
        ):
            raise RepositoryClientError(
                "REPOSITORY_QINGLAN_OVERLAY_CONFLICT",
                "delegate already contains the Qinglan category",
            )
        next_root_order = (
            max(
                (
                    item.order
                    for item in categories
                    if item.parent_id is None
                ),
                default=-1,
            )
            + 1
        )
        return (
            *categories,
            CategoryRef(
                category_id=QINGLAN_CATEGORY_ID,
                parent_id=None,
                name="青岚社区图书馆（完全虚构）",
                order=next_root_order,
            ),
        )

    def list_resources(
        self,
        category_id: str,
    ) -> tuple[ResourceHead, ...]:
        if category_id != QINGLAN_CATEGORY_ID:
            return self._delegate.list_resources(category_id)
        return (
            ResourceHead(
                resource_id=QINGLAN_RESOURCE_ID,
                category_id=QINGLAN_CATEGORY_ID,
                name="青岚社区图书馆控制树",
                head_version=QINGLAN_VERSION,
                head_version_record_id=QINGLAN_VERSION_RECORD_ID,
            ),
            ResourceHead(
                resource_id=QINGLAN_SEMANTIC_RESOURCE_ID,
                category_id=QINGLAN_CATEGORY_ID,
                name="青岚社区图书馆中型语义挑战树",
                head_version=QINGLAN_SEMANTIC_VERSION,
                head_version_record_id=(
                    QINGLAN_SEMANTIC_VERSION_RECORD_ID
                ),
            ),
        )

    def list_versions(
        self,
        resource_id: str,
    ) -> tuple[VersionRef, ...]:
        if resource_id == QINGLAN_RESOURCE_ID:
            return (
                VersionRef(
                    position=0,
                    version=QINGLAN_VERSION,
                    version_record_id=QINGLAN_VERSION_RECORD_ID,
                    description="完全虚构的 48 节点跨领域控制树",
                    is_head=True,
                ),
            )
        if resource_id == QINGLAN_SEMANTIC_RESOURCE_ID:
            return (
                VersionRef(
                    position=0,
                    version=QINGLAN_SEMANTIC_VERSION,
                    version_record_id=(
                        QINGLAN_SEMANTIC_VERSION_RECORD_ID
                    ),
                    description="完全虚构的 312 节点语义挑战树",
                    is_head=True,
                ),
            )
        return self._delegate.list_versions(resource_id)

    def fetch_tree(
        self,
        resource_id: str,
        *,
        version: str | None = None,
        version_record_id: str | None = None,
    ) -> ImportResult:
        if resource_id == QINGLAN_RESOURCE_ID:
            expected_version = QINGLAN_VERSION
            expected_record_id = QINGLAN_VERSION_RECORD_ID
            build_tree = build_qinglan_library_tree
        elif resource_id == QINGLAN_SEMANTIC_RESOURCE_ID:
            expected_version = QINGLAN_SEMANTIC_VERSION
            expected_record_id = QINGLAN_SEMANTIC_VERSION_RECORD_ID
            build_tree = build_qinglan_library_semantic_tree
        else:
            return self._delegate.fetch_tree(
                resource_id,
                version=version,
                version_record_id=version_record_id,
            )
        if (version is None) == (version_record_id is None):
            raise RepositoryClientError(
                "REPOSITORY_QINGLAN_SELECTOR_INVALID",
                "select exactly one Qinglan tree identity",
            )
        if (
            version is not None
            and version != expected_version
        ) or (
            version_record_id is not None
            and version_record_id != expected_record_id
        ):
            raise RepositoryClientError(
                "REPOSITORY_QINGLAN_SELECTOR_INVALID",
                "Qinglan tree identity is not registered",
            )
        try:
            result = adapt_tree_document(build_tree())
        except (TreeFormatError, TypeError, ValueError):
            raise RepositoryClientError(
                "REPOSITORY_QINGLAN_TREE_INVALID",
                "Qinglan tree failed canonical adaptation",
            ) from None
        if not result.is_valid or result.tree is None:
            raise RepositoryClientError(
                "REPOSITORY_QINGLAN_TREE_INVALID",
                "Qinglan tree failed canonical adaptation",
            )
        return result


def _scenario(source: dict[str, Any]) -> ValidationScenario:
    request = _mapping(source["request"], "request")
    proposed = _mapping(
        source["proposed_observable_state"],
        "proposed_observable_state",
    )
    primary_risk = _text(source["primary_risk"])
    category = _text(proposed["category"])
    draft_status = (
        "NEEDS_CLARIFICATION"
        if category == _NEEDS_CLARIFICATION
        else "READY_FOR_HUMAN_REVIEW"
    )
    return ValidationScenario(
        scenario_ref=_text(source["scenario_ref"]),
        purpose=(
            f"主要审核风险：{_risk_title(primary_risk)}；"
            "本次只比较意图阶段状态。"
        ),
        flow="INTENT_ONLY",
        request=ValidationScenarioRequest(
            requirement_text=_text(request["requirement_text"]),
            proposed_parent_node_id=_optional_text(
                request["proposed_parent_node_id"]
            ),
            node_kind_hint=_text(request["node_kind_hint"]),
            value_type_hint=_optional_text(request["value_type_hint"]),
            cardinality_hint=_text(request["cardinality_hint"]),
        ),
        oracle=ValidationScenarioOracle(
            draft_status=draft_status,
            clarification_status=None,
            candidate_status=None,
            recommendation_status=None,
        ),
    )


def _risk_title(primary_risk: str) -> str:
    try:
        return _RISK_TITLES[primary_risk]
    except KeyError:
        raise ValueError("Qinglan primary risk is unsupported") from None


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Qinglan {name} must be an object")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Qinglan text field is invalid")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value)


def _positive_integer(value: object, name: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise ValueError(f"Qinglan {name} is invalid")
    return value


__all__ = [
    "FictionalQinglanRepositoryOverlay",
    "FictionalQinglanSemanticValidationDataset",
    "FictionalQinglanValidationDataset",
    "QINGLAN_CATEGORY_ID",
    "QINGLAN_DATASET_REF",
    "QINGLAN_RESOURCE_ID",
    "QINGLAN_SEMANTIC_DATASET_REF",
    "QINGLAN_SEMANTIC_RESOURCE_ID",
    "QINGLAN_SEMANTIC_VARIANT_REF",
    "QINGLAN_SEMANTIC_VERSION",
    "QINGLAN_SEMANTIC_VERSION_RECORD_ID",
    "QINGLAN_VARIANT_REF",
    "QINGLAN_VERSION",
    "QINGLAN_VERSION_RECORD_ID",
]
