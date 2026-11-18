// Owner-level SQL for the `review` project (U-mail-categories-19): the plan the agent would have built, and the facts the
// browser cannot see (plan state, apply time, move-back request). The stack has no agent, so the steps that only the agent
// takes (build, apply, answer a Telegram Cancel) are set here by SQL, through the same state guard the agent's own writes
// pass; what the agent does with the plan is covered by its pytest with a fake Gmail and Telegram.
import { sql } from "./db";
import { INVOICES_ID, OTHER_ID, resetCategories, seedList } from "./categoriesDb";

const MAILBOX = "primary";
const PLAN_ID = "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00aa";

export interface PlanSeed {
  /** Mails in the one group "Other to Invoices". */
  items: number;
  /** Mails per 24 hours above which an approval waits. */
  threshold: number;
  /** Minutes an approval above the threshold waits. */
  delayMinutes: number;
  /** Text put in sender and subject of every mail, so a log search can find it. */
  canary: string;
}

/** No plan, no approvals, no list: a fresh stack as before the agent's first start. */
export function resetReview(): void {
  sql(`
    DELETE FROM categories.move_back_request;
    DELETE FROM categories.apply_audit;
    DELETE FROM categories.rejection;
    DELETE FROM categories.apply_config;
  `);
  resetCategories();
}

/** Version 1 of the list plus a ready plan with one group of mails from "Other" to "Invoices". */
export function seedPlan(seed: PlanSeed): void {
  seedList();
  sql(`
    BEGIN;
    INSERT INTO categories.apply_config (mailbox_id, threshold, delay_minutes)
      VALUES ('${MAILBOX}', ${String(seed.threshold)}, ${String(seed.delayMinutes)});
    INSERT INTO categories.plan (mailbox_id, id, list_version, state, checked_count)
      VALUES ('${MAILBOX}', '${PLAN_ID}', 1, 'ready', ${String(seed.items)});
    INSERT INTO categories.plan_item
      (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, old_category_id, new_category_id)
    SELECT '${MAILBOX}', '${PLAN_ID}', 'm' || n, '${seed.canary} sender ' || n, 'a' || n || '@${seed.canary}.example',
           '${seed.canary} subject ' || n, '${OTHER_ID}', '${INVOICES_ID}'
      FROM generate_series(1, ${String(seed.items)}) AS n;
    COMMIT;
  `);
}

/** The state of the plan, or null when there is none. */
export function planState(): string | null {
  const out = sql(`SELECT state FROM categories.plan WHERE mailbox_id = '${MAILBOX}' AND id = '${PLAN_ID}'`);
  return out === "" ? null : out;
}

/** Minutes from now until the plan may be applied (negative: in the past), or null when no time is set. */
export function applyDelayMinutes(): number | null {
  const out = sql(
    `SELECT extract(epoch FROM (apply_after - now())) / 60 FROM categories.plan WHERE mailbox_id = '${MAILBOX}' AND id = '${PLAN_ID}'`,
  );
  return out === "" ? null : Number(out);
}

/** "decision/state|count" per kind of item, for instance "approved/approved|20". */
export function itemStates(): string[] {
  const out = sql(
    `SELECT decision || '/' || state || '|' || count(*) FROM categories.plan_item WHERE plan_id = '${PLAN_ID}' GROUP BY decision, state ORDER BY 1`,
  );
  return out === "" ? [] : out.split("\n");
}

/** What the agent does after the approval time: the plan is applied and every approved mail is moved. */
export function markApplied(): void {
  sql(`
    UPDATE categories.plan SET state = 'applying' WHERE id = '${PLAN_ID}' AND state = 'scheduled';
    UPDATE categories.plan_item SET state = 'applied' WHERE plan_id = '${PLAN_ID}' AND decision = 'approved';
    UPDATE categories.plan SET state = 'applied' WHERE id = '${PLAN_ID}' AND state = 'applying';
  `);
}

/** What the agent does when the user presses Cancel in Telegram while the plan waits. */
export function cancelFromTelegram(): void {
  sql(`UPDATE categories.plan SET state = 'cancelled' WHERE id = '${PLAN_ID}' AND state = 'scheduled'`);
}

/** Move-back requests of the plan that the agent has not processed yet. */
export function openMoveBackRequests(): number {
  return Number(sql(`SELECT count(*) FROM categories.move_back_request WHERE plan_id = '${PLAN_ID}' AND NOT processed`));
}
