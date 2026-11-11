// Architecture tooling (skill `architecture`): the architecture model in docs/architecture/model.json is the
// source of truth for where things live and which parts may depend on which. This script keeps the model,
// the architecture overview and the code consistent.
//   node scripts/architecture.mjs check              model valid, every code folder in a component, imports only
//                                                     along allowed dependencies, overview table current
//   node scripts/architecture.mjs render             rewrite the component table in docs/architecture/README.md
//   node scripts/architecture.mjs init               create a draft model from the folders that exist (older projects)
//   node scripts/architecture.mjs add --id <id> --kind <kind> --path <dir> [--name <name>] [--responsibility <text>]
//                                     [--depends-on <id,id>]   register a new component (used by add-component)
// Options: --root <dir> (default: the project root). `enforce: "warn"` in the model reports without failing.
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

export const KINDS = ["frontend", "mobile", "backend", "shared", "agent", "mcp-server", "channel", "worker", "datastore", "external", "platform"];
/** Kinds that are not code in this repository and therefore have no paths. */
const NO_PATHS = new Set(["datastore", "external"]);
/** Folders that hold code; every one that exists must belong to a component. */
const CODE_ROOTS = ["apps/*", "packages/*", "backend", "agents/*", "mcp-servers/*", "channels/*", "workers/*", "deploy"];
const SKIP = new Set(["node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".git", "coverage", ".turbo", ".expo", "playwright-report", "test-results", "cdk.out", ".pytest_cache", ".ruff_cache", "android", "ios"]);
const CODE_EXT = /\.(?:[cm]?[jt]sx?|py)$/;
const START = "<!-- architecture:components:start -->";
const END = "<!-- architecture:components:end -->";
export const PENDING = "<!-- architecture:pending -->";

const posix = (p) => p.split(path.sep).join("/");
const modelFile = (root) => path.join(root, "docs", "architecture", "model.json");
const readmeFile = (root) => path.join(root, "docs", "architecture", "README.md");
const cell = (text) => String(text ?? "").replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ").trim();

export function readModel(root) {
  const file = modelFile(root);
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, "utf8"));
}

export function writeModel(root, model) {
  mkdirSync(path.dirname(modelFile(root)), { recursive: true });
  writeFileSync(modelFile(root), `${JSON.stringify(model, null, 2)}\n`, "utf8");
}

/** The code folders of the project that exist, e.g. ["apps/web", "backend", "packages/tokens"]. */
export function codeRoots(root) {
  const out = [];
  for (const pattern of CODE_ROOTS) {
    if (pattern.endsWith("/*")) {
      const dir = path.join(root, pattern.slice(0, -2));
      if (!existsSync(dir)) continue;
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.isDirectory() && !SKIP.has(entry.name) && !entry.name.startsWith(".")) out.push(`${pattern.slice(0, -2)}/${entry.name}`);
      }
    } else if (existsSync(path.join(root, pattern))) out.push(pattern);
  }
  return out.sort();
}

const inside = (child, parent) => child === parent || child.startsWith(`${parent}/`);

/** The component that owns a repository-relative path: the one with the longest matching path. */
export function ownerOf(model, relPath) {
  let best = null;
  let length = -1;
  for (const component of model.components ?? []) {
    for (const p of component.paths ?? []) {
      const clean = p.replace(/\/+$/, "");
      if (inside(relPath, clean) && clean.length > length) { best = component; length = clean.length; }
    }
  }
  return best;
}

/** Structural problems in the model itself. */
export function validateModel(root, model) {
  const problems = [];
  if (!["draft", "approved"].includes(model.status)) problems.push(`model.json: status must be "draft" or "approved"`);
  if (!["block", "warn"].includes(model.enforce)) problems.push(`model.json: enforce must be "block" or "warn"`);
  const components = Array.isArray(model.components) ? model.components : [];
  if (components.length === 0) problems.push("model.json: no components");
  const ids = new Set();
  for (const c of components) {
    const label = `model.json: component ${c.id ?? "(no id)"}`;
    if (!/^[a-z][a-z0-9-]*$/.test(c.id ?? "")) problems.push(`${label}: id must be lowercase kebab-case`);
    if (ids.has(c.id)) problems.push(`${label}: duplicate id`);
    ids.add(c.id);
    if (!c.name) problems.push(`${label}: name is missing`);
    if (!KINDS.includes(c.kind)) problems.push(`${label}: kind must be one of ${KINDS.join(", ")}`);
    if (!c.responsibility) problems.push(`${label}: responsibility is missing (one sentence: what it is for)`);
    const paths = c.paths ?? [];
    if (NO_PATHS.has(c.kind) && paths.length > 0) problems.push(`${label}: a ${c.kind} has no paths in this repository`);
    if (!NO_PATHS.has(c.kind) && paths.length === 0) problems.push(`${label}: paths are missing`);
    for (const p of paths) if (!existsSync(path.join(root, p))) problems.push(`${label}: path ${p} does not exist`);
  }
  for (const c of components) {
    for (const dep of c.dependsOn ?? []) {
      if (dep === c.id) problems.push(`model.json: component ${c.id} depends on itself`);
      else if (!ids.has(dep)) problems.push(`model.json: component ${c.id} depends on unknown component ${dep}`);
    }
  }
  return problems;
}

/** Code folders that no component owns. */
export function uncovered(root, model) {
  return codeRoots(root)
    .filter((dir) => !(model.components ?? []).some((c) => (c.paths ?? []).some((p) => inside(dir, p.replace(/\/+$/, "")))))
    .map((dir) => `${dir} is not part of any component in docs/architecture/model.json (add it, or move the code)`);
}

function codeFiles(root, rel, out = []) {
  const full = path.join(root, rel);
  if (!existsSync(full)) return out;
  if (statSync(full).isFile()) {
    if (CODE_EXT.test(rel)) out.push(rel);
    return out;
  }
  for (const entry of readdirSync(full, { withFileTypes: true })) {
    if (SKIP.has(entry.name) || (entry.isDirectory() && entry.name.startsWith("."))) continue;
    codeFiles(root, rel ? `${rel}/${entry.name}` : entry.name, out);
  }
  return out;
}

const JS_IMPORT = /(?:^|[^\w$.])(?:import|export)\s+(?:type\s+)?(?:[^'"`;]*?\s+from\s+)?["']([^"'\n]+)["']|(?:import|require)\s*\(\s*["']([^"'\n]+)["']\s*\)/g;
const PY_FROM = /^[ \t]*from[ \t]+(\.*[\w.]*)[ \t]+import\b/gm;
const PY_IMPORT = /^[ \t]*import[ \t]+([\w.]+(?:[ \t]*,[ \t]*[\w.]+)*)/gm;

/** The import specifiers in one file: [{ spec, python }]. */
export function importsOf(text, python) {
  const out = [];
  if (python) {
    for (const [, spec] of text.matchAll(PY_FROM)) out.push(spec);
    for (const [, list] of text.matchAll(PY_IMPORT)) for (const spec of list.split(",")) out.push(spec.trim());
  } else {
    for (const m of text.matchAll(JS_IMPORT)) out.push(m[1] ?? m[2]);
  }
  return out.filter(Boolean);
}

function packageIndex(root, model) {
  const index = new Map();
  for (const c of model.components ?? []) {
    for (const p of c.paths ?? []) {
      const file = path.join(root, p, "package.json");
      if (!existsSync(file)) continue;
      try {
        const name = JSON.parse(readFileSync(file, "utf8")).name;
        if (name) index.set(name, p);
      } catch { /* not a package */ }
    }
  }
  return index;
}

function pythonRoots(root) {
  const roots = [];
  for (const dir of codeRoots(root)) {
    if (existsSync(path.join(root, dir, "pyproject.toml"))) {
      roots.push(dir);
      if (existsSync(path.join(root, dir, "src"))) roots.push(`${dir}/src`);
    }
  }
  return roots;
}

/** The repository-relative path an import points at, or null for an external library. */
export function resolveImport(root, file, spec, { packages, pyRoots }) {
  const python = file.endsWith(".py");
  if (python) {
    const dots = /^\.*/.exec(spec)[0].length;
    const parts = spec.slice(dots).split(".").filter(Boolean);
    if (dots > 0) {
      let base = path.posix.dirname(file);
      for (let i = 1; i < dots; i++) base = path.posix.dirname(base);
      return parts.length ? `${base}/${parts.join("/")}` : base;
    }
    const ordered = [...pyRoots].sort((a, b) => Number(inside(file, b)) - Number(inside(file, a)) || b.length - a.length);
    for (const pyRoot of ordered) {
      if (!existsSync(path.join(root, pyRoot, parts[0])) && !existsSync(path.join(root, pyRoot, `${parts[0]}.py`))) continue;
      for (let k = parts.length; k > 0; k--) {
        const candidate = `${pyRoot}/${parts.slice(0, k).join("/")}`;
        if (existsSync(path.join(root, candidate)) || existsSync(path.join(root, `${candidate}.py`))) return candidate;
      }
    }
    return null;
  }
  if (spec.startsWith(".")) return posix(path.posix.normalize(`${path.posix.dirname(file)}/${spec}`));
  const segments = spec.split("/");
  const name = spec.startsWith("@") ? segments.slice(0, 2).join("/") : segments[0];
  return packages.get(name) ?? null;
}

/** Imports that cross a component boundary without a declared dependency. */
export function dependencyViolations(root, model) {
  const context = { packages: packageIndex(root, model), pyRoots: pythonRoots(root) };
  const problems = [];
  const files = new Set((model.components ?? []).flatMap((c) => (c.paths ?? []).flatMap((p) => codeFiles(root, p.replace(/\/+$/, "")))));
  for (const file of [...files].sort()) {
    const source = ownerOf(model, file);
    if (!source) continue;
    const allowed = new Set(source.dependsOn ?? []);
    for (const spec of new Set(importsOf(readFileSync(path.join(root, file), "utf8"), file.endsWith(".py")))) {
      const targetPath = resolveImport(root, file, spec, context);
      if (!targetPath) continue;
      const target = ownerOf(model, targetPath);
      if (!target || target.id === source.id || allowed.has(target.id)) continue;
      const nested = (target.paths ?? []).some((tp) => (source.paths ?? []).some((sp) => inside(tp, sp)));
      if (nested) continue;
      problems.push(`${file}: ${source.id} imports ${spec} from ${target.id}, but ${source.id} may not depend on ${target.id} (dependsOn in docs/architecture/model.json, or move the code)`);
    }
  }
  return problems;
}

/** The component table of the architecture overview, generated from the model. */
export function renderTable(model) {
  const rows = (model.components ?? []).map((c) => `| ${cell(c.name)} (\`${c.id}\`) | ${cell(c.kind)} | ${cell(c.responsibility)} | ${cell((c.owns ?? []).join("; ")) || "—"} | ${(c.dependsOn ?? []).map((d) => `\`${d}\``).join(", ") || "—"} | ${(c.paths ?? []).map((p) => `\`${p}\``).join(", ") || "—"} |`);
  return [
    START,
    "",
    "Generated from `docs/architecture/model.json` by `node scripts/architecture.mjs render`; edit the model, not this table.",
    "",
    "| Component | Kind | Responsibility | Owns | May depend on | Code |",
    "|---|---|---|---|---|---|",
    ...rows,
    "",
    END,
  ].join("\n");
}

function tableProblems(root, model) {
  const file = readmeFile(root);
  if (!existsSync(file)) return ["docs/architecture/README.md is missing"];
  const text = readFileSync(file, "utf8").replace(/\r\n/g, "\n");
  const problems = [];
  const start = text.indexOf(START);
  const end = text.indexOf(END);
  if (start < 0 || end < start) problems.push(`docs/architecture/README.md has no component table markers (${START} … ${END}): run node scripts/architecture.mjs render`);
  else if (text.slice(start, end + END.length) !== renderTable(model)) problems.push("docs/architecture/README.md: the component table does not match model.json: run node scripts/architecture.mjs render");
  if (text.includes("{{")) problems.push("docs/architecture/README.md still contains template placeholders");
  if (model.status === "approved" && text.includes(PENDING)) problems.push(`docs/architecture/README.md: the baseline is approved but sections are still marked ${PENDING}`);
  return problems;
}

/** Everything that is inconsistent between the model, the overview and the code; an empty list is a pass. */
export function checkArchitecture(root) {
  const model = readModel(root);
  if (!model) return { problems: ["docs/architecture/model.json is missing: run node scripts/architecture.mjs init, then complete it (skill architecture)"], enforce: "block", status: "missing" };
  const structural = validateModel(root, model);
  const problems = structural.length > 0 ? structural : [...uncovered(root, model), ...dependencyViolations(root, model), ...tableProblems(root, model)];
  return { problems, enforce: model.enforce, status: model.status };
}

export function renderReadme(root) {
  const model = readModel(root);
  const file = readmeFile(root);
  const text = readFileSync(file, "utf8").replace(/\r\n/g, "\n");
  const start = text.indexOf(START);
  const end = text.indexOf(END);
  const table = renderTable(model);
  const next = start >= 0 && end > start ? `${text.slice(0, start)}${table}${text.slice(end + END.length)}` : `${text.trimEnd()}\n\n## Components\n\n${table}\n`;
  writeFileSync(file, next, "utf8");
}

const GUESS = [
  [/^apps\/mobile/, "mobile", "Mobile app"],
  [/^apps\//, "frontend", null],
  [/^packages\//, "shared", null],
  [/^backend$/, "backend", "API"],
  [/^agents\//, "agent", null],
  [/^mcp-servers\//, "mcp-server", null],
  [/^channels\//, "channel", null],
  [/^workers\//, "worker", null],
  [/^deploy$/, "platform", "Deployment"],
];

/** A draft model from the folders that exist; responsibilities are left for the architect to fill in. */
export function initModel(root) {
  const components = codeRoots(root).map((dir) => {
    const [, kind, title] = GUESS.find(([re]) => re.test(dir)) ?? [null, "shared", null];
    const base = dir.split("/").pop();
    return { id: { backend: "api", deploy: "platform" }[base] ?? base, name: title ?? base, kind, paths: [dir], responsibility: "", owns: [], dependsOn: [] };
  });
  return { status: "draft", enforce: "warn", components };
}

export function addComponent(root, { id, kind, paths, name, responsibility, dependsOn }) {
  const model = readModel(root);
  if (!model) throw new Error("docs/architecture/model.json is missing");
  if (model.components.some((c) => c.id === id)) return false;
  model.components.push({ id, name: name ?? id, kind, paths, responsibility: responsibility ?? "", owns: [], dependsOn: dependsOn ?? [] });
  writeModel(root, model);
  if (existsSync(readmeFile(root))) renderReadme(root);
  return true;
}

function main(argv) {
  const { values: opts, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: {
      root: { type: "string" }, id: { type: "string" }, kind: { type: "string" }, path: { type: "string" },
      name: { type: "string" }, responsibility: { type: "string" }, "depends-on": { type: "string" },
    },
  });
  const root = path.resolve(opts.root ?? path.join(path.dirname(fileURLToPath(import.meta.url)), ".."));
  const [command] = positionals;
  if (command === "check") {
    const { problems, enforce, status } = checkArchitecture(root);
    if (problems.length === 0) {
      console.log(`Architecture is consistent (baseline ${status})`);
      return;
    }
    const text = problems.map((p) => `  - ${p}`).join("\n");
    if (enforce === "warn") {
      console.warn(`Architecture check (warn only until the baseline is approved and enforce is "block"):\n${text}`);
      return;
    }
    console.error(`Architecture check failed:\n${text}`);
    process.exit(1);
  } else if (command === "render") {
    renderReadme(root);
    console.log("docs/architecture/README.md component table is current");
  } else if (command === "init") {
    if (readModel(root)) { console.log("docs/architecture/model.json exists; nothing to do"); return; }
    writeModel(root, initModel(root));
    if (existsSync(readmeFile(root))) renderReadme(root);
    console.log("Draft docs/architecture/model.json written (enforce: warn). Complete it with the skill architecture.");
  } else if (command === "add") {
    if (!opts.id || !opts.kind || !opts.path) throw new Error("add needs --id, --kind and --path");
    if (!KINDS.includes(opts.kind)) throw new Error(`--kind must be one of ${KINDS.join(", ")}`);
    const added = addComponent(root, { id: opts.id, kind: opts.kind, paths: [opts.path], name: opts.name, responsibility: opts.responsibility, dependsOn: opts["depends-on"]?.split(",").map((s) => s.trim()).filter(Boolean) });
    console.log(added ? `Component ${opts.id} added to docs/architecture/model.json` : `Component ${opts.id} already exists`);
  } else {
    console.error("Usage: node scripts/architecture.mjs check | render | init | add --id <id> --kind <kind> --path <dir>");
    process.exit(2);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    main(process.argv.slice(2));
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }
}
