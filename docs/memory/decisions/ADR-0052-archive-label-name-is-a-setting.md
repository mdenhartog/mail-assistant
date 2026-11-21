---
id: ADR-0052
title: "The name of the archive label is a setting of the agent, default Assistant/Archive"
status: accepted
area: product
tags: [mail-categories, mail-triage, gmail, configuration]
date: 2026-11-21
guardrails: [guardrail-python, guardrail-gmail, guardrail-pydantic]
---

## Context

Spec C-14 fixed the protected label as the top-level label `Archive`: mail the user files there is never re-sorted and the agent never puts mail in it. The first deploy against a real mailbox showed that Gmail refuses to create a label with that name (HTTP 400 `invalidArgument`, ADR-0051 and PR #154), so the protected place did not exist. The user wants to choose the name of that label, and wants a default that Gmail accepts. The label holds mail that is already handled and no longer important, but that must be kept.

## Decision

1. The name is the setting `ARCHIVE_LABEL` of the mail-triage agent. The default is `Assistant/Archive`. Gmail accepts names under `Assistant/` (the category labels already live there).
2. The agent creates the label when it is missing (as C-14 said for `Archive`), never puts mail in it and never removes it. A mail that carries it is out of scope, and wins over an `Assistant/` category label. Matching is by name, without regard to letter case, as before.
3. A valid name has 1 to 225 characters, no control characters, no leading or trailing space, no `..`, is not a Gmail system label name and is not `Assistant/Other`. It is either outside `Assistant/` (for example `Bewaard` or `Mail/Done`) or exactly `Assistant/Archive`. A name of the form `Assistant/<other>` is refused at start, because the category rules (one level, reserved names `other` and `archive`, shared with the web page and the api) would then take it for a category. A wrong value stops the agent at start with a clear error, never silently.
4. The reserved category names do not change: `Archive` and `Other` stay unusable as category names.
5. The agent never changes the name of an existing label. After a change of the setting the old label stays as the user left it and is no longer protected; the new one is created.

## Consequences

- One component knows the name: the agent. The web page says "your archive label" and does not name it; the user guide names the default and the setting.
- A user who already has a top-level `Archive` label and wants it protected sets `ARCHIVE_LABEL=Archive`.
- Mail in a label that was protected before a change of the setting becomes in scope for the next plan (label moves only, nothing is deleted, the user reviews the plan first).
- The check of the name is code, the allow-list of the Gmail adapter (AC-28) still holds: only the configured archive label and labels under `Assistant/` are created.

## Alternatives

- Keep the name `Archive` and ask the user to create it by hand: rejected, the protection silently does not exist when the label is missing.
- A fixed name `Assistant/Archive` without a setting: rejected, the user asked to choose.
- Let the user pick any name under `Assistant/`: rejected, it would collide with the category rules shared with the web page and the api.
- A setting in the web page: later option; it needs a database column and a role change, the environment setting does not.
