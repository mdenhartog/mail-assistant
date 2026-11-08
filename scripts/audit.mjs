// Dependency audit with time-boxed, path-restricted risk acceptance (secure-by-design, supply chain).
//
// Fails when pnpm audit reports an advisory at or above --level (default: high) unless it is listed in
// .sdlc/accepted-advisories.json AND
//   - the acceptance has not expired,
//   - every dependency path matches the entry's allowedPaths (so the package cannot spread unnoticed),
//   - no patched version exists yet (a fix must be applied, not accepted).
// Usage: node scripts/audit.mjs [--level high|critical|moderate]
import { existsSync, readFileSync } from "node:fs";

import { runPnpm } from "./lib/run-pnpm.mjs";

const LEVELS = ["low", "moderate", "high", "critical"];
const level = process.argv.includes("--level") ? process.argv[process.argv.indexOf("--level") + 1] : "high";
const today = new Date().toISOString().slice(0, 10);

function runAudit() {
  try {
    return runPnpm(["audit", "--json"], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  } catch (err) {
    if (err.stdout) return err.stdout; // pnpm exits non-zero when it finds advisories
    throw err;
  }
}

const report = JSON.parse(runAudit());
const accepted = existsSync(".sdlc/accepted-advisories.json")
  ? JSON.parse(readFileSync(".sdlc/accepted-advisories.json", "utf8"))
  : [];

const problems = [];
const tolerated = [];
for (const advisory of Object.values(report.advisories ?? {})) {
  if (LEVELS.indexOf(advisory.severity) < LEVELS.indexOf(level)) continue;
  const id = advisory.github_advisory_id;
  const paths = advisory.findings.flatMap((f) => f.paths);
  const entry = accepted.find((a) => a.ghsa === id && a.package === advisory.module_name);
  const label = `${id} ${advisory.module_name} (${advisory.severity})`;
  if (!entry) {
    problems.push(`${label}: not accepted — fix it (upgrade/override) or record an accepted-risk ADR.`);
    continue;
  }
  if (advisory.patched_versions && advisory.patched_versions !== "<0.0.0") {
    problems.push(`${label}: a patched version exists (${advisory.patched_versions}) — upgrade and remove the acceptance.`);
    continue;
  }
  if (entry.expires < today) {
    problems.push(`${label}: acceptance expired on ${entry.expires} — re-evaluate (see ${entry.adr}).`);
    continue;
  }
  const patterns = entry.allowedPaths.map((p) => new RegExp(p));
  const outside = paths.filter((p) => !patterns.some((re) => re.test(p)));
  if (outside.length > 0) {
    problems.push(`${label}: found outside the accepted scope: ${outside.join(", ")}`);
    continue;
  }
  tolerated.push(`${label}: accepted until ${entry.expires} (${entry.adr}); ${paths.length} path(s) within scope.`);
}

const reported = new Set(Object.values(report.advisories ?? {}).map((a) => a.github_advisory_id));
for (const entry of accepted.filter((a) => !reported.has(a.ghsa))) {
  console.warn(`STALE     ${entry.ghsa} ${entry.package} is no longer reported — remove it from .sdlc/accepted-advisories.json and supersede ${entry.adr}.`);
}
for (const line of tolerated) console.log(`ACCEPTED  ${line}`);
for (const line of problems) console.error(`FAIL      ${line}`);
if (problems.length > 0) process.exit(1);
console.log(`OK        no unaccepted advisories at level >= ${level}.`);
