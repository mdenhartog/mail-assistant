---
id: ADR-0059
title: "The archive label name is part of the list; the agent adopts, creates or renames it"
status: accepted
area: product
tags: [label-structure, mail-triage, gmail, configuration]
date: 2026-11-21
supersedes: ADR-0052
guardrails: [guardrail-python, guardrail-gmail, guardrail-pydantic]
---

## Context

ADR-0052 made the archive label name an agent setting (`ARCHIVE_LABEL`, default `Assistant/Archive`) and said that after a change the old label stays and is no longer protected. The user wants to set it in the app (D7), and an anti-goal says a change must not make archived mail part of a re-sort. The architect and product-owner noted that a rename by id widens the Gmail allow-list and that ADR-0052 allowed adopting an existing label.

## Decision

1. The name is a list-level field in `list_settings` (ADR-0053), versioned and audited like the list; the Categories page shows and saves it. The environment setting `ARCHIVE_LABEL` is removed from the agent, compose and Helm. The migration job reads `ARCHIVE_LABEL` once (when present, else the default `Assistant/Archive`) into the migrated `list_settings` rows, so a custom value is not lost; afterwards the variable is ignored.
2. A valid name: 1 to 225 characters, no control characters, no leading or trailing space, no `..`, outside `Assistant/` or exactly `Assistant/Archive`, not a Gmail system label (INBOX, SPAM, TRASH, `CATEGORY_*`, compared without regard to case), and never equal to or below a category label; a category name never lies below the archive label (first segment "Archive" is reserved, ADR-0053).
3. **First time set:** an existing Gmail label of that name is adopted, else created. **Later change (D14):** the agent renames the existing label by id, so mail in it stays protected; it never creates a second archive label and never moves mail into or out of it. A rename waits until no plan is `scheduled` or `applying`, and new mail is judged meanwhile.
4. The agent's label operations stay on an allow-list: labels under `Assistant/` (create, add, remove, rename by id) and the archive label by id. A reflection test enforces it (extends AC-28 of `mail-categories`).
5. The matching rules of ADR-0052 stay: a mail that carries the archive label is out of scope and wins over a category label; matching is by label, not by prefix.

## Consequences

- Supersedes ADR-0052 in full (it moves to `archive/` when this ADR is accepted).
- A rename of a label outside `Assistant/` is a new write on a user-owned label; the allow-list names exactly that one label by id.
- If the name changes while the old label does not exist, the new one is created.

## Alternatives

- Keep the environment setting: the user asked to set it in the app. Rejected.
- Create a new label on change and leave the old one: archived mail becomes part of the next re-sort. Rejected (anti-goal).
- Allow only names under `Assistant/`: rules out an existing label such as `Bewaard`. Rejected.
