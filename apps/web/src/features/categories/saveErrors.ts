import type { CategoryProblem } from "@/api/categories/categories.types";
import { validateCategory, validateList } from "@/features/categories/policy";
import { problemText } from "@/features/categories/problemText";
import type { Row } from "@/features/categories/rows";
import { duplicateText, parseSenders, senderErrors } from "@/features/categories/senders";
import type { SenderError } from "@/features/categories/senders";

/** What is wrong with one category; a field that is not there is fine. */
export interface RowErrors {
  name?: string;
  description?: string;
  senders?: SenderError[];
}

/** The errors per category key. */
export type ErrorsByRow = Record<string, RowErrors>;

/** A refusal as the api and the local rules both give it. */
export type Refusal = Pick<CategoryProblem, "rule" | "field" | "index" | "position" | "otherIndex">;

function nameOf(rows: readonly Row[], index: number | null, own: number | null): string | null {
  const other = index === null || index === own ? undefined : rows[index];
  return other?.name ?? null;
}

function senderTextOf(problem: Refusal, row: Row, rows: readonly Row[]): SenderError {
  const { entries, lines } = parseSenders(row.sendersText);
  const at = problem.position;
  const entry = at === null ? undefined : entries[at]?.entry;
  const line = at === null ? null : (lines[at] ?? null);
  if (problem.rule === "sender_duplicate" && entry !== undefined) {
    return { line, text: duplicateText(entry, nameOf(rows, problem.otherIndex, problem.index)) };
  }
  return { line, text: problemText(problem.rule) };
}

function partOf(problem: Refusal, row: Row, rows: readonly Row[], mine: RowErrors): RowErrors | null {
  if (problem.field === "name") {
    return { name: mine.name ?? problemText(problem.rule) };
  }
  if (problem.field === "description") {
    return { description: mine.description ?? problemText(problem.rule) };
  }
  return problem.field === "senders" ? { senders: [...(mine.senders ?? []), senderTextOf(problem, row, rows)] } : null;
}

function addProblem(errors: ErrorsByRow, problem: Refusal, rows: readonly Row[]): void {
  const row = problem.index === null ? undefined : rows[problem.index];
  const part = row === undefined ? null : partOf(problem, row, rows, errors[row.key] ?? {});
  if (row !== undefined && part !== null) {
    errors[row.key] = { ...errors[row.key], ...part };
  }
}

/** Maps problems with a category position and a field to messages; the first problem of a text field wins. */
export function errorsOf(problems: readonly Refusal[], rows: readonly Row[]): ErrorsByRow {
  const errors: ErrorsByRow = {};
  for (const problem of problems) {
    addProblem(errors, problem, rows);
  }
  return errors;
}

const noPosition = { position: null, otherIndex: null } as const;

/** The problems of one category that can be seen without the api: its name and description, and its senders. */
export function rowErrors(rows: readonly Row[], row: Row, settings: readonly string[]): ErrorsByRow {
  const index = rows.indexOf(row);
  const others = rows.filter((other) => other.key !== row.key).map((other) => other.name);
  const problems = validateCategory(row.name, row.description, others, settings).map((problem) => ({
    ...problem,
    ...noPosition,
    index,
  }));
  const errors = errorsOf(problems, rows);
  const senders = senderErrors(rows, row);
  return senders.length > 0 ? { ...errors, [row.key]: { ...errors[row.key], senders } } : errors;
}

/** Everything the draft gets wrong that can be seen without the api, per category. */
export function draftErrors(rows: readonly Row[], settings: readonly string[]): ErrorsByRow {
  const merged: ErrorsByRow = {};
  const named = errorsOf(
    validateList(rows, settings).map((problem) => ({ ...problem, ...noPosition })),
    rows,
  );
  for (const row of rows) {
    const senders = senderErrors(rows, row);
    const mine = { ...named[row.key], ...(senders.length > 0 ? { senders } : {}) };
    if (Object.keys(mine).length > 0) {
      merged[row.key] = mine;
    }
  }
  return merged;
}
