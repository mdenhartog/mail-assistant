---
id: ADR-0057
title: "Always notify: a tick per category raises one alert next to the urgency alert"
status: accepted
area: product
tags: [label-structure, mail-triage, telegram, alerts]
date: 2026-11-21
guardrails: [guardrail-telegram, guardrail-python, guardrail-llm]
---

## Context

Today an alert exists only when the model judges a mail urgent (D7 of `mail-triage`; pinned Google security mail, ADR-0048). The user wants every new mail in a category they choose (D5), without losing the urgency alerts (D10), and never two alerts for one mail. Threat model LS-13, LS-20 and LS-21 name the flood, the platform-text and the unverified-sender risks.

## Decision

1. A pure function in `core/alert_decision.py` decides the alert: an alert exists when the mail is urgent **or** a category it is filed under (topic or extra label) is ticked. It returns one decision with every cause.
2. The alert starts with a fixed label, "Always notify: <category>" or "Urgent: needs your attention", and names every cause; it keeps the sender, subject, summary and the three actions of the existing alert. A sender-rule mail shows the verified domain, "content not checked by the model", no summary line and no clickable or masked link. A mail filed by the model in a ticked category without an authenticated sender says "sender not verified" and shows the real address, never only the display name (also for a missing or unparsable `From`).
3. One alert per mail, also across a restart: the alert is written once, keyed by the mail id (idempotent insert), before the Telegram send.
4. Quiet hours (held and sent together), the hourly cap of 5 alerts (to be confirmed against the current setting in phase 4) with batching, and the daily overview apply as today.
5. A mail moved by "Sort everything again" or handled by the INT-003 backlog never creates an always-notify alert.
6. Pinned mail (ADR-0048) keeps its own alert rules and is never filed by a sender rule.

## Consequences

- Extends ADR-0048; the existing alert text builder gets the label and the cause list.
- The tick is a new way to reach the user; accepted risk AR-1 (text of a platform that passes DMARC) is shown to the user in the alert.
- A busy tick can raise many alerts; the cap and batching bound it, and the Categories page shows the cap beside the tick.

## Alternatives

- Two separate Telegram messages (one per cause): double alerts. Rejected (D5).
- Alert only for urgent mail: what exists today. Rejected by the user.
