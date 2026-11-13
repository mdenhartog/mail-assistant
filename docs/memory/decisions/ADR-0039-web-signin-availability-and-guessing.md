---
id: ADR-0039
title: "Web sign-in: protect the owner from lock-out, limit per client, and lock the web after repeated wrong codes"
status: accepted
area: identity
tags: [authentication, web, rate-limit, denial-of-service, one-time-code, mail-triage]
date: 2026-11-13
guardrails: [guardrail-fastapi, guardrail-sqlalchemy-alembic, guardrail-kubernetes, guardrail-helm]
---

## Context

The phase 6 challenge of `web-settings` (red team, security review, code review, all on `main` 67b137e) found that one device on the local network can keep Marco from signing in, and that guessing is not detected in R1:

- Decoy login requests (ADR-0038) for random usernames fill the cap of 100 open login requests; every request for the real username is then refused. About 10 requests a minute keep it full. ADR-0038 said a flood of unknown names cannot fill the table; that is wrong across usernames (RT-01, SEC-02).
- Anyone who knows the username kills Marco's live login request with each new request and uses up the 5-codes-an-hour cap (RT-04).
- The Helm chart sets no trusted proxy, so in Kubernetes all clients share one rate-limit bucket (RT-02, SEC-01). An IPv6 client gets a fresh bucket per address (RT-03). Session routes are not limited before the session check (RT-05).
- With 5 codes an hour and 5 attempts per code, a guesser gets 25 attempts an hour with no alert; the alert (U-48) is R2 and the one-row-per-minute event dedup would stop it from firing (SEC-03, SEC-04).

## Decision

Marco decided on 2026-11-13:

1. **Protect the owner and limit per client.**
   - A request for the configured username is never refused because of decoy rows. Decoys have their own cap and do not count towards the owner's.
   - Open login requests and codes per hour are also capped per client (a hash of the client key is stored on the row). IPv6 clients are keyed by /64. The limiter caps its counters per window.
   - A request from another client does not kill a live login request of the same username; only a request with the same login cookie or the same client replaces it. The 5 codes an hour per username stay, so the guessing budget does not grow.
   - Every limit and every `Retry-After` is the real remaining wait, and the hourly cap counts from the same timestamp for real and decoy rows.
   - Session routes are rate limited before the session lookup.
2. **Detect and stop guessing in R1.**
   - The wrong-code alert (U-48) moves into R1. `code_refused` events are counted, not deduplicated per minute.
   - The agent sets the existing web lock (ADR-0033) when 15 wrong codes are seen in 24 hours and tells Marco in Telegram; he unlocks with `/web_unlock`. While the lock is set, a code request gets the same answer but no code is created and no mail is sent.
   - The code mail says what to do if the code was not asked for.
3. **Production-readiness of the edge.** The chart takes trusted proxy CIDRs and hops from values and the start-up refuses an empty list in production. The values schema requires a non-empty HSTS mechanism when `hsts` is true.

## Consequences

- One device can no longer lock Marco out of sign-in, by decoys or by his username. A group of devices can still use the 5 codes an hour of the username; that costs Marco a delay of up to an hour, is visible in the security events and does not touch Telegram.
- A guesser can force the web lock with 15 wrong codes in a day. That is a visible, recoverable denial of web sign-in (Marco unlocks in Telegram) and is preferred over a silent takeover. Recorded as R-3 in the threat model.
- One migration for the client hash on the login request, one for the Undo burst (CR-07), one `count` column on `security_event`; numbers are checked against `main` before merge.
- ADR-0038 stays accepted; its claim on the table size is corrected by this ADR.

## Alternatives

- Accept the lock-out as a risk (R-3 only): no code change, but any device on the network could deny sign-in at no cost. Not chosen.
- Limit per client only: does not stop several devices together or the known-username kill. Not chosen.
- A daily cap on codes per username instead of the lock: gives a guesser a way to keep Marco out for 24 hours without his knowledge. Not chosen.
