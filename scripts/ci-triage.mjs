#!/usr/bin/env node
// CI triage (skills sdlc-flow phase 8, git-workflow): turns one red CI run of a feature's pull request into
// repair rounds, one per unit that caused a failure, so the units are fixed together and pushed once
// (one more CI run) instead of a CI run per unit.
//
//   node scripts/ci-triage.mjs [--pr <number>] [--json]
//       GitHub: reads the failing checks of the pull request (default: the one of the current branch) and
//       their failed-step logs with the gh CLI.
//   node scripts/ci-triage.mjs --job <name> --log <file> [--job … --log …] [--head <ref>] [--base main] [--json]
//       Any host (Bitbucket: download the failed step's log): triage logs you already have.
//
// How a failure is assigned: the files the feature changed (git log base..head) and the `Unit:` trailer
// of the commits that changed them give every file its unit(s). A file named in a job's log belongs to
// that job's failure ("named in the log"). When the log names none of them, the units whose files the job
// tests (the areas of scripts/ci-changes.mjs) are the likely cause ("in the job's area"). What is left
// (no unit, or a commit without a `Unit:` trailer) is fixed on the feature branch itself.
// The full logs are saved in .sdlc/run/ci-triage/ for the repair rounds to read.
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { classify } from "./ci-changes.mjs";
import { existingRef, parseUnitId } from "./lib/branches.mjs";

/** The ci-changes area a CI job tests ("" for the always-on docs job, null for a job without files). */
export function jobArea(name) {
  const job = String(name).toLowerCase().split(/[\s(/:]/).find(Boolean) ?? "";
  if (job === "helm") return "deploy";
  if (job === "docs") return "";
  return ["backend", "web", "components", "images", "e2e", "gxp", "security", "deploy"].includes(job) ? job : null;
}

/** `git log --format=%x1e%(trailers:key=Unit,valueonly,separator=%x2c) --name-only` → Map(file → Set(unit)). */
export function parseOwnership(text) {
  const owners = new Map();
  for (const record of String(text).split("\x1e").slice(1)) {
    const [head, ...files] = record.split(/\r?\n/);
    const units = head.split(",").map((u) => u.trim()).filter((u) => parseUnitId(u));
    for (const file of files.map((f) => f.trim()).filter(Boolean)) {
      if (!owners.has(file)) owners.set(file, new Set());
      for (const unit of units) owners.get(file).add(unit);
    }
  }
  return owners;
}

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The spellings a file can have in a log: its repository path and the shorter paths a tool prints from a sub-folder. */
function spellings(file) {
  const parts = file.split("/");
  return parts.map((_, i) => parts.slice(i).join("/")).filter((s, i) => i === 0 || s.includes("/"));
}

/** The files of `files` that the log names (by repository path or by a path relative to a sub-folder). */
export function namedFiles(log, files) {
  return files.filter((file) => spellings(file).some((s) => new RegExp(`(^|[\\s"'(\\[=:/])${escape(s)}(?=$|[\\s"':),\\]])`, "m").test(log)));
}

const inArea = (file, area) => (area === "" ? /\.md$|^docs\//.test(file) : classify([file])[area] === true);

/**
 * failures: [{ job, log }]; owners: Map(file → Set(unit)).
 * → { failures: [{ job, files, units, reason }], rounds: [{ unit, jobs: [{ job, files, reason }] }], unassigned: [job] }
 */
export function triage(failures, owners) {
  const changed = [...owners.keys()];
  const result = { failures: [], rounds: [], unassigned: [] };
  const roundOf = (unit) => {
    let round = result.rounds.find((r) => r.unit === unit);
    if (!round) { round = { unit, jobs: [] }; result.rounds.push(round); }
    return round;
  };
  for (const { job, log } of failures) {
    const area = jobArea(job);
    const candidates = area === null ? changed : changed.filter((f) => inArea(f, area));
    let files = namedFiles(log ?? "", candidates);
    let reason = "named in the log";
    if (files.length === 0) { files = area === null ? [] : candidates; reason = "in the job's area"; }
    const units = [...new Set(files.flatMap((f) => [...(owners.get(f) ?? [])]))].sort();
    const unowned = files.filter((f) => (owners.get(f)?.size ?? 0) === 0);
    result.failures.push({ job, files, units, reason: units.length ? reason : "no unit" });
    for (const unit of units) roundOf(unit).jobs.push({ job, files: files.filter((f) => owners.get(f)?.has(unit)), reason });
    if (units.length === 0 || unowned.length) result.unassigned.push(job);
  }
  result.rounds.sort((a, b) => a.unit.localeCompare(b.unit));
  return result;
}

export function renderTriage(result, { title = "CI triage", logDir = "" } = {}) {
  const out = [`${title}: ${result.failures.length} failing job(s), ${result.rounds.length} repair round(s).`, ""];
  for (const round of result.rounds) {
    out.push(`Repair round ${round.unit}`);
    for (const j of round.jobs) out.push(`  - ${j.job} (${j.reason}): ${j.files.join(", ") || "—"}`);
    out.push("");
  }
  if (result.unassigned.length) out.push(`On the feature branch itself (no unit to give it to): ${[...new Set(result.unassigned)].join(", ")}`, "");
  if (logDir) out.push(`Failed logs: ${logDir}`);
  out.push(
    "Each round: node scripts/feature.mjs unit <unit> → reproduce the failure as a failing test → fix → node scripts/feature.mjs land <unit>.",
    "Independent rounds run in parallel. Push the feature branch once, after every round has landed: that is the next (single) CI run.",
  );
  return `${out.join("\n")}\n`;
}

// --- reading CI and git ---------------------------------------------------------------------------

function sh(cmd, args, cwd) {
  const r = spawnSync(cmd, args, { cwd, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (r.error || r.status !== 0) throw new Error(`${cmd} ${args.join(" ")} failed: ${(r.stderr || r.error?.message || "").trim()}`);
  return r.stdout;
}

function ownershipOf(root, base, head) {
  return parseOwnership(sh("git", ["log", "--no-merges", "--format=%x1e%(trailers:key=Unit,valueonly,separator=%x2c)", "--name-only", `${base}..${head}`], root));
}

function githubFailures(root, pr) {
  const view = JSON.parse(sh("gh", ["pr", "view", ...(pr ? [String(pr)] : []), "--json", "number,headRefName,baseRefName"], root));
  const checks = JSON.parse(sh("gh", ["pr", "checks", String(view.number), "--json", "name,bucket,link"], root).trim() || "[]");
  const failures = checks.filter((c) => c.bucket === "fail").map((c) => {
    const m = /\/actions\/runs\/(\d+)\/job\/(\d+)/.exec(c.link ?? "");
    let log = "";
    if (m) { try { log = sh("gh", ["run", "view", m[1], "--job", m[2], "--log-failed"], root); } catch { log = ""; } }
    return { job: c.name, log };
  });
  return { failures, head: view.headRefName, base: view.baseRefName, title: `CI triage for pull request #${view.number} (${view.headRefName} → ${view.baseRefName})` };
}

function main(argv, cwd = process.cwd()) {
  const { values } = parseArgs({ args: argv, options: {
    pr: { type: "string" }, json: { type: "boolean", default: false }, job: { type: "string", multiple: true },
    log: { type: "string", multiple: true }, head: { type: "string" }, base: { type: "string" }, root: { type: "string" },
  } });
  const root = path.resolve(values.root ?? cwd);
  let run;
  if (values.log?.length) {
    if ((values.job ?? []).length !== values.log.length) { console.error("ci-triage: give one --job per --log."); return 2; }
    run = { failures: values.log.map((file, i) => ({ job: values.job[i], log: readFileSync(file, "utf8") })), head: values.head ?? "HEAD", base: values.base ?? "main", title: "CI triage" };
  } else {
    try { run = githubFailures(root, values.pr); } catch (error) { console.error(`ci-triage: ${error.message}\nWithout the gh CLI: --job <name> --log <file>.`); return 1; }
  }
  if (run.failures.length === 0) { console.log(values.json ? JSON.stringify({ failures: [], rounds: [], unassigned: [] }) : "ci-triage: no failing checks."); return 0; }
  const head = existingRef(root, [run.head]) || run.head;
  const base = existingRef(root, [run.base]) || run.base;
  const result = triage(run.failures, ownershipOf(root, base, head));
  const logDir = path.join(root, ".sdlc", "run", "ci-triage");
  mkdirSync(logDir, { recursive: true });
  for (const f of run.failures) writeFileSync(path.join(logDir, `${f.job.replace(/[^A-Za-z0-9._-]+/g, "-")}.log`), f.log ?? "");
  console.log(values.json ? JSON.stringify({ ...result, head, base }, null, 2) : renderTriage(result, { title: run.title, logDir: path.relative(root, logDir) }));
  return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) process.exit(main(process.argv.slice(2)));
