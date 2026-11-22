import type { ReactElement } from "react";

import { CategoryRow } from "@/features/categories/CategoryRow";
import type { TreeNode } from "@/features/categories/tree";

export interface CategoryTreeProps {
  nodes: readonly TreeNode[];
  /** True while a search or filter is on: every parent of a match is open. */
  openAll: boolean;
  expanded: ReadonlySet<string>;
  onToggle: (path: string) => void;
  onEdit: (key: string) => void;
  onNotify: (key: string, on: boolean) => void;
  label?: string;
  nested?: boolean;
}

/**
 * The categories as real nested lists: one `li` per category or group, its children in a nested `ul` that is
 * only rendered while the parent is open.
 */
export function CategoryTree({ nodes, openAll, expanded, onToggle, onEdit, onNotify, label, nested = false }: CategoryTreeProps): ReactElement {
  return (
    <ul aria-label={label} className={nested ? "ml-4 border-l border-divider pl-2" : ""}>
      {nodes.map((node) => {
        const open = openAll || expanded.has(node.path);
        return (
          <li data-row-key={node.row?.key} key={node.row?.key ?? `group:${node.path}`}>
            <CategoryRow node={node} onEdit={onEdit} onNotify={onNotify} onToggle={onToggle} open={open} />
            {open && node.children.length > 0 ? (
              <CategoryTree expanded={expanded} nested nodes={node.children} onEdit={onEdit} onNotify={onNotify} onToggle={onToggle} openAll={openAll} />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
