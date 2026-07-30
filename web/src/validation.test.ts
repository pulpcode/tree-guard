import { describe, expect, it } from "vitest";

import type { ValidationDatasetCatalog } from "./api";
import {
  findValidationDataset,
  findValidationVariant,
  formatValidationValue,
  validationMetricLabel,
  validationStatusLabel,
} from "./validation";

const catalog: ValidationDatasetCatalog = {
  schema_version: "validation-dataset-catalog.v1",
  items: [
    {
      dataset_ref: "fictional-dataset",
      title: "完全虚构验证数据",
      fictional: true,
      gold_eligible: false,
      limitations: ["仅用于前端虚构合同测试。"],
      variants: [
        {
          variant_ref: "small",
          category_id: "fictional-category",
          resource_id: "fictional-resource",
          version: "FICTIONAL-V1",
          benchmark_role: "precision_contract",
          node_count: 31,
          scenario_count: 8,
        },
      ],
    },
  ],
};

describe("validation presentation", () => {
  it("resolves a registered dataset and variant", () => {
    const dataset = findValidationDataset(
      catalog.items,
      "fictional-dataset",
    );
    expect(findValidationVariant(dataset, "small")?.node_count).toBe(31);
    expect(findValidationVariant(dataset, "large")).toBeUndefined();
    expect(
      findValidationDataset(catalog.items, "unknown"),
    ).toBeUndefined();
  });

  it("uses explicit labels without changing contract values", () => {
    expect(validationMetricLabel("candidate_status")).toBe("候选状态");
    expect(validationStatusLabel("NOT_OBSERVED")).toBe("终态未观察到");
    expect(formatValidationValue(false)).toBe("false");
    expect(formatValidationValue(null)).toBe("—");
  });
});
