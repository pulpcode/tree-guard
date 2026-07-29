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

async function requestJSON<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    method: "GET",
    headers: { Accept: "application/json" },
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
