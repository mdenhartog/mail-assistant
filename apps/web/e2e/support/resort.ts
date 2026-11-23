// Owner-level SQL for the `label-structure-r2` project (U-label-structure-27): what the agent would have written after
// "Sort everything again" (ADR-0056): the two plans of one request, an `auto` plan the agent approves itself and a
// `review` plan for the mails it was not sure about. The prod-like stack has no agent and no Gmail, so SQL stands in for
// the agent's writes (plan rows, items, the apply and a Telegram Cancel) while the browser journey checks what the user
// sees and what the api stores. The columns and constraints are those of revisions 0015, 0024 and 0029 of mail-triage:
//
// - `plan.kind` is `auto` or `review`; an `auto` plan needs `request_id`, and its `threshold` is copied from the request
//   by a trigger (no value is written here); one open plan per mailbox and kind.
// - `plan_item`: the old and new pair (`old_topic_id`, `new_topic_id`, ...), `confidence_pct` 0 to 100, `tip` up to 500
//   characters; `decision_source = 'threshold'` needs `decision = 'approved'`; an applied, skipped or failed item was
//   approved; `state` approved or rejected equals the decision.
import { sql } from "./db";
import { INVOICES_ID, OTHER_ID, TRAVEL_ID } from "./categoriesDb";
import { resetReview } from "./reviewDb";

const MAILBOX = "primary";
const AUTO_PLAN_ID = "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00ab";
const REVIEW_PLAN_ID = "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00ac";

/** The tip the model would write for the category Invoices; the page shows it as plain text. */
export const INVOICES_TIP = "Mention payment reminders in the description of Invoices so they are filed there.";

/** Mails the `auto` plan holds: four are moved by the apply, one is skipped by it. */
export const AUTO_ITEMS = 5;
/** Mails of the `review` plan: four for Invoices (with the tip) and two for Travel (no tip). */
export const REVIEW_ITEMS = 6;

/** No plan, no list and no request: a fresh stack. The request table is emptied too, which also resets the hourly limit. */
export function resetResort(): void {
  resetReview();
  sql("DELETE FROM categories.resort_request");
}

/** A request as the api stores it (the channel and the time are the database's). Returns its id. */
export function seedRequest(threshold: number): string {
  return sql(`INSERT INTO categories.resort_request (mailbox_id, threshold) VALUES ('${MAILBOX}', ${String(threshold)}) RETURNING id`)
    .split("\n")[0] ?? "";
}

/** The id of the newest request, which the page made when the user pressed the button. */
export function latestRequestId(): string {
  return sql(`SELECT id FROM categories.resort_request WHERE mailbox_id = '${MAILBOX}' ORDER BY at DESC, id DESC LIMIT 1`);
}

/** "threshold|channel" per request, oldest first; the channel is `web` for a request the api made. */
export function requestRows(): string[] {
  const out = sql(`SELECT threshold || '|' || channel FROM categories.resort_request WHERE mailbox_id = '${MAILBOX}' ORDER BY at, id`);
  return out === "" ? [] : out.split("\n");
}

/**
 * The `auto` plan of the request: five mails with a confidence above the threshold, approved by the agent itself
 * (decision source `threshold`) and scheduled 20 minutes from now. Nothing has moved yet.
 */
export function seedAutoPlan(request: string): void {
  sql(`
    BEGIN;
    INSERT INTO categories.plan (mailbox_id, id, list_version, state, checked_count, kind, request_id, apply_after)
      VALUES ('${MAILBOX}', '${AUTO_PLAN_ID}', 1, 'scheduled', ${String(AUTO_ITEMS)}, 'auto', '${request}', now() + interval '20 minutes');
    INSERT INTO categories.plan_item
      (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, old_category_id, new_category_id,
       new_topic_id, confidence_pct, decision, state, decision_source, decided_at)
    SELECT '${MAILBOX}', '${AUTO_PLAN_ID}', 'auto' || n, 'Auto sender ' || n, 'auto' || n || '@sender.example',
           'Auto subject ' || n, '${OTHER_ID}', '${INVOICES_ID}', '${INVOICES_ID}', 90 + n, 'approved', 'approved',
           'threshold', now()
      FROM generate_series(1, ${String(AUTO_ITEMS)}) AS n;
    COMMIT;
  `);
}

/**
 * The `review` plan of the request: six mails the model was less sure about, in two groups. The first mail of the group
 * to Invoices carries the tip; the group to Travel has none.
 */
export function seedReviewPlan(request: string): void {
  sql(`
    BEGIN;
    INSERT INTO categories.plan (mailbox_id, id, list_version, state, checked_count, kind, request_id)
      VALUES ('${MAILBOX}', '${REVIEW_PLAN_ID}', 1, 'ready', ${String(AUTO_ITEMS + REVIEW_ITEMS)}, 'review', '${request}');
    INSERT INTO categories.plan_item
      (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, old_category_id, new_category_id,
       new_topic_id, confidence_pct, tip)
    SELECT '${MAILBOX}', '${REVIEW_PLAN_ID}', 'review' || n, 'Review sender ' || n, 'review' || n || '@sender.example',
           'Review subject ' || n, '${OTHER_ID}',
           CASE WHEN n <= 4 THEN '${INVOICES_ID}'::uuid ELSE '${TRAVEL_ID}'::uuid END,
           CASE WHEN n <= 4 THEN '${INVOICES_ID}'::uuid ELSE '${TRAVEL_ID}'::uuid END,
           40 + n * 5,
           CASE WHEN n = 1 THEN '${INVOICES_TIP}' ELSE NULL END
      FROM generate_series(1, ${String(REVIEW_ITEMS)}) AS n;
    COMMIT;
  `);
}

/** The request, the `auto` plan and the `review` plan, as the agent leaves them after it has built both. Returns the request id. */
export function seedBothPlans(threshold: number): string {
  const request = seedRequest(threshold);
  seedAutoPlan(request);
  seedReviewPlan(request);
  return request;
}

/** What the agent does after the delay: four mails are moved, one is skipped, the `auto` plan is applied. */
export function applyAutoPlan(): void {
  sql(`
    UPDATE categories.plan SET state = 'applying' WHERE id = '${AUTO_PLAN_ID}' AND state = 'scheduled';
    UPDATE categories.plan_item SET state = 'applied' WHERE plan_id = '${AUTO_PLAN_ID}' AND message_id <> 'auto${String(AUTO_ITEMS)}';
    UPDATE categories.plan_item SET state = 'skipped', reason = 'moved_by_user' WHERE plan_id = '${AUTO_PLAN_ID}' AND message_id = 'auto${String(AUTO_ITEMS)}';
    UPDATE categories.plan SET state = 'applied' WHERE id = '${AUTO_PLAN_ID}' AND state = 'applying';
  `);
}

/** What the agent does when the user presses Cancel in Telegram while the `auto` plan waits. */
export function cancelAutoPlan(): void {
  sql(`UPDATE categories.plan SET state = 'cancelled' WHERE id = '${AUTO_PLAN_ID}' AND state = 'scheduled'`);
}

export function autoPlanState(): string | null {
  const out = sql(`SELECT state FROM categories.plan WHERE id = '${AUTO_PLAN_ID}'`);
  return out === "" ? null : out;
}

/** Minutes from now until the `auto` plan may start (negative: in the past). */
export function autoApplyMinutes(): number {
  return Number(sql(`SELECT extract(epoch FROM (apply_after - now())) / 60 FROM categories.plan WHERE id = '${AUTO_PLAN_ID}'`));
}

/** "state|count" per item state of the `auto` plan, for instance "approved|5". */
export function autoItemStates(): string[] {
  const out = sql(`SELECT state || '|' || count(*) FROM categories.plan_item WHERE plan_id = '${AUTO_PLAN_ID}' GROUP BY state ORDER BY 1`);
  return out === "" ? [] : out.split("\n");
}

/** "decision/state|count" per kind of item of the `review` plan. */
export function reviewItemStates(): string[] {
  const out = sql(
    `SELECT decision || '/' || state || '|' || count(*) FROM categories.plan_item WHERE plan_id = '${REVIEW_PLAN_ID}' GROUP BY decision, state ORDER BY 1`,
  );
  return out === "" ? [] : out.split("\n");
}

/** The threshold the `review` plan copied from its request. */
export function reviewPlanThreshold(): number | null {
  const out = sql(`SELECT threshold FROM categories.plan WHERE id = '${REVIEW_PLAN_ID}'`);
  return out === "" ? null : Number(out);
}
