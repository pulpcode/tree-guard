import type { DataNode } from "antd/es/tree";

import type { TreeViewNode } from "./api";

export interface WorkbenchTreeNode extends DataNode {
  key: string;
  title: string;
  source: TreeViewNode;
  children?: WorkbenchTreeNode[];
}

export interface TreeSearchResult {
  matchedRefs: string[];
  expandedRefs: string[];
}

export function buildTreeData(
  nodes: TreeViewNode[],
  rootRefs: string[],
): WorkbenchTreeNode[] {
  const sourceByRef = new Map(nodes.map((node) => [node.ref, node]));
  const visited = new Set<string>();

  const build = (ref: string): WorkbenchTreeNode => {
    const source = sourceByRef.get(ref);
    if (!source || visited.has(ref)) {
      throw new Error("WORKBENCH_TREE_RELATION_INVALID");
    }
    visited.add(ref);
    const children = source.child_refs.map(build);
    return {
      key: source.ref,
      title: source.name,
      source,
      children: children.length > 0 ? children : undefined,
    };
  };

  const roots = rootRefs.map(build);
  if (visited.size !== nodes.length) {
    throw new Error("WORKBENCH_TREE_RELATION_INVALID");
  }
  return roots;
}

export function searchTree(
  nodes: TreeViewNode[],
  rawTerm: string,
): TreeSearchResult {
  const term = rawTerm.trim().toLocaleLowerCase();
  if (!term) {
    return { matchedRefs: [], expandedRefs: [] };
  }

  const parentByRef = new Map(
    nodes.map((node) => [node.ref, node.parent_ref]),
  );
  const matchedRefs = nodes
    .filter(
      (node) =>
        node.name.toLocaleLowerCase().includes(term) ||
        node.label.toLocaleLowerCase().includes(term),
    )
    .map((node) => node.ref);
  const expanded = new Set<string>();
  for (const ref of matchedRefs) {
    let parent = parentByRef.get(ref) ?? null;
    while (parent !== null) {
      if (expanded.has(parent)) {
        break;
      }
      expanded.add(parent);
      parent = parentByRef.get(parent) ?? null;
    }
  }
  return {
    matchedRefs,
    expandedRefs: [...expanded],
  };
}

export function filterTreeData(
  nodes: WorkbenchTreeNode[],
  matchedRefs: ReadonlySet<string>,
): WorkbenchTreeNode[] {
  const filtered: WorkbenchTreeNode[] = [];
  for (const node of nodes) {
    const children = filterTreeData(node.children ?? [], matchedRefs);
    if (matchedRefs.has(node.key) || children.length > 0) {
      filtered.push({
        ...node,
        children: children.length > 0 ? children : undefined,
      });
    }
  }
  return filtered;
}
