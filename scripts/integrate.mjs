#!/usr/bin/env node
// Rolling integration run (skills sdlc-flow phase 5, verify): the full suite on the integrated state
// of a branch, in the background, so units can be built without waiting for it and an integration
// problem shows up one run after a unit lands instead of at the end of the feature. `node scripts/feature.mjs
// land` asks for a run of the feature branch; the stop check asks for one when `main` has moved.
//
//   node scripts/integrate.mjs request [--ref main]   ask for a run (starts the runner when none is active)
//   node scripts/integrate.mjs status [--json]        what is running and the last result
//   node scripts/integrate.mjs run                    the runner itself (started by `request`)
//
// One run at a time. Requests are kept per branch (main and each feature branch) and merged: when a run
// ends, one more run follows for the newest commit of each branch that is still waiting, oldest request
// first, so 50 landed units never mean 50 runs and a request for main never pushes a feature branch out
// (state: `pending` per branch, `tested` = last tested commit per branch). The run happens in its own worktree
// (.sdlc/run/integration), never in the folders agents are working in. The stop check and
// docs/STATUS.md report a failed run once.
import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, openSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { planFull, planInstall, recordRun, runSteps } from "./check.mjs";

const runDir = (root) => path.join(root, ".sdlc", "run");
const stateFile = (root) => path.join(runDir(root), "integrate.json");

function git(root, args) {
  const result = spawnSync("git", args, { cwd: root, encoding: "utf8" });
  return result.status === 0 ? result.stdout.trim() : "";
}

export const emptyState = () => ({ requested: null, pending: {}, tested: {}, running: null, last: null });

export function readState(root) {
  try { return { ...emptyState(), ...JSON.parse(readFileSync(stateFile(root), "utf8")) }; } catch { return emptyState(); }
}

export function writeState(root, state) {
  mkdirSync(runDir(root), { recursive: true });
  const tmp = `${stateFile(root)}.${process.pid}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(state, null, 2)}\n`);
  renameSync(tmp, stateFile(root));
}

/** The commit that still needs a run ({ sha, at, branch }, the oldest waiting branch first), or null. */
export function nextTarget(state) {
  const tested = state.tested ?? {};
  const waiting = Object.entries(state.pending ?? {})
    .filter(([branch, r]) => r.sha !== tested[branch] && r.sha !== state.last?.ref)
    .sort(([, a], [, b]) => String(a.at).localeCompare(String(b.at)));
  if (waiting.length) return { ...waiting[0][1], branch: waiting[0][0] };
  // A state file of an older kit has one request and no branches.
  const legacy = Object.keys(state.pending ?? {}).length === 0 && state.requested && !state.requested.branch;
  return legacy && state.requested.sha !== state.last?.ref ? state.requested : null;
}

/** True when a process with this id is alive. */
export function alive(pid) {
  if (!pid) return false;
  try { process.kill(pid, 0); return true; } catch (error) { return error.code === "EPERM"; }
}

/** A request for `sha` on `branch`: replaces that branch's waiting commit, keeps its place in the queue. */
export function applyRequest(state, sha, now = new Date().toISOString(), branch = "main") {
  const at = state.pending?.[branch]?.at ?? now;
  return { ...state, requested: { sha, at: now, branch }, pending: { ...state.pending, [branch]: { sha, at } } };
}

/** Whether `request` must start a runner: something to do and nobody doing it. */
export function needsRunner(state, isAlive = alive) {
  return nextTarget(state) !== null && !(state.running && isAlive(state.running.pid));
}

/** A finished run of `result.ref` (a commit): no branch waits for that commit any more. */
export function applyResult(state, result) {
  const pending = Object.fromEntries(Object.entries(state.pending ?? {}).filter(([, r]) => r.sha !== result.ref));
  const tested = result.branch ? { ...state.tested, [result.branch]: result.ref } : { ...state.tested };
  return { ...state, pending, tested, running: null, last: { ...result, reported: false } };
}

/** The runner loop: keeps going while a newer request is waiting. `integrate(sha)` does the work. */
export function runLoop({ read, write, integrate, pid = process.pid, now = () => new Date().toISOString() }) {
  let runs = 0;
  while (true) {
    const target = nextTarget(read());
    if (!target) break;
    const branch = target.branch ? { branch: target.branch } : {};
    write({ ...read(), running: { pid, sha: target.sha, ...branch, startedAt: now() } });
    const result = integrate(target.sha);
    write(applyResult(read(), { ref: target.sha, ...branch, ok: result.ok, failures: result.failures, finishedAt: now() }));
    runs += 1;
  }
  return runs;
}

/** Checks `sha` out in the integration worktree, installs dependencies, runs the whole suite. */
function integrateCommit(root, sha) {
  const wt = path.join(runDir(root), "integration");
  if (!existsSync(path.join(wt, ".git"))) git(root, ["worktree", "add", "--detach", wt, sha]);
  else spawnSync("git", ["checkout", "--detach", "-f", sha], { cwd: wt, encoding: "utf8" });
  if (existsSync(path.join(root, ".env")) && !existsSync(path.join(wt, ".env"))) copyFileSync(path.join(root, ".env"), path.join(wt, ".env"));
  const log = () => {};
  const install = runSteps(wt, planInstall(wt), { log });
  const full = install.ok ? runSteps(wt, planFull(wt), { log }) : install;
  const tree = git(root, ["rev-parse", `${sha}^{tree}`]);
  if (tree) recordRun(root, tree, full.ok);
  return { ok: full.ok, failures: full.results.filter((r) => !r.ok).map((r) => ({ name: r.name, tail: r.output.trim().slice(-1500) })) };
}

function request(root, ref) {
  const sha = git(root, ["rev-parse", "--verify", "-q", ref]);
  if (!sha) { console.error(`integrate: unknown ref '${ref}'`); return 1; }
  const before = readState(root);
  if (before.tested?.[ref] === sha) { console.log(`integrate: ${ref} at ${sha.slice(0, 7)} was already tested.`); return 0; }
  const state = applyRequest(before, sha, undefined, ref);
  const start = needsRunner(state);
  writeState(root, state);
  if (!start) { console.log(nextTarget(state) ? `integrate: a run is active; ${ref} at ${sha.slice(0, 7)} follows.` : `integrate: ${sha.slice(0, 7)} was already tested.`); return 0; }
  mkdirSync(runDir(root), { recursive: true });
  const out = openSync(path.join(runDir(root), "integrate.log"), "w");
  const child = spawn(process.execPath, [fileURLToPath(import.meta.url), "run", "--root", root], { cwd: root, detached: true, stdio: ["ignore", out, out], windowsHide: true });
  child.unref();
  console.log(`integrate: run started in the background for ${sha.slice(0, 7)} (log: .sdlc/run/integrate.log).`);
  return 0;
}

export function describe(state, isAlive = alive) {
  const short = (sha) => (sha ?? "").slice(0, 7);
  const on = (run) => `${short(run.sha ?? run.ref)}${run.branch ? ` (${run.branch})` : ""}`;
  if (state.running && isAlive(state.running.pid)) return `running on ${on(state.running)} since ${state.running.startedAt}`;
  if (!state.last) return "no run yet";
  const failed = (state.last.failures ?? []).map((f) => f.name).join(", ");
  return state.last.ok ? `green on ${on(state.last)} (${state.last.finishedAt})` : `RED on ${on(state.last)}: ${failed} (${state.last.finishedAt})`;
}

function main(argv) {
  const { positionals, values: opts } = parseArgs({ args: argv, allowPositionals: true, options: { ref: { type: "string", default: "main" }, json: { type: "boolean", default: false }, root: { type: "string" } } });
  const root = path.resolve(opts.root ?? process.cwd());
  const command = positionals[0];
  if (command === "request") return request(root, opts.ref);
  if (command === "status") {
    const state = readState(root);
    console.log(opts.json ? JSON.stringify(state, null, 2) : `integration: ${describe(state)}`);
    return 0;
  }
  if (command === "run") {
    runLoop({ read: () => readState(root), write: (s) => writeState(root, s), integrate: (sha) => integrateCommit(root, sha) });
    return 0;
  }
  console.error("Usage: node scripts/integrate.mjs request [--ref main] | status [--json] | run");
  return 2;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) process.exit(main(process.argv.slice(2)));
