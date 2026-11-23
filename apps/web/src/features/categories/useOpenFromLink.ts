import { useEffect } from "react";
import { useSearchParams } from "react-router";

import type { Row } from "@/features/categories/rows";

/** The query parameter that names the category whose edit view a link opens (Review moves tips link here). */
export const EDIT_PARAM = "edit";

/**
 * Opens the edit view of the category named by `?edit=<id>` once, then removes the parameter so a reload or Back
 * does not open it again. An id that is not in the list opens nothing; the value is only compared, never shown.
 */
export function useOpenFromLink(rows: readonly Row[], open: (key: string) => void): void {
  const [params, setParams] = useSearchParams();
  const wanted = params.get(EDIT_PARAM);
  useEffect(() => {
    if (wanted === null) {
      return;
    }
    const row = rows.find((candidate) => candidate.id === wanted);
    if (row !== undefined) {
      open(row.key);
    }
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete(EDIT_PARAM);
        return next;
      },
      { replace: true },
    );
    // Runs once per link: the rows and `open` change on every keystroke and must not re-open the view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted]);
}
