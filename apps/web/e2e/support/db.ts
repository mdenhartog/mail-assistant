// Owner-level SQL for the `journey` project (U-web-settings-43): resets between tests, seeds and the few facts the
// browser cannot see (a session aged, the web lock set, the number of sessions). It runs `psql` inside the `db` service
// of the prod-like stack as its bootstrap owner `app`. The unix socket of that container is `trust` in
// deploy/prod-like/pg_hba.conf and is not reachable from outside, so no password is needed, read or written here; the
// stack's own .env is only read by compose to resolve the service definition. The SQL goes in through stdin, never
// through the command line.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const REPOSITORY = fileURLToPath(new URL("../../../../", import.meta.url));

/** Runs SQL as the owner and returns the unaligned, tuples-only output (one line per row, `|` between columns). */
function sql(statements: string): string {
  return execFileSync(
    "docker",
    [
      "compose",
      "--project-directory",
      REPOSITORY,
      "--profile",
      "prod-like",
      "exec",
      "-T",
      "db",
      "psql",
      "-U",
      "app",
      "-d",
      "app",
      "-v",
      "ON_ERROR_STOP=1",
      "-At",
      "-f",
      "-",
    ],
    { input: statements, encoding: "utf8" },
  ).trim();
}

/** The stored times of a seeded row: Amsterdam, quiet 23:00 to 07:00, overview 18:00, reminders 09:00, from Telegram. */
const SEED = `
INSERT INTO settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by)
VALUES (1, 'Europe/Amsterdam', 1380, 420, 1080, 540, 1, 'telegram', 'telegram:journey');
`;

/** The settings row, the sign-in tables and the lock back to a fresh stack. */
export function resetState(): void {
  sql(`
    DELETE FROM settings.schedule;
    DELETE FROM web_auth.session;
    DELETE FROM web_auth.login_request;
    DELETE FROM web_auth.security_event;
    DELETE FROM web_auth.web_lock;
  `);
}

/** A stored row at version 1, last changed from Telegram. */
export function seedSettings(): void {
  sql(SEED);
}

/** "version|overview" of the stored row as minutes of the day, or an empty string when there is no row. */
export function storedRow(): string {
  return sql("SELECT version || '|' || overview_at || '|' || zone FROM settings.schedule WHERE id = 1");
}

/** Makes every session idle for hours, so the next request with it is an expired one. */
export function ageSessions(): void {
  sql("UPDATE web_auth.session SET last_seen_at = now() - interval '3 hours'");
}

export function sessionCount(): number {
  return Number(sql("SELECT count(*) FROM web_auth.session"));
}

/** Sets the web lock, as the agent's lock action does (ADR-0033). */
export function lockWeb(): void {
  sql("INSERT INTO web_auth.web_lock (id, locked_at) VALUES (1, now()) ON CONFLICT DO NOTHING");
}
