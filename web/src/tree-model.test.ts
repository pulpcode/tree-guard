import { describe, expect, it } from "vitest";

import type { TreeViewNode } from "./api";
import { buildTreeData, filterTreeData, searchTree } from "./tree-model";

const nodes: TreeViewNode[] = [
  {
    ref: "N000001",
    parent_ref: null,
    child_refs: ["N000002"],
    name: "虚构博物馆",
    label: "MUSEUM",
    kind: "CONCEPT",
    value_type: null,
    cardinality: null,
    order: 1,
    breadcrumb: ["虚构博物馆"],
  },
  {
    ref: "N000002",
    parent_ref: "N000001",
    child_refs: ["N000003"],
    name: "展品尺寸",
    label: "DIMENSIONS",
    kind: "PROPERTY",
    value_type: "class",
    cardinality: "single",
    order: 1,
    breadcrumb: ["虚构博物馆", "展品尺寸"],
  },
  {
    ref: "N000003",
    parent_ref: "N000002",
    child_refs: [],
    name: "陈列高度",
    label: "HEIGHT",
    kind: "PROPERTY",
    value_type: "float",
    cardinality: "single",
    order: 1,
    breadcrumb: ["虚构博物馆", "展品尺寸", "陈列高度"],
  },
];

describe("tree model", () => {
  it("builds a deterministic hierarchy", () => {
    const tree = buildTreeData(nodes, ["N000001"]);

    expect(tree).toHaveLength(1);
    expect(tree[0].children?.[0].children?.[0].key).toBe("N000003");
  });

  it("finds names or labels and expands every ancestor", () => {
    expect(searchTree(nodes, "高度")).toEqual({
      matchedRefs: ["N000003"],
      expandedRefs: ["N000002", "N000001"],
    });
    expect(searchTree(nodes, "DIMENSIONS").matchedRefs).toEqual(["N000002"]);
  });

  it("returns an empty search for whitespace", () => {
    expect(searchTree(nodes, "   ")).toEqual({
      matchedRefs: [],
      expandedRefs: [],
    });
  });

  it("filters the visible tree to matches and their ancestors", () => {
    const tree = buildTreeData(nodes, ["N000001"]);
    const filtered = filterTreeData(tree, new Set(["N000003"]));

    expect(filtered).toHaveLength(1);
    expect(filtered[0].children?.[0].children?.[0].key).toBe("N000003");
    expect(filtered[0].children?.[0].children).toHaveLength(1);
  });

  it("rejects detached nodes", () => {
    expect(() => buildTreeData(nodes, ["N000002"])).toThrow(
      "WORKBENCH_TREE_RELATION_INVALID",
    );
  });
});
