#!/usr/bin/env node
// Decides which CI jobs a pull request needs (used by the `changes` job of .github/workflows/ci.yml).
// It reads the files of the pull request and prints `name=true|false` lines for $GITHUB_OUTPUT.
// A file it does not know turns everything on, and so does any event that is not a pull request
// (nightly run, manual run, merge queue). The documentation job always runs: it takes seconds.
//
//   node scripts/ci-changes.mjs                 in Actions: reads GH_TOKEN, EVENT, REPO, PR
//   node scripts/ci-changes.mjs --files a,b     print the outcome for these files (to try it)
import { spawnSync } from "node:child_process";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const FLAGS = ["backend", "web", "components", "deploy", "images", "e2e", "gxp", "security"];

const RULES = [
  // [pattern, flags switched on]; the first matching rule wins.
  [/^\.github\/workflows\/|^scripts\/ci-changes\.mjs$/, FLAGS],
  [/^backend\//, ["backend", "images", "e2e", "security"]],
  [/^apps\/mobile\//, ["web", "security"]],
  [/^(apps|packages)\/|^(package\.json|pnpm-lock\.yaml|pnpm-workspace\.yaml|knip\.json|\.npmrc|tsconfig[^/]*\.json)$/, ["web", "images", "e2e", "security"]],
  [/^(agents|mcp-servers|channels|workers)\/|^\.sdlc\/components\.json$|^scripts\/components\.mjs$/, ["components", "security"]],
  [/^deploy\//, ["deploy", "security"]],
  [/^(compose[^/]*\.ya?ml|\.env\.example)$/, ["images", "e2e", "deploy", "security"]],
  [/^(validation|fixtures)\//, ["gxp", "e2e", "images", "security"]],
  [/^(\.semgrep\/|\.pre-commit-config\.yaml$|renovate\.json$|commitlint\.config\.mjs$|\.gitignore$|\.markdownlint)/, ["security"]],
  [/^scripts\//, ["security"]],
  [/^(docs\/|\.github\/pull_request_template\.md$|CHANGELOG\.md$|\.release-please-manifest\.json$|release-please-config\.json$|LICENSE|.*\.md$)/, []],
];

/** The CI areas a list of changed files touches. */
export function classify(files) {
  const on = new Set();
  for (const file of files) {
    const rule = RULES.find(([pattern]) => pattern.test(file));
    for (const flag of rule ? rule[1] : FLAGS) on.add(flag); // unknown file: everything
  }
  return Object.fromEntries(FLAGS.map((flag) => [flag, on.has(flag)]));
}

export const allOn = () => Object.fromEntries(FLAGS.map((flag) => [flag, true]));

function pullRequestFiles(env) {
  const result = spawnSync("gh", ["api", `repos/${env.REPO}/pulls/${env.PR}/files`, "--paginate", "--jq", ".[].filename"], { encoding: "utf8", env });
  if (result.status !== 0) return null;
  const files = result.stdout.split("\n").map((l) => l.trim()).filter(Boolean);
  return files.length > 0 ? files : null;
}

function main(argv, env = process.env) {
  const at = argv.indexOf("--files");
  let flags;
  if (at >= 0) flags = classify(argv[at + 1].split(",").filter(Boolean));
  else if (env.EVENT === "pull_request" && env.PR && env.REPO) {
    const files = pullRequestFiles(env);
    flags = files ? classify(files) : allOn(); // cannot tell: run everything
  } else flags = allOn();
  for (const [name, value] of Object.entries(flags)) console.log(`${name}=${value}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main(process.argv.slice(2));
