import type {
  ValidationComparison,
  ValidationDataset,
  ValidationVariant,
} from "./api";

export function findValidationDataset(
  datasets: ValidationDataset[] | undefined,
  datasetRef: string | undefined,
): ValidationDataset | undefined {
  return datasets?.find((item) => item.dataset_ref === datasetRef);
}

export function findValidationVariant(
  dataset: ValidationDataset | undefined,
  variantRef: string | undefined,
): ValidationVariant | undefined {
  return dataset?.variants.find(
    (item) => item.variant_ref === variantRef,
  );
}

export function validationMetricLabel(metric: string): string {
  const labels: Record<string, string> = {
    intent_review_status: "意图状态",
    candidate_status: "候选状态",
    record_status: "人工记录状态",
    semantic_approval: "语义审批",
    gold_eligible: "Gold 资格",
    patch_eligible: "Patch 资格",
  };
  return labels[metric] ?? metric;
}

export function validationStatusLabel(
  status:
    | ValidationComparison["status"]
    | ValidationComparison["items"][number]["status"],
): string {
  const labels: Record<string, string> = {
    IN_PROGRESS: "运行中",
    MATCH: "符合合同预期",
    MISMATCH: "偏离合同预期",
    RUN_FAILED: "运行失败",
    PENDING: "尚未观察",
    NOT_OBSERVED: "终态未观察到",
  };
  return labels[status] ?? status;
}

export function formatValidationValue(
  value: string | boolean | null,
): string {
  if (value === null) {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return value;
}
