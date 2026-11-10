---
id: ADR-0037
title: "The web settings page is reachable only locally"
status: accepted
area: hosting
tags: [web, ingress, tls, exposure, local, mail-triage]
date: 2026-11-10
supersedes: ADR-0032
guardrails: [guardrail-kubernetes, guardrail-tls-certificates]
---

## Context

ADR-0032 made the settings page reachable from the internet because Marco travels. On 2026-11-10 Marco said that the whole management side is only available locally and not on the internet, and asked for a different sign-in (ADR-0036). Away from home he keeps Telegram, which can change the same settings.

## Decision

The page is reachable **only from the local network** (decision of Marco, 2026-11-10). There is no public ingress, no public DNS name and no port forward.

- The ingress (or service) listens on a private address. The host name is local and decided before staging.
- HTTPS stays on: a certificate from a private certificate authority that Marco's own devices trust. This keeps the `__Host-` cookies, `Secure`, HSTS (without `includeSubDomains`, no preload) and the HTTP to HTTPS redirect (AC-18). Certificate expiry is still monitored at least 14 days ahead.
- The ingress exposes only the web assets, `/api/*` and `/auth/*`; docs, OpenAPI, health and metrics answer 404 (AC-19). NetworkPolicies stay as designed.
- Telegram remains the way to change settings when away from the local network.
- Domain registration, Let's Encrypt, an internet-facing load balancer and a certificate on a public name are not needed.

## Consequences

- The surface is smaller: no internet scanning, and the code check is protected by the local network as well as by its own limits (ADR-0034, ADR-0036). The page is no longer "the first internet-facing surface of the project".
- The limits, the attempts per code, the session rules, the lock and the audit stay as designed; they protect against anything else on the local network and against a mistake in the network setup.
- Marco cannot open the page abroad without being on the local network (for example through a VPN he sets up himself); that is outside this feature.
- If the page is ever exposed to the internet, that needs a new decision and a new threat model review first.

## Alternatives

- Reachable from the internet (ADR-0032, superseded): needed a public name and certificate and a stronger sign-in surface.
- A VPN or private network as part of the product: not chosen; the local network is enough for now.
