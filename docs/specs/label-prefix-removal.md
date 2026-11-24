---
feature: label-prefix-removal
intent: INT-010
status: approved
revision: 2 (decisions D1 to D7 and P1 to P7 approved by the user, 2026-11-24)
date: 2026-11-24
approved: 2026-11-24 (the user, phase 1 gate)
approver: the user
depends_on: label-structure, mail-categories, mail-triage, web-settings
---

# Gmail labels without the Assistant prefix

## Summary

Every Gmail label that the agent manages carries the prefix `Assistant/` today (`Assistant/Aankopen/Marktplaats`). The user does not want it: the labels must carry the names of the category list (`Aankopen/Marktplaats`) (INT-010).

The prefix does three jobs today, so removing it replaces all three:

1. **Scope.** A mail is in scope when it sits in the inbox or carries an `Assistant/` label (`scope.classify`).
2. **Safety boundary.** The agent may only add, remove, create and rename labels under `Assistant/` (ADR-0046, ADR-0059 point 4); a reflection test enforces the allow-list.
3. **First list.** Version 1 of the list is seeded from the `Assistant/` labels that exist (`list_sync`, AC-49 of `mail-categories`).

After this change:

- The **list is the boundary**. The agent touches only labels whose name is the label of a category in the current list, the "Other" label and the archive label, each by Gmail label id once known.
- The two labels that are not in the list, "Other" and the archive label, get the default names `Other` and `Archive`, without `Assistant/`; the user can change both.
- The agent **deletes a label** when it has no mail, it is not in the list and it is not a Gmail system label, but only after it has stayed empty for a waiting time the user sets (up to 12 hours). This is new: ADR-0046 D18 forbids every label delete today.
- The labels that exist today under `Assistant/` are **renamed by id** after a backup and a preview; the mail on them stays.

It reverses parts of ADR-0046 (D18, no label delete), ADR-0059 point 2 and 4 (archive name rules and allow-list) and AC-49 of `mail-categories` (seed from labels).

## Who it is for

The user, with one mailbox and one agent (D7 of `mail-categories` stays: no several mailboxes).

## Goals

1. In Gmail (app and web) no label managed by the agent starts with `Assistant/`; the names and nesting are those of the list.
2. The mail that sat on `Assistant/...` labels is on the renamed labels afterwards; nothing is lost or moved.
3. The agent adds, removes and renames labels only for the list, "Other" and the archive label; it deletes only an empty label, never a Gmail system label.
4. An empty label that is not in the list is removed by the agent after the waiting time, and only then.
5. The user sets the name of "Other" and of the archive label on the Categories page.

## Non-goals

- Renaming a label that is not in the list, "Other" or the archive label (`Amerika`, `Aiden Auto`, ...), or changing the mail on it. Such a label is deleted only when it is empty (D6).
- A new prefix or a configurable prefix.
- Changing how the model judges, the sender rules, the alerts or the re-sort.
- Several mailboxes.

## Anti-goals (a failure even if it technically works)

- A label the user made by hand is renamed or merged without the user's say, or deleted while it still holds mail.
- A label that still holds mail, is still in the list or is a Gmail system label is deleted.
- A label is deleted the moment it becomes empty, without the waiting time.
- Mail loses a label, or an archived mail becomes part of a re-sort, during the rename.
- The agent becomes able to delete anything else than an empty, non-system label by id (no mail delete, trash or send).

## Decisions made by the user (INT-010, 2026-11-24)

| # | Decision |
|---|---|
| D1 | The `Assistant/` prefix is removed from all labels the agent manages. |
| D2 | The boundary of the agent is the category list (plus "Other" and the archive label). |
| D3 | The agent may delete a label when all mail has moved out, it holds no mail and it is not in the list. |
| D4 | Existing `Assistant/` labels are renamed by label id. |
| D5 | "Other" and the archive label have default names (`Other`, `Archive`) without `Assistant/`, always used as the base; the user can change them. |
| D6 | The agent may delete every empty label that is not in the list and is not a Gmail system label, also a label the user made by hand. |
| D7 | A delete always waits: a label must stay empty for a waiting time the user sets, from a minimum up to 12 hours, before it is deleted. |

## Decisions proposed here (to be confirmed by the user)

| # | Proposal | Why |
|---|---|---|
| P1 | The rename runs once, as a prepared plan: a preview (old name, new name, mails on it), a backup of the label table, and a Telegram notice when it is done. Nothing is renamed before the user presses the button on the Categories page. | A rename touches the real mailbox; the user sees what will change. |
| P2 | On a name clash (the new name is also a label the user made, with or without mail) the rename of that label **stops** (an empty clashing label is not deleted to make room; the normal waiting time rules apply), the rest continues, and the user decides on the page: keep both under a different list name, or merge. The agent never merges by itself. | Anti-goal 1. |
| P3 | A label is deleted only when (a) it is not a Gmail system label, (b) it is in no current list or setting, (c) Gmail reports `messagesTotal = 0` and `threadsTotal = 0`, (d) it has no child label, and (e) it has been seen empty in every check for the whole waiting time, checked again just before the delete. A parent whose children are empty goes after them, one level per cycle. | Deleting a parent in Gmail would turn its children into top-level labels; the double check and the waiting time make a late mail or a re-sort safe. |
| P7 | The waiting time is a list-level setting (like the archive name), default 12 hours, minimum 5 minutes, maximum 12 hours, versioned and audited. | D7: it always waits; the user sets it. |
| P4 | The first list is no longer seeded from Gmail labels: it comes from the uploaded YAML. A mailbox without a list does nothing, as before version 1 exists. | Without the prefix, managed labels cannot be told from the user's own. |
| P5 | The name of "Other" is a list-level field next to the archive label (ADR-0059), versioned and audited like the list. | Same mechanism, no new place. |
| P6 | Matching by name keeps working until the label id is stored: a hand-renamed label is found by id afterwards. The label id is stored per category (the known limit "a hand-renamed archive label is not found by id" is closed for all labels). | The id is the stable link once the prefix no longer marks ownership. |

## Constraints

- The contract of the list changes (label name rules, the "Other" and archive names): `rebuild-not-patch`, one contract, no flag or second mode, no environment switch.
- Existing data migrates in place (expand and contract); old `Assistant/` names are mapped by the migration and the rename plan, never left in two forms.
- ADRs: a new ADR supersedes ADR-0046 D18 and ADR-0059 points 2 and 4; the model of `docs/architecture/model.json` stays as is unless the placement says otherwise.
- No secret, mail text, sender or subject in logs, notices or the audit (label names are the user's own and appear only in the web app and the preview).
- Gmail scope stays `gmail.modify` (label delete is covered by it).

## Behaviour

1. **Boundary.** A label is *managed* when its id or its name is the label of a category of the current list, the "Other" label or the archive label. Everything else is read-only for the agent.
2. **Scope.** A mail is in scope when it sits in the inbox or carries a managed label; the archive label and the excluded labels win, as today.
3. **Rename plan (once).** The page lists the old `Assistant/...` labels with the new name and the count of mail; on confirmation the agent renames them by id, one at a time, stores the ids, and reports the result.
4. **New names.** A new category creates its label (by the list name), a renamed category renames it (by id), as today without the prefix.
5. **Delete.** Each cycle the agent looks at the labels that are not system labels and not in the list. A label with no mail and no child starts a timer; when it is empty again at every check and the waiting time has passed, it is deleted (one per cycle, with a notice of counts). A mail arriving or a label coming back into the list resets the timer.
6. **Clash.** See P2.

## Architecture fit

- **`category-policy`** (shared): the label mapping (`label_for`, `LABEL_PREFIX`, name length rules) loses the prefix; the archive and "Other" name rules change.
- **`mail-triage` agent**: scope, Gmail adapters (`gmail_read`, `gmail_resort`, `gmail_apply`, `list_sync`), judgement, resort build/apply and move back change; a new narrow label delete and a rename plan runner.
- **`api` and `web`**: the "Other" name field, the rename preview and confirmation on the Categories page, a clash decision.
- **`platform`**: only if the migration job needs a value.
- No new component is needed: the work belongs to the components that own labels today.

## Acceptance criteria (draft)

1. Given a list with the category `Aankopen/Marktplaats`, When the agent creates its label, Then the Gmail label is `Aankopen/Marktplaats` (happy).
2. Given a mail that carries `Aankopen/Marktplaats` and a list with that category, When the scope is decided, Then the mail is in scope (happy).
3. Given a mail with only the label `Amerika` that is not in the list, When the scope is decided, Then the mail is out of scope and the label is never changed (security).
4. Given an old label `Assistant/Aankopen/Marktplaats` with 12 mails, When the user confirms the rename plan, Then the label is renamed by id to `Aankopen/Marktplaats` and the 12 mails are still on it (happy).
5. Given the preview, When the user has not confirmed, Then no label is renamed (security).
6. Given the new name equals a label the user made, When the plan runs, Then that rename stops, the others go on, and the page asks the user (error).
7. Given an empty label that is not in the list and has stayed empty for the whole waiting time, When the agent runs, Then it deletes the label and reports it (happy).
8. Given a label that still holds one mail, When the agent runs, Then it is not deleted (security).
9. Given a label that is in the list but empty, When the agent runs, Then it is not deleted (security).
10. Given an empty label that is not in the list but the waiting time has not passed, When the agent runs, Then it is not deleted (security).
10a. Given a label that was empty and gets a mail within the waiting time, When the agent runs, Then the timer resets and the label stays (edge).
10b. Given a Gmail system label (`INBOX`, `SENT`, `CATEGORY_*`, ...) that is empty, When the agent runs, Then it is never deleted (security).
10c. Given an empty parent label with an empty child, When the agent runs, Then the child goes first and the parent a cycle later, after its own waiting time (edge).
10d. Given a waiting time above 12 hours or below the minimum, When the user saves, Then it is refused (error).
11. Given the allow-list, When the reflection test runs, Then the agent can delete only a label by id through the narrow delete, and no other delete, trash or send exists (security).
12. Given a new installation, When no names are set, Then "Other" is `Other` and the archive label is `Archive`; Given the user changed either, Then the changed name is used (happy).
13. Given a name for "Other" or the archive that clashes with a list category or a system label, When the user saves, Then it is refused with a clear message (error).
14. Given a first start without a list, When the agent runs, Then it seeds nothing from Gmail and waits for the upload (edge).
15. Given a hand-renamed label whose id is stored, When the agent runs, Then it is found by id and not recreated (edge).
16. Given the migration, When it runs twice, Then the second run changes nothing (edge).
17. Given the plan page, When it is used with the keyboard and a screen reader, Then every control has a name and the focus moves to the result (a11y).
18. Given logs and notices, When a rename or a delete happens, Then they carry counts only, never mail data (security).

## Open points for the user

1. Is the default waiting time of 12 hours (P7) right, or do you want a shorter default?
2. P1 (rename once, with a preview and your button), P2 (stop on a clash) and P4 (the first list only from the YAML) are not answered yet.
3. The confirmed intent says "it must not touch any label that is not in my category list". D6 allows deleting such a label when it is empty. The intent wording needs your amendment.
