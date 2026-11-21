import type { CategoryItem, CategoryList } from "@/api/categories/categories.types";
import { LABEL_PREFIX, normaliseName } from "@/features/categories/policy";

/** One category card as the user is editing it. `key` is local; `id` is null until the api has stored it. */
export interface Row {
  key: string;
  id: string | null;
  name: string;
  description: string;
  mailCount: number | null;
  /** Carried untouched from the api until the screens that edit them exist; a new card is a topic without tick or senders. */
  kind: CategoryItem["kind"];
  notify: boolean;
  senders: CategoryItem["senders"];
}

export type RowField = "name" | "description";

export function rowsOf(list: CategoryList): Row[] {
  return list.categories.map((category) => ({
    key: category.id,
    id: category.id,
    name: category.name,
    description: category.description,
    mailCount: category.mailCount,
    kind: category.kind,
    notify: category.notify,
    senders: category.senders,
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

/** One thing a save does, with the names it concerns. Renames carry the stored name and the new one. */
export type Change =
  | { kind: "rename"; from: string; to: string }
  | { kind: "describe"; name: string }
  | { kind: "remove"; name: string }
  | { kind: "add"; name: string };

/** What a save will do against the stored list: renames, description changes, removals, then additions. */
export function changesOf(rows: readonly Row[], list: CategoryList): Change[] {
  const stored = new Map(list.categories.map((category) => [category.id, category]));
  const kept = new Set(rows.map((row) => row.id));
  const pairs = rows.flatMap((row) => {
    const before = row.id === null ? undefined : stored.get(row.id);
    return before === undefined ? [] : [{ row, before }];
  });
  return [
    ...pairs.filter(({ row, before }) => before.name !== row.name).map(({ row, before }): Change => ({ kind: "rename", from: before.name, to: row.name })),
    ...pairs.filter(({ row, before }) => before.description !== row.description).map(({ row }): Change => ({ kind: "describe", name: row.name })),
    ...list.categories.filter((category) => !kept.has(category.id)).map((category): Change => ({ kind: "remove", name: category.name })),
    ...rows.filter((row) => row.id === null).map((row): Change => ({ kind: "add", name: row.name })),
  ];
}
