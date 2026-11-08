// WCAG contrast check for the token pairs listed in tokens.json (guardrail-a11y).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const tokens = JSON.parse(readFileSync(new URL("./tokens.json", import.meta.url), "utf8"));

function luminance(hex) {
  const channels = hex.replace("#", "").match(/../g).map((h) => parseInt(h, 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

for (const mode of ["light", "dark"]) {
  for (const [fg, bg] of tokens.contrastPairs) {
    test(`${mode}: ${fg} on ${bg} has contrast >= 4.5`, () => {
      const ratio = contrast(tokens.color[fg][mode], tokens.color[bg][mode]);
      assert.ok(ratio >= 4.5, `ratio ${ratio.toFixed(2)}`);
    });
  }
}
