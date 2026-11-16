/**
 * The name, description and list rules of a category, as the api and the agent apply them
 * (`packages/category-policy`, INT-004, AC-2, AC-8). The cases both runtimes must pass live in
 * `category_cases.json`; this file adds no rule of its own. The api stays the authority: it checks again.
 */

export const NAME_MAX = 40;
export const DESCRIPTION_MAX = 500;
export const MAX_CATEGORIES = 50;
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

function canonical(raw: string): string {
  return raw.trim().normalize("NFKC").trim();
}

function length(text: string): number {
  return Array.from(text).length;
}

/**
 * The comparison key of a name: trim, NFKC and case folding (upper then lower case stands in for
 * Python's `casefold`, so "Straße" and "STRASSE" meet).
 */
export function normaliseName(raw: string): string {
  return canonical(raw).toUpperCase().toLowerCase().normalize("NFKC").trim();
}

/** The Gmail label of a category name. */
export function labelFor(name: string): string {
  return `${LABEL_PREFIX}${name.trim()}`;
}

/** Whether the label of the name exists and is not an older category's label (which the name adopts). */
function labelClashes(name: string, labels: readonly string[], adoptable: readonly string[]): boolean {
  const key = normaliseName(labelFor(name));
  const has = (list: readonly string[]): boolean => list.some((label) => normaliseName(label) === key);
  return has(labels) && !has(adoptable);
}

function nameProblems(
  name: string,
  existing: readonly string[],
  labels: readonly string[],
  adoptable: readonly string[],
): string[] {
  const text = canonical(name);
  if (text === "") {
    return ["name_empty"];
  }
  const rules: string[] = [];
  if (length(text) > NAME_MAX) {
    rules.push("name_too_long");
  }
  if (text.includes("/")) {
    rules.push("name_slash");
  }
  if (hasForbidden(text)) {
    rules.push("name_forbidden_char");
  }
  const key = normaliseName(name);
  if (RESERVED_NAMES.includes(key)) {
    rules.push("name_reserved");
  }
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
 * Checks a whole list: every category (a later duplicate is the one flagged) and the cap of 50.
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
