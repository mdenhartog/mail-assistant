import { describe, expect, it } from "vitest";

import type { Row } from "@/features/categories/rows";
import { buildTree, visibleTree } from "@/features/categories/tree";
import type { TreeNode } from "@/features/categories/tree";

const row = (name: string, notify = false): Row => ({
  key: name,
  id: name,
  name,
  description: "d",
  mailCount: 0,
  kind: "topic",
  notify,
  sendersText: "",
});

const shape = (nodes: readonly TreeNode[]): unknown[] =>
  nodes.map((node) => [node.path, node.row === null ? "group" : "category", shape(node.children)]);

describe("the category tree", () => {
  it("nests names by their path; a parent that is a category keeps its row, a missing parent is a group", () => {
    const tree = buildTree([row("Huis"), row("Huis/Energie"), row("Reizen/Vliegtuig"), row("Werk")]);
    expect(shape(tree)).toEqual([
      ["huis", "category", [["huis/energie", "category", []]]],
      ["reizen", "group", [["reizen/vliegtuig", "category", []]]],
      ["werk", "category", []],
    ]);
    expect(tree[1]?.children[0]?.label).toBe("Vliegtuig");
  });

  it("merges parents that differ only in letter case", () => {
    const tree = buildTree([row("Huis/A"), row("huis/B")]);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.children).toHaveLength(2);
  });

  it("filters by search on the full name and keeps the parents of a match", () => {
    const tree = buildTree([row("Huis/Energie"), row("Huis/Water"), row("Werk")]);
    expect(shape(visibleTree(tree, { query: "ener", notifyOnly: false }))).toEqual([
      ["huis", "group", [["huis/energie", "category", []]]],
    ]);
    expect(shape(visibleTree(tree, { query: "huis/w", notifyOnly: false }))).toEqual([
      ["huis", "group", [["huis/water", "category", []]]],
    ]);
  });

  it("filters to the categories that always notify", () => {
    const tree = buildTree([row("A", true), row("B"), row("C/D", true)]);
    expect(shape(visibleTree(tree, { query: "", notifyOnly: true }))).toEqual([
      ["a", "category", []],
      ["c", "group", [["c/d", "category", []]]],
    ]);
  });

  it("shows everything without a filter", () => {
    const tree = buildTree([row("A"), row("B")]);
    expect(visibleTree(tree, { query: "  ", notifyOnly: false })).toEqual(tree);
  });
});
