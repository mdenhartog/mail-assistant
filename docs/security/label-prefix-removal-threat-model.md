---
feature: label-prefix-removal
intent: INT-010
spec: docs/specs/label-prefix-removal.md
extends: label-structure-threat-model, mail-triage-threat-model
status: approved
revision: 2 (after the phase 2 round table, 2026-11-24; approved by the user)
date: 2026-11-24
asvs: "5.0"
---

# Threat model: Gmail labels without the Assistant prefix

This model adds to `label-structure-threat-model.md` and `mail-triage-threat-model.md`. The sign-in, session, CSRF and Telegram designs are unchanged.

## Scope

New in this feature:

- The boundary of what the agent may change in Gmail moves from "a name under `Assistant/`" to "a label of the current list, plus the "Other" and archive labels, matched by Gmail label id".
- A **label delete** (new Gmail write): any empty label that is not in the list and is not a Gmail system label, after a user-set waiting time (5 minutes to 12 hours).
- A **one-off rename plan** of the existing `Assistant/` labels, run only after the user confirms a preview.
- Two list-level settings, the name of "Other" and the waiting time, next to the archive name (ADR-0059).

Out of scope: mail bodies, sender rules, the model prompt, sign-in, several mailboxes.

## Data classification

| Data | Class | Note |
| --- | --- | --- |
| Label names (list, Gmail) | internal; may reveal the user's life (health, money) | Shown only in the web app and the preview; never in a log, a URL, a Telegram text or the audit (counts only). |
| Label ids and the label-id table | internal | Agent-owned; the api reads names and counts only. |
| Label message and thread counts from Gmail | internal | Used for the delete decision; not stored beyond the timer. |
| Delete timers (label id, first seen empty) | internal | Agent-owned; no names. |
| Rename plan and its backup (old name, id, new name, count) | internal | Stored for the preview and the undo; retained with the list audit, no mail data. |
| Waiting time, "Other" name | internal | List-level settings, versioned and audited. |

## Trust boundaries

1. Browser to api: the settings and the rename button (existing session, CSRF and role checks).
2. Api to database to agent: the agent reads the settings and the confirmed plan; it does not call the api.
3. Agent to Gmail (`gmail.modify`): the only place a label changes. A new delete and a rename by id cross it.
4. The user's own Gmail labels and other Gmail clients: labels can be created, renamed, deleted and filled by the user or other apps while the agent runs.

## Threats (STRIDE)

| id | element | STRIDE | threat | L | I | mitigation | criterion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | the delete | T, E | A bug or a stale list makes the agent delete a label that holds mail or is in the list; Gmail removes the label from every mail on it. | M | H | Triple check: not a system label (by id and by name, case-insensitive, `CATEGORY_*` included); counts `messagesTotal = 0` and `threadsTotal = 0` read just before the delete; not in the list version read in the same step; no child label. The delete is by id only. | AC 7 to 10, 10b, 10c |
| T2 | the waiting time | T | A mail arrives, or a re-sort is moving mail into a label, between the check and the delete. | M | H | The label must be empty at every check for the whole waiting time; a mail, a list change or a plan touching it resets the timer; the last check is made immediately before the delete call; a re-sort in progress blocks deletes of labels it targets. | AC 10a |
| T3 | the delete | E | The agent can now delete labels; a prompt-injected mail or a model answer reaches the delete. | L | H | The delete is reached only from the cycle's own timer logic, never from model output or mail content; a reflection test allows exactly one delete call (by id) and no trash, delete-mail or send. The model has no tool for labels. | AC 11 |
| T4 | the boundary | E | The list as boundary: an uploaded YAML names `INBOX`, `SENT`, `Amerika` or another label of the user, and the agent then adds, removes or renames it. Since D8 an existing user label is adopted without a confirmation. | H | H | A category name that equals a Gmail system label, a label the user made outside the agent's history, or a reserved name is refused at upload (preview shows the clash); an adopted existing label requires an explicit confirmation of that name; renames by id only of ids the agent stored. | AC 3, 6, 13 |
| T5 | the rename plan | T | The rename plan renames a label the user made, or two labels onto one name (a merge). | M | M | The plan lists only ids that the agent created or that carry `Assistant/`; a name clash stops that rename; the agent never merges; every rename is one id and one name. | AC 4 to 6 |
| T6 | the rename plan | R | The user cannot see or undo what changed. | M | H | Preview before, a backup of the old names and ids, a notice with counts after; the old name is restorable by the same operation. | AC 4, 5, 18 |
| T7 | label names | I | A label name reaches a log, a URL, the audit or Telegram. | L | M | Counts only in logs, audit and notices; names only in the web app and the preview; redaction test extended. | AC 18 |
| T8 | the api | S, E | Another session or a CSRF request starts the rename or changes the waiting time to the minimum. | L | H | Existing session, role and CSRF protection; the rename needs a typed confirmation that carries the plan hash; the waiting time has a hard minimum of 5 minutes in code and database. | AC 5, 10d |
| T9 | Gmail | D | A long list of deletes or renames exhausts the quota or loops. | L | M | One delete per cycle, one rename at a time with back-off on 403/429; no retry loop on a refused delete. | AC 4, 7 |
| T10 | the stored ids | T | The user renames a label by hand; the agent then acts on a stale name and creates a duplicate or deletes the wrong one. | M | M | The id is the link (P6); a name that no longer matches its id is re-read, not recreated; a delete never starts from a name. | AC 15 |
| T11 | the migration | T | The migration runs twice or half-way and leaves two forms of a name. | M | M | Idempotent migration and plan; expand and contract; a test that runs it twice. | AC 16 |
| T12 | scope | I, T | Without the prefix a mail in `Amerika` (not in the list) is read, judged or moved. | M | H | Scope = inbox or a managed label; any other label leaves the mail out of scope; the archive and excluded labels win. | AC 2, 3 |

## Round table result (phase 2)

Reviewers: security-architect, architect, qa-strategist (also product and UX). No Critical finding; one user, every change needs a session and CSRF.

New threats:

| id | element | STRIDE | threat | L | I | mitigation (spec) | criterion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T13 | adopt, drain, delete | T, E | A label of the user is adopted (D8), its mail is moved out by a re-sort, it leaves the list and is deleted; every step passes its own check. | M | H | A label that left the list less than 7 days ago is not deleted (R6, awaits the user); adoption and re-sort in the same version never move mail out of the adopted label. Accepted by the user under D8; this is the control. | AC 19, 28 |
| T14 | Gmail filters | T, D | An empty label that a Gmail filter targets is deleted and the filter loses its action. | M | H | R1: read the filters, never delete a targeted label. | AC 21 |
| T15 | the emptiness check | T | Counters lag; mail only in spam or trash is counted as gone; no conditional delete exists. | M | H | R2: type `user`, counts and a second `includeSpamTrash` check, doubt means not empty; R9: a lease and an adjacent re-check and delete. | AC 22, 30 |
| T16 | the waiting time | T, E | Lowering the time from 12 hours to 5 minutes makes running timers fire at once. | L | H | R3: a new time applies only to new timers; timers persist per label id. | AC 23, 24 |
| T17 | the sync | T | After the deploy the sync renames labels before the user confirms. | H | H | R4: a migration state blocks all label writes until the plan is done; scope and allow-list by id. | AC 25 |
| T18 | the rename plan | T | The plan is stale between the preview and the run. | M | M | R5: the hash covers id, old and new name; each id is re-read; a hand-renamed entry is skipped. | AC 26, 27 |
| T19 | notices and errors | I | Gmail errors and `LabelRefused` messages echo a label name; the backup keeps old names. | L | M | R7: codes only in exceptions, status and reason in logs, backup removed after 30 days, a canary test. | AC 29 |
| T20 | the delete record | R | The user cannot tell which label went (the daily notice has counts only, D10). | M | M | R7: "recently deleted" on the page for 30 days; the audit keeps counts and a hash of the id. | AC 29 |

Changed: T4 likelihood M to H (D8 and the chain of T13), T6 impact M to H (a delete cannot be undone).

Accepted risks, added: A3: D8 adopts an existing label without a confirmation (the user's decision, 2026-11-24); the 7-day protection of R6 is the control.

Open questions closed: the delete notice is one message a day with counts only (D10); the waiting time default stays open (12 hours proposed).

## Accepted risks (need an ADR owned by the user)

- A1: an empty label the user made by hand may be deleted after the waiting time (D6). Accepted by the user; the waiting time and the notice are the control.
- A2: a label deleted in error cannot be restored with its mail from the agent; Gmail can restore a deleted label's name only by recreating it. Accepted because the delete requires zero mail.

## Open questions

- The waiting time default (12 hours proposed).
- Whether a notice goes to Telegram per delete or once per day.

## ASVS mapping

V4 (access control: boundary, delete), V5 (input: names, uploaded YAML), V8 (data protection: no names in logs), V13 (API: confirmation, CSRF), V7 (logging: counts only).
