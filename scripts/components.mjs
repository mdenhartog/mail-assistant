#!/usr/bin/env node
// Runs the same checks over every agent, MCP server and channel gateway in .sdlc/components.json
// (and the CDK app in deploy/aws, when present). Windows, Linux and macOS; CI calls this too.
//
//   node scripts/components.mjs list
//   node scripts/components.mjs check   [name]   # ruff, format, pyright, bandit, pytest (coverage gate)
//   node scripts/components.mjs audit   [name]   # pip-audit: known vulnerabilities in the locked dependencies
//   node scripts/components.mjs upgrade [name]   # uv lock --upgrade, uv sync, then check: move to the latest versions
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const [command = "list", only] = process.argv.slice(2);

const registry = existsSync(join(root, ".sdlc", "components.json")) ? JSON.parse(readFileSync(join(root, ".sdlc", "components.json"), "utf8")).components : [];
const targets = registry.map((c) => ({ name: c.name, path: c.path, kind: c.kind }));
if (existsSync(join(root, "deploy", "aws", "pyproject.toml"))) targets.push({ name: "aws", path: "deploy/aws", kind: "aws" });
const selected = targets.filter((t) => !only || t.name === only).filter((t) => existsSync(join(root, t.path, "pyproject.toml")));

const uv = (args, cwd) => spawnSync("uv", args, { cwd, stdio: "inherit" }).status === 0;

/** The checks differ per kind: the CDK app has no bandit/pyright (jsii typings), the rest run the full set. */
function steps(kind) {
  const common = [["ruff", "check", "."], ["ruff", "format", "--check", "."]];
  if (kind === "aws") return [...common, ["pytest"]];
  return [...common, ["pyright"], ["bandit", "-q", "-c", "pyproject.toml", "-r", "app"], ["pytest"]];
}

function check(target) {
  const cwd = join(root, target.path);
  console.log(`\n== ${target.name} (${target.kind}) ==`);
  if (!uv(["sync", "--frozen"], cwd)) return false;
  return steps(target.kind).every((step) => uv(["run", ...step], cwd));
}

if (command === "list") {
  for (const t of targets) console.log(`${t.name.padEnd(24)} ${t.kind.padEnd(11)} ${t.path}`);
  process.exit(0);
}
if (!["check", "audit", "upgrade"].includes(command)) {
  console.error("Usage: node scripts/components.mjs list|check|audit|upgrade [name]");
  process.exit(2);
}
if (selected.length === 0) {
  console.log(only ? `No component named '${only}'.` : "No components yet: add one with /sdlc:component.");
  process.exit(only ? 1 : 0);
}

const failed = [];
for (const target of selected) {
  const cwd = join(root, target.path);
  let ok = true;
  if (command === "upgrade") {
    console.log(`\n== ${target.name}: moving to the latest compatible versions ==`);
    ok = uv(["lock", "--upgrade"], cwd) && uv(["sync"], cwd) && check(target);
  } else if (command === "audit") {
    console.log(`\n== ${target.name}: pip-audit ==`);
    ok = uv(["sync", "--frozen"], cwd) && uv(["run", "pip-audit"], cwd);
  } else {
    ok = check(target);
  }
  if (!ok) failed.push(target.name);
}
console.log(failed.length === 0 ? `\nAll ${selected.length} component(s) passed.` : `\nFAILED: ${failed.join(", ")}`);
process.exit(failed.length === 0 ? 0 : 1);
