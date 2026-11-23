import { describe, expect, it } from "vitest";

import { parseThreshold } from "@/features/categories/sort-again/threshold";

describe("parseThreshold (AC-45, mirrors the api)", () => {
  it.each([
    ["50", 50],
    ["100", 100],
    ["75", 75],
    ["050", 50],
  ])("given %j, then it is the number %i", (text, expected) => {
    expect(parseThreshold(text)).toBe(expected);
  });

  it.each(["49", "101", "50.5", "50 ", " 50", "abc", "", "-60", "+60", "5e1", "0x40", "٦٠", "1,0"])(
    "given %j, then it is refused",
    (text) => {
      expect(parseThreshold(text)).toBeNull();
    },
  );
});
