import { useId } from "react";
import type { ReactElement } from "react";

import { sendersCountText } from "@/features/categories/copy";
import { parseSenders } from "@/features/categories/senders";
import type { TreeNode } from "@/features/categories/tree";

export interface CategoryRowProps {
  node: TreeNode;
  /** Whether the children are shown; only meaningful when the node has children. */
  open: boolean;
  onToggle: (path: string) => void;
  onEdit: (key: string) => void;
  onNotify: (key: string, on: boolean) => void;
}

const KIND_WORD = { topic: "Topic", extra: "Extra label" } as const;

function Expander({ node, open, onToggle }: Pick<CategoryRowProps, "node" | "open" | "onToggle">): ReactElement {
  if (node.children.length === 0) {
    return <span aria-hidden="true" className="min-w-11" />;
  }
  const name = node.row?.name ?? node.label;
  return (
    <button
      aria-expanded={open}
      aria-label={`${open ? "Collapse" : "Expand"} ${name}`}
      className="min-h-11 min-w-11 cursor-pointer rounded-control text-text"
      onClick={() => {
        onToggle(node.path);
      }}
      type="button"
    >
      <span aria-hidden="true">{open ? "▾" : "▸"}</span>
    </button>
  );
}

/**
 * One line of the list. A category is a button that opens its edit view (name, kind as a word, sender count) and a
 * tick for Always notify; a group (a parent that is no category itself) is only a name. Every text is rendered as
 * text, so a name with markup stays inert.
 */
export function CategoryRow({ node, open, onToggle, onEdit, onNotify }: CategoryRowProps): ReactElement {
  const { row } = node;
  const descriptionId = useId();
  return (
    <div className="flex items-center gap-1 border-b border-divider py-1">
      <Expander node={node} onToggle={onToggle} open={open} />
      {row === null ? (
        <span className="min-w-0 flex-1 py-2 font-semibold text-text wrap-anywhere">{node.label}</span>
      ) : (
        <>
          <button
            aria-describedby={descriptionId}
            aria-label={`Edit ${row.name}`}
            className="flex min-h-11 min-w-0 flex-1 cursor-pointer flex-wrap items-center gap-x-2 rounded-control py-2 text-left text-text"
            data-edit=""
            onClick={() => {
              onEdit(row.key);
            }}
            type="button"
          >
            <span className="font-semibold wrap-anywhere">{node.label === "" ? "Unnamed category" : node.label}</span>
            {/* Kept out of the visible label so the name "Edit <name>" holds the visible name (WCAG 2.5.3); the
                description still tells a screen reader the kind and the sender count. */}
            <span aria-hidden="true" className="contents" id={descriptionId}>
              <span className="rounded-pill border border-border px-2 text-sm text-text-muted">{KIND_WORD[row.kind]}</span>
              <span className="text-sm text-text-muted">{sendersCountText(parseSenders(row.sendersText).entries.length)}</span>
            </span>
          </button>
          <label className="inline-grid min-h-11 min-w-11 flex-none cursor-pointer place-items-center">
            <input
              aria-label={`Always notify, ${row.name}`}
              checked={row.notify}
              className="size-11 cursor-pointer"
              onChange={(event) => {
                onNotify(row.key, event.target.checked);
              }}
              type="checkbox"
            />
          </label>
        </>
      )}
    </div>
  );
}
