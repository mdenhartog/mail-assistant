import type { CategoryList } from "@/api/categories/categories.types";
import { LABEL_PREFIX, normaliseName } from "@/features/categories/policy";

/** One category card as the user is editing it. `key` is local; `id` is null until the api has stored it. */
export interface Row {
  key: string;
  id: string | null;
  name: string;
  description: string;
  mailCount: number | null;
}

export type RowField = "name" | "description";

export function rowsOf(list: CategoryList): Row[] {
  return list.categories.map((category) => ({
    key: category.id,
    id: category.id,
    name: category.name,
    description: category.description,
    mailCount: category.mailCount,
  }));
}

/** The name an older label gets as a card: the label without its `Assistant/` prefix. */
export function nameOfLabel(labelName: string): string {
  return labelName.startsWith(LABEL_PREFIX) ? labelName.slice(LABEL_PREFIX.length) : labelName;
}

/** The older labels the draft does not already carry as a card. */
export function openOlder(list: CategoryList, rows: readonly Row[]): CategoryList["olderCategories"] {
  const taken = new Set(rows.map((row) => normaliseName(row.name)));
  return list.olderCategories.filter((older) => !taken.has(normaliseName(nameOfLabel(older.labelName))));
}

/** Whether the draft differs from the stored list in order, name or description. */
export function isDirty(rows: readonly Row[], list: CategoryList): boolean {
  return (
    rows.length !== list.categories.length ||
    rows.some((row, index) => {
      const stored = list.categories[index];
      return stored === undefined || row.id !== stored.id || row.name !== stored.name || row.description !== stored.description;
    })
  );
}

/** What a save will do, counted against the stored list. */
export interface Summary {
  renamed: number;
  described: number;
  added: number;
  removed: number;
}

/** How many changes a save would make: one per renamed, re-described, added or removed category. */
export function changeCount({ renamed, described, added, removed }: Summary): number {
  return renamed + described + added + removed;
}

export function summaryOf(rows: readonly Row[], list: CategoryList): Summary {
  const stored = new Map(list.categories.map((category) => [category.id, category]));
  const kept = new Set(rows.map((row) => row.id));
  const before = (row: Row) => (row.id === null ? undefined : stored.get(row.id));
  return {
    renamed: rows.filter((row) => before(row) !== undefined && before(row)?.name !== row.name).length,
    described: rows.filter((row) => before(row) !== undefined && before(row)?.description !== row.description).length,
    added: rows.filter((row) => row.id === null).length,
    removed: list.categories.filter((category) => !kept.has(category.id)).length,
  };
}
