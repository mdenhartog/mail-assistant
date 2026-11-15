---
feature: mail-categories
intent: INT-004
spec: docs/specs/mail-categories.md
extends: web-settings-threat-model, mail-triage-threat-model
status: approved
date: 2026-11-14
approver: the user
asvs: "5.0"
---

# Threat model: mail categories

This model adds to `mail-triage-threat-model.md` (Gmail, model, Telegram) and `web-settings-threat-model.md` (sign-in, session, CSRF, database roles). Threats that are unchanged there are not repeated; ids here are `MC-n`, accepted risks `MR-n`.

## Scope

The list of categories (name, description), the re-sort plan with its items (message id, sender, subject, old and new category, decision), two new pages in `apps/web` ("Categories", "Review moves"), the new routes in `backend`, a new database schema with its grants, the agent's judging against a closed list, the building and applying of plans, the label `Archive`, Telegram notices for list changes, ready plans and results, and the extra Gmail operations the agent needs (list by label, remove a label from a mail, rename an `Assistant/` label by id). There is no label delete (D18).

Out of scope: sign-in and session design (unchanged, `web-settings`), mail bodies in the web app (non-goal), several mailboxes and Google sign-in (D7).

## Data classification

| Data | Class | Note |
| --- | --- | --- |
| Category name | internal | User text. Becomes a Gmail label `Assistant/<name>`, visible in Gmail. |
| Category description | internal, sent to the model | User text, read by the model as data (C-4). It leaves our infrastructure like mail text (A-1 of ADR-0018). The page says so. |
| Plan item: sender, subject (cut to 120) | personal data (third parties' names and addresses, subject lines) | New in the web app (D13). Kept at most 14 days after the last decision. Never in a log, a URL, a Telegram notice, an error or Sentry. |
| Plan item: Gmail message id, old and new category, decision | internal | Ids alone give nothing without the Gmail token. |
| Plan counts (moved, skipped, failed, per group) | internal | May be sent to Telegram. |
| Category and plan audit records | internal | Actor is a keyed digest, as `settings_change`. |
| Mail bodies, alert content, Gmail token | secret / personal data | Stay unreachable for the api role (AC-20). |
| Label `Archive` | internal | The agent creates it and never fills it. |

## Diagram

```text
Browser --[B1: local network, TLS, session + CSRF, unchanged]--> ingress --> web app --> backend API
backend API --[B2: api DB role: list versions (select, insert), plan items (column select); decisions and approvals only through the functions record_decision and approve_plan (ADR-0047)]--> PostgreSQL schema "categories" (migrated by the agent)
agent --[B2': agent DB role: list (read), plans and items (read/write), mail tables]--> PostgreSQL
agent --[B4: Gmail API, gmail.modify (unchanged scope): list, read, add/remove label, create label, rename Assistant/ label by id; no delete]--> Gmail
agent --[B5: model API, closed-set answer, descriptions as data]--> Anthropic
agent --[B6: Telegram, numbers and list changes only]--> User
```

B1, B2 (as a role), B4, B5 and B6 exist today. New is the content that crosses them: user text towards the model, sender and subject towards the browser, and the plan as a new write path from browser to a table the agent acts on. An archify data-flow diagram is added with the design in phase 3.

## What is new compared with today

1. The web app can now cause **mail to move** (indirectly: a decision in a table that the agent acts on). Until now it could only change four settings.
2. The web app now shows **third-party personal data** (sender, subject).
3. **User-written text** (descriptions) becomes part of the model prompt.
4. The agent needs **two more Gmail operations**: remove a label from many mails, and rename a label by id (no label delete, D18).

## Threats

| id | element | STRIDE | threat | L | I | mitigation | criterion | ASVS / OWASP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MC-1 | B5 judging, mail text and descriptions | T, E | Prompt injection in a mail or in a description makes the model file a mail outside the list, hide an important mail, or return text that is used as an instruction. | H | M | The model has no tools and answers with one id from a closed set; anything else becomes "Other"; mail text and descriptions go in fixed places of the prompt with the same limits and escaping; nothing from the answer is executed or shown unescaped; urgency rules are fixed in the agent and independent of the category (C-16, AC-38); the model judges one mail per call. | AC-5, AC-6, AC-7 | LLM01, LLM06; V1, V2 |
| MC-2 | B1 list write, stolen session or mailbox | T, S | Someone who reads the user's mailbox (R-1 of web-settings) signs in and rewrites the list or a description so that mail is filed away from the inbox (for example "Other: everything"), or so that the model hides mail from the user. | M | H | Every list change is announced in Telegram with old and new list and Undo, also in quiet hours (ADR-0033 style); Undo restores the previous list as a new version and discards a pending plan; the web lock refuses list calls; new mail is only labelled and never deleted or sent; versioned list and audit. | AC-18, AC-31, AC-32 | V6, V16 |
| MC-3 | B1 plan decisions, stolen session | T, E | The same attacker approves a plan (or inserts approvals) so that a large number of mails move at once, or hides the effect. | M | H | A move changes labels only and is reversible; a result notice with counts goes to Telegram after every apply; "approve all" carries the plan id and the number of items the user saw, a different state gives 409; the web lock refuses plan calls; the plan is announced in Telegram before anything can be approved. Decided (D16): no re-authentication; approvals above a threshold (counted over all approvals of the mailbox in 24 hours, so splitting does not avoid it; set only by deployment configuration) wait 15 minutes in the plan state `scheduled`, with decisions frozen and a Telegram Cancel and Lock bound to chat, plan and a single-use nonce (AC-48), and the apply audit keeps message id, old and new label so "Move back" works after the items are removed. | AC-31, AC-32, AC-18, AC-41, AC-42 | V6, V16, V3 |
| MC-4 | B1 state-changing calls | T | A cross-site request saves a list, approves or rejects items. | M | H | CSRF token and strict `Origin` check on every state-changing call, state changes only by POST or PUT, no CORS (as `web-settings`). | AC-22 | V3 |
| MC-5 | web pages, Telegram notices | T, I | Script or markup in a sender, a subject, a category name or a description is run in the page or changes a Telegram message (hidden links, fake buttons). | M | H | React escaping, no raw HTML, strict Content-Security-Policy without inline scripts; Telegram text escaped and plain; names and descriptions are length-limited and the name pattern forbids `/` and control characters. | AC-21, AC-29 | V1, V3 |
| MC-6 | B2 api DB role | E, I | The api role reads mail bodies, alert content or tokens, or writes plan item fields other than the decision (message id, categories), inserts items, or alters the schema. | M | H | New schema `categories`, migrated only by the agent chain (ADR-0025); the api role gets column-level `SELECT` on plan items and no `UPDATE`, `INSERT` or `DELETE` on them; it changes decisions and approves only through the `SECURITY DEFINER` functions `record_decision` and `approve_plan` (fixed `search_path`, non-login owner, revoked from `PUBLIC`, `EXECUTE` for the api only, no dynamic SQL, ids checked against plan and mailbox, a 409 when the plan is not `ready`); list versions are insert-only with a version check; nothing on `public`; the full grant matrix is in the design. | AC-20, AC-27, AC-56 | V8, V13 |
| MC-7 | plan page, logs, caches | I | Sender and subject leak through logs, errors, Sentry, URLs, browser cache or a shared screen; items live for ever. | M | M | Sender and subject are never logged, put in a URL, error body, Sentry event or Telegram notice (counts only); responses carry `Cache-Control: no-store`; items are removed 14 days after the last decision, at once after an apply, or when replaced; the page is shown only to the signed-in user. Accepted exposure to anyone who can sign in: MR-1. | AC-19, AC-30 | V14, V16 |
| MC-8 | agent apply, stale or forged plan | T | A plan built for an old list is applied after the list changed, or an approved item points to a category that no longer exists, so mail goes to a wrong or invented label. | M | M | A plan carries the list version it was built for; the agent applies only when the version equals the current one; the proposed category must exist in the current list at apply time; a replaced plan can never be applied (C-10). | AC-16, AC-26 | V2, V13 |
| MC-9 | agent apply, concurrency | T | Two runs apply the same item (double move), or an item is applied after the user moved or archived the mail. | M | M | Item states `pending, approved, rejected, applied, skipped, failed`, changed with a compare-and-set; one apply run at a time; before moving, the agent checks the mail is still in scope (in the inbox or carrying exactly the old `Assistant/` label, not in spam, trash or `Archive`); otherwise the item is skipped and shown as skipped. | AC-14, AC-15, AC-35 | V2 |
| MC-10 | B4 Gmail operations | E | The new operations (bulk label change, label delete) become a path to delete mail or to damage labels the user owns (`Archive`, their own labels, system labels). | M | H | The scope is unchanged (`gmail.modify`, already granted); the wrapper still has no trash, delete-message, spam or send in the apply path, and a test fails if one is added (T-14); label changes only on messages of the plan; `Assistant/` labels only, never `Archive`, system labels or labels outside the prefix; a label delete only for an `Assistant/` label that is not in the list and is empty at that moment, by id. Decided (D18): there is no label delete at all; the only new label operations are remove-from-message and rename by id for `Assistant/` labels (D14). | AC-14, AC-25, AC-28 | LLM06; V4 |
| MC-11 | agent model budget | D | A long list (50 categories) and a mailbox of tens of thousands of mails make a plan that eats the model budget, or many quick list saves start many plans (each replacing the last) and burn the budget. | H | M | Plans use only the budget above the reserve of ADR-0021 and complete over days; new mail keeps its guaranteed share; a plan build starts only after the list has been stable for a short time and a newer list cancels the running build; a cap of 5 000 mails per plan, newest first, no age window (D15); list saves are rate limited per account (not per session, which new sessions would bypass). | AC-8, AC-11, AC-33 | LLM10; V2 |
| MC-12 | B1 plan page and approve call | D | A plan of tens of thousands of items freezes the page or the api; a request with thousands of ids exhausts memory. | M | M | Pages of 100 with "Load more" (no virtualised scrolling); approve by group or by at most 200 ids per call; body limit 8 KB as before, except 32 KB for `PUT /api/categories` (a full list is about 27 KB); items per plan capped (MC-11). | AC-24, AC-34 | V2 |
| MC-13 | list, decisions, applies | R | Nobody can later tell who changed the list, who approved which mail, or what the agent did. | M | M | An append-only audit for list versions (old and new), plan decisions and approvals (`plan_decision`, `plan_approval`: channel, keyed digest of actor, time), apply results and move-back requests (message ids, old and new label and counts, no sender or subject); retention only through the parameterless owner-role `purge_expired()` (ADR-0047); the database derives channel and actor as in ADR-0030; retention one year as the settings audit. | AC-36 | V16 |
| MC-14 | B6 Telegram notices | D | Repeated saves or a large plan flood the user with notices. | L | M | One notice per burst of list changes (as ADR-0033), one "plan ready" per plan, one result per apply; no per-mail messages. | AC-18 | -- |
| MC-15 | B5 descriptions to the model | I | A user puts something secret in a description, which then goes to the Anthropic API; or a description repeats other people's data. | L | L | Covered by A-1 (ADR-0018): same provider, same limits; the page states that the description is read by the model; descriptions are capped at 500 characters. | AC-1 | V8 |
| MC-16 | label names | T, S | A category name collides with a label that has another meaning: "Other", a system label, a name differing only in case, or an existing label `Archive`. | M | M | Names are compared after trim, NFKC and case folding, "Other" and "Archive" are reserved, `/` and format characters are forbidden, every list label lives under `Assistant/`; the label `Archive` is looked up as a top-level label by name without regard to case and adopted if it exists, never changed; the agent creates exactly one (a create race is retried as a lookup). | AC-2, AC-4, AC-25 | V2 |
| MC-17 | B2 and API, later more mailboxes | S, I | If a second mailbox or agent is added later, a user sees or approves plan items of another mailbox (object-level access). | L now, M later | H | Rows carry a mailbox id from the start and the repository layer filters on it; with one mailbox the id is a constant, and the repository test with two ids exists from R1 (AC-37); row-level security comes with several mailboxes. | AC-37 | V8 |
| MC-19 | R1 filing of new mail, stolen session or mailbox | T, I | A description such as "Newsletters: also Google security alerts and sign-in codes" makes the agent file the app's own sign-in code mail and Google security mail out of the inbox without approval; Undo restores the list but not the mails already filed. | M | H | The agent never files the app's own sign-in mail or Google security mail (verified sender, not the model's answer); urgency rules are fixed and separate from descriptions (C-16); pinned mail is never a plan item and never moved by an apply; every filing records the list version so mails filed under a version can be moved back after an Undo (R2; for the R1 window see MR-4); the list-change notice goes out even in quiet hours (MC-2). | AC-38, AC-39, AC-41 | LLM01, LLM06; V2, V16 |
| MC-20 | review page, display names | S | A sender display name or subject written by an attacker contains bidi or look-alike characters or imitates a trusted sender ("Your bank") so that the user approves a move wrongly. | M | M | The page shows the real address next to the name; format and bidi control characters are removed from sender and subject; text only. | AC-21, AC-44 | V1, V3 |
| MC-18 | migrations and deploy | T, D | The api is deployed before the agent has migrated the new schema, or a failed migration leaves half a schema. | L | M | As ADR-0025: the agent chain migrates, the api readiness check fails on a schema or contract version it does not know, migrations are reversible and tested up and down. | AC-20 | V13 |

All STRIDE types are covered: S (MC-2, MC-16, MC-17, MC-20), T (MC-1 to MC-5, MC-8, MC-9, MC-16, MC-18, MC-19), R (MC-13), I (MC-5 to MC-7, MC-15, MC-17, MC-19), D (MC-11, MC-12, MC-14, MC-18), E (MC-1, MC-3, MC-6, MC-10).

## Security acceptance criteria

The security criteria are AC-26 to AC-37, AC-38 to AC-44 and AC-48 in `docs/specs/mail-categories.md`; the spec is the only copy (the duplicate table that stood here was removed to avoid two wordings). Mapping: MC-1 AC-5 to AC-7, AC-38; MC-2 AC-18, AC-31, AC-32; MC-3 AC-31, AC-32, AC-41, AC-42, AC-48; MC-4 AC-22; MC-5 AC-21, AC-29; MC-6 AC-20, AC-27; MC-7 AC-19, AC-30; MC-8 AC-16, AC-26; MC-9 AC-14, AC-15, AC-35; MC-10 AC-14, AC-25, AC-28; MC-11 AC-8, AC-11, AC-33; MC-12 AC-24, AC-34; MC-13 AC-36; MC-16 AC-2, AC-4, AC-25; MC-17 AC-37; MC-19 AC-38, AC-39; MC-20 AC-21, AC-44.

## Accepted risks (each needs an ADR in phase 3; owner: the user)

| # | Risk | Reason |
| --- | --- | --- |
| MR-1 | Whoever can sign in to the web app (including someone who reads the user's mailbox, R-1 of web-settings) sees sender and subject of mails in a plan. | Decided by the user as D13. Reduced by: 14-day retention, purge at apply, `no-store`, web lock, Telegram notices without content, two-step verification on the mailbox (existing production condition of ADR-0033). Review together with R-1 on 2027-05-10. |
| MR-2 | The model may file a mail under a wrong category, or under "Other". | New mail is filed without approval, as today (R1). Old mail is reviewed before it moves (R2). A move only changes labels and is reversible. |
| MR-3 | Description texts are sent to the Anthropic API with mail text. | Extends A-1 of ADR-0018: same provider and limits, user-written text of at most 500 characters. |
| MR-4 | In the R1 window (list and filing of new mail, no plans yet) an Undo of a list change restores the list but does not move back mails already filed under it. | The security mail is pinned in the inbox (AC-39), mail is only labelled and stays findable under `Assistant/` in Gmail, and the list-change notice reaches the user even in quiet hours. The move-back of mails filed under a version arrives with R2 (AC-41). Reviewed with R-1 on 2027-05-10. |

## Round table 2026-11-14: decisions

Reviewed by security-architect, ux-critic, product-owner, qa-strategist and architect, merged by the moderator, then re-checked by security-architect and qa-strategist. Decided by the user on 2026-11-14: rename keeps the label without a plan (D14); cap of 5 000 items, no age window (D15); delayed apply above a threshold with Cancel and Lock, and Move back, no re-authentication (D16); Telegram Undo and Cancel are allowed as an exception to D1 (D17); no label delete (D18); success measures (D19). Added threats: MC-19, MC-20. Added criteria: AC-38 to AC-53 in the spec.

Calls made after the re-check (the user may change them): the threshold of D16 counts all approvals of a mailbox over a rolling 24 hours, so splitting an approval does not avoid the wait; threshold and delay are deployment configuration, never changeable from the web app; the delay is a plan state `scheduled`, decisions are frozen from the moment of approval and Cancel wins a race by compare-and-set; Telegram buttons are bound to the chat id, the plan or version id and a single-use nonce, and expire (AC-48); "verified sender" for the pinned mail is Gmail's `Authentication-Results` showing DMARC pass for a From domain on a configured allow-list; Move back restores labels that are no longer in the list, which is the one exception to AC-26 (it restores, it does not file); pinned mail is never a plan item and never moved by an apply.

## Open questions

1. **Mailbox id on the new tables:** recommended and put in the spec (Architecture fit); recorded as an ADR in phase 3.
2. Rename, re-authentication, plan size and age, label delete, urgency: decided (D14, D16, D15, D18, C-16, AC-38).
3. ASVS references are chapters of ASVS 5.0; requirement ids are added when the plan is made.
