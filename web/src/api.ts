export interface CategoryItem {
  category_id: string;
  parent_id: string | null;
  name: string;
  order: number;
}

export interface ResourceItem {
  resource_id: string;
  category_id: string;
  name: string;
  head_version: string;
}

export interface VersionItem {
  position: number;
  version: string;
  description: string | null;
  is_head: boolean;
}

export interface TreeViewNode {
  ref: string;
  parent_ref: string | null;
  child_refs: string[];
  name: string;
  label: string;
  kind: string;
  value_type: string | null;
  cardinality: string | null;
  order: number | null;
  breadcrumb: string[];
}

export interface TreeView {
  schema_version: "workbench-tree-view.v1";
  tree_version: string;
  node_count: number;
  root_refs: string[];
  nodes: TreeViewNode[];
}

interface ListResponse<T> {
  schema_version: string;
  items: T[];
}

interface ErrorResponse {
  schema_version: "workbench-error.v1";
  error_code: string;
  message: string;
}

export class WorkbenchAPIError extends Error {
  readonly code: string;

  constructor(code: string) {
    super("工作台请求未能完成");
    this.code = code;
  }
}

export type GovernanceModelMode =
  | "SIMULATOR_LIVE"
  | "BAILIAN_LIVE"
  | "QWEN_LIVE";

export interface GovernanceOperation {
  schema_version: "workbench-operation-view.v1";
  operation_ref: string;
  case_ref: string;
  kind: string;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";
  error_code: string | null;
  case_status: string;
}

export interface GovernanceIntentContent {
  subject: string | null;
  role: string | null;
  scenario: string | null;
  lifecycle: string | null;
  ownership: string;
  node_kind: string;
  value_type: string | null;
  cardinality: string;
  confirmed_facts: string[];
  assumptions: string[];
  evidence_gaps: string[];
  clarification_question: string | null;
}

export interface GovernanceCandidate {
  candidate_ref: string;
  rank: number;
  kind: string;
  label: string;
  name: string;
  path_labels: string[];
  path_names: string[];
  value_type: string | null;
  cardinality: string | null;
  parent_relation: string;
}

export interface GovernanceRecommendation {
  schema_version: "semantic-recommendation-content.v1";
  candidate_assessments: Array<{
    candidate_ref: string;
    relation: string;
    reason: string;
  }>;
  recommended_action: string;
  selected_candidate_ref: string | null;
  rationale: string;
  uncertainties: string[];
  evidence_gaps: string[];
  clarification_question: string | null;
}

export interface GovernanceCase {
  schema_version: "workbench-governance-case-view.v1";
  case_ref: string;
  status: string;
  model_mode: GovernanceModelMode;
  intent: {
    review_status: string;
    content: GovernanceIntentContent;
  } | null;
  candidates: {
    status: string;
    items: GovernanceCandidate[];
  } | null;
  recommendation: GovernanceRecommendation | null;
  record: {
    report_version: "recommendation-record-aggregate.v1";
    valid: boolean;
    record_semantics: "OPERATIONAL_FEEDBACK_ONLY";
    status: string;
    semantic_approval: false;
    patch_eligible: false;
    gold_eligible: false;
  } | null;
}

export interface GovernanceModelTraceMessage {
  role: string;
  content: string;
  content_truncated: boolean;
}

export interface GovernanceModelTraceAttempt {
  stage:
    | "INTENT_DRAFT"
    | "INTENT_CLARIFICATION"
    | "SEMANTIC_RECOMMENDATION"
    | "CHANGE_UNDERSTANDING"
    | "CHANGE_UNDERSTANDING_CLARIFICATION"
    | "SEMANTIC_RELATION";
  attempt: number;
  provider: string;
  model: string;
  prompt_version: string;
  thinking_status: "DISABLED";
  request_messages: GovernanceModelTraceMessage[];
  response_content: string | null;
  response_content_truncated: boolean;
  validation_status: "PASSED" | "FAILED";
  validation_error_code: string | null;
  usage: {
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
    total_tokens?: number | null;
  } | null;
}

export interface GovernanceModelTraceView {
  schema_version: "workbench-model-trace-view.v1";
  case_ref: string;
  model_mode: GovernanceModelMode;
  thinking_status: "DISABLED";
  items: GovernanceModelTraceAttempt[];
}

export interface NavigationCopilotCapability {
  schema_version: "navigation-copilot-capability.v1";
  enabled: boolean;
  shadow_only: true;
  max_model_calls: 2;
  max_display_candidates: 8;
  production_write_enabled: false;
}

export interface NavigationCopilotCandidate {
  candidate_ref: string;
  rank: number;
  node_ref: string;
  name: string;
  label: string;
  kind: "CONCEPT" | "PROPERTY";
  value_type: string | null;
  cardinality: "SINGLE" | "MULTIPLE" | null;
  path_names: string[];
  parent_relation: string;
  relation: string | null;
  reason: string | null;
}

export interface NavigationCopilotCase {
  schema_version: "navigation-copilot-case-view.v1";
  case_ref: string;
  status: string;
  model_mode: GovernanceModelMode;
  model_call_count: number;
  interpretation: {
    status: "MODEL_VALID" | "MODEL_DEGRADED";
    node_kind: "CONCEPT" | "PROPERTY" | "UNKNOWN";
    value_type: string | null;
    cardinality: "SINGLE" | "MULTIPLE" | "UNKNOWN";
    clarification_question: string | null;
  } | null;
  degradation_codes: string[];
  candidate_status:
    | "CANDIDATES_AVAILABLE"
    | "AMBIGUOUS"
    | "NONE"
    | "NEED_EVIDENCE"
    | null;
  highlighted_candidate_ref: string | null;
  candidates: NavigationCopilotCandidate[];
  outcome: {
    action: string;
    candidate_miss: boolean;
    user_corrected: boolean;
    record_semantics: "OPERATIONAL_FEEDBACK_ONLY";
    semantic_approval: false;
    gold_eligible: false;
    patch_eligible: false;
  } | null;
  navigation_target_ref: string | null;
}

export interface ValidationVariant {
  variant_ref: string;
  category_id: string;
  resource_id: string;
  version: string;
  benchmark_role: string;
  node_count: number;
  scenario_count: number;
}

export interface ValidationDataset {
  dataset_ref: string;
  title: string;
  fictional: true;
  gold_eligible: false;
  limitations: string[];
  variants: ValidationVariant[];
}

export interface ValidationDatasetCatalog {
  schema_version: "validation-dataset-catalog.v1";
  items: ValidationDataset[];
}

export interface ValidationExpected {
  intent_review_status: string;
  candidate_status: string | null;
  record_status: string | null;
  semantic_approval: false | null;
  gold_eligible: false | null;
  patch_eligible: false | null;
}

export interface ValidationScenario {
  scenario_ref: string;
  purpose: string;
  flow: string;
  request: {
    requirement_text: string;
    proposed_parent_ref: string | null;
    node_kind_hint: "CONCEPT" | "PROPERTY" | "UNKNOWN";
    value_type_hint: string | null;
    cardinality_hint: "SINGLE" | "MULTIPLE" | "UNKNOWN";
  };
  expected: ValidationExpected;
}

export interface ValidationScenarioList {
  schema_version: "validation-scenarios.v1";
  dataset_ref: string;
  variant_ref: string;
  benchmark_role: string;
  fictional: true;
  gold_eligible: false;
  items: ValidationScenario[];
}

export interface ValidationComparison {
  schema_version: "validation-comparison.v1";
  case_ref: string;
  dataset_ref: string;
  variant_ref: string;
  scenario_ref: string;
  case_status: string;
  status: "IN_PROGRESS" | "MATCH" | "MISMATCH" | "RUN_FAILED";
  fictional: true;
  gold_eligible: false;
  items: Array<{
    metric: string;
    expected: string | boolean;
    actual: string | boolean | null;
    status: "PENDING" | "MATCH" | "MISMATCH" | "NOT_OBSERVED";
  }>;
  limitations: string[];
}

export interface GovernanceCaseCreateInput {
  resource_id: string;
  version: string;
  requirement_text: string;
  proposed_parent_ref: string | null;
  node_kind_hint: "CONCEPT" | "PROPERTY" | "UNKNOWN";
  value_type_hint: string | null;
  cardinality_hint: "SINGLE" | "MULTIPLE" | "UNKNOWN";
  model_mode: GovernanceModelMode;
  external_data_approved: boolean;
}

async function requestJSON<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    method: init.method ?? "GET",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    cache: "no-store",
    credentials: "same-origin",
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const error = payload as Partial<ErrorResponse>;
    throw new WorkbenchAPIError(error.error_code ?? "WORKBENCH_REQUEST_FAILED");
  }
  return payload as T;
}

export async function fetchCategories(): Promise<CategoryItem[]> {
  const response =
    await requestJSON<ListResponse<CategoryItem>>("/api/v1/categories");
  return response.items;
}

export async function fetchResources(
  categoryId: string,
): Promise<ResourceItem[]> {
  const query = new URLSearchParams({ category_id: categoryId });
  const response = await requestJSON<ListResponse<ResourceItem>>(
    `/api/v1/resources?${query.toString()}`,
  );
  return response.items;
}

export async function fetchVersions(
  resourceId: string,
): Promise<VersionItem[]> {
  const encodedResource = encodeURIComponent(resourceId);
  const response = await requestJSON<ListResponse<VersionItem>>(
    `/api/v1/resources/${encodedResource}/versions`,
  );
  return response.items;
}

export async function fetchTree(
  resourceId: string,
  version: string,
): Promise<TreeView> {
  const encodedResource = encodeURIComponent(resourceId);
  const query = new URLSearchParams({ version });
  return requestJSON<TreeView>(
    `/api/v1/resources/${encodedResource}/tree?${query.toString()}`,
  );
}

export async function fetchValidationDatasets(): Promise<ValidationDatasetCatalog> {
  return requestJSON<ValidationDatasetCatalog>(
    "/api/v1/validation/datasets",
  );
}

export async function fetchValidationScenarios(
  datasetRef: string,
  variantRef: string,
): Promise<ValidationScenarioList> {
  const query = new URLSearchParams({ variant_ref: variantRef });
  return requestJSON<ValidationScenarioList>(
    `/api/v1/validation/datasets/${encodeURIComponent(datasetRef)}/scenarios?${query.toString()}`,
  );
}

export async function createValidationRun(input: {
  dataset_ref: string;
  variant_ref: string;
  scenario_ref: string;
  model_mode: GovernanceModelMode;
  external_data_approved: boolean;
}): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    "/api/v1/validation/runs",
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export async function fetchValidationComparison(
  caseRef: string,
): Promise<ValidationComparison> {
  return requestJSON<ValidationComparison>(
    `/api/v1/validation/runs/${encodeURIComponent(caseRef)}/comparison`,
  );
}

export async function createGovernanceCase(
  input: GovernanceCaseCreateInput,
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>("/api/v1/governance/cases", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function fetchGovernanceOperation(
  operationRef: string,
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    `/api/v1/governance/operations/${encodeURIComponent(operationRef)}`,
  );
}

export async function fetchGovernanceCase(
  caseRef: string,
): Promise<GovernanceCase> {
  return requestJSON<GovernanceCase>(
    `/api/v1/governance/cases/${encodeURIComponent(caseRef)}`,
  );
}

export async function fetchGovernanceModelTraces(
  caseRef: string,
): Promise<GovernanceModelTraceView> {
  return requestJSON<GovernanceModelTraceView>(
    `/api/v1/governance/cases/${encodeURIComponent(caseRef)}/model-traces`,
  );
}

export async function fetchNavigationCopilotCapability(): Promise<NavigationCopilotCapability> {
  return requestJSON<NavigationCopilotCapability>(
    "/api/v1/navigation-copilot/capability",
  );
}

export async function createNavigationCopilotCase(
  input: GovernanceCaseCreateInput,
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    "/api/v1/navigation-copilot/cases",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function fetchNavigationCopilotOperation(
  operationRef: string,
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    `/api/v1/navigation-copilot/operations/${encodeURIComponent(operationRef)}`,
  );
}

export async function fetchNavigationCopilotCase(
  caseRef: string,
): Promise<NavigationCopilotCase> {
  return requestJSON<NavigationCopilotCase>(
    `/api/v1/navigation-copilot/cases/${encodeURIComponent(caseRef)}`,
  );
}

export async function clarifyNavigationCopilotCase(
  caseRef: string,
  answerText: string,
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    `/api/v1/navigation-copilot/cases/${encodeURIComponent(caseRef)}/clarification`,
    { method: "POST", body: JSON.stringify({ answer_text: answerText }) },
  );
}

export async function completeNavigationCopilotCase(
  caseRef: string,
  input: {
    action: "SELECT_CANDIDATE" | "SELECT_OUTSIDE_CANDIDATE" | "REJECT_ALL" | "EXIT";
    selected_candidate_ref: string | null;
    selected_node_ref: string | null;
    rejection_disposition?: "PRESENT_NOT_FOUND" | "ABSENT" | "UNKNOWN" | null;
  },
): Promise<NavigationCopilotCase> {
  return requestJSON<NavigationCopilotCase>(
    `/api/v1/navigation-copilot/cases/${encodeURIComponent(caseRef)}/outcome`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function clarifyGovernanceCase(
  caseRef: string,
  answerText: string,
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    `/api/v1/governance/cases/${encodeURIComponent(caseRef)}/clarification`,
    {
      method: "POST",
      body: JSON.stringify({ answer_text: answerText }),
    },
  );
}

export async function reviewGovernanceIntent(
  caseRef: string,
  decision: "CONFIRM" | "REJECT",
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    `/api/v1/governance/cases/${encodeURIComponent(caseRef)}/intent-review`,
    {
      method: "POST",
      body: JSON.stringify({ decision }),
    },
  );
}

export async function reviewGovernanceRecommendation(
  caseRef: string,
  decision: "CONFIRM" | "REJECT",
  reviewerReasoning: string | null,
): Promise<GovernanceOperation> {
  return requestJSON<GovernanceOperation>(
    `/api/v1/governance/cases/${encodeURIComponent(caseRef)}/recommendation-review`,
    {
      method: "POST",
      body: JSON.stringify({
        decision,
        reviewer_reasoning: reviewerReasoning,
      }),
    },
  );
}
