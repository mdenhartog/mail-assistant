---
id: ADR-0048
title: "Pinned mail: Google security mail raises an urgent alert, the app's own sign-in code mail stays silent"
status: accepted
area: security
tags: [mail-categories, mail-triage, telegram, privacy]
date: 2026-11-15
guardrails: [guardrail-gmail, guardrail-telegram, guardrail-python]
---

## Context

ADR-0045 pins two kinds of mail to the inbox: the app's own sign-in code mail and Google security mail from a verified sender (AC-39). The first build of U-05 completed pinned mail without an alert and left it out of the daily overview, so a Google security alert (new sign-in, password change) no longer reached the user. Pinning is about filing, not about alerting.

## Decision

1. Two allow-lists replace the single `PINNED_SENDER_DOMAINS` setting: Google security senders (default `accounts.google.com`) and the sender domains of the app's own sign-in mail (deployment configuration, no default).
2. Pinned Google security mail stays in the inbox, is never judged by the model, is never filed or a plan item, and raises an urgent Telegram alert with a fixed urgency. It appears in the daily overview. The alert text follows the existing capped alert rules and is built from the topmost `Authentication-Results` only.
3. Pinned sign-in code mail stays in the inbox, raises no alert, never sends its text to Telegram and is not in the daily overview.
4. Both kinds require the verified-sender check of ADR-0045 (topmost header from `mx.google.com`, dmarc=pass, `header.from` equal to the From domain).

## Consequences

- Keeps the behaviour before this feature for security alerts; the one-time code never leaves the mailbox.
- Extends ADR-0045; the settings, wiring and compose files of U-05 change (follow-up fix on `r1`).

## Alternatives

- Silent pinned mail (the first build): a taken-over Google account would go unnoticed. Rejected.
- Alert for both kinds: sends a one-time code into Telegram. Rejected.
