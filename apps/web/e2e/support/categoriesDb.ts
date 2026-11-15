// Owner-level SQL for the `categories` project (U-mail-categories-11): the stored list the agent would have seeded
// (AC-49), and the facts the browser cannot see (versions, channel, audit, plans). It runs through support/db.ts, so it
// reaches the database of the stack the run was started for (COMPOSE_PROJECT_NAME), as the bootstrap owner.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { sql } from "./db";

const REPOSITORY = fileURLToPath(new URL("../../../../", import.meta.url));
const MAILBOX = "primary";

export const INVOICES_ID = "00000000-0000-4000-8000-0000000000a1";
export const TRAVEL_ID = "00000000-0000-4000-8000-0000000000a2";
export const BILLS_ID = "00000000-0000-4000-8000-0000000000a3";
export const OTHER_ID = "00000000-0000-0000-0000-000000000000";

export interface StoredCategory {
  id: string;
  name: string;
  description: string;
  position: number;
}

/** No list at all: the agent has not written version 1 yet, as before its first start. */
export function resetCategories(): void {
  sql(`
    TRUNCATE categories.plan_approval, categories.plan_decision, categories.plan_item, categories.plan,
      categories.list_audit, categories.category, categories.list_version, categories.category_label,
      categories.category_identity, categories.category_count, categories.gmail_label, categories.list_cursor
      CASCADE;
    INSERT INTO categories.mailbox (id) VALUES ('${MAILBOX}') ON CONFLICT DO NOTHING;
  `);
}

/**
 * Version 1 as the agent seeds it: Invoices and Travel with counts, "Other" with a count, and one Gmail label under
 * `Assistant/` that is not on the list (an older category).
 */
export function seedList(): void {
  sql(`
    BEGIN;
    INSERT INTO categories.category_identity (mailbox_id, id) VALUES
      ('${MAILBOX}', '${INVOICES_ID}'), ('${MAILBOX}', '${TRAVEL_ID}');
    INSERT INTO categories.list_version (mailbox_id, version) VALUES ('${MAILBOX}', 1);
    INSERT INTO categories.category (mailbox_id, version, id, name, description, position) VALUES
      ('${MAILBOX}', 1, '${INVOICES_ID}', 'Invoices', 'Invoices, receipts and payment confirmations', 0),
      ('${MAILBOX}', 1, '${TRAVEL_ID}', 'Travel', 'Bookings, tickets and itineraries', 1);
    INSERT INTO categories.category_count (mailbox_id, category_id, mail_count) VALUES
      ('${MAILBOX}', '${INVOICES_ID}', 12), ('${MAILBOX}', '${TRAVEL_ID}', 1), ('${MAILBOX}', '${OTHER_ID}', 3);
    INSERT INTO categories.gmail_label (mailbox_id, name) VALUES
      ('${MAILBOX}', 'Assistant/Invoices'), ('${MAILBOX}', 'Assistant/Travel'), ('${MAILBOX}', 'Assistant/Other'),
      ('${MAILBOX}', 'Assistant/Newsletters');
    COMMIT;
  `);
}

/** Another writer changes the list (as Telegram would): version 2 with Invoices, Travel and Bills. */
export function changeListElsewhere(): void {
  sql(`
    BEGIN;
    INSERT INTO categories.category_identity (mailbox_id, id) VALUES ('${MAILBOX}', '${BILLS_ID}');
    INSERT INTO categories.list_version (mailbox_id, version) VALUES ('${MAILBOX}', 2);
    INSERT INTO categories.category (mailbox_id, version, id, name, description, position) VALUES
      ('${MAILBOX}', 2, '${INVOICES_ID}', 'Invoices', 'Invoices, receipts and payment confirmations', 0),
      ('${MAILBOX}', 2, '${TRAVEL_ID}', 'Travel', 'Bookings, tickets and itineraries', 1),
      ('${MAILBOX}', 2, '${BILLS_ID}', 'Bills from elsewhere', 'Added in Telegram', 2);
    COMMIT;
  `);
}

/** The categories of one stored version, in order. */
export function storedList(version: number): StoredCategory[] {
  const json = sql(`SELECT categories.list_json('${MAILBOX}', ${String(version)})`);
  return JSON.parse(json) as StoredCategory[];
}

/** "version|channel" per stored version, oldest first. */
export function versions(): string[] {
  const out = sql(`SELECT version || '|' || created_via FROM categories.list_version WHERE mailbox_id = '${MAILBOX}' ORDER BY version`);
  return out === "" ? [] : out.split("\n");
}

/** The channel of the audit record of a version, or null when there is none. */
export function auditChannel(version: number): string | null {
  const out = sql(`SELECT channel FROM categories.list_audit WHERE mailbox_id = '${MAILBOX}' AND version = ${String(version)}`);
  return out === "" ? null : out;
}

/** How many review plans exist; R1 makes none. */
export function planCount(): number {
  return Number(sql("SELECT count(*) FROM categories.plan"));
}

/** What the stack's services logged so far, as one text (stdout and stderr of edge, web, api, db and mail). */
export function stackLogs(): string {
  return execFileSync(
    "docker",
    ["compose", "--project-directory", REPOSITORY, "--profile", "prod-like", "logs", "--no-color", "edge", "web", "api", "db", "mail"],
    { encoding: "utf8", maxBuffer: 256 * 1024 * 1024 },
  );
}
