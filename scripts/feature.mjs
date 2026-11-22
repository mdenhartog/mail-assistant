#!/usr/bin/env node
// Feature branch and units (skills git-workflow, sdlc-flow phases 5 and 8): every unit is built in its own
// local branch and worktree, and lands in the feature branch without a pull request and without CI. The
// feature branch gets one pull request at the end (phase 8), so CI runs once per feature, not once per unit.
//
//   node scripts/feature.mjs start <feature> [--fix] [--close-old-prs]
//                                                        create (or reuse) feat/<INT-nnn>/<feature> + its worktree;
//                                                        unit branches of an older kit (feat/<INT-nnn>/<feature>/<nn>)
//                                                        move to unit/…, so a running feature continues after an upgrade
//   node scripts/feature.mjs unit <U-feature-nn>         branch unit/<INT-nnn>/<feature>/<nn> + worktree from the
//                                                        feature branch (also for a repair round after CI)
//   node scripts/feature.mjs land <U-feature-nn> [--no-check]
//                                                        check.mjs unit, merge into the feature branch with the
//                                                        Refs/Unit trailers, remove the worktree and branch, ask
//                                                        for an integration run of the feature branch
//   node scripts/feature.mjs trailers <feature>          the Refs/Unit lines for the squash-merge message
//
// The intent of a feature comes from docs/plans/<feature>/index.md. Worktrees live in .worktrees/<branch>.
// Exit code 0 on success, 1 on a failure (the reason is printed), 2 on wrong usage.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { existingRef, featureBranch, featureCandidates, parseUnitBranch, parseUnitId, stripRemote, unitBranch } from "./lib/branches.mjs";
import { readPlans, readWorktrees } from "./status.mjs";

class FeatureError extends Error {}

function git(cwd, args, { allowFail = false } = {}) {
  const r = spawnSync("git", args, { cwd, encoding: "utf8" });
  if (r.status !== 0 && !allowFail) throw new FeatureError(`git ${args.join(" ")} failed:\n${(r.stderr || r.stdout).trim()}`);
  return { ok: r.status === 0, out: (r.stdout ?? "").trim(), err: (r.stderr ?? "").trim() };
}

/** The main worktree: plans, .worktrees and .sdlc live there, whichever worktree the command runs in. */
export function mainRoot(cwd) {
  return readWorktrees(cwd)[0]?.path ?? path.resolve(cwd);
}

function planOf(root, feature) {
  const plan = readPlans(path.join(root, "docs", "plans")).find((p) => p.feature === feature);
  if (!plan) throw new FeatureError(`no plan for feature '${feature}' in docs/plans/ (phase 4 writes it first).`);
  if (!plan.intent) throw new FeatureError(`the plan of '${feature}' names no intent (index.md front matter: intent: INT-nnn).`);
  return plan;
}

const worktreeOf = (root, branch) => readWorktrees(root).find((w) => w.branch === branch)?.path ?? "";
const worktreePath = (root, branch) => path.join(root, ".worktrees", ...branch.split("/"));
const localBranch = (root, name) => git(root, ["rev-parse", "--verify", "-q", `refs/heads/${name}`], { allowFail: true }).ok;
const dirty = (cwd) => git(cwd, ["status", "--porcelain"]).out !== "";

/** The feature branch of a feature as a local branch name, or "" when there is none yet. */
export function findFeatureBranch(root, { intent, feature }) {
  const ref = existingRef(root, featureCandidates({ intent, feature }));
  if (!ref) return "";
  const name = stripRemote(ref);
  if (!localBranch(root, name)) git(root, ["branch", "--track", name, ref]);
  return name;
}

function ensureWorktree(root, branch) {
  const existing = worktreeOf(root, branch);
  if (existing) return existing;
  const wt = worktreePath(root, branch);
  git(root, ["worktree", "add", wt, branch]);
  return wt;
}

/** The Unit trailers on main: units that are done there. */
function doneOnMain(root) {
  const trunk = existingRef(root, ["main", "master"]);
  if (!trunk) return new Set();
  return new Set([...git(root, ["log", trunk, "--format=%B"]).out.matchAll(/^Unit:\s*(U-[a-z0-9-]+-\d+)\s*$/gm)].map((m) => m[1]));
}

/**
 * Unit branches of an older kit (feat|fix/<INT-nnn>/<feature>/<nn>: a branch, a pull request and a CI run per
 * unit) move to unit/<INT-nnn>/<feature>/<nn>, so the feature branch can exist next to them and the build
 * continues where it was. A unit already on main is only renamed (reported as safe to delete); a unit only on
 * the remote gets a local branch.
 * The remote's old branches block pushing the feature branch (a ref conflict on the remote too): they are
 * reported, and closed only with `closeRemote` (their pull requests are closed and the branches deleted).
 */
export function adoptLegacyUnits(root, plan, { closeRemote = false } = {}) {
  const refs = git(root, ["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin"]).out.split("\n").filter(Boolean);
  const done = doneOnMain(root);
  const result = { moved: [], done: [], remote: [], closed: [] };
  for (const ref of refs) {
    const info = parseUnitBranch(ref);
    if (!info?.legacy || info.feature !== plan.feature) continue;
    const remote = ref.startsWith("origin/");
    const name = stripRemote(ref);
    if (remote) result.remote.push(name);
    const target = unitBranch(info.intent, info.feature, info.nn);
    if (localBranch(root, target)) continue;
    if (!remote) {
      // Renamed even when the unit is done: the old name alone blocks the feature branch (ref conflict).
      git(root, ["branch", "-m", name, target]); // a worktree on the branch follows the rename
      (done.has(info.unit) ? result.done : result.moved).push({ from: name, to: target });
    } else if (!done.has(info.unit) && !localBranch(root, name)) {
      git(root, ["branch", "--no-track", target, ref]);
      result.moved.push({ from: ref, to: target });
    }
  }
  if (closeRemote) {
    for (const name of result.remote) {
      const pr = spawnSync("gh", ["pr", "close", name, "--delete-branch", "--comment", `Moved into the feature branch: units now land there and the feature has one pull request (claude-sdlc-kit).`], { cwd: root, encoding: "utf8" });
      if (pr.status !== 0) git(root, ["push", "origin", "--delete", name]);
      result.closed.push(name);
    }
    result.remote = [];
  }
  return result;
}

export function start(cwd, feature, { fix = false, closeRemote = false } = {}) {
  const root = mainRoot(cwd);
  const plan = planOf(root, feature);
  const adopted = adoptLegacyUnits(root, plan, { closeRemote });
  let branch = findFeatureBranch(root, plan);
  const created = !branch;
  if (created) {
    branch = featureBranch(plan.intent, feature, fix ? "fix" : "feat");
    const trunk = existingRef(root, ["main", "master"]);
    if (!trunk) throw new FeatureError("no main branch to start the feature branch from.");
    git(root, ["branch", branch, trunk]);
  }
  return { branch, created, worktree: ensureWorktree(root, branch), adopted };
}

function unitContext(root, id) {
  const parsed = parseUnitId(id);
  if (!parsed) throw new FeatureError(`'${id}' is not a unit id (U-<feature>-<nn>).`);
  const plan = planOf(root, parsed.feature);
  if (!plan.units.some((u) => u.id === id)) throw new FeatureError(`${id} is not a unit of the plan docs/plans/${parsed.feature}/.`);
  const feature = findFeatureBranch(root, plan);
  if (!feature) throw new FeatureError(`feature '${parsed.feature}' has no feature branch yet: node scripts/feature.mjs start ${parsed.feature}`);
  return { plan, feature, branch: unitBranch(plan.intent, parsed.feature, parsed.nn) };
}

export function openUnit(cwd, id) {
  const root = mainRoot(cwd);
  const { feature, branch } = unitContext(root, id);
  const existed = localBranch(root, branch);
  const existing = worktreeOf(root, branch);
  if (existing) return { branch, feature, worktree: existing, created: false };
  const wt = worktreePath(root, branch);
  git(root, existed ? ["worktree", "add", wt, branch] : ["worktree", "add", "-b", branch, wt, feature]);
  return { branch, feature, worktree: wt, created: !existed };
}

export function land(cwd, id, { check = true, integrate = true, log = console.log } = {}) {
  const root = mainRoot(cwd);
  const { plan, feature, branch } = unitContext(root, id);
  if (!localBranch(root, branch)) throw new FeatureError(`${id} has no branch ${branch} (open it with: node scripts/feature.mjs unit ${id}).`);
  const unitTree = worktreeOf(root, branch);
  if (unitTree && dirty(unitTree)) throw new FeatureError(`${id}: the worktree ${unitTree} has uncommitted changes; commit them first.`);
  const ahead = Number(git(root, ["rev-list", "--count", `${feature}..${branch}`]).out);
  if (ahead === 0) throw new FeatureError(`${id}: ${branch} has no commits that ${feature} does not have; nothing to land.`);

  if (check && unitTree && existsSync(path.join(unitTree, "scripts", "check.mjs"))) {
    log(`land: node scripts/check.mjs unit --base ${feature} (in ${unitTree})`);
    const r = spawnSync(process.execPath, ["scripts/check.mjs", "unit", "--base", feature], { cwd: unitTree, stdio: "inherit" });
    if (r.status !== 0) throw new FeatureError(`${id}: check.mjs unit failed; fix it in the unit's worktree and land again.`);
  }

  const featureTree = ensureWorktree(root, feature);
  if (dirty(featureTree)) throw new FeatureError(`the feature worktree ${featureTree} has uncommitted changes; units land in a clean feature branch.`);
  const name = plan.units.find((u) => u.id === id)?.name ?? "";
  const merge = git(featureTree, ["merge", "--no-ff", "-m", `Merge ${id} into ${feature}`, "-m", `${name ? `${name}\n\n` : ""}Refs: ${plan.intent}\nUnit: ${id}`, branch], { allowFail: true });
  if (!merge.ok) {
    git(featureTree, ["merge", "--abort"], { allowFail: true });
    throw new FeatureError(`${id} does not merge cleanly into ${feature}:\n${merge.out || merge.err}\nUpdate the unit in its worktree first (git rebase ${feature}), rerun its tests, then land again.`);
  }
  // The unit is in the feature branch now; a leftover worktree or branch is only reported.
  const removed = !unitTree || git(root, ["worktree", "remove", unitTree], { allowFail: true }).ok;
  const deleted = removed && git(root, ["branch", "-D", branch], { allowFail: true }).ok; // merged into the feature branch, not main: -d would refuse
  if (!deleted) log(`land: ${id} landed, but ${unitTree || branch} could not be removed; remove it by hand (git worktree remove, git branch -D).`);

  let integration = "";
  const project = (() => { try { return JSON.parse(readFileSync(path.join(root, ".sdlc", "project.json"), "utf8")); } catch { return {}; } })();
  if (integrate && project.integration !== false && existsSync(path.join(root, "scripts", "integrate.mjs"))) {
    const r = spawnSync(process.execPath, [path.join(root, "scripts", "integrate.mjs"), "request", "--ref", feature], { cwd: root, encoding: "utf8" });
    integration = (r.stdout ?? "").trim();
  }
  return { feature, branch, featureTree, integration };
}

/** The Refs and Unit trailers of everything on the feature branch that main does not have yet. */
export function trailers(cwd, feature) {
  const root = mainRoot(cwd);
  const plan = planOf(root, feature);
  const branch = findFeatureBranch(root, plan);
  if (!branch) throw new FeatureError(`feature '${feature}' has no feature branch.`);
  const trunk = existingRef(root, ["main", "master"]);
  const body = git(root, ["log", "--reverse", "--format=%B", `${trunk}..${branch}`]).out;
  const pick = (key) => [...new Set([...body.matchAll(new RegExp(`^${key}:\\s*(\\S+)\\s*$`, "gm"))].map((m) => m[1]))];
  const refs = pick("Refs");
  const units = pick("Unit").sort();
  return [...(refs.length ? refs : [plan.intent]).map((r) => `Refs: ${r}`), ...units.map((u) => `Unit: ${u}`)].join("\n");
}

const USAGE = "Usage: node scripts/feature.mjs start <feature> [--fix] [--close-old-prs] | unit <U-feature-nn> | land <U-feature-nn> [--no-check] | trailers <feature>";

export function main(argv, cwd = process.cwd()) {
  const { positionals, values } = parseArgs({ args: argv, allowPositionals: true, options: { fix: { type: "boolean", default: false }, "close-old-prs": { type: "boolean", default: false }, "no-check": { type: "boolean", default: false }, root: { type: "string" } } });
  const [command, target] = positionals;
  const at = path.resolve(values.root ?? cwd);
  if (!command || !target) { console.error(USAGE); return 2; }
  try {
    if (command === "start") {
      const r = start(at, target, { fix: values.fix, closeRemote: values["close-old-prs"] });
      const a = r.adopted;
      for (const m of a.moved) console.log(`feature: unit branch of the older kit ${m.from} → ${m.to} (continue it with: node scripts/feature.mjs unit …, then land it).`);
      if (a.done.length) console.log(`feature: units already on main, renamed out of the way and safe to delete (git branch -D): ${a.done.map((m) => m.to).join(", ")}`);
      if (a.closed.length) console.log(`feature: closed the old per-unit pull requests and deleted their remote branches: ${a.closed.join(", ")}`);
      console.log(`feature: ${r.created ? "created" : "using"} ${r.branch} (worktree ${r.worktree}). Open units with: node scripts/feature.mjs unit U-${target}-01`);
      if (a.remote.length) {
        console.log(`feature: the remote still has unit branches of the older kit (each with its own pull request and CI run): ${a.remote.join(", ")}.`);
        console.log(`  Their work is in local unit/ branches now. ${r.branch} cannot be pushed while they exist; after the user agrees: node scripts/feature.mjs start ${target} --close-old-prs`);
      }
    } else if (command === "unit") {
      const r = openUnit(at, target);
      console.log(`unit: ${r.created ? "created" : "using"} ${r.branch} from ${r.feature} (worktree ${r.worktree}).`);
    } else if (command === "land") {
      const r = land(at, target, { check: !values["no-check"] });
      console.log(`land: ${target} merged into ${r.feature}; worktree and branch ${r.branch} removed.${r.integration ? ` ${r.integration}` : ""}`);
      console.log("No pull request and no CI per unit: the feature branch gets one pull request in phase 8.");
    } else if (command === "trailers") {
      console.log(trailers(at, target));
    } else { console.error(USAGE); return 2; }
    return 0;
  } catch (error) {
    if (!(error instanceof FeatureError)) throw error;
    console.error(`feature: ${error.message}`);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) process.exit(main(process.argv.slice(2)));
