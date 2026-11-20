import { describe, expect, it } from "vitest";

import { categoryName, cleanText, groupKey, groupTitle } from "@/features/review/text";
import { INVOICES } from "@/test/categories";
import { GONE_ID, OTHER_ID } from "@/test/plan";

describe("cleanText (AC-44)", () => {
  it("removes bidi controls, zero-width and other format characters", () => {
    expect(cleanText("‮evil‬ name​⁦x⁩﻿")).toBe("evil namex");
  });

  it("removes control characters but keeps ordinary text, accents and spaces", () => {
    expect(cleanText("Zoë\u0007 Jansen  <b>")).toBe("Zoë Jansen  <b>");
  });

  it("does not rewrite look-alike letters; the real address shown beside the name is what the reader checks", () => {
    expect(cleanText("pаypal@example.com")).toBe("pаypal@example.com");
  });
});

describe("categories of a group", () => {
  const list = [INVOICES];

  it("names a known category, Other for the nil id, and a safe text for an id that no longer resolves", () => {
    expect(categoryName(INVOICES.id, list)).toBe("Invoices");
    expect(categoryName(OTHER_ID, list)).toBe("Other");
    expect(categoryName(GONE_ID, list)).toBe("A category that no longer exists");
  });

  it("builds a stable key and a title from the two ids", () => {
    expect(groupKey({ from: OTHER_ID, to: INVOICES.id })).toBe(`${OTHER_ID}:${INVOICES.id}`);
    expect(groupTitle({ from: OTHER_ID, to: INVOICES.id }, list)).toBe("Other to Invoices");
  });
});
