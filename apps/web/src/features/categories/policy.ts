/**
 * The name, description and list rules of a category, as the api and the agent apply them
 * (`packages/category-policy` v3, INT-004, INT-008, INT-010). The cases both runtimes must pass live in
 * `category_cases.json`; this file adds no rule of its own. The api stays the authority: it checks again.
 */

const SEGMENT_MAX = 40;
const LABEL_MAX = 255;
const DESCRIPTION_MAX = 1500;
/** The most characters the general instructions of the list may have (C-3). */
export const MAX_INSTRUCTIONS = 4000;
export const MAX_CATEGORIES = 100;
const SEPARATOR = "/";
/** The default name of the "Other" label; renaming it is not part of this page yet. */
export const OTHER_LABEL_DEFAULT = "Other";
const RESERVED_NAMES: readonly string[] = ["other", "archive"];
const GMAIL_SYSTEM_LABELS: readonly string[] = ["inbox", "spam", "trash", "sent", "draft", "starred", "unread", "important", "chat"];
const SYSTEM_LABEL_START = "category_";
const FORBIDDEN = /[\p{Cc}\p{Cf}]/u;

// Control and format characters and "..": the agent refuses a label with ".." too.
function hasForbidden(text: string): boolean {
  return text.includes("..") || FORBIDDEN.test(text);
}

export interface Problem {
  rule: string;
  field: "name" | "description" | "list";
  /** Position of the category in the list; null for a rule about the whole list. */
  index: number | null;
}

export interface CategoryText {
  name: string;
  description: string;
}

// Look-alikes of "/" that NFKC leaves alone (division slash; the full-width solidus NFKC folds itself).
const SLASH_LOOK_ALIKES = /[∕／]/g;

/** The segments of a name: look-alikes of "/" folded, NFKC, every segment trimmed (letter case kept). */
function segmentsOf(raw: string): string[] {
  const folded = raw.replace(SLASH_LOOK_ALIKES, SEPARATOR).normalize("NFKC").replace(SLASH_LOOK_ALIKES, SEPARATOR);
  return folded
    .trim()
    .split(SEPARATOR)
    .map((segment) => segment.trim());
}

/** The stored form of a name: every segment trimmed and joined with "/". */
function canonical(raw: string): string {
  return segmentsOf(raw).join(SEPARATOR);
}

function length(text: string): number {
  return Array.from(text).length;
}

/**
 * The comparison key of a name: trim, NFKC and case folding (upper then lower case stands in for
 * Python's `casefold`, so "Straße" and "STRASSE" meet).
 */
export function normaliseName(raw: string): string {
  return canonical(canonical(raw).toUpperCase().toLowerCase().normalize("NFKC").toUpperCase().toLowerCase());
}

function isSystemLabel(key: string): boolean {
  return GMAIL_SYSTEM_LABELS.includes(key) || key.startsWith(SYSTEM_LABEL_START);
}

/** The rules about the shape of a name, in rule order. */
function shapeProblems(segments: readonly string[], text: string): string[] {
  const checks: [boolean, string][] = [
    [segments.some((segment) => segment === ""), "name_segment_empty"],
    [segments.some((segment) => length(segment) > SEGMENT_MAX), "name_segment_too_long"],
    [length(text) > LABEL_MAX, "name_label_too_long"],
    [hasForbidden(text), "name_forbidden_char"],
    [RESERVED_NAMES.includes(normaliseName(segments[0] ?? "")) || isSystemLabel(normaliseName(text)), "name_reserved"],
  ];
  return checks.filter(([broken]) => broken).map(([, rule]) => rule);
}

function nameProblems(name: string, existing: readonly string[], settings: readonly string[]): string[] {
  const segments = segmentsOf(name);
  const text = segments.join(SEPARATOR);
  if (text === "") {
    return ["name_empty"];
  }
  const rules = shapeProblems(segments, text);
  const key = normaliseName(name);
  if (existing.some((other) => normaliseName(other) === key)) {
    rules.push("name_duplicate");
  } else if (!rules.includes("name_reserved") && settings.some((setting) => normaliseName(setting) === key)) {
    rules.push("name_setting_clash");
  }
  return rules;
}

function descriptionProblems(description: string): string[] {
  const text = description.trim();
  if (text === "") {
    return ["description_empty"];
  }
  return length(text) > DESCRIPTION_MAX ? ["description_too_long"] : [];
}

/**
 * Checks one category. A label that exists in Gmail never refuses a name: the caller adopts it (ADR-0060).
 *
 * @param existing Names of the other categories on the list.
 * @param settings The current names of the "Other" label and the archive label; a category of that name clashes.
 * @returns The problems in rule order; empty when the category is valid.
 */
export function validateCategory(
  name: string,
  description: string,
  existing: readonly string[],
  settings: readonly string[],
): Problem[] {
  return [
    ...nameProblems(name, existing, settings).map((rule): Problem => ({ rule, field: "name", index: null })),
    ...descriptionProblems(description).map((rule): Problem => ({ rule, field: "description", index: null })),
  ];
}

/**
 * Checks a whole list: every category (a later duplicate is the one flagged) and the cap of 100.
 *
 * @example
 * validateList([{ name: "Invoices", description: "Bills" }], ["Other", "Archive"]); // []
 */
export function validateList(categories: readonly CategoryText[], settings: readonly string[]): Problem[] {
  const problems = categories.flatMap((category, index) =>
    validateCategory(
      category.name,
      category.description,
      categories.slice(0, index).map((other) => other.name),
      settings,
    ).map((problem): Problem => ({ ...problem, index })),
  );
  return categories.length > MAX_CATEGORIES ? [...problems, { rule: "list_too_many", field: "list", index: null }] : problems;
}
