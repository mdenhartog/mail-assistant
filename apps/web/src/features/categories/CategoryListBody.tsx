import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { CategoryTree } from "@/features/categories/CategoryTree";
import { ListToolbar } from "@/features/categories/ListToolbar";
import { buildTree, isFiltering, visibleTree } from "@/features/categories/tree";
import type { TreeNode } from "@/features/categories/tree";
import type { CategoriesFlow } from "@/features/categories/useCategoriesFlow";
import type { ListView } from "@/features/categories/useListView";

export interface CategoryListBodyProps {
  flow: CategoriesFlow;
  view: ListView;
  onEdit: (key: string) => void;
  onNotify: (key: string, on: boolean) => void;
  onAdd: () => void;
  onUndo: () => void;
  /** While a save is on its way, the list cannot be changed. */
  locked: boolean;
}

function countCategories(nodes: readonly TreeNode[]): number {
  return nodes.reduce((sum, node) => sum + (node.row === null ? 0 : 1) + countCategories(node.children), 0);
}

/** Takes the place of the category that was removed, and says what saving does with it. */
function RemovedNotice({ name, onUndo }: { name: string; onUndo: () => void }): ReactElement {
  return (
    <Banner action={{ label: "Undo", onClick: onUndo }} kind="info" title={`Removed ${name}.`}>
      It is removed when you save. Mail already filed under it stays where it is.
    </Banner>
  );
}

/** The search, the collapsed list, and Add category; or the empty state when there is nothing yet. */
export function CategoryListBody({ flow, view, onEdit, onNotify, onAdd, onUndo, locked }: CategoryListBodyProps): ReactElement {
  const filtering = isFiltering(view.filter);
  const nodes = visibleTree(buildTree(flow.rows), view.filter);
  return (
    <fieldset className="flex min-w-0 flex-col gap-6" disabled={locked}>
      {flow.removed === null ? null : <RemovedNotice name={flow.removed.row.name} onUndo={onUndo} />}
      {flow.rows.length === 0 ? (
        <p className="text-text">You have no categories yet.</p>
      ) : (
        <>
          <ListToolbar shown={filtering ? countCategories(nodes) : null} view={view} />
          <CategoryTree
            expanded={view.expanded}
            label="Category list"
            nodes={nodes}
            onEdit={onEdit}
            onNotify={onNotify}
            onToggle={view.toggle}
            openAll={filtering}
          />
        </>
      )}
      <div>
        <Button disabled={!flow.canAdd} onClick={onAdd}>
          Add category
        </Button>
        {flow.canAdd ? null : (
          <p className="mt-2 text-sm text-text-muted">You have reached the limit of 100 categories. Remove one to add another.</p>
        )}
      </div>
    </fieldset>
  );
}
