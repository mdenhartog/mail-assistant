---
id: ADR-0026
title: "Mail triage: one conversation state for all Telegram dialogues"
status: accepted
area: architecture
tags: [mail-triage, telegram, state]
date: 2026-11-09
guardrails: [guardrail-telegram, guardrail-sqlalchemy-alembic]
---

## Context

Pending Telegram input is stored as `alert.awaiting_input`, tied to an alert, and any typed text answers whatever is awaited. A settings dialogue has no alert, and a settings answer could be read as a snooze answer (round table, 2026-11-09).

## Decision

A single-row `conversation` table (kind: snooze, reply or settings; target; step; partial values; random nonce; expiry) replaces `alert.awaiting_input`. Starting a dialogue replaces the current one and says what was dropped. Slash commands are handled before awaited text. Buttons carry the nonce and an index into stored candidates, never a value. `CommandRouter` becomes a registry of dialogue handlers (settings, snooze, reply). Settings questions expire after 15 minutes; snooze and reply questions keep their current behaviour.

## Consequences

- A migration drops `alert.awaiting_input`; the snooze and reply flows move onto the new state (rebuild, no wrapper).
- Stale or forwarded buttons are harmless because the nonce does not match.
- Telegram update ids are used to ignore replayed updates.

## Alternatives

- Add a second pending slot for settings: two competing slots and ambiguous text. Rejected.
- Put the dialogue state in memory: lost on restart. Rejected.
