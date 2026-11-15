import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { normaliseName, validateCategory, validateList } from "@/features/categories/policy";

// The one source of the rules: the file the Python package and the api also run (INT-004, AC-2, AC-8).
// Vitest runs in apps/web.
const CASES_FILE = resolve(process.cwd(), "../../packages/category-policy/contract/category_cases.json");

interface Cases {
  normalise: { id: string; raw: string; expected: string }[];
  category: { id: string; name: string; description: string; existing: string[]; labels: string[]; rules: string[] }[];
  list: {
    id: string;
    categories?: { name: string; description: string }[];
    generate?: number;
    labels: string[];
    problems: [number | null, string][];
  }[];
}

const cases = JSON.parse(readFileSync(CASES_FILE, "utf8")) as Cases;

/** A description of the form `__N__` stands for N letters. */
function expand(description: string): string {
  const match = /^__(\d+)__$/.exec(description);
  return match?.[1] === undefined ? description : "a".repeat(Number(match[1]));
}

describe("the shared category cases (category_cases.json)", () => {
  it.each(cases.normalise)("normalise $id", ({ raw, expected }) => {
    expect(normaliseName(raw)).toBe(expected);
  });

  it.each(cases.category)("category $id", ({ name, description, existing, labels, rules }) => {
    const found = validateCategory(name, expand(description), existing, labels).map((problem) => problem.rule);
    expect(found).toEqual(rules);
  });

  it.each(cases.list)("list $id", ({ categories, generate, labels, problems }) => {
    const list =
      generate === undefined
        ? (categories ?? [])
        : Array.from({ length: generate }, (_, index) => ({ name: `Category ${String(index)}`, description: "x" }));
    const found = validateList(list, labels).map((problem) => [problem.index, problem.rule]);
    expect(found).toEqual(problems);
  });
});
