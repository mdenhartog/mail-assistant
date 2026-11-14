---
id: ADR-0033
title: "Web changes are announced with their own Undo token and a lock for web sign-in"
status: accepted
area: security
tags: [web, telegram, undo, audit, mail-triage]
date: 2026-11-10
guardrails: [guardrail-telegram, guardrail-oauth2-oidc]
---

## Context

The spec accepts risk R-1: anyone who can read Marco's mailbox can sign in (the web sign-in is a username and a code sent by e-mail, ADR-0036). What limits the damage is the Telegram notice with Undo for every web change (W-11, AC-13). The design round table found that this control, as first designed, does not hold for someone with a session:

- Undo restores one step and only while the row is still at that version. After two quick web saves, the Undo of the first notice fails and the Undo of the second restores the attacker's first change.
- The Undo of a quiet-hours change lives in the single conversation row (ADR-0026) with a 24 hour life; a web notice that used the same row would replace a Telegram dialogue Marco is in.
- A web session lives up to 12 hours and nothing ends it from Telegram.

## Decision

1. **Own token record.** A web notice has its own short-lived token record in the agent's database, not the conversation row. A web notice never replaces a Telegram dialogue in progress.
2. **Undo goes back to before the burst.** One notice per web change, but the Undo of every notice restores the values as they were before the first web change the agent had not yet announced, guarded by the current version; it writes one audit record.
3. **A lock button.** Each notice also has "Undo and lock web sign-in". The agent writes `web_auth.web_lock` (the agent role gets insert and update on that one table and nothing else in `web_auth`). While it is set, the api refuses every session request and every sign-in callback, and deletes sessions. It is cleared only by a command in Telegram.
4. **Quiet hours never hold the notice.** That includes quiet hours the change itself has just set.
5. **Review date for R-1.** R-1 is reviewed on 2027-05-10. The mailbox that receives the sign-in code must use two-step verification or a passkey; this is a condition for production.
6. Notices are selected by `settings_change.db_role` (derived on the server) and ordered by the version as an integer, never by the text of the version or by the writer's own `updated_by`.

## Consequences

- R-1 becomes defensible: a thief can be reversed and locked out from Telegram.
- A new table (`web_auth.web_lock`), one narrow grant for the agent and a lock check in the api on every request.
- The notice latency equals the agent's run interval; the page says "within about N minutes" with the real interval.
- The agent stays a reader of the web tables except for the lock.

## Alternatives

- One Undo per notice as in Telegram: fails after a burst of changes; rejected.
- Re-authentication for every write: more friction for Marco on a phone, and it does not help when the mailbox itself is taken; kept as an option for later.
- A Telegram command only to lock: slower in the moment than a button on the notice.

## Amendment 2026-11-14 (phase 8, what was built)

- **Agent grants.** Besides insert and update on `web_auth.web_lock`, the agent role has `DELETE` on it (`/web_unlock` removes the row) and on `web_notice_token` (expired tokens are removed), and column `SELECT (id, kind, at, count)` on `web_auth.security_event` for the wrong-code alert (ADR-0039). It has nothing else in `web_auth`. Only the owner purge deletes from `settings.settings_change`.
- **Commands.** `/web_lock` sets the lock from the allowed Telegram chat and says whether it was already set; `/web_unlock` lifts it. The sign-in e-mail names `/web_lock` for the case that Marco did not ask for the code. The agent also sets the lock by itself after 15 wrong codes in 24 hours (ADR-0039).
- **Alert and lock are R1**, not R2.
