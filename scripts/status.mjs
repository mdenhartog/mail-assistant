// Build status (skill `build-status`): what is being built right now, split intent -> feature -> unit.
// Derived from the repository, never typed: the plans in docs/plans, the intents in docs/intent,
// git worktrees and branches, the TDD commits on each branch, `Unit:` trailers on main and (when the
// `gh` CLI is available) pull requests. The page is docs/STATUS.md in the main worktree; it is
// gitignored (generated, so parallel worktrees never conflict on it).
//   node scripts/status.mjs                 write docs/STATUS.md and print the one-line summary
//   node scripts/status.mjs --stdout        print the page instead of writing it
//   node scripts/status.mjs --escape        escape plan text for a Git host issue (Control Room)
//   node scripts/status.mjs --no-prs        do not ask the Git host for pull requests
//   node scripts/status.mjs --quiet         print nothing (used by the plugin hook)
//   node scripts/status.mjs --root <dir>    project root (default: the current directory)
// Conventions: branch `feat|fix/<INT-nnn>/<feature>/<nn>` is unit `U-<feature>-<nn>` of the plan
// docs/plans/<feature>.md; every commit carries trailers `Refs: INT-nnn` and `Unit: U-<feature>-<nn>`
// and the squash-merge message keeps them (that is how a merged unit is recognised as done).
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BRANCH = /^(?:origin\/)?(?:feat|fix)\/(INT-\d+)\/([a-z0-9][a-z0-9-]*)\/(\d+)$/;

export function parseBranch(name) {
  const m = BRANCH.exec(name);
  return m ? { intent: m[1], feature: m[2], unit: `U-${m[2]}-${m[3]}` } : null;
}

function frontMatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (!m) return { data: {}, body: text };
  const data = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([A-Za-z_-]+):\s*(.*?)\s*(?:#.*)?$/.exec(line);
    if (kv) data[kv[1]] = kv[2].replace(/^["']|["']$/g, "");
  }
  return { data, body: text.slice(m[0].length) };
}

export function parseIntent(text, file = "") {
  const { data } = frontMatter(text);
  const id = data.id ?? /INT-\d+/.exec(path.basename(file))?.[0] ?? "";
  return { id, title: data.title ?? id, status: data.status ?? "draft" };
}

export function parsePlan(text, file = "") {
  const { data, body } = frontMatter(text);
  const feature = data.feature ?? path.basename(file, ".md");
  const units = [];
  let current = null;
  for (const line of body.split(/\r?\n/)) {
    const head = /^###\s+(U-[a-z0-9-]+-\d+):\s*(.+?)\s*$/.exec(line);
    if (head) { current = { id: head[1], name: head[2], layer: "", dependsOn: [], parallel: false }; units.push(current); continue; }
    if (/^#{1,3}\s/.test(line)) { current = null; continue; }
    if (!current) continue;
    const field = /^-\s+([A-Za-z ]+):\s*(.*)$/.exec(line);
    if (!field) continue;
    const key = field[1].trim().toLowerCase();
    if (key === "layer") current.layer = field[2].trim();
    else if (key === "depends on") current.dependsOn = field[2].split(/[,\s]+/).filter((d) => /^U-/.test(d));
    else if (key === "parallel") current.parallel = /^yes/i.test(field[2].trim());
  }
  return { intent: data.intent ?? "", feature, title: data.title ?? feature, units };
}

/** The TDD stage from the commit subjects on a branch, oldest first. */
export function unitStage(subjects) {
  let stage = "started";
  for (const subject of subjects) {
    const type = /^(\w+)(?:\([^)]*\))?!?:/.exec(subject)?.[1];
    if (type === "test") stage = "red";
    else if (type === "feat" || type === "fix") stage = "green";
    else if (type === "refactor") stage = "refactor";
  }
  return stage;
}

const stripRemote = (name) => name.replace(/^origin\//, "");

function aggregate(statuses) {
  if (statuses.length === 0) return "no-plan";
  if (statuses.every((s) => s === "done")) return "done";
  if (statuses.some((s) => s !== "todo" && s !== "waiting")) return "in-progress";
  return statuses.some((s) => s === "done") ? "in-progress" : "todo";
}

export function buildModel({ intents = [], plans = [], branches = [], doneUnits = new Set(), prs = [] }) {
  const prByHead = new Map(prs.map((p) => [stripRemote(p.head), p]));
  const branchByUnit = new Map();
  const unplanned = [];
  const planned = new Set(plans.flatMap((p) => p.units.map((u) => u.id)));
  for (const b of branches) {
    const info = parseBranch(b.name);
    if (!info) continue;
    const merged = prByHead.get(stripRemote(b.name))?.state === "MERGED";
    if (merged) continue;
    if (!planned.has(info.unit)) { if (!unplanned.some((u) => stripRemote(u.name) === stripRemote(b.name))) unplanned.push(b); continue; }
    const known = branchByUnit.get(info.unit);
    if (!known || (b.worktree && !known.worktree)) branchByUnit.set(info.unit, { ...known, ...b, name: stripRemote(b.name) });
  }
  const done = new Set(doneUnits);
  for (const p of prs) if (p.state === "MERGED") { const info = parseBranch(p.head); if (info) done.add(info.unit); }

  const nowBuilding = [];
  const waitingForYou = [];
  const featureOf = (plan) => {
    const units = plan.units.map((u) => {
      const branch = branchByUnit.get(u.id);
      const pr = branch ? prByHead.get(branch.name) : null;
      const base = { id: u.id, name: u.name, feature: plan.feature, intent: plan.intent, layer: u.layer, parallel: u.parallel };
      if (done.has(u.id)) return { ...base, status: "done" };
      if (branch) {
        const open = pr?.state === "OPEN" && !pr.isDraft;
        const unit = { ...base, status: open ? "review" : "in-progress", stage: open ? "review" : unitStage(branch.subjects ?? []), worktree: branch.worktree ?? "", branch: branch.name, url: pr?.url ?? "" };
        (open ? waitingForYou : nowBuilding).push(unit);
        return unit;
      }
      const waitingOn = u.dependsOn.filter((d) => !done.has(d));
      return waitingOn.length ? { ...base, status: "waiting", waitingOn } : { ...base, status: "todo" };
    });
    const doneCount = units.filter((u) => u.status === "done").length;
    return { feature: plan.feature, title: plan.title, units, progress: { done: doneCount, total: units.length }, status: aggregate(units.map((u) => u.status)) };
  };

  const known = new Map(intents.map((i) => [i.id, { ...i, features: [] }]));
  for (const plan of plans) {
    const key = plan.intent || "(no intent)";
    if (!known.has(key)) known.set(key, { id: key, title: plan.intent ? "(intent file not found)" : "Plans without an intent", status: "unknown", features: [] });
    known.get(key).features.push(featureOf(plan));
  }
  const result = [...known.values()].map((i) => {
    const units = i.features.flatMap((f) => f.units);
    return { ...i, status: aggregate(i.features.map((f) => f.status)), progress: { done: units.filter((u) => u.status === "done").length, total: units.length } };
  });
  return { intents: result, nowBuilding, waitingForYou, unplanned };
}

const LABEL = { done: "✅ done", "in-progress": "🔨 in progress", review: "👀 in review", todo: "⬜ todo", waiting: "⏳ waiting", "no-plan": "📝 no plan yet", unknown: "❔ unknown" };
const STAGE = { started: "started", red: "red (failing test written)", green: "green (test passes)", refactor: "refactor", review: "pull request open" };

const plain = (text) => String(text ?? "").replace(/[\r\n]+/g, " ").replace(/\|/g, "\\|").trim();
/** For a Git host issue: text from plans must not add markup, links or @mentions. */
function hostSafe(text) {
  return plain(text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/[\\`*_{}[\]()#+!~]/g, (c) => `\\${c}`)
    .replace(/@/g, "@\u200b")
    .replace(/(https?):\/\//gi, "$1\u200b://");
}

const bar = (done, total) => (total === 0 ? "" : `${"▓".repeat(done)}${"░".repeat(total - done)} `);

export function renderStatus(model, { escape = false } = {}) {
  const c = escape ? hostSafe : plain;
  const worktree = (u) => (u.worktree ? `\`${String(u.worktree).replace(/`/g, "")}\`` : "—");
  const out = ["# Build status", "", "Generated from git and `docs/plans` by `node scripts/status.mjs`; do not edit.", ""];
  if (model.integration) out.push(`Integration (full suite on the merged state of main): ${c(model.integration)}`, "");
  out.push("## Building now", "");
  if (model.nowBuilding.length === 0) out.push("Nothing is being built right now.", "");
  else {
    out.push("| Unit | Name | Feature | Stage | Worktree |", "|---|---|---|---|---|");
    for (const u of model.nowBuilding) out.push(`| ${c(u.id)} | ${c(u.name)} | ${c(u.feature)} | ${STAGE[u.stage] ?? u.stage} | ${worktree(u)} |`);
    out.push("");
  }
  if (model.waitingForYou.length) {
    out.push("## Waiting for you", "", "| Unit | Name | Feature | Pull request |", "|---|---|---|---|");
    for (const u of model.waitingForYou) out.push(`| ${c(u.id)} | ${c(u.name)} | ${c(u.feature)} | ${/^https:\/\//.test(u.url) ? `[open](${u.url})` : "open"} |`);
    out.push("");
  }
  for (const i of model.intents) {
    out.push(`## ${c(i.id)} — ${c(i.title)}`, "", `${LABEL[i.status] ?? i.status}${i.progress.total ? ` · ${i.progress.done} of ${i.progress.total} units done` : ""}`, "");
    for (const f of i.features) {
      out.push(`### ${c(f.feature)} — ${c(f.title)}`, "", `${bar(f.progress.done, f.progress.total)}${f.progress.done} of ${f.progress.total} units done`, "");
      out.push("| Unit | Name | Status | Stage | Worktree |", "|---|---|---|---|---|");
      for (const u of f.units) {
        const status = u.status === "waiting" ? `${LABEL.waiting} on ${u.waitingOn.map(c).join(", ")}` : LABEL[u.status];
        out.push(`| ${c(u.id)} | ${c(u.name)} | ${status} | ${u.stage ? (STAGE[u.stage] ?? u.stage) : "—"} | ${worktree(u)} |`);
      }
      out.push("");
    }
  }
  if (model.unplanned.length) {
    out.push("## Branches without a planned unit", "", ...model.unplanned.map((b) => `- \`${b.name.replace(/`/g, "")}\``), "");
  }
  return `${out.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd()}\n`;
}

// --- reading the repository -------------------------------------------------------------------

function git(args, cwd) {
  const r = spawnSync("git", args, { cwd, encoding: "utf8" });
  return r.status === 0 ? r.stdout : "";
}

/** The first worktree listed is the main one; STATUS.md is written there. */
export function readWorktrees(cwd) {
  const list = [];
  for (const block of git(["worktree", "list", "--porcelain"], cwd).split(/\n\n+/)) {
    const wt = /^worktree (.+)$/m.exec(block)?.[1];
    if (wt) list.push({ path: path.resolve(wt), branch: /^branch refs\/heads\/(.+)$/m.exec(block)?.[1] ?? "" });
  }
  return list;
}

function readDir(dir, pattern) {
  return existsSync(dir) ? readdirSync(dir).filter((f) => pattern.test(f)).sort().map((f) => [f, readFileSync(path.join(dir, f), "utf8")]) : [];
}

function readPullRequests(cwd) {
  const r = spawnSync("gh", ["pr", "list", "--state", "all", "--limit", "200", "--json", "headRefName,state,url,isDraft"], { cwd, encoding: "utf8", timeout: 20_000 });
  if (r.status !== 0) return [];
  try {
    return JSON.parse(r.stdout).map((p) => ({ head: p.headRefName, state: p.state, url: p.url, isDraft: p.isDraft }));
  } catch {
    return [];
  }
}

/** One line on the last rolling integration run (scripts/integrate.mjs), or "" when there is none. */
export function integrationLine(main) {
  try {
    const state = JSON.parse(readFileSync(path.join(main, ".sdlc", "run", "integrate.json"), "utf8"));
    const short = (sha) => String(sha ?? "").slice(0, 7);
    if (state.running) {
      try { process.kill(state.running.pid, 0); return `running on ${short(state.running.sha)}`; } catch { /* the runner is gone */ }
    }
    if (!state.last) return "";
    return state.last.ok ? `green on ${short(state.last.ref)}` : `RED on ${short(state.last.ref)}: ${(state.last.failures ?? []).map((f) => f.name).join(", ")}`;
  } catch {
    return "";
  }
}

export function collect(root, { prs = true } = {}) {
  const worktrees = readWorktrees(root);
  const main = worktrees[0]?.path ?? path.resolve(root);
  const trunk = ["main", "master"].find((b) => git(["rev-parse", "--verify", "-q", b], main).trim()) ?? "HEAD";
  const refs = git(["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin"], main).split("\n").filter(Boolean);
  const branches = refs.filter((r) => parseBranch(r)).map((name) => ({
    name,
    worktree: worktrees.find((w) => w.branch === stripRemote(name)) ? path.relative(main, worktrees.find((w) => w.branch === stripRemote(name)).path).split(path.sep).join("/") : "",
    subjects: git(["log", "--reverse", "--format=%s", `${trunk}..${name}`], main).split("\n").filter(Boolean),
  }));
  const doneUnits = new Set([...git(["log", trunk, "--format=%B"], main).matchAll(/^Unit:\s*(U-[a-z0-9-]+-\d+)\s*$/gm)].map((m) => m[1]));
  const intents = readDir(path.join(main, "docs", "intent"), /^INT-\d+.*\.md$/).map(([f, text]) => parseIntent(text, f));
  const plans = readDir(path.join(main, "docs", "plans"), /\.md$/).map(([f, text]) => parsePlan(text, f)).filter((p) => p.units.length);
  const model = buildModel({ intents, plans, branches, doneUnits, prs: prs ? readPullRequests(main) : [] });
  const integration = integrationLine(main);
  if (integration) model.integration = integration;
  return { model, main };
}

export function summary(model) {
  const units = model.intents.flatMap((i) => i.features.flatMap((f) => f.units));
  const now = model.nowBuilding.map((u) => `${u.id} (${u.stage})`).join(", ") || "nothing";
  return `Build status: ${units.filter((u) => u.status === "done").length}/${units.length} units done; building now: ${now}; waiting for you: ${model.waitingForYou.length}.`;
}

function main(argv) {
  const opt = (name) => argv.includes(`--${name}`);
  const at = argv.indexOf("--root");
  const root = at >= 0 ? path.resolve(argv[at + 1]) : process.cwd();
  const { model, main: mainTree } = collect(root, { prs: !opt("no-prs") });
  const page = renderStatus(model, { escape: opt("escape") });
  if (opt("stdout")) { process.stdout.write(page); return; }
  mkdirSync(path.join(mainTree, "docs"), { recursive: true });
  writeFileSync(path.join(mainTree, "docs", "STATUS.md"), page);
  if (!opt("quiet")) console.log(summary(model));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2));
