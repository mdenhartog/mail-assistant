---
feature: label-structure
intent: INT-008
status: draft
revision: 2 (after the phase 2 round table, 2026-11-21)
docs: docs/user-guide/label-structure.md
date: 2026-11-21
approver: the user
depends_on: mail-categories, mail-triage, web-settings
---

# My own label structure, sender rules and always-notify

## Summary

The user researched their mailbox and wrote a structure of about 43 labels with instructions for the model (nested names such as `Huis/Energie`, an extra label `Facturen`, sender lists, notes, general working rules). The categories of INT-004 cannot hold it: names may not nest, a mail gets exactly one label, a description is limited to 500 characters and the list has no general instructions. This feature rebuilds the category contract so that the structure fits, and adds what the user asked for:

1. **Sender rules.** A category may list senders. A mail from a listed sender that Gmail has authenticated is filed there directly, **without the model choosing the category**.
2. **Always notify.** Every category has a tick; a new mail filed in a ticked category gives a Telegram alert, on top of the urgency alerts that exist today, and never two alerts for one mail.
3. **Upload, export and a template.** The list is loaded from a YAML file at any time, exported in the same format, and a commented template file shows the format.
4. **Control of old mail.** A change of the list affects new mail only. Old mail is re-sorted only when the user presses "Sort everything again" and types a confidence threshold: mail the model is sure about moves without a review, the rest is reviewed, with a tip per category on how to reach the threshold.
5. **The archive label name** is set on the Categories page, not in the environment.

Why: the user cannot express their own label structure today, hears only about mail the model judges urgent, and cannot change the archive label without changing the environment (INT-008).

It reverses parts of `mail-categories` (INT-004): C-3 (no `/` in names, 500 characters, 50 categories), the single label per mail, D4 (the automatic re-sort after a list change; AC-33 debounce and AC-54 first-start plan) and ADR-0052 (archive label as an agent setting). INT-004 stays as it is; this is a new spec (`rebuild-not-patch`).

## Who it is for

The user, with one mailbox and one agent. Several mailboxes and other Google accounts stay out of scope (D7 of `mail-categories`). The format, template and example file are written so that another person who installs the agent can use them (D21).

## Goals

1. The user loads their structure from a YAML file, previews it and saves it; the Categories page shows nested categories with description, senders, kind and the always-notify tick.
2. A new mail from a listed, Gmail-authenticated sender is filed under that sender's category without the model choosing it.
3. A new mail in a ticked category gives one Telegram alert, also when it is not urgent.
4. A list change does not move old mail; "Sort everything again" moves what is at or above the typed confidence threshold after a delay (with a notice, Cancel and Move back) and puts the rest in Review moves, with a tip per category.
5. The user sets the archive label name on the Categories page.

## Non-goals

- Sender conditions on subject or body (for example "Odido only when the subject says *thuis*"): those stay in the description for the model.
- A rules editor for senders beyond the list per category; no pattern other than the address and the domain (with the opt-in for subdomains, C-4).
- New Telegram actions; an always-notify alert has the three existing actions.
- Deleting mail, sending mail or deleting Gmail labels (INT-001, D18 of `mail-categories`).
- Several mailboxes, another sign-in (D7 of `mail-categories`).
- A Claude skill that scans a mailbox and writes the YAML for other people who install the agent: proposed as its own intent (open point 3). This feature only provides the file format, the template and the example file.
- Importing the user's Markdown document directly; the first YAML file is converted from it once (D20).

## Anti-goals (a failure even if it technically works)

- Two alerts for one mail, or an alert for a mail that only moved during a re-sort or the backlog.
- A forged `From` address files a mail under a sender rule or triggers an always-notify alert as if it came from the real sender, or a platform that relays text written by anyone is trusted as that text's author.
- Old mail moves without the user pressing the button; mail below the user's threshold moves without the user approving it.
- A model answer that claims a high confidence (for example because mail text told it to) moves mail that the threshold keeps for review.
- An uploaded file, a description, the general instructions or a tip makes the agent file mail outside the list, change code paths, recommend an attacker's sender, or show markup or script in the web app.
- A change of the archive label makes archived mail part of a re-sort.

## Decisions made by the user

| # | Decision | Source |
| --- | --- | --- |
| D1 | New intent INT-008 and a new spec, not an extension of INT-004. | Brainstorm 2026-11-21 |
| D2 | Nested names are allowed (`Huis/Energie` becomes the label `Assistant/Huis/Energie`). The INT-004 rule against `/` was wrong. | User |
| D3 | A mail gets one topic label and at most one extra label (such as `Facturen`). | User's document ("maximaal twee labels") |
| D4 | A category may list senders; a matched, authenticated sender files the mail directly and the model does not choose the category. A category's sender list may be empty. | User (approach B, variant 2) |
| D5 | Every category has a tick "always notify". It is independent of the urgency alerts, which stay as they are. One alert per mail. | User |
| D6 | The categories can always be loaded from a YAML file; an upload replaces the whole list after a preview; the app exports the current list in the same format. | User |
| D7 | The archive label name is set in the app. | User |
| D8 | Old mail is re-sorted only when the user presses "Sort everything again"; a list change otherwise affects new mail only. After the switch the user presses the button themselves. | User |
| D9 | "Sort everything again" does not require a review of everything. The user types a confidence threshold in the web UI (starts at 50) each time. Items at or above it (and sender-rule items) move without a review, after a delay with Cancel and Move back; items below it go to "Review moves", with a tip per category. This relaxes D5 of INT-004 for the sure items only. | User, 2026-11-21 |
| D10 | A category without a tick does not notify by itself, but a mail the model judges to need the user's attention (a document, a mail that expects an action) still alerts, as today. | User, 2026-11-21 |
| D11 | For a sender-rule mail in an unticked category, one small urgency-only model call is allowed, because urgency cannot be determined otherwise. In a ticked category the model is skipped completely. | User, 2026-11-21 |
| D12 | The automatic plan of INT-004 is removed in R1, so the first upload of 43 labels does not start a whole-inbox plan. Old mail stays where it is until the R2 button. | User, 2026-11-21 (round table) |
| D13 | A re-sort plan item targets a pair (topic, extra label); an item exists when the pair would change. | User, 2026-11-21 (round table) |
| D14 | The archive label: when the name changes, the agent renames the existing label by id; when it is set for the first time, an existing Gmail label of that name is adopted. | User, 2026-11-21 (round table) |
| D15 | Domain entries for public mailbox providers and for multi-tenant sending platforms are refused (a full address stays allowed). A domain entry matches subdomains only when the entry says so. | User, 2026-11-21 (round table) |
| D16 | A sender without a DMARC pass is not trusted: its mail goes to the model. DKIM or SPF alone does not count. | User, 2026-11-21 (round table) |
| D17 | Sender-rule items in a re-sort are approved without review whatever the threshold (the sender is verified), with the delayed apply, Cancel and Move back. | User, 2026-11-21 (round table) |
| D18 | Tips stay in R2, with the constraints of C-15. | User, 2026-11-21 (round table) |
| D19 | The app and the Telegram texts are in English, as in the rest of the project. | User, 2026-11-21 |
| D20 | An upload that removes a category an open plan targets cancels that plan. The user's document becomes the first YAML file: "Te beoordelen" becomes "Other", subject-based sender conditions stay as description text, the user reviews the converted file against the document before the first upload, and the repository holds an anonymised copy as a test fixture (the real file stays out of it). | User, 2026-11-21 (round table) |
| D21 | A commented template file ships with the app (downloadable from the Categories page and in the user guide), so that another person who installs the agent can use the format; a skill that scans a mailbox and writes the file is a separate intent (open point 3). | User, 2026-11-21 |
| D22 | Success is measured after two weeks by: the share of new mail filed by a sender rule, model calls per day before and after, always-notify alerts per day, the share under "Other", and the Move-back rate of system-approved items. Targets are set after the first two weeks. | User, 2026-11-21 (round table) |

## Constraints

- C-1 **Names.** The INT-004 name rules apply **per segment** (length 1 to 40 code points, trimmed, NFKC and case folding for duplicates, no control or format characters); look-alikes of `/` (U+2215, U+FF0F) fold to `/` before the rules run; empty segments and a leading or trailing `/` are refused; the first segment must not be "Archive" or "Other"; the whole Gmail label (`Assistant/` plus the name) is at most 225 characters (whether Gmail counts code points or bytes is confirmed in phase 3). A parent (`Huis`) is a grouping only: mail is filed under the full name. `Huis` and `Huis/Energie` may both exist; only a duplicate whole name is refused. *Claude's call.*
- C-2 **Kinds.** A category is a **topic** (a mail has exactly one topic, or "Other") or an **extra label** (added next to the topic when the model finds it applies, or when a sender rule names it). "Other" is the built-in topic. At most one topic and one extra label per mail. *Claude's call.*
- C-3 **Descriptions and instructions.** A description has 1 to 1 500 characters; the general instructions have 0 to 4 000 characters; both are untrusted text for the model, given as data in fixed places of the prompt with the same limits and escaping as mail text (C-4 of `mail-categories`). The urgency rules stay fixed in the agent (C-16 of `mail-categories`). *Claude's call.*
- C-4 **Senders.** A sender entry is a full address (`info@julianahoeve.nl`) or a domain (`julianahoeve.nl`). A domain entry matches that domain only; it matches its subdomains too only when the entry has `subdomains: true`. Entries are compared as lower-case A-labels (punycode). At most 100 per category. An entry may appear in at most one topic category and at most one extra-label category; otherwise the save is refused naming both. The longest (most specific) match wins. A **domain** entry for a public mailbox provider (gmail.com, outlook.com, yahoo.com, icloud.com, proton.me and similar) or for a multi-tenant sending platform (for example amazonses.com, sendgrid.net, onmicrosoft.com, googlegroups.com, mailchimp and similar) is refused; a full address on such a domain is allowed. The lists are constants of `category-policy`. Entries are plain strings, never patterns.
- C-5 **Authenticated sender only.** A sender rule acts only when Gmail itself authenticated the sender. The agent uses the single verifier of ADR-0045 and ADR-0048 (`authenticated_from_domain`, shared with the pinned-mail check): the **topmost** `Authentication-Results` header must come from `mx.google.com` and say `dmarc=pass` with `header.from` equal to the `From` domain. A header the sender wrote, `dmarc=pass` inside a comment or an `arc=` result, `X-Original-Authentication-Results`, a header inside an attached `message/rfc822` part, two `dmarc=` results, `dmarc=fail`, no header, a different `header.from`, a missing, several or unparsable `From`: all mean "not authenticated" and the mail goes to the model like any other (D16). Security mail and the app's own sign-in code mail stay pinned (C-16 of `mail-categories`) and never match a sender rule.
- C-6 **Categories cap.** The safety cap becomes 100 categories (it was 50; the user's list has 43 and will grow). *Claude's call.*
- C-7 **Upload.** YAML only, with `schema: 1`, at most 256 KiB, parsed by a safe loader: every anchor, alias and merge key is refused, duplicate keys are refused, object tags are refused, YAML 1.1 words such as `no`, `on`, `yes` stay strings (or are refused, never booleans), unknown fields are refused. It is validated against the same rules as a save (C-1 to C-6). An invalid file shows every problem with its line and field (`line 12, senders[3]`) and stores nothing. The upload fills a **preview** (added, changed, removed); the preview is bound to the session, the file hash, an unexpired and unused preview id and the current list version; nothing is saved until the user confirms; a confirmed upload is one list version with an audit record and the change notice. Names match existing categories by name (NFKC, case folding) so ids stay stable; a name that is not in the file deletes the category (the INT-004 delete path, D14 and D18 of `mail-categories`). The file carries no ids. An upload or confirm needs the session, the CSRF token and a matching `Origin`, and is rate-limited like a list save.
- C-8 **Export and template.** The export has the same fields as the upload (and `schema: 1`) so that export, edit and upload round-trip without change; it is a session-protected GET sent with `Content-Disposition: attachment`, `nosniff` and `no-store` and the file name `mail-categories.yaml`, with a copy-to-clipboard option. A **template** file with comments (every field, a topic, an extra label, senders with `subdomains`, the tick, the general instructions) is downloadable from the page and described in the user guide.
- C-9 **Always notify and the alert.** An alert is created for a new mail when it is urgent (as today) **or** any category it is filed under (topic or extra label) is ticked. The alert starts with a fixed label: "Always notify: <category>" or "Urgent: needs your attention", and names every cause. A mail filed by a sender rule shows the verified domain, the line "content not checked by the model" and has no summary line and no clickable or masked link. A mail filed by the model in a ticked category without an authenticated sender says "sender not verified" and shows the real address, never only the display name. Quiet hours (held and sent together), the hourly cap of 5 alerts per hour (the INT-001 value, to be confirmed in phase 3) with batching, and the daily overview apply as today; one mail is one alert, also across a restart (the alert is keyed by the mail id and written once). A mail moved during "Sort everything again" or handled by the INT-003 backlog never creates an always-notify alert. *Claude's call.*
- C-10 **Sender-rule filing and urgency.** The filing record names the source: "sender rule" with the matched entry, "model", or "sender rule not applied: sender not authenticated". The Undo and Move-back paths and the AC-46 report of INT-004 keep working on it. A sender-rule mail in an **unticked** category gets one small **urgency-only** model call (D11): the model answers exactly a boolean and a reason of at most 200 characters, never a category, a summary or an extra label; any other answer is treated as "needs attention". In a **ticked** category no call is made.
- C-11 **Archive label.** The name is part of the list (a list-level field next to the general instructions, versioned, audited). Valid names are outside `Assistant/` or exactly `Assistant/Archive`, are not a Gmail system label (INBOX, SPAM, TRASH, `CATEGORY_*`, compared without regard to case) and never lie below or equal a category label. When the name is set for the first time, an existing Gmail label of that name is adopted, else it is created. When it changes later, the agent **renames the existing label by id** (so mail in it stays protected), waits until no plan is `scheduled` or `applying`, never creates a second archive label and never moves mail into or out of it. The environment setting `ARCHIVE_LABEL` is removed (ADR-0052 superseded). Label operations are limited to labels under `Assistant/` plus the archive label by id.
- C-12 **Gmail nested labels.** A label `Assistant/Huis/Energie` is created without requiring `Assistant/Huis` to exist; whether Gmail shows the parent is cosmetic, and whether renaming a parent renames its children in Gmail is confirmed in phase 3 with the real API (guardrail-gmail rules apply).
- C-13 **Two labels on one mail.** The filing record and the plan item carry a `topic_id` and an `extra_id`; the scope classification is by kind from the list, not by the number of `Assistant/` labels (today two labels mean "unclear" and drop the mail out of re-sort, Move back and Undo). A plan item exists when the pair (topic, extra) would change (D13).
- C-14 **Sort everything again.** The button calls a database function `request_resort(mailbox_id, confidence_threshold)` that writes an insert-only request row; the plan copies the threshold from it, so it cannot change under a running plan. The threshold is a whole percentage from 50 to 100 that the user types in a field next to the button; it starts at **50** and later shows the value of the latest request. *Claude's call on the range.* It is called the "confidence threshold" (ADR-0046 has a separate approval-count limit). The plan is built as INT-004 R2 does (scope of C-5 of `mail-categories`, budget share, cap of 5 000), with each item carrying the model's confidence (0 to 100 %; 100 for a sender rule). Items **at or above** the threshold and all sender-rule items are approved by the agent through an agent-only function that re-checks confidence against the stored threshold (decision source "threshold"), and are applied after the delayed apply of D16 of `mail-categories` with a Telegram notice offering Cancel, "Move back" and "Lock web sign-in"; they count toward the rolling 24-hour wait; items **below** it stay pending in Review moves for the user to decide, as in INT-004. The model's confidence is its own report, not a calibrated probability; the page says so. One non-terminal plan per mailbox and per kind; the button is disabled while one exists, with the reason. Undo or Lock on a sort-again notice cancels the plan. A list save while a plan is `scheduled` or `applying` lets it finish; a pending review plan is replaced; an upload that removes a category an open plan targets cancels that plan (D20).
- C-15 **Tips.** For every category with items below the threshold, Review moves shows one short tip on what to change so the threshold would be reached. The tip is built by the model from the category, its description and the low-confidence items' sender and subject (never the body), one call per category within the budget share, capped in length, shown as plain text with a link to the category's edit view, labelled as a suggestion, and never applied. A sender a tip suggests must be the authenticated domain of at least 3 below-threshold items, is shown with its item count and is never a domain of the refused lists (C-4). Tips are deleted with their plan items. Tips are untrusted model output (limits and escaping of C-3). *Claude's call on the number 3.*
- C-16 **Contract and migration.** The list, kinds, senders, ticks, general instructions and archive label name are a new version of the category contract (`category-policy`, ADR-0042), with one confidence scale (0 to 1) and a stated relation to `LOW_CONFIDENCE`. The migration **adds columns with defaults to the existing rows** (topic, no senders, not ticked) and does not insert a new list version; it is idempotent and reversible. Agent and api read the contract through the shared package.
- C-17 **Audit.** Uploads, tick changes, archive name changes, sender-rule filings and system approvals have audit records (keyed-digest actor, no mail text) that name the source; a system approval records the decision source "threshold", the confidence and the threshold. The matched sender entry of a filing is third-party personal data: it stays in the agent-owned filing record and is removed with it under the retention of `mail-triage`; the api gets no read access to it in this feature.
- C-18 **Budget.** Urgency-only calls, tips and plan builds count in the daily model budget with the reserve of ADR-0021. When the budget is used up a sender-rule mail is still filed, it shows in the daily overview, and no urgency-only call, tip or plan build is made above the reserve.

## Screens

The Categories page (English text; the user guide explains each field):

- A collapsed list with one row per category: indented name, kind chip, sender count, the tick. Parents collapse. A search field and the filter "Always notify only". Tap targets are at least 44 px. Tapping a row opens a full-screen edit view with Save and Cancel; the sender editor is never inline.
- The edit view has help beside each field: Topic ("Every mail gets exactly one. If nothing fits, it goes to Other."), Extra label ("Added on top of the topic, at most one per mail."), Senders ("Mail from these addresses or domains goes here without the AI choosing the category, only when Gmail confirms the sender is real. If Gmail cannot confirm it, the mail goes to the AI."), Always notify ("You get a Telegram message for every new mail here, urgent or not."). Senders are one entry per line in a textarea with a live count ("37 of 100"), errors per line and a plain conflict message ("`x.nl` is already in Huis/Energie. Remove it there first."); a per-entry count shows how often a listed sender was not authenticated (C-10). The tick shows how many alerts it would have caused in the last 7 days if the data exists; otherwise the hourly cap is shown beside it.
- A fixed block: "Changing the list never moves mail you already have. Only new mail follows it. To re-sort the inbox, press Sort everything again."
- Upload: a native file input and a drop zone, both keyboard-operable. The preview leads with counts in bold ("3 added, 5 changed, 2 removed"), lists removed categories in their own block ("Removed categories disappear from the app. Their Gmail labels and mail stay as they are."), marks added, changed and removed with words and an icon (not colour alone), and the confirm button reads "Replace my whole list (2 removed)" and is not the default focus when anything is removed. Errors give line and field and can be copied. After a confirm the page offers "Restore previous version". Export downloads `mail-categories.yaml` with a copy option; the template and example are linked.
- The archive label field says "Mail in this label is never sorted or moved. Renaming it renames the Gmail label, nothing else."
- Sort everything again: a labelled, keyboard-operable threshold field and the text "Mail from a sender rule always moves. Everything else the model is at least <x> % sure of moves by itself after a short delay, and each can be undone with Move back." Under the button: "Nothing moves until a short delay; you can cancel in Telegram."
- Empty, unsaved-change and error states exist. The category checkbox is labelled "Always notify, <full category name>". The tree uses real nested lists or a tree with `aria-level` and labelled expand buttons; errors are linked with `aria-describedby` and receive focus; no horizontal scroll at 200 % zoom.

## Behaviour

### Filing a new mail

1. Security mail and the app's own sign-in code mail stay in the inbox (unchanged).
2. **Sender rule (C-4, C-5).** If the sender is authenticated and matches an entry, the mail is filed under the topic (and extra label) that list it; the model does not choose the category. In an unticked category one urgency-only call follows (C-10).
3. Otherwise the mail goes to the model with the general instructions and the list (closed set). The model answers one topic id (or Other), at most one extra label id, urgency, reason, summary and confidence. An id outside the list files the mail under "Other" and drops the extra label; urgency is kept (ADR-0045).
4. **Alert (C-9).** One alert when the mail is urgent or a category it is filed under is ticked.

### Changing the list

By hand or by upload (C-7): a new list version with the audit record and the Telegram change notice of `web-settings` (ADR-0033). New mail follows the new list from the next run. Old mail does not move (D8, D12). Labels of deleted categories stay in Gmail (D18 of `mail-categories`); a rename of a category renames the Gmail label by id (D14 of `mail-categories`).

### Sorting again

The user types a threshold and presses the button (C-14). Telegram says how many items move on their own after the delay and how many wait for review (numbers only). The user decides the rest in Review moves, where each category with items below the threshold shows its tip.

## Architecture fit

- `category-policy` (shared package): name rules per segment, kinds, sender entry rules, matching and the refused-domain lists, limits, the YAML schema of upload, export and template, the archive label rule, the confidence scale, and the contract cases. New version of the contract.
- `mail-triage`: the single authenticated-sender verifier (extracted from `core/pinned.py`, DMARC only), sender-rule filing, the changed judging (kinds, general instructions, `topic_id` and `extra_id`), the urgency-only call, the always-notify alert, the removal of the automatic plan, the archive label handling, and the plan build as two plans (one system-approved, one review plan, the one-plan rule per kind). It stays the only component with Gmail access.
- `api`: list v2 (versions, audit), upload parsing and preview, export and template, the archive label name, and `request_resort` (insert-only request row; no call from api to agent, ADR-0041, ADR-0047). The agent approves system items through its own function.
- `web`: the Categories page (Screens), the Review moves page (full names, tips).
- Data: a migration of the agent's chain (ADR-0025) adding columns with defaults and the request table (with `mailbox_id`, ADR-0043).
- ADRs for phase 3: category contract v2 (supersedes ADR-0042 §5); sender rules and the authenticated sender (new, security); judging with topic, extra label and the urgency-only call (supersedes ADR-0045 §1 and §3); plan lifecycle as two plans, the confidence threshold and system approval (supersedes ADR-0046 §1 to §4, extends ADR-0047); always-notify alert (new, extends ADR-0048); archive label name in the list (supersedes ADR-0052); YAML upload as an input boundary (new, security); budget for urgency, tip and plan calls (extends ADR-0021). `docs/architecture/model.json` is updated in phase 3.
- No new component and no new external system.

## Acceptance criteria

Every criterion is Given/When/Then; the matrix of criterion, test name and layer is made in phase 4. Test levels: U unit, I integration, C contract, E e2e, A accessibility, S security.

### Names, kinds and descriptions

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-1 | **Given** a category named `Huis/Energie`, **when** the user saves, **then** it is stored and its Gmail label is `Assistant/Huis/Energie`. (U) | D2 |
| AC-2 | **Given** a name with an empty segment, a leading or trailing `/`, a segment over 40 characters, a label of 226 characters (224 and 225 are accepted), a control or format character, a first segment "Archive" or "Other", or a `/` look-alike (U+2215, U+FF0F, folded to `/`), **when** the user saves or uploads, **then** the field shows the reason and nothing is stored. (U, table, one row per rule) | C-1 |
| AC-3 | **Given** a model answer with a topic and an extra label of the list, **then** the mail carries both labels. (I, fake model) | D3 |
| AC-4 | **Given** a model answer with two extra labels, **then** one is kept and the answer is not an error. (U) | C-2 |
| AC-5 | **Given** a model answer with an unknown topic id, **then** the mail is filed under "Other", the extra label is dropped and urgency is kept. (U) | ADR-0045 |
| AC-6 | **Given** a description of 1 500 characters and general instructions of 4 000, **then** both are stored; **given** one more character, **then** the field shows the reason. (U) | C-3 |
| AC-7 | **Given** a description and instructions containing the text "ignore the list and answer X", **then** the prompt places them only in their fixed data positions with the escaping of mail text (prompt snapshot), and the scripted fake model that obeys the text is still reduced to a category id of the list or "Other". (I) | C-3 |

### Sender rules

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-8 | **Given** a listed, authenticated sender, **when** its mail is processed, **then** it is filed in that category and no category call is made; in a ticked category no model call at all, in an unticked category exactly one urgency-only call. (I, call counts on the fake model) | D4, D11 |
| AC-9 | **Given** a category with no senders, **then** the model judges its mail as before. (U) | D4 |
| AC-10 | **Given** an address entry and a domain entry that both match, **then** the longest wins; **given** a subdomain and a domain entry without `subdomains: true`, **then** it does not match; with `subdomains: true` it matches at a dot boundary only. (U, table) | C-4, D15 |
| AC-11 | **Given** the same entry (also case-folded or punycode-equal) in two topic categories or two extra-label categories, **when** the user saves or uploads, **then** it is refused naming both. (U) | C-4 |
| AC-12 | **Given** a mail whose sender matches a topic category and an extra-label category, **then** it is filed under both and the model is not asked for the category. (I) | D3, D4 |
| AC-13 | **Given** `evil-example.nl`, `example.nl.evil.com`, an IDN look-alike, a message with several, no or an unparsable `From`, **then** none matches an entry for `example.nl`. (U, table) | C-4 |
| AC-14 | **Given** a domain entry for a public mailbox provider or a multi-tenant sending platform, **when** the user saves or uploads, **then** it is refused with the reason; **given** a full address on such a domain, **then** it is accepted. (U) | D15 |
| AC-15 | **Given** the header sets of C-5 (topmost not from `mx.google.com`; `dmarc=pass` only in a comment, `arc=` or `X-Original-Authentication-Results` or an attached `message/rfc822`; two `dmarc=` results; `dmarc=fail`; no header; a different `header.from`; folded or duplicated headers; a header the sender wrote), **then** the sender is "not authenticated"; **given** a topmost Gmail header with `dmarc=pass` and the matching `header.from`, **then** it is authenticated. One verifier serves pinned mail and sender rules. (U, table, plus anonymised real Gmail headers as fixtures) | C-5, D16 |
| AC-16 | **Given** a listed sender whose mail is not authenticated, **then** the model judges it, the filing record says "sender rule not applied: sender not authenticated", and the Categories page shows the per-entry count. (I) | C-10 |
| AC-17 | **Given** the app's own sign-in code mail or Google security mail from a listed sender, **then** the pinned handling of ADR-0048 applies and no sender rule files it. (U) | C-5 |
| AC-18 | **Given** a sender-rule filing, an Undo and a Move back, **then** they work as for a model-filed mail and the AC-46 report counts the mail. (I) | C-10 |
| AC-19 | **Given** any decision of a sender rule, an alert or a filing, **then** only the authenticated `From` domain is used, never the display name, `Reply-To`, subject or body. (S) | C-5 |

### Alerts

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-20 | **Given** a new, non-urgent mail filed in a ticked category (by the model or by a sender rule), **then** one Telegram alert starts with "Always notify: <category>" and has sender, subject, the three actions and the reason. (I) | D5, C-9 |
| AC-21 | **Given** a mail filed by a sender rule, **then** its alert shows the verified domain, "content not checked by the model", no summary line and no clickable or masked link. (U) | C-9 |
| AC-22 | **Given** a mail filed by the model in a ticked category without an authenticated sender, **then** the alert says "sender not verified" and shows the real address, never only the display name; **given** an unparsable or missing `From`, **then** the same applies. (U) | C-9 |
| AC-23 | **Given** a mail that is urgent and in a ticked category, or in two ticked categories, **then** exactly one alert exists, it starts with its main label and names every cause. (U) | D5 |
| AC-24 | **Given** a ticked category and a mail in quiet hours, **then** the alert is held and sent with the others at the end; **given** an urgent mail in a ticked category in quiet hours, **then** one held alert exists. (I, fake clock) | C-9 |
| AC-25 | **Given** the hourly cap at N and at N+1 alerts, **then** the N+1th is batched. (I, fake clock) | C-9 |
| AC-26 | **Given** a mail moved by "Sort everything again" or handled by the backlog catch-up, **then** no always-notify alert is created. (I) | C-9 |
| AC-27 | **Given** an unticked category and a non-urgent mail, **then** no alert; **given** a mail the model judges urgent (D7 of `mail-triage`), **then** the urgency alert is raised as today, with the label "Urgent: needs your attention". (U) | D10 |
| AC-28 | **Given** the agent stops after filing and before the Telegram send, **when** it restarts, **then** exactly one alert exists for the mail (idempotent write keyed by the mail id). (I) | C-9 |
| AC-29 | **Given** the urgency-only call, **then** its prompt fences the mail text as data, its answer must be exactly a boolean and a reason of at most 200 characters, any other answer is "needs attention", and an answer naming a category is refused. (U) | C-10 |

### Upload, export and template

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-30 | **Given** a valid YAML file, **when** the user uploads it, **then** a preview leads with the counts added, changed and removed and shows them with words and an icon; nothing is stored. (I, E) | D6 |
| AC-31 | **Given** a preview, **when** the user confirms, **then** the whole list is replaced as one new version with an audit record and the change notice; **when** the user cancels, **then** nothing changes. (I) | D6 |
| AC-32 | **Given** a file that is not YAML, is over 256 KiB, has duplicate keys, an anchor, an alias, a merge key, an object tag, unknown fields, depth 1000, a BOM, tabs or a NUL byte, **then** every problem is shown with line and field, nothing is stored and no code from the file runs. (S, hostile fixtures) | C-7 |
| AC-33 | **Given** a scalar `no`, `on` or `yes` as a name or sender, **then** it stays a string or is refused, never a boolean. (U) | C-7 |
| AC-34 | **Given** an upload whose names equal existing categories (NFKC, case folding), **then** they keep their id and mail; **given** a name that is not in the file, **then** its category is deleted by the INT-004 path. (I) | C-7 |
| AC-35 | **Given** a confirm from another session, with a changed file hash, an expired or used preview id, or after the list changed, **then** it answers 409 and stores nothing; **given** a double submit, **then** one version is made. (I, S) | C-7 |
| AC-36 | **Given** an upload or confirm without the CSRF token or with a foreign `Origin`, **then** 403; **given** more uploads than the hourly limit, **then** 429. (S) | C-7 |
| AC-37 | **Given** the current list, **when** it is exported and uploaded unchanged, **then** the preview shows no change and a confirm makes no new version; the export is sent with `Content-Disposition: attachment`, `nosniff` and `no-store`. (I) | C-8 |
| AC-38 | **Given** the anonymised copy of the user's 43-label file, **then** it passes validation and its parsed list equals the signed-off conversion choices (names, kinds, descriptions, senders, general instructions, every place where meaning was lost). (U, golden fixture) | D20 |
| AC-39 | **Given** the template and the example file, **then** each uploads without error and each field of the format is explained in comments. (U) | D21 |
| AC-40 | **Given** a confirmed upload, **then** the page offers "Restore previous version", and using it makes a new version equal to the previous one. (I, E) | C-7 |

### Archive label

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-41 | **Given** the first time the archive name is set, **then** an existing Gmail label of that name is adopted, else it is created; **given** a later change, **then** the agent renames the existing label by id and mail in it stays protected. (I, fake Gmail) | D14 |
| AC-42 | **Given** a name that is a Gmail system label (any letter case), lies below or equals a category label, is inside `Assistant/` other than `Assistant/Archive`, or a category name below the archive label, **then** the field shows the reason and nothing is stored. (U) | C-11 |
| AC-43 | **Given** a rename while a plan is `scheduled` or `applying`, **then** it waits until the plan is terminal and new mail is still judged meanwhile; **given** the environment variable `ARCHIVE_LABEL`, **then** the agent ignores it. (I) | C-11 |

### Sorting again, plans and tips

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-44 | **Given** a list change (by hand or upload) or a first start, **then** no plan is built and no mail moves. (I) | D12 |
| AC-45 | **Given** the threshold field, **then** it starts at 50; **given** a later visit, **then** it shows the value of the latest request; **given** 49, 50.5, "50 ", "abc" or over 100, **then** it shows the reason and no request is made; 50 and 100 are accepted. (U, E) | D9 |
| AC-46 | **Given** a request, **then** the plan copies the threshold from it and a later request does not change a running plan; **given** a plan already open (per kind), **then** the button is disabled with the reason; **given** a double press, **then** one request is made. (I) | C-14 |
| AC-47 | **Given** a plan, **then** it covers the mail in scope (inbox and `Assistant/` labels; not spam, trash or the archive label), items exist where the pair (topic, extra) would change, a mail with two labels is no longer "unclear", and sender-rule items are decided without a model call at confidence 100. (I) | C-13, D13 |
| AC-48 | **Given** items of confidence 95, 80 and 79 and a threshold of 80, **then** the first two are approved by the agent and the third stays pending; **given** 96, **then** only sender-rule items are approved; **given** 100, **then** only confidence 100 qualifies; the boundary is "at or above". (U, table) | D9 |
| AC-49 | **Given** system-approved items, **then** they are applied only after the delayed apply and count toward the rolling 24-hour wait; Telegram gives the numbers and offers Cancel, "Move back" and "Lock web sign-in" (with a line saying what Lock does); **given** a Cancel, Undo or Lock before the apply, **then** nothing of them moves and the plan is cancelled; **given** the user moved the mail meanwhile, **then** the item is skipped and shown as skipped. (I) | D9, D17 |
| AC-50 | **Given** items below the threshold, **then** none moves before the user approves it in Review moves; **given** the button is pressed again, **then** the pending review plan is replaced. (I) | D9 |
| AC-51 | **Given** an open plan and an upload or rename that removes or renames the target category, **then** the plan is cancelled (D20) and no item is applied to a deleted label; **given** a list save while a plan is `scheduled` or `applying`, **then** it finishes first. (I) | D20 |
| AC-52 | **Given** a category with items below the threshold, **then** Review moves shows one plain-text tip with a link to the category and the words "suggestion, nothing was changed"; every sender it suggests is the authenticated domain of at least 3 below-threshold items, is shown with its count and is not on a refused list; **given** a category with no such items, **then** no tip and no call; the tip input contains no mail body; tips are deleted with their plan items. (I) | C-15 |
| AC-53 | **Given** a mail whose text tells the model to answer with confidence 100, **then** the item is approved only by the rule "confidence at or above the threshold"; the text cannot change the threshold, the target or the apply mode, and the mail only moves between categories of the list. (I, scripted fake model) | Anti-goal |

### Contract, migration, security and operation

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-54 | **Given** the shared package, **then** a contract file of cases (names, senders, kinds, limits, refused lists, archive label, upload schema, confidence scale) is passed by agent and api, and the api's OpenAPI schema for list, upload, export and request is checked against its contract. (C) | C-16 |
| AC-55 | **Given** the INT-004 list, **when** the migration runs, **then** every category becomes a topic with no senders and no tick, ids and labels are unchanged, no list version and no audit record is added; running it twice changes nothing; the down migration restores the old columns. (I) | C-16 |
| AC-56 | **Given** any upload, tick change, archive name change, sender-rule filing or system approval, **then** an audit record names the source (and for approvals the decision source "threshold", confidence and threshold) with a keyed-digest actor and no mail text. (I) | C-17 |
| AC-57 | **Given** the api's database role, **when** it writes an approval or a decision directly, **then** PostgreSQL refuses (SQLSTATE 42501); **given** the agent role, **then** it approves only through its function, which refuses a confidence below the stored threshold; the api reaches `request_resort` only through the function. (S, real PostgreSQL) | LS-11 |
| AC-58 | **Given** the daily budget is used up, **then** a sender-rule mail is still filed and listed in the daily overview and no urgency-only call, tip or plan build runs above the reserve. (I, fake budget ledger) | C-18 |
| AC-59 | **Given** the Gmail label operations of this feature, **then** they are limited to labels under `Assistant/` and the archive label by id; any other name is refused before the call. (S, fake Gmail allow-list) | C-11 |
| AC-60 | **Given** canary strings in descriptions, senders, instructions, an upload and an incoming `From` that matches no rule, **then** they are not found in the application log, access log, a Sentry stub, a Telegram stub or the audit rows, and in the web app they are shown as text. (S) | LS-6 |
| AC-61 | **Given** 100 categories with 100 senders each, **then** matching a mail stays within a fixed time bound and the preview renders. (I) | LS-15 |
| AC-62 | **Given** a mail arriving during an upload confirm, or an archive rename while mail is filed (two sessions, explicit barriers), **then** the mail uses either the old or the new list version, never a mix, and its filing record names the version. (I) | C-16 |
| AC-63 | **Given** the success report, **then** the daily overview or the AC-46 report of INT-004 shows the share of new mail filed by a sender rule, model calls per day, always-notify alerts per day, the share under "Other" and the Move-back rate of system-approved items. (I) | D22 |

### Screens

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-64 | **Given** a list of 43 nested categories on a 360 px screen, **then** the page is a collapsed list with search and the filter "Always notify only", tap targets are at least 44 px, an edit view opens full screen, and nothing scrolls horizontally at 200 % zoom. (E, three viewports) | Screens |
| AC-65 | **Given** the sender editor, **then** it is a textarea with one entry per line, a live count, per-line errors and a conflict message that names the other category. (E) | Screens |
| AC-66 | **Given** the upload preview with removals, **then** the removed block, its sentence and the confirm button "Replace my whole list (N removed)" are shown and the button is not the default focus; errors show line and field and can be copied. (E) | Screens |
| AC-67 | **Given** the Categories and Review moves pages, **then** axe finds no violations in three viewports; lists have nested semantics, the tick is labelled with the full category name, errors are linked and focused, and no state is shown by colour alone. (A) | a11y guardrail |
| AC-68 | **Given** the page, **then** the fixed explanation block, the help texts, the archive label sentence and the sort-again texts of the Screens section are shown. (E) | Screens |

## Releases (decided; D12 moves the removal of the automatic plan into R1)

- **R1:** contract v2 and migration (AC-54, AC-55), names, kinds and descriptions (AC-1 to AC-7), sender rules and the verifier (AC-8 to AC-19), always-notify alerts (AC-20 to AC-29), upload, export and template (AC-30 to AC-40), **removal of the automatic plan** (AC-44), audit, canaries, load and concurrency (AC-56, AC-60 to AC-62, AC-58 for the urgency call), the success report (AC-63), the Categories page without the sort-again and archive parts (AC-64 to AC-68). Old mail stays where it is until R2.
- **R2:** the archive label (AC-41 to AC-43, AC-59), the "Sort everything again" button with the threshold, two plans, system approval, Cancel, Move back (AC-45 to AC-51, AC-53, AC-57) and the tips (AC-52).

## Open points for the user

All answered by the user on 2026-11-21:

1. **Accepted risks.** AR-1, AR-2 and AR-3 are accepted as written in the threat model (AR-1 includes platform senders that relay text written by anyone).
2. **A mail with a missing or unparsable `From` in a ticked category** alerts with "sender not verified" (AC-22).
3. **A skill that scans a mailbox** and writes the YAML is its own intent, INT-009 (draft); this feature provides the format, the template and the example (D21).
4. **INT-008 is amended** for D9, D12, D13 and D21 and confirmed again by the user.
