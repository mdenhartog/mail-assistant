import { useId } from "react";
import type { ReactElement } from "react";

import type { OlderCategory } from "@/api/categories/categories.types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { countText } from "@/features/categories/copy";
import { nameOfLabel } from "@/features/categories/rows";

export interface OlderCategoriesProps {
  older: readonly OlderCategory[];
  onAdopt: (labelName: string) => void;
}

/** Gmail labels under `Assistant/` that are not on the list, each with "Add to my list" (AC-53). */
export function OlderCategories({ older, onAdopt }: OlderCategoriesProps): ReactElement | null {
  const headingId = useId();
  if (older.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 className="font-display text-xl text-text" id={headingId}>
        {older.length === 1 ? "Older category" : "Older categories"}
      </h2>
      <p className="text-sm text-text-muted">Labels you already have in Gmail that are not on your list.</p>
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {older.map((item) => {
          const name = nameOfLabel(item.labelName);
          return (
            <li key={item.labelName}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0 wrap-anywhere">
                    <p className="font-semibold text-text">{name}</p>
                    <p className="text-sm text-text-muted">
                      {item.mailCount === null ? "Not counted yet" : countText(item.mailCount)}
                    </p>
                  </div>
                  <Button
                    aria-label={`Add to my list: ${name}`}
                    onClick={() => {
                      onAdopt(item.labelName);
                    }}
                  >
                    Add to my list
                  </Button>
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
