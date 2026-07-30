"""Trusted adapter from the fictional fire fixtures to validation contracts."""

from __future__ import annotations

from treeguard.fictional_fire_data import (
    FIRE_VALIDATION_CATEGORY_ID,
    FIRE_VALIDATION_RESOURCE_IDS,
    FIRE_VALIDATION_TIERS,
    build_fictional_fire_manifest,
    build_fictional_fire_scenarios,
    fire_validation_version,
)
from treeguard.workbench_validation import (
    ValidationDatasetManifest,
    ValidationScenario,
    ValidationScenarioOracle,
    ValidationScenarioRequest,
    ValidationVariant,
)


class FictionalFireValidationDataset:
    """Expose one clean-room fire-themed dataset through the generic boundary."""

    @property
    def dataset_ref(self) -> str:
        return build_fictional_fire_manifest()["dataset_id"]

    def manifest(self) -> ValidationDatasetManifest:
        source = build_fictional_fire_manifest()
        return ValidationDatasetManifest(
            dataset_ref=source["dataset_id"],
            title=source["title"],
            limitations=tuple(source["limitations"]),
            variants=tuple(
                ValidationVariant(
                    variant_ref=item["tier"],
                    category_id=FIRE_VALIDATION_CATEGORY_ID,
                    resource_id=FIRE_VALIDATION_RESOURCE_IDS[item["tier"]],
                    version=fire_validation_version(item["tier"]),
                    benchmark_role=item["benchmark_role"],
                    node_count=item["node_count"],
                    scenario_count=item["scenario_count"],
                )
                for item in source["tiers"]
            ),
        )

    def scenarios(
        self,
        variant_ref: str,
    ) -> tuple[ValidationScenario, ...]:
        if variant_ref not in FIRE_VALIDATION_TIERS:
            return ()
        source = build_fictional_fire_scenarios(variant_ref)
        return tuple(_scenario(item) for item in source["items"])


def _scenario(source: dict[str, object]) -> ValidationScenario:
    request = source["request"]
    oracle = source["oracle"]
    if not isinstance(request, dict) or not isinstance(oracle, dict):
        raise ValueError("fictional fire scenario shape is invalid")
    return ValidationScenario(
        scenario_ref=_text(source["scenario_ref"]),
        purpose=_text(source["purpose"]),
        flow=_text(source["flow"]),
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
            draft_status=_text(oracle["draft_status"]),
            clarification_status=_optional_text(
                oracle["clarification_status"]
            ),
            candidate_status=_optional_text(oracle["candidate_status"]),
            recommendation_status=_optional_text(
                oracle["recommendation_status"]
            ),
        ),
    )


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("fictional fire text field is invalid")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value)


__all__ = ["FictionalFireValidationDataset"]
