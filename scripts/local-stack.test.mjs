// Tests of scripts/local-stack.mjs (U-web-settings-73). They are static: a temp directory stands in for the checkout
// and a fake runner stands in for docker and bash, so nothing here starts a container or reads a real .env.
// Run with `node --test scripts/local-stack.test.mjs`; agents/mail-triage/tests/infra/test_local_stack.py runs it too.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  SECRET_KEYS,
  backupFileName,
  composeVersionOk,
  main,
  parseEnv,
  projectName,
} from "./local-stack.mjs";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const SCRIPT = readFileSync(join(REPO, "scripts", "local-stack.mjs"), "utf8");
const FIXED = new Date("2026-11-14T10:15:30Z");

/** A checkout in a temp directory: compose.yaml with the project name, a .env that only the fake runner "reads". */
function checkout(options = {}) {
  const root = mkdtempSync(join(tmpdir(), "local-stack-"));
  writeFileSync(join(root, "compose.yaml"), "name: mail-assistant\nservices: {}\n");
  writeFileSync(join(root, ".env"), "POSTGRES_PASSWORD=pg-from-env\nMAIL_TRIAGE_RUNTIME_PASSWORD=rt-from-env\n");
  mkdirSync(join(root, "deploy", "prod-like"), { recursive: true });
  if (options.certs) {
    mkdirSync(join(root, "deploy", "prod-like", "certs"), { recursive: true });
    writeFileSync(join(root, "deploy", "prod-like", "certs", "ca.crt"), "ca");
  }
  return root;
}

/** The fake runner: records every call; `handlers` decide the answer by the command line. */
function fakeRunner(root, handlers = {}) {
  const calls = [];
  const runner = (command, args, options = {}) => {
    calls.push({ command, args, options });
    const line = [command, ...args].join(" ");
    for (const [needle, answer] of Object.entries(handlers)) {
      if (line.includes(needle)) return typeof answer === "function" ? answer({ command, args, options, root }) : answer;
    }
    if (line.includes("compose version")) return { status: 0, stdout: "2.40.3\n" };
    if (command === "bash") {
      mkdirSync(join(root, "deploy", "prod-like", "certs"), { recursive: true });
      writeFileSync(join(root, "deploy", "prod-like", "certs", "ca.crt"), "ca");
      return { status: 0, stdout: "" };
    }
    if (line.includes("pg_dump") && options.outFile) writeFileSync(options.outFile, "-- dump\n");
    return { status: 0, stdout: "" };
  };
  return { runner, calls };
}

async function run(root, argv, handlers, extra = {}) {
  const out = [];
  const err = [];
  const { runner, calls } = fakeRunner(root, handlers);
  const status = await main(argv, {
    root,
    runner,
    out: { write: (text) => out.push(text) },
    err: { write: (text) => err.push(text) },
    now: () => FIXED,
    ...extra,
  });
  return { status, calls, out: out.join(""), err: err.join("") };
}

const dockerCalls = (calls) => calls.filter((call) => call.command === "docker");
const composeCalls = (calls) => dockerCalls(calls).filter((call) => call.args[0] === "compose");
const sub = (call) => call.args.slice(call.args.indexOf("local") + 1).join(" ");
const secretsPath = (root) => join(root, "deploy", "local", "secrets.env");

async function ready(options = {}) {
  const root = checkout({ certs: true });
  assert.equal((await run(root, ["init"])).status, 0);
  return { root, ...options };
}

test("criterion 3: init twice makes the secrets file with five distinct random values and changes nothing the second time", async () => {
  const root = checkout();
  const first = await run(root, ["init"]);
  assert.equal(first.status, 0, first.err);
  const text = readFileSync(secretsPath(root), "utf8");
  const values = parseEnv(text);
  const random = ["APP_CODE_HASH_KEY", "APP_CSRF_KEY", "APP_USERNAME_HASH_KEY", "WEB_ROLE_PASSWORD", "MAIL_SMTP_PASSWORD"];
  assert.deepEqual(SECRET_KEYS.slice().sort(), random.slice().sort());
  assert.equal(new Set(random.map((key) => values.get(key))).size, 5);
  for (const key of random) assert.match(values.get(key), /^[0-9a-f]{48,}$/, key);
  for (const key of ["APP_CODE_HASH_KEY", "APP_CSRF_KEY", "APP_USERNAME_HASH_KEY"]) {
    assert.ok(values.get(key).length >= 64, `${key} is at least 32 bytes`);
  }
  assert.equal(values.get("WEB_USERNAME"), "marco");
  assert.equal(values.get("WEB_EMAIL_ADDRESS"), "marco@example.test");

  const second = await run(root, ["init"]);
  assert.equal(second.status, 0, second.err);
  assert.equal(readFileSync(secretsPath(root), "utf8"), text);

  for (const answer of [first, second]) {
    for (const key of random) assert.ok(!(answer.out + answer.err).includes(values.get(key)), `${key} was printed`);
  }
  rmSync(root, { recursive: true, force: true });
});

test("criterion 3: init keeps every value that is already there and adds only what is missing", async () => {
  const root = checkout({ certs: true });
  mkdirSync(join(root, "deploy", "local"), { recursive: true });
  writeFileSync(secretsPath(root), "APP_CSRF_KEY=keep-this-one\nWEB_USERNAME=anna\n");
  const answer = await run(root, ["init"]);
  assert.equal(answer.status, 0, answer.err);
  const values = parseEnv(readFileSync(secretsPath(root), "utf8"));
  assert.equal(values.get("APP_CSRF_KEY"), "keep-this-one");
  assert.equal(values.get("WEB_USERNAME"), "anna");
  assert.equal(values.get("WEB_EMAIL_ADDRESS"), "marco@example.test");
  assert.ok(values.get("WEB_ROLE_PASSWORD"));
  assert.ok(!(answer.out + answer.err).includes("keep-this-one"));
  rmSync(root, { recursive: true, force: true });
});

test("criterion 3: the secrets file and the backups are git-ignored", () => {
  const ignore = readFileSync(join(REPO, ".gitignore"), "utf8").split(/\r?\n/);
  assert.ok(ignore.includes("deploy/local/secrets.env"));
  assert.ok(ignore.includes("deploy/local/backups/"));
});

test("criterion 3: init makes the certificates only when there are none, with the prod-like script", async () => {
  const root = checkout();
  const first = await run(root, ["init"]);
  const bash = first.calls.filter((call) => call.command === "bash");
  assert.equal(bash.length, 1);
  assert.deepEqual(bash[0].args, ["deploy/prod-like/certs.sh"]);
  assert.equal(bash[0].options.cwd, root);
  const second = await run(root, ["init"]);
  assert.equal(second.calls.filter((call) => call.command === "bash").length, 0);
  const renew = await run(root, ["init", "--renew-certs"]);
  assert.equal(renew.calls.filter((call) => call.command === "bash").length, 1);
  rmSync(root, { recursive: true, force: true });
});

test("criterion 3: on Windows the certificate script runs with the MSYS argument conversion excluded for /CN=", async () => {
  const win = checkout();
  const onWindows = await run(win, ["init"], {}, { platform: "win32" });
  const bash = onWindows.calls.find((call) => call.command === "bash");
  assert.equal(bash.options.env.MSYS2_ARG_CONV_EXCL, "/CN=");
  const other = checkout();
  const onLinux = await run(other, ["init"], {}, { platform: "linux" });
  const linuxBash = onLinux.calls.find((call) => call.command === "bash");
  assert.ok(!linuxBash.options.env || !("MSYS2_ARG_CONV_EXCL" in linuxBash.options.env));
  rmSync(win, { recursive: true, force: true });
  rmSync(other, { recursive: true, force: true });
});

test("criterion 5: up with an existing database volume starts the database, backs up first, then migrates and starts the rest", async () => {
  const { root } = await ready();
  const answer = await run(root, ["up"]);
  assert.equal(answer.status, 0, answer.err);
  const steps = dockerCalls(answer.calls).map((call) => (call.args[0] === "volume" ? call.args.join(" ") : sub(call)));
  assert.deepEqual(steps, [
    "volume inspect mail-assistant_db-data",
    "up -d --wait db mail",
    "exec -T db pg_dump -U app app",
    "run --rm --build mail-triage-migrate",
    "up -d --build --wait --no-deps mail-triage api web edge",
  ]);
  const dump = answer.calls.find((call) => call.args.includes("pg_dump"));
  assert.equal(dump.options.outFile, join(root, "deploy", "local", "backups", "20261114T101530Z.sql"));
  assert.ok(existsSync(dump.options.outFile));
  rmSync(root, { recursive: true, force: true });
});

test("criterion 5: a failing backup stops up before the migration and the rest, and leaves no partial dump", async () => {
  const { root } = await ready();
  const answer = await run(root, ["up"], {
    pg_dump: ({ options }) => {
      writeFileSync(options.outFile, "-- half");
      return { status: 1, stdout: "" };
    },
  });
  assert.notEqual(answer.status, 0);
  const lines = composeCalls(answer.calls).map(sub);
  assert.ok(!lines.some((line) => line.startsWith("run ")), "the migration must not run");
  assert.ok(!lines.some((line) => line.includes("mail-triage api web edge")), "the rest must not start");
  assert.ok(!existsSync(join(root, "deploy", "local", "backups", "20261114T101530Z.sql")));
  assert.match(answer.err, /backup/i);
  rmSync(root, { recursive: true, force: true });
});

test("criterion 5: up without a database volume makes no backup", async () => {
  const { root } = await ready();
  const answer = await run(root, ["up"], { "volume inspect": { status: 1, stdout: "" } });
  assert.equal(answer.status, 0, answer.err);
  assert.ok(!answer.calls.some((call) => call.args.includes("pg_dump")));
  assert.ok(composeCalls(answer.calls).map(sub).includes("run --rm --build mail-triage-migrate"));
  rmSync(root, { recursive: true, force: true });
});

test("criterion 5: a failing migration stops up before the rest", async () => {
  const { root } = await ready();
  const answer = await run(root, ["up"], { "mail-triage-migrate": { status: 2, stdout: "" } });
  assert.notEqual(answer.status, 0);
  assert.ok(!composeCalls(answer.calls).map(sub).some((line) => line.includes("mail-triage api web edge")));
  rmSync(root, { recursive: true, force: true });
});

test("up --recreate recreates the containers so that renewed certificates are read", async () => {
  const { root } = await ready();
  const answer = await run(root, ["up", "--recreate"]);
  const ups = composeCalls(answer.calls).map(sub).filter((line) => line.startsWith("up "));
  assert.deepEqual(ups, [
    "up -d --wait --force-recreate db mail",
    "up -d --build --wait --no-deps --force-recreate mail-triage api web edge",
  ]);
  rmSync(root, { recursive: true, force: true });
});

test("up refuses to start without the secrets file, the certificates or the .env, and names what to do", async () => {
  const bare = checkout();
  const noSecrets = await run(bare, ["up"]);
  assert.notEqual(noSecrets.status, 0);
  assert.match(noSecrets.err, /init/);
  assert.equal(dockerCalls(noSecrets.calls).length, 0);
  rmSync(bare, { recursive: true, force: true });

  const { root } = await ready();
  rmSync(join(root, ".env"));
  const noEnv = await run(root, ["up"]);
  assert.notEqual(noEnv.status, 0);
  assert.match(noEnv.err, /\.env/);
  rmSync(root, { recursive: true, force: true });
});

test("up names the keys that the .env lacks (never a value) and stops", async () => {
  const { root } = await ready();
  writeFileSync(join(root, ".env"), "POSTGRES_PASSWORD=secret-pg-value\n");
  const answer = await run(root, ["up"]);
  assert.notEqual(answer.status, 0);
  assert.match(answer.err, /MAIL_TRIAGE_RUNTIME_PASSWORD/);
  assert.ok(!(answer.out + answer.err).includes("secret-pg-value"));
  assert.equal(dockerCalls(answer.calls).length, 0);
  rmSync(root, { recursive: true, force: true });
});

test("up stops when docker compose is older than the multiple --env-file flags need", async () => {
  const { root } = await ready();
  const answer = await run(root, ["up"], { "compose version": { status: 0, stdout: "2.20.0\n" } });
  assert.notEqual(answer.status, 0);
  assert.match(answer.err, /2\.24/);
  assert.equal(composeCalls(answer.calls).length, 1); // only the version question
  assert.equal(composeVersionOk("v2.24.0"), true);
  assert.equal(composeVersionOk("2.40.3-desktop.1"), true);
  assert.equal(composeVersionOk("2.23.9"), false);
  assert.equal(composeVersionOk("1.29.2"), false);
  assert.equal(composeVersionOk("garbage"), false);
});

test("every compose call names the project of compose.yaml, the profile local and both env files in order", async () => {
  const { root } = await ready();
  const all = [];
  for (const command of [["up"], ["status"], ["logs"], ["backup"], ["down"]]) {
    all.push(...(await run(root, command)).calls);
  }
  const compose = composeCalls(all).filter((call) => call.args[1] !== "version");
  assert.ok(compose.length >= 8);
  for (const call of compose) {
    assert.deepEqual(call.args.slice(0, 10), [
      "compose",
      "-p",
      "mail-assistant",
      "--env-file",
      ".env",
      "--env-file",
      "deploy/local/secrets.env",
      "--profile",
      "local",
      call.args[9],
    ]);
    assert.equal(call.options.cwd, root);
  }
  for (const call of dockerCalls(all)) {
    const kind = call.args[0] === "volume" ? call.args.slice(0, 2).join(" ") : call.args[0];
    assert.ok(["compose", "volume inspect"].includes(kind), `unexpected docker call: ${kind}`);
  }
  rmSync(root, { recursive: true, force: true });
});

test("the project name is the one compose.yaml defines, and the real compose.yaml defines mail-assistant", () => {
  assert.equal(projectName("# c\nname: other-name\nservices: {}\n"), "other-name");
  assert.throws(() => projectName("services: {}\n"));
  assert.equal(projectName(readFileSync(join(REPO, "compose.yaml"), "utf8")), "mail-assistant");
});

test("down stops the stack and never removes a volume", async () => {
  const { root } = await ready();
  const answer = await run(root, ["down", "--volumes"]);
  assert.notEqual(answer.status, 0); // the flag is refused, not passed on
  assert.equal(dockerCalls(answer.calls).length, 0);

  const plain = await run(root, ["down"]);
  assert.equal(plain.status, 0, plain.err);
  const down = composeCalls(plain.calls).find((call) => call.args.includes("down"));
  assert.deepEqual(down.args.slice(down.args.indexOf("local") + 1), ["down"]);
  assert.ok(!plain.calls.some((call) => call.args.some((arg) => arg === "-v" || arg === "--volumes")));
  rmSync(root, { recursive: true, force: true });
});

test("the script source has no way to remove a volume", () => {
  assert.ok(!/--volumes|["']-v["']|volume\s+(rm|prune)|\bprune\b/.test(SCRIPT.replace(/\/\/.*$/gm, "")));
  assert.ok(!SCRIPT.includes("shell: true"));
});

test("backup writes a timestamped dump from the container's own pg_dump and puts no secret on the command line", async () => {
  const { root } = await ready();
  const answer = await run(root, ["backup"]);
  assert.equal(answer.status, 0, answer.err);
  const dump = composeCalls(answer.calls).find((call) => call.args.includes("pg_dump"));
  assert.equal(sub(dump), "exec -T db pg_dump -U app app");
  assert.equal(dump.options.outFile, join(root, "deploy", "local", "backups", "20261114T101530Z.sql"));
  const joined = dockerCalls(answer.calls).map((call) => call.args.join(" ")).join("\n");
  assert.ok(!/PASSWORD|pg-from-env|rt-from-env/.test(joined));
  assert.equal(backupFileName(FIXED), "20261114T101530Z.sql");
  rmSync(root, { recursive: true, force: true });
});

test("backup of an empty dump counts as a failure", async () => {
  const { root } = await ready();
  const answer = await run(root, ["backup"], {
    pg_dump: ({ options }) => {
      writeFileSync(options.outFile, "");
      return { status: 0, stdout: "" };
    },
  });
  assert.notEqual(answer.status, 0);
  assert.ok(!existsSync(join(root, "deploy", "local", "backups", "20261114T101530Z.sql")));
  rmSync(root, { recursive: true, force: true });
});

test("status and logs pass through to compose; an unknown service name is refused", async () => {
  const { root } = await ready();
  const status = await run(root, ["status"]);
  assert.ok(composeCalls(status.calls).map(sub).includes("ps --all"));
  const logs = await run(root, ["logs", "api", "--follow"]);
  assert.ok(composeCalls(logs.calls).map(sub).includes("logs --no-color --tail 200 --follow api"));
  const bad = await run(root, ["logs", "api; rm -rf /"]);
  assert.notEqual(bad.status, 0);
  assert.equal(dockerCalls(bad.calls).length, 0);
  rmSync(root, { recursive: true, force: true });
});

test("trust-ca prints how to trust the CA and changes nothing", async () => {
  const { root } = await ready();
  const answer = await run(root, ["trust-ca"]);
  assert.equal(answer.status, 0, answer.err);
  assert.match(answer.out, /ca\.crt/);
  assert.match(answer.out, /certutil/);
  assert.match(answer.out, /Firefox/);
  assert.equal(answer.calls.length, 0);
  const none = checkout();
  assert.notEqual((await run(none, ["trust-ca"])).status, 0);
  rmSync(root, { recursive: true, force: true });
  rmSync(none, { recursive: true, force: true });
});

test("an unknown command prints the usage and exits with 2", async () => {
  const root = checkout();
  const answer = await run(root, ["explode"]);
  assert.equal(answer.status, 2);
  assert.match(answer.err, /usage/i);
  assert.equal(answer.calls.length, 0);
  assert.ok(statSync(root).isDirectory());
  rmSync(root, { recursive: true, force: true });
});
