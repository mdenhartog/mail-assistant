import { useId } from "react";
import type { ReactElement } from "react";

import { MAX_SENDER_LENGTH } from "@/api/plan/plan.types";
import type { ItemSort } from "@/api/plan/plan.types";
import { Button } from "@/components/Button";

export const SORT_LABELS: Record<ItemSort, string> = {
  default: "Default order",
  "sender-asc": "Sender A to Z",
  "sender-desc": "Sender Z to A",
  "subject-asc": "Subject A to Z",
  "subject-desc": "Subject Z to A",
};

const SORTS: ItemSort[] = ["default", "sender-asc", "sender-desc", "subject-asc", "subject-desc"];

const CONTROL =
  "min-h-11 w-full rounded-control border-2 border-border bg-surface-raised px-3 text-text " +
  "motion-safe:transition-colors motion-safe:duration-200";

export interface ItemFilterBarProps {
  text: string;
  sort: ItemSort;
  onText: (text: string) => void;
  onSort: (sort: ItemSort) => void;
}

/**
 * The sender search and the sort choice above the mails of a group. Both are native controls with a visible label, so
 * the keyboard and a screen reader work as they expect. The search text is kept in memory only (AC-59).
 */
export function ItemFilterBar({ text, sort, onText, onSort }: ItemFilterBarProps): ReactElement {
  const searchId = useId();
  const sortId = useId();
  return (
    <div className="mb-3 grid gap-3 sm:grid-cols-2">
      <div className="flex flex-col gap-1">
        <label className="font-semibold text-text" htmlFor={searchId}>
          Search by sender
        </label>
        <div className="flex gap-2">
          <input
            autoComplete="off"
            className={CONTROL}
            id={searchId}
            maxLength={MAX_SENDER_LENGTH}
            onChange={(event) => {
              onText(event.target.value);
            }}
            spellCheck={false}
            type="search"
            value={text}
          />
          {text === "" ? null : (
            <Button
              aria-label="Clear search"
              onClick={() => {
                onText("");
              }}
              variant="ghost"
            >
              Clear
            </Button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label className="font-semibold text-text" htmlFor={sortId}>
          Sort mails
        </label>
        <select
          className={CONTROL}
          id={sortId}
          onChange={(event) => {
            const next = SORTS.find((value) => value === event.target.value);
            if (next !== undefined) {
              onSort(next);
            }
          }}
          value={sort}
        >
          {SORTS.map((value) => (
            <option key={value} value={value}>
              {SORT_LABELS[value]}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
