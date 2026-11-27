// Owner-level SQL for the `label-prefix-removal` project (U-label-prefix-removal-14): what the agent would have written for
// the one-time rename of the old `Assistant/...` labels (ADR-0060, ADR-0061) and for the delayed delete of empty labels.
// The prod-like stack has no agent, no Gmail and no Telegram, so SQL stands in for the agent's writes (the plan and its
// hash, the items it finishes, the state `done`, an empty-label timer that comes due and the record of a deleted label)
// while the browser journey checks what the user sees and what the api stores (the confirmation and the restore request).
// What the agent does with the plan is covered by the agent's own tests with a fake Gmail. The columns and rules are those
// of revision 0030 of mail-triage:
//
// - `label_migration`: the state goes `pending` to `confirmed` only through `confirm_label_rename` (a trigger refuses any
//   other writer, also an insert as `confirmed`); `confirmed` to `done` is the agent's. The plan hash may be set while the
//   plan is `pending`.
// - `label_rename_item`: one row per label (`rename` or `merge`), `planned` until the agent has handled it.
// - `label_empty_since`: the timer of an empty label with the waiting time it started with (5 to 720 minutes).
// - `deleted_label`: the record the page lists, keyed by the hash of the label id.
import { sql } from "./db";
import { seedList } from "./categoriesDb";

const MAILBOX = "primary";

export interface PlanItem {
  id: string;
  oldName: string;
  newName: string;
  mailCount: number;
  action: "rename" | "merge";
}

/** The merge into an existing label (the largest), a plain rename and the label the user skips in the journey. */
export const MERGED: PlanItem = { id: "Label_Amerika", oldName: "Assistant/Amerika", newName: "Amerika", mailCount: 40, action: "merge" };
export const RENAMED: PlanItem = { id: "Label_Facturen", oldName: "Assistant/Facturen", newName: "Facturen", mailCount: 12, action: "rename" };
const TRIPS: PlanItem = { id: "Label_Reizen", oldName: "Assistant/Reizen", newName: "Reizen", mailCount: 5, action: "rename" };
export const SKIPPED: PlanItem = { id: "Label_Oud", oldName: "Assistant/Oud", newName: "Oud", mailCount: 3, action: "rename" };

/** The plan the agent leaves when it has looked at the mailbox, largest label first as the page shows it. */
export const PLAN: readonly PlanItem[] = [MERGED, RENAMED, TRIPS, SKIPPED];
export const PLAN_LABELS = PLAN.length;
export const PLAN_MAILS = PLAN.reduce((total, item) => total + item.mailCount, 0);

function literal(text: string): string {
  return `'${text.replaceAll("'", "''")}'`;
}

/**
 * The list of version 1 and a pending rename plan: `label_migration` is `pending` with the hash the database function
 * computes from the items, as the agent stores it when the plan is complete. Returns that hash.
 */
export function seedRenamePlan(): string {
  seedList();
  const values = PLAN.map(
    (item) =>
      `('${MAILBOX}', ${literal(item.id)}, ${literal(item.oldName)}, ${literal(item.newName)}, ${String(item.mailCount)}, '${item.action}')`,
  ).join(",\n      ");
  const out = sql(`
    BEGIN;
    DELETE FROM categories.label_migration WHERE mailbox_id = '${MAILBOX}';
    INSERT INTO categories.label_migration (mailbox_id, state) VALUES ('${MAILBOX}', 'pending');
    INSERT INTO categories.label_rename_item (mailbox_id, label_id, old_name, new_name, mail_count, action) VALUES
      ${values};
    UPDATE categories.label_migration SET plan_hash = categories.label_plan_hash('${MAILBOX}') WHERE mailbox_id = '${MAILBOX}';
    COMMIT;
    SELECT plan_hash FROM categories.label_migration WHERE mailbox_id = '${MAILBOX}';
  `);
  // psql prints a status line (BEGIN, INSERT 0 4, ...) for every statement that is not a SELECT: keep the hash line.
  const hash = out.split("\n").find((line) => /^[0-9a-f]{64}$/.test(line));
  if (hash === undefined) {
    throw new Error("the seeded plan has no hash");
  }
  return hash;
}

/** The state of the rename plan (`pending`, `confirmed`, `done`), or null when there is no row. */
export function migrationState(): string | null {
  const out = sql(`SELECT state FROM categories.label_migration WHERE mailbox_id = '${MAILBOX}'`);
  return out === "" ? null : out;
}

export interface StoredConfirmation {
  planHash: string;
  skippedIds: string[];
  channel: string;
}

/** The confirmation the api stored, or null while there is none. */
export function storedConfirmation(): StoredConfirmation | null {
  const out = sql(
    `SELECT plan_hash || '|' || array_to_string(skipped_ids, ',') || '|' || channel FROM categories.label_confirmation WHERE mailbox_id = '${MAILBOX}'`,
  );
  if (out === "") {
    return null;
  }
  const [planHash = "", skipped = "", channel = ""] = out.split("|");
  return { planHash, skippedIds: skipped === "" ? [] : skipped.split(","), channel };
}

/** "label_id|state" per item, in label id order, for instance "Label_Amerika|planned". */
export function itemStates(): string[] {
  const out = sql(`SELECT label_id || '|' || state FROM categories.label_rename_item WHERE mailbox_id = '${MAILBOX}' ORDER BY label_id COLLATE "C"`);
  return out === "" ? [] : out.split("\n");
}

/**
 * What the agent does after the confirmation: every label of the plan is renamed or merged (`done`) except the ones the
 * user skipped, then the plan is `done`. The state change is the one the guard allows (`confirmed` to `done`).
 */
export function agentFinishesRename(): void {
  sql(`
    BEGIN;
    UPDATE categories.label_rename_item i
       SET state = CASE WHEN i.label_id = ANY (c.skipped_ids) THEN 'skipped' ELSE 'done' END
      FROM categories.label_confirmation c
     WHERE i.mailbox_id = '${MAILBOX}' AND c.mailbox_id = i.mailbox_id AND i.state = 'planned';
    UPDATE categories.label_migration SET state = 'done' WHERE mailbox_id = '${MAILBOX}' AND state = 'confirmed';
    COMMIT;
  `);
}

/** "channel|state" per restore request the api stored, oldest first; the state is `open` until the agent has processed it. */
export function restoreRequests(): string[] {
  const out = sql(
    `SELECT channel || '|' || CASE WHEN processed_at IS NULL THEN 'open' ELSE 'processed' END FROM categories.label_restore_request WHERE mailbox_id = '${MAILBOX}' ORDER BY at`,
  );
  return out === "" ? [] : out.split("\n");
}

/** A label that is empty since `emptyMinutesAgo` minutes, with the waiting time its timer started with. */
export function seedEmptyLabel(labelId: string, emptyMinutesAgo: number, waitMinutes: number): void {
  sql(`
    INSERT INTO categories.label_empty_since (mailbox_id, label_id, empty_since, last_seen_empty, wait_minutes)
    VALUES ('${MAILBOX}', ${literal(labelId)}, now() - make_interval(mins => ${String(emptyMinutesAgo)}), now(), ${String(waitMinutes)})
  `);
}

/**
 * One cycle of the agent's delayed delete: the label whose timer has run its own waiting time is deleted and recorded,
 * its timer goes. Returns how many labels were deleted (0 while the label is still within its wait).
 */
export function agentDeletesIfDue(labelId: string, name: string): number {
  const out = sql(`
    WITH due AS (
      DELETE FROM categories.label_empty_since
       WHERE mailbox_id = '${MAILBOX}' AND label_id = ${literal(labelId)}
         AND empty_since + make_interval(mins => wait_minutes) <= now()
       RETURNING label_id
    ), recorded AS (
      INSERT INTO categories.deleted_label (mailbox_id, label_id_hash, name)
      SELECT '${MAILBOX}', encode(sha256(convert_to(label_id, 'UTF8')), 'hex'), ${literal(name)} FROM due
      RETURNING 1
    )
    SELECT count(*) FROM recorded
  `);
  return Number(out);
}

/** How many empty-label timers are running. */
export function emptyTimers(): number {
  return Number(sql(`SELECT count(*) FROM categories.label_empty_since WHERE mailbox_id = '${MAILBOX}'`));
}

/** A label the agent deleted `daysAgo` days ago (a record older than the retention is not listed). */
export function seedDeletedLabel(labelId: string, name: string, daysAgo: number): void {
  sql(`
    INSERT INTO categories.deleted_label (mailbox_id, label_id_hash, name, deleted_at)
    VALUES ('${MAILBOX}', encode(sha256(convert_to(${literal(labelId)}, 'UTF8')), 'hex'), ${literal(name)},
            now() - make_interval(days => ${String(daysAgo)}))
  `);
}

/** The stored waiting time of the label cleanup in minutes, or null when the settings row does not exist. */
export function storedWaitMinutes(): number | null {
  const out = sql("SELECT label_wait_minutes FROM settings.schedule WHERE id = 1");
  return out === "" ? null : Number(out);
}
