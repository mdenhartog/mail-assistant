#!/usr/bin/env node
// Rolling integration run (skills sdlc-flow phase 5, verify): the full suite on the integrated state
// of `main`, in the background, so units can be built without waiting for it and an integration
// problem shows up one run after the merge instead of at the end of the feature.
//
//   node scripts/integrate.mjs request [--ref main]   ask for a run (starts the runner when none is active)
//   node scripts/integrate.mjs status [--json]        what is running and the last result
//   node scripts/integrate.mjs run                    the runner itself (started by `request`)
//
// One run at a time. Requests that arrive during a run are merged: when it ends, one more run follows
// for the newest commit, so 50 merges never mean 50 runs. The run happens in its own worktree
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

export const emptyState = () => ({ requested: null, running: null, last: null });

export function readState(root) {
  try { return { ...emptyState(), ...JSON.parse(readFileSync(stateFile(root), "utf8")) }; } catch { return emptyState(); }
}

export function writeState(root, state) {
  mkdirSync(runDir(root), { recursive: true });
  const tmp = `${stateFile(root)}.${process.pid}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(state, null, 2)}\n`);
  renameSync(tmp, stateFile(root));
}

/** The commit that still needs a run, or null when the last run already covers the newest request. */
export function nextTarget(state) {
  return state.requested && state.requested.sha !== state.last?.ref ? state.requested : null;
}

/** True when a process with this id is alive. */
export function alive(pid) {
  if (!pid) return false;
  try { process.kill(pid, 0); return true; } catch (error) { return error.code === "EPERM"; }
}

export function applyRequest(state, sha, now = new Date().toISOString()) {
  return { ...state, requested: { sha, at: now } };
}

/** Whether `request` must start a runner: something to do and nobody doing it. */
export function needsRunner(state, isAlive = alive) {
  return nextTarget(state) !== null && !(state.running && isAlive(state.running.pid));
}

export function applyResult(state, result) {
  return { ...state, running: null, last: { ...result, reported: false } };
}

/** The runner loop: keeps going while a newer request is waiting. `integrate(sha)` does the work. */
export function runLoop({ read, write, integrate, pid = process.pid, now = () => new Date().toISOString() }) {
  let runs = 0;
  while (true) {
    const target = nextTarget(read());
    if (!target) break;
    write({ ...read(), running: { pid, sha: target.sha, startedAt: now() } });
    const result = integrate(target.sha);
    write(applyResult(read(), { ref: target.sha, ok: result.ok, failures: result.failures, finishedAt: now() }));
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
  const state = applyRequest(readState(root), sha);
  const start = needsRunner(state);
  writeState(root, state);
  if (!start) { console.log(nextTarget(state) ? `integrate: a run is active; one more follows for ${sha.slice(0, 7)}.` : `integrate: ${sha.slice(0, 7)} was already tested.`); return 0; }
  mkdirSync(runDir(root), { recursive: true });
  const out = openSync(path.join(runDir(root), "integrate.log"), "w");
  const child = spawn(process.execPath, [fileURLToPath(import.meta.url), "run", "--root", root], { cwd: root, detached: true, stdio: ["ignore", out, out], windowsHide: true });
  child.unref();
  console.log(`integrate: run started in the background for ${sha.slice(0, 7)} (log: .sdlc/run/integrate.log).`);
  return 0;
}

export function describe(state, isAlive = alive) {
  const short = (sha) => (sha ?? "").slice(0, 7);
  if (state.running && isAlive(state.running.pid)) return `running on ${short(state.running.sha)} since ${state.running.startedAt}`;
  if (!state.last) return "no run yet";
  const failed = (state.last.failures ?? []).map((f) => f.name).join(", ");
  return state.last.ok ? `green on ${short(state.last.ref)} (${state.last.finishedAt})` : `RED on ${short(state.last.ref)}: ${failed} (${state.last.finishedAt})`;
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
