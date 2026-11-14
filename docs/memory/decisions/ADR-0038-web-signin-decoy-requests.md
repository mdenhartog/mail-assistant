---
id: ADR-0038
title: "Web sign-in: unknown usernames get a decoy login request with the same counters"
status: accepted
area: identity
tags: [authentication, web, enumeration, one-time-code, mail-triage]
date: 2026-11-12
guardrails: [guardrail-fastapi, guardrail-sqlalchemy-alembic]
---

## Context

ADR-0036 says the sign-in answers the same way whether or not the username is known. The verify-code endpoint (U-web-settings-18) shows the gap: the refusal body carries `attemptsLeft` only when the `__Host-login` cookie names a live login request. A visitor who asks for a code for username X and posts one wrong code sees `attemptsLeft: 4` for the real username and no `attemptsLeft` for any other name. That tells a visitor which username exists. A wrong-format code also answers with the unchanged count, which shows that it was not counted. The threat model (W-2) wants no enumeration.

## Decision

Marco decided on 2026-11-12: **show `attemptsLeft` every time, also for an unknown username.**

- A request for an unknown username creates a **decoy login request**: the same row, the same `__Host-login` cookie, the same expiry (10 minutes), the same attempt counter and the same 60 second cooldown as a real one. No code is sent and no code hash is stored that can match.
- Verifying against a decoy counts attempts exactly like a real request, answers `attemptsLeft` in the same way, and after 5 wrong attempts it is dead, with the same cookie clearing. A right-looking code is always refused with the generic answer.
- A code of the wrong format is handled the same way for real and decoy requests.
- Decoys use the per-hour cap and the in-process limits of ADR-0034 like real requests, so a flood of unknown names cannot fill the table (corrected by ADR-0039: decoys of many usernames can fill the cap; decoys now have their own cap and never block the configured username); expired rows are purged with the existing retention.
- The timing of both paths is the same within noise; a test compares them.

## Consequences

- The answer no longer separates a known username from an unknown one.
- One more branch in the request-code and verify-code flow, and a flag on the login request that is never exposed.
- The extra rows are bounded by the limits and the retention purge.

## Alternatives

- Never show `attemptsLeft`: simplest, but Marco no longer sees how many attempts are left.
- Accept the leak, because the page is local only (ADR-0037): needs an accepted risk in the threat model; not chosen.
