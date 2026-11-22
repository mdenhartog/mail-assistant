import type { Row } from "@/features/categories/rows";

/** One line of the list: a category (with its row) or a group that only exists because names start with it. */
export interface TreeNode {
  /** The lower-case path, the stable id of the node. */
  path: string;
  /** The last part of the name, what the line shows. */
  label: string;
  row: Row | null;
  children: TreeNode[];
}

export interface ListFilter {
  query: string;
  notifyOnly: boolean;
}

/** The parts of a name, trimmed; an empty name has one empty part. */
function segmentsOf(name: string): string[] {
  return name.split("/").map((part) => part.trim());
}

/** Builds the tree from the names (`Huis/Energie` sits under `Huis`), keeping the order of first appearance. */
export function buildTree(rows: readonly Row[]): TreeNode[] {
  const roots: TreeNode[] = [];
  for (const row of rows) {
    let level = roots;
    let path = "";
    const parts = segmentsOf(row.name);
    parts.forEach((part, index) => {
      path = index === 0 ? part.toLowerCase() : `${path}/${part.toLowerCase()}`;
      let node = level.find((candidate) => candidate.path === path);
      if (node === undefined) {
        node = { path, label: part, row: null, children: [] };
        level.push(node);
      }
      if (index === parts.length - 1) {
        node.row = row;
      }
      level = node.children;
    });
  }
  return roots;
}

/** The ancestors of a name that must be open for the name to be seen. */
export function ancestorsOf(name: string): string[] {
  const parts = segmentsOf(name).map((part) => part.toLowerCase());
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join("/"));
}

/** Whether a filter is on, which shows every match open. */
export function isFiltering(filter: ListFilter): boolean {
  return filter.query.trim() !== "" || filter.notifyOnly;
}

function matches(row: Row, filter: ListFilter): boolean {
  const query = filter.query.trim().toLowerCase();
  return (!filter.notifyOnly || row.notify) && row.name.toLowerCase().includes(query);
}

/** The nodes that match the filter, with the parents of a match kept as context. */
export function visibleTree(nodes: readonly TreeNode[], filter: ListFilter): TreeNode[] {
  if (!isFiltering(filter)) {
    return [...nodes];
  }
  return nodes.flatMap((node) => {
    const children = visibleTree(node.children, filter);
    return children.length > 0 || (node.row !== null && matches(node.row, filter)) ? [{ ...node, children }] : [];
  });
}
