---
feature: mail-categories
intent: INT-004
status: draft
docs: docs/user-guide/mail-categories.md
date: 2026-11-14
approver: Marco
depends_on: mail-triage, web-settings
---

# Mail categories chosen by the owner

## Summary

Today the agent invents the category labels (`Assistant/<name>`) itself, up to a maximum of 15 (`MAX_CATEGORIES`, base spec C2). On the first real run 36 of 75 old mails ended under "Other" because the limit was reached. This feature turns the list around: Marco keeps a list of categories, each with a name and a description, in the web app. The agent files a mail only under a category of that list, or under "Other" when nothing fits. When Marco changes the list, the agent proposes how mail it filed earlier moves, Marco sees the proposal and approves it, and only then does anything move.

Why: the categories on the first run were not the ones Marco wants (INT-004).

It reverses decision D1 of `mail-triage` (the agent chooses categories), replaces C2 (maximum of 15) and the non-goal "No rules editor", and adds a second page to the web app.

## Who it is for

Marco, the single owner, with one mailbox and one agent. Several mailboxes and other Google accounts come later and are not built here (D7).

## Goals

1. Marco sees and edits his list of categories, each with a name and a description, in the web app.
2. A new mail is filed under a category of the list, or under "Other"; the agent never creates a category on its own.
3. After a change of the list, Marco sees which already filed mails would move and approves all of them at once, or each mail separately, before any mail moves.
4. The mails Marco did not like in the first run end up where he wants them.

## Non-goals

- Editing categories through Telegram (D1).
- More than one mailbox, more than one agent, another Google account or a Google sign-in (D7); the sign-in stays as in `web-settings` (ADR-0036, ADR-0037).
- Sorting mail in spam, trash or archive (D6).
- Rules by sender or keyword: the description is the only rule, and the model applies it.
- Deleting mail or sending mail (INT-001): the feature only changes labels.
- Showing mail bodies in the web app.

## Anti-goals (a failure even if it technically works)

- A mail moves that Marco did not approve, or a mail he rejected moves anyway.
- Text in a mail or in a description makes the agent file mail somewhere outside the list, move mail without approval, or show markup or script in the web app.
- The web app or its database role can read mail bodies, alert content or the Gmail token.
- A change of the list silently re-files the whole mailbox.

## Decisions made by Marco

| # | Decision | Source |
| --- | --- | --- |
| D1 | Categories are set only in the web app, not in Telegram. | INT-004, 2026-11-08 |
| D2 | A category has a name and a description; the description tells the model why a mail belongs there. | INT-004 |
| D3 | A mail that fits no category goes to "Other". | INT-004 |
| D4 | After a change of the list, the agent sorts the mail it already filed again. | INT-004 |
| D5 | Marco always sees what will move before it moves, and can approve all at once and mail by mail. | INT-004 |
| D6 | Sorting again covers all mail that is in the categories, but not mail in spam, trash and archive. | INT-004 |
| D7 | Now there is one mailbox; several agents and mailboxes may come later. The sign-in stays as it is. | Marco, 2026-11-14 |
| D8 | When a category is changed or deleted, the model decides where each of its mails goes. | INT-004 |
| D9 | The maximum of 15 categories is dropped. | Marco, 2026-11-14 |
| D10 | The overview shows sender and subject of each mail that would move, in the web app (approach A of the brainstorm); mail can be rejected one by one. | Marco, 2026-11-14 |

## My calls (Marco may change these)

- C-1: The list starts with the categories the agent has today (the seven starter categories and the labels already created under `Assistant/`), so nothing changes until Marco edits the list. A label under `Assistant/` that is not on the list is a legacy label: its mails are part of the first plan.
- C-2: "Other" always exists, cannot be renamed or deleted, and has no description Marco has to write. Its label is the existing `Assistant/Other`.
- C-3: Limits, set by configuration: 1 to 40 characters for a name (no `/`, because Gmail nests labels on it), unique without regard to letter case; 1 to 500 characters for a description; at most 50 categories as a safety cap against runaway model cost and prompt size. The name pattern is the one `judgement.py` uses today, to be confirmed in phase 3.
- C-4: Descriptions are untrusted text for the model: they are given to the model as data in a fixed place of the prompt, with the same limits and escaping as mail text, and the model may only answer with a category id from the list (a closed set); anything else is filed under "Other". They are shown in the web app as text.
- C-5: "In the categories" (D6) means: the mail carries an `Assistant/` label, is not in spam or trash, and is not archived by Marco. Archived by Marco means: not in the inbox and without an `Assistant/` label. A mail the agent filed (moved out of the inbox under a label) is therefore in scope, and so is a mail Marco read and left in the inbox with an `Assistant/` label.
- C-6: Plan, not move. A change of the list creates a re-sort plan. The agent judges each mail in scope again with the model, within the daily budget above the reserve of ADR-0021, over as many days as needed, and writes a plan item only for mails whose category would change. Mails that stay are not listed.
- C-7: A plan item holds the Gmail message id, sender, subject (cut to 120 characters), old category, proposed category and a decision (pending, approved, rejected). Nothing else from the mail. Plans are removed 14 days after the last decision or when replaced; items of an applied plan are removed at once.
- C-8: Review screen: items are grouped by "from category, to category", with counts, a select-all per group and for the whole plan, and a checkbox per mail. Marco can approve the selected mails or approve all. A mail he does not approve stays where it is, and stays out of later plans until the list changes again.
- C-9: Applying: the agent, not the api, moves mail. Before moving it checks the mail is still in scope and still carries the old label; a mail that Marco moved in Gmail meanwhile is skipped and shown as skipped. The move removes the old `Assistant/` label and adds the new one; it deletes nothing.
- C-10: When Marco edits the list while a plan is pending, the pending plan is replaced by a new one (decisions already given are discarded and the page says so). A deleted category's mails are part of the new plan; the label itself is removed in Gmail only after the plan is applied and the label is empty.
- C-11: A change of the list is announced in Telegram with old and new list and an Undo button, like web settings changes (ADR-0033); a ready plan is announced with its numbers only, no mail content.
- C-12: Words: "Categories", "Description", "Other", "Review moves". The page says that the description is read by the model.

## Behaviour

1. Marco opens "Categories" in the web app and sees the list with name, description and the number of mails per category.
2. He adds, edits or deletes a category and saves. The list is stored as a whole with a version (as web settings).
3. New mail is judged against the list from then on; the result is a category of the list, or "Other".
4. The agent builds a re-sort plan from the mails in scope, and tells Marco in Telegram that a plan is ready.
5. Marco opens "Review moves", sees the groups, un-ticks the mails that should stay, and approves.
6. The agent moves the approved mails and reports the result (moved, skipped, failed).

## Architecture fit

- `mail-triage`: judging against the list (closed set), building and applying plans, Telegram notices. It stays the only component with Gmail access.
- `api`: CRUD of the list with versions, reading the plan, recording approve and reject. It does not move mail.
- `web`: the "Categories" page and the "Review moves" page.
- Shared rules: validation of the list (names, lengths, "Other") belongs in a shared Python package used by agent and api, like `schedule-policy`; whether that is a new package or an extension is decided in phase 3.
- Data: a new schema for the list and the plan, migrated by the agent's chain (ADR-0025). The api role gets rights on the list and on the plan items only (select, and update of the decision); it still has no right on `public`. This narrows ADR-0025 ("no access to mail content") to "no access to mail bodies and tokens", and extends ADR-0018 for sender and subject in the web app. Both need an ADR in phase 3.
- Open for phase 3 (decision-gate): whether the new tables carry a mailbox id now, for the later several mailboxes (drift item 1 of the architecture baseline); the same answer serves INT-006 (drift item 2).

## Acceptance criteria

| # | Criterion |
| --- | --- |
| AC-1 | **Given** a signed-in Marco, **when** he opens "Categories", **then** he sees his list with name, description and number of mails, and "Other". |
| AC-2 | **Given** a valid name and description, **when** he saves, **then** the list is stored whole with a new version and an audit record, and the agent uses it from its next run; **given** a name that is empty, too long, duplicated (any letter case), contains `/`, or a description over the limit, **then** the field shows the reason and nothing is stored. |
| AC-3 | **Given** the page loaded at version 1 and the list changed elsewhere, **when** Marco saves, **then** the save is refused with 409 and the page shows the new list. |
| AC-4 | **Given** "Other", **when** Marco tries to rename or delete it, **then** it is refused. |
| AC-5 | **Given** a new mail, **when** the agent judges it, **then** it carries exactly one label of the list or `Assistant/Other`, and the agent never creates another `Assistant/` label. |
| AC-6 | **Given** a model answer that is not an id of the list (an invented name, markup, a second category), **when** it is processed, **then** the mail goes to "Other". |
| AC-7 | **Given** a description or mail text with instructions (to move mail, to approve, to reveal other mail), **when** it is processed, **then** filing, plans, approvals and sending are unaffected. |
| AC-8 | **Given** more than 15 categories in the list, **when** mail is judged, **then** all of them can be used; **given** the safety cap, **when** Marco adds one more, **then** it is refused with the reason. |
| AC-9 | **Given** a changed list, **when** the agent runs, **then** it creates a plan with items only for mails whose category would change, and moves nothing. |
| AC-10 | **Given** mail in spam, in trash, or archived by Marco (no inbox, no `Assistant/` label), **when** a plan is built, **then** none of it is an item. |
| AC-11 | **Given** a plan, **when** the budget above the reserve is used up, **then** the plan is completed on later days, and new mail keeps its guaranteed share (ADR-0021). |
| AC-12 | **Given** a plan, **when** Marco opens "Review moves", **then** he sees groups "from, to" with counts, and per mail the sender and subject as plain text. |
| AC-13 | **Given** the review page, **when** Marco approves all, **or** approves selected mails and leaves others, **then** exactly the approved items are moved and the others stay and stay out of later plans until the list changes again. |
| AC-14 | **Given** an approved item, **when** the agent applies it, **then** it moves the mail by removing the old `Assistant/` label and adding the new one, and it deletes and sends nothing. |
| AC-15 | **Given** an approved item whose mail was moved or deleted in Gmail meanwhile, **when** the agent applies it, **then** the item is skipped and shown as skipped. |
| AC-16 | **Given** a pending plan, **when** the list changes, **then** the plan is replaced, the decisions are discarded and the page says so. |
| AC-17 | **Given** a deleted category, **when** the plan is built, **then** its mails are items with the model's proposed category, and the label is removed from Gmail only when it is empty after the plan is applied. |
| AC-18 | **Given** a change of the list or a ready plan, **then** Marco gets one Telegram notice (list change: old and new list with Undo; plan: numbers only, no sender, no subject). |
| AC-19 | **Given** plan items, **when** 14 days passed since the last decision or the plan was applied or replaced, **then** the items are removed. |
| AC-20 | **Given** the api's database role, **when** it reads mail bodies, alert content or the token store, or writes anything to a plan item except the decision, **then** PostgreSQL refuses (SQLSTATE 42501). |
| AC-21 | **Given** a sender or subject with markup or script, **when** it is shown, **then** it is rendered as text and the page's Content-Security-Policy blocks inline scripts. |
| AC-22 | **Given** a visitor who is not signed in, or a state-changing call without the CSRF token, **then** it is refused as for web settings (AC-2 and AC-8 of `web-settings`). |
| AC-23 | **Given** both pages and their states (loading, saving, save failed, validation error, empty plan, large plan, 403, session expired) at 320, 375, 768 and 1280 px and 200 % text size, **then** there is no horizontal scroll and axe finds no violation; the whole flow works with the keyboard. |
| AC-24 | **Given** a large plan (1 000 items), **then** the review page stays usable: groups can be collapsed and the list is paged or virtualised. |

Security acceptance criteria from the threat model (phase 2) are added to this table.

## Releases (my proposal)

- **R1:** the list and the page "Categories" (AC-1 to AC-8, AC-22, AC-23 for that page): the agent follows the list for new mail. This already fixes the first-run problem for new mail.
- **R2:** re-sorting existing mail with the review page (AC-9 to AC-21, AC-23 and AC-24 for that page).

## Open points for Marco

- Is "archived" as defined in C-5 what you mean: not in the inbox and without an `Assistant/` label?
- One feature in two releases (R1 and R2 above), or two separate features?
- The sign-in code mail, the plan notice and the page now show more of your mail. Is it acceptable that anyone who can read your mailbox and sign in to the web app also sees sender and subject of the plan? (The threat model of phase 2 re-reviews risk R-1.)
