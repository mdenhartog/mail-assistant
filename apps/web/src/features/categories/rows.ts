import type { CategoryItem, CategoryList } from "@/api/categories/categories.types";
import { LABEL_PREFIX, normaliseName } from "@/features/categories/policy";
import { entryKey, parseSenders, textOfSenders } from "@/features/categories/senders";

/** One category card as the user is editing it. `key` is local; `id` is null until the api has stored it. */
export interface Row {
  key: string;
  id: string | null;
  name: string;
  description: string;
  mailCount: number | null;
  kind: CategoryItem["kind"];
  notify: boolean;
  /** The senders as the user edits them: one entry per line, see `senders.ts`. */
  sendersText: string;
  /** How often Gmail could not confirm each stored entry (only counts above 0), keyed by `entryKey`. Read-only: a save never sends it. */
  skipped: ReadonlyMap<string, number>;
}

/** What the edit view can change on a row. */
export type RowPatch = Partial<Pick<Row, "name" | "description" | "kind" | "notify" | "sendersText">>;

/** A new category: a topic without tick or senders. */
export function blankRow(key: string, name: string): Row {
  return { key, id: null, name, description: "", mailCount: null, kind: "topic", notify: false, sendersText: "", skipped: new Map() };
}

export function rowsOf(list: CategoryList): Row[] {
  return list.categories.map((category) => ({
    key: category.id,
    id: category.id,
    name: category.name,
    description: category.description,
    mailCount: category.mailCount,
    kind: category.kind,
    notify: category.notify,
    sendersText: textOfSenders(category.senders),
    skipped: new Map(category.senders.filter((sender) => sender.skippedCount > 0).map((sender) => [entryKey(sender.entry), sender.skippedCount])),
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

/** The senders as one comparable text, so blank lines and spaces are not a change. */
function sendersKey(text: string): string {
  return textOfSenders(parseSenders(text).entries);
}

function differs(row: Row, stored: CategoryItem | undefined): boolean {
  return (
    stored === undefined ||
    row.id !== stored.id ||
    row.name !== stored.name ||
    row.description !== stored.description ||
    row.kind !== stored.kind ||
    row.notify !== stored.notify ||
    sendersKey(row.sendersText) !== textOfSenders(stored.senders)
  );
}

/** Whether the draft differs from the stored list in order or in any field of a category. */
export function isDirty(rows: readonly Row[], list: CategoryList, instructions: string): boolean {
  return (
    instructions !== list.generalInstructions ||
    rows.length !== list.categories.length ||
    rows.some((row, index) => differs(row, list.categories[index]))
  );
}

/** One thing a save does, with the names it concerns. Renames carry the stored name and the new one. */
export type Change =
  | { kind: "rename"; from: string; to: string }
  | { kind: "describe"; name: string }
  | { kind: "retype"; name: string }
  | { kind: "notify"; name: string; on: boolean }
  | { kind: "senders"; name: string }
  | { kind: "instructions" }
  | { kind: "remove"; name: string }
  | { kind: "add"; name: string };

function fieldChanges(row: Row, before: CategoryItem): Change[] {
  const changes: Change[] = [];
  if (before.name !== row.name) {
    changes.push({ kind: "rename", from: before.name, to: row.name });
  }
  if (before.description !== row.description) {
    changes.push({ kind: "describe", name: row.name });
  }
  if (before.kind !== row.kind) {
    changes.push({ kind: "retype", name: row.name });
  }
  if (before.notify !== row.notify) {
    changes.push({ kind: "notify", name: row.name, on: row.notify });
  }
  if (sendersKey(row.sendersText) !== textOfSenders(before.senders)) {
    changes.push({ kind: "senders", name: row.name });
  }
  return changes;
}

/** What a save will do against the stored list: the list's instructions, each category's changes, removals, then additions. */
export function changesOf(rows: readonly Row[], list: CategoryList, instructions: string): Change[] {
  const stored = new Map(list.categories.map((category) => [category.id, category]));
  const kept = new Set(rows.map((row) => row.id));
  return [
    ...(instructions === list.generalInstructions ? [] : [{ kind: "instructions" } as const]),
    ...rows.flatMap((row) => {
      const before = row.id === null ? undefined : stored.get(row.id);
      return before === undefined ? [] : fieldChanges(row, before);
    }),
    ...list.categories.filter((category) => !kept.has(category.id)).map((category): Change => ({ kind: "remove", name: category.name })),
    ...rows.filter((row) => row.id === null).map((row): Change => ({ kind: "add", name: row.name })),
  ];
}
