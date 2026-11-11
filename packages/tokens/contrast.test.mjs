// Token checks (U-web-settings-01): shape, WCAG contrast (guardrail-a11y), motion, generated files
// and self-hosted fonts. Run with `node --test` in packages/tokens.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const read = (file) => readFileSync(join(here, file), "utf8");
const tokens = JSON.parse(read("tokens.json"));

const MODES = ["light", "dark"];
const COLOR_NAMES = [
  "surface",
  "surface-raised",
  "text",
  "text-muted",
  "border",
  "divider",
  "primary",
  "primary-contrast",
  "danger",
  "danger-soft",
  "success",
  "success-soft",
  "focus",
];

function luminance(hex) {
  const channels = hex.replace("#", "").match(/../g).map((h) => parseInt(h, 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Returns one message per failing pair and mode, naming both, the mode and the ratio. */
function failingPairs(set, pairs, minimum) {
  const failures = [];
  for (const mode of MODES) {
    for (const [fg, bg] of pairs) {
      const ratio = contrast(set.color[fg][mode], set.color[bg][mode]);
      if (ratio < minimum) {
        failures.push(`${fg} on ${bg} in ${mode} mode is ${ratio.toFixed(2)}:1, needs ${minimum}:1`);
      }
    }
  }
  return failures;
}

const seconds = (duration) => (duration.endsWith("ms") ? Number.parseFloat(duration) : Number.parseFloat(duration) * 1000);

test("given tokens.json, when validated, then every colour has a light and a dark value, names are semantic and the placeholder description is gone", () => {
  assert.deepEqual(Object.keys(tokens.color).sort(), [...COLOR_NAMES].sort());
  for (const [name, value] of Object.entries(tokens.color)) {
    assert.match(name, /^[a-z]+(-[a-z]+)*$/, `${name} is not a kebab-case name`);
    for (const mode of MODES) {
      assert.match(value[mode], /^#[0-9a-f]{6}$/i, `${name} has no valid ${mode} value`);
    }
  }
  assert.equal(tokens.$description?.toLowerCase().includes("placeholder"), false);
  assert.deepEqual(tokens.radius, { pill: "999px", control: "14px", card: "24px" });
  assert.ok(tokens.shadow.soft, "soft shadow is missing");
  assert.deepEqual(Object.keys(tokens.space), ["1", "2", "3", "4", "5", "6", "8"]);
  assert.equal(tokens.space["1"], "0.25rem");
  assert.equal(tokens.space["8"], "2rem");
  assert.equal(tokens.fontSize.sm, "0.875rem");
  assert.equal(tokens.fontSize["2xl"], "2rem");
  assert.match(tokens.font.display, /^"Bricolage Grotesque", .*sans-serif$/);
  assert.match(tokens.font.sans, /^"Figtree", .*sans-serif$/);
});

test("given text pairs in both modes, when measured, then each is at least 4.5:1 (AC-22)", () => {
  assert.ok(tokens.textPairs.length >= 7);
  for (const required of [
    ["text", "surface"],
    ["text", "surface-raised"],
    ["text-muted", "surface"],
    ["text-muted", "surface-raised"],
    ["primary-contrast", "primary"],
    ["danger", "danger-soft"],
    ["success", "success-soft"],
  ]) {
    assert.ok(
      tokens.textPairs.some(([fg, bg]) => fg === required[0] && bg === required[1]),
      `${required.join(" on ")} is not covered`,
    );
  }
  assert.deepEqual(failingPairs(tokens, tokens.textPairs, 4.5), []);
});

test("given border, focus ring and control edge against their adjacent surface in both modes, when measured, then each is at least 3:1 (AC-23)", () => {
  for (const required of [
    ["border", "surface"],
    ["border", "surface-raised"],
    ["focus", "surface"],
    ["focus", "surface-raised"],
    ["primary", "surface"],
  ]) {
    assert.ok(
      tokens.edgePairs.some(([fg, bg]) => fg === required[0] && bg === required[1]),
      `${required.join(" on ")} is not covered`,
    );
  }
  assert.deepEqual(failingPairs(tokens, tokens.edgePairs, 3), []);
});

test("given a token that is 4.49:1 and one that is 4.50:1, when the test runs, then the first fails naming the pair and the mode and the second passes", () => {
  const sample = (hex) => ({
    color: { text: { light: hex, dark: hex }, surface: { light: "#ffffff", dark: "#ffffff" } },
  });
  const pairs = [["text", "surface"]];

  const below = failingPairs(sample("#767680"), pairs, 4.5);
  assert.equal(below.length, 2);
  assert.match(below[0], /text on surface in light mode is 4\.49:1/);
  assert.match(below[1], /text on surface in dark mode/);

  assert.deepEqual(failingPairs(sample("#76767e"), pairs, 4.5), []);
});

test("given a changed tokens.json without regenerated files, when build.mjs --check runs, then it fails", () => {
  const copy = mkdtempSync(join(tmpdir(), "tokens-check-"));
  try {
    cpSync(here, copy, { recursive: true, filter: (source) => !source.includes("node_modules") });
    const run = () => spawnSync(process.execPath, [join(copy, "build.mjs"), "--check"], { encoding: "utf8" });

    assert.equal(run().status, 0, "a clean copy must pass");

    const changed = JSON.parse(readFileSync(join(copy, "tokens.json"), "utf8"));
    changed.color.primary.light = "#000000";
    writeFileSync(join(copy, "tokens.json"), JSON.stringify(changed, null, 2));

    const result = run();
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Out of date/);
  } finally {
    rmSync(copy, { recursive: true, force: true });
  }
});

test("given the motion tokens, when read, then the longest duration is 250 ms and a reduced-motion value of 0 exists", () => {
  const durations = Object.values(tokens.motion.duration).map(seconds);
  assert.equal(Math.max(...durations), 250);
  assert.equal(tokens.motion.duration.press, "200ms");
  assert.equal(tokens.motion.duration.enter, "250ms");
  assert.equal(seconds(tokens.motion.reducedDuration), 0);
  assert.match(tokens.motion.ease.spring, /^cubic-bezier\(/);
});

test("given the generated files, when read, then both modes, the reduced-motion override and every token are present", () => {
  const css = read("tokens.css");
  const native = JSON.parse(read("theme.native.json"));
  for (const name of COLOR_NAMES) {
    assert.ok(css.includes(`--color-${name}: ${tokens.color[name].light};`), `${name} light is missing in css`);
    assert.ok(css.includes(`--color-${name}: ${tokens.color[name].dark};`), `${name} dark is missing in css`);
    assert.equal(native.light[name], tokens.color[name].light);
    assert.equal(native.dark[name], tokens.color[name].dark);
  }
  assert.match(css, /@media \(prefers-color-scheme: dark\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /--radius-pill: 999px;/);
  assert.match(css, /--shadow-soft: /);
  assert.match(css, /--duration-enter: 250ms;/);
  assert.equal(native.motion.duration.enter, "250ms");
});

test("given the generated CSS, when read, then every @font-face URL is relative, no https URL appears and every font file has a licence beside it (D-2, AC-14)", () => {
  const css = read("tokens.css");
  const faces = css.match(/@font-face\s*\{[^}]*\}/g) ?? [];
  assert.ok(faces.some((face) => face.includes('"Bricolage Grotesque"')), "Bricolage Grotesque is not declared");
  assert.ok(faces.some((face) => face.includes('"Figtree"')), "Figtree is not declared");
  assert.equal(css.includes("https://"), false);
  assert.equal(css.includes("http://"), false);

  const urls = [...css.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/g)].map((m) => m[1]);
  assert.ok(urls.length >= 2);
  for (const url of urls) {
    assert.match(url, /^\.\/fonts\/[\w./-]+\.woff2$/, `${url} is not a relative woff2 path`);
    const file = resolve(here, url);
    assert.ok(existsSync(file), `${url} does not exist`);
    assert.ok(statSync(file).size > 1000, `${url} is empty`);
    const licences = readdirSync(dirname(file)).filter((name) => /^OFL.*\.txt$/.test(name));
    assert.ok(licences.length > 0, `no OFL licence beside ${url}`);
    assert.match(readFileSync(join(dirname(file), licences[0]), "utf8"), /SIL OPEN FONT LICENSE Version 1\.1/i);
  }
});

test("given the font faces, when generated, then each swaps in with a system fallback stack", () => {
  const css = read("tokens.css");
  for (const face of css.match(/@font-face\s*\{[^}]*\}/g) ?? []) {
    assert.match(face, /font-display: swap;/);
    assert.match(face, /format\("woff2"\)/);
  }
  assert.match(tokens.font.sans, /system-ui/);
  assert.match(tokens.font.display, /system-ui/);
});

test("given apps/web/src, when searched for hex colours, rgb( and arbitrary Tailwind values, then there is no hit outside the tokens package", () => {
  const root = resolve(here, "../../apps/web/src");
  const files = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if ([".ts", ".tsx", ".css"].includes(extname(path))) files.push(path);
    }
  };
  walk(root);
  assert.ok(files.length > 0);

  const forbidden = [/#[0-9a-fA-F]{3,8}\b/, /\brgba?\(/, /\bhsla?\(/, /[a-z0-9:-]+-\[[^\]\s]+\]/];
  const hits = [];
  for (const file of files) {
    read_lines: for (const [index, line] of readFileSync(file, "utf8").split("\n").entries()) {
      for (const pattern of forbidden) {
        if (pattern.test(line)) {
          hits.push(`${file}:${index + 1}: ${line.trim()}`);
          continue read_lines;
        }
      }
    }
  }
  assert.deepEqual(hits, []);
});
