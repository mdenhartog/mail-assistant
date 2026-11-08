---
id: ADR-0019
title: "Mail triage: one new agent component with its own Telegram client"
status: accepted
area: architecture
tags: [mail-triage, agents, telegram, gmail, postgresql]
date: 2026-11-08
guardrails: [guardrail-gmail, guardrail-llm, guardrail-telegram, guardrail-sqlalchemy-alembic, guardrail-python]
---

## Context

`mail-triage` (spec `docs/specs/mail-triage.md`) must poll Gmail, judge mail with a model, start conversations with Marco in Telegram (alerts with buttons, drafts to confirm, reminders, a daily overview) and send mail only after confirmation. The scaffold has `channels/chat-gateway` (a stateless webhook relay: message in, agent answer out, public HTTPS needed) and `agents/assistant` (a Bedrock chat agent).

## Decision

Create one new component, `agents/mail-triage`, built in the ports-and-adapters style:

- **Core** (pure, no I/O): urgency policy, state machine of an alert (open, held, snoozed, confirmed, closed), quiet hours, reminder and digest timing.
- **Adapters**: Gmail (label and send only), Anthropic model (structured result only, no tools), Telegram (long polling and sending, allow-list), PostgreSQL (state, audit, encrypted token).
- The component runs as a single replica (a database lock stops a second copy from processing).
- `channels/chat-gateway` and `agents/assistant` are not changed and not used by this feature.

## Consequences

- No public inbound endpoint is needed (long polling for Gmail and Telegram), which keeps the attack surface small (spec D9, D11).
- The Telegram code lives inside the agent, so there is no internal API between agent and gateway to secure. If a second feature needs Telegram, the adapter is moved to its own component then (rebuild, not patch).
- `chat-gateway` stays unused for now; whether to remove it is a later decision.
- The new component is registered in `.sdlc/components.json` via `/sdlc:component`.

## Alternatives

- Extend `channels/chat-gateway` — rejected: it is stateless and request/response with webhooks; alerts, buttons, confirmations and reminders need agent-initiated, stateful conversation. Bolting that on would break its contract.
- Separate agent and Telegram components — rejected for now: only one feature uses Telegram, so it would add a network hop and an internal API to secure without a benefit.
- Bedrock AgentCore runtime — rejected by ADR-0017.
