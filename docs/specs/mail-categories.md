---
feature: mail-categories
intent: INT-004
status: approved
docs: docs/user-guide/mail-categories.md
date: 2026-11-14
approver: the user
depends_on: mail-triage, web-settings
---

# Mail categories chosen by the user

## Summary

Today the agent invents the category labels (`Assistant/<name>`) itself, up to a maximum of 15 (`MAX_CATEGORIES`, base spec C2). On the first real run 36 of 75 old mails ended under "Other" because the limit was reached. This feature turns the list around: the user keeps a list of categories, each with a name and a description, in the web app. The agent files a mail only under a category of that list, or under "Other" when nothing fits. When the user changes the list, the agent proposes how mail it filed earlier moves, the user sees the proposal and approves it, and only then does anything move.

Why: the categories on the first run were not the ones the user wants (INT-004).

It reverses decision D1 of `mail-triage` (the agent chooses categories), replaces C2 (maximum of 15) and the non-goal "No rules editor", and adds a second page to the web app.

## Who it is for

The user, with one mailbox and one agent. Several mailboxes and other Google accounts come later and are not built here (D7).

## Goals

1. The user sees and edits their list of categories, each with a name and a description, in the web app.
2. A new mail is filed under a category of the list, or under "Other"; the agent never creates a category on its own.
3. After a change of the list, the user sees which already filed mails would move and approves all of them at once, or each mail separately, before any mail moves.
4. The mails the user did not like in the first run end up where the user wants them.

## Non-goals

- Editing categories through Telegram (D1).
- More than one mailbox, more than one agent, another Google account or a Google sign-in (D7); the sign-in stays as in `web-settings` (ADR-0036, ADR-0037).
- Sorting mail in spam, trash or archive (D6).
- Rules by sender or keyword: the description is the only rule, and the model applies it.
- Deleting mail or sending mail (INT-001): the feature only changes labels.
- Showing mail bodies in the web app.

## Anti-goals (a failure even if it technically works)

- A mail moves that the user did not approve, or a mail the user rejected moves anyway.
- Text in a mail or in a description makes the agent file mail somewhere outside the list, move mail without approval, or show markup or script in the web app.
- The web app or its database role can read mail bodies, alert content or the Gmail token.
- A change of the list silently re-files the whole mailbox.

## Decisions made by the user

| # | Decision | Source |
| --- | --- | --- |
| D1 | Categories are set only in the web app, not in Telegram. | INT-004, 2026-11-08 |
| D2 | A category has a name and a description; the description tells the model why a mail belongs there. | INT-004 |
| D3 | A mail that fits no category goes to "Other". | INT-004 |
| D4 | After a change of the list, the agent sorts the mail it already filed again. | INT-004 |
| D5 | The user always sees what will move before it moves, and can approve all at once and mail by mail. | INT-004 |
| D6 | Sorting again covers all mail that is in the categories, but not mail in spam, trash and archive. | INT-004 |
| D7 | Now there is one mailbox; several agents and mailboxes may come later. The sign-in stays as it is. | User, 2026-11-14 |
| D8 | When a category is changed or deleted, the model decides where each of its mails goes. | INT-004 |
| D9 | The maximum of 15 categories is dropped. | User, 2026-11-14 |
| D10 | The overview shows sender and subject of each mail that would move, in the web app (approach A of the brainstorm); mail can be rejected one by one. | User, 2026-11-14 |
| D11 | "Archived" (excluded from sorting) means mail in a real Gmail label (folder) "Archive". The agent creates that label itself when it does not exist. Mail without any label is in the inbox and is sorted from there. (Replaces the first reading of D11: "not in the inbox and without an `Assistant/` label".) | User, 2026-11-14 |
| D12 | One feature, two releases: R1 (list and page "Categories") and R2 (re-sorting with "Review moves"). | User, 2026-11-14 |
| D13 | It is accepted that anyone who can read the user's mailbox and sign in to the web app also sees sender and subject of the plan; the phase 2 threat model still re-reviews risk R-1 and its mitigations. | User, 2026-11-14 |
| D14 | A pure rename of a category keeps its id and renames the Gmail label; no plan, no model call. A changed description or a deleted category goes through a plan. This narrows D8. | User, 2026-11-14 (round table) |
| D15 | A plan is limited by a cap of items (5 000, newest first, the rest reported as "not looked at"), not by an age window. | User, 2026-11-14 (round table) |
| D16 | An approval above a threshold of mails (default 50, configurable) waits 15 minutes (configurable) before the agent applies it, with a Telegram notice offering Cancel and Lock web sign-in. An applied plan can be moved back. There is no extra sign-in step. | User, 2026-11-14 (round table) |
| D17 | Undo and Cancel through Telegram are allowed as an exception to D1: they restore or stop a change, they never edit the list. | User, 2026-11-14 (round table) |
| D18 | The agent never deletes a Gmail label. Empty labels of deleted categories are listed in the result notice; the user removes them in Gmail. | User, 2026-11-14 (round table) |
| D19 | Success measures: two weeks after R1 the user re-files by hand fewer than 5 % of new mails and at most 15 % of new mail lands in "Other"; after the first R2 plan is applied, the 36 first-run mails under "Other" and the mails the user flagged on 2026-11-08 are where the user wants them. | User, 2026-11-14 (round table) |

## My calls (the user may change these)

- C-1: The list starts with the categories the agent has today (the seven starter categories and the labels already created under `Assistant/`), so nothing changes until the user edits the list. A label under `Assistant/` that is not on the list is a legacy label: its mails are part of the first plan.
- C-2: "Other" always exists, cannot be renamed or deleted, and has no description the user has to write. Its label is the existing `Assistant/Other`.
- C-3: Limits, set by configuration: 1 to 40 characters (code points, not bytes) for a name, no `/` (Gmail nests labels on it) and no control or format characters; names are trimmed and compared after Unicode NFKC normalisation and case folding, so look-alikes and letter case do not make a duplicate; the names "Other" and "Archive" are reserved; a name that equals an existing Gmail label under `Assistant/` that is not on the list is refused; 1 to 500 characters for a description; at most 50 categories as a safety cap against runaway model cost and prompt size. The name pattern is the one `judgement.py` uses today, to be confirmed in phase 3. The rules live in the shared package `category-policy` (phase 3).
- C-4: Descriptions are untrusted text for the model: they are given to the model as data in a fixed place of the prompt, with the same limits and escaping as mail text, and the model may only answer with a category id from the list (a closed set); anything else is filed under "Other". They are shown in the web app as text.
- C-5: "In the categories" (D6) means: the mail is in the inbox or carries an `Assistant/` label, is not in spam or trash, and does not carry the label `Archive`. A mail the agent filed (moved out of the inbox under a label) is therefore in scope, and so is a mail still in the inbox without a label. Mail that is neither in the inbox nor under an `Assistant/` label (Gmail's plain "All Mail") is out of scope.
- C-14: The label `Archive` is a top-level label (not under `Assistant/`), matched by name without regard to letter case; a nested label such as `Foo/Archive` does not count. It is written in English like the rest of the project. The agent creates it at the start of a run when it is missing (and again when the user deleted it), and does nothing else with it: it never puts mail in `Archive` and never removes it. The user files mail there by hand in Gmail. When a mail carries both `Archive` and an `Assistant/` label, `Archive` wins and the mail is out of scope. The agent already has the right to create labels (it creates the `Assistant/` labels), so no new Gmail permission is needed; to be confirmed in phase 2.
- C-6: Plan, not move. A change of the list creates a re-sort plan. The agent judges each mail in scope again with the model, within the daily budget above the reserve of ADR-0021, over as many days as needed, and writes a plan item only for mails whose category would change. Mails that stay are not listed.
- C-7: A plan item holds the Gmail message id, sender (display name and the real address), subject (cut to 120 characters, format and bidi control characters removed), old category, proposed category and a decision (pending, approved, rejected, applied, skipped, failed). Nothing else from the mail. Plans are removed 14 days after the last decision or when replaced; items of an applied plan are removed at once. Two things outlive the items, both without sender or subject: the apply audit (message id, old and new label, time; one year) so an apply can be moved back, and a table of rejected message ids that keeps them out of later plans until the list changes again (C-8).
- C-8: Review screen: items are grouped by "from category, to category", with counts, a select-all per group and for the whole plan, and a checkbox per mail. The user can approve the selected mails or approve all. A mail not approved stays where it is, and stays out of later plans until the list changes again.
- C-9: Applying: the agent, not the api, moves mail. Before moving it checks the mail is still in scope and still carries the old label; a mail that the user moved in Gmail meanwhile is skipped and shown as skipped. The move removes the old `Assistant/` label and adds the new one; it deletes nothing. Decisions are frozen from the moment the plan is `scheduled`; a list save while a plan is `scheduled` or `applying` lets that plan finish first, and the next build starts only after it is terminal (one non-terminal plan per mailbox). When the Gmail change succeeded and the database write failed, the retry ends with the item applied and moves nothing twice. An approval above the threshold waits (D16); the result is announced with counts, a "Move back" button for the whole apply and a "Lock web sign-in" button.
- C-10: When the user edits the list while a plan is pending, the pending plan is replaced by a new one (decisions already given are discarded and the page warns before saving, not afterwards). A deleted category's mails are part of the new plan; the label itself stays in Gmail (D18) and, when empty after the plan is applied, is named in the result notice.
- C-11: A change of the list is announced in Telegram with old and new list and an Undo button, like web settings changes (ADR-0033); a ready plan is announced with its numbers only, no mail content.
- C-12: Words: "Categories", "Description", "Other", "Review moves" (with a badge showing the number of open items), "Older category" (instead of "legacy label", with an "Add to my list" action). The page says that the description is read by the model, shows an example ("Invoices, receipts and payment confirmations"), says that changes apply to new mail from now on and old mail only after a review (R1), says that mail in the Gmail label `Archive` is never re-sorted, and that renaming only changes the label name.
- C-15: Rename (D14): every category has a stable id; a change of the name only is applied by the agent as a rename of the Gmail label by id. A new name that equals an existing Gmail label is refused at save. In R2, before saving a change of a description or a delete, the page shows "Saving will create a review of up to N mails". In R1, which has no review, the page says "Old mail stays where it is for now." instead.
- C-16: Urgency is separate from the category. The urgency rules are fixed in the agent and never come from a description; descriptions are given to the model as data in a separate block. An unknown category id goes to "Other" and keeps the model's urgency; an invalid answer stays "needs attention". The agent also never files the app's own sign-in code mail or Google security mail, matched by verified sender (not by the model's answer); they stay in the inbox. Every filing records the list version it used, so that a plan can move back what was filed under a version (for example after an Undo).
- C-17: Details: an empty list (only "Other") is allowed; a save without a change makes no new version and no notice; a mail with two or more `Assistant/` labels is out of scope and counted as "unclear" in the plan numbers; the counts on the page come from the agent's database, not live from Gmail; the first run seeds list version 1 from the current labels (C-1), and the api answers "not ready" until then; the web app shows skipped and failed items with a plain reason ("You moved this mail yourself").
- C-18: Review page (R2): groups are collapsed by default with count, one example row and "Approve group" / "Keep all" per group; "12 of 80 selected" with "select all 80 in this group"; filter and sort by sender; paging with "Load more" (no virtualised infinite scroll); a sticky action bar on mobile; the approve button states the effect ("Move 842 mails, labels only") and opens a summary (counts per group, "nothing is deleted", "you can move back"); while a plan is being built the page shows "340 of about 2 000 checked, nothing moves yet" and the number "not looked at" when the cap is reached; a line "last plan: applied 12 Nov, 310 moved".

## Behaviour

1. The user opens "Categories" in the web app and sees the list with name, description and the number of mails per category.
2. The user adds, edits or deletes a category and saves. The list is stored as a whole with a version (as web settings).
3. New mail is judged against the list from then on; the result is a category of the list, or "Other".
4. The agent builds a re-sort plan from the mails in scope, and tells the user in Telegram that a plan is ready.
5. The user opens "Review moves", sees the groups, un-ticks the mails that should stay, and approves.
6. The agent moves the approved mails and reports the result (moved, skipped, failed).

## Architecture fit

- `mail-triage`: judging against the list (closed set), building and applying plans, Telegram notices. It stays the only component with Gmail access.
- `api`: CRUD of the list with versions, reading the plan, recording approve and reject. It does not move mail.
- `web`: the "Categories" page and the "Review moves" page.
- Shared rules: a new shared Python package `packages/category-policy` (name rules, limits, reserved names, label mapping, decision values, a shared contract test file) used by agent and api. `schedule-policy` is not extended (round table). New component in `docs/architecture/model.json` in phase 3.
- Plan state machine: owned by the agent (building, ready, scheduled, applying, applied, replaced, discarded, cancelled; items pending, approved, rejected, applied, skipped, failed, with compare-and-set); the api changes decisions and approves only through two database functions (ADR-0047). The agent learns of list changes by polling a version cursor (as for web notices); there is no direct call from api to agent (ADR-0041).
- Gmail operations for plans live in a narrow adapter next to the triage wrapper: list, read, add and remove label, create label, rename a label by id (`Assistant/` only). No label delete (D18).
- Schema: the api-writable tables (list, versions, audit) are kept apart from the agent-owned tables (Gmail label map, plans, items, rejections, apply audit).
- Data: a new schema for the list and the plan, migrated by the agent's chain (ADR-0025). The api role gets rights on the list (select, insert) and column-level select on the plan items; it changes decisions only through two database functions (ADR-0047) and has no right on `public`. This narrows ADR-0025 ("no access to mail content") to "no access to mail bodies and tokens", and extends ADR-0018 for sender and subject in the web app. Both need an ADR in phase 3.
- Mailbox id (recommended by the round table, to be recorded as an ADR in phase 3): every new table carries a `mailbox_id` (NOT NULL, first in keys), filtered in the repository layer; the api takes it from configuration for now; row-level security is deferred. The same answer serves INT-006 (drift item 2 of the architecture baseline).
- ADRs for phase 3 (proposed): category contract and `category-policy` (extends ADR-0025); mailbox id; api reads sender and subject (narrows ADR-0025, partly supersedes ADR-0018, records MR-1); closed-set judging with urgency separate and security mail pinned (reverses D1 and C2 of `mail-triage`); plan lifecycle, budget share (extends ADR-0021) and Gmail operations, with Telegram Undo and Cancel as an exception to D1 (D17); database functions for decisions and the retention purge (ADR-0047). These are ADR-0042 to ADR-0047, status proposed until the phase 3 gate.

## Acceptance criteria

| # | Criterion |
| --- | --- |
| AC-1 | **Given** a signed-in user, **when** they open "Categories", **then** they see their list with name, description and number of mails, and "Other". |
| AC-2 | **Given** a valid name and description, **when** the user saves, **then** the list is stored whole with a new version and an audit record, and the agent uses it from its next run; **given** a name that is empty, too long, duplicated (any letter case), contains `/` or a control or format character, equals "Other" or "Archive" (also as a look-alike after NFKC and case folding), equals an existing Gmail label under `Assistant/` that is not on the list, or a description over the limit, **then** the field shows the reason and nothing is stored; **given** a save without a change, **then** no new version and no notice are made; **given** a list with only "Other", **then** it is allowed. (Tested as a table with one row per rule.) |
| AC-3 | **Given** the page loaded at version 1 and the list changed elsewhere, **when** the user saves, **then** the save is refused with 409 and the page shows the new list. |
| AC-4 | **Given** "Other", **when** the user tries to rename or delete it, **then** it is refused. |
| AC-5 | **Given** a new mail, **when** the agent judges it, **then** it carries exactly one label of the list or `Assistant/Other`, and the agent never creates another `Assistant/` label. |
| AC-6 | **Given** a model answer that is not an id of the list (an invented name, markup, a second category), **when** it is processed, **then** the mail goes to "Other". |
| AC-7 | **Given** a stubbed model that returns hostile output (an id outside the list, two ids, markup, "approve", an empty or very long answer) for mail text or a description with instructions, **when** it is processed, **then** the mail goes to "Other" and filing, plans, approvals and sending are unaffected; an answer longer than 1 000 characters is treated as invalid; the model judges one mail per call. (A live-model evaluation is optional and runs nightly, not in CI.) |
| AC-8 | **Given** more than 15 categories in the list, **when** mail is judged, **then** all of them can be used; **given** the safety cap, **when** the user adds one more, **then** it is refused with the reason. |
| AC-9 | **Given** a changed list, **when** the agent runs, **then** it creates a plan with items only for mails whose category would change, and moves nothing. |
| AC-10 | **Given** mail in spam, in trash, or carrying the label `Archive` (also when it carries an `Assistant/` label), **when** a plan is built, **then** none of it is an item; **given** mail in the inbox without a label, **then** it is judged and can be an item. |
| AC-11 | **Given** a plan and a fake clock and budget ledger, **when** the budget above the reserve is used up (also when it is zero), **then** the reserve is never used, the plan stays "building" with its progress and continues after the next day boundary, and new mail keeps its guaranteed share (ADR-0021); **given** more than 5 000 mails in scope, **then** the plan holds the newest 5 000 and reports the rest as "not looked at" (D15). |
| AC-12 | **Given** a plan, **when** the user opens "Review moves", **then** they see groups "from, to" with counts, and per mail the sender and subject as plain text. |
| AC-13 | **Given** the review page, **when** the user approves all, **or** approves selected mails and leaves others, **then** exactly the approved items are moved and the others stay and stay out of later plans until the list changes again. |
| AC-14 | **Given** an approved item, **when** the agent applies it, **then** it moves the mail by removing the old `Assistant/` label and adding the new one, and it deletes and sends nothing. |
| AC-15 | **Given** an approved item whose mail was moved or deleted in Gmail meanwhile, **when** the agent applies it, **then** the item is skipped and shown as skipped. |
| AC-16 | **Given** a pending plan, **when** the list changes, **then** the plan is replaced, the decisions are discarded and the page says so. |
| AC-17 | **Given** a deleted category, **when** the plan is built, **then** its mails are items with the model's proposed category; the Gmail label is not deleted (D18) and, when empty after the apply, is named in the result notice. |
| AC-18 | **Given** a ready plan, **then** the user gets one Telegram notice with numbers only (no sender, no subject). The notice for a change of the list is AC-31. |
| AC-19 | **Given** the items of a plan, **when** the plan is applied, **then** they are removed at once; **given** a plan that is not applied, **when** 14 days passed since the last decision or since it was replaced, **then** its items are removed (the apply audit and the rejection table stay, AC-47). |
| AC-20 | **Given** the api's database role, **when** it reads mail bodies, alert content or the token store, or writes to a plan item, a decision, an approval or an audit table directly, **then** PostgreSQL refuses (SQLSTATE 42501). |
| AC-21 | **Given** a sender or subject with markup or script, **when** it is shown, **then** it is rendered as text and the page's Content-Security-Policy blocks inline scripts. |
| AC-22 | **Given** a visitor who is not signed in, or a state-changing call without the CSRF token, **then** it is refused as for web settings (AC-2 and AC-8 of `web-settings`). |
| AC-23 | **Given** both pages and their states (loading, saving, save failed, validation error, empty plan, large plan, 403, session expired) at 320, 375, 768 and 1280 px and 200 % text size, **then** there is no horizontal scroll and axe finds no violation; the whole flow works with the keyboard. |
| AC-24 | **Given** a large plan (1 000 items), **then** the review page stays usable: groups can be collapsed and the list is shown in pages of 100 with "Load more" (no virtualised scrolling). |

Security acceptance criteria from the threat model (`docs/security/mail-categories-threat-model.md`, phase 2) are added to this table, to be approved with it:

| # | Criterion |
| --- | --- |
| AC-25 | **Given** a Gmail account without the label `Archive` (or where the user deleted it), **when** the agent starts a run, **then** the label exists afterwards, and it is created once, not twice, when runs overlap; **given** the label exists, **then** the agent changes nothing on it and never adds mail to it. (Numbered 25 for traceability; it belongs to R1.) |
| AC-26 | **Given** an approved item whose plan was built for an older list version, or whose proposed category is no longer in the list, **when** the agent applies, **then** the item is skipped and shown as skipped; nothing moves to a label that is not in the list. A plan that is already `scheduled` or `applying` when the list changes is finished first; only items whose proposed category was removed are skipped. Move back is the one exception: it restores old labels even when they are no longer in the list. |
| AC-27 | **Given** the api's database role, **when** it inserts, updates or deletes a plan item (including its decision), writes `plan_decision`, `plan_approval` or any audit table directly, or alters the schema, **then** PostgreSQL refuses (SQLSTATE 42501); **given** `record_decision` or `approve_plan` for a plan that is not `ready`, with a wrong item count, an id of another plan or mailbox, or more than 200 ids, **then** the function answers with a 409 error and changes nothing. |
| AC-28 | **Given** the Gmail wrapper used by plans, **then** its public operations are exactly list, read, add label, remove label, create label and rename label by id, and none for label delete, trash, delete message, spam or send (a reflection test against an allow-list fails when one is added); **given** a rename or label change for `Archive`, a label outside `Assistant/` or a system label, **then** it is refused. |
| AC-29 | **Given** a category name, description, sender or subject with Telegram markup or control characters, **when** it is in a notice, **then** it is sent as escaped plain text; a plan notice holds numbers only. |
| AC-30 | **Given** any request, error, log line, Sentry event or Telegram message, **then** sender and subject of plan items are in none of them, and plan responses carry `Cache-Control: no-store`. |
| AC-31 | **Given** a list change made in the web app, **when** the agent next runs, **then** one Telegram notice with old and new list and Undo is sent, also in quiet hours; Undo restores the previous list as a new version and discards a pending plan; an applied plan sends a result notice with counts. |
| AC-32 | **Given** the web lock is set, **when** a list or plan call arrives, **then** it is refused; **given** "approve all" with a plan id and item count that no longer match the plan, **then** it is refused with 409 and nothing is approved. |
| AC-33 | **Given** several list saves in a short time, **then** at most one plan build runs, it starts when the list has not changed for the debounce time (default 10 minutes, configuration, tested with a fake clock) and a newer list cancels a running build without half-written items; saves above the hourly limit of the account (default 10) get 429. |
| AC-34 | **Given** an approve call with more than the allowed number of ids, or a plan page request above the page size, **then** it is refused with a reason. |
| AC-35 | **Given** an approved item, **when** two apply runs start at once or one is repeated, **then** the mail moves once; **given** the mail gained `Archive`, left the inbox or changed its `Assistant/` label meanwhile, **then** the item is skipped. |
| AC-36 | **Given** a list change, a decision or an apply, **then** an append-only audit record exists with channel, a keyed digest of the actor and the time (apply: message ids and counts only). |
| AC-37 | **Given** two mailbox ids, **then** the repository layer never returns or changes rows of another mailbox (repository-level test in R1; the api-level test and row-level security come with the several-mailboxes feature). |
| AC-38 | **Given** any list, including a category "Other: everything", **when** an urgent mail arrives, **then** it raises the alert as before; **given** a model answer with an unknown category id and urgent, **then** the mail goes to "Other" and stays urgent (C-16). |
| AC-39 | **Given** the app's own sign-in code mail or a Google security mail (verified sender), **when** the agent files mail, **then** it stays in the inbox whatever the list and the model say; **given** a filing, **then** the list version used is recorded; **given** such mail in a plan scope, **then** it is never a plan item and never moved by an apply. "Verified sender" means Gmail's `Authentication-Results` shows DMARC pass for a From domain on a configured allow-list. |
| AC-40 | **Given** a change of only the name of a category, **when** the agent runs, **then** the Gmail label is renamed by id, no plan and no model call happen, and the category id and mail counts are unchanged; **given** a new name that equals an existing Gmail label, **then** the save is refused. |
| AC-41 | **Given** an applied plan, **when** the user presses "Move back" in Telegram or on the page, **then** the moved mails get their old label back using the apply audit (message id, old and new label), skipping mails changed meanwhile; **given** Undo of a list change after mails were filed under it, **then** the notice offers to move back the mails filed under that version. |
| AC-42 | **Given** an approval of more mails than the threshold (default 50), **when** it is made, **then** the apply waits the delay (default 15 minutes) and Telegram sends "N mails move at T" with Cancel and Lock web sign-in; Cancel stops the apply and nothing moves; the threshold counts all approvals of the mailbox over a rolling 24 hours, so approving 49 mails at a time still waits once the total passes it; threshold and delay can be changed only by deployment configuration, never from the web app; decisions are frozen from the moment of approval (plan state `scheduled`), and Cancel wins a race with the start of the apply (compare-and-set); **given** Cancel pressed after the delay has expired, **then** it is refused and the notice says so. |
| AC-43 | **Given** a plan being built, **when** the user opens "Review moves", **then** they see "n of about m checked, nothing moves yet" and, when the cap was reached, the number not looked at. |
| AC-44 | **Given** a sender display name or subject with bidi or other format characters, or a display name that imitates another sender, **then** the page shows the real address next to the name and the format characters are removed. |
| AC-45 | **Given** the first R2 plan has been applied, **then** the user confirms that the 36 first-run mails under "Other" and the mails flagged on 2026-11-08 are where they want them (D19, **type: user acceptance**, signed off in `docs/release/mail-categories-r2.md`, not an automated test). |
| AC-46 | **Given** two weeks after R1, **then** fewer than 5 % of new mails were re-filed by the user by hand and at most 15 % of new mail is under "Other" (D19, **type: user acceptance with data**, signed off in `docs/release/mail-categories-r1.md`; the numbers come from a daily report of the agent that compares the label recorded in its `filing` rows with the mail's current label, divided by the mails filed in the period; Gmail history is not used because it does not say who changed a label and is kept for only about a week; the report is built in R1 and tested on a fake Gmail). |
| AC-48 | **Given** a Telegram button (Undo, Cancel, Move back, Lock), **then** it is bound to the allowed chat id, to the plan or list version it belongs to and to a single-use nonce, expires, and a second or late press changes nothing and says so. |
| AC-49 | **Given** a first start after the migration, **then** the agent seeds list version 1 from its current labels (C-1), and until then the api answers "not ready" and the Categories page says so. |
| AC-50 | **Given** a list save while a plan is `scheduled` or `applying`, **then** that plan is finished first and a new build starts only after it is terminal; **given** a save while a plan is being built, **then** the build stops with no half-written items. |
| AC-51 | **Given** a Gmail change that succeeded and a database write that failed, **when** the run is repeated, **then** the item ends as applied and the mail is not moved twice (tested with a fake Gmail that injects the fault). |
| AC-52 | **Given** a mail with two or more `Assistant/` labels, **then** it is out of scope and counted as "unclear" in the plan numbers. |
| AC-53 | **Given** an older label under `Assistant/` that is not in the list, **then** the Categories page shows it as "Older category" with "Add to my list", and its mails are part of the first plan (C-1). |
| AC-56 | **Given** the database functions `record_decision`, `approve_plan` and `purge_expired`, **then** each is owned by a non-login role, has a fixed `search_path`, is revoked from `PUBLIC` and executable only by its role (the api for the first two, the agent for the last), builds no SQL from an argument, and reports errors without row values; **given** the agent calls `purge_expired` at any time or with any session setting, **then** rows younger than their retention survive, and a direct `DELETE` by the agent on an audit table is refused. |
| AC-57 | **Given** a plan that is `applying`, **when** web sign-in is locked or the plan is cancelled, **then** the agent stops before the next batch (checked by compare-and-set), the mails already moved stay moved and can be moved back; **given** a move-back request, **then** only an `applied` plan is processed once (unique per plan), `apply_audit` rows record the channel and one Telegram notice is sent. |
| AC-54 | **Given** the first start of R2 and no plan, **when** the agent runs, **then** it builds a plan against the current list, so that the first-run mails (D19) are reviewed even if the list was not changed after R2 shipped. |
| AC-55 | **Given** the save summary, the approve summary and "Move back", **then** a confirmation that only renames or moves labels uses a normal confirm button, and only "replaces the review and discards your decisions" and "Move back" use the red one; the cancel button comes first and has the focus, Escape cancels, and the focus trap covers every focusable element. |
| AC-47 | **Given** a rejected item, **when** its plan is 14 days old and the items are removed, **then** its message id is still in the rejection table and stays out of later plans until the list changes again. |

## Releases (decided, D12)

- **R1:** the list and the page "Categories" (AC-1 to AC-8, AC-22, AC-23 for that page): the agent follows the list for new mail. This already fixes the first-run problem for new mail.
- **R2:** re-sorting existing mail with the review page (the criteria are listed in the mapping below).
- The `Archive` label (C-14, AC-25) is created in R1 already, so the user can start filing mail there before the first plan is built.

Release mapping of the criteria (the round table asked for it):

| Release | Criteria |
| --- | --- |
| R1 | AC-1 to AC-8, AC-20 (the api role exists from R1), AC-22 and AC-23 (Categories page), AC-25, AC-28 (allow-list test, since R1 renames and creates labels), AC-29, AC-31 (list change part), AC-32 (lock part), AC-33 (rate limit part), AC-36 (list part), AC-37, AC-38, AC-39 (filing part), AC-40, AC-46, AC-48 (Undo), AC-49, AC-53, AC-55 (save summary), AC-56 (the `purge_expired` and the list-side hardening) |
| R2 | AC-9 to AC-19, AC-21, AC-22 and AC-23 (Review moves page and approve calls), AC-24, AC-26, AC-27, AC-30, AC-31 (result part), AC-32 (approve part), AC-33 (debounce part), AC-34, AC-35, AC-36 (decision and apply part), AC-39 (plan part), AC-41 to AC-45, AC-47, AC-48 (Cancel, Move back), AC-50 to AC-52, AC-54, AC-55 (approve and move-back summaries), AC-56 (decision and approval functions), AC-57 |

R1 gap, accepted as risk MR-4 in the threat model: in R1 an Undo restores the list but does not move back mail already filed under it (AC-41 arrives with R2).

Measurable bounds (set in phase 4 as configuration or test constants): AC-24 a page of 100 rows renders within 1 second and under 1 500 DOM nodes in the test environment; AC-23 is a Playwright run with the viewports and a 200 % zoom; AC-21 and AC-30 use canary strings as sender and subject, searched for in the logs, the access log, a Sentry stub and a Telegram stub.

## Open points for the user

None. The three points of the draft are answered in D11, D12 and D13. Open for phase 3 (design): the mailbox id on the new tables and the shared validation package (see Architecture fit).
