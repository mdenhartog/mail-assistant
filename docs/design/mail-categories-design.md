---
feature: mail-categories
intent: INT-004
spec: docs/specs/mail-categories.md
threat_model: docs/security/mail-categories-threat-model.md
adrs: [ADR-0042, ADR-0043, ADR-0044, ADR-0045, ADR-0046, ADR-0047]
status: approved
date: 2026-11-14
revised: 2026-11-14 (round table of phase 3)
approver: the user
---

# Design: mail categories

Placement follows the architecture baseline (ADR-0041): judging, plans, Gmail and Telegram stay in `mail-triage`; list and approvals are served by `api`; pages live in `web`; the rules are shared in `category-policy`. The components meet only in PostgreSQL. `node scripts/architecture.mjs check` passes with `docs/architecture/model.json`.

## Releases

- **R1:** schema (list half, counts, label names, filing, Telegram actions), `category-policy`, list routes, the "Categories" page (incl. "Older category" and "Add to my list"), judging against the list, pinned security mail, the `Archive` label, rename by id, list-change notice with Undo, rate limit, audit, the daily AC-46 report.
- **R2:** plan tables, plan build (also the first plan at the first start when none exists), apply, Move back, rejections, approvals with the delayed apply and Cancel, the "Review moves" page.
- Deferred to later: sender filter and sort on the review page, mutation testing of the apply state machine.

## Data model (schema `categories`, ADR-0042, ADR-0043, ADR-0047)

Every table has `mailbox_id` first in its keys. Rows written by the api carry no actor or channel from the api: the database derives them from the session role (ADR-0030).

| Table | Written by | Holds | Retention |
| --- | --- | --- | --- |
| `mailbox` | migration | id only | kept |
| `category_identity` | api (insert) | `mailbox_id`, `id` (stable uuid, kept across renames); referenced by `category` and `category_label` | kept |
| `list_version` | api, agent (seed v1, Undo) | `mailbox_id`, `version`, `created_at`, `created_via`, `created_by` (all derived by trigger) | 1 year after replaced |
| `category` | api, agent (insert only) | `mailbox_id`, `version`, `id`, `name`, `description`, `position`; "Other" is built in | with its version |
| `list_audit` | deferred constraint trigger | old and new list, channel, actor digest, time | 1 year |
| `category_count` | agent | per category the number of mails (from the agent's own data) | replaced each cycle |
| `gmail_label` | agent | name of each `Assistant/` label that exists in Gmail (names only) | replaced each cycle |
| `category_label` | agent | category id to Gmail label id and name | kept |
| `filing` | agent | message id, category id, list version used, time; no sender, no subject | 1 year |
| `list_cursor` | agent | `mailbox_id`, `last_version` (advanced only after the Gmail effects) | kept |
| `plan` | agent | id, list version built for, state, `apply_after`, cursor, counts (checked, cap, unclear), timestamps; partial unique index: one non-terminal plan per mailbox | 14 days after terminal |
| `plan_item` | agent inserts; decisions through functions only | `mailbox_id`, plan id, message id, sender name, sender address, subject (120), old and new category, decision, state, reason | 14 days after the last decision; at once after apply |
| `plan_decision` | `record_decision` | `mailbox_id`, plan id, scope, count, channel, actor digest (derived), time; append only | 1 year |
| `plan_approval` | `approve_plan` | `mailbox_id`, plan id, item count, time, actor digest; used for the rolling 24 hours threshold | 1 year |
| `rejection` | `approve_plan` (pending items) and agent | `mailbox_id`, message id, list version; until the list changes again | until then |
| `apply_audit` | agent | `mailbox_id`, message id, old and new label, plan id, channel, actor digest, time; no sender, no subject | 1 year |
| `move_back_request` | api (insert) | `mailbox_id`, plan id, time, actor digest | 1 year |
| `telegram_action` | agent | nonce hash, chat id, kind (undo, cancel, move back, lock), target, `expires_at`, `used_at`; single use by compare-and-set | 7 days after expiry |

## Grants and functions (ADR-0042, ADR-0044, ADR-0047)

Per-table grant matrix (everything not listed is refused, SQLSTATE 42501; a test checks the whole matrix):

| Table | api role | agent role |
| --- | --- | --- |
| `mailbox`, `category_identity` | `SELECT`; `INSERT` on `category_identity` | `SELECT`, `INSERT` |
| `list_version`, `category` | `SELECT`, `INSERT` | `SELECT`, `INSERT` (seed v1, Undo) |
| `list_audit` | none | `SELECT` |
| `apply_config` | none (the functions read it as definer) | `SELECT`, `INSERT`, `UPDATE` |
| `category_count`, `gmail_label`, `category_label`, `list_cursor` | `SELECT` on `category_count` and `gmail_label` only | `SELECT`, `INSERT`, `UPDATE`, `DELETE` on the derived and cursor tables (they are replaced each cycle) |
| `filing`, `rejection` | none | `SELECT`, `INSERT` |
| `plan` | `SELECT` | `SELECT`, `INSERT`, `UPDATE` |
| `plan_item` | column `SELECT` on `id`, `plan_id`, `mailbox_id`, sender name and address, subject, categories, decision, state, reason (not the message id) | `SELECT`, `INSERT`, `UPDATE` (state and reason only; decisions change only through the functions) |
| `plan_decision`, `plan_approval` | none (written by the functions) | `SELECT` |
| `apply_audit` | none | `SELECT`, `INSERT` |
| `move_back_request` | `SELECT`, `INSERT` (unique `(mailbox_id, plan_id)`) | `SELECT`; `UPDATE` of its processed flag |
| `telegram_action` | none | `SELECT`, `INSERT`, `UPDATE` (`used_at` only) |

No runtime role has `DELETE` on an audit, decision or approval table, `UPDATE` on `plan_item.decision`, or any right on `public` tables of the other runtime. `EXECUTE` on `record_decision` and `approve_plan` is for the api role only; `purge_expired()` is for the agent role only.

- **Functions** (`SECURITY DEFINER`, owned by a non-login role, `search_path` pinned, revoked from `PUBLIC`, error messages without row values):
  - `record_decision(plan_id, item_count, scope, decision)`: locks the plan `FOR UPDATE`, checks that it is `ready` and that the count matches (otherwise a 409 error), sets the decisions, inserts `plan_decision`. Idempotent: the same decision twice succeeds.
  - `approve_plan(plan_id, item_count)`: locks the plan `FOR UPDATE`, checks state and count, inserts `plan_approval`, turns still-pending items into `rejected` and into `rejection`, sums the approved items of the mailbox over 24 hours including this approval and sets the plan to `scheduled` with `apply_after` = now (sum at or below the threshold) or now + delay (sum strictly above it). The threshold and the delay are read by the function from the one-row table `categories.apply_config(mailbox_id, threshold, delay_minutes)`, which only the agent writes from its deployment configuration; the function takes no parameter for them, so a leaked api credential cannot raise them. A repeated `approve_plan` for a plan that is already `scheduled` returns its current state instead of an error.
  - `purge_expired()`: owner role, **no parameters**: it uses the database clock (`now()`) inside and deletes only rows past their retention, whatever the caller supplies; tests backdate rows with owner fixtures and a fake clock at the test level only.
  - Input checks (all three functions): no dynamic SQL is built from any argument; `scope` must be one of the fixed shapes (`group` with its `groupCount`, `ids` of at most 200, or `all`); every id must belong to the given plan and mailbox; the plan's `mailbox_id` must match the caller's mailbox; a decision on a plan that is not `ready` is a 409 error; functions and triggers set a fixed `search_path`, are owned by a non-login role, revoked from `PUBLIC`, and error text carries no row values.
- The trigger functions that fill the audit tables and derive actor, channel and time are `SECURITY DEFINER`, owned by the owner role, with a pinned `search_path` (neither runtime role has `INSERT` on `list_audit`). A deferred constraint trigger allows inserts into `category` only for a version created in the same transaction, with `version = expected + 1`; a unique violation on `(mailbox_id, version)` is a 409.

## State machines (owned by the agent, ADR-0046)

Plan: `building -> ready -> scheduled -> applying -> applied`. `scheduled` is always used; below the threshold `apply_after` is now. `building` and `ready` become `replaced` when the list changes; `scheduled` and `applying` are finished first (a list change never discards an approved plan, and AC-26 skips only items whose category is gone). `scheduled -> cancelled` (Cancel, or Lock) and `scheduled -> applying` both go through compare-and-set under `FOR UPDATE`, so Cancel wins or loses cleanly. `ready` plans older than 14 days become `discarded`.

Item: `pending -> approved | rejected`; `approved -> applied | skipped | failed`. Decisions are frozen from `scheduled`.

## API (api, generated OpenAPI, added to the route allow-list of AC-15 of web-settings)

403 only for the web lock, CSRF and Origin. 409 for a version, plan, count or state mismatch (also `not-ready` before the seed exists, and "plan not ready"). Errors are problem+json without row values; responses carry `Cache-Control: no-store`.

| Method and path | Release | Result |
| --- | --- | --- |
| GET `/api/categories` | R1 | `{version, categories: [{id, name, description, mailCount}], other: {mailCount}, olderCategories: [{labelName, mailCount}], ready}`; counts from `category_count`, older labels from `gmail_label` |
| PUT `/api/categories` | R1 | body `{version, categories: [{id?, name, description}]}`; 200, 409 (current list, or `not-ready`), 422 `problems`, 429 above the account limit; the name rule also checks `gmail_label`; an unchanged list makes no version |
| GET `/api/plan` | R2 | state, progress, groups `{from, to, count}`, counts, `applyAfter`, `lastPlan` |
| GET `/api/plan/items?from=&to=&page=` | R2 | at most 100 items; no search or filter in the URL |
| POST `/api/plan/decisions` | R2 | body `{planId, itemCount, scope: {group, groupCount} or {ids (at most 200)} or {all: true}, decision}`; calls `record_decision` |
| POST `/api/plan/approve` | R2 | body `{planId, itemCount}`; calls `approve_plan`; returns the state and `applyAfter` |
| POST `/api/plan/{id}/move-back` | R2 | inserts `move_back_request`; the agent restores the labels from `apply_audit` |

## Agent flows

- **Judging (R1).** Per cycle a snapshot of the current list (version read through `list_cursor`), one mail per call, fixed urgency rules, descriptions as a separate data block, resolve the id (unknown to "Other", urgency kept), skip pinned mail, label, write a `filing` row. Pinned mail: only the topmost `Authentication-Results` header with authserv-id `mx.google.com`, `dmarc=pass` and a `header.from` domain equal to the parsed From domain and on the allow-list; checked again before each apply.
- **List change (R1).** Reads `list_audit` above its cursor, sends one notice with old and new list and Undo (also in quiet hours), renames labels by id for name-only changes, creates missing labels and `Archive`, refreshes `category_count` and `gmail_label`, then advances the cursor. Everything is idempotent by label id; Undo writes the previous list as a new version and produces exactly one notice. Seeds version 1 from the current labels at the first start.
- **AC-46 report (R1).** A daily check compares the label recorded in `filing` with the mail's current label and reports the numbers of D19.
- **Plan build (R2).** Starts when the list has been stable for the debounce time, and at the first R2 start when no plan exists. One build at a time; lists mail in scope (not spam, trash, `Archive`, pinned, `rejection`; two `Assistant/` labels counted as unclear), newest first up to 5 000, judges within the budget above the reserve, writes an item only when the category would change, sends "plan ready" with numbers.
- **Apply (R2).** Polls `scheduled` plans whose `apply_after` has passed; takes approved items; re-checks scope, labels and pinning per mail; removes the old and adds the new label; writes `apply_audit`; removes the items; sends the result notice with Move back and Lock. Lock also cancels `scheduled` plans, and an `applying` plan checks the lock and its own state by compare-and-set before every batch and stops (the mails already moved stay moved and can be moved back). Move back processes only `applied` plans, reads `move_back_request` and `apply_audit`, restores labels skipping mail changed meanwhile, writes `apply_audit` rows with the channel and sends one Telegram notice.
- **Telegram actions.** Every button carries a nonce; the agent stores only its hash in `telegram_action` with chat id, kind, target and expiry, and consumes it by compare-and-set.

## Web

Routes `/categories` and `/review`; the main navigation is a `nav` with links and `aria-current`, and a badge with the text "842 open items". Data only through hooks in `src/api/categories/*.queries.ts`; types from OpenAPI; all states. The built `ConfirmDialog` is rebuilt with a `tone` (safe or danger, ADR-0046 and the hand-off): saves and label-only moves get a normal confirm button, "replaces the review and discards your decisions" and Move back stay red; the cancel button comes first in the DOM, the focus trap covers every focusable element and Escape cancels. One debounced polite live region for the selection count; group rows keep a stable DOM; "Select all N in this group" only selects; "Keep all in place". Pages of 100 rows with "Load more", no virtualised scrolling. Viewports in tests: 320, 375, 768 and 1280 px and 200 % text size.

## Test strategy (summary; the plan in phase 4 maps every AC to a test)

Unit 1 is the set of test fakes: a Gmail with a label and message state machine and fault hooks (fail after the change and before the database write, 429 and 5xx, a label created twice, a mail changed meanwhile, a deleted label or mail, `Authentication-Results`), a contract test that keeps it aligned with the real Gmail wrapper, a shared fake clock, a budget ledger, a Telegram fake that records text and checks canary strings, a stub model with a hostile corpus, and seed factories (1 000 items in 20 groups, 50 and 51 categories, 5 001 mails in scope, NFKC look-alikes, bidi subjects). Real PostgreSQL: a matrix of table, column, operation and role expecting SQLSTATE 42501, functions revoked from `PUBLIC`, the Cancel-versus-apply race and compare-and-set with two connections, retention with the fake clock, migrations up and down with data kept, the two-mailbox test, a seeded token table in another schema. Contract: OpenAPI with schemathesis (authenticated session and CSRF) and `category_cases.json` in both runtimes. Web: MSW component tests, axe on all states, Playwright journeys at the viewports above. A scan for canary strings in logs, a Sentry stub and the Telegram fake. Mutation testing on `category-policy` and the label classifier (the apply state machine later).

## Units (proposal for phase 4, order matters)

R1: U-01 test fakes and seed data, U-02 `category-policy`, U-03 schema, roles and functions, U-04 list API (with "Older category"), U-05 judging (closed set, pinned mail, `filing`), U-06 label sync (rename, `Archive`, counts), U-07 list notice, Undo and audit, U-08 `ConfirmDialog` tone and Categories page, U-09 R1 e2e and the AC-46 report. R2: U-10 plan state machine and tables, U-11 plan build (budget, cap, scope, first plan), U-12 apply and Move back, U-13 approvals, Telegram Cancel, Lock and nonces, U-14 plan, approve and move-back API, U-15 Review moves page, U-16 R2 e2e.

## Decisions taken in the phase 3 round table (the user, 2026-11-14)

D16 stays in R2 (delayed apply, Cancel, 24-hour threshold); `ConfirmDialog` gets a `tone`; `filing` stays in R1; pages of 100 with "Load more"; the api reads only the columns listed above. The sender filter and sort and the mutation testing of the apply state machine move to a later release.
