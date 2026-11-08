---
id: ADR-0018
title: "Mail triage: accepted data-disclosure risks"
status: accepted
area: security
tags: [privacy, anthropic, telegram, threat-model]
date: 2026-11-08
guardrails: [guardrail-llm, guardrail-telegram]
---

## Context

The threat model for `mail-triage` (`docs/security/mail-triage-threat-model.md`) found two disclosures that cannot be removed without dropping what Marco asked for in INT-001. Marco owns the mailbox and accepts both.

## Decision

- **A-1:** Mail text (subject, sender, trimmed body, including other people's data inside it) is sent to the Anthropic API for categorising and judging urgency. Reduced by: no attachments ever, a size cap per mail, one mail per call, a zero-retention setting where available (ADR-0017).
- **A-2:** Short summaries of mails that need attention pass through Telegram's servers, which are not end-to-end encrypted for bots. Reduced by: a short summary only, never the full body or attachments, escaped text, an allow-list of Marco's own chat.

## Consequences

- Mail from other people is processed by a third party. This is acceptable for Marco's personal mailbox only; a shared or business mailbox needs a new decision.
- Any change that sends more data (attachments, full bodies) or uses another model provider or channel needs a new ADR and a threat-model update.
- The owner of both accepted risks is Marco.

## Alternatives

- Process mail with a local model — rejected earlier (ADR-0014, ADR-0017).
- Alert without any content ("you have an urgent mail") — rejected: Marco could not decide anything from it.
