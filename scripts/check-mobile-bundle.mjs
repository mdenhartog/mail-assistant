// Proves that build-time-only packages never reach the shipped mobile app: exports the JS bundle
// with `expo export` and fails when a forbidden package name appears in it.
// Usage: node scripts/check-mobile-bundle.mjs [package ...]   (default: node-forge)
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { runPnpm } from "./lib/run-pnpm.mjs";

const forbidden = process.argv.slice(2).length ? process.argv.slice(2) : ["node-forge"];
const out = mkdtempSync(path.join(tmpdir(), "mobile-bundle-"));

try {
  const args = ["exec", "expo", "export", "--platform", "android", "--output-dir", out];
  const options = { cwd: "apps/mobile", stdio: ["ignore", "ignore", "inherit"] };
  runPnpm(args, options);

  const files = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (/\.(js|hbc|map|json)$/.test(name)) files.push(full);
    }
  };
  walk(out);

  const hits = [];
  for (const file of files) {
    const text = readFileSync(file, "latin1");
    for (const pkg of forbidden) if (text.includes(pkg)) hits.push(`${pkg} in ${path.relative(out, file)}`);
  }
  if (files.length === 0) throw new Error("expo export produced no bundle files");
  if (hits.length) {
    console.error(`FAIL forbidden build-time packages found in the app bundle:\n  ${hits.join("\n  ")}`);
    process.exit(1);
  }
  console.log(`OK   ${forbidden.join(", ")} not present in ${files.length} exported bundle file(s).`);
} finally {
  rmSync(out, { recursive: true, force: true });
}
