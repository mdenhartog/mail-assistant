import type { ReactElement } from "react";
import { Link } from "react-router";

import { EDIT_PARAM } from "@/features/categories/useOpenFromLink";
import { TIP_LABEL } from "@/features/review/copy";
import { cleanText } from "@/features/review/text";
import { paths } from "@/router/paths";

export interface TipBlockProps {
  /** The tip as the model wrote it: untrusted, so it only ever becomes a React text node. */
  tip: string;
  /** The category the tip is about; null when it is the built-in Other, which has no edit view. */
  categoryId: string | null;
  categoryName: string;
}

/**
 * The tip of a category: plain text (never HTML, never turned into a link), labelled as a suggestion, and a link to the
 * edit view of that category. The link is ours (`?edit=<id>`); nothing from the tip goes into it.
 */
export function TipBlock({ tip, categoryId, categoryName }: TipBlockProps): ReactElement {
  return (
    <aside aria-label={`Tip for ${categoryName}`} className="mt-3 rounded-control border border-border p-3">
      <p className="m-0 text-sm font-semibold text-text-muted">{TIP_LABEL}</p>
      <p className="mt-1 whitespace-pre-line text-text wrap-anywhere">{cleanText(tip)}</p>
      {categoryId === null ? null : (
        <p className="mt-2">
          <Link
            className="inline-flex min-h-11 items-center font-semibold text-primary underline wrap-anywhere"
            to={`${paths.categories}?${EDIT_PARAM}=${encodeURIComponent(categoryId)}`}
          >
            {`Open the edit view of ${categoryName}`}
          </Link>
        </p>
      )}
    </aside>
  );
}
