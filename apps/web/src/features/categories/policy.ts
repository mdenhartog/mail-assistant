/**
 * The name, description and list rules of a category, as the api and the agent apply them
 * (`packages/category-policy` v2, INT-004, INT-008). The cases both runtimes must pass live in
 * `category_cases.json`; this file adds no rule of its own. The api stays the authority: it checks again.
 */

const SEGMENT_MAX = 40;
const LABEL_MAX = 225;
const DESCRIPTION_MAX = 1500;
export const MAX_CATEGORIES = 100;
const SEPARATOR = "/";
export const LABEL_PREFIX = "Assistant/";
const RESERVED_NAMES: readonly string[] = ["other", "archive"];
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

/** The Gmail label of a category name. */
function labelFor(name: string): string {
  return `${LABEL_PREFIX}${canonical(name)}`;
}

/** Whether the label of the name exists and is not an older category's label (which the name adopts). */
function labelClashes(name: string, labels: readonly string[], adoptable: readonly string[]): boolean {
  const key = normaliseName(labelFor(name));
  const has = (list: readonly string[]): boolean => list.some((label) => normaliseName(label) === key);
  return has(labels) && !has(adoptable);
}

/** The rules about the shape of a name, in rule order. */
function shapeProblems(segments: readonly string[], text: string): string[] {
  const checks: [boolean, string][] = [
    [segments.some((segment) => segment === ""), "name_segment_empty"],
    [segments.some((segment) => length(segment) > SEGMENT_MAX), "name_segment_too_long"],
    [length(LABEL_PREFIX) + length(text) > LABEL_MAX, "name_label_too_long"],
    [hasForbidden(text), "name_forbidden_char"],
    [RESERVED_NAMES.includes(normaliseName(segments[0] ?? "")), "name_reserved"],
  ];
  return checks.filter(([broken]) => broken).map(([, rule]) => rule);
}

function nameProblems(
  name: string,
  existing: readonly string[],
  labels: readonly string[],
  adoptable: readonly string[],
): string[] {
  const segments = segmentsOf(name);
  const text = segments.join(SEPARATOR);
  if (text === "") {
    return ["name_empty"];
  }
  const rules = shapeProblems(segments, text);
  const key = normaliseName(name);
  if (existing.some((other) => normaliseName(other) === key)) {
    rules.push("name_duplicate");
  } else if (labelClashes(text, labels, adoptable)) {
    rules.push("name_label_exists");
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
 * Checks one category.
 *
 * @param existing Names of the other categories on the list.
 * @param labels The Gmail labels that exist, as the caller knows them.
 * @param adoptable The subset of `labels` that belongs to an older category: a new category of that name adopts
 * the label and its mail instead of clashing (C-15, AC-40, AC-53).
 * @returns The problems in rule order; empty when the category is valid.
 */
export function validateCategory(
  name: string,
  description: string,
  existing: readonly string[],
  labels: readonly string[],
  adoptable: readonly string[],
): Problem[] {
  return [
    ...nameProblems(name, existing, labels, adoptable).map((rule): Problem => ({ rule, field: "name", index: null })),
    ...descriptionProblems(description).map((rule): Problem => ({ rule, field: "description", index: null })),
  ];
}

/**
 * Checks a whole list: every category (a later duplicate is the one flagged) and the cap of 100.
 *
 * @example
 * validateList([{ name: "Invoices", description: "Bills" }], [], []); // []
 */
export function validateList(
  categories: readonly CategoryText[],
  labels: readonly string[],
  adoptable: readonly string[],
): Problem[] {
  const problems = categories.flatMap((category, index) =>
    validateCategory(
      category.name,
      category.description,
      categories.slice(0, index).map((other) => other.name),
      labels,
      adoptable,
    ).map((problem): Problem => ({ ...problem, index })),
  );
  return categories.length > MAX_CATEGORIES ? [...problems, { rule: "list_too_many", field: "list", index: null }] : problems;
}
