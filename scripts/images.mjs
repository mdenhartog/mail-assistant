#!/usr/bin/env node
// Keeps the container image names in deploy/ pointing where the release workflow pushes them:
// ghcr.io/<repository owner>/<repository>/<image>. The owner is never typed in: it follows the GitHub
// repository the project lives in (origin remote, or GITHUB_REPOSITORY in GitHub Actions); before there
// is a remote it is the logged-in GitHub account. Move the repository to an organisation and the next
// commit (pre-commit hook) updates the image names.
//
//   node scripts/images.mjs check    # fails when an image name in deploy/ points elsewhere
//   node scripts/images.mjs sync     # rewrites the image names (the pre-commit hook runs this)
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { pathToFileURL } from "node:url";

const PREFIX = /ghcr\.io\/([\w.-]+)\/([\w.-]+)\//g;

/** owner/repo of a GitHub remote URL (https or ssh), or null. */
export function githubRepoOf(url) {
  return /github\.com[:/]([\w.-]+\/[\w.-]+?)(?:\.git)?\/?$/.exec(url ?? "")?.[1] ?? null;
}

function capture(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, encoding: "utf8", shell: false });
  return result.status === 0 ? result.stdout.trim() : "";
}

/** The ghcr.io prefix the images belong under (owner/repo, lowercase as the registry requires), or null when unknown. */
export function expectedPrefix(root, env = process.env) {
  const repo = env.GITHUB_REPOSITORY || githubRepoOf(capture("git", ["remote", "get-url", "origin"], root));
  if (repo) return repo.toLowerCase();
  const login = capture("gh", ["api", "user", "--jq", ".login"], root);
  if (!login) return null;
  const current = currentPrefix(root);
  return current ? `${login.toLowerCase()}/${current.split("/")[1]}` : null;
}

/** Every YAML file under deploy/. */
function deployFiles(root) {
  const dir = join(root, "deploy");
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile() && /\.ya?ml$/.test(e.name))
    .map((e) => join(e.parentPath ?? e.path, e.name));
}

/** The project's own image prefix (owner/repo) as the app chart has it now, or null. */
export function currentPrefix(root) {
  const values = join(root, "deploy", "charts", "app", "values.yaml");
  if (!existsSync(values)) return null;
  const first = [...readFileSync(values, "utf8").matchAll(PREFIX)][0];
  return first ? `${first[1]}/${first[2]}` : null;
}

/** Files whose project image names differ from the expected prefix: [{ file, from, to }]. */
export function mismatches(root, env = process.env) {
  const current = currentPrefix(root);
  const expected = expectedPrefix(root, env);
  if (!current || !expected || current === expected) return [];
  return deployFiles(root)
    .filter((file) => readFileSync(file, "utf8").includes(`ghcr.io/${current}/`))
    .map((file) => ({ file: relative(root, file).split("\\").join("/"), from: current, to: expected }));
}

export function sync(root, env = process.env) {
  const found = mismatches(root, env);
  for (const { file, from, to } of found) {
    const path = join(root, file);
    writeFileSync(path, readFileSync(path, "utf8").replaceAll(`ghcr.io/${from}/`, `ghcr.io/${to}/`));
  }
  return found;
}

function main() {
  const root = process.cwd();
  const command = process.argv[2] ?? "check";
  if (command === "sync") {
    for (const { file, from, to } of sync(root)) console.log(`images: ${file}: ghcr.io/${from}/ -> ghcr.io/${to}/`);
    return 0;
  }
  if (command !== "check") {
    console.error("Usage: node scripts/images.mjs check | sync");
    return 2;
  }
  const found = mismatches(root);
  for (const { file, from, to } of found) console.error(`images: ${file} pushes to ghcr.io/${from}/ but the repository is ${to}; run: node scripts/images.mjs sync`);
  // OWNER with nothing known yet (no remote, not logged in) is not an error: the first sync fills it in.
  if (found.length === 0 && currentPrefix(root)?.startsWith("OWNER/")) {
    console.warn("images: the image owner is still OWNER; it is filled in once there is a GitHub remote or after 'gh auth login' (node scripts/images.mjs sync).");
  }
  return found.length > 0 ? 1 : 0;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) process.exit(main());
