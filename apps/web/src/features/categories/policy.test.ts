import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { normaliseName, validateCategory, validateList } from "@/features/categories/policy";
import { problemText } from "@/features/categories/problemText";

// The one source of the rules: the file the Python package and the api also run (INT-004, AC-2, AC-8).
// Vitest runs in apps/web.
const CASES_FILE = resolve(process.cwd(), "../../packages/category-policy/contract/category_cases.json");

interface Cases {
  normalise: { id: string; raw: string; expected: string }[];
  category: { id: string; name: string; description: string; existing: string[]; settings: string[]; rules: string[] }[];
  list: {
    id: string;
    categories?: { name: string; description: string }[];
    generate?: number;
    settings: string[];
    problems: [number | null, string][];
  }[];
}

const cases = JSON.parse(readFileSync(CASES_FILE, "utf8")) as Cases;

/** A description of the form `__N__` stands for N letters. */
function expand(description: string): string {
  const match = /^__(\d+)__$/.exec(description);
  return match?.[1] === undefined ? description : "a".repeat(Number(match[1]));
}

/** A name `__label_len_N__` stands for a nested name whose Gmail label has N characters (segments of 40 letters). */
function expandName(name: string): string {
  const match = /^__label_len_(\d+)__$/.exec(name);
  if (match?.[1] === undefined) {
    return name;
  }
  let remaining = Number(match[1]);
  const segments: string[] = [];
  while (remaining > 0) {
    const take = Math.min(40, remaining);
    segments.push("a".repeat(take));
    remaining -= take + 1;
  }
  return segments.join("/");
}

describe("the shared category cases (category_cases.json)", () => {
  it.each(cases.normalise)("normalise $id", ({ raw, expected }) => {
    expect(normaliseName(raw)).toBe(expected);
  });

  it.each(cases.category)("category $id", ({ name, description, existing, settings, rules }) => {
    const found = validateCategory(expandName(name), expand(description), existing, settings).map((problem) => problem.rule);
    expect(found).toEqual(rules);
  });

  it.each(cases.list)("list $id", ({ categories, generate, settings, problems }) => {
    const list =
      generate === undefined
        ? (categories ?? [])
        : Array.from({ length: generate }, (_, index) => ({ name: `Category ${String(index)}`, description: "x" }));
    const found = validateList(list, settings).map((problem) => [problem.index, problem.rule]);
    expect(found).toEqual(problems);
  });
});

const SETTINGS = ["Other", "Archive"];
const rulesOf = (name: string, description = "Something"): string[] =>
  validateCategory(name, description, [], SETTINGS).map((problem) => problem.rule);

describe("policy v2 name rules in the form (U-label-structure-30)", () => {
  it("given a nested name, when validated, then it is accepted", () => {
    expect(rulesOf("Huis/Energie")).toEqual([]);
  });

  it.each([
    ["a segment of 41 characters", `Huis/${"a".repeat(41)}`, "name_segment_too_long"],
    ["an empty segment", "Huis//Energie", "name_segment_empty"],
    ["a label of more than 255 characters", Array.from({ length: 11 }, () => "a".repeat(25)).join("/"), "name_label_too_long"],
  ])("given %s, when validated, then the rule is %s and the form has its own text", (_label, name, rule) => {
    expect(rulesOf(name)).toContain(rule);
    expect(problemText(rule)).not.toBe(problemText("unknown_rule"));
  });

  it("given a segment of 40 characters, then it passes", () => {
    expect(rulesOf("a".repeat(40))).toEqual([]);
  });

  it("given a description of 1 500 characters, then it passes; one more is refused", () => {
    expect(rulesOf("Huis", "a".repeat(1500))).toEqual([]);
    expect(rulesOf("Huis", "a".repeat(1501))).toEqual(["description_too_long"]);
  });

  it("given 100 categories, then the list passes; one more is refused", () => {
    const make = (count: number): { name: string; description: string }[] =>
      Array.from({ length: count }, (_, index) => ({ name: `Category ${String(index)}`, description: "x" }));
    expect(validateList(make(100), SETTINGS)).toEqual([]);
    expect(validateList(make(101), SETTINGS).map((problem) => problem.rule)).toEqual(["list_too_many"]);
  });

  it("given the policy, when the codes are read, then the old ones are gone and every name and description code has text", () => {
    const covered = ["name_empty", "name_segment_empty", "name_segment_too_long", "name_label_too_long", "name_forbidden_char", "name_reserved", "name_duplicate", "name_setting_clash", "description_empty", "description_too_long"];
    for (const rule of covered) {
      expect(problemText(rule)).not.toBe(problemText("unknown_rule"));
    }
    for (const old of ["name_slash", "name_too_long", "name_label_exists"]) {
      expect(problemText(old)).toBe(problemText("unknown_rule"));
    }
    expect(problemText("name_segment_too_long")).toContain("40");
    expect(problemText("name_label_too_long")).toContain("255");
    expect(problemText("description_too_long")).toContain("1500");
  });
});

describe("policy v3 in the form (U-label-prefix-removal-20)", () => {
  it("given a category named like an existing label, when validated, then it is accepted (AC 19)", () => {
    // The mirror takes no labels: an existing label is adopted, so a plain name passes.
    expect(validateCategory("Travel", "Trips", [], SETTINGS)).toEqual([]);
  });

  it.each([["Other"], ["Archive"], ["archive"], ["Mijn Archief"]])("given a category equal to the setting %s, then name_setting_clash with a plain text (AC 13)", (setting) => {
    const rules = validateCategory(setting, "x", [], ["Other", "Mijn Archief"]).map((problem) => problem.rule);
    expect(rules.includes("name_setting_clash") || rules.includes("name_reserved")).toBe(true);
    expect(problemText("name_setting_clash")).not.toBe(problemText("unknown_rule"));
    expect(problemText("name_setting_clash")).not.toMatch(/[<>]/);
  });

  it("given a name equal to a custom setting, then name_setting_clash is the one rule", () => {
    expect(validateCategory("Mijn Archief", "x", [], ["Other", "Mijn Archief"]).map((problem) => problem.rule)).toEqual(["name_setting_clash"]);
  });

  it.each([["Archive"], ["ARCHIVE/Old"], ["Other"], ["other/x"], ["INBOX"], ["inbox"], ["SPAM"], ["category_promotions"], ["CATEGORY_SOCIAL"]])(
    "given the reserved name %s, then it is refused with name_reserved in any case",
    (name) => {
      expect(validateCategory(name, "x", [], SETTINGS).map((problem) => problem.rule)).toContain("name_reserved");
    },
  );

  it("given the policy source, when searched, then the old label inputs are gone (criterion 5)", () => {
    const dir = resolve(process.cwd(), "src/features/categories");
    const files = readdirSync(dir, { recursive: true, encoding: "utf8" }).filter((file) => /\.(ts|tsx)$/.test(file) && !/\.test\./.test(file));
    const offenders = files.filter((file) => /name_label_exists|adoptable|LABEL_PREFIX|Assistant\//.test(readFileSync(resolve(dir, file), "utf8")));
    expect(offenders).toEqual([]);
  });
});
