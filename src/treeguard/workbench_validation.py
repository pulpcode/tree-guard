"""Dataset-driven validation overlay for the existing governance workbench."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from treeguard.workbench import (
    ReadOnlyTreeRepository,
    TreeReferenceIndex,
    WorkbenchError,
    build_tree_reference_index,
)


DATASET_CATALOG_VERSION = "validation-dataset-catalog.v1"
SCENARIOS_VERSION = "validation-scenarios.v1"
COMPARISON_VERSION = "validation-comparison.v1"
_MODEL_MODES = {"SIMULATOR_LIVE", "BAILIAN_LIVE"}
_TERMINAL_CASE_STATUSES = {
    "CLARIFICATION_LIMIT_REACHED",
    "COMPLETED",
    "FAILED",
    "INTENT_REJECTED",
}
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ValidationWorkbenchError(RuntimeError):
    """A validation workbench request failed its stable local contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ValidationVariant:
    """One trusted tree/scenario size or shape exposed by a dataset."""

    variant_ref: str
    category_id: str
    resource_id: str
    version: str
    benchmark_role: str
    node_count: int
    scenario_count: int

    def __post_init__(self) -> None:
        for name in (
            "variant_ref",
            "category_id",
            "resource_id",
            "version",
            "benchmark_role",
        ):
            _required_text(getattr(self, name), name)
        if _REFERENCE.fullmatch(self.variant_ref) is None:
            raise ValueError("validation variant_ref is invalid")
        for name in ("node_count", "scenario_count"):
            value = getattr(self, name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
            ):
                raise ValueError(f"validation {name} must be positive")


@dataclass(frozen=True, slots=True)
class ValidationDatasetManifest:
    """Safe public metadata for one clean-room validation dataset."""

    dataset_ref: str
    title: str
    limitations: tuple[str, ...]
    variants: tuple[ValidationVariant, ...]

    def __post_init__(self) -> None:
        _required_text(self.dataset_ref, "dataset_ref")
        _required_text(self.title, "title")
        if _REFERENCE.fullmatch(self.dataset_ref) is None:
            raise ValueError("validation dataset_ref is invalid")
        if (
            not isinstance(self.limitations, tuple)
            or not self.limitations
            or len(self.limitations) > 32
            or any(
                not isinstance(item, str)
                or not item
                or len(item) > 2_000
                for item in self.limitations
            )
        ):
            raise ValueError("validation limitations are invalid")
        if (
            not isinstance(self.variants, tuple)
            or not self.variants
            or len(self.variants) > 32
            or any(
                not isinstance(item, ValidationVariant)
                for item in self.variants
            )
        ):
            raise ValueError("validation variants are invalid")
        refs = [item.variant_ref for item in self.variants]
        if len(refs) != len(set(refs)):
            raise ValueError("validation variant_ref values must be unique")


@dataclass(frozen=True, slots=True)
class ValidationScenarioRequest:
    """Trusted internal governance input for one scenario."""

    requirement_text: str
    proposed_parent_node_id: str | None
    node_kind_hint: str
    value_type_hint: str | None
    cardinality_hint: str

    def __post_init__(self) -> None:
        _required_text(self.requirement_text, "requirement_text")
        if (
            self.proposed_parent_node_id is not None
            and (
                not isinstance(self.proposed_parent_node_id, str)
                or not self.proposed_parent_node_id
            )
        ):
            raise ValueError("validation proposed parent is invalid")
        if self.node_kind_hint not in {"CONCEPT", "PROPERTY", "UNKNOWN"}:
            raise ValueError("validation node kind hint is invalid")
        if (
            self.value_type_hint is not None
            and (
                not isinstance(self.value_type_hint, str)
                or not self.value_type_hint
            )
        ):
            raise ValueError("validation value type hint is invalid")
        if self.cardinality_hint not in {
            "SINGLE",
            "MULTIPLE",
            "UNKNOWN",
        }:
            raise ValueError("validation cardinality hint is invalid")


@dataclass(frozen=True, slots=True)
class ValidationScenarioOracle:
    """Observable contract states; never an expert or semantic Gold label."""

    draft_status: str
    clarification_status: str | None
    candidate_status: str | None
    recommendation_status: str | None

    def __post_init__(self) -> None:
        _required_text(self.draft_status, "draft_status")
        for name in (
            "clarification_status",
            "candidate_status",
            "recommendation_status",
        ):
            value = getattr(self, name)
            if value is not None:
                _required_text(value, name)


@dataclass(frozen=True, slots=True)
class ValidationScenario:
    """One trusted scenario definition owned by a dataset provider."""

    scenario_ref: str
    purpose: str
    flow: str
    request: ValidationScenarioRequest
    oracle: ValidationScenarioOracle

    def __post_init__(self) -> None:
        for name in ("scenario_ref", "purpose", "flow"):
            _required_text(getattr(self, name), name)
        if _REFERENCE.fullmatch(self.scenario_ref) is None:
            raise ValueError("validation scenario_ref is invalid")
        if not isinstance(self.request, ValidationScenarioRequest):
            raise ValueError("validation scenario request is invalid")
        if not isinstance(self.oracle, ValidationScenarioOracle):
            raise ValueError("validation scenario oracle is invalid")


class ValidationDatasetProvider(Protocol):
    """Trusted local provider registered with the generic validation service."""

    @property
    def dataset_ref(self) -> str: ...

    def manifest(self) -> ValidationDatasetManifest: ...

    def scenarios(
        self,
        variant_ref: str,
    ) -> tuple[ValidationScenario, ...]: ...


class GovernanceRunService(Protocol):
    """Narrow existing-governance boundary used by the validation overlay."""

    def create_case(
        self,
        *,
        resource_id: str,
        version: str,
        requirement_text: str,
        proposed_parent_ref: str | None,
        node_kind_hint: str,
        value_type_hint: str | None,
        cardinality_hint: str,
        model_mode: str,
        external_data_approved: bool,
    ) -> dict[str, Any]: ...

    def case_view(self, case_ref: str) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class _RunBinding:
    dataset_ref: str
    variant_ref: str
    scenario_ref: str


@dataclass(slots=True)
class ValidationWorkbenchService:
    """Resolve trusted dataset references into the shared governance flow."""

    repository: ReadOnlyTreeRepository
    governance: GovernanceRunService
    providers: tuple[ValidationDatasetProvider, ...]
    _providers_by_ref: dict[str, ValidationDatasetProvider] = field(
        default_factory=dict,
        init=False,
    )
    _runs: dict[str, _RunBinding] = field(default_factory=dict, init=False)
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.providers, tuple)
            or not self.providers
            or len(self.providers) > 32
        ):
            raise ValueError(
                "validation providers must contain between 1 and 32 items"
            )
        providers_by_ref: dict[str, ValidationDatasetProvider] = {}
        for provider in self.providers:
            manifest = provider.manifest()
            if manifest.dataset_ref != provider.dataset_ref:
                raise ValueError(
                    "validation provider identity does not match manifest"
                )
            if provider.dataset_ref in providers_by_ref:
                raise ValueError("validation dataset_ref values must be unique")
            providers_by_ref[provider.dataset_ref] = provider
        self._providers_by_ref = providers_by_ref

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": DATASET_CATALOG_VERSION,
            "items": [
                _manifest_view(provider.manifest())
                for provider in self.providers
            ],
        }

    def scenarios(
        self,
        dataset_ref: str,
        variant_ref: str,
    ) -> dict[str, Any]:
        provider, manifest, variant = self._selection(
            dataset_ref,
            variant_ref,
        )
        scenarios = provider.scenarios(variant_ref)
        _verify_scenarios(scenarios, variant)
        reference_index = self._reference_index(variant)
        return {
            "schema_version": SCENARIOS_VERSION,
            "dataset_ref": manifest.dataset_ref,
            "variant_ref": variant.variant_ref,
            "benchmark_role": variant.benchmark_role,
            "fictional": True,
            "gold_eligible": False,
            "items": [
                _scenario_view(item, reference_index.ref_by_node_id)
                for item in scenarios
            ],
        }

    def create_run(
        self,
        *,
        dataset_ref: str,
        variant_ref: str,
        scenario_ref: str,
        model_mode: str,
        external_data_approved: bool,
    ) -> dict[str, Any]:
        if model_mode not in _MODEL_MODES:
            raise ValidationWorkbenchError(
                "VALIDATION_MODEL_MODE_INVALID",
                "validation model mode is unsupported",
            )
        if model_mode == "BAILIAN_LIVE" and not external_data_approved:
            raise ValidationWorkbenchError(
                "EXTERNAL_DATA_APPROVAL_REQUIRED",
                "Bailian mode requires explicit external data approval",
            )
        provider, _, variant = self._selection(
            dataset_ref,
            variant_ref,
        )
        scenarios = provider.scenarios(variant_ref)
        _verify_scenarios(scenarios, variant)
        item = _scenario_for_ref(scenarios, scenario_ref)
        reference_index = self._reference_index(variant)
        parent_node_id = item.request.proposed_parent_node_id
        try:
            parent_ref = (
                reference_index.ref_by_node_id[parent_node_id]
                if parent_node_id is not None
                else None
            )
        except KeyError:
            raise ValidationWorkbenchError(
                "VALIDATION_SCENARIO_SOURCE_INVALID",
                "validation scenario parent is not in its bound tree",
            ) from None
        operation = self.governance.create_case(
            resource_id=variant.resource_id,
            version=variant.version,
            requirement_text=item.request.requirement_text,
            proposed_parent_ref=parent_ref,
            node_kind_hint=item.request.node_kind_hint,
            value_type_hint=item.request.value_type_hint,
            cardinality_hint=item.request.cardinality_hint,
            model_mode=model_mode,
            external_data_approved=external_data_approved,
        )
        case_ref = operation.get("case_ref")
        if not isinstance(case_ref, str) or not case_ref:
            raise ValidationWorkbenchError(
                "VALIDATION_OPERATION_INVALID",
                "governance did not return a case reference",
            )
        with self._lock:
            self._runs[case_ref] = _RunBinding(
                dataset_ref=dataset_ref,
                variant_ref=variant_ref,
                scenario_ref=scenario_ref,
            )
        return operation

    def comparison(self, case_ref: str) -> dict[str, Any]:
        with self._lock:
            binding = self._runs.get(case_ref)
        if binding is None:
            raise ValidationWorkbenchError(
                "VALIDATION_RUN_NOT_FOUND",
                "validation run reference is unknown",
            )
        provider, manifest, variant = self._selection(
            binding.dataset_ref,
            binding.variant_ref,
        )
        scenarios = provider.scenarios(binding.variant_ref)
        _verify_scenarios(scenarios, variant)
        item = _scenario_for_ref(scenarios, binding.scenario_ref)
        case = self.governance.case_view(case_ref)
        expected = _expected_view(item.oracle)
        actual = {
            "intent_review_status": (
                case["intent"]["review_status"]
                if case.get("intent") is not None
                else None
            ),
            "candidate_status": (
                case["candidates"]["status"]
                if case.get("candidates") is not None
                else None
            ),
            "record_status": (
                case["record"]["status"]
                if case.get("record") is not None
                else None
            ),
            "semantic_approval": (
                case["record"]["semantic_approval"]
                if case.get("record") is not None
                else None
            ),
            "gold_eligible": (
                case["record"]["gold_eligible"]
                if case.get("record") is not None
                else None
            ),
            "patch_eligible": (
                case["record"]["patch_eligible"]
                if case.get("record") is not None
                else None
            ),
        }
        terminal = case["status"] in _TERMINAL_CASE_STATUSES
        comparisons = [
            _comparison_item(metric, value, actual[metric], terminal)
            for metric, value in expected.items()
            if value is not None
        ]
        statuses = {item["status"] for item in comparisons}
        if case["status"] == "FAILED":
            overall_status = "RUN_FAILED"
        elif statuses & {"MISMATCH", "NOT_OBSERVED"}:
            overall_status = "MISMATCH"
        elif terminal and statuses == {"MATCH"}:
            overall_status = "MATCH"
        else:
            overall_status = "IN_PROGRESS"
        return {
            "schema_version": COMPARISON_VERSION,
            "case_ref": case_ref,
            "dataset_ref": manifest.dataset_ref,
            "variant_ref": variant.variant_ref,
            "scenario_ref": binding.scenario_ref,
            "case_status": case["status"],
            "status": overall_status,
            "fictional": True,
            "gold_eligible": False,
            "items": comparisons,
            "limitations": [
                *manifest.limitations,
                "这里只比较可观察合同状态，不代表真实领域准确率。",
                "不比较模型文本、语义结论或数据集中的冻结模型输出。",
                "候选节点完整召回率和专家 Gold 不在本次对照范围。",
            ],
        }

    def _selection(
        self,
        dataset_ref: str,
        variant_ref: str,
    ) -> tuple[
        ValidationDatasetProvider,
        ValidationDatasetManifest,
        ValidationVariant,
    ]:
        provider = self._providers_by_ref.get(dataset_ref)
        if provider is None:
            raise ValidationWorkbenchError(
                "VALIDATION_DATASET_NOT_FOUND",
                "validation dataset reference is unknown",
            )
        manifest = provider.manifest()
        variant = next(
            (
                item
                for item in manifest.variants
                if item.variant_ref == variant_ref
            ),
            None,
        )
        if variant is None:
            raise ValidationWorkbenchError(
                "VALIDATION_VARIANT_NOT_FOUND",
                "validation variant reference is unknown",
            )
        return provider, manifest, variant

    def _reference_index(
        self,
        variant: ValidationVariant,
    ) -> TreeReferenceIndex:
        result = self.repository.fetch_tree(
            variant.resource_id,
            version=variant.version,
        )
        if not result.is_valid or result.tree is None:
            raise WorkbenchError(
                "WORKBENCH_TREE_NOT_AVAILABLE",
                "validation tree is not available",
            )
        return build_tree_reference_index(result.tree)


def _manifest_view(
    manifest: ValidationDatasetManifest,
) -> dict[str, Any]:
    return {
        "dataset_ref": manifest.dataset_ref,
        "title": manifest.title,
        "fictional": True,
        "gold_eligible": False,
        "limitations": list(manifest.limitations),
        "variants": [
            {
                "variant_ref": variant.variant_ref,
                "category_id": variant.category_id,
                "resource_id": variant.resource_id,
                "version": variant.version,
                "benchmark_role": variant.benchmark_role,
                "node_count": variant.node_count,
                "scenario_count": variant.scenario_count,
            }
            for variant in manifest.variants
        ],
    }


def _verify_scenarios(
    scenarios: tuple[ValidationScenario, ...],
    variant: ValidationVariant,
) -> None:
    if (
        not isinstance(scenarios, tuple)
        or len(scenarios) > 128
        or len(scenarios) != variant.scenario_count
        or any(
            not isinstance(item, ValidationScenario)
            for item in scenarios
        )
    ):
        raise ValidationWorkbenchError(
            "VALIDATION_DATASET_CONTRACT_INVALID",
            "validation provider scenarios do not match the manifest",
        )
    refs = [item.scenario_ref for item in scenarios]
    if len(refs) != len(set(refs)):
        raise ValidationWorkbenchError(
            "VALIDATION_DATASET_CONTRACT_INVALID",
            "validation scenario references must be unique",
        )


def _scenario_for_ref(
    scenarios: tuple[ValidationScenario, ...],
    scenario_ref: str,
) -> ValidationScenario:
    for item in scenarios:
        if item.scenario_ref == scenario_ref:
            return item
    raise ValidationWorkbenchError(
        "VALIDATION_SCENARIO_NOT_FOUND",
        "validation scenario reference is unknown",
    )


def _scenario_view(
    item: ValidationScenario,
    ref_by_node_id: Mapping[str, str],
) -> dict[str, Any]:
    parent_node_id = item.request.proposed_parent_node_id
    try:
        parent_ref = (
            ref_by_node_id[parent_node_id]
            if parent_node_id is not None
            else None
        )
    except KeyError:
        raise ValidationWorkbenchError(
            "VALIDATION_SCENARIO_SOURCE_INVALID",
            "validation scenario parent is not in its bound tree",
        ) from None
    return {
        "scenario_ref": item.scenario_ref,
        "purpose": item.purpose,
        "flow": item.flow,
        "request": {
            "requirement_text": item.request.requirement_text,
            "proposed_parent_ref": parent_ref,
            "node_kind_hint": item.request.node_kind_hint,
            "value_type_hint": item.request.value_type_hint,
            "cardinality_hint": item.request.cardinality_hint,
        },
        "expected": _expected_view(item.oracle),
    }


def _expected_view(
    oracle: ValidationScenarioOracle,
) -> dict[str, Any]:
    record_expected = oracle.recommendation_status is not None
    return {
        "intent_review_status": (
            oracle.clarification_status
            if oracle.clarification_status is not None
            else oracle.draft_status
        ),
        "candidate_status": oracle.candidate_status,
        "record_status": oracle.recommendation_status,
        "semantic_approval": False if record_expected else None,
        "gold_eligible": False if record_expected else None,
        "patch_eligible": False if record_expected else None,
    }


def _comparison_item(
    metric: str,
    expected: Any,
    actual: Any,
    terminal: bool,
) -> dict[str, Any]:
    if actual is None:
        status = "NOT_OBSERVED" if terminal else "PENDING"
    else:
        status = "MATCH" if actual == expected else "MISMATCH"
    return {
        "metric": metric,
        "expected": expected,
        "actual": actual,
        "status": status,
    }


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"validation {name} must be non-empty text")
    return value


__all__ = [
    "COMPARISON_VERSION",
    "DATASET_CATALOG_VERSION",
    "SCENARIOS_VERSION",
    "ValidationDatasetManifest",
    "ValidationDatasetProvider",
    "ValidationScenario",
    "ValidationScenarioOracle",
    "ValidationScenarioRequest",
    "ValidationVariant",
    "ValidationWorkbenchError",
    "ValidationWorkbenchService",
]
