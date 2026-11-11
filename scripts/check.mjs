#!/usr/bin/env node
// Checks scaled to the change (skills sdlc-flow phases 5 and 7, verify):
//
//   node scripts/check.mjs unit [--base <ref>] [--files a,b] [--static] [--dry-run]
//       Everything a change can break, nothing else: lint, types and security on the changed files
//       and the tests that run them (pytest-testmon, vitest related, jest --findRelatedTests). A change
//       to a shared package or a contract also checks the components that depend on it (model.json).
//   node scripts/check.mjs full [--reuse] [--dry-run]
//       The whole suite with coverage, typecheck, lint, architecture, documentation and image names.
//       `--reuse` skips the run when the same committed tree already passed (.sdlc/run/full.json).
//
// Exit code 0 when every step passes, 1 otherwise.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { ownerOf, readModel } from "./architecture.mjs";
import { runPnpm } from "./lib/run-pnpm.mjs";

const PY = /\.py$/;
const JS = /\.(ts|tsx|js|jsx|mjs|cjs)$/;
const CONTRACT = /(^|\/)(openapi[^/]*\.json|asyncapi[^/]*\.(json|ya?ml)|[^/]+\.proto)$/;
const PY_CONFIG = /(^|\/)(pyproject\.toml|uv\.lock)$|(^|\/)alembic\//;
const CODE_ROOT = /^(apps|packages|backend|agents|mcp-servers|channels|workers|deploy)\//;
const SKIP_DIRS = new Set(["node_modules", ".venv", ".git", ".worktrees", ".sdlc", "dist", "build", "coverage", "__pycache__"]);
const posix = (p) => p.split(path.sep).join("/");
const read = (root, rel) => (existsSync(path.join(root, rel)) ? readFileSync(path.join(root, rel), "utf8") : "");

function git(root, args) {
  const result = spawnSync("git", args, { cwd: root, encoding: "utf8" });
  return result.status === 0 ? result.stdout : "";
}

/** Files changed since the branch left `base` (committed, uncommitted and untracked). */
export function changedFiles(root, base) {
  const branch = git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).trim();
  const baseRef = base ?? ["main", "origin/main"].find((ref) => git(root, ["rev-parse", "--verify", "-q", ref]).trim());
  let from = "HEAD";
  if (baseRef && branch !== baseRef) from = git(root, ["merge-base", "HEAD", baseRef]).trim() || "HEAD";
  const lines = [
    ...git(root, ["diff", "--name-only", "--diff-filter=ACMR", from]).split("\n"),
    ...git(root, ["ls-files", "--others", "--exclude-standard"]).split("\n"),
  ];
  return [...new Set(lines.map((l) => l.trim()).filter(Boolean))].filter((f) => existsSync(path.join(root, f))).sort();
}

/** The nearest folder at or above the file that holds `marker` (never above the root), or null. */
function nearest(root, file, marker, { allowRoot = false } = {}) {
  let dir = path.posix.dirname(file);
  while (true) {
    if (dir === ".") return allowRoot && existsSync(path.join(root, marker)) ? "." : null;
    if (existsSync(path.join(root, dir, marker))) return dir;
    dir = path.posix.dirname(dir);
  }
}
const relTo = (dir, file) => (dir === "." ? file : file.slice(dir.length + 1));
const step = (name, tool, args, cwd = ".") => ({ name, tool, args, cwd });

function pythonSteps(root, dir, files, full, staticOnly) {
  const text = read(root, `${dir}/pyproject.toml`);
  const has = (tool) => new RegExp(tool, "i").test(text);
  const rel = files.map((f) => relTo(dir, f));
  const app = rel.filter((f) => !/^tests?\//.test(f));
  const steps = [];
  if (has("ruff") && rel.length) {
    steps.push(step(`ruff check (${dir})`, "uv", ["run", "ruff", "check", ...rel], dir));
    steps.push(step(`ruff format (${dir})`, "uv", ["run", "ruff", "format", "--check", ...rel], dir));
  }
  if (has("pyright") && rel.length) steps.push(step(`pyright (${dir})`, "uv", ["run", "pyright", ...rel], dir));
  if (has("bandit") && app.length) steps.push(step(`bandit (${dir})`, "uv", ["run", "bandit", "-q", "-c", "pyproject.toml", ...app], dir));
  if (!staticOnly && has("pytest")) {
    const select = has("pytest-testmon") && !full;
    steps.push(step(`pytest ${select ? "affected tests" : "all tests"} (${dir})`, "uv", ["run", "pytest", "-q", ...(has("pytest-cov") ? ["--no-cov"] : []), ...(select ? ["--testmon"] : [])], dir));
  }
  return steps;
}

function nodeSteps(root, dir, files, { staticOnly, full = false }) {
  const pkg = read(root, `${dir}/package.json`);
  const has = (tool) => new RegExp(`"${tool}"`).test(pkg);
  const rel = files.map((f) => relTo(dir, f)).filter((f) => JS.test(f));
  const steps = [];
  if (has("eslint") && rel.length) steps.push(step(`eslint (${dir})`, "pnpm", ["exec", "eslint", "--cache", ...rel], dir));
  if (has("typescript") && existsSync(path.join(root, dir, "tsconfig.json"))) {
    steps.push(step(`tsc (${dir})`, "pnpm", ["exec", "tsc", "--noEmit", "--incremental", "--tsBuildInfoFile", "node_modules/.cache/unit.tsbuildinfo"], dir));
  }
  if (!staticOnly && has("vitest")) steps.push(step(`vitest ${full ? "all" : "related"} (${dir})`, "pnpm", full ? ["exec", "vitest", "run", "--passWithNoTests"] : ["exec", "vitest", "related", "--run", "--passWithNoTests", ...rel], dir));
  if (!staticOnly && has("jest")) steps.push(step(`jest ${full ? "all" : "related"} (${dir})`, "pnpm", full ? ["exec", "jest", "--passWithNoTests"] : ["exec", "jest", "--findRelatedTests", ...rel, "--passWithNoTests"], dir));
  return steps;
}

/** Components that depend (directly or through others) on the given component ids. */
export function dependentsOf(model, ids) {
  const found = new Set();
  const queue = [...ids];
  while (queue.length) {
    const id = queue.pop();
    for (const c of model.components ?? []) {
      if ((c.dependsOn ?? []).includes(id) && !found.has(c.id) && !ids.includes(c.id)) { found.add(c.id); queue.push(c.id); }
    }
  }
  return [...found].map((id) => model.components.find((c) => c.id === id));
}

/** The steps for a change: what the changed files can break. */
export function planUnit(root, files, { staticOnly = false } = {}) {
  const steps = [];
  const python = new Map();
  const node = new Map();
  for (const file of files) {
    const py = nearest(root, file, "pyproject.toml");
    if (py && (PY.test(file) || PY_CONFIG.test(file) || CONTRACT.test(file))) {
      const entry = python.get(py) ?? { files: [], full: false };
      if (PY.test(file)) entry.files.push(file);
      if (PY_CONFIG.test(file) || CONTRACT.test(file)) entry.full = true;
      python.set(py, entry);
    }
    const js = nearest(root, file, "package.json");
    if (js && JS.test(file)) node.set(js, [...(node.get(js) ?? []), file]);
  }
  for (const [dir, entry] of python) steps.push(...pythonSteps(root, dir, entry.files, entry.full, staticOnly));
  for (const [dir, list] of node) steps.push(...nodeSteps(root, dir, list, { staticOnly }));

  // A shared package, or a contract, reaches the components built on it.
  let model = null;
  try { model = readModel(root); } catch { model = null; }
  if (model) {
    const touched = new Set();
    for (const file of files) {
      const owner = ownerOf(model, file);
      if (owner && (owner.kind === "shared" || CONTRACT.test(file))) touched.add(owner.id);
    }
    for (const dependent of dependentsOf(model, [...touched])) {
      for (const dir of dependent.paths ?? []) {
        if (node.has(dir) || !existsSync(path.join(root, dir, "package.json"))) continue;
        steps.push(...nodeSteps(root, dir, [], { staticOnly, full: true }).map((s) => ({ ...s, name: `${s.name} [depends on ${[...touched].join(", ")}]` })));
      }
    }
  }
  if (files.some((f) => CODE_ROOT.test(f) || f.startsWith("docs/architecture/")) && existsSync(path.join(root, "scripts", "architecture.mjs"))) {
    steps.push(step("architecture", "node", ["scripts/architecture.mjs", "check"]));
  }
  const seen = new Set();
  return steps.filter((s) => { const key = `${s.cwd}|${s.tool}|${s.args.join(" ")}`; if (seen.has(key)) return false; seen.add(key); return true; });
}

function projectDirs(root, marker, depth = 3, dir = ".") {
  if (depth < 0) return [];
  const found = existsSync(path.join(root, dir, marker)) && dir !== "." ? [dir] : [];
  for (const entry of readdirSync(path.join(root, dir), { withFileTypes: true })) {
    if (entry.isDirectory() && !SKIP_DIRS.has(entry.name) && !entry.name.startsWith(".")) found.push(...projectDirs(root, marker, depth - 1, posix(path.join(dir, entry.name))));
  }
  return found.sort();
}

/** Installing dependencies, for a checkout that has none yet (the integration worktree). */
export function planInstall(root) {
  const steps = projectDirs(root, "uv.lock").map((dir) => step(`uv sync (${dir})`, "uv", ["sync", "--frozen"], dir));
  if (existsSync(path.join(root, "pnpm-lock.yaml"))) steps.push(step("pnpm install", "pnpm", ["install", "--frozen-lockfile"]));
  return steps;
}

/** The whole suite: lint, types, tests with coverage, architecture, documentation, image names. */
export function planFull(root) {
  const steps = [];
  for (const dir of projectDirs(root, "pyproject.toml")) {
    const text = read(root, `${dir}/pyproject.toml`);
    const has = (tool) => new RegExp(tool, "i").test(text);
    if (has("ruff")) steps.push(step(`ruff check (${dir})`, "uv", ["run", "ruff", "check", "."], dir), step(`ruff format (${dir})`, "uv", ["run", "ruff", "format", "--check", "."], dir));
    if (has("pyright")) steps.push(step(`pyright (${dir})`, "uv", ["run", "pyright"], dir));
    if (has("bandit") && existsSync(path.join(root, dir, "app"))) steps.push(step(`bandit (${dir})`, "uv", ["run", "bandit", "-q", "-c", "pyproject.toml", "-r", "app"], dir));
    if (has("pytest")) steps.push(step(`pytest with coverage (${dir})`, "uv", ["run", "pytest", "-q"], dir));
  }
  if (existsSync(path.join(root, "pnpm-workspace.yaml"))) {
    for (const script of ["typecheck", "lint", "test"]) steps.push(step(`pnpm ${script}`, "pnpm", ["-r", "--if-present", script]));
  }
  for (const [name, script, args] of [["architecture", "architecture.mjs", ["check"]], ["documentation", "docs.mjs", ["check"]], ["image names", "images.mjs", ["check"]]]) {
    if (existsSync(path.join(root, "scripts", script))) steps.push(step(name, "node", [`scripts/${script}`, ...args]));
  }
  return steps;
}

/** Runs one step; never throws. */
export function execute(root, s) {
  const cwd = path.join(root, s.cwd);
  const started = Date.now();
  let ok = true;
  let output = "";
  try {
    if (s.tool === "pnpm") output = String(runPnpm(s.args, { cwd, encoding: "utf8", stdio: "pipe" }) ?? "");
    else {
      const result = spawnSync(s.tool === "node" ? process.execPath : s.tool, s.args, { cwd, encoding: "utf8", shell: false });
      output = `${result.stdout ?? ""}${result.stderr ?? ""}${result.error ? String(result.error) : ""}`;
      ok = result.status === 0 && !result.error;
    }
  } catch (error) {
    ok = false;
    output = `${error.stdout ?? ""}${error.stderr ?? ""}${error.message ?? ""}`;
  }
  return { name: s.name, ok, output, seconds: Math.round((Date.now() - started) / 100) / 10 };
}

export function runSteps(root, steps, { exec = execute, log = console.log } = {}) {
  const results = [];
  for (const s of steps) {
    log(`  … ${s.name}`);
    const result = exec(root, s);
    results.push(result);
    log(`  ${result.ok ? "ok  " : "FAIL"} ${s.name} (${result.seconds}s)`);
    if (!result.ok) log(result.output.trim().split("\n").slice(-25).join("\n"));
  }
  return { ok: results.every((r) => r.ok), results };
}

// --- remembered full runs, keyed by the committed tree ---------------------------------------
const recordFile = (root) => path.join(root, ".sdlc", "run", "full.json");

export function treeOf(root, ref = "HEAD") {
  const clean = git(root, ["status", "--porcelain"]).trim() === "";
  return { tree: git(root, ["rev-parse", `${ref}^{tree}`]).trim(), clean };
}

export function readRuns(root) {
  try { return JSON.parse(readFileSync(recordFile(root), "utf8")).runs ?? {}; } catch { return {}; }
}

export function recordRun(root, tree, ok) {
  const runs = { ...readRuns(root), [tree]: { ok, at: new Date().toISOString() } };
  const keep = Object.entries(runs).sort((a, b) => b[1].at.localeCompare(a[1].at)).slice(0, 20);
  mkdirSync(path.dirname(recordFile(root)), { recursive: true });
  writeFileSync(recordFile(root), `${JSON.stringify({ runs: Object.fromEntries(keep) }, null, 2)}\n`);
}

function main(argv) {
  const { positionals, values: opts } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: { base: { type: "string" }, files: { type: "string" }, static: { type: "boolean", default: false }, reuse: { type: "boolean", default: false }, "dry-run": { type: "boolean", default: false }, root: { type: "string" } },
  });
  const root = path.resolve(opts.root ?? process.cwd());
  const mode = positionals[0];
  if (mode !== "unit" && mode !== "full") {
    console.error("Usage: node scripts/check.mjs unit [--base <ref>] [--files a,b] [--static] | full [--reuse] [--dry-run]");
    return 2;
  }
  let steps;
  if (mode === "unit") {
    const files = opts.files ? opts.files.split(",").map((f) => f.trim()).filter(Boolean) : changedFiles(root, opts.base);
    if (files.length === 0) { console.log("check unit: no changed files, nothing to check."); return 0; }
    console.log(`check unit: ${files.length} changed file(s)`);
    steps = planUnit(root, files, { staticOnly: opts.static });
  } else {
    const { tree, clean } = treeOf(root);
    if (opts.reuse && clean && readRuns(root)[tree]?.ok) { console.log(`check full: this tree already passed (${readRuns(root)[tree].at}); not run again.`); return 0; }
    steps = planFull(root);
  }
  if (steps.length === 0) { console.log("check: no step applies to this change."); return 0; }
  if (opts["dry-run"]) { for (const s of steps) console.log(`  ${s.cwd === "." ? "" : `${s.cwd}: `}${s.tool} ${s.args.join(" ")}`); return 0; }
  const { ok, results } = runSteps(root, steps);
  if (mode === "full") { const { tree, clean } = treeOf(root); if (clean) recordRun(root, tree, ok); }
  console.log(ok ? `check ${mode}: all ${results.length} step(s) passed.` : `check ${mode}: ${results.filter((r) => !r.ok).length} of ${results.length} step(s) failed.`);
  return ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) process.exit(main(process.argv.slice(2)));
