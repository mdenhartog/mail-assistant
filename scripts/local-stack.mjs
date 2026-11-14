#!/usr/bin/env node
// The local week-test stack (U-web-settings-73, ADR-0037, D-22): the whole feature in Docker on this computer, with
// the limits of the spec and TLS everywhere, reachable from this computer only.
//
//   node scripts/local-stack.mjs init [--renew-certs] [--username NAME] [--email ADDRESS]
//   node scripts/local-stack.mjs up [--recreate]
//   node scripts/local-stack.mjs down
//   node scripts/local-stack.mjs status
//   node scripts/local-stack.mjs logs [service] [--follow]
//   node scripts/local-stack.mjs backup
//   node scripts/local-stack.mjs trust-ca
//
// It only runs `docker compose` with the project name that compose.yaml defines and the profile `local` (and
// `docker volume inspect` to see whether the database volume exists). The compose files get, in this order, Marco's
// .env, deploy/local/stack.env (settings, checked in) and deploy/local/secrets.env (made by `init`, git-ignored).
// A secret is never printed and never overwritten. `down` never removes a volume: there is no such option.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  chmodSync,
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

/** The keys `init` fills with fresh random values (three distinct 32-byte keys and two passwords). */
export const SECRET_KEYS = [
  "APP_CODE_HASH_KEY",
  "APP_CSRF_KEY",
  "APP_USERNAME_HASH_KEY",
  "WEB_ROLE_PASSWORD",
  "MAIL_SMTP_PASSWORD",
];
const KEY_BYTES = { WEB_ROLE_PASSWORD: 24, MAIL_SMTP_PASSWORD: 24 };
const DEFAULT_USERNAME = "marco";
const DEFAULT_EMAIL = "marco@example.test";
const REQUIRED_IN_ENV = ["POSTGRES_PASSWORD", "MAIL_TRIAGE_RUNTIME_PASSWORD"];
const SERVICES = ["db", "mail", "mail-triage-migrate", "mail-triage", "api", "web", "edge"];
const MIN_COMPOSE = [2, 24, 0]; // repeated --env-file flags
const ENV_FILES = [".env", "deploy/local/stack.env", "deploy/local/secrets.env"];
const SECRETS = "deploy/local/secrets.env";
const CERTS = "deploy/prod-like/certs";
const USAGE =
  "usage: node scripts/local-stack.mjs init [--renew-certs] | up [--recreate] | down | status | logs [service] [--follow] | backup | trust-ca";

/** The project name compose.yaml defines (a top-level `name:`). */
export function projectName(composeText) {
  const name = /^name:\s*([\w.-]+)\s*$/m.exec(composeText)?.[1];
  if (!name) throw new Error("compose.yaml defines no project name");
  return name;
}

/** KEY=value lines to a Map; comments and blank lines are skipped. */
export function parseEnv(text) {
  const values = new Map();
  for (const line of text.split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line);
    if (match) values.set(match[1], match[2].trim());
  }
  return values;
}

/** `20261114T101530Z.sql` */
export function backupFileName(date) {
  return `${date.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z")}.sql`;
}

/** True when `docker compose version --short` is at least 2.24.0. */
export function composeVersionOk(text) {
  const match = /(\d+)\.(\d+)\.(\d+)/.exec(String(text));
  if (!match) return false;
  const found = match.slice(1, 4).map(Number);
  for (let i = 0; i < 3; i += 1) {
    if (found[i] !== MIN_COMPOSE[i]) return found[i] > MIN_COMPOSE[i];
  }
  return true;
}

/** The new secrets file text: what is there stays, what is missing is added. Never returns a value for printing. */
export function planSecrets(existingText, { random, username, email }) {
  const present = parseEnv(existingText);
  const used = new Set(present.values());
  const lines = [];
  const added = [];
  const add = (key, value) => {
    lines.push(`${key}=${value}`);
    added.push(key);
  };
  for (const key of SECRET_KEYS) {
    if (present.has(key)) continue;
    let value;
    do value = random(KEY_BYTES[key] ?? 32).toString("hex");
    while (used.has(value));
    used.add(value);
    add(key, value);
  }
  if (!present.has("WEB_USERNAME")) add("WEB_USERNAME", username);
  if (!present.has("WEB_EMAIL_ADDRESS")) add("WEB_EMAIL_ADDRESS", email);
  const head = existingText === "" || existingText.endsWith("\n") ? existingText : `${existingText}\n`;
  const text = head === "" ? `# Made by scripts/local-stack.mjs init. Git-ignored. Never commit or share.\n${lines.join("\n")}\n` : `${head}${lines.join("\n")}${lines.length ? "\n" : ""}`;
  return { text, added };
}

function composeBase(project) {
  return ["compose", "-p", project, ...ENV_FILES.flatMap((file) => ["--env-file", file]), "--profile", "local"];
}

/** The real runner: spawnSync without a shell. `outFile` sends stdout to that file; `capture` returns it. */
export function realRunner(command, args, options = {}) {
  let fd;
  try {
    const stdio = options.outFile
      ? ["ignore", (fd = openSync(options.outFile, "w", 0o600)), "inherit"]
      : options.capture
        ? ["ignore", "pipe", "inherit"]
        : "inherit";
    const result = spawnSync(command, args, { cwd: options.cwd, env: options.env ? { ...process.env, ...options.env } : process.env, stdio, encoding: "utf8", shell: false });
    return { status: result.error ? 127 : (result.status ?? 1), stdout: result.stdout ?? "" };
  } finally {
    if (fd !== undefined) closeSync(fd);
  }
}

function validName(value, pattern) {
  return typeof value === "string" && pattern.test(value);
}

export async function main(argv, deps = {}) {
  const root = deps.root ?? join(dirname(fileURLToPath(import.meta.url)), "..");
  const runner = deps.runner ?? realRunner;
  const out = deps.out ?? process.stdout;
  const err = deps.err ?? process.stderr;
  const now = deps.now ?? (() => new Date());
  const random = deps.random ?? randomBytes;
  const platform = deps.platform ?? process.platform;
  const [command, ...rest] = argv;
  const say = (text) => out.write(`${text}\n`);
  const fail = (text, status = 1) => {
    err.write(`${text}\n`);
    return status;
  };
  const path = (...parts) => join(root, ...parts);

  let project;
  try {
    project = projectName(readFileSync(path("compose.yaml"), "utf8"));
  } catch (error) {
    return fail(error.message);
  }
  const compose = (...args) => runner("docker", [...composeBase(project), ...args], { cwd: root });
  const flags = new Set(rest.filter((arg) => arg.startsWith("--")));
  const positional = rest.filter((arg) => !arg.startsWith("--"));
  const known = (allowed) => [...flags].every((flag) => allowed.includes(flag));

  const preflight = () => {
    if (!existsSync(path(".env"))) return "There is no .env in the checkout. Copy .env.example to .env and fill it in.";
    if (!existsSync(path(SECRETS))) return "There is no deploy/local/secrets.env. Run: node scripts/local-stack.mjs init";
    if (!existsSync(path(CERTS, "ca.crt"))) return "There are no certificates. Run: node scripts/local-stack.mjs init";
    const names = new Set([...parseEnv(readFileSync(path(".env"), "utf8")).keys(), ...parseEnv(readFileSync(path(SECRETS), "utf8")).keys()]);
    const missing = REQUIRED_IN_ENV.filter((key) => !names.has(key));
    if (missing.length) return `.env lacks: ${missing.join(", ")}`;
    return null;
  };

  const backup = () => {
    const dir = path("deploy", "local", "backups");
    mkdirSync(dir, { recursive: true });
    const file = join(dir, backupFileName(now()));
    // The password stays inside the container: pg_dump uses its unix socket there.
    const result = runner("docker", [...composeBase(project), "exec", "-T", "db", "pg_dump", "-U", "app", "app"], { cwd: root, outFile: file });
    if (result.status !== 0 || !existsSync(file) || statSync(file).size === 0) {
      rmSync(file, { force: true });
      return null;
    }
    try {
      chmodSync(file, 0o600);
    } catch {
      // not supported on every platform
    }
    return file;
  };

  switch (command) {
    case "init": {
      if (!known(["--renew-certs", "--username", "--email"])) return fail(USAGE, 2);
      const optionValue = (name, fallback) => {
        const index = rest.indexOf(name);
        return index >= 0 ? rest[index + 1] : fallback;
      };
      const username = optionValue("--username", DEFAULT_USERNAME);
      const email = optionValue("--email", DEFAULT_EMAIL);
      if (!validName(username, /^[A-Za-z0-9._-]{1,64}$/)) return fail("--username: letters, digits, . _ - only");
      if (!validName(email, /^[^\s@,=]{1,64}@[A-Za-z0-9.-]{1,120}$/)) return fail("--email: not a valid address");
      mkdirSync(path("deploy", "local"), { recursive: true });
      const existing = existsSync(path(SECRETS)) ? readFileSync(path(SECRETS), "utf8") : "";
      const plan = planSecrets(existing, { random, username, email });
      if (plan.added.length) {
        writeFileSync(path(SECRETS), plan.text, { mode: 0o600 });
        say(`deploy/local/secrets.env: added ${plan.added.join(", ")} (values are not printed).`);
      } else say("deploy/local/secrets.env: nothing to add.");
      if (!existsSync(path(CERTS, "ca.crt")) || flags.has("--renew-certs")) {
        // Git Bash converts an argument that starts with / into a Windows path, which breaks -subj "/CN=...".
        const env = platform === "win32" ? { MSYS2_ARG_CONV_EXCL: "/CN=" } : undefined;
        const result = runner(process.env.LOCAL_STACK_BASH || "bash", ["deploy/prod-like/certs.sh"], { cwd: root, ...(env ? { env } : {}) });
        if (result.status !== 0) return fail("The certificates could not be made (needs bash and openssl).");
        say(flags.has("--renew-certs") ? "New certificates. Trust the new CA again (trust-ca), then: node scripts/local-stack.mjs up --recreate" : "Certificates made. Next: node scripts/local-stack.mjs trust-ca");
      } else say("Certificates exist; nothing changed (init --renew-certs makes new ones).");
      if (!existsSync(path(".env"))) say("Note: there is no .env yet. Copy .env.example to .env and fill it in before `up`.");
      return 0;
    }
    case "up": {
      if (!known(["--recreate"])) return fail(USAGE, 2);
      const problem = preflight();
      if (problem) return fail(problem);
      const version = runner("docker", ["compose", "version", "--short"], { cwd: root, capture: true });
      if (version.status !== 0 || !composeVersionOk(version.stdout)) return fail("docker compose 2.24.0 or newer is needed (repeated --env-file).");
      const recreate = flags.has("--recreate") ? ["--force-recreate"] : [];
      const volume = runner("docker", ["volume", "inspect", `${project}_db-data`], { cwd: root, capture: true });
      if (compose("up", "-d", "--wait", ...recreate, "db", "mail").status !== 0) return fail("The database and the mail catcher did not start.");
      if (volume.status === 0) {
        const file = backup();
        if (!file) return fail("The backup failed, so nothing was changed. Fix it first (is the database healthy?).");
        say("Backup written to deploy/local/backups/ (not printed in full).");
      }
      // A one-shot service cannot be part of `up --wait` (an exited container counts as failed): run it by itself.
      if (compose("run", "--rm", "--build", "mail-triage-migrate").status !== 0) return fail("The migration failed; the rest was not started.");
      if (compose("up", "-d", "--build", "--wait", "--no-deps", ...recreate, "mail-triage", "api", "web", "edge").status !== 0) return fail("The stack did not become healthy: node scripts/local-stack.mjs logs");
      say("The stack is up: https://mail-assistant.localhost:8443 (sign-in codes: http://127.0.0.1:8025).");
      return 0;
    }
    case "down": {
      if (flags.size || positional.length) return fail(`down takes no options; it never removes a volume.\n${USAGE}`, 2);
      const problem = existsSync(path(SECRETS)) ? null : "There is no deploy/local/secrets.env. Run: node scripts/local-stack.mjs init";
      if (problem) return fail(problem);
      return compose("down").status === 0 ? 0 : 1;
    }
    case "status": {
      const status = compose("ps", "--all").status;
      const ca = path(CERTS, "ca.crt");
      if (existsSync(ca)) {
        const end = runner("openssl", ["x509", "-enddate", "-noout", "-in", ca], { cwd: root, capture: true });
        if (end.status === 0) say(`Certificates: ${end.stdout.trim()} (renew: init --renew-certs, then up --recreate)`);
      } else say("There are no certificates yet. Run: node scripts/local-stack.mjs init");
      return status === 0 ? 0 : 1;
    }
    case "logs": {
      if (!known(["--follow"]) || positional.length > 1) return fail(USAGE, 2);
      const service = positional[0];
      if (service !== undefined && !SERVICES.includes(service)) return fail(`unknown service; one of: ${SERVICES.join(", ")}`, 2);
      const args = ["logs", "--no-color", "--tail", "200", ...(flags.has("--follow") ? ["--follow"] : []), ...(service ? [service] : [])];
      return compose(...args).status === 0 ? 0 : 1;
    }
    case "backup": {
      const problem = preflight();
      if (problem) return fail(problem);
      const file = backup();
      if (!file) return fail("The backup failed.");
      say(`Backup written to ${file}`);
      return 0;
    }
    case "trust-ca": {
      const ca = path(CERTS, "ca.crt");
      if (!existsSync(ca)) return fail("There is no CA yet. Run: node scripts/local-stack.mjs init");
      say(`The private CA of the local stack: ${ca}`);
      say("It is valid for 30 days and signs only this stack's certificates. Nothing was changed on this computer.");
      say("");
      say("Edge and Chrome on Windows (the current user only, no administrator needed; Windows asks you to confirm):");
      say(`  certutil -user -addstore Root "${ca}"`);
      say("Firefox (its own store): Settings > Privacy & Security > Certificates > View Certificates > Authorities >");
      say("  Import, choose ca.crt, tick \"Trust this CA to identify websites\".");
      say("Remove it later: certutil -user -delstore Root \"mail-assistant prod-like CA\"; in Firefox, delete it in the same list.");
      return 0;
    }
    default:
      return fail(USAGE, 2);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).then((code) => process.exit(code));
}
