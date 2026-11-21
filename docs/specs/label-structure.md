---
feature: label-structure
intent: INT-008
status: draft
docs: docs/user-guide/label-structure.md
date: 2026-11-21
approver: the user
depends_on: mail-categories, mail-triage, web-settings
---

# My own label structure, sender rules and always-notify

## Summary

The user researched their mailbox and wrote a structure of about 43 labels with instructions for the model (nested names such as `Huis/Energie`, an extra label `Facturen`, sender lists, notes, general working rules). The categories of INT-004 cannot hold it: names may not nest, a mail gets exactly one label, a description is limited to 500 characters and the list has no general instructions. This feature rebuilds the category contract so that the structure fits, and adds four things the user asked for:

1. **Sender rules.** A category may list senders. A mail from a listed (and authenticated) sender is filed there directly, **without a model call**.
2. **Always notify.** Every category has a tick; a new mail filed in a ticked category gives a Telegram alert, on top of the urgency alerts that exist today, and never two alerts for one mail.
3. **Upload and export.** The list can be loaded from a YAML file at any time, and exported in the same format.
4. **Control of old mail.** A change of the list affects new mail only. Old mail is re-sorted only when the user presses "Sort everything again" and picks a confidence threshold: mail the model is sure about moves without a review, the rest is reviewed, with a tip per category on how to reach the threshold. The name of the archive label is set on the Categories page, not in the environment.

Why: the user cannot express their own label structure today, hears only about mail the model judges urgent, and cannot change the archive label without changing the environment (INT-008).

It reverses parts of `mail-categories` (INT-004): C-3 (no `/` in names, 500 characters, 50 categories), the single label per mail, D4 (the automatic re-sort after a list change; AC-33 debounce and AC-54 first-start plan) and ADR-0052 (archive label as an agent setting). INT-004 stays as it is; this is a new spec (`rebuild-not-patch`).

## Who it is for

The user, with one mailbox and one agent. Several mailboxes and other Google accounts stay out of scope (D7 of `mail-categories`).

## Goals

1. The user loads their structure from a YAML file, previews it and saves it; the Categories page shows nested categories with description, senders, kind and the always-notify tick.
2. A new mail from a named, authenticated sender is filed under that sender's category without a model call.
3. A new mail in a ticked category gives one Telegram alert, also when it is not urgent.
4. A list change does not move old mail; "Sort everything again" asks for a confidence threshold, moves what is at or above it without a review (with a notice and Move back) and puts the rest in Review moves, with a tip per category.
5. The user sets the archive label name on the Categories page.

## Non-goals

- Sender conditions on subject or body (for example "Odido only when the subject says *thuis*"): those stay in the description for the model.
- A rules editor for senders beyond the list per category; no wildcard other than the domain rule (D6).
- New Telegram actions; an always-notify alert has the three existing actions.
- Deleting mail, sending mail or deleting Gmail labels (INT-001, D18 of `mail-categories`).
- Several mailboxes, another sign-in (D7 of `mail-categories`).
- Importing the user's Markdown document directly; the first YAML file is converted from it once, as part of the build (D13).

## Anti-goals (a failure even if it technically works)

- Two alerts for one mail, or an alert for a mail that only moved during a re-sort or the backlog.
- A forged `From` address files a mail under a sender rule or triggers an always-notify alert as if it came from the real sender.
- Old mail moves without the user pressing the button, or mail below the user's threshold moves without the user approving it.
- A model answer that claims a high confidence (for example because mail text told it to) moves mail that the threshold was meant to keep for review.
- An uploaded file (or a description or the general instructions) makes the agent file mail outside the list, change code paths, or show markup or script in the web app.
- A change of the archive label name makes archived mail part of a re-sort.

## Decisions made by the user

| # | Decision | Source |
| --- | --- | --- |
| D1 | New intent INT-008 and a new spec, not an extension of INT-004. | Brainstorm 2026-11-21 |
| D2 | Nested names are allowed (`Huis/Energie` becomes the label `Assistant/Huis/Energie`). The INT-004 rule against `/` was wrong. | User |
| D3 | A mail gets one topic label and at most one extra label (such as `Facturen`). | User's document ("maximaal twee labels") |
| D4 | A category may list senders; a matched sender files the mail directly and skips the model completely. A category's sender list may be empty. | User (approach B, variant 2) |
| D5 | Every category has a tick "always notify". It is independent of the urgency alerts, which stay as they are. One alert per mail. | User |
| D6 | The categories can always be loaded from a YAML file; an upload replaces the whole list after a preview; the app exports the current list in the same format. | User |
| D7 | The archive label name is set in the app. | User |
| D8 | Old mail is re-sorted only when the user presses "Sort everything again"; a list change otherwise affects new mail only. After the switch the user presses the button themselves. | User |
| D9 | "Sort everything again" does not require a review of everything. The user sets a confidence threshold (a percentage) **each time** they press the button. Items the model is at least that sure about (and all sender-rule items) move without a review; items below it go to "Review moves", with a tip per category on what to change so the threshold is reached. This relaxes D5 of INT-004 for the sure items only. | User, 2026-11-21 |
| D10 | A category without a tick does not notify by itself, but a mail the model judges to need the user's attention (a document, a mail that expects an action) still alerts, as today. | User, 2026-11-21 |

## Constraints

- C-1 **Names.** The INT-004 name rules apply **per segment** (length 1 to 40 code points, trimmed, NFKC and case folding for duplicates, no control or format characters, reserved names "Other" and "Archive"); empty segments and a leading or trailing `/` are refused; the whole Gmail label (`Assistant/` plus the name) is at most 225 characters. A parent (`Huis`) is a grouping only: mail is filed under the full name and the parent need not be a category. `Huis` and `Huis/Energie` may both exist as categories; only a duplicate whole name is refused. *Claude's call.*
- C-2 **Kinds.** A category is a **topic** (a mail has exactly one topic, or "Other") or an **extra label** (added next to the topic when the model finds it applies). "Other" is the built-in topic; the user's "Te beoordelen" is a normal topic or is mapped to "Other" in the converted file. At most one topic and one extra label per mail. *Claude's call.*
- C-3 **Descriptions and instructions.** A description has 1 to 1 500 characters; the general instructions have 0 to 4 000 characters; both are untrusted text for the model, given as data in fixed places of the prompt with the same limits and escaping as mail text (C-4 of `mail-categories`). The urgency rules stay fixed in the agent (C-16 of `mail-categories`). *Claude's call.*
- C-4 **Senders.** A sender entry is a full address (`info@julianahoeve.nl`) or a domain (`julianahoeve.nl`, matching that domain and its subdomains); entries are lower-cased and checked for syntax; at most 100 per category; an entry may appear in at most one topic category and at most one extra label category, otherwise the save is refused with the reason. When two entries match, the longest (most specific) wins. *Claude's call.*
- C-5 **Authenticated sender only.** A sender rule acts only when Gmail's own `Authentication-Results` header (the one added by Gmail's server, not one in the message body or an earlier hop) says the message passed DMARC, or SPF or DKIM aligned with the `From` domain, for the matched domain. A mail that does not pass is **not** matched; it goes to the model like any other. Security mail and the app's own sign-in code mail stay pinned (C-16 of `mail-categories`) and never match a sender rule.
- C-6 **Categories cap.** The safety cap becomes 100 categories (it was 50; the user's list has 43 and will grow). *Claude's call.*
- C-7 **Upload.** YAML only, parsed with a safe loader (no object construction, no merge keys or anchors that expand, no duplicate keys), at most 256 KiB, validated against a schema and against the same rules as a save (C-1 to C-4, C-6); an invalid file shows every problem and stores nothing. The upload fills a preview; nothing is saved until the user confirms; a confirmed upload is one list version with an audit record, like any save. Names match existing categories by name (NFKC, case folding) so ids stay stable; a name that is not in the file means the category is deleted (the INT-004 delete path, D14 and D18 apply). The file carries no ids.
- C-8 **Export.** The export has the same fields as the upload so that export, edit and upload round-trips without change.
- C-9 **Always notify and the alert.** An alert is created for a new mail when it is urgent (as today) **or** any category it is filed under (topic or extra label) is ticked. The reason line names the cause ("Category Facturen is set to always notify"); when the model was skipped there is no summary line. Quiet hours (held and sent together), the hourly cap and batching (AC-26 of `mail-categories`) and the daily overview apply as today; one mail is one alert. A mail moved during "Sort everything again" or handled by the INT-003 backlog never creates an always-notify alert. *Claude's call.*
- C-10 **Sender-rule filing.** The filing record says "sender rule" and names the matched entry instead of a model judgement; the Undo and Move-back paths and the AC-46 report keep working on it. Whether a sender-rule mail in an **unticked** category still gets an urgency check is open point 1 (D10 says urgent mail must still alert); in a **ticked** category it alerts anyway.
- C-11 **Archive label setting.** The name is part of the list (versioned, audited) with the INT-004 validation (C-14 of `mail-categories`). When the name changes and the old label exists, the agent **renames that label by id** (as for a category rename, D14), so mail in it stays protected; it never creates a second archive label and never moves mail into or out of it. A new name that equals an existing Gmail label is refused. The setting `ARCHIVE_LABEL` of the agent is removed (ADR-0052 superseded). *Claude's call.*
- C-12 **Sort everything again.** The button asks for a **confidence threshold**, a whole percentage from 50 to 100 that the user types by hand in a field on the Categories page, next to the button, like the other settings of the web app (quiet hours in `adjustable-quiet-hours`). The field starts at **50** (decided by the user, 2026-11-21) and afterwards shows the value used last, which the user can change before each press; the value is kept with the other web settings (ADR-0023), so it survives a reload. *Claude's call on the range, so that nothing the model is less than half sure about moves unreviewed.* It then builds a plan as INT-004 R2 does (scope of C-5 of `mail-categories`, budget share, cap of 5 000), with one change: each item carries the model's confidence (0 to 100 %; 100 for a sender rule). Items **at or above** the threshold are approved by the system and applied with the delayed apply of D16 of `mail-categories` (a Telegram notice with Cancel, "Move back" and "Lock web sign-in"); items **below** it stay pending in Review moves for the user to decide, as in INT-004. A mail whose target equals its current category is no item. The model's confidence is its own report and not a calibrated probability; the page says so, and Move back stays available for every applied item. Sender rules apply in the plan, so a sender-rule category can be the target of an item without a model call. There is no automatic plan after a list save and none on first start. One non-terminal plan per mailbox; the button is disabled while one exists, with the reason shown. The nesting is shown in Review moves by the full name.
- C-15 **Tips.** For every category that has items below the threshold, Review moves shows one short tip: what to change in that category so the threshold would be reached (for example "add the senders `x.nl` and `y.nl`", "the description does not say how this differs from `Huis/Onderhoud`"). The tip is built by the model from the category, its description and the low-confidence items' sender and subject (never the body), one call per category within the budget share, capped in length, shown as plain text and never applied automatically; the user changes the category themselves, and may press the button again with a new threshold or after a change. Tips are untrusted model output (same limits and escaping as mail text, C-3). *Claude's call.*
- C-13 **Gmail nested labels.** A label `Assistant/Huis/Energie` is created without requiring `Assistant/Huis` to exist; whether Gmail shows the parent is cosmetic. To confirm in phase 3 with the real API (the guardrail-gmail rules apply).
- C-14 **Contract.** The list, the kinds, the senders, the ticks, the general instructions and the archive label name are a new version of the category contract (`category-policy`, ADR-0042). The old list is migrated as a version 2 of the same list: every existing category becomes a topic with no senders and no tick. Both the agent and the api read it through the shared package.

## Behaviour

### Filing a new mail

1. Security mail and the app's own sign-in code mail stay in the inbox (unchanged).
2. **Sender rule (C-5, C-4).** If the sender is authenticated and matches an entry, the mail is filed under the topic (and extra label) that list it; the model is not called.
3. Otherwise the mail goes to the model with the general instructions and the list (closed set). The model answers one topic id (or Other), at most one extra label id, urgency, reason, summary and confidence. An id outside the list files the mail under "Other" and drops the extra label; urgency is kept (ADR-0045).
4. **Alert (C-9).** One alert when the mail is urgent or a category it is filed under is ticked.

### Changing the list

- By hand in the web app, or by upload (C-7): both create a new list version, with the audit record and the Telegram change notice of `web-settings` (ADR-0033). New mail follows the new list from the next run. Old mail does not move (D8).
- Labels of deleted categories stay in Gmail (D18 of `mail-categories`); a rename of a category renames the Gmail label by id (D14 of `mail-categories`).

### Sorting again

The Categories page has "Sort everything again" with a field for the threshold. It starts the plan (C-12). The sure items move after the delayed apply; Telegram says a plan is ready, with the number of items that move on their own and the number that wait for review (numbers only, as AC-18 of `mail-categories`). The user decides the rest in Review moves, where each category with items below the threshold shows its tip.

## Architecture fit

- `category-policy` (shared package): name rules per segment, kinds, sender entry rules and matching, limits, the YAML schema of the upload and export (parsing itself in the api), the archive label name rule, and the contract cases. New version of the contract.
- `mail-triage`: sender-rule filing (reads the authenticated result from Gmail), the changed judging (kinds, general instructions), the always-notify alert, the removal of the automatic plan, the archive label rename, the plan build for the button. It stays the only component with Gmail access.
- `api`: list v2 (CRUD, versions, audit), upload parsing and preview, export, the archive label name, the "Sort everything again" request (a request row the agent picks up, as for decisions; no call from api to agent, ADR-0041).
- `web`: the Categories page (nesting, kind, senders, tick, general instructions, upload and export, archive label, button) and the Review moves page (full names).
- Data: a migration of the agent's chain (ADR-0025): kind, senders, tick, general instructions, archive label name, the sort-again request. The api role gets the same narrow rights as for the list today.
- New or changed ADRs for phase 3 (proposed): category contract v2 (supersedes the C-3 part of ADR-0042); sender rules and authenticated sender (new, security); always-notify alert and its place in the alert flow (new, extends ADR-0048); archive label name in the list (supersedes ADR-0052); manual re-sort only (changes ADR-0046); YAML upload as an input boundary (new, security).
- No new component and no new external system. Gmail's `Authentication-Results` header is read from the existing Gmail adapter.

## Acceptance criteria

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-1 | **Given** a category named `Huis/Energie`, **when** the user saves, **then** it is stored and the Gmail label is `Assistant/Huis/Energie`; **given** an empty segment, a leading or trailing `/`, a segment over 40 characters, a label over 225 characters, a control or format character, or a reserved name as a whole name, **then** the field shows the reason and nothing is stored. (Table test, one row per rule.) | What I want (nested), D2 |
| AC-2 | **Given** a category of kind "extra label", **when** a mail is judged and the model names a topic and that extra label, **then** the mail carries both labels; **given** a model answer with two extra labels or an unknown id, **then** at most one extra label is kept, an unknown topic id files under "Other" and urgency is kept. | What I want (extra label), D3 |
| AC-3 | **Given** a category with a description of 1 500 characters and general instructions of 4 000, **when** the user saves, **then** both are stored; **given** one character more, **then** the field shows the reason. **Given** a description or instructions with text that tells the model to do something, **then** it is sent only as data in its fixed place and the answer stays a category id from the list. | What I want (long descriptions) |
| AC-4 | **Given** a category with a sender entry and an authenticated mail from it, **when** the mail is processed, **then** it is filed there and the model is not called (asserted on the fake model: zero calls). | What I want (sender rules), D4 |
| AC-5 | **Given** a category with an empty sender list, **when** a mail arrives, **then** the model judges it as before. | D4 |
| AC-6 | **Given** an address entry and a domain entry that both match, **then** the longest entry wins; **given** a subdomain of a domain entry, **then** it matches; **given** the same entry in two topic categories or two extra-label categories, **when** the user saves or uploads, **then** the save is refused naming both categories. | D4, C-4 |
| AC-7 | **Given** a mail whose `From` matches a sender entry but whose Gmail authentication result is missing, failed, or for another domain, **or** whose result header sits in the body or in a header not added by Gmail's server, **when** it is processed, **then** no sender rule applies and the model judges it; no alert is raised because of the rule. | Must not do (forged sender), C-5 |
| AC-8 | **Given** the app's own sign-in code mail or Google security mail from a listed sender, **then** the pinned handling of ADR-0048 applies and no sender rule files it. | C-5 |
| AC-9 | **Given** a mail filed by a sender rule, **then** its filing record says "sender rule" with the matched entry; **given** an Undo or Move back, **then** it works as for a model-filed mail; **given** the AC-46 report, **then** the mail is counted. | C-10 |
| AC-10 | **Given** a ticked category and a new, non-urgent mail filed in it (by the model or by a sender rule), **when** it is processed, **then** the user gets one Telegram alert with sender, subject, the three actions and the reason "Category X is set to always notify"; **given** a mail filed by a sender rule, **then** the alert has no summary line. | What I want (always notify), D5 |
| AC-11 | **Given** a mail that is urgent and in a ticked category, **or** in two ticked categories (topic and extra label), **then** exactly one alert is created and its reason names every cause. | Must not do (two notifications) |
| AC-12 | **Given** a ticked category and a mail processed in quiet hours, **then** the alert is held and sent with the others when the hours end; **given** the hourly cap is reached, **then** alerts are batched as in AC-26 of `mail-categories`. | D5, C-9 |
| AC-13 | **Given** a ticked category, **when** a mail moves because of "Sort everything again", **or** is handled by the backlog catch-up, **then** no always-notify alert is created. | C-9 |
| AC-14 | **Given** an unticked category and a non-urgent mail, **then** no alert; **given** a mail the model judges urgent (a document or a mail that expects an action from the user, D7 of `mail-triage`) in an unticked category, **then** the urgency alert is raised exactly as today. | What I want (stays as is), D10 |
| AC-15 | **Given** a valid YAML file, **when** the user uploads it, **then** a preview shows what will be added, changed and removed (names, kinds, senders, ticks) and nothing is stored; **when** the user confirms, **then** the whole list is replaced as one new version with an audit record and the change notice; **when** the user cancels, **then** nothing changes. | What I want (upload), D6 |
| AC-16 | **Given** a file that is not YAML, is over 256 KiB, has duplicate keys, anchors or merge keys that expand, object tags, unknown fields, or any list or limit violation, **when** it is uploaded, **then** every problem is shown with its place in the file and nothing is stored, and no code from the file is executed. | Must not do, C-7 |
| AC-17 | **Given** an upload where a name equals an existing category (NFKC, case folding), **then** that category keeps its id and its mail; **given** a name that is not in the file, **then** its category is deleted by the INT-004 path (label stays, its mail is part of the next plan only after the user presses the button). | C-7 |
| AC-18 | **Given** the current list, **when** the user exports it and uploads the file unchanged, **then** the preview shows no change and a confirm makes no new version. | C-8 |
| AC-19 | **Given** the user's converted file (43 labels), **when** it is uploaded, **then** it passes validation and the list matches the document (names, kinds, descriptions, senders, general instructions). | How I will know it works |
| AC-20 | **Given** a list change (by hand or upload), **when** the debounce time has passed, **then** no plan is built and no mail moves; **given** a first start with no plan, **then** no plan is built. | What I want (button only), D8 |
| AC-21 | **Given** the user presses "Sort everything again" with a threshold, **then** a plan is built over the mail in scope (inbox and `Assistant/` labels, not spam, trash or the archive label); **given** a plan already open, **then** the button is disabled with the reason; **given** a threshold outside 50 to 100 or not a whole number, **then** the field shows the reason and no plan starts; **given** the first visit, **then** the field shows 50, and **given** a later visit, **then** it shows the value used last; the field is labelled, keyboard-operable and says what the threshold does. | D8, D9, C-12 |
| AC-22 | **Given** a plan, **then** items whose target is reached by a sender rule are decided without a model call (confidence 100), the others by the model, within the budget share (ADR-0021); Review moves shows full nested names. | C-12 |
| AC-32 | **Given** a plan with items of confidence 95, 80 and 79 and a threshold of 80, **when** the plan is built, **then** the first two are approved by the system and the third stays pending; **given** the same plan with a threshold of 96, **then** none of the model items is approved by the system and only sender-rule items are; the boundary is "at or above". (Table test with a fake model.) | D9 |
| AC-33 | **Given** the items approved by the system, **then** they are applied only after the delayed apply, Telegram names the numbers (moved on their own, waiting for review) and offers Cancel, "Move back" and "Lock web sign-in"; **given** a Cancel before the apply, **then** nothing of them moves; **given** the item's mail was moved by the user meanwhile, **then** it is skipped and shown as skipped (C-9 of `mail-categories`). | D9 |
| AC-34 | **Given** items below the threshold, **then** none of them moves before the user approves it in Review moves (all at once or mail by mail, as in INT-004); **given** the user presses the button again with a lower threshold, **then** a new plan is built and the earlier undecided items are replaced. | D9, anti-goal |
| AC-35 | **Given** a category with items below the threshold, **when** the user opens Review moves, **then** that category shows one tip in plain text that names what to change (for example senders to add or a sentence in the description); **given** a category with no items below the threshold, **then** no tip and no model call for it; **given** a tip, **then** nothing in the list changes until the user edits it. | D9, C-15 |
| AC-36 | **Given** a mail whose text tells the model to answer with confidence 100, **when** the plan is built, **then** the item is still approved only by the rule "confidence at or above the threshold" and the text cannot change the threshold, the target category or the apply mode; the mail only ever moves between categories of the list and Move back restores it. | Anti-goal |
| AC-23 | **Given** the archive label name field, **when** the user saves a valid new name and the old label exists, **then** the agent renames the Gmail label by id and mail in it stays protected; **given** a name that equals an existing Gmail label, an `Assistant/` category label or a reserved name, **then** the field shows the reason; **given** the environment variable `ARCHIVE_LABEL`, **then** the agent ignores it. | What I want (archive label), D7, C-11 |
| AC-24 | **Given** a rename of the archive label while a plan is `scheduled` or `applying`, **then** the rename waits until the plan is terminal. | C-11, C-12 |
| AC-25 | **Given** the Categories page, **then** nesting is shown (indented by path), the kind, the senders (with a count) and the tick are visible and operable by keyboard with labels, in three viewports and at 200 % zoom (axe, Playwright); the upload and export controls say what an upload does ("replaces the whole list after a preview"). | a11y guardrail |
| AC-26 | **Given** the shared package, **then** a contract file of cases (names, senders, kinds, limits, archive label, upload schema) is passed by both the agent and the api. | C-14 |
| AC-27 | **Given** the existing list of INT-004, **when** the migration runs, **then** every category becomes a topic with no senders and no tick and ids and labels are unchanged; running it twice changes nothing. | C-14 |

### Security acceptance criteria (to be extended by the threat model, `docs/security/label-structure-threat-model.md`)

| # | Criterion | Threat |
| --- | --- | --- |
| AC-28 | **Given** any mail, header or sender text, **when** a sender rule, alert or filing is decided, **then** the decision uses only the authenticated sender from Gmail's header (AC-7) and never text from the body, the subject or `Reply-To`. | Spoofed sender |
| AC-29 | **Given** an upload, **then** the loader is the safe loader, size and depth are limited before parsing, and the api role has no right beyond what a normal save has (SQLSTATE 42501 otherwise). | Malicious file |
| AC-30 | **Given** uploaded or typed text with canary strings in descriptions, senders or instructions, **then** the canaries are not found in logs, the access log, a Sentry stub or a Telegram stub, and in the web app they are shown as text. | Leak, XSS |
| AC-31 | **Given** the upload endpoint, **then** it needs the signed-in user, has an hourly limit like the list save (AC-33 of `mail-categories`) and returns 429 above it. | Abuse |

## Releases (proposed; the user decides in phase 2)

- **R1:** the contract v2 (nesting, kinds, senders, ticks, general instructions, limits), judging and sender-rule filing, the always-notify alert, the Categories page changes, upload and export, and the migration (AC-1 to AC-19, AC-25 to AC-31).
- **R2:** the archive label setting, the removal of the automatic plan, the "Sort everything again" button with the threshold, the system-approved items and the tips (AC-20 to AC-24, AC-32 to AC-36).

## Open points for the user

1. **Urgency for sender-rule mail (needs your decision).** D4 says a matched sender skips the model completely, and D10 says an unticked category must still alert for a document or a mail that expects an action. Both cannot hold for a sender-rule mail in an unticked category: with no model call, nothing judges urgency. *Claude's proposal:* the model is skipped for **choosing the category** only; for a sender-rule mail in an **unticked** category the agent makes one small call that answers only "does this need the user's attention" (no category, no summary list), and for a **ticked** category it makes no call at all because the alert comes anyway. This costs one small call per sender-rule mail in unticked categories and nothing else.
2. Always-notify alerts only for **new** mail (C-9, AC-13), not for mail moved by "Sort everything again" or the backlog. Agreed by the user.
3. The threshold is typed by hand in the web UI and starts at 50 (decided by the user). The range of 50 to 100 and that mail below the threshold waits in Review moves are *Claude's call; confirm or change.*
4. The releases R1 and R2. Agreed by the user.
