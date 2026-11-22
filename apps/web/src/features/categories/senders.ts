import type { CategoryInput, CategoryItem } from "@/api/categories/categories.types";

/** A sender entry as a save carries it: the read-only `skippedCount` of a read is not part of it. */
type SenderEntries = CategoryInput["senders"];

/** The most senders one category may list (C-4 of the spec); the api checks again. */
export const MAX_SENDERS = 100;

/** Written after a domain to say that its subdomains count too: `example.nl +subdomains`. */
const SUBDOMAINS_MARKER = "+subdomains";

const MARKED = /^(.*\S)\s+\+subdomains$/i;

/** The sender entries of a text, and for each the 1-based line it was written on (blank lines are skipped). */
export interface ParsedSenders {
  entries: SenderEntries;
  lines: number[];
}

/** The text the user edits: one entry per line, `+subdomains` after an entry that includes its subdomains. */
export function textOfSenders(senders: SenderEntries): string {
  return senders.map((sender) => (sender.subdomains ? `${sender.entry} ${SUBDOMAINS_MARKER}` : sender.entry)).join("\n");
}

/** Reads the text back into the api's `{entry, subdomains}` list. */
export function parseSenders(text: string): ParsedSenders {
  const entries: SenderEntries = [];
  const lines: number[] = [];
  text.split("\n").forEach((raw, index) => {
    const line = raw.trim();
    if (line === "") {
      return;
    }
    const marked = MARKED.exec(line);
    entries.push({ entry: marked?.[1] ?? line, subdomains: marked !== null });
    lines.push(index + 1);
  });
  return { entries, lines };
}

/** One thing wrong with the sender text; `line` is null when it is about the whole text. */
export interface SenderError {
  line: number | null;
  text: string;
}

/** The part of a row the sender checks need. */
export interface SenderScope {
  key: string;
  name: string;
  kind: CategoryItem["kind"];
  sendersText: string;
}

/** The comparable form of an entry: trimmed and lower case. */
export const entryKey = (entry: string): string => entry.trim().toLowerCase();
const keyOf = entryKey;

function conflictText(entry: string, otherName: string): string {
  return `${entry} is already in ${otherName}. Remove it there first.`;
}

/**
 * What is wrong with the senders of `row`, as it can be seen without the api: too many, an entry twice, or an entry that
 * another category of the same kind already has (at most one topic and one extra label may list an entry).
 */
export function senderErrors(rows: readonly SenderScope[], row: SenderScope): SenderError[] {
  const { entries, lines } = parseSenders(row.sendersText);
  const owners = new Map<string, string>();
  for (const other of rows) {
    if (other.key !== row.key && other.kind === row.kind) {
      for (const sender of parseSenders(other.sendersText).entries) {
        owners.set(keyOf(sender.entry), other.name);
      }
    }
  }
  const seen = new Set<string>();
  const errors: SenderError[] = [];
  entries.forEach(({ entry }, index) => {
    const line = lines[index] ?? null;
    const owner = owners.get(keyOf(entry));
    if (seen.has(keyOf(entry))) {
      errors.push({ line, text: `${entry} is listed twice in this category.` });
    } else if (owner !== undefined) {
      errors.push({ line, text: conflictText(entry, owner) });
    }
    seen.add(keyOf(entry));
  });
  return entries.length > MAX_SENDERS
    ? [...errors, { line: null, text: `A category can list at most ${String(MAX_SENDERS)} senders.` }]
    : errors;
}

/** The text of the api's `sender_duplicate` for the entry written at that place. */
export function duplicateText(entry: string, otherName: string | null): string {
  return otherName === null ? `${entry} is listed twice in this category.` : conflictText(entry, otherName);
}
